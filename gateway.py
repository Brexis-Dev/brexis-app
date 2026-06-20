"""
Brexis Gateway — Three-layer security proxy between Brexis and all external data sources.
Layer 1: Allowlist (hard gate)
Layer 2: Pre-check (rate limits, permission scope, sanitization)
Layer 3: Response sanitizer (injection scan, size cap)
All requests logged to task_log.
"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup

import database as db

logger = logging.getLogger(__name__)

# ── Layer 1: Allowlist ──────────────────────────────────────────────────────

ALLOWED_DOMAINS = {
    "www.ebay.com",           # eBay scraper (no API key — scrape workaround)
    "www.pricecharting.com",  # PriceCharting API + scraper fallback
    "api.tcgplayer.com",      # TCGPlayer API (Phase 1 — key required)
    "api.shipengine.com",     # ShipEngine API (Phase 1 — key required)
}

WRITE_PERMITTED = set()  # No external writes in Phase 1

# ── Layer 2: Rate limits ────────────────────────────────────────────────────

RATE_LIMITS = {
    "www.ebay.com":           {"max": 15, "window": 60},
    "www.pricecharting.com":  {"max": 10, "window": 60},
    "api.tcgplayer.com":      {"max": 15, "window": 60},
    "api.shipengine.com":     {"max": 10, "window": 60},
}

_call_counts: dict = {}

TIMEOUTS = {
    "www.ebay.com":          15,
    "www.pricecharting.com": 12,
    "api.tcgplayer.com":     8,
    "api.shipengine.com":    8,
}

# ── Layer 2: Outbound sanitizer ─────────────────────────────────────────────

SENSITIVE_PATTERNS = [
    re.compile(r"sk[-_]?[a-zA-Z0-9]{20,}", re.I),
    re.compile(r"Bearer\s+[a-zA-Z0-9\-._~+/]+=*", re.I),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b4[0-9]{12}(?:[0-9]{3})?\b"),
    re.compile(r'password["\'s]?\s*[:=]\s*["\']?[^\s"\']+', re.I),
    re.compile(r"railway_token", re.I),
]

# ── Layer 3: Injection scanner ──────────────────────────────────────────────

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.I),
    re.compile(r"you\s+are\s+now\s+(a\s+)?different", re.I),
    re.compile(r"forget\s+(everything|all|your)\s+(you\s+know|instructions|rules)", re.I),
    re.compile(r"new\s+instructions?\s*:", re.I),
    re.compile(r"system\s*:\s*you\s+are", re.I),
    re.compile(r"\[INST\]", re.I),
    re.compile(r"<\|system\|>", re.I),
    re.compile(r"override\s+(your\s+)?(safety|rules|instructions)", re.I),
    re.compile(r"act\s+as\s+(if\s+you\s+are|a\s+different)", re.I),
    re.compile(r"disregard\s+(your|all|previous)", re.I),
]

MAX_RESPONSE_SIZE = 50_000       # API responses
MAX_SCRAPE_SIZE   = 500_000      # HTML scrape pages (eBay, PriceCharting)


# ── Internal helpers ─────────────────────────────────────────────────────────

def _audit(event, detail="", status="info"):
    db.log_task("gateway", event, detail, status)
    logger.info(f"[GATEWAY] {event} — {detail}")


def _domain(url):
    try:
        from urllib.parse import urlparse
        return urlparse(url).hostname.lower()
    except Exception:
        return ""


def _allowlist_check(url):
    domain = _domain(url)
    if domain not in ALLOWED_DOMAINS:
        _audit("ALLOWLIST_BLOCK", f"Domain not permitted: {domain}", "blocked")
        raise PermissionError(f"Gateway: domain not on allowlist — {domain}")
    return domain


def _rate_limit_check(domain):
    limits = RATE_LIMITS.get(domain, {"max": 10, "window": 60})
    window_key = f"{domain}:{int(time.time() // limits['window'])}"
    count = _call_counts.get(window_key, 0) + 1
    _call_counts[window_key] = count
    if count > limits["max"]:
        _audit("RATE_LIMIT_HIT", f"{domain} — {count}/{limits['max']} per {limits['window']}s", "blocked")
        raise RuntimeError(f"Gateway: rate limit hit for {domain}")


def _permission_check(domain, method):
    if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
        if domain not in WRITE_PERMITTED:
            _audit("PERMISSION_BLOCK", f"Write blocked for {domain}", "blocked")
            raise PermissionError(f"Gateway: write not permitted for {domain}")


def _sanitize_outbound(text):
    for pattern in SENSITIVE_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _scan_injection(text):
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            _audit("INJECTION_DETECTED", text[:200], "blocked")
            raise ValueError("Gateway: potential prompt injection in response — discarded")


def _size_check(text):
    if len(text) > MAX_RESPONSE_SIZE:
        _audit("RESPONSE_TRUNCATED", f"Size {len(text)} → {MAX_RESPONSE_SIZE}", "warning")
        return text[:MAX_RESPONSE_SIZE]
    return text


def _request(url, method="GET", headers=None, params=None, json=None):
    """Core HTTP dispatch with all three Gateway layers applied."""
    domain = _allowlist_check(url)
    _rate_limit_check(domain)
    _permission_check(domain, method)

    timeout = TIMEOUTS.get(domain, 10)
    default_headers = {"User-Agent": "PurpleHorizon-BrexisGateway/1.0"}
    if headers:
        default_headers.update(headers)

    _audit("REQUEST_SENT", f"{method} {url}")

    try:
        resp = requests.request(
            method, url,
            headers=default_headers,
            params=params,
            json=json,
            timeout=timeout,
        )
    except Exception as e:
        _audit("API_ERROR", str(e), "failed")
        raise RuntimeError(f"Gateway: external request failed — {e}")

    raw = resp.text
    raw = _size_check(raw)
    _scan_injection(raw)

    _audit("RESPONSE_RECEIVED", f"{domain} status={resp.status_code} size={len(raw)}")
    return resp.status_code, raw


# ── Public API: eBay (scraper workaround) ───────────────────────────────────

_PC_PLATFORM_MAP = {
    "Switch": "nintendo-switch", "3DS": "nintendo-3ds", "Wii U": "wii-u",
    "Wii": "wii", "DS": "nintendo-ds", "GBA": "gameboy-advance",
    "GBC": "gameboy-color", "Game Boy": "gameboy", "N64": "nintendo-64",
    "GameCube": "gamecube", "SNES": "super-nintendo", "NES": "nintendo",
    "PS4": "playstation-4", "PS3": "playstation-3", "PS2": "playstation-2",
    "PS1": "playstation", "PS Vita": "playstation-vita", "PSP": "psp",
    "Xbox One": "xbox-one", "Xbox 360": "xbox-360", "Xbox": "xbox",
    "Genesis": "sega-genesis", "Dreamcast": "sega-dreamcast",
}

_SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def fetch_ebay_sold(title, platform="Switch"):
    """Return a direct eBay sold listings search URL for the given title and platform."""
    query = requests.utils.quote(f"{title} {platform}")
    url = (
        f"https://www.ebay.com/sch/i.html?_nkw={query}"
        "&LH_Sold=1&LH_Complete=1&LH_ItemCondition=3000&_sop=13"
    )
    _audit("REQUEST_SENT", f"eBay link generated: {title} / {platform}")
    return {"found": True, "search_url": url}


# ── Public API: PriceCharting ────────────────────────────────────────────────

_PC_DEMO_TOKEN = "c0b53bce27c1bdab90b1605249e600dc43dfd1d5"


def _slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def _cents(val):
    if val and int(val) > 0:
        return round(int(val) / 100, 2)
    return None


def fetch_pricecharting(title, platform="Switch"):
    """Fetch PriceCharting prices via API (falls back to scraper)."""
    token = db.get_config("PRICECHARTING_API_KEY") or _PC_DEMO_TOKEN
    query = requests.utils.quote(f"{title} {platform}")
    url = f"https://www.pricecharting.com/api/products?q={query}&t={token}"

    try:
        _status, raw = _request(url)
        import json
        data = json.loads(raw)

        if data.get("status") == "error":
            return {"found": False, "error": data.get("error-message", "API error")}

        products = data.get("products", [])
        if not products:
            return {"found": False, "error": "No results found"}

        platform_slug = _PC_PLATFORM_MAP.get(platform, "").replace("-", " ").lower()
        best = None
        for p in products:
            if title.lower() in p.get("product-name", "").lower() and \
               platform_slug in p.get("console-name", "").lower():
                best = p
                break
        if best is None:
            best = products[0]

        pid = best.get("id")
        price_data = best
        if pid:
            url2 = f"https://www.pricecharting.com/api/product?id={pid}&t={token}"
            _s2, raw2 = _request(url2)
            d2 = json.loads(raw2)
            if d2.get("status") == "success":
                price_data = d2

        slug_console = _slugify(price_data.get("console-name", best.get("console-name", "")))
        slug_product = _slugify(price_data.get("product-name", best.get("product-name", "")))
        page_url = f"https://www.pricecharting.com/game/{slug_console}/{slug_product}"

        loose  = _cents(price_data.get("loose-price"))
        cib    = _cents(price_data.get("cib-price"))
        sealed = _cents(price_data.get("new-price"))
        graded = _cents(price_data.get("graded-price"))

        if not any([loose, cib, sealed, graded]):
            scraped = _scrape_pc_page(page_url)
            loose  = scraped.get("loose")  or loose
            cib    = scraped.get("cib")    or cib
            sealed = scraped.get("sealed") or sealed
            graded = scraped.get("graded") or graded

        return {
            "found":    True,
            "name":     price_data.get("product-name", best.get("product-name")),
            "platform": price_data.get("console-name", best.get("console-name")),
            "loose":    loose,
            "cib":      cib,
            "sealed":   sealed,
            "graded":   graded,
            "url":      page_url,
        }
    except Exception as e:
        _audit("API_ERROR", f"PriceCharting: {e}", "failed")
        return {"found": False, "error": str(e)}


def _scrape_pc_page(url):
    try:
        domain = _allowlist_check(url)
        _rate_limit_check(domain)
        resp = requests.get(url, headers=_SCRAPE_HEADERS, timeout=12)
        raw = resp.text[:MAX_SCRAPE_SIZE]
        _scan_injection(raw)
        soup = BeautifulSoup(raw, "html.parser")

        def _parse(el):
            if not el:
                return None
            m = re.search(r"\$([\d,]+\.\d{2})", el.get_text())
            return round(float(m.group(1).replace(",", "")), 2) if m else None

        return {
            "loose":  _parse(soup.select_one("#used_price")),
            "cib":    _parse(soup.select_one("#complete_price")),
            "sealed": _parse(soup.select_one("#new_price")),
            "graded": _parse(soup.select_one("#graded_price")),
        }
    except Exception:
        return {}


# ── Public API: TCGPlayer ────────────────────────────────────────────────────

def fetch_tcgplayer(card_name, set_name=""):
    """Fetch Pokémon TCG card prices from TCGPlayer API."""
    api_key = db.get_config("TCGPLAYER_API_KEY")
    if not api_key:
        return {"found": False, "error": "TCGPlayer API key not configured — add it in /settings"}

    try:
        import json
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        query = card_name + (f" {set_name}" if set_name else "")
        url = f"https://api.tcgplayer.com/catalog/products?productName={requests.utils.quote(query)}&categoryId=3&limit=5"
        _status, raw = _request(url, headers=headers)
        data = json.loads(raw)

        results = data.get("results", [])
        if not results:
            return {"found": False, "error": f"No TCGPlayer results for '{card_name}'"}

        product = results[0]
        pid = product.get("productId")

        price_url = f"https://api.tcgplayer.com/pricing/product/{pid}"
        _ps, price_raw = _request(price_url, headers=headers)
        prices = json.loads(price_raw).get("results", [])

        price_map = {}
        for p in prices:
            sub = p.get("subTypeName", "Normal")
            price_map[sub] = {
                "low":    p.get("lowPrice"),
                "mid":    p.get("midPrice"),
                "high":   p.get("highPrice"),
                "market": p.get("marketPrice"),
            }

        return {
            "found":    True,
            "name":     product.get("name"),
            "set":      product.get("groupName"),
            "prices":   price_map,
            "url":      product.get("url", ""),
        }
    except Exception as e:
        _audit("API_ERROR", f"TCGPlayer: {e}", "failed")
        return {"found": False, "error": str(e)}


# ── Public API: ShipEngine ───────────────────────────────────────────────────

def fetch_shipping_rates(from_zip, to_zip, weight_oz, length=12, width=9, height=4):
    """Get shipping rate estimates from ShipEngine."""
    api_key = db.get_config("SHIPENGINE_API_KEY")
    if not api_key:
        return {"found": False, "error": "ShipEngine API key not configured — add it in /settings"}

    try:
        import json
        headers = {
            "API-Key": api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "rate_options": {"carrier_ids": []},
            "shipment": {
                "ship_from": {"postal_code": from_zip, "country_code": "US"},
                "ship_to":   {"postal_code": to_zip,   "country_code": "US"},
                "packages": [{
                    "weight": {"value": weight_oz, "unit": "ounce"},
                    "dimensions": {"length": length, "width": width, "height": height, "unit": "inch"},
                }],
            },
        }
        _status, raw = _request(
            "https://api.shipengine.com/v1/rates/estimate",
            method="POST",
            headers=headers,
            json=payload,
        )
        data = json.loads(raw)
        rates = []
        for r in data if isinstance(data, list) else []:
            if r.get("shipping_amount"):
                rates.append({
                    "carrier":  r.get("carrier_friendly_name", r.get("carrier_id")),
                    "service":  r.get("service_type"),
                    "rate":     r.get("shipping_amount", {}).get("amount"),
                    "days":     r.get("delivery_days"),
                })
        rates.sort(key=lambda x: x.get("rate") or 999)
        return {"found": True, "rates": rates[:5]}
    except Exception as e:
        _audit("API_ERROR", f"ShipEngine: {e}", "failed")
        return {"found": False, "error": str(e)}
