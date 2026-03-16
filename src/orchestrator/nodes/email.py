"""Email sending task node."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from src.orchestrator.nodes.base import TaskNode, run_node
from src.report.email_sender import ReportEmailSender, EmailConfig


class EmailNode(TaskNode):
    """
    Task node for sending email notifications.

    Input:
        to_addrs: List of recipient email addresses
        subject: Email subject
        report_path: Path to report file to send
        body: Email body text (optional)
        html_body: HTML email body (optional)
        attach_report: Whether to attach the report file

    Output:
        success: Whether email was sent successfully
        recipients: List of recipients
        sent_at: Timestamp when email was sent
    """

    def setup(self) -> None:
        """Initialize email sender."""
        self.sender = ReportEmailSender()

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        """Validate input data."""
        if "to_addrs" not in input_data:
            logger.error("Missing required field: to_addrs")
            return False

        to_addrs = input_data.get("to_addrs", [])
        if not to_addrs or not isinstance(to_addrs, list):
            logger.error("to_addrs must be a non-empty list")
            return False

        return True

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Send email."""
        to_addrs = input_data["to_addrs"]
        subject = input_data.get("subject", "InvestManager Report")
        report_path = input_data.get("report_path")
        body = input_data.get("body", "")
        html_body = input_data.get("html_body")
        attach_report = input_data.get("attach_report", True)

        logger.info(f"Sending email to {len(to_addrs)} recipients")

        # Check if email is configured
        if not self.sender.is_configured:
            logger.warning("Email not configured, skipping send")
            return {
                "success": False,
                "error": "Email not configured",
                "recipients": to_addrs,
            }

        # Prepare attachments
        attachments = []
        if report_path and attach_report:
            report_file = self._resolve_path(report_path)
            if report_file.exists():
                attachments.append(report_file)
                logger.info(f"Will attach: {report_file}")
            else:
                logger.warning(f"Report file not found: {report_file}")

        # Load report content if HTML body not provided
        if not html_body and report_path:
            html_body = self._load_report_content(report_path)

        # Generate default body if not provided
        if not body:
            body = self._generate_default_body(subject, report_path)

        # Send email
        try:
            success = self.sender.send_email(
                to_addrs=to_addrs,
                subject=subject,
                body=body,
                html_body=html_body,
                attachments=attachments if attachments else None,
            )

            if success:
                logger.info(f"Email sent successfully to {', '.join(to_addrs)}")
            else:
                logger.error("Failed to send email")

            return {
                "success": success,
                "recipients": to_addrs,
                "subject": subject,
                "attachments": [str(a) for a in attachments],
                "sent_at": datetime.now().isoformat() if success else None,
            }

        except Exception as e:
            logger.exception(f"Error sending email: {e}")
            return {
                "success": False,
                "error": str(e),
                "recipients": to_addrs,
            }

    def _load_report_content(self, report_path: str) -> Optional[str]:
        """Load report content from file."""
        path = self._resolve_path(report_path)

        if not path.exists():
            return None

        if path.suffix == ".html":
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        elif path.suffix == ".md":
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

        return None

    def _generate_default_body(self, subject: str, report_path: Optional[str]) -> str:
        """Generate default email body."""
        body = f"""
{subject}

Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        if report_path:
            body += f"\nReport file: {Path(report_path).name}\n"

        body += "\n---\nInvestManager Automated Report"
        return body.strip()

    def send_daily_report(
        self,
        to_addrs: list[str],
        report_data: dict,
        report_file: Optional[Path] = None,
    ) -> bool:
        """Send daily market report email."""
        if not self.sender.is_configured:
            logger.warning("Email not configured")
            return False

        return self.sender.send_daily_report(to_addrs, report_data, report_file)

    def send_backtest_report(
        self,
        to_addrs: list[str],
        symbol: str,
        strategy_name: str,
        metrics: dict,
        report_file: Optional[Path] = None,
    ) -> bool:
        """Send backtest report email."""
        if not self.sender.is_configured:
            logger.warning("Email not configured")
            return False

        return self.sender.send_backtest_report(
            to_addrs, symbol, strategy_name, metrics, report_file
        )

    def send_risk_alert(
        self,
        to_addrs: list[str],
        alert_type: str,
        message: str,
        details: Optional[dict] = None,
    ) -> bool:
        """Send risk alert email."""
        if not self.sender.is_configured:
            logger.warning("Email not configured")
            return False

        return self.sender.send_risk_alert(to_addrs, alert_type, message, details)


if __name__ == "__main__":
    run_node(EmailNode)