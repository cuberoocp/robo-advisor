import re
import time
from datetime import datetime, timedelta
from typing import Optional

import akshare as ak
import pandas as pd


def _retry(func, max_retries=3, delay=1.5):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(delay * (attempt + 1))


def _parse_num(val) -> Optional[float]:
    if val is None or val is False or val is True:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "").replace(" ", "")
    if not s or s == "--" or s == "nan":
        return None
    multiplier = 1.0
    if "万亿" in s:
        multiplier = 1e12
        s = s.replace("万亿", "")
    elif "亿" in s:
        multiplier = 1e8
        s = s.replace("亿", "")
    elif "万" in s:
        multiplier = 1e4
        s = s.replace("万", "")
    s = s.replace("%", "").replace("--", "")
    try:
        return round(float(s) * multiplier, 4)
    except (ValueError, TypeError):
        return None


CODE_NAME_CACHE = None


def _get_code_name_map() -> pd.DataFrame:
    global CODE_NAME_CACHE
    if CODE_NAME_CACHE is not None:
        return CODE_NAME_CACHE
    CODE_NAME_CACHE = _retry(lambda: ak.stock_info_a_code_name())
    return CODE_NAME_CACHE


def get_stock_info(code: str) -> Optional[dict]:
    try:
        df = _get_code_name_map()
        row = df[df["code"] == code]
        if row.empty:
            return None
        name = row.iloc[0]["name"]
        return {"code": code, "name": name, "industry": "", "market": ""}
    except Exception:
        return None


