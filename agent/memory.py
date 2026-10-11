"""SQLite task history. Never stores secrets (requests/summaries are truncated plain text).

NOTE: on Streamlit Community Cloud the disk is ephemeral - this file resets on reboot.
For permanent cloud memory, point this module at a hosted database later.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    request TEXT NOT NULL,
    summary TEXT,
    status TEXT NOT NULL DEFAULT 'running'
);
CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    created_at TEXT NOT NULL,
    tool TEXT NOT NULL,
    ok INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    title TEXT NOT NULL,
    transcript TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Memory:
    """Tiny SQLite wrapper (one short-lived connection per call = thread-safe)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        with self._connect() as con:
            con.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=10)
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def start_task(self, request: str) -> int:
        with closing(self._connect()) as con, con:
            cur = con.execute("INSERT INTO tasks (created_at, request) VALUES (?, ?)", (_now(), request[:500]))
            return int(cur.lastrowid)

    def log_tool(self, task_id: int, tool: str, ok: bool) -> None:
        with closing(self._connect()) as con, con:
            con.execute("INSERT INTO tool_calls (task_id, created_at, tool, ok) VALUES (?,?,?,?)", (task_id, _now(), tool, int(ok)))

    def finish_task(self, task_id: int, summary: str, status: str) -> None:
        with closing(self._connect()) as con, con:
            con.execute("UPDATE tasks SET summary=?, status=? WHERE id=?", (summary[:500], status, task_id))

    def recent_tasks(self, limit: int = 10) -> list[dict[str, Any]]:
        with closing(self._connect()) as con:
            rows = con.execute("SELECT id, created_at, request, status FROM tasks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": r[0], "created_at": r[1], "request": r[2], "status": r[3]} for r in rows]

    def save_conversation(self, conv_id: int | None, title: str, chat: list[dict]) -> int:
        transcript = json.dumps(chat, ensure_ascii=False)
        now = _now()

        with closing(self._connect()) as con, con:
            if conv_id is not None:
                row = con.execute(
                    "SELECT id FROM conversations WHERE id=?", (conv_id,)
                ).fetchone()
                if row:
                    con.execute(
                        "UPDATE conversations SET title=?, transcript=?, updated_at=? WHERE id=?",
                        (title[:100], transcript, now, conv_id),
                    )
                    return conv_id

            cur = con.execute(
                "INSERT INTO conversations (created_at, updated_at, title, transcript) VALUES (?,?,?,?)",
                (now, now, title[:100], transcript),
            )
            return int(cur.lastrowid)

    def load_conversation(self, conv_id: int) -> list[dict] | None:
        with closing(self._connect()) as con:
            row = con.execute(
                "SELECT transcript FROM conversations WHERE id=?", (conv_id,)
            ).fetchone()

        if not row:
            return None

        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None

    def list_conversations(self, limit: int = 25) -> list[dict[str, Any]]:
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT id, title, updated_at FROM conversations "
                "ORDER BY updated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [
            {"id": r[0], "title": r[1], "updated_at": r[2]}
            for r in rows
        ]

    def delete_conversation(self, conv_id: int) -> None:
        with closing(self._connect()) as con, con:
            con.execute("DELETE FROM conversations WHERE id=?", (conv_id,))

    def stats(self) -> dict[str, int]:
        with closing(self._connect()) as con:
            tasks = con.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            calls = con.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0]
        return {"tasks": tasks, "tool_calls": calls}

    def clear(self) -> None:
        with closing(self._connect()) as con, con:
            con.executescript("DELETE FROM tool_calls; DELETE FROM tasks; DELETE FROM conversations;")
