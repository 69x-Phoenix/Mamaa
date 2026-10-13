import json
import re
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from PIL import Image
from pypdf import PdfWriter

from agent import file_analysis as fa
from tools import build_registry


def make_pdf(pages: list[str]) -> bytes:
    """Build a tiny valid text PDF by hand (no extra libraries needed)."""
    objects: list[bytes] = []
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    font_id = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        content = f"BT /F1 14 Tf 72 720 Td ({text}) Tj ET".encode()
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
                       f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode())
        objects.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "input").mkdir()
    (tmp_path / "output").mkdir()
    return tmp_path


@pytest.fixture
def reg(ws):
    return build_registry(ws)


def put(ws: Path, name: str, data: bytes) -> str:
    (ws / "input" / name).write_bytes(data)
    return f"input/{name}"


def run(reg, tool, **args):
    res = reg.execute(tool, args)
    json.dumps(res)  # every result must be JSON-safe for the model
    return res


# ------------------------------------------------------------------------ PDF
def test_read_pdf_pages_and_paging(ws, reg):
    path = put(ws, "a.pdf", make_pdf(["alpha page", "beta page", "gamma page"]))
    res = run(reg, "read_pdf", path=path, start_page=1, max_pages=2)
    assert res["ok"], res
    out = res["result"]
    assert out["total_pages"] == 3 and out["end_page"] == 2 and out["next_page"] == 3
    assert "alpha page" in out["text"] and "beta page" in out["text"] and "gamma" not in out["text"]
    assert not out["needs_ocr"]
    last = run(reg, "read_pdf", path=path, start_page=3)["result"]
    assert "gamma page" in last["text"] and last["next_page"] is None


def test_blank_pdf_reports_needs_ocr(ws, reg):
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    buf = BytesIO()
    writer.write(buf)
    res = run(reg, "read_pdf", path=put(ws, "blank.pdf", buf.getvalue()))
    assert res["ok"] and res["result"]["needs_ocr"] and "scanned" in res["result"]["note"]


def test_encrypted_pdf_rejected(ws, reg):
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    writer.encrypt("secret")
    buf = BytesIO()
    writer.write(buf)
    res = run(reg, "read_pdf", path=put(ws, "locked.pdf", buf.getvalue()))
    assert not res["ok"] and "Password" in res["error"]


def test_fake_pdf_and_wrong_tool_rejected(ws, reg):
    assert not run(reg, "read_pdf", path=put(ws, "fake.pdf", b"not a pdf at all"))["ok"]
    csv = put(ws, "t.csv", b"a,b\n1,2\n")
    assert not run(reg, "read_pdf", path=csv)["ok"]


def test_pdf_text_is_capped(ws, reg):
    path = put(ws, "long.pdf", make_pdf(["word " * 400] * 10))
    out = run(reg, "read_pdf", path=path, max_pages=10)["result"]
    assert out["truncated"] and len(out["text"]) <= fa.MAX_PDF_CHARS_PER_CALL and out["next_page"] is not None


# ---------------------------------------------------------------------- tables
CSV = "name,city,score,sales\nআমিন,ঢাকা,80,100\nরিমা,ঢাকা,90,250\nকরিম,চট্টগ্রাম,70,\nসালমা,চট্টগ্রাম,85,300\n".encode("utf-8")


def test_inspect_csv_with_bangla(ws, reg):
    out = run(reg, "inspect_table", path=put(ws, "s.csv", CSV))["result"]
    assert out["rows"] == 4 and [c["name"] for c in out["columns"]] == ["name", "city", "score", "sales"]
    assert {c["name"]: c["missing"] for c in out["columns"]}["sales"] == 1
    assert out["numeric_summary"]["score"]["max"] == 90 and out["numeric_summary"]["sales"]["sum"] == 650
    assert out["preview"][0]["name"] == "আমিন"


def test_query_filter_group_sort(ws, reg):
    path = put(ws, "s.csv", CSV)
    flt = run(reg, "query_table", path=path, filter_column="score", filter_op=">=", filter_value="85")["result"]
    assert flt["matched_rows"] == 2
    grp = run(reg, "query_table", path=path, group_by="city", aggregate="sum", value_column="sales",
              sort_by="sum_sales", descending=True)["result"]
    assert grp["rows"][0] == {"city": "ঢাকা", "sum_sales": 350.0}
    total = run(reg, "query_table", path=path, aggregate="mean", value_column="score")["result"]
    assert total["value"] == pytest.approx(81.25)
    assert run(reg, "query_table", path=path, aggregate="count")["result"]["value"] == 4
    contains = run(reg, "query_table", path=path, filter_column="city", filter_op="contains", filter_value="ঢাকা")["result"]
    assert contains["matched_rows"] == 2


