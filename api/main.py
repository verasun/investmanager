"""Main FastAPI application."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.routes import analysis, backtest, market, report, tasks
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan handler."""
    logger.info("Starting InvestManager API...")

    # Initialize resources
    # TODO: Initialize database connections, cache, etc.

    yield

    # Cleanup
    logger.info("Shutting down InvestManager API...")


app = FastAPI(
    title="InvestManager API",
    description="Financial quantitative analysis system API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if hasattr(settings, "CORS_ORIGINS") else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(market.router, prefix="/api/v1/market", tags=["Market Data"])
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["Analysis"])
app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["Backtest"])
app.include_router(report.router, prefix="/api/v1/report", tags=["Reports"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "name": "InvestManager API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "investmanager-api",
    }