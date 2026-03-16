"""Task management page for the web interface."""

import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# API base URL
API_BASE_URL = "http://localhost:8000/api/v1"


def get_tasks(status=None):
    """Fetch tasks from the API."""
    try:
        params = {}
        if status:
            params["status"] = status
        response = requests.get(f"{API_BASE_URL}/tasks", params=params)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to fetch tasks: {response.text}")
            return {"tasks": [], "total": 0, "status_counts": {}}
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to API. Make sure the API server is running.")
        return {"tasks": [], "total": 0, "status_counts": {}}


def get_task(task_id):
    """Fetch a single task from the API."""
    try:
        response = requests.get(f"{API_BASE_URL}/tasks/{task_id}")
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to API.")
        return None


def create_task(task_type, input_data, **kwargs):
    """Create a new task via the API."""
    payload = {
        "type": task_type,
        "input": input_data,
        **kwargs
    }
    try:
        response = requests.post(f"{API_BASE_URL}/tasks", json=payload)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to create task: {response.text}")
            return None
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to API.")
        return None


def cancel_task(task_id):
    """Cancel a task via the API."""
    try:
        response = requests.post(f"{API_BASE_URL}/tasks/{task_id}/cancel")
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        return False


def retry_task(task_id):
    """Retry a failed task via the API."""
    try:
        response = requests.post(f"{API_BASE_URL}/tasks/{task_id}/retry")
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        return False


def create_pipeline(symbols, strategies=None, email_recipients=None):
    """Create a task pipeline via the API."""
    payload = {
        "symbols": symbols,
    }
    if strategies:
        payload["strategies"] = strategies
    if email_recipients:
        payload["email_recipients"] = email_recipients

    try:
        response = requests.post(f"{API_BASE_URL}/tasks/pipeline", json=payload)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to create pipeline: {response.text}")
            return None
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to API.")
        return None


def get_orchestrator_status():
    """Get orchestrator status from the API."""
    try:
        response = requests.get(f"{API_BASE_URL}/tasks/status")
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except requests.exceptions.ConnectionError:
        return None


