"""Analysis Tool - Technical and fundamental analysis."""

import sys
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger

from .base import BaseTool, ToolResult


class StockAnalysisTool(BaseTool):
    """Tool for stock technical and fundamental analysis.

    Provides technical indicators, pattern recognition, and analysis insights.
    """

    name = "stock_analysis"
    description = "分析股票的技术指标和基本面。提供均线、MACD、RSI等技术指标分析，以及估值、财务等基本面分析。"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "股票代码",
            },
            "analysis_type": {
                "type": "string",
                "enum": ["technical", "fundamental", "comprehensive"],
                "description": "分析类型: technical(技术分析), fundamental(基本面), comprehensive(综合)",
                "default": "comprehensive",
            },
            "days": {
                "type": "integer",
                "description": "分析天数",
                "default": 365,
            },
        },
        "required": ["symbol"],
    }
    timeout = 60

    async def execute(
        self,
        symbol: str,
        analysis_type: str = "comprehensive",
        days: int = 365,
    ) -> ToolResult:
        """Execute stock analysis.

        Args:
            symbol: Stock symbol
            analysis_type: Type of analysis
            days: Number of days to analyze

        Returns:
            ToolResult with analysis results
        """
        try:
            results = {}

            if analysis_type in ["technical", "comprehensive"]:
                technical = await self._technical_analysis(symbol, days)
                results["technical"] = technical

            if analysis_type in ["fundamental", "comprehensive"]:
                fundamental = await self._fundamental_analysis(symbol)
                results["fundamental"] = fundamental

            # Generate summary if comprehensive
            if analysis_type == "comprehensive":
                results["summary"] = self._generate_summary(results)

            return ToolResult(
                success=True,
                data=results,
                metadata={
                    "symbol": symbol,
                    "analysis_type": analysis_type,
                    "days": days,
                },
            )

        except Exception as e:
            logger.error(f"Stock analysis failed: {e}")
            return ToolResult(
                success=False,
                error=f"股票分析失败: {str(e)}",
            )

    async def _technical_analysis(self, symbol: str, days: int) -> dict:
        """Perform technical analysis."""
        try:
            from src.analysis.technical import TechnicalAnalyzer

            analyzer = TechnicalAnalyzer()
            result = await analyzer.analyze(symbol, days=days)

            return {
                "indicators": result.get("indicators", {}),
                "signals": result.get("signals", []),
                "patterns": result.get("patterns", []),
                "trend": result.get("trend", "unknown"),
                "support_resistance": result.get("support_resistance", {}),
            }

        except ImportError:
            # Fallback: basic technical analysis
            return await self._basic_technical_analysis(symbol, days)

    async def _basic_technical_analysis(self, symbol: str, days: int) -> dict:
        """Basic technical analysis without external dependencies."""
        # Get stock data first
        from .stock_data import StockDataTool

        data_tool = StockDataTool()
        data_result = await data_tool.execute(symbol, days=days, data_type="kline")

        if not data_result.success:
            return {"error": data_result.error}

        records = data_result.data.get("records", [])
        if not records:
            return {"error": "No data for analysis"}

        # Calculate basic indicators
        import pandas as pd
        import numpy as np

        df = pd.DataFrame(records)

        # Handle column names
        close_col = None
        for col in ["close", "收盘", "Close"]:
            if col in df.columns:
                close_col = col
                break

        if close_col is None:
            return {"error": "No close price data"}

        closes = df[close_col].astype(float)

        # Moving averages
        ma5 = closes.rolling(5).mean().iloc[-1] if len(closes) >= 5 else None
        ma10 = closes.rolling(10).mean().iloc[-1] if len(closes) >= 10 else None
        ma20 = closes.rolling(20).mean().iloc[-1] if len(closes) >= 20 else None
        ma60 = closes.rolling(60).mean().iloc[-1] if len(closes) >= 60 else None

        # RSI
        def calc_rsi(prices, period=14):
            deltas = prices.diff()
            gain = deltas.where(deltas > 0, 0).rolling(period).mean()
            loss = (-deltas.where(deltas < 0, 0)).rolling(period).mean()
            rs = gain / loss
            return 100 - (100 / (1 + rs))

        rsi = calc_rsi(closes).iloc[-1] if len(closes) >= 14 else None

        # MACD
        ema12 = closes.ewm(span=12).mean()
        ema26 = closes.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        hist = macd - signal

        # Trend determination
        current_price = closes.iloc[-1]
        trend = "neutral"
        if ma5 and ma10 and ma20:
            if current_price > ma5 > ma10 > ma20:
                trend = "uptrend"
            elif current_price < ma5 < ma10 < ma20:
                trend = "downtrend"

        # Signals
        signals = []
        if rsi:
            if rsi > 70:
                signals.append({"type": "overbought", "indicator": "RSI", "value": rsi})
            elif rsi < 30:
                signals.append({"type": "oversold", "indicator": "RSI", "value": rsi})

        if len(hist) > 1 and hist.iloc[-1] > 0 and hist.iloc[-2] <= 0:
            signals.append({"type": "bullish_cross", "indicator": "MACD"})
        elif len(hist) > 1 and hist.iloc[-1] < 0 and hist.iloc[-2] >= 0:
            signals.append({"type": "bearish_cross", "indicator": "MACD"})

        return {
            "indicators": {
                "MA5": round(ma5, 2) if ma5 else None,
                "MA10": round(ma10, 2) if ma10 else None,
                "MA20": round(ma20, 2) if ma20 else None,
                "MA60": round(ma60, 2) if ma60 else None,
                "RSI": round(rsi, 2) if rsi else None,
                "MACD": round(macd.iloc[-1], 4) if len(macd) > 0 else None,
                "MACD_Signal": round(signal.iloc[-1], 4) if len(signal) > 0 else None,
            },
            "signals": signals,
            "trend": trend,
            "current_price": round(current_price, 2),
        }

    async def _fundamental_analysis(self, symbol: str) -> dict:
        """Perform fundamental analysis."""
        from .stock_data import StockDataTool

        data_tool = StockDataTool()
        data_result = await data_tool.execute(symbol, data_type="fundamental")

        if not data_result.success:
            return {"error": data_result.error}

        return data_result.data

    def _generate_summary(self, results: dict) -> str:
        """Generate analysis summary."""
        parts = []

        technical = results.get("technical", {})
        if technical:
            trend = technical.get("trend", "unknown")
            signals = technical.get("signals", [])

            parts.append(f"技术面趋势: {trend}")

            if signals:
                signal_strs = []
                for s in signals:
                    signal_strs.append(f"{s.get('indicator', '')} {s.get('type', '')}")
                parts.append(f"技术信号: {', '.join(signal_strs)}")

        fundamental = results.get("fundamental", {})
        if fundamental and "error" not in fundamental:
            info = fundamental.get("info", fundamental)
            if isinstance(info, dict):
                if "pe_ratio" in info and info["pe_ratio"]:
                    parts.append(f"PE: {info['pe_ratio']:.2f}")
                if "market_cap" in info and info["market_cap"]:
                    cap = info["market_cap"] / 1e9  # Convert to billions
                    parts.append(f"市值: {cap:.1f}B")

        return " | ".join(parts) if parts else "分析完成"