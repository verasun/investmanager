"""Risk exposure tracking and management."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


class RiskMetric(Enum):
    """Risk metric types."""

    VAR = "var"
    CVAR = "cvar"
    VOLATILITY = "volatility"
    BETA = "beta"
    DRAWDOWN = "drawdown"


@dataclass
class ExposureSnapshot:
    """Snapshot of portfolio exposure at a point in time."""

    timestamp: datetime
    total_value: float
    gross_exposure: float  # Sum of absolute position values
    net_exposure: float  # Long - Short
    long_exposure: float
    short_exposure: float
    cash: float
    leverage: float
    beta: Optional[float] = None
    var_95: Optional[float] = None


@dataclass
class RiskLimits:
    """Risk limits configuration."""

    max_gross_exposure: float = 1.0  # Max 100% gross exposure
    max_net_exposure: float = 1.0  # Max 100% net long/short
    max_leverage: float = 2.0
    max_single_position: float = 0.10
    max_sector_exposure: float = 0.30
    max_var_pct: float = 0.05  # Max 5% daily VaR
    max_drawdown: float = 0.20  # Max 20% drawdown


class ExposureManager:
    """
    Portfolio exposure manager.

    Tracks and manages risk exposure across multiple dimensions.
    """

    def __init__(self, limits: Optional[RiskLimits] = None):
        """
        Initialize exposure manager.

        Args:
            limits: Risk limits configuration
        """
        self.limits = limits or RiskLimits()
        self.snapshots: list[ExposureSnapshot] = []
        self.position_history: dict[str, list[dict]] = {}

    def calculate_exposure(
        self,
        positions: dict[str, float],
        prices: dict[str, float],
        cash: float,
    ) -> ExposureSnapshot:
        """
        Calculate current exposure.

        Args:
            positions: Symbol -> quantity mapping
            prices: Symbol -> price mapping
            cash: Cash balance

        Returns:
            ExposureSnapshot
        """
        long_value = 0.0
        short_value = 0.0

        for symbol, quantity in positions.items():
            price = prices.get(symbol, 0)
            value = quantity * price

            if quantity > 0:
                long_value += value
            else:
                short_value += abs(value)

        gross_exposure = long_value + short_value
        net_exposure = long_value - short_value
        total_value = gross_exposure + cash

        leverage = gross_exposure / total_value if total_value > 0 else 0

        snapshot = ExposureSnapshot(
            timestamp=datetime.now(),
            total_value=total_value,
            gross_exposure=gross_exposure,
            net_exposure=net_exposure,
            long_exposure=long_value,
            short_exposure=short_value,
            cash=cash,
            leverage=leverage,
        )

        self.snapshots.append(snapshot)
        return snapshot

    def calculate_var(
        self,
        returns: pd.Series,
        confidence: float = 0.95,
    ) -> float:
        """
        Calculate Value at Risk.

        Args:
            returns: Historical returns series
            confidence: Confidence level

        Returns:
            VaR value
        """
        return abs(returns.quantile(1 - confidence))

    def calculate_cvar(
        self,
        returns: pd.Series,
        confidence: float = 0.95,
    ) -> float:
        """
        Calculate Conditional VaR.

        Args:
            returns: Historical returns series
            confidence: Confidence level

        Returns:
            CVaR value
        """
        var_threshold = returns.quantile(1 - confidence)
        return abs(returns[returns <= var_threshold].mean())

    def calculate_beta(
        self,
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series,
    ) -> float:
        """
        Calculate portfolio beta.

        Args:
            portfolio_returns: Portfolio returns
            benchmark_returns: Benchmark returns

        Returns:
            Beta value
        """
        covariance = portfolio_returns.cov(benchmark_returns)
        variance = benchmark_returns.var()

        if variance == 0:
            return 0.0

        return covariance / variance

    def check_limits(
        self,
        snapshot: ExposureSnapshot,
    ) -> list[dict]:
        """
        Check if exposure violates limits.

        Args:
            snapshot: Current exposure snapshot

        Returns:
            List of limit violations
        """
        violations = []

        if snapshot.gross_exposure / snapshot.total_value > self.limits.max_gross_exposure:
            violations.append(
                {
                    "type": "gross_exposure",
                    "current": snapshot.gross_exposure / snapshot.total_value,
                    "limit": self.limits.max_gross_exposure,
                    "message": "Gross exposure exceeds limit",
                }
            )

        if abs(snapshot.net_exposure / snapshot.total_value) > self.limits.max_net_exposure:
            violations.append(
                {
                    "type": "net_exposure",
                    "current": abs(snapshot.net_exposure / snapshot.total_value),
                    "limit": self.limits.max_net_exposure,
                    "message": "Net exposure exceeds limit",
                }
            )

        if snapshot.leverage > self.limits.max_leverage:
            violations.append(
                {
                    "type": "leverage",
                    "current": snapshot.leverage,
                    "limit": self.limits.max_leverage,
                    "message": "Leverage exceeds limit",
                }
            )

        return violations

    def get_exposure_summary(self) -> dict:
        """
        Get summary of recent exposure.

        Returns:
            Exposure summary dictionary
        """
        if not self.snapshots:
            return {}

        latest = self.snapshots[-1]

        # Calculate trends
        if len(self.snapshots) >= 5:
            recent_leverage = [s.leverage for s in self.snapshots[-5:]]
            leverage_trend = "increasing" if recent_leverage[-1] > recent_leverage[0] else "decreasing"
        else:
            leverage_trend = "stable"

        return {
            "total_value": latest.total_value,
            "gross_exposure": latest.gross_exposure,
            "gross_exposure_pct": latest.gross_exposure / latest.total_value,
            "net_exposure": latest.net_exposure,
            "net_exposure_pct": latest.net_exposure / latest.total_value,
            "long_exposure": latest.long_exposure,
            "short_exposure": latest.short_exposure,
            "cash": latest.cash,
            "leverage": latest.leverage,
            "leverage_trend": leverage_trend,
        }

    def get_exposure_history(self, days: int = 30) -> pd.DataFrame:
        """
        Get exposure history.

        Args:
            days: Number of days to retrieve

        Returns:
            DataFrame with exposure history
        """
        if not self.snapshots:
            return pd.DataFrame()

        recent = self.snapshots[-days:] if len(self.snapshots) > days else self.snapshots

        return pd.DataFrame([
            {
                "timestamp": s.timestamp,
                "total_value": s.total_value,
                "gross_exposure": s.gross_exposure,
                "net_exposure": s.net_exposure,
                "leverage": s.leverage,
            }
            for s in recent
        ])


class StressTester:
    """
    Portfolio stress testing.

    Simulates various market scenarios to assess risk.
    """

    def __init__(self):
        """Initialize stress tester."""
        self.scenarios = {
            "market_crash": {
                "equity_shock": -0.20,
                "volatility_mult": 2.0,
            },
            "flash_crash": {
                "equity_shock": -0.10,
                "volatility_mult": 5.0,
            },
            "rate_hike": {
                "bond_shock": -0.05,
                "equity_shock": -0.05,
            },
            "liquidity_crisis": {
                "spread_widening": 0.02,
                "equity_shock": -0.15,
            },
        }

    def run_stress_test(
        self,
        positions: dict[str, float],
        prices: dict[str, float],
        asset_classes: dict[str, str],  # symbol -> asset class
        scenario: str = "market_crash",
    ) -> dict:
        """
        Run stress test for a scenario.

        Args:
            positions: Current positions
            prices: Current prices
            asset_classes: Asset class mapping
            scenario: Stress scenario name

        Returns:
            Stress test results
        """
        if scenario not in self.scenarios:
            raise ValueError(f"Unknown scenario: {scenario}")

        params = self.scenarios[scenario]

        original_value = sum(
            positions[s] * prices.get(s, 0) for s in positions
        )

        stressed_value = 0.0
        position_impacts = []

        for symbol, quantity in positions.items():
            price = prices.get(symbol, 0)
            original_pos_value = quantity * price

            asset_class = asset_classes.get(symbol, "equity")

            # Apply shock based on asset class
            if asset_class == "equity":
                shock = params.get("equity_shock", 0)
            elif asset_class == "bond":
                shock = params.get("bond_shock", 0)
            else:
                shock = params.get("equity_shock", 0)

            stressed_price = price * (1 + shock)
            stressed_pos_value = quantity * stressed_price
            stressed_value += stressed_pos_value

            position_impacts.append({
                "symbol": symbol,
                "original_value": original_pos_value,
                "stressed_value": stressed_pos_value,
                "impact": stressed_pos_value - original_pos_value,
                "impact_pct": (stressed_pos_value - original_pos_value) / original_pos_value,
            })

        total_impact = stressed_value - original_value
        impact_pct = total_impact / original_value if original_value > 0 else 0

        return {
            "scenario": scenario,
            "original_value": original_value,
            "stressed_value": stressed_value,
            "total_impact": total_impact,
            "impact_pct": impact_pct,
            "position_impacts": position_impacts,
        }

    def run_all_scenarios(
        self,
        positions: dict[str, float],
        prices: dict[str, float],
        asset_classes: dict[str, str],
    ) -> dict[str, dict]:
        """
        Run all stress scenarios.

        Args:
            positions: Current positions
            prices: Current prices
            asset_classes: Asset class mapping

        Returns:
            Dictionary of scenario results
        """
        results = {}

        for scenario in self.scenarios:
            results[scenario] = self.run_stress_test(
                positions, prices, asset_classes, scenario
            )

        return results