# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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