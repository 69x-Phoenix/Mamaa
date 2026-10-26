"""Task history and saved conversations.

Local SQLite by default. When TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are set, the same data lives in a
free hosted Turso database (SQLite-compatible), so chat history survives app reboots.
Never stores secrets (requests/summaries are truncated plain text). If the hosted database cannot be
reached the app keeps working on a local file and says so (see ``backend_label``).
"""
from __future__ import annotations

import functools
import json
import logging
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.remote_db import RemoteConnection, RemoteError, make_client

log = logging.getLogger(__name__)
_CACHE_SECONDS = 3.0  # hosted reads are cached briefly: Streamlit reruns the whole page often

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
CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry REAL NOT NULL,
    exit_price REAL,
    stop_loss REAL,
    take_profit REAL,
    size REAL,
    risk_amount REAL,
    pnl REAL,
    r_multiple REAL,
    notes TEXT
);
"""
_JOURNAL_FIELDS = ("symbol", "side", "entry", "exit_price", "stop_loss", "take_profit", "size", "risk_amount", "pnl", "r_multiple", "notes")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resilient(method):
    """If the hosted database fails mid-session, switch to the local file and repeat the call once."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except RemoteError as exc:
            if self._remote is None:
                raise
            self._fall_back(exc)
            return method(self, *args, **kwargs)

    return wrapper


class Memory:
    """Tiny SQL wrapper (one short-lived connection per call = thread-safe)."""

    def __init__(self, db_path: Path, remote: tuple[str, str] | None = None) -> None:
        self.db_path = Path(db_path)
        self._remote = remote
        self._client = make_client() if remote else None
        self._cache: dict[Any, tuple[float, Any]] = {}
        self.backend = "turso" if remote else "local"
        self.warning = ""
        try:
            self._init_schema()
        except RemoteError as exc:
            self._fall_back(exc)

    # ------------------------------------------------------------ backends
    @property
    def backend_label(self) -> str:
        return {"turso": "Permanent (Turso)", "local": "Temporary (resets on reboot)"}.get(
            self.backend, "Temporary (hosted DB unreachable)")

    def _fall_back(self, exc: Exception) -> None:
        log.warning("Hosted memory unavailable (%s); using the local file instead", exc)
        self.warning = str(exc)
        self._remote = None
        self.backend = "fallback"
        self._cache.clear()
        self._init_schema()

    def _init_schema(self) -> None:
        with closing(self._connect()) as con:
            con.executescript(_SCHEMA)

    def _connect(self) -> Any:
        if self._remote is not None:
            return RemoteConnection(self._remote[0], self._remote[1], self._client)
        con = sqlite3.connect(self.db_path, timeout=10)
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def _cached(self, key: Any, loader):
        if self.backend != "turso":
            return loader()
        hit = self._cache.get(key)
        now = time.monotonic()
        if hit and now - hit[0] < _CACHE_SECONDS:
            return hit[1]
        value = loader()
        self._cache[key] = (now, value)
        return value

    # --------------------------------------------------------------- tasks
    @_resilient
    def start_task(self, request: str) -> int:
        self._cache.clear()
        with closing(self._connect()) as con, con:
            cur = con.execute("INSERT INTO tasks (created_at, request) VALUES (?, ?)", (_now(), request[:500]))
            return int(cur.lastrowid)

    @_resilient
    def log_tool(self, task_id: int, tool: str, ok: bool) -> None:
        self._cache.clear()
        with closing(self._connect()) as con, con:
            con.execute("INSERT INTO tool_calls (task_id, created_at, tool, ok) VALUES (?,?,?,?)", (task_id, _now(), tool, int(ok)))

    @_resilient
    def finish_task(self, task_id: int, summary: str, status: str) -> None:
        self._cache.clear()
        with closing(self._connect()) as con, con:
            con.execute("UPDATE tasks SET summary=?, status=? WHERE id=?", (summary[:500], status, task_id))

    @_resilient
    def recent_tasks(self, limit: int = 10) -> list[dict[str, Any]]:
        with closing(self._connect()) as con:
            rows = con.execute("SELECT id, created_at, request, status FROM tasks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": r[0], "created_at": r[1], "request": r[2], "status": r[3]} for r in rows]

    # ------------------------------------------------------- conversations
    @_resilient
    def save_conversation(self, conv_id: int | None, title: str, chat: list[dict]) -> int:
        self._cache.clear()
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

    @_resilient
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

    @_resilient
    def list_conversations(self, limit: int = 25, query: str = "") -> list[dict[str, Any]]:
        """Newest first; ``query`` filters by title (the navigation search box uses it)."""
        needle = (query or "").strip()

        def load() -> list[dict[str, Any]]:
            sql = "SELECT id, title, updated_at FROM conversations"
            params: list[Any] = []
            if needle:
                escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                sql += " WHERE title LIKE ? ESCAPE '\\'"
                params.append(f"%{escaped}%")
            sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
            params.append(limit)
            with closing(self._connect()) as con:
                rows = con.execute(sql, params).fetchall()
            return [{"id": r[0], "title": r[1], "updated_at": r[2]} for r in rows]

        return list(self._cached(("list", limit, needle), load))

    @_resilient
    def delete_conversation(self, conv_id: int) -> None:
        self._cache.clear()
        with closing(self._connect()) as con, con:
            con.execute("DELETE FROM conversations WHERE id=?", (conv_id,))

    # ------------------------------------------------------------- journal
    @_resilient
    def journal_add(self, trade: dict[str, Any]) -> int:
        """Save one trade. The trading journal is separate from chat history and is NOT removed by clear()."""
        self._cache.clear()
        values = [trade.get(name) for name in _JOURNAL_FIELDS]
        with closing(self._connect()) as con, con:
            cur = con.execute(
                "INSERT INTO journal (created_at, " + ", ".join(_JOURNAL_FIELDS) + ") VALUES (?" + ",?" * len(_JOURNAL_FIELDS) + ")",
                (_now(), *values),
            )
            return int(cur.lastrowid)

    @_resilient
    def journal_list(self, limit: int = 50) -> list[dict[str, Any]]:
        """Newest first."""
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT id, created_at, " + ", ".join(_JOURNAL_FIELDS) + " FROM journal ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        names = ("id", "created_at") + _JOURNAL_FIELDS
        return [dict(zip(names, row)) for row in rows]

    @_resilient
    def journal_delete(self, trade_id: int) -> bool:
        self._cache.clear()
        with closing(self._connect()) as con, con:
            cur = con.execute("DELETE FROM journal WHERE id=?", (int(trade_id),))
            return (cur.rowcount or 0) > 0

    # --------------------------------------------------------------- admin
    @_resilient
    def stats(self) -> dict[str, int]:
        def load() -> dict[str, int]:
            with closing(self._connect()) as con:
                row = con.execute("SELECT (SELECT COUNT(*) FROM tasks), (SELECT COUNT(*) FROM tool_calls)").fetchone()
            return {"tasks": int(row[0]), "tool_calls": int(row[1])}

        return dict(self._cached("stats", load))

    @_resilient
    def clear(self) -> None:
        self._cache.clear()
        with closing(self._connect()) as con, con:
            con.executescript("DELETE FROM tool_calls; DELETE FROM tasks; DELETE FROM conversations;")
