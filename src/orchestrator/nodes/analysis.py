"""Technical analysis task node."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from loguru import logger

from src.orchestrator.nodes.base import TaskNode, run_node
from src.analysis.technical.indicators import TechnicalIndicators
from src.analysis.technical.signals import SignalGenerator
from src.analysis.technical.patterns import PatternRecognition


class AnalysisNode(TaskNode):
    """
    Task node for technical analysis.

    Calculates technical indicators, generates signals, and recognizes patterns.

    Input:
        data_path: Path to OHLCV data file
        indicators: List of indicators to calculate (optional)
        generate_signals: Whether to generate trading signals
        recognize_patterns: Whether to recognize chart patterns
        custom_params: Custom parameters for indicators

    Output:
        analysis_path: Path to analysis results
        indicators: List of calculated indicators
        signals: Trading signals (if generated)
        patterns: Recognized patterns (if detected)
    """

    # Default indicators to calculate
    DEFAULT_INDICATORS = [
        "sma_5", "sma_10", "sma_20", "sma_50",
        "ema_12", "ema_26",
        "rsi_6", "rsi_14",
        "macd",
        "bollinger_bands",
        "kdj",
        "atr_14",
        "obv",
        "adx",
    ]

    def setup(self) -> None:
        """Initialize analysis components."""
        self.indicators = TechnicalIndicators()
        self.signal_generator = SignalGenerator()
        self.pattern_recognizer = PatternRecognition()

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        """Validate input data."""
        if "data_path" not in input_data:
            logger.error("Missing required field: data_path")
            return False
        return True

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute technical analysis."""
        task_id = input_data.get("task_id", "unknown")
        data_path = input_data["data_path"]
        indicators_list = input_data.get("indicators", self.DEFAULT_INDICATORS)
        generate_signals = input_data.get("generate_signals", True)
        recognize_patterns = input_data.get("recognize_patterns", False)
        custom_params = input_data.get("custom_params", {})

        logger.info(f"Loading data from {data_path}")

        # Load data
        df = self._load_data(data_path)
        logger.info(f"Loaded {len(df)} rows of data")

        # Calculate indicators
        df = self._calculate_indicators(df, indicators_list, custom_params)
        logger.info(f"Calculated {len(indicators_list)} indicators")

        results = {
            "indicators": indicators_list,
            "row_count": len(df),
            "symbols": df["symbol"].unique().tolist() if "symbol" in df.columns else ["unknown"],
        }

        # Generate signals if requested
        if generate_signals:
            signals = self._generate_signals(df)
            df = pd.concat([df, signals], axis=1)
            results["signals"] = {
                "buy_count": int((signals["signal"] == 1).sum()) if "signal" in signals.columns else 0,
                "sell_count": int((signals["signal"] == -1).sum()) if "signal" in signals.columns else 0,
            }
            logger.info("Generated trading signals")

        # Recognize patterns if requested
        if recognize_patterns:
            patterns = self._recognize_patterns(df)
            results["patterns"] = patterns
            logger.info(f"Recognized {len(patterns)} patterns")

        # Save results
        output_dir = self._ensure_output_dir(task_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save as parquet
        analysis_file = output_dir / f"analysis_{timestamp}.parquet"
        df.to_parquet(analysis_file, index=False)

        # Save summary as JSON
        summary_file = output_dir / f"analysis_summary_{timestamp}.json"
        with open(summary_file, "w") as f:
            json.dump(results, f, default=str, indent=2)

        logger.info(f"Saved analysis to {analysis_file}")

        return {
            "analysis_path": str(analysis_file),
            "summary_path": str(summary_file),
            **results,
            "artifacts": [str(analysis_file), str(summary_file)],
        }

    def _load_data(self, data_path: str) -> pd.DataFrame:
        """Load data from file."""
        path = self._resolve_path(data_path)

        if path.suffix == ".parquet":
            return pd.read_parquet(path)
        elif path.suffix == ".json":
            return pd.read_json(path)
        elif path.suffix == ".csv":
            return pd.read_csv(path)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

    def _calculate_indicators(
        self,
        df: pd.DataFrame,
        indicators_list: list[str],
        custom_params: dict,
    ) -> pd.DataFrame:
        """Calculate specified technical indicators."""
        df = df.copy()

        # Ensure column names are lowercase
        df.columns = [col.lower() for col in df.columns]

        for indicator in indicators_list:
            try:
                if indicator.startswith("sma_"):
                    period = int(indicator.split("_")[1])
                    df[f"sma_{period}"] = self.indicators.sma(df["close"], period)

                elif indicator.startswith("ema_"):
                    period = int(indicator.split("_")[1])
                    df[f"ema_{period}"] = self.indicators.ema(df["close"], period)

                elif indicator.startswith("rsi_"):
                    period = int(indicator.split("_")[1])
                    df[f"rsi_{period}"] = self.indicators.rsi(df["close"], period)

                elif indicator == "macd":
                    macd = self.indicators.macd(df["close"])
                    df["macd"] = macd["macd"]
                    df["macd_signal"] = macd["signal"]
                    df["macd_hist"] = macd["histogram"]

                elif indicator == "bollinger_bands":
                    bb = self.indicators.bollinger_bands(df["close"])
                    df["bb_upper"] = bb["upper"]
                    df["bb_middle"] = bb["middle"]
                    df["bb_lower"] = bb["lower"]
                    df["bb_width"] = bb["width"]

                elif indicator == "kdj":
                    kdj = self.indicators.kdj(df["high"], df["low"], df["close"])
                    df["k"] = kdj["K"]
                    df["d"] = kdj["D"]
                    df["j"] = kdj["J"]

                elif indicator.startswith("atr_"):
                    period = int(indicator.split("_")[1])
                    df[f"atr_{period}"] = self.indicators.atr(
                        df["high"], df["low"], df["close"], period
                    )

                elif indicator == "obv":
                    df["obv"] = self.indicators.obv(df["close"], df["volume"])

                elif indicator == "adx":
                    adx = self.indicators.adx(df["high"], df["low"], df["close"])
                    df["adx"] = adx["adx"]
                    df["plus_di"] = adx["plus_di"]
                    df["minus_di"] = adx["minus_di"]

                elif indicator == "all":
                    # Calculate all default indicators
                    df = self.indicators.add_all_indicators(df)

            except Exception as e:
                logger.warning(f"Failed to calculate {indicator}: {e}")

        return df

    def _generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate trading signals."""
        signals = pd.DataFrame(index=df.index)

        # Simple MACD signal
        if "macd" in df.columns and "macd_signal" in df.columns:
            signals["macd_signal"] = 0
            signals.loc[df["macd"] > df["macd_signal"], "macd_signal"] = 1
            signals.loc[df["macd"] < df["macd_signal"], "macd_signal"] = -1

        # RSI signal
        if "rsi_14" in df.columns:
            signals["rsi_signal"] = 0
            signals.loc[df["rsi_14"] < 30, "rsi_signal"] = 1  # Oversold
            signals.loc[df["rsi_14"] > 70, "rsi_signal"] = -1  # Overbought

        # Bollinger Band signal
        if "bb_upper" in df.columns and "bb_lower" in df.columns:
            signals["bb_signal"] = 0
            signals.loc[df["close"] < df["bb_lower"], "bb_signal"] = 1  # Buy signal
            signals.loc[df["close"] > df["bb_upper"], "bb_signal"] = -1  # Sell signal

        # Combined signal (simple voting)
        signal_cols = [col for col in signals.columns if col.endswith("_signal")]
        if signal_cols:
            signals["signal"] = signals[signal_cols].mean(axis=1)
            signals["signal"] = signals["signal"].apply(
                lambda x: 1 if x > 0.3 else (-1 if x < -0.3 else 0)
            )

        return signals

    def _recognize_patterns(self, df: pd.DataFrame) -> list[dict]:
        """Recognize chart patterns."""
        patterns = []

        try:
            # Use pattern recognizer if available
            recognized = self.pattern_recognizer.recognize_all(df)
            patterns = [
                {
                    "name": p.pattern_name,
                    "start_idx": p.start_idx,
                    "end_idx": p.end_idx,
                    "direction": p.direction,
                    "confidence": getattr(p, "confidence", 0.5),
                }
                for p in recognized
            ]
        except Exception as e:
            logger.warning(f"Pattern recognition failed: {e}")

        return patterns


if __name__ == "__main__":
    run_node(AnalysisNode)