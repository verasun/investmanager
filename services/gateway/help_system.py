"""Guided Help System for InvestManager.

This module provides:
- Interactive help content management
- Feature discovery and exploration
- Step-by-step guided tutorials
- Context-aware help suggestions

Architecture:
┌─────────────────────────────────────────────────────────────────────┐
│                         Gateway (:8000)                             │
│  ┌─────────────────┐                                                │
│  │  Help Manager   │◀───┐                                           │
│  └─────────────────┘    │                                           │
│                         │                                           │
│  ┌──────────────────────┴─────────────────────────────────────────┐ │
│  │                      Help Content Store                        │ │
│  │  - Feature guides                                              │ │
│  │  - Step-by-step tutorials                                      │ │
│  │  - FAQs                                                        │ │
│  │  - Quick tips                                                  │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from datetime import datetime

from pydantic import BaseModel, Field


# ============================================
# Enums
# ============================================

class HelpType(str, Enum):
    """Types of help content."""
    GUIDE = "guide"           # 功能指南
    TUTORIAL = "tutorial"     # 步骤教程
    FAQ = "faq"               # 常见问题
    TIP = "tip"               # 快速提示
    EXAMPLE = "example"       # 使用示例
    QUICK_START = "quick_start"  # 快速开始


class HelpCategory(str, Enum):
    """Categories of help content."""
    GENERAL = "general"       # 通用
    INVEST = "invest"         # 投资分析
    CHAT = "chat"             # 对话聊天
    DEV = "dev"               # 开发模式
    SYSTEM = "system"         # 系统功能


# ============================================
# Models
# ============================================

class HelpStep(BaseModel):
    """A single step in a tutorial."""
    step_number: int
    title: str
    description: str
    example: Optional[str] = None
    tips: list[str] = Field(default_factory=list)


class HelpContent(BaseModel):
    """A piece of help content."""
    id: str
    title: str
    description: str
    help_type: HelpType
    category: HelpCategory
    keywords: list[str] = Field(default_factory=list)
    steps: list[HelpStep] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    related_help_ids: list[str] = Field(default_factory=list)
    priority: int = 0  # Higher = more important


class HelpSearchResult(BaseModel):
    """Result of help search."""
    content: HelpContent
    relevance: float  # 0.0 - 1.0


class UserHelpState(BaseModel):
    """User's help state for tracking progress."""
    user_id: str
    viewed_help_ids: list[str] = Field(default_factory=list)
    completed_tutorials: list[str] = Field(default_factory=list)
    last_help_shown: Optional[str] = None
    help_disabled: bool = False
    tutorial_progress: dict[str, int] = Field(default_factory=dict)  # tutorial_id -> step


# ============================================
# Help Content Store
# ============================================

