"""The Settings switch really changes which tools the model is offered (end to end, fake model)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent.providers import BaseModelProvider, ModelReply
from tools.trading import TRADING_TOOL_NAMES

APP = str(Path(__file__).resolve().parents[1] / "app.py")
SEEN: list[set[str]] = []


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
        return {"role": "tool"}

    def generate(self, messages, system_prompt, tools):
        SEEN.append({t.name for t in tools})
        return ModelReply("DONE-OK", [], raw={"role": "model", "text": "DONE-OK"})

    def grounded_search(self, query):
        return {"answer": "", "sources": []}


@pytest.fixture
def app(tmp_path, monkeypatch):
    SEEN.clear()
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db" / "agent.db"))
    monkeypatch.setattr("agent.factory.GeminiProvider", FakeGemini)
    return AppTest.from_file(APP, default_timeout=60)


def test_auto_mode_hides_trading_tools_until_needed(app):
    app.run()
    assert not app.exception
    app.chat_input[0].set_value("tell me about river erosion").run()
    assert not app.exception and not SEEN[-1] & TRADING_TOOL_NAMES
    app.chat_input[0].set_value("what position size should I use for a BTC long").run()
    assert TRADING_TOOL_NAMES <= SEEN[-1]


def test_all_tools_switch_offers_everything(app):
    app.run()
    app.radio(key="tool_mode").set_value("All tools").run()
    app.chat_input[0].set_value("tell me about river erosion").run()
    assert not app.exception and TRADING_TOOL_NAMES <= SEEN[-1]
