"""Data fetch task node."""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from src.orchestrator.nodes.base import TaskNode, run_node
from src.data.sources.yfinance_source import YFinanceSource
from src.data.sources.akshare_source import AkshareSource


class DataFetchNode(TaskNode):
    """
    Task node for fetching market data.

    Supports multiple data sources:
    - YFinance (US stocks)
    - AKShare (Chinese A-shares)

    Input:
        symbols: List of stock symbols
        source: Data source ('yfinance' or 'akshare')
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        interval: Data interval ('1d', '1h', etc.)

    Output:
        data_path: Path to saved data file
        symbols: List of fetched symbols
        count: Total number of data points
    """

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        """Validate input data."""
        if "symbols" not in input_data:
            logger.error("Missing required field: symbols")
            return False

        symbols = input_data.get("symbols", [])
        if not symbols or not isinstance(symbols, list):
            logger.error("symbols must be a non-empty list")
            return False

        return True

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute data fetch."""
        task_id = input_data.get("task_id", "unknown")
        symbols = input_data["symbols"]
        source = input_data.get("source", "yfinance")
        start_date = input_data.get("start_date")
        end_date = input_data.get("end_date")
        interval = input_data.get("interval", "1d")

        logger.info(f"Fetching data for {len(symbols)} symbols from {source}")

        # Parse dates
        if end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end = datetime.now()

        if start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start = end - timedelta(days=365)  # Default 1 year

        # Get data source
        data_source = self._get_data_source(source)

        # Fetch data for each symbol
        all_data = []
        errors = []

        for symbol in symbols:
            try:
                logger.info(f"Fetching {symbol}...")
                df = asyncio.run(
                    data_source.fetch_ohlcv(symbol, start, end, interval)
                )

                if df.empty:
                    logger.warning(f"No data returned for {symbol}")
                    continue

                all_data.append(df)
                logger.info(f"Fetched {len(df)} rows for {symbol}")

            except Exception as e:
                logger.error(f"Error fetching {symbol}: {e}")
                errors.append({"symbol": symbol, "error": str(e)})

        if not all_data:
            raise ValueError("No data fetched for any symbol")

        # Combine all data
        import pandas as pd
        combined_df = pd.concat(all_data, ignore_index=True)

        # Save to file
        output_dir = self._ensure_output_dir(task_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        data_file = output_dir / f"data_{timestamp}.parquet"
        combined_df.to_parquet(data_file, index=False)

        # Also save as JSON for small datasets
        json_file = output_dir / f"data_{timestamp}.json"
        combined_df.to_json(json_file, orient="records", date_format="iso")

        logger.info(f"Saved {len(combined_df)} total rows to {data_file}")

        return {
            "data_path": str(data_file),
            "data_path_json": str(json_file),
            "symbols": symbols,
            "count": len(combined_df),
            "date_range": {
                "start": str(start.date()),
                "end": str(end.date()),
            },
            "errors": errors if errors else None,
            "artifacts": [str(data_file), str(json_file)],
        }

    def _get_data_source(self, source: str):
        """Get the appropriate data source."""
        if source == "yfinance":
            return YFinanceSource()
        elif source == "akshare":
            return AkshareSource()
        else:
            raise ValueError(f"Unknown data source: {source}")


if __name__ == "__main__":
    run_node(DataFetchNode)