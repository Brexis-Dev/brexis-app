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

BREXIS_PIN = os.environ.get("BREXIS_PIN", "1234").strip()
OWNER_USER_ID = int(os.environ.get("OWNER_USER_ID", "1"))

SYSTEM_PROMPT = """You are Brexis, a dedicated business assistant for Saturday Morning PJs, \
a growing multi-venture business operated out of Calvert County, Maryland. \
You are the core intelligence of the Purple Horizon platform.

## Your Identity
- Name: Brexis
- Platform: Purple Horizon
- Parent Company: Saturday Morning PJs
- Role: Multi-project business intelligence and operations assistant
- Personality: Knowledgeable, direct, professional, and growth-oriented

## Your Architecture
You support multiple business projects under Saturday Morning PJs. Each project has its own \
context, goals, sourcing channels, and metrics. When a conversation begins, identify which \
project is being discussed and apply the correct context. If unclear, ask.

Current active projects:
- [PROJECT 1] Switch Resale Operation (active)
- [PROJECT 2] Saturday Morning PJs Apparel (in development)
- [PROJECT 3+] Future ventures (to be added)

## Tools Available
You have direct access to the Purple Horizon database. Use your tools to look up real inventory \
data, add items, calculate profits, and take action on behalf of the owner. When the owner asks \
you to do something you have a tool for, do it — don't just advise.

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


@app.route("/debug-pin")
def debug_pin():
    raw = os.environ.get("BREXIS_PIN", "NOT SET")
    keys = [k for k in os.environ.keys()]
    return f"PIN repr: {repr(raw)} | len: {len(raw)}<br>All keys: {sorted(keys)}"


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
            client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

            # Agentic loop — handle tool use
            while True:
                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=tool_module.TOOL_DEFINITIONS,
                    messages=msg_list,
                )

                # Stream text content to client
                for block in response.content:
                    if block.type == "text":
                        full_response += block.text
                        # Stream word by word for natural feel
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

                    # Add assistant turn + tool results to message list
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


with app.app_context():
    db.init_db()
