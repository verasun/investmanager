"""Main Streamlit application."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st

from config.settings import settings

# Page config
st.set_page_config(
    page_title="InvestManager",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Sidebar navigation
st.sidebar.title("InvestManager")
st.sidebar.caption("金融量化分析系统")

page = st.sidebar.radio(
    "导航",
    ["📈 市场概览", "📊 数据分析", "🔄 策略回测", "📋 每日报告", "⚙️ 系统设置"],
)

# Route to pages
if page == "📈 市场概览":
    from web.pages import market_overview

    market_overview.show()

elif page == "📊 数据分析":
    from web.pages import data_analysis

    data_analysis.show()

elif page == "🔄 策略回测":
    from web.pages import backtest

    backtest.show()

elif page == "📋 每日报告":
    from web.pages import daily_report

    daily_report.show()

elif page == "⚙️ 系统设置":
    from web.pages import settings_page

    settings_page.show()

# Footer
st.sidebar.markdown("---")
st.sidebar.caption(f"Version 0.1.0 | {settings.ENVIRONMENT if hasattr(settings, 'ENVIRONMENT') else 'dev'}")