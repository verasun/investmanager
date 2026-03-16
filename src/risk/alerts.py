"""Risk alerts and notifications."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

from loguru import logger


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertType(Enum):
    """Alert type enumeration."""

    POSITION_LIMIT = "position_limit"
    LOSS_LIMIT = "loss_limit"
    DRAWDOWN = "drawdown"
    LEVERAGE = "leverage"
    VOLATILITY = "volatility"
    CORRELATION = "correlation"
    LIQUIDITY = "liquidity"
    CONCENTRATION = "concentration"
    VAR_BREACH = "var_breach"
    STRESS_TEST = "stress_test"


@dataclass
class RiskAlert:
    """Risk alert data structure."""

    alert_type: AlertType
    severity: AlertSeverity
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    symbol: Optional[str] = None
    current_value: Optional[float] = None
    threshold: Optional[float] = None
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "details": self.details,
        }


@dataclass
class AlertRule:
    """Alert rule configuration."""

    alert_type: AlertType
    threshold: float
    severity: AlertSeverity = AlertSeverity.WARNING
    cooldown_minutes: int = 60  # Don't repeat same alert
    enabled: bool = True


class AlertManager:
    """
    Risk alert management system.

    Monitors risk metrics and generates alerts when thresholds are breached.
    """

    def __init__(self):
        """Initialize alert manager."""
        self.rules: dict[AlertType, AlertRule] = {}
        self.alerts: list[RiskAlert] = []
        self._last_alert_time: dict[str, datetime] = {}
        self._callbacks: list[Callable[[RiskAlert], None]] = []

        # Initialize default rules
        self._init_default_rules()

    def _init_default_rules(self) -> None:
        """Initialize default alert rules."""
        default_rules = [
            AlertRule(
                alert_type=AlertType.DRAWDOWN,
                threshold=0.10,
                severity=AlertSeverity.WARNING,
            ),
            AlertRule(
                alert_type=AlertType.DRAWDOWN,
                threshold=0.15,
                severity=AlertSeverity.CRITICAL,
            ),
            AlertRule(
                alert_type=AlertType.DRAWDOWN,
                threshold=0.20,
                severity=AlertSeverity.EMERGENCY,
            ),
            AlertRule(
                alert_type=AlertType.LEVERAGE,
                threshold=1.5,
                severity=AlertSeverity.WARNING,
            ),
            AlertRule(
                alert_type=AlertType.LEVERAGE,
                threshold=2.0,
                severity=AlertSeverity.CRITICAL,
            ),
            AlertRule(
                alert_type=AlertType.POSITION_LIMIT,
                threshold=0.10,
                severity=AlertSeverity.WARNING,
            ),
            AlertRule(
                alert_type=AlertType.LOSS_LIMIT,
                threshold=0.05,
                severity=AlertSeverity.WARNING,
            ),
            AlertRule(
                alert_type=AlertType.VAR_BREACH,
                threshold=0.95,
                severity=AlertSeverity.WARNING,
            ),
        ]

        for rule in default_rules:
            self.rules[rule.alert_type] = rule

    def add_rule(self, rule: AlertRule) -> None:
        """Add or update an alert rule."""
        self.rules[rule.alert_type] = rule

    def remove_rule(self, alert_type: AlertType) -> None:
        """Remove an alert rule."""
        if alert_type in self.rules:
            del self.rules[alert_type]

    def register_callback(self, callback: Callable[[RiskAlert], None]) -> None:
        """Register a callback for alerts."""
        self._callbacks.append(callback)

    def check_drawdown(
        self,
        current_drawdown: float,
        portfolio_value: float,
        peak_value: float,
    ) -> Optional[RiskAlert]:
        """
        Check drawdown against thresholds.

        Args:
            current_drawdown: Current drawdown percentage
            portfolio_value: Current portfolio value
            peak_value: Peak portfolio value

        Returns:
            Alert if threshold breached
        """
        rule = self.rules.get(AlertType.DRAWDOWN)
        if not rule or not rule.enabled:
            return None

        # Find applicable threshold
        severity = None
        threshold = None

        if current_drawdown >= 0.20:
            severity = AlertSeverity.EMERGENCY
            threshold = 0.20
        elif current_drawdown >= 0.15:
            severity = AlertSeverity.CRITICAL
            threshold = 0.15
        elif current_drawdown >= 0.10:
            severity = AlertSeverity.WARNING
            threshold = 0.10
        else:
            return None

        return self._create_alert(
            RiskAlert(
                alert_type=AlertType.DRAWDOWN,
                severity=severity,
                message=f"Drawdown {current_drawdown:.1%} exceeds {threshold:.0%} threshold",
                current_value=current_drawdown,
                threshold=threshold,
                details={
                    "portfolio_value": portfolio_value,
                    "peak_value": peak_value,
                },
            )
        )

    def check_leverage(
        self,
        current_leverage: float,
    ) -> Optional[RiskAlert]:
        """
        Check leverage against thresholds.

        Args:
            current_leverage: Current leverage ratio

        Returns:
            Alert if threshold breached
        """
        if current_leverage <= 1.0:
            return None

        severity = None
        threshold = None

        if current_leverage >= 2.0:
            severity = AlertSeverity.CRITICAL
            threshold = 2.0
        elif current_leverage >= 1.5:
            severity = AlertSeverity.WARNING
            threshold = 1.5
        else:
            return None

        return self._create_alert(
            RiskAlert(
                alert_type=AlertType.LEVERAGE,
                severity=severity,
                message=f"Leverage {current_leverage:.2f}x exceeds {threshold:.1f}x threshold",
                current_value=current_leverage,
                threshold=threshold,
            )
        )

    def check_position_concentration(
        self,
        symbol: str,
        position_weight: float,
    ) -> Optional[RiskAlert]:
        """
        Check position concentration.

        Args:
            symbol: Security symbol
            position_weight: Position weight in portfolio

        Returns:
            Alert if threshold breached
        """
        rule = self.rules.get(AlertType.POSITION_LIMIT)
        if not rule or not rule.enabled:
            return None

        if position_weight <= rule.threshold:
            return None

        return self._create_alert(
            RiskAlert(
                alert_type=AlertType.POSITION_LIMIT,
                severity=rule.severity,
                message=f"Position {symbol} at {position_weight:.1%} exceeds {rule.threshold:.0%} limit",
                symbol=symbol,
                current_value=position_weight,
                threshold=rule.threshold,
            )
        )

    def check_daily_loss(
        self,
        daily_pnl_pct: float,
        daily_pnl: float,
    ) -> Optional[RiskAlert]:
        """
        Check daily loss against limits.

        Args:
            daily_pnl_pct: Daily P&L percentage
            daily_pnl: Daily P&L amount

        Returns:
            Alert if threshold breached
        """
        rule = self.rules.get(AlertType.LOSS_LIMIT)
        if not rule or not rule.enabled:
            return None

        if daily_pnl_pct >= -rule.threshold:
            return None

        return self._create_alert(
            RiskAlert(
                alert_type=AlertType.LOSS_LIMIT,
                severity=rule.severity,
                message=f"Daily loss {daily_pnl_pct:.1%} exceeds {rule.threshold:.0%} limit",
                current_value=daily_pnl_pct,
                threshold=-rule.threshold,
                details={"daily_pnl": daily_pnl},
            )
        )

    def check_var_breach(
        self,
        var_95: float,
        portfolio_value: float,
    ) -> Optional[RiskAlert]:
        """
        Check VaR against limits.

        Args:
            var_95: 95% VaR
            portfolio_value: Portfolio value

        Returns:
            Alert if threshold breached
        """
        rule = self.rules.get(AlertType.VAR_BREACH)
        if not rule or not rule.enabled:
            return None

        var_pct = var_95 / portfolio_value

        if var_pct <= rule.threshold:
            return None

        return self._create_alert(
            RiskAlert(
                alert_type=AlertType.VAR_BREACH,
                severity=rule.severity,
                message=f"VaR {var_pct:.1%} exceeds {rule.threshold:.0%} threshold",
                current_value=var_pct,
                threshold=rule.threshold,
                details={"var_95": var_95, "portfolio_value": portfolio_value},
            )
        )

    def _create_alert(self, alert: RiskAlert) -> Optional[RiskAlert]:
        """
        Create and process an alert.

        Args:
            alert: Alert to create

        Returns:
            Alert if created, None if in cooldown
        """
        # Check cooldown
        alert_key = f"{alert.alert_type.value}_{alert.symbol or 'portfolio'}"

        if alert_key in self._last_alert_time:
            time_since = (datetime.now() - self._last_alert_time[alert_key]).total_seconds() / 60

            rule = self.rules.get(alert.alert_type)
            cooldown = rule.cooldown_minutes if rule else 60

            if time_since < cooldown:
                logger.debug(f"Alert {alert_key} in cooldown")
                return None

        # Store alert
        self.alerts.append(alert)
        self._last_alert_time[alert_key] = datetime.now()

        # Log alert
        log_msg = f"RISK ALERT [{alert.severity.value.upper()}]: {alert.message}"
        if alert.severity == AlertSeverity.EMERGENCY:
            logger.error(log_msg)
        elif alert.severity == AlertSeverity.CRITICAL:
            logger.error(log_msg)
        elif alert.severity == AlertSeverity.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        # Call callbacks
        for callback in self._callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

        return alert

    def get_recent_alerts(
        self,
        hours: int = 24,
        severity: Optional[AlertSeverity] = None,
    ) -> list[RiskAlert]:
        """
        Get recent alerts.

        Args:
            hours: Hours to look back
            severity: Optional severity filter

        Returns:
            List of recent alerts
        """
        cutoff = datetime.now() - __import__("datetime").timedelta(hours=hours)

        alerts = [a for a in self.alerts if a.timestamp >= cutoff]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    def clear_alerts(self) -> None:
        """Clear all alerts."""
        self.alerts.clear()
        self._last_alert_time.clear()

    def get_alert_summary(self) -> dict:
        """
        Get summary of current alert status.

        Returns:
            Alert summary dictionary
        """
        recent = self.get_recent_alerts(hours=24)

        summary = {
            "total_alerts_24h": len(recent),
            "by_severity": {},
            "by_type": {},
            "latest_alert": None,
        }

        for severity in AlertSeverity:
            count = len([a for a in recent if a.severity == severity])
            if count > 0:
                summary["by_severity"][severity.value] = count

        for alert_type in AlertType:
            count = len([a for a in recent if a.alert_type == alert_type])
            if count > 0:
                summary["by_type"][alert_type.value] = count

        if recent:
            summary["latest_alert"] = recent[0].to_dict()

        return summary