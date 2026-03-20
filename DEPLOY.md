# InvestManager 部署说明

## 一、架构概览

InvestManager v1.2 采用多进程架构：

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Feishu    │────▶│   Gateway    │────▶│  Capabilities    │
│   Webhook   │     │   :8000      │     │   :8010-8012     │
└─────────────┘     └──────────────┘     └──────────────────┘
```

| 服务 | 端口 | 职责 |
|------|------|------|
| Gateway | 8000 | 流量入口、路由、Webhook |
| LLM | 8001 | LLM API 代理 |
| Invest | 8010 | 投资分析能力 |
| Chat | 8011 | 对话能力+个人化 |
| Dev | 8012 | 开发模式+Claude Code |

---

## 二、部署方式

### 方式一：本地多进程模式（推荐开发）

```bash
# 1. 配置环境
cp .env.example .env
# 设置 WORK_DIR=/root/autowork

# 2. 创建工作目录
mkdir -p /root/autowork/{data,logs,reports,config}
chmod -R 777 /root/autowork

# 3. 安装依赖
pip install -e .

# 4. 启动服务
make dev-multiprocess
```

### 方式二：Docker 多进程部署

```bash
# 启动
make up-multiprocess

# 查看日志
make logs-multiprocess

# 停止
make down-multiprocess
```

### 方式三：单容器部署（简化版）

```bash
# 构建镜像
make package

# 启动服务
make run-image

# 后台运行
make run-image-detach
```

---

## 三、配置说明

### 3.1 核心环境变量

```bash
# ===========================================
# 工作目录配置
# ===========================================
WORK_DIR=/root/autowork
CLAUDE_CODE_WORKING_DIR=/root/autowork
SQLITE_DB_PATH=/root/autowork/data/investmanager.db
REPORT_OUTPUT_DIR=/root/autowork/reports

# ===========================================
# LLM 配置
# ===========================================
LLM_PROVIDER=alibaba_bailian
ALIBABA_BAILIAN_API_KEY=your_key
ALIBABA_BAILIAN_MODEL=kimi-k2.5

# ===========================================
# 飞书配置
# ===========================================
FEISHU_ENABLED=true
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_ENCRYPT_KEY=xxx
FEISHU_VERIFICATION_TOKEN=xxx

# ===========================================
# Claude Code 配置 (DEV 模式)
# ===========================================
CLAUDE_CODE_ENABLED=true
CLAUDE_CODE_WORKING_DIR=/root/autowork
```

### 3.2 多进程服务 URL

```bash
GATEWAY_URL=http://localhost:8000
LLM_SERVICE_URL=http://localhost:8001
INVEST_SERVICE_URL=http://localhost:8010
CHAT_SERVICE_URL=http://localhost:8011
DEV_SERVICE_URL=http://localhost:8012
```

### 3.3 目录结构

```
/root/autowork/
├── data/               # SQLite 数据库
│   └── investmanager.db
├── logs/               # 服务日志
│   ├── gateway.log
│   ├── llm.log
│   ├── invest.log
│   ├── chat.log
│   └── dev.log
├── reports/            # 分析报告
└── config/             # 配置文件
```

---

## 四、服务地址

| 服务 | 地址 |
|------|------|
| Gateway API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |
| LLM 服务 | http://localhost:8001 |
| Invest 服务 | http://localhost:8010 |
| Chat 服务 | http://localhost:8011 |
| Dev 服务 | http://localhost:8012 |

---

## 五、常用命令

```bash
# 查看所有命令
make help

# 本地多进程启动
make dev-multiprocess

# Docker 多进程启动
make up-multiprocess

# 查看日志
tail -f /root/autowork/logs/*.log

# 健康检查
curl http://localhost:8000/health

# 停止所有服务
pkill -f "python -m services"
```

---

## 六、故障排查

### 6.1 查看服务状态

```bash
# 检查所有服务健康
curl http://localhost:8000/health  # Gateway
curl http://localhost:8001/health  # LLM
curl http://localhost:8010/health  # Invest
curl http://localhost:8011/health  # Chat
curl http://localhost:8012/health  # Dev
```

### 6.2 查看日志

```bash
# Gateway 日志
tail -100 /root/autowork/logs/gateway.log

# LLM 日志
tail -100 /root/autowork/logs/llm.log

# 所有日志
tail -f /root/autowork/logs/*.log
```

### 6.3 重启服务

```bash
# 停止所有
pkill -f "python -m services"

# 重新启动
make dev-multiprocess
```

### 6.4 端口冲突

```bash
# 检查端口占用
netstat -tlnp | grep -E '800[0-2]|801[0-2]'

# 释放端口
kill -9 $(lsof -t -i:8000)
```

---

## 七、飞书配置

### 7.1 创建应用

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 创建企业自建应用
3. 配置权限：
   - `im:message` - 获取消息
   - `im:message:send_as_bot` - 发送消息

### 7.2 配置事件订阅

- 请求地址: `https://your-domain/webhook/feishu`
- 订阅事件: `im.message.receive_v1`

### 7.3 工作模式

| 模式 | 触发方式 | 说明 |
|------|----------|------|
| INVEST | 默认模式 | 投资助手，支持自然语言 |
| CHAT | 发送"切换到对话模式" | 通用对话，可讨论任何话题 |
| DEV | 发送"切换到开发模式" | Claude Code 集成 |

---

## 八、LLM 配置

### 阿里百炼 (推荐)

```bash
LLM_PROVIDER=alibaba_bailian
ALIBABA_BAILIAN_API_KEY=sk-xxx
ALIBABA_BAILIAN_MODEL=kimi-k2.5  # 或 qwen-turbo, qwen-plus
```

### OpenAI

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxx
```

### Anthropic

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-xxx
```

---

## 九、架构演进

详见 [架构演进设计文档](docs/ARCHITECTURE_EVOLUTION.md)

```
v0.1 单体 → v1.0 简化 → v1.1 个人化 → v1.2 多进程
PostgreSQL    SQLite        用户画像       Gateway+5服务
Redis         LRU Cache     工作模式       独立LLM服务
                            多LLM支持      Dev模式
```