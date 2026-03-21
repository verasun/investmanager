"""Web Search Tool - Search the internet for information."""

import sys
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger

from .base import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    """Tool for searching the web.

    Wraps the existing WebSearcher from src/web/search.py.
    """

    name = "web_search"
    description = "搜索互联网获取最新信息。用于查询时事新闻、最新数据、实时信息、当前事件等需要最新资料的场景。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，应该是简洁、准确的搜索词",
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数",
                "default": 5,
            },
        },
        "required": ["query"],
    }
    timeout = 30

    def __init__(self, engine: str = "duckduckgo"):
        """Initialize web search tool.

        Args:
            engine: Search engine to use (duckduckgo, tavily, bing)
        """
        self.engine = engine
        self._searcher = None

    def _get_searcher(self):
        """Get or create the web searcher."""
        if self._searcher is None:
            from src.web import get_web_searcher

            self._searcher = get_web_searcher()
        return self._searcher

    async def execute(self, query: str, max_results: int = 5) -> ToolResult:
        """Execute web search.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            ToolResult with search results
        """
        try:
            from src.web import SearchEngine

            searcher = self._get_searcher()
            engine = SearchEngine(self.engine)

            response = await searcher.search(query, engine, max_results)

            if response.error:
                return ToolResult(
                    success=False,
                    error=response.error,
                )

            if response.is_empty():
                return ToolResult(
                    success=True,
                    data={"results": [], "message": f"未找到与 '{query}' 相关的结果"},
                    metadata={"query": query, "count": 0},
                )

            # Format results for agent consumption
            results = []
            for r in response.results:
                results.append({
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "source": r.source,
                })

            return ToolResult(
                success=True,
                data={
                    "results": results,
                    "formatted": searcher.format_results_for_llm(response),
                },
                metadata={
                    "query": query,
                    "count": len(results),
                    "engine": self.engine,
                },
            )

        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return ToolResult(
                success=False,
                error=f"搜索失败: {str(e)}",
            )


class WebSearchWithLLMTool(BaseTool):
    """Tool for web search with LLM-based query refinement.

    This tool can refine search queries using LLM before searching.
    """

    name = "web_search_smart"
    description = "智能网络搜索，会优化搜索词以获得更好的结果。适合需要精确搜索的场景。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "原始搜索意图或问题",
            },
            "context": {
                "type": "string",
                "description": "搜索上下文，帮助理解搜索意图",
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数",
                "default": 5,
            },
        },
        "required": ["query"],
    }
    timeout = 60

    def __init__(self, llm_provider=None, engine: str = "duckduckgo"):
        """Initialize smart search tool.

        Args:
            llm_provider: LLM provider for query refinement
            engine: Search engine to use
        """
        self.llm_provider = llm_provider
        self.engine = engine
        self._basic_search = WebSearchTool(engine)

    async def execute(
        self,
        query: str,
        context: Optional[str] = None,
        max_results: int = 5,
    ) -> ToolResult:
        """Execute smart web search.

        Args:
            query: Search query
            context: Optional context for refinement
            max_results: Maximum results

        Returns:
            ToolResult with search results
        """
        # For now, delegate to basic search
        # TODO: Add LLM-based query refinement
        return await self._basic_search.execute(query, max_results)