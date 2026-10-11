"""Workspace-sandboxed file tools. Nothing outside the workspace is reachable."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.registry import Permission, ToolError, ToolSpec

READABLE = {".txt", ".md", ".csv", ".json", ".py", ".log"}
MAX_LIST = 200
MAX_WRITE_CHARS = 200_000


def safe_path(root: Path, relative: str) -> Path:
    """Resolve ``relative`` inside ``root`` or raise (blocks ../ and absolute paths)."""
    root = root.resolve()
    target = (root / relative).resolve()
    if target != root and not target.is_relative_to(root):
        raise ToolError("Access denied: path is outside the workspace")
    return target


def make_file_tools(workspace: Path) -> list[ToolSpec]:
    """Build list/read/write tools bound to one workspace directory."""
    workspace = workspace.resolve()
    output = workspace / "output"

    def list_files(path: str = ".") -> dict[str, Any]:
        target = safe_path(workspace, path)
        if not target.is_dir():
            raise ToolError(f"Not a directory: {path}")
        entries = []
        for item in sorted(target.iterdir())[:MAX_LIST]:
            if item.name == ".gitkeep":
                continue
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size_bytes": item.stat().st_size if item.is_file() else None,
            })
        return {"path": path, "entries": entries}

    def read_text_file(path: str, max_chars: int = 20_000) -> dict[str, Any]:
        target = safe_path(workspace, path)
        if not target.is_file():
            raise ToolError(f"File not found: {path}")
        if target.suffix.lower() not in READABLE:
            raise ToolError(f"Unsupported type {target.suffix!r}. Readable: {sorted(READABLE)}")
        max_chars = max(100, min(int(max_chars), 100_000))
        text = target.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "truncated": len(text) > max_chars, "content": text[:max_chars]}

    def write_text_file(path: str, content: str) -> dict[str, Any]:
        if len(content) > MAX_WRITE_CHARS:
            raise ToolError("Content too large")
        target = safe_path(output, path)
        if target.suffix.lower() not in READABLE:
            raise ToolError(f"Unsupported type {target.suffix!r}. Allowed: {sorted(READABLE)}")
        if target.exists():
            raise ToolError("File already exists. Choose a new file name (existing files are never overwritten).")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"saved": str(target.relative_to(workspace)), "chars": len(content)}

    return [
        ToolSpec(
            name="list_files",
            description="List files/folders inside the workspace (folders: input, output, downloads, temp).",
            parameters={"type": "object", "properties": {"path": {"type": "string", "description": "Folder relative to workspace, e.g. 'input'. Default '.'"}}},
            func=list_files, permission=Permission.READ_ONLY, timeout=10,
        ),
        ToolSpec(
            name="read_text_file",
            description="Read a text-like file (.txt .md .csv .json .py .log) from the workspace.",
            parameters={"type": "object", "properties": {
                "path": {"type": "string", "description": "e.g. 'input/notes.txt'"},
                "max_chars": {"type": "integer", "description": "Max characters to return (default 20000)"},
            }, "required": ["path"]},
            func=read_text_file, permission=Permission.READ_ONLY, timeout=10,
        ),
        ToolSpec(
            name="write_text_file",
            description="Create a NEW text file in workspace/output (path is relative to output/). Never overwrites.",
            parameters={"type": "object", "properties": {
                "path": {"type": "string", "description": "e.g. 'report.md'"},
                "content": {"type": "string", "description": "Full file content"},
            }, "required": ["path", "content"]},
            func=write_text_file, permission=Permission.SAFE_WRITE, timeout=10,
        ),
    ]
