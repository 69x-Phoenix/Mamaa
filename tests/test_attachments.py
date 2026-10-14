from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from agent.core import Agent
from agent.memory import Memory
from agent.providers import BaseModelProvider, GeminiProvider, ModelReply
from tools import build_registry
from ui import attachments as att

CSV = "name,score\nA,10\nB,20\n".encode()


def png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (20, 10), "blue").save(buf, format="PNG")
    return buf.getvalue()


def pdf_bytes() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ----------------------------------------------------------------- file names
@pytest.mark.parametrize("raw, expected", [
    ("../../etc/passwd.pdf", "passwd.pdf"),
    ("my file (1).PDF", "my_file_1.pdf"),
    ("C:\\Users\\me\\data.csv", "data.csv"),
    ("নদী ভাঙন.xlsx", "নদী_ভাঙন.xlsx"),
    ("....csv", "file.csv"),
    ("report", "report"),
    ("a.b.csv", "a.b.csv"),
    ("UPPER.CSV", "UPPER.csv"),
])
def test_safe_input_name(raw, expected):
    assert att.safe_input_name(raw) == expected


def test_unique_path_never_overwrites(tmp_path):
    (tmp_path / "a.csv").write_text("x")
    assert att.unique_path(tmp_path, "a.csv").name == "a_2.csv"
    (tmp_path / "a_2.csv").write_text("x")
    assert att.unique_path(tmp_path, "a.csv").name == "a_3.csv"
    assert att.unique_path(tmp_path, "b.csv").name == "b.csv"


# -------------------------------------------------------------------- prepare
def test_prepare_saves_documents_and_keeps_images_in_memory(tmp_path):
    inp = tmp_path / "input"
    out = att.prepare([("t.csv", CSV), ("doc.pdf", pdf_bytes()), ("pic.png", png_bytes())], inp)
    assert out.errors == []
    assert out.saved == ["input/t.csv", "input/doc.pdf"]
    assert (inp / "t.csv").read_bytes() == CSV
    assert out.images and out.images[0][1] == "image/png" and out.image_names == ["pic.png"]
    assert not (inp / "pic.png").exists()  # images are never written to disk


def test_prepare_same_name_twice_keeps_both(tmp_path):
    inp = tmp_path / "input"
    att.prepare([("t.csv", CSV)], inp)
    second = att.prepare([("t.csv", CSV)], inp)
    assert second.saved == ["input/t_2.csv"] and (inp / "t.csv").exists()


def test_prepare_rejects_bad_files(tmp_path):
    inp = tmp_path / "input"
    out = att.prepare([("evil.exe", b"MZ"), ("fake.pdf", b"nope"), ("empty.csv", b""), ("bad.png", b"\x89PNG\r\n\x1a\nxx")], inp)
    assert out.saved == [] and out.images == [] and len(out.errors) == 4
    assert not inp.exists() or not any(inp.iterdir())


def test_prepare_limits(tmp_path):
    many = [(f"f{i}.csv", CSV) for i in range(8)]
    out = att.prepare(many, tmp_path / "input")
    assert len(out.saved) == att.MAX_FILES and any("Only the first" in e for e in out.errors)
    imgs = att.prepare([(f"p{i}.png", png_bytes()) for i in range(5)], tmp_path / "input2")
    assert len(imgs.images) == att.MAX_IMAGES and any("At most" in e for e in imgs.errors)


def test_agent_text_and_display_suffix(tmp_path):
    out = att.prepare([("t.csv", CSV), ("doc.pdf", pdf_bytes()), ("pic.png", png_bytes())], tmp_path / "input")
    text = att.agent_text("hello", out)
    assert text.startswith("hello") and "input/t.csv (use inspect_table, then query_table)" in text
    assert "input/doc.pdf (use read_pdf)" in text and "pic.png" in text
    assert att.agent_text("plain", att.Prepared()) == "plain"
    shown = att.display_suffix(out)
    assert "📎 t.csv" in shown and "📎 pic.png" in shown and att.display_suffix(att.Prepared()) == ""


# ------------------------------------------------------- provider and agent core
def test_gemini_user_message_carries_images():
    provider = GeminiProvider("dummy-key", "gemini-flash-lite-latest")
    plain = provider.user_message("hi")
    assert len(plain.parts) == 1
    with_img = provider.user_message("what is this?", images=[(png_bytes(), "image/png")])
    assert len(with_img.parts) == 2 and with_img.parts[1].inline_data.mime_type == "image/png"


class SpyProvider(BaseModelProvider):
    name = "spy"

    def __init__(self):
        self.seen = []

    def user_message(self, text, images=None):
        return {"role": "user", "text": text, "images": len(images or [])}

    def tool_results_message(self, results):
        return {"role": "tool"}

    def generate(self, messages, system_prompt, tools):
        self.seen.append([m.get("images", 0) for m in messages if m.get("role") == "user"])
        return ModelReply("done", [], raw={"role": "model", "text": "done"})


def make_agent(tmp_path, provider):
    (tmp_path / "output").mkdir(exist_ok=True)
    return Agent(provider, build_registry(tmp_path), Memory(tmp_path / "t.db"), max_steps=3)


def test_images_reach_the_model_once_and_are_not_kept_in_history(tmp_path):
    provider = SpyProvider()
    agent = make_agent(tmp_path, provider)
    result = agent.run("describe", images=[(png_bytes(), "image/png")])
    assert result.ok and provider.seen[-1] == [1]  # the model saw the image this turn
    assert agent.messages[0]["images"] == 0 and "not kept in history" in agent.messages[0]["text"]
    agent.run("and now?")
    assert provider.seen[-1] == [0, 0]  # never resent on later turns


def test_run_without_images_is_unchanged(tmp_path):
    class OldStyle(SpyProvider):  # providers that do not know about images keep working
        def user_message(self, text):
            return {"role": "user", "text": text, "images": 0}

    agent = make_agent(tmp_path, OldStyle())
    assert agent.run("hello").ok and agent.messages[0]["text"] == "hello"
