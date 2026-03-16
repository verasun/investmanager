"""API response schemas."""

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field


class StockListResponse(BaseModel):
    """Response for stock list."""

    market: str
    count: int
    stocks: list[dict]


class StockInfoResponse(BaseModel):
    """Response for stock info."""

    symbol: str
    info: dict


class MarketDataResponse(BaseModel):
    """Response for market data."""

    symbol: str
    start_date: date
    end_date: date
    interval: str
    data: list[dict]


class AnalysisResponse(BaseModel):
    """Response for analysis."""

    symbol: str
    analysis_type: str
    data: dict
    signals: Optional[list[dict]] = None


class BacktestResultResponse(BaseModel):
    """Response for backtest result."""

    strategy_name: str
    symbol: str
    start_date: str
    end_date: str
    initial_value: float
    final_value: float
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    version: Optional[str] = None