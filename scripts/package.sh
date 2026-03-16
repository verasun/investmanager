#!/bin/bash
# ============================================
# InvestManager - 构建打包脚本
# ============================================
# 用法: ./scripts/package.sh [选项]
#
# 功能:
#   1. 编译打包Python程序
#   2. 构建Docker镜像
#   3. 可选：导出镜像为tar文件
#   4. 可选：推送到镜像仓库
#
# 选项:
#   -t, --tag        镜像标签 (默认: latest)
#   -o, --output     导出镜像文件路径 (如: investmanager.tar)
#   -r, --registry   镜像仓库地址
#   -p, --push       构建后推送到仓库
#   --no-cache       不使用构建缓存
#   --export         导出镜像为tar文件
#   -h, --help       显示帮助
#
# 示例:
#   ./scripts/package.sh                    # 构建镜像
#   ./scripts/package.sh -t v1.0.0          # 指定版本标签
#   ./scripts/package.sh --export           # 构建并导出tar
#   ./scripts/package.sh -o app.tar         # 指定导出文件名
#   ./scripts/package.sh -r registry.com -p # 推送到仓库
# ============================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 默认配置
IMAGE_NAME="investmanager"
IMAGE_TAG="latest"
REGISTRY=""
OUTPUT_FILE=""
EXPORT_IMAGE=false
PUSH_IMAGE=false
USE_CACHE=true
DOCKERFILE="Dockerfile"

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_FILE="$2"
            EXPORT_IMAGE=true
            shift 2
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -p|--push)
            PUSH_IMAGE=true
            shift
            ;;
        --no-cache)
            USE_CACHE=false
            shift
            ;;
        --export)
            EXPORT_IMAGE=true
            shift
            ;;
        -h|--help)
            head -30 "$0" | tail -27
            exit 0
            ;;
        *)
            echo -e "${RED}未知选项: $1${NC}"
            exit 1
            ;;
    esac
done

cd "$PROJECT_DIR"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  InvestManager - 构建打包${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# ============================================
# 1. 环境检查
# ============================================
echo -e "${YELLOW}[1/5] 检查构建环境...${NC}"

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker未安装${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}错误: Docker守护进程未运行${NC}"
    exit 1
fi

echo -e "  ${GREEN}✓${NC} Docker已就绪"

# 检查必要文件
if [ ! -f "Dockerfile" ]; then
    echo -e "${RED}错误: Dockerfile不存在${NC}"
    exit 1
fi

if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}错误: pyproject.toml不存在${NC}"
    exit 1
fi

echo -e "  ${GREEN}✓${NC} 配置文件完整"
echo ""

# ============================================
# 2. 代码检查与准备
# ============================================
echo -e "${YELLOW}[2/5] 准备构建文件...${NC}"

# 生成poetry.lock（如果不存在）
if [ ! -f "poetry.lock" ]; then
    if command -v poetry &> /dev/null; then
        echo -e "  ${BLUE}生成poetry.lock...${NC}"
        poetry lock --no-interaction
    elif [ -f ".venv/bin/poetry" ]; then
        echo -e "  ${BLUE}使用venv生成poetry.lock...${NC}"
        .venv/bin/poetry lock --no-interaction
    fi
fi

# 创建必要的目录
mkdir -p logs reports data cache

echo -e "  ${GREEN}✓${NC} 构建文件准备完成"
echo ""

# ============================================
# 3. 构建Docker镜像
# ============================================
echo -e "${YELLOW}[3/5] 构建Docker镜像...${NC}"
echo ""

# 构建参数
BUILD_ARGS=""
if [ "$USE_CACHE" = false ]; then
    BUILD_ARGS="--no-cache"
fi

# 完整镜像名
if [ -n "$REGISTRY" ]; then
    FULL_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
else
    FULL_IMAGE_NAME="${IMAGE_NAME}:${IMAGE_TAG}"
fi

echo -e "${BLUE}镜像: ${FULL_IMAGE_NAME}${NC}"
echo -e "${BLUE}Dockerfile: ${DOCKERFILE}${NC}"
echo ""

# 执行构建
BUILD_START=$(date +%s)

