"""Adapt the sandbox's freeform patch tool to Chat Completions function calling."""

from typing import Any

from agents import FunctionTool, Tool, function_tool
from agents.sandbox.capabilities import Filesystem
from agents.sandbox.capabilities.tools import SandboxApplyPatchTool
from agents.tool_context import ToolContext


def _patch_function(tool: SandboxApplyPatchTool) -> FunctionTool:
    # Do not silently drop approval policies that the function interface cannot represent.
    if not isinstance(tool.needs_approval, bool) or tool.on_approval is not None:
        raise ValueError(
            "Custom apply_patch approval callbacks need a function-tool adapter"
        )

    description = tool.description.replace(
        "This is a FREEFORM tool, so do not wrap the patch in JSON.",
        'Pass the complete patch text in the "patch" string argument.',
    )

    @function_tool(
        name_override=tool.name,
        description_override=description,
        needs_approval=tool.needs_approval,
    )
    async def apply_patch(ctx: ToolContext[Any], patch: str) -> str:
        # Delegate parsing, editing, identity and workspace enforcement to the original tool.
        return await tool.on_invoke_tool(ctx, patch)

    return apply_patch


class ChatCompletionsFilesystem(Filesystem):
    def tools(self) -> list[Tool]:
        return [
            _patch_function(tool) if isinstance(tool, SandboxApplyPatchTool) else tool
            for tool in super().tools()
        ]
