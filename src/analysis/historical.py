import pandas as pd
import numpy as np


def calc_percentile(value: float, series: pd.Series) -> dict:
    series = series.dropna()
    if len(series) < 10 or value is None:
        return {}

    pct = (series < value).mean() * 100

    return {
        "当前值": round(value, 2),
        "历史均值": round(series.mean(), 2),
        "历史中位数": round(series.median(), 2),
        "历史最低": round(series.min(), 2),
        "历史最高": round(series.max(), 2),
        "当前百分位(%)": round(pct, 1),
        "数据样本数": len(series),
        "_p30": round(series.quantile(0.3), 2),
        "_p70": round(series.quantile(0.7), 2),
    }


def calc_growth_trend(fin_df: pd.DataFrame) -> dict:
    if fin_df.empty:
        return {}

    df = fin_df.copy()
    if "report_date" in df.columns:
        df["report_date"] = pd.to_datetime(df["report_date"])
        df = df.sort_values("report_date")
    else:
        return {}

    result = {}

    rev_col = None
    for c in ["total_revenue", "营业总收入(亿)", "revenue"]:
        if c in df.columns:
            rev_col = c
            break

    eps_col = None
    for c in ["basic_eps", "基本每股收益"]:
        if c in df.columns:
            eps_col = c
            break

    # Year-over-year growth (latest vs prior year)
    if rev_col and len(df) >= 2:
        latest = df.iloc[-1].get(rev_col)
        prev = df.iloc[-2].get(rev_col)
        if latest and prev and prev != 0:
            result["营收同比增速(%)"] = round((latest - prev) / abs(prev) * 100, 1)

        # 3-year CAGR
        if len(df) >= 4:
            p3 = df.iloc[-4].get(rev_col)
            if latest and p3 and p3 > 0:
                cagr = ((latest / p3) ** (1 / 3) - 1) * 100
                result["营收3年CAGR(%)"] = round(cagr, 1)

        # 5-year CAGR
        if len(df) >= 6:
            p5 = df.iloc[-6].get(rev_col)
            if latest and p5 and p5 > 0:
                cagr = ((latest / p5) ** (1 / 5) - 1) * 100
                result["营收5年CAGR(%)"] = round(cagr, 1)

    if eps_col and len(df) >= 2:
        latest_eps = df.iloc[-1].get(eps_col)
        prev_eps = df.iloc[-2].get(eps_col)
        if latest_eps and prev_eps and prev_eps != 0:
            result["EPS同比增速(%)"] = round((latest_eps - prev_eps) / abs(prev_eps) * 100, 1)

    return result


