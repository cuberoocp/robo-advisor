import sqlite3
import json
from typing import Optional
import pandas as pd


def save_report(
    conn: sqlite3.Connection,
    code: str,
    stock_name: str,
    price: float,
    valuation_coef: Optional[float],
    price_range_low: Optional[float],
    price_range_high: Optional[float],
    pe: Optional[float],
    pb: Optional[float],
    pe_pct: Optional[float],
    pb_pct: Optional[float],
    sectors: str,
    metrics_json: str,
    llm_analysis: str,
    report_text: str,
):
    conn.execute("DELETE FROM reports WHERE code = ?", (code,))
    conn.execute(
        """INSERT INTO reports
           (code, stock_name, price, valuation_coef, price_range_low, price_range_high,
            pe, pb, pe_pct, pb_pct, sectors, metrics_json, llm_analysis, report_text)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            code, stock_name, price, valuation_coef,
            price_range_low, price_range_high,
            pe, pb, pe_pct, pb_pct,
            sectors, metrics_json, llm_analysis, report_text,
        ),
    )
    conn.commit()


def get_reports(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT id, code, stock_name, price, valuation_coef,
                  price_range_low, price_range_high,
                  pe, pb, pe_pct, pb_pct, sectors,
                  created_at
           FROM reports ORDER BY created_at DESC""",
        conn,
    )


def get_report_by_id(conn: sqlite3.Connection, report_id: int):
    cur = conn.execute(
        """SELECT id, code, stock_name, price, valuation_coef,
                  price_range_low, price_range_high,
                  pe, pb, pe_pct, pb_pct, sectors,
                  metrics_json, llm_analysis, report_text, created_at
           FROM reports WHERE id = ?""",
        (report_id,),
    )
    row = cur.fetchone()
    if row:
        return {
            "id": row[0], "code": row[1], "stock_name": row[2],
            "price": row[3], "valuation_coef": row[4],
            "price_range_low": row[5], "price_range_high": row[6],
            "pe": row[7], "pb": row[8], "pe_pct": row[9], "pb_pct": row[10],
            "sectors": row[11], "metrics_json": row[12],
            "llm_analysis": row[13], "report_text": row[14], "created_at": row[15],
        }
    return None


def delete_report(conn: sqlite3.Connection, report_id: int):
    conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    conn.commit()
