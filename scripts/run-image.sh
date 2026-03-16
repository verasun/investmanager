#!/bin/bash
# ============================================
# InvestManager - 镜像运行脚本
# ============================================
# 用法: ./scripts/run-image.sh [镜像名] [选项]
#
# 功能:
#   1. 加载Docker镜像（支持从tar文件）
#   2. 运行容器化应用
#   3. 管理容器生命周期
#
# 选项:
#   -l, --load      从tar文件加载镜像
#   -e, --env       环境变量文件 (默认: .env)
#   -p, --port      API端口映射 (默认: 8000:8000)
#   -w, --web       启用Web UI (端口 8501)
#   -d, --detach    后台运行
#   --name          容器名称 (默认: investmanager)
#   --network       Docker网络 (默认: investmanager-net)
#   -h, --help      显示帮助
#
# 示例:
#   ./scripts/run-image.sh                          # 运行默认镜像
#   ./scripts/run-image.sh investmanager:v1.0.0    # 运行指定版本
#   ./scripts/run-image.sh -l app.tar.gz           # 从tar加载并运行
#   ./scripts/run-image.sh -w                      # 启用Web UI
#   ./scripts/run-image.sh -d                      # 后台运行
# ============================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 默认配置
IMAGE_NAME="investmanager:latest"
ENV_FILE=".env"
API_PORT="8000"
WEB_PORT="8501"
CONTAINER_NAME="investmanager"
NETWORK_NAME="investmanager-net"
LOAD_TAR=""
ENABLE_WEB=false
DETACH=false

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 显示帮助
show_help() {
    head -28 "$0" | tail -25
    exit 0
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -l|--load)
            LOAD_TAR="$2"
            shift 2
            ;;
        -e|--env)
            ENV_FILE="$2"
            shift 2
            ;;
        -p|--port)
            API_PORT="$2"
            shift 2
            ;;
        -w|--web)
            ENABLE_WEB=true
            shift
            ;;
        -d|--detach)
            DETACH=true
            shift
            ;;
        --name)
            CONTAINER_NAME="$2"
            shift 2
            ;;
        --network)
            NETWORK_NAME="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            ;;
        -*)
            echo -e "${RED}未知选项: $1${NC}"
            show_help
            ;;
        *)
            # 位置参数：镜像名
            IMAGE_NAME="$1"
            shift
            ;;
    esac
done

cd "$PROJECT_DIR"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  InvestManager - 镜像运行${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# ============================================
# 1. 检查Docker环境
# ============================================
echo -e "${YELLOW}[1/4] 检查Docker环境...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker未安装${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}错误: Docker守护进程未运行${NC}"
    exit 1
fi

echo -e "  ${GREEN}✓${NC} Docker已就绪"
echo ""

# ============================================
# 2. 加载镜像（如果指定tar文件）
# ============================================
if [ -n "$LOAD_TAR" ]; then
    echo -e "${YELLOW}[2/4] 从tar文件加载镜像...${NC}"

    if [ ! -f "$LOAD_TAR" ]; then
        echo -e "${RED}错误: 文件不存在: ${LOAD_TAR}${NC}"
        exit 1
    fi

    echo -e "  ${BLUE}加载: ${LOAD_TAR}${NC}"

    # 解压并加载
    if [[ "$LOAD_TAR" == *.gz ]]; then
        gunzip -c "$LOAD_TAR" | docker load
    else
        docker load -i "$LOAD_TAR"
    fi

    echo -e "  ${GREEN}✓${NC} 镜像加载完成"
    echo ""
else
    echo -e "${YELLOW}[2/4] 检查镜像...${NC}"

    # 检查镜像是否存在
    if ! docker image inspect "$IMAGE_NAME" &> /dev/null; then
        echo -e "  ${YELLOW}镜像不存在，尝试拉取...${NC}"
        if docker pull "$IMAGE_NAME" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} 镜像拉取成功"
        else
            echo -e "${RED}错误: 镜像不存在: ${IMAGE_NAME}${NC}"
            echo -e "${YELLOW}请先运行: ./scripts/package.sh${NC}"
            exit 1
        fi
    else
        echo -e "  ${GREEN}✓${NC} 镜像已存在: ${IMAGE_NAME}"
    fi
    echo ""
fi

# 显示镜像信息
echo -e "${YELLOW}镜像信息:${NC}"
docker images "$IMAGE_NAME" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}" 2>/dev/null || \
    docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}" | head -5
echo ""

# ============================================
# 3. 准备运行环境
# ============================================
echo -e "${YELLOW}[3/4] 准备运行环境...${NC}"

# 创建网络（如果不存在）
if ! docker network inspect "$NETWORK_NAME" &> /dev/null; then
    echo -e "  ${BLUE}创建网络: ${NETWORK_NAME}${NC}"
    docker network create "$NETWORK_NAME"
fi
echo -e "  ${GREEN}✓${NC} 网络: ${NETWORK_NAME}"

# 创建必要目录
mkdir -p logs reports data cache
echo -e "  ${GREEN}✓${NC} 数据目录已创建"

