"""API request schemas."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class MarketDataRequest(BaseModel):
    """Request for market data."""

    symbol: str = Field(..., description="Stock symbol")
    start_date: date = Field(..., description="Start date")
    end_date: date = Field(..., description="End date")
    interval: str = Field("1d", description="Data interval")


class AnalysisRequest(BaseModel):
    """Request for analysis."""

    symbol: str = Field(..., description="Stock symbol")
    start_date: date = Field(..., description="Start date")
    end_date: date = Field(..., description="End date")
    analysis_type: str = Field("technical", description="Type of analysis")
    parameters: Optional[dict] = Field(None, description="Analysis parameters")


class BacktestRequest(BaseModel):
    """Request for backtest."""

    symbol: str = Field(..., description="Stock symbol")
    start_date: date = Field(..., description="Start date")
    end_date: date = Field(..., description="End date")
    strategy: str = Field("momentum", description="Strategy name")
    initial_cash: float = Field(100000.0, description="Initial capital")
    commission_rate: float = Field(0.001, description="Commission rate")


class ReportRequest(BaseModel):
    """Request for report generation."""

    report_type: str = Field(..., description="Type of report")
    symbols: list[str] = Field(..., description="Symbols to include")
    start_date: Optional[date] = Field(None, description="Start date")
    end_date: Optional[date] = Field(None, description="End date")
    format: str = Field("html", description="Output format")