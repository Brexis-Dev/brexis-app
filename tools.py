import json
import database as db


TOOL_DEFINITIONS = [
    {
        "name": "send_discord_message",
        "description": "Post a message to a Discord channel in the Saturday Morning PJs server. Use for announcements, alerts, listings, and reports.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name without #, e.g. 'switch-listings', 'brexis-alerts', 'daily-briefing'"},
                "message": {"type": "string", "description": "Message content to post"},
                "pin": {"type": "boolean", "description": "Whether to pin the message after posting"}
            },
            "required": ["channel", "message"]
        }
    },
    {
        "name": "setup_discord_channels",
        "description": "Set up the full Saturday Morning PJs Discord server channel structure including public and private categories.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "create_discord_channel",
        "description": "Create a new Discord channel in the Saturday Morning PJs server.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Channel name (lowercase, hyphens)"},
                "category": {"type": "string", "description": "Category name to place it under"},
                "private": {"type": "boolean", "description": "Whether the channel should be private (owner only)"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "get_task_history",
        "description": "Get the recent task history log showing all autonomous actions Brexis has taken — Discord posts, emails, scheduled jobs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of recent entries to return (default 20)"}
            },
            "required": []
        }
    },
    {
        "name": "trigger_scheduled_job",
        "description": "Manually trigger a scheduled job right now without waiting for its next scheduled time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Job to trigger",
                    "enum": ["morning_briefing", "weekly_market_report", "deadline_alert", "low_inventory_alert"]
                }
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "get_inventory_summary",
        "description": "Get a count of items across all Purple Horizon inventory categories for this user.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_lrg_games",
        "description": "Get the LRG (Limited Run Games) tracker — titles being watched, pre-ordered, owned, or sold.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: watching, pre-ordered, owned, sold. Omit for all.",
                    "enum": ["watching", "pre-ordered", "owned", "sold"]
                }
            },
            "required": []
        }
    },
    {
        "name": "search_inventory",
        "description": "Search across all inventory categories (games, cards, figures, comics, apparel, shoes, LRG) by title or name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term to look for in item names and titles."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "add_lrg_game",
        "description": "Add a new game to the LRG tracker. Use this when the user wants to track a new title.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Game title"},
                "publisher": {"type": "string", "description": "Publisher name, e.g. Limited Run Games"},
                "status": {
                    "type": "string",
                    "description": "Current status",
                    "enum": ["watching", "pre-ordered", "owned", "sold"]
                },
                "buy_price": {"type": "number", "description": "Purchase price in USD"},
                "est_resale": {"type": "number", "description": "Estimated resale value in USD"},
                "deadline": {"type": "string", "description": "Pre-order deadline date (YYYY-MM-DD)"},
                "notes": {"type": "string", "description": "Any notes about this title"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "calculate_profit",
        "description": "Calculate net profit after platform fees for a resale transaction.",
        "input_schema": {
            "type": "object",
            "properties": {
                "buy_price": {"type": "number", "description": "What you paid for the item"},
                "sell_price": {"type": "number", "description": "What you sold or plan to sell it for"},
                "platform": {
                    "type": "string",
                    "description": "Selling platform",
                    "enum": ["ebay", "mercari", "facebook", "reddit"]
                }
            },
            "required": ["buy_price", "sell_price", "platform"]
        }
    }
]


FEE_RATES = {
    "ebay": 0.1295,
    "mercari": 0.13,
    "facebook": 0.0,
    "reddit": 0.0,
}


