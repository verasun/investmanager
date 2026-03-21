"""Stock Data Tool - Retrieve stock market data."""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger

from .base import BaseTool, ToolResult


class StockDataTool(BaseTool):
    """Tool for retrieving stock market data.

    Supports A-shares (China) and US stocks.
    """

    name = "stock_data"
    description = "获取股票行情数据。支持A股(中国)和美股。可获取历史K线、实时行情、基本面数据等。"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "股票代码，如 '600519' (茅台) 或 'AAPL' (苹果)",
            },
            "days": {
                "type": "integer",
                "description": "获取最近多少天的数据",
                "default": 365,
            },
            "data_type": {
                "type": "string",
                "enum": ["kline", "realtime", "fundamental"],
                "description": "数据类型: kline(历史K线), realtime(实时行情), fundamental(基本面)",
                "default": "kline",
            },
        },
        "required": ["symbol"],
    }
    timeout = 30

    async def execute(
        self,
        symbol: str,
        days: int = 365,
        data_type: str = "kline",
    ) -> ToolResult:
        """Execute stock data retrieval.

        Args:
            symbol: Stock symbol
            days: Number of days of historical data
            data_type: Type of data to retrieve

        Returns:
            ToolResult with stock data
        """
        try:
            # Determine market based on symbol format
            is_china = symbol.isdigit() or symbol.startswith(("sh", "sz", "0", "3", "6"))

            if data_type == "kline":
                return await self._get_kline_data(symbol, days, is_china)
            elif data_type == "realtime":
                return await self._get_realtime_data(symbol, is_china)
            elif data_type == "fundamental":
                return await self._get_fundamental_data(symbol, is_china)
            else:
                return ToolResult(
                    success=False,
                    error=f"Unknown data type: {data_type}",
                )

        except Exception as e:
            logger.error(f"Stock data retrieval failed: {e}")
            return ToolResult(
                success=False,
                error=f"获取股票数据失败: {str(e)}",
            )

    async def _get_kline_data(
        self,
        symbol: str,
        days: int,
        is_china: bool,
    ) -> ToolResult:
        """Get historical K-line data."""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            if is_china:
                # Use akshare for A-shares
                import akshare as ak

                # Normalize symbol
                code = symbol.lstrip("shsz").lstrip("0").lstrip("3").lstrip("6")
                if len(code) == 6:
                    code = code
                else:
                    code = symbol

                try:
                    df = ak.stock_zh_a_hist(
                        symbol=code,
                        period="daily",
                        start_date=start_date.strftime("%Y%m%d"),
                        end_date=end_date.strftime("%Y%m%d"),
                        adjust="qfq",  # Forward adjusted
                    )

                    if df.empty:
                        return ToolResult(
                            success=False,
                            error=f"未找到股票 {symbol} 的数据",
                        )

                    # Convert to list of dicts
                    records = df.to_dict("records")

                    return ToolResult(
                        success=True,
                        data={
                            "symbol": symbol,
                            "market": "A股",
                            "data_type": "kline",
                            "records": records[:100],  # Limit to 100 records
                            "total_records": len(records),
                            "date_range": {
                                "start": start_date.strftime("%Y-%m-%d"),
                                "end": end_date.strftime("%Y-%m-%d"),
                            },
                        },
                        metadata={
                            "symbol": symbol,
                            "count": len(records),
                        },
                    )

                except Exception as e:
                    # Fallback: try with original symbol
                    df = ak.stock_zh_a_hist(
                        symbol=symbol,
                        period="daily",
                        start_date=start_date.strftime("%Y%m%d"),
                        end_date=end_date.strftime("%Y%m%d"),
                        adjust="qfq",
                    )

                    if df.empty:
                        return ToolResult(
                            success=False,
                            error=f"未找到股票 {symbol} 的数据: {str(e)}",
                        )

                    records = df.to_dict("records")

                    return ToolResult(
                        success=True,
                        data={
                            "symbol": symbol,
                            "market": "A股",
                            "data_type": "kline",
                            "records": records[:100],
                            "total_records": len(records),
                            "date_range": {
                                "start": start_date.strftime("%Y-%m-%d"),
                                "end": end_date.strftime("%Y-%m-%d"),
                            },
                        },
                        metadata={
                            "symbol": symbol,
                            "count": len(records),
                        },
                    )

            else:
                # Use yfinance for US stocks
                import yfinance as yf

                ticker = yf.Ticker(symbol)
                df = ticker.history(start=start_date, end=end_date)

                if df.empty:
                    return ToolResult(
                        success=False,
                        error=f"未找到股票 {symbol} 的数据",
                    )

                # Convert to list of dicts
                df = df.reset_index()
                df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
                records = df.to_dict("records")

                return ToolResult(
                    success=True,
                    data={
                        "symbol": symbol,
                        "market": "美股",
                        "data_type": "kline",
                        "records": records,
                        "total_records": len(records),
                        "date_range": {
                            "start": start_date.strftime("%Y-%m-%d"),
                            "end": end_date.strftime("%Y-%m-%d"),
                        },
                    },
                    metadata={
                        "symbol": symbol,
                        "count": len(records),
                    },
                )

        except Exception as e:
            logger.error(f"K-line data retrieval failed: {e}")
            return ToolResult(
                success=False,
                error=f"获取K线数据失败: {str(e)}",
            )

    async def _get_realtime_data(
        self,
        symbol: str,
        is_china: bool,
    ) -> ToolResult:
        """Get realtime stock data."""
        try:
            if is_china:
                import akshare as ak

                # Get realtime quote
                df = ak.stock_zh_a_spot_em()
                stock_info = df[df["代码"] == symbol.lstrip("shsz")]

                if stock_info.empty:
                    return ToolResult(
                        success=False,
                        error=f"未找到股票 {symbol} 的实时行情",
                    )

                info = stock_info.iloc[0].to_dict()

                return ToolResult(
                    success=True,
                    data={
                        "symbol": symbol,
                        "market": "A股",
                        "data_type": "realtime",
                        "name": info.get("名称", ""),
                        "price": info.get("最新价", 0),
                        "change": info.get("涨跌幅", 0),
                        "change_amount": info.get("涨跌额", 0),
                        "volume": info.get("成交量", 0),
                        "amount": info.get("成交额", 0),
                        "high": info.get("最高", 0),
                        "low": info.get("最低", 0),
                        "open": info.get("今开", 0),
                        "prev_close": info.get("昨收", 0),
                    },
                    metadata={"symbol": symbol},
                )

            else:
                import yfinance as yf

                ticker = yf.Ticker(symbol)
                info = ticker.info

                return ToolResult(
                    success=True,
                    data={
                        "symbol": symbol,
                        "market": "美股",
                        "data_type": "realtime",
                        "name": info.get("longName", info.get("shortName", "")),
                        "price": info.get("currentPrice", info.get("regularMarketPrice", 0)),
                        "change": info.get("regularMarketChangePercent", 0),
                        "volume": info.get("regularMarketVolume", 0),
                        "market_cap": info.get("marketCap", 0),
                        "pe_ratio": info.get("trailingPE", 0),
                    },
                    metadata={"symbol": symbol},
                )

        except Exception as e:
            logger.error(f"Realtime data retrieval failed: {e}")
            return ToolResult(
                success=False,
                error=f"获取实时行情失败: {str(e)}",
            )

    async def _get_fundamental_data(
        self,
        symbol: str,
        is_china: bool,
    ) -> ToolResult:
        """Get fundamental data."""
        try:
            if is_china:
                import akshare as ak

                # Get financial indicators
                try:
                    df = ak.stock_financial_analysis_indicator(symbol=symbol.lstrip("shsz"))
                    indicators = df.to_dict("records")[:20] if not df.empty else []
                except Exception:
                    indicators = []

                return ToolResult(
                    success=True,
                    data={
                        "symbol": symbol,
                        "market": "A股",
                        "data_type": "fundamental",
                        "indicators": indicators,
                    },
                    metadata={"symbol": symbol},
                )

            else:
                import yfinance as yf

                ticker = yf.Ticker(symbol)
                info = ticker.info

                return ToolResult(
                    success=True,
                    data={
                        "symbol": symbol,
                        "market": "美股",
                        "data_type": "fundamental",
                        "info": {
                            "name": info.get("longName", ""),
                            "sector": info.get("sector", ""),
                            "industry": info.get("industry", ""),
                            "market_cap": info.get("marketCap", 0),
                            "pe_ratio": info.get("trailingPE", 0),
                            "forward_pe": info.get("forwardPE", 0),
                            "pb_ratio": info.get("priceToBook", 0),
                            "dividend_yield": info.get("dividendYield", 0),
                            "roe": info.get("returnOnEquity", 0),
                            "revenue_growth": info.get("revenueGrowth", 0),
                            "profit_margin": info.get("profitMargins", 0),
                        },
                    },
                    metadata={"symbol": symbol},
                )

        except Exception as e:
            logger.error(f"Fundamental data retrieval failed: {e}")
            return ToolResult(
                success=False,
                error=f"获取基本面数据失败: {str(e)}",
            )