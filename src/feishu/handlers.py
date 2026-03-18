"""Command handlers for Feishu bot."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional

from loguru import logger

from src.feishu.bot import CommandType, ParsedCommand

# Store running tasks for status tracking
_running_tasks: dict[str, dict[str, Any]] = {}


async def handle_collect_data(command: ParsedCommand) -> dict[str, Any]:
    """
    Handle collect data command.

    Args:
        command: Parsed command with symbols

    Returns:
        Result dict
    """
    # Support both 'symbols' (list) and 'symbol' (single string)
    symbols = command.params.get("symbols", [])
    if not symbols:
        single_symbol = command.params.get("symbol")
        if single_symbol:
            symbols = [single_symbol]
    chat_id = command.chat_id

    logger.info(f"Collecting data for symbols: {symbols}")

    # Start background task
    task_id = f"collect_{'_'.join(symbols)}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Store task info
    _running_tasks[task_id] = {
        "status": "running",
        "symbols": symbols,
        "started_at": datetime.now().isoformat(),
        "chat_id": chat_id,
    }

    # Start background collection
    asyncio.create_task(_collect_data_task(task_id, symbols, chat_id))

    return {
        "status": "accepted",
        "message": f"开始收集 {', '.join(symbols)} 的数据，完成后将通知您",
        "task_id": task_id,
    }


async def _collect_data_task(task_id: str, symbols: list[str], chat_id: str) -> None:
    """Background task to collect data and send notification."""
    from src.data.sources.sina_source import SinaFinanceSource
    from src.feishu.client import get_feishu_client

    # Use Sina Finance as primary source (more reliable)
    source = SinaFinanceSource()
    results = {}

    try:
        for symbol in symbols:
            try:
                # Fetch last 30 days of data
                end = datetime.now()
                start = end - timedelta(days=30)

                df = await source.fetch_ohlcv(symbol, start, end)

                if not df.empty:
                    # Get stock info
                    info = await source.get_stock_info(symbol)
                    name = info.get("股票简称", symbol)

                    results[symbol] = {
                        "name": name,
                        "rows": len(df),
                        "latest_close": float(df.iloc[-1]["close"]) if not df.empty else None,
                        "latest_date": df.iloc[-1]["time"].strftime("%Y-%m-%d") if not df.empty else None,
                        "status": "success",
                    }
                    logger.info(f"Collected {len(df)} rows for {symbol} ({name})")
                else:
                    results[symbol] = {"status": "no_data", "error": "未找到数据"}

            except Exception as e:
                logger.error(f"Error collecting data for {symbol}: {e}")
                results[symbol] = {"status": "error", "error": str(e)}

        # Update task status
        _running_tasks[task_id]["status"] = "completed"
        _running_tasks[task_id]["completed_at"] = datetime.now().isoformat()
        _running_tasks[task_id]["results"] = results

        # Send notification
        client = get_feishu_client()
        if client and chat_id:
            # Build notification message
            success_count = sum(1 for r in results.values() if r.get("status") == "success")
            total_count = len(symbols)

            msg_lines = [f"📊 数据收集完成 ({success_count}/{total_count} 成功)\n"]

            for symbol, result in results.items():
                if result.get("status") == "success":
                    msg_lines.append(
                        f"✅ {result.get('name', symbol)} ({symbol}): "
                        f"{result.get('rows', 0)}条数据, "
                        f"最新收盘价: {result.get('latest_close', 'N/A')}"
                    )
                else:
                    msg_lines.append(f"❌ {symbol}: {result.get('error', '未知错误')}")

            await client.send_text_message(chat_id, "chat_id", "\n".join(msg_lines))
            logger.info(f"Sent completion notification for task {task_id}")

    except Exception as e:
        logger.error(f"Error in collect data task: {e}")
        _running_tasks[task_id]["status"] = "failed"
        _running_tasks[task_id]["error"] = str(e)

        # Send error notification
        try:
            client = get_feishu_client()
            if client and chat_id:
                await client.send_text_message(
                    chat_id, "chat_id",
                    f"❌ 数据收集失败: {str(e)}"
                )
        except Exception as notify_error:
            logger.error(f"Failed to send error notification: {notify_error}")


async def handle_analyze(command: ParsedCommand) -> dict[str, Any]:
    """
    Handle analyze command.

    Args:
        command: Parsed command with symbol

    Returns:
        Result dict
    """
    symbol = command.params.get("symbol", "")
    chat_id = command.chat_id

    logger.info(f"Analyzing symbol: {symbol}")

    # Start background task
    task_id = f"analyze_{symbol}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    _running_tasks[task_id] = {
        "status": "running",
        "symbol": symbol,
        "started_at": datetime.now().isoformat(),
        "chat_id": chat_id,
    }

    asyncio.create_task(_analyze_task(task_id, symbol, chat_id))

    return {
        "status": "accepted",
        "message": f"开始分析 {symbol}，完成后将通知您",
        "task_id": task_id,
    }


async def _analyze_task(task_id: str, symbol: str, chat_id: str) -> None:
    """Background task to analyze stock and send notification."""
    from src.data.sources.sina_source import SinaFinanceSource
    from src.feishu.client import get_feishu_client

    # Use Sina Finance as primary source (more reliable)
    source = SinaFinanceSource()

    try:
        # Fetch data
        end = datetime.now()
        start = end - timedelta(days=60)

        df = await source.fetch_ohlcv(symbol, start, end)
        info = await source.get_stock_info(symbol)

        if df.empty:
            raise ValueError(f"未找到 {symbol} 的数据")

        # Simple analysis
        latest = df.iloc[-1]
        name = info.get("股票简称", symbol)

        # Calculate simple metrics
        closes = df["close"]
        ma5 = closes.tail(5).mean()
        ma20 = closes.tail(20).mean()
        change_5d = (closes.iloc[-1] - closes.iloc[-5]) / closes.iloc[-5] * 100 if len(closes) >= 5 else 0

        _running_tasks[task_id]["status"] = "completed"
        _running_tasks[task_id]["completed_at"] = datetime.now().isoformat()

        # Send notification
        client = get_feishu_client()
        if client and chat_id:
            msg = f"""📈 {name} ({symbol}) 分析报告

