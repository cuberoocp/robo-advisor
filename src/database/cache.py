import sqlite3
from datetime import date, timedelta
from typing import Optional
import pandas as pd
from .models import get_conn


def stock_exists(conn: sqlite3.Connection, code: str) -> bool:
    cur = conn.execute("SELECT 1 FROM stock_info WHERE code = ?", (code,))
    return cur.fetchone() is not None


def get_stock_info(conn: sqlite3.Connection, code: str) -> Optional[dict]:
    cur = conn.execute(
        "SELECT code, name, industry, market FROM stock_info WHERE code = ?", (code,)
    )
    row = cur.fetchone()
    if row:
        return {"code": row[0], "name": row[1], "industry": row[2], "market": row[3]}
    return None


def save_stock_info(conn: sqlite3.Connection, code: str, name: str, industry: str, market: str):
    conn.execute(
        """INSERT OR REPLACE INTO stock_info (code, name, industry, market, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'))""",
        (code, name, industry, market),
    )
    conn.commit()


def get_daily_price(conn: sqlite3.Connection, code: str, start_date: str) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT * FROM daily_price WHERE code = ? AND date >= ? ORDER BY date",
        conn, params=(code, start_date),
    )


def get_latest_price_date(conn: sqlite3.Connection, code: str) -> Optional[str]:
    cur = conn.execute(
        "SELECT MAX(date) FROM daily_price WHERE code = ?", (code,)
    )
    row = cur.fetchone()
    return row[0] if row and row[0] else None


def save_daily_price(conn: sqlite3.Connection, df: pd.DataFrame, code: str):
    if df.empty:
        return
    data = df.copy()
    data["code"] = code
    data.to_sql("daily_price", conn, if_exists="append", index=False, method="multi")
    conn.commit()


def has_daily_data(conn: sqlite3.Connection, code: str, date: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM daily_price WHERE code = ? AND date >= ? LIMIT 1",
        (code, date),
    )
    return cur.fetchone() is not None


def get_latest_financial_reports(conn: sqlite3.Connection, code: str, n: int = 8) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT * FROM financial_report WHERE code = ? ORDER BY report_date DESC LIMIT ?",
        conn, params=(code, n),
    )


def save_financial_report(conn: sqlite3.Connection, df: pd.DataFrame, code: str):
    if df.empty:
        return
    conn.execute("DELETE FROM financial_report WHERE code = ?", (code,))
    data = df.copy()
    data["code"] = code
    # Only save columns that exist in the table (for schema compatibility)
    table_cols = {r[1] for r in conn.execute("PRAGMA table_info(financial_report)").fetchall()}
    data_cols = {c.lower() for c in data.columns}
    valid_cols = [c for c in data.columns if c.lower() in table_cols]
    data = data[valid_cols]
    data.to_sql("financial_report", conn, if_exists="append", index=False, method="multi")
    conn.commit()


def has_financial_data(conn: sqlite3.Connection, code: str) -> bool:
    cur = conn.execute(
        "SELECT MAX(report_date) FROM financial_report WHERE code = ?", (code,)
    )
    row = cur.fetchone()
    if row and row[0]:
        from datetime import datetime
        try:
            latest = int(str(row[0])[:4])  # "2025-01-01" -> 2025
            return latest >= datetime.now().year - 1
        except (ValueError, TypeError):
            return False
    return False


def get_valuation_history(conn: sqlite3.Connection, code: str) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT * FROM valuation_daily WHERE code = ? ORDER BY date",
        conn, params=(code,),
    )


def save_valuation_daily(conn: sqlite3.Connection, df: pd.DataFrame, code: str):
    if df.empty:
        return
    data = df.copy()
    data["code"] = code
    data.to_sql("valuation_daily", conn, if_exists="append", index=False, method="multi")
    conn.commit()


def has_valuation_data(conn: sqlite3.Connection, code: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM valuation_daily WHERE code = ? LIMIT 1", (code,)
    )
    return cur.fetchone() is not None


def has_quarterly_data(conn: sqlite3.Connection, code: str) -> bool:
    from datetime import datetime, timedelta
    cur = conn.execute(
        "SELECT MAX(report_date) FROM financial_quarterly WHERE code = ?", (code,)
    )
    row = cur.fetchone()
    if row and row[0]:
        try:
            dt = datetime.strptime(str(row[0])[:7], "%Y-%m")
            return dt >= datetime.now() - timedelta(days=180)
        except (ValueError, TypeError):
            return False
    return False


def get_quarterly_reports(conn: sqlite3.Connection, code: str) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT * FROM financial_quarterly WHERE code = ? ORDER BY report_date DESC",
        conn, params=(code,),
    )


def save_quarterly_reports(conn: sqlite3.Connection, df: pd.DataFrame, code: str):
    if df.empty:
        return
    conn.execute("DELETE FROM financial_quarterly WHERE code = ?", (code,))
    data = df.copy()
    data["code"] = code
    dt_cols = [c for c in data.columns if c != "code"]
    data[dt_cols] = data[dt_cols].astype(object).where(data[dt_cols].notna(), None)
    data.to_sql("financial_quarterly", conn, if_exists="append", index=False, method="multi")
    conn.commit()


def get_industry_comparison(conn: sqlite3.Connection, industry: str) -> pd.DataFrame:  
    return pd.read_sql_query(
        "SELECT * FROM industry_comparison WHERE industry = ? ORDER BY statistic_date",
        conn, params=(industry,),
    )


def save_industry_comparison(conn: sqlite3.Connection, df: pd.DataFrame, industry: str):
    if df.empty:
        return
    data = df.copy()
    data["industry"] = industry
    data.to_sql("industry_comparison", conn, if_exists="append", index=False, method="multi")
    conn.commit()
