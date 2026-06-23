"""
database.py — SQLite-backed user memory store.

Stores per-user facts: name, preferences, conversation history.
Thread-safe via connection-per-call pattern.
"""
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from v2_llm_agent.config import SQLITE_DB_PATH, CONVERSATION_WINDOW

logger = logging.getLogger(__name__)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    Path(SQLITE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    """Create tables if they don't exist. Call once at startup."""
    with _conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id   TEXT PRIMARY KEY,
                name      TEXT,
                meta      TEXT DEFAULT '{}',
                created   TEXT DEFAULT (datetime('now')),
                updated   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   TEXT NOT NULL,
                role      TEXT NOT NULL,      -- 'user' | 'assistant'
                content   TEXT NOT NULL,
                ts        TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, id);
            """
        )
    logger.info("SQLite DB initialised at %s", SQLITE_DB_PATH)


# ─── User helpers ─────────────────────────────────────────────────────────────

def upsert_user(user_id: str, name: str | None = None, **meta_updates: Any) -> None:
    with _conn() as con:
        row = con.execute(
            "SELECT meta FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

        if row is None:
            meta = meta_updates
            con.execute(
                "INSERT INTO users (user_id, name, meta) VALUES (?, ?, ?)",
                (user_id, name, json.dumps(meta)),
            )
        else:
            existing_meta: dict = json.loads(row["meta"] or "{}")
            existing_meta.update(meta_updates)
            con.execute(
                """UPDATE users
                   SET name    = COALESCE(?, name),
                       meta    = ?,
                       updated = datetime('now')
                   WHERE user_id = ?""",
                (name, json.dumps(existing_meta), user_id),
            )


def get_user(user_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["meta"] = json.loads(d.get("meta") or "{}")
        return d


def get_user_name(user_id: str) -> str | None:
    user = get_user(user_id)
    return user["name"] if user else None


# ─── Conversation history ─────────────────────────────────────────────────────

def save_turn(user_id: str, role: str, content: str) -> int:
    """Persist a single conversation turn. Returns the new row id."""
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        return int(cur.lastrowid)


def get_history(user_id: str, limit: int = CONVERSATION_WINDOW) -> list[dict]:
    """Return the last `limit` turns as list of {id, role, content} dicts."""
    with _conn() as con:
        rows = con.execute(
            """SELECT id, role, content FROM conversations
               WHERE user_id = ?
               ORDER BY id DESC
               LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [
        {"id": r["id"], "role": r["role"], "content": r["content"]}
        for r in reversed(rows)
    ]


def get_message(msg_id: int, user_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT id, role, content FROM conversations WHERE id = ? AND user_id = ?",
            (msg_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def delete_message_ids(user_id: str, msg_ids: list[int]) -> int:
    if not msg_ids:
        return 0
    placeholders = ",".join("?" * len(msg_ids))
    with _conn() as con:
        cur = con.execute(
            f"DELETE FROM conversations WHERE user_id = ? AND id IN ({placeholders})",
            (user_id, *msg_ids),
        )
        return cur.rowcount


def delete_message_turn(msg_id: int, user_id: str) -> list[dict]:
    """
    Permanently delete a message and its paired turn (user+assistant).
    Returns deleted rows [{id, role, content}, ...].
    """
    with _conn() as con:
        row = con.execute(
            "SELECT id, role, content FROM conversations WHERE id = ? AND user_id = ?",
            (msg_id, user_id),
        ).fetchone()
        if not row:
            return []

        ids = {row["id"]}
        deleted = [dict(row)]

        if row["role"] == "user":
            nxt = con.execute(
                """SELECT id, role, content FROM conversations
                   WHERE user_id = ? AND id > ? ORDER BY id ASC LIMIT 1""",
                (user_id, msg_id),
            ).fetchone()
            if nxt and nxt["role"] == "assistant":
                ids.add(nxt["id"])
                deleted.append(dict(nxt))
        elif row["role"] == "assistant":
            prev = con.execute(
                """SELECT id, role, content FROM conversations
                   WHERE user_id = ? AND id < ? ORDER BY id DESC LIMIT 1""",
                (user_id, msg_id),
            ).fetchone()
            if prev and prev["role"] == "user":
                ids.add(prev["id"])
                deleted.insert(0, dict(prev))

        placeholders = ",".join("?" * len(ids))
        con.execute(
            f"DELETE FROM conversations WHERE user_id = ? AND id IN ({placeholders})",
            (user_id, *ids),
        )
    return deleted


def clear_history(user_id: str) -> int:
    with _conn() as con:
        cur = con.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        return cur.rowcount


def delete_conversation(user_id: str) -> int:
    """Permanently remove all messages and user record for a session."""
    with _conn() as con:
        cur = con.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        con.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        return cur.rowcount


def list_sessions(limit: int = 40) -> list[dict]:
    """All chat sessions (user_id groups) with preview title, newest first."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT
                c.user_id,
                MAX(c.ts) AS updated,
                COUNT(*) AS turns,
                (
                    SELECT content FROM conversations c2
                    WHERE c2.user_id = c.user_id AND c2.role = 'user'
                    ORDER BY c2.id ASC LIMIT 1
                ) AS title
            FROM conversations c
            GROUP BY c.user_id
            ORDER BY updated DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        title = (r["title"] or "New chat").strip().replace("\n", " ")
        if len(title) > 48:
            title = title[:45] + "…"
        out.append({
            "user_id": r["user_id"],
            "title": title or "New chat",
            "updated": r["updated"],
            "turns": r["turns"],
        })
    return out


def delete_user(user_id: str) -> None:
    with _conn() as con:
        con.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        con.execute("DELETE FROM users WHERE user_id = ?", (user_id,))