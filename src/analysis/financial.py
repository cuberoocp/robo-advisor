import pandas as pd
import numpy as np


def calc_financial_metrics(fin_df: pd.DataFrame) -> dict:
    if fin_df.empty:
        return {}

    fin = fin_df.dropna(subset=["report_date"]).copy()
    fin["report_date"] = pd.to_datetime(fin["report_date"])
    fin = fin.sort_values("report_date", ascending=False).reset_index(drop=True)

    f_latest = _first_valid(fin, 0)
    f_prev = _first_valid(fin, 1)
    if f_latest is None:
        return {}

    metrics = {}

    def _add(k, v):
        if v is not None:
            metrics[k] = v

    _add("营业总收入(亿)", _r(f_latest.get("total_revenue"), 1e8))
    _add("扣非净利润(亿)", _r(f_latest.get("net_profit_deducted"), 1e8))
    _add("基本每股收益", _r(f_latest.get("basic_eps"), 1))
    _add("每股净资产", _r(f_latest.get("bvps"), 1))
    _add("ROE(%)", _r(f_latest.get("roe_pct"), 1, 1))
    _add("毛利率(%)", _r(f_latest.get("gross_margin_pct"), 1, 1))
    _add("净利率(%)", _r(f_latest.get("net_margin_pct"), 1, 1))
    _add("资产负债率(%)", _r(f_latest.get("debt_ratio_pct"), 1, 1))
    _add("流动比率", _r(f_latest.get("current_ratio"), 1, 2))
    _add("每股经营现金流", _r(f_latest.get("cash_flow_ps"), 1, 2))
    _add("存货周转天数", _r(f_latest.get("inventory_turnover_days"), 1, 0))

    # 净现比 = 每股经营现金流 / 基本每股收益 (衡量利润的现金含量)
    eps_val = _r(f_latest.get("basic_eps"), 1)
    cf_val = _r(f_latest.get("cash_flow_ps"), 1)
    if eps_val and eps_val != 0 and cf_val is not None:
        _add("净现比", round(cf_val / eps_val, 2))

    if f_prev is not None:
        _add("营收同比(%)", _yoy(f_latest.get("total_revenue"), f_prev.get("total_revenue")))
        _add("净利润同比(%)", _yoy(f_latest.get("net_profit_deducted"), f_prev.get("net_profit_deducted")))

    return metrics


def _first_valid(df, idx):
    for i in range(idx, len(df)):
        row = df.iloc[i]
        return row.to_dict()
    return None


def _r(val, divisor=1, decimals=2):
    if val is None or pd.isna(val):
        return None
    return round(float(val) / divisor, decimals)


def _yoy(cur, prev):
    if cur is None or prev is None or pd.isna(cur) or pd.isna(prev) or prev == 0:
        return None
    return round((float(cur) - float(prev)) / float(prev) * 100, 1)

    return metrics


def _calc_ttm_eps(fin_df_q: pd.DataFrame) -> float | None:
    if fin_df_q is None or fin_df_q.empty or "basic_eps" not in fin_df_q.columns:
        return None
    df = fin_df_q.copy()
    df["report_date"] = pd.to_datetime(df["report_date"])
    df = df.sort_values("report_date")
    eps = df["basic_eps"].astype(float).tail(4)
    if len(eps) < 4:
        return None
    return float(eps.sum())


def get_eps_bvps(fin_df: pd.DataFrame, fin_df_q: pd.DataFrame = None):
    eps = _calc_ttm_eps(fin_df_q)
    if eps is None:
        for _, row in fin_df.iterrows():
            v = row.get("basic_eps")
            if pd.notna(v):
                eps = float(v)
                break
    bvps = None
    for _, row in fin_df.iterrows():
        v = row.get("bvps")
        if pd.notna(v):
            bvps = float(v)
            break
    return eps, bvps


def calc_current_pe_pb(close_price: float, fin_df: pd.DataFrame, fin_df_q: pd.DataFrame = None) -> dict:
    if close_price is None or close_price == 0:
        return {}
    result = {}

    eps = _calc_ttm_eps(fin_df_q)
    if eps is None:
        for _, row in fin_df.iterrows():
            if pd.notna(row.get("basic_eps")):
                eps = float(row["basic_eps"])
                break

    bvps = None
    for _, row in fin_df.iterrows():
        if pd.notna(row.get("bvps")):
            bvps = float(row["bvps"])
            break

    if eps and eps != 0:
        result["PE"] = round(close_price / eps, 2)
    if bvps and bvps != 0:
        result["PB"] = round(close_price / bvps, 2)

    return result
