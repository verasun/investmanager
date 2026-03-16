"""Email sender for reports with attachments."""

import smtplib
import asyncio
from dataclasses import dataclass
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from pathlib import Path
from typing import Optional, Literal

from loguru import logger

from config.settings import settings


@dataclass
class EmailConfig:
    """Email configuration settings."""

    smtp_host: str
    smtp_port: int
    username: str
    password: str
    from_addr: str
    use_tls: bool = True
    auth_method: Literal["password", "oauth2"] = "password"

    @classmethod
    def from_env(cls) -> Optional["EmailConfig"]:
        """
        Create config from environment variables.

        Returns:
            EmailConfig if all required vars are set, None otherwise
        """
        import os

        # Check for OAuth2 configuration first (preferred)
        if settings.email_oauth2_client_id and settings.email_oauth2_refresh_token:
            return cls(
                smtp_host=cls._get_smtp_host_for_provider(settings.email_provider),
                smtp_port=587,
                username=settings.email_from_address,
                password="",  # Not used for OAuth2
                from_addr=settings.email_from_address,
                use_tls=True,
                auth_method="oauth2",
            )

        # Fall back to SMTP password authentication
        smtp_host = os.getenv("EMAIL_SMTP_HOST", settings.email_smtp_host)
        smtp_port = os.getenv("EMAIL_SMTP_PORT", settings.email_smtp_port)
        username = os.getenv("EMAIL_SMTP_USER", settings.email_smtp_user)
        password = os.getenv("EMAIL_SMTP_PASSWORD", settings.email_smtp_password)
        from_addr = os.getenv("EMAIL_FROM_ADDRESS", settings.email_from_address)

        if all([smtp_host, username, password, from_addr]):
            return cls(
                smtp_host=smtp_host,
                smtp_port=int(smtp_port),
                username=username,
                password=password,
                from_addr=from_addr,
                use_tls=True,
                auth_method="password",
            )
        return None

    @staticmethod
    def _get_smtp_host_for_provider(provider: str) -> str:
        """Get SMTP host for known providers."""
        hosts = {
            "gmail": "smtp.gmail.com",
            "outlook": "smtp.office365.com",
            "qq": "smtp.qq.com",
        }
        return hosts.get(provider, settings.email_smtp_host or "smtp.gmail.com")


