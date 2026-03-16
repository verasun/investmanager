"""Backtest page."""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta


def show():
    """Display backtest page."""
    st.title("🔄 策略回测")
    st.markdown("---")

    # Configuration sidebar
    st.sidebar.subheader("回测配置")

    # Strategy selection
    strategy = st.sidebar.selectbox(
        "选择策略",
        [
            "动量策略 (Momentum)",
            "均值回归策略 (Mean Reversion)",
            "趋势跟踪策略 (Trend Following)",
            "MACD策略",
        ],
    )

    # Initial capital
    initial_cash = st.sidebar.number_input(
        "初始资金",
        min_value=10000,
        max_value=10000000,
        value=100000,
        step=10000,
    )

    # Commission
    commission = st.sidebar.slider(
        "手续费率",
        min_value=0.0,
        max_value=0.01,
        value=0.001,
        format="%.3f",
    )

    # Main content
    col1, col2 = st.columns([1, 1])

    with col1:
        symbol = st.text_input("股票代码", "AAPL").upper()

    with col2:
        period = st.selectbox(
            "回测周期",
            ["1年", "2年", "3年", "5年"],
            index=1,
        )

    # Date range
    end_date = datetime.now()
    period_map = {"1年": 365, "2年": 730, "3年": 1095, "5年": 1825}
    start_date = end_date - timedelta(days=period_map[period])

    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("开始日期", start_date.date())
    with col2:
        end = st.date_input("结束日期", end_date.date())

    # Run backtest
    if st.button("开始回测", type="primary"):
        with st.spinner("正在运行回测..."):
            try:
                import asyncio
                from src.data.sources.yfinance_source import YFinanceSource
                from src.backtest.engine import BacktestEngine, BacktestConfig
                from src.strategies.momentum import MomentumStrategy, MACDMomentumStrategy
                from src.strategies.mean_reversion import MeanReversionStrategy
                from src.strategies.trend_following import TrendFollowingStrategy

                # Fetch data
                source = YFinanceSource()
                data = asyncio.run(
                    source.fetch_ohlcv(
                        symbol,
                        datetime.combine(start, datetime.min.time()),
                        datetime.combine(end, datetime.max.time()),
                    )
                )

                if data.empty:
                    st.error("无法获取数据")
                    return

                # Select strategy
                strategy_map = {
                    "动量策略 (Momentum)": MomentumStrategy(),
                    "均值回归策略 (Mean Reversion)": MeanReversionStrategy(),
                    "趋势跟踪策略 (Trend Following)": TrendFollowingStrategy(),
                    "MACD策略": MACDMomentumStrategy(),
                }

                selected_strategy = strategy_map[strategy]

                # Configure backtest
                config = BacktestConfig(
                    initial_cash=initial_cash,
                    commission_rate=commission,
                )
                engine = BacktestEngine(config)

                # Run backtest
                result = engine.run(selected_strategy, data, symbol)

                # Display results
                st.subheader("回测结果")
                st.markdown("---")

                # Key metrics
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric(
                        "总收益率",
                        f"{result.metrics.total_return:.2%}",
                        delta=f"{result.metrics.total_return:.2%}",
                    )

                with col2:
                    st.metric(
                        "年化收益",
                        f"{result.metrics.annualized_return:.2%}",
                    )

                with col3:
                    st.metric(
                        "夏普比率",
                        f"{result.metrics.sharpe_ratio:.2f}",
                    )

                with col4:
                    st.metric(
                        "最大回撤",
                        f"{result.metrics.max_drawdown:.2%}",
                        delta_color="inverse",
                    )

                # More metrics
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("胜率", f"{result.metrics.win_rate:.1%}")

                with col2:
                    st.metric("总交易次数", f"{result.metrics.total_trades}")

                with col3:
                    st.metric("盈利因子", f"{result.metrics.profit_factor:.2f}")

                with col4:
                    st.metric("波动率", f"{result.metrics.volatility:.2%}")

                # Portfolio value chart
                st.subheader("组合价值曲线")
                if not result.portfolio_history.empty:
                    st.line_chart(result.portfolio_history["total_value"])

                # Drawdown chart
                st.subheader("回撤曲线")
                if not result.portfolio_history.empty:
                    values = result.portfolio_history["total_value"]
                    running_max = values.cummax()
                    drawdown = (values - running_max) / running_max * 100
                    st.line_chart(drawdown)

                # Trade history
                st.subheader("交易记录")
                if not result.trade_history.empty:
                    st.dataframe(
                        result.trade_history[
                            ["timestamp", "symbol", "side", "quantity", "price", "commission"]
                        ],
                        use_container_width=True,
                    )
                else:
                    st.info("无交易记录")

                # Download report
                st.subheader("导出报告")
                if st.button("生成报告"):
                    report = engine.generate_report(result)
                    st.download_button(
                        "下载报告 (文本)",
                        report,
                        file_name=f"backtest_{symbol}_{datetime.now().strftime('%Y%m%d')}.txt",
                        mime="text/plain",
                    )

            except Exception as e:
                st.error(f"回测失败: {e}")
                st.exception(e)

    # Strategy comparison
    st.markdown("---")
    st.subheader("策略对比")

    if st.button("对比所有策略"):
        with st.spinner("正在运行对比..."):
            try:
                import asyncio
                from src.data.sources.yfinance_source import YFinanceSource
                from src.backtest.engine import BacktestEngine
                from src.strategies.momentum import MomentumStrategy, MACDMomentumStrategy
                from src.strategies.mean_reversion import MeanReversionStrategy
                from src.strategies.trend_following import TrendFollowingStrategy

                source = YFinanceSource()
                data = asyncio.run(
                    source.fetch_ohlcv(
                        symbol,
                        datetime.combine(start, datetime.min.time()),
                        datetime.combine(end, datetime.max.time()),
                    )
                )

                if data.empty:
                    st.error("无法获取数据")
                    return

                strategies = {
                    "Momentum": MomentumStrategy(),
                    "Mean Reversion": MeanReversionStrategy(),
                    "Trend Following": TrendFollowingStrategy(),
                    "MACD": MACDMomentumStrategy(),
                }

                engine = BacktestEngine()
                results = engine.run_multiple(strategies, data, symbol)

                # Comparison table
                comparison_data = []
                for name, result in results.items():
                    comparison_data.append({
                        "策略": name,
                        "总收益": f"{result.metrics.total_return:.2%}",
                        "年化收益": f"{result.metrics.annualized_return:.2%}",
                        "夏普比率": f"{result.metrics.sharpe_ratio:.2f}",
                        "最大回撤": f"{result.metrics.max_drawdown:.2%}",
                        "胜率": f"{result.metrics.win_rate:.1%}",
                    })

                st.dataframe(pd.DataFrame(comparison_data), use_container_width=True)

            except Exception as e:
                st.error(f"对比失败: {e}")