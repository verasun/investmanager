"""Streamlit UI components."""

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def price_chart(
    data: pd.DataFrame,
    title: str = "Price Chart",
    show_volume: bool = True,
) -> go.Figure:
    """
    Create a candlestick chart with volume.

    Args:
        data: DataFrame with OHLCV data
        title: Chart title
        show_volume: Whether to show volume

    Returns:
        Plotly Figure
    """
    if show_volume:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.7, 0.3],
        )
    else:
        fig = go.Figure()

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=data.index,
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            name="OHLC",
        ),
        row=1,
        col=1,
    )

    # Volume
    if show_volume and "volume" in data.columns:
        colors = [
            "green" if data["close"].iloc[i] >= data["open"].iloc[i] else "red"
            for i in range(len(data))
        ]

        fig.add_trace(
            go.Bar(
                x=data.index,
                y=data["volume"],
                marker_color=colors,
                name="Volume",
            ),
            row=2,
            col=1,
        )

    fig.update_layout(
        title=title,
        xaxis_rangeslider_visible=False,
        height=600 if show_volume else 400,
    )

    return fig


def metrics_card(title: str, value: str, delta: str = None, delta_color: str = "normal") -> None:
    """
    Display a metrics card.

    Args:
        title: Metric title
        value: Metric value
        delta: Optional delta value
        delta_color: Delta color (normal, inverse, off)
    """
    st.metric(title, value, delta=delta, delta_color=delta_color)


def data_table(df: pd.DataFrame, title: str = None) -> None:
    """
    Display a styled data table.

    Args:
        df: DataFrame to display
        title: Optional table title
    """
    if title:
        st.subheader(title)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )


def signal_indicator(signal: str) -> None:
    """
    Display a signal indicator.

    Args:
        signal: Signal type (BUY, SELL, HOLD)
    """
    if signal == "BUY":
        st.success("🟢 买入信号")
    elif signal == "SELL":
        st.error("🔴 卖出信号")
    else:
        st.info("⚪ 持有")


def progress_spinner(message: str = "Loading..."):
    """
    Context manager for progress spinner.

    Args:
        message: Spinner message

    Returns:
        Streamlit spinner context
    """
    return st.spinner(message)


def alert_box(message: str, alert_type: str = "info") -> None:
    """
    Display an alert box.

    Args:
        message: Alert message
        alert_type: Type of alert (info, success, warning, error)
    """
    if alert_type == "info":
        st.info(message)
    elif alert_type == "success":
        st.success(message)
    elif alert_type == "warning":
        st.warning(message)
    elif alert_type == "error":
        st.error(message)


def sidebar_nav() -> str:
    """
    Create sidebar navigation.

    Returns:
        Selected page
    """
    st.sidebar.title("InvestManager")
    st.sidebar.caption("金融量化分析系统")

    return st.sidebar.radio(
        "导航",
        ["📈 市场概览", "📊 数据分析", "🔄 策略回测", "📋 每日报告", "⚙️ 系统设置"],
    )