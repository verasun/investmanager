"""Extract user preferences from conversation."""

import re
from dataclasses import dataclass
from typing import Optional

from loguru import logger


@dataclass
class ExtractedPreferences:
    """Preferences extracted from a message."""

    # Communication preferences
    communication_style: Optional[str] = None
    tone_preference: Optional[str] = None
    technical_level: Optional[str] = None

    # Investment preferences
    risk_preference: Optional[str] = None
    investment_style: Optional[str] = None
    investment_experience: Optional[str] = None
    investment_horizon: Optional[str] = None

    # Mentioned stocks
    mentioned_stocks: list[str] = None
    mentioned_stock_names: list[str] = None

    # Topics
    mentioned_topics: list[str] = None

    # Confidence
    confidence: float = 0.0

    def __post_init__(self):
        if self.mentioned_stocks is None:
            self.mentioned_stocks = []
        if self.mentioned_stock_names is None:
            self.mentioned_stock_names = []
        if self.mentioned_topics is None:
            self.mentioned_topics = []

    def has_preferences(self) -> bool:
        """Check if any preferences were extracted."""
        return any([
            self.communication_style,
            self.tone_preference,
            self.technical_level,
            self.risk_preference,
            self.investment_style,
            self.investment_experience,
            self.investment_horizon,
        ])

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "communication_style": self.communication_style,
            "tone_preference": self.tone_preference,
            "technical_level": self.technical_level,
            "risk_preference": self.risk_preference,
            "investment_style": self.investment_style,
            "investment_experience": self.investment_experience,
            "investment_horizon": self.investment_horizon,
            "mentioned_stocks": self.mentioned_stocks,
            "mentioned_stock_names": self.mentioned_stock_names,
            "mentioned_topics": self.mentioned_topics,
            "confidence": self.confidence,
        }


