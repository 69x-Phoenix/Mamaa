import pytest

from agent import file_analysis as fa
from tools import build_registry
from ui import attachments as att

CODE = "def hello():\n    return 'নমস্কার'\n".encode("utf-8")


def test_text_and_code_files_are_validated():
    for name in ["a.py", "b.js", "c.html", "d.css", "e.txt", "f.md", "g.json"]:
        assert fa.validate_upload(name, CODE) == "." + name.split(".")[1]
    with pytest.raises(fa.FileAnalysisError):
        fa.validate_upload("bin.py", b"abc\x00def")
    with pytest.raises(fa.FileAnalysisError):
        fa.validate_upload("big.txt", b"x" * (fa.MAX_TEXT_FILE_BYTES + 1))
    with pytest.raises(fa.FileAnalysisError):
        fa.validate_upload("run.sh", b"echo hi")  # scripts for shells are not accepted
    assert fa.inspect_upload("a.py", CODE) == {"kind": "text", "chars": len(CODE.decode("utf-8"))}


def test_prepare_saves_code_and_the_agent_can_read_it(tmp_path):
    ws = tmp_path / "ws"
    (ws / "output").mkdir(parents=True)
    out = att.prepare([("app.js", b"console.log('hi')"), ("notes.py", CODE)], ws / "input")
    assert out.errors == [] and out.saved == ["input/app.js", "input/notes.py"]
    assert "input/notes.py (use read_text_file)" in att.agent_text("review this", out)
    reg = build_registry(ws)
    assert reg.execute("read_text_file", {"path": "input/app.js"})["result"]["content"] == "console.log('hi')"
    assert "নমস্কার" in reg.execute("read_text_file", {"path": "input/notes.py"})["result"]["content"]


def test_attachment_types_include_code_but_no_executables():
    assert {"py", "js", "html", "css", "txt", "md", "json"} <= set(att.ATTACH_TYPES)
    assert not {"sh", "exe", "bat", "zip"} & set(att.ATTACH_TYPES)
