# InvestManager 部署说明

## 一、配置说明

### 1. 环境变量 (.env)

```bash
# 复制示例配置
cp .env.example .env

# 核心配置项
APP_ENV=production          # 运行环境
SQLITE_DB_PATH=./data/investmanager.db  # 数据库路径
LOG_LEVEL=INFO

# LLM配置 (必填)
LLM_PROVIDER=alibaba_bailian  # openai, anthropic, alibaba_bailian
ALIBABA_BAILIAN_API_KEY=your_key  # 阿里百炼API密钥
ALIBABA_BAILIAN_MODEL=qwen-turbo   # 模型选择

# 飞书配置 (可选)
FEISHU_ENABLED=true
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_secret
```

### 2. 目录结构

```
investmanager/
├── .env              # 环境配置
├── logs/             # 日志目录
├── data/             # 数据目录
├── reports/          # 报告目录
└── cache/            # 缓存目录
```

---

## 二、部署方式

### 方式一：Docker镜像（推荐）

```bash
# 1. 构建镜像
make package

# 2. 启动服务
make run-image

# 3. 后台运行
make run-image-detach

# 4. 带Web UI启动
make run-image-web
```

### 方式二：导出/导入镜像

```bash
# 导出镜像
make package-export
# 生成: investmanager-latest.tar.gz

# 在目标机器导入并运行
docker load -i investmanager-latest.tar.gz
./scripts/run-image.sh
```

### 方式三：Docker Compose

```bash
# 启动所有服务（API + DB + Redis）
make up

# 启动Web UI
make web

# 停止服务
make down
```

---

## 三、服务地址

| 服务 | 地址 |
|------|------|
| API | http://localhost:8000 |
| API文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |
| Web UI | http://localhost:8501 |

---

## 四、常用命令

```bash
make help           # 查看所有命令
make package        # 构建镜像
make run-image      # 运行镜像
make logs           # 查看日志
make down           # 停止服务
make clean          # 清理临时文件
```

---

## 五、故障排查

```bash
# 查看容器日志
docker logs -f investmanager

# 进入容器
docker exec -it investmanager /bin/bash

# 检查健康状态
curl http://localhost:8000/health
```

---

## 六、飞书配置

### 1. 创建飞书应用

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 创建企业自建应用
3. 配置权限：
   - `im:message` - 获取消息
   - `im:message:send_as_bot` - 发送消息
   - `bitable:record` - 多维表格操作（可选）

### 2. 配置事件订阅

- 请求地址: `https://your-domain/api/feishu/webhook`
- 订阅事件: `im.message.receive_v1`

### 3. 配置环境变量

```bash
FEISHU_ENABLED=true
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_ENCRYPT_KEY=xxx          # 加密密钥（可选）
FEISHU_VERIFICATION_TOKEN=xxx   # 验证令牌（可选）
```

### 4. 工作模式

| 模式 | 触发方式 | 说明 |
|------|----------|------|
| INVEST | 默认模式 | 投资助手，支持自然语言 |
| CHAT | 发送"切换模式" | 通用对话，可讨论任何话题 |
| STRICT | 再次切换 | 仅响应精确命令 |

---

## 七、LLM配置

### 阿里百炼 (推荐)

```bash
LLM_PROVIDER=alibaba_bailian
ALIBABA_BAILIAN_API_KEY=sk-xxx
ALIBABA_BAILIAN_MODEL=qwen-turbo  # 或 qwen-plus, qwen-max
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