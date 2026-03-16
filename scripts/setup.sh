#!/bin/bash
# ============================================
# InvestManager - Development Setup Script
# ============================================
# Usage: ./scripts/setup.sh
#
# This script initializes the development environment:
# - Checks system dependencies (Docker, Python, Poetry)
# - Creates virtual environment
# - Installs Python dependencies
# - Copies environment configuration
# - Creates necessary directories
# - Sets up pre-commit hooks
# ============================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  InvestManager - Development Setup${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# ============================================
# Check System Dependencies
# ============================================
echo -e "${YELLOW}Checking system dependencies...${NC}"
echo ""

MISSING_DEPS=()

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    echo -e "  ${GREEN}✓${NC} Python ${PYTHON_VERSION}"
else
    echo -e "  ${RED}✗${NC} Python not found"
    MISSING_DEPS+=("python3")
fi

# Check pip
if command -v pip3 &> /dev/null || command -v pip &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} pip"
else
    echo -e "  ${RED}✗${NC} pip not found"
    MISSING_DEPS+=("pip")
fi

# Check Poetry (optional)
if command -v poetry &> /dev/null; then
    POETRY_VERSION=$(poetry --version 2>&1 | awk '{print $3}' | tr -d ')')
    echo -e "  ${GREEN}✓${NC} Poetry ${POETRY_VERSION}"
else
    echo -e "  ${YELLOW}○${NC} Poetry not found (optional, will use pip)"
fi

# Check Docker
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version 2>&1 | awk '{print $3}' | tr -d ',')
    echo -e "  ${GREEN}✓${NC} Docker ${DOCKER_VERSION}"
else
    echo -e "  ${YELLOW}○${NC} Docker not found (optional for local development)"
fi

# Check Docker Compose
if docker compose version &> /dev/null; then
    COMPOSE_VERSION=$(docker compose version --short 2>&1)
    echo -e "  ${GREEN}✓${NC} Docker Compose ${COMPOSE_VERSION}"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_VERSION=$(docker-compose --version 2>&1 | awk '{print $3}' | tr -d ',')
    echo -e "  ${GREEN}✓${NC} Docker Compose ${COMPOSE_VERSION}"
else
    echo -e "  ${YELLOW}○${NC} Docker Compose not found (optional)"
fi

# Check git
if command -v git &> /dev/null; then
    GIT_VERSION=$(git --version 2>&1 | awk '{print $3}')
    echo -e "  ${GREEN}✓${NC} Git ${GIT_VERSION}"
else
    echo -e "  ${YELLOW}○${NC} Git not found (optional)"
fi

echo ""

# Check for missing critical dependencies
if [ ${#MISSING_DEPS[@]} -ne 0 ]; then
    echo -e "${RED}Error: Missing critical dependencies: ${MISSING_DEPS[*]}${NC}"
    echo -e "${YELLOW}Please install them and run this script again.${NC}"
    exit 1
fi

# ============================================
# Create Virtual Environment
# ============================================
echo -e "${YELLOW}Setting up virtual environment...${NC}"

if [ -d ".venv" ]; then
    echo -e "  ${GREEN}✓${NC} Virtual environment already exists"
else
    if command -v poetry &> /dev/null; then
        echo -e "  ${BLUE}Creating venv with Poetry...${NC}"
        poetry env use python3 2>/dev/null || true
    else
        echo -e "  ${BLUE}Creating venv with venv...${NC}"
        python3 -m venv .venv
    fi
    echo -e "  ${GREEN}✓${NC} Virtual environment created"
fi

echo ""

# ============================================
# Install Dependencies
# ============================================
echo -e "${YELLOW}Installing Python dependencies...${NC}"

if command -v poetry &> /dev/null; then
    echo -e "  ${BLUE}Using Poetry...${NC}"
    poetry install --with dev
else
    echo -e "  ${BLUE}Using pip...${NC}"
    if [ -f ".venv/bin/pip" ]; then
        .venv/bin/pip install --upgrade pip
        .venv/bin/pip install -e ".[dev]" 2>/dev/null || .venv/bin/pip install -e .
    else
        pip3 install --user -e ".[dev]" 2>/dev/null || pip3 install --user -e .
    fi
fi

echo -e "  ${GREEN}✓${NC} Dependencies installed"
echo ""

# ============================================
# Setup Environment Configuration
# ============================================
echo -e "${YELLOW}Setting up environment configuration...${NC}"

if [ -f ".env" ]; then
    echo -e "  ${GREEN}✓${NC} .env file already exists"
else
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "  ${GREEN}✓${NC} Created .env from .env.example"
        echo -e "  ${YELLOW}  Please edit .env with your configuration${NC}"
    else
        echo -e "  ${YELLOW}!${NC} .env.example not found, skipping"
    fi
fi

echo ""

# ============================================
# Create Directory Structure
# ============================================
echo -e "${YELLOW}Creating directory structure...${NC}"

DIRECTORIES=(
    "logs"
    "data"
    "reports"
    "models"
    "cache"
)

for dir in "${DIRECTORIES[@]}"; do
    if [ -d "$dir" ]; then
        echo -e "  ${GREEN}✓${NC} $dir/ already exists"
    else
        mkdir -p "$dir"
        echo -e "  ${GREEN}✓${NC} Created $dir/"
    fi
done

# Create .gitkeep files
for dir in "${DIRECTORIES[@]}"; do
    touch "$dir/.gitkeep"
done

echo ""

# ============================================
# Setup Pre-commit Hooks
# ============================================
echo -e "${YELLOW}Setting up pre-commit hooks...${NC}"

if [ -f ".pre-commit-config.yaml" ]; then
    if command -v pre-commit &> /dev/null || [ -f ".venv/bin/pre-commit" ]; then
        PRE_COMMIT_CMD="pre-commit"
        [ -f ".venv/bin/pre-commit" ] && PRE_COMMIT_CMD=".venv/bin/pre-commit"

        $PRE_COMMIT_CMD install
        echo -e "  ${GREEN}✓${NC} Pre-commit hooks installed"
    else
        echo -e "  ${YELLOW}!${NC} pre-commit not found, skipping hook installation"
    fi
else
    echo -e "  ${YELLOW}!${NC} .pre-commit-config.yaml not found, skipping"
fi

echo ""

# ============================================
# Summary
# ============================================
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo -e "  1. ${BLUE}Edit .env with your configuration${NC}"
echo -e "     ${YELLOW}vim .env${NC}"
echo ""
echo -e "  2. ${BLUE}Start services with Docker:${NC}"
echo -e "     ${YELLOW}make up${NC}"
echo ""
echo -e "     ${BLUE}Or run locally without Docker:${NC}"
echo -e "     ${YELLOW}make dev${NC}"
echo ""
echo -e "  3. ${BLUE}Run tests:${NC}"
echo -e "     ${YELLOW}make test${NC}"
echo ""
echo -e "  4. ${BLUE}View available commands:${NC}"
echo -e "     ${YELLOW}make help${NC}"
echo ""
echo -e "${YELLOW}Useful Commands:${NC}"
echo -e "  ${BLUE}make up${NC}       - Start all services"
echo -e "  ${BLUE}make down${NC}     - Stop all services"
echo -e "  ${BLUE}make logs${NC}     - View logs"
echo -e "  ${BLUE}make test${NC}     - Run tests"
echo -e "  ${BLUE}make lint${NC}     - Run code linting"
echo -e "  ${BLUE}make format${NC}   - Format code"
echo ""