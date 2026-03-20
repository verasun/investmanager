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

### v1.2 新特性 - 多进程架构

- **Gateway + 能力服务**: 关注点分离，独立扩展
- **独立 LLM 服务**: 统一的 LLM API 代理
- **DEV 模式**: Claude Code 集成，开发辅助
- **工作目录隔离**: 所有数据存储在 `/root/autowork`

### v1.1 特性

- **个人化系统**: 用户画像管理、对话记忆、偏好学习
- **工作模式**: INVEST(投资助手)、CHAT(通用对话)、DEV(开发模式)
- **多LLM支持**: OpenAI、Anthropic、阿里百炼(Qwen/Kimi系列)
- **综合分析**: 一键执行完整分析流程
- **智能解析**: 自然语言指令识别，无需精确命令格式

## 架构

```
                           ┌─────────────┐
                           │   Feishu    │
                           │   Webhook   │
                           └──────┬──────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        GATEWAY (:8000)                          │
│  Webhook处理 │ LLM代理 │ 能力路由 (模式判断)                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ LLM SERVICE   │   │  INVEST       │   │   CHAT        │
│   :8001       │   │   :8010       │   │   :8011       │
│ Qwen/Kimi     │   │ 投资分析      │   │ 个人化对话    │
└───────────────┘   └───────────────┘   └───────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │    DEV        │
                    │   :8012       │
                    │ Claude Code   │
                    └───────────────┘
```

详见 [架构演进设计文档](docs/ARCHITECTURE_EVOLUTION.md)

## 快速开始

### 前置要求

- Python 3.11+
- Docker 24.0+ & Docker Compose 2.20+

### 方式一：本地多进程模式（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/yourorg/investmanager.git
cd investmanager

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置:
# - WORK_DIR=/root/autowork
# - CLAUDE_CODE_WORKING_DIR=/root/autowork

# 3. 创建工作目录
mkdir -p /root/autowork/{data,logs,reports,config}
chmod -R 777 /root/autowork

# 4. 安装依赖
pip install -e .

# 5. 启动服务
make dev-multiprocess
# 或
./scripts/start-multiprocess.sh

# 6. 检查状态
curl http://localhost:8000/health
```

### 方式二：Docker 多进程部署

```bash
# 启动所有服务
make up-multiprocess

# 查看日志
make logs-multiprocess

# 停止服务
make down-multiprocess
```

### 方式三：单容器部署（简化版）

```bash
# 启动服务
docker compose -f docker-compose.standalone.yml up -d

# 检查状态
curl http://localhost:8000/health
```

## 服务地址

| 服务 | 端口 | 说明 |
|------|------|------|
| Gateway | 8000 | 流量入口、Webhook |
| LLM | 8001 | LLM API 代理 |
| Invest | 8010 | 投资分析能力 |
| Chat | 8011 | 对话能力 |
| Dev | 8012 | 开发模式 |
| API文档 | 8000/docs | Swagger UI |
| 健康检查 | 8000/health | 服务状态 |

## 项目结构

```
investmanager/
├── services/                    # 多进程服务
│   ├── gateway/                 # 网关服务 (:8000)
│   ├── llm/                     # LLM 服务 (:8001)
│   ├── invest/                  # 投资能力服务 (:8010)
│   ├── chat/                    # 对话能力服务 (:8011)
│   ├── dev/                     # 开发能力服务 (:8012)
│   └── capabilities/            # 能力基础类
├── src/
│   ├── feishu/
│   │   ├── gateway/             # 消息路由层
│   │   ├── capabilities/        # 能力实现
│   │   ├── bot.py               # 机器人核心
│   │   └── intent_parser.py     # 意图解析
│   ├── memory/                  # 个人化系统
│   ├── analysis/                # 分析模块
│   ├── backtest/                # 回测引擎
│   └── report/                  # 报告生成
├── config/                      # 配置模块
├── tests/                       # 测试套件
├── docs/                        # 文档
└── scripts/                     # 工具脚本
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
| `切换模式` | 切换工作模式 (投资/对话/开发) |
| `当前模式` | 查看当前模式 |
| `我的画像` | 查看个人偏好设置 |
| `清除记忆` | 清除个人信息 |
| `帮助` | 显示帮助 |

### 工作模式

| 模式 | 说明 |
|------|------|
| **INVEST** | 投资助手模式，支持自然语言对话 |
| **CHAT** | 通用对话模式，可讨论任何话题 |
| **DEV** | 开发模式，集成 Claude Code |

### 配置飞书

1. 在飞书开放平台创建应用
2. 配置权限和事件订阅
3. 设置Webhook URL: `https://your-domain/api/feishu/webhook`
4. 在 `.env` 中配置应用凭证

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `WORK_DIR` | 工作目录 | `/root/autowork` |
| `CLAUDE_CODE_WORKING_DIR` | Claude Code 工作目录 | `/root/autowork` |
| `SQLITE_DB_PATH` | 数据库路径 | `$WORK_DIR/data/investmanager.db` |
| `LLM_PROVIDER` | LLM提供商 | `alibaba_bailian` |
| `ALIBABA_BAILIAN_API_KEY` | 阿里百炼API密钥 | - |
| `ALIBABA_BAILIAN_MODEL` | 模型选择 | `kimi-k2.5` |
| `FEISHU_ENABLED` | 启用飞书 | `true` |

完整配置见 [.env.example](.env.example)

## 文档

- [架构演进设计文档](docs/ARCHITECTURE_EVOLUTION.md) - 架构演进历程
- [打包和运行说明书](docs/PACKAGING_AND_RUNNING_GUIDE.md) - 部署详解
- [个人化系统设计](docs/CHAT_PERSONALIZATION_DESIGN.md) - 个人化功能
- [命令系统设计](docs/COMPREHENSIVE_COMMAND_DESIGN.md) - 命令详解
- [变更日志](CHANGELOG.md) - 版本历史

## 开发

```bash
# 运行测试
pytest tests/ -v

# 代码检查
ruff check src/

# 类型检查
mypy src/

# 本地启动
make dev-multiprocess
```

## 许可证

[MIT License](LICENSE)

## 贡献

欢迎贡献！请阅读 [贡献指南](CONTRIBUTING.md)