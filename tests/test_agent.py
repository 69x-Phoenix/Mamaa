from agent.core import Agent
from agent.memory import Memory
from agent.providers import BaseModelProvider, ModelReply, ProviderError, ToolCall
from tools import build_registry


class FakeProvider(BaseModelProvider):
    """Scripted model: replays prepared replies, no network needed."""

    name = "fake"

    def __init__(self, replies):
        self.replies = list(replies)

    def user_message(self, text):
        return {"role": "user", "text": text}

    def tool_results_message(self, results):
        return {"role": "tool", "results": [(c.name, r) for c, r in results]}

    def generate(self, messages, system_prompt, tools):
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def grounded_search(self, query):
        return {"answer": f"result for {query}", "sources": [{"title": "T", "url": "https://example.com"}]}


def make_agent(tmp_path, replies, max_steps=5):
    (tmp_path / "output").mkdir(exist_ok=True)
    provider = FakeProvider(replies)
    registry = build_registry(tmp_path, search_fn=provider.grounded_search)
    return Agent(provider, registry, Memory(tmp_path / "t.db"), max_steps=max_steps)


def call(name, **args):
    return ModelReply("", [ToolCall(name, args)], raw={"role": "model", "call": name})


def final(text):
    return ModelReply(text, [], raw={"role": "model", "text": text})


def test_multi_step_tool_chain(tmp_path):
    agent = make_agent(tmp_path, [call("calculator", expression="2+2"), call("web_search", query="x"), final("Answer: 4")])
    result = agent.run("do it")
    assert result.ok and result.text == "Answer: 4" and result.steps == 3
    assert [e.message for e in result.events if e.kind == "tool_done"] == ["calculator: done", "web_search: done"]
    assert agent.memory.stats() == {"tasks": 1, "tool_calls": 2}


def test_failed_tool_is_reported_to_model_and_loop_continues(tmp_path):
    agent = make_agent(tmp_path, [call("calculator", expression="1/0"), final("Could not divide")])
    result = agent.run("x")
    assert result.ok and any(not e.ok for e in result.events)


def test_provider_failure_rolls_back_history(tmp_path):
    agent = make_agent(tmp_path, [call("calculator", expression="1+1"), ProviderError("boom"), final("ok")])
    bad = agent.run("first")
    assert not bad.ok and "boom" in bad.text and agent.messages == []
    good = agent.run("second")
    assert good.ok and len(agent.messages) == 2


def test_step_limit(tmp_path):
    agent = make_agent(tmp_path, [call("calculator", expression="1+1")] * 3, max_steps=3)
    result = agent.run("loop")
    assert not result.ok and "stopped" in result.text


def test_empty_and_long_input(tmp_path):
    agent = make_agent(tmp_path, [])
    assert not agent.run("   ").ok
    assert not agent.run("x" * 9000).ok


def test_memory_clear(tmp_path):
    agent = make_agent(tmp_path, [final("hi")])
    agent.run("hello")
    agent.memory.clear()
    assert agent.memory.stats() == {"tasks": 0, "tool_calls": 0}
