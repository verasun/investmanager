-- InvestManager Database Initialization Script
-- Creates tables for market data, analysis results, and backtest records

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Stock metadata table
CREATE TABLE IF NOT EXISTS stocks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(200),
    exchange VARCHAR(20) NOT NULL,  -- 'SH', 'SZ', 'NASDAQ', 'NYSE', etc.
    market VARCHAR(20) NOT NULL,    -- 'A股', 'US', 'HK', etc.
    sector VARCHAR(100),
    industry VARCHAR(100),
    listing_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for stock lookups
CREATE INDEX idx_stocks_symbol ON stocks(symbol);
CREATE INDEX idx_stocks_exchange ON stocks(exchange);
CREATE INDEX idx_stocks_market ON stocks(market);

-- Market data table (timeseries)
CREATE TABLE IF NOT EXISTS market_data (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    open NUMERIC(12, 4),
    high NUMERIC(12, 4),
    low NUMERIC(12, 4),
    close NUMERIC(12, 4),
    volume BIGINT,
    amount NUMERIC(18, 2),
    turnover_rate NUMERIC(8, 4),
    pct_change NUMERIC(8, 4),
    PRIMARY KEY (time, symbol)
);

-- Convert to hypertable for timeseries optimization
SELECT create_hypertable('market_data', 'time', if_not_exists => TRUE);

-- Indexes for market data queries
CREATE INDEX idx_market_data_symbol ON market_data(symbol, time DESC);
CREATE INDEX idx_market_data_time ON market_data(time DESC);

-- Technical indicators cache
CREATE TABLE IF NOT EXISTS technical_indicators (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    indicator_type VARCHAR(50) NOT NULL,
    value NUMERIC(18, 6),
    parameters JSONB DEFAULT '{}',
    PRIMARY KEY (time, symbol, indicator_type)
);

SELECT create_hypertable('technical_indicators', 'time', if_not_exists => TRUE);

-- News and sentiment data
CREATE TABLE IF NOT EXISTS news (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    title VARCHAR(500) NOT NULL,
    content TEXT,
    source VARCHAR(100),
    url VARCHAR(1000),
    publish_time TIMESTAMPTZ,
    sentiment_score NUMERIC(4, 3),  -- -1 to 1
    sentiment_label VARCHAR(20),     -- 'positive', 'negative', 'neutral'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_news_symbol ON news(symbol);
CREATE INDEX idx_news_publish_time ON news(publish_time DESC);
CREATE INDEX idx_news_sentiment ON news(sentiment_label);

-- Trading signals
CREATE TABLE IF NOT EXISTS trading_signals (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    signal_type VARCHAR(50) NOT NULL,
    signal_value VARCHAR(20) NOT NULL,  -- 'buy', 'sell', 'hold'
    confidence NUMERIC(4, 3),
    price_at_signal NUMERIC(12, 4),
    generated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    strategy_name VARCHAR(100),
    parameters JSONB DEFAULT '{}',
    notes TEXT
);

CREATE INDEX idx_signals_symbol ON trading_signals(symbol);
CREATE INDEX idx_signals_time ON trading_signals(generated_at DESC);

-- Backtest results
CREATE TABLE IF NOT EXISTS backtest_runs (
    id SERIAL PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL,
    symbol VARCHAR(20),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital NUMERIC(18, 2),
    final_capital NUMERIC(18, 2),
    total_return NUMERIC(10, 4),
    annual_return NUMERIC(10, 4),
    sharpe_ratio NUMERIC(10, 4),
    max_drawdown NUMERIC(10, 4),
    win_rate NUMERIC(6, 4),
    profit_factor NUMERIC(10, 4),
    total_trades INTEGER,
    parameters JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_backtest_strategy ON backtest_runs(strategy_name);
CREATE INDEX idx_backtest_date ON backtest_runs(created_at DESC);

-- Trade records
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    backtest_run_id INTEGER REFERENCES backtest_runs(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'buy', 'sell'
    quantity INTEGER NOT NULL,
    price NUMERIC(12, 4) NOT NULL,
    commission NUMERIC(12, 4),
    executed_at TIMESTAMPTZ NOT NULL,
    notes TEXT
);

CREATE INDEX idx_trades_backtest ON trades(backtest_run_id);
CREATE INDEX idx_trades_symbol ON trades(symbol);

-- Daily reports
CREATE TABLE IF NOT EXISTS daily_reports (
    id SERIAL PRIMARY KEY,
    report_date DATE NOT NULL UNIQUE,
    report_type VARCHAR(50) DEFAULT 'daily',
    title VARCHAR(200),
    content TEXT,
    summary TEXT,
    market_overview JSONB,
    top_gainers JSONB,
    top_losers JSONB,
    sector_performance JSONB,
    ai_analysis TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reports_date ON daily_reports(report_date DESC);

-- System configuration
CREATE TABLE IF NOT EXISTS system_config (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Task execution log
CREATE TABLE IF NOT EXISTS task_logs (
    id SERIAL PRIMARY KEY,
    task_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- 'running', 'success', 'failed'
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    details JSONB
);

CREATE INDEX idx_task_logs_name ON task_logs(task_name);
CREATE INDEX idx_task_logs_status ON task_logs(status);
CREATE INDEX idx_task_logs_time ON task_logs(started_at DESC);

-- Insert default configuration
INSERT INTO system_config (key, value, description) VALUES
    ('last_data_update', '{"time": null}', 'Last time market data was updated'),
    ('data_sources', '{"a股": "akshare", "us": "yfinance"}', 'Active data sources'),
    ('scheduler_jobs', '{"daily_analysis": true, "data_update": true}', 'Enabled scheduler jobs')
ON CONFLICT (key) DO NOTHING;

-- Create update trigger function
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to relevant tables
CREATE TRIGGER update_stocks_updated_at
    BEFORE UPDATE ON stocks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();