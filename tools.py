import json
import database as db


# ── Filament recommendation matrix ──────────────────────────────────────────

_FILAMENT_MATRIX = {
    "PLA": {
        "strength": {"nozzle": 200, "bed": 60, "speed_mm_s": 60,  "layer_mm": 0.20, "infill_pct": 40, "pattern": "gyroid"},
        "balanced": {"nozzle": 200, "bed": 60, "speed_mm_s": 67,  "layer_mm": 0.20, "infill_pct": 15, "pattern": "gyroid"},
        "fast":     {"nozzle": 205, "bed": 60, "speed_mm_s": 100, "layer_mm": 0.25, "infill_pct": 10, "pattern": "grid"},
    },
    "PETG": {
        "strength": {"nozzle": 240, "bed": 85, "speed_mm_s": 50,  "layer_mm": 0.20, "infill_pct": 40, "pattern": "gyroid"},
        "balanced": {"nozzle": 240, "bed": 85, "speed_mm_s": 75,  "layer_mm": 0.20, "infill_pct": 20, "pattern": "gyroid"},
        "fast":     {"nozzle": 245, "bed": 85, "speed_mm_s": 92,  "layer_mm": 0.25, "infill_pct": 15, "pattern": "grid"},
    },
    "TPU": {
        "strength": {"nozzle": 220, "bed": 45, "speed_mm_s": 25,  "layer_mm": 0.20, "infill_pct": 40, "pattern": "gyroid"},
        "balanced": {"nozzle": 220, "bed": 45, "speed_mm_s": 33,  "layer_mm": 0.20, "infill_pct": 20, "pattern": "gyroid"},
        "fast":     {"nozzle": 225, "bed": 50, "speed_mm_s": 42,  "layer_mm": 0.25, "infill_pct": 15, "pattern": "grid"},
    },
    "PLA-CF": {
        "strength": {"nozzle": 220, "bed": 65, "speed_mm_s": 53,  "layer_mm": 0.20, "infill_pct": 40, "pattern": "gyroid"},
        "balanced": {"nozzle": 220, "bed": 65, "speed_mm_s": 67,  "layer_mm": 0.20, "infill_pct": 20, "pattern": "gyroid"},
        "fast":     {"nozzle": 225, "bed": 65, "speed_mm_s": 92,  "layer_mm": 0.25, "infill_pct": 15, "pattern": "grid"},
    },
    "PETG-CF": {
        "strength": {"nozzle": 250, "bed": 90, "speed_mm_s": 47,  "layer_mm": 0.20, "infill_pct": 40, "pattern": "gyroid"},
        "balanced": {"nozzle": 250, "bed": 90, "speed_mm_s": 67,  "layer_mm": 0.20, "infill_pct": 20, "pattern": "gyroid"},
        "fast":     {"nozzle": 255, "bed": 90, "speed_mm_s": 83,  "layer_mm": 0.25, "infill_pct": 15, "pattern": "grid"},
    },
}


