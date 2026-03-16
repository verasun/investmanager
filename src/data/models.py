"""Data models for market data and related entities."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Market(str, Enum):
    """Market types."""

    A_SHARE = "A股"
    US = "US"
    HK = "HK"


class Exchange(str, Enum):
    """Exchange codes."""

    SH = "SH"  # Shanghai
    SZ = "SZ"  # Shenzhen
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"
    HKEX = "HKEX"


class SignalType(str, Enum):
    """Trading signal types."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class SentimentLabel(str, Enum):
    """Sentiment labels."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class Stock(BaseModel):
    """Stock metadata model."""

    symbol: str
    name: Optional[str] = None
    exchange: Exchange
    market: Market
    sector: Optional[str] = None
    industry: Optional[str] = None
    listing_date: Optional[date] = None
    is_active: bool = True

    class Config:
        use_enum_values = True


class OHLCV(BaseModel):
    """OHLCV (Open-High-Low-Close-Volume) data model."""

    time: datetime
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    amount: Optional[Decimal] = None
    turnover_rate: Optional[Decimal] = None
    pct_change: Optional[Decimal] = None

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None,
        }


class TechnicalIndicator(BaseModel):
    """Technical indicator data model."""

    time: datetime
    symbol: str
    indicator_type: str
    value: Decimal
    parameters: dict[str, Any] = Field(default_factory=dict)


class News(BaseModel):
    """News data model."""

    id: Optional[int] = None
    symbol: Optional[str] = None
    title: str
    content: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    publish_time: Optional[datetime] = None
    sentiment_score: Optional[Decimal] = None
    sentiment_label: Optional[SentimentLabel] = None

    class Config:
        use_enum_values = True


class TradingSignal(BaseModel):
    """Trading signal model."""

    id: Optional[int] = None
    symbol: str
    signal_type: str
    signal_value: SignalType
    confidence: Optional[Decimal] = None
    price_at_signal: Optional[Decimal] = None
    generated_at: datetime = Field(default_factory=datetime.now)
    strategy_name: Optional[str] = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None

    class Config:
        use_enum_values = True


class Trade(BaseModel):
    """Trade record model."""

    id: Optional[int] = None
    backtest_run_id: Optional[int] = None
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: int
    price: Decimal
    commission: Optional[Decimal] = None
    executed_at: datetime
    notes: Optional[str] = None


class BacktestResult(BaseModel):
    """Backtest result model."""

    id: Optional[int] = None
    strategy_name: str
    symbol: Optional[str] = None
    start_date: date
    end_date: date
    initial_capital: Decimal
    final_capital: Decimal
    total_return: Decimal
    annual_return: Decimal
    sharpe_ratio: Decimal
    max_drawdown: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    total_trades: int
    parameters: dict[str, Any] = Field(default_factory=dict)
    trades: list[Trade] = Field(default_factory=list)


class DailyReport(BaseModel):
    """Daily report model."""

    id: Optional[int] = None
    report_date: date
    report_type: str = "daily"
    title: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    market_overview: Optional[dict[str, Any]] = None
    top_gainers: Optional[list[dict[str, Any]]] = None
    top_losers: Optional[list[dict[str, Any]]] = None
    sector_performance: Optional[list[dict[str, Any]]] = None
    ai_analysis: Optional[str] = None