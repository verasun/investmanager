"""Report API routes."""

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from loguru import logger
from pydantic import BaseModel, EmailStr

router = APIRouter()


class DailyReportRequest(BaseModel):
    """Daily report request."""

    symbols: list[str]
    date: Optional[date] = None


class SendEmailRequest(BaseModel):
    """Send email request."""

    to: list[EmailStr]
    subject: str
    body: str
    html_body: Optional[str] = None
    cc: Optional[list[EmailStr]] = None
    bcc: Optional[list[EmailStr]] = None


class SendDailyReportEmailRequest(BaseModel):
    """Send daily report via email request."""

    to: list[EmailStr]
    symbols: list[str]
    date: Optional[date] = None
    cc: Optional[list[EmailStr]] = None
    attach_file: bool = True


class SendBacktestReportEmailRequest(BaseModel):
    """Send backtest report via email request."""

    to: list[EmailStr]
    symbol: str
    strategy: str
    start_date: date
    end_date: date
    initial_cash: float = 100000.0
    cc: Optional[list[EmailStr]] = None


class EmailConfigRequest(BaseModel):
    """Email configuration request."""

    smtp_host: str
    smtp_port: int = 587
    username: str
    password: str
    from_addr: str
    use_tls: bool = True


@router.post("/daily")
async def generate_daily_report(request: DailyReportRequest) -> dict:
    """
    Generate a daily market report.
    """
    try:
        from src.data.sources.yfinance_source import YFinanceSource
        from src.report.generator import ReportGenerator

        source = YFinanceSource()
        generator = ReportGenerator()

        report_date = request.date or date.today()

        # Fetch market data for symbols
        market_summary = []
        top_gainers = []
        top_losers = []

        for symbol in request.symbols[:10]:  # Limit to 10 symbols
            try:
                info = await source.get_stock_info(symbol.upper())
                latest = await source.fetch_latest(symbol.upper())

                market_summary.append({
                    "name": symbol.upper(),
                    "close": float(latest.get("close", 0)),
                    "change": float(latest.get("close", 0) - latest.get("open", 0)),
                    "change_pct": float(
                        (latest.get("close", 0) - latest.get("open", 0))
                        / max(latest.get("open", 1), 0.01) * 100
                    ),
                })
            except Exception:
                continue

        # Sort for gainers/losers
        sorted_by_change = sorted(market_summary, key=lambda x: x["change_pct"], reverse=True)
        top_gainers = sorted_by_change[:5]
        top_losers = sorted_by_change[-5:][::-1]

        # Generate report
        report_data = {
            "date": report_date.isoformat(),
            "market_summary": market_summary,
            "top_gainers": top_gainers,
            "top_losers": top_losers,
        }

        report = generator.generate_daily_report(report_data)

        return {
            "date": report_date.isoformat(),
            "report_html": report,
            "summary": {
                "symbols_analyzed": len(market_summary),
                "top_gainer": top_gainers[0] if top_gainers else None,
                "top_loser": top_losers[0] if top_losers else None,
            },
        }

    except Exception as e:
        logger.error(f"Error generating daily report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio")
async def generate_portfolio_report(
    symbols: str = Query(..., description="Comma-separated symbols"),
) -> dict:
    """
    Generate portfolio analysis report.
    """
    try:
        from src.data.sources.yfinance_source import YFinanceSource
        from src.report.generator import ReportGenerator

        symbol_list = [s.strip().upper() for s in symbols.split(",")]

        source = YFinanceSource()
        generator = ReportGenerator()

        positions = []
        total_value = 0

        for symbol in symbol_list:
            try:
                latest = await source.fetch_latest(symbol)
                price = float(latest.get("close", 0))
                quantity = 100  # Mock quantity

                positions.append({
                    "symbol": symbol,
                    "quantity": quantity,
                    "price": price,
                    "value": price * quantity,
                })
                total_value += price * quantity
            except Exception:
                continue

        # Calculate weights
        for pos in positions:
            pos["weight"] = pos["value"] / total_value if total_value > 0 else 0

        portfolio_data = {
            "positions": positions,
            "total_value": total_value,
        }

        return {
            "portfolio": portfolio_data,
            "generated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating portfolio report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk")
async def generate_risk_report(
    symbols: str = Query(..., description="Comma-separated symbols"),
) -> dict:
    """
    Generate risk analysis report.
    """
    try:
        from src.risk.exposure import ExposureManager, StressTester
        from src.risk.position import PositionManager

        symbol_list = [s.strip().upper() for s in symbols.split(",")]

        # Mock positions and prices
        positions = {s: 100 for s in symbol_list}
        prices = {s: 100.0 for s in symbol_list}  # Mock prices
        cash = 50000.0

        # Calculate exposure
        exposure_manager = ExposureManager()
        exposure = exposure_manager.calculate_exposure(positions, prices, cash)

        # Run stress tests
        stress_tester = StressTester()
        asset_classes = {s: "equity" for s in symbol_list}
        stress_results = stress_tester.run_all_scenarios(positions, prices, asset_classes)

        return {
            "exposure": {
                "total_value": exposure.total_value,
                "gross_exposure": exposure.gross_exposure,
                "net_exposure": exposure.net_exposure,
                "leverage": exposure.leverage,
            },
            "stress_tests": {
                name: {
                    "impact_pct": result["impact_pct"],
                    "total_impact": result["total_impact"],
                }
                for name, result in stress_results.items()
            },
            "generated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating risk report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/{report_type}")
