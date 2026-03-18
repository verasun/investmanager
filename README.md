# InvestManager

一个综合性的量化投资分析系统，支持A股、美股和衍生品市场。

## 特性

### 核心功能

- **多市场数据支持**: A股 (akshare/tushare)、美股 (yfinance)、衍生品
- **技术分析**: 50+技术指标、形态识别、信号生成
- **基本面分析**: 估值指标、财务报表分析
- **情绪分析**: 新闻情绪、市场情绪追踪
- **AI驱动洞察**: 基于LLM的市场分析和投资建议
- **回测引擎**: 策略测试与综合性能指标
- **风险管理**: 仓位管理、敞口追踪、风险预警
- **报告生成**: 日报、回测报告、投资建议

### v1.1 新特性

- **个人化系统**: 用户画像管理、对话记忆、偏好学习
- **工作模式**: INVEST(投资助手)、CHAT(通用对话)、STRICT(严格模式)
- **多LLM支持**: OpenAI、Anthropic、阿里百炼(Qwen系列)
- **综合分析**: 一键执行完整分析流程
- **智能解析**: 自然语言指令识别，无需精确命令格式

## 快速开始

### 前置要求

- Python 3.11+
- Docker 24.0+ & Docker Compose 2.20+

### Docker部署（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/yourorg/investmanager.git
cd investmanager

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 3. 启动服务
docker compose -f docker-compose.standalone.yml up -d

# 4. 检查状态
curl http://localhost:8000/health
```

### 本地开发

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate

# 2. 安装依赖
pip install -e ".[dev]"

# 3. 配置环境
cp .env.example .env

# 4. 运行测试
pytest tests/ -v

# 5. 启动API服务
uvicorn api.main:app --reload

# 6. 启动Web界面
streamlit run web/app.py
```

## 项目结构

```
investmanager/
├── api/              # FastAPI 路由
├── config/           # 配置模块
├── src/
│   ├── data/         # 数据层 (SQLite)
│   ├── cache/        # 本地缓存 (LRU)
│   ├── email/        # OAuth2邮件
│   ├── feishu/       # 飞书集成
│   │   ├── bot.py        # 机器人核心
│   │   ├── handlers.py   # 命令处理器
│   │   └── intent_parser.py # 意图解析
│   ├── memory/       # 个人化系统
│   │   ├── profile_manager.py    # 用户画像
│   │   ├── conversation_memory.py # 对话记忆
│   │   ├── interactive_learning.py # 交互学习
│   │   └── prompt_builder.py     # 个性化提示
│   ├── analysis/     # 分析模块
│   ├── backtest/     # 回测引擎
│   ├── strategies/   # 交易策略
│   └── report/       # 报告生成
├── tests/            # 测试套件
├── docs/             # 文档
├── scripts/          # 工具脚本
└── web/              # Streamlit界面
```

## 飞书集成

### 支持的命令

| 命令 | 说明 |
|-----|------|
| `综合分析 <代码>` | 完整分析流程（数据→分析→回测→报告）|
| `收集数据 <代码>` | 收集股票数据 |
| `分析 <代码>` | 分析股票 |
| `回测 <策略> <代码> [天数]` | 运行回测，默认365天 |
| `生成报告 [类型]` | 生成报告 |
| `发送报告 <目标>` | 发送报告 |
| `任务状态 <ID>` | 查询任务 |
| `切换模式` | 切换工作模式 (投资/对话/严格) |
| `当前模式` | 查看当前模式 |
| `我的画像` | 查看个人偏好设置 |
| `清除记忆` | 清除个人信息 |
| `帮助` | 显示帮助 |

### 工作模式

| 模式 | 说明 |
|------|------|
| **INVEST** | 投资助手模式，支持自然语言对话 |
| **CHAT** | 通用对话模式，可讨论任何话题 |
| **STRICT** | 严格模式，仅响应精确命令 |

### 配置飞书

1. 在飞书开放平台创建应用
2. 配置权限和事件订阅
3. 设置Webhook URL: `https://your-domain/api/feishu/webhook`
4. 在 `.env` 中配置应用凭证

详见 [打包和运行说明书](docs/PACKAGING_AND_RUNNING_GUIDE.md)

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_BACKEND` | 数据库类型 | `sqlite` |
| `SQLITE_DB_PATH` | 数据库路径 | `./data/investmanager.db` |
| `LOCAL_CACHE_ENABLED` | 启用本地缓存 | `true` |
| `FEISHU_ENABLED` | 启用飞书 | `false` |
| `LLM_PROVIDER` | LLM提供商 | `openai` |
| `ALIBABA_BAILIAN_API_KEY` | 阿里百炼API密钥 | - |
| `ALIBABA_BAILIAN_MODEL` | Qwen模型 | `qwen-turbo` |
| `EMAIL_PROVIDER` | 邮件提供商 | `gmail` |

完整配置见 [.env.example](.env.example)

## 文档

- [打包和运行说明书](docs/PACKAGING_AND_RUNNING_GUIDE.md)
- [部署指南](docs/DEPLOYMENT_GUIDE.html)
- [变更日志](CHANGELOG.md)
- [贡献指南](CONTRIBUTING.md)

## 开发

```bash
# 运行测试
pytest tests/ -v

# 代码检查
ruff check src/

# 类型检查
mypy src/
```

## 许可证

[MIT License](LICENSE)

## 贡献

欢迎贡献！请阅读 [贡献指南](CONTRIBUTING.md)