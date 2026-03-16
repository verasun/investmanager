"""Data analysis page."""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta


def show():
    """Display data analysis page."""
    st.title("📊 数据分析")
    st.markdown("---")

    # Sidebar options
    st.sidebar.subheader("分析选项")

    analysis_type = st.sidebar.radio(
        "分析类型",
        ["技术分析", "基本面分析", "形态识别"],
    )

    # Main content
    col1, col2 = st.columns([1, 2])

    with col1:
        symbol = st.text_input("股票代码", "AAPL").upper()

        end_date = st.date_input("结束日期", datetime.now())
        start_date = st.date_input("开始日期", datetime.now() - timedelta(days=365))

        period = st.select_slider(
            "分析周期",
            options=["1个月", "3个月", "6个月", "1年", "2年"],
            value="1年",
        )

    with col2:
        st.info("选择股票代码和分析参数后，点击下方按钮开始分析")

    # Analysis execution
    if st.button("开始分析", type="primary"):
        with st.spinner("正在分析..."):
            try:
                import asyncio
                from src.data.sources.yfinance_source import YFinanceSource
                from src.analysis.technical.indicators import TechnicalIndicators

                source = YFinanceSource()

                # Fetch data
                data = asyncio.run(
                    source.fetch_ohlcv(
                        symbol,
                        datetime.combine(start_date, datetime.min.time()),
                        datetime.combine(end_date, datetime.max.time()),
                    )
                )

                if data.empty:
                    st.error("无法获取数据")
                    return

                # Technical Analysis
                if analysis_type == "技术分析":
                    st.subheader(f"{symbol} 技术分析")

                    indicators = TechnicalIndicators()
                    data = indicators.add_all_indicators(data)

                    # Price chart with indicators
                    st.subheader("价格走势")

                    chart_data = data[["close"]].copy()
                    chart_data.columns = ["收盘价"]
                    st.line_chart(chart_data)

                    # Moving averages
                    st.subheader("移动均线")
                    ma_cols = ["close", "sma_20", "sma_50"]
                    available_ma = [c for c in ma_cols if c in data.columns]
                    if available_ma:
                        st.line_chart(data[available_ma])

                    # Indicators
                    col1, col2 = st.columns(2)

                    with col1:
                        st.subheader("RSI")
                        if "rsi_14" in data.columns:
                            st.line_chart(data[["rsi_14"]])

                            # RSI signal
                            latest_rsi = data["rsi_14"].iloc[-1]
                            if latest_rsi > 70:
                                st.warning(f"⚠️ RSI 超买 ({latest_rsi:.1f})")
                            elif latest_rsi < 30:
                                st.success(f"✅ RSI 超卖 ({latest_rsi:.1f})")
                            else:
                                st.info(f"RSI: {latest_rsi:.1f}")

                    with col2:
                        st.subheader("MACD")
                        if "macd" in data.columns:
                            st.line_chart(data[["macd", "macd_signal"]])

                    # Bollinger Bands
                    st.subheader("布林带")
                    if "bb_upper" in data.columns:
                        bb_data = data[["close", "bb_upper", "bb_middle", "bb_lower"]].dropna()
                        st.line_chart(bb_data)

                # Pattern Recognition
                elif analysis_type == "形态识别":
                    st.subheader(f"{symbol} 形态识别")

                    try:
                        from src.analysis.technical.patterns import PatternDetector

                        detector = PatternDetector()
                        patterns = detector.detect_all(data)

                        if patterns:
                            st.write("检测到的形态：")
                            for pattern_name, occurrences in patterns.items():
                                st.write(f"- **{pattern_name}**: {occurrences} 次")
                        else:
                            st.info("未检测到明显形态")
                    except Exception as e:
                        st.warning(f"形态识别功能暂不可用: {e}")

                # Fundamental Analysis placeholder
                else:
                    st.subheader(f"{symbol} 基本面分析")

                    try:
                        info = asyncio.run(source.get_stock_info(symbol))

                        # Display key metrics
                        col1, col2, col3, col4 = st.columns(4)

                        with col1:
                            st.metric(
                                "市值",
                                f"${info.get('marketCap', 0) / 1e9:.1f}B"
                                if info.get("marketCap")
                                else "N/A",
                            )

                        with col2:
                            st.metric(
                                "市盈率",
                                f"{info.get('trailingPE', 0):.1f}"
                                if info.get("trailingPE")
                                else "N/A",
                            )

                        with col3:
                            st.metric(
                                "股息率",
                                f"{info.get('dividendYield', 0) * 100:.2f}%"
                                if info.get("dividendYield")
                                else "N/A",
                            )

                        with col4:
                            st.metric(
                                "52周高点",
                                f"${info.get('fiftyTwoWeekHigh', 0):.2f}"
                                if info.get("fiftyTwoWeekHigh")
                                else "N/A",
                            )

                        # Company info
                        st.subheader("公司简介")
                        st.write(info.get("longBusinessSummary", "暂无信息"))

                    except Exception as e:
                        st.error(f"获取基本面数据失败: {e}")

            except Exception as e:
                st.error(f"分析失败: {e}")