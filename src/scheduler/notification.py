"""Notification service for alerts and reports."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from loguru import logger


class NotificationChannel(Enum):
    """Notification channel types."""

    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    LOG = "log"


@dataclass
class Notification:
    """Notification data structure."""

    title: str
    message: str
    channel: NotificationChannel
    severity: str = "info"  # info, warning, error, critical
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class NotificationProvider(ABC):
    """Abstract base class for notification providers."""

    @abstractmethod
    async def send(self, notification: Notification) -> bool:
        """
        Send a notification.

        Args:
            notification: Notification to send

        Returns:
            True if sent successfully
        """
        pass


class LogNotificationProvider(NotificationProvider):
    """Simple logging notification provider."""

    async def send(self, notification: Notification) -> bool:
        """Log the notification."""
        log_msg = f"[{notification.severity.upper()}] {notification.title}: {notification.message}"

        if notification.severity == "critical":
            logger.error(log_msg)
        elif notification.severity == "error":
            logger.error(log_msg)
        elif notification.severity == "warning":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        return True


class EmailNotificationProvider(NotificationProvider):
    """Email notification provider."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_addr: str,
        to_addrs: list[str],
    ):
        """
        Initialize email provider.

        Args:
            smtp_host: SMTP server host
            smtp_port: SMTP server port
            username: SMTP username
            password: SMTP password
            from_addr: Sender email address
            to_addrs: Recipient email addresses
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs

    async def send(self, notification: Notification) -> bool:
        """Send email notification."""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg["From"] = self.from_addr
            msg["To"] = ", ".join(self.to_addrs)
            msg["Subject"] = f"[{notification.severity.upper()}] {notification.title}"

            body = f"{notification.message}\n\n"
            if notification.metadata:
                body += "Details:\n"
                for key, value in notification.metadata.items():
                    body += f"  {key}: {value}\n"

            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info(f"Email notification sent: {notification.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


class SlackNotificationProvider(NotificationProvider):
    """Slack notification provider."""

    def __init__(self, webhook_url: str):
        """
        Initialize Slack provider.

        Args:
            webhook_url: Slack webhook URL
        """
        self.webhook_url = webhook_url

    async def send(self, notification: Notification) -> bool:
        """Send Slack notification."""
        try:
            import httpx

            # Color based on severity
            colors = {
                "info": "#36a64f",
                "warning": "#ff9800",
                "error": "#f44336",
                "critical": "#9c27b0",
            }

            payload = {
                "attachments": [
                    {
                        "color": colors.get(notification.severity, "#36a64f"),
                        "title": notification.title,
                        "text": notification.message,
                        "fields": [
                            {"title": k, "value": str(v), "short": True}
                            for k, v in (notification.metadata or {}).items()
                        ],
                        "footer": "InvestManager",
                        "ts": int(__import__("time").time()),
                    }
                ]
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                )

            if response.status_code == 200:
                logger.info(f"Slack notification sent: {notification.title}")
                return True
            else:
                logger.error(f"Slack notification failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False


class WebhookNotificationProvider(NotificationProvider):
    """Generic webhook notification provider."""

    def __init__(self, webhook_url: str, headers: Optional[dict] = None):
        """
        Initialize webhook provider.

        Args:
            webhook_url: Webhook URL
            headers: Optional headers
        """
        self.webhook_url = webhook_url
        self.headers = headers or {}

    async def send(self, notification: Notification) -> bool:
        """Send webhook notification."""
        try:
            import httpx

            payload = {
                "title": notification.title,
                "message": notification.message,
                "severity": notification.severity,
                "metadata": notification.metadata,
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers=self.headers,
                )

            if response.status_code in (200, 201, 202):
                logger.info(f"Webhook notification sent: {notification.title}")
                return True
            else:
                logger.error(f"Webhook notification failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")
            return False


class NotificationService:
    """
    Unified notification service.

    Manages multiple notification providers and routes notifications.
    """

    def __init__(self):
        """Initialize notification service."""
        self.providers: dict[NotificationChannel, NotificationProvider] = {
            NotificationChannel.LOG: LogNotificationProvider(),
        }
        self._enabled = True

    def add_provider(
        self,
        channel: NotificationChannel,
        provider: NotificationProvider,
    ) -> None:
        """Add a notification provider."""
        self.providers[channel] = provider
        logger.info(f"Added notification provider: {channel.value}")

    def remove_provider(self, channel: NotificationChannel) -> bool:
        """Remove a notification provider."""
        if channel in self.providers and channel != NotificationChannel.LOG:
            del self.providers[channel]
            return True
        return False

    def enable(self) -> None:
        """Enable notifications."""
        self._enabled = True

    def disable(self) -> None:
        """Disable notifications."""
        self._enabled = False

    async def notify(
        self,
        notification: Notification,
        channels: Optional[list[NotificationChannel]] = None,
    ) -> dict[NotificationChannel, bool]:
        """
        Send notification through specified channels.

        Args:
            notification: Notification to send
            channels: Channels to use (default: all configured)

        Returns:
            Dictionary of channel -> success status
        """
        if not self._enabled:
            return {}

        if channels is None:
            channels = list(self.providers.keys())

        results = {}

        for channel in channels:
            provider = self.providers.get(channel)
            if provider:
                try:
                    success = await provider.send(notification)
                    results[channel] = success
                except Exception as e:
                    logger.error(f"Notification error ({channel.value}): {e}")
                    results[channel] = False

        return results

    async def send_alert(
        self,
        title: str,
        message: str,
        severity: str = "warning",
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Send an alert notification.

        Args:
            title: Alert title
            message: Alert message
            severity: Alert severity
            metadata: Additional metadata

        Returns:
            True if sent successfully to any channel
        """
        notification = Notification(
            title=title,
            message=message,
            channel=NotificationChannel.LOG,
            severity=severity,
            metadata=metadata,
        )

        results = await self.notify(notification)
        return any(results.values())

    async def send_report(
        self,
        title: str,
        summary: str,
        details: Optional[dict] = None,
    ) -> bool:
        """
        Send a report notification.

        Args:
            title: Report title
            summary: Report summary
            details: Report details

        Returns:
            True if sent successfully
        """
        return await self.send_alert(
            title=title,
            message=summary,
            severity="info",
            metadata=details,
        )

    async def send_risk_alert(
        self,
        alert_type: str,
        message: str,
        current_value: float,
        threshold: float,
    ) -> bool:
        """
        Send a risk alert.

        Args:
            alert_type: Type of risk alert
            message: Alert message
            current_value: Current metric value
            threshold: Threshold that was breached

        Returns:
            True if sent successfully
        """
        return await self.send_alert(
            title=f"Risk Alert: {alert_type}",
            message=message,
            severity="warning",
            metadata={
                "current_value": current_value,
                "threshold": threshold,
                "alert_type": alert_type,
            },
        )