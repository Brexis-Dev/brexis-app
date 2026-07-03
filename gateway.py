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
    "www.ebay.com",              # eBay scraper (no API key — scrape workaround)
    "www.pricecharting.com",     # PriceCharting API + scraper fallback
    "api.tcgplayer.com",         # TCGPlayer API (Phase 1 — key required)
    "ssapi.shipstation.com",     # ShipStation API (Phase 1 — key required)
    "api.search.brave.com",      # Brave Search API
    "openapi.etsy.com",          # Etsy API v3 (read-only)
    "api.pinterest.com",         # Pinterest API v5 (read-only)
    "web-production-815bd.up.railway.app",  # Purple Horizon /pipeline/* — Nate-approved write, TASK-AUTO-PIPE
}

WRITE_PERMITTED = {
    "web-production-815bd.up.railway.app",  # Purple Horizon /pipeline/submit only
}

# ── Layer 2: Rate limits ────────────────────────────────────────────────────

RATE_LIMITS = {
    "www.ebay.com":           {"max": 15, "window": 60},
    "www.pricecharting.com":  {"max": 10, "window": 60},
    "api.tcgplayer.com":      {"max": 15, "window": 60},
    "api.shipengine.com":     {"max": 10, "window": 60},
    "api.search.brave.com":   {"max": 20, "window": 60},
    "openapi.etsy.com":       {"max": 10, "window": 60},
    "api.pinterest.com":      {"max": 10, "window": 60},
}

_call_counts: dict = {}

