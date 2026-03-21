"""Web search with multiple engine support."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import httpx
from loguru import logger


class SearchEngine(str, Enum):
    """Available search engines."""

    DUCKDUCKGO = "duckduckgo"
    TAVILY = "tavily"
    BING = "bing"


@dataclass
class SearchResult:
    """Single search result."""

    title: str
    url: str
    snippet: str
    source: str = ""
    published_date: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
            "published_date": self.published_date,
        }


@dataclass
class SearchResponse:
    """Response from web search."""

    query: str
    results: list[SearchResult] = field(default_factory=list)
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
            "error": self.error,
            "timestamp": self.timestamp,
        }

    def is_empty(self) -> bool:
        """Check if response has no results."""
        return len(self.results) == 0


class WebSearcher:
    """Web search with multiple engine support."""

    def __init__(
        self,
        timeout: int = 10,
        max_results: int = 5,
        tavily_api_key: Optional[str] = None,
        bing_api_key: Optional[str] = None,
        bing_endpoint: Optional[str] = None,
    ):
        """Initialize web searcher.

        Args:
            timeout: Request timeout in seconds
            max_results: Maximum number of results to return
            tavily_api_key: Optional Tavily API key
            bing_api_key: Optional Bing Search API key
            bing_endpoint: Optional Bing Search API endpoint
        """
        self.timeout = timeout
        self.max_results = max_results
        self.tavily_api_key = tavily_api_key
        self.bing_api_key = bing_api_key
        self.bing_endpoint = bing_endpoint or "https://api.bing.microsoft.com/v7.0/search"

    async def search(
        self,
        query: str,
        engine: SearchEngine = SearchEngine.DUCKDUCKGO,
        max_results: Optional[int] = None,
    ) -> SearchResponse:
        """Execute web search.

        Args:
            query: Search query
            engine: Search engine to use
            max_results: Override max results for this search

        Returns:
            SearchResponse with results or error
        """
        max_results = max_results or self.max_results

        try:
            if engine == SearchEngine.DUCKDUCKGO:
                return await self._search_duckduckgo(query, max_results)
            elif engine == SearchEngine.TAVILY:
                return await self._search_tavily(query, max_results)
            elif engine == SearchEngine.BING:
                return await self._search_bing(query, max_results)
            else:
                return SearchResponse(query=query, error=f"Unknown engine: {engine}")
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            return SearchResponse(query=query, error=str(e))

    async def _search_duckduckgo(self, query: str, max_results: int) -> SearchResponse:
        """Search using DuckDuckGo (free, no API key required).

        Uses the duckduckgo-search library for Python-native search.
        """
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.warning("duckduckgo-search not installed, falling back to HTTP API")
            return await self._search_duckduckgo_http(query, max_results)

        try:
            results = []
            # DDGS is synchronous, run in thread pool
            import asyncio

            def sync_search():
                with DDGS() as ddgs:
                    search_results = list(ddgs.text(query, max_results=max_results))
                return search_results

            loop = asyncio.get_event_loop()
            search_results = await loop.run_in_executor(None, sync_search)

            for r in search_results:
                results.append(
                    SearchResult(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        snippet=r.get("body", ""),
                        source="DuckDuckGo",
                    )
                )

            logger.info(f"DuckDuckGo search returned {len(results)} results for '{query}'")
            return SearchResponse(query=query, results=results)

        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            # Fallback to HTTP API
            logger.info("Falling back to DuckDuckGo HTTP API")
            return await self._search_duckduckgo_http(query, max_results)

    async def _search_duckduckgo_http(self, query: str, max_results: int) -> SearchResponse:
        """Fallback HTTP-based DuckDuckGo search.

        Uses DuckDuckGo Instant Answer API (limited results).
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # DuckDuckGo Instant Answer API
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": 1,
                        "skip_disambig": 1,
                    },
                )
                response.raise_for_status()
                data = response.json()

            results = []

            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and "Text" in topic and "FirstURL" in topic:
                    results.append(
                        SearchResult(
                            title=topic.get("Text", "").split(" - ")[0] if " - " in topic.get("Text", "") else topic.get("Text", ""),
                            url=topic.get("FirstURL", ""),
                            snippet=topic.get("Text", ""),
                            source="DuckDuckGo",
                        )
                    )

            # Abstract
            if data.get("Abstract") and len(results) < max_results:
                results.insert(
                    0,
                    SearchResult(
                        title=data.get("Heading", query),
                        url=data.get("AbstractURL", ""),
                        snippet=data.get("Abstract", ""),
                        source="DuckDuckGo",
                    ),
                )

            logger.info(f"DuckDuckGo HTTP search returned {len(results)} results for '{query}'")
            return SearchResponse(query=query, results=results[:max_results])

        except Exception as e:
            logger.error(f"DuckDuckGo HTTP search error: {e}")
            return SearchResponse(query=query, error=str(e))

    async def _search_tavily(self, query: str, max_results: int) -> SearchResponse:
        """Search using Tavily API (optimized for AI, requires API key).

        Get your API key at: https://tavily.com
        """
        if not self.tavily_api_key:
            return SearchResponse(query=query, error="Tavily API key not configured")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {self.tavily_api_key}"},
                    json={
                        "query": query,
                        "max_results": max_results,
                        "include_answer": False,
                        "include_raw_content": False,
                    },
                )
                response.raise_for_status()
                data = response.json()

            results = []
            for r in data.get("results", []):
                results.append(
                    SearchResult(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("content", ""),
                        source="Tavily",
                    )
                )

            logger.info(f"Tavily search returned {len(results)} results for '{query}'")
            return SearchResponse(query=query, results=results)

        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return SearchResponse(query=query, error=str(e))

    async def _search_bing(self, query: str, max_results: int) -> SearchResponse:
        """Search using Bing Search API (requires API key).

        Get your API key at: https://azure.microsoft.com/services/cognitive-services/bing-web-search-api/
        """
        if not self.bing_api_key:
            return SearchResponse(query=query, error="Bing API key not configured")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.bing_endpoint,
                    headers={"Ocp-Apim-Subscription-Key": self.bing_api_key},
                    params={
                        "q": query,
                        "count": max_results,
                        "responseFilter": "Webpages",
                    },
                )
                response.raise_for_status()
                data = response.json()

            results = []
            for r in data.get("webPages", {}).get("value", []):
                results.append(
                    SearchResult(
                        title=r.get("name", ""),
                        url=r.get("url", ""),
                        snippet=r.get("snippet", ""),
                        source="Bing",
                        published_date=r.get("datePublished"),
                    )
                )

            logger.info(f"Bing search returned {len(results)} results for '{query}'")
            return SearchResponse(query=query, results=results)

        except Exception as e:
            logger.error(f"Bing search error: {e}")
            return SearchResponse(query=query, error=str(e))

    def format_results_for_llm(self, response: SearchResponse, include_urls: bool = True) -> str:
        """Format search results for LLM context.

        Args:
            response: Search response
            include_urls: Whether to include URLs in output

        Returns:
            Formatted string for LLM context
        """
        if response.error:
            return f"搜索失败: {response.error}"

        if response.is_empty():
            return f"未找到与 '{response.query}' 相关的结果。"

        lines = [f"搜索关键词: {response.query}", f"找到 {len(response.results)} 条结果:", ""]

        for i, result in enumerate(response.results, 1):
            if include_urls:
                lines.append(f"{i}. {result.title}")
                lines.append(f"   来源: {result.url}")
            else:
                lines.append(f"{i}. {result.title}")
            lines.append(f"   摘要: {result.snippet}")
            if result.published_date:
                lines.append(f"   发布时间: {result.published_date}")
            lines.append("")

        return "\n".join(lines)


# Global instance
_web_searcher: Optional[WebSearcher] = None


def get_web_searcher() -> WebSearcher:
    """Get or create web searcher instance."""
    global _web_searcher
    if _web_searcher is None:
        from config.settings import settings

        _web_searcher = WebSearcher(
            timeout=settings.web_search_timeout,
            max_results=settings.web_search_max_results,
            tavily_api_key=settings.tavily_api_key,
            bing_api_key=settings.bing_search_api_key,
            bing_endpoint=settings.bing_search_endpoint,
        )
    return _web_searcher