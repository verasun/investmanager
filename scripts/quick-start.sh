#!/bin/bash
# ============================================
# InvestManager - Quick Start Script
# ============================================
set -e

cd /root/devworks/investmanager

# Activate venv
source .venv/bin/activate

# Export environment
export SQLITE_DB_PATH=/root/autowork/data/investmanager.db
export REPORT_OUTPUT_DIR=/root/autowork/reports
export CLAUDE_CODE_WORKING_DIR=/root/autowork

# Create directories
mkdir -p /root/autowork/{data,logs,reports}
chmod -R 777 /root/autowork

# Load .env manually
export $(grep -v '^#' .env | grep -E '^[A-Z]' | head -50 | xargs)

echo "=== Starting Services ==="
echo "Working Dir: /root/autowork"
echo "SQLite: $SQLITE_DB_PATH"
echo "LLM Provider: $LLM_PROVIDER"
echo "Model: $ALIBABA_BAILIAN_MODEL"
echo ""

# Start services in background
echo "Starting LLM Service..."
python -m services.llm.main --port 8001 &
LLM_PID=$!

echo "Starting Invest Service..."
python -m services.invest.main --port 8010 &
INVEST_PID=$!

echo "Starting Chat Service..."
python -m services.chat.main --port 8011 &
CHAT_PID=$!

echo "Starting Dev Service..."
python -m services.dev.main --port 8012 &
DEV_PID=$!

# Wait for services
sleep 5

echo "Starting Gateway Service..."
python -m services.gateway.main --port 8000 &
GATEWAY_PID=$!

# Wait and check
sleep 5

echo ""
echo "=== Service Status ==="
curl -s http://localhost:8000/services | python -m json.tool 2>/dev/null || echo "Gateway not responding"

echo ""
echo "=== PIDs ==="
echo "LLM: $LLM_PID"
echo "Invest: $INVEST_PID"
echo "Chat: $CHAT_PID"
echo "Dev: $DEV_PID"
echo "Gateway: $GATEWAY_PID"

echo ""
echo "Press Ctrl+C to stop..."
wait