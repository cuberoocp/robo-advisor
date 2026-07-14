import sqlite3
import pandas as pd
from pathlib import Path


def get_cache_path(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "cache.db"


def get_conn(cache_dir: Path) -> sqlite3.Connection:
    db_path = get_cache_path(cache_dir)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stock_info (
            code TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            market TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS stock_sector (
            code TEXT NOT NULL,
            sector TEXT NOT NULL,
            PRIMARY KEY (code, sector)
        );

        CREATE TABLE IF NOT EXISTS daily_price (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            close REAL,
            high REAL,
            low REAL,
            volume REAL,
            amount REAL,
            PRIMARY KEY (code, date)
        );

        CREATE TABLE IF NOT EXISTS financial_report (
            code TEXT NOT NULL,
            report_date TEXT NOT NULL,
            total_revenue REAL,
            net_profit_deducted REAL,
            basic_eps REAL,
            bvps REAL,
            gross_margin_pct REAL,
            net_margin_pct REAL,
            roe_pct REAL,
            current_ratio REAL,
            quick_ratio REAL,
            debt_ratio_pct REAL,
            PRIMARY KEY (code, report_date)
        );

        CREATE TABLE IF NOT EXISTS valuation_daily (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            pe REAL,
            pb REAL,
            ps REAL,
            market_cap REAL,
            PRIMARY KEY (code, date)
        );

        CREATE TABLE IF NOT EXISTS financial_quarterly (
            code TEXT NOT NULL,
            report_date TEXT NOT NULL,
            total_revenue REAL,
            net_profit REAL,
            operating_cf REAL,
            roe_pct REAL,
            revenue_ps REAL,
            basic_eps REAL,
            cash_flow_ps REAL,
            PRIMARY KEY (code, report_date)
        );

        CREATE TABLE IF NOT EXISTS industry_comparison (
            industry TEXT NOT NULL,
            statistic_date TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            avg_value REAL,
            median_value REAL,
            p25 REAL,
            p75 REAL,
            sample_count INTEGER,
            PRIMARY KEY (industry, statistic_date, metric_name)
        );

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            price REAL,
            valuation_coef REAL,
            price_range_low REAL,
            price_range_high REAL,
            pe REAL,
            pb REAL,
            pe_pct REAL,
            pb_pct REAL,
            sectors TEXT,
            metrics_json TEXT,
            llm_analysis TEXT,
            report_text TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit()
    # Migrate: add new columns if missing
    for col in ("net_profit", "cash_flow_ps", "inventory_turnover_days"):
        try:
            conn.execute(f"ALTER TABLE financial_report ADD COLUMN {col} REAL")
        except Exception:
            pass
    conn.commit()