async def export_report(
    report_type: str,
    format: str = Query("html", description="Export format: html, json, csv"),
) -> dict:
    """
    Export a report in specified format.
    """
    try:
        from src.report.export import ReportExporter, ExportFormat

        exporter = ReportExporter()

        # Map format string to enum
        format_map = {
            "html": ExportFormat.HTML,
            "json": ExportFormat.JSON,
            "csv": ExportFormat.CSV,
            "md": ExportFormat.MARKDOWN,
        }

        export_format = format_map.get(format.lower(), ExportFormat.HTML)

        # Generate mock report content
        content = {
            "report_type": report_type,
            "generated_at": datetime.now().isoformat(),
            "data": {},
        }

        # Export
        from datetime import datetime
        filename = f"{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        path = exporter.export(content, filename, export_format)

        return {
            "report_type": report_type,
            "format": format,
            "path": str(path),
            "download_url": f"/api/v1/report/download/{path.name}",
        }

    except Exception as e:
        logger.error(f"Error exporting report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Email Endpoints ==============

@router.post("/email/send")
async def send_email(request: SendEmailRequest) -> dict:
    """
    Send a simple email.

    Requires SMTP configuration via environment variables:
    - SMTP_HOST
    - SMTP_PORT
    - SMTP_USERNAME
    - SMTP_PASSWORD
    - SMTP_FROM_ADDR
    """
    try:
        from src.report.email_sender import get_email_sender

        sender = get_email_sender()

        if not sender.is_configured:
            raise HTTPException(
                status_code=503,
                detail="Email service not configured. Please set SMTP environment variables.",
            )

        success = sender.send_email(
            to_addrs=request.to,
            subject=request.subject,
            body=request.body,
            html_body=request.html_body,
            cc=request.cc,
            bcc=request.bcc,
        )

        if success:
            return {
                "success": True,
                "message": f"Email sent successfully to {', '.join(request.to)}",
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/email/daily")
async def send_daily_report_email(request: SendDailyReportEmailRequest) -> dict:
    """
    Generate and send daily market report via email.

    Fetches market data for specified symbols, generates a report,
    and sends it to the specified email addresses.
    """
    try:
        from src.data.sources.yfinance_source import YFinanceSource
        from src.report.generator import ReportGenerator
        from src.report.export import ReportExporter, ExportFormat
        from src.report.email_sender import get_email_sender

        sender = get_email_sender()

        if not sender.is_configured:
            raise HTTPException(
                status_code=503,
                detail="Email service not configured. Please set SMTP environment variables.",
            )

        source = YFinanceSource()
        generator = ReportGenerator()
        exporter = ReportExporter()

        report_date = request.date or date.today()

        # Fetch market data
        market_summary = []
        for symbol in request.symbols[:20]:
            try:
                latest = await source.fetch_latest(symbol.upper())

                if not latest.empty:
                    close = float(latest.get("close", 0))
                    open_price = float(latest.get("open", close))
                    change = close - open_price
                    change_pct = (change / open_price * 100) if open_price > 0 else 0

                    market_summary.append({
                        "name": symbol.upper(),
                        "symbol": symbol.upper(),
                        "close": close,
                        "change": change,
                        "change_pct": change_pct,
                    })
            except Exception:
                continue

        if not market_summary:
            raise HTTPException(
                status_code=400,
                detail="No market data could be fetched for the specified symbols",
            )

        # Sort for gainers/losers
        sorted_by_change = sorted(
            market_summary, key=lambda x: x["change_pct"], reverse=True
        )
        top_gainers = sorted_by_change[:5]
        top_losers = sorted_by_change[-5:][::-1]

        report_data = {
            "date": report_date.isoformat(),
            "market_summary": market_summary,
            "top_gainers": top_gainers,
            "top_losers": top_losers,
        }

        # Generate report content
        report_html = generator.generate_daily_report(report_data)

        # Optionally export to file
        report_file = None
        if request.attach_file:
            filename = f"daily_report_{report_date.strftime('%Y%m%d')}"
            report_file = exporter.export(
                report_html,
                filename,
                ExportFormat.HTML,
                title=f"每日市场报告 - {report_date}",
            )

        # Send email
        success = sender.send_daily_report(
            to_addrs=request.to,
            report_data=report_data,
            report_file=report_file,
        )

        if success:
            return {
                "success": True,
                "message": f"Daily report sent to {', '.join(request.to)}",
                "report_date": report_date.isoformat(),
                "symbols_analyzed": len(market_summary),
                "report_file": str(report_file) if report_file else None,
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send daily report email")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending daily report email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/email/backtest")
async def send_backtest_report_email(request: SendBacktestReportEmailRequest) -> dict:
    """
    Run backtest and send results via email.

    Executes a backtest for the specified symbol and strategy,
    then sends the results to the specified email addresses.
    """
    try:
        from datetime import datetime as dt
        from src.data.sources.yfinance_source import YFinanceSource
        from src.backtest.engine import BacktestEngine, BacktestConfig
        from src.strategies.momentum import MomentumStrategy, MACDMomentumStrategy
        from src.strategies.mean_reversion import MeanReversionStrategy
        from src.strategies.trend_following import TrendFollowingStrategy
        from src.report.export import ReportExporter, ExportFormat
        from src.report.email_sender import get_email_sender

        sender = get_email_sender()

        if not sender.is_configured:
            raise HTTPException(
                status_code=503,
                detail="Email service not configured. Please set SMTP environment variables.",
            )

        source = YFinanceSource()

        # Fetch historical data
        data = await source.fetch_ohlcv(
            request.symbol.upper(),
            dt.combine(request.start_date, dt.min.time()),
            dt.combine(request.end_date, dt.max.time()),
        )

        if data.empty:
            raise HTTPException(
                status_code=400,
                detail=f"No data available for symbol: {request.symbol}",
            )

        # Select strategy
        strategy_map = {
            "momentum": MomentumStrategy(),
            "macd": MACDMomentumStrategy(),
            "mean_reversion": MeanReversionStrategy(),
            "trend_following": TrendFollowingStrategy(),
        }

        strategy = strategy_map.get(request.strategy.lower())
        if not strategy:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown strategy: {request.strategy}. Available: {list(strategy_map.keys())}",
            )

        # Run backtest
        config = BacktestConfig(initial_cash=request.initial_cash)
        engine = BacktestEngine(config)
        result = engine.run(strategy, data, request.symbol.upper())

        # Export report
        exporter = ReportExporter()
        timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backtest_{request.symbol}_{request.strategy}_{timestamp}"
        report_file = exporter.export(
            engine.generate_report(result),
            filename,
            ExportFormat.HTML,
            title=f"Backtest Report - {request.symbol}",
        )

        # Prepare metrics for email
        metrics = {
            "total_return": result.metrics.total_return,
            "annualized_return": result.metrics.annualized_return,
            "sharpe_ratio": result.metrics.sharpe_ratio,
            "max_drawdown": result.metrics.max_drawdown,
            "win_rate": result.metrics.win_rate,
            "total_trades": result.metrics.total_trades,
            "profit_factor": result.metrics.profit_factor,
            "volatility": result.metrics.volatility,
        }

        # Send email
        success = sender.send_backtest_report(
            to_addrs=request.to,
            symbol=request.symbol.upper(),
            strategy_name=request.strategy,
            metrics=metrics,
            report_file=report_file,
        )

        if success:
            return {
                "success": True,
                "message": f"Backtest report sent to {', '.join(request.to)}",
                "symbol": request.symbol.upper(),
                "strategy": request.strategy,
                "metrics": {
                    "total_return": f"{result.metrics.total_return:.2%}",
                    "sharpe_ratio": f"{result.metrics.sharpe_ratio:.2f}",
                    "max_drawdown": f"{result.metrics.max_drawdown:.2%}",
                    "win_rate": f"{result.metrics.win_rate:.1%}",
                    "total_trades": result.metrics.total_trades,
                },
                "report_file": str(report_file),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send backtest report email")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending backtest report email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/email/configure")
async def configure_email(request: EmailConfigRequest) -> dict:
    """
    Configure email settings for the current session.

    This endpoint allows runtime configuration of SMTP settings.
    For persistent configuration, use environment variables.
    """
    try:
        from src.report.email_sender import EmailConfig, ReportEmailSender

        config = EmailConfig(
            smtp_host=request.smtp_host,
            smtp_port=request.smtp_port,
            username=request.username,
            password=request.password,
            from_addr=request.from_addr,
            use_tls=request.use_tls,
        )

        # Test connection
        sender = ReportEmailSender(config)

        # Try a simple connection test
        import smtplib
        try:
            with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as server:
                if config.use_tls:
                    server.starttls()
                server.login(config.username, config.password)
        except smtplib.SMTPAuthenticationError:
            raise HTTPException(
                status_code=401,
                detail="SMTP authentication failed. Please check your credentials.",
            )
        except smtplib.SMTPException as e:
            raise HTTPException(
                status_code=400,
                detail=f"SMTP connection failed: {str(e)}",
            )

        return {
            "success": True,
            "message": "Email configuration validated successfully",
            "smtp_host": request.smtp_host,
            "smtp_port": request.smtp_port,
            "from_addr": request.from_addr,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error configuring email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/email/status")
async def get_email_status() -> dict:
    """
    Check if email service is configured and available.
    """
    try:
        from src.report.email_sender import get_email_sender

        sender = get_email_sender()

        return {
            "configured": sender.is_configured,
            "message": (
                "Email service is configured and ready"
                if sender.is_configured
                else "Email service not configured. Set SMTP environment variables."
            ),
        }

    except Exception as e:
        logger.error(f"Error checking email status: {e}")
        raise HTTPException(status_code=500, detail=str(e))