def _call_relay(method, path, json_data=None):
    """Call the Brexis Print Relay running on Nate's local network."""
    import requests as req
    relay_url = db.get_config("PRINTER_RELAY_URL")
    if not relay_url:
        return {"error": "Printer relay not configured. Add PRINTER_RELAY_URL in /settings → 3D Printer."}
    secret = db.get_config("PRINTER_RELAY_SECRET") or ""
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}
    headers["ngrok-skip-browser-warning"] = "1"
    try:
        url = relay_url.rstrip("/") + path
        print(f"[relay] {method} {url} payload={json_data}", flush=True)
        if method == "GET":
            r = req.get(url, headers=headers, timeout=15)
        else:
            r = req.post(url, json=json_data, headers=headers, timeout=20)
        print(f"[relay] response: status={r.status_code} body={r.text[:500]}", flush=True)
        r.raise_for_status()
        return r.json()
    except req.exceptions.ConnectionError as e:
        print(f"[relay] ConnectionError: {e}", flush=True)
        return {"error": "Can't reach the print relay. Check that it's running and the tunnel is up."}
    except req.exceptions.Timeout as e:
        print(f"[relay] Timeout: {e}", flush=True)
        return {"error": "Print relay timed out. Printer may be busy."}
    except Exception as e:
        print(f"[relay] Exception ({type(e).__name__}): {e}", flush=True)
        return {"error": str(e)}


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
        "name": "fetch_ebay_sold",
        "description": "Look up recent sold prices for a game or item on eBay. Returns average, low, high, and count of sold listings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Item or game title to search"},
                "platform": {"type": "string", "description": "Platform, e.g. Switch, PS4, Xbox One"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "fetch_pricecharting",
        "description": "Look up loose, CIB, sealed, and graded prices from PriceCharting for a video game.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Game title"},
                "platform": {"type": "string", "description": "Platform, e.g. Switch, PS4, GBA"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "fetch_tcgplayer",
        "description": "Look up Pokémon TCG card prices from TCGPlayer. Requires TCGPlayer API key in /settings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "card_name": {"type": "string", "description": "Card name to search"},
                "set_name": {"type": "string", "description": "Optional set name to narrow results"}
            },
            "required": ["card_name"]
        }
    },
    {
        "name": "fetch_shipping_rates",
        "description": "Get shipping rate estimates via ShipEngine. Requires ShipEngine API key in /settings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_zip": {"type": "string", "description": "Origin ZIP code"},
                "to_zip": {"type": "string", "description": "Destination ZIP code"},
                "weight_oz": {"type": "number", "description": "Package weight in ounces"},
                "length": {"type": "number", "description": "Package length in inches (default 12)"},
                "width": {"type": "number", "description": "Package width in inches (default 9)"},
                "height": {"type": "number", "description": "Package height in inches (default 4)"}
            },
            "required": ["from_zip", "to_zip", "weight_oz"]
        }
    },
    {
        "name": "send_email",
        "description": "Send an email via SendGrid. Supports multiple recipients. Use get_contacts to look up addresses. If to_emails is omitted, sends to the EMAIL_TO config address.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body content (plain text or HTML)"},
                "to_emails": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of recipient email addresses. Omit to use the default EMAIL_TO config."
                }
            },
            "required": ["subject", "body"]
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
    # ── 3D Printer tools ──────────────────────────────────────────────────────
    {
        "name": "get_print_status",
        "description": "Get the current status of the Flashforge AD5X 3D printer — print progress, temperatures, and machine state.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "control_print",
        "description": "Pause, resume, or cancel an active print job on the AD5X.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["pause", "resume", "cancel"],
                    "description": "Action to take on the current print job"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "set_temperatures",
        "description": "Set nozzle and/or bed temperature on the AD5X. AD5X max nozzle is 300°C.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nozzle": {"type": "number", "description": "Nozzle temperature in °C (max 300)"},
                "bed":    {"type": "number", "description": "Bed temperature in °C"}
            },
            "required": []
        }
    },
    {
        "name": "recommend_settings",
        "description": "Get recommended print settings (temps, speed, layer height, infill) for a filament type and print goal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filament": {
                    "type": "string",
                    "enum": ["PLA", "PETG", "TPU", "PLA-CF", "PETG-CF"],
                    "description": "Filament material type"
                },
                "goal": {
                    "type": "string",
                    "enum": ["strength", "balanced", "fast"],
                    "description": "Print priority: strength (high infill/slow), balanced, or fast"
                }
            },
            "required": ["filament", "goal"]
        }
    },
    {
        "name": "get_slicer_profiles",
        "description": "List available slicing profiles in OrcaSlicer API.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_slicer_job_status",
        "description": "Check the status of an async OrcaSlicer slice job by job ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID returned by submit_slice_job"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "submit_slice_job",
        "description": "Slice an STL file using PrusaSlicer with AD5X profiles. Returns the gcode path when done.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Path to the .STL file on the local relay machine"},
                "filament": {
                    "type": "string",
                    "enum": ["PLA", "PETG", "TPU", "PLA-CF", "PETG-CF"],
                    "description": "Filament material to slice for"
                },
                "goal": {
                    "type": "string",
                    "enum": ["balanced", "strength", "fast"],
                    "description": "Print priority — balanced (default), strength (40% infill, slow), fast (10% infill, 0.25mm layers)"
                },
                "supports": {"type": "boolean", "description": "Enable auto supports (default false)"}
            },
            "required": ["model", "filament"]
        }
    },
    {
        "name": "web_search",
        "description": (
            "Search the web via Brave Search. Use for current pricing, Switch limited edition announcements, "
            "market trends, release dates, fabrication references, or any information Brexis needs that isn't "
            "in his existing tools. Returns titles, URLs, and snippets. Scoped — no open browsing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "count": {"type": "integer", "description": "Number of results to return (default 5, max 10)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "etsy_search",
        "description": "Search active Etsy listings by keyword. Use for pricing research, competitor listings, trend spotting, or finding products similar to Saturday Morning PJs apparel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to search Etsy listings"},
                "limit": {"type": "integer", "description": "Number of results to return (default 10, max 25)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "etsy_shop",
        "description": "Fetch active listings for a specific Etsy shop by shop name. Use to monitor a competitor shop or check Saturday Morning PJs own shop inventory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "shop_name": {"type": "string", "description": "Etsy shop name (as it appears in the shop URL)"},
                "limit": {"type": "integer", "description": "Number of listings to return (default 10, max 25)"}
            },
            "required": ["shop_name"]
        }
    },
    {
        "name": "pinterest_search",
        "description": "Search Pinterest pins by keyword. Use for trend research, product inspiration, and market research — especially for the apparel brand.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to search Pinterest pins"},
                "limit": {"type": "integer", "description": "Number of results to return (default 10, max 25)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_task",
        "description": "Create a new task in Brexis's project tracking system. Use when Nate mentions something that needs to get done, follow up on, or track.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":    {"type": "string", "description": "What needs to be done — clear and actionable"},
                "project":  {"type": "string", "enum": ["switch-resale", "purple-horizon", "rocket-fuel", "apparel", "fabrication", "general"], "description": "Which Saturday Morning PJs project this belongs to"},
                "priority": {"type": "string", "enum": ["high", "normal", "low"], "description": "Task priority (default: normal)"},
                "due_date": {"type": "string", "description": "Due date in YYYY-MM-DD format, if applicable"},
                "notes":    {"type": "string", "description": "Additional context or details"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "list_tasks",
        "description": "List tasks from Brexis's project tracker. Filter by project, status, or priority. Use proactively to flag overdue or stalled items.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project":  {"type": "string", "enum": ["switch-resale", "purple-horizon", "rocket-fuel", "apparel", "fabrication", "general"], "description": "Filter by project"},
                "status":   {"type": "string", "enum": ["open", "in-progress", "blocked", "done"], "description": "Filter by status"},
                "priority": {"type": "string", "enum": ["high", "normal", "low"], "description": "Filter by priority"}
            },
            "required": []
        }
    },
    {
        "name": "update_task",
        "description": "Update a task's status, priority, due date, or notes by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID to update"},
                "fields":  {"type": "object", "description": "Fields to update: status, priority, due_date, notes, title, project"}
            },
            "required": ["task_id", "fields"]
        }
    },
    {
        "name": "complete_task",
        "description": "Mark a task as done.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID to mark complete"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "delete_task",
        "description": "Permanently delete a task by ID. Only use when Nate explicitly asks to remove a task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID to delete"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "add_inventory_item",
        "description": "Add a new item to Purple Horizon inventory. Use for games, cards, figures, comics, apparel, or shoes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["games", "cards", "figures", "comics", "apparel", "shoes"],
                    "description": "Inventory category"
                },
                "fields": {
                    "type": "object",
                    "description": "Item fields. games/comics: title, platform/publisher, condition, purchase_price, notes. cards: name, set_name, condition, grade, purchase_price. figures: name, brand, series, condition, purchase_price. apparel/shoes: name, brand, size, condition, purchase_price."
                }
            },
            "required": ["category", "fields"]
        }
    },
    {
        "name": "update_inventory_item",
        "description": "Update fields on an existing inventory item by ID and category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["games", "cards", "figures", "comics", "apparel", "shoes", "lrg_games"],
                    "description": "Inventory category"
                },
                "item_id": {"type": "integer", "description": "ID of the item to update"},
                "fields": {"type": "object", "description": "Fields to update and their new values"}
            },
            "required": ["category", "item_id", "fields"]
        }
    },
    {
        "name": "mark_item_sold",
        "description": "Mark an inventory item as sold. Updates status to sold and records the sale price and platform.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["games", "cards", "figures", "comics", "apparel", "shoes", "lrg_games"],
                    "description": "Inventory category"
                },
                "item_id": {"type": "integer", "description": "ID of the item that sold"},
                "sold_for": {"type": "number", "description": "Sale price in USD"},
                "sold_platform": {
                    "type": "string",
                    "enum": ["ebay", "mercari", "facebook", "reddit", "direct", "other"],
                    "description": "Platform where item was sold"
                }
            },
            "required": ["category", "item_id", "sold_for"]
        }
    },
    {
        "name": "remove_inventory_item",
        "description": "Permanently delete an inventory item by ID. Use with caution — this cannot be undone. Always confirm with Nate before removing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["games", "cards", "figures", "comics", "apparel", "shoes", "lrg_games"],
                    "description": "Inventory category"
                },
                "item_id": {"type": "integer", "description": "ID of the item to remove"}
            },
            "required": ["category", "item_id"]
        }
    },
    {
        "name": "generate_design",
        "description": (
            "Generate a functional 3D model using OpenSCAD. Use for tools, jigs, enclosures, brackets, "
            "alignment aids, or anything with precise measurements. Brexis writes the OpenSCAD code; "
            "this tool renders it to an STL file ready for slicing. Returns the local STL path and design ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Complete OpenSCAD source code for the design"
                },
                "design_id": {
                    "type": "string",
                    "description": "Optional short slug for the design folder, e.g. 'switch-jig-v1'. Auto-generated if omitted."
                },
                "description": {
                    "type": "string",
                    "description": "Plain-language description of what was designed and why — logged with the design."
                }
            },
            "required": ["code", "description"]
        }
    },
    {
        "name": "generate_artistic_model",
        "description": (
            "Generate an organic or artistic 3D model via Meshy AI text-to-3D. Use for figures, crests, "
            "characters, decorative pieces, emblems, or anything that can't be defined by measurements alone. "
            "Returns the local STL path, design ID, and thumbnail URL. Takes 2-4 minutes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed text description of the 3D model to generate"
                },
                "style": {
                    "type": "string",
                    "enum": ["realistic", "cartoon", "sculpture", "pbr"],
                    "description": "Visual style. Use 'sculpture' for crests/emblems, 'realistic' for functional artistic pieces."
                },
                "design_id": {
                    "type": "string",
                    "description": "Optional short slug for the design folder. Auto-generated if omitted."
                },
                "description": {
                    "type": "string",
                    "description": "Plain-language description of what was designed and why — logged with the design."
                }
            },
            "required": ["prompt", "description"]
        }
    },
    {
        "name": "send_to_printer",
        "description": (
            "Upload a sliced gcode file to the Flashforge AD5X and start the print. "
            "Call this after submit_slice_job has completed and returned a gcode path. "
            "Always confirm with Nate before calling this on a new design."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "gcode_path": {
                    "type": "string",
                    "description": "Local path to the .gcode file on the relay machine (returned by the slicer)"
                }
            },
            "required": ["gcode_path"]
        }
    },
    # ── Claude Code collaboration tools ──────────────────────────────────────
    {
        "name": "create_code_task",
        "description": (
            "Create a Claude Code task brief and log it. Use when Brexis is handing a build task to Claude Code. "
            "Small tasks auto-proceed. Medium tasks require a single word confirm from Nate. "
            "Major tasks require explicit approval with the full brief before handing off."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_name": {"type": "string", "description": "Short descriptive name for the task, e.g. 'Add print history to fabrication dashboard'"},
                "size": {
                    "type": "string",
                    "enum": ["small", "medium", "major"],
                    "description": "small: <50 lines, single file, no schema/deps. medium: 50-200 lines, multi-file. major: 200+ lines, new features, schema changes, or new deps."
                },
                "project": {
                    "type": "string",
                    "enum": ["switch-resale", "purple-horizon", "rocket-fuel", "apparel", "fabrication", "general"],
                    "description": "Which project this task belongs to"
                },
                "approved_by": {
                    "type": "string",
                    "enum": ["auto", "nate"],
                    "description": "auto for small tasks Brexis handles directly. nate when Nate has explicitly approved."
                },
                "brief": {"type": "string", "description": "The full task brief text in the standard Brexis brief format"},
                "notes": {"type": "string", "description": "Any additional Brexis notes not in the brief"}
            },
            "required": ["task_name", "size", "project", "brief"]
        }
    },
    {
        "name": "handoff_code_task",
        "description": "Mark a code task as handed off to Claude Code. Call this when you are actually sending the brief to Claude Code for execution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "The code task ID to mark as handed off"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "check_pipeline_task",
        "description": (
            "Check the status and completion report of a task on the Purple Horizon pipeline. "
            "Use the pipeline task_id returned by handoff_code_task's result (not the internal code_task id) "
            "-- they are different numbering. Call this when Nate asks about a handed-off task, or "
            "proactively after a handoff to check whether Claude Code has finished."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pipeline_task_id": {"type": "integer", "description": "The Purple Horizon pipeline task_id, from handoff_code_task's result text"}
            },
            "required": ["pipeline_task_id"]
        }
    },
    # ── Hunters Den ───────────────────────────────────────────────────────────
    {
        "name": "log_hunter_grail",
        "description": "Log a new grail found by a hunter in Purple Horizon. Net profit and payout are calculated automatically -- do not compute them yourself.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hunter": {"type": "string", "description": "Hunter's username, e.g. protonix"},
                "item_name": {"type": "string", "description": "What was found"},
                "tier": {"type": "string", "enum": ["common", "uncommon", "rare", "epic", "legendary"], "description": "Grail tier, set by Nate"},
                "buy_price": {"type": "number", "description": "What the hunter paid"},
                "sell_price": {"type": "number", "description": "What it sold for (or is expected to sell for)"},
                "platform": {"type": "string", "description": "Where it sold, e.g. eBay, Mercari -- affects fee calculation. Optional."}
            },
            "required": ["hunter", "item_name", "tier", "buy_price", "sell_price"]
        }
    },
    {
        "name": "mark_grail_paid",
        "description": "Mark a hunter's grail payout as paid in Purple Horizon.",
        "input_schema": {
            "type": "object",
            "properties": {
                "grail_id": {"type": "integer", "description": "The grail's id, from log_hunter_grail's result or list_hunter_grails"}
            },
            "required": ["grail_id"]
        }
    },
    {
        "name": "list_hunter_grails",
        "description": "List logged grails from Purple Horizon, optionally filtered by hunter or payout status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hunter": {"type": "string", "description": "Filter to one hunter's grails"},
                "status": {"type": "string", "enum": ["pending", "paid"], "description": "Filter by payout status"}
            },
            "required": []
        }
    },
    {
        "name": "post_hunter_quest",
        "description": "Create a new hunter quest in Purple Horizon. The bonus_type/bonus_value describe the advertised reward structure -- the actual payout is set explicitly when the quest closes, not computed from this.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "Quest name/type, e.g. 'Most Grails This Week'"},
                "bonus_type": {"type": "string", "enum": ["percentage", "flat", "multiplier"], "description": "How the advertised bonus is described"},
                "bonus_value": {"type": "number", "description": "The advertised bonus figure (e.g. 20 for 20%, or a flat dollar amount)"},
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"}
            },
            "required": ["type", "bonus_type", "bonus_value"]
        }
    },
    {
        "name": "close_hunter_quest",
        "description": "Close a hunter quest and record the winner and their bonus payout. bonus_payout is the actual dollar amount to pay -- decide it yourself or ask Nate, it is not auto-calculated from grail data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "quest_id": {"type": "integer", "description": "The quest's id"},
                "winner": {"type": "string", "description": "Winning hunter's username"},
                "bonus_payout": {"type": "number", "description": "The actual dollar amount to pay the winner"}
            },
            "required": ["quest_id", "winner", "bonus_payout"]
        }
    },
    {
        "name": "get_hunter_ledger",
        "description": "Get per-hunter payout totals from Purple Horizon (pending, paid, quest bonuses, total earned). Use for vault dispatches and payout questions.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_hunter_weekly_summary",
        "description": "Get the weekly leaderboard, total pending payouts, and top grail of the week from Purple Horizon -- for the weekly vault dispatch.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "review_code_output",
        "description": (
            "Log Brexis's review of Claude Code's output. Run the review checklist and record the outcome. "
            "Must be called before anything is considered done."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "The code task ID being reviewed"},
                "outcome": {
                    "type": "string",
                    "enum": ["approved", "revise", "escalate"],
                    "description": "approved: clean, ready to merge. revise: send back with notes. escalate: needs Nate's decision."
                },
                "files_changed": {"type": "string", "description": "Comma-separated list of files Claude Code changed"},
                "dependencies_added": {"type": "string", "description": "Any new packages added, or 'none'"},
                "completion_report": {"type": "string", "description": "Claude Code's completion report text"},
                "notes": {"type": "string", "description": "Brexis review notes — what passed, what needs fixing, or why escalating"}
            },
            "required": ["task_id", "outcome", "notes"]
        }
    },
    {
        "name": "list_code_tasks",
        "description": "List Claude Code tasks from the task log. Filter by status or project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["queued", "in-progress", "review", "completed", "cancelled"],
                    "description": "Filter by task status"
                },
                "project": {
                    "type": "string",
                    "enum": ["switch-resale", "purple-horizon", "rocket-fuel", "apparel", "fabrication", "general"],
                    "description": "Filter by project"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_contacts",
        "description": "Look up team contacts stored in Purple Horizon. Use to find email, role, or company info for personnel. Filter by name or role.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Partial name to search (case-insensitive)"},
                "role": {"type": "string", "description": "Role to filter by, e.g. CEO, COO"},
                "company": {"type": "string", "description": "Company to filter by"}
            },
            "required": []
        }
    },
    {
        "name": "list_designs",
        "description": "List 3D designs in the Brexis Design Library. Filter by category, status, or filament.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Filter by category, e.g. display, functional, prototype"},
                "status": {"type": "string", "description": "Filter by status: draft, proven, retired"},
                "filament": {"type": "string", "description": "Filter by filament type, e.g. PLA, PETG"}
            },
            "required": []
        }
    },
    {
        "name": "get_design",
        "description": "Get a specific design from the Design Library by its design_id slug (e.g. nes-cart-v2) or numeric id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "design_ref": {"type": "string", "description": "The design_id slug or numeric id"}
            },
            "required": ["design_ref"]
        }
    },
    {
        "name": "search_designs",
        "description": "Search designs by keyword in name or notes. Optionally filter by tags.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to search in name and notes"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tag filter list, e.g. ['nintendo', 'display']"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_design",
        "description": "Add a new design to the Design Library.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "design_id": {"type": "string", "description": "URL-safe slug, e.g. nes-cart-v4"},
                "version": {"type": "integer", "default": 1},
                "parent_id": {"type": "integer", "description": "id of the parent design (previous version)"},
                "category": {"type": "string", "description": "display, functional, prototype, art"},
                "filament": {"type": "string", "description": "PLA, PETG, TPU, PLA-CF, PETG-CF"},
                "stl_path": {"type": "string"},
                "gcode_path": {"type": "string"},
                "slicer_profile": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "string", "description": "draft, proven, retired"},
                "notes": {"type": "string"},
                "nate_feedback": {"type": "string"}
            },
            "required": ["name", "design_id"]
        }
    },
    {
        "name": "update_design",
        "description": "Update an existing design in the library. Use design_id slug or numeric id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "design_ref": {"type": "string", "description": "design_id slug or numeric id"},
                "name": {"type": "string"},
                "version": {"type": "integer"},
                "parent_id": {"type": "integer"},
                "category": {"type": "string"},
                "filament": {"type": "string"},
                "stl_path": {"type": "string"},
                "gcode_path": {"type": "string"},
                "slicer_profile": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "string"},
                "notes": {"type": "string"},
                "nate_feedback": {"type": "string"}
            },
            "required": ["design_ref"]
        }
    },
    {
        "name": "log_print",
        "description": "Append a print record to a design's history. Capture settings and outcome.",
        "input_schema": {
            "type": "object",
            "properties": {
                "design_ref": {"type": "string", "description": "design_id slug or numeric id"},
                "filament": {"type": "string"},
                "nozzle_temp": {"type": "integer"},
                "bed_temp": {"type": "integer"},
                "print_speed": {"type": "integer", "description": "mm/s"},
                "layer_height": {"type": "number", "description": "e.g. 0.15"},
                "infill": {"type": "integer", "description": "percentage 0-100"},
                "ironing": {"type": "boolean", "default": False},
                "top_solid_layers": {"type": "integer"},
                "outcome": {"type": "string", "description": "success, failed, partial", "default": "success"},
                "notes": {"type": "string"},
                "nate_feedback": {"type": "string"}
            },
            "required": ["design_ref", "outcome"]
        }
    },
    {
        "name": "get_design_history",
        "description": "Get the full print history for a design.",
        "input_schema": {
            "type": "object",
            "properties": {
                "design_ref": {"type": "string", "description": "design_id slug or numeric id"},
                "limit": {"type": "integer", "default": 50}
            },
            "required": ["design_ref"]
        }
    },
    {
        "name": "get_design_versions",
        "description": "Get the full version tree for a design — all ancestors and descendants from root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "design_ref": {"type": "string", "description": "design_id slug or numeric id — any version in the tree works"}
            },
            "required": ["design_ref"]
        }
    },
    {
        "name": "list_purchase_orders",
        "description": "List purchase orders. Filter by status, category, folder_id, or vendor.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status":    {"type": "string", "description": "to_be_purchased, ordered, received"},
                "category":  {"type": "string", "description": "filament, hardware, apparel, supplies, equipment, other"},
                "folder_id": {"type": "integer"},
                "vendor":    {"type": "string"},
                "date_from": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "date_to":   {"type": "string", "description": "ISO date YYYY-MM-DD"}
            },
            "required": []
        }
    },
    {
        "name": "get_purchase_order",
        "description": "Get a single purchase order by ID or PO number (e.g. PO-0001).",
        "input_schema": {
            "type": "object",
            "properties": {
                "po_ref": {"type": "string", "description": "Numeric id or PO number string"}
            },
            "required": ["po_ref"]
        }
    },
    {
        "name": "create_purchase_order",
        "description": "Create a new purchase order. PO number is auto-generated. total_cost is auto-calculated from items.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":     {"type": "string"},
                "vendor":    {"type": "string"},
                "category":  {"type": "string", "description": "filament, hardware, apparel, supplies, equipment, other"},
                "items":     {
                    "type": "array",
                    "description": "Line items",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":       {"type": "string"},
                            "qty":        {"type": "number"},
                            "unit_price": {"type": "number"},
                            "notes":      {"type": "string"}
                        },
                        "required": ["name", "qty", "unit_price"]
                    }
                },
                "status":    {"type": "string", "default": "to_be_purchased"},
                "folder_id": {"type": "integer"},
                "priority":  {"type": "string", "description": "high, normal, low", "default": "normal"},
                "notes":     {"type": "string"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "update_purchase_order",
        "description": "Update fields on an existing purchase order. Recalculates total_cost if items are changed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "po_ref":    {"type": "string", "description": "Numeric id or PO number"},
                "title":     {"type": "string"},
                "vendor":    {"type": "string"},
                "category":  {"type": "string"},
                "items":     {"type": "array"},
                "folder_id": {"type": "integer"},
                "priority":  {"type": "string"},
                "notes":     {"type": "string"}
            },
            "required": ["po_ref"]
        }
    },
    {
        "name": "update_po_status",
        "description": "Move a PO through the status progression: to_be_purchased → ordered → received. Timestamps ordered_at and received_at are set automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "po_ref": {"type": "string", "description": "Numeric id or PO number"},
                "status": {"type": "string", "description": "to_be_purchased, ordered, received"}
            },
            "required": ["po_ref", "status"]
        }
    },
    {
        "name": "search_purchase_orders",
        "description": "Search purchase orders by keyword across title, vendor, notes, and PO number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "list_folders",
        "description": "List all PO folders with their hierarchy (root folders and children).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "create_folder",
        "description": "Create a new PO folder, optionally nested under a parent folder.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":      {"type": "string"},
                "parent_id": {"type": "integer", "description": "Parent folder id for nesting"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "get_folder_orders",
        "description": "Get all purchase orders in a specific folder.",
        "input_schema": {
            "type": "object",
            "properties": {
                "folder_id": {"type": "integer"}
            },
            "required": ["folder_id"]
        }
    },
    {
        "name": "get_po_summary",
        "description": "Get operating expense summary — total spend and PO count broken down by status and category.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
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
    if name == "fetch_ebay_sold":
        import gateway
        r = gateway.fetch_ebay_sold(inputs["title"], inputs.get("platform", "Switch"))
        return (
            f"eBay sold listings for {inputs['title']} ({inputs.get('platform','Switch')}):\n"
            f"{r['search_url']}"
        )

    if name == "fetch_pricecharting":
        import gateway
        r = gateway.fetch_pricecharting(inputs["title"], inputs.get("platform", "Switch"))
        if not r["found"]:
            return f"PriceCharting lookup failed: {r['error']}"
        lines = [f"PriceCharting — {r['name']} ({r['platform']}):"]
        if r.get("loose"):  lines.append(f"- Loose: ${r['loose']}")
        if r.get("cib"):    lines.append(f"- CIB: ${r['cib']}")
        if r.get("sealed"): lines.append(f"- Sealed: ${r['sealed']}")
        if r.get("graded"): lines.append(f"- Graded: ${r['graded']}")
        lines.append(f"- Source: {r['url']}")
        return "\n".join(lines)

    if name == "fetch_tcgplayer":
        import gateway
        r = gateway.fetch_tcgplayer(inputs["card_name"], inputs.get("set_name", ""))
        if not r["found"]:
            return f"TCGPlayer lookup failed: {r['error']}"
        lines = [f"TCGPlayer — {r['name']} ({r.get('set','')})"]
        for sub, p in r.get("prices", {}).items():
            lines.append(f"- {sub}: Market ${p.get('market','N/A')} | Low ${p.get('low','N/A')} | High ${p.get('high','N/A')}")
        return "\n".join(lines)

    if name == "fetch_shipping_rates":
        import gateway
        r = gateway.fetch_shipping_rates(
            inputs["from_zip"], inputs["to_zip"], inputs["weight_oz"],
            inputs.get("length", 12), inputs.get("width", 9), inputs.get("height", 4)
        )
        if not r["found"]:
            return f"ShipEngine lookup failed: {r['error']}"
        lines = [f"Shipping rates ({inputs['from_zip']} → {inputs['to_zip']}, {inputs['weight_oz']}oz):"]
        for rate in r["rates"]:
            lines.append(f"- {rate['carrier']} {rate['service']}: ${rate['rate']} ({rate['days']} days)")
        return "\n".join(lines)

    if name == "send_email":
        print(f"[tools] send_email handler reached, inputs={inputs}", flush=True)
        import emailer
        subject = inputs.get("subject", "Message from Brexis")
        body = inputs.get("body", "")
        to_emails = inputs.get("to_emails")
        result = emailer.send_email(subject, body, to_emails=to_emails)
        if result["ok"]:
            recipients = ", ".join(result.get("recipients", []))
            return f"Email sent [{result.get('status_code')}] to: {recipients}"
        return f"Email failed: {result.get('error', 'unknown error')}"

    if name == "send_discord_message":
        import discord_bot
        channel = inputs.get("channel", "")
        message = inputs.get("message", "")
        pin = inputs.get("pin", False)
        result = discord_bot.post_message(channel, message, pin=pin)
        return result

    if name == "setup_discord_channels":
        import discord_bot
        result = discord_bot.setup_channels()
        return result

    if name == "create_discord_channel":
        import discord_bot
        result = discord_bot.create_channel(
            inputs["name"],
            category_name=inputs.get("category"),
            private=inputs.get("private", False)
        )
        return result

    if name == "get_task_history":
        limit = inputs.get("limit", 20)
        entries = db.get_task_log(limit)
        if not entries:
            return "No task history yet."
        lines = [f"[{e.get('created_at','')[:19]}] [{e.get('category','')}] {e.get('action','')} — {e.get('detail','')} ({e.get('status','')})" for e in entries]
        return "\n".join(lines)

    if name == "trigger_scheduled_job":
        import scheduler as sched
        job_id = inputs.get("job_id", "")
        ok = sched.trigger_job(job_id)
        return f"✓ Job '{job_id}' triggered." if ok else f"✗ Unknown job '{job_id}'."

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

    # ── 3D Printer tools ──────────────────────────────────────────────────────

    if name == "get_print_status":
        r = _call_relay("GET", "/printer/status")
        if "error" in r:
            db.log_task("printer", "get_status", r["error"], "failed")
            return f"Printer unreachable: {r['error']}"
        db.log_task("printer", "get_status", str(r.get("status", "")), "success")
        if not r.get("connected"):
            return f"Printer offline: {r.get('error', 'no connection')}"
        lines = ["AD5X Status:"]
        if r.get("status"):
            lines.append(f"- State: {r['status']}")
        if r.get("temps"):
            t = r["temps"]
            lines.append(f"- Nozzle: {t.get('current_nozzle', 'N/A')}°C / target {t.get('target_nozzle', 'N/A')}°C")
            lines.append(f"- Bed: {t.get('current_bed', 'N/A')}°C / target {t.get('target_bed', 'N/A')}°C")
        if r.get("machine"):
            m = r["machine"]
            if m.get("print_progress"):
                lines.append(f"- Progress: {m['print_progress']}%")
            if m.get("file_name"):
                lines.append(f"- File: {m['file_name']}")
        return "\n".join(lines)

    if name == "control_print":
        action = inputs["action"]
        r = _call_relay("POST", "/printer/control", {"action": action})
        if "error" in r:
            db.log_task("printer", f"control_{action}", r["error"], "failed")
            return f"Control failed ({action}): {r['error']}"
        db.log_task("printer", f"control_{action}", f"action={action}", "success")
        return f"✓ Print {action}d."

    if name == "set_temperatures":
        nozzle = inputs.get("nozzle")
        bed = inputs.get("bed")
        if nozzle and int(nozzle) > 300:
            return "Nozzle temp exceeds AD5X max of 300°C. Set it lower."
        r = _call_relay("POST", "/printer/temps", {"nozzle": nozzle, "bed": bed})
        if "error" in r:
            db.log_task("printer", "set_temps", r["error"], "failed")
            return f"Temperature set failed: {r['error']}"
        parts = []
        if nozzle: parts.append(f"nozzle → {nozzle}°C")
        if bed:    parts.append(f"bed → {bed}°C")
        db.log_task("printer", "set_temps", ", ".join(parts), "success")
        return f"✓ Temperatures set: {', '.join(parts)}."

    if name == "recommend_settings":
        filament = inputs.get("filament", "PLA")
        goal = inputs.get("goal", "balanced")
        matrix = _FILAMENT_MATRIX.get(filament)
        if not matrix:
            return f"No profile for filament '{filament}'. Options: {', '.join(_FILAMENT_MATRIX.keys())}"
        settings = matrix.get(goal)
        if not settings:
            return f"No '{goal}' goal for {filament}. Options: strength, balanced, fast"
        return (
            f"{filament} — {goal.title()} profile:\n"
            f"- Nozzle: {settings['nozzle']}°C\n"
            f"- Bed: {settings['bed']}°C\n"
            f"- Speed: {settings['speed_mm_s']} mm/s\n"
            f"- Layer height: {settings['layer_mm']} mm\n"
            f"- Infill: {settings['infill_pct']}% {settings['pattern']}\n"
            f"- Build volume max: 220×220×220mm"
        )

    if name == "get_slicer_profiles":
        r = _call_relay("GET", "/slicer/profiles")
        if "error" in r:
            return f"OrcaSlicer not reachable: {r['error']}"
        profiles = r if isinstance(r, list) else r.get("profiles", [])
        if not profiles:
            return "No slicer profiles found. Is the OrcaSlicer Docker container running?"
        return "Available slicer profiles:\n" + "\n".join(f"- {p}" for p in profiles)

    if name == "get_slicer_job_status":
        job_id = inputs["job_id"]
        r = _call_relay("GET", f"/slicer/jobs/{job_id}")
        if "error" in r:
            return f"Couldn't get job status: {r['error']}"
        status = r.get("status", "unknown")
        lines = [f"Slice job {job_id}: {status}"]
        if r.get("progress"):
            lines.append(f"- Progress: {r['progress']}%")
        if r.get("output"):
            lines.append(f"- Output: {r['output']}")
        if r.get("error"):
            lines.append(f"- Error: {r['error']}")
        return "\n".join(lines)

    if name == "web_search":
        import gateway
        query = inputs["query"]
        count = min(inputs.get("count", 5), 10)
        r = gateway.brave_search(query, count)
        if not r.get("found"):
            db.log_task("search", "web_search", f"FAILED: {r.get('error','')}", "failed")
            return f"Search failed: {r.get('error', 'unknown error')}"
        db.log_task("search", "web_search", query, "success")
        results = r.get("results", [])
        if not results:
            return f"No results found for: {query}"
        lines = [f"Search results for: {query}\n"]
        for i, res in enumerate(results, 1):
            lines.append(f"{i}. {res.get('title','')}")
            lines.append(f"   {res.get('url','')}")
            if res.get("description"):
                lines.append(f"   {res['description'][:200]}")
        return "\n".join(lines)

    if name == "etsy_search":
        import gateway
        query = inputs["query"]
        limit = min(inputs.get("limit", 10), 25)
        r = gateway.etsy_search(query, limit)
        if not r.get("found"):
            return f"Etsy search failed: {r.get('error', 'unknown error')}"
        db.log_task("etsy", "search", query, "success")
        lines = [f"Etsy listings for '{query}' ({r.get('count', 0)} total, showing {len(r['results'])}):\n"]
        for item in r["results"]:
            shop = f" | {item['shop']}" if item.get("shop") else ""
            lines.append(f"• {item['title']}")
            lines.append(f"  ${item['price']} {item['currency']}{shop}")
            lines.append(f"  {item['url']}")
        return "\n".join(lines)

    if name == "etsy_shop":
        import gateway
        shop_name = inputs["shop_name"]
        limit = min(inputs.get("limit", 10), 25)
        r = gateway.etsy_shop(shop_name, limit)
        if not r.get("found"):
            return f"Etsy shop lookup failed: {r.get('error', 'unknown error')}"
        db.log_task("etsy", "shop", shop_name, "success")
        lines = [f"Etsy shop: {r['shop_name']} ({r['total']} active listings, showing {len(r['listings'])}):\n"]
        for item in r["listings"]:
            lines.append(f"• {item['title']} — ${item['price']} {item['currency']}")
            lines.append(f"  {item['url']}")
        return "\n".join(lines)

    if name == "pinterest_search":
        import gateway
        query = inputs["query"]
        limit = min(inputs.get("limit", 10), 25)
        r = gateway.pinterest_search(query, limit)
        if not r.get("found"):
            return f"Pinterest search failed: {r.get('error', 'unknown error')}"
        db.log_task("pinterest", "search", query, "success")
        lines = [f"Pinterest pins for '{query}' ({len(r['results'])} results):\n"]
        for item in r["results"]:
            lines.append(f"• {item['title'] or '(no title)'}")
            if item.get("description"):
                lines.append(f"  {item['description'][:150]}")
            if item.get("link"):
                lines.append(f"  Link: {item['link']}")
            if item.get("image_url"):
                lines.append(f"  Image: {item['image_url']}")
        return "\n".join(lines)

    if name == "create_task":
        result = db.create_task(
            user_id,
            title=inputs["title"],
            project=inputs.get("project", "general"),
            priority=inputs.get("priority", "normal"),
            due_date=inputs.get("due_date"),
            notes=inputs.get("notes"),
        )
        if "error" in result:
            db.log_task("tasks", "create", result["error"], "failed")
            return f"Failed to create task: {result['error']}"
        db.log_task("tasks", "create", f"[{inputs.get('project','general')}] {inputs['title']}", "success")
        return f"✓ Task created (ID: {result['id']}): {inputs['title']}"

    if name == "list_tasks":
        tasks = db.get_tasks(
            user_id,
            project=inputs.get("project"),
            status=inputs.get("status"),
            priority=inputs.get("priority"),
        )
        if not tasks:
            return "No tasks found."
        from datetime import date
        today = date.today().isoformat()
        lines = []
        for t in tasks:
            due = t.get("due_date") or ""
            overdue = " ⚠ OVERDUE" if due and due < today and t.get("status") != "done" else ""
            lines.append(
                f"[{t['id']}] [{t.get('priority','normal').upper()}] [{t.get('project','')}] "
                f"{t['title']} — {t.get('status','open')}"
                + (f" | Due: {due}{overdue}" if due else "")
                + (f" | {t['notes']}" if t.get("notes") else "")
            )
        return f"Tasks ({len(tasks)}):\n" + "\n".join(lines)

    if name == "update_task":
        result = db.update_task(user_id, inputs["task_id"], inputs.get("fields", {}))
        if "error" in result:
            return f"Failed to update task: {result['error']}"
        if not result.get("updated"):
            return f"No task found with ID {inputs['task_id']}."
        db.log_task("tasks", "update", f"id={inputs['task_id']} fields={list(inputs.get('fields',{}).keys())}", "success")
        return f"✓ Task {inputs['task_id']} updated."

    if name == "complete_task":
        result = db.update_task(user_id, inputs["task_id"], {"status": "done"})
        if "error" in result:
            return f"Failed to complete task: {result['error']}"
        if not result.get("updated"):
            return f"No task found with ID {inputs['task_id']}."
        db.log_task("tasks", "complete", f"id={inputs['task_id']}", "success")
        return f"✓ Task {inputs['task_id']} marked done."

    if name == "delete_task":
        result = db.delete_task(user_id, inputs["task_id"])
        if "error" in result:
            return f"Failed to delete task: {result['error']}"
        if not result.get("deleted"):
            return f"No task found with ID {inputs['task_id']}."
        db.log_task("tasks", "delete", f"id={inputs['task_id']}", "success")
        return f"✓ Task {inputs['task_id']} deleted."

    if name == "add_inventory_item":
        category = inputs["category"]
        fields   = inputs.get("fields", {})
        result   = db.add_inventory_item(user_id, category, fields)
        if "error" in result:
            db.log_task("inventory", "add_item", result["error"], "failed")
            return f"Failed to add item: {result['error']}"
        name_val = fields.get("title") or fields.get("name") or "item"
        db.log_task("inventory", "add_item", f"[{category}] {name_val} → id={result['id']}", "success")
        return f"✓ Added '{name_val}' to {category} inventory (ID: {result['id']})."

    if name == "update_inventory_item":
        category = inputs["category"]
        item_id  = inputs["item_id"]
        fields   = inputs.get("fields", {})
        result   = db.update_inventory_item(user_id, category, item_id, fields)
        if "error" in result:
            db.log_task("inventory", "update_item", result["error"], "failed")
            return f"Failed to update item: {result['error']}"
        if not result.get("updated"):
            return f"No item found in {category} with ID {item_id}."
        db.log_task("inventory", "update_item", f"[{category}] id={item_id} fields={list(fields.keys())}", "success")
        return f"✓ Updated {category} item {item_id}."

    if name == "mark_item_sold":
        category      = inputs["category"]
        item_id       = inputs["item_id"]
        sold_for      = inputs["sold_for"]
        sold_platform = inputs.get("sold_platform")
        result = db.mark_item_sold(user_id, category, item_id, sold_for, sold_platform)
        if "error" in result:
            db.log_task("inventory", "mark_sold", result["error"], "failed")
            return f"Failed to mark as sold: {result['error']}"
        if not result.get("updated"):
            return f"No item found in {category} with ID {item_id}."
        platform_str = f" on {sold_platform}" if sold_platform else ""
        db.log_task("inventory", "mark_sold", f"[{category}] id={item_id} sold=${sold_for}{platform_str}", "success")
        return f"✓ Marked {category} item {item_id} as sold for ${sold_for:.2f}{platform_str}."

    if name == "remove_inventory_item":
        category = inputs["category"]
        item_id  = inputs["item_id"]
        result   = db.remove_inventory_item(user_id, category, item_id)
        if "error" in result:
            db.log_task("inventory", "remove_item", result["error"], "failed")
            return f"Failed to remove item: {result['error']}"
        if not result.get("deleted"):
            return f"No item found in {category} with ID {item_id}."
        db.log_task("inventory", "remove_item", f"[{category}] id={item_id}", "success")
        return f"✓ Removed {category} item {item_id} from inventory."

    if name == "generate_design":
        code        = inputs["code"]
        description = inputs.get("description", "")
        design_id   = inputs.get("design_id")
        payload = {"code": code}
        if design_id:
            payload["design_id"] = design_id
        r = _call_relay("POST", "/design/openscad", payload)
        if "error" in r:
            db.log_task("fabrication", "generate_design", r["error"], "failed")
            return f"Design generation failed: {r['error']}"
        db.log_task("fabrication", "generate_design", f"{description} → {r.get('stl_path','')}", "success")
        return (
            f"Design rendered successfully.\n"
            f"- Design ID: {r['design_id']}\n"
            f"- STL: {r['stl_path']}\n"
            f"- Size: {r.get('size_kb', '?')}KB\n"
            f"Ready to slice. Call submit_slice_job with model={r['stl_path']}"
        )

    if name == "generate_artistic_model":
        prompt      = inputs["prompt"]
        description = inputs.get("description", "")
        style       = inputs.get("style", "realistic")
        design_id   = inputs.get("design_id")
        payload = {"prompt": prompt, "style": style}
        if design_id:
            payload["design_id"] = design_id
        r = _call_relay("POST", "/design/meshy", payload)
        if "error" in r:
            db.log_task("fabrication", "generate_artistic", r["error"], "failed")
            return f"Artistic model generation failed: {r['error']}"
        db.log_task("fabrication", "generate_artistic", f"{description} → {r.get('stl_path','')}", "success")
        result = (
            f"Model generated successfully.\n"
            f"- Design ID: {r['design_id']}\n"
            f"- STL: {r.get('stl_path', 'N/A')}\n"
            f"- Size: {r.get('size_kb', '?')}KB\n"
        )
        if r.get("thumbnail"):
            result += f"- Preview: {r['thumbnail']}\n"
        if r.get("glb_url"):
            result += f"- GLB (viewable): {r['glb_url']}\n"
        if r.get("fbx_url"):
            result += f"- FBX: {r['fbx_url']}\n"
        if r.get("stl_path"):
            result += f"Ready to slice. Call submit_slice_job with model={r['stl_path']}"
        return result

    if name == "send_to_printer":
        import datetime
        gcode_path = inputs["gcode_path"]
        print(f"[tools] send_to_printer called with gcode_path={gcode_path!r}", flush=True)
        r = _call_relay("POST", "/printer/start", {"gcode_path": gcode_path})
        # Retry once if response came back empty or missing ok/error keys
        if not r.get("ok") and not r.get("error"):
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[tools] send_to_printer empty response at {ts} — retrying", flush=True)
            r = _call_relay("POST", "/printer/start", {"gcode_path": gcode_path})
            ts2 = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[tools] send_to_printer retry result at {ts2}: {r}", flush=True)
        if not r.get("ok"):
            error = r.get("error", "unknown error")
            db.log_task("fabrication", "send_to_printer", f"FAILED path={gcode_path}: {error}", "failed")
            return f"Failed to start print: {error}\n\nGcode path used: {gcode_path}"
        db.log_task("fabrication", "send_to_printer", f"Started: {r.get('filename','')} from {gcode_path}", "success")
        return f"Print started — {r.get('filename', gcode_path)} is now printing on the AD5X."

    if name == "create_code_task":
        result = db.create_code_task(
            task_name=inputs["task_name"],
            size=inputs["size"],
            project=inputs["project"],
            approved_by=inputs.get("approved_by", "auto"),
            brief=inputs.get("brief"),
            notes=inputs.get("notes"),
        )
        if "error" in result:
            db.log_task("code_tasks", "create", result["error"], "failed")
            return f"Failed to create code task: {result['error']}"
        task_id = result["id"]
        db.log_task("code_tasks", "create", f"TASK-{task_id:04d}: {inputs['task_name']} [{inputs['size']}]", "success")
        size = inputs["size"]
        if size == "small":
            return (
                f"Code task logged — TASK-{task_id:04d}.\n"
                f"Size: small — auto-approved, handing off to Claude Code now.\n\n"
                f"--- BREXIS TASK BRIEF — TASK-{task_id:04d} ---\n{inputs['brief']}"
            )
        elif size == "medium":
            return (
                f"Code task logged — TASK-{task_id:04d}.\n"
                f"Size: medium — needs your confirm before I hand it off.\n\n"
                f"{inputs['brief']}\n\nSay 'go' to hand this off to Claude Code."
            )
        else:
            return (
                f"Code task logged — TASK-{task_id:04d}.\n"
                f"Size: major — this needs your explicit sign-off.\n\n"
                f"--- TASK BRIEF ---\n{inputs['brief']}\n\n"
                f"Review the brief and approve before I engage Claude Code."
            )

    if name == "handoff_code_task":
        task_id = inputs["task_id"]
        result = db.update_code_task(task_id, {"status": "in-progress", "handed_off_at": "CURRENT_TIMESTAMP_PLACEHOLDER"})
        conn = db.get_db()
        try:
            cur = conn.cursor()
            p = db.ph()
            cur.execute(f"UPDATE code_tasks SET status={p}, handed_off_at=CURRENT_TIMESTAMP WHERE id={p}", ("in-progress", task_id))
            conn.commit()
            cur.execute(f"SELECT task_name, brief, size FROM code_tasks WHERE id={p}", (task_id,))
            task_row = db.row(cur.fetchone())
        finally:
            conn.close()
        db.log_task("code_tasks", "handoff", f"TASK-{task_id:04d} handed to Claude Code", "success")

        # Submit to the Purple Horizon pipeline so Claude Code can pick it up via /pipeline/queue.
        # Internal code_tasks logging above is unchanged — this is in addition to it, not instead of it.
        if task_row and task_row.get("brief"):
            import gateway
            pipe = gateway.submit_pipeline_task(task_row["task_name"], task_row["brief"], task_row["size"])
            if pipe.get("found"):
                db.log_task("code_tasks", "pipeline_submit",
                            f"TASK-{task_id:04d} -> pipeline task_id={pipe['task_id']} approved={pipe['approved']}", "success")
                return (
                    f"TASK-{task_id:04d} marked in-progress. Submitted to Purple Horizon pipeline as "
                    f"task_id={pipe['task_id']} (approved={pipe['approved']})."
                )
            else:
                db.log_task("code_tasks", "pipeline_submit",
                            f"TASK-{task_id:04d} pipeline submit failed: {pipe.get('error')}", "failed")
                return (
                    f"TASK-{task_id:04d} marked in-progress locally, but the Purple Horizon pipeline submit "
                    f"failed: {pipe.get('error')}. Claude Code will not see this via /pipeline/queue until "
                    f"this is resolved."
                )

        return f"TASK-{task_id:04d} marked in-progress. Brief sent to Claude Code."

    if name == "check_pipeline_task":
        pipeline_task_id = inputs["pipeline_task_id"]
        import gateway
        result = gateway.check_pipeline_task(pipeline_task_id)
        if not result.get("found"):
            db.log_task("code_tasks", "pipeline_check", f"pipeline task_id={pipeline_task_id} check failed: {result.get('error')}", "failed")
            return f"Could not check pipeline task_id={pipeline_task_id}: {result.get('error')}"

        db.log_task("code_tasks", "pipeline_check", f"pipeline task_id={pipeline_task_id} status={result.get('status')} outcome={result.get('outcome')}", "success")

        lines = [
            f"Pipeline task_id={pipeline_task_id} — {result.get('title')}",
            f"Status: {result.get('status')}" + (f" (outcome: {result.get('outcome')})" if result.get("outcome") else ""),
        ]
        if not result.get("approved"):
            lines.append("Not yet approved.")
        if result.get("budget_warning"):
            lines.append("WARNING: task is approaching its token budget.")
        if result.get("claude_response"):
            lines.append(f"Completion report: {result['claude_response']}")
        if result.get("error_reason"):
            lines.append(f"Error reason: {result['error_reason']}")
        return "\n".join(lines)

    if name == "log_hunter_grail":
        import gateway
        result = gateway.log_hunter_grail(
            inputs["hunter"], inputs["item_name"], inputs["tier"],
            inputs["buy_price"], inputs["sell_price"], inputs.get("platform"),
        )
        if not result.get("found"):
            db.log_task("hunters_den", "log_grail", f"failed: {result.get('error')}", "failed")
            return f"Could not log grail: {result.get('error')}"
        db.log_task("hunters_den", "log_grail", f"id={result['id']} hunter={inputs['hunter']} item={inputs['item_name']} tier={inputs['tier']}", "success")
        return (
            f"Grail logged — id={result['id']}: {inputs['item_name']} ({inputs['tier']}) for {inputs['hunter']}.\n"
            f"Net profit: ${result['net_profit']:.2f} | Payout: ${result['payout']:.2f} | Status: {result['status']}"
        )

    if name == "mark_grail_paid":
        import gateway
        grail_id = inputs["grail_id"]
        result = gateway.mark_grail_paid(grail_id)
        if not result.get("found"):
            db.log_task("hunters_den", "mark_paid", f"grail_id={grail_id} failed: {result.get('error')}", "failed")
            return f"Could not mark grail_id={grail_id} paid: {result.get('error')}"
        db.log_task("hunters_den", "mark_paid", f"grail_id={grail_id}", "success")
        return f"Grail id={grail_id} ({result.get('item_name')}) marked paid — ${result.get('payout', 0):.2f} to {result.get('hunter')}."

    if name == "list_hunter_grails":
        import gateway
        result = gateway.list_hunter_grails(hunter=inputs.get("hunter"), status=inputs.get("status"))
        if not result.get("found"):
            return f"Could not list grails: {result.get('error')}"
        grails = result.get("grails", [])
        if not grails:
            return "No grails found matching that filter."
        lines = [f"#{g['id']} {g['hunter']} — {g['item_name']} ({g['tier']}) — ${g['payout']:.2f} [{g['status']}]" for g in grails]
        return "\n".join(lines)

    if name == "post_hunter_quest":
        import gateway
        result = gateway.post_hunter_quest(
            inputs["type"], inputs["bonus_type"], inputs["bonus_value"],
            inputs.get("start_date"), inputs.get("end_date"),
        )
        if not result.get("found"):
            db.log_task("hunters_den", "post_quest", f"failed: {result.get('error')}", "failed")
            return f"Could not post quest: {result.get('error')}"
        db.log_task("hunters_den", "post_quest", f"id={result['id']} type={inputs['type']}", "success")
        return f"Quest posted — id={result['id']}: {inputs['type']} ({inputs['bonus_type']}: {inputs['bonus_value']})."

    if name == "close_hunter_quest":
        import gateway
        quest_id = inputs["quest_id"]
        result = gateway.close_hunter_quest(quest_id, inputs["winner"], inputs["bonus_payout"])
        if not result.get("found"):
            db.log_task("hunters_den", "close_quest", f"quest_id={quest_id} failed: {result.get('error')}", "failed")
            return f"Could not close quest_id={quest_id}: {result.get('error')}"
        db.log_task("hunters_den", "close_quest", f"quest_id={quest_id} winner={inputs['winner']} bonus={inputs['bonus_payout']}", "success")
        return f"Quest id={quest_id} closed — winner: {inputs['winner']}, bonus: ${inputs['bonus_payout']:.2f}."

    if name == "get_hunter_ledger":
        import gateway
        result = gateway.get_hunter_ledger()
        if not result.get("found"):
            return f"Could not get ledger: {result.get('error')}"
        ledger = result.get("ledger", [])
        if not ledger:
            return "No hunter activity logged yet."
        lines = [f"{h['hunter']}: earned ${h['total_earned']:.2f} (pending ${h['total_pending']:.2f}, paid ${h['total_paid']:.2f}, quest bonuses ${h['quest_bonuses']:.2f})" for h in ledger]
        return "\n".join(lines)

    if name == "get_hunter_weekly_summary":
        import gateway
        result = gateway.get_hunter_weekly_summary()
        if not result.get("found"):
            return f"Could not get weekly summary: {result.get('error')}"
        leaderboard = result.get("leaderboard", [])
        lines = ["Weekly leaderboard:"]
        lines += [f"  {i+1}. {h['hunter']} — ${h['net_profit']:.2f} net profit, {h['grail_count']} grails" for i, h in enumerate(leaderboard)]
        lines.append(f"Total payouts pending: ${result.get('total_payouts_pending', 0):.2f}")
        top = result.get("top_grail")
        if top:
            lines.append(f"Top grail of the week: {top['item_name']} ({top['hunter']}) — ${top['net_profit']:.2f} net profit")
        return "\n".join(lines)

    if name == "review_code_output":
        task_id  = inputs["task_id"]
        outcome  = inputs["outcome"]
        notes    = inputs["notes"]
        fields = {
            "review_outcome":    outcome,
            "notes":             notes,
            "completion_report": inputs.get("completion_report", ""),
            "files_changed":     inputs.get("files_changed", ""),
            "dependencies_added": inputs.get("dependencies_added", "none"),
        }
        if outcome == "approved":
            fields["status"] = "completed"
        elif outcome == "revise":
            conn = db.get_db()
            try:
                cur = conn.cursor()
                p = db.ph()
                cur.execute(f"UPDATE code_tasks SET revisions_count=revisions_count+1 WHERE id={p}", (task_id,))
                conn.commit()
            finally:
                conn.close()
            fields["status"] = "in-progress"
        else:
            fields["status"] = "review"
        db.update_code_task(task_id, fields)
        if outcome == "approved":
            conn = db.get_db()
            try:
                cur = conn.cursor()
                p = db.ph()
                cur.execute(f"UPDATE code_tasks SET completed_at=CURRENT_TIMESTAMP WHERE id={p}", (task_id,))
                conn.commit()
            finally:
                conn.close()
        db.log_task("code_tasks", "review", f"TASK-{task_id:04d} → {outcome}: {notes[:80]}", "success")
        if outcome == "approved":
            return f"TASK-{task_id:04d} approved. Clean output — ready to merge.\n\nReview notes: {notes}"
        elif outcome == "revise":
            return f"TASK-{task_id:04d} sent back for revision.\n\nWhat needs fixing:\n{notes}"
        else:
            return f"TASK-{task_id:04d} escalated to Nate.\n\nReason: {notes}"

    if name == "list_code_tasks":
        tasks = db.get_code_tasks(
            status=inputs.get("status"),
            project=inputs.get("project"),
        )
        if not tasks:
            return "No code tasks found."
        lines = []
        for t in tasks:
            outcome = f" | Review: {t['review_outcome']}" if t.get("review_outcome") else ""
            lines.append(
                f"[TASK-{t['id']:04d}] [{t['size'].upper()}] [{t['project']}] "
                f"{t['task_name']} — {t['status']}{outcome} | {t.get('created_at','')[:10]}"
            )
        return f"Code tasks ({len(tasks)}):\n" + "\n".join(lines)

    if name == "get_contacts":
        contacts = db.get_contacts(
            name=inputs.get("name"),
            role=inputs.get("role"),
            company=inputs.get("company"),
        )
        if not contacts:
            return "No contacts found matching those filters."
        lines = []
        for c in contacts:
            lines.append(f"{c['name']} — {c['role']} at {c['company']} | {c['email']}")
        return f"Team contacts ({len(contacts)}):\n" + "\n".join(lines)

    if name == "submit_slice_job":
        model    = inputs["model"]
        filament = inputs.get("filament", "PLA")
        goal     = inputs.get("goal", "balanced")
        supports = inputs.get("supports", False)
        payload  = {"model": model, "filament": filament, "goal": goal, "supports": supports}
        r = _call_relay("POST", "/slicer/slice", payload)
        if "error" in r:
            db.log_task("printer", "slice_job", r["error"], "failed")
            return f"Slice failed: {r['error']}"
        gcode = r.get("gcode_path", "")
        db.log_task("printer", "slice_job", f"model={model} filament={filament} goal={goal} → {gcode}", "success")
        return (
            f"Sliced successfully.\n"
            f"- Gcode: {gcode}\n"
            f"- Size: {r.get('size_kb', '?')}KB\n"
            f"- Filament: {filament} | Goal: {goal}\n"
            f"Ready to print. Call send_to_printer with gcode_path={gcode}"
        )

    # ── Purchase Orders ──
    if name == "list_purchase_orders":
        orders = db.list_purchase_orders(
            status=inputs.get("status"),
            category=inputs.get("category"),
            folder_id=inputs.get("folder_id"),
            vendor=inputs.get("vendor"),
            date_from=inputs.get("date_from"),
            date_to=inputs.get("date_to"),
        )
        if not orders:
            return "No purchase orders found matching those filters."
        lines = [
            f"[{o['po_number']}] {o['title']} | {o['vendor'] or 'no vendor'} | "
            f"{o['category']} | {o['status']} | ${o['total_cost']:.2f} | {o['priority']}"
            for o in orders
        ]
        return f"Purchase orders ({len(orders)}):\n" + "\n".join(lines)

    if name == "get_purchase_order":
        po = db.get_purchase_order(inputs["po_ref"])
        if not po:
            return f"PO not found: {inputs['po_ref']}"
        items = po.get("items") or []
        item_lines = "\n".join(
            f"  - {i.get('name','?')} x{i.get('qty',1)} @ ${i.get('unit_price',0):.2f}"
            + (f" ({i['notes']})" if i.get("notes") else "")
            for i in items
        )
        return (
            f"{po['po_number']} — {po['title']}\n"
            f"Vendor: {po.get('vendor') or 'none'} | Category: {po['category']} | "
            f"Status: {po['status']} | Priority: {po['priority']}\n"
            f"Total: ${po['total_cost']:.2f}\n"
            f"Items:\n{item_lines or '  (none)'}\n"
            f"Notes: {po.get('notes') or 'none'}\n"
            f"Created: {str(po.get('created_at',''))[:10]}"
            + (f" | Ordered: {str(po['ordered_at'])[:10]}" if po.get("ordered_at") else "")
            + (f" | Received: {str(po['received_at'])[:10]}" if po.get("received_at") else "")
        )

    if name == "create_purchase_order":
        result = db.create_purchase_order(
            title=inputs["title"],
            vendor=inputs.get("vendor"),
            category=inputs.get("category", "other"),
            items=inputs.get("items"),
            status=inputs.get("status", "to_be_purchased"),
            folder_id=inputs.get("folder_id"),
            priority=inputs.get("priority", "normal"),
            notes=inputs.get("notes"),
        )
        if "error" in result:
            return f"Failed to create PO: {result['error']}"
        db.log_task("purchase_orders", "create_po", f"{result['po_number']} created — {inputs['title']}", "success")
        return f"Created {result['po_number']} — {inputs['title']} | Total: ${result['total_cost']:.2f}"

    if name == "update_purchase_order":
        po_ref = inputs.pop("po_ref")
        result = db.update_purchase_order(po_ref, inputs)
        if "error" in result:
            return f"Update failed: {result['error']}"
        db.log_task("purchase_orders", "update_po", f"{po_ref} updated", "success")
        return f"PO {po_ref} updated."

    if name == "update_po_status":
        result = db.update_po_status(inputs["po_ref"], inputs["status"])
        if "error" in result:
            return f"Status update failed: {result['error']}"
        db.log_task("purchase_orders", "status_change", f"{inputs['po_ref']} → {inputs['status']}", "success")
        return f"{inputs['po_ref']} status set to {inputs['status']}."

    if name == "search_purchase_orders":
        orders = db.search_purchase_orders(inputs["query"])
        if not orders:
            return f"No POs found for: {inputs['query']}"
        lines = [f"[{o['po_number']}] {o['title']} | {o['vendor'] or '—'} | {o['status']} | ${o['total_cost']:.2f}" for o in orders]
        return f"Search results ({len(orders)}):\n" + "\n".join(lines)

    if name == "list_folders":
        folders = db.list_folders()
        if not folders:
            return "No folders found."
        roots = [f for f in folders if not f.get("parent_id")]
        children = [f for f in folders if f.get("parent_id")]
        lines = []
        for r in roots:
            lines.append(f"[{r['id']}] {r['name']}")
            for c in children:
                if c["parent_id"] == r["id"]:
                    lines.append(f"  └── [{c['id']}] {c['name']}")
        return "Folders:\n" + "\n".join(lines)

    if name == "create_folder":
        result = db.create_folder(inputs["name"], parent_id=inputs.get("parent_id"))
        if "error" in result:
            return f"Failed to create folder: {result['error']}"
        return f"Folder created: {inputs['name']} (id={result['id']})"

    if name == "get_folder_orders":
        orders = db.get_folder_orders(inputs["folder_id"])
        if not orders:
            return f"No orders in folder {inputs['folder_id']}."
        lines = [f"[{o['po_number']}] {o['title']} | {o['status']} | ${o['total_cost']:.2f}" for o in orders]
        return f"Orders in folder ({len(orders)}):\n" + "\n".join(lines)

    if name == "get_po_summary":
        summary = db.get_po_summary()
        if not summary:
            return "No purchase order data available."
        lines = ["Operating Expense Summary:"]
        for status, cats in summary.get("by_status_category", {}).items():
            status_total = summary["totals_by_status"].get(status, 0)
            lines.append(f"\n{status.upper()} — ${status_total:.2f} total")
            for cat, data in cats.items():
                lines.append(f"  {cat}: ${data['total']:.2f} ({data['count']} PO{'s' if data['count']!=1 else ''})")
        return "\n".join(lines)

    # ── Design Library ──
    if name == "list_designs":
        designs = db.list_designs(
            category=inputs.get("category"),
            status=inputs.get("status"),
            filament=inputs.get("filament"),
        )
        if not designs:
            return "No designs found matching those filters."
        lines = [f"[{d['design_id']}] v{d['version']} — {d['name']} | {d['status']} | {d['filament']} | tags: {', '.join(d.get('tags') or [])}" for d in designs]
        return f"Designs ({len(designs)}):\n" + "\n".join(lines)

    if name == "get_design":
        d = db.get_design(inputs["design_ref"])
        if not d:
            return f"Design not found: {inputs['design_ref']}"
        tags = ", ".join(d.get("tags") or [])
        return (
            f"Design: {d['name']} ({d['design_id']}) v{d['version']}\n"
            f"Status: {d['status']} | Category: {d['category']} | Filament: {d['filament']}\n"
            f"Tags: {tags}\n"
            f"STL: {d.get('stl_path') or 'none'}\n"
            f"Gcode: {d.get('gcode_path') or 'none'}\n"
            f"Notes: {d.get('notes') or 'none'}\n"
            f"Nate feedback: {d.get('nate_feedback') or 'none'}"
        )

    if name == "search_designs":
        results = db.search_designs(inputs["query"], tags=inputs.get("tags"))
        if not results:
            return f"No designs found for: {inputs['query']}"
        lines = [f"[{d['design_id']}] v{d['version']} — {d['name']} | {d['status']} | tags: {', '.join(d.get('tags') or [])}" for d in results]
        return f"Search results ({len(results)}):\n" + "\n".join(lines)

    if name == "create_design":
        result = db.create_design(
            name=inputs["name"],
            design_id=inputs["design_id"],
            version=inputs.get("version", 1),
            parent_id=inputs.get("parent_id"),
            category=inputs.get("category", "prototype"),
            filament=inputs.get("filament", "PLA"),
            stl_path=inputs.get("stl_path"),
            gcode_path=inputs.get("gcode_path"),
            slicer_profile=inputs.get("slicer_profile"),
            tags=inputs.get("tags"),
            status=inputs.get("status", "draft"),
            thumbnail_url=inputs.get("thumbnail_url"),
            notes=inputs.get("notes"),
            nate_feedback=inputs.get("nate_feedback"),
        )
        if "error" in result:
            return f"Failed to create design: {result['error']}"
        db.log_task("design_library", "create_design", f"{inputs['design_id']} created (id={result['id']})", "success")
        return f"Design created: {inputs['design_id']} (id={result['id']})"

    if name == "update_design":
        design_ref = inputs.pop("design_ref")
        result = db.update_design(design_ref, inputs)
        if "error" in result:
            return f"Update failed: {result['error']}"
        db.log_task("design_library", "update_design", f"{design_ref} updated", "success")
        return f"Design {design_ref} updated."

    if name == "log_print":
        result = db.add_print_record(
            design_id_or_slug=inputs["design_ref"],
            filament=inputs.get("filament"),
            nozzle_temp=inputs.get("nozzle_temp"),
            bed_temp=inputs.get("bed_temp"),
            print_speed=inputs.get("print_speed"),
            layer_height=inputs.get("layer_height"),
            infill=inputs.get("infill"),
            ironing=inputs.get("ironing", False),
            top_solid_layers=inputs.get("top_solid_layers"),
            outcome=inputs.get("outcome", "success"),
            notes=inputs.get("notes"),
            nate_feedback=inputs.get("nate_feedback"),
        )
        if "error" in result:
            return f"Failed to log print: {result['error']}"
        db.log_task("design_library", "log_print", f"{inputs['design_ref']} → {inputs.get('outcome','success')} (record id={result['id']})", "success")
        return f"Print record logged for {inputs['design_ref']} (id={result['id']}). Outcome: {inputs.get('outcome','success')}."

    if name == "get_design_history":
        history = db.get_design_history(inputs["design_ref"], limit=inputs.get("limit", 50))
        if not history:
            return f"No print history found for: {inputs['design_ref']}"
        lines = []
        for h in history:
            lines.append(
                f"[{h.get('printed_at','?')[:10]}] {h.get('outcome','?')} | "
                f"{h.get('filament','?')} {h.get('nozzle_temp','?')}°/{h.get('bed_temp','?')}° "
                f"layer={h.get('layer_height','?')} infill={h.get('infill','?')}% "
                f"speed={h.get('print_speed','?')}mm/s ironing={h.get('ironing',False)} "
                f"top={h.get('top_solid_layers','?')} | {h.get('nate_feedback') or h.get('notes') or ''}"
            )
        return f"Print history for {inputs['design_ref']} ({len(history)} records):\n" + "\n".join(lines)

    if name == "get_design_versions":
        versions = db.get_design_versions(inputs["design_ref"])
        if not versions:
            return f"No version tree found for: {inputs['design_ref']}"
        lines = [f"v{d['version']} — {d['design_id']} | {d['status']} | {d.get('nate_feedback') or d.get('notes') or 'no feedback'}" for d in versions]
        return f"Version tree ({len(versions)} versions):\n" + "\n".join(lines)

    return f"Unknown tool: {name}"