def test_query_rejects_bad_input(ws, reg):
    path = put(ws, "s.csv", CSV)
    assert not run(reg, "query_table", path=path, filter_column="nope", filter_op="==", filter_value="1")["ok"]
    assert not run(reg, "query_table", path=path, filter_column="score", filter_op="__import__", filter_value="1")["ok"]
    assert not run(reg, "query_table", path=path, filter_column="score", filter_op=">", filter_value="abc")["ok"]
    assert not run(reg, "query_table", path=path, group_by="city")["ok"]
    assert not run(reg, "query_table", path=path, aggregate="median", value_column="score")["ok"]
    assert not run(reg, "query_table", path=path, filter_column="city", filter_op=">", filter_value="x")["ok"]


def test_semicolon_csv_and_limit(ws, reg):
    rows = "id;v\n" + "\n".join(f"{i};{i * 2}" for i in range(100))
    out = run(reg, "query_table", path=put(ws, "semi.csv", rows.encode()), limit=500)["result"]
    assert out["columns"] == ["id", "v"] and len(out["rows"]) == fa.MAX_RESULT_ROWS and out["matched_rows"] == 100


def test_xlsx_sheets(ws, reg):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame({"a": [1, 2, 3]}).to_excel(writer, sheet_name="First", index=False)
        pd.DataFrame({"b": ["x", "y"]}).to_excel(writer, sheet_name="Second", index=False)
    path = put(ws, "book.xlsx", buf.getvalue())
    first = run(reg, "inspect_table", path=path)["result"]
    assert first["sheets"] == ["First", "Second"] and first["rows"] == 3
    second = run(reg, "inspect_table", path=path, sheet="Second")["result"]
    assert second["columns"][0]["name"] == "b"
    assert not run(reg, "inspect_table", path=path, sheet="Missing")["ok"]


def test_empty_and_duplicate_column_files(ws, reg):
    assert not run(reg, "inspect_table", path=put(ws, "empty.csv", b""))["ok"]
    dup = run(reg, "inspect_table", path=put(ws, "dup.csv", b"a,a\n1,2\n"))["result"]
    names = [c["name"] for c in dup["columns"]]
    assert len(names) == 2 and len(set(names)) == 2


# --------------------------------------------------------------- safety limits
def test_path_traversal_and_missing_file(ws, reg):
    assert not run(reg, "read_pdf", path="../outside.pdf")["ok"]
    assert not run(reg, "inspect_table", path="input/none.csv")["ok"]


def test_size_limit(ws, reg, monkeypatch):
    path = put(ws, "big.csv", b"a,b\n" + b"1,2\n" * 50)
    monkeypatch.setattr(fa, "MAX_FILE_BYTES", 20)
    res = run(reg, "inspect_table", path=path)
    assert not res["ok"] and "limit" in res["error"]


def test_validate_upload_rules():
    assert fa.validate_upload("x.PDF", b"%PDF-1.4 ...") == ".pdf"
    for name, data in [("x.exe", b"MZ"), ("x.pdf", b""), ("x.png", b"%PDF"), ("x.csv", b"a\x00b")]:
        with pytest.raises(fa.FileAnalysisError):
            fa.validate_upload(name, data)


def test_inspect_image_and_upload(tmp_path):
    buf = BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, format="PNG")
    info = fa.inspect_upload("pic.png", buf.getvalue())
    assert info["format"] == "PNG" and (info["width"], info["height"]) == (40, 30) and info["mime"] == "image/png"
    with pytest.raises(fa.FileAnalysisError):
        fa.inspect_image(b"\x89PNG\r\n\x1a\nbroken")
    gif = BytesIO()
    Image.new("RGB", (5, 5)).save(gif, format="GIF")
    with pytest.raises(fa.FileAnalysisError):
        fa.validate_upload("x.png", gif.getvalue())


def test_inspect_upload_pdf_and_table():
    assert fa.inspect_upload("a.pdf", make_pdf(["hi"]))["pages"] == 1
    assert fa.inspect_upload("t.csv", CSV)["rows"] == 4


def test_policy_no_shell_or_eval_in_new_modules():
    for module in (fa, __import__("tools.analysis_tools", fromlist=["x"])):
        source = Path(module.__file__).read_text(encoding="utf-8")
        for banned in ("subprocess", "os.system", "eval(", "exec(", "__import__(", "write_bytes", "write_text"):
            assert banned not in source, f"{banned} found in {module.__name__}"
        assert not re.search(r"(?<![\w.])open\(", source), f"builtin open() used in {module.__name__}"
