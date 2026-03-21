"""Tool Registry - Centralized tool management."""

from typing import Optional

from loguru import logger

from .base import BaseTool, ToolInfo, ToolResult


class ToolRegistry:
    """Central registry for all agent tools.

    Manages tool registration, retrieval, and execution.
    Supports both OpenAI and Anthropic tool formats.
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool.

        Args:
            tool: Tool instance to register
        """
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, overwriting")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def unregister(self, name: str) -> bool:
        """Unregister a tool.

        Args:
            name: Name of tool to unregister

        Returns:
            True if tool was unregistered, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Unregistered tool: {name}")
            return True
        return False

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered.

        Args:
            name: Tool name

        Returns:
            True if tool exists
        """
        return name in self._tools

    def list_tools(self) -> list[ToolInfo]:
        """List all registered tools.

        Returns:
            List of ToolInfo objects
        """
        return [
            ToolInfo(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                timeout=tool.timeout,
            )
            for tool in self._tools.values()
        ]

    def get_tools_description(self) -> str:
        """Get a formatted description of all tools for LLM prompts.

        Returns:
            Formatted string describing all tools
        """
        lines = ["Available tools:"]
        for tool in self._tools.values():
            lines.append(f"\n## {tool.name}")
            lines.append(f"Description: {tool.description}")
            lines.append("Parameters:")
            for param_name, param_info in tool.parameters.get("properties", {}).items():
                required = param_name in tool.parameters.get("required", [])
                req_str = " (required)" if required else " (optional)"
                lines.append(f"  - {param_name}{req_str}: {param_info.get('description', '')}")
        return "\n".join(lines)

    def to_openai_tools(self) -> list[dict]:
        """Convert all tools to OpenAI format.

        Returns:
            List of tool definitions in OpenAI format
        """
        return [tool.to_openai_tool() for tool in self._tools.values()]

    def to_anthropic_tools(self) -> list[dict]:
        """Convert all tools to Anthropic format.

        Returns:
            List of tool definitions in Anthropic format
        """
        return [tool.to_anthropic_tool() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict) -> ToolResult:
        """Execute a tool by name.

        Args:
            name: Tool name
            params: Tool parameters

        Returns:
            ToolResult from execution
        """
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' not found",
            )

        # Validate parameters
        is_valid, error = tool.validate_params(params)
        if not is_valid:
            return ToolResult(
                success=False,
                error=f"Invalid parameters: {error}",
            )

        try:
            result = await tool.execute(**params)
            logger.info(f"Tool '{name}' executed successfully")
            return result
        except Exception as e:
            logger.error(f"Tool '{name}' execution failed: {e}")
            return ToolResult(
                success=False,
                error=str(e),
            )

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools.values())


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get or create the global tool registry."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def register_tool(tool: BaseTool) -> None:
    """Register a tool with the global registry."""
    get_tool_registry().register(tool)