@dataclass
class HelpContentStore:
    """Stores and manages help content."""

    _contents: dict[str, HelpContent] = field(default_factory=dict)

    def __post_init__(self):
        self._load_default_content()

    def _load_default_content(self):
        """Load default help content."""
        # Quick Start Guide
        self.register(HelpContent(
            id="quick_start",
            title="🚀 快速开始",
            description="5分钟了解 InvestManager 的核心功能",
            help_type=HelpType.QUICK_START,
            category=HelpCategory.GENERAL,
            keywords=["开始", "入门", "使用", "帮助"],
            steps=[
                HelpStep(
                    step_number=1,
                    title="选择工作模式",
                    description="InvestManager 提供三种工作模式：投资分析、通用对话、开发模式",
                    example="发送「切换模式」或「切换到投资模式」",
                    tips=["投资模式：股票分析、投资建议", "对话模式：日常聊天、知识问答", "开发模式：代码编写、技术问题"]
                ),
                HelpStep(
                    step_number=2,
                    title="尝试对话",
                    description="直接发送消息，系统会智能识别您的意图",
                    example="试试发送「贵州茅台股价如何」或「今天天气怎么样」",
                ),
                HelpStep(
                    step_number=3,
                    title="使用强制模式",
                    description="如果想指定特定模块处理，可以使用强制模式",
                    example="发送「使用 invest 模块」后，所有消息都由投资服务处理",
                ),
            ],
            priority=100,
        ))

        # Invest Mode Guide
        self.register(HelpContent(
            id="invest_guide",
            title="📊 投资分析模式指南",
            description="了解如何使用投资分析功能",
            help_type=HelpType.GUIDE,
            category=HelpCategory.INVEST,
            keywords=["投资", "股票", "分析", "回测"],
            examples=[
                "分析600519",
                "贵州茅台投资价值",
                "茅台和五粮液对比",
                "推荐一些消费股",
            ],
            steps=[
                HelpStep(
                    step_number=1,
                    title="股票分析",
                    description="询问任何股票的相关信息",
                    example="分析贵州茅台的投资价值",
                ),
                HelpStep(
                    step_number=2,
                    title="行业研究",
                    description="了解特定行业的投资机会",
                    example="白酒行业有哪些投资机会？",
                ),
                HelpStep(
                    step_number=3,
                    title="投资建议",
                    description="获取个性化的投资建议",
                    example="我有10万闲钱，该怎么投资？",
                ),
            ],
            related_help_ids=["stock_analysis", "backtest_guide"],
            priority=90,
        ))

        # Stock Analysis
        self.register(HelpContent(
            id="stock_analysis",
            title="📈 股票分析功能",
            description="详细的股票分析使用说明",
            help_type=HelpType.TUTORIAL,
            category=HelpCategory.INVEST,
            keywords=["股票", "分析", "技术", "基本面"],
            steps=[
                HelpStep(
                    step_number=1,
                    title="基本查询",
                    description="发送股票代码或名称，获取基本信息",
                    example="600519 或 贵州茅台",
                ),
                HelpStep(
                    step_number=2,
                    title="深度分析",
                    description="使用「分析」关键词触发深度分析",
                    example="分析600519的技术走势和基本面",
                ),
                HelpStep(
                    step_number=3,
                    title="对比分析",
                    description="对比多只股票",
                    example="茅台和五粮液哪个更值得投资？",
                ),
            ],
            priority=80,
        ))

        # Chat Mode Guide
        self.register(HelpContent(
            id="chat_guide",
            title="💬 对话模式指南",
            description="了解通用对话模式的功能",
            help_type=HelpType.GUIDE,
            category=HelpCategory.CHAT,
            keywords=["对话", "聊天", "问答", "搜索"],
            examples=[
                "今天天气怎么样",
                "讲个笑话",
                "Python怎么学",
                "推荐一本书",
            ],
            steps=[
                HelpStep(
                    step_number=1,
                    title="日常对话",
                    description="可以和我聊任何话题",
                    example="我今天心情不太好",
                ),
                HelpStep(
                    step_number=2,
                    title="知识问答",
                    description="询问任何知识性问题",
                    example="什么是量子计算？",
                ),
                HelpStep(
                    step_number=3,
                    title="个性化学习",
                    description="系统会学习你的偏好，提供个性化回复",
                    tips=["系统会记住你的投资偏好", "回复风格会根据你的习惯调整"],
                ),
            ],
            priority=85,
        ))

        # Dev Mode Guide
        self.register(HelpContent(
            id="dev_guide",
            title="💻 开发模式指南",
            description="了解如何使用开发助手功能",
            help_type=HelpType.GUIDE,
            category=HelpCategory.DEV,
            keywords=["开发", "代码", "编程", "调试"],
            examples=[
                "帮我写一个排序算法",
                "这段代码有什么问题",
                "如何优化这个函数",
            ],
            steps=[
                HelpStep(
                    step_number=1,
                    title="代码编写",
                    description="让 Claude 帮你写代码",
                    example="写一个 Python 函数，计算斐波那契数列",
                ),
                HelpStep(
                    step_number=2,
                    title="代码审查",
                    description="让 Claude 检查你的代码",
                    example="检查这段代码的性能问题：[粘贴代码]",
                ),
                HelpStep(
                    step_number=3,
                    title="问题解答",
                    description="询问技术问题",
                    example="FastAPI 如何实现依赖注入？",
                ),
            ],
            priority=75,
        ))

        # Mode Switching
        self.register(HelpContent(
            id="mode_switch",
            title="🔄 模式切换说明",
            description="如何在不同模式之间切换",
            help_type=HelpType.FAQ,
            category=HelpCategory.SYSTEM,
            keywords=["模式", "切换", "invest", "chat", "dev"],
            examples=[
                "切换模式",
                "切换到投资模式",
                "使用 chat 模块",
            ],
            steps=[
                HelpStep(
                    step_number=1,
                    title="自动切换",
                    description="发送「切换模式」循环切换",
                ),
                HelpStep(
                    step_number=2,
                    title="指定切换",
                    description="发送「切换到投资模式」直接切换",
                ),
                HelpStep(
                    step_number=3,
                    title="强制模式",
                    description="发送「使用 invest 模块」锁定特定模块",
                    tips=["强制模式下，所有消息都会发送到指定模块", "发送「取消强制模式」恢复智能路由"],
                ),
            ],
            related_help_ids=["quick_start"],
            priority=95,
        ))

        # Profile Management
        self.register(HelpContent(
            id="profile_guide",
            title="👤 个人画像管理",
            description="了解系统如何学习和个性化",
            help_type=HelpType.GUIDE,
            category=HelpCategory.SYSTEM,
            keywords=["画像", "偏好", "个性化", "记忆"],
            examples=[
                "我的画像",
                "清除记忆",
            ],
            steps=[
                HelpStep(
                    step_number=1,
                    title="查看画像",
                    description="发送「我的画像」查看系统了解你的信息",
                ),
                HelpStep(
                    step_number=2,
                    title="清除记忆",
                    description="发送「清除记忆」重置个人信息",
                ),
                HelpStep(
                    step_number=3,
                    title="偏好学习",
                    description="系统会从对话中学习你的偏好",
                    tips=["回复风格：简洁/详细/平衡", "投资偏好：风险等级、关注行业"],
                ),
            ],
            priority=70,
        ))

        # FAQ
        self.register(HelpContent(
            id="faq_general",
            title="❓ 常见问题",
            description="用户常见问题解答",
            help_type=HelpType.FAQ,
            category=HelpCategory.GENERAL,
            keywords=["问题", "FAQ", "帮助", "怎么办"],
            steps=[
                HelpStep(
                    step_number=1,
                    title="Q: 如何获取股票实时价格？",
                    description="A: 直接发送股票代码或名称，如「600519」或「茅台股价」",
                ),
                HelpStep(
                    step_number=2,
                    title="Q: 系统记住了我的什么信息？",
                    description="A: 发送「我的画像」查看，包括投资偏好、对话风格等",
                ),
                HelpStep(
                    step_number=3,
                    title="Q: 如何让系统更懂我？",
                    description="A: 多交流！系统会从对话中学习你的偏好和风格",
                ),
                HelpStep(
                    step_number=4,
                    title="Q: 回答不准确怎么办？",
                    description="A: 可以提供更多上下文，或使用强制模式指定模块",
                ),
            ],
            priority=60,
        ))

    def register(self, content: HelpContent):
        """Register help content."""
        self._contents[content.id] = content

    def get(self, content_id: str) -> Optional[HelpContent]:
        """Get help content by ID."""
        return self._contents.get(content_id)

    def get_all(self) -> list[HelpContent]:
        """Get all help content."""
        return sorted(self._contents.values(), key=lambda x: -x.priority)

    def get_by_category(self, category: HelpCategory) -> list[HelpContent]:
        """Get help content by category."""
        return [
            c for c in self.get_all()
            if c.category == category
        ]

    def get_by_type(self, help_type: HelpType) -> list[HelpContent]:
        """Get help content by type."""
        return [
            c for c in self.get_all()
            if c.help_type == help_type
        ]

    def search(self, query: str, limit: int = 5) -> list[HelpSearchResult]:
        """Search help content by query."""
        query_lower = query.lower()
        results = []

        for content in self._contents.values():
            score = 0.0

            # Check title match
            if query_lower in content.title.lower():
                score += 0.5

            # Check description match
            if query_lower in content.description.lower():
                score += 0.3

            # Check keywords match
            for keyword in content.keywords:
                if query_lower in keyword.lower():
                    score += 0.2
                    break

            # Check examples match
            for example in content.examples:
                if query_lower in example.lower():
                    score += 0.1
                    break

            if score > 0:
                results.append(HelpSearchResult(
                    content=content,
                    relevance=min(1.0, score),
                ))

        # Sort by relevance
        results.sort(key=lambda x: -x.relevance)
        return results[:limit]


