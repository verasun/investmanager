"""Settings page."""

import streamlit as st
from datetime import datetime


def show():
    """Display settings page."""
    st.title("⚙️ 系统设置")
    st.markdown("---")

    # Application settings
    st.subheader("应用设置")

    col1, col2 = st.columns(2)

    with col1:
        st.text_input("API 基础地址", "http://localhost:8000")
        st.selectbox("日志级别", ["DEBUG", "INFO", "WARNING", "ERROR"], index=1)
        st.checkbox("启用缓存", value=True)

    with col2:
        st.number_input("请求超时 (秒)", min_value=5, max_value=120, value=30)
        st.selectbox("默认市场", ["US", "CN", "HK"], index=0)
        st.checkbox("自动刷新数据", value=False)

    # Data source settings
    st.subheader("数据源设置")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**美股数据**")
        st.selectbox("数据源", ["Yahoo Finance", "Alpha Vantage"], index=0)
        st.text_input("API Key", type="password")

    with col2:
        st.markdown("**A股数据**")
        st.selectbox("数据源", ["Akshare", "Tushare"], index=0)
        st.text_input("Token", type="password")

    # Risk settings
    st.subheader("风控设置")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.number_input(
            "最大持仓比例 (%)",
            min_value=1,
            max_value=100,
            value=10,
        )
        st.number_input(
            "最大回撤预警 (%)",
            min_value=1,
            max_value=50,
            value=10,
        )

    with col2:
        st.number_input(
            "止损比例 (%)",
            min_value=1,
            max_value=50,
            value=5,
        )
        st.number_input(
            "止盈比例 (%)",
            min_value=1,
            max_value=100,
            value=10,
        )

    with col3:
        st.number_input(
            "最大杠杆倍数",
            min_value=1.0,
            max_value=5.0,
            value=1.0,
            step=0.1,
        )
        st.selectbox(
            "仓位计算方式",
            ["固定金额", "固定比例", "风险平价"],
            index=1,
        )

    # Notification settings
    st.subheader("通知设置")

    col1, col2 = st.columns(2)

    with col1:
        st.checkbox("启用邮件通知", value=False)
        st.text_input("SMTP 服务器")
        st.text_input("发件邮箱")
        st.text_input("邮箱密码", type="password")

    with col2:
        st.checkbox("启用 Slack 通知", value=False)
        st.text_input("Webhook URL", type="password")
        st.multiselect(
            "通知类型",
            ["交易信号", "风险预警", "每日报告", "系统错误"],
            default=["风险预警", "系统错误"],
        )

    # Backtest settings
    st.subheader("回测设置")

    col1, col2 = st.columns(2)

    with col1:
        st.number_input(
            "默认初始资金",
            min_value=10000,
            max_value=10000000,
            value=100000,
            step=10000,
        )
        st.slider(
            "默认手续费率 (%)",
            min_value=0.0,
            max_value=1.0,
            value=0.1,
            format="%.2f",
        )

    with col2:
        st.slider(
            "滑点率 (%)",
            min_value=0.0,
            max_value=0.5,
            value=0.05,
            format="%.2f",
        )
        st.checkbox("允许做空", value=False)

    # Save button
    st.markdown("---")

    col1, col2, col3 = st.columns([2, 1, 2])

    with col2:
        if st.button("保存设置", type="primary", use_container_width=True):
            st.success("设置已保存！")

    # System info
    st.markdown("---")
    st.subheader("系统信息")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.info(f"**版本**: 0.1.0")
        st.info(f"**Python**: 3.11+")

    with col2:
        st.info(f"**运行环境**: Development")
        st.info(f"**数据库**: PostgreSQL")

    with col3:
        st.info(f"**缓存**: Redis")
        st.info(f"**当前时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Danger zone
    st.markdown("---")
    st.subheader("危险操作")
    st.warning("以下操作不可撤销，请谨慎使用")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("清除缓存", type="secondary"):
            st.warning("缓存已清除")

    with col2:
        if st.button("重置所有设置", type="secondary"):
            st.error("设置已重置为默认值")