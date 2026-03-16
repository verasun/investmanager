#!/bin/bash
# ============================================
# InvestManager - Health Check Script
# ============================================
# Usage: ./scripts/healthcheck.sh [service]
# ============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Service URLs
API_URL="http://localhost:8000"
DB_HOST="localhost"
DB_PORT="5432"
REDIS_HOST="localhost"
REDIS_PORT="6379"

check_api() {
    echo -n "API (${API_URL})... "
    if curl -sf "${API_URL}/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ healthy${NC}"
        return 0
    else
        echo -e "${RED}✗ unhealthy${NC}"
        return 1
    fi
}

check_database() {
    echo -n "Database (${DB_HOST}:${DB_PORT})... "
    if command -v pg_isready &> /dev/null; then
        if pg_isready -h "$DB_HOST" -p "$DB_PORT" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ healthy${NC}"
            return 0
        fi
    elif command -v nc &> /dev/null; then
        if nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; then
            echo -e "${GREEN}✓ healthy${NC}"
            return 0
        fi
    fi
    echo -e "${RED}✗ unhealthy${NC}"
    return 1
}

check_redis() {
    echo -n "Redis (${REDIS_HOST}:${REDIS_PORT})... "
    if command -v redis-cli &> /dev/null; then
        if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping 2>/dev/null | grep -q PONG; then
            echo -e "${GREEN}✓ healthy${NC}"
            return 0
        fi
    elif command -v nc &> /dev/null; then
        if nc -z "$REDIS_HOST" "$REDIS_PORT" 2>/dev/null; then
            echo -e "${GREEN}✓ healthy${NC}"
            return 0
        fi
    fi
    echo -e "${RED}✗ unhealthy${NC}"
    return 1
}

check_all() {
    echo -e "${YELLOW}Checking all services...${NC}"
    echo ""

    FAILED=0

    check_api || FAILED=$((FAILED + 1))
    check_database || FAILED=$((FAILED + 1))
    check_redis || FAILED=$((FAILED + 1))

    echo ""

    if [ $FAILED -eq 0 ]; then
        echo -e "${GREEN}All services are healthy!${NC}"
        exit 0
    else
        echo -e "${RED}${FAILED} service(s) are unhealthy${NC}"
        exit 1
    fi
}

# Main
SERVICE=${1:-all}

case $SERVICE in
    api) check_api ;;
    db|database) check_database ;;
    redis) check_redis ;;
    all) check_all ;;
    *)
        echo "Usage: $0 [api|db|redis|all]"
        exit 1
        ;;
esac