# InvestManager 打包和运行说明书

## 目录

1. [系统要求](#1-系统要求)
2. [环境准备](#2-环境准备)
3. [配置说明](#3-配置说明)
4. [Docker镜像构建](#4-docker镜像构建)
5. [容器运行](#5-容器运行)
6. [飞书集成配置](#6-飞书集成配置)
7. [OAuth2邮件配置](#7-oauth2邮件配置)
8. [健康检查与监控](#8-健康检查与监控)
9. [数据备份与恢复](#9-数据备份与恢复)
10. [常见问题排查](#10-常见问题排查)

---

## 1. 系统要求

### 1.1 硬件要求

| 资源 | 最低配置 | 推荐配置 |
|------|----------|----------|
| CPU | 2核 | 4核+ |
| 内存 | 2GB | 4GB+ |
| 磁盘 | 10GB | 50GB+ (数据存储) |
| 网络 | 100Mbps | 1Gbps |

### 1.2 软件要求

| 软件 | 版本要求 | 用途 |
|------|----------|------|
| Docker | 24.0+ | 容器运行时 |
| Docker Compose | 2.20+ | 容器编排 |
| Git | 2.30+ | 代码获取 |

### 1.3 端口要求

| 端口 | 服务 | 说明 |
|------|------|------|
| 8000 | API服务 | HTTP API接口 |
| 8000 | Webhook | 飞书事件回调 |

---

## 2. 环境准备

### 2.1 安装Docker

**Ubuntu/Debian:**

```bash
# 更新包索引
sudo apt-get update

# 安装依赖
sudo apt-get install -y ca-certificates curl gnupg

# 添加Docker官方GPG密钥
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# 添加Docker仓库
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 安装Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 启动Docker服务
sudo systemctl enable docker
sudo systemctl start docker

# 验证安装
docker --version
docker compose version
```

**CentOS/RHEL:**

```bash
# 安装必要工具
sudo yum install -y yum-utils

# 添加Docker仓库
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# 安装Docker
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 启动Docker服务
sudo systemctl enable docker
sudo systemctl start docker

# 验证安装
docker --version
docker compose version
```

### 2.2 获取代码

```bash
# 克隆代码仓库
git clone https://github.com/your-org/investmanager.git
cd investmanager

# 查看项目结构
ls -la
```

### 2.3 创建必要目录

```bash
# 创建数据存储目录
mkdir -p data logs config

# 设置目录权限
chmod 755 data logs config
```

---

## 3. 配置说明

### 3.1 配置文件结构

```
config/
├── settings.py       # 主配置文件
├── email.yaml        # 邮件配置
└── feishu.yaml       # 飞书配置
```

### 3.2 环境变量配置

复制环境变量模板：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# ===========================================
# 基础配置
# ===========================================

# 应用环境: development, staging, production
APP_ENV=production

# 日志级别: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# API服务端口
API_PORT=8000

# ===========================================
# 数据库配置 (SQLite模式)
# ===========================================

# 数据库后端: sqlite
DATABASE_BACKEND=sqlite

# SQLite数据库文件路径
SQLITE_DB_PATH=./data/investmanager.db

# ===========================================
# 缓存配置
# ===========================================

# 启用本地缓存
LOCAL_CACHE_ENABLED=true

# 缓存最大条目数
LOCAL_CACHE_MAX_SIZE=1000

# 缓存默认TTL (秒)
LOCAL_CACHE_TTL=300

# ===========================================
# 邮件配置 (OAuth2模式)
# ===========================================

# 邮件服务提供商: gmail, outlook, qq, custom
EMAIL_PROVIDER=gmail

# OAuth2客户端ID
EMAIL_OAUTH2_CLIENT_ID=your-client-id.apps.googleusercontent.com

# OAuth2客户端密钥
EMAIL_OAUTH2_CLIENT_SECRET=your-client-secret

# OAuth2刷新令牌
EMAIL_OAUTH2_REFRESH_TOKEN=your-refresh-token

# OAuth2令牌URL (可选, 使用默认值)
EMAIL_OAUTH2_TOKEN_URL=https://oauth2.googleapis.com/token

# 发件人邮箱地址
EMAIL_FROM_ADDRESS=your-email@gmail.com

# 默认收件人列表 (逗号分隔)
EMAIL_TO_ADDRESSES=recipient1@example.com,recipient2@example.com

# ===========================================
# 飞书配置
# ===========================================

# 启用飞书集成
FEISHU_ENABLED=true

# 飞书应用ID
FEISHU_APP_ID=cli_xxxxxxxxxxxx

# 飞书应用密钥
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxx

# 飞书加密密钥 (用于事件回调验签)
FEISHU_ENCRYPT_KEY=xxxxxxxx

# 飞书验证令牌
FEISHU_VERIFICATION_TOKEN=xxxxxxxx

# 飞书多维表格Token (可选)
FEISHU_BITABLE_TOKEN=xxxxxxxxxxxxxxxxxxxx

# 飞书文档文件夹Token (可选)
FEISHU_FOLDER_TOKEN=xxxxxxxxxxxxxxxxxxxx
```

### 3.3 邮件YAML配置 (可选)

创建 `config/email.yaml`:

```yaml
email:
  provider: gmail

  oauth2:
    client_id: "${EMAIL_OAUTH2_CLIENT_ID}"
    client_secret: "${EMAIL_OAUTH2_CLIENT_SECRET}"
    refresh_token: "${EMAIL_OAUTH2_REFRESH_TOKEN}"
    token_url: "https://oauth2.googleapis.com/token"

  from_address: "${EMAIL_FROM_ADDRESS}"

  default_recipients:
    - "${EMAIL_TO_ADDRESSES}"

  templates:
    daily_report:
      subject: "InvestManager 日报 - {{date}}"
      enabled: true
    weekly_report:
      subject: "InvestManager 周报 - {{week}}"
      enabled: true
```

### 3.4 飞书YAML配置 (可选)

创建 `config/feishu.yaml`:

```yaml
feishu:
  enabled: true

  app:
    id: "${FEISHU_APP_ID}"
    secret: "${FEISHU_APP_SECRET}"

  security:
    encrypt_key: "${FEISHU_ENCRYPT_KEY}"
    verification_token: "${FEISHU_VERIFICATION_TOKEN}"

  bitable:
    token: "${FEISHU_BITABLE_TOKEN}"
    enabled: false

  document:
    folder_token: "${FEISHU_FOLDER_TOKEN}"
    enabled: true

  bot:
    welcome_message: "欢迎使用InvestManager智能投资助手!"
    help_text: |
      可用命令:
      - 收集数据 <股票代码> - 收集股票数据
      - 分析 <股票代码> - 分析股票
      - 回测 <策略> <股票代码> - 运行回测
      - 生成报告 [类型] - 生成分析报告
      - 发送报告 <邮箱/飞书> - 发送报告
      - 任务状态 <任务ID> - 查询任务状态
      - 帮助 - 显示帮助信息
```

---

## 4. Docker镜像构建

### 4.1 构建命令

**标准构建:**

```bash
# 构建镜像
docker build -f Dockerfile.standalone -t investmanager:latest .

# 查看镜像
docker images investmanager
```

**带构建参数:**

```bash
# 指定Python版本
docker build -f Dockerfile.standalone \
  --build-arg PYTHON_VERSION=3.11 \
  -t investmanager:latest .

# 指定镜像标签
docker build -f Dockerfile.standalone \
  -t investmanager:v1.0.0 \
  -t investmanager:latest .
```

**多平台构建:**

```bash
# 启用buildx
docker buildx create --use

# 构建多平台镜像
docker buildx build -f Dockerfile.standalone \
  --platform linux/amd64,linux/arm64 \
  -t investmanager:latest .
```

### 4.2 Dockerfile说明

`Dockerfile.standalone` 内容解析：

```dockerfile
# 基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml poetry.lock* ./

# 安装Python依赖
RUN pip install --no-cache-dir -e ".[dev]" || \
    pip install --no-cache-dir -e "."

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p /app/data /app/logs /app/config

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV DATABASE_BACKEND=sqlite

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 4.3 镜像优化建议

**减小镜像体积:**

```dockerfile
# 使用多阶段构建
FROM python:3.11-slim as builder

WORKDIR /app
COPY pyproject.toml poetry.lock* ./
RUN pip install --no-cache-dir --target=/app/deps -e "."

FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /app/deps /usr/local/lib/python3.11/site-packages
COPY . .

RUN mkdir -p /app/data /app/logs
ENV PYTHONUNBUFFERED=1
ENV DATABASE_BACKEND=sqlite

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 5. 容器运行

### 5.1 使用Docker Compose (推荐)

**启动服务:**

```bash
# 启动所有服务
docker compose -f docker-compose.standalone.yml up -d

# 查看服务状态
docker compose -f docker-compose.standalone.yml ps

# 查看日志
docker compose -f docker-compose.standalone.yml logs -f
```

**停止服务:**

```bash
# 停止服务
docker compose -f docker-compose.standalone.yml stop

# 停止并删除容器
docker compose -f docker-compose.standalone.yml down

# 停止并删除容器和数据卷
docker compose -f docker-compose.standalone.yml down -v
```

**重启服务:**

```bash
# 重启服务
docker compose -f docker-compose.standalone.yml restart

# 重新构建并启动
docker compose -f docker-compose.standalone.yml up -d --build
```

### 5.2 Docker Compose配置文件

`docker-compose.standalone.yml` 内容：

```yaml
version: '3.8'

services:
  investmanager:
    build:
      context: .
      dockerfile: Dockerfile.standalone
    image: investmanager:latest
    container_name: investmanager
    restart: unless-stopped

    ports:
      - "${API_PORT:-8000}:8000"

    volumes:
      # 数据持久化
      - ./data:/app/data
      # 日志持久化
      - ./logs:/app/logs
      # 配置文件挂载
      - ./config:/app/config:ro
      # 环境变量文件
      - ./.env:/app/.env:ro

    environment:
      - APP_ENV=${APP_ENV:-production}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - DATABASE_BACKEND=sqlite
      - SQLITE_DB_PATH=/app/data/investmanager.db
      - LOCAL_CACHE_ENABLED=${LOCAL_CACHE_ENABLED:-true}
      - FEISHU_ENABLED=${FEISHU_ENABLED:-false}

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 5.3 使用Docker命令运行

**基本运行:**

```bash
docker run -d \
  --name investmanager \
  --restart unless-stopped \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/config:/app/config:ro \
  -e DATABASE_BACKEND=sqlite \
  -e FEISHU_ENABLED=true \
  investmanager:latest
```

**完整参数运行:**

```bash
docker run -d \
  --name investmanager \
  --restart unless-stopped \
  --memory="2g" \
  --cpus="2" \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/config:/app/config:ro \
  --env-file .env \
  investmanager:latest
```

### 5.4 生产环境配置

**创建生产环境配置文件 `docker-compose.prod.yml`:**

```yaml
version: '3.8'

services:
  investmanager:
    build:
      context: .
      dockerfile: Dockerfile.standalone
    image: investmanager:latest
    container_name: investmanager
    restart: always

    ports:
      - "8000:8000"

    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config:ro
      - ./.env:/app/.env:ro

    environment:
      - APP_ENV=production
      - LOG_LEVEL=WARNING
      - DATABASE_BACKEND=sqlite

    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "10"

    labels:
      - "com.investmanager.version=1.0.0"
      - "com.investmanager.description=Quantitative Investment Analysis System"
```

**启动生产环境:**

```bash
docker compose -f docker-compose.prod.yml up -d
```

---

## 6. 飞书集成配置

### 6.1 创建飞书应用

1. **登录飞书开放平台**

   访问 https://open.feishu.cn/ 并登录

2. **创建企业自建应用**

   - 点击「创建企业自建应用」
   - 填写应用名称：`InvestManager`
   - 填写应用描述：`智能投资分析助手`
   - 上传应用图标

3. **获取应用凭证**

   在「凭证与基础信息」页面获取：
   - App ID
   - App Secret

4. **配置权限**

   在「权限管理」中开通以下权限：

   | 权限名称 | 权限标识 | 用途 |
   |---------|---------|------|
   | 获取与更新群组信息 | im:chat:readonly | 群聊消息 |
   | 获取与发送单聊、群聊消息 | im:message | 发送消息 |
   | 接收群聊消息 | im:message.group_at_msg | 接收@消息 |
   | 接收单聊消息 | im:message.p2p_msg | 接收私聊 |
   | 查看、评论、编辑和管理云空间中所有文件 | drive:drive | 文档操作 |
   | 查看、评论、编辑和管理多维表格 | bitable:bitable | 多维表格 |

### 6.2 配置事件订阅

1. **配置请求网址**

   在「事件订阅」页面设置：
   ```
   https://your-domain.com/api/feishu/webhook
   ```

2. **获取加密配置**

   - Encrypt Key：用于消息加密
   - Verification Token：用于验签

3. **添加事件**

   订阅以下事件：
   - `im.message.receive_v1` - 接收消息

### 6.3 配置环境变量

更新 `.env` 文件：

```bash
# 飞书配置
FEISHU_ENABLED=true
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxx
FEISHU_ENCRYPT_KEY=xxxxxxxx
FEISHU_VERIFICATION_TOKEN=xxxxxxxx
```

### 6.4 验证飞书集成

**测试Webhook连接:**

```bash
# 发送验证请求
curl -X POST https://your-domain.com/api/feishu/webhook \
  -H "Content-Type: application/json" \
  -d '{"type":"url_verification","challenge":"test123"}'

# 预期响应
# {"challenge":"test123"}
```

**检查飞书状态:**

```bash
# 查看飞书集成状态
curl https://your-domain.com/api/feishu/status

# 预期响应
# {"status":"ok","enabled":true}
```

### 6.5 飞书命令使用

在飞书聊天中发送以下命令：

| 命令 | 说明 | 示例 |
|-----|------|-----|
| 收集数据 <代码> | 收集股票数据 | `收集数据 000001.SZ` |
| 分析 <代码> | 分析股票 | `分析 600000.SH` |
| 回测 <策略> <代码> | 运行回测 | `回测 ma_cross 000001.SZ` |
| 生成报告 [类型] | 生成报告 | `生成报告 daily` |
| 发送报告 <目标> | 发送报告 | `发送报告 feishu` |
| 任务状态 <ID> | 查询任务 | `任务状态 task_123` |
| 帮助 | 显示帮助 | `帮助` |

---

## 7. OAuth2邮件配置

### 7.1 Gmail OAuth2配置

**步骤1: 创建Google Cloud项目**

1. 访问 https://console.cloud.google.com/
2. 创建新项目或选择现有项目
3. 启用Gmail API

**步骤2: 配置OAuth2同意屏幕**

1. 导航到「API和服务」→「OAuth2同意屏幕」
2. 选择「外部」用户类型
3. 填写应用名称、支持邮箱
4. 添加作用域：`https://mail.google.com/`
5. 添加测试用户（您的Gmail地址）

**步骤3: 创建OAuth2凭证**

1. 导航到「API和服务」→「凭证」
2. 点击「创建凭证」→「OAuth2客户端ID」
3. 应用类型选择「桌面应用」
4. 记录Client ID和Client Secret

**步骤4: 获取Refresh Token**

运行OAuth2设置脚本：

```bash
# 进入容器
docker exec -it investmanager bash

# 运行设置脚本
python scripts/email_oauth2_setup.py --provider gmail \
  --client-id "your-client-id.apps.googleusercontent.com" \
  --client-secret "your-client-secret"

# 按提示访问授权URL，获取授权码，完成授权
# 脚本将输出refresh_token
```

或手动获取：

```bash
# 1. 生成授权URL
# 访问以下URL（替换client_id）:
https://accounts.google.com/o/oauth2/v2/auth?client_id=YOUR_CLIENT_ID&redirect_uri=urn:ietf:wg:oauth:2.0:oob&response_type=code&scope=https://mail.google.com/

# 2. 授权后获取code

# 3. 交换token
curl -X POST https://oauth2.googleapis.com/token \
  -d "client_id=YOUR_CLIENT_ID" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "code=AUTHORIZATION_CODE" \
  -d "redirect_uri=urn:ietf:wg:oauth:2.0:oob" \
  -d "grant_type=authorization_code"

# 记录返回的refresh_token
```

### 7.2 Outlook OAuth2配置

**步骤1: 注册Azure应用**

1. 访问 https://portal.azure.com/
2. 导航到「Azure Active Directory」→「应用注册」
3. 点击「新注册」
4. 名称：`InvestManager`
5. 受支持的账户类型：选择适当选项
6. 重定向URI：`urn:ietf:wg:oauth:2.0:oob`

**步骤2: 获取凭证**

记录：
- 应用程序(客户端)ID
- 目录(租户)ID

创建客户端密钥：
1. 导航到「证书和密码」
2. 点击「新客户端密码」
3. 记录密钥值

**步骤3: 配置权限**

添加API权限：
- `SMTP.Send`
- `offline_access`

**步骤4: 获取Refresh Token**

```bash
# 运行设置脚本
python scripts/email_oauth2_setup.py --provider outlook \
  --client-id "your-client-id" \
  --client-secret "your-client-secret"
```

### 7.3 更新环境变量

```bash
# 更新.env文件
EMAIL_PROVIDER=gmail
EMAIL_OAUTH2_CLIENT_ID=your-client-id.apps.googleusercontent.com
EMAIL_OAUTH2_CLIENT_SECRET=your-client-secret
EMAIL_OAUTH2_REFRESH_TOKEN=your-refresh-token
EMAIL_FROM_ADDRESS=your-email@gmail.com
EMAIL_TO_ADDRESSES=recipient@example.com
```

### 7.4 测试邮件发送

```bash
# 测试邮件发送API
curl -X POST http://localhost:8000/api/email/test \
  -H "Content-Type: application/json" \
  -d '{"to": "test@example.com"}'
```

---

## 8. 健康检查与监控

### 8.1 健康检查端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 整体健康状态 |
| `/health/ready` | GET | 就绪状态 |
| `/health/live` | GET | 存活状态 |
| `/api/feishu/status` | GET | 飞书集成状态 |

### 8.2 健康检查响应

**正常响应:**

```json
{
  "status": "healthy",
  "timestamp": "2024-03-16T10:00:00Z",
  "components": {
    "database": "ok",
    "cache": "ok",
    "feishu": "ok"
  }
}
```

**异常响应:**

```json
{
  "status": "unhealthy",
  "timestamp": "2024-03-16T10:00:00Z",
  "components": {
    "database": "error: connection failed",
    "cache": "ok",
    "feishu": "disabled"
  }
}
```

### 8.3 监控配置

**Prometheus指标 (可选):**

```yaml
# 添加到docker-compose.standalone.yml
services:
  investmanager:
    # ... 其他配置
    labels:
      - "prometheus.io/scrape=true"
      - "prometheus.io/port=8000"
      - "prometheus.io/path=/metrics"
```

**日志收集:**

```bash
# 查看实时日志
docker compose logs -f investmanager

# 导出日志
docker compose logs investmanager > logs/container.log

# 查看最近100行日志
docker compose logs --tail=100 investmanager
```

### 8.4 告警配置 (可选)

使用外部监控工具（如Prometheus + Alertmanager）配置告警规则：

```yaml
# alertmanager规则示例
groups:
  - name: investmanager
    rules:
      - alert: ServiceDown
        expr: up{job="investmanager"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "InvestManager服务不可用"

      - alert: HighMemoryUsage
        expr: container_memory_usage_bytes{name="investmanager"} > 2000000000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "InvestManager内存使用过高"
```

---

## 9. 数据备份与恢复

### 9.1 数据备份

**手动备份:**

```bash
# 创建备份目录
mkdir -p backups

# 备份SQLite数据库
cp data/investmanager.db backups/investmanager_$(date +%Y%m%d_%H%M%S).db

# 备份配置文件
tar -czf backups/config_$(date +%Y%m%d_%H%M%S).tar.gz config/ .env

# 备份日志
tar -czf backups/logs_$(date +%Y%m%d_%H%M%S).tar.gz logs/
```

**自动备份脚本 `scripts/backup.sh`:**

```bash
#!/bin/bash

# 配置
BACKUP_DIR="./backups"
DATA_DIR="./data"
CONFIG_DIR="./config"
RETENTION_DAYS=30

# 创建备份目录
mkdir -p $BACKUP_DIR

# 生成时间戳
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 备份数据库
cp $DATA_DIR/investmanager.db $BACKUP_DIR/investmanager_$TIMESTAMP.db

# 备份配置
tar -czf $BACKUP_DIR/config_$TIMESTAMP.tar.gz $CONFIG_DIR .env 2>/dev/null

# 清理旧备份
find $BACKUP_DIR -type f -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $TIMESTAMP"
```

**设置定时备份:**

```bash
# 添加crontab任务
crontab -e

# 每天凌晨2点执行备份
0 2 * * * /path/to/investmanager/scripts/backup.sh >> /var/log/investmanager_backup.log 2>&1
```

### 9.2 数据恢复

**恢复数据库:**

```bash
# 停止服务
docker compose down

# 恢复数据库
cp backups/investmanager_20240316_020000.db data/investmanager.db

# 启动服务
docker compose up -d
```

**恢复配置:**

```bash
# 解压配置备份
tar -xzf backups/config_20240316_020000.tar.gz

# 重启服务
docker compose restart
```

### 9.3 数据迁移

**从PostgreSQL迁移到SQLite:**

```bash
# 1. 导出PostgreSQL数据
docker exec postgres pg_dump -U user investmanager > postgres_backup.sql

# 2. 转换SQL语法（根据需要调整）
# 注意：需要处理PostgreSQL特有语法

# 3. 导入到SQLite
sqlite3 data/investmanager.db < converted_data.sql
```

---

## 10. 常见问题排查

### 10.1 容器无法启动

**问题现象:**
```
Error: container investmanager: container not found
```

**排查步骤:**

```bash
# 1. 检查镜像是否存在
docker images investmanager

# 2. 检查容器日志
docker logs investmanager

# 3. 检查端口占用
netstat -tlnp | grep 8000

# 4. 检查磁盘空间
df -h

# 5. 检查内存
free -m
```

**解决方案:**

```bash
# 释放端口
kill -9 $(lsof -t -i:8000)

# 清理容器
docker rm -f investmanager

# 重新构建
docker compose up -d --build
```

### 10.2 数据库连接失败

**问题现象:**
```
sqlite3.OperationalError: unable to open database file
```

**排查步骤:**

```bash
# 1. 检查数据目录
ls -la data/

# 2. 检查文件权限
stat data/investmanager.db

# 3. 检查容器挂载
docker inspect investmanager | grep -A 10 Mounts
```

**解决方案:**

```bash
# 创建数据目录
mkdir -p data

# 修复权限
chmod 755 data
chmod 644 data/investmanager.db

# 重启容器
docker compose restart
```

### 10.3 飞书Webhook验证失败

**问题现象:**
```
Feishu webhook verification failed
```

**排查步骤:**

```bash
# 1. 检查飞书配置
curl http://localhost:8000/api/feishu/status

# 2. 检查环境变量
docker exec investmanager env | grep FEISHU

# 3. 测试webhook端点
curl -X POST http://localhost:8000/api/feishu/webhook \
  -H "Content-Type: application/json" \
  -d '{"type":"url_verification","challenge":"test"}'
```

**解决方案:**

```bash
# 检查配置
grep FEISHU .env

# 更新配置
docker compose down
# 修改.env文件
docker compose up -d
```

### 10.4 邮件发送失败

**问题现象:**
```
SMTP authentication failed
```

**排查步骤:**

```bash
# 1. 检查OAuth2配置
docker exec investmanager env | grep EMAIL

# 2. 测试OAuth2 token
curl http://localhost:8000/api/email/test \
  -X POST -H "Content-Type: application/json" \
  -d '{"to":"test@example.com"}'

# 3. 查看详细日志
docker compose logs | grep -i email
```

**解决方案:**

```bash
# 重新获取refresh token
python scripts/email_oauth2_setup.py --provider gmail \
  --client-id "xxx" \
  --client-secret "xxx"

# 更新.env
# EMAIL_OAUTH2_REFRESH_TOKEN=new_token

# 重启服务
docker compose restart
```

### 10.5 内存使用过高

**问题现象:**
容器内存使用持续增长

**排查步骤:**

```bash
# 1. 查看容器资源使用
docker stats investmanager

# 2. 查看进程内存
docker exec investmanager ps aux --sort=-%mem

# 3. 检查缓存统计
curl http://localhost:8000/api/cache/stats
```

**解决方案:**

```bash
# 调整缓存配置
# 在.env中设置:
LOCAL_CACHE_MAX_SIZE=500
LOCAL_CACHE_TTL=60

# 重启服务
docker compose restart

# 或限制容器内存
docker update --memory="2g" investmanager
```

### 10.6 日志查看

```bash
# 查看所有日志
docker compose logs

# 实时查看
docker compose logs -f

# 查看最近100行
docker compose logs --tail=100

# 过滤特定内容
docker compose logs | grep ERROR

# 导出日志
docker compose logs > debug.log
```

### 10.7 重置服务

**完全重置:**

```bash
# 停止并删除所有资源
docker compose down -v

# 删除数据（谨慎操作！）
rm -rf data/*

# 重新启动
docker compose up -d
```

**保留数据重置:**

```bash
# 备份数据
cp -r data data_backup

# 重置容器
docker compose down
docker compose up -d --build
```

---

## 附录

### A. 常用命令速查

```bash
# 构建镜像
docker build -f Dockerfile.standalone -t investmanager:latest .

# 启动服务
docker compose -f docker-compose.standalone.yml up -d

# 停止服务
docker compose -f docker-compose.standalone.yml down

# 查看日志
docker compose -f docker-compose.standalone.yml logs -f

# 重启服务
docker compose -f docker-compose.standalone.yml restart

# 进入容器
docker exec -it investmanager bash

# 健康检查
curl http://localhost:8000/health

# 运行测试
./venv/bin/python -m pytest tests/ -v
```

### B. 配置检查清单

- [ ] Docker已安装并运行
- [ ] 端口8000未被占用
- [ ] 数据目录已创建
- [ ] `.env`文件已配置
- [ ] 飞书应用已创建（如需）
- [ ] OAuth2凭证已获取（如需）
- [ ] 防火墙已开放端口

### C. 技术支持

- **文档**: `docs/DEPLOYMENT_GUIDE.html`
- **问题反馈**: 创建GitHub Issue
- **日志位置**: `./logs/`
- **数据位置**: `./data/`