#!/bin/bash
# ============================================
# InvestManager - Run Script
# ============================================
# Usage: ./scripts/run.sh [command]
#
# Commands:
#   start       Start all services (default)
#   stop        Stop all services
#   restart     Restart all services
#   status      Show service status
#   logs        Show logs (optional: -f for follow)
#   shell       Open shell in container
#   ps          List running containers
#   clean       Remove containers and volumes
#   web         Start with web UI
#   help        Show this help
# ============================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.yml"
PROJECT_NAME="investmanager"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Warning: .env file not found, creating from .env.example${NC}"
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}Please edit .env with your configuration${NC}"
    fi
fi

# Function to show help
show_help() {
    head -20 "$0" | tail -17
    exit 0
}

# Function to check Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed${NC}"
        exit 1
    fi

    if ! docker info &> /dev/null; then
        echo -e "${RED}Error: Docker daemon is not running${NC}"
        exit 1
    fi
}

# Function to check if compose is available
get_compose_cmd() {
    if docker compose version &> /dev/null; then
        echo "docker compose"
    elif command -v docker-compose &> /dev/null; then
        echo "docker-compose"
    else
        echo -e "${RED}Error: Docker Compose is not installed${NC}"
        exit 1
    fi
}

COMPOSE_CMD=$(get_compose_cmd)

# Parse command
COMMAND=${1:-start}
shift || true

case $COMMAND in
    start)
        echo -e "${BLUE}============================================${NC}"
        echo -e "${BLUE}  Starting InvestManager Services${NC}"
        echo -e "${BLUE}============================================${NC}"
        echo ""

        check_docker

        # Build if image doesn't exist
        if ! docker images investmanager:latest -q | grep -q .; then
            echo -e "${YELLOW}Image not found, building...${NC}"
            ./scripts/build.sh
        fi

        echo -e "${YELLOW}Starting services...${NC}"
        $COMPOSE_CMD -p $PROJECT_NAME up -d

        echo ""
        echo -e "${GREEN}✓ Services started!${NC}"
        echo ""
        echo -e "${YELLOW}Endpoints:${NC}"
        echo -e "  API:  ${GREEN}http://localhost:8000${NC}"
        echo -e "  Docs: ${GREEN}http://localhost:8000/docs${NC}"
        echo -e "  DB:   ${GREEN}localhost:5432${NC}"
        echo -e "  Redis:${GREEN}localhost:6379${NC}"
        echo ""
        echo -e "To start web UI: ${BLUE}./scripts/run.sh web${NC}"
        echo -e "View logs:       ${BLUE}./scripts/run.sh logs -f${NC}"
        ;;

    web)
        echo -e "${BLUE}============================================${NC}"
        echo -e "${BLUE}  Starting InvestManager with Web UI${NC}"
        echo -e "${BLUE}============================================${NC}"
        echo ""

        check_docker

        $COMPOSE_CMD -p $PROJECT_NAME --profile web up -d

        echo ""
        echo -e "${GREEN}✓ Services started with Web UI!${NC}"
        echo ""
        echo -e "${YELLOW}Endpoints:${NC}"
        echo -e "  API:  ${GREEN}http://localhost:8000${NC}"
        echo -e "  Web:  ${GREEN}http://localhost:8501${NC}"
        echo -e "  Docs: ${GREEN}http://localhost:8000/docs${NC}"
        ;;

    stop)
        echo -e "${YELLOW}Stopping services...${NC}"
        $COMPOSE_CMD -p $PROJECT_NAME down
        echo -e "${GREEN}✓ Services stopped${NC}"
        ;;

    restart)
        echo -e "${YELLOW}Restarting services...${NC}"
        $COMPOSE_CMD -p $PROJECT_NAME restart
        echo -e "${GREEN}✓ Services restarted${NC}"
        ;;

    status)
        echo -e "${BLUE}============================================${NC}"
        echo -e "${BLUE}  Service Status${NC}"
        echo -e "${BLUE}============================================${NC}"
        echo ""
        $COMPOSE_CMD -p $PROJECT_NAME ps
        echo ""

        # Show health status
        echo -e "${YELLOW}Health Status:${NC}"
        for container in $($COMPOSE_CMD -p $PROJECT_NAME ps -q); do
            name=$(docker inspect --format='{{.Name}}' $container | sed 's/^//')
            health=$(docker inspect --format='{{.State.Health.Status}}' $container 2>/dev/null || echo "N/A")
            case $health in
                healthy) echo -e "  ${name}: ${GREEN}$health${NC}" ;;
                unhealthy) echo -e "  ${name}: ${RED}$health${NC}" ;;
                *) echo -e "  ${name}: ${YELLOW}$health${NC}" ;;
            esac
        done
        ;;

    logs)
        FOLLOW=${1:-""}
        if [ "$FOLLOW" = "-f" ] || [ "$FOLLOW" = "--follow" ]; then
            $COMPOSE_CMD -p $PROJECT_NAME logs -f
        else
            $COMPOSE_CMD -p $PROJECT_NAME logs --tail=100
        fi
        ;;

    shell)
        SERVICE=${1:-api}
        echo -e "${YELLOW}Opening shell in $SERVICE container...${NC}"
        $COMPOSE_CMD -p $PROJECT_NAME exec $SERVICE /bin/bash
        ;;

    ps)
        $COMPOSE_CMD -p $PROJECT_NAME ps
        ;;

    clean)
        echo -e "${RED}Warning: This will remove all containers, volumes, and data!${NC}"
        echo -e "${YELLOW}Press Ctrl+C to cancel, Enter to continue...${NC}"
        read -r

        echo -e "${YELLOW}Removing containers and volumes...${NC}"
        $COMPOSE_CMD -p $PROJECT_NAME down -v --remove-orphans

        echo -e "${YELLOW}Cleaning up unused resources...${NC}"
        docker system prune -f

        echo -e "${GREEN}✓ Cleanup complete${NC}"
        ;;

    build)
        ./scripts/build.sh "$@"
        ;;

    test)
        echo -e "${YELLOW}Running tests in container...${NC}"
        $COMPOSE_CMD -p $PROJECT_NAME exec api pytest tests/ -v
        ;;

    help|--help|-h)
        show_help
        ;;

    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        echo ""
        show_help
        ;;
esac