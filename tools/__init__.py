"""Tool package: ``build_registry`` wires every tool into one registry."""
from __future__ import annotations

from pathlib import Path

from tools.calculator import CALCULATOR
from tools.files import make_file_tools
from tools.registry import Permission, ToolError, ToolRegistry, ToolSpec
from tools.system_tools import CURRENT_DATETIME
from tools.web_search import make_web_search

__all__ = ["build_registry", "Permission", "ToolError", "ToolRegistry", "ToolSpec"]


def build_registry(workspace: Path, search_fn=None) -> ToolRegistry:
    """Create the registry. ``search_fn`` comes from the model provider."""
    registry = ToolRegistry()
    registry.register(CALCULATOR)
    registry.register(CURRENT_DATETIME)
    for spec in make_file_tools(workspace):
        registry.register(spec)
    if search_fn is not None:
        registry.register(make_web_search(search_fn))
    return registry
