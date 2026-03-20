# CHAT模式个性化系统设计文档

## 1. 概述

### 1.1 目标
让CHAT模式下的用户体验随使用次数增加而不断提升，系统能够：
- 记住用户偏好和习惯
- 学习用户沟通方式
- 适应问题风格
- 通过主动交互逐步完善用户画像

### 1.2 核心理念
- **渐进式学习**: 通过交互逐步了解用户，而非一次性问卷
- **持久记忆**: 跨会话记住用户偏好，存储在本地数据库
- **主动确认**: 不确定时主动询问，避免误解
- **无感融入**: 在正常对话中自然收集信息

---

## 2. 系统架构

### 2.1 整体流程

```
┌─────────────────────────────────────────────────────────────┐
│                        用户消息                              │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   记忆检索模块                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  用户画像   │  │  对话历史   │  │  交互状态   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 个性化Prompt构建                             │
│  基于用户画像动态生成system prompt                          │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     LLM响应                                  │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   记忆更新模块                               │
│  - 更新对话历史                                             │
│  - 提取新偏好                                               │
│  - 更新交互计数                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块职责

| 模块 | 职责 |
|------|------|
| UserProfileManager | 用户画像管理（读取、更新、初始化） |
| ConversationMemory | 对话历史管理（存储、检索、摘要） |
| PersonalizedPromptBuilder | 个性化Prompt构建 |
| PreferenceExtractor | 偏好提取（从对话中提取用户特征） |
| InteractiveLearning | 交互式学习（主动询问确认偏好） |

---

## 3. 数据结构设计

### 3.1 用户画像 (user_profiles表)

```sql
CREATE TABLE user_profiles (
    user_id TEXT PRIMARY KEY,
    -- 基本信息
    nickname TEXT,                          -- 用户昵称
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 沟通偏好
    communication_style TEXT DEFAULT 'balanced',  -- concise/balanced/detailed
    tone_preference TEXT DEFAULT 'friendly',      -- formal/friendly/casual
    technical_level TEXT DEFAULT 'medium',        -- beginner/medium/expert

    -- 投资偏好
    risk_preference TEXT,                   -- aggressive/moderate/conservative
    investment_style TEXT,                  -- value/growth/index/trading
    investment_experience TEXT,             -- beginner/intermediate/advanced
    investment_horizon TEXT,                -- short/medium/long

    -- 关注领域
    preferred_topics TEXT,                  -- JSON: ["股票", "基金", "宏观"]
    favorite_stocks TEXT,                   -- JSON: ["600519", "000001"]
    watchlist TEXT,                         -- JSON: 自选股列表

    -- 交互统计
    total_interactions INTEGER DEFAULT 0,
    last_interaction_at TIMESTAMP,
    learning_stage TEXT DEFAULT 'onboarding'  -- onboarding/learning/mature
);
```

### 3.2 对话历史 (conversation_history表)

```sql
CREATE TABLE conversation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,                     -- user/assistant
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 元数据
    intent_detected TEXT,                   -- 识别的意图
    preferences_extracted TEXT,             -- JSON: 提取的偏好

    INDEX idx_user_time (user_id, created_at)
);
```

### 3.3 学习任务 (learning_tasks表)

```sql
CREATE TABLE learning_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    task_type TEXT NOT NULL,                -- preference_confirm/style_check/topic_inquire
    question TEXT NOT NULL,                 -- 待询问的问题
    options TEXT,                           -- JSON: 选项列表
    priority INTEGER DEFAULT 5,             -- 优先级 (1-10)
    asked BOOLEAN DEFAULT FALSE,
    answered BOOLEAN DEFAULT FALSE,
    answer TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_user_pending (user_id, asked, answered)
);
```

### 3.4 Python数据模型

```python
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from enum import Enum

class CommunicationStyle(str, Enum):
    CONCISE = "concise"      # 简洁快速
    BALANCED = "balanced"    # 平衡适中
    DETAILED = "detailed"    # 详细分析

class TonePreference(str, Enum):
    FORMAL = "formal"        # 正式专业
    FRIENDLY = "friendly"    # 友好亲切
    CASUAL = "casual"        # 轻松随意

class TechnicalLevel(str, Enum):
    BEGINNER = "beginner"    # 入门
    MEDIUM = "medium"        # 进阶
    EXPERT = "expert"        # 专业