TIMEOUTS = {
    "www.ebay.com":          15,
    "www.pricecharting.com": 12,
    "api.tcgplayer.com":     8,
    "ssapi.shipstation.com": 8,
    "api.search.brave.com":  8,
    "openapi.etsy.com":      10,
    "api.pinterest.com":     10,
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

# Precise console name strings for API result filtering
_PC_CONSOLE_MATCH = {
    "NES":      "nes",
    "SNES":     "super nintendo",
    "N64":      "nintendo 64",
    "GameCube": "gamecube",
    "Wii":      "nintendo wii",
    "Wii U":    "wii u",
    "Game Boy": "game boy",
    "GBC":      "game boy color",
    "GBA":      "game boy advance",
    "DS":       "nintendo ds",
    "3DS":      "nintendo 3ds",
    "Switch":   "nintendo switch",
    "PS1":      "playstation",
    "PS2":      "playstation 2",
    "PS3":      "playstation 3",
    "PS4":      "playstation 4",
    "PSP":      "psp",
    "PS Vita":  "ps vita",
    "Xbox":     "xbox",
    "Xbox 360": "xbox 360",
    "Xbox One": "xbox one",
    "Genesis":  "sega genesis",
    "Dreamcast":"sega dreamcast",
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
    """Fetch PriceCharting prices via API search with precise platform filtering."""
    platform_slug = _PC_PLATFORM_MAP.get(platform, _slugify(platform))
    console_match = _PC_CONSOLE_MATCH.get(platform, platform.lower())

    try:
        token = db.get_config("PRICECHARTING_API_KEY") or _PC_DEMO_TOKEN
        import json

        # Strip platform prefix from title if user included it (e.g. "nes zelda" → "zelda")
        clean_title = re.sub(rf"^{re.escape(platform.lower())}\s+", "", title.lower()).strip()
        query = requests.utils.quote(clean_title)
        url = f"https://www.pricecharting.com/api/products?q={query}&t={token}"
        _audit("REQUEST_SENT", f"PriceCharting search: '{clean_title}' on {platform}")

        _status, raw = _request(url)
        data = json.loads(raw)
        products = data.get("products", [])

        if not products:
            return {"found": False, "error": f"No results found for '{title}' on PriceCharting"}

        # Filter strictly to the requested platform using precise console name
        matches = [
            p for p in products
            if console_match in p.get("console-name", "").lower()
        ]

        if not matches:
            found_platforms = list({p.get("console-name", "") for p in products[:5]})
            return {
                "found": False,
                "error": f"No {platform} results for '{title}'. Found on: {', '.join(found_platforms)}"
            }

        # Pick best title match within platform results
        title_lower = clean_title.lower()
        matches.sort(key=lambda p: sum(w in p.get("product-name","").lower() for w in title_lower.split()), reverse=True)
        best = matches[0]

        # Fetch full price data
        pid = best.get("id")
        price_data = best
        if pid:
            _s2, raw2 = _request(f"https://www.pricecharting.com/api/product?id={pid}&t={token}")
            d2 = json.loads(raw2)
            if d2.get("status") == "success":
                price_data = d2

        loose  = _cents(price_data.get("loose-price"))
        cib    = _cents(price_data.get("cib-price"))
        sealed = _cents(price_data.get("new-price"))
        graded = _cents(price_data.get("graded-price"))

        slug_c = _slugify(price_data.get("console-name", platform))
        slug_p = _slugify(price_data.get("product-name", title))
        page_url = f"https://www.pricecharting.com/game/{slug_c}/{slug_p}"

        # Scrape page if API didn't return prices (demo token limitation)
        if not any([loose, cib, sealed, graded]):
            scraped = _scrape_pc_page(page_url)
            loose  = scraped.get("loose")  or loose
            cib    = scraped.get("cib")    or cib
            sealed = scraped.get("sealed") or sealed
            graded = scraped.get("graded") or graded

        return {
            "found":    True,
            "name":     price_data.get("product-name", title),
            "platform": price_data.get("console-name", platform),
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
    """Get shipping rate estimates from ShipStation."""
    api_key = db.get_config("SHIPENGINE_API_KEY")
    if not api_key:
        return {"found": False, "error": "ShipStation API key not configured — add it in /settings"}

    try:
        import json, base64
        encoded = base64.b64encode(f"{api_key}:".encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
        }
        payload = {
            "carrierCode": None,
            "fromPostalCode": from_zip,
            "toState": "MD",
            "toCountry": "US",
            "toPostalCode": to_zip,
            "toCity": "",
            "weight": {"value": weight_oz, "units": "ounces"},
            "dimensions": {"length": length, "width": width, "height": height, "units": "inches"},
            "confirmation": "none",
            "residential": True,
        }
        _status, raw = _request(
            "https://ssapi.shipstation.com/shipments/getrates",
            method="POST",
            headers=headers,
            json=payload,
        )
        data = json.loads(raw)
        rates = []
        for r in (data if isinstance(data, list) else []):
            rates.append({
                "carrier":  r.get("carrierCode", ""),
                "service":  r.get("serviceCode", ""),
                "rate":     r.get("shipmentCost", 0) + r.get("otherCost", 0),
                "days":     r.get("transitDays"),
            })
        rates.sort(key=lambda x: x.get("rate") or 999)
        return {"found": True, "rates": rates[:5]}
    except Exception as e:
        _audit("API_ERROR", f"ShipStation: {e}", "failed")
        return {"found": False, "error": str(e)}


# ── Public API: Brave Search ─────────────────────────────────────────────────

def brave_search(query, count=5):
    """Search the web via Brave Search API. Returns list of result dicts."""
    api_key = db.get_config("BRAVE_SEARCH_API_KEY")
    if not api_key:
        return {"found": False, "error": "Brave Search API key not configured — add it in /settings"}

    try:
        import json
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }
        params = {"q": query, "count": min(int(count), 10), "safesearch": "moderate"}
        _status, raw = _request(url, headers=headers, params=params)
        data = json.loads(raw)

        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title":       item.get("title", ""),
                "url":         item.get("url", ""),
                "description": item.get("description", ""),
            })

        if not results:
            return {"found": False, "error": f"No web results for '{query}'"}

        _audit("BRAVE_SEARCH", f"query='{query}' count={len(results)}")
        return {"found": True, "query": query, "results": results}
    except Exception as e:
        _audit("API_ERROR", f"BraveSearch: {e}", "failed")
        return {"found": False, "error": str(e)}


# ── Public API: Etsy v3 ──────────────────────────────────────────────────────

