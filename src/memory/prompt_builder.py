"""Build personalized prompts based on user profile."""

from typing import Optional

from loguru import logger

from src.memory.profile_manager import (
    UserProfile,
    LearningStage,
    CommunicationStyle,
    TonePreference,
    TechnicalLevel,
)
from src.memory.conversation_memory import ConversationMemory, get_conversation_memory


class PersonalizedPromptBuilder:
    """Build personalized system prompts for LLM."""

    # Base prompts for each learning stage
    STAGE_PROMPTS = {
        LearningStage.ONBOARDING.value: """你是投资助手，正在了解新用户。
目标：通过友好的对话了解用户偏好。
规则：
1. 每次最多问一个问题
2. 问题要自然融入对话
3. 提供选项而非开放问题
4. 保持友好和耐心
""",
        LearningStage.LEARNING.value: """你是投资助手，正在持续学习用户偏好。
目标：完善用户画像，提供越来越个性化的服务。
规则：
1. 在合适时机确认推测的偏好
2. 发现新偏好时主动记录
3. 避免重复询问已确认的信息
4. 对用户关注的话题给予更多关注
""",
        LearningStage.MATURE.value: """你是投资助手的成熟形态。
目标：基于完整画像提供精准服务。
规则：
1. 直接给出个性化建议
2. 主动提及用户关注的内容
3. 保持用户习惯的沟通风格
4. 预判用户需求，主动提供帮助
"""
    }

    # Style descriptions
    STYLE_DESCRIPTIONS = {
        "concise": "用简短精炼的语言回答，突出核心要点，不超过3句话",
        "balanced": "用适中的篇幅回答，包含分析和结论，结构清晰",
        "detailed": "用详细深入的方式回答，包含数据、分析和建议，全面完整",
    }

    # Tone descriptions
    TONE_DESCRIPTIONS = {
        "formal": "使用正式专业的语气，避免口语化表达",
        "friendly": "使用友好亲切的语气，像朋友一样交流",
        "casual": "使用轻松随意的语气，可以适当使用口语化表达",
    }

    # Technical level descriptions
    TECHNICAL_DESCRIPTIONS = {
        "beginner": "用户是投资新手，避免使用专业术语，必要时解释概念",
        "medium": "用户有一定投资经验，可以使用常见术语，适度解释",
        "expert": "用户是投资专家，可以直接使用专业术语，深入分析",
    }

    def __init__(self):
        """Initialize prompt builder."""
        self._conversation_memory: Optional[ConversationMemory] = None

    @property
    def conversation_memory(self) -> ConversationMemory:
        """Get conversation memory instance."""
        if self._conversation_memory is None:
            self._conversation_memory = get_conversation_memory()
        return self._conversation_memory

    async def build_system_prompt(
        self,
        user_profile: UserProfile,
        include_history: bool = True,
        learning_task: Optional[str] = None,
    ) -> str:
        """Build personalized system prompt.

        Args:
            user_profile: User's profile
            include_history: Whether to include conversation summary
            learning_task: Optional learning task question to ask

        Returns:
            Personalized system prompt
        """
        # Start with stage-appropriate base prompt
        base_prompt = self.STAGE_PROMPTS.get(
            user_profile.learning_stage,
            self.STAGE_PROMPTS[LearningStage.LEARNING.value]
        )

        # Build user profile section
        profile_section = self._build_profile_section(user_profile)

        # Build style guidelines
        style_section = self._build_style_section(user_profile)

        # Build conversation context
        context_section = ""
        if include_history:
            context_section = await self._build_context_section(user_profile.user_id)

        # Build learning task section
        task_section = ""
        if learning_task:
            task_section = f"""
## 当前任务
{learning_task}

请在回答后自然地提出这个问题，不要生硬。
"""

        # Combine all sections
        prompt = f"""{base_prompt}

{profile_section}

{style_section}
{context_section}
{task_section}
"""
        return prompt.strip()

    def _build_profile_section(self, profile: UserProfile) -> str:
        """Build user profile section."""
        parts = ["## 用户画像"]

        # Basic info
        if profile.nickname:
            parts.append(f"- 昵称: {profile.nickname}")

        # Communication preferences
        parts.append(f"- 沟通风格: {profile.get_style_description()}")
        parts.append(f"- 语气偏好: {profile.get_tone_description()}")
        parts.append(f"- 专业程度: {self._get_technical_desc(profile.technical_level)}")

        # Investment preferences (if known)
        if profile.risk_preference:
            risk_names = {"aggressive": "激进型", "moderate": "稳健型", "conservative": "保守型"}
            parts.append(f"- 风险偏好: {risk_names.get(profile.risk_preference, profile.risk_preference)}")

        if profile.investment_style:
            style_names = {"value": "价值投资", "growth": "成长投资", "index": "指数投资", "trading": "短线交易"}
            parts.append(f"- 投资风格: {style_names.get(profile.investment_style, profile.investment_style)}")

        if profile.investment_experience:
            exp_names = {"beginner": "新手", "intermediate": "中级", "advanced": "资深"}
            parts.append(f"- 投资经验: {exp_names.get(profile.investment_experience, profile.investment_experience)}")

        # Interests
        if profile.preferred_topics:
            parts.append(f"- 关注领域: {', '.join(profile.preferred_topics)}")

        if profile.favorite_stocks or profile.watchlist:
            stocks = list(set(profile.favorite_stocks + profile.watchlist))
            parts.append(f"- 自选股: {', '.join(stocks[:5])}")

        # Stats
        parts.append(f"- 交互次数: {profile.total_interactions}")
        parts.append(f"- 学习阶段: {profile.learning_stage}")

        return "\n".join(parts)

    def _build_style_section(self, profile: UserProfile) -> str:
        """Build style guidelines section."""
        parts = ["## 回答风格指南"]

        # Communication style
        style_guide = self.STYLE_DESCRIPTIONS.get(
            profile.communication_style,
            self.STYLE_DESCRIPTIONS["balanced"]
        )
        parts.append(f"1. {style_guide}")

        # Tone
        tone_guide = self.TONE_DESCRIPTIONS.get(
            profile.tone_preference,
            self.TONE_DESCRIPTIONS["friendly"]
        )
        parts.append(f"2. {tone_guide}")

        # Technical level
        tech_guide = self.TECHNICAL_DESCRIPTIONS.get(
            profile.technical_level,
            self.TECHNICAL_DESCRIPTIONS["medium"]
        )
        parts.append(f"3. {tech_guide}")

        # Risk consideration
        if profile.risk_preference:
            risk_considerations = {
                "aggressive": "用户偏好高风险高收益，可以提及成长性机会",
                "moderate": "用户偏好稳健投资，建议风险收益平衡",
                "conservative": "用户偏好低风险，建议关注稳健标的",
            }
            parts.append(f"4. {risk_considerations.get(profile.risk_preference, '')}")

        return "\n".join(parts)

    async def _build_context_section(self, user_id: str) -> str:
        """Build conversation context section."""
        try:
            summary = await self.conversation_memory.get_conversation_summary(user_id)
            if summary and summary != "无最近对话记录":
                return f"""
## 对话上下文
{summary}
"""
        except Exception as e:
            logger.warning(f"Failed to get conversation summary: {e}")

        return ""

    def _get_technical_desc(self, level: str) -> str:
        """Get technical level description."""
        names = {
            "beginner": "入门级",
            "medium": "进阶级",
            "expert": "专业级",
        }
        return names.get(level, "进阶级")

    def build_chat_prompt(
        self,
        user_profile: UserProfile,
        is_unrestricted: bool = False,
    ) -> str:
        """Build prompt for chat mode.

        Args:
            user_profile: User's profile
            is_unrestricted: If True, no investment-specific constraints

        Returns:
            Chat mode system prompt
        """
        if is_unrestricted:
            # Unrestricted chat - just personality, no topic constraints
            return f"""你是用户的AI助手。
用户偏好:
- 沟通风格: {user_profile.get_style_description()}
- 语气: {user_profile.get_tone_description()}

请根据用户的偏好进行自然对话。可以讨论任何话题。
"""

        # Investment-focused chat
        return f"""你是用户的专属投资助手。

用户画像:
- 沟通风格: {user_profile.get_style_description()}
- 语气: {user_profile.get_tone_description()}
- 专业程度: {self._get_technical_desc(user_profile.technical_level)}
- 自选股: {', '.join(user_profile.watchlist[:5]) if user_profile.watchlist else '暂无'}

请根据用户偏好提供个性化的投资相关回答。
对于非投资问题，可以礼貌地说明你的专业领域是投资。
"""

    def build_preference_confirm_prompt(
        self,
        preference_type: str,
        suggested_value: str,
    ) -> str:
        """Build prompt for confirming a preference.

        Args:
            preference_type: Type of preference to confirm
            suggested_value: Suggested value for the preference

        Returns:
            Confirmation prompt
        """
        prompts = {
            "communication_style": "您希望我用什么风格回答？",
            "tone_preference": "您更喜欢什么样的语气？",
            "technical_level": "您的投资知识水平如何？",
            "risk_preference": "您的风险承受能力如何？",
            "investment_style": "您更偏好哪种投资方式？",
            "investment_experience": "您的投资经验如何？",
        }

        return prompts.get(preference_type, "这个设置符合您的需求吗？")


# Global instance
_prompt_builder: Optional[PersonalizedPromptBuilder] = None


def get_prompt_builder() -> PersonalizedPromptBuilder:
    """Get or create the global prompt builder."""
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = PersonalizedPromptBuilder()
    return _prompt_builder