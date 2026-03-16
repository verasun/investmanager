#!/bin/bash
# ============================================
# InvestManager - Build Script
# ============================================
# Usage: ./scripts/build.sh [options]
#
# Options:
#   -t, --tag        Image tag (default: latest)
#   -p, --push       Push image to registry
#   -r, --registry   Docker registry URL
#   -c, --cache      Use build cache
#   --no-cache       Disable build cache
#   --prod           Production build
#   -h, --help       Show this help
# ============================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
IMAGE_NAME="investmanager"
IMAGE_TAG="latest"
REGISTRY=""
PUSH=false
USE_CACHE=true
PRODUCTION=false
DOCKERFILE="Dockerfile"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -p|--push)
            PUSH=true
            shift
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -c|--cache)
            USE_CACHE=true
            shift
            ;;
        --no-cache)
            USE_CACHE=false
            shift
            ;;
        --prod)
            PRODUCTION=true
            shift
            ;;
        --simple)
            DOCKERFILE="Dockerfile.simple"
            shift
            ;;
        -h|--help)
            head -20 "$0" | tail -15
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  InvestManager - Docker Build${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Build info
echo -e "${YELLOW}Build Configuration:${NC}"
echo -e "  Image:      ${GREEN}${IMAGE_NAME}:${IMAGE_TAG}${NC}"
echo -e "  Dockerfile: ${GREEN}${DOCKERFILE}${NC}"
echo -e "  Registry:   ${GREEN}${REGISTRY:-local}${NC}"
echo -e "  Cache:      ${GREEN}${USE_CACHE}${NC}"
echo -e "  Production: ${GREEN}${PRODUCTION}${NC}"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}Error: Docker daemon is not running${NC}"
    exit 1
fi

# Generate poetry.lock if not exists (skip if poetry not available locally)
if [ ! -f "poetry.lock" ]; then
    if command -v poetry &> /dev/null; then
        echo -e "${YELLOW}Generating poetry.lock...${NC}"
        poetry lock --no-interaction
    elif [ -f ".venv/bin/poetry" ]; then
        echo -e "${YELLOW}Generating poetry.lock using venv...${NC}"
        .venv/bin/poetry lock --no-interaction
    else
        echo -e "${YELLOW}poetry.lock not found. It will be generated during Docker build.${NC}"
    fi
fi

# Build arguments
BUILD_ARGS=""
if [ "$USE_CACHE" = false ]; then
    BUILD_ARGS="--no-cache"
fi

# Full image name
if [ -n "$REGISTRY" ]; then
    FULL_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
else
    FULL_IMAGE_NAME="${IMAGE_NAME}:${IMAGE_TAG}"
fi

# Build the image
echo -e "${YELLOW}Building Docker image...${NC}"
echo ""

BUILD_CMD="docker build \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    -t ${FULL_IMAGE_NAME} \
    -f ${DOCKERFILE} \
    ${BUILD_ARGS} \
    ."

if [ "$PRODUCTION" = true ]; then
    BUILD_CMD="docker build \
        --build-arg BUILDKIT_INLINE_CACHE=1 \
        --target production \
        -t ${FULL_IMAGE_NAME} \
        -f ${DOCKERFILE} \
        ${BUILD_ARGS} \
        ."
fi

echo -e "${BLUE}Running: ${BUILD_CMD}${NC}"
echo ""

if $BUILD_CMD; then
    echo ""
    echo -e "${GREEN}✓ Build successful!${NC}"
else
    echo ""
    echo -e "${RED}✗ Build failed!${NC}"
    exit 1
fi

# Show image size
echo ""
echo -e "${YELLOW}Image details:${NC}"
docker images "${FULL_IMAGE_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

# Push to registry if requested
if [ "$PUSH" = true ] && [ -n "$REGISTRY" ]; then
    echo ""
    echo -e "${YELLOW}Pushing to registry: ${REGISTRY}${NC}"

    if docker push "${FULL_IMAGE_NAME}"; then
        echo -e "${GREEN}✓ Push successful!${NC}"
    else
        echo -e "${RED}✗ Push failed!${NC}"
        exit 1
    fi
fi

# Tag as latest if not already
if [ "$IMAGE_TAG" != "latest" ]; then
    echo ""
    echo -e "${YELLOW}Tagging as latest...${NC}"
    docker tag "${FULL_IMAGE_NAME}" "${IMAGE_NAME}:latest"
fi

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Build Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "Run with: ${BLUE}./scripts/run.sh${NC}"
echo -e "Or:       ${BLUE}docker-compose up -d${NC}"