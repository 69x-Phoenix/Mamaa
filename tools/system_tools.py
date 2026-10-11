"""Small system helpers."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tools.registry import Permission, ToolError, ToolSpec


def current_datetime(timezone: str = "Asia/Dhaka") -> dict[str, Any]:
    """Return the current date/time (default Bangladesh time)."""
    try:
        now = datetime.now(ZoneInfo(timezone))
    except ZoneInfoNotFoundError as exc:
        raise ToolError(f"Unknown timezone: {timezone}") from exc
    return {"timezone": timezone, "iso": now.isoformat(timespec="seconds"), "weekday": now.strftime("%A")}


CURRENT_DATETIME = ToolSpec(
    name="current_datetime",
    description="Get today's date and time. Use before answering anything that depends on 'today' or 'now'.",
    parameters={"type": "object", "properties": {"timezone": {"type": "string", "description": "IANA zone, default Asia/Dhaka"}}},
    func=current_datetime, permission=Permission.READ_ONLY, timeout=5,
)