def get_daily_price(code: str, years: int = 5, start: str = None) -> pd.DataFrame:
    if start:
        start_date = start
    else:
        start_date = (datetime.now() - timedelta(days=years * 365)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")

    prefix = "sh" if code.startswith("6") else "sz"
    symbol = f"{prefix}{code}"

    df = _retry(lambda: ak.stock_zh_a_daily(
        symbol=symbol, start_date=start_date, end_date=end, adjust="qfq"
    ))
    if df.empty:
        return df

    df = df.rename(columns={
        "date": "date", "open": "open", "close": "close",
        "high": "high", "low": "low", "volume": "volume",
        "amount": "amount",
    })
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df[["date", "open", "close", "high", "low", "volume", "amount"]].copy()


_FIN_COLUMNS = {
    "报告期": "report_date",
    "营业收入": "revenue",
    "营业收入同比增长": "revenue_yoy",
    "营业利润": "operating_profit",
    "营业利润同比增长": "operating_profit_yoy",
    "净利润": "net_profit",
    "扣非净利润": "net_profit_deducted",
    "扣非净利润同比增长": "net_profit_deducted_yoy",
    "基本每股收益": "basic_eps",
    "每股净资产": "bvps",
    "每股经营现金流": "cash_flow_ps",
    "存货周转天数": "inventory_turnover_days",
    "销售毛利率": "gross_margin_pct",
    "销售净利率": "net_margin_pct",
    "净资产收益率": "roe_pct",
    "营业总收入": "total_revenue",
    "流动比率": "current_ratio",
    "速动比率": "quick_ratio",
    "资产负债率": "debt_ratio_pct",
}


def get_financial_data(code: str) -> pd.DataFrame:
    df = _retry(lambda: ak.stock_financial_abstract_ths(
        symbol=code, indicator="按年度"
    ))
    if df.empty:
        return df

    available = {k: v for k, v in _FIN_COLUMNS.items() if k in df.columns}
    df = df.rename(columns=available)
    df = df[list(available.values())].copy()

    if "report_date" in df.columns:
        df["report_date"] = pd.to_datetime(
            df["report_date"].astype(str), errors="coerce"
        ).dt.strftime("%Y-%m-%d")

    num_cols = [c for c in df.columns if c != "report_date"]
    for col in num_cols:
        df[col] = df[col].apply(_parse_num)

    return df.sort_values("report_date", ascending=False).reset_index(drop=True)


def get_financial_data_quarterly(code: str, max_quarters: int = 20) -> pd.DataFrame:
    try:
        df = _retry(lambda: ak.stock_financial_abstract(symbol=code))
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    periods = [c for c in df.columns if c not in ("选项", "指标")]
    periods = sorted(periods, reverse=True)[:max_quarters + 8]

    # Indicator names to extract (total values, not per-share)
    raw_ind_map = {
        "营业总收入": "total_revenue",
        "归母净利润": "net_profit",
        "经营现金流量净额": "operating_cf",
        "净资产收益率(ROE)": "roe_pct",
    }

    rows = []
    for _, row in df.iterrows():
        ind = row["指标"]
        col_name = raw_ind_map.get(ind)
        if not col_name:
            continue
        for p in periods:
            val = row.get(p)
            if val is not None and val != "-" and val != "":
                try:
                    rows.append({"report_date": p, "indicator": col_name, "value": float(val)})
                except (ValueError, TypeError):
                    pass

    if not rows:
        return pd.DataFrame()

    raw = pd.DataFrame(rows)
    pivot = raw.pivot_table(index="report_date", columns="indicator", values="value", aggfunc="first").reset_index()
    pivot["report_date"] = pd.to_datetime(pivot["report_date"], format="%Y%m%d")
    pivot = pivot.sort_values("report_date")

    # Derive latest total shares from latest period: total_revenue / 每股营业总收入
    latest_eps_ps = None
    for _, row in df.iterrows():
        if row["指标"] == "每股营业总收入":
            latest_p = sorted(periods, reverse=True)[0]
            val = row.get(latest_p)
            if val is not None and val != "-" and val != "":
                try:
                    latest_eps_ps = float(val)
                except (ValueError, TypeError):
                    pass
            break

    total_shares = None
    if latest_eps_ps and "total_revenue" in pivot.columns and not pivot.empty:
        latest_rev = pivot.iloc[-1]["total_revenue"]
        if latest_rev and latest_rev > 0:
            total_shares = latest_rev / latest_eps_ps

    # Calculate per-share values using latest total shares
    if total_shares and total_shares > 0:
        if "total_revenue" in pivot.columns:
            pivot["revenue_ps"] = pivot["total_revenue"] / total_shares
        if "net_profit" in pivot.columns:
            pivot["basic_eps"] = pivot["net_profit"] / total_shares
        if "operating_cf" in pivot.columns:
            pivot["cash_flow_ps"] = pivot["operating_cf"] / total_shares

    # De-cumulate flow indicators
    flow_cols = [c for c in ["revenue_ps", "basic_eps", "cash_flow_ps"] if c in pivot.columns]
    for col in flow_cols:
        pivot[col] = _decumulate_by_year(pivot, col)

    pivot = pivot.dropna(subset=["roe_pct"] + flow_cols, how="all")
    pivot["report_date"] = pivot["report_date"].dt.strftime("%Y-%m-%d")
    pivot = pivot.sort_values("report_date", ascending=False).reset_index(drop=True)
    return pivot.head(max_quarters)


def _decumulate_by_year(df: pd.DataFrame, col: str) -> pd.Series:
    result = df[col].copy()
    q_map = {3: 0, 6: 1, 9: 2, 12: 3}
    periods_in_year = [3, 6, 9, 12]
    for year, group in df.groupby(df["report_date"].dt.year):
        # Check if all 4 periods exist
        months = sorted(set(group["report_date"].dt.month))
        if len(months) < 4:
            continue
        for i in range(1, 4):
            m = periods_in_year[i]
            prev_m = periods_in_year[i - 1]
            cur = group[group["report_date"].dt.month == m]
            prev = group[group["report_date"].dt.month == prev_m]
            if not cur.empty and not prev.empty:
                idx = cur.index[0]
                result.loc[idx] = cur.iloc[0][col] - prev.iloc[0][col]
    return result


def search_stock(keyword: str) -> list:
    try:
        df = _get_code_name_map()
        mask = df["code"].str.contains(keyword) | df["name"].str.contains(keyword)
        return df[mask].to_dict("records")
    except Exception:
        return []
