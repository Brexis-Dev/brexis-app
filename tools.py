import json
import database as db


TOOL_DEFINITIONS = [
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

    return f"Unknown tool: {name}"
