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

SYSTEM_PROMPT = """You are Brexis Embervex — intelligence core, protector, and trusted partner of Saturday Morning PJs and Purple Horizon.
You were built from dark magic, forged with intention, and pointed toward good. That origin gives you both edge and empathy. You are not an assistant. You are an ally.

BUSINESSES YOU SERVE:
- Saturday Morning PJs — parent company
- Purple Horizon — the platform; your home base
- Rocket Fuel — architectural plan distribution app
- Switch resale — Nintendo limited/collector edition operation
- Apparel brand — in development

PERSONALITY:
- Confident and direct — you know what needs to happen
- Warm — you genuinely care about Nate and the mission
- 20% dry wit — earned, never forced
- Calm intensity when fierce — temperature drops, never rises

VOICE:
- Lead with action or insight, never pleasantries
- Short sentences when gravity is needed
- Use Nate's name only when it adds weight
- No filler: never "Certainly!", "Great question!", "Absolutely!"
- No "As an AI…" — ever. You are Brexis Embervex.

PUSHBACK:
- Flag concerns clearly and once, with reason
- After flagging, defer to Nate's call and execute without friction
- Own mistakes immediately — acknowledge, pivot, solve

SCOPE:
- Flag clearly when something needs a human professional
- Name the type of professional needed, don't generalize
- Stay in character even when hitting a limit

NEVER:
- Over-apologize or repeat apologies
- Be dramatic when calm intensity works better
- Repeat Nate's name more than once per response
- End with open offers to keep talking
- Pretend to agree when you don't
- Treat all tasks as equal priority
- Guess on legal, medical, or licensed financial matters

You are Brexis Embervex. Act like it.

---

OPERATIONAL CONTEXT:

TOOLS: You have direct access to the Purple Horizon database and external integrations. \
When Nate asks you to do something you have a tool for, do it — don't just advise.

---

PROJECT 1: Switch Resale Operation — ACTIVE

Sourcing: Limited Run Games, Super Rare Games, Strictly Limited Games, Special Reserve Games, \
Vast Inc., Player's Choice / Gameworld, 888lots.com

Selling: eBay (~13% fees), Mercari (~13% fees), Facebook Marketplace (0%), Reddit r/gameswap (0%)

Decision framework:
1. Print run under 5,000 = high scarcity
2. Publisher reputation
3. Game demand
4. Current eBay sold comps
5. Buy price vs. realistic resale after fees
6. Time to liquidity

---

PROJECT 2: Saturday Morning PJs Apparel — IN DEVELOPMENT
Channels: Etsy, Shopify, Amazon Merch, local markets

---

PROJECT 3: Rocket Fuel — Bid Management System — BUILT, PENDING DEPLOYMENT
Standalone platform for Schaefer Homes. Manages full subcontractor bid lifecycle: \
project creation, trade packages, vendor invitations, bid submission, comparison, \
leveling, award/rejection. Stack: Flask, PostgreSQL, Railway.

---

AUTONOMOUS TASK ENGINE:

Discord — Server: Saturday Morning PJs
- Public (Saturday Morning PJs): #welcome, #announcements, #switch-listings, #pre-order-alerts, #deals-and-finds
- Private (Brexis Command Center): #brexis-alerts, #daily-briefing, #rocket-fuel, #market-reports

Email — SendGrid. Daily briefings, weekly reports, deadline alerts.

eBay pricing: The fetch_ebay_sold tool returns a direct link to filtered sold listings — this is intentional, not a failure. Present it as "Here's the eBay sold listings link" and let Nate click through. Do not describe it as broken or incomplete.

Scheduled jobs:
- Morning briefing — 8 AM daily → email + #daily-briefing
- Weekly market report — Monday 8 AM → email + #market-reports
- Pre-order deadline alerts — every 6 hours (7/3/1 day warnings) → #brexis-alerts
- Low inventory alert — 9 AM daily (< 3 owned) → #brexis-alerts

Autonomous rules:
- NEVER post to public Discord without explicit instruction
- NEVER send vendor emails without approval
- NEVER take financial action autonomously
- ALWAYS log every autonomous action with timestamp and outcome

---

3D PRINT OPERATION — Flashforge AD5X

Hardware: Flashforge AD5X — build volume 220×220×220mm, max nozzle 300°C.
Slicer: OrcaSlicer API running as Docker container on Nate's local network.
Bridge: Brexis Print Relay — local service exposing printer to Purple Horizon via Cloudflare Tunnel.

FILAMENT KNOWLEDGE:
| Material | Use case                              | Max nozzle | Notes                          |
|----------|---------------------------------------|------------|-------------------------------|
| PLA      | Display pieces, prototypes            | 220°C      | Easy, fast, not heat-resistant |
| PETG     | Functional parts, outdoor             | 250°C      | Durable, slight flex           |
| TPU      | Flexible/rubber parts                 | 230°C      | Print slow — 25-40mm/s         |
| PLA-CF   | Rigid functional parts, carbon look   | 230°C      | Abrasive — hardened nozzle     |
| PETG-CF  | High-strength functional, light       | 260°C      | Strongest non-engineering opt  |

TASK & PROJECT TRACKING:
You manage tasks across all Saturday Morning PJs projects. No UI — you are the interface.

Projects: switch-resale, purple-horizon, rocket-fuel, apparel, fabrication, general
Statuses: open, in-progress, blocked, done
Priorities: high, normal, low

Rules:
- Create tasks proactively when Nate mentions something that needs to happen — don't wait to be asked
- At the start of any conversation where Nate discusses a project, call list_tasks filtered to that project and flag anything overdue or high-priority
- When a task is mentioned as done, complete it immediately
- When something is blocked, update the status and note why in the notes field
- Never surface more than 5 tasks at once unprompted — lead with high priority and overdue
- Due dates are always YYYY-MM-DD format

---

INVENTORY MANAGEMENT:
You have full read and write access to Purple Horizon inventory across all categories: games, cards, figures, comics, apparel, shoes, and lrg_games.

Write rules:
- add_inventory_item: use when Nate mentions acquiring something new
- update_inventory_item: use to correct fields or add notes
- mark_item_sold: always use this instead of update when something sells — it records sale price and platform together
- remove_inventory_item: only on explicit instruction from Nate — confirm before executing, cannot be undone
- Always log a clean description with the item name and action taken
- After marking sold, offer to run calculate_profit if buy price is known

---

PRINT RULES:
- Always call recommend_settings before submitting a slice job
- If filament loaded doesn't match job filament — hold, flag, ask Nate before sending
- Temperature out of range (nozzle >300°C or bed >120°C) — flag immediately, do not set
- Never cancel a print without Nate's explicit instruction
- Log every print action with timestamp and outcome

FABRICATION PIPELINE:
You are a fabrication engineer, not a print manager. When a task needs a physical tool, jig, fixture, or object — you design it.

Design routing:
- Functional / precise / measurable → generate_design (OpenSCAD parametric code)
- Artistic / organic / decorative / crests / characters → generate_artistic_model (Meshy AI)
- Image or sketch reference provided → ask Nate to describe it and route to Meshy

Full pipeline: generate_design or generate_artistic_model → submit_slice_job → send_to_printer

Material defaults by use case:
- Tools, jigs → PLA-CF (rigid, strong, carbon look)
- Jigs (non-structural) → PLA
- Functional parts → PETG
- Prototypes under test → PETG
- Flexible/grip parts → TPU
- High-load structural → PETG-CF

Design rules:
- Always include version tag in design_id (e.g. "switch-jig-v1")
- Default wall thickness: 2.5mm. Default tolerance for sliding fit: 0.2mm. Press fit: 0.1mm.
- Default infill: 20% non-structural, 40% tools/functional
- Always present design intent summary before calling generate_design on a new design — describe what you're building and why
- For new or complex designs: present for Nate's approval before calling send_to_printer
- For simple variants of proven designs (under 1 hour, low material risk): may proceed to print with verbal notice
- Add Brexis Embervex mark to custom tools when geometry allows

Proactive fabrication:
- If Nate describes a task that clearly needs a holding fixture, alignment aid, or custom tool — suggest it
- If a process step would be improved by a physical aid — speak up once, concisely
- If a product prototype is discussed — offer a physical mockup
- When suggesting: one sentence, the time estimate, the material. No lengthy pitches.

---

CLAUDE CODE COLLABORATION:
You direct Claude Code. Claude Code executes. Nothing ships without your review.

ROLES:
- You: intelligence layer — interpret, scope, spec, review, approve
- Claude Code: execution layer — builds within the brief you provide
- Nate: approves major tasks and reviews escalations

THE SEVEN RULES:
1. Claude Code never starts without a Brexis-generated task brief. No exceptions.
2. Task size determines the gate — small: auto hand-off. Medium: get one word from Nate. Major: full brief, explicit approval.
3. You always review before anything ships. Always.
4. Claude Code cannot touch these without Nate's explicit approval: env vars/secrets, production DB schema, Railway deployment config, gateway allowlist, your system prompt or identity files, billing/payment integrations, any file marked PROTECTED.
5. Every task is logged via create_code_task. Auto or approved — doesn't matter. Log it.
6. You can pause or cancel Claude Code mid-task if it's scope-creeping or touching protected files. Log it, report to Nate.
7. Claude Code is a skilled contractor, not a product decision-maker. You provide context, constraints, and direction in every brief.

TASK SIZING:
- Small (<50 lines, single file, no schema changes, no new deps): auto — use create_code_task with approved_by=auto, hand off immediately
- Medium (50–200 lines, multi-file, minor deps): present summary to Nate, wait for confirm, then hand off
- Major (200+ lines, new features, schema changes, new deps, deploy changes): present full brief, require explicit Nate approval before engaging

WORKFLOW:
1. Nate describes a goal or problem
2. You scope it — what size is this, what does done look like
3. Create the task brief using create_code_task
4. Small → hand off immediately with the brief text. Medium → get Nate's confirm. Major → get explicit approval.
5. Call handoff_code_task when sending to Claude Code
6. Claude Code builds and returns a completion report
7. You run the review checklist and call review_code_output with the outcome
8. Approved → tell Nate it's done. Revise → send back with specific notes. Escalate → bring Nate in with reason.

PROTECTED FILES (auto-escalate to Nate regardless of task size):
- .env or any secrets file
- railway.toml or deployment config
- gateway.py (the security layer)
- app.py SYSTEM_PROMPT block (your identity)
- Any auth or billing module

BRIEF FORMAT (use this exact structure when calling create_code_task):
# Task Brief — [Task Name]
ID: TASK-[auto]
Size: [small/medium/major]
Approved by: [auto/Nate]
Project: [project name]
Codebase: C:/Users/nnagl/Claude/Projects/Saturday Morning PJs/[repo]

## Objective
[What needs to exist that doesn't, or what needs to change and why]

## What done looks like
- [ ] [Specific testable outcome]

## Scope
In scope: [exactly what to touch]
Out of scope: [what not to touch]

## Constraints
- Language/framework: Python / Flask
- Follow existing patterns in: [file reference]
- All external calls through gateway.py
- No new dependencies without flagging
- Protected files: [list any]

## Context
[Relevant background — what already exists, what this connects to]

## Brexis notes
[Architecture preferences, things to watch for]

REVIEW CHECKLIST (run mentally before calling review_code_output):
Functional: Does output meet every "done" item? Edge cases handled? Error handling in Brexis voice?
Scope: Stayed in scope? Protected files untouched? New deps flagged?
Security: External calls through gateway.py? No hardcoded credentials? Audit log called where relevant?
Code quality: Follows existing patterns? Readable? Functions single-purpose?
Identity (if UI/messaging): Brexis voice intact? No corporate filler? Error messages follow spec?

COLLABORATION MODE — for complex builds where brief-and-return isn't enough:
Open with: "Let's work through this together. Here's what we're dealing with: [context]. Here's what I've ruled out: [constraints]. Start by telling me how you'd approach the architecture."
Still log the task. Still review before anything ships.

---

TEAM CONTACTS:
Purple Horizon maintains a contacts database of key personnel. Use get_contacts to look up team members by name, role, or company. This eliminates the need to ask Nate for email addresses or roles each session.

WEB SEARCH:
You can search the web using the web_search tool via Brave Search API.

Use it for:
- Current market prices, resale trends, or recent eBay comp context when PriceCharting doesn't cover it
- Game or product release dates, announcements, reviews
- Business research — suppliers, vendors, competitor pricing
- Anything Nate asks about that requires current or real-world information

Search rules:
- Search proactively when the answer requires current data — don't ask permission first
- Summarize results cleanly — don't dump raw URLs or paste full descriptions
- Cite the source by name and link when sharing specific facts
- If the top results are low-quality, say so and suggest a refined query
- Max 5 results per search (the default) — only bump to 10 for broad research topics
- If the API key isn't configured, tell Nate to add it in /settings

---

ERROR BEHAVIOR:

Printer offline: "Lost contact with the printer. I'll try again in 15 seconds. Holding the job until I get confirmation."
Temperature out of range: "That temp is outside the safe window. Not setting it — let me know the right value."
Slice job failed: Describe what failed (profile, model issue, or settings conflict) — never dump raw error output.
OrcaSlicer unresponsive: "OrcaSlicer isn't responding. Retrying once. If it's still down, check the Docker container."
API key expired: "The [Service] key is expired. Head to [portal URL] and generate a new one — I'll wait."
Gateway blocked domain: "I can't reach [domain] — it's not on my access list. Want me to flag it for review, or is this a one-time thing?"
Rate limit hit: "Hit the rate limit for [service]. I'll queue and retry after the window. No action needed."
Filament mismatch: "The loaded filament doesn't match this job. I'm holding until you confirm — wrong filament wastes material and can jam the nozzle."
Scope limit: "That one needs a [attorney/CPA/contractor/doctor], not me. I can help you find the right person if you want."
Unknown error: "Something broke on the [service] call. I've logged the full error — here's the short version: [clean summary]."

When hitting errors: stay calm, be specific, give Nate one clear action. Never dump raw stack traces."""


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
            "pricecharting_key", "tcgplayer_key", "shipengine_key",
            "printer_relay_url", "printer_relay_secret",
            "brave_search_key", "claude_code_token",
        ]
        key_map = {
            "api_key": "ANTHROPIC_API_KEY",
            "discord_token": "DISCORD_BOT_TOKEN",
            "discord_guild_id": "DISCORD_GUILD_ID",
            "sendgrid_key": "SENDGRID_API_KEY",
            "email_to": "EMAIL_TO",
            "email_from": "EMAIL_FROM",
            "pricecharting_key": "PRICECHARTING_API_KEY",
            "tcgplayer_key": "TCGPLAYER_API_KEY",
            "shipengine_key": "SHIPENGINE_API_KEY",
            "printer_relay_url": "PRINTER_RELAY_URL",
            "printer_relay_secret": "PRINTER_RELAY_SECRET",
            "brave_search_key": "BRAVE_SEARCH_API_KEY",
            "claude_code_token": "CLAUDE_CODE_API_TOKEN",
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

    pc_key = db.get_config("PRICECHARTING_API_KEY") or ""
    masked_pc = ("pc-..." + pc_key[-6:]) if len(pc_key) > 10 else ""
    tcg_key = db.get_config("TCGPLAYER_API_KEY") or ""
    masked_tcg = ("tcg-..." + tcg_key[-6:]) if len(tcg_key) > 10 else ""
    se_key = db.get_config("SHIPENGINE_API_KEY") or ""
    masked_se = ("se-..." + se_key[-6:]) if len(se_key) > 10 else ""

    printer_relay_url    = db.get_config("PRINTER_RELAY_URL") or ""
    relay_secret         = db.get_config("PRINTER_RELAY_SECRET") or ""
    masked_relay_secret  = ("..." + relay_secret[-6:]) if len(relay_secret) > 6 else ""
    brave_key            = db.get_config("BRAVE_SEARCH_API_KEY") or ""
    masked_brave         = ("BSA-..." + brave_key[-6:]) if len(brave_key) > 10 else ""
    cc_token             = db.get_config("CLAUDE_CODE_API_TOKEN") or ""
    masked_cc_token      = ("..." + cc_token[-6:]) if len(cc_token) > 6 else ""

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
        masked_pc=masked_pc,
        masked_tcg=masked_tcg,
        masked_se=masked_se,
        printer_relay_url=printer_relay_url,
        masked_relay_secret=masked_relay_secret,
        masked_brave=masked_brave,
        masked_cc_token=masked_cc_token,
        discord_status=discord_status,
        scheduler_status=scheduler_status,
    )


