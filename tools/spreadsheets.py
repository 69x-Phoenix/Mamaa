"""Spreadsheet tool: create a NEW Excel (.xlsx) workbook in workspace/output.

Like every file-creating tool it needs the user's approval before it runs (see agent/permissions.py).
Values are written as data only: text that starts with "=" is stored as plain text, never as a formula.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tools.documents import BANGLA_FONT, THEMES, _as_dict, _has_bangla, _new_path, _text
from tools.registry import Permission, ToolError, ToolSpec

MAX_SHEETS = 10
MAX_ROWS = 5000
MAX_COLS = 50
MAX_CELL_CHARS = 2000
_INT = re.compile(r"-?(0|[1-9]\d{0,14})")
_FLOAT = re.compile(r"-?(0|[1-9]\d{0,14})\.\d{1,10}")
_BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


def _cell_value(value: Any) -> Any:
    """Numbers sent as text become numbers; identifiers like '007' and everything else stay text."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()[:MAX_CELL_CHARS]
    if _INT.fullmatch(text):
        return int(text)
    if _FLOAT.fullmatch(text):
        return float(text)
    return text


def _sheet_name(raw: Any, used: set[str]) -> str:
    name = _BAD_SHEET_CHARS.sub(" ", _text(raw, 60)).strip().strip("'") or "Sheet"
    name = name[:31]
    base, counter = name, 2
    while name.lower() in used:
        suffix = f"_{counter}"
        name = base[: 31 - len(suffix)] + suffix
        counter += 1
    used.add(name.lower())
    return name


def make_spreadsheet_tools(workspace: Path) -> list[ToolSpec]:
    """Build the create_xlsx tool bound to one workspace directory."""
    workspace = workspace.resolve()
    output = workspace / "output"

    def create_xlsx(filename: str, sheets: Any, theme: str = "academic") -> dict[str, Any]:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
        except ImportError as exc:
            raise ToolError("openpyxl is not installed on the server") from exc
        items = list(sheets) if isinstance(sheets, (list, tuple)) else []
        if not items:
            raise ToolError("Provide at least one sheet in 'sheets'")
        if len(items) > MAX_SHEETS:
            raise ToolError(f"Too many sheets (max {MAX_SHEETS})")
        theme_name = (_text(theme, 20) or "academic").lower()
        if theme_name not in THEMES:
            raise ToolError(f"Unknown theme '{theme_name}'. Use one of: {sorted(THEMES)}")
        colors = THEMES[theme_name]
        target = _new_path(output, filename, ".xlsx")

        book = Workbook()
        book.remove(book.active)
        used: set[str] = set()
        total_rows = 0
        for raw in items:
            item = _as_dict(raw, "name")
            columns = [_text(c, 100) for c in (item.get("columns") if isinstance(item.get("columns"), list) else [])]
            raw_rows = item.get("rows") if isinstance(item.get("rows"), list) else []
            if len(raw_rows) > MAX_ROWS:
                raise ToolError(f"Too many rows in one sheet (max {MAX_ROWS})")
            rows = [list(r) if isinstance(r, (list, tuple)) else [r] for r in raw_rows]
            width = max([len(columns)] + [len(r) for r in rows])
            if width == 0:
                raise ToolError("A sheet needs at least one column or row")
            if width > MAX_COLS:
                raise ToolError(f"Too many columns (max {MAX_COLS})")

            sheet = book.create_sheet(_sheet_name(item.get("name"), used))
            if columns:
                sheet.append(columns)
                for cell in sheet[1]:
                    cell.font = Font(name=BANGLA_FONT if _has_bangla(str(cell.value)) else None, bold=True, color="FFFFFF")
                    cell.fill = PatternFill("solid", fgColor=colors["dark"])
                    cell.alignment = Alignment(vertical="center")
                sheet.freeze_panes = "A2"
            for row in rows:
                sheet.append([_cell_value(v) for v in row])
            for row in sheet.iter_rows(min_row=2 if columns else 1):
                for cell in row:
                    if isinstance(cell.value, str):
                        cell.data_type = "s"  # never let text become a formula
                        if _has_bangla(cell.value):
                            cell.font = Font(name=BANGLA_FONT)
            if columns:
                sheet.auto_filter.ref = f"A1:{get_column_letter(width)}{max(len(rows) + 1, 1)}"
            for index in range(1, width + 1):
                longest = 0
                for row in sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 200), min_col=index, max_col=index):
                    value = row[0].value
                    longest = max(longest, len(str(value)) if value is not None else 0)
                sheet.column_dimensions[get_column_letter(index)].width = min(max(longest * 1.2 + 2, 8), 60)
            total_rows += len(rows)
        book.properties.title = target.stem
        book.save(str(target))
        return {"saved": str(target.relative_to(workspace)), "sheets": len(items), "rows": total_rows}

    return [
        ToolSpec(
            name="create_xlsx",
            description=(
                "Create a NEW Excel (.xlsx) workbook in workspace/output. Never overwrites existing files. "
                "Use for tables, budgets, schedules, comparisons or exported analysis results. "
                "Put the header names in 'columns' and one list per row in 'rows'. Write every cell as text; "
                "numbers are converted automatically. Formulas are not supported (text starting with '=' stays text), "
                "so compute totals yourself (use the calculator tool) and write the results."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "File name, e.g. 'budget.xlsx'"},
                    "theme": {"type": "string", "description": "'academic' (navy header) or 'modern' (teal header)", "enum": ["academic", "modern"]},
                    "sheets": {
                        "type": "array",
                        "description": "Worksheets in order (max 10)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Sheet name (max 31 characters)"},
                                "columns": {"type": "array", "items": {"type": "string"}, "description": "Header row"},
                                "rows": {
                                    "type": "array",
                                    "description": "Data rows (max 5000); each row is a list of cell values",
                                    "items": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                            "required": ["name", "columns", "rows"],
                        },
                    },
                },
                "required": ["filename", "sheets"],
            },
            func=create_xlsx, permission=Permission.SAFE_WRITE, timeout=30,
        ),
    ]
