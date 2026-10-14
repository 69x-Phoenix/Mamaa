"""The agent loop: plan -> call tools -> inspect -> retry -> answer."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from agent.memory import Memory
from agent.prompts import SYSTEM_PROMPT
from agent.providers import BaseModelProvider, ProviderError
from tools.registry import ConfirmFn, ToolRegistry

log = logging.getLogger(__name__)
MAX_HISTORY_MESSAGES = 30
MAX_INPUT_CHARS = 8000


@dataclass
class AgentEvent:
    """Short progress message for the UI (no hidden reasoning is exposed)."""

    kind: str  # "thinking" | "tool_start" | "tool_done"
    message: str
    ok: bool = True


@dataclass
class AgentResult:
    text: str
    ok: bool
    events: list[AgentEvent] = field(default_factory=list)
    steps: int = 0


EventCallback = Callable[[AgentEvent], None]


class Agent:
    """Keeps the conversation and runs the multi-step tool loop."""

    def __init__(
        self,
        provider: BaseModelProvider,
        registry: ToolRegistry,
        memory: Memory | None = None,
        max_steps: int = 8,
        confirm: ConfirmFn | None = None,
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.memory = memory
        self.max_steps = max_steps
        self.confirm = confirm
        self.messages: list = []
        self._turn_starts: list[int] = []

    def reset(self) -> None:
        self.messages.clear()
        self._turn_starts.clear()

    def restore(self, transcript: list[dict]) -> None:
        self.reset()
        for item in transcript:
            if item.get("role") == "user":
                self._turn_starts.append(len(self.messages))
                self.messages.append(self.provider.user_message(item["content"]))
            elif item.get("role") == "assistant" and self._turn_starts:
                self.messages.append(self.provider.model_message(item["content"]))
        self._trim_history()

    def _trim_history(self) -> None:
        """Drop the oldest whole turns (keeps tool-call/response pairs intact)."""
        while len(self.messages) > MAX_HISTORY_MESSAGES and len(self._turn_starts) > 1:
            cut = self._turn_starts[1]
            del self.messages[:cut]
            self._turn_starts = [s - cut for s in self._turn_starts[1:]]

    def run(self, user_text: str, on_event: EventCallback | None = None,
            images: list[tuple[bytes, str]] | None = None) -> AgentResult:
        """Handle one user request. Never raises for normal failures."""
        events: list[AgentEvent] = []

        def emit(kind: str, message: str, ok: bool = True) -> None:
            ev = AgentEvent(kind, message, ok)
            events.append(ev)
            if on_event:
                on_event(ev)

        user_text = user_text.strip()
        if not user_text:
            return AgentResult("Please type a request.", ok=False)
        if len(user_text) > MAX_INPUT_CHARS:
            return AgentResult(f"Request too long (max {MAX_INPUT_CHARS} characters).", ok=False)

        task_id = self.memory.start_task(user_text) if self.memory else None
        start_len = len(self.messages)
        self._turn_starts.append(start_len)
        if images:
            self.messages.append(self.provider.user_message(user_text, images=images))
        else:
            self.messages.append(self.provider.user_message(user_text))
        final_text, ok, steps = "", True, 0

        try:
            for steps in range(1, self.max_steps + 1):
                emit("thinking", "Planning..." if steps == 1 else "Reviewing results...")
                reply = self.provider.generate(self.messages, SYSTEM_PROMPT, self.registry.specs())
                if reply.raw is not None:
                    self.messages.append(reply.raw)
                if not reply.tool_calls:
                    final_text = reply.text or "(no answer)"
                    break

                results = []
                for call in reply.tool_calls:
                    emit("tool_start", f"Running {call.name}...")
                    outcome = self.registry.execute(call.name, call.args, self.confirm)
                    if task_id is not None:
                        self.memory.log_tool(task_id, call.name, bool(outcome["ok"]))
                    emit("tool_done", f"{call.name}: " + ("done" if outcome["ok"] else f"failed - {outcome['error']}"), bool(outcome["ok"]))
                    results.append((call, outcome))
                self.messages.append(self.provider.tool_results_message(results))
            else:
                ok = False
                final_text = f"I stopped after {self.max_steps} steps without finishing. Try a smaller or more specific request."
        except ProviderError as exc:
            log.error("Provider failure: %s", exc)
            del self.messages[start_len:]  # roll back so history never has dangling tool calls
            self._turn_starts.pop()
            ok, final_text = False, f"The AI model call failed: {exc}"
        except Exception as exc:  # last-resort guard: the UI must not crash
            log.exception("Agent crashed")
            del self.messages[start_len:]
            self._turn_starts.pop()
            ok, final_text = False, f"Unexpected error: {type(exc).__name__}: {exc}"

        if images and len(self.messages) > start_len:
            # Cost control: image bytes are sent once and never resent on later turns.
            self.messages[start_len] = self.provider.user_message(
                user_text + "\n[An image was attached to this message. It is not kept in history.]")
        self._trim_history()
        if task_id is not None:
            self.memory.finish_task(task_id, final_text, "done" if ok else "failed")
        return AgentResult(final_text, ok, events, steps)
