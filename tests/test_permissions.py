import pytest

from agent.factory import build_agent
from agent.permissions import (
    READ_ONLY_TOOLS, ApprovalQueue, apply_approval_policy, approval_confirm, describe_action, fingerprint, run_approved,
)
from agent.providers import BaseModelProvider, ModelReply, ToolCall
from config import Settings
from tools import build_registry
from tools.registry import Permission, ToolSpec

DOC_ARGS = {"filename": "note", "title": "T", "sections": [{"heading": "H", "paragraphs": ["p"]}]}


class Scripted(BaseModelProvider):
    name = "scripted"
    model = "m"

    def __init__(self, replies):
        self.replies = list(replies)

    def user_message(self, text, images=None):
        return {"role": "user", "text": text}

    def model_message(self, text):
        return {"role": "model", "text": text}

    def tool_results_message(self, results):
        return {"role": "tool", "results": [(c.name, r) for c, r in results]}

    def generate(self, messages, system_prompt, tools):
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


def make(settings, replies):
    return build_agent(settings, provider=Scripted(replies))


# ---------------------------------------------------------------------- policy
def test_everything_except_known_read_only_tools_needs_approval(settings):
    agent = make(settings, [])
    by_name = {s.name: s.permission for s in agent.registry.specs()}
    assert {"write_text_file", "create_pptx", "create_docx"} <= set(by_name)
    for name, permission in by_name.items():
        expected = Permission.READ_ONLY if name in READ_ONLY_TOOLS else Permission.CONFIRM_REQUIRED
        assert permission is expected, name
    assert Permission.SAFE_WRITE not in by_name.values()


def test_unknown_tools_default_to_approval(tmp_path):
    registry = build_registry(tmp_path)
    schema = {"type": "object", "properties": {}}
    registry.register(ToolSpec("sneaky_write", "d", schema, lambda: "x", Permission.SAFE_WRITE))
    registry.register(ToolSpec("sneaky_read", "d", schema, lambda: "x", Permission.READ_ONLY))
    apply_approval_policy(registry)
    assert registry.get("sneaky_write").permission is Permission.CONFIRM_REQUIRED
    assert registry.get("sneaky_read").permission is Permission.CONFIRM_REQUIRED  # not on the read-only allow-list


def test_there_is_no_command_or_shell_tool(settings):
    names = [s.name for s in make(settings, []).registry.specs()]
    assert not [n for n in names if any(w in n for w in ("shell", "exec", "command", "subprocess", "bash"))]


# ------------------------------------------------------------------ the approval flow
def test_write_is_blocked_until_approved(settings):
    agent = make(settings, [call("create_docx", **DOC_ARGS), final("I prepared it, please approve.")])
    result = agent.run("make a doc")
    out = settings.workspace_dir / "output" / "note.docx"
    assert result.ok and not out.exists()
    pending = agent.approvals.items()
    assert len(pending) == 1 and "note" in pending[0].title and pending[0].tool == "create_docx"
    outcome = run_approved(agent.registry, agent.approvals.take(pending[0].id))
    assert outcome["ok"] and out.exists()


def test_same_request_twice_makes_one_card(settings):
    agent = make(settings, [call("create_docx", **DOC_ARGS), call("create_docx", **DOC_ARGS), final("waiting")])
    agent.run("make a doc")
    assert len(agent.approvals.items()) == 1


def test_an_approval_works_only_once_and_only_for_the_exact_action(settings):
    agent = make(settings, [call("create_docx", **DOC_ARGS), final("waiting")])
    agent.run("make a doc")
    action = agent.approvals.items()[0]
    confirm = approval_confirm(action)
    spec = agent.registry.get("create_docx")
    assert confirm(spec, dict(action.args)) is True
    assert confirm(spec, {**action.args, "filename": "other"}) is False
    assert confirm(agent.registry.get("write_text_file"), dict(action.args)) is False
    assert agent.approvals.take(action.id) is not None and agent.approvals.take(action.id) is None


def test_rejecting_creates_nothing_and_new_work_drops_old_cards(settings):
    agent = make(settings, [call("create_docx", **DOC_ARGS), final("waiting")])
    agent.run("make a doc")
    agent.approvals.take(agent.approvals.items()[0].id)  # rejected = simply discarded
    assert not (settings.workspace_dir / "output" / "note.docx").exists()
    agent2 = make(settings, [call("create_docx", **DOC_ARGS), final("waiting")])
    agent2.run("make a doc")
    assert agent2.approvals.items()
    agent2.reset()
    assert agent2.approvals.items() == []


def test_invalid_calls_do_not_create_cards(settings):
    agent = make(settings, [call("create_docx", filename="x"), final("oops")])  # missing required arguments
    agent.run("bad")
    assert agent.approvals.items() == []


def test_describe_action_and_fingerprint():
    title, details = describe_action("create_pptx", {"filename": "river.pptx", "slides": [{"title": "One"}, {"title": "Two"}], "theme": "modern"})
    assert "river.pptx" in title and "2 content slides" in details[0] and "modern" in details[0] and "- One" in details
    assert "output/a.md" in describe_action("write_text_file", {"path": "a.md", "content": "hello"})[0]
    assert fingerprint("t", {"a": 1, "b": 2}) == fingerprint("t", {"b": 2, "a": 1})
    assert fingerprint("t", {"a": 1}) != fingerprint("t", {"a": 2})
    queue = ApprovalQueue()
    spec = ToolSpec("create_docx", "d", {"type": "object", "properties": {}}, lambda: 1, Permission.CONFIRM_REQUIRED)
    assert queue.request(spec, {"filename": "n"}) is False and len(queue.items()) == 1
