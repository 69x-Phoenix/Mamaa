"""Wire settings, provider, tools and memory into a ready Agent."""
from __future__ import annotations

from agent.core import Agent
from agent.memory import Memory
from agent.permissions import ApprovalQueue, apply_approval_policy
from agent.routing import ToolRouter
from agent.providers import BaseModelProvider, GeminiProvider
from config import Settings
from tools import build_registry


def build_agent(settings: Settings, provider: BaseModelProvider | None = None) -> Agent:
    """Create an Agent. Pass a fake ``provider`` in tests."""
    if provider is None:
        provider = GeminiProvider(settings.gemini_api_key, settings.model)
    memory = Memory(settings.db_path, remote=settings.remote_db())
    registry = apply_approval_policy(build_registry(settings.workspace_dir, search_fn=provider.grounded_search, memory=memory))
    approvals = ApprovalQueue()
    agent = Agent(provider, registry, memory, max_steps=settings.max_steps, confirm=approvals.request)
    agent.approvals = approvals
    agent.router = ToolRouter(registry)
    return agent