def main():
    """Main page content."""
    st.set_page_config(
        page_title="Task Management - InvestManager",
        page_icon="⚙️",
        layout="wide",
    )

    st.title("⚙️ Task Management")
    st.markdown("Manage and monitor background tasks for the InvestManager system.")

    # Sidebar
    st.sidebar.header("Actions")

    # Orchestrator status
    status = get_orchestrator_status()
    if status:
        st.sidebar.metric("Orchestrator", "Running" if status.get("running") else "Stopped")
        if status.get("current_task"):
            st.sidebar.info(f"Current: {status['current_task']}")
    else:
        st.sidebar.warning("Orchestrator status unavailable")

    # Quick actions in sidebar
    st.sidebar.subheader("Quick Actions")

    if st.sidebar.button("🔄 Refresh", use_container_width=True):
        st.rerun()

    if st.sidebar.button("🧹 Cleanup Old Tasks", use_container_width=True):
        try:
            response = requests.post(f"{API_BASE_URL}/tasks/cleanup")
            if response.status_code == 200:
                st.sidebar.success(response.json().get("message"))
            else:
                st.sidebar.error("Cleanup failed")
        except:
            st.sidebar.error("Cleanup failed")

    # Main content tabs
    tab1, tab2, tab3 = st.tabs(["📊 Task Queue", "➕ Create Task", "🔗 Pipeline"])

    with tab1:
        # Status filter
        col1, col2 = st.columns([1, 3])
        with col1:
            status_filter = st.selectbox(
                "Filter by status",
                ["all", "pending", "queued", "running", "completed", "failed", "retrying"],
            )

        # Fetch and display tasks
        tasks_data = get_tasks(status_filter if status_filter != "all" else None)
        tasks = tasks_data.get("tasks", [])
        status_counts = tasks_data.get("status_counts", {})

        # Status counts
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Pending", status_counts.get("pending", 0))
        with col2:
            st.metric("Running", status_counts.get("running", 0))
        with col3:
            st.metric("Completed", status_counts.get("completed", 0))
        with col4:
            st.metric("Failed", status_counts.get("failed", 0))
        with col5:
            st.metric("Retrying", status_counts.get("retrying", 0))

        st.divider()

        if tasks:
            # Convert to dataframe for display
            df = pd.DataFrame(tasks)
            df = df[["id", "name", "type", "status", "created_at", "priority"]]
            df.columns = ["ID", "Name", "Type", "Status", "Created", "Priority"]

            # Display tasks
            for idx, task in enumerate(tasks):
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])

                    with col1:
                        status_emoji = {
                            "pending": "⏳",
                            "queued": "📋",
                            "running": "🔄",
                            "completed": "✅",
                            "failed": "❌",
                            "retrying": "🔁",
                            "cancelled": "🚫",
                        }.get(task["status"], "❓")

                        st.markdown(f"**{status_emoji} {task['name']}**")
                        st.caption(f"ID: {task['id']} | Type: {task['type']}")

                    with col2:
                        st.text(task["created_at"][:19] if task.get("created_at") else "N/A")

                    with col3:
                        if task["status"] in ["pending", "queued"]:
                            if st.button("Cancel", key=f"cancel_{task['id']}", type="secondary"):
                                if cancel_task(task["id"]):
                                    st.success("Task cancelled")
                                    st.rerun()
                                else:
                                    st.error("Failed to cancel task")
                        elif task["status"] == "failed":
                            if st.button("Retry", key=f"retry_{task['id']}", type="primary"):
                                if retry_task(task["id"]):
                                    st.success("Task scheduled for retry")
                                    st.rerun()
                                else:
                                    st.error("Failed to retry task")

                    # Show error if failed
                    if task["status"] == "failed" and task.get("error"):
                        st.error(f"Error: {task['error'][:200]}...")

                    st.divider()
        else:
            st.info("No tasks found.")

    with tab2:
        st.subheader("Create New Task")

        task_type = st.selectbox(
            "Task Type",
            ["data_fetch", "analysis", "backtest", "report", "email"],
        )

        # Task-specific input forms
        if task_type == "data_fetch":
            st.subheader("Data Fetch Configuration")
            symbols = st.text_input("Symbols (comma-separated)", "AAPL,MSFT,GOOGL")
            start_date = st.date_input("Start Date")
            end_date = st.date_input("End Date")
            source = st.selectbox("Data Source", ["yfinance", "akshare"])

            if st.button("Create Data Fetch Task", type="primary"):
                result = create_task(
                    "data_fetch",
                    {
                        "symbols": [s.strip().upper() for s in symbols.split(",")],
                        "start_date": str(start_date),
                        "end_date": str(end_date),
                        "source": source,
                    }
                )
                if result:
                    st.success(f"Task created: {result['id']}")

        elif task_type == "analysis":
            st.subheader("Analysis Configuration")
            data_path = st.text_input("Data Path", "data/latest.parquet")
            generate_signals = st.checkbox("Generate Trading Signals", value=True)

            if st.button("Create Analysis Task", type="primary"):
                result = create_task(
                    "analysis",
                    {
                        "data_path": data_path,
                        "generate_signals": generate_signals,
                    }
                )
                if result:
                    st.success(f"Task created: {result['id']}")

        elif task_type == "backtest":
            st.subheader("Backtest Configuration")
            data_path = st.text_input("Data Path", "data/analysis.parquet")
            strategy = st.selectbox("Strategy", ["momentum", "mean_reversion", "trend_following"])
            initial_cash = st.number_input("Initial Cash", value=100000)

            if st.button("Create Backtest Task", type="primary"):
                result = create_task(
                    "backtest",
                    {
                        "data_path": data_path,
                        "strategy": strategy,
                        "config": {"initial_cash": initial_cash},
                    }
                )
                if result:
                    st.success(f"Task created: {result['id']}")

        elif task_type == "report":
            st.subheader("Report Configuration")
            report_type = st.selectbox("Report Type", ["daily", "backtest", "risk", "portfolio"])
            data_path = st.text_input("Data Path", "data/backtest/")
            output_format = st.selectbox("Output Format", ["html", "markdown"])

            if st.button("Create Report Task", type="primary"):
                result = create_task(
                    "report",
                    {
                        "report_type": report_type,
                        "data_path": data_path,
                        "output_format": output_format,
                    }
                )
                if result:
                    st.success(f"Task created: {result['id']}")

        elif task_type == "email":
            st.subheader("Email Configuration")
            to_addrs = st.text_input("Recipients (comma-separated)", "user@example.com")
            subject = st.text_input("Subject", "InvestManager Report")
            report_path = st.text_input("Report Path", "data/report.html")

            if st.button("Create Email Task", type="primary"):
                result = create_task(
                    "email",
                    {
                        "to_addrs": [e.strip() for e in to_addrs.split(",")],
                        "subject": subject,
                        "report_path": report_path,
                    }
                )
                if result:
                    st.success(f"Task created: {result['id']}")

    with tab3:
        st.subheader("Create Analysis Pipeline")

        st.markdown("""
        Create a complete analysis pipeline that:
        1. Fetches market data
        2. Performs technical analysis
        3. Runs backtests (optional)
        4. Generates reports
        5. Sends email notification (optional)
        """)

        col1, col2 = st.columns(2)

        with col1:
            symbols = st.text_input("Stock Symbols (comma-separated)", "AAPL,MSFT,GOOGL")
            strategies = st.multiselect(
                "Strategies to Backtest",
                ["momentum", "mean_reversion", "trend_following"],
            )

        with col2:
            email_enabled = st.checkbox("Send Email Notification")
            if email_enabled:
                email_recipients = st.text_input(
                    "Email Recipients (comma-separated)",
                    "user@example.com"
                )
            else:
                email_recipients = None

        if st.button("Create Pipeline", type="primary"):
            result = create_pipeline(
                symbols=[s.strip().upper() for s in symbols.split(",")],
                strategies=strategies if strategies else None,
                email_recipients=[e.strip() for e in email_recipients.split(",")] if email_recipients else None,
            )
            if result:
                st.success(result.get("message"))
                st.json(result.get("task_ids"))


if __name__ == "__main__":
    main()