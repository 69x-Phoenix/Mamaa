"""Read-only file analysis helpers for PDF, CSV/XLSX and images.

No shell, no network, no file writes, no eval. Every function works on bytes in memory
and enforces size limits. Heavy libraries are imported lazily so the app still starts
if one of them is missing.
"""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_PDF_PAGES = 100
MAX_PDF_PAGES_PER_CALL = 25
MAX_PDF_CHARS_PER_CALL = 12_000
MAX_TABLE_ROWS = 20_000
MAX_TABLE_COLUMNS = 60
MAX_RESULT_ROWS = 50
MAX_CELL_CHARS = 100
MAX_IMAGE_PIXELS = 25_000_000

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
TABLE_EXTENSIONS = {".csv", ".xlsx"}
TEXT_EXTENSIONS = {".txt", ".md", ".py", ".js", ".html", ".css", ".json"}
MAX_TEXT_FILE_BYTES = 1024 * 1024  # 1 MB for text and code files
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS | TABLE_EXTENSIONS | TEXT_EXTENSIONS

FILTER_OPS = {"==", "!=", ">", ">=", "<", "<=", "contains"}
AGGREGATES = {"count", "sum", "mean", "min", "max"}


class FileAnalysisError(ValueError):
    """An expected problem with a file; the message is safe to show to the user or model."""


# ----------------------------------------------------------------- validation
def _signature_ok(suffix: str, data: bytes) -> bool:
    if suffix == ".pdf":
        return data[:1024].lstrip().startswith(b"%PDF")
    if suffix == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if suffix == ".xlsx":
        return data.startswith(b"PK\x03\x04")
    if suffix == ".csv" or suffix in TEXT_EXTENSIONS:
        return b"\x00" not in data[:4096]
    return False


