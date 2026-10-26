import pytest

from agent.factory import build_agent
from agent.memory import Memory
from agent.permissions import describe_action, run_approved
from agent.providers import BaseModelProvider, ModelReply, ToolCall
from config import Settings
from tools import build_registry
from tools.registry import Permission
from tools.trading import TRADING_TOOL_NAMES


class Scripted(BaseModelProvider):
    name = "scripted"
    model = "m"

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen_tools = []

    def user_message(self, text, images=None):
        return {"role": "user", "text": text}

    def model_message(self, text):
        return {"role": "model", "text": text}

    def tool_results_message(self, results):
        return {"role": "tool", "results": [(c.name, r) for c, r in results]}

    def generate(self, messages, system_prompt, tools):
        self.seen_tools.append([t.name for t in tools])
        return self.replies.pop(0)

    def grounded_search(self, query):
        return {"answer": "", "sources": []}


def call(name, **args):
    return ModelReply("", [ToolCall(name, args)], raw={"role": "model", "call": name})


def final(text):
    return ModelReply(text, [], raw={"role": "model", "text": text})


@pytest.fixture
def settings(tmp_path):
    ws = tmp_path / "ws"
    for sub in ("input", "output"):
        (ws / sub).mkdir(parents=True)
    return Settings(gemini_api_key="x", model="m", app_password="", max_steps=4, log_level="INFO",
                    workspace_dir=ws, db_path=tmp_path / "db.sqlite")


@pytest.fixture
def reg(tmp_path):
    (tmp_path / "output").mkdir()
    return build_registry(tmp_path, memory=Memory(tmp_path / "m.db"))


def test_calculator_tools_work_through_the_registry(reg):
    ok = reg.execute("position_size", {"account_balance": 1000, "risk_percent": 1, "entry": 100, "stop_loss": 95, "side": "long"})
    assert ok["ok"] and ok["result"]["position_size_units"] == 2.0
    bad = reg.execute("position_size", {"account_balance": 1000, "risk_percent": 1, "entry": 100, "stop_loss": 105, "side": "long"})
    assert not bad["ok"] and "BELOW the entry" in bad["error"]
    assert not reg.execute("position_size", {"account_balance": 1000, "entry": 1})["ok"]          # missing arguments
    assert not reg.execute("position_size", {"account_balance": 1, "entry": 1, "stop_loss": 1, "side": "long", "hack": 1})["ok"]
    assert reg.execute("trade_stats", {"results": [1, -1, 2]})["ok"]


def test_journal_tools_only_exist_with_a_memory(tmp_path):
    names = {s.name for s in build_registry(tmp_path).specs()}
    assert {"position_size", "trade_stats"} <= names and not {"journal_add", "journal_list"} & names
    assert TRADING_TOOL_NAMES <= {s.name for s in build_registry(tmp_path, memory=Memory(tmp_path / "m.db")).specs()}


def test_trading_permissions(settings):
    agent = build_agent(settings, provider=Scripted([]))
    by_name = {s.name: s.permission for s in agent.registry.specs()}
    for name in ("position_size", "risk_reward", "liquidation_estimate", "pnl_calculator", "portfolio_risk",
                 "daily_limit_check", "trade_stats", "journal_list", "journal_stats"):
        assert by_name[name] is Permission.READ_ONLY, name
    assert by_name["journal_add"] is Permission.CONFIRM_REQUIRED and by_name["journal_delete"] is Permission.CONFIRM_REQUIRED


def test_journal_needs_approval_and_computes_r(settings):
    trade = dict(symbol="btcusdt", side="long", entry=100, stop_loss=95, size=2, pnl=20, notes="clean breakout")
    agent = build_agent(settings, provider=Scripted([call("journal_add", **trade), final("waiting for approval")]))
    agent.run("save my trade")
    assert agent.memory.journal_list() == []                      # nothing is saved before approval
    (action,) = agent.approvals.items()
    title, details = describe_action(action.tool, action.args)
    assert title == "Save trade to journal: BTCUSDT long" and "pnl 20" in details
    outcome = run_approved(agent.registry, agent.approvals.take(action.id))
    assert outcome["ok"] and "Saved trade #1" in outcome["result"]["message"] and outcome["result"]["r_multiple"] == 2.0
    saved = agent.memory.journal_list()[0]
    assert saved["symbol"] == "BTCUSDT" and saved["risk_amount"] == 10.0 and saved["r_multiple"] == 2.0


def test_journal_list_stats_delete_and_clear(settings):
    agent = build_agent(settings, provider=Scripted([]))
    memory, reg = agent.memory, agent.registry
    for pnl_r in (2.0, -1.0, 3.0):
        memory.journal_add({"symbol": "ETHUSDT", "side": "short", "entry": 50.0, "pnl": pnl_r * 10, "r_multiple": pnl_r})
    memory.journal_add({"symbol": "NOREC", "side": "long", "entry": 1.0})
    listed = reg.execute("journal_list", {"limit": 10})
    assert listed["ok"] and listed["result"]["count"] == 4
    stats = reg.execute("journal_stats", {})["result"]
    assert stats["trades"] == 3 and stats["total_result"] == 4.0 and stats["trades_without_data_skipped"] == 1
    assert reg.execute("journal_stats", {"unit": "USDT"})["result"]["total_result"] == 40.0
    refused = reg.execute("journal_delete", {"trade_id": 1})
    assert not refused["ok"]                                       # a delete never runs without approval
    ok = reg.execute("journal_delete", {"trade_id": 1}, confirm=lambda spec, args: True)
    assert ok["ok"] and not reg.execute("journal_delete", {"trade_id": 99}, confirm=lambda s, a: True)["ok"]
    memory.clear()
    assert len(memory.journal_list()) == 3                        # "Clear memory" never wipes the trading journal
    empty = build_agent(settings, provider=Scripted([]))
    assert Memory(settings.workspace_dir / "empty.db").journal_list() == [] and empty.registry.get("journal_stats") is not None


def test_journal_validation(settings):
    agent = build_agent(settings, provider=Scripted([]))
    yes = lambda spec, args: True
    bad = agent.registry.execute("journal_add", {"symbol": "X", "side": "long", "entry": 100, "stop_loss": 105}, confirm=yes)
    assert not bad["ok"] and "BELOW" in bad["error"]
    assert not agent.registry.execute("journal_add", {"symbol": " ", "side": "long", "entry": 100}, confirm=yes)["ok"]
    gross = agent.registry.execute("journal_add", {"symbol": "X", "side": "long", "entry": 100, "exit_price": 110, "size": 1}, confirm=yes)
    assert gross["ok"] and "gross" in gross["result"]["message"] and agent.memory.journal_list()[0]["pnl"] == 10.0