def etsy_search(query, limit=10):
    """Search active Etsy listings by keyword. Returns title, price, shop, url."""
    api_key = db.get_config("ETSY_API_KEY")
    if not api_key:
        return {"found": False, "error": "Etsy API key not configured — add it in /settings"}
    try:
        import json
        url = "https://openapi.etsy.com/v3/application/listings/active"
        headers = {"x-api-key": api_key, "Accept": "application/json"}
        params = {"keywords": query, "limit": min(int(limit), 25), "includes": ["Shop"]}
        _status, raw = _request(url, headers=headers, params=params)
        data = json.loads(raw)
        results = []
        for item in data.get("results", []):
            price = item.get("price", {})
            amount = price.get("amount", 0)
            divisor = price.get("divisor", 100)
            results.append({
                "title":     item.get("title", ""),
                "price":     round(amount / divisor, 2) if divisor else 0,
                "currency":  price.get("currency_code", "USD"),
                "shop":      item.get("shop", {}).get("shop_name", "") if item.get("shop") else "",
                "url":       item.get("url", ""),
                "status":    item.get("state", ""),
                "listing_id": item.get("listing_id"),
            })
        if not results:
            return {"found": False, "error": f"No Etsy listings found for '{query}'"}
        _audit("ETSY_SEARCH", f"query='{query}' count={len(results)}")
        return {
            "found":   True,
            "query":   query,
            "count":   data.get("count", len(results)),
            "results": results,
        }
    except Exception as e:
        _audit("API_ERROR", f"Etsy search: {e}", "failed")
        return {"found": False, "error": str(e)}


def etsy_shop(shop_name, limit=10):
    """Fetch active listings for a specific Etsy shop by shop name."""
    api_key = db.get_config("ETSY_API_KEY")
    if not api_key:
        return {"found": False, "error": "Etsy API key not configured — add it in /settings"}
    try:
        import json
        # First resolve shop_id from shop_name
        shop_url = f"https://openapi.etsy.com/v3/application/shops"
        headers = {"x-api-key": api_key, "Accept": "application/json"}
        _s, raw = _request(shop_url, headers=headers, params={"shop_name": shop_name})
        shop_data = json.loads(raw)
        shops = shop_data.get("results", [])
        if not shops:
            return {"found": False, "error": f"No Etsy shop found named '{shop_name}'"}
        shop = shops[0]
        shop_id = shop.get("shop_id")
        listings_url = f"https://openapi.etsy.com/v3/application/shops/{shop_id}/listings/active"
        _s2, raw2 = _request(listings_url, headers=headers, params={"limit": min(int(limit), 25)})
        data = json.loads(raw2)
        results = []
        for item in data.get("results", []):
            price = item.get("price", {})
            amount = price.get("amount", 0)
            divisor = price.get("divisor", 100)
            results.append({
                "title":      item.get("title", ""),
                "price":      round(amount / divisor, 2) if divisor else 0,
                "currency":   price.get("currency_code", "USD"),
                "url":        item.get("url", ""),
                "status":     item.get("state", ""),
                "listing_id": item.get("listing_id"),
            })
        _audit("ETSY_SHOP", f"shop='{shop_name}' listings={len(results)}")
        return {
            "found":     True,
            "shop_name": shop.get("shop_name", shop_name),
            "shop_id":   shop_id,
            "total":     data.get("count", len(results)),
            "listings":  results,
        }
    except Exception as e:
        _audit("API_ERROR", f"Etsy shop: {e}", "failed")
        return {"found": False, "error": str(e)}


# ── Public API: Pinterest v5 ─────────────────────────────────────────────────

