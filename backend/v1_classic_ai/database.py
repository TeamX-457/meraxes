"""SQLite storage for bots and per-bot settings."""
import json
import sqlite3
import uuid
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "platform.db"


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS bots (
                bot_id       TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                business_id  TEXT NOT NULL,
                model_type   TEXT NOT NULL DEFAULT 'hybrid',
                custom_qa    TEXT DEFAULT '[]',
                created_at   TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name    TEXT
            );
            CREATE TABLE IF NOT EXISTS messages (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id    TEXT NOT NULL,
                user_id   TEXT NOT NULL,
                role      TEXT NOT NULL,
                content   TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_messages_bot_user
                ON messages(bot_id, user_id, id);

            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id   TEXT PRIMARY KEY,
                bot_id       TEXT,
                dataset      TEXT NOT NULL DEFAULT 'saas',
                title        TEXT NOT NULL DEFAULT 'New chat',
                created_at   TEXT DEFAULT (datetime('now')),
                updated_at   TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated
                ON chat_sessions(updated_at DESC);
            """
        )
        cols = [r[1] for r in con.execute("PRAGMA table_info(messages)").fetchall()]
        if "session_id" not in cols:
            con.execute("ALTER TABLE messages ADD COLUMN session_id TEXT")
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)"
            )
        session_cols = [r[1] for r in con.execute("PRAGMA table_info(chat_sessions)").fetchall()]
        if "client_id" not in session_cols:
            con.execute("ALTER TABLE chat_sessions ADD COLUMN client_id TEXT")
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_sessions_client ON chat_sessions(client_id, updated_at DESC)"
            )
            # Remove legacy test sessions (no client_id) from dev runs
            con.execute(
                "DELETE FROM messages WHERE session_id IN "
                "(SELECT session_id FROM chat_sessions WHERE client_id IS NULL)"
            )
            con.execute("DELETE FROM chat_sessions WHERE client_id IS NULL")


def create_bot(name: str, business_id: str, model_type: str = "hybrid") -> dict:
    bot_id = str(uuid.uuid4())[:8]
    with _conn() as con:
        con.execute(
            "INSERT INTO bots (bot_id, name, business_id, model_type) VALUES (?, ?, ?, ?)",
            (bot_id, name, business_id, model_type),
        )
    return get_bot(bot_id)


def get_bot(bot_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM bots WHERE bot_id = ?", (bot_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["custom_qa"] = json.loads(d.get("custom_qa") or "[]")
    return d


def list_bots() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM bots ORDER BY created_at DESC").fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["custom_qa"] = json.loads(d.get("custom_qa") or "[]")
        out.append(d)
    return out


def update_bot(bot_id: str, **fields) -> dict | None:
    bot = get_bot(bot_id)
    if not bot:
        return None
    if "custom_qa" in fields:
        fields["custom_qa"] = json.dumps(fields["custom_qa"])
    allowed = {"name", "business_id", "model_type", "custom_qa"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return bot
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [bot_id]
    with _conn() as con:
        con.execute(f"UPDATE bots SET {cols} WHERE bot_id = ?", vals)
    return get_bot(bot_id)


def save_user_name(user_id: str, name: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO users (user_id, name) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET name = excluded.name",
            (user_id, name),
        )


def get_user_name(user_id: str) -> str | None:
    with _conn() as con:
        row = con.execute("SELECT name FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return row["name"] if row else None


def save_message(bot_id: str, user_id: str, role: str, content: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO messages (bot_id, user_id, role, content) VALUES (?, ?, ?, ?)",
            (bot_id, user_id, role, content),
        )


def get_messages(bot_id: str, user_id: str, limit: int = 100) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            """SELECT role, content, created_at FROM messages
               WHERE bot_id = ? AND user_id = ?
               ORDER BY id ASC
               LIMIT ?""",
            (bot_id, user_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"], "created_at": r["created_at"]} for r in rows]


def clear_messages(bot_id: str, user_id: str) -> int:
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM messages WHERE bot_id = ? AND user_id = ?",
            (bot_id, user_id),
        )
        return cur.rowcount


# ─── Agent chat sessions (multi-turn, list/create/delete) ────────────────────

def create_chat_session(
    bot_id: str | None = None,
    dataset: str = "saas",
    client_id: str | None = None,
) -> dict:
    session_id = str(uuid.uuid4())[:12]
    with _conn() as con:
        con.execute(
            "INSERT INTO chat_sessions (session_id, bot_id, dataset, title, client_id) VALUES (?, ?, ?, ?, ?)",
            (session_id, bot_id, dataset, "New chat", client_id),
        )
    return get_chat_session(session_id)


def get_chat_session(session_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM chat_sessions WHERE session_id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def list_chat_sessions(client_id: str | None = None, limit: int = 40) -> list[dict]:
    with _conn() as con:
        if client_id:
            rows = con.execute(
                """SELECT s.*,
                          (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) AS message_count
                   FROM chat_sessions s
                   WHERE s.client_id = ?
                     AND (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) > 0
                   ORDER BY s.updated_at DESC
                   LIMIT ?""",
                (client_id, limit),
            ).fetchall()
        else:
            rows = con.execute(
                """SELECT s.*,
                          (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) AS message_count
                   FROM chat_sessions s
                   WHERE (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) > 0
                   ORDER BY s.updated_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def touch_chat_session(session_id: str, title: str | None = None) -> None:
    with _conn() as con:
        if title:
            con.execute(
                "UPDATE chat_sessions SET title = ?, updated_at = datetime('now') WHERE session_id = ?",
                (title[:80], session_id),
            )
        else:
            con.execute(
                "UPDATE chat_sessions SET updated_at = datetime('now') WHERE session_id = ?",
                (session_id,),
            )


def update_chat_session_bot(
    session_id: str, bot_id: str | None = None, dataset: str | None = None
) -> None:
    """Update which bot/dataset a session is scoped to (when user changes the dropdown)."""
    sets, params = [], []
    if bot_id is not None:
        sets.append("bot_id = ?")
        params.append(bot_id or None)
    if dataset is not None:
        sets.append("dataset = ?")
        params.append(dataset)
    if not sets:
        return
    params.append(session_id)
    with _conn() as con:
        con.execute(
            f"UPDATE chat_sessions SET {', '.join(sets)} WHERE session_id = ?",
            tuple(params),
        )


def delete_chat_session(session_id: str) -> int:
    with _conn() as con:
        con.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        cur = con.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
        return cur.rowcount


def save_session_message(session_id: str, role: str, content: str) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO messages (bot_id, user_id, role, content, session_id) VALUES (?, ?, ?, ?, ?)",
            ("agent", session_id, role, content, session_id),
        )
        con.execute(
            "UPDATE chat_sessions SET updated_at = datetime('now') WHERE session_id = ?",
            (session_id,),
        )
        return int(cur.lastrowid)


def get_session_messages(session_id: str, limit: int = 100) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            """SELECT id, role, content, created_at FROM messages
               WHERE session_id = ?
               ORDER BY id ASC
               LIMIT ?""",
            (session_id, limit),
        ).fetchall()
    return [{"id": r["id"], "role": r["role"], "content": r["content"], "created_at": r["created_at"]} for r in rows]
