"""Web research tool backed by the provider's grounded search (Gemini + Google Search)."""
from __future__ import annotations

from typing import Any

from tools.registry import Permission, ToolError, ToolSpec


def make_web_search(search_fn) -> ToolSpec:
    """``search_fn(query) -> {"answer": str, "sources": [{"title","url"}]}``"""

    def web_search(query: str) -> dict[str, Any]:
        if not query.strip():
            raise ToolError("Empty query")
        try:
            data = search_fn(query.strip())
        except NotImplementedError as exc:
            raise ToolError("This model provider has no web search. Do NOT claim to have searched.") from exc
        if not data.get("sources"):
            data["note"] = "No sources were returned; treat the answer as unverified."
        data["answer"] = data.get("answer", "")[:8000]
        return data

    return ToolSpec(
        name="web_search",
        description=(
            "Search the live web (Google) for current or time-sensitive facts: news, prices, products, "
            "government/company info. Returns an answer plus source URLs. Always cite these sources."
        ),
        parameters={"type": "object", "properties": {"query": {"type": "string", "description": "A focused search question"}}, "required": ["query"]},
        func=web_search, permission=Permission.READ_ONLY, timeout=60,
    )