class RiskPreference(str, Enum):
    AGGRESSIVE = "aggressive"  # 激进
    MODERATE = "moderate"      # 稳健
    CONSERVATIVE = "conservative"  # 保守

class LearningStage(str, Enum):
    ONBOARDING = "onboarding"  # 新用户引导
    LEARNING = "learning"      # 学习阶段
    MATURE = "mature"          # 成熟阶段


@dataclass
class UserProfile:
    """用户画像"""
    user_id: str
    nickname: Optional[str] = None

    # 沟通偏好
    communication_style: CommunicationStyle = CommunicationStyle.BALANCED
    tone_preference: TonePreference = TonePreference.FRIENDLY
    technical_level: TechnicalLevel = TechnicalLevel.MEDIUM

    # 投资偏好
    risk_preference: Optional[RiskPreference] = None
    investment_style: Optional[str] = None
    investment_experience: Optional[str] = None
    investment_horizon: Optional[str] = None

    # 关注领域
    preferred_topics: list[str] = field(default_factory=list)
    favorite_stocks: list[str] = field(default_factory=list)
    watchlist: list[str] = field(default_factory=list)

    # 统计
    total_interactions: int = 0
    last_interaction_at: Optional[datetime] = None
    learning_stage: LearningStage = LearningStage.ONBOARDING


@dataclass
class ConversationMessage:
    """对话消息"""
    role: str  # user / assistant
    content: str
    timestamp: datetime
    intent: Optional[str] = None
    preferences_extracted: dict = field(default_factory=dict)


@dataclass
class LearningTask:
    """学习任务"""
    task_type: str
    question: str
    options: list[str]
    priority: int = 5
    asked: bool = False
    answered: bool = False
    answer: Optional[str] = None
```

---

## 4. 交互式学习流程

### 4.1 学习阶段划分

```
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│   ONBOARDING   │───►│    LEARNING    │───►│     MATURE     │
│   (0-5次交互)  │    │   (5-20次交互) │    │  (20+次交互)   │
└────────────────┘    └────────────────┘    └────────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
   基础偏好设置         持续学习优化          精细化调整
   - 沟通风格           - 投资偏好           - 微调响应
   - 专业程度           - 关注领域           - 特殊习惯
   - 基本引导           - 风险偏好           - 深度个性化
```

### 4.2 主动询问触发条件

| 触发场景 | 询问内容 | 示例 |
|----------|----------|------|
| 首次交互 | 沟通风格 | "您希望我用什么风格回答？" |
| 提及股票 | 是否关注 | "您经常提到茅台，要加入自选吗？" |
| 风险话题 | 风险偏好 | "您更倾向哪种投资风格？" |
| 专业术语 | 专业程度 | "需要我解释这个术语吗？" |
| 多次同类问题 | 偏好确认 | "您似乎偏爱短线操作，对吗？" |

### 4.3 交互示例

**场景1: 首次交互 (ONBOARDING阶段)**

```
用户: 今天行情怎么样
机器人: 您好！我是您的投资助手。为了让我的回答更贴合您的需求，
       请问您希望我用什么风格与您交流？

       [简洁快速] - 三言两语说重点
       [平衡适中] - 有分析有结论
       [详细分析] - 深入剖析，数据详尽

用户: 平衡适中
机器人: 好的，我会保持平衡适中的风格。
       还有一个问题：您的投资经验如何？

       [入门新手] - 刚开始接触投资
       [有一定经验] - 投资过一段时间
       [资深玩家] - 多年投资经验

用户: 有一定经验
机器人: 明白了！现在来看今天的行情...
       [行情分析内容]
```

**场景2: 持续学习 (LEARNING阶段)**

```
用户: 茅台今天涨了多少
机器人: 茅台(600519)今日上涨2.35%，收盘价1850元...

用户: 这只股票怎么样
机器人: [分析内容]

机器人: 我注意到您多次提到茅台，这是您重点关注的股票吗？
       [是的，加入自选] [偶尔关注] [其他原因]

用户: 是的，加入自选
机器人: 已将茅台加入您的自选列表，以后可以直接问"我的自选股"
```

**场景3: 成熟阶段 (MATURE阶段)**

```
用户: 帮我看看持仓
机器人: [根据用户已知的风险偏好和投资风格，直接给出个性化分析]
       基于您稳健的投资风格，当前持仓整体风险适中...
       [不需要再询问基本信息]