def execute_tool(name, inputs, user_id):
    if name == "get_inventory_summary":
        summary = db.get_inventory_summary(user_id)
        total = sum(summary.values())
        lines = [f"- {k.replace('_', ' ').title()}: {v} items" for k, v in summary.items()]
        return f"Inventory summary ({total} total items):\n" + "\n".join(lines)

    if name == "get_lrg_games":
        status = inputs.get("status")
        games = db.get_lrg_games(user_id, status)
        if not games:
            return "No LRG games found" + (f" with status '{status}'" if status else "") + "."
        lines = []
        for g in games:
            profit = (g.get("sold_for") or 0) - (g.get("buy_price") or 0)
            line = f"- {g['title']} ({g.get('publisher','')}) | Status: {g.get('status','')} | Buy: ${g.get('buy_price',0):.2f} | Est Resale: ${g.get('est_resale',0):.2f}"
            if g.get("sold_for"):
                line += f" | Sold: ${g['sold_for']:.2f} | P/L: ${profit:+.2f}"
            if g.get("deadline"):
                line += f" | Deadline: {g['deadline']}"
            lines.append(line)
        return f"LRG Tracker ({len(games)} items):\n" + "\n".join(lines)

    if name == "search_inventory":
        query = inputs.get("query", "")
        results = db.search_inventory(user_id, query)
        if not results:
            return f"No items found matching '{query}'."
        lines = [f"- [{r['category']}] {r['display_name']} ({r['display_sub']}) | Status: {r.get('status','')} | Paid: ${r.get('purchase_price') or 0:.2f}" for r in results]
        return f"Found {len(results)} items matching '{query}':\n" + "\n".join(lines)

    if name == "add_lrg_game":
        new_id = db.add_lrg_game(
            user_id=user_id,
            title=inputs["title"],
            publisher=inputs.get("publisher", "Limited Run Games"),
            status=inputs.get("status", "watching"),
            buy_price=inputs.get("buy_price", 0),
            est_resale=inputs.get("est_resale", 0),
            deadline=inputs.get("deadline"),
            notes=inputs.get("notes"),
        )
        if isinstance(new_id, dict) and "error" in new_id:
            return f"Failed to add game: {new_id['error']}"
        return f"✓ Added '{inputs['title']}' to your LRG tracker (ID: {new_id}) with status '{inputs.get('status','watching')}'."

    if name == "calculate_profit":
        buy = float(inputs["buy_price"])
        sell = float(inputs["sell_price"])
        platform = inputs["platform"].lower()
        rate = FEE_RATES.get(platform, 0)
        fees = sell * rate
        net = sell - fees - buy
        roi = (net / buy * 100) if buy > 0 else 0
        return (
            f"Profit calculation for {platform.title()}:\n"
            f"- Buy price: ${buy:.2f}\n"
            f"- Sell price: ${sell:.2f}\n"
            f"- Platform fees ({rate*100:.1f}%): ${fees:.2f}\n"
            f"- Net profit: ${net:.2f}\n"
            f"- ROI: {roi:.1f}%"
        )

    if name == "send_discord_message":
        import discord_bot
        if not discord_bot.is_ready():
            return "Discord bot is not connected. Check that DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are set in /settings."
        channel = inputs["channel"]
        message = inputs["message"]
        pin = inputs.get("pin", False)
        result = discord_bot.post_message(channel, message, pin=pin)
        db.log_task("discord", "post_message", f"#{channel}: {message[:80]}", "success" if "Posted" in result or "✓" in result else "failed")
        return result

    if name == "setup_discord_channels":
        import discord_bot
        if not discord_bot.is_ready():
            return "Discord bot is not connected. Check that DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are set in /settings."
        result = discord_bot.setup_channels()
        db.log_task("discord", "setup_channels", result[:120], "success")
        return result

    if name == "create_discord_channel":
        import discord_bot
        if not discord_bot.is_ready():
            return "Discord bot is not connected."
        result = discord_bot.create_channel(
            name=inputs["name"],
            category_name=inputs.get("category"),
            private=inputs.get("private", False),
        )
        db.log_task("discord", "create_channel", f"#{inputs['name']}", "success")
        return result

    if name == "get_task_history":
        limit = inputs.get("limit", 20)
        logs = db.get_task_log(limit)
        if not logs:
            return "No task history found yet."
        lines = [f"[{r.get('created_at','')[:16]}] [{r.get('category','')}] {r.get('action','')} — {r.get('detail','')} ({r.get('status','')})" for r in logs]
        return f"Recent task history ({len(logs)} entries):\n" + "\n".join(lines)

    if name == "trigger_scheduled_job":
        import scheduler
        job_id = inputs["job_id"]
        ok = scheduler.trigger_job(job_id)
        if ok:
            db.log_task("scheduler", "manual_trigger", f"Triggered: {job_id}", "success")
            return f"✓ Triggered job '{job_id}' — it is running in the background now."
        return f"Unknown job '{job_id}'."

    return f"Unknown tool: {name}"