class ReportEmailSender:
    """
    Send reports via email with attachments.

    Supports HTML email bodies and multiple file attachments.
    """

    def __init__(self, config: Optional[EmailConfig] = None):
        """
        Initialize email sender.

        Args:
            config: Email configuration (if None, will try to load from env)
        """
        self.config = config or EmailConfig.from_env()
        if not self.config:
            logger.warning(
                "Email config not provided and not found in environment. "
                "Email sending will be disabled."
            )

    @property
    def is_configured(self) -> bool:
        """Check if email is properly configured."""
        return self.config is not None

    def send_email(
        self,
        to_addrs: list[str],
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        attachments: Optional[list[Path]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        reply_to: Optional[str] = None,
    ) -> bool:
        """
        Send an email with optional attachments.

        Args:
            to_addrs: Recipient email addresses
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            attachments: List of file paths to attach
            cc: CC recipients
            bcc: BCC recipients
            reply_to: Reply-to address

        Returns:
            True if sent successfully
        """
        if not self.is_configured:
            logger.error("Email not configured, cannot send")
            return False

        try:
            msg = MIMEMultipart("mixed" if attachments else "alternative")
            msg["From"] = self.config.from_addr
            msg["To"] = ", ".join(to_addrs)
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=True)

            if cc:
                msg["Cc"] = ", ".join(cc)

            if reply_to:
                msg["Reply-To"] = reply_to

            # Build the body
            if html_body:
                # Create multipart/alternative for text and HTML
                msg_alternative = MIMEMultipart("alternative")
                msg_alternative.attach(MIMEText(body, "plain", "utf-8"))
                msg_alternative.attach(MIMEText(html_body, "html", "utf-8"))
                msg.attach(msg_alternative)
            else:
                msg.attach(MIMEText(body, "plain", "utf-8"))

            # Add attachments
            if attachments:
                for attachment_path in attachments:
                    if attachment_path.exists():
                        with open(attachment_path, "rb") as f:
                            part = MIMEApplication(f.read(), Name=attachment_path.name)

                        part["Content-Disposition"] = (
                            f'attachment; filename="{attachment_path.name}"'
                        )
                        msg.attach(part)
                    else:
                        logger.warning(f"Attachment not found: {attachment_path}")

            # Combine all recipients
            all_recipients = to_addrs.copy()
            if cc:
                all_recipients.extend(cc)
            if bcc:
                all_recipients.extend(bcc)

            # Send the email
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                if self.config.use_tls:
                    server.starttls()

                server.login(self.config.username, self.config.password)
                server.sendmail(
                    self.config.from_addr,
                    all_recipients,
                    msg.as_string(),
                )

            logger.info(f"Email sent successfully to {', '.join(to_addrs)}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    async def send_email_async(
        self,
        to_addrs: list[str],
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        attachments: Optional[list[Path]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        reply_to: Optional[str] = None,
    ) -> bool:
        """
        Async wrapper for send_email.

        Args:
            to_addrs: Recipient email addresses
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            attachments: List of file paths to attach
            cc: CC recipients
            bcc: BCC recipients
            reply_to: Reply-to address

        Returns:
            True if sent successfully
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.send_email(
                to_addrs=to_addrs,
                subject=subject,
                body=body,
                html_body=html_body,
                attachments=attachments,
                cc=cc,
                bcc=bcc,
                reply_to=reply_to,
            ),
        )

    def send_report(
        self,
        to_addrs: list[str],
        report_title: str,
        report_content: str,
        report_file: Optional[Path] = None,
        report_format: str = "html",
        summary: Optional[str] = None,
    ) -> bool:
        """
        Send a report email.

        Args:
            to_addrs: Recipient email addresses
            report_title: Report title
            report_content: Report content (HTML)
            report_file: Optional report file to attach
            report_format: Format of the report
            summary: Optional summary text

        Returns:
            True if sent successfully
        """
        subject = f"[InvestManager] {report_title} - {datetime.now().strftime('%Y-%m-%d')}"

        # Plain text summary
        body = summary or f"请查看附件中的报告: {report_title}"
        body += f"\n\n报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # HTML body with embedded report
        html_body = self._build_html_email(report_title, report_content, summary)

        attachments = [report_file] if report_file and report_file.exists() else None

        return self.send_email(
            to_addrs=to_addrs,
            subject=subject,
            body=body,
            html_body=html_body,
            attachments=attachments,
        )

    async def send_report_async(
        self,
        to_addrs: list[str],
        report_title: str,
        report_content: str,
        report_file: Optional[Path] = None,
        report_format: str = "html",
        summary: Optional[str] = None,
    ) -> bool:
        """
        Async wrapper for send_report.
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.send_report(
                to_addrs=to_addrs,
                report_title=report_title,
                report_content=report_content,
                report_file=report_file,
                report_format=report_format,
                summary=summary,
            ),
        )

    def send_daily_report(
        self,
        to_addrs: list[str],
        report_data: dict,
        report_file: Optional[Path] = None,
    ) -> bool:
        """
        Send daily market report.

        Args:
            to_addrs: Recipient email addresses
            report_data: Report data dictionary
            report_file: Optional report file attachment

        Returns:
            True if sent successfully
        """
        date = report_data.get("date", datetime.now().strftime("%Y-%m-%d"))
        market_summary = report_data.get("market_summary", [])

        # Build summary
        total_stocks = len(market_summary)
        gainers = len([s for s in market_summary if s.get("change_pct", 0) > 0])
        losers = len([s for s in market_summary if s.get("change_pct", 0) < 0])
        avg_change = (
            sum(s.get("change_pct", 0) for s in market_summary) / total_stocks
            if total_stocks > 0
            else 0
        )

        summary = f"""
每日市场报告 - {date}

监控股票: {total_stocks} 只
上涨股票: {gainers} 只
下跌股票: {losers} 只
平均涨跌: {avg_change:.2f}%

此报告由 InvestManager 自动生成。
        """.strip()

        # Build HTML content
        html_content = self._build_daily_report_html(report_data)

        return self.send_report(
            to_addrs=to_addrs,
            report_title=f"每日市场报告 - {date}",
            report_content=html_content,
            report_file=report_file,
            summary=summary,
        )

    def send_backtest_report(
        self,
        to_addrs: list[str],
        symbol: str,
        strategy_name: str,
        metrics: dict,
        report_file: Optional[Path] = None,
    ) -> bool:
        """
        Send backtest results report.

        Args:
            to_addrs: Recipient email addresses
            symbol: Stock symbol
            strategy_name: Strategy name
            metrics: Performance metrics
            report_file: Optional report file attachment

        Returns:
            True if sent successfully
        """
        summary = f"""
策略回测报告

股票代码: {symbol}
策略名称: {strategy_name}

绩效指标:
- 总收益率: {metrics.get('total_return', 0):.2%}
- 年化收益: {metrics.get('annualized_return', 0):.2%}
- 夏普比率: {metrics.get('sharpe_ratio', 0):.2f}
- 最大回撤: {metrics.get('max_drawdown', 0):.2%}
- 胜率: {metrics.get('win_rate', 0):.1%}
- 总交易次数: {metrics.get('total_trades', 0)}

此报告由 InvestManager 自动生成。
        """.strip()

        html_content = self._build_backtest_report_html(symbol, strategy_name, metrics)

        return self.send_report(
            to_addrs=to_addrs,
            report_title=f"回测报告 - {symbol} ({strategy_name})",
            report_content=html_content,
            report_file=report_file,
            summary=summary,
        )

    def send_risk_alert(
        self,
        to_addrs: list[str],
        alert_type: str,
        message: str,
        details: Optional[dict] = None,
    ) -> bool:
        """
        Send risk alert email.

        Args:
            to_addrs: Recipient email addresses
            alert_type: Type of risk alert
            message: Alert message
            details: Additional details

        Returns:
            True if sent successfully
        """
        subject = f"[风险预警] {alert_type} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        body = f"风险预警: {alert_type}\n\n{message}\n"
        if details:
            body += "\n详细信息:\n"
            for key, value in details.items():
                body += f"  {key}: {value}\n"

        html_body = self._build_alert_html(alert_type, message, details)

        return self.send_email(
            to_addrs=to_addrs,
            subject=subject,
            body=body,
            html_body=html_body,
        )

    def _build_html_email(
        self,
        title: str,
        content: str,
        summary: Optional[str] = None,
    ) -> str:
        """Build HTML email body."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: #ffffff;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            border-bottom: 2px solid #667eea;
            padding-bottom: 15px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            color: #1a1a2e;
            margin: 0;
        }}
        .header .date {{
            color: #666;
            font-size: 14px;
        }}
        .summary {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .content {{
            line-height: 1.6;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 15px;
            border-top: 1px solid #eee;
            font-size: 12px;
            color: #666;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="date">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>
        {f'<div class="summary">{summary}</div>' if summary else ''}
        <div class="content">
            {content}
        </div>
        <div class="footer">
            <p>此报告由 InvestManager 自动生成</p>
            <p>© 2026 InvestManager. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
        """

    def _build_daily_report_html(self, report_data: dict) -> str:
        """Build HTML content for daily report."""
        date = report_data.get("date", "")
        market_summary = report_data.get("market_summary", [])
        top_gainers = report_data.get("top_gainers", [])
        top_losers = report_data.get("top_losers", [])

        # Build table rows
        def build_rows(data):
            rows = ""
            for item in data[:10]:
                change_class = "positive" if item.get("change_pct", 0) >= 0 else "negative"
                rows += f"""
                <tr>
                    <td>{item.get('name', item.get('symbol', 'N/A'))}</td>
                    <td>{item.get('close', 0):.2f}</td>
                    <td class="{change_class}">{item.get('change_pct', 0):+.2f}%</td>
                </tr>
                """
            return rows

        html = f"""
        <style>
            table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            th {{ background-color: #667eea; color: white; padding: 10px; text-align: left; }}
            td {{ padding: 8px; border-bottom: 1px solid #eee; }}
            .positive {{ color: #28a745; }}
            .negative {{ color: #dc3545; }}
            .section-title {{ font-size: 18px; color: #1a1a2e; margin: 20px 0 10px 0; }}
            .stats {{ display: flex; gap: 20px; margin: 15px 0; }}
            .stat-box {{ background: #f8f9fa; padding: 15px; border-radius: 5px; text-align: center; flex: 1; }}
            .stat-value {{ font-size: 24px; font-weight: bold; color: #667eea; }}
            .stat-label {{ font-size: 12px; color: #666; }}
        </style>

        <div class="stats">
            <div class="stat-box">
                <div class="stat-value">{len(market_summary)}</div>
                <div class="stat-label">监控股票</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" style="color: #28a745;">{len([s for s in market_summary if s.get('change_pct', 0) > 0])}</div>
                <div class="stat-label">上涨股票</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" style="color: #dc3545;">{len([s for s in market_summary if s.get('change_pct', 0) < 0])}</div>
                <div class="stat-label">下跌股票</div>
            </div>
        </div>

        <h3 class="section-title">涨幅前5</h3>
        <table>
            <tr><th>代码</th><th>收盘价</th><th>涨跌幅</th></tr>
            {build_rows(top_gainers)}
        </table>

        <h3 class="section-title">跌幅前5</h3>
        <table>
            <tr><th>代码</th><th>收盘价</th><th>涨跌幅</th></tr>
            {build_rows(top_losers)}
        </table>

        <h3 class="section-title">市场概览</h3>
        <table>
            <tr><th>代码</th><th>收盘价</th><th>涨跌幅</th></tr>
            {build_rows(market_summary)}
        </table>
        """

        return html

    def _build_backtest_report_html(
        self,
        symbol: str,
        strategy_name: str,
        metrics: dict,
    ) -> str:
        """Build HTML content for backtest report."""
        html = f"""
        <style>
            .metrics-grid {{
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 15px;
                margin: 20px 0;
            }}
            .metric-card {{
                background: #f8f9fa;
                padding: 15px;
                border-radius: 8px;
                text-align: center;
            }}
            .metric-value {{
                font-size: 24px;
                font-weight: bold;
                color: #667eea;
            }}
            .metric-label {{
                font-size: 12px;
                color: #666;
                margin-top: 5px;
            }}
            .positive {{ color: #28a745 !important; }}
            .negative {{ color: #dc3545 !important; }}
        </style>

        <p><strong>股票代码:</strong> {symbol}</p>
        <p><strong>策略名称:</strong> {strategy_name}</p>

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-value {'positive' if metrics.get('total_return', 0) >= 0 else 'negative'}">
                    {metrics.get('total_return', 0):.2%}
                </div>
                <div class="metric-label">总收益率</div>
            </div>
            <div class="metric-card">
                <div class="metric-value {'positive' if metrics.get('annualized_return', 0) >= 0 else 'negative'}">
                    {metrics.get('annualized_return', 0):.2%}
                </div>
                <div class="metric-label">年化收益</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics.get('sharpe_ratio', 0):.2f}</div>
                <div class="metric-label">夏普比率</div>
            </div>
            <div class="metric-card">
                <div class="metric-value negative">{metrics.get('max_drawdown', 0):.2%}</div>
                <div class="metric-label">最大回撤</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics.get('win_rate', 0):.1%}</div>
                <div class="metric-label">胜率</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics.get('total_trades', 0)}</div>
                <div class="metric-label">总交易次数</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics.get('profit_factor', 0):.2f}</div>
                <div class="metric-label">盈利因子</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics.get('volatility', 0):.2%}</div>
                <div class="metric-label">波动率</div>
            </div>
        </div>
        """

        return html

    def _build_alert_html(
        self,
        alert_type: str,
        message: str,
        details: Optional[dict] = None,
    ) -> str:
        """Build HTML content for risk alert."""
        details_html = ""
        if details:
            details_html = "<ul>"
            for key, value in details.items():
                details_html += f"<li><strong>{key}:</strong> {value}</li>"
            details_html += "</ul>"

        return f"""
        <style>
            .alert-box {{
                background-color: #fff3cd;
                border: 1px solid #ffc107;
                border-radius: 8px;
                padding: 20px;
                margin: 20px 0;
            }}
            .alert-title {{
                color: #856404;
                font-size: 18px;
                font-weight: bold;
                margin-bottom: 10px;
            }}
        </style>

        <div class="alert-box">
            <div class="alert-title">⚠️ {alert_type}</div>
            <p>{message}</p>
            {details_html}
        </div>
        """


