"""Document tools: create PowerPoint (.pptx) and Word (.docx) files in workspace/output.

Files are always NEW (never overwritten) and never leave the workspace sandbox.
Bangla text automatically gets a Bangla-capable font so it renders correctly.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tools.files import safe_path
from tools.registry import Permission, ToolError, ToolSpec

BANGLA_FONT = "Nirmala UI"
_BANGLA = re.compile(r"[\u0980-\u09FF]")
MAX_SLIDES = 40
MAX_BULLETS = 12
MAX_SECTIONS = 60
MAX_ITEMS = 40
MAX_TEXT = 3000


def _has_bangla(text: str) -> bool:
    return bool(_BANGLA.search(text or ""))


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    return ("" if value is None else str(value)).strip()[:limit]


def _text_list(values: Any, max_items: int) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    try:
        items = list(values)[:max_items]
    except TypeError:
        return []
    return [t for t in (_text(v) for v in items) if t]


def _as_dict(item: Any, key: str) -> dict[str, Any]:
    """Models sometimes send a bare string instead of an object; accept both."""
    return item if isinstance(item, dict) else {key: item}


def _new_path(output: Path, filename: str, ext: str) -> Path:
    name = _text(filename, 120)
    if not name:
        raise ToolError("filename is required")
    if not name.lower().endswith(ext):
        if Path(name).suffix:
            raise ToolError(f"File name must end with {ext}")
        name += ext
    target = safe_path(output, name)
    if target.exists():
        raise ToolError("File already exists. Choose a new file name (existing files are never overwritten).")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


# ----------------------------------------------------------------- PowerPoint
def _style_pptx_text(frame: Any, size: int | None = None) -> None:
    from pptx.oxml.ns import qn
    from pptx.util import Pt

    for paragraph in frame.paragraphs:
        for run in paragraph.runs:
            if size:
                run.font.size = Pt(size)
            if _has_bangla(run.text):
                run.font.name = BANGLA_FONT
                props = run._r.get_or_add_rPr()
                for old in props.findall(qn("a:cs")):
                    props.remove(old)
                props.append(props.makeelement(qn("a:cs"), {"typeface": BANGLA_FONT}))


def _drop(placeholder: Any) -> None:
    element = placeholder._element
    element.getparent().remove(element)


def _bullet_size(bullets: list[str]) -> int:
    total = sum(len(b) for b in bullets)
    if len(bullets) <= 4 and total <= 200:
        return 28
    if len(bullets) <= 6 and total <= 360:
        return 24
    if len(bullets) <= 8:
        return 20
    return 18


# ----------------------------------------------------------------------- Word
def _style_docx(doc: Any) -> None:
    from docx.oxml.ns import qn

    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            if _has_bangla(run.text):
                run.font.name = BANGLA_FONT
                fonts = run._element.get_or_add_rPr().rFonts
                if fonts is not None:
                    fonts.set(qn("w:cs"), BANGLA_FONT)


def make_document_tools(workspace: Path) -> list[ToolSpec]:
    """Build create_pptx / create_docx bound to one workspace directory."""
    workspace = workspace.resolve()
    output = workspace / "output"

    def create_pptx(filename: str, title: str, slides: Any, subtitle: str = "") -> dict[str, Any]:
        try:
            from pptx import Presentation
        except ImportError as exc:
            raise ToolError("python-pptx is not installed on the server") from exc
        items = list(slides) if isinstance(slides, (list, tuple)) else []
        if not items:
            raise ToolError("Provide at least one slide in 'slides'")
        if len(items) > MAX_SLIDES:
            raise ToolError(f"Too many slides (max {MAX_SLIDES})")
        deck_title = _text(title, 200) or "Presentation"
        target = _new_path(output, filename, ".pptx")

        prs = Presentation()
        cover = prs.slides.add_slide(prs.slide_layouts[0])
        cover.shapes.title.text = deck_title
        _style_pptx_text(cover.shapes.title.text_frame, 36 if len(deck_title) > 40 else None)
        sub = _text(subtitle, 300)
        if sub:
            cover.placeholders[1].text = sub
            _style_pptx_text(cover.placeholders[1].text_frame)
        else:
            _drop(cover.placeholders[1])

        for raw in items:
            item = _as_dict(raw, "title")
            slide_title = _text(item.get("title"), 200) or "Untitled"
            bullets = _text_list(item.get("bullets"), MAX_BULLETS)
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            slide.shapes.title.text = slide_title
            _style_pptx_text(slide.shapes.title.text_frame, 30 if len(slide_title) > 45 else None)
            body = slide.placeholders[1]
            if bullets:
                frame = body.text_frame
                frame.word_wrap = True
                for i, bullet in enumerate(bullets):
                    paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
                    paragraph.text = bullet
                _style_pptx_text(frame, _bullet_size(bullets))
            else:
                _drop(body)
            notes = _text(item.get("notes"))
            if notes:
                slide.notes_slide.notes_text_frame.text = notes
        prs.save(str(target))
        return {"saved": str(target.relative_to(workspace)), "slides": len(items) + 1}

    def create_docx(filename: str, title: str, sections: Any, author: str = "") -> dict[str, Any]:
        try:
            from docx import Document
        except ImportError as exc:
            raise ToolError("python-docx is not installed on the server") from exc
        items = list(sections) if isinstance(sections, (list, tuple)) else []
        if not items:
            raise ToolError("Provide at least one section in 'sections'")
        if len(items) > MAX_SECTIONS:
            raise ToolError(f"Too many sections (max {MAX_SECTIONS})")
        doc_title = _text(title, 200) or "Document"
        target = _new_path(output, filename, ".docx")

        doc = Document()
        doc.core_properties.title = doc_title
        if _text(author, 100):
            doc.core_properties.author = _text(author, 100)
        doc.add_heading(doc_title, level=0)
        for raw in items:
            item = _as_dict(raw, "heading")
            heading = _text(item.get("heading"), 200)
            if heading:
                doc.add_heading(heading, level=1)
            for para in _text_list(item.get("paragraphs"), MAX_ITEMS):
                doc.add_paragraph(para)
            for bullet in _text_list(item.get("bullets"), MAX_ITEMS):
                doc.add_paragraph(bullet, style="List Bullet")
        _style_docx(doc)
        doc.save(str(target))
        return {"saved": str(target.relative_to(workspace)), "sections": len(items)}

    return [
        ToolSpec(
            name="create_pptx",
            description=(
                "Create a NEW PowerPoint (.pptx) presentation in workspace/output. "
                "Write real, complete slide content (3-6 short bullets per slide). Never overwrites existing files."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "File name, e.g. 'river_erosion.pptx'"},
                    "title": {"type": "string", "description": "Title shown on the first slide"},
                    "subtitle": {"type": "string", "description": "Optional subtitle (author, course, date)"},
                    "slides": {
                        "type": "array",
                        "description": "Content slides in order (max 40)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "Slide title"},
                                "bullets": {"type": "array", "items": {"type": "string"}, "description": "Short bullet points"},
                                "notes": {"type": "string", "description": "Optional speaker notes"},
                            },
                            "required": ["title"],
                        },
                    },
                },
                "required": ["filename", "title", "slides"],
            },
            func=create_pptx, permission=Permission.SAFE_WRITE, timeout=30,
        ),
        ToolSpec(
            name="create_docx",
            description=(
                "Create a NEW Word (.docx) document in workspace/output. "
                "Write real, complete text. Never overwrites existing files."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "File name, e.g. 'assignment.docx'"},
                    "title": {"type": "string", "description": "Document title"},
                    "author": {"type": "string", "description": "Optional author name"},
                    "sections": {
                        "type": "array",
                        "description": "Sections in order (max 60)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "heading": {"type": "string", "description": "Section heading"},
                                "paragraphs": {"type": "array", "items": {"type": "string"}, "description": "Body paragraphs"},
                                "bullets": {"type": "array", "items": {"type": "string"}, "description": "Bullet points"},
                            },
                            "required": ["heading"],
                        },
                    },
                },
                "required": ["filename", "title", "sections"],
            },
            func=create_docx, permission=Permission.SAFE_WRITE, timeout=30,
        ),
    ]
