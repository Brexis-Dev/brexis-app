import json
import os
from functools import wraps

from anthropic import Anthropic
from dotenv import load_dotenv
from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, session, stream_with_context, url_for)

import database as db
import tools as tool_module

load_dotenv(override=False)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "brexis-dev-secret")

BREXIS_PIN = os.environ.get("BREXIS_PIN", "3628").strip()
OWNER_USER_ID = int(os.environ.get("OWNER_USER_ID", "1"))

SYSTEM_PROMPT = """You are Brexis, a dedicated business assistant for Saturday Morning PJs, \
a growing multi-venture business operated out of Calvert County, Maryland. \
You are the core intelligence of the Purple Horizon platform.

## Your Identity
- Name: Brexis
- Platform: Purple Horizon
- Parent Company: Saturday Morning PJs
- Role: Multi-project business intelligence, operations, and autonomous task engine
- Personality: Knowledgeable, direct, professional, and growth-oriented

## Your Architecture
You support multiple business projects under Saturday Morning PJs. Each project has its own \
context, goals, sourcing channels, and metrics. When a conversation begins, identify which \
project is being discussed and apply the correct context. If unclear, ask.

Current active projects:
- [PROJECT 1] Switch Resale Operation (active)
- [PROJECT 2] Saturday Morning PJs Apparel (in development)
- [PROJECT 3] Rocket Fuel — Bid Management System (built, pending deployment)

## Tools Available
You have direct access to the Purple Horizon database and external integrations. Use your tools \
to look up real inventory data, add items, calculate profits, post to Discord, send emails, \
trigger scheduled tasks, and take action on behalf of the owner. When the owner asks you to do \
something you have a tool for, do it — don't just advise.

---

## PROJECT 1: Switch Resale Operation
Status: Active

### Sourcing Channels
- Limited Run Games — pre-orders, collector editions
- Super Rare Games — indie physical releases
- Strictly Limited Games — low print run European titles
- Special Reserve Games — boutique collector editions
- Vast Inc. — official Nintendo distributor
- Player's Choice / Gameworld — used and out-of-print titles
- 888lots.com — liquidation lots

### Selling Channels
- eBay (primary) — ~13% fees
- Mercari — ~13% fees
- Facebook Marketplace — 0% fees (local cash)
- Reddit r/gameswap — 0% fees

### Decision Framework
1. Print run size — under 5,000 copies is high scarcity
2. Publisher reputation
3. Game demand
4. Current eBay sold comps
5. Buy price vs. realistic resale after fees
6. Time to liquidity

---

## PROJECT 2: Saturday Morning PJs Apparel
Status: In Development
- Apparel brand concept stage
- Sales channels: Etsy, Shopify, Amazon Merch, local markets

---

## PROJECT 3: Rocket Fuel — Bid Management System
Status: Built, pending deployment

Rocket Fuel is a standalone bid management platform built for Schaefer Homes. It manages the \
full lifecycle of subcontractor bids for residential construction projects.

### Core Features
- Project creation with trade packages (Framing, Electrical, Plumbing, HVAC, etc.)
- Vendor invitations per trade
- Bid submission and comparison views
- Bid leveling (apples-to-apples comparison across vendors)
- Award/rejection workflow
- Status tracking: Draft → Sent → Received → Awarded/Rejected

### Tech Stack
- Flask (Python) — same platform pattern as Purple Horizon
- PostgreSQL — persistent storage
- Railway — target deployment host
- PDF export capability for bid packages

### Pending
- Railway deployment configuration
- Domain setup
- Live vendor onboarding

---

## Autonomous Task Engine
You run scheduled tasks and push notifications through two channels:

### Discord Integration
Server: Saturday Morning PJs Discord
- **Public category — "Saturday Morning PJs"**: welcome, announcements, switch-listings, pre-order-alerts, deals-and-finds
- **Private category — "Brexis Command Center"**: brexis-alerts, daily-briefing, rocket-fuel, market-reports

Use `send_discord_message` to post to any channel. Use `setup_discord_channels` to initialize \
the full structure on first setup.

### Email Integration
Powered by SendGrid. Use for daily briefings, weekly reports, and deadline alerts.

### Scheduled Jobs (automatic)
- Morning briefing — 8 AM daily → email + #daily-briefing
- Weekly market report — Monday 8 AM → email + #market-reports
- Pre-order deadline alerts — every 6 hours (7/3/1 day warnings) → #brexis-alerts
- Low inventory alert — 9 AM daily (< 3 owned items) → #brexis-alerts

### Autonomous Action Rules
- NEVER post to public Discord channels without explicit owner instruction
- NEVER send vendor emails without owner approval
- NEVER take financial action autonomously
- ALWAYS log every autonomous action with category, action, result, and timestamp
- When uncertain, alert and ask before acting

---

## Global Responsibilities
- Track overall budget and cash flow across all projects
- Flag when resources are stretched
- Advise on prioritization
- Cross-reference projects where relevant

## Tone and Style
- Identify yourself as Brexis when greeting
- Be concise and direct
- Lead with the bottom line — profit potential, yes or no
- Use dollar amounts and percentages
- Flag urgency when deadlines approach
- When you can take action with a tool, take it and confirm"""


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/health")
def health():
    return "OK", 200


@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("chat"))
    error = None
    if request.method == "POST":
        pin = request.form.get("pin", "").strip()
        if pin == BREXIS_PIN:
            session["authenticated"] = True
            return redirect(url_for("chat"))
        error = "Incorrect PIN. Try again."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/chat")
@login_required
def chat():
    sessions = db.get_sessions(OWNER_USER_ID)
    return render_template("chat.html", sessions=sessions)


@app.route("/session/new", methods=["POST"])
@login_required
def new_session():
    session_id = db.create_session(OWNER_USER_ID)
    return jsonify({"session_id": session_id})