# Singleton instance for convenience
_default_sender: Optional[ReportEmailSender] = None


def get_email_sender() -> ReportEmailSender:
    """Get or create the default email sender."""
    global _default_sender
    if _default_sender is None:
        _default_sender = ReportEmailSender()
    return _default_sender


class OAuth2EmailSender(ReportEmailSender):
    """
    Email sender using OAuth2 authentication.

    This is the recommended approach for sending emails
    as it doesn't require storing passwords.
    """

    def __init__(self, config: Optional[EmailConfig] = None):
        """
        Initialize OAuth2 email sender.

        Args:
            config: Email configuration with OAuth2 settings
        """
        super().__init__(config)
        self._oauth2_auth = None
        self._access_token: Optional[str] = None

    async def _get_oauth2_token(self) -> str:
        """Get valid OAuth2 access token."""
        if not self._oauth2_auth:
            from src.email.oauth2_auth import OAuth2Authenticator

            self._oauth2_auth = OAuth2Authenticator(
                provider=settings.email_provider,
                client_id=settings.email_oauth2_client_id,
                client_secret=settings.email_oauth2_client_secret,
            )
            # Set refresh token if available
            if settings.email_oauth2_refresh_token:
                self._oauth2_auth._token = type(
                    "OAuth2Token", (), {"refresh_token": settings.email_oauth2_refresh_token}
                )()

        return await self._oauth2_auth.get_valid_access_token()

    def _generate_xoauth2_auth_string(self, user: str, access_token: str) -> str:
        """Generate XOAUTH2 authentication string."""
        return f"user={user}\x01auth=Bearer {access_token}\x01\x01"

    def send_email(
        self,
        to_addrs: list[str],
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        attachments: Optional[list[Path]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        reply_to: Optional[str] = None,
    ) -> bool:
        """
        Send an email using OAuth2 authentication.

        This overrides the parent method to use XOAUTH2.
        """
        if not self.is_configured:
            logger.error("Email not configured, cannot send")
            return False

        # Get access token synchronously (run async in new event loop)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create new event loop for sync context
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._get_oauth2_token()
                    )
                    access_token = future.result()
            else:
                access_token = loop.run_until_complete(self._get_oauth2_token())
        except Exception as e:
            logger.error(f"Failed to get OAuth2 token: {e}")
            return False

        try:
            msg = MIMEMultipart("mixed" if attachments else "alternative")
            msg["From"] = self.config.from_addr
            msg["To"] = ", ".join(to_addrs)
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=True)

            if cc:
                msg["Cc"] = ", ".join(cc)

            if reply_to:
                msg["Reply-To"] = reply_to

            # Build the body
            if html_body:
                msg_alternative = MIMEMultipart("alternative")
                msg_alternative.attach(MIMEText(body, "plain", "utf-8"))
                msg_alternative.attach(MIMEText(html_body, "html", "utf-8"))
                msg.attach(msg_alternative)
            else:
                msg.attach(MIMEText(body, "plain", "utf-8"))

            # Add attachments
            if attachments:
                for attachment_path in attachments:
                    if attachment_path.exists():
                        with open(attachment_path, "rb") as f:
                            part = MIMEApplication(f.read(), Name=attachment_path.name)

                        part["Content-Disposition"] = (
                            f'attachment; filename="{attachment_path.name}"'
                        )
                        msg.attach(part)
                    else:
                        logger.warning(f"Attachment not found: {attachment_path}")

            # Combine all recipients
            all_recipients = to_addrs.copy()
            if cc:
                all_recipients.extend(cc)
            if bcc:
                all_recipients.extend(bcc)

            # Send the email with OAuth2
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                server.ehlo()
                if self.config.use_tls:
                    server.starttls()
                    server.ehlo()

                # Use XOAUTH2 authentication
                auth_string = self._generate_xoauth2_auth_string(
                    self.config.username,
                    access_token,
                )
                server.docmd("AUTH", "XOAUTH2 " + auth_string)

                server.sendmail(
                    self.config.from_addr,
                    all_recipients,
                    msg.as_string(),
                )

            logger.info(f"Email sent successfully to {', '.join(to_addrs)} (OAuth2)")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"OAuth2 SMTP authentication failed: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


def get_oauth2_email_sender() -> OAuth2EmailSender:
    """Get or create OAuth2 email sender."""
    config = EmailConfig.from_env()
    if config and config.auth_method == "oauth2":
        return OAuth2EmailSender(config)
    # Fall back to password-based sender
    return ReportEmailSender(config)