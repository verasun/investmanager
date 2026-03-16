"""Daily report page."""

import streamlit as st
import pandas as pd
from datetime import datetime, date


def show():
    """Display daily report page."""
    st.title("📋 每日报告")
    st.markdown("---")

    # Report configuration
    col1, col2 = st.columns([2, 1])

    with col1:
        symbols_input = st.text_area(
            "股票代码 (每行一个)",
            "AAPL\nMSFT\nGOOGL\nAMZN\nTSLA\nNVDA\nMETA\nJPM\nV\nJNJ",
            height=150,
        )

    with col2:
        report_date = st.date_input("报告日期", date.today())
        report_format = st.selectbox("报告格式", ["HTML", "Markdown", "JSON"])

    # Parse symbols
    symbols = [s.strip().upper() for s in symbols_input.split("\n") if s.strip()]

    # Store report data in session state for email sending
    if "report_data" not in st.session_state:
        st.session_state.report_data = None
    if "report_content" not in st.session_state:
        st.session_state.report_content = None

    # Generate report
    if st.button("生成报告", type="primary"):
        with st.spinner("正在生成报告..."):
            try:
                import asyncio
                from src.data.sources.yfinance_source import YFinanceSource
                from src.report.generator import ReportGenerator
                from src.report.export import ReportExporter

                source = YFinanceSource()
                generator = ReportGenerator()
                exporter = ReportExporter()

                # Fetch market data
                market_summary = []
                top_gainers = []
                top_losers = []

                progress_bar = st.progress(0)

                for i, symbol in enumerate(symbols[:20]):
                    try:
                        latest = asyncio.run(source.fetch_latest(symbol))

                        if not latest.empty:
                            close = float(latest.get("close", 0))
                            open_price = float(latest.get("open", close))
                            change = close - open_price
                            change_pct = (change / open_price * 100) if open_price > 0 else 0

                            market_summary.append({
                                "name": symbol,
                                "close": close,
                                "change": change,
                                "change_pct": change_pct,
                            })
                    except Exception:
                        pass

                    progress_bar.progress((i + 1) / min(len(symbols), 20))

                progress_bar.empty()

                # Sort for gainers/losers
                sorted_by_change = sorted(
                    market_summary, key=lambda x: x["change_pct"], reverse=True
                )
                top_gainers = sorted_by_change[:5]
                top_losers = sorted_by_change[-5:][::-1]

                # Generate report
                report_data = {
                    "date": report_date.isoformat(),
                    "market_summary": market_summary,
                    "top_gainers": top_gainers,
                    "top_losers": top_losers,
                }

                output_format = report_format.lower()
                if output_format == "markdown":
                    output_format = "md"

                report = generator.generate_daily_report(
                    report_data, output_format=output_format
                )

                # Store in session state
                st.session_state.report_data = report_data
                st.session_state.report_content = report

                # Display report
                st.subheader(f"每日报告 - {report_date}")

                # Summary metrics
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("监控股票", len(market_summary))

                with col2:
                    gainers_count = len([m for m in market_summary if m["change_pct"] > 0])
                    st.metric("上涨股票", gainers_count)

                with col3:
                    losers_count = len([m for m in market_summary if m["change_pct"] < 0])
                    st.metric("下跌股票", losers_count)

                with col4:
                    avg_change = (
                        sum(m["change_pct"] for m in market_summary) / len(market_summary)
                        if market_summary
                        else 0
                    )
                    st.metric("平均涨跌", f"{avg_change:.2f}%")

                # Market summary table
                st.subheader("市场概览")
                df = pd.DataFrame(market_summary)
                df.columns = ["代码", "收盘价", "涨跌额", "涨跌幅(%)"]
                st.dataframe(df, use_container_width=True, hide_index=True)

                # Top gainers/losers
                col1, col2 = st.columns(2)

                with col1:
                    st.subheader("🟢 涨幅前5")
                    if top_gainers:
                        gainers_df = pd.DataFrame(top_gainers)
                        gainers_df.columns = ["代码", "收盘价", "涨跌额", "涨跌幅(%)"]
                        st.dataframe(gainers_df, use_container_width=True, hide_index=True)
                    else:
                        st.info("暂无数据")

                with col2:
                    st.subheader("🔴 跌幅前5")
                    if top_losers:
                        losers_df = pd.DataFrame(top_losers)
                        losers_df.columns = ["代码", "收盘价", "涨跌额", "涨跌幅(%)"]
                        st.dataframe(losers_df, use_container_width=True, hide_index=True)
                    else:
                        st.info("暂无数据")

                # Download report
                st.subheader("导出报告")

                col1, col2 = st.columns(2)

                with col1:
                    if report_format == "HTML":
                        st.download_button(
                            "下载 HTML 报告",
                            report,
                            file_name=f"daily_report_{report_date}.html",
                            mime="text/html",
                        )
                    else:
                        st.download_button(
                            f"下载 {report_format} 报告",
                            report,
                            file_name=f"daily_report_{report_date}.{output_format}",
                            mime="text/plain",
                        )

                with col2:
                    # Also export as JSON
                    import json
                    json_report = json.dumps(report_data, indent=2, default=str)
                    st.download_button(
                        "下载 JSON 数据",
                        json_report,
                        file_name=f"daily_report_{report_date}.json",
                        mime="application/json",
                    )

            except Exception as e:
                st.error(f"生成报告失败: {e}")

    # Email sending section
    st.markdown("---")
    st.subheader("📧 发送报告到邮箱")

    # Check email configuration
    try:
        from src.report.email_sender import get_email_sender
        sender = get_email_sender()
        email_configured = sender.is_configured
    except Exception:
        email_configured = False

    if not email_configured:
        st.warning("⚠️ 邮件服务未配置。请在设置页面配置SMTP信息，或设置以下环境变量：")
        with st.expander("查看所需环境变量"):
            st.code("""
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_email@example.com
SMTP_PASSWORD=your_password
SMTP_FROM_ADDR=your_email@example.com
            """)
    else:
        st.success("✅ 邮件服务已配置")

    # Email form
    with st.form("email_form"):
        col1, col2 = st.columns(2)

        with col1:
            email_to = st.text_input(
                "收件邮箱",
                placeholder="recipient@example.com",
                help="多个邮箱用逗号分隔",
            )

        with col2:
            email_cc = st.text_input(
                "抄送 (可选)",
                placeholder="cc@example.com",
                help="多个邮箱用逗号分隔",
            )

        email_subject = st.text_input(
            "邮件主题",
            value=f"每日市场报告 - {report_date.strftime('%Y-%m-%d')}",
        )

        attach_file = st.checkbox("附加报告文件", value=True)

        submitted = st.form_submit_button("发送邮件", type="primary", disabled=not email_configured)

        if submitted and email_configured:
            if not email_to:
                st.error("请输入收件邮箱地址")
            elif st.session_state.report_data is None:
                st.error("请先生成报告")
            else:
                with st.spinner("正在发送邮件..."):
                    try:
                        from src.report.email_sender import get_email_sender
                        from src.report.export import ReportExporter, ExportFormat
                        from pathlib import Path

                        sender = get_email_sender()
                        exporter = ReportExporter()

                        # Parse email addresses
                        to_list = [e.strip() for e in email_to.split(",") if e.strip()]
                        cc_list = [e.strip() for e in email_cc.split(",") if e.strip()] if email_cc else None

                        # Optionally export report file
                        report_file = None
                        if attach_file and st.session_state.report_content:
                            filename = f"daily_report_{report_date.strftime('%Y%m%d')}"
                            report_file = exporter.export(
                                st.session_state.report_content,
                                filename,
                                ExportFormat.HTML,
                                title=f"每日市场报告 - {report_date}",
                            )

                        # Send email
                        success = sender.send_daily_report(
                            to_addrs=to_list,
                            report_data=st.session_state.report_data,
                            report_file=report_file,
                        )

                        if success:
                            st.success(f"✅ 报告已成功发送至: {', '.join(to_list)}")
                        else:
                            st.error("❌ 邮件发送失败，请检查SMTP配置")

                    except Exception as e:
                        st.error(f"发送邮件失败: {e}")

    # Quick email test
    if email_configured:
        with st.expander("🔧 测试邮件配置"):
            test_email = st.text_input("测试收件邮箱", key="test_email")
            if st.button("发送测试邮件"):
                if test_email:
                    try:
                        from src.report.email_sender import get_email_sender
                        sender = get_email_sender()

                        success = sender.send_email(
                            to_addrs=[test_email],
                            subject="[InvestManager] 测试邮件",
                            body="这是一封测试邮件，如果您收到此邮件，说明邮件配置正确。",
                            html_body="""
                            <h2>测试邮件</h2>
                            <p>这是一封来自 InvestManager 的测试邮件。</p>
                            <p>如果您收到此邮件，说明邮件配置正确！</p>
                            <hr>
                            <p style="color: #666;">发送时间: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</p>
                            """,
                        )

                        if success:
                            st.success(f"✅ 测试邮件已发送至: {test_email}")
                        else:
                            st.error("❌ 测试邮件发送失败")

                    except Exception as e:
                        st.error(f"发送测试邮件失败: {e}")
                else:
                    st.warning("请输入测试邮箱地址")

    # Report history
    st.markdown("---")
    st.subheader("历史报告")

    try:
        from src.report.export import ReportExporter

        exporter = ReportExporter()
        reports = exporter.list_reports()

        if reports:
            st.dataframe(
                pd.DataFrame(reports),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("暂无历史报告")

    except Exception:
        st.info("暂无历史报告")