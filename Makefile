# ============================================
# InvestManager - Makefile
# ============================================
# Usage: make [target]
# Help:  make help
# ============================================

.PHONY: help install setup dev build up down logs shell test lint format check db-init db-reset db-migrate clean docker-clean package package-export run-image dev-multiprocess up-multiprocess down-multiprocess

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m

# ============================================
# Help
# ============================================
help: ## Show this help message
	@echo ""
	@echo "$(BLUE)============================================$(NC)"
	@echo "$(BLUE)  InvestManager - Development Commands$(NC)"
	@echo "$(BLUE)============================================$(NC)"
	@echo ""
	@echo "$(YELLOW)Installation & Setup:$(NC)"
	@grep -E '^install:|^setup:' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Docker Operations:$(NC)"
	@grep -E '^build:|^up:|^down:|^logs:|^shell:|^web:|^prod:|^up-multiprocess:|^down-multiprocess:' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Development:$(NC)"
	@grep -E '^dev:|^dev-multiprocess:|^test:|^test-local:|^lint:|^format:|^check:' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Database:$(NC)"
	@grep -E '^db-' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Cleanup:$(NC)"
	@grep -E '^clean:|^docker-clean:' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Package & Deploy:$(NC)"
	@grep -E '^package:|^package-export:|^run-image:' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""

# ============================================
# Installation & Setup
# ============================================
install: ## Install Python dependencies with Poetry
	@echo "$(BLUE)Installing dependencies...$(NC)"
	@if command -v poetry >/dev/null 2>&1; then \
		poetry install; \
	else \
		echo "$(YELLOW)Poetry not found, using pip...$(NC)"; \
		pip install -e .; \
	fi
	@echo "$(GREEN)Dependencies installed!$(NC)"

setup: ## Initialize complete development environment
	@./scripts/setup.sh

# ============================================
# Development (Local)
# ============================================
dev: ## Start local development server (no Docker)
	@./scripts/dev.sh api

dev-web: ## Start local Web UI server
	@./scripts/dev.sh web

dev-all: ## Start all local services (API + Web + Worker)
	@./scripts/dev.sh all

dev-multiprocess: ## Start multi-process services (5 services locally)
	@./scripts/start-multiprocess.sh

# ============================================
# Docker Operations
# ============================================
build: ## Build Docker image
	@./scripts/build.sh

build-no-cache: ## Build Docker image without cache
	@./scripts/build.sh --no-cache

up: ## Start all services with Docker
	@./scripts/run.sh start

down: ## Stop all services
	@./scripts/run.sh stop

restart: ## Restart all services
	@./scripts/run.sh restart

status: ## Show service status
	@./scripts/run.sh status

logs: ## View service logs (use: make logs-f for follow)
	@./scripts/run.sh logs

logs-f: ## Follow service logs
	@./scripts/run.sh logs -f

shell: ## Open shell in container (default: api)
	@./scripts/run.sh shell api

web: ## Start with Web UI
	@./scripts/run.sh web

prod: ## Start production environment
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

prod-down: ## Stop production environment
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# ============================================
# Multi-Process Deployment
# ============================================
up-multiprocess: ## Start multi-process architecture (5 services)
	@echo "$(BLUE)Starting multi-process deployment...$(NC)"
	@docker compose -f docker-compose.multiprocess.yml up -d
	@echo "$(GREEN)Multi-process services started!$(NC)"
	@echo ""
	@echo "Gateway:  http://localhost:8000"
	@echo "LLM:      http://localhost:8001"
	@echo "Invest:   http://localhost:8010"
	@echo "Chat:     http://localhost:8011"
	@echo "Dev:      http://localhost:8012"

down-multiprocess: ## Stop multi-process deployment
	@echo "$(BLUE)Stopping multi-process deployment...$(NC)"
	@docker compose -f docker-compose.multiprocess.yml down
	@echo "$(GREEN)Multi-process services stopped!$(NC)"

logs-multiprocess: ## View multi-process logs
	@docker compose -f docker-compose.multiprocess.yml logs -f

# ============================================
# Testing & Code Quality
# ============================================
test: ## Run tests in Docker container
	@docker compose exec api pytest tests/ -v

test-local: ## Run tests locally
	@echo "$(BLUE)Running tests...$(NC)"
	@if command -v poetry >/dev/null 2>&1; then \
		poetry run pytest tests/ -v --cov=src --cov=api --cov-report=term-missing; \
	elif [ -f ".venv/bin/pytest" ]; then \
		.venv/bin/pytest tests/ -v --cov=src --cov=api --cov-report=term-missing; \
	else \
		pytest tests/ -v; \
	fi

lint: ## Run code linting with ruff and mypy
	@echo "$(BLUE)Running linter...$(NC)"
	@if command -v poetry >/dev/null 2>&1; then \
		poetry run ruff check src/ api/ tests/; \
		poetry run mypy src/ api/; \
	elif [ -f ".venv/bin/ruff" ]; then \
		.venv/bin/ruff check src/ api/ tests/; \
		.venv/bin/mypy src/ api/; \
	else \
		ruff check src/ api/ tests/; \
		mypy src/ api/; \
	fi

format: ## Format code with black and ruff
	@echo "$(BLUE)Formatting code...$(NC)"
	@if command -v poetry >/dev/null 2>&1; then \
		poetry run black src/ api/ tests/; \
		poetry run ruff check --fix src/ api/ tests/; \
	elif [ -f ".venv/bin/black" ]; then \
		.venv/bin/black src/ api/ tests/; \
		.venv/bin/ruff check --fix src/ api/ tests/; \
	else \
		black src/ api/ tests/; \
		ruff check --fix src/ api/ tests/; \
	fi

check: lint test ## Run lint and tests

# ============================================
# Database Operations
# ============================================
db-init: ## Initialize database schema
	@echo "$(BLUE)Initializing database...$(NC)"
	@if command -v docker >/dev/null 2>&1 && docker ps 2>/dev/null | grep -q investmanager-db; then \
		docker exec investmanager-db psql -U investuser -d investmanager -f /docker-entrypoint-initdb.d/init.sql; \
		echo "$(GREEN)Database initialized!$(NC)"; \
	else \
		echo "$(YELLOW)Database container not running. Run 'make up' first.$(NC)"; \
	fi

db-reset: ## Reset database (WARNING: destroys all data)
	@echo "$(RED)Warning: This will destroy all database data!$(NC)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	@./scripts/run.sh clean
	@./scripts/run.sh start
	@$(MAKE) db-init

db-migrate: ## Run database migrations
	@echo "$(BLUE)Running database migrations...$(NC)"
	@if command -v docker >/dev/null 2>&1 && docker ps 2>/dev/null | grep -q investmanager-api; then \
		docker exec investmanager-api alembic upgrade head 2>/dev/null || echo "$(YELLOW)Alembic not configured yet$(NC)"; \
	else \
		echo "$(YELLOW)API container not running. Run 'make up' first.$(NC)"; \
	fi

# ============================================
# Cleanup
# ============================================
clean: ## Clean temporary files and caches
	@echo "$(BLUE)Cleaning temporary files...$(NC)"
	@rm -rf .pytest_cache/
	@rm -rf .ruff_cache/
	@rm -rf .mypy_cache/
	@rm -rf htmlcov/
	@rm -rf .coverage
	@rm -rf *.egg-info/
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@echo "$(GREEN)Cleanup complete!$(NC)"

docker-clean: ## Clean Docker resources (containers, volumes, images)
	@echo "$(RED)Warning: This will remove Docker containers, volumes, and images!$(NC)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	@./scripts/run.sh clean
	@docker rmi investmanager:latest 2>/dev/null || true
	@docker system prune -f
	@echo "$(GREEN)Docker cleanup complete!$(NC)"

# ============================================
# Registry Operations
# ============================================
push: ## Build and push to registry
	@./scripts/build.sh --tag $$(git rev-parse --short HEAD 2>/dev/null || echo "latest") --push

pull: ## Pull image from registry
	@docker pull investmanager:latest

# ============================================
# Package & Deploy
# ============================================
package: ## Build and package Docker image
	@./scripts/package.sh

package-export: ## Build, package and export image to tar.gz
	@./scripts/package.sh --export

run-image: ## Run application from Docker image
	@./scripts/run-image.sh

run-image-web: ## Run application with Web UI
	@./scripts/run-image.sh -w

run-image-detach: ## Run application in background
	@./scripts/run-image.sh -d