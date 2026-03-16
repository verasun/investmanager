"""Market data API routes."""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from api.schemas.requests import MarketDataRequest
from api.schemas.responses import (
    MarketDataResponse,
    StockInfoResponse,
    StockListResponse,
)

router = APIRouter()


@router.get("/stocks", response_model=StockListResponse)
async def get_stock_list(
    market: str = Query("US", description="Market type: US, CN, HK"),
    limit: int = Query(100, ge=1, le=1000),
) -> StockListResponse:
    """
    Get list of stocks for a market.

    Returns stock symbols and basic information.
    """
    try:
        from src.data.sources.akshare_source import AkshareSource
        from src.data.sources.yfinance_source import YFinanceSource
        from src.data.models import Market

        if market.upper() == "CN":
            source = AkshareSource()
            market_enum = Market.CN
        else:
            source = YFinanceSource()
            market_enum = Market.US

        stocks = await source.get_stock_list(market_enum)

        # Limit results
        stocks = stocks.head(limit)

        return StockListResponse(
            market=market,
            count=len(stocks),
            stocks=stocks.to_dict("records") if not stocks.empty else [],
        )

    except Exception as e:
        logger.error(f"Error getting stock list: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stocks/{symbol}", response_model=StockInfoResponse)
async def get_stock_info(symbol: str) -> StockInfoResponse:
    """
    Get detailed information for a stock.
    """
    try:
        from src.data.sources.yfinance_source import YFinanceSource

        source = YFinanceSource()
        info = await source.get_stock_info(symbol.upper())

        return StockInfoResponse(
            symbol=symbol.upper(),
            info=info,
        )

    except Exception as e:
        logger.error(f"Error getting stock info for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/{symbol}", response_model=MarketDataResponse)
async def get_market_data(
    symbol: str,
    start_date: date = Query(..., description="Start date"),
    end_date: date = Query(..., description="End date"),
    interval: str = Query("1d", description="Data interval"),
) -> MarketDataResponse:
    """
    Get historical market data for a symbol.
    """
    try:
        from src.data.sources.yfinance_source import YFinanceSource

        source = YFinanceSource()

        data = await source.fetch_ohlcv(
            symbol=symbol.upper(),
            start=datetime.combine(start_date, datetime.min.time()),
            end=datetime.combine(end_date, datetime.max.time()),
            interval=interval,
        )

        if data.empty:
            raise HTTPException(status_code=404, detail="No data found")

        # Reset index for JSON serialization
        data = data.reset_index()

        return MarketDataResponse(
            symbol=symbol.upper(),
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            data=data.to_dict("records"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting market data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quote/{symbol}")
async def get_quote(symbol: str) -> dict:
    """
    Get latest quote for a symbol.
    """
    try:
        from src.data.sources.yfinance_source import YFinanceSource

        source = YFinanceSource()
        latest = await source.fetch_latest(symbol.upper())

        return {
            "symbol": symbol.upper(),
            "price": float(latest.get("close", 0)),
            "volume": int(latest.get("volume", 0)),
            "timestamp": latest.name.isoformat() if hasattr(latest, "name") else None,
        }

    except Exception as e:
        logger.error(f"Error getting quote for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))