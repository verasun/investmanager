"""Tests for web search module."""

import asyncio
import pytest

from src.web.search import WebSearcher, SearchEngine, SearchResponse
from src.web.intent_detector import SearchIntentDetector


class TestSearchIntentDetector:
    """Tests for SearchIntentDetector."""

    def test_detect_news_keyword(self):
        """Test detection of news-related queries."""
        detector = SearchIntentDetector()

        intent = detector.detect("今天的新闻有什么？")
        assert intent.needs_search is True
        assert intent.intent_type == "news"

    def test_detect_time_keyword(self):
        """Test detection of time-related queries."""
        detector = SearchIntentDetector()

        intent = detector.detect("最近发生了什么？")
        assert intent.needs_search is True

    def test_detect_price_keyword(self):
        """Test detection of price-related queries."""
        detector = SearchIntentDetector()

        intent = detector.detect("苹果股价今天多少？")
        assert intent.needs_search is True
        assert intent.intent_type == "price"

    def test_detect_no_search_needed(self):
        """Test detection when no search is needed."""
        detector = SearchIntentDetector()

        intent = detector.detect("你好，介绍一下你自己")
        assert intent.needs_search is False

    def test_needs_search_convenience_method(self):
        """Test convenience method."""
        detector = SearchIntentDetector()

        assert detector.needs_search("今天科技新闻") is True
        assert detector.needs_search("普通对话") is False


class TestWebSearcher:
    """Tests for WebSearcher."""

    @pytest.mark.asyncio
    async def test_search_duckduckgo(self):
        """Test DuckDuckGo search."""
        searcher = WebSearcher(timeout=10, max_results=3)

        response = await searcher.search("Python programming", SearchEngine.DUCKDUCKGO)

        assert isinstance(response, SearchResponse)
        assert response.query == "Python programming"
        # May or may not have results depending on network

    @pytest.mark.asyncio
    async def test_format_results(self):
        """Test result formatting."""
        searcher = WebSearcher()

        response = SearchResponse(
            query="test query",
            results=[
                {
                    "title": "Test Title",
                    "url": "https://example.com",
                    "snippet": "Test snippet",
                    "source": "Test",
                }
            ],
        )

        # Create SearchResult objects manually
        from src.web.search import SearchResult
        response = SearchResponse(
            query="test query",
            results=[
                SearchResult(
                    title="Test Title",
                    url="https://example.com",
                    snippet="Test snippet",
                    source="Test",
                )
            ],
        )

        formatted = searcher.format_results_for_llm(response)
        assert "test query" in formatted
        assert "Test Title" in formatted

    @pytest.mark.asyncio
    async def test_format_error_response(self):
        """Test formatting of error response."""
        searcher = WebSearcher()

        response = SearchResponse(query="test", error="API error")
        formatted = searcher.format_results_for_llm(response)

        assert "搜索失败" in formatted
        assert "API error" in formatted

    @pytest.mark.asyncio
    async def test_format_empty_response(self):
        """Test formatting of empty response."""
        searcher = WebSearcher()

        response = SearchResponse(query="test", results=[])
        formatted = searcher.format_results_for_llm(response)

        assert "未找到" in formatted


class TestWebSearchIntegration:
    """Integration tests for web search with intent parser."""

    @pytest.mark.asyncio
    async def test_intent_parser_has_web_search(self):
        """Test that intent parser loads web search modules."""
        from src.feishu.intent_parser import IntentParser

        parser = IntentParser()
        parser._load_web_search_modules()

        assert parser._web_search_modules_loaded is True
        assert hasattr(parser, "_web_searcher")
        assert hasattr(parser, "_intent_detector")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])