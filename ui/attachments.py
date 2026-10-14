"""UI-side helpers for chat attachments (PDF, CSV, XLSX, PNG, JPG).

Nothing here talks to the AI. Documents are validated, then saved (never overwriting) into the
workspace input folder; images are validated and kept in memory only. The caller must obtain the
user's approval first (see render_attachment_approval in ui/components.py).
"""
from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path

from agent import file_analysis as fa

ATTACH_TYPES = ["pdf", "png", "jpg", "jpeg", "csv", "xlsx"]
MAX_FILES = 5
MAX_IMAGES = 3
UPLOAD_LIMIT_MB = 15
DEFAULT_REQUEST = "Please analyze the attached file(s) and summarize the key points."

_UNSAFE = re.compile(r"[^\w.\-\u0980-\u09FF]+")
_EXT = re.compile(r"\.([A-Za-z0-9]{1,5})$")


@dataclass
class Prepared:
    saved: list[str] = field(default_factory=list)  # workspace-relative paths, e.g. "input/report.pdf"
    images: list[tuple[bytes, str]] = field(default_factory=list)  # (bytes, mime) kept in memory only
    image_names: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def attach_kwargs() -> dict:
    """Arguments for st.chat_input that enable attachments on Streamlit versions that support them."""
    import streamlit as st

    params = inspect.signature(st.chat_input).parameters
    if "accept_file" not in params:
        return {}
    kwargs: dict = {"accept_file": "multiple", "file_type": list(ATTACH_TYPES)}
    if "max_upload_size" in params:
        kwargs["max_upload_size"] = UPLOAD_LIMIT_MB
    return kwargs


def safe_input_name(name: str) -> str:
    """Keep only the base name; replace unsafe characters (Bangla letters are kept)."""
    base = Path(str(name).replace("\\", "/")).name
    match = _EXT.search(base)
    suffix = match.group(0).lower() if match else ""
    stem = _UNSAFE.sub("_", base[: len(base) - len(suffix)]).strip("._") or "file"
    return stem[:60] + suffix


def unique_path(directory: Path, name: str) -> Path:
    """A path in ``directory`` that does not exist yet (existing files are never overwritten)."""
    target = directory / name
    stem, suffix, counter = target.stem, target.suffix, 2
    while target.exists():
        target = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    return target


def prepare(files: list[tuple[str, bytes]], input_dir: Path) -> Prepared:
    """Validate attachments; save documents to ``input_dir``; keep images in memory."""
    out = Prepared()
    if len(files) > MAX_FILES:
        out.errors.append(f"Only the first {MAX_FILES} files are used.")
        files = files[:MAX_FILES]
    for name, data in files:
        label = Path(str(name).replace("\\", "/")).name or "file"
        try:
            suffix = fa.validate_upload(label, data)
            if suffix in fa.IMAGE_EXTENSIONS:
                if len(out.images) >= MAX_IMAGES:
                    raise fa.FileAnalysisError(f"At most {MAX_IMAGES} images per message.")
                info = fa.inspect_image(data)
                out.images.append((data, info["mime"]))
                out.image_names.append(label)
                continue
            if suffix == ".pdf":
                fa.read_pdf(data, 1, 1)  # readable, not encrypted, not too long
            else:
                fa.load_table(data, suffix)  # parses as a table
            input_dir.mkdir(parents=True, exist_ok=True)
            target = unique_path(input_dir, safe_input_name(label))
            target.write_bytes(data)
            out.saved.append(f"input/{target.name}")
        except fa.FileAnalysisError as exc:
            out.errors.append(f"{label}: {exc}")
    return out


def display_suffix(prepared: Prepared) -> str:
    """Lines appended to the visible chat message."""
    names = [Path(p).name for p in prepared.saved] + prepared.image_names
    lines = [f"📎 {n}" for n in names] + [f"⚠️ {e}" for e in prepared.errors]
    return "\n\n" + "  \n".join(lines) if lines else ""


def agent_text(prompt: str, prepared: Prepared) -> str:
    """The request the agent sees: the user's text plus a short note about the attachments."""
    notes = []
    for path in prepared.saved:
        use = "read_pdf" if path.lower().endswith(".pdf") else "inspect_table, then query_table"
        notes.append(f"- {path} (use {use})")
    if prepared.image_names:
        notes.append("- Image(s) attached directly to this message: " + ", ".join(prepared.image_names))
    if not notes:
        return prompt
    return prompt + "\n\n[The user attached files for you to use:\n" + "\n".join(notes) + "\n]"
