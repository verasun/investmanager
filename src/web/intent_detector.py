"""Search intent detection for fallback scenarios.

Used when LLM doesn't support function calling.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SearchIntent:
    """Detected search intent."""

    needs_search: bool
    query: Optional[str] = None
    confidence: float = 0.0
    intent_type: Optional[str] = None


class SearchIntentDetector:
    """Fallback keyword-based search detection.

    Used when LLM doesn't support function calling.
    """

    # Keywords that suggest need for real-time search
    TIME_KEYWORDS = [
        # Chinese
        "今天",
        "昨天",
        "明天",
        "本周",
        "上周",
        "本月",
        "上月",
        "今年",
        "去年",
        "最近",
        "最新",
        "当前",
        "现在",
        "实时",
        # English
        "today",
        "yesterday",
        "tomorrow",
        "this week",
        "last week",
        "this month",
        "last month",
        "this year",
        "last year",
        "recent",
        "latest",
        "current",
        "now",
        "real-time",
        "realtime",
    ]

    NEWS_KEYWORDS = [
        # Chinese
        "新闻",
        "消息",
        "事件",
        "发生了",
        "报道",
        "公告",
        "资讯",
        "动态",
        # English
        "news",
        "headline",
        "breaking",
        "announcement",
        "update",
        "what happened",
    ]

    PRICE_KEYWORDS = [
        # Chinese
        "股价",
        "价格",
        "行情",
        "涨跌",
        "跌幅",
        "涨幅",
        "现价",
        "报价",
        # English
        "price",
        "stock price",
        "market",
        "quote",
        "trading",
    ]

    QUESTION_PATTERNS = [
        # Chinese question patterns
        r"^(.+)?(是什么|怎么样|如何|多少|什么时候|在哪里|谁)",
        r"(.+)?发生了(什么|啥)",
        r"(.+)?(最新|最近)(.+)?(消息|新闻|动态)",
        r"(.+)?今天(.+)?",
        # English question patterns
        r"^what('s| is| are)",
        r"^when('s| is| was)",
        r"^where('s| is| was)",
        r"^who('s| is| was)",
        r"^how('s| is| was)",
        r"what happened",
        r"tell me about",
        r"latest on",
    ]

    # Stock-related patterns that might need real-time data
    STOCK_PATTERNS = [
        r"\b\d{6}\b",  # Chinese stock codes like 600519
        r"\b[A-Z]{1,5}\b",  # US stock tickers like AAPL
        r"(股票|股价|行情)",
        r"(stock|share|price)",
    ]

    def __init__(self, threshold: float = 0.6):
        """Initialize detector.

        Args:
            threshold: Confidence threshold for triggering search
        """
        self.threshold = threshold

    def detect(self, message: str) -> SearchIntent:
        """Detect if message needs web search.

        Args:
            message: User message

        Returns:
            SearchIntent with detection result
        """
        message_lower = message.lower().strip()

        # Skip very short messages
        if len(message_lower) < 3:
            return SearchIntent(needs_search=False)

        # Count keyword matches
        time_matches = sum(1 for kw in self.TIME_KEYWORDS if kw in message_lower)
        news_matches = sum(1 for kw in self.NEWS_KEYWORDS if kw in message_lower)
        price_matches = sum(1 for kw in self.PRICE_KEYWORDS if kw in message_lower)

        # Check question patterns
        question_matches = sum(
            1 for pattern in self.QUESTION_PATTERNS
            if re.search(pattern, message_lower)
        )

        # Check stock patterns
        stock_matches = sum(
            1 for pattern in self.STOCK_PATTERNS
            if re.search(pattern, message)
        )

        # Calculate confidence
        total_matches = time_matches + news_matches + price_matches + question_matches + stock_matches
        confidence = min(1.0, total_matches * 0.25)

        # Determine if search is needed
        needs_search = confidence >= self.threshold

        # Determine intent type
        intent_type = None
        if news_matches > 0:
            intent_type = "news"
        elif price_matches > 0:
            intent_type = "price"
        elif time_matches > 0:
            intent_type = "realtime"
        elif question_matches > 0:
            intent_type = "question"

        # Extract search query from message
        query = self._extract_query(message) if needs_search else None

        return SearchIntent(
            needs_search=needs_search,
            query=query,
            confidence=confidence,
            intent_type=intent_type,
        )

    def needs_search(self, message: str) -> bool:
        """Simple check if message needs search.

        Args:
            message: User message

        Returns:
            True if search is needed
        """
        return self.detect(message).needs_search

    def _extract_query(self, message: str) -> str:
        """Extract search query from message.

        Removes common filler words and extracts the core search topic.
        """
        # Remove common question words
        filler_patterns = [
            r"^(请|帮我|能不能|可以|我想|我要)",
            r"(吗|呢|吧|呀|啊)$",
            r"(是什么|怎么样|如何|多少)",
        ]

        query = message.strip()
        for pattern in filler_patterns:
            query = re.sub(pattern, "", query)

        return query.strip() or message.strip()


# Global instance
_intent_detector: Optional[SearchIntentDetector] = None


def get_intent_detector() -> SearchIntentDetector:
    """Get or create intent detector instance."""
    global _intent_detector
    if _intent_detector is None:
        _intent_detector = SearchIntentDetector()
    return _intent_detector