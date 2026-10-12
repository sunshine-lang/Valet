from agent_api.tools.base import Tool, ToolContext, ToolError, ToolRegistry
from agent_api.tools.files import FILE_TOOLS
from agent_api.tools.live import LIVE_TOOLS
from agent_api.tools.probes import PROBE_TOOLS
from agent_api.tools.skills import SKILL_TOOLS


def default_registry() -> ToolRegistry:
    return ToolRegistry([*PROBE_TOOLS, *LIVE_TOOLS, *FILE_TOOLS, *SKILL_TOOLS])


__all__ = ["Tool", "ToolContext", "ToolError", "ToolRegistry", "default_registry"]
