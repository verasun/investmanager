"""Portfolio strategy for multi-asset allocation."""

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import numpy as np

from src.backtest.strategy import Signal
from src.strategies.base import BaseStrategy, StrategyConfig


@dataclass
class AllocationConfig:
    """Configuration for portfolio allocation."""

    target_weights: dict[str, float]  # symbol -> target weight
    rebalance_threshold: float = 0.05  # Rebalance when drift exceeds this
    max_weight: float = 0.40  # Maximum single position weight
    min_weight: float = 0.05  # Minimum position weight


class PortfolioStrategy(BaseStrategy):
    """
    Portfolio strategy for multi-asset allocation.

    Manages a portfolio of multiple instruments with:
    - Target allocation weights
    - Periodic rebalancing
    - Risk parity options
    """

    def __init__(
        self,
        allocation_config: Optional[AllocationConfig] = None,
        rebalance_frequency: str = "monthly",
        config: Optional[StrategyConfig] = None,
    ):
        """
        Initialize portfolio strategy.

        Args:
            allocation_config: Allocation configuration
            rebalance_frequency: 'daily', 'weekly', 'monthly'
            config: Strategy configuration
        """
        config = config or StrategyConfig(name="PortfolioStrategy")
        super().__init__(config)
        self.allocation_config = allocation_config or AllocationConfig(
            target_weights={},
        )
        self.rebalance_frequency = rebalance_frequency
        self._last_rebalance: Optional[pd.Timestamp] = None

    def calculate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate portfolio signals.

        Note: For multi-asset portfolio, use calculate_portfolio_signals instead.

        Args:
            data: OHLCV DataFrame

        Returns:
            Series of Signal values
        """
        return pd.Series(Signal.HOLD, index=data.index)

    def calculate_portfolio_signals(
        self,
        data: dict[str, pd.DataFrame],
    ) -> dict[str, pd.Series]:
        """
        Calculate signals for all portfolio assets.

        Args:
            data: Dictionary of symbol -> OHLCV DataFrame

        Returns:
            Dictionary of symbol -> Signal series
        """
        signals = {}

        for symbol, df in data.items():
            if symbol not in self.allocation_config.target_weights:
                signals[symbol] = pd.Series(Signal.HOLD, index=df.index)
                continue

            signals[symbol] = self._calculate_asset_signal(symbol, df)

        return signals

    def _calculate_asset_signal(
        self,
        symbol: str,
        data: pd.DataFrame,
    ) -> pd.Series:
        """
        Calculate signal for a single asset.

        Args:
            symbol: Asset symbol
            data: OHLCV DataFrame

        Returns:
            Series of Signal values
        """
        signals = pd.Series(Signal.HOLD, index=data.index)
        target_weight = self.allocation_config.target_weights.get(symbol, 0)

        # Check if rebalancing is needed
        for i, (timestamp, row) in enumerate(data.iterrows()):
            if self._should_rebalance(timestamp):
                if target_weight > 0:
                    signals[timestamp] = Signal.BUY
                else:
                    signals[timestamp] = Signal.SELL
                self._last_rebalance = timestamp

        return signals

    def _should_rebalance(self, timestamp: pd.Timestamp) -> bool:
        """
        Check if rebalancing should occur.

        Args:
            timestamp: Current timestamp

        Returns:
            True if rebalancing should occur
        """
        if self._last_rebalance is None:
            return True

        if self.rebalance_frequency == "daily":
            return timestamp.date() > self._last_rebalance.date()

        elif self.rebalance_frequency == "weekly":
            days_since = (timestamp - self._last_rebalance).days
            return days_since >= 7

        elif self.rebalance_frequency == "monthly":
            return timestamp.month != self._last_rebalance.month

        return False

    def calculate_target_weights(
        self,
        prices: dict[str, float],
        current_weights: dict[str, float],
    ) -> dict[str, float]:
        """
        Calculate target weights considering constraints.

        Args:
            prices: Current prices
            current_weights: Current portfolio weights

        Returns:
            Adjusted target weights
        """
        targets = self.allocation_config.target_weights.copy()

        # Apply max weight constraint
        for symbol, weight in targets.items():
            if weight > self.allocation_config.max_weight:
                targets[symbol] = self.allocation_config.max_weight

        # Normalize weights
        total = sum(targets.values())
        if total > 1.0:
            targets = {s: w / total for s, w in targets.items()}

        # Check for significant drift
        adjustments = {}
        for symbol, target in targets.items():
            current = current_weights.get(symbol, 0)
            drift = abs(target - current)

            if drift > self.allocation_config.rebalance_threshold:
                adjustments[symbol] = target

        return adjustments if adjustments else targets


class RiskParityStrategy(BaseStrategy):
    """
    Risk parity portfolio strategy.

    Allocates based on risk contribution rather than capital.
    """

    def __init__(
        self,
        lookback: int = 60,
        target_risk: float = 0.10,
        config: Optional[StrategyConfig] = None,
    ):
        """
        Initialize risk parity strategy.

        Args:
            lookback: Lookback period for volatility calculation
            target_risk: Target portfolio volatility
            config: Strategy configuration
        """
        config = config or StrategyConfig(name="RiskParityStrategy")
        super().__init__(config)
        self.lookback = lookback
        self.target_risk = target_risk

    def calculate_risk_parity_weights(
        self,
        returns: pd.DataFrame,
    ) -> dict[str, float]:
        """
        Calculate risk parity weights.

        Args:
            returns: DataFrame of asset returns (columns are assets)

        Returns:
            Dictionary of asset weights
        """
        # Calculate inverse volatility
        vol = returns.std() * np.sqrt(252)
        inv_vol = 1 / vol

        # Inverse volatility weights
        weights = inv_vol / inv_vol.sum()

        return weights.to_dict()

    def calculate_portfolio_signals(
        self,
        data: dict[str, pd.DataFrame],
    ) -> dict[str, pd.Series]:
        """
        Calculate risk parity signals.

        Args:
            data: Dictionary of symbol -> OHLCV DataFrame

        Returns:
            Dictionary of symbol -> Signal series
        """
        # Get common index
        common_index = None
        for df in data.values():
            if common_index is None:
                common_index = df.index
            else:
                common_index = common_index.intersection(df.index)

        # Calculate returns
        returns = pd.DataFrame()
        for symbol, df in data.items():
            returns[symbol] = df.loc[common_index, "close"].pct_change()

        # Calculate weights
        signals = {symbol: pd.Series(Signal.HOLD, index=common_index) for symbol in data}

        # Rebalance periodically
        last_rebalance = None

        for i, timestamp in enumerate(common_index):
            if i < self.lookback:
                continue

            # Monthly rebalancing
            if last_rebalance is None or timestamp.month != last_rebalance.month:
                hist_returns = returns.loc[:timestamp].tail(self.lookback)
                weights = self.calculate_risk_parity_weights(hist_returns)

                for symbol, weight in weights.items():
                    if weight > 0.05:  # Minimum position
                        signals[symbol][timestamp] = Signal.BUY

                last_rebalance = timestamp

        return signals


class SectorRotationStrategy(BaseStrategy):
    """
    Sector rotation strategy.

    Rotates between sectors based on momentum and relative strength.
    """

    def __init__(
        self,
        top_n: int = 3,
        lookback: int = 60,
        rebalance_frequency: str = "monthly",
        config: Optional[StrategyConfig] = None,
    ):
        """
        Initialize sector rotation strategy.

        Args:
            top_n: Number of top sectors to hold
            lookback: Lookback period for momentum
            rebalance_frequency: How often to rebalance
            config: Strategy configuration
        """
        config = config or StrategyConfig(name="SectorRotationStrategy")
        super().__init__(config)
        self.top_n = top_n
        self.lookback = lookback
        self.rebalance_frequency = rebalance_frequency

    def calculate_sector_ranking(
        self,
        data: dict[str, pd.DataFrame],
        timestamp: pd.Timestamp,
    ) -> list[tuple[str, float]]:
        """
        Rank sectors by momentum.

        Args:
            data: Dictionary of sector ETF data
            timestamp: Current timestamp

        Returns:
            List of (sector, momentum) sorted by momentum descending
        """
        momentum_scores = {}

        for sector, df in data.items():
            if timestamp not in df.index:
                continue

            # Get historical data
            hist = df.loc[:timestamp].tail(self.lookback)
            if len(hist) < self.lookback:
                continue

            # Calculate momentum (price return)
            momentum = hist["close"].iloc[-1] / hist["close"].iloc[0] - 1
            momentum_scores[sector] = momentum

        # Sort by momentum
        ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)

        return ranked

    def calculate_portfolio_signals(
        self,
        data: dict[str, pd.DataFrame],
    ) -> dict[str, pd.Series]:
        """
        Calculate sector rotation signals.

        Args:
            data: Dictionary of sector -> OHLCV DataFrame

        Returns:
            Dictionary of sector -> Signal series
        """
        # Initialize signals
        signals = {sector: pd.Series(Signal.HOLD, index=df.index) for sector, df in data.items()}

        # Get common index
        common_index = None
        for df in data.values():
            if common_index is None:
                common_index = df.index
            else:
                common_index = common_index.intersection(df.index)

        last_rebalance = None
        current_sectors = set()

        for timestamp in common_index:
            # Check if rebalancing needed
            should_rebalance = False
            if last_rebalance is None:
                should_rebalance = True
            elif self.rebalance_frequency == "monthly" and timestamp.month != last_rebalance.month:
                should_rebalance = True
            elif self.rebalance_frequency == "weekly":
                days_since = (timestamp - last_rebalance).days
                should_rebalance = days_since >= 7

            if should_rebalance:
                # Rank sectors
                ranked = self.calculate_sector_ranking(data, timestamp)

                # Select top N
                top_sectors = {s for s, _ in ranked[: self.top_n]}

                # Generate signals
                for sector in data:
                    if sector in top_sectors and sector not in current_sectors:
                        signals[sector][timestamp] = Signal.BUY
                    elif sector not in top_sectors and sector in current_sectors:
                        signals[sector][timestamp] = Signal.SELL

                current_sectors = top_sectors
                last_rebalance = timestamp

        return signals