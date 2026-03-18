# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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