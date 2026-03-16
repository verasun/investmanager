# InvestManager 部署说明

## 一、配置说明

### 1. 环境变量 (.env)

```bash
# 复制示例配置
cp .env.example .env

# 必要配置项
APP_ENV=production          # 运行环境
DATABASE_URL=postgresql://user:pass@host:5432/dbname
REDIS_URL=redis://host:6379/0
LOG_LEVEL=INFO
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