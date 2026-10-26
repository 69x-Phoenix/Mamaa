import pytest

from agent.factory import build_agent
from agent.providers import BaseModelProvider, ModelReply
from agent.routing import ToolRouter, pack_of
from config import Settings
from tools.trading import TRADING_TOOL_NAMES

CORE = {"calculator", "current_datetime", "list_files", "read_text_file", "web_search", "read_pdf", "create_docx"}


class Spy(BaseModelProvider):
    name = "spy"
    model = "m"

    def __init__(self):
        self.seen = []

    def user_message(self, text, images=None):
        return {"role": "user", "text": text}

    def tool_results_message(self, results):
        return {"role": "tool"}

    def generate(self, messages, system_prompt, tools):
        self.seen.append({t.name for t in tools})
        return ModelReply("ok", [], raw={"role": "model", "text": "ok"})

    def grounded_search(self, query):
        return {"answer": "", "sources": []}


@pytest.fixture
def agent(tmp_path):
    ws = tmp_path / "ws"
    (ws / "output").mkdir(parents=True)
    settings = Settings(gemini_api_key="x", model="m", app_password="", max_steps=4, log_level="INFO",
                        workspace_dir=ws, db_path=tmp_path / "db.sqlite")
    built = build_agent(settings, provider=Spy())
    return built


def names(router, text):
    return {s.name for s in router.select(text)}


def test_neutral_text_hides_the_trading_pack(agent):
    router = agent.router
    chosen = names(router, "Please summarise this article for me")
    assert CORE <= chosen and not chosen & TRADING_TOOL_NAMES
    assert len(chosen) < len(agent.registry.specs())


@pytest.mark.parametrize("text", [
    "How big should my position size be?", "set my SL and TP for this long", "what is the liquidation price at 20x leverage",
    "my BTC trade lost money", "calculate PnL", "ট্রেডে কত ঝুঁকি নেব?", "লিভারেজ ১০ গুণ হলে লিকুইডেশন কত", "আমার ক্রিপ্টো জার্নাল দেখাও",
])
def test_trading_words_switch_the_pack_on(agent, text):
    assert TRADING_TOOL_NAMES <= names(agent.router, text)


def test_the_pack_stays_on_until_reset_and_all_mode_shows_everything(agent):
    router = agent.router
    names(router, "position size please")
    assert TRADING_TOOL_NAMES <= names(router, "and now with 5x?")
    router.reset()
    assert not names(router, "hello there") & TRADING_TOOL_NAMES
    router.mode = "all"
    assert {s.name for s in router.select("hello")} == {s.name for s in agent.registry.specs()}


def test_tools_outside_every_pack_are_always_offered(agent):
    assert pack_of("calculator") is None and pack_of("position_size") == "trading"
    assert CORE <= names(ToolRouter(agent.registry), "")


def test_the_agent_sends_only_the_routed_tools_and_reset_clears_the_pack(agent):
    spy = agent.provider
    agent.run("hello, what is the capital of France?")
    assert not spy.seen[-1] & TRADING_TOOL_NAMES
    agent.run("how much should I risk on this BTC long?")
    assert TRADING_TOOL_NAMES <= spy.seen[-1]
    agent.run("thanks")
    assert TRADING_TOOL_NAMES <= spy.seen[-1]            # still on within the conversation
    agent.reset()
    agent.run("tell me a joke")
    assert not spy.seen[-1] & TRADING_TOOL_NAMES