# 检查环境变量文件
if [ ! -f "$ENV_FILE" ]; then
    if [ -f ".env.example" ]; then
        echo -e "  ${YELLOW}复制环境配置: .env.example -> ${ENV_FILE}${NC}"
        cp .env.example "$ENV_FILE"
    else
        echo -e "  ${YELLOW}警告: 环境配置文件不存在${NC}"
    fi
else
    echo -e "  ${GREEN}✓${NC} 环境配置: ${ENV_FILE}"
fi

# 停止并删除已存在的容器
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "  ${BLUE}停止并移除旧容器: ${CONTAINER_NAME}${NC}"
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
fi

echo ""

# ============================================
# 4. 运行容器
# ============================================
echo -e "${YELLOW}[4/4] 启动容器...${NC}"
echo ""

# 构建docker run命令
RUN_CMD="docker run"
RUN_CMD="$RUN_CMD --name ${CONTAINER_NAME}"
RUN_CMD="$RUN_CMD --network ${NETWORK_NAME}"
RUN_CMD="$RUN_CMD -p ${API_PORT}:8000"

# 端口映射
if [ "$ENABLE_WEB" = true ]; then
    RUN_CMD="$RUN_CMD -p ${WEB_PORT}:8501"
fi

# 环境变量
if [ -f "$ENV_FILE" ]; then
    RUN_CMD="$RUN_CMD --env-file ${ENV_FILE}"
fi

# 数据卷挂载
RUN_CMD="$RUN_CMD -v $(pwd)/logs:/app/logs"
RUN_CMD="$RUN_CMD -v $(pwd)/reports:/app/reports"
RUN_CMD="$RUN_CMD -v $(pwd)/data:/app/data"
RUN_CMD="$RUN_CMD -v $(pwd)/cache:/app/cache"

# 后台运行
if [ "$DETACH" = true ]; then
    RUN_CMD="$RUN_CMD -d"
else
    RUN_CMD="$RUN_CMD -it"
fi

# 重启策略
RUN_CMD="$RUN_CMD --restart unless-stopped"

# 镜像名
RUN_CMD="$RUN_CMD ${IMAGE_NAME}"

# 显示运行命令
echo -e "${BLUE}执行命令:${NC}"
echo -e "  ${RUN_CMD}"
echo ""

# 执行运行
if $RUN_CMD; then
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  容器启动成功!${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo -e "${YELLOW}服务地址:${NC}"
    echo -e "  API:    ${GREEN}http://localhost:${API_PORT}${NC}"
    echo -e "  Docs:   ${GREEN}http://localhost:${API_PORT}/docs${NC}"
    echo -e "  Health: ${GREEN}http://localhost:${API_PORT}/health${NC}"

    if [ "$ENABLE_WEB" = true ]; then
        echo -e "  Web:    ${GREEN}http://localhost:${WEB_PORT}${NC}"
    fi

    echo ""
    echo -e "${YELLOW}管理命令:${NC}"
    echo -e "  查看日志:   ${BLUE}docker logs -f ${CONTAINER_NAME}${NC}"
    echo -e "  进入容器:   ${BLUE}docker exec -it ${CONTAINER_NAME} /bin/bash${NC}"
    echo -e "  停止容器:   ${BLUE}docker stop ${CONTAINER_NAME}${NC}"
    echo -e "  重启容器:   ${BLUE}docker restart ${CONTAINER_NAME}${NC}"
    echo -e "  删除容器:   ${BLUE}docker rm -f ${CONTAINER_NAME}${NC}"
    echo ""

    # 健康检查
    if [ "$DETACH" = true ]; then
        echo -e "${YELLOW}等待服务就绪...${NC}"
        MAX_RETRIES=30
        RETRY_COUNT=0

        while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
            if curl -sf "http://localhost:${API_PORT}/health" > /dev/null 2>&1; then
                echo -e "${GREEN}✓ 服务已就绪!${NC}"
                break
            fi

            RETRY_COUNT=$((RETRY_COUNT + 1))
            echo -e "  ${YELLOW}等待中... ($RETRY_COUNT/$MAX_RETRIES)${NC}"
            sleep 2
        done

        if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
            echo -e "${RED}✗ 服务启动超时，请检查日志${NC}"
            echo -e "  ${BLUE}docker logs ${CONTAINER_NAME}${NC}"
        fi
    fi
else
    echo ""
    echo -e "${RED}============================================${NC}"
    echo -e "${RED}  容器启动失败!${NC}"
    echo -e "${RED}============================================${NC}"
    echo ""
    echo -e "${YELLOW}排查建议:${NC}"
    echo -e "  1. 检查端口是否被占用: ${BLUE}netstat -tlnp | grep -E '${API_PORT}|${WEB_PORT}'${NC}"
    echo -e "  2. 检查镜像是否存在: ${BLUE}docker images ${IMAGE_NAME}${NC}"
    echo -e "  3. 查看详细错误: ${BLUE}docker logs ${CONTAINER_NAME}${NC}"
    exit 1
fi