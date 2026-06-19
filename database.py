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
        conn.commit()
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
    p = ph()
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"INSERT INTO chat_sessions (user_id, title) VALUES ({p},{p})", (user_id, "New Conversation"))
        conn.commit()
        if pg:
            cur.execute("SELECT lastval()")
            return cur.fetchone()[0]
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


def add_lrg_game(user_id, title, publisher="Limited Run Games", status="watching",
                 buy_price=0, est_resale=0, deadline=None, notes=None):
    p = ph()
    url = os.environ.get("DATABASE_URL", "sqlite:///brexis.db")
    pg = _is_postgres(url)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO lrg_games (user_id, title, publisher, status, buy_price, est_resale, deadline, notes) VALUES ({p},{p},{p},{p},{p},{p},{p},{p})",
            (user_id, title, publisher, status, buy_price, est_resale, deadline, notes)
        )
        conn.commit()
        if pg:
            cur.execute("SELECT lastval()")
            return cur.fetchone()[0]
        return cur.lastrowid
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()