📊 价格信息:
• 最新价: {latest['close']:.2f}
• 涨跌幅(5日): {change_5d:.2f}%

📈 技术指标:
• MA5: {ma5:.2f}
• MA20: {ma20:.2f}
• 趋势: {"上涨" if ma5 > ma20 else "下跌"}

📋 基本信息:
• 行业: {info.get('行业', 'N/A')}
• 市值: {info.get('总市值', 'N/A')}
• 市盈率: {info.get('市盈率', 'N/A')}"""

            await client.send_text_message(chat_id, "chat_id", msg)
            logger.info(f"Sent analysis notification for {symbol}")

    except Exception as e:
        logger.error(f"Error in analyze task: {e}")
        _running_tasks[task_id]["status"] = "failed"
        _running_tasks[task_id]["error"] = str(e)

        try:
            client = get_feishu_client()
            if client and chat_id:
                await client.send_text_message(
                    chat_id, "chat_id",
                    f"❌ 分析失败: {str(e)}"
                )
        except Exception as notify_error:
            logger.error(f"Failed to send error notification: {notify_error}")


async def handle_backtest(command: ParsedCommand) -> dict[str, Any]:
    """
    Handle backtest command.

    Args:
        command: Parsed command with strategy and symbol

    Returns:
        Result dict
    """
    strategy = command.params.get("strategy", "")
    symbol = command.params.get("symbol", "")
    days = command.params.get("days", 365)  # Default 1 year
    start_date = command.params.get("start_date")
    end_date = command.params.get("end_date")
    chat_id = command.chat_id

    logger.info(f"Running backtest: {strategy} on {symbol} for {days} days")

    # Start background task
    task_id = f"backtest_{strategy}_{symbol}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    _running_tasks[task_id] = {
        "status": "running",
        "strategy": strategy,
        "symbol": symbol,
        "days": days,
        "started_at": datetime.now().isoformat(),
        "chat_id": chat_id,
    }

    asyncio.create_task(_backtest_task(task_id, strategy, symbol, chat_id, days, start_date, end_date))

    return {
        "status": "accepted",
        "message": f"开始回测 {strategy} 策略应用于 {symbol}（{days}天），完成后将通知您",
        "task_id": task_id,
    }


async def _backtest_task(
    task_id: str,
    strategy: str,
    symbol: str,
    chat_id: str,
    days: int = 365,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> None:
    """Background task to run backtest and send notification."""
    from src.data.sources.sina_source import SinaFinanceSource
    from src.feishu.client import get_feishu_client

    source = SinaFinanceSource()

    try:
        # Determine date range
        if start_date and end_date:
            # Use explicit date range
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            # Use days parameter
            end = datetime.now()
            start = end - timedelta(days=days)

        df = await source.fetch_ohlcv(symbol, start, end)

        if df.empty:
            raise ValueError(f"未找到 {symbol} 的数据")

        # Run simple backtest based on strategy
        results = await _run_simple_backtest(df, strategy, symbol)

        # Update task status
        _running_tasks[task_id]["status"] = "completed"
        _running_tasks[task_id]["completed_at"] = datetime.now().isoformat()
        _running_tasks[task_id]["results"] = results

        # Send notification
        client = get_feishu_client()
        if client and chat_id:
            msg = f"""📊 回测完成 - {strategy} 策略