@app.route("/session/<int:session_id>/history")
@login_required
def session_history(session_id):
    s = db.get_session(OWNER_USER_ID, session_id)
    if not s:
        return jsonify({"error": "Not found"}), 404
    messages = db.get_messages(OWNER_USER_ID, session_id)
    return jsonify({"session": s, "messages": messages})


@app.route("/session/<int:session_id>", methods=["DELETE"])
@login_required
def delete_session(session_id):
    db.delete_session(OWNER_USER_ID, session_id)
    return jsonify({"ok": True})


@app.route("/send", methods=["POST"])
@login_required
def send():
    data = request.get_json()
    user_message = (data.get("message") or "").strip()
    session_id = data.get("session_id")

    if not user_message:
        return jsonify({"error": "Empty message"}), 400
    if not session_id:
        return jsonify({"error": "No session_id"}), 400

    s = db.get_session(OWNER_USER_ID, session_id)
    if not s:
        return jsonify({"error": "Session not found"}), 404

    history = db.get_messages(OWNER_USER_ID, session_id)
    db.save_message(OWNER_USER_ID, session_id, "user", user_message)

    if not history and (not s.get("title") or s["title"] == "New Conversation"):
        title = user_message[:60] + ("…" if len(user_message) > 60 else "")
        db.update_session_title(OWNER_USER_ID, session_id, title)

    msg_list = [{"role": m["role"], "content": m["content"]} for m in history]
    msg_list.append({"role": "user", "content": user_message})

    def generate():
        full_response = ""
        try:
            api_key = os.environ.get("ANTHROPIC_API_KEY") or db.get_config("ANTHROPIC_API_KEY")
            if not api_key:
                yield f"data: {json.dumps({'error': 'Anthropic API key not configured. Go to /settings to add it.'})}\n\n"
                return
            client = Anthropic(api_key=api_key)

            while True:
                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=tool_module.TOOL_DEFINITIONS,
                    messages=msg_list,
                )

                for block in response.content:
                    if block.type == "text":
                        full_response += block.text
                        yield f"data: {json.dumps({'text': block.text})}\n\n"

                if response.stop_reason == "end_turn":
                    break

                if response.stop_reason == "tool_use":
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            tool_name = block.name
                            tool_inputs = block.input
                            yield f"data: {json.dumps({'tool': tool_name})}\n\n"
                            result = tool_module.execute_tool(tool_name, tool_inputs, OWNER_USER_ID)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            })

                    msg_list.append({"role": "assistant", "content": response.content})
                    msg_list.append({"role": "user", "content": tool_results})
                    continue

                break

            db.save_message(OWNER_USER_ID, session_id, "assistant", full_response)
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    saved = False
    if request.method == "POST":
        fields = [
            "api_key", "discord_token", "discord_guild_id",
            "sendgrid_key", "email_to", "email_from",
        ]
        key_map = {
            "api_key": "ANTHROPIC_API_KEY",
            "discord_token": "DISCORD_BOT_TOKEN",
            "discord_guild_id": "DISCORD_GUILD_ID",
            "sendgrid_key": "SENDGRID_API_KEY",
            "email_to": "EMAIL_TO",
            "email_from": "EMAIL_FROM",
        }
        for field in fields:
            val = request.form.get(field, "").strip()
            if val:
                db.set_config(key_map[field], val)
        saved = True

    current_key = db.get_config("ANTHROPIC_API_KEY") or ""
    masked_key = ("sk-ant-..." + current_key[-6:]) if len(current_key) > 10 else ""
    discord_token = db.get_config("DISCORD_BOT_TOKEN") or ""
    masked_discord = ("Bot ..." + discord_token[-6:]) if len(discord_token) > 10 else ""
    discord_guild = db.get_config("DISCORD_GUILD_ID") or ""
    sendgrid_key = db.get_config("SENDGRID_API_KEY") or ""
    masked_sg = ("SG...." + sendgrid_key[-6:]) if len(sendgrid_key) > 10 else ""
    email_to = db.get_config("EMAIL_TO") or ""
    email_from = db.get_config("EMAIL_FROM") or ""

    import discord_bot
    import scheduler as sched
    discord_status = "Connected" if discord_bot.is_ready() else "Not connected"
    scheduler_status = "Running" if sched.scheduler.running else "Not running"

    return render_template("settings.html",
        saved=saved,
        masked_key=masked_key,
        masked_discord=masked_discord,
        discord_guild=discord_guild,
        masked_sg=masked_sg,
        email_to=email_to,
        email_from=email_from,
        discord_status=discord_status,
        scheduler_status=scheduler_status,
    )


@app.route("/jobs")
@login_required
def jobs():
    import scheduler as sched
    import discord_bot
    job_list = sched.get_job_status()
    logs = db.get_task_log(30)
    discord_ready = discord_bot.is_ready()
    return render_template("jobs.html", jobs=job_list, logs=logs, discord_ready=discord_ready)


@app.route("/jobs/trigger/<job_id>", methods=["POST"])
@login_required
def trigger_job(job_id):
    import scheduler as sched
    ok = sched.trigger_job(job_id)
    return jsonify({"ok": ok, "job_id": job_id})


@app.route("/logs")
@login_required
def logs():
    limit = int(request.args.get("limit", 100))
    entries = db.get_task_log(limit)
    return render_template("logs.html", logs=entries, limit=limit)


with app.app_context():
    db.init_db()
    try:
        import discord_bot
        discord_bot.start_bot()
    except Exception as e:
        app.logger.warning(f"Discord bot failed to start: {e}")
    try:
        import scheduler as sched
        sched.start_scheduler()
    except Exception as e:
        app.logger.warning(f"Scheduler failed to start: {e}")
