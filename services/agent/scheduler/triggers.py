"""Scheduler Triggers - Define trigger types for scheduled tasks."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional, Callable


class TriggerType(str, Enum):
    """Types of triggers."""

    CRON = "cron"
    INTERVAL = "interval"
    ONCE = "once"
    EVENT = "event"
    PRICE = "price"
    NEWS = "news"


@dataclass
class Trigger:
    """Base class for triggers."""

    trigger_type: TriggerType
    enabled: bool = True

    def get_next_fire_time(self, now: datetime = None) -> Optional[datetime]:
        """Get the next fire time."""
        raise NotImplementedError


@dataclass
class CronTrigger(Trigger):
    """Cron-based trigger."""

    trigger_type: TriggerType = TriggerType.CRON
    hour: int = 0
    minute: int = 0
    day_of_week: str = "*"  # * or 0-6 (monday=0)

    def get_next_fire_time(self, now: datetime = None) -> Optional[datetime]:
        """Calculate next fire time based on cron expression."""
        now = now or datetime.now()

        # Simple implementation for daily tasks
        next_time = now.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)

        if next_time <= now:
            # Move to next day
            next_time += timedelta(days=1)

        return next_time


@dataclass
class IntervalTrigger(Trigger):
    """Interval-based trigger."""

    trigger_type: TriggerType = TriggerType.INTERVAL
    seconds: int = 60
    start_time: Optional[datetime] = None

    def get_next_fire_time(self, now: datetime = None) -> Optional[datetime]:
        """Get next fire time based on interval."""
        now = now or datetime.now()
        start = self.start_time or now

        # Calculate next fire time
        elapsed = (now - start).total_seconds()
        intervals = int(elapsed / self.seconds) + 1
        return start + timedelta(seconds=intervals * self.seconds)


@dataclass
class OnceTrigger(Trigger):
    """One-time trigger."""

    trigger_type: TriggerType = TriggerType.ONCE
    fire_time: datetime = None
    fired: bool = False

    def get_next_fire_time(self, now: datetime = None) -> Optional[datetime]:
        """Get fire time if not already fired."""
        if self.fired:
            return None
        return self.fire_time


@dataclass
class PriceTrigger(Trigger):
    """Price-based trigger."""

    trigger_type: TriggerType = TriggerType.PRICE
    symbol: str = ""
    target_price: float = 0.0
    condition: str = "above"  # above, below, cross_up, cross_down
    last_price: float = 0.0

    def check(self, current_price: float) -> bool:
        """Check if trigger condition is met."""
        if self.condition == "above":
            return current_price >= self.target_price
        elif self.condition == "below":
            return current_price <= self.target_price
        elif self.condition == "cross_up":
            triggered = self.last_price < self.target_price <= current_price
            self.last_price = current_price
            return triggered
        elif self.condition == "cross_down":
            triggered = self.last_price > self.target_price >= current_price
            self.last_price = current_price
            return triggered
        return False


@dataclass
class NewsTrigger(Trigger):
    """News-based trigger."""

    trigger_type: TriggerType = TriggerType.NEWS
    keywords: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    last_check: Optional[datetime] = None

    def matches(self, title: str, content: str = "") -> bool:
        """Check if news matches trigger."""
        text = f"{title} {content}".lower()
        return any(kw.lower() in text for kw in self.keywords)


# Factory functions
def daily_trigger(hour: int, minute: int = 0) -> CronTrigger:
    """Create a daily trigger."""
    return CronTrigger(hour=hour, minute=minute)


def interval_trigger(seconds: int) -> IntervalTrigger:
    """Create an interval trigger."""
    return IntervalTrigger(seconds=seconds)


def price_alert(symbol: str, target_price: float, condition: str = "above") -> PriceTrigger:
    """Create a price alert trigger."""
    return PriceTrigger(symbol=symbol, target_price=target_price, condition=condition)


def news_monitor(keywords: list[str]) -> NewsTrigger:
    """Create a news monitoring trigger."""
    return NewsTrigger(keywords=keywords)