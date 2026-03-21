#!/bin/bash
# ============================================
# InvestManager - Local Multi-Process Startup
# ============================================
# Run all services locally for development.
#
# Working Directory: /root/autowork
#
# Architecture:
# ┌─────────────┐     ┌──────────────────────────────────────────────────────────────┐
# │   Feishu    │────▶│                    GATEWAY (:8000)                           │
# │   Webhook   │     │  - Webhook Handler    - LLM Proxy     - Capability Router   │
# └─────────────┘     └───────────────────────────┬──────────────────────────────────┘
#                                                 │
#                     ┌───────────────────────────┼───────────────────────────┐
#                     ▼                           ▼                           ▼
#              ┌──────────────┐          ┌──────────────┐          ┌──────────────┐
#              │ LLM SERVICE  │          │  INVEST      │          │   CHAT       │
#              │   :8001      │          │  :8010       │          │   :8011      │
#              └──────────────┘          └──────────────┘          └──────────────┘
#                                                     │
#                                                     ▼
#                                             ┌──────────────┐
#                                             │    DEV       │
#                                             │   :8012      │
#                                             └──────────────┘
#
# Usage:
#   ./scripts/start-multiprocess.sh
# ============================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Working directory
WORK_DIR="${WORK_DIR:-/root/autowork}"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Change to project directory
cd "$PROJECT_DIR"

# Activate virtual environment if exists
if [ -d ".venv" ]; then
    echo -e "${GREEN}Activating virtual environment...${NC}"
    source .venv/bin/activate
fi

# Load environment variables
if [ -f .env ]; then
    echo -e "${GREEN}Loading environment from .env${NC}"
    set -a
    source .env
    set +a
fi

# Create necessary directories in working directory
echo -e "${GREEN}Setting up working directory: ${WORK_DIR}${NC}"
mkdir -p "${WORK_DIR}/data" "${WORK_DIR}/logs" "${WORK_DIR}/reports" "${WORK_DIR}/config"

# Set permissions
chmod -R 777 "${WORK_DIR}"

# Update SQLite path to working directory
export SQLITE_DB_PATH="${WORK_DIR}/data/investmanager.db"
export REPORT_OUTPUT_DIR="${WORK_DIR}/reports"
export CLAUDE_CODE_WORKING_DIR="${WORK_DIR}"

# Array to store PIDs
declare -a PIDS
declare -a SERVICES

# Function to cleanup background processes
cleanup() {
    echo -e "\n${YELLOW}Shutting down services...${NC}"
    for i in "${!PIDS[@]}"; do
        pid="${PIDS[$i]}"
        service="${SERVICES[$i]}"
        if [ ! -z "$pid" ]; then
            kill $pid 2>/dev/null || true
            echo "  ${service} stopped (PID: $pid)"
        fi
    done
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  InvestManager Multi-Process Mode   ${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "${BLUE}Working Directory: ${WORK_DIR}${NC}"
echo ""

# Function to wait for service
wait_for_service() {
    local port=$1
    local name=$2
    local max_attempts=30

    echo -e "${YELLOW}Waiting for ${name} to be ready...${NC}"
    for i in $(seq 1 $max_attempts); do
        if curl -s "http://localhost:${port}/health" > /dev/null 2>&1; then
            echo -e "${GREEN}${name} is ready!${NC}"
            return 0
        fi
        sleep 1
    done
    echo -e "${RED}${name} failed to start within ${max_attempts} seconds${NC}"
    return 1
}

# ==========================================
# Start Gateway Service (port 8000) - MUST START FIRST
# ==========================================
echo -e "${BLUE}Starting Gateway Service on port 8000...${NC}"
python -m services.gateway.main \
    --port 8000 \
    --llm-url http://localhost:8001 \
    --invest-url http://localhost:8010 \
    --chat-url http://localhost:8011 \
    --dev-url http://localhost:8012 &
PIDS+=($!)
SERVICES+=("Gateway Service")
echo "Gateway Service started (PID: ${PIDS[-1]})"
wait_for_service 8000 "Gateway Service"

# ==========================================
# Start LLM Service (port 8001)
# ==========================================
echo -e "${BLUE}Starting LLM Service on port 8001...${NC}"
python -m services.llm.main --port 8001 &
PIDS+=($!)
SERVICES+=("LLM Service")
echo "LLM Service started (PID: ${PIDS[-1]})"
wait_for_service 8001 "LLM Service"

# ==========================================
# Start Invest Service (port 8010)
# ==========================================
echo -e "${BLUE}Starting Invest Service on port 8010...${NC}"
python -m services.invest.main --port 8010 --gateway-url http://localhost:8000 &
PIDS+=($!)
SERVICES+=("Invest Service")
echo "Invest Service started (PID: ${PIDS[-1]})"
wait_for_service 8010 "Invest Service"

# ==========================================
# Start Chat Service (port 8011)
# ==========================================
echo -e "${BLUE}Starting Chat Service on port 8011...${NC}"
python -m services.chat.main --port 8011 --gateway-url http://localhost:8000 &
PIDS+=($!)
SERVICES+=("Chat Service")
echo "Chat Service started (PID: ${PIDS[-1]})"
wait_for_service 8011 "Chat Service"

# ==========================================
# Start Dev Service (port 8012)
# ==========================================
echo -e "${BLUE}Starting Dev Service on port 8012...${NC}"
python -m services.dev.main --port 8012 &
PIDS+=($!)
SERVICES+=("Dev Service")
echo "Dev Service started (PID: ${PIDS[-1]})"
wait_for_service 8012 "Dev Service"

echo ""
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  All Services Started!              ${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo "Service URLs:"
echo "  Gateway:  http://localhost:8000"
echo "  LLM:      http://localhost:8001"
echo "  Invest:   http://localhost:8010"
echo "  Chat:     http://localhost:8011"
echo "  Dev:      http://localhost:8012"
echo ""
echo "Working Directory: ${WORK_DIR}"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for any process to exit
wait -n

# Cleanup
cleanup