BUILD_CMD="docker build \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    -t ${FULL_IMAGE_NAME} \
    -f ${DOCKERFILE} \
    ${BUILD_ARGS} \
    ."

echo -e "${BLUE}执行: ${BUILD_CMD}${NC}"
echo ""

if $BUILD_CMD; then
    BUILD_END=$(date +%s)
    BUILD_TIME=$((BUILD_END - BUILD_START))
    echo ""
    echo -e "${GREEN}✓ 镜像构建成功! (耗时: ${BUILD_TIME}秒)${NC}"
else
    echo ""
    echo -e "${RED}✗ 镜像构建失败!${NC}"
    exit 1
fi

# 标记为latest
if [ "$IMAGE_TAG" != "latest" ]; then
    docker tag "${FULL_IMAGE_NAME}" "${IMAGE_NAME}:latest"
    echo -e "  ${GREEN}✓${NC} 已标记为 ${IMAGE_NAME}:latest"
fi

echo ""

# ============================================
# 4. 导出镜像（可选）
# ============================================
if [ "$EXPORT_IMAGE" = true ]; then
    echo -e "${YELLOW}[4/5] 导出镜像文件...${NC}"

    # 确定输出文件名
    if [ -z "$OUTPUT_FILE" ]; then
        OUTPUT_FILE="${IMAGE_NAME}-${IMAGE_TAG}.tar"
    fi

    # 确保输出目录存在
    OUTPUT_DIR=$(dirname "$OUTPUT_FILE")
    if [ "$OUTPUT_DIR" != "." ] && [ ! -d "$OUTPUT_DIR" ]; then
        mkdir -p "$OUTPUT_DIR"
    fi

    echo -e "  ${BLUE}导出到: ${OUTPUT_FILE}${NC}"

    if docker save "${FULL_IMAGE_NAME}" -o "$OUTPUT_FILE"; then
        # 压缩镜像
        echo -e "  ${BLUE}压缩镜像文件...${NC}"
        gzip -f "$OUTPUT_FILE"

        OUTPUT_SIZE=$(du -h "${OUTPUT_FILE}.gz" | cut -f1)
        echo -e "  ${GREEN}✓${NC} 镜像已导出: ${OUTPUT_FILE}.gz (${OUTPUT_SIZE})"
    else
        echo -e "${RED}✗ 镜像导出失败!${NC}"
        exit 1
    fi
    echo ""
else
    echo -e "${YELLOW}[4/5] 跳过镜像导出${NC}"
    echo ""
fi

# ============================================
# 5. 推送镜像（可选）
# ============================================
if [ "$PUSH_IMAGE" = true ] && [ -n "$REGISTRY" ]; then
    echo -e "${YELLOW}[5/5] 推送镜像到仓库...${NC}"

    echo -e "  ${BLUE}仓库: ${REGISTRY}${NC}"

    if docker push "${FULL_IMAGE_NAME}"; then
        echo -e "  ${GREEN}✓${NC} 镜像已推送"
    else
        echo -e "${RED}✗ 镜像推送失败!${NC}"
        exit 1
    fi
    echo ""
else
    echo -e "${YELLOW}[5/5] 跳过镜像推送${NC}"
    echo ""
fi

# ============================================
# 构建摘要
# ============================================
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  构建完成!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${YELLOW}镜像信息:${NC}"
docker images "${FULL_IMAGE_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
echo ""

if [ "$EXPORT_IMAGE" = true ] && [ -f "${OUTPUT_FILE}.gz" ]; then
    echo -e "${YELLOW}导出文件:${NC}"
    echo -e "  ${GREEN}${OUTPUT_FILE}.gz${NC}"
    echo ""
fi

echo -e "${YELLOW}运行方式:${NC}"
echo -e "  ${BLUE}./scripts/run-image.sh ${FULL_IMAGE_NAME}${NC}"
echo ""
if [ "$EXPORT_IMAGE" = true ]; then
    echo -e "${YELLOW}从tar文件运行:${NC}"
    echo -e "  ${BLUE}docker load -i ${OUTPUT_FILE}.gz${NC}"
    echo -e "  ${BLUE}./scripts/run-image.sh ${IMAGE_NAME}:${IMAGE_TAG}${NC}"
    echo ""
fi