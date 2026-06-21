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
