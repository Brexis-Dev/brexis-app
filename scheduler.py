import json
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import database as db

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


def get_anthropic_client():
    from anthropic import Anthropic
    key = os.environ.get("ANTHROPIC_API_KEY") or db.get_config("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("Anthropic API key not configured.")
    return Anthropic(api_key=key)


def _get_system_prompt():
    from app import SYSTEM_PROMPT
    return SYSTEM_PROMPT


def _call_brexis(prompt):
    client = get_anthropic_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=_get_system_prompt(),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _deliver(subject, body, discord_channel=None, send_email=True):
    import emailer
    import discord_bot

    if send_email:
        emailer.send_email(subject, body)

    if discord_channel and discord_bot.is_ready():
        discord_bot.post_message(discord_channel, f"**{subject}**\n\n{body}")


# ── Jobs ──

def job_morning_briefing():
    db.log_task("scheduler", "morning_briefing", "Starting morning briefing", "running")
    try:
        lrg = db.get_lrg_games(1, status=None)
        summary = db.get_inventory_summary(1)

        # Find upcoming deadlines
        from datetime import date, timedelta
        today = date.today()
        soon = []
        for g in lrg:
            if g.get("deadline") and g.get("status") in ("watching", "pre-ordered"):
                try:
                    dl = date.fromisoformat(g["deadline"])
                    days_left = (dl - today).days
                    if 0 <= days_left <= 7:
                        soon.append(f"- {g['title']} ({g['publisher']}) — {days_left} day(s) left")
                except Exception:
                    pass

        deadline_text = "\n".join(soon) if soon else "No urgent pre-order deadlines."
        inv_text = "\n".join(f"- {k.replace('_',' ').title()}: {v}" for k, v in summary.items())

        prompt = (
            f"Generate a concise morning briefing for Saturday Morning PJs. Today is {today}.\n\n"
            f"LRG Pre-order deadlines within 7 days:\n{deadline_text}\n\n"
            f"Current inventory counts:\n{inv_text}\n\n"
            f"Format: short, direct, action-oriented. Lead with the most urgent item. "
            f"End with top 3 action items for today."
        )

        briefing = _call_brexis(prompt)
        _deliver(
            subject=f"Brexis Morning Briefing — {today}",
            body=briefing,
            discord_channel="daily-briefing",
        )
        db.log_task("scheduler", "morning_briefing", "Morning briefing delivered", "success")

    except Exception as e:
        logger.error(f"Morning briefing failed: {e}")
        db.log_task("scheduler", "morning_briefing", f"Failed: {e}", "failed")


def job_weekly_market_report():
    from datetime import date
    today = date.today()
    db.log_task("scheduler", "weekly_market_report", "Starting weekly market report", "running")
    try:
        lrg = db.get_lrg_games(1)
        owned = [g for g in lrg if g.get("status") == "owned"]
        watching = [g for g in lrg if g.get("status") == "watching"]
        sold = [g for g in lrg if g.get("status") == "sold"]

        owned_text = "\n".join(f"- {g['title']} | Buy: ${g.get('buy_price',0):.2f} | Est: ${g.get('est_resale',0):.2f}" for g in owned) or "None"
        watching_text = "\n".join(f"- {g['title']} ({g.get('publisher','')})" for g in watching) or "None"

        total_invested = sum(g.get("buy_price", 0) or 0 for g in owned)
        total_est = sum(g.get("est_resale", 0) or 0 for g in owned)
        total_profit_sold = sum((g.get("sold_for", 0) or 0) - (g.get("buy_price", 0) or 0) for g in sold)

        prompt = (
            f"Generate a weekly Switch resale market report for Saturday Morning PJs. Week of {today}.\n\n"
            f"Currently owned inventory:\n{owned_text}\n\n"
            f"Titles being watched:\n{watching_text}\n\n"
            f"Portfolio stats:\n"
            f"- Total invested in owned: ${total_invested:.2f}\n"
            f"- Total estimated resale value: ${total_est:.2f}\n"
            f"- Total profit from sold items: ${total_profit_sold:.2f}\n\n"
            f"Provide: market outlook, reinvestment recommendations, which owned titles to prioritize listing this week."
        )

        report = _call_brexis(prompt)
        _deliver(
            subject=f"Brexis Weekly Market Report — {today}",
            body=report,
            discord_channel="market-reports",
        )
        db.log_task("scheduler", "weekly_market_report", "Weekly market report delivered", "success")

    except Exception as e:
        logger.error(f"Weekly market report failed: {e}")
        db.log_task("scheduler", "weekly_market_report", f"Failed: {e}", "failed")


def job_deadline_alert():
    from datetime import date
    today = date.today()
    try:
        lrg = db.get_lrg_games(1)
        alerts = []
        for g in lrg:
            if g.get("deadline") and g.get("status") in ("watching", "pre-ordered"):
                try:
                    dl = date.fromisoformat(g["deadline"])
                    days_left = (dl - today).days
                    if days_left in (7, 3, 1):
                        alerts.append((g, days_left))
                except Exception:
                    pass

        for game, days in alerts:
            msg = (
                f"⚠️ **Pre-order Alert** — {game['title']} ({game.get('publisher','')})\n"
                f"Window closes in **{days} day(s)** on {game['deadline']}.\n"
                f"Status: {game.get('status','')} | Buy price: ${game.get('buy_price',0):.2f} | Est resale: ${game.get('est_resale',0):.2f}"
            )
            _deliver(
                subject=f"Pre-order Alert: {game['title']} — {days} day(s) left",
                body=msg,
                discord_channel="brexis-alerts",
            )
            db.log_task("scheduler", "deadline_alert", f"{game['title']} — {days}d left", "success")

    except Exception as e:
        logger.error(f"Deadline alert failed: {e}")
        db.log_task("scheduler", "deadline_alert", f"Failed: {e}", "failed")


def job_low_inventory_alert():
    try:
        lrg = db.get_lrg_games(1, status="owned")
        count = len(lrg)
        if count < 3:
            msg = (
                f"📦 **Low Inventory Alert**\n"
                f"Switch resale owned inventory is down to **{count} item(s)**.\n"
                f"Consider sourcing new titles to maintain pipeline."
            )
            _deliver(
                subject=f"Low Inventory Alert — {count} items owned",
                body=msg,
                discord_channel="brexis-alerts",
            )
            db.log_task("scheduler", "low_inventory_alert", f"Owned count: {count}", "success")
    except Exception as e:
        logger.error(f"Low inventory alert failed: {e}")
        db.log_task("scheduler", "low_inventory_alert", f"Failed: {e}", "failed")


# ── PO Price Monitor ──────────────────────────────────────────────────────────

def _extract_price_from_search(results, item_name):
    """Parse the lowest USD price found across search result titles/descriptions."""
    import re
    prices = []
    pattern = re.compile(r'\$\s*(\d+(?:\.\d{1,2})?)')
    for r in results:
        for field in (r.get("title", ""), r.get("description", "")):
            for m in pattern.finditer(field):
                val = float(m.group(1))
                if 0.01 < val < 10000:
                    prices.append(val)
    if not prices:
        return None
    # Return the median-ish value — ignore outliers by taking the value
    # closest to the median of the lower half (avoids $0.01 junk listings
    # and $9999 bundle prices skewing the result)
    prices.sort()
    lower_half = prices[: max(1, len(prices) // 2 + 1)]
    return lower_half[-1]


def job_po_price_monitor():
    """Check market prices for all to_be_purchased PO items daily at 9 AM."""
    import gateway
    import emailer
    import discord_bot
    import json
    from datetime import datetime, timezone

    db.log_task("scheduler", "po_price_monitor", "Starting PO price check", "running")
    alerts_fired = 0
    pos_checked = 0

    try:
        orders = db.list_purchase_orders(status="to_be_purchased")
        if not orders:
            db.log_task("scheduler", "po_price_monitor", "No to_be_purchased POs", "success")
            return

        # Resolve Nate's email via contacts
        contacts = db.get_contacts(name="Nate")
        nate_email = contacts[0]["email"] if contacts else "nate@saturdaymorningpjs.com"

        for po in orders:
            items = po.get("items") or []
            if not items:
                continue

            items_changed = False
            now_iso = datetime.now(timezone.utc).isoformat()

            for item in items:
                item_name = item.get("name", "")
                unit_price = float(item.get("unit_price", 0) or 0)
                if not item_name or unit_price <= 0:
                    continue

                # Web search for current price
                search_q = f"{item_name} price buy"
                search_result = gateway.brave_search(search_q, count=8)
                if not search_result.get("found"):
                    item["last_checked"] = now_iso
                    items_changed = True
                    continue

                market_price = _extract_price_from_search(search_result["results"], item_name)
                item["last_checked"] = now_iso
                items_changed = True

                if market_price is None:
                    continue

                item["last_price"] = round(market_price, 2)

                drop_pct = (unit_price - market_price) / unit_price
                was_triggered = bool(item.get("alert_triggered", False))

                if drop_pct >= 0.10:
                    # Price dropped 10%+ — alert if not already triggered
                    if not was_triggered:
                        item["alert_triggered"] = True
                        save_amount = round(unit_price - market_price, 2)
                        pct_label = f"{drop_pct * 100:.0f}%"
                        alert_msg = (
                            f"Price Drop Alert — {item_name}\n"
                            f"{po['po_number']} | Was: ${unit_price:.2f} | Now: ${market_price:.2f} "
                            f"| Save: ${save_amount:.2f} ({pct_label})\n"
                            f"Vendor: {po.get('vendor') or 'unknown'} | Check it now."
                        )
                        subject = f"Price Drop: {item_name} — Save ${save_amount:.2f} ({pct_label})"
                        emailer.send_email(subject, alert_msg, to_emails=[nate_email])
                        if discord_bot.is_ready():
                            discord_bot.post_message("brexis-alerts", f"**{alert_msg}**")
                        db.log_task("scheduler", "po_price_monitor",
                                    f"Alert fired: {po['po_number']} {item_name} ${unit_price:.2f}->${market_price:.2f}",
                                    "success")
                        alerts_fired += 1
                else:
                    # Price recovered — reset flag
                    if was_triggered:
                        item["alert_triggered"] = False

            if items_changed:
                db.update_purchase_order(po["id"], {"items": items})

            pos_checked += 1

        db.log_task("scheduler", "po_price_monitor",
                    f"Checked {pos_checked} POs, {alerts_fired} alert(s) fired", "success")

    except Exception as e:
        logger.error(f"PO price monitor failed: {e}")
        db.log_task("scheduler", "po_price_monitor", f"Failed: {e}", "failed")


def job_slickdeals_monitor():
    """Check Slickdeals for new Nintendo-keyword deals -- Mon/Thu/Sat at 9 AM.

    Uses Brave Search (site:slickdeals.net) rather than fetching Slickdeals directly --
    no new gateway.py allowlist entry needed, and avoids Slickdeals' JS-rendered pages
    breaking a direct-fetch/scrape approach. Brave Search results don't have a separate
    structured price field; the title/description text is included as-is (Slickdeals
    listings normally put price in the title), rather than regex-guessing a price out
    of free text.
    """
    import gateway
    import emailer
    import discord_bot

    db.log_task("scheduler", "slickdeals_monitor", "Starting Slickdeals Nintendo check", "running")

    try:
        result = gateway.brave_search("Nintendo site:slickdeals.net", count=10)
        if not result.get("found"):
            db.log_task("scheduler", "slickdeals_monitor", f"No results: {result.get('error')}", "success")
            return

        new_deals = []
        for item in result.get("results", []):
            url = item.get("url", "")
            if not url or db.is_deal_seen(url):
                continue
            new_deals.append(item)
            db.mark_deal_seen(url, item.get("title", ""))

        if not new_deals:
            db.log_task("scheduler", "slickdeals_monitor", "No new deals found", "success")
            return

        lines = [f"- {d.get('title','')}\n  {d.get('description','')}\n  {d.get('url','')}" for d in new_deals]
        body = "New Nintendo deals on Slickdeals:\n\n" + "\n\n".join(lines)
        subject = f"Slickdeals Nintendo Alert — {len(new_deals)} new deal(s)"

        emailer.send_email(subject, body)
        if discord_bot.is_ready():
            discord_bot.post_message("brexis-alerts", f"**{subject}**\n\n{body}")

        db.log_task("scheduler", "slickdeals_monitor", f"{len(new_deals)} new deal(s) alerted", "success")

    except Exception as e:
        logger.error(f"Slickdeals monitor failed: {e}")
        db.log_task("scheduler", "slickdeals_monitor", f"Failed: {e}", "failed")


def get_price_alerts():
    """Return all items with alert_triggered=True across to_be_purchased POs."""
    orders = db.list_purchase_orders(status="to_be_purchased")
    alerts = []
    for po in orders:
        for item in (po.get("items") or []):
            if item.get("alert_triggered"):
                alerts.append({
                    "po_number":    po["po_number"],
                    "po_id":        po["id"],
                    "title":        po["title"],
                    "vendor":       po.get("vendor"),
                    "item_name":    item.get("name"),
                    "unit_price":   item.get("unit_price"),
                    "last_price":   item.get("last_price"),
                    "last_checked": item.get("last_checked"),
                })
    return alerts


# ── Scheduler init ──

def start_scheduler():
    if scheduler.running:
        return

    # Morning briefing — 8 AM daily
    scheduler.add_job(
        job_morning_briefing,
        CronTrigger(hour=8, minute=0),
        id="morning_briefing",
        replace_existing=True,
        name="Morning Briefing",
    )

    # Weekly market report — Monday 8 AM
    scheduler.add_job(
        job_weekly_market_report,
        CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="weekly_market_report",
        replace_existing=True,
        name="Weekly Market Report",
    )

    # Deadline alerts — check every 6 hours
    scheduler.add_job(
        job_deadline_alert,
        IntervalTrigger(hours=6),
        id="deadline_alert",
        replace_existing=True,
        name="Pre-order Deadline Alert",
    )

    # Low inventory check — daily at 9 AM
    scheduler.add_job(
        job_low_inventory_alert,
        CronTrigger(hour=9, minute=0),
        id="low_inventory_alert",
        replace_existing=True,
        name="Low Inventory Alert",
    )

    # PO price monitor — daily at 9 AM
    scheduler.add_job(
        job_po_price_monitor,
        CronTrigger(hour=9, minute=15),
        id="po_price_monitor",
        replace_existing=True,
        name="PO Price Monitor",
    )

    # Slickdeals Nintendo keyword monitor — Mon/Thu/Sat at 9 AM
    scheduler.add_job(
        job_slickdeals_monitor,
        CronTrigger(day_of_week="mon,thu,sat", hour=9, minute=0),
        id="slickdeals_monitor",
        replace_existing=True,
        name="Slickdeals Nintendo Monitor",
    )

    scheduler.start()
    logger.info("Brexis scheduler started.")
    db.log_task("scheduler", "start", "APScheduler started with 6 jobs", "success")


def get_job_status():
    if not scheduler.running:
        return []
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time)[:19] if job.next_run_time else "N/A",
        })
    return jobs


def trigger_job(job_id):
    job_map = {
        "morning_briefing":    job_morning_briefing,
        "weekly_market_report": job_weekly_market_report,
        "deadline_alert":      job_deadline_alert,
        "low_inventory_alert": job_low_inventory_alert,
        "po_price_monitor":    job_po_price_monitor,
    }
    fn = job_map.get(job_id)
    if fn:
        import threading
        threading.Thread(target=fn, daemon=True).start()
        return True
    return False
