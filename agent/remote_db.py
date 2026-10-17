"""A tiny client for Turso's SQL-over-HTTP API ("hrana over HTTP", POST /v2/pipeline).

It offers just the slice of the sqlite3 connection API that agent/memory.py uses, so the same SQL
runs on a local file or on a free hosted Turso database. Error messages never contain the token.
"""
from __future__ import annotations

import base64
import time
from typing import Any

CONNECT_TIMEOUT = 8.0
READ_TIMEOUT = 15.0


class RemoteError(RuntimeError):
    """The hosted database could not be used (safe to log: it never contains the auth token)."""


def pipeline_url(url: str) -> str:
    """libsql://name-org.turso.io -> https://name-org.turso.io/v2/pipeline (plain http only for localhost tests)."""
    raw = (url or "").strip().rstrip("/")
    if raw.startswith("libsql://"):
        raw = "https://" + raw[len("libsql://"):]
    local = raw.startswith("http://127.0.0.1") or raw.startswith("http://localhost")
    if not (raw.startswith("https://") or local):
        raise RemoteError("TURSO_DATABASE_URL must start with libsql:// or https://")
    return raw + "/v2/pipeline"


def encode_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}  # a string, to avoid precision loss
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, (bytes, bytearray)):
        return {"type": "blob", "base64": base64.b64encode(bytes(value)).decode("ascii")}
    return {"type": "text", "value": str(value)}


def decode_value(item: dict[str, Any]) -> Any:
    kind = item.get("type")
    if kind == "null":
        return None
    if kind == "integer":
        return int(item["value"])
    if kind == "float":
        return float(item["value"])
    if kind == "blob":
        return base64.b64decode(item.get("base64", ""))
    return item.get("value")


def make_client() -> Any:
    import httpx

    return httpx.Client(timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT))


class RemoteCursor:
    def __init__(self, result: dict[str, Any]) -> None:
        self._rows = [tuple(decode_value(v) for v in row) for row in result.get("rows", [])]
        raw = result.get("last_insert_rowid")
        self.lastrowid = int(raw) if raw not in (None, "") else None
        self.rowcount = int(result.get("affected_row_count", -1))

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple]:
        return list(self._rows)


class RemoteConnection:
    """Autocommit connection: every statement is committed as soon as it runs."""

    def __init__(self, url: str, token: str, client: Any) -> None:
        self._url = pipeline_url(url)
        self._token = token
        self._client = client

    def _send(self, statements: list[tuple[str, tuple]]) -> list[dict[str, Any]]:
        import httpx

        requests: list[dict[str, Any]] = []
        for sql, params in statements:
            stmt: dict[str, Any] = {"sql": sql}
            if params:
                stmt["args"] = [encode_value(p) for p in params]  # args must be omitted when empty
            requests.append({"type": "execute", "stmt": stmt})
        requests.append({"type": "close"})
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        last: Exception | None = None
        response = None
        for _ in range(2):
            try:
                response = self._client.post(self._url, json={"requests": requests}, headers=headers)
                break
            except httpx.TransportError as exc:
                last = exc
                time.sleep(0.4)
        if response is None:
            raise RemoteError(f"could not reach the hosted database ({type(last).__name__})")
        if response.status_code in (401, 403):
            raise RemoteError("the hosted database rejected the credentials (check TURSO_AUTH_TOKEN)")
        if response.status_code != 200:
            raise RemoteError(f"the hosted database answered with HTTP {response.status_code}")
        try:
            results = response.json()["results"]
        except (ValueError, KeyError, TypeError) as exc:
            raise RemoteError("unexpected reply from the hosted database") from exc
        out: list[dict[str, Any]] = []
        for item in results[: len(statements)]:
            if item.get("type") == "error":
                message = str((item.get("error") or {}).get("message", "unknown error"))[:200]
                raise RemoteError(f"database error: {message}")
            out.append(item["response"]["result"])
        if len(out) != len(statements):
            raise RemoteError("incomplete reply from the hosted database")
        return out

    def execute(self, sql: str, params: tuple | list = ()) -> RemoteCursor:
        return RemoteCursor(self._send([(sql, tuple(params))])[0])

    def executescript(self, script: str) -> None:
        statements = [(s.strip(), ()) for s in script.split(";") if s.strip()]
        if statements:
            self._send(statements)

    def close(self) -> None:
        return None

    def __enter__(self) -> "RemoteConnection":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        return False
