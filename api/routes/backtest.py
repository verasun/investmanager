"""Backtest API routes."""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from loguru import logger
from pydantic import BaseModel

router = APIRouter()


class BacktestRequest(BaseModel):
    """Backtest request model."""

    symbol: str
    start_date: date
    end_date: date
    strategy: str = "momentum"
    initial_cash: float = 100000.0


class BacktestResultResponse(BaseModel):
    """Backtest result response."""

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


@router.post("/run", response_model=BacktestResultResponse)
async def run_backtest(request: BacktestRequest) -> BacktestResultResponse:
    """
    Run a backtest for a strategy.
    """
    try:
        from src.data.sources.yfinance_source import YFinanceSource
        from src.backtest.engine import BacktestEngine, BacktestConfig
        from src.strategies.momentum import MomentumStrategy, MACDMomentumStrategy
        from src.strategies.mean_reversion import MeanReversionStrategy
        from src.strategies.trend_following import TrendFollowingStrategy

        # Fetch data
        source = YFinanceSource()
        data = await source.fetch_ohlcv(
            symbol=request.symbol.upper(),
            start=datetime.combine(request.start_date, datetime.min.time()),
            end=datetime.combine(request.end_date, datetime.max.time()),
        )

        if data.empty:
            raise HTTPException(status_code=404, detail="No data found")

        # Select strategy
        if request.strategy == "momentum":
            strategy = MomentumStrategy()
        elif request.strategy == "macd":
            strategy = MACDMomentumStrategy()
        elif request.strategy == "mean_reversion":
            strategy = MeanReversionStrategy()
        elif request.strategy == "trend_following":
            strategy = TrendFollowingStrategy()
        else:
            strategy = MomentumStrategy()

        # Configure and run backtest
        config = BacktestConfig(initial_cash=request.initial_cash)
        engine = BacktestEngine(config)

        result = engine.run(strategy, data, symbol=request.symbol.upper())

        return BacktestResultResponse(
            strategy_name=result.strategy_name,
            symbol=request.symbol.upper(),
            start_date=result.start_date.strftime("%Y-%m-%d"),
            end_date=result.end_date.strftime("%Y-%m-%d"),
            initial_value=result.initial_value,
            final_value=result.final_value,
            total_return=result.metrics.total_return,
            annualized_return=result.metrics.annualized_return,
            sharpe_ratio=result.metrics.sharpe_ratio,
            max_drawdown=result.metrics.max_drawdown,
            win_rate=result.metrics.win_rate,
            total_trades=result.metrics.total_trades,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compare")
async def compare_strategies(
    symbol: str = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    strategies: str = Query("momentum,mean_reversion,trend_following"),
) -> dict:
    """
    Compare multiple strategies on the same data.
    """
    try:
        from src.data.sources.yfinance_source import YFinanceSource
        from src.backtest.engine import BacktestEngine
        from src.strategies.momentum import MomentumStrategy
        from src.strategies.mean_reversion import MeanReversionStrategy
        from src.strategies.trend_following import TrendFollowingStrategy

        # Fetch data
        source = YFinanceSource()
        data = await source.fetch_ohlcv(
            symbol=symbol.upper(),
            start=datetime.combine(start_date, datetime.min.time()),
            end=datetime.combine(end_date, datetime.max.time()),
        )

        if data.empty:
            raise HTTPException(status_code=404, detail="No data found")

        # Map strategy names to classes
        strategy_map = {
            "momentum": MomentumStrategy,
            "mean_reversion": MeanReversionStrategy,
            "trend_following": TrendFollowingStrategy,
        }

        # Run backtests
        engine = BacktestEngine()
        strategy_instances = {}

        for strat_name in strategies.split(","):
            strat_name = strat_name.strip()
            if strat_name in strategy_map:
                strategy_instances[strat_name] = strategy_map[strat_name]()

        results = engine.run_multiple(strategy_instances, data, symbol.upper())

        # Format comparison
        comparison = []
        for name, result in results.items():
            comparison.append({
                "strategy": name,
                "total_return": f"{result.metrics.total_return:.2%}",
                "sharpe_ratio": f"{result.metrics.sharpe_ratio:.2f}",
                "max_drawdown": f"{result.metrics.max_drawdown:.2%}",
                "win_rate": f"{result.metrics.win_rate:.2%}",
                "total_trades": result.metrics.total_trades,
            })

        return {
            "symbol": symbol.upper(),
            "period": f"{start_date} to {end_date}",
            "comparison": comparison,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/{symbol}")
async def get_backtest_report(
    symbol: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    strategy: str = Query("momentum"),
) -> dict:
    """
    Generate detailed backtest report.
    """
    try:
        from src.data.sources.yfinance_source import YFinanceSource
        from src.backtest.engine import BacktestEngine
        from src.strategies.momentum import MomentumStrategy

        # Fetch data and run backtest
        source = YFinanceSource()
        data = await source.fetch_ohlcv(
            symbol=symbol.upper(),
            start=datetime.combine(start_date, datetime.min.time()),
            end=datetime.combine(end_date, datetime.max.time()),
        )

        if data.empty:
            raise HTTPException(status_code=404, detail="No data found")

        engine = BacktestEngine()
        result = engine.run(MomentumStrategy(), data, symbol.upper())

        # Generate report
        report = engine.generate_report(result)

        # Get portfolio history
        portfolio_history = result.portfolio_history.reset_index().to_dict("records")

        # Get trade history
        trade_history = result.trade_history.to_dict("records") if not result.trade_history.empty else []

        return {
            "report": report,
            "portfolio_history": portfolio_history,
            "trades": trade_history,
            "metrics": result.metrics.to_dict(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        raise HTTPException(status_code=500, detail=str(e))