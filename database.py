import os
import sqlite3


def _is_postgres(url):
    return url and (url.startswith("postgres://") or url.startswith("postgresql://"))


def _fix_pg_url(url):
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def get_db():
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    if _is_postgres(url):
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(_fix_pg_url(url))
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return conn
    db_path = url.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ph(url=None):
    url = url or os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    return "%s" if _is_postgres(url) else "?"


def row(r):
    return dict(r) if r else None


def get_config(key):
    conn = get_db()
    try:
        cur = conn.cursor()
        p = ph()
        try:
            cur.execute(f"SELECT value FROM brexis_config WHERE key={p}", (key,))
            row = cur.fetchone()
            return row["value"] if row else None
        except Exception:
            return None
    finally:
        conn.close()


def set_config(key, value):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        if pg:
            cur.execute(
                f"INSERT INTO brexis_config (key, value) VALUES ({p},{p}) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                (key, value)
            )
        else:
            cur.execute("INSERT OR REPLACE INTO brexis_config (key, value) VALUES (?,?)", (key, value))
        conn.commit()
    finally:
        conn.close()


def init_db():
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    auto = "SERIAL PRIMARY KEY" if pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"""CREATE TABLE IF NOT EXISTS chat_sessions (
            id         {auto},
            user_id    INTEGER NOT NULL,
            title      TEXT DEFAULT 'New Conversation',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute(f"""CREATE TABLE IF NOT EXISTS brexis_config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")
        cur.execute(f"""CREATE TABLE IF NOT EXISTS chat_messages (
            id         {auto},
            session_id INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute(f"""CREATE TABLE IF NOT EXISTS task_log (
            id         {auto},
            category   TEXT NOT NULL,
            action     TEXT NOT NULL,
            detail     TEXT,
            status     TEXT DEFAULT 'success',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        # ── Task tracking ──
        cur.execute(f"""CREATE TABLE IF NOT EXISTS tasks (
            id         {auto},
            user_id    INTEGER NOT NULL,
            title      TEXT NOT NULL,
            project    TEXT DEFAULT 'general',
            status     TEXT DEFAULT 'open',
            priority   TEXT DEFAULT 'normal',
            due_date   TEXT,
            notes      TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        # ── Inventory tables ──
        cur.execute(f"""CREATE TABLE IF NOT EXISTS games (
            id             {auto},
            user_id        INTEGER NOT NULL,
            title          TEXT NOT NULL,
            platform       TEXT,
            condition      TEXT DEFAULT 'Good',
            status         TEXT DEFAULT 'have',
            purchase_price REAL DEFAULT 0,
            sold_for       REAL,
            sold_platform  TEXT,
            notes          TEXT,
            added_at       TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute(f"""CREATE TABLE IF NOT EXISTS cards (
            id             {auto},
            user_id        INTEGER NOT NULL,
            name           TEXT NOT NULL,
            set_name       TEXT,
            condition      TEXT DEFAULT 'NM',
            grade          TEXT,
            status         TEXT DEFAULT 'have',
            purchase_price REAL DEFAULT 0,
            sold_for       REAL,
            sold_platform  TEXT,
            notes          TEXT,
            added_at       TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute(f"""CREATE TABLE IF NOT EXISTS figures (
            id             {auto},
            user_id        INTEGER NOT NULL,
            name           TEXT NOT NULL,
            brand          TEXT,
            series         TEXT,
            condition      TEXT DEFAULT 'Good',
            status         TEXT DEFAULT 'have',
            purchase_price REAL DEFAULT 0,
            sold_for       REAL,
            sold_platform  TEXT,
            notes          TEXT,
            added_at       TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute(f"""CREATE TABLE IF NOT EXISTS comics (
            id             {auto},
            user_id        INTEGER NOT NULL,
            title          TEXT NOT NULL,
            publisher      TEXT,
            issue          TEXT,
            condition      TEXT DEFAULT 'Good',
            status         TEXT DEFAULT 'have',
            purchase_price REAL DEFAULT 0,
            sold_for       REAL,
            sold_platform  TEXT,
            notes          TEXT,
            added_at       TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute(f"""CREATE TABLE IF NOT EXISTS apparel (
            id             {auto},
            user_id        INTEGER NOT NULL,
            name           TEXT NOT NULL,
            brand          TEXT,
            size           TEXT,
            condition      TEXT DEFAULT 'New',
            status         TEXT DEFAULT 'have',
            purchase_price REAL DEFAULT 0,
            sold_for       REAL,
            sold_platform  TEXT,
            notes          TEXT,
            added_at       TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute(f"""CREATE TABLE IF NOT EXISTS shoes (
            id             {auto},
            user_id        INTEGER NOT NULL,
            name           TEXT NOT NULL,
            brand          TEXT,
            size           TEXT,
            condition      TEXT DEFAULT 'New',
            status         TEXT DEFAULT 'have',
            purchase_price REAL DEFAULT 0,
            sold_for       REAL,
            sold_platform  TEXT,
            notes          TEXT,
            added_at       TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute(f"""CREATE TABLE IF NOT EXISTS lrg_games (
            id             {auto},
            user_id        INTEGER NOT NULL,
            title          TEXT NOT NULL,
            publisher      TEXT DEFAULT 'Limited Run Games',
            status         TEXT DEFAULT 'watching',
            buy_price      REAL DEFAULT 0,
            est_resale     REAL DEFAULT 0,
            sold_for       REAL,
            deadline       TEXT,
            notes          TEXT,
            added_at       TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        # ── Contacts ──
        cur.execute(f"""CREATE TABLE IF NOT EXISTS contacts (
            id         {auto},
            name       TEXT NOT NULL,
            email      TEXT NOT NULL,
            role       TEXT NOT NULL,
            company    TEXT NOT NULL DEFAULT 'Saturday Morning PJs',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        # Correct misspelled last name in existing records
        _ph = "%s" if pg else "?"
        cur.execute(f"UPDATE contacts SET name={_ph} WHERE name={_ph}", ("Nate Nagle", "Nate Nagel"))
        cur.execute(f"UPDATE contacts SET name={_ph} WHERE name={_ph}", ("Leanne Nagle", "Leanne Nagel"))
        # Seed core team if table is empty
        cur.execute("SELECT COUNT(*) AS cnt FROM contacts")
        row_ = cur.fetchone()
        if (row_["cnt"] if isinstance(row_, dict) else row_[0]) == 0:
            cur.execute(
                f"INSERT INTO contacts (name, email, role, company) VALUES ({_ph},{_ph},{_ph},{_ph})",
                ("Nate Nagle", "nate@saturdaymorningpjs.com", "COO", "Saturday Morning PJs")
            )
            cur.execute(
                f"INSERT INTO contacts (name, email, role, company) VALUES ({_ph},{_ph},{_ph},{_ph})",
                ("Leanne Nagle", "leanne@saturdaymorningpjs.com", "CEO", "Saturday Morning PJs")
            )
        # ── Design library ──
        if pg:
            cur.execute(f"""CREATE TABLE IF NOT EXISTS designs (
                id              SERIAL PRIMARY KEY,
                name            VARCHAR NOT NULL,
                design_id       VARCHAR UNIQUE NOT NULL,
                version         INTEGER NOT NULL DEFAULT 1,
                parent_id       INTEGER REFERENCES designs(id),
                category        VARCHAR NOT NULL DEFAULT 'prototype',
                filament        VARCHAR NOT NULL DEFAULT 'PLA',
                stl_path        VARCHAR,
                gcode_path      VARCHAR,
                slicer_profile  VARCHAR,
                tags            TEXT[] DEFAULT ARRAY[]::TEXT[],
                status          VARCHAR NOT NULL DEFAULT 'draft',
                thumbnail_url   VARCHAR,
                notes           TEXT,
                nate_feedback   TEXT,
                created_at      TIMESTAMP DEFAULT NOW(),
                updated_at      TIMESTAMP DEFAULT NOW()
            )""")
            cur.execute(f"""CREATE TABLE IF NOT EXISTS print_history (
                id               SERIAL PRIMARY KEY,
                design_id        INTEGER NOT NULL REFERENCES designs(id),
                printed_at       TIMESTAMP DEFAULT NOW(),
                filament         VARCHAR,
                nozzle_temp      INTEGER,
                bed_temp         INTEGER,
                print_speed      INTEGER,
                layer_height     DECIMAL(4,3),
                infill           INTEGER,
                ironing          BOOLEAN DEFAULT FALSE,
                top_solid_layers INTEGER,
                outcome          VARCHAR NOT NULL DEFAULT 'success',
                notes            TEXT,
                nate_feedback    TEXT
            )""")
        else:
            cur.execute(f"""CREATE TABLE IF NOT EXISTS designs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                design_id       TEXT UNIQUE NOT NULL,
                version         INTEGER NOT NULL DEFAULT 1,
                parent_id       INTEGER REFERENCES designs(id),
                category        TEXT NOT NULL DEFAULT 'prototype',
                filament        TEXT NOT NULL DEFAULT 'PLA',
                stl_path        TEXT,
                gcode_path      TEXT,
                slicer_profile  TEXT,
                tags            TEXT DEFAULT '[]',
                status          TEXT NOT NULL DEFAULT 'draft',
                thumbnail_url   TEXT,
                notes           TEXT,
                nate_feedback   TEXT,
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
            )""")
            cur.execute(f"""CREATE TABLE IF NOT EXISTS print_history (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                design_id        INTEGER NOT NULL REFERENCES designs(id),
                printed_at       TEXT DEFAULT CURRENT_TIMESTAMP,
                filament         TEXT,
                nozzle_temp      INTEGER,
                bed_temp         INTEGER,
                print_speed      INTEGER,
                layer_height     REAL,
                infill           INTEGER,
                ironing          INTEGER DEFAULT 0,
                top_solid_layers INTEGER,
                outcome          TEXT NOT NULL DEFAULT 'success',
                notes            TEXT,
                nate_feedback    TEXT
            )""")

        # Seed NES cartridge design history if designs table is empty
        cur.execute("SELECT COUNT(*) AS cnt FROM designs")
        r_ = cur.fetchone()
        if (r_["cnt"] if isinstance(r_, dict) else r_[0]) == 0:
            _ph = "%s" if pg else "?"
            stl_base = "C:/Users/nnagl/Claude/Projects/Saturday Morning PJs/brexis-relay/designs"
            _tags_v1 = "{nintendo,nes,cartridge,miniature,display}" if pg else '["nintendo","nes","cartridge","miniature","display"]'

            # v1
            if pg:
                cur.execute(
                    f"INSERT INTO designs (name,design_id,version,category,filament,stl_path,gcode_path,tags,status,nate_feedback) "
                    f"VALUES ({_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph}::text[],{_ph},{_ph}) RETURNING id",
                    ("NES Cartridge Mini","nes-cart-v1",1,"display","PLA",
                     f"{stl_base}/nes-cart-mini-v1/design.stl",
                     f"{stl_base}/nes-cart-mini-v1/design.gcode",
                     _tags_v1,"proven",
                     "Sides perfect. Bottom dark/burnt. Top surface rough.")
                )
                v1_id = cur.fetchone()["id"]
                cur.execute(
                    f"INSERT INTO designs (name,design_id,version,parent_id,category,filament,stl_path,gcode_path,tags,status,nate_feedback) "
                    f"VALUES ({_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph}::text[],{_ph},{_ph}) RETURNING id",
                    ("NES Cartridge Mini","nes-cart-v2",2,v1_id,"display","PLA",
                     f"{stl_base}/nes-cart-v2/design.stl",
                     f"{stl_base}/nes-cart-v2/design.gcode",
                     _tags_v1,"proven",
                     "Edges perfect. Bottom fixed. Top still showing layer lines.")
                )
                v2_id = cur.fetchone()["id"]
                cur.execute(
                    f"INSERT INTO designs (name,design_id,version,parent_id,category,filament,stl_path,gcode_path,tags,status,nate_feedback) "
                    f"VALUES ({_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph}::text[],{_ph},{_ph}) RETURNING id",
                    ("NES Cartridge Mini","nes-cart-v3",3,v2_id,"display","PLA",
                     f"{stl_base}/nes-cart-v2/design.stl",
                     f"{stl_base}/nes-cart-v2/design.gcode",
                     _tags_v1,"draft",
                     "Pending — currently printing.")
                )
                v3_id = cur.fetchone()["id"]
            else:
                cur.execute(
                    "INSERT INTO designs (name,design_id,version,category,filament,stl_path,gcode_path,tags,status,nate_feedback) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ("NES Cartridge Mini","nes-cart-v1",1,"display","PLA",
                     f"{stl_base}/nes-cart-mini-v1/design.stl",
                     f"{stl_base}/nes-cart-mini-v1/design.gcode",
                     _tags_v1,"proven",
                     "Sides perfect. Bottom dark/burnt. Top surface rough.")
                )
                v1_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO designs (name,design_id,version,parent_id,category,filament,stl_path,gcode_path,tags,status,nate_feedback) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    ("NES Cartridge Mini","nes-cart-v2",2,v1_id,"display","PLA",
                     f"{stl_base}/nes-cart-v2/design.stl",
                     f"{stl_base}/nes-cart-v2/design.gcode",
                     _tags_v1,"proven",
                     "Edges perfect. Bottom fixed. Top still showing layer lines.")
                )
                v2_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO designs (name,design_id,version,parent_id,category,filament,stl_path,gcode_path,tags,status,nate_feedback) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    ("NES Cartridge Mini","nes-cart-v3",3,v2_id,"display","PLA",
                     f"{stl_base}/nes-cart-v2/design.stl",
                     f"{stl_base}/nes-cart-v2/design.gcode",
                     _tags_v1,"draft",
                     "Pending — currently printing.")
                )
                v3_id = cur.lastrowid

            # Seed print history
            _ph = "%s" if pg else "?"
            cur.execute(
                f"INSERT INTO print_history (design_id,filament,nozzle_temp,bed_temp,print_speed,layer_height,infill,ironing,top_solid_layers,outcome,nate_feedback) "
                f"VALUES ({_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph})",
                (v1_id,"PLA",200,60,67,0.20,15,False,3,"success","Sides perfect. Bottom dark/burnt. Top surface rough.")
            )
            cur.execute(
                f"INSERT INTO print_history (design_id,filament,nozzle_temp,bed_temp,print_speed,layer_height,infill,ironing,top_solid_layers,outcome,nate_feedback) "
                f"VALUES ({_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph})",
                (v2_id,"PLA",205,50,40,0.15,20,False,5,"success","Edges perfect. Bottom fixed. Top still showing layer lines.")
            )
            cur.execute(
                f"INSERT INTO print_history (design_id,filament,nozzle_temp,bed_temp,print_speed,layer_height,infill,ironing,top_solid_layers,outcome,notes) "
                f"VALUES ({_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph},{_ph})",
                (v3_id,"PLA",205,50,40,0.15,25,True,7,"success","In progress at time of seed.")
            )

        # ── Purchase Orders ──
        if pg:
            cur.execute(f"""CREATE TABLE IF NOT EXISTS folders (
                id         SERIAL PRIMARY KEY,
                name       VARCHAR NOT NULL,
                parent_id  INTEGER REFERENCES folders(id),
                created_at TIMESTAMP DEFAULT NOW()
            )""")
            cur.execute(f"""CREATE TABLE IF NOT EXISTS purchase_orders (
                id          SERIAL PRIMARY KEY,
                po_number   VARCHAR UNIQUE NOT NULL,
                title       VARCHAR NOT NULL,
                vendor      VARCHAR,
                category    VARCHAR NOT NULL DEFAULT 'other',
                items       JSONB DEFAULT '[]'::JSONB,
                total_cost  DECIMAL(10,2) DEFAULT 0,
                status      VARCHAR NOT NULL DEFAULT 'to_be_purchased',
                folder_id   INTEGER REFERENCES folders(id),
                priority    VARCHAR NOT NULL DEFAULT 'normal',
                notes       TEXT,
                ordered_at  TIMESTAMP,
                received_at TIMESTAMP,
                created_at  TIMESTAMP DEFAULT NOW(),
                updated_at  TIMESTAMP DEFAULT NOW()
            )""")
        else:
            cur.execute(f"""CREATE TABLE IF NOT EXISTS folders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                parent_id  INTEGER REFERENCES folders(id),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""")
            cur.execute(f"""CREATE TABLE IF NOT EXISTS purchase_orders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                po_number   TEXT UNIQUE NOT NULL,
                title       TEXT NOT NULL,
                vendor      TEXT,
                category    TEXT NOT NULL DEFAULT 'other',
                items       TEXT DEFAULT '[]',
                total_cost  REAL DEFAULT 0,
                status      TEXT NOT NULL DEFAULT 'to_be_purchased',
                folder_id   INTEGER REFERENCES folders(id),
                priority    TEXT NOT NULL DEFAULT 'normal',
                notes       TEXT,
                ordered_at  TEXT,
                received_at TEXT,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )""")

        # Seed default folders + PO-0001 if folders table is empty
        cur.execute("SELECT COUNT(*) AS cnt FROM folders")
        r_ = cur.fetchone()
        if (r_["cnt"] if isinstance(r_, dict) else r_[0]) == 0:
            _ph = "%s" if pg else "?"
            if pg:
                cur.execute(
                    f"INSERT INTO folders (name, parent_id) VALUES ({_ph},{_ph}) RETURNING id",
                    ("Saturday Morning PJs Operating Expenses", None)
                )
                root_id = cur.fetchone()["id"]
                cur.execute(
                    f"INSERT INTO folders (name, parent_id) VALUES ({_ph},{_ph}) RETURNING id",
                    ("To Be Purchased", root_id)
                )
                tbp_id = cur.fetchone()["id"]
                cur.execute(
                    f"INSERT INTO folders (name, parent_id) VALUES ({_ph},{_ph})",
                    ("Ordered", root_id)
                )
                cur.execute(
                    f"INSERT INTO folders (name, parent_id) VALUES ({_ph},{_ph})",
                    ("Received", root_id)
                )
            else:
                cur.execute("INSERT INTO folders (name, parent_id) VALUES (?,?)",
                            ("Saturday Morning PJs Operating Expenses", None))
                root_id = cur.lastrowid
                cur.execute("INSERT INTO folders (name, parent_id) VALUES (?,?)",
                            ("To Be Purchased", root_id))
                tbp_id = cur.lastrowid
                cur.execute("INSERT INTO folders (name, parent_id) VALUES (?,?)",
                            ("Ordered", root_id))
                cur.execute("INSERT INTO folders (name, parent_id) VALUES (?,?)",
                            ("Received", root_id))

            # Seed PO-0001
            import json as _j
            items_seed = _j.dumps([
                {"name": "Hatchbox PETG Light Gray 1kg", "qty": 1, "unit_price": 24.99, "notes": "NES body color"},
                {"name": "eSUN PETG Solid Black 1kg",    "qty": 1, "unit_price": 21.99, "notes": "Accent/trim"},
                {"name": "Hatchbox PETG Red 1kg",        "qty": 1, "unit_price": 24.99, "notes": "NES logo match"},
            ])
            po_notes = (
                "NES color match set for cartridge earring production run. "
                "Gray = NES body (Hatchbox), Black = accent/trim (eSUN), "
                "Red = NES logo match (Hatchbox). Prototype run in PLA first — "
                "order after prototype approved."
            )
            if pg:
                cur.execute(
                    f"INSERT INTO purchase_orders "
                    f"(po_number,title,vendor,category,items,total_cost,status,folder_id,priority,notes) "
                    f"VALUES ({_ph},{_ph},{_ph},{_ph},{_ph}::jsonb,{_ph},{_ph},{_ph},{_ph},{_ph})",
                    ("PO-0001","PETG Filament — NES Color Set","Amazon","filament",
                     items_seed,71.97,"to_be_purchased",tbp_id,"normal",po_notes)
                )
            else:
                cur.execute(
                    "INSERT INTO purchase_orders "
                    "(po_number,title,vendor,category,items,total_cost,status,folder_id,priority,notes) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ("PO-0001","PETG Filament — NES Color Set","Amazon","filament",
                     items_seed,71.97,"to_be_purchased",tbp_id,"normal",po_notes)
                )

        # ── Claude Code task log ──
        cur.execute(f"""CREATE TABLE IF NOT EXISTS code_tasks (
            id                {auto},
            task_name         TEXT NOT NULL,
            size              TEXT NOT NULL DEFAULT 'small',
            project           TEXT NOT NULL DEFAULT 'general',
            status            TEXT NOT NULL DEFAULT 'queued',
            approved_by       TEXT NOT NULL DEFAULT 'auto',
            approved_at       TEXT,
            handed_off_at     TEXT,
            completed_at      TEXT,
            review_outcome    TEXT,
            revisions_count   INTEGER DEFAULT 0,
            files_changed     TEXT,
            dependencies_added TEXT,
            notes             TEXT,
            brief             TEXT,
            completion_report TEXT,
            created_at        TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()
    finally:
        conn.close()


def log_task(category, action, detail="", status="success"):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO task_log (category, action, detail, status) VALUES ({p},{p},{p},{p})",
            (category, action, detail, status)
        )
        conn.commit()
    except Exception as e:
        pass
    finally:
        conn.close()


def get_task_log(limit=50):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM task_log ORDER BY created_at DESC LIMIT %s" % limit if _is_postgres(os.environ.get("DATABASE_URL","")) else f"SELECT * FROM task_log ORDER BY created_at DESC LIMIT {limit}")
        return [row(r) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


# ── Sessions ──

def get_sessions(user_id):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM chat_sessions WHERE user_id={p} ORDER BY updated_at DESC LIMIT 50", (user_id,))
        return [row(r) for r in cur.fetchall()]
    finally:
        conn.close()


def create_session(user_id):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        if pg:
            cur.execute(f"INSERT INTO chat_sessions (user_id, title) VALUES ({p},{p}) RETURNING id", (user_id, "New Conversation"))
            new_id = cur.fetchone()["id"]
            conn.commit()
            return new_id
        cur.execute(f"INSERT INTO chat_sessions (user_id, title) VALUES ({p},{p})", (user_id, "New Conversation"))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_session(user_id, session_id):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM chat_sessions WHERE id={p} AND user_id={p}", (session_id, user_id))
        return row(cur.fetchone())
    finally:
        conn.close()


def update_session_title(user_id, session_id, title):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE chat_sessions SET title={p}, updated_at=CURRENT_TIMESTAMP WHERE id={p} AND user_id={p}", (title, session_id, user_id))
        conn.commit()
    finally:
        conn.close()


def touch_session(user_id, session_id):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE chat_sessions SET updated_at=CURRENT_TIMESTAMP WHERE id={p} AND user_id={p}", (session_id, user_id))
        conn.commit()
    finally:
        conn.close()


def delete_session(user_id, session_id):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM chat_messages WHERE session_id={p} AND user_id={p}", (session_id, user_id))
        cur.execute(f"DELETE FROM chat_sessions WHERE id={p} AND user_id={p}", (session_id, user_id))
        conn.commit()
    finally:
        conn.close()


# ── Messages ──

def get_messages(user_id, session_id):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM chat_messages WHERE session_id={p} AND user_id={p} ORDER BY created_at ASC", (session_id, user_id))
        return [row(r) for r in cur.fetchall()]
    finally:
        conn.close()


def save_message(user_id, session_id, role, content):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"INSERT INTO chat_messages (session_id, user_id, role, content) VALUES ({p},{p},{p},{p})", (session_id, user_id, role, content))
        conn.commit()
    finally:
        conn.close()
    touch_session(user_id, session_id)


# ── Inventory reads (Phase 2 tools) ──

def get_inventory_summary(user_id):
    p = ph()
    conn = get_db()
    summary = {}
    try:
        cur = conn.cursor()
        for table in ["games", "cards", "figures", "comics", "apparel", "shoes", "lrg_games"]:
            try:
                cur.execute(f"SELECT COUNT(*) as cnt FROM {table} WHERE user_id={p}", (user_id,))
                r = cur.fetchone()
                summary[table] = r["cnt"] if r else 0
            except Exception:
                summary[table] = 0
    finally:
        conn.close()
    return summary


def get_lrg_games(user_id, status=None):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        q = f"SELECT * FROM lrg_games WHERE user_id={p}"
        params = [user_id]
        if status:
            q += f" AND status={p}"
            params.append(status)
        q += " ORDER BY added_at DESC"
        cur.execute(q, params)
        return [row(r) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def search_inventory(user_id, query):
    p = ph()
    conn = get_db()
    results = []
    like = f"%{query}%"
    searches = [
        ("games",   "title",  "platform"),
        ("cards",   "name",   "set_name"),
        ("figures", "name",   "brand"),
        ("comics",  "title",  "publisher"),
        ("apparel", "name",   "brand"),
        ("shoes",   "name",   "brand"),
        ("lrg_games","title", "publisher"),
    ]
    try:
        cur = conn.cursor()
        for table, name_col, sub_col in searches:
            try:
                cur.execute(
                    f"SELECT *, '{table}' as category, {name_col} as display_name, {sub_col} as display_sub "
                    f"FROM {table} WHERE user_id={p} AND ({name_col} LIKE {p} OR {sub_col} LIKE {p}) LIMIT 5",
                    (user_id, like, like)
                )
                results.extend([row(r) for r in cur.fetchall()])
            except Exception:
                pass
    finally:
        conn.close()
    return results


# ── Task tracking ────────────────────────────────────────────────────────────

def create_task(user_id, title, project="general", priority="normal", due_date=None, notes=None):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        if pg:
            cur.execute(
                f"INSERT INTO tasks (user_id, title, project, priority, due_date, notes) VALUES ({p},{p},{p},{p},{p},{p}) RETURNING id",
                (user_id, title, project, priority, due_date, notes)
            )
            new_id = cur.fetchone()["id"]
            conn.commit()
            return {"id": new_id}
        cur.execute(
            f"INSERT INTO tasks (user_id, title, project, priority, due_date, notes) VALUES ({p},{p},{p},{p},{p},{p})",
            (user_id, title, project, priority, due_date, notes)
        )
        conn.commit()
        return {"id": cur.lastrowid}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def get_tasks(user_id, project=None, status=None, priority=None):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        q = f"SELECT * FROM tasks WHERE user_id={p}"
        params = [user_id]
        if project:
            q += f" AND project={p}"; params.append(project)
        if status:
            q += f" AND status={p}"; params.append(status)
        if priority:
            q += f" AND priority={p}"; params.append(priority)
        q += " ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'normal' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, due_date ASC NULLS LAST, created_at ASC"
        cur.execute(q, params)
        return [row(r) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def update_task(user_id, task_id, fields):
    allowed = {"title", "project", "status", "priority", "due_date", "notes"}
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return {"error": "No valid fields to update."}
    clean["updated_at"] = "CURRENT_TIMESTAMP"
    p = ph()
    set_clause = ", ".join(f"{k}={'CURRENT_TIMESTAMP' if v == 'CURRENT_TIMESTAMP' else p}" for k, v in clean.items())
    values = [v for v in clean.values() if v != "CURRENT_TIMESTAMP"] + [task_id, user_id]
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE tasks SET {set_clause} WHERE id={p} AND user_id={p}", values)
        conn.commit()
        return {"updated": cur.rowcount > 0}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def delete_task(user_id, task_id):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM tasks WHERE id={p} AND user_id={p}", (task_id, user_id))
        conn.commit()
        return {"deleted": cur.rowcount > 0}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


# ── Inventory writes ──────────────────────────────────────────────────────────

_INVENTORY_TABLES = {"games", "cards", "figures", "comics", "apparel", "shoes"}

_ALLOWED_FIELDS = {
    "games":   {"title", "platform", "condition", "status", "purchase_price", "sold_for", "sold_platform", "notes"},
    "cards":   {"name", "set_name", "condition", "grade", "status", "purchase_price", "sold_for", "sold_platform", "notes"},
    "figures": {"name", "brand", "series", "condition", "status", "purchase_price", "sold_for", "sold_platform", "notes"},
    "comics":  {"title", "publisher", "issue", "condition", "status", "purchase_price", "sold_for", "sold_platform", "notes"},
    "apparel": {"name", "brand", "size", "condition", "status", "purchase_price", "sold_for", "sold_platform", "notes"},
    "shoes":   {"name", "brand", "size", "condition", "status", "purchase_price", "sold_for", "sold_platform", "notes"},
}


def add_inventory_item(user_id, category, fields):
    if category not in _INVENTORY_TABLES:
        return {"error": f"Unknown category '{category}'. Options: {', '.join(_INVENTORY_TABLES)}"}
    allowed = _ALLOWED_FIELDS[category]
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return {"error": "No valid fields provided."}
    clean["user_id"] = user_id
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    cols = ", ".join(clean.keys())
    placeholders = ", ".join([p] * len(clean))
    conn = get_db()
    try:
        cur = conn.cursor()
        if pg:
            cur.execute(f"INSERT INTO {category} ({cols}) VALUES ({placeholders}) RETURNING id", list(clean.values()))
            new_id = cur.fetchone()["id"]
            conn.commit()
            return {"id": new_id}
        cur.execute(f"INSERT INTO {category} ({cols}) VALUES ({placeholders})", list(clean.values()))
        conn.commit()
        return {"id": cur.lastrowid}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def update_inventory_item(user_id, category, item_id, fields):
    if category not in _INVENTORY_TABLES:
        return {"error": f"Unknown category '{category}'."}
    allowed = _ALLOWED_FIELDS[category]
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return {"error": "No valid fields to update."}
    p = ph()
    set_clause = ", ".join(f"{k}={p}" for k in clean.keys())
    values = list(clean.values()) + [item_id, user_id]
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE {category} SET {set_clause} WHERE id={p} AND user_id={p}", values)
        conn.commit()
        return {"updated": cur.rowcount > 0}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def mark_item_sold(user_id, category, item_id, sold_for, sold_platform=None):
    if category == "lrg_games":
        fields = {"status": "sold", "sold_for": sold_for}
    elif category in _INVENTORY_TABLES:
        fields = {"status": "sold", "sold_for": sold_for}
        if sold_platform:
            fields["sold_platform"] = sold_platform
    else:
        return {"error": f"Unknown category '{category}'."}
    return update_inventory_item(user_id, category, item_id, fields) if category != "lrg_games" else _mark_lrg_sold(user_id, item_id, sold_for, sold_platform)


def _mark_lrg_sold(user_id, item_id, sold_for, sold_platform=None):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE lrg_games SET status={p}, sold_for={p} WHERE id={p} AND user_id={p}",
            ("sold", sold_for, item_id, user_id)
        )
        conn.commit()
        return {"updated": cur.rowcount > 0}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def remove_inventory_item(user_id, category, item_id):
    if category not in _INVENTORY_TABLES and category != "lrg_games":
        return {"error": f"Unknown category '{category}'."}
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {category} WHERE id={p} AND user_id={p}", (item_id, user_id))
        conn.commit()
        return {"deleted": cur.rowcount > 0}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


# ── Claude Code task log ─────────────────────────────────────────────────────

def create_code_task(task_name, size, project, approved_by="auto", brief=None, notes=None):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        if pg:
            cur.execute(
                f"INSERT INTO code_tasks (task_name, size, project, approved_by, brief, notes, approved_at) "
                f"VALUES ({p},{p},{p},{p},{p},{p},CURRENT_TIMESTAMP) RETURNING id",
                (task_name, size, project, approved_by, brief, notes)
            )
            new_id = cur.fetchone()["id"]
            conn.commit()
            return {"id": new_id}
        cur.execute(
            f"INSERT INTO code_tasks (task_name, size, project, approved_by, brief, notes, approved_at) "
            f"VALUES ({p},{p},{p},{p},{p},{p},CURRENT_TIMESTAMP)",
            (task_name, size, project, approved_by, brief, notes)
        )
        conn.commit()
        return {"id": cur.lastrowid}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def update_code_task(task_id, fields):
    allowed = {
        "status", "handed_off_at", "completed_at", "review_outcome",
        "revisions_count", "files_changed", "dependencies_added",
        "notes", "completion_report"
    }
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return {"error": "No valid fields to update."}
    p = ph()
    set_clause = ", ".join(f"{k}={p}" for k in clean.keys())
    values = list(clean.values()) + [task_id]
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE code_tasks SET {set_clause} WHERE id={p}", values)
        conn.commit()
        return {"updated": cur.rowcount > 0}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def get_code_tasks(status=None, project=None, limit=50):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        q = "SELECT * FROM code_tasks WHERE 1=1"
        params = []
        if status:
            q += f" AND status={p}"; params.append(status)
        if project:
            q += f" AND project={p}"; params.append(project)
        q += " ORDER BY created_at DESC"
        if limit:
            q += f" LIMIT {int(limit)}"
        cur.execute(q, params)
        return [row(r) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def get_contacts(name=None, role=None, company=None):
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        q = "SELECT * FROM contacts WHERE 1=1"
        params = []
        if name:
            q += f" AND LOWER(name) LIKE LOWER({p})"; params.append(f"%{name}%")
        if role:
            q += f" AND LOWER(role) LIKE LOWER({p})"; params.append(f"%{role}%")
        if company:
            q += f" AND LOWER(company) LIKE LOWER({p})"; params.append(f"%{company}%")
        q += " ORDER BY name"
        cur.execute(q, params)
        return [row(r) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


# ── Design Library ───────────────────────────────────────────────────────────

import json as _json


def _tags_to_db(tags, pg):
    """Convert a list of tags to DB storage format."""
    if tags is None:
        return "{}" if pg else "[]"
    if isinstance(tags, list):
        if pg:
            return "{" + ",".join(tags) + "}"
        return _json.dumps(tags)
    return tags  # already a string


def _tags_from_db(tags_raw, pg):
    """Normalize tags from DB to a Python list."""
    if tags_raw is None:
        return []
    if isinstance(tags_raw, list):
        return tags_raw
    s = str(tags_raw).strip()
    if pg:
        # PostgreSQL returns native list via psycopg2 already — but handle string fallback
        s = s.strip("{}")
        return [t.strip() for t in s.split(",")] if s else []
    try:
        return _json.loads(s)
    except Exception:
        return []


def _normalize_design(d, pg):
    if d and "tags" in d:
        d["tags"] = _tags_from_db(d["tags"], pg)
    return d


def create_design(name, design_id, version=1, parent_id=None, category="prototype",
                  filament="PLA", stl_path=None, gcode_path=None, slicer_profile=None,
                  tags=None, status="draft", thumbnail_url=None, notes=None, nate_feedback=None):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        tags_val = _tags_to_db(tags, pg)
        cols = "name,design_id,version,parent_id,category,filament,stl_path,gcode_path,slicer_profile,tags,status,thumbnail_url,notes,nate_feedback"
        vals = (name, design_id, version, parent_id, category, filament, stl_path, gcode_path, slicer_profile, tags_val, status, thumbnail_url, notes, nate_feedback)
        placeholders = ",".join([p] * 14)
        if pg:
            placeholders_pg = placeholders.replace(f"{p},", f"{p},", 13)
            # Replace the tags placeholder with cast
            parts = [p] * 14
            parts[9] = f"{p}::text[]"
            pg_ph = ",".join(parts)
            cur.execute(f"INSERT INTO designs ({cols}) VALUES ({pg_ph}) RETURNING id", vals)
            new_id = cur.fetchone()["id"]
            conn.commit()
            return {"id": new_id}
        cur.execute(f"INSERT INTO designs ({cols}) VALUES ({placeholders})", vals)
        conn.commit()
        return {"id": cur.lastrowid}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def get_design(design_id_or_slug):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        # Try numeric id first, then slug
        try:
            int_id = int(design_id_or_slug)
            cur.execute(f"SELECT * FROM designs WHERE id={p}", (int_id,))
        except (ValueError, TypeError):
            cur.execute(f"SELECT * FROM designs WHERE design_id={p}", (design_id_or_slug,))
        return _normalize_design(row(cur.fetchone()), pg)
    except Exception:
        return None
    finally:
        conn.close()


def list_designs(category=None, status=None, filament=None):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        q = "SELECT * FROM designs WHERE 1=1"
        params = []
        if category:
            q += f" AND category={p}"; params.append(category)
        if status:
            q += f" AND status={p}"; params.append(status)
        if filament:
            q += f" AND filament={p}"; params.append(filament)
        q += " ORDER BY name, version"
        cur.execute(q, params)
        return [_normalize_design(row(r), pg) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def search_designs(query, tags=None):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        like = f"%{query}%"
        if pg and tags:
            tag_list = tags if isinstance(tags, list) else [tags]
            tag_array = "{" + ",".join(tag_list) + "}"
            cur.execute(
                f"SELECT * FROM designs WHERE (name ILIKE {p} OR notes ILIKE {p}) AND tags @> {p}::text[] ORDER BY name, version",
                (like, like, tag_array)
            )
        elif pg:
            cur.execute(
                f"SELECT * FROM designs WHERE name ILIKE {p} OR notes ILIKE {p} ORDER BY name, version",
                (like, like)
            )
        elif tags:
            tag_list = tags if isinstance(tags, list) else [tags]
            results = []
            cur.execute(
                f"SELECT * FROM designs WHERE (name LIKE {p} OR notes LIKE {p}) ORDER BY name, version",
                (like, like)
            )
            for r in cur.fetchall():
                d = _normalize_design(row(r), pg)
                if any(t in d.get("tags", []) for t in tag_list):
                    results.append(d)
            return results
        else:
            cur.execute(
                f"SELECT * FROM designs WHERE name LIKE {p} OR notes LIKE {p} ORDER BY name, version",
                (like, like)
            )
        return [_normalize_design(row(r), pg) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def update_design(design_id_or_slug, fields):
    allowed = {"name", "version", "parent_id", "category", "filament", "stl_path", "gcode_path",
               "slicer_profile", "tags", "status", "thumbnail_url", "notes", "nate_feedback"}
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return {"error": "No valid fields to update."}
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        set_parts = []
        values = []
        for k, v in clean.items():
            if k == "tags":
                v = _tags_to_db(v, pg)
                set_parts.append(f"{k}={p}::text[]" if pg else f"{k}={p}")
            else:
                set_parts.append(f"{k}={p}")
            values.append(v)
        if pg:
            set_parts.append("updated_at=NOW()")
        else:
            set_parts.append("updated_at=CURRENT_TIMESTAMP")
        set_clause = ", ".join(set_parts)
        # Where clause — numeric id or slug
        try:
            int_id = int(design_id_or_slug)
            values.append(int_id)
            cur.execute(f"UPDATE designs SET {set_clause} WHERE id={p}", values)
        except (ValueError, TypeError):
            values.append(design_id_or_slug)
            cur.execute(f"UPDATE designs SET {set_clause} WHERE design_id={p}", values)
        conn.commit()
        return {"updated": cur.rowcount > 0}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def add_print_record(design_id_or_slug, filament=None, nozzle_temp=None, bed_temp=None,
                     print_speed=None, layer_height=None, infill=None, ironing=False,
                     top_solid_layers=None, outcome="success", notes=None, nate_feedback=None):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        # Resolve slug to id if needed
        try:
            did = int(design_id_or_slug)
        except (ValueError, TypeError):
            cur.execute(f"SELECT id FROM designs WHERE design_id={p}", (design_id_or_slug,))
            r = cur.fetchone()
            if not r:
                return {"error": f"Design not found: {design_id_or_slug}"}
            did = r["id"] if isinstance(r, dict) else r[0]
        cols = "design_id,filament,nozzle_temp,bed_temp,print_speed,layer_height,infill,ironing,top_solid_layers,outcome,notes,nate_feedback"
        vals = (did, filament, nozzle_temp, bed_temp, print_speed, layer_height, infill, ironing, top_solid_layers, outcome, notes, nate_feedback)
        placeholders = ",".join([p] * 12)
        if pg:
            cur.execute(f"INSERT INTO print_history ({cols}) VALUES ({placeholders}) RETURNING id", vals)
            new_id = cur.fetchone()["id"]
            conn.commit()
            return {"id": new_id}
        cur.execute(f"INSERT INTO print_history ({cols}) VALUES ({placeholders})", vals)
        conn.commit()
        return {"id": cur.lastrowid}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def get_design_history(design_id_or_slug, limit=50):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        try:
            did = int(design_id_or_slug)
        except (ValueError, TypeError):
            cur.execute(f"SELECT id FROM designs WHERE design_id={p}", (design_id_or_slug,))
            r = cur.fetchone()
            if not r:
                return []
            did = r["id"] if isinstance(r, dict) else r[0]
        cur.execute(
            f"SELECT * FROM print_history WHERE design_id={p} ORDER BY printed_at DESC LIMIT {int(limit)}",
            (did,)
        )
        return [row(r) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def get_design_versions(design_id_or_slug):
    """Walk the entire version tree (ancestors + descendants) for any node."""
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        # Resolve to id
        try:
            start_id = int(design_id_or_slug)
        except (ValueError, TypeError):
            cur.execute(f"SELECT id FROM designs WHERE design_id={p}", (design_id_or_slug,))
            r = cur.fetchone()
            if not r:
                return []
            start_id = r["id"] if isinstance(r, dict) else r[0]

        if pg:
            # Use recursive CTE to walk full tree from root
            cur.execute(f"""
                WITH RECURSIVE tree AS (
                    SELECT id FROM designs WHERE id={p}
                    UNION ALL
                    SELECT d.id FROM designs d JOIN tree t ON d.parent_id=t.id
                ),
                root AS (
                    SELECT COALESCE(
                        (WITH RECURSIVE anc AS (
                            SELECT id, parent_id FROM designs WHERE id={p}
                            UNION ALL
                            SELECT d.id, d.parent_id FROM designs d JOIN anc a ON d.id=a.parent_id
                        ) SELECT id FROM anc WHERE parent_id IS NULL LIMIT 1),
                        {p}
                    ) AS root_id
                ),
                full_tree AS (
                    SELECT d.id FROM designs d, root WHERE d.id=root.root_id
                    UNION ALL
                    SELECT d.id FROM designs d JOIN full_tree ft ON d.parent_id=ft.id
                )
                SELECT designs.* FROM designs JOIN full_tree ON designs.id=full_tree.id
                ORDER BY version
            """, (start_id, start_id, start_id))
        else:
            # SQLite: walk manually in Python
            cur.execute("SELECT * FROM designs")
            all_rows = [row(r) for r in cur.fetchall()]
            by_id = {d["id"]: d for d in all_rows}
            # Walk up to root
            root_id = start_id
            visited = set()
            while root_id in by_id and by_id[root_id]["parent_id"] and root_id not in visited:
                visited.add(root_id)
                root_id = by_id[root_id]["parent_id"]
            # Walk down from root
            result = []
            queue = [root_id]
            seen = set()
            while queue:
                curr = queue.pop(0)
                if curr in seen:
                    continue
                seen.add(curr)
                if curr in by_id:
                    result.append(_normalize_design(by_id[curr], pg))
                    for d in all_rows:
                        if d["parent_id"] == curr:
                            queue.append(d["id"])
            return result

        return [_normalize_design(row(r), pg) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


# ── Purchase Orders ──────────────────────────────────────────────────────────

import json as _json2


def _next_po_number(cur, pg):
    """Generate next sequential PO number."""
    p = "%s" if pg else "?"
    cur.execute("SELECT po_number FROM purchase_orders ORDER BY id DESC LIMIT 1")
    r = cur.fetchone()
    if r:
        last = r["po_number"] if isinstance(r, dict) else r[0]
        try:
            n = int(last.replace("PO-", "")) + 1
        except Exception:
            n = 1
    else:
        n = 1
    return f"PO-{n:04d}"


def _items_to_db(items, pg):
    if items is None:
        return "[]" if not pg else "[]"
    if isinstance(items, list):
        return _json2.dumps(items)
    return items


def _items_from_db(raw, pg):
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        return _json2.loads(raw)
    except Exception:
        return []


def _calc_total(items):
    total = 0.0
    for item in (items or []):
        try:
            total += float(item.get("qty", 1)) * float(item.get("unit_price", 0))
        except Exception:
            pass
    return round(total, 2)


def _normalize_po(d, pg):
    if d and "items" in d:
        d["items"] = _items_from_db(d["items"], pg)
    return d


def list_purchase_orders(status=None, category=None, folder_id=None, vendor=None,
                         date_from=None, date_to=None):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        q = "SELECT * FROM purchase_orders WHERE 1=1"
        params = []
        if status:
            q += f" AND status={p}"; params.append(status)
        if category:
            q += f" AND category={p}"; params.append(category)
        if folder_id is not None:
            q += f" AND folder_id={p}"; params.append(folder_id)
        if vendor:
            like = f"%{vendor}%"
            q += f" AND vendor ILIKE {p}" if pg else f" AND LOWER(vendor) LIKE LOWER({p})"
            params.append(like)
        if date_from:
            q += f" AND created_at >= {p}"; params.append(date_from)
        if date_to:
            q += f" AND created_at <= {p}"; params.append(date_to)
        q += " ORDER BY created_at DESC"
        cur.execute(q, params)
        return [_normalize_po(row(r), pg) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def get_purchase_order(po_ref):
    """Get by numeric id or PO number string."""
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        try:
            int_id = int(po_ref)
            cur.execute(f"SELECT * FROM purchase_orders WHERE id={p}", (int_id,))
        except (ValueError, TypeError):
            cur.execute(f"SELECT * FROM purchase_orders WHERE po_number={p}", (str(po_ref).upper(),))
        return _normalize_po(row(cur.fetchone()), pg)
    except Exception:
        return None
    finally:
        conn.close()


def create_purchase_order(title, vendor=None, category="other", items=None,
                          status="to_be_purchased", folder_id=None, priority="normal", notes=None):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        po_number = _next_po_number(cur, pg)
        items_val = _items_to_db(items, pg)
        total = _calc_total(items)
        cols = "po_number,title,vendor,category,items,total_cost,status,folder_id,priority,notes"
        vals = (po_number, title, vendor, category, items_val, total, status, folder_id, priority, notes)
        if pg:
            parts = [p] * 10
            parts[4] = f"{p}::jsonb"
            cur.execute(f"INSERT INTO purchase_orders ({cols}) VALUES ({','.join(parts)}) RETURNING id", vals)
            new_id = cur.fetchone()["id"]
            conn.commit()
            return {"id": new_id, "po_number": po_number, "total_cost": total}
        cur.execute(f"INSERT INTO purchase_orders ({cols}) VALUES ({','.join([p]*10)})", vals)
        conn.commit()
        return {"id": cur.lastrowid, "po_number": po_number, "total_cost": total}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def update_purchase_order(po_ref, fields):
    allowed = {"title", "vendor", "category", "items", "status", "folder_id",
               "priority", "notes", "ordered_at", "received_at"}
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return {"error": "No valid fields to update."}
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        set_parts = []
        values = []
        for k, v in clean.items():
            if k == "items":
                v = _items_to_db(v, pg)
                set_parts.append(f"{k}={p}::jsonb" if pg else f"{k}={p}")
                values.append(v)
                # Recalculate total
                set_parts.append(f"total_cost={p}")
                values.append(_calc_total(_items_from_db(v, pg)))
            else:
                set_parts.append(f"{k}={p}")
                values.append(v)
        set_parts.append("updated_at=NOW()" if pg else "updated_at=CURRENT_TIMESTAMP")
        set_clause = ", ".join(set_parts)
        try:
            int_id = int(po_ref)
            values.append(int_id)
            cur.execute(f"UPDATE purchase_orders SET {set_clause} WHERE id={p}", values)
        except (ValueError, TypeError):
            values.append(str(po_ref).upper())
            cur.execute(f"UPDATE purchase_orders SET {set_clause} WHERE po_number={p}", values)
        conn.commit()
        return {"updated": cur.rowcount > 0}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def update_po_status(po_ref, status):
    valid = {"to_be_purchased", "ordered", "received"}
    if status not in valid:
        return {"error": f"Invalid status. Must be one of: {', '.join(valid)}"}
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        now = "NOW()" if pg else "CURRENT_TIMESTAMP"
        extra = ""
        if status == "ordered":
            extra = f", ordered_at={now}"
        elif status == "received":
            extra = f", received_at={now}"
        set_clause = f"status={p}, updated_at={now}{extra}"
        try:
            int_id = int(po_ref)
            cur.execute(f"UPDATE purchase_orders SET {set_clause} WHERE id={p}", [status, int_id])
        except (ValueError, TypeError):
            cur.execute(f"UPDATE purchase_orders SET {set_clause} WHERE po_number={p}", [status, str(po_ref).upper()])
        conn.commit()
        return {"updated": cur.rowcount > 0, "status": status}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def search_purchase_orders(query):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        like = f"%{query}%"
        if pg:
            cur.execute(
                f"SELECT * FROM purchase_orders WHERE title ILIKE {p} OR vendor ILIKE {p} OR notes ILIKE {p} OR po_number ILIKE {p} ORDER BY created_at DESC",
                (like, like, like, like)
            )
        else:
            cur.execute(
                f"SELECT * FROM purchase_orders WHERE LOWER(title) LIKE LOWER({p}) OR LOWER(vendor) LIKE LOWER({p}) OR LOWER(notes) LIKE LOWER({p}) OR LOWER(po_number) LIKE LOWER({p}) ORDER BY created_at DESC",
                (like, like, like, like)
            )
        return [_normalize_po(row(r), pg) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def list_folders():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM folders ORDER BY parent_id NULLS FIRST, name" if _is_postgres(os.environ.get("DATABASE_URL","")) else "SELECT * FROM folders ORDER BY CASE WHEN parent_id IS NULL THEN 0 ELSE 1 END, name")
        return [row(r) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def create_folder(name, parent_id=None):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        if pg:
            cur.execute(f"INSERT INTO folders (name, parent_id) VALUES ({p},{p}) RETURNING id", (name, parent_id))
            new_id = cur.fetchone()["id"]
            conn.commit()
            return {"id": new_id}
        cur.execute(f"INSERT INTO folders (name, parent_id) VALUES ({p},{p})", (name, parent_id))
        conn.commit()
        return {"id": cur.lastrowid}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def get_folder_orders(folder_id):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM purchase_orders WHERE folder_id={p} ORDER BY created_at DESC", (folder_id,))
        return [_normalize_po(row(r), pg) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def get_po_summary():
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status, category, SUM(total_cost) AS total, COUNT(*) AS count FROM purchase_orders GROUP BY status, category ORDER BY status, category")
        rows = [row(r) for r in cur.fetchall()]
        summary = {}
        for r in rows:
            s = r["status"]
            c = r["category"]
            summary.setdefault(s, {})
            summary[s][c] = {"total": float(r["total"] or 0), "count": int(r["count"])}
        totals_by_status = {}
        for s, cats in summary.items():
            totals_by_status[s] = round(sum(v["total"] for v in cats.values()), 2)
        return {"by_status_category": summary, "totals_by_status": totals_by_status}
    except Exception:
        return {}
    finally:
        conn.close()


def add_lrg_game(user_id, title, publisher="Limited Run Games", status="watching",
                 buy_price=0, est_resale=0, deadline=None, notes=None):
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    p = ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        if pg:
            cur.execute(
                f"INSERT INTO lrg_games (user_id, title, publisher, status, buy_price, est_resale, deadline, notes) VALUES ({p},{p},{p},{p},{p},{p},{p},{p}) RETURNING id",
                (user_id, title, publisher, status, buy_price, est_resale, deadline, notes)
            )
            new_id = cur.fetchone()["id"]
            conn.commit()
            return new_id
        cur.execute(
            f"INSERT INTO lrg_games (user_id, title, publisher, status, buy_price, est_resale, deadline, notes) VALUES ({p},{p},{p},{p},{p},{p},{p},{p})",
            (user_id, title, publisher, status, buy_price, est_resale, deadline, notes)
        )
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()
