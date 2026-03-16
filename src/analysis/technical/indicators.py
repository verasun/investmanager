"""Technical indicators calculation."""

from typing import Optional, Union

import numpy as np
import pandas as pd
from loguru import logger


class TechnicalIndicators:
    """Calculate various technical indicators for financial data."""

    @staticmethod
    def sma(data: pd.Series, period: int) -> pd.Series:
        """
        Simple Moving Average.

        Args:
            data: Price series
            period: Number of periods

        Returns:
            SMA series
        """
        return data.rolling(window=period).mean()

    @staticmethod
    def ema(data: pd.Series, period: int) -> pd.Series:
        """
        Exponential Moving Average.

        Args:
            data: Price series
            period: Number of periods

        Returns:
            EMA series
        """
        return data.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(data: pd.Series, period: int = 14) -> pd.Series:
        """
        Relative Strength Index.

        Args:
            data: Price series (typically close)
            period: RSI period

        Returns:
            RSI series (0-100)
        """
        delta = data.diff()
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)

        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        rs = avg_gain / (avg_loss + 1e-10)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(
        data: pd.Series,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> dict[str, pd.Series]:
        """
        MACD (Moving Average Convergence Divergence).

        Args:
            data: Price series
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            signal_period: Signal line period

        Returns:
            Dictionary with 'macd', 'signal', 'histogram' series
        """
        ema_fast = data.ewm(span=fast_period, adjust=False).mean()
        ema_slow = data.ewm(span=slow_period, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line

        return {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram,
        }

    @staticmethod
    def bollinger_bands(
        data: pd.Series,
        period: int = 20,
        std_dev: float = 2.0,
    ) -> dict[str, pd.Series]:
        """
        Bollinger Bands.

        Args:
            data: Price series
            period: Moving average period
            std_dev: Number of standard deviations

        Returns:
            Dictionary with 'upper', 'middle', 'lower' bands
        """
        middle = data.rolling(window=period).mean()
        std = data.rolling(window=period).std()

        return {
            "upper": middle + std_dev * std,
            "middle": middle,
            "lower": middle - std_dev * std,
            "width": (2 * std_dev * std) / middle * 100,
        }

    @staticmethod
    def kdj(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        n: int = 9,
        m1: int = 3,
        m2: int = 3,
    ) -> dict[str, pd.Series]:
        """
        KDJ (Stochastic Oscillator).

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            n: RSV period
            m1: K period
            m2: D period

        Returns:
            Dictionary with 'K', 'D', 'J' values
        """
        lowest_low = low.rolling(window=n).min()
        highest_high = high.rolling(window=n).max()

        rsv = (close - lowest_low) / (highest_high - lowest_low + 1e-10) * 100

        k = rsv.ewm(alpha=1 / m1, adjust=False).mean()
        d = k.ewm(alpha=1 / m2, adjust=False).mean()
        j = 3 * k - 2 * d

        return {"K": k, "D": d, "J": j}

    @staticmethod
    def atr(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
    ) -> pd.Series:
        """
        Average True Range.

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: ATR period

        Returns:
            ATR series
        """
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """
        On-Balance Volume.

        Args:
            close: Close prices
            volume: Volume

        Returns:
            OBV series
        """
        direction = np.sign(close.diff())
        direction.iloc[0] = 0
        return (volume * direction).cumsum()

    @staticmethod
    def vwap(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
    ) -> pd.Series:
        """
        Volume Weighted Average Price.

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            volume: Volume

        Returns:
            VWAP series
        """
        typical_price = (high + low + close) / 3
        return (typical_price * volume).cumsum() / volume.cumsum()

    @staticmethod
    def williams_r(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
    ) -> pd.Series:
        """
        Williams %R.

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: Lookback period

        Returns:
            Williams %R series (-100 to 0)
        """
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()

        return (highest_high - close) / (highest_high - lowest_low + 1e-10) * -100

    @staticmethod
    def cci(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 20,
    ) -> pd.Series:
        """
        Commodity Channel Index.

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: CCI period

        Returns:
            CCI series
        """
        tp = (high + low + close) / 3
        sma = tp.rolling(window=period).mean()
        mad = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())

        return (tp - sma) / (0.015 * mad + 1e-10)

    @staticmethod
    def adx(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
    ) -> dict[str, pd.Series]:
        """
        Average Directional Index.

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: ADX period

        Returns:
            Dictionary with 'adx', 'plus_di', 'minus_di' series
        """
        plus_dm = high.diff()
        minus_dm = low.diff()

        plus_dm = plus_dm.where((plus_dm > 0) & (plus_dm > minus_dm.abs()), 0)
        minus_dm = minus_dm.where((minus_dm < 0) & (minus_dm.abs() > plus_dm.abs()), 0).abs()

        tr = pd.concat(
            [
                high - low,
                abs(high - close.shift(1)),
                abs(low - close.shift(1)),
            ],
            axis=1,
        ).max(axis=1)

        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / (atr + 1e-10))
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / (atr + 1e-10))

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = dx.rolling(window=period).mean()

        return {"adx": adx, "plus_di": plus_di, "minus_di": minus_di}

    @staticmethod
    def parabolic_sar(
        high: pd.Series,
        low: pd.Series,
        af: float = 0.02,
        max_af: float = 0.2,
    ) -> pd.Series:
        """
        Parabolic SAR.

        Args:
            high: High prices
            low: Low prices
            af: Acceleration factor
            max_af: Maximum acceleration factor

        Returns:
            SAR series
        """
        sar = pd.Series(index=high.index, dtype=float)
        sar.iloc[0] = low.iloc[0]

        trend = 1  # 1 = uptrend, -1 = downtrend
        ep = high.iloc[0]  # Extreme point
        current_af = af

        for i in range(1, len(high)):
            if trend == 1:
                sar.iloc[i] = sar.iloc[i - 1] + current_af * (ep - sar.iloc[i - 1])
                sar.iloc[i] = min(sar.iloc[i], low.iloc[i - 1], low.iloc[i - 2] if i > 1 else low.iloc[i - 1])

                if low.iloc[i] < sar.iloc[i]:
                    trend = -1
                    sar.iloc[i] = ep
                    ep = low.iloc[i]
                    current_af = af
                else:
                    if high.iloc[i] > ep:
                        ep = high.iloc[i]
                        current_af = min(current_af + af, max_af)
            else:
                sar.iloc[i] = sar.iloc[i - 1] - current_af * (sar.iloc[i - 1] - ep)
                sar.iloc[i] = max(sar.iloc[i], high.iloc[i - 1], high.iloc[i - 2] if i > 1 else high.iloc[i - 1])

                if high.iloc[i] > sar.iloc[i]:
                    trend = 1
                    sar.iloc[i] = ep
                    ep = high.iloc[i]
                    current_af = af
                else:
                    if low.iloc[i] < ep:
                        ep = low.iloc[i]
                        current_af = min(current_af + af, max_af)

        return sar

    @staticmethod
    def ichimoku(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        tenkan_period: int = 9,
        kijun_period: int = 26,
        senkou_b_period: int = 52,
    ) -> dict[str, pd.Series]:
        """
        Ichimoku Cloud.

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            tenkan_period: Tenkan-sen period
            kijun_period: Kijun-sen period
            senkou_b_period: Senkou Span B period

        Returns:
            Dictionary with Ichimoku components
        """
        tenkan = (high.rolling(window=tenkan_period).max() + low.rolling(window=tenkan_period).min()) / 2
        kijun = (high.rolling(window=kijun_period).max() + low.rolling(window=kijun_period).min()) / 2

        senkou_a = ((tenkan + kijun) / 2).shift(kijun_period)
        senkou_b = (
            (high.rolling(window=senkou_b_period).max() + low.rolling(window=senkou_b_period).min()) / 2
        ).shift(kijun_period)

        chikou = close.shift(-kijun_period)

        return {
            "tenkan_sen": tenkan,
            "kijun_sen": kijun,
            "senkou_span_a": senkou_a,
            "senkou_span_b": senkou_b,
            "chikou_span": chikou,
        }

    def add_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add all common indicators to a DataFrame.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with all indicators added
        """
        df = df.copy()

        # Moving averages
        for period in [5, 10, 20, 50, 100, 200]:
            df[f"sma_{period}"] = self.sma(df["close"], period)
            df[f"ema_{period}"] = self.ema(df["close"], period)

        # RSI
        df["rsi_6"] = self.rsi(df["close"], 6)
        df["rsi_14"] = self.rsi(df["close"], 14)

        # MACD
        macd = self.macd(df["close"])
        df["macd"] = macd["macd"]
        df["macd_signal"] = macd["signal"]
        df["macd_hist"] = macd["histogram"]

        # Bollinger Bands
        bb = self.bollinger_bands(df["close"])
        df["bb_upper"] = bb["upper"]
        df["bb_middle"] = bb["middle"]
        df["bb_lower"] = bb["lower"]
        df["bb_width"] = bb["width"]

        # KDJ
        kdj = self.kdj(df["high"], df["low"], df["close"])
        df["k"] = kdj["K"]
        df["d"] = kdj["D"]
        df["j"] = kdj["J"]

        # ATR
        df["atr_14"] = self.atr(df["high"], df["low"], df["close"], 14)

        # OBV
        df["obv"] = self.obv(df["close"], df["volume"])

        # ADX
        adx = self.adx(df["high"], df["low"], df["close"])
        df["adx"] = adx["adx"]
        df["plus_di"] = adx["plus_di"]
        df["minus_di"] = adx["minus_di"]

        return df