```

---

## 5. 个性化Prompt构建

### 5.1 Prompt模板

```python
PERSONALIZED_PROMPT_TEMPLATE = """你是{user_nickname}的专属投资助手。

## 用户画像
- 沟通风格: {communication_style}
- 专业程度: {technical_level}
- 投资经验: {investment_experience}
- 风险偏好: {risk_preference}
- 关注领域: {preferred_topics}
- 自选股: {favorite_stocks}

## 最近对话摘要
{conversation_summary}

## 响应指南
1. 根据"{communication_style}"风格调整回答长度
2. 用户专业程度为"{technical_level}"，{"使用专业术语" if technical_level == "expert" else "避免过于专业的术语"}
3. 用户风险偏好为"{risk_preference}"，在建议时考虑这一点
4. 用户关注{preferred_topics}，可以多提及相关内容
5. 保持{tone_preference}的语气

请根据以上信息，个性化回复用户消息。"""
```

### 5.2 动态调整策略

```python
class PromptBuilder:

    def build_system_prompt(self, user_profile: UserProfile, context: dict) -> str:
        """构建个性化system prompt"""

        # 基础prompt
        prompt = self._get_base_prompt(user_profile.learning_stage)

        # 注入用户画像
        prompt = self._inject_profile(prompt, user_profile)

        # 注入对话上下文
        prompt = self._inject_context(prompt, context)

        # 注入学习任务（如果有待询问的问题）
        prompt = self._inject_learning_task(prompt, user_profile)

        return prompt

    def _get_base_prompt(self, stage: LearningStage) -> str:
        """根据学习阶段返回基础prompt"""
        prompts = {
            LearningStage.ONBOARDING: """
你是投资助手，正在了解新用户。
目标：通过友好的对话了解用户偏好。
规则：
1. 每次最多问一个问题
2. 问题要自然融入对话
3. 提供选项而非开放问题
""",
            LearningStage.LEARNING: """
你是投资助手，正在持续学习用户偏好。
目标：完善用户画像，提供越来越个性化的服务。
规则：
1. 在合适时机确认推测的偏好
2. 发现新偏好时主动记录
3. 避免重复询问已确认的信息
""",
            LearningStage.MATURE: """
你是投资助手的成熟形态。
目标：基于完整画像提供精准服务。
规则：
1. 直接给出个性化建议
2. 主动提及用户关注的内容
3. 保持用户习惯的沟通风格
"""
        }
        return prompts.get(stage, prompts[LearningStage.LEARNING])
```

---

## 6. 偏好提取

### 6.1 提取规则

```python
class PreferenceExtractor:

    # 关键词到偏好的映射
    PREFERENCE_PATTERNS = {
        # 沟通风格
        "简洁": {"communication_style": "concise"},
        "快速": {"communication_style": "concise"},
        "详细": {"communication_style": "detailed"},
        "深入": {"communication_style": "detailed"},

        # 风险偏好
        "激进": {"risk_preference": "aggressive"},
        "稳健": {"risk_preference": "moderate"},
        "保守": {"risk_preference": "conservative"},

        # 投资风格
        "长线": {"investment_style": "value"},
        "价值投资": {"investment_style": "value"},
        "短线": {"investment_style": "trading"},
        "波段": {"investment_style": "trading"},
        "定投": {"investment_style": "index"},
        "指数": {"investment_style": "index"},

        # 投资经验
        "新手": {"investment_experience": "beginner"},
        "刚入门": {"investment_experience": "beginner"},
        "老手": {"investment_experience": "advanced"},
        "多年": {"investment_experience": "advanced"},
    }

    # 股票代码识别
    STOCK_CODE_PATTERN = r'\b(\d{6})\b'
    # 股票名称识别
    STOCK_NAME_PATTERN = r'(茅台|平安银行|招商银行|宁德时代|比亚迪|...)'

    def extract(self, message: str, response: str) -> dict:
        """从对话中提取偏好"""
        preferences = {}

        # 1. 关键词匹配
        for keyword, pref in self.PREFERENCE_PATTERNS.items():
            if keyword in message:
                preferences.update(pref)

        # 2. 股票识别
        stocks = self._extract_stocks(message)
        if stocks:
            preferences["mentioned_stocks"] = stocks

        # 3. 意图推断
        intent = self._infer_intent(message)
        if intent:
            preferences["inferred_intent"] = intent

        return preferences
