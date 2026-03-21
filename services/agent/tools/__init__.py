"""Agent Tools - Unified tool management for LLM function calling.

This module provides:
- BaseTool: Abstract base class for all tools
- ToolResult: Standard result type for tool execution
- ToolRegistry: Central registry for tool management
- Built-in tools: web_search, stock_data, analysis, backtest, report
"""

from .base import BaseTool, ToolResult, ToolInfo
from .registry import ToolRegistry, get_tool_registry, register_tool
from .web_search import WebSearchTool, WebSearchWithLLMTool
from .stock_data import StockDataTool
from .analysis import StockAnalysisTool
from .backtest import BacktestTool
from .report import ReportTool


def get_default_tools() -> list[BaseTool]:
    """Get list of default tools for the agent.

    Returns:
        List of tool instances
    """
    return [
        WebSearchTool(),
        StockDataTool(),
        StockAnalysisTool(),
        BacktestTool(),
        ReportTool(),
    ]


def register_default_tools(registry: ToolRegistry = None) -> ToolRegistry:
    """Register all default tools.

    Args:
        registry: Optional registry to use, creates new one if None

    Returns:
        ToolRegistry with all tools registered
    """
    if registry is None:
        registry = get_tool_registry()

    for tool in get_default_tools():
        registry.register(tool)

    return registry


__all__ = [
    # Base classes
    "BaseTool",
    "ToolResult",
    "ToolInfo",
    # Registry
    "ToolRegistry",
    "get_tool_registry",
    "register_tool",
    # Tools
    "WebSearchTool",
    "WebSearchWithLLMTool",
    "StockDataTool",
    "StockAnalysisTool",
    "BacktestTool",
    "ReportTool",
    # Helpers
    "get_default_tools",
    "register_default_tools",
]