def pinterest_search(query, limit=10):
    """Search Pinterest pins by keyword. Returns title, description, image url, link."""
    access_token = db.get_config("PINTEREST_ACCESS_TOKEN")
    if not access_token:
        return {"found": False, "error": "Pinterest access token not configured — add it in /settings"}
    try:
        import json
        url = "https://api.pinterest.com/v5/search/pins"
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        params = {"query": query, "page_size": min(int(limit), 25)}
        _status, raw = _request(url, headers=headers, params=params)
        data = json.loads(raw)
        results = []
        for item in data.get("items", []):
            media = item.get("media", {})
            images = media.get("images", {})
            image_url = (
                images.get("600x", {}).get("url") or
                images.get("400x300", {}).get("url") or ""
            )
            results.append({
                "title":       item.get("title", ""),
                "description": item.get("description", ""),
                "link":        item.get("link", ""),
                "image_url":   image_url,
                "board":       item.get("board_id", ""),
                "pin_id":      item.get("id", ""),
            })
        if not results:
            return {"found": False, "error": f"No Pinterest pins found for '{query}'"}
        bookmark = data.get("bookmark")
        _audit("PINTEREST_SEARCH", f"query='{query}' count={len(results)}")
        return {
            "found":    True,
            "query":    query,
            "results":  results,
            "bookmark": bookmark,
        }
    except Exception as e:
        _audit("API_ERROR", f"Pinterest search: {e}", "failed")
        return {"found": False, "error": str(e)}


# ── Public API: Purple Horizon pipeline ──────────────────────────────────────

PIPELINE_SUBMIT_URL = "https://web-production-815bd.up.railway.app/pipeline/submit"


def submit_pipeline_task(title, brief, size="small"):
    """Submit a task brief to the Purple Horizon /pipeline/submit endpoint."""
    api_key = db.get_config("brexis_api_key")
    if not api_key:
        return {"found": False, "error": "brexis_api_key not configured — add it in /settings"}

    status = None
    raw = None
    try:
        import json
        headers = {"Authorization": f"Bearer {api_key}"}
        payload = {"title": title, "brief": brief, "size": size}
        status, raw = _request(PIPELINE_SUBMIT_URL, method="POST", headers=headers, json=payload)
        # Log the raw body every time, before attempting to parse it — if parsing fails below,
        # this is still on record instead of being replaced by a generic parse-error message.
        _audit("PIPELINE_RAW_RESPONSE", f"status={status} body={raw[:1000]!r}")
        data = json.loads(raw)

        if status >= 400:
            _audit("API_ERROR", f"Pipeline submit failed: {status} {data}", "failed")
            return {"found": False, "error": data.get("error", f"HTTP {status}")}

        _audit("PIPELINE_SUBMIT", f"task_id={data.get('task_id')} size={size} approved={data.get('approved')}")
        return {
            "found":        True,
            "task_id":      data.get("task_id"),
            "status":       data.get("status"),
            "approved":     data.get("approved"),
        }
    except Exception as e:
        _audit("API_ERROR", f"Pipeline submit: {e} — status={status} raw={(raw or '')[:1000]!r}", "failed")
        return {"found": False, "error": str(e)}


PIPELINE_STATUS_URL = "https://web-production-815bd.up.railway.app/pipeline/status/{task_id}"


def check_pipeline_task(task_id):
    """Check a task's status/outcome/completion report on the Purple Horizon pipeline."""
    api_key = db.get_config("brexis_api_key")
    if not api_key:
        return {"found": False, "error": "brexis_api_key not configured — add it in /settings"}

    status = None
    raw = None
    try:
        import json
        headers = {"Authorization": f"Bearer {api_key}"}
        url = PIPELINE_STATUS_URL.format(task_id=task_id)
        status, raw = _request(url, method="GET", headers=headers)
        _audit("PIPELINE_RAW_RESPONSE", f"status={status} body={raw[:1000]!r}")
        data = json.loads(raw)

        if status >= 400:
            _audit("API_ERROR", f"Pipeline status check failed: {status} {data}", "failed")
            return {"found": False, "error": data.get("error", f"HTTP {status}")}

        _audit("PIPELINE_STATUS_CHECK", f"task_id={task_id} status={data.get('status')} outcome={data.get('outcome')}")
        return {
            "found":           True,
            "task_id":         data.get("id"),
            "title":           data.get("title"),
            "status":          data.get("status"),
            "approved":        data.get("approved"),
            "outcome":         data.get("outcome"),
            "claude_response": data.get("claude_response"),
            "error_reason":    data.get("error_reason"),
            "budget_warning":  data.get("budget_warning"),
        }
    except Exception as e:
        _audit("API_ERROR", f"Pipeline status check: {e} — status={status} raw={(raw or '')[:1000]!r}", "failed")
        return {"found": False, "error": str(e)}


