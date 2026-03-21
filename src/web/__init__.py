"""Web search module for CHAT mode."""

from src.web.search import WebSearcher, SearchEngine, SearchResult, SearchResponse
from src.web.intent_detector import SearchIntentDetector, get_intent_detector

__all__ = [
    "WebSearcher",
    "SearchEngine",
    "SearchResult",
    "SearchResponse",
    "SearchIntentDetector",
    "get_intent_detector",
    "get_web_searcher",
]

# Global searcher instance
_web_searcher: WebSearcher | None = None


def get_web_searcher() -> WebSearcher:
    """Get or create the global web searcher instance."""
    global _web_searcher
    if _web_searcher is None:
        from config.settings import settings
        _web_searcher = WebSearcher(
            timeout=settings.web_search_timeout,
            max_results=settings.web_search_max_results,
            tavily_api_key=settings.tavily_api_key if hasattr(settings, 'tavily_api_key') else None,
            bing_api_key=settings.bing_search_api_key if hasattr(settings, 'bing_search_api_key') else None,
        )
    return _web_searcher