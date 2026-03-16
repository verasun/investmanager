#!/bin/bash
# ============================================
# InvestManager - Deployment Script
# ============================================
# Usage: ./scripts/deploy.sh [environment]
#
# Environments:
#   dev       Development environment (default)
#   prod      Production environment
#   staging   Staging environment
# ============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
ENVIRONMENT=${1:-dev}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  InvestManager Deployment${NC}"
echo -e "${BLUE}  Environment: ${ENVIRONMENT}${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|prod|staging)$ ]]; then
    echo -e "${RED}Error: Invalid environment '${ENVIRONMENT}'${NC}"
    echo -e "Valid options: dev, prod, staging"
    exit 1
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}Error: Docker daemon is not running${NC}"
    exit 1
fi

# Get compose command
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo -e "${RED}Error: Docker Compose is not installed${NC}"
    exit 1
fi

# Environment file
ENV_FILE=".env.${ENVIRONMENT}"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}Creating environment file: ${ENV_FILE}${NC}"
    cp .env.example "$ENV_FILE"
    echo -e "${YELLOW}Please configure ${ENV_FILE} before deploying${NC}"
fi

# Load environment
set -a
source "$ENV_FILE"
set +a

# Build image if needed
echo -e "${YELLOW}Checking Docker image...${NC}"
if ! docker images investmanager:latest -q | grep -q .; then
    echo -e "${YELLOW}Building image...${NC}"
    ./scripts/build.sh
fi

# Deploy based on environment
case $ENVIRONMENT in
    dev)
        echo -e "${YELLOW}Deploying to development...${NC}"
        $COMPOSE_CMD --env-file "$ENV_FILE" up -d
        ;;

    prod)
        echo -e "${YELLOW}Deploying to production...${NC}"

        # Pull latest image if registry is configured
        if [ -n "$REGISTRY" ]; then
            echo -e "${YELLOW}Pulling latest image from registry...${NC}"
            docker pull "${REGISTRY}/investmanager:latest"
            docker tag "${REGISTRY}/investmanager:latest" investmanager:latest
        fi

        # Deploy with production compose
        $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml \
            --env-file "$ENV_FILE" up -d

        # Run migrations if needed
        echo -e "${YELLOW}Running database migrations...${NC}"
        # $COMPOSE_CMD exec api alembic upgrade head
        ;;

    staging)
        echo -e "${YELLOW}Deploying to staging...${NC}"
        $COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml \
            --env-file "$ENV_FILE" up -d
        ;;
esac

# Wait for services to be healthy
echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
sleep 5

# Check health
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ API is healthy${NC}"
        break
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -e "${YELLOW}Waiting for API... ($RETRY_COUNT/$MAX_RETRIES)${NC}"
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo -e "${RED}✗ API health check failed${NC}"
    echo -e "${YELLOW}Check logs with: ./scripts/run.sh logs${NC}"
    exit 1
fi

# Show status
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

$COMPOSE_CMD ps

echo ""
echo -e "${YELLOW}Endpoints:${NC}"
echo -e "  API:     ${GREEN}http://localhost:8000${NC}"
echo -e "  Docs:    ${GREEN}http://localhost:8000/docs${NC}"
echo -e "  Health:  ${GREEN}http://localhost:8000/health${NC}"
echo ""
echo -e "Useful commands:"
echo -e "  View logs: ${BLUE}./scripts/run.sh logs -f${NC}"
echo -e "  Stop:      ${BLUE}./scripts/run.sh stop${NC}"
echo -e "  Status:    ${BLUE}./scripts/run.sh status${NC}"