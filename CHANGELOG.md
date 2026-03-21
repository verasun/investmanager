# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-03-21

### Added

#### Multi-Model Scoring and Routing System
- **Model Registry**: Track capabilities for 7 Alibaba Bailian models
  - qwen3.5-plus, qwen3-max-2026-01-23, qwen3-coder-next, qwen3-coder-plus
  - glm-5, kimi-k2.5, MiniMax-M2.5
  - Capabilities: TEXT, DEEP_THINKING, VISUAL, CODING

- **Intelligent Router**: Quality-first model selection
  - Weighted scoring: 50% quality, 30% latency, 20% cost
  - Automatic fallback on model failure
  - 10% exploration rate for underutilized models

- **Score Manager**: SQLite-based performance tracking
  - Tables: model_scores, execution_history, user_feedback
  - Rolling average with decay for recent performance
  - Support for explicit (1-5 rating) and implicit feedback

- **Multi-Model Provider**: Dynamic model selection per request
  - Task type routing (text, deep_thinking, visual, coding)
  - Fallback chain for reliability
  - Metrics recording for continuous improvement

#### Multi-Model Consensus System
- **Consensus Coordinator**: Multi-model discussion for complex tasks
  - Minimum 3 models participating
  - Roles: Designer, Arbitrator, Reviewer

- **Voting System**: Simple majority with tie-breaker
  - Maximum 3 discussion rounds
  - Arbitrator has final decision on ties
  - Configurable timeout (default: 60s)

#### Service Registration Protocol
- **Capability Protocol** (`services/capability_protocol.py`):
  - Standardized data structures for service registration
  - CapabilityInfo, EndpointInfo, ParamInfo models
  - Service status and heartbeat support

- **Gateway Enhancements**:
  - Service registry for dynamic service discovery
  - LLM-based intent routing
  - Help system for new users

### Changed
- LLM service now supports `/handle` endpoint for Gateway routing
- Removed deprecated `base.py` from providers
- Updated settings with multi-model configuration options

---

## [1.2.0] - 2026-03-20

### Added

#### Multi-Process Architecture
- **Gateway Service (:8000)**: Central traffic entry point
  - Webhook handler for Feishu events
  - LLM proxy for unified API access
  - Capability router based on work mode

- **LLM Service (:8001)**: Dedicated LLM API proxy
  - Support for Alibaba Bailian (Qwen/Kimi)
  - OpenAI and Anthropic compatible
  - Independent scaling and rate limiting

- **Capability Services**:
  - **Invest (:8010)**: Stock analysis, backtest, reports
  - **Chat (:8011)**: Personalized conversation with memory
  - **Dev (:8012)**: Claude Code integration for development

#### Working Directory Isolation
- All data stored in configurable `WORK_DIR` (default: `/root/autowork`)
- SQLite database: `$WORK_DIR/data/investmanager.db`
- Logs: `$WORK_DIR/logs/`
- Reports: `$WORK_DIR/reports/`

#### Deployment Scripts
- `scripts/start-multiprocess.sh`: Local multi-process startup
- `docker-compose.multiprocess.yml`: Docker deployment
- `make dev-multiprocess`: Quick start command
- `make up-multiprocess`: Docker deployment command

#### DEV Mode
- Claude Code CLI integration
- Subprocess execution with configurable working directory
- Full permission for LLM and Claude operations

### Changed
- Refactored `src/feishu/gateway/` for message routing
- Created `services/` directory for multi-process services
- Updated `.env.example` with multi-process URLs
- Updated documentation for new architecture

### Architecture Evolution
```
v1.1 Single Process          v1.2 Multi-Process
┌─────────────────┐         ┌─────────────────────────────┐
│    Monolith     │   →     │ Gateway → LLM Service       │
│  (all-in-one)   │         │        → Invest Capability  │
│                 │         │        → Chat Capability    │
│                 │         │        → Dev Capability     │
└─────────────────┘         └─────────────────────────────┘
```

---

## [1.1.0] - 2026-03-18

### Added

#### Personalization System
- **User Profile Management**: SQLite-based user preference storage
  - Communication style (concise/balanced/detailed)
  - Tone preference (formal/friendly/casual)
  - Technical level (beginner/medium/expert)
  - Risk preference and investment style
  - Learning stages: ONBOARDING → LEARNING → MATURE

- **Conversation Memory**: Per-user chat history with context summaries

- **Interactive Learning**: Progressive preference discovery
  - Automatic task generation based on interaction count
  - Option-based preference setting
  - Stock mention tracking and watchlist suggestions

- **Personalized Prompts**: LLM responses tailored to user preferences

#### Work Modes
- **INVEST Mode**: Investment-focused assistant with LLM fallback
- **CHAT Mode**: General conversation with full personalization
- **STRICT Mode**: Command-only mode, no LLM chat

#### LLM Provider Support
- **Alibaba Bailian (阿里百炼)**: Qwen models via DashScope API
  - Support for qwen-turbo, qwen-plus, qwen-max
  - OpenAI-compatible API interface
- **Provider Configuration**: `LLM_PROVIDER` environment variable

#### New Commands
- `综合分析 <代码>` - Full analysis pipeline (data → analysis → backtest → report)
- `切换模式` - Cycle work modes
- `当前模式` - Check current mode
- `我的画像` - View user profile
- `清除记忆` - Clear user memory

### Fixed
- User ID extraction in Feishu messages now prefers `open_id` with fallbacks to `user_id` and `union_id`

### Changed
- Dockerfile optimized with Chinese mirrors for faster builds
- Feishu webhook supports encrypted event decryption

---

## [1.0.0] - 2024-03-16

### Added

#### Architecture Optimization
- **SQLite Database**: Replaced PostgreSQL with embedded SQLite for simplified deployment
  - Async SQLite manager with connection pooling
  - WAL mode for better concurrency
  - Full schema migration from PostgreSQL

- **Local Cache**: Replaced Redis with in-memory LRU cache
  - TTL expiration support
  - Namespace-based caching
  - Statistics and monitoring

- **OAuth2 Email Authentication**: Secure email sending without password
  - Support for Gmail, Outlook, QQ
  - Automatic token refresh
  - PKCE flow support

- **Feishu Integration**: Full IM-based task control
  - Bot command parser (Chinese & English)
  - Webhook event handling
  - Report delivery to Feishu
  - Document and message sending
  - Bitable integration

#### New Features
- Standalone Docker deployment (single container)
- YAML configuration files for email and feishu
- OAuth2 email setup CLI tool
- Comprehensive test suite (88 tests)

### Changed
- Simplified deployment: no external database/cache required
- Enhanced security: OAuth2 instead of password authentication
- Improved configuration: environment variables + YAML files

### Removed
- PostgreSQL dependency
- Redis dependency
- Password-based SMTP authentication

---

## [0.1.0] - 2024-03-01

### Added
- Multi-market data support (A-shares, US stocks, derivatives)
- Technical analysis with 50+ indicators
- Fundamental analysis module
- Sentiment analysis module
- AI-powered insights
- Backtesting engine
- Risk management
- Report generation
- Web dashboard (Streamlit)
- RESTful API (FastAPI)
- Task scheduling and orchestration