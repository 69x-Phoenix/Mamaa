"""Model provider abstraction. Swap the LLM by writing another BaseModelProvider."""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from tools.registry import ToolSpec

log = logging.getLogger(__name__)


class ProviderError(Exception):
    """The model backend failed in a way the agent cannot recover from."""


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class ModelReply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None  # provider-native message to append to history


class BaseModelProvider(ABC):
    """Interface the agent core talks to. History items are provider-native objects."""

    name: str = "base"
    model: str = ""

    @abstractmethod
    def user_message(self, text: str) -> Any: ...

    @abstractmethod
    def tool_results_message(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> Any: ...

    @abstractmethod
    def generate(self, messages: list[Any], system_prompt: str, tools: list[ToolSpec]) -> ModelReply: ...

    def grounded_search(self, query: str) -> dict[str, Any]:
        raise NotImplementedError


class GeminiProvider(BaseModelProvider):
    """Google Gemini via the official ``google-genai`` SDK."""

    name = "gemini"
    _RETRY_CODES = {429, 500, 503, 504}

    def __init__(self, api_key: str, model: str) -> None:
        self.api_calls = 0
        from google import genai  # imported lazily so tests work without a key

        self._client = genai.Client(api_key=api_key)
        self.model = model

    # ----- message builders -------------------------------------------------
    def user_message(self, text: str) -> Any:
        from google.genai import types

        return types.Content(role="user", parts=[types.Part.from_text(text=text)])

    def model_message(self, text: str) -> Any:
        from google.genai import types
        return types.Content(
            role="model",
            parts=[types.Part.from_text(text=text)],
        )

    def tool_results_message(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> Any:
        from google.genai import types

        parts = [types.Part.from_function_response(name=c.name, response=r) for c, r in results]
        return types.Content(role="user", parts=parts)

    # ----- generation -------------------------------------------------------
    def _call(self, **kwargs: Any) -> Any:
        """generate_content with small retry/backoff for rate limits and overload."""
        from google.genai import errors

        delay = 2.0
        for attempt in range(1, 3):
            try:
                self.api_calls += 1
                return self._client.models.generate_content(model=self.model, **kwargs)
            except errors.APIError as exc:
                code = getattr(exc, "code", None)
                if code in self._RETRY_CODES and attempt < 3:
                    log.warning("Gemini %s, retry %d in %.0fs", code, attempt, delay)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise ProviderError(f"Gemini API error {code}: {getattr(exc, 'message', exc)}") from exc
            except Exception as exc:
                raise ProviderError(f"{type(exc).__name__}: {exc}") from exc
        raise ProviderError("Gemini request failed after retries")

    def generate(self, messages: list[Any], system_prompt: str, tools: list[ToolSpec]) -> ModelReply:
        from google.genai import types

        declarations = [
            types.FunctionDeclaration(name=t.name, description=t.description, parameters=t.parameters)
            for t in tools
        ]
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[types.Tool(function_declarations=declarations)] if declarations else None,
            # We run the tool loop ourselves so we can enforce permissions/timeouts/logging.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        response = self._call(contents=messages, config=config)
        candidate = response.candidates[0] if response.candidates else None
        content = candidate.content if candidate else None
        if content is None or not content.parts:
            reason = getattr(candidate, "finish_reason", "unknown")
            return ModelReply(text=f"(The model returned no content. finish_reason={reason})")

        text = "".join(p.text for p in content.parts if p.text and not p.thought)
        calls = [
            ToolCall(p.function_call.name, dict(p.function_call.args or {}))
            for p in content.parts
            if p.function_call
        ]
        # Keep the native content object: Gemini 3 needs its thought signatures echoed back.
        return ModelReply(text=text, tool_calls=calls, raw=content)

    def grounded_search(self, query: str) -> dict[str, Any]:
        """Google-Search-grounded answer + source URLs (separate call, see README)."""
        from google.genai import types

        response = self._call(
            contents=query,
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
        )
        candidate = response.candidates[0] if response.candidates else None
        meta = getattr(candidate, "grounding_metadata", None)
        sources: list[dict[str, str]] = []
        seen: set[str] = set()
        for chunk in (getattr(meta, "grounding_chunks", None) or []):
            web = getattr(chunk, "web", None)
            if web and web.uri and web.uri not in seen:
                seen.add(web.uri)
                sources.append({"title": web.title or web.uri, "url": web.uri})
        return {
            "answer": response.text or "",
            "sources": sources,
            "search_queries": list(getattr(meta, "web_search_queries", None) or []),
        }