def validate_upload(filename: str, data: bytes) -> str:
    """Check extension, size and file signature. Returns the lower-case extension."""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise FileAnalysisError(f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}")
    if not data:
        raise FileAnalysisError("The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise FileAnalysisError(f"File exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit.")
    if suffix in TEXT_EXTENSIONS and len(data) > MAX_TEXT_FILE_BYTES:
        raise FileAnalysisError("Text and code files are limited to 1 MB.")
    if not _signature_ok(suffix, data):
        raise FileAnalysisError(f"The content does not look like a real {suffix} file.")
    return suffix


# ------------------------------------------------------------------------ PDF
def read_pdf(data: bytes, start_page: int = 1, max_pages: int = 10,
             max_chars: int = MAX_PDF_CHARS_PER_CALL) -> dict[str, Any]:
    """Extract text from a page range of a text-based PDF."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise FileAnalysisError("The pypdf package is not installed on the server.") from exc
    try:
        reader = PdfReader(BytesIO(data))
        encrypted = reader.is_encrypted
        total = 0 if encrypted else len(reader.pages)
    except Exception as exc:
        raise FileAnalysisError("Could not read this PDF (it may be damaged).") from exc
    if encrypted:
        raise FileAnalysisError("Password-protected PDFs are not supported yet.")
    if total == 0:
        raise FileAnalysisError("This PDF has no pages.")
    if total > MAX_PDF_PAGES:
        raise FileAnalysisError(f"PDF exceeds the {MAX_PDF_PAGES}-page limit ({total} pages).")

    start = min(max(int(start_page), 1), total)
    count = max(1, min(int(max_pages), MAX_PDF_PAGES_PER_CALL))
    end = min(start + count - 1, total)
    max_chars = max(500, min(int(max_chars), MAX_PDF_CHARS_PER_CALL))

    parts: list[str] = []
    used = 0
    truncated = False
    last_read = start - 1
    for number in range(start, end + 1):
        try:
            text = (reader.pages[number - 1].extract_text() or "").strip()
        except Exception:
            text = ""
        if text:
            block = f"[Page {number}]\n{text}"
            separator = 2 if parts else 0  # the "\n\n" joining pages
            room = max_chars - used - separator
            if len(block) > room:
                block = block[: max(room, 0)]
                truncated = True
            if block:
                parts.append(block)
                used += len(block) + separator
        last_read = number
        if truncated:
            break
    text_out = "\n\n".join(parts)
    if truncated:
        next_page: int | None = last_read
    else:
        next_page = last_read + 1 if last_read < total else None
    return {
        "kind": "pdf", "total_pages": total, "start_page": start, "end_page": last_read,
        "text": text_out, "truncated": truncated, "next_page": next_page,
        "needs_ocr": not text_out.strip(),
    }


# ---------------------------------------------------------------------- tables
def _unique_names(columns: list[Any]) -> list[str]:
    seen: dict[str, int] = {}
    names = []
    for col in columns:
        base = str(col)
        seen[base] = seen.get(base, 0) + 1
        names.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return names


def load_table(data: bytes, suffix: str, sheet: str = "") -> tuple[Any, dict[str, Any]]:
    """Load a CSV or XLSX into a DataFrame (row and column limits applied)."""
    try:
        import pandas as pd
    except ImportError as exc:
        raise FileAnalysisError("The pandas package is not installed on the server.") from exc
    info: dict[str, Any] = {"kind": "table", "sheet": None, "sheets": None}
    try:
        if suffix == ".csv":
            frame = None
            for encoding in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    frame = pd.read_csv(BytesIO(data), nrows=MAX_TABLE_ROWS + 1, encoding=encoding,
                                        sep=None, engine="python", on_bad_lines="skip")
                    break
                except UnicodeDecodeError:
                    continue
            if frame is None:
                raise FileAnalysisError("Could not decode this CSV file.")
        elif suffix == ".xlsx":
            book = pd.ExcelFile(BytesIO(data), engine="openpyxl")
            sheets = [str(s) for s in book.sheet_names]
            chosen = sheet or sheets[0]
            if chosen not in sheets:
                raise FileAnalysisError(f"Sheet '{chosen}' not found. Available sheets: {sheets}")
            frame = book.parse(chosen, nrows=MAX_TABLE_ROWS + 1)
            info["sheet"], info["sheets"] = chosen, sheets
        else:
            raise FileAnalysisError(f"Unsupported table type '{suffix}'.")
    except FileAnalysisError:
        raise
    except pd.errors.EmptyDataError as exc:
        raise FileAnalysisError("The table file has no data.") from exc
    except Exception as exc:
        raise FileAnalysisError(f"Could not read this {suffix} file ({type(exc).__name__}).") from exc

    info["rows_truncated"] = len(frame) > MAX_TABLE_ROWS
    frame = frame.head(MAX_TABLE_ROWS)
    info["columns_truncated"] = frame.shape[1] > MAX_TABLE_COLUMNS
    frame = frame.iloc[:, :MAX_TABLE_COLUMNS].copy()
    frame.columns = _unique_names(list(frame.columns))
    return frame, info


def _clip(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_CELL_CHARS:
        return value[:MAX_CELL_CHARS] + "..."
    if isinstance(value, dict):
        return {k: _clip(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clip(v) for v in value]
    return value


def _records(frame: Any) -> list[dict[str, Any]]:
    """DataFrame -> plain JSON-safe list of dicts (NaN becomes null, long text is clipped)."""
    return _clip(json.loads(frame.to_json(orient="records", date_format="iso", force_ascii=False)))


def summarize_table(frame: Any, info: dict[str, Any]) -> dict[str, Any]:
    columns = [{"name": c, "dtype": str(frame[c].dtype), "missing": int(frame[c].isna().sum()),
                "unique": int(frame[c].nunique(dropna=True))} for c in frame.columns]
    numeric = frame.select_dtypes("number")
    numeric_summary: dict[str, Any] = {}
    if not numeric.empty:
        stats = numeric.describe().T[["count", "mean", "min", "max"]]
        stats["sum"] = numeric.sum()
        numeric_summary = json.loads(stats.to_json(orient="index"))
    return {
        "kind": "table", "sheet": info.get("sheet"), "sheets": info.get("sheets"),
        "rows": int(len(frame)), "columns": columns, "numeric_summary": numeric_summary,
        "preview": _records(frame.head(5)),
        "rows_truncated": info["rows_truncated"], "columns_truncated": info["columns_truncated"],
    }


def query_table(frame: Any, info: dict[str, Any], *, filter_column: str = "", filter_op: str = "",
                filter_value: str = "", group_by: str = "", value_column: str = "", aggregate: str = "",
                sort_by: str = "", descending: bool = False, limit: int = 20) -> dict[str, Any]:
    """Filter, group, aggregate and sort with a fixed allow-list of operations (no eval)."""
    import pandas as pd

    def need(column: str) -> None:
        if column not in frame.columns:
            raise FileAnalysisError(f"Unknown column '{column}'. Columns: {list(frame.columns)}")

    work = frame
    if filter_column:
        need(filter_column)
        if filter_op not in FILTER_OPS:
            raise FileAnalysisError(f"Unsupported filter_op '{filter_op}'. Use one of: {sorted(FILTER_OPS)}")
        series = work[filter_column]
        if filter_op == "contains":
            mask = series.astype(str).str.contains(str(filter_value), case=False, regex=False, na=False)
        elif pd.api.types.is_numeric_dtype(series):
            try:
                number = float(filter_value)
            except (TypeError, ValueError) as exc:
                raise FileAnalysisError(f"filter_value '{filter_value}' is not a number") from exc
            mask = {"==": series == number, "!=": series != number, ">": series > number,
                    ">=": series >= number, "<": series < number, "<=": series <= number}[filter_op]
        else:
            text = series.astype(str).str.strip()
            target = str(filter_value).strip()
            if filter_op not in {"==", "!="}:
                raise FileAnalysisError(f"'{filter_op}' needs a numeric column; '{filter_column}' is text")
            mask = (text == target) if filter_op == "==" else (text != target)
        work = work[mask]

    matched = int(len(work))
    result_frame = work
    extra: dict[str, Any] = {}
    if aggregate and aggregate not in AGGREGATES:
        raise FileAnalysisError(f"Unsupported aggregate '{aggregate}'. Use one of: {sorted(AGGREGATES)}")
    if group_by:
        need(group_by)
        if not aggregate:
            raise FileAnalysisError("group_by needs an aggregate (count, sum, mean, min or max)")
        if aggregate == "count":
            result_frame = work.groupby(group_by, dropna=False).size().reset_index(name="count")
        else:
            if not value_column:
                raise FileAnalysisError("value_column is required for this aggregate")
            need(value_column)
            values = pd.to_numeric(work[value_column], errors="coerce")
            grouped = work.assign(__value=values).groupby(group_by, dropna=False)["__value"].agg(aggregate)
            result_frame = grouped.reset_index().rename(columns={"__value": f"{aggregate}_{value_column}"})
    elif aggregate:
        if aggregate == "count":
            extra = {"aggregate": "count", "value": matched}
        else:
            if not value_column:
                raise FileAnalysisError("value_column is required for this aggregate")
            need(value_column)
            values = pd.to_numeric(work[value_column], errors="coerce")
            value = getattr(values, aggregate)()
            extra = {"aggregate": f"{aggregate}({value_column})", "value": None if pd.isna(value) else float(value)}
        result_frame = work.head(0)

    if sort_by:
        if sort_by not in result_frame.columns:
            raise FileAnalysisError(f"Cannot sort by '{sort_by}'. Columns: {list(result_frame.columns)}")
        result_frame = result_frame.sort_values(sort_by, ascending=not descending)
    limit = max(1, min(int(limit), MAX_RESULT_ROWS))
    out: dict[str, Any] = {
        "matched_rows": matched, "columns": list(result_frame.columns),
        "rows": [] if extra else _records(result_frame.head(limit)),
        "rows_truncated_in_source": info["rows_truncated"],
    }
    out.update(extra)
    return out


# ---------------------------------------------------------------------- images
def inspect_image(data: bytes) -> dict[str, Any]:
    """Validate a PNG/JPEG and report its format and size (no AI call here)."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise FileAnalysisError("The Pillow package is not installed on the server.") from exc
    try:
        with Image.open(BytesIO(data)) as image:
            fmt, (width, height) = image.format, image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise FileAnalysisError(f"Image is too large ({width}x{height} pixels).")
            image.verify()
    except FileAnalysisError:
        raise
    except Exception as exc:
        raise FileAnalysisError("Could not read this image (it may be damaged).") from exc
    if fmt not in {"PNG", "JPEG"}:
        raise FileAnalysisError("Only PNG and JPEG images are supported.")
    return {"kind": "image", "format": fmt, "width": width, "height": height,
            "mime": "image/png" if fmt == "PNG" else "image/jpeg"}


def inspect_upload(filename: str, data: bytes) -> dict[str, Any]:
    """One-call check used by the upload UI: validate, then describe the file."""
    suffix = validate_upload(filename, data)
    if suffix in PDF_EXTENSIONS:
        probe = read_pdf(data, 1, 3)
        return {"kind": "pdf", "pages": probe["total_pages"], "needs_ocr": probe["needs_ocr"]}
    if suffix in IMAGE_EXTENSIONS:
        return inspect_image(data)
    if suffix in TEXT_EXTENSIONS:
        return {"kind": "text", "chars": len(data.decode("utf-8", errors="replace"))}
    frame, info = load_table(data, suffix)
    return summarize_table(frame, info)
