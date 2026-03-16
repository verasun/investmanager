#!/bin/bash
# ============================================
# InvestManager - Local Development Script
# ============================================
# Usage: ./scripts/dev.sh [command]
#
# Commands:
#   api       Start API server (default)
#   web       Start Web UI
#   worker    Start background worker
#   all       Start all services locally
#   help      Show this help
# ============================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-8501}"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Function to show help
show_help() {
    head -14 "$0" | tail -11
    exit 0
}

# Function to check Python environment
check_python_env() {
    if [ -f ".venv/bin/python" ]; then
        PYTHON_CMD=".venv/bin/python"
    elif command -v poetry &> /dev/null; then
        PYTHON_CMD="poetry run python"
    else
        PYTHON_CMD="python3"
    fi
    echo "$PYTHON_CMD"
}

# Function to check dependencies
check_deps() {
    echo -e "${YELLOW}Checking dependencies...${NC}"

    PYTHON_CMD=$(check_python_env)

    if ! $PYTHON_CMD -c "import fastapi" 2>/dev/null; then
        echo -e "${RED}Error: FastAPI not installed. Run 'make install' first.${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ Dependencies OK${NC}"
    echo ""
}

# Function to load environment
load_env() {
    if [ -f ".env" ]; then
        echo -e "${YELLOW}Loading environment from .env...${NC}"
        set -a
        source .env 2>/dev/null || true
        set +a
    fi
}

# Function to wait for database
wait_for_db() {
    if [ -n "$DATABASE_URL" ]; then
        echo -e "${YELLOW}Waiting for database...${NC}"

        MAX_RETRIES=30
        RETRY_COUNT=0

        while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
            if $PYTHON_CMD -c "
import asyncio
import asyncpg

async def check():
    try:
        conn = await asyncpg.connect('${DATABASE_URL}')
        await conn.close()
        return True
    except:
        return False

asyncio.run(check())
" 2>/dev/null; then
                echo -e "${GREEN}✓ Database connected${NC}"
                return 0
            fi

            RETRY_COUNT=$((RETRY_COUNT + 1))
            echo -e "${YELLOW}Waiting for database... ($RETRY_COUNT/$MAX_RETRIES)${NC}"
            sleep 2
        done

        echo -e "${RED}Warning: Could not connect to database${NC}"
        return 1
    fi
}

# Parse command
COMMAND=${1:-api}

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  InvestManager - Local Development${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

check_deps
load_env

PYTHON_CMD=$(check_python_env)

case $COMMAND in
    api)
        echo -e "${YELLOW}Starting API server...${NC}"
        echo ""
        echo -e "  ${GREEN}API:${NC}    http://localhost:${API_PORT}"
        echo -e "  ${GREEN}Docs:${NC}   http://localhost:${API_PORT}/docs"
        echo -e "  ${GREEN}Health:${NC} http://localhost:${API_PORT}/health"
        echo ""
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        echo ""

        wait_for_db || true

        if [ -f ".venv/bin/uvicorn" ]; then
            .venv/bin/uvicorn api.main:app --host $API_HOST --port $API_PORT --reload
        elif command -v poetry &> /dev/null; then
            poetry run uvicorn api.main:app --host $API_HOST --port $API_PORT --reload
        else
            uvicorn api.main:app --host $API_HOST --port $API_PORT --reload
        fi
        ;;

    web)
        echo -e "${YELLOW}Starting Web UI...${NC}"
        echo ""
        echo -e "  ${GREEN}Web:${NC} http://localhost:${WEB_PORT}"
        echo ""
        echo -e "${YELLOW}Note: Make sure API server is running (${BLUE}./scripts/dev.sh api${NC})${YELLOW}${NC}"
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        echo ""

        export API_URL="${API_URL:-http://localhost:${API_PORT}}"

        if [ -f ".venv/bin/streamlit" ]; then
            .venv/bin/streamlit run web/app.py --server.port $WEB_PORT --server.address 0.0.0.0
        elif command -v poetry &> /dev/null; then
            poetry run streamlit run web/app.py --server.port $WEB_PORT --server.address 0.0.0.0
        else
            streamlit run web/app.py --server.port $WEB_PORT --server.address 0.0.0.0
        fi
        ;;

    worker)
        echo -e "${YELLOW}Starting background worker...${NC}"
        echo ""

        wait_for_db

        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        echo ""

        $PYTHON_CMD -m src.orchestrator.main --db-path ./data/tasks.db --poll-interval 5
        ;;

    all)
        echo -e "${YELLOW}Starting all services...${NC}"
        echo ""
        echo -e "  ${GREEN}API:${NC}    http://localhost:${API_PORT}"
        echo -e "  ${GREEN}Web:${NC}    http://localhost:${WEB_PORT}"
        echo -e "  ${GREEN}Docs:${NC}   http://localhost:${API_PORT}/docs"
        echo ""

        wait_for_db || true

        echo -e "${YELLOW}Starting services in background...${NC}"

        # Start API in background
        if [ -f ".venv/bin/uvicorn" ]; then
            .venv/bin/uvicorn api.main:app --host $API_HOST --port $API_PORT &
            API_PID=$!
        else
            uvicorn api.main:app --host $API_HOST --port $API_PORT &
            API_PID=$!
        fi

        sleep 2

        # Start Web UI
        export API_URL="${API_URL:-http://localhost:${API_PORT}}"

        if [ -f ".venv/bin/streamlit" ]; then
            .venv/bin/streamlit run web/app.py --server.port $WEB_PORT --server.address 0.0.0.0 &
            WEB_PID=$!
        else
            streamlit run web/app.py --server.port $WEB_PORT --server.address 0.0.0.0 &
            WEB_PID=$!
        fi

        echo ""
        echo -e "${GREEN}All services started!${NC}"
        echo -e "${YELLOW}API PID: $API_PID${NC}"
        echo -e "${YELLOW}Web PID: $WEB_PID${NC}"
        echo ""
        echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
        echo ""

        # Trap to kill background processes on exit
        trap "echo ''; echo '${YELLOW}Stopping services...${NC}'; kill $API_PID $WEB_PID 2>/dev/null; echo '${GREEN}Services stopped${NC}'; exit 0" SIGINT SIGTERM

        # Wait for background processes
        wait
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