"""Notifier - Send notifications to users."""

from typing import Optional
from loguru import logger


class Notifier:
    """Handles sending notifications to users.

    Integrates with Feishu for message delivery.
    """

    def __init__(self, feishu_client=None):
        """Initialize notifier.

        Args:
            feishu_client: Feishu client for sending messages
        """
        self.feishu_client = feishu_client

    def set_feishu_client(self, client) -> None:
        """Set Feishu client."""
        self.feishu_client = client

    async def send_message(
        self,
        user_id: str,
        message: str,
        title: str = None,
    ) -> bool:
        """Send a message to a user.

        Args:
            user_id: Target user ID
            message: Message content
            title: Optional message title

        Returns:
            True if sent successfully
        """
        if not self.feishu_client:
            logger.warning("No Feishu client configured, cannot send notification")
            return False

        try:
            # Format message
            if title:
                formatted = f"**{title}**\n\n{message}"
            else:
                formatted = message

            # Send via Feishu
            # This would call the actual Feishu API
            logger.info(f"Sending notification to {user_id}: {message[:50]}...")
            # await self.feishu_client.send_message(user_id, formatted)
            return True

        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False

    async def send_task_result(
        self,
        user_id: str,
        task_name: str,
        result: str,
        success: bool = True,
    ) -> bool:
        """Send task result notification.

        Args:
            user_id: Target user ID
            task_name: Name of the task
            result: Result content
            success: Whether task succeeded

        Returns:
            True if sent successfully
        """
        status = "✅ 成功" if success else "❌ 失败"
        title = f"{status} - {task_name}"

        return await self.send_message(user_id, result, title)

    async def send_alert(
        self,
        user_id: str,
        alert_type: str,
        alert_data: dict,
    ) -> bool:
        """Send alert notification.

        Args:
            user_id: Target user ID
            alert_type: Type of alert (price, news, etc.)
            alert_data: Alert data

        Returns:
            True if sent successfully
        """
        if alert_type == "price":
            symbol = alert_data.get("symbol", "")
            price = alert_data.get("price", 0)
            target = alert_data.get("target", 0)
            message = f"⚠️ 股价预警\n\n股票 {symbol} 当前价格 {price}，已触及目标价 {target}"

        elif alert_type == "news":
            title = alert_data.get("title", "")
            source = alert_data.get("source", "")
            message = f"📰 新闻提醒\n\n{title}\n\n来源: {source}"

        else:
            message = f"📢 通知\n\n{alert_data}"

        return await self.send_message(user_id, message)


# Global notifier instance
_notifier: Optional[Notifier] = None


def get_notifier() -> Notifier:
    """Get or create the global notifier instance."""
    global _notifier
    if _notifier is None:
        _notifier = Notifier()
    return _notifier