```

### 6.2 提取时机

```python
# 在每次对话后调用
async def after_response(user_id: str, user_message: str, assistant_response: str):
    # 提取偏好
    new_preferences = extractor.extract(user_message, assistant_response)

    # 更新画像
    profile = await profile_manager.get(user_id)
    for key, value in new_preferences.items():
        if key == "mentioned_stocks":
            # 累计提及次数
            for stock in value:
                profile.stock_mentions[stock] = profile.stock_mentions.get(stock, 0) + 1
        else:
            # 更新偏好（需要确认的存入待确认列表）
            if profile.has_preference(key):
                # 已有该偏好，检查是否一致
                if profile.get(key) != value:
                    await learning_queue.add_confirm_task(user_id, key, value)
            else:
                # 新偏好，需要确认
                await learning_queue.add_confirm_task(user_id, key, value)

    # 更新交互计数
    profile.total_interactions += 1
    profile.last_interaction_at = datetime.now()

    # 检查是否需要升级学习阶段
    await check_stage_upgrade(profile)
```

---

## 7. 文件结构

```
src/
├── memory/
│   ├── __init__.py
│   ├── profile_manager.py      # 用户画像管理
│   ├── conversation_memory.py  # 对话历史管理
│   ├── preference_extractor.py # 偏好提取
│   ├── prompt_builder.py       # 个性化Prompt构建
│   └── interactive_learning.py # 交互式学习
├── data/
│   └── memory_repository.py    # 记忆数据存储
└── feishu/
    └── intent_parser.py        # 修改: 集成个性化
```

---

## 8. 实现步骤

### Phase 1: 基础存储 (1-2天)
1. 创建数据表 (user_profiles, conversation_history, learning_tasks)
2. 实现 UserRepository 基础CRUD
3. 实现 ConversationMemory 消息存储

### Phase 2: 用户画像 (2-3天)
1. 实现 UserProfileManager
2. 实现偏好提取基础逻辑
3. 修改intent_parser集成画像读取

### Phase 3: 个性化Prompt (1-2天)
1. 实现PromptBuilder
2. 实现对话摘要生成
3. 根据画像动态调整响应

### Phase 4: 交互式学习 (2-3天)
1. 实现LearningTaskManager
2. 实现主动询问逻辑
3. 实现偏好确认流程

### Phase 5: 优化迭代 (持续)
1. 收集反馈优化提取规则
2. 优化Prompt模板
3. 添加更多个性化维度

---

## 9. 隐私与安全

### 9.1 数据存储
- 所有用户数据存储在本地SQLite
- 不上传到第三方服务器
- 用户可随时清除自己的数据

### 9.2 敏感信息处理
- 不存储具体的资金数额
- 不存储交易密码等敏感信息
- 偏好数据仅用于改善服务

### 9.3 用户控制
- 提供"清除我的记忆"命令
- 提供"查看我的画像"命令
- 提供"修改偏好"命令

---

## 10. 测试用例

### 10.1 基础功能测试

| 测试项 | 输入 | 预期输出 |
|--------|------|----------|
| 首次交互 | "今天行情" | 返回行情 + 引导选择风格 |
| 风格选择 | 选择"简洁" | 确认 + 后续回复简洁 |
| 股票记忆 | 多次提茅台 | 询问是否加入自选 |
| 偏好记忆 | 重启后再次交互 | 记住之前的偏好 |

### 10.2 学习阶段测试

| 阶段 | 交互次数 | 预期行为 |
|------|----------|----------|
| ONBOARDING | 0-5 | 主动询问基础偏好 |
| LEARNING | 5-20 | 在对话中确认偏好 |
| MATURE | 20+ | 直接个性化响应 |

### 10.3 边界情况测试

| 场景 | 预期处理 |
|------|----------|
| 用户回答矛盾 | 再次确认偏好 |
| 用户拒绝回答 | 跳过，使用默认值 |
| 清除记忆 | 重置为ONBOARDING |
| 跨设备使用 | 通过user_id同步画像 |