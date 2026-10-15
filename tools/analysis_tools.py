"""Read-only agent tools for uploaded files: read_pdf, inspect_table, query_table.

They only read files inside the workspace sandbox. They never write, delete or run commands.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agent import file_analysis as fa
from tools.files import safe_path
from tools.registry import Permission, ToolError, ToolSpec


def make_analysis_tools(workspace: Path) -> list[ToolSpec]:
    """Build the read-only analysis tools bound to one workspace directory."""
    workspace = workspace.resolve()

    def _load(path: str, allowed: set[str], label: str) -> tuple[bytes, str]:
        target = safe_path(workspace, path)
        if not target.is_file():
            raise ToolError(f"File not found: {path}")
        if target.suffix.lower() not in allowed:
            raise ToolError(f"This tool reads {label} files only (got '{target.suffix}').")
        if target.stat().st_size > fa.MAX_FILE_BYTES:
            raise ToolError(f"File exceeds the {fa.MAX_FILE_BYTES // (1024 * 1024)} MB limit.")
        data = target.read_bytes()
        try:
            return data, fa.validate_upload(target.name, data)
        except fa.FileAnalysisError as exc:
            raise ToolError(str(exc)) from exc

    def read_pdf(path: str, start_page: int = 1, max_pages: int = 10) -> dict[str, Any]:
        data, _ = _load(path, fa.PDF_EXTENSIONS, "PDF")
        try:
            result = fa.read_pdf(data, int(start_page), int(max_pages))
        except fa.FileAnalysisError as exc:
            raise ToolError(str(exc)) from exc
        result["path"] = path
        if result["needs_ocr"]:
            result["note"] = "No extractable text on these pages. The PDF may be scanned (OCR is not supported yet)."
        return result

    def inspect_table(path: str, sheet: str = "") -> dict[str, Any]:
        data, suffix = _load(path, fa.TABLE_EXTENSIONS, "CSV/XLSX")
        try:
            frame, info = fa.load_table(data, suffix, str(sheet or ""))
            result = fa.summarize_table(frame, info)
        except fa.FileAnalysisError as exc:
            raise ToolError(str(exc)) from exc
        result["path"] = path
        return result

    def query_table(path: str, sheet: str = "", filter_column: str = "", filter_op: str = "",
                    filter_value: str = "", group_by: str = "", value_column: str = "",
                    aggregate: str = "", sort_by: str = "", descending: bool = False,
                    limit: int = 20) -> dict[str, Any]:
        data, suffix = _load(path, fa.TABLE_EXTENSIONS, "CSV/XLSX")
        try:
            frame, info = fa.load_table(data, suffix, str(sheet or ""))
            result = fa.query_table(
                frame, info, filter_column=str(filter_column), filter_op=str(filter_op),
                filter_value=str(filter_value), group_by=str(group_by), value_column=str(value_column),
                aggregate=str(aggregate), sort_by=str(sort_by), descending=bool(descending), limit=int(limit))
        except fa.FileAnalysisError as exc:
            raise ToolError(str(exc)) from exc
        result["path"] = path
        return result

    path_prop = {"type": "string", "description": "Path inside the workspace, e.g. 'input/report.pdf'"}
    return [
        ToolSpec(
            name="read_pdf",
            description=(
                "Read text from a text-based PDF in the workspace (read-only). Returns a page range and next_page for continuing. "
                "Scanned PDFs return needs_ocr=true. Use it before summarising or answering questions about a PDF; never claim to have read it otherwise."
            ),
            parameters={"type": "object", "properties": {
                "path": path_prop,
                "start_page": {"type": "integer", "description": "First page to read (default 1)"},
                "max_pages": {"type": "integer", "description": "Pages to read, 1-25 (default 10)"},
            }, "required": ["path"]},
            func=read_pdf, permission=Permission.READ_ONLY, timeout=45,
        ),
        ToolSpec(
            name="inspect_table",
            description=(
                "Describe a CSV or XLSX file in the workspace (read-only): sheets, row count, column names and types, "
                "missing values, numeric summary and a 5-row preview. Use it first before querying a table."
            ),
            parameters={"type": "object", "properties": {
                "path": path_prop,
                "sheet": {"type": "string", "description": "XLSX sheet name (default: first sheet)"},
            }, "required": ["path"]},
            func=inspect_table, permission=Permission.READ_ONLY, timeout=45,
        ),
        ToolSpec(
            name="query_table",
            description=(
                "Filter, group, aggregate or sort a CSV/XLSX table (read-only, fixed operations only). "
                "filter_op is one of ==, !=, >, >=, <, <=, contains. aggregate is one of count, sum, mean, min, max "
                "(use group_by for per-group results). Call inspect_table first to learn the exact column names."
            ),
            parameters={"type": "object", "properties": {
                "path": path_prop,
                "sheet": {"type": "string", "description": "XLSX sheet name (default: first sheet)"},
                "filter_column": {"type": "string", "description": "Column to filter on"},
                "filter_op": {"type": "string", "description": "==, !=, >, >=, <, <= or contains"},
                "filter_value": {"type": "string", "description": "Value to compare with"},
                "group_by": {"type": "string", "description": "Column to group by (needs aggregate)"},
                "value_column": {"type": "string", "description": "Numeric column to aggregate"},
                "aggregate": {"type": "string", "description": "count, sum, mean, min or max"},
                "sort_by": {"type": "string", "description": "Column of the result to sort by"},
                "descending": {"type": "boolean", "description": "Sort high to low"},
                "limit": {"type": "integer", "description": "Max rows returned, 1-50 (default 20)"},
            }, "required": ["path"]},
            func=query_table, permission=Permission.READ_ONLY, timeout=45,
        ),
    ]
