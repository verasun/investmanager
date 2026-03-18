"""User memory and personalization module."""

from src.memory.profile_manager import (
    UserProfileManager,
    get_profile_manager,
    CommunicationStyle,
    TonePreference,
    TechnicalLevel,
    RiskPreference,
    LearningStage,
    UserProfile,
)
from src.memory.conversation_memory import (
    ConversationMemory,
    get_conversation_memory,
    ConversationMessage,
)
from src.memory.preference_extractor import (
    PreferenceExtractor,
    get_preference_extractor,
)
from src.memory.prompt_builder import (
    PersonalizedPromptBuilder,
    get_prompt_builder,
)
from src.memory.interactive_learning import (
    InteractiveLearningManager,
    get_learning_manager,
    LearningTask,
)

__all__ = [
    # Profile
    "UserProfileManager",
    "get_profile_manager",
    "UserProfile",
    "CommunicationStyle",
    "TonePreference",
    "TechnicalLevel",
    "RiskPreference",
    "LearningStage",
    # Conversation
    "ConversationMemory",
    "get_conversation_memory",
    "ConversationMessage",
    # Preference
    "PreferenceExtractor",
    "get_preference_extractor",
    # Prompt
    "PersonalizedPromptBuilder",
    "get_prompt_builder",
    # Learning
    "InteractiveLearningManager",
    "get_learning_manager",
    "LearningTask",
]