class PreferenceExtractor:
    """Extract user preferences from conversation."""

    # Keyword to preference mapping
    STYLE_KEYWORDS = {
        # Communication style
        "简洁": "concise",
        "简单": "concise",
        "快速": "concise",
        "简要": "concise",
        "详细": "detailed",
        "深入": "detailed",
        "全面": "detailed",
        "完整": "detailed",
        "专业": "detailed",

        # Tone
        "正式": "formal",
        "严肃": "formal",
        "友好": "friendly",
        "亲切": "friendly",
        "轻松": "casual",
        "随意": "casual",

        # Technical level
        "入门": "beginner",
        "新手": "beginner",
        "小白": "beginner",
        "进阶": "medium",
        "中级": "medium",
        "专业": "expert",
        "资深": "expert",
        "老手": "expert",

        # Risk preference
        "激进": "aggressive",
        "高风险": "aggressive",
        "稳健": "moderate",
        "适中": "moderate",
        "保守": "conservative",
        "低风险": "conservative",
        "安全": "conservative",

        # Investment style
        "长线": "value",
        "价值投资": "value",
        "长期持有": "value",
        "成长": "growth",
        "短线": "trading",
        "波段": "trading",
        "日内": "trading",
        "定投": "index",
        "指数": "index",
        "ETF": "index",

        # Investment experience
        "刚入": "beginner",
        "刚开始": "beginner",
        "接触不久": "beginner",
        "几年": "intermediate",
        "多年": "advanced",
        "十几年": "advanced",

        # Investment horizon
        "短期": "short",
        "几天": "short",
        "几周": "short",
        "中期": "medium",
        "一年": "medium",
        "长期": "long",
        "几年": "long",
        "长期持有": "long",
    }

    # Common stock names
    STOCK_NAMES = {
        "茅台": "600519",
        "贵州茅台": "600519",
        "平安银行": "000001",
        "招商银行": "600036",
        "宁德时代": "300750",
        "比亚迪": "002594",
        "中国平安": "601318",
        "腾讯": "00700",
        "阿里巴巴": "09988",
        "美团": "03690",
        "京东": "09618",
        "五粮液": "000858",
        "泸州老窖": "000568",
        "洋河股份": "002304",
        "海天味业": "603288",
        "中国中免": "601888",
        "恒瑞医药": "600276",
        "药明康德": "603259",
        "迈瑞医疗": "300760",
        "隆基绿能": "601012",
        "中国神华": "601088",
        "长江电力": "600900",
        "中国石油": "601857",
        "工商银行": "601398",
        "建设银行": "601939",
        "农业银行": "601288",
        "中国银行": "601988",
    }

    # Topics keywords
    TOPIC_KEYWORDS = {
        "股票": "股票",
        "A股": "股票",
        "港股": "股票",
        "美股": "股票",
        "基金": "基金",
        "ETF": "基金",
        "理财": "理财",
        "存款": "理财",
        "债券": "债券",
        "国债": "债券",
        "期货": "期货",
        "期权": "期权",
        "外汇": "外汇",
        "宏观": "宏观经济",
        "经济": "宏观经济",
        "政策": "政策",
        "行情": "行情",
        "大盘": "行情",
        "技术": "技术分析",
        "指标": "技术分析",
        "K线": "技术分析",
    }

    def extract(self, message: str) -> ExtractedPreferences:
        """Extract preferences from a user message."""
        message_lower = message.lower()

        preferences = ExtractedPreferences()
        preference_counts = {}

        # 1. Extract keywords-based preferences
        for keyword, pref_value in self.STYLE_KEYWORDS.items():
            if keyword in message:
                # Determine preference type
                pref_type = self._get_preference_type(pref_value)
                if pref_type:
                    preference_counts[pref_type] = preference_counts.get(pref_type, 0) + 1
                    setattr(preferences, pref_type, pref_value)

        # 2. Extract stock codes (6 digits)
        stock_codes = re.findall(r'\b(\d{6})\b', message)
        for code in stock_codes:
            if code.startswith(('6', '0', '3', '688')):
                preferences.mentioned_stocks.append(code)

        # 3. Extract stock names
        for name, code in self.STOCK_NAMES.items():
            if name in message:
                if code not in preferences.mentioned_stocks:
                    preferences.mentioned_stocks.append(code)
                if name not in preferences.mentioned_stock_names:
                    preferences.mentioned_stock_names.append(name)

        # 4. Extract topics
        for keyword, topic in self.TOPIC_KEYWORDS.items():
            if keyword in message:
                if topic not in preferences.mentioned_topics:
                    preferences.mentioned_topics.append(topic)

        # 5. Calculate confidence
        total_indicators = (
            len(preferences.mentioned_stocks) +
            len(preferences.mentioned_topics) +
            sum(1 for p in preference_counts.values() if p > 0)
        )
        preferences.confidence = min(1.0, total_indicators * 0.3)

        if preferences.has_preferences() or preferences.mentioned_stocks:
            logger.debug(f"Extracted preferences: {preferences.to_dict()}")

        return preferences

    def _get_preference_type(self, value: str) -> Optional[str]:
        """Determine preference type from value."""
        type_mapping = {
            "concise": "communication_style",
            "balanced": "communication_style",
            "detailed": "communication_style",
            "formal": "tone_preference",
            "friendly": "tone_preference",
            "casual": "tone_preference",
            "beginner": "technical_level",
            "medium": "technical_level",
            "expert": "technical_level",
            "aggressive": "risk_preference",
            "moderate": "risk_preference",
            "conservative": "risk_preference",
            "value": "investment_style",
            "growth": "investment_style",
            "index": "investment_style",
            "trading": "investment_style",
            "short": "investment_horizon",
            "medium": "investment_horizon",
            "long": "investment_horizon",
        }
        return type_mapping.get(value)

    def detect_confirmation(self, message: str) -> Optional[bool]:
        """Detect if user is confirming or denying something."""
        positive_patterns = [
            r"^(是|对|好|可以|确认|确定|没错|是的)$",
            r"^(是|对|好|可以)的?$",
            r"^好的?$",
            r"^OK$",
            r"^没问题$",
        ]
        negative_patterns = [
            r"^(不|否|不是|不对|不要|取消)$",
            r"^(不|否|不是)的?$",
        ]

        message = message.strip()

        for pattern in positive_patterns:
            if re.match(pattern, message, re.IGNORECASE):
                return True

        for pattern in negative_patterns:
            if re.match(pattern, message, re.IGNORECASE):
                return False

        return None

    def detect_option_selection(
        self, message: str, options: list[str]
    ) -> Optional[int]:
        """Detect which option the user selected.

        Args:
            message: User's message
            options: List of option strings

        Returns:
            Index of selected option, or None if not detected
        """
        message = message.strip()

        # Try exact match
        for i, option in enumerate(options):
            if message == option:
                return i

        # Try number selection (1, 2, 3...)
        if message.isdigit():
            idx = int(message) - 1
            if 0 <= idx < len(options):
                return idx

        # Try partial match
        for i, option in enumerate(options):
            if message in option or option in message:
                return i

        return None


# Global instance
_preference_extractor: Optional[PreferenceExtractor] = None


def get_preference_extractor() -> PreferenceExtractor:
    """Get or create the global preference extractor."""
    global _preference_extractor
    if _preference_extractor is None:
        _preference_extractor = PreferenceExtractor()
    return _preference_extractor