"""Market overview page."""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta


def show():
    """Display market overview page."""
    st.title("📈 市场概览")
    st.markdown("---")

    # Market selector
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        market = st.selectbox(
            "选择市场",
            ["US", "CN", "HK"],
            index=0,
        )

    with col2:
        symbols_input = st.text_input(
            "股票代码 (逗号分隔)",
            "AAPL,MSFT,GOOGL,AMZN,TSLA",
        )

    with col3:
        st.write("")
        st.write("")
        refresh = st.button("🔄 刷新", type="primary")

    # Parse symbols
    symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

    # Fetch market data
    st.subheader("市场数据")

    try:
        import asyncio
        from src.data.sources.yfinance_source import YFinanceSource

        source = YFinanceSource()

        # Create progress bar
        progress_bar = st.progress(0)

        market_data = []
        for i, symbol in enumerate(symbols[:10]):
            try:
                # Fetch latest data
                latest = asyncio.run(source.fetch_latest(symbol))

                if not latest.empty:
                    market_data.append({
                        "代码": symbol,
                        "价格": float(latest.get("close", 0)),
                        "涨跌额": float(latest.get("close", 0) - latest.get("open", 0)),
                        "涨跌幅": f"{float((latest.get('close', 0) - latest.get('open', 0)) / max(latest.get('open', 1), 0.01) * 100):.2f}%",
                        "成交量": f"{int(latest.get('volume', 0)):,}",
                    })
            except Exception as e:
                st.warning(f"无法获取 {symbol} 数据: {e}")

            progress_bar.progress((i + 1) / min(len(symbols), 10))

        progress_bar.empty()

        if market_data:
            df = pd.DataFrame(market_data)

            # Style the dataframe
            def color_returns(val):
                if isinstance(val, str) and val.startswith("-"):
                    return "color: red"
                elif isinstance(val, str) and not val.startswith("代码"):
                    return "color: green"
                return ""

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("暂无市场数据，请检查股票代码是否正确")

    except Exception as e:
        st.error(f"获取市场数据失败: {e}")

    # Market summary
    st.markdown("---")
    st.subheader("市场统计")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("监控股票", f"{len(symbols)}")

    with col2:
        st.metric("市场状态", "交易中" if datetime.now().hour < 16 else "已收盘")

    with col3:
        st.metric("数据源", "Yahoo Finance")

    with col4:
        st.metric("最后更新", datetime.now().strftime("%H:%M:%S"))

    # Quick analysis
    st.markdown("---")
    st.subheader("快速分析")

    selected_symbol = st.selectbox("选择股票进行详细分析", symbols if symbols else ["AAPL"])

    if st.button("开始分析"):
        with st.spinner("正在分析..."):
            try:
                from src.analysis.technical.indicators import TechnicalIndicators

                # Fetch historical data
                end_date = datetime.now()
                start_date = end_date - timedelta(days=60)

                data = asyncio.run(
                    source.fetch_ohlcv(selected_symbol, start_date, end_date)
                )

                if not data.empty:
                    indicators = TechnicalIndicators()

                    # Add indicators
                    data = indicators.add_all_indicators(data)

                    # Display chart
                    st.line_chart(data[["close", "sma_20", "sma_50"]].dropna())

                    # Display key metrics
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        latest_rsi = data["rsi_14"].iloc[-1]
                        st.metric("RSI (14)", f"{latest_rsi:.1f}")

                    with col2:
                        latest_macd = data["macd"].iloc[-1]
                        st.metric("MACD", f"{latest_macd:.2f}")

                    with col3:
                        latest_close = data["close"].iloc[-1]
                        st.metric("最新价格", f"${latest_close:.2f}")

                else:
                    st.warning("无法获取历史数据")

            except Exception as e:
                st.error(f"分析失败: {e}")