import pytest

from tools import Permission, ToolRegistry, ToolSpec, build_registry
from tools.calculator import calculate
from tools.files import safe_path
from tools.registry import ToolError


def test_calculator_basic():
    assert calculate("(1250*12)/100")["result"] == 150
    assert calculate("sqrt(16) + 2**3")["result"] == 12


@pytest.mark.parametrize("bad", ["__import__('os').system('ls')", "9**9**9", "1/0", "2^3", "open('x')", "a+1"])
def test_calculator_rejects_unsafe_or_invalid(bad):
    with pytest.raises(ToolError):
        calculate(bad)


def test_path_traversal_blocked(tmp_path):
    with pytest.raises(ToolError):
        safe_path(tmp_path, "../secret.txt")
    with pytest.raises(ToolError):
        safe_path(tmp_path, "/etc/passwd")
    assert safe_path(tmp_path, "input/a.txt").is_relative_to(tmp_path.resolve())


def test_file_tools_roundtrip_and_no_overwrite(tmp_path):
    (tmp_path / "input").mkdir()
    (tmp_path / "output").mkdir()
    reg = build_registry(tmp_path)
    assert reg.execute("write_text_file", {"path": "a.md", "content": "hello"})["ok"]
    again = reg.execute("write_text_file", {"path": "a.md", "content": "x"})
    assert not again["ok"] and "already exists" in again["error"]
    (tmp_path / "input" / "n.txt").write_text("data")
    assert reg.execute("read_text_file", {"path": "input/n.txt"})["result"]["content"] == "data"
    assert not reg.execute("read_text_file", {"path": "../../etc/passwd"})["ok"]
    assert not reg.execute("write_text_file", {"path": "../escape.txt", "content": "x"})["ok"]
    listing = reg.execute("list_files", {"path": "."})["result"]["entries"]
    assert {e["name"] for e in listing} == {"input", "output"}


def test_registry_errors_do_not_raise():
    reg = ToolRegistry()
    reg.register(ToolSpec("boom", "d", {"type": "object", "properties": {}}, lambda: 1 / 0))
    reg.register(ToolSpec("danger", "d", {"type": "object", "properties": {}}, lambda: "ran", Permission.CONFIRM_REQUIRED))
    reg.register(ToolSpec("slow", "d", {"type": "object", "properties": {}}, lambda: __import__("time").sleep(2), timeout=0.2))
    assert "ZeroDivisionError" in reg.execute("boom", {})["error"]
    assert "Unknown tool" in reg.execute("nope", {})["error"]
    assert "timed out" in reg.execute("slow", {})["error"]
    assert not reg.execute("danger", {})["ok"]
    assert reg.execute("danger", {}, confirm=lambda s, a: True)["ok"]
    assert "Bad arguments" in reg.execute("boom", {"x": 1})["error"]
