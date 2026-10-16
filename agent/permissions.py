"""Approval policy: nothing that writes a file runs without the user's explicit, per-action approval.

How it works
1. Every tool that is not explicitly known to be read-only is forced to CONFIRM_REQUIRED.
2. When the model asks for such a tool, the call is NOT run. It is parked in an ApprovalQueue
   and the UI shows an approval card.
3. Only a click on Approve runs it, exactly once, with exactly the approved arguments.
   Starting a new request, a new chat or a reset discards anything still waiting.
There is deliberately no shell or command tool.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from tools.registry import Permission, ToolRegistry, ToolSpec

# Tools that only read data. Anything else (including future tools) needs approval by default.
READ_ONLY_TOOLS = frozenset({
    "calculator", "current_datetime", "list_files", "read_text_file",
    "web_search", "read_pdf", "inspect_table", "query_table",
})


def apply_approval_policy(registry: ToolRegistry) -> ToolRegistry:
    """Force CONFIRM_REQUIRED on every tool that is not explicitly known to be read-only."""
    for spec in registry.specs():
        if spec.name not in READ_ONLY_TOOLS and spec.permission is not Permission.CONFIRM_REQUIRED:
            registry._tools[spec.name] = dataclasses.replace(spec, permission=Permission.CONFIRM_REQUIRED)
    return registry


def fingerprint(tool: str, args: dict[str, Any]) -> str:
    payload = json.dumps([tool, args], sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class PendingAction:
    id: str
    tool: str
    args: dict[str, Any]
    title: str
    details: list[str] = field(default_factory=list)


def describe_action(tool: str, args: dict[str, Any]) -> tuple[str, list[str]]:
    """A plain-language summary of what the action would do (shown on the approval card)."""
    name = str(args.get("filename") or args.get("path") or "file")[:120]
    if tool == "create_pptx":
        slides = args.get("slides") if isinstance(args.get("slides"), list) else []
        titles = [str(s.get("title", "")) if isinstance(s, dict) else str(s) for s in slides[:12]]
        theme = args.get("theme") or "academic"
        return f"Create PowerPoint: {name}", [f"{len(slides)} content slides, theme: {theme}"] + [f"- {t[:90]}" for t in titles]
    if tool == "create_docx":
        sections = args.get("sections") if isinstance(args.get("sections"), list) else []
        heads = [str(s.get("heading", "")) if isinstance(s, dict) else str(s) for s in sections[:12]]
        return f"Create Word document: {name}", [f"{len(sections)} sections"] + [f"- {h[:90]}" for h in heads]
    if tool == "create_xlsx":
        sheets = args.get("sheets") if isinstance(args.get("sheets"), list) else []
        info = []
        for sheet in sheets[:10]:
            if isinstance(sheet, dict):
                rows = sheet.get("rows") if isinstance(sheet.get("rows"), list) else []
                info.append(f"- {str(sheet.get('name', 'Sheet'))[:60]}: {len(rows)} rows")
        return f"Create Excel workbook: {name}", [f"{len(sheets)} sheets"] + info
    if tool == "write_text_file":
        content = str(args.get("content", ""))
        preview = content[:400] + ("..." if len(content) > 400 else "")
        return f"Create text file: output/{name}", [f"{len(content)} characters", preview]
    return f"Run tool: {tool}", [json.dumps(args, ensure_ascii=False, default=str)[:400]]


class ApprovalQueue:
    """Parks refused tool calls until the user decides. Never runs anything itself."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingAction] = {}

    def request(self, spec: ToolSpec, args: dict[str, Any]) -> bool:
        """Used as the agent's confirm callback: records the request and always answers 'not now'."""
        action_id = fingerprint(spec.name, args)[:10]
        if action_id not in self._pending:
            title, details = describe_action(spec.name, args)
            self._pending[action_id] = PendingAction(action_id, spec.name, dict(args), title, details)
        return False

    def items(self) -> list[PendingAction]:
        return list(self._pending.values())

    def take(self, action_id: str) -> PendingAction | None:
        """Remove and return an action; a second call returns None, so an approval works once."""
        return self._pending.pop(action_id, None)

    def clear(self) -> None:
        self._pending.clear()


def approval_confirm(action: PendingAction) -> Callable[[ToolSpec, dict[str, Any]], bool]:
    """A confirm callback that says yes only to exactly this tool with exactly these arguments."""
    wanted = fingerprint(action.tool, action.args)

    def confirm(spec: ToolSpec, args: dict[str, Any]) -> bool:
        return fingerprint(spec.name, args) == wanted

    return confirm


def run_approved(registry: ToolRegistry, action: PendingAction) -> dict[str, Any]:
    """Run the approved action (and nothing else)."""
    return registry.execute(action.tool, action.args, approval_confirm(action))