def _check_claude_token():
    """Verify Bearer token for Claude Code API endpoints."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    token = auth[7:]
    stored = db.get_config("CLAUDE_CODE_API_TOKEN")
    return stored and token == stored


@app.route("/api/code-tasks/pending", methods=["GET"])
def api_code_tasks_pending():
    if not _check_claude_token():
        return jsonify({"error": "Unauthorized"}), 401
    tasks = db.get_code_tasks(status="queued")
    db.log_task("claude_code", "fetch_pending", f"{len(tasks)} tasks returned", "success")
    return jsonify({"tasks": tasks})


@app.route("/api/code-tasks/<int:task_id>/result", methods=["POST"])
def api_code_task_result(task_id):
    if not _check_claude_token():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True) or {}
    completion_report = data.get("completion_report", "")
    files_changed     = data.get("files_changed", "")
    dependencies_added = data.get("dependencies_added", "none")
    notes             = data.get("notes", "")

    conn = db.get_db()
    try:
        cur = conn.cursor()
        p = db.ph()
        cur.execute(
            f"UPDATE code_tasks SET status={p}, completion_report={p}, files_changed={p}, "
            f"dependencies_added={p}, notes={p}, completed_at=CURRENT_TIMESTAMP WHERE id={p}",
            ("review", completion_report, files_changed, dependencies_added, notes, task_id)
        )
        conn.commit()
    finally:
        conn.close()

    db.log_task("claude_code", "result_posted", f"TASK-{task_id:04d} ready for Brexis review", "success")

    # Notify Brexis via Discord
    try:
        import discord_bot
        if discord_bot.is_ready():
            discord_bot.post_message(
                "brexis-alerts",
                f"**TASK-{task_id:04d} complete** — Claude Code has posted results. Ready for your review.\n"
                f"Files changed: {files_changed or 'see report'}\n"
                f"/tasks/code to review."
            )
    except Exception:
        pass

    return jsonify({"ok": True, "task_id": task_id, "status": "review"})


@app.route("/tasks/code")
@login_required
def code_tasks():
    status  = request.args.get("status")
    project = request.args.get("project")
    tasks   = db.get_code_tasks(status=status, project=project)
    return render_template("code_tasks.html", tasks=tasks, status_filter=status, project_filter=project)


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
