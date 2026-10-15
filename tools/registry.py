"""Central tool registry: schema, permission level, timeout and safe execution."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

log = logging.getLogger(__name__)
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tool")


class Permission(str, Enum):
    """How risky a tool is."""

    READ_ONLY = "READ_ONLY"  # runs automatically
    SAFE_WRITE = "SAFE_WRITE"  # creates new files inside the workspace
    CONFIRM_REQUIRED = "CONFIRM_REQUIRED"  # needs explicit user approval


class ToolError(Exception):
    """An expected failure. The message is shown to the model so it can recover."""


@dataclass(frozen=True)
class ToolSpec:
    """Everything the model and the executor need to know about one tool."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON-schema style: {"type": "object", ...}
    func: Callable[..., Any]
    permission: Permission = Permission.READ_ONLY
    timeout: float = 30.0


ConfirmFn = Callable[[ToolSpec, dict[str, Any]], bool]


class ToolRegistry:
    """Holds all tools and runs them without ever raising to the caller."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def execute(
        self, name: str, args: dict[str, Any] | None, confirm: ConfirmFn | None = None
    ) -> dict[str, Any]:
        """Run a tool. Returns {"ok": True, "result": ...} or {"ok": False, "error": ...}."""
        spec = self._tools.get(name)
        if spec is None:
            return {"ok": False, "error": f"Unknown tool '{name}'. Available: {sorted(self._tools)}"}

        args = dict(args or {})
        props = spec.parameters.get("properties", {})
        missing = [p for p in spec.parameters.get("required", []) if p not in args]
        unknown = [k for k in args if k not in props]
        if missing or unknown:
            return {"ok": False, "error": f"Bad arguments. missing={missing} unexpected={unknown}"}

        if spec.permission is Permission.CONFIRM_REQUIRED and not (confirm and confirm(spec, args)):
            return {"ok": False, "error": "This action needs the user's explicit approval. An approval card is now shown to the user; the action was NOT run. Do not retry it. Tell the user what is waiting for approval."}

        future = _POOL.submit(spec.func, **args)
        try:
            result = future.result(timeout=spec.timeout)
        except FutureTimeout:
            future.cancel()
            log.warning("Tool %s timed out after %ss", name, spec.timeout)
            return {"ok": False, "error": f"Tool '{name}' timed out after {spec.timeout:.0f}s"}
        except ToolError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # never crash the agent loop
            log.exception("Tool %s crashed", name)
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        log.info("Tool %s ok", name)
        return {"ok": True, "result": result}