def calc_ops_risk_score(metrics: dict, growth_trend: dict = None, fin_df_q=None, fin_df=None) -> tuple:
    """统一经营风险评估：返回 (得分0-100, PE乘数0.7-1.2, 明细列表)

    基于五维度财务分析框架：
    一、利润表（盈利能力与质量）
    二、现金流量表（利润含金量）
    三、资产负债表（资产质量）
    四、成长与趋势
    五、极端风险

    明细列表: [{'因子': str, '调整': int, '说明': str}, ...]
    """
    score = 60
    steps = [{'因子': '基础分', '调整': 60, '说明': '起始 60 分'}]

    def add(name, adj, reason):
        nonlocal score
        if adj != 0:
            score += adj
            steps.append({'因子': name, '调整': adj, '说明': reason})

    if not metrics:
        score = max(10, min(100, score))
        mult = round(0.7 + (score / 100) * 0.5, 3)
        return score, mult, steps

    # ── 一、利润表 ──

    if "ROE(%)" in metrics:
        roe = metrics["ROE(%)"]
        if isinstance(roe, (int, float)):
            if roe >= 25:
                add('ROE水平', 15, f'ROE={roe}% ≥ 25，极强盈利能力')
            elif roe >= 20:
                add('ROE水平', 10, f'ROE={roe}% ≥ 20，盈利能力强')
            elif roe >= 15:
                add('ROE水平', 5, f'ROE={roe}% ≥ 15，盈利能力较好')
            elif roe >= 10:
                add('ROE水平', 0, f'ROE={roe}% ≥ 10，盈利能力中等')
            elif roe >= 5:
                add('ROE水平', -5, f'ROE={roe}% ≥ 5，盈利能力偏弱')
            elif roe >= 0:
                add('ROE水平', -12, f'ROE={roe}% ≥ 0，盈利能力差')
            else:
                add('ROE水平', -20, f'ROE={roe}% < 0，亏损状态')
    if "净利率(%)" in metrics:
        nm = metrics["净利率(%)"]
        if isinstance(nm, (int, float)):
            if nm >= 25:
                add('净利率', 10, f'净利率={nm}% ≥ 25，极高利润率')
            elif nm >= 20:
                add('净利率', 6, f'净利率={nm}% ≥ 20，高利润率护城河')
            elif nm >= 15:
                add('净利率', 3, f'净利率={nm}% ≥ 15，利润率优秀')
            elif nm >= 10:
                add('净利率', 0, f'净利率={nm}% ≥ 10，利润率较好')
            elif nm >= 5:
                add('净利率', -3, f'净利率={nm}% ≥ 5，利润率一般')
            elif nm >= 0:
                add('净利率', -8, f'净利率={nm}% ≥ 0，利润率偏低')
            else:
                add('净利率', -15, f'净利率={nm}% < 0，亏损')
    if "毛利率(%)" in metrics:
        gm = metrics["毛利率(%)"]
        if isinstance(gm, (int, float)):
            if gm >= 70:
                add('毛利率', 12, f'毛利率={gm}% ≥ 70，极强竞争优势')
            elif gm >= 50:
                add('毛利率', 8, f'毛利率={gm}% ≥ 50，强竞争优势')
            elif gm >= 35:
                add('毛利率', 4, f'毛利率={gm}% ≥ 35，有竞争优势')
            elif gm >= 20:
                add('毛利率', 0, f'毛利率={gm}% ≥ 20，毛利尚可')
            elif gm >= 15:
                add('毛利率', -4, f'毛利率={gm}% ≥ 15，毛利偏低')
            elif gm >= 10:
                add('毛利率', -8, f'毛利率={gm}% ≥ 10，毛利薄弱')
            else:
                add('毛利率', -12, f'毛利率={gm}% < 10，毛利极低')

    # 扣非净利润亏损 — 主业能否造血
    np_deducted = metrics.get("扣非净利润(亿)")
    if np_deducted is not None and not pd.isna(np_deducted):
        if np_deducted < 0:
            add('扣非净利润', -15, f'扣非净利润={np_deducted}亿 < 0，主业亏损')

    # 净利润连续亏损 / 由盈转亏 — 从年度fin_df检查
    if fin_df is not None and hasattr(fin_df, "columns") and not fin_df.empty and "net_profit" in fin_df.columns:
        npf = fin_df.copy()
        npf["report_date"] = pd.to_datetime(npf["report_date"])
        npf = npf.sort_values("report_date").dropna(subset=["net_profit"])
        np_vals = npf["net_profit"].astype(float)
        if len(np_vals) >= 2:
            latest_np = np_vals.iloc[-1]
            prior_np = np_vals.iloc[-2]
            if latest_np < 0 and prior_np < 0:
                add('净利润趋势', -25, f'最近2年净利润均为负（{prior_np:.1f}亿 → {latest_np:.1f}亿），持续亏损')
            elif latest_np < 0 < prior_np:
                add('净利润趋势', -20, f'净利润由盈转亏（{prior_np:.1f}亿 → {latest_np:.1f}亿）')
            elif latest_np < 0:
                add('净利润趋势', -15, f'净利润为负（{latest_np:.1f}亿）')
            elif prior_np < 0 < latest_np:
                add('净利润趋势', 5, f'净利润扭亏为盈（{prior_np:.1f}亿 → {latest_np:.1f}亿）')

    # ── 二、现金流量表 ──

    if fin_df_q is not None and hasattr(fin_df_q, "columns") and not fin_df_q.empty:
        fq = fin_df_q.copy()
        if "report_date" in fq.columns:
            fq["report_date"] = pd.to_datetime(fq["report_date"])
            fq = fq.sort_values("report_date")

        # 净现比（净利润现金含量）
        if "cash_flow_ps" in fq.columns and "basic_eps" in fq.columns:
            cf_vals = pd.to_numeric(fq["cash_flow_ps"], errors="coerce")
            eps_vals = pd.to_numeric(fq["basic_eps"], errors="coerce")
            total_cf = cf_vals.sum()
            total_np = eps_vals.sum()
            if total_np and total_np > 0:
                cr = total_cf / total_np
                recent = cf_vals.tail(min(6, len(cf_vals)))
                neg_ratio = (recent < 0).sum() / len(recent) if len(recent) > 0 else 0
                is_temporary = neg_ratio < 0.3
                tag = '临时性(主动囤货等)' if is_temporary else '结构性问题'
                if cr > 2.0:
                    add('现金流质量', 8, f'净现比={cr:.2f} > 2.0，现金流极充沛')
                elif cr > 1.5:
                    add('现金流质量', 5, f'净现比={cr:.2f} > 1.5，现金流充沛')
                elif cr > 1.0:
                    add('现金流质量', 3, f'净现比={cr:.2f} > 1.0，现金流良好')
                elif cr > 0.8:
                    add('现金流质量', 0, f'净现比={cr:.2f} > 0.8，现金流正常')
                elif cr > 0.6:
                    add('现金流质量', -3, f'净现比={cr:.2f} < 0.8，现金流偏弱')
                elif cr > 0.3:
                    add('现金流质量', -6, f'净现比={cr:.2f} < 0.6，现金流较差')
                else:
                    add('现金流质量', -10 if is_temporary else -20,
                        f'净现比={cr:.2f} < 0.3，现金流差({tag})')

        # 经营现金流持续为负
        if "cash_flow_ps" in fq.columns:
            cf_vals = pd.to_numeric(fq["cash_flow_ps"], errors="coerce")
            recent_cf = cf_vals.tail(min(8, len(cf_vals)))
            if len(recent_cf) >= 4:
                neg_cf_ratio = (recent_cf < 0).sum() / len(recent_cf)
                if neg_cf_ratio >= 0.75:
                    add('经营现金流为负', -12, f'近{len(recent_cf)}季中{int(neg_cf_ratio*len(recent_cf))}季经营现金流为负，持续失血')
                elif neg_cf_ratio >= 0.5:
                    add('经营现金流为负', -6, f'近{len(recent_cf)}季中{int(neg_cf_ratio*len(recent_cf))}季经营现金流为负')

        # 销售现金比率趋势（经营现金流/营收）
        if "cash_flow_ps" in fq.columns and "revenue_ps" in fq.columns:
            cf_vals = pd.to_numeric(fq["cash_flow_ps"], errors="coerce")
            rev_vals = pd.to_numeric(fq["revenue_ps"], errors="coerce")
            valid = cf_vals.notna() & rev_vals.notna() & (rev_vals > 0)
            if valid.sum() >= 4:
                cf_ratios = (cf_vals[valid] / rev_vals[valid]).tail(8)
                if len(cf_ratios) >= 4:
                    early = cf_ratios.head(len(cf_ratios)//2).mean()
                    late = cf_ratios.tail(len(cf_ratios)//2).mean()
                    if early > 0 and late < early * 0.5 and late < 0:
                        add('销售现金比率', -8, f'经营现金流/营收比值由{early:.2f}降至{late:.2f}，销售回款能力恶化')
                    elif early > 0 and late < early * 0.5:
                        add('销售现金比率', -4, f'经营现金流/营收比值由{early:.2f}降至{late:.2f}，销售回款趋弱')

        # ── 三、资产负债表 ──

        # 存货周转天数趋势（从年度数据）
        if fin_df is not None and hasattr(fin_df, "columns") and not fin_df.empty and "inventory_turnover_days" in fin_df.columns:
            inv_df = fin_df.copy()
            inv_df["report_date"] = pd.to_datetime(inv_df["report_date"])
            inv_df = inv_df.sort_values("report_date").dropna(subset=["inventory_turnover_days"])
            inv_vals = inv_df["inventory_turnover_days"].astype(float).tail(5)
            if len(inv_vals) >= 3:
                inv_chg = (inv_vals.iloc[-1] - inv_vals.iloc[0]) / inv_vals.iloc[0] * 100
                if inv_chg > 50:
                    add('存货周转恶化', -12, f'存货周转天数由{inv_vals.iloc[0]:.0f}升至{inv_vals.iloc[-1]:.0f}天（+{inv_chg:.0f}%），严重积压')
                elif inv_chg > 25:
                    add('存货周转恶化', -8, f'存货周转天数由{inv_vals.iloc[0]:.0f}升至{inv_vals.iloc[-1]:.0f}天（+{inv_chg:.0f}%），明显积压')
                elif inv_chg > 10:
                    add('存货周转恶化', -3, f'存货周转天数由{inv_vals.iloc[0]:.0f}升至{inv_vals.iloc[-1]:.0f}天（+{inv_chg:.0f}%），周转放缓')

    # 净资产为负（资不抵债）
    bvps = metrics.get("每股净资产")
    if bvps is not None and not pd.isna(bvps) and bvps <= 0:
        add('净资产为负', -25, f'每股净资产={bvps} ≤ 0，资不抵债')

    # ── 四、成长与趋势 ──

    if fin_df_q is not None and hasattr(fin_df_q, "columns") and not fin_df_q.empty:
        fq = fin_df_q.copy()
        if "report_date" in fq.columns:
            fq["report_date"] = pd.to_datetime(fq["report_date"])
            fq = fq.sort_values("report_date")

        # ROE趋势
        if "roe_pct" in fq.columns:
            roe_vals = pd.to_numeric(fq["roe_pct"], errors="coerce").dropna()
            if len(roe_vals) >= 6:
                recent_roe = roe_vals.tail(2).mean()
                prior_roe = roe_vals.iloc[-6:-2].mean()
                if prior_roe > 0:
                    roe_chg = (recent_roe - prior_roe) / prior_roe * 100
                    if roe_chg >= 20:
                        add('ROE趋势', 8, f'近2季ROE均值({recent_roe:.1f})较前4季({prior_roe:.1f})提升{roe_chg:.0f}%')
                    elif roe_chg >= 10:
                        add('ROE趋势', 5, f'近2季ROE均值({recent_roe:.1f})较前4季({prior_roe:.1f})提升{roe_chg:.0f}%')
                    elif roe_chg >= 3:
                        add('ROE趋势', 2, f'近2季ROE均值({recent_roe:.1f})较前4季({prior_roe:.1f})小幅提升{roe_chg:.0f}%')
                    elif roe_chg > -5:
                        add('ROE趋势', 0, f'近2季ROE均值({recent_roe:.1f})较前4季({prior_roe:.1f})基本稳定({roe_chg:.0f}%)')
                    elif roe_chg > -15:
                        add('ROE趋势', -4, f'近2季ROE均值({recent_roe:.1f})较前4季({prior_roe:.1f})下滑{abs(roe_chg):.0f}%')
                    elif roe_chg > -25:
                        add('ROE趋势', -8, f'近2季ROE均值({recent_roe:.1f})较前4季({prior_roe:.1f})明显下滑{abs(roe_chg):.0f}%')
                    elif roe_chg > -40:
                        add('ROE趋势', -14, f'近2季ROE均值({recent_roe:.1f})较前4季({prior_roe:.1f})大幅下滑{abs(roe_chg):.0f}%')
                    else:
                        add('ROE趋势', -20, f'近2季ROE均值({recent_roe:.1f})较前4季({prior_roe:.1f})恶化{abs(roe_chg):.0f}%')
            if len(roe_vals) >= 4:
                avg_roe = roe_vals.mean()
                latest_roe = roe_vals.iloc[-1]
                ratio = latest_roe / avg_roe if avg_roe > 0 else 1
                if ratio > 3.0 and latest_roe > 15:
                    add('ROE均值回归', -20, f'最新ROE={latest_roe:.1f} 为均值({avg_roe:.1f})的{ratio:.1f}倍，极端顶部')
                elif ratio > 2.0 and latest_roe > 15:
                    add('ROE均值回归', -12, f'最新ROE={latest_roe:.1f} 为均值({avg_roe:.1f})的{ratio:.1f}倍，周期顶部')
                elif ratio > 1.5 and latest_roe > 15:
                    add('ROE均值回归', -8, f'最新ROE={latest_roe:.1f} 为均值({avg_roe:.1f})的{ratio:.1f}倍，偏高')
                elif ratio > 1.2:
                    add('ROE均值回归', -3, f'最新ROE={latest_roe:.1f} 为均值({avg_roe:.1f})的{ratio:.1f}倍，略高')
                elif ratio > 0.8:
                    add('ROE均值回归', 0, f'最新ROE={latest_roe:.1f} 为均值({avg_roe:.1f})的{ratio:.1f}倍，正常波动')
                elif ratio > 0.5:
                    add('ROE均值回归', 4, f'最新ROE={latest_roe:.1f} 为均值({avg_roe:.1f})的{ratio:.1f}倍，低于均值有反弹潜力')
                else:
                    add('ROE均值回归', 8, f'最新ROE={latest_roe:.1f} 为均值({avg_roe:.1f})的{ratio:.1f}倍，严重低于均值')

    # 营收稳定性
    if growth_trend:
        rev_rates = [v for k, v in growth_trend.items() if "营收" in k and v is not None]
        if len(rev_rates) >= 2:
            spread = max(rev_rates) - min(rev_rates)
            if spread <= 3:
                add('营收稳定性', 3, f'各周期营收增速极差={spread:.0f}% ≤ 3%，高度稳定')
            elif spread <= 6:
                add('营收稳定性', 0, f'各周期营收增速极差={spread:.0f}% ≤ 6%，基本稳定')
            elif spread <= 10:
                add('营收稳定性', -3, f'各周期营收增速极差={spread:.0f}% ≤ 10%，轻度波动')
            elif spread <= 16:
                add('营收稳定性', -6, f'各周期营收增速极差={spread:.0f}% ≤ 16%，有一定波动')
            elif spread <= 22:
                add('营收稳定性', -9, f'各周期营收增速极差={spread:.0f}% ≤ 22%，波动较大')
            elif spread <= 30:
                add('营收稳定性', -12, f'各周期营收增速极差={spread:.0f}% ≤ 30%，波动明显')
            else:
                add('营收稳定性', -15, f'各周期营收增速极差={spread:.0f}% > 30%，增速极不稳定')

    # ── 五、极端风险 ──

    # 营收踩线（主板退市风险：利润为负且营收<3亿）
    revenue = metrics.get("营业总收入(亿)")
    if revenue is not None and not pd.isna(revenue) and np_deducted is not None and not pd.isna(np_deducted):
        if revenue < 3 and np_deducted < 0:
            add('营收踩线', -25, f'营收={revenue}亿 < 3亿 且 扣非净利润={np_deducted}亿 < 0，退市风险警示')
        elif revenue < 1:
            add('营收踩线', -10, f'营收={revenue}亿 < 1亿，经营规模极小')

    score = max(10, min(100, score))
    mult = round(0.7 + (score / 100) * 0.5, 3)
    steps.append({'因子': '合计', '调整': score, '说明': f'最终得分 {score} 分，PE乘数 {mult}'})
    return score, mult, steps


def _calc_ops_risk_multiplier(metrics: dict, growth_trend: dict = None, fin_df_q=None, fin_df=None) -> float:
    _, mult, _ = calc_ops_risk_score(metrics, growth_trend, fin_df_q, fin_df)
    return mult


def calc_price_range(
    pe_analysis: dict,
    pb_analysis: dict,
    eps: float,
    bvps: float,
    current_price: float,
    growth_trend: dict = None,
    roe: float = None,
    ops_risk_mult: float = 1.0,
    sector_pe: float = None,
) -> dict:
    result = {}

    if pe_analysis and eps and eps > 0:
        p30 = pe_analysis.get("_p30")
        p70 = pe_analysis.get("_p70")
        if p30 and p70 and p30 > 0 and p70 > 0:
            low = round(p30 * eps, 2)
            high = round(p70 * eps, 2)
            coef = round(current_price * 2 / (high + low), 3) if (high + low) > 0 else None
            result["PE合理价位"] = {"低": low, "高": high, "中轴": round((low + high) / 2, 2)}

    if pb_analysis and bvps and bvps > 0:
        p30 = pb_analysis.get("_p30")
        p70 = pb_analysis.get("_p70")
        if p30 and p70 and p30 > 0 and p70 > 0:
            low = round(p30 * bvps, 2)
            high = round(p70 * bvps, 2)
            result["PB合理价位"] = {"低": low, "高": high, "中轴": round((low + high) / 2, 2)}

    # ──  Fundamental fair PE (Gordon Growth Model) ──
    fundamental_pe = None
    if growth_trend and eps and eps > 0 and roe and roe > 0:
        rates = [v for k, v in growth_trend.items() if "%" in k and v is not None]
        if rates:
            g = max(0, min(rates)) / 100.0  # sustainable growth (decimal, floored at 0)
            r = 0.09  # cost of equity
            roe_dec = roe / 100.0
            payout = max(0.3, min(1.0, 1 - g / max(roe_dec, 0.02)))
            effective_g = min(g, r - 0.01)  # cap growth to avoid GGM singularity
            denominator = max(0.02, r - effective_g)
            fundamental_pe = round(payout / denominator, 1)
            result["基本面合理PE"] = fundamental_pe

    # Combined range from PE, PB, and fundamental
    lows, highs = [], []
    if "PE合理价位" in result:
        lows.append(result["PE合理价位"]["低"])
        highs.append(result["PE合理价位"]["高"])
    if "PB合理价位" in result:
        lows.append(result["PB合理价位"]["低"])
        highs.append(result["PB合理价位"]["高"])

    # Add fundamental-based range if available (dynamic bands from ops risk)
    if fundamental_pe and eps > 0:
        up_pct, down_pct = 15, 15
        f_low = round(fundamental_pe * eps * (1 - down_pct / 100), 2)
        f_high = round(fundamental_pe * eps * (1 + up_pct / 100), 2)
        result["基本面合理价位"] = {"低": f_low, "高": f_high, "中轴": round(fundamental_pe * eps, 2)}

    if lows and highs:
        avg_low = round(sum(lows) / len(lows), 2)
        avg_high = round(sum(highs) / len(highs), 2)
        mid = round((avg_low + avg_high) / 2, 2)
        coef = round(current_price * 2 / (avg_high + avg_low), 3) if (avg_high + avg_low) > 0 else None
        result["综合合理价位"] = {"低": avg_low, "高": avg_high, "中轴": mid, "估值系数": coef}

        # Growth-adjusted & fundamental blended valuation
        if growth_trend and fundamental_pe:
            rates = [v for k, v in growth_trend.items() if "%" in k and v is not None]
            if rates:
                rates_sorted = sorted(rates)
                median_g = rates_sorted[len(rates_sorted)//2]
                sustainable_g = max(median_g, 3.0)
                hist_g = max(rates)
                adj = max(0.4, min(1.2, sustainable_g / max(hist_g, 5.0)))

                pe_r = result.get("PE合理价位", {})
                pb_r = result.get("PB合理价位", {})

                pb_low = pb_r.get("低") if pb_r else None
                pb_high = pb_r.get("高") if pb_r else None

                if pe_r.get("低") and pe_r.get("高"):
                    pe_low_c = round(pe_r["低"] * adj, 2)
                    pe_high_c = round(pe_r["高"] * adj, 2)
                else:
                    pe_low_c, pe_high_c = avg_low, avg_high

                # Sector-based price (if sector median PE available)
                s_low, s_high = None, None
                if sector_pe and sector_pe > 0 and eps and eps > 0:
                    s_low = round(sector_pe * eps * 0.85, 2)
                    s_high = round(sector_pe * eps * 1.15, 2)
                    result["板块合理价位"] = {"低": s_low, "高": s_high, "中轴": round(sector_pe * eps, 2)}

                # Weighted blend then apply risk multiplier
                f_r = result.get("基本面合理价位", {})
                f_low = f_r.get("低", pe_low_c)
                f_high = f_r.get("高", pe_high_c)
                c_low = pe_low_c * 0.40 + f_low * 0.35
                c_high = pe_high_c * 0.40 + f_high * 0.35
                if pb_low is not None:
                    c_low += pb_low * 0.10
                    c_high += pb_high * 0.10
                if s_low is not None and s_high is not None:
                    c_low += s_low * 0.15
                    c_high += s_high * 0.15
                else:
                    c_low /= 0.85
                    c_high /= 0.85
                blend_raw_low = c_low
                blend_raw_high = c_high
                c_low = round(c_low * ops_risk_mult, 2)
                c_high = round(c_high * ops_risk_mult, 2)
                c_mid = round((c_low + c_high) / 2, 2)
                c_coef = round(current_price * 2 / (c_high + c_low), 3) if (c_high + c_low) > 0 else None
                result["综合合理价位"] = {"低": c_low, "高": c_high, "中轴": c_mid, "估值系数": c_coef}
                result["_风险乘数"] = ops_risk_mult
                # Store component detail for UI breakdown
                comps = [
                    ("历史PE(增长调整)", pe_low_c, pe_high_c, 40),
                    ("基本面(GGM)", f_low, f_high, 35),
                ]
                if pb_low is not None:
                    comps.insert(1, ("历史PB", pb_low, pb_high, 10))
                if s_low is not None:
                    comps.append(("板块参考", s_low, s_high, 15))
                result["_权重明细"] = [
                    {"名称": name, "低": lo, "高": hi, "权重": w,
                     "贡献低": round(lo * w / 100, 2), "贡献高": round(hi * w / 100, 2)}
                    for name, lo, hi, w in comps
                ]

    return result


def _build_fundamental_series(fin_df: pd.DataFrame, col: str):
    """Build a time-indexed Series of a fundamental value (EPS/BVPS) from annual data,
    forward-filled so each date maps to the most recent known value."""
    df = fin_df.copy()
    df["report_date"] = pd.to_datetime(df["report_date"])
    df = df.sort_values("report_date").dropna(subset=["report_date", col])
    if df.empty:
        return pd.Series(dtype=float)
    s = df.set_index("report_date")[col].astype(float)
    s = s[~s.index.duplicated(keep="last")]
    return s


def _build_ttm_eps_series(fin_df_q: pd.DataFrame):
    """Build time-indexed Series of TTM EPS from de-cumulated quarterly data."""
    df = fin_df_q.copy()
    df["report_date"] = pd.to_datetime(df["report_date"])
    df = df.sort_values("report_date").dropna(subset=["report_date", "basic_eps"])
    if df.empty:
        return pd.Series(dtype=float)
    df = df.set_index("report_date")
    eps = df["basic_eps"].astype(float)
    ttm = eps.rolling(4, min_periods=4).sum()
    return ttm.dropna()


def _calc_historical_pe_pb_series(price_df: pd.DataFrame, fin_df: pd.DataFrame, fin_df_q: pd.DataFrame = None):
    """Calculate daily PE and PB. For periods with negative EPS/BVPS,
    use the nearest prior positive value so the PE curve has no gaps.
    Uses TTM EPS from quarterly data when available (dynamic PE)."""
    price = price_df.copy()
    price["d"] = pd.to_datetime(price["date"])
    price = price.set_index("d").sort_index()

    eps_annual = _build_fundamental_series(fin_df, "basic_eps")
    eps_q = _build_ttm_eps_series(fin_df_q) if fin_df_q is not None else pd.Series(dtype=float)
    eps_s = eps_q.combine_first(eps_annual) if not eps_q.empty else eps_annual

    bvps_s = _build_fundamental_series(fin_df, "bvps")

    def _ffill_positive(series):
        """Forward-fill and replace negative values with last positive."""
        s = series.copy()
        last_pos = None
        for i in range(len(s)):
            v = s.iloc[i]
            if v > 0:
                last_pos = v
            elif last_pos is not None:
                s.iloc[i] = last_pos
        return s

    pe = pb = None
    if not eps_s.empty:
        eps_ff = eps_s.reindex(price.index, method="ffill").fillna(eps_s.iloc[0])
        eps_ff = _ffill_positive(eps_ff)
        pe = price["close"] / eps_ff
        pe = pe[(pe > 0) & (pe < 1000)]
    if not bvps_s.empty:
        bvps_ff = bvps_s.reindex(price.index, method="ffill").fillna(bvps_s.iloc[0])
        bvps_ff = _ffill_positive(bvps_ff)
        pb = price["close"] / bvps_ff
        pb = pb[(pb > 0) & (pb < 100)]
    return pe, pb


def calc_pe_pb_history(price_df: pd.DataFrame, fin_df: pd.DataFrame, fin_df_q: pd.DataFrame = None) -> dict:
    if price_df.empty or fin_df.empty:
        return {}

    result = {}
    pe_series, pb_series = _calc_historical_pe_pb_series(price_df, fin_df, fin_df_q)

    if pe_series is not None and not pe_series.empty and len(pe_series) > 10:
        result["PE历史"] = calc_percentile(float(pe_series.iloc[-1]), pe_series)

    if pb_series is not None and not pb_series.empty and len(pb_series) > 10:
        result["PB历史"] = calc_percentile(float(pb_series.iloc[-1]), pb_series)

    return result
