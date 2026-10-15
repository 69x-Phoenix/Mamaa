"""End-to-end approval flow inside the real Streamlit app (fake model, temp workspace)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent.providers import BaseModelProvider, ModelReply, ToolCall

APP = str(Path(__file__).resolve().parents[1] / "app.py")
DOC_ARGS = {"filename": "note", "title": "T", "sections": [{"heading": "H", "paragraphs": ["p"]}]}


class FakeGemini(BaseModelProvider):
    name = "fake"
    model = "fake-model"
    api_calls = 0

    def __init__(self, *args, **kwargs):
        pass

    def user_message(self, text, images=None):
        return {"role": "user", "text": text}

    def model_message(self, text):
        return {"role": "model", "text": text}

    def tool_results_message(self, results):
        return {"role": "tool", "results": [(c.name, r) for c, r in results]}

    def generate(self, messages, system_prompt, tools):
        last = messages[-1]
        if last["role"] == "user" and "make a doc" in last["text"]:
            return ModelReply("", [ToolCall("create_docx", dict(DOC_ARGS))], raw={"role": "model", "call": 1})
        if last["role"] == "tool":
            return ModelReply("WAITING-FOR-APPROVAL", [], raw={"role": "model", "text": "WAITING-FOR-APPROVAL"})
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
    return AppTest.from_file(APP, default_timeout=60), tmp_path / "ws" / "output" / "note.docx"


def _buttons(at, prefix):
    return [b for b in at.button if b.key and b.key.startswith(prefix)]


def test_card_appears_and_nothing_is_created_before_approval(app):
    at, out = app
    at.run()
    at.chat_input[0].set_value("please make a doc").run()
    assert not at.exception
    assert len(_buttons(at, "approve_")) == 1 and len(_buttons(at, "reject_")) == 1
    assert not out.exists()
    assert any("WAITING-FOR-APPROVAL" in m.value for m in at.markdown)


def test_approve_creates_the_file_once(app):
    at, out = app
    at.run()
    at.chat_input[0].set_value("please make a doc").run()
    _buttons(at, "approve_")[0].click().run()
    assert not at.exception
    assert out.exists()
    assert any("Created" in m.value and "note.docx" in m.value for m in at.markdown)
    assert _buttons(at, "approve_") == []  # the card is gone, so it cannot run twice


def test_reject_creates_nothing(app):
    at, out = app
    at.run()
    at.chat_input[0].set_value("please make a doc").run()
    _buttons(at, "reject_")[0].click().run()
    assert not at.exception
    assert not out.exists()
    assert _buttons(at, "approve_") == []
    assert any("Rejected" in m.value for m in at.markdown)


def test_a_new_message_discards_old_cards(app):
    at, out = app
    at.run()
    at.chat_input[0].set_value("please make a doc").run()
    assert _buttons(at, "approve_")
    at.chat_input[0].set_value("just chatting").run()
    assert _buttons(at, "approve_") == []
    assert not out.exists()