📈 标的: {symbol}
📅 回测区间: {start.strftime('%Y-%m-%d')} 至 {end.strftime('%Y-%m-%d')}
📊 数据点数: {len(df)}

💰 收益统计:
• 总收益率: {results['total_return']:.2f}%
• 年化收益率: {results['annual_return']:.2f}%
• 最大回撤: {results['max_drawdown']:.2f}%

📈 交易统计:
• 交易次数: {results['trades']}
• 胜率: {results['win_rate']:.1f}%"""

            await client.send_text_message(chat_id, "chat_id", msg)
            logger.info(f"Sent backtest notification for {symbol}")

    except Exception as e:
        logger.error(f"Error in backtest task: {e}")
        _running_tasks[task_id]["status"] = "failed"
        _running_tasks[task_id]["error"] = str(e)

        try:
            client = get_feishu_client()
            if client and chat_id:
                await client.send_text_message(
                    chat_id, "chat_id",
                    f"❌ 回测失败: {str(e)}"
                )
        except Exception as notify_error:
            logger.error(f"Failed to send error notification: {notify_error}")


async def _run_simple_backtest(df, strategy: str, symbol: str) -> dict:
    """Run simple backtest strategy."""
    import numpy as np

    closes = df["close"].values
    dates = df["time"].values

    # Default results
    results = {
        "total_return": 0.0,
        "annual_return": 0.0,
        "max_drawdown": 0.0,
        "trades": 0,
        "win_rate": 0.0,
    }

    if len(closes) < 20:
        return results

    # Simple moving average crossover strategy
    if strategy.lower() in ["ma", "macd", "momentum", "均线"]:
        # Calculate MAs
        ma5 = np.convolve(closes, np.ones(5) / 5, mode='valid')
        ma20 = np.convolve(closes, np.ones(20) / 20, mode='valid')

        # Align arrays
        ma5 = ma5[-len(ma20):]
        closes_aligned = closes[-len(ma20):]

        # Generate signals
        position = 0
        entry_price = 0
        trades = []
        returns = []

        for i in range(1, len(ma20)):
            if ma5[i] > ma20[i] and position == 0:
                # Buy signal
                position = 1
                entry_price = closes_aligned[i]
                trades.append({"type": "buy", "price": entry_price})
            elif ma5[i] < ma20[i] and position == 1:
                # Sell signal
                position = 0
                exit_price = closes_aligned[i]
                trade_return = (exit_price - entry_price) / entry_price * 100
                trades.append({"type": "sell", "price": exit_price, "return": trade_return})
                returns.append(trade_return)

        if position == 1:
            # Close position at end
            exit_price = closes_aligned[-1]
            trade_return = (exit_price - entry_price) / entry_price * 100
            returns.append(trade_return)

        # Calculate metrics
        if returns:
            results["trades"] = len(returns)
            results["win_rate"] = sum(1 for r in returns if r > 0) / len(returns) * 100
            results["total_return"] = sum(returns)

            # Annual return (approximate)
            days = (df["time"].iloc[-1] - df["time"].iloc[0]).days
            if days > 0:
                results["annual_return"] = results["total_return"] * 365 / days

        # Calculate max drawdown
        cumulative = np.cumsum(returns) if returns else [0]
        running_max = np.maximum.accumulate(cumulative) if len(cumulative) > 0 else [0]
        drawdowns = cumulative - running_max
        results["max_drawdown"] = abs(np.min(drawdowns)) if len(drawdowns) > 0 else 0

    else:
        # Buy and hold strategy
        total_return = (closes[-1] - closes[0]) / closes[0] * 100
        results["total_return"] = total_return
        results["trades"] = 1
        results["win_rate"] = 100 if total_return > 0 else 0

        days = (df["time"].iloc[-1] - df["time"].iloc[0]).days
        if days > 0:
            results["annual_return"] = total_return * 365 / days

        # Calculate max drawdown for buy and hold
        peak = closes[0]
        max_dd = 0
        for price in closes:
            if price > peak:
                peak = price
            dd = (peak - price) / peak * 100
            if dd > max_dd:
                max_dd = dd
        results["max_drawdown"] = max_dd

    return results


async def handle_generate_report(command: ParsedCommand) -> dict[str, Any]:
    """
    Handle generate report command.

    Args:
        command: Parsed command with report type

    Returns:
        Result dict
    """
    report_type = command.params.get("report_type", "daily")
    logger.info(f"Generating {report_type} report")

    # TODO: Implement actual report generation
    await asyncio.sleep(1)

    return {
        "status": "accepted",
        "message": f"正在生成{report_type}报告...",
        "task_id": f"task_report_{report_type}",
    }


async def handle_send_report(command: ParsedCommand) -> dict[str, Any]:
    """
    Handle send report command.

    Args:
        command: Parsed command with destination

    Returns:
        Result dict
    """
    destination = command.params.get("destination", "")
    logger.info(f"Sending report to: {destination}")

    # TODO: Implement actual report sending
    await asyncio.sleep(1)

    return {
        "status": "accepted",
        "message": f"正在发送报告到 {destination}...",
        "task_id": f"task_send_{destination}",
    }


async def handle_task_status(command: ParsedCommand) -> dict[str, Any]:
    """
    Handle task status command.

    Args:
        command: Parsed command with task ID

    Returns:
        Result dict
    """
    task_id = command.params.get("task_id", "")
    logger.info(f"Checking task status: {task_id}")

    task_info = _running_tasks.get(task_id)

    if task_info:
        return {
            "task_id": task_id,
            "status": task_info.get("status", "unknown"),
            "started_at": task_info.get("started_at"),
            "completed_at": task_info.get("completed_at"),
            "results": task_info.get("results"),
        }
    else:
        return {
            "task_id": task_id,
            "status": "not_found",
            "message": "任务不存在或已过期",
        }


async def handle_comprehensive(command: ParsedCommand) -> dict[str, Any]:
    """
    Handle comprehensive command - execute full analysis pipeline.

    流程: 数据获取 → 技术分析 → 策略回测 → 综合报告

    Args:
        command: Parsed command with symbols

    Returns:
        Result dict
    """
    # Support both 'symbols' (list) and 'symbol' (single string)
    symbols = command.params.get("symbols", [])
    if not symbols:
        single_symbol = command.params.get("symbol")
        if single_symbol:
            symbols = [single_symbol]

    if not symbols:
        return {"status": "error", "message": "请提供股票代码"}

    chat_id = command.chat_id
    symbol = symbols[0]  # Process first symbol

    logger.info(f"Starting comprehensive analysis for: {symbol}")

    # Start background task
    task_id = f"comprehensive_{symbol}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    _running_tasks[task_id] = {
        "status": "running",
        "symbol": symbol,
        "started_at": datetime.now().isoformat(),
        "chat_id": chat_id,
    }

    asyncio.create_task(_comprehensive_task(task_id, symbol, chat_id))

    return {
        "status": "accepted",
        "message": f"开始综合分析 {symbol}，正在获取数据并分析...",
        "task_id": task_id,
    }


async def _comprehensive_task(task_id: str, symbol: str, chat_id: str) -> None:
    """Background task for comprehensive analysis pipeline."""
    from src.data.sources.sina_source import SinaFinanceSource
    from src.feishu.client import get_feishu_client

    source = SinaFinanceSource()
    results = {"symbol": symbol}

    try:
        # =====================
        # Step 1: 数据获取
        # =====================
        end = datetime.now()
        start = end - timedelta(days=365)  # 1 year for backtest
        start_30d = end - timedelta(days=30)  # 30 days for analysis

        # Fetch data
        df_full = await source.fetch_ohlcv(symbol, start, end)
        df_30d = df_full[df_full["time"] >= start_30d] if not df_full.empty else df_full
        info = await source.get_stock_info(symbol)

        if df_full.empty:
            raise ValueError(f"未找到 {symbol} 的数据")

        name = info.get("股票简称", symbol)
        results["name"] = name

        # =====================
        # Step 2: 技术分析
        # =====================
        import numpy as np

        closes = df_30d["close"].values

        # Calculate MAs
        ma5 = np.convolve(closes, np.ones(5) / 5, mode='valid')[-1] if len(closes) >= 5 else closes[-1]
        ma10 = np.convolve(closes, np.ones(10) / 10, mode='valid')[-1] if len(closes) >= 10 else closes[-1]
        ma20 = np.convolve(closes, np.ones(20) / 20, mode='valid')[-1] if len(closes) >= 20 else closes[-1]

        # Calculate RSI
        def calc_rsi(prices, period=14):
            if len(prices) < period + 1:
                return 50
            deltas = np.diff(prices)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains[-period:])
            avg_loss = np.mean(losses[-period:])
            if avg_loss == 0:
                return 100
            rs = avg_gain / avg_loss
            return 100 - (100 / (1 + rs))

        rsi = calc_rsi(closes)

        # Calculate MACD
        ema12 = df_30d["close"].ewm(span=12, adjust=False).mean()
        ema26 = df_30d["close"].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        macd_val = macd.iloc[-1]
        signal_val = signal.iloc[-1]
        macd_signal = "金叉" if macd_val > signal_val else "死叉"

        # Trend
        trend = "上涨" if ma5 > ma20 else "下跌"
        trend_emoji = "📈" if ma5 > ma20 else "📉"

        # Support/Resistance
        recent_high = float(df_30d["high"].max())
        recent_low = float(df_30d["low"].min())

        # Price changes
        latest_price = float(closes[-1])
        prev_close = float(closes[-2]) if len(closes) > 1 else latest_price
        change_pct = (latest_price - prev_close) / prev_close * 100 if prev_close else 0

        results["technical"] = {
            "price": latest_price,
            "change_pct": change_pct,
            "ma5": round(ma5, 2),
            "ma10": round(ma10, 2),
            "ma20": round(ma20, 2),
            "trend": trend,
            "rsi": round(rsi, 1),
            "macd_signal": macd_signal,
            "support": round(recent_low, 2),
            "resistance": round(recent_high, 2),
        }

        # =====================
        # Step 3: 策略回测
        # =====================
        backtest_result = await _run_simple_backtest(df_full, "ma", symbol)
        results["backtest"] = backtest_result

        # =====================
        # Step 4: 生成综合报告
        # =====================
        _running_tasks[task_id]["status"] = "completed"
        _running_tasks[task_id]["completed_at"] = datetime.now().isoformat()
        _running_tasks[task_id]["results"] = results

        # Generate recommendation
        if trend == "上涨" and rsi < 70:
            recommendation = f"短期趋势向上，技术面偏强，建议关注MA20支撑{results['technical']['ma20']}，回调时可考虑介入。"
        elif trend == "下跌" and rsi > 30:
            recommendation = f"短期趋势向下，建议观望，等待企稳信号。关注MA20压力位{results['technical']['ma20']}。"
        else:
            recommendation = f"当前RSI {rsi:.1f}，趋势{trend}，建议谨慎操作。"

        # Build comprehensive report
        report = f"""📊 {name} ({symbol}) 综合分析报告

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 行情概览
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 最新价: {latest_price:.2f} | 涨跌: {change_pct:+.2f}%
• MA5: {ma5:.2f} | MA10: {ma10:.2f} | MA20: {ma20:.2f}
• 趋势: {trend} {trend_emoji}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 技术指标
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• RSI(14): {rsi:.1f} {"(超买)" if rsi > 70 else "(超卖)" if rsi < 30 else "(偏多)" if rsi > 50 else "(偏空)"}
• MACD: {macd_signal}，动能{"增强" if macd_val > 0 else "减弱"}
• 支撑位: {results['technical']['support']:.2f} (近期低点)
• 压力位: {results['technical']['resistance']:.2f} (近期高点)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 策略回测 (均线策略，1年)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 总收益: {backtest_result['total_return']:+.2f}%
• 年化收益: {backtest_result['annual_return']:+.2f}%
• 最大回撤: {backtest_result['max_drawdown']:.2f}%
• 交易次数: {backtest_result['trades']}次 | 胜率: {backtest_result['win_rate']:.1f}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 综合建议
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{recommendation}