# ============================================
# Help Manager
# ============================================

class HelpManager:
    """Manages help content and user help state."""

    def __init__(self):
        self._store = HelpContentStore()
        self._user_states: dict[str, UserHelpState] = {}

    def get_store(self) -> HelpContentStore:
        """Get help content store."""
        return self._store

    def get_user_state(self, user_id: str) -> UserHelpState:
        """Get or create user help state."""
        if user_id not in self._user_states:
            self._user_states[user_id] = UserHelpState(user_id=user_id)
        return self._user_states[user_id]

    def mark_help_viewed(self, user_id: str, help_id: str):
        """Mark help content as viewed by user."""
        state = self.get_user_state(user_id)
        if help_id not in state.viewed_help_ids:
            state.viewed_help_ids.append(help_id)
        state.last_help_shown = help_id

    def complete_tutorial(self, user_id: str, tutorial_id: str):
        """Mark tutorial as completed by user."""
        state = self.get_user_state(user_id)
        if tutorial_id not in state.completed_tutorials:
            state.completed_tutorials.append(tutorial_id)

    def update_tutorial_progress(self, user_id: str, tutorial_id: str, step: int):
        """Update user's progress in a tutorial."""
        state = self.get_user_state(user_id)
        state.tutorial_progress[tutorial_id] = step

    def is_new_user(self, user_id: str) -> bool:
        """Check if user is new (hasn't viewed any help)."""
        state = self.get_user_state(user_id)
        return len(state.viewed_help_ids) == 0

    def should_show_help(self, user_id: str, context: str = "") -> Optional[HelpContent]:
        """Determine if help should be shown based on context."""
        state = self.get_user_state(user_id)

        if state.help_disabled:
            return None

        # New user - show quick start
        if self.is_new_user(user_id):
            return self._store.get("quick_start")

        # Context-based suggestions
        if context:
            results = self._store.search(context, limit=1)
            if results and results[0].relevance > 0.3:
                content = results[0].content
                if content.id not in state.viewed_help_ids:
                    return content

        return None

    def format_help(self, content: HelpContent, step: Optional[int] = None) -> str:
        """Format help content for display."""
        lines = [f"📌 **{content.title}**", ""]
        lines.append(f"{content.description}")
        lines.append("")

        # Format steps
        if content.steps:
            lines.append("📋 **操作步骤：**")
            for s in content.steps:
                if step is None or s.step_number <= step:
                    lines.append(f"  **{s.step_number}.** {s.title}")
                    lines.append(f"     {s.description}")
                    if s.example:
                        lines.append(f"     💡 示例：`{s.example}`")
                    if s.tips:
                        for tip in s.tips:
                            lines.append(f"     ✓ {tip}")
                    lines.append("")

        # Format examples
        if content.examples:
            lines.append("📝 **使用示例：**")
            for ex in content.examples[:4]:
                lines.append(f"  • `{ex}`")
            lines.append("")

        # Related helps
        if content.related_help_ids:
            lines.append("🔗 **相关帮助：**")
            for rid in content.related_help_ids:
                related = self._store.get(rid)
                if related:
                    lines.append(f"  • {related.title} (发送「帮助 {rid}」)")
            lines.append("")

        return "\n".join(lines)

    def format_help_menu(self, category: Optional[HelpCategory] = None) -> str:
        """Format help menu for display."""
        lines = ["📖 **帮助中心**", ""]

        if category:
            contents = self._store.get_by_category(category)
        else:
            contents = self._store.get_all()

        # Group by category
        categories: dict[HelpCategory, list[HelpContent]] = {}
        for content in contents:
            if content.category not in categories:
                categories[content.category] = []
            categories[content.category].append(content)

        category_names = {
            HelpCategory.GENERAL: "通用",
            HelpCategory.INVEST: "投资分析",
            HelpCategory.CHAT: "对话聊天",
            HelpCategory.DEV: "开发模式",
            HelpCategory.SYSTEM: "系统功能",
        }

        for cat, cat_contents in categories.items():
            lines.append(f"**{category_names.get(cat, cat.value)}：**")
            for content in cat_contents[:5]:
                lines.append(f"  • {content.title} (发送「帮助 {content.id}」)")
            lines.append("")

        lines.append("💡 **提示：** 发送「帮助 [关键词]」搜索相关帮助")
        lines.append("         发送「引导」开始交互式引导")

        return "\n".join(lines)

    def format_quick_tips(self) -> str:
        """Format quick tips for display."""
        tips = [
            "💡 发送股票代码（如600519）快速查股",
            "💡 使用「分析」触发深度分析",
            "💡 「切换模式」在三种模式间切换",
            "💡 「使用 invest 模块」锁定投资模式",
            "💡 「我的画像」查看个性化设置",
        ]
        return "\n".join(tips)


# ============================================
# Global Instance
# ============================================

_help_manager: Optional[HelpManager] = None


def get_help_manager() -> HelpManager:
    """Get or create the global help manager."""
    global _help_manager
    if _help_manager is None:
        _help_manager = HelpManager()
    return _help_manager