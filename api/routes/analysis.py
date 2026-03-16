"""Analysis API routes."""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from api.schemas.requests import AnalysisRequest

router = APIRouter()


class TechnicalAnalysisRequest(BaseModel):
    """Technical analysis request."""

    symbol: str
    start_date: date
    end_date: date
    indicators: list[str] = ["sma", "ema", "rsi", "macd"]


class AnalysisResult(BaseModel):
    """Analysis result model."""

    symbol: str
    analysis_type: str
    data: dict
    signals: Optional[list[dict]] = None


@router.post("/technical", response_model=AnalysisResult)
async def analyze_technical(request: TechnicalAnalysisRequest) -> AnalysisResult:
    """
    Perform technical analysis on market data.
    """
    try:
        from src.data.sources.yfinance_source import YFinanceSource
        from src.analysis.technical.indicators import TechnicalIndicators

        # Fetch data
        source = YFinanceSource()
        data = await source.fetch_ohlcv(
            symbol=request.symbol.upper(),
            start=datetime.combine(request.start_date, datetime.min.time()),
            end=datetime.combine(request.end_date, datetime.max.time()),
        )

        if data.empty:
            raise HTTPException(status_code=404, detail="No data found")

        # Calculate indicators
        indicators = TechnicalIndicators()
        result_data = {}

        for indicator in request.indicators:
            indicator = indicator.lower()

            if indicator == "sma":
                for period in [5, 10, 20, 50]:
                    result_data[f"sma_{period}"] = indicators.sma(data["close"], period).to_dict()
            elif indicator == "ema":
                for period in [5, 10, 20, 50]:
                    result_data[f"ema_{period}"] = indicators.ema(data["close"], period).to_dict()
            elif indicator == "rsi":
                result_data["rsi_14"] = indicators.rsi(data["close"], 14).to_dict()
            elif indicator == "macd":
                macd = indicators.macd(data["close"])
                result_data["macd"] = macd["macd"].to_dict()
                result_data["macd_signal"] = macd["signal"].to_dict()
                result_data["macd_histogram"] = macd["histogram"].to_dict()
            elif indicator == "bollinger":
                bb = indicators.bollinger_bands(data["close"])
                result_data["bb_upper"] = bb["upper"].to_dict()
                result_data["bb_middle"] = bb["middle"].to_dict()
                result_data["bb_lower"] = bb["lower"].to_dict()

        return AnalysisResult(
            symbol=request.symbol.upper(),
            analysis_type="technical",
            data=result_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in technical analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals")
async def generate_signals(
    symbol: str = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    strategy: str = Query("momentum", description="Strategy type"),
) -> dict:
    """
    Generate trading signals for a symbol.
    """
    try:
        from src.data.sources.yfinance_source import YFinanceSource
        from src.strategies.momentum import MomentumStrategy, MACDMomentumStrategy
        from src.strategies.mean_reversion import MeanReversionStrategy

        # Fetch data
        source = YFinanceSource()
        data = await source.fetch_ohlcv(
            symbol=symbol.upper(),
            start=datetime.combine(start_date, datetime.min.time()),
            end=datetime.combine(end_date, datetime.max.time()),
        )

        if data.empty:
            raise HTTPException(status_code=404, detail="No data found")

        # Select strategy
        if strategy == "momentum":
            strat = MomentumStrategy()
        elif strategy == "macd":
            strat = MACDMomentumStrategy()
        elif strategy == "mean_reversion":
            strat = MeanReversionStrategy()
        else:
            strat = MomentumStrategy()

        # Generate signals
        signals = strat.generate_signals(data)

        # Convert signals to readable format
        signal_list = []
        for idx, signal in signals.items():
            if signal.value != 0:  # Not HOLD
                signal_list.append({
                    "date": idx.isoformat(),
                    "signal": signal.name,
                    "price": float(data.loc[idx, "close"]),
                })

        return {
            "symbol": symbol.upper(),
            "strategy": strategy,
            "signals": signal_list,
            "total_signals": len(signal_list),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pattern/{symbol}")
async def detect_patterns(
    symbol: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
) -> dict:
    """
    Detect chart patterns for a symbol.
    """
    try:
        from src.data.sources.yfinance_source import YFinanceSource
        from src.analysis.technical.patterns import PatternDetector

        # Fetch data
        source = YFinanceSource()
        data = await source.fetch_ohlcv(
            symbol=symbol.upper(),
            start=datetime.combine(start_date, datetime.min.time()),
            end=datetime.combine(end_date, datetime.max.time()),
        )

        if data.empty:
            raise HTTPException(status_code=404, detail="No data found")

        # Detect patterns
        detector = PatternDetector()
        patterns = detector.detect_all(data)

        return {
            "symbol": symbol.upper(),
            "patterns": patterns,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error detecting patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))