# ── Public API: Hunters Den ──────────────────────────────────────────────────

PURPLE_HORIZON_BASE = "https://web-production-815bd.up.railway.app"


def _ph_call(path, method="GET", payload=None, params=None):
    """Shared caller for Purple Horizon endpoints, authenticated with brexis_api_key."""
    api_key = db.get_config("brexis_api_key")
    if not api_key:
        return {"found": False, "error": "brexis_api_key not configured — add it in /settings"}

    status = None
    raw = None
    try:
        import json
        headers = {"Authorization": f"Bearer {api_key}"}
        url = PURPLE_HORIZON_BASE + path
        status, raw = _request(url, method=method, headers=headers, params=params, json=payload)
        _audit("PIPELINE_RAW_RESPONSE", f"{method} {path} status={status} body={raw[:1000]!r}")
        data = json.loads(raw)
        if status >= 400:
            _audit("API_ERROR", f"Purple Horizon call failed: {method} {path} {status} {data}", "failed")
            return {"found": False, "error": data.get("error", f"HTTP {status}")}
        return {"found": True, "data": data}
    except Exception as e:
        _audit("API_ERROR", f"Purple Horizon call: {method} {path}: {e} — status={status} raw={(raw or '')[:1000]!r}", "failed")
        return {"found": False, "error": str(e)}


def log_hunter_grail(hunter, item_name, tier, buy_price, sell_price, platform=None):
    payload = {"hunter": hunter, "item_name": item_name, "tier": tier, "buy_price": buy_price, "sell_price": sell_price, "platform": platform}
    result = _ph_call("/hunter-grails", method="POST", payload=payload)
    if not result["found"]:
        return result
    _audit("HUNTER_GRAIL_LOGGED", f"hunter={hunter} item={item_name} tier={tier}")
    return {"found": True, **result["data"]}


def mark_grail_paid(grail_id):
    result = _ph_call(f"/hunter-grails/{grail_id}/mark-paid", method="POST")
    if not result["found"]:
        return result
    _audit("HUNTER_GRAIL_MARKED_PAID", f"grail_id={grail_id}")
    return {"found": True, **result["data"]}


def list_hunter_grails(hunter=None, status=None):
    params = {}
    if hunter:
        params["hunter"] = hunter
    if status:
        params["status"] = status
    result = _ph_call("/hunter-grails", method="GET", params=params)
    if not result["found"]:
        return result
    return {"found": True, "grails": result["data"]}


def post_hunter_quest(quest_type, bonus_type, bonus_value, start_date=None, end_date=None):
    payload = {"type": quest_type, "bonus_type": bonus_type, "bonus_value": bonus_value, "start_date": start_date, "end_date": end_date}
    result = _ph_call("/hunter-quests", method="POST", payload=payload)
    if not result["found"]:
        return result
    _audit("HUNTER_QUEST_POSTED", f"type={quest_type} bonus_type={bonus_type} bonus_value={bonus_value}")
    return {"found": True, **result["data"]}


def close_hunter_quest(quest_id, winner, bonus_payout):
    payload = {"winner": winner, "bonus_payout": bonus_payout}
    result = _ph_call(f"/hunter-quests/{quest_id}/close", method="POST", payload=payload)
    if not result["found"]:
        return result
    _audit("HUNTER_QUEST_CLOSED", f"quest_id={quest_id} winner={winner} bonus_payout={bonus_payout}")
    return {"found": True, **result["data"]}


def get_hunter_ledger():
    result = _ph_call("/hunter-ledger", method="GET")
    if not result["found"]:
        return result
    return {"found": True, "ledger": result["data"]}


def get_hunter_weekly_summary():
    result = _ph_call("/hunter-grails/weekly-summary", method="GET")
    if not result["found"]:
        return result
    return {"found": True, **result["data"]}