⚠️ 风险提示: 以上仅供参考，不构成投资建议。"""

        # Send report
        client = get_feishu_client()
        if client and chat_id:
            await client.send_text_message(chat_id, "chat_id", report)
            logger.info(f"Sent comprehensive report for {symbol}")

    except Exception as e:
        logger.error(f"Error in comprehensive task: {e}")
        _running_tasks[task_id]["status"] = "failed"
        _running_tasks[task_id]["error"] = str(e)

        try:
            client = get_feishu_client()
            if client and chat_id:
                await client.send_text_message(
                    chat_id, "chat_id",
                    f"❌ 综合分析失败: {str(e)}"
                )
        except Exception as notify_error:
            logger.error(f"Failed to send error notification: {notify_error}")


async def handle_mode_switch(command: ParsedCommand) -> dict[str, Any]:
    """
    Handle mode switch command.

    Args:
        command: Parsed command with target mode

    Returns:
        Result dict
    """
    from src.feishu.bot import (
        WorkMode,
        MODE_NAMES,
        get_user_mode,
        set_user_mode,
        cycle_user_mode,
    )

    user_id = command.user_id
    raw_text = command.raw_text.lower()

    # Determine target mode
    if "投资" in raw_text or "invest" in raw_text:
        target_mode = WorkMode.INVEST
        set_user_mode(user_id, target_mode)
    elif "对话" in raw_text or "chat" in raw_text:
        target_mode = WorkMode.CHAT
        set_user_mode(user_id, target_mode)
    elif "严格" in raw_text or "strict" in raw_text:
        target_mode = WorkMode.STRICT
        set_user_mode(user_id, target_mode)
    else:
        # Cycle through modes
        target_mode = cycle_user_mode(user_id)

    mode_name = MODE_NAMES.get(target_mode, target_mode)

    logger.info(f"Switched user {user_id} to mode: {target_mode}")

    return {
        "status": "success",
        "message": f"已切换到「{mode_name}」模式",
        "mode": target_mode,
        "mode_name": mode_name,
    }


async def handle_mode_status(command: ParsedCommand) -> dict[str, Any]:
    """
    Handle mode status query command.

    Args:
        command: Parsed command

    Returns:
        Result dict with current mode info
    """
    from src.feishu.bot import (
        WorkMode,
        MODE_NAMES,
        get_user_mode,
    )

    user_id = command.user_id
    current_mode = get_user_mode(user_id)
    mode_name = MODE_NAMES.get(current_mode, current_mode)

    # Build mode description
    mode_desc = {
        WorkMode.INVEST: "专注股票分析，我会为您提供专业的投资建议",
        WorkMode.CHAT: "自由对话，您可以和我聊任何话题",
        WorkMode.STRICT: "仅响应指令，不支持闲聊",
    }

    return {
        "status": "success",
        "message": f"当前模式：「{mode_name}」\n{mode_desc.get(current_mode, '')}",
        "mode": current_mode,
        "mode_name": mode_name,
    }


async def handle_profile_view(command: ParsedCommand) -> dict[str, Any]:
    """Handle profile view command."""
    from src.memory import get_profile_manager, get_conversation_memory

    user_id = command.user_id

    try:
        profile_manager = get_profile_manager()
        memory = get_conversation_memory()

        profile = await profile_manager.get(user_id)

        # Build profile display
        lines = ["📋 您的用户画像", ""]

        # Communication preferences
        style_names = {"concise": "简洁快速", "balanced": "平衡适中", "detailed": "详细分析"}
        tone_names = {"formal": "正式专业", "friendly": "友好亲切", "casual": "轻松随意"}
        level_names = {"beginner": "入门级", "medium": "进阶级", "expert": "专业级"}

        lines.append(f"💬 沟通偏好:")
        lines.append(f"  • 风格: {style_names.get(profile.communication_style, '平衡适中')}")
        lines.append(f"  • 语气: {tone_names.get(profile.tone_preference, '友好亲切')}")
        lines.append(f"  • 专业程度: {level_names.get(profile.technical_level, '进阶级')}")

        # Investment preferences
        lines.append(f"\n📊 投资偏好:")
        if profile.risk_preference:
            risk_names = {"aggressive": "激进型", "moderate": "稳健型", "conservative": "保守型"}
            lines.append(f"  • 风险偏好: {risk_names.get(profile.risk_preference, profile.risk_preference)}")
        else:
            lines.append(f"  • 风险偏好: 未设置")

        if profile.investment_style:
            style_names = {"value": "价值投资", "growth": "成长投资", "index": "指数投资", "trading": "短线交易"}
            lines.append(f"  • 投资风格: {style_names.get(profile.investment_style, profile.investment_style)}")
        else:
            lines.append(f"  • 投资风格: 未设置")

        # Interests
        if profile.watchlist:
            lines.append(f"\n⭐ 自选股: {', '.join(profile.watchlist[:10])}")

        if profile.preferred_topics:
            lines.append(f"\n📌 关注领域: {', '.join(profile.preferred_topics)}")

        # Stats
        stage_names = {"onboarding": "新用户引导", "learning": "学习阶段", "mature": "成熟阶段"}
        lines.append(f"\n📈 统计信息:")
        lines.append(f"  • 交互次数: {profile.total_interactions}")
        lines.append(f"  • 学习阶段: {stage_names.get(profile.learning_stage, profile.learning_stage)}")

        # Hint for clearing
        lines.append(f"\n💡 提示: 发送「清除记忆」可重置您的偏好设置")

        return {"status": "success", "message": "\n".join(lines)}

    except Exception as e:
        logger.error(f"Failed to get profile: {e}")
        return {"status": "error", "message": f"获取画像失败: {str(e)}"}


async def handle_profile_clear(command: ParsedCommand) -> dict[str, Any]:
    """Handle profile clear command."""
    from src.memory import get_profile_manager, get_conversation_memory, get_learning_manager

    user_id = command.user_id

    try:
        profile_manager = get_profile_manager()
        memory = get_conversation_memory()
        learning_manager = get_learning_manager()

        # Clear all user data
        await profile_manager.clear_profile(user_id)
        await memory.clear_history(user_id)
        await learning_manager.clear_user_tasks(user_id)

        logger.info(f"Cleared all memory for user {user_id}")

        return {
            "status": "success",
            "message": "✅ 已清除您的所有记忆和偏好设置。\n下次对话时，我会重新了解您！"
        }

    except Exception as e:
        logger.error(f"Failed to clear profile: {e}")
        return {"status": "error", "message": f"清除记忆失败: {str(e)}"}


def register_all_handlers(bot) -> None:
    """
    Register all command handlers to the bot.

    Args:
        bot: FeishuBot instance
    """
    bot.register_command_handler(CommandType.COLLECT_DATA, handle_collect_data)
    bot.register_command_handler(CommandType.ANALYZE, handle_analyze)
    bot.register_command_handler(CommandType.BACKTEST, handle_backtest)
    bot.register_command_handler(CommandType.COMPREHENSIVE, handle_comprehensive)
    bot.register_command_handler(CommandType.MODE_SWITCH, handle_mode_switch)
    bot.register_command_handler(CommandType.MODE_STATUS, handle_mode_status)
    bot.register_command_handler(CommandType.GENERATE_REPORT, handle_generate_report)
    bot.register_command_handler(CommandType.SEND_REPORT, handle_send_report)
    bot.register_command_handler(CommandType.TASK_STATUS, handle_task_status)
    bot.register_command_handler(CommandType.PROFILE_VIEW, handle_profile_view)
    bot.register_command_handler(CommandType.PROFILE_CLEAR, handle_profile_clear)

    logger.info("All Feishu command handlers registered")