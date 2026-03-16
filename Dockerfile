# ============================================
# InvestManager - Multi-stage Docker Build
# ============================================

# Stage 1: Builder
FROM python:3.11-bookworm as builder

WORKDIR /build

# Install build dependencies (bookworm has better package availability)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Export dependencies to requirements.txt for faster install
# If poetry.lock doesn't exist, poetry will generate it
RUN poetry lock --no-interaction || true
RUN poetry export --without-hashes --only main -f requirements.txt -o requirements.txt || true

# Stage 2: Production
FROM python:3.11-bookworm as production

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Copy requirements from builder and install
COPY --from=builder /build/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && rm requirements.txt

# Copy application code
COPY --chown=appuser:appuser . .

# Create necessary directories
RUN mkdir -p logs reports data && chown -R appuser:appuser logs reports data

# Switch to non-root user
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production

# Expose ports
EXPOSE 8000 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command (can be overridden)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]