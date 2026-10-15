"""End-to-end check of the approval card flow inside the real Streamlit app (fake model, temp workspace)."""
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

from agent.providers import BaseModelProvider, ModelReply, ToolCall

APP = str(Path(__file__).resolve().parents[1] / "app.py")
CSV = "name,score\nA,10\nB,20\n".encode()


class FakeGemini(BaseModelProvider):
    name = "fake"
    model = "fake-model"
    api_calls = 0

    def __init__(self, *args, **kwargs):
        pass

    def user_message(self, text, images=None):
        return {"role": "user", "text": text, "images": len(images or [])}

    def model_message(self, text):
        return {"role": "model", "text": text}

    def tool_results_message(self, results):
        return {"role": "tool", "results": [(c.name, r) for c, r in results]}

    def generate(self, messages, system_prompt, tools):
        last = messages[-1]
        if last["role"] == "user" and "input/sales.csv" in last["text"]:
            return ModelReply("", [ToolCall("inspect_table", {"path": "input/sales.csv"})], raw={"role": "model", "call": 1})
        if last["role"] == "tool":
            return ModelReply("TABLE-ANALYSED", [], raw={"role": "model", "text": "TABLE-ANALYSED"})
        return ModelReply("PLAIN-ANSWER", [], raw={"role": "model", "text": "PLAIN-ANSWER"})

    def grounded_search(self, query):
        return {"answer": "", "sources": []}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db" / "agent.db"))
    monkeypatch.setattr("agent.factory.GeminiProvider", FakeGemini)
    return AppTest.from_file(APP, default_timeout=60), tmp_path / "ws"


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, format="PNG")
    return buf.getvalue()


def _button(at, key):
    return next(b for b in at.button if b.key == key)


def test_text_only_prompt_still_works(app):
    at, ws = app
    at.run()
    assert not at.exception
    at.chat_input[0].set_value("hello").run()
    assert not at.exception
    assert any("PLAIN-ANSWER" in m.value for m in at.markdown)


def test_approve_saves_file_and_agent_reads_it(app):
    at, ws = app
    at.session_state["pending_send"] = {"text": "summarize this", "files": [("sales.csv", CSV)]}
    at.run()
    assert not at.exception
    assert not (ws / "input" / "sales.csv").exists()  # nothing is saved before approval
    _button(at, "attach_send").click().run()
    assert not at.exception
    assert (ws / "input" / "sales.csv").read_bytes() == CSV
    assert any("TABLE-ANALYSED" in m.value for m in at.markdown)
    assert "pending_send" not in at.session_state


def test_cancel_discards_everything(app):
    at, ws = app
    at.session_state["pending_send"] = {"text": "summarize this", "files": [("sales.csv", CSV)]}
    at.run()
    _button(at, "attach_cancel").click().run()
    assert not at.exception
    assert not (ws / "input" / "sales.csv").exists()
    assert "pending_send" not in at.session_state
    assert not any("TABLE-ANALYSED" in m.value for m in at.markdown)


def test_image_is_sent_once_and_not_saved(app):
    at, ws = app
    at.session_state["pending_send"] = {"text": "what is this?", "files": [("pic.png", _png())]}
    at.run()
    _button(at, "attach_send").click().run()
    assert not at.exception
    assert not (ws / "input" / "pic.png").exists()
    provider = at.session_state["agent"].provider
    assert any("PLAIN-ANSWER" in m.value for m in at.markdown)
    assert at.session_state["agent"].messages[0]["images"] == 0
