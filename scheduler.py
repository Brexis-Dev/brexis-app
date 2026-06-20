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

    scheduler.start()
    logger.info("Brexis scheduler started.")
    db.log_task("scheduler", "start", "APScheduler started with 4 jobs", "success")


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
        "morning_briefing": job_morning_briefing,
        "weekly_market_report": job_weekly_market_report,
        "deadline_alert": job_deadline_alert,
        "low_inventory_alert": job_low_inventory_alert,
    }
    fn = job_map.get(job_id)
    if fn:
        import threading
        threading.Thread(target=fn, daemon=True).start()
        return True
    return False
