import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
import streamlit as st

from src.analysis.historical import calc_ops_risk_score


def _score_financial(metrics, growth_trend=None, fin_df_q=None, fin_df=None):
    score, _, _ = calc_ops_risk_score(metrics, growth_trend, fin_df_q, fin_df)
    return score


def _score_valuation(pe_pct):
    if pe_pct is None:
        return 50
    return max(0, min(100, 100 - pe_pct))


def _score_historical(pe_pct, coef, growth_trend=None, pe_value=None):
    base = _score_valuation(pe_pct)
    steps = [{'因子': 'PE百分位', '调整': int(base), '说明': f'当前PE处于历史 {pe_pct:.1f}% 分位，得分 {int(base)}'}]
    if growth_trend and pe_value and pe_value > 0:
        rates = [v for k, v in growth_trend.items() if "%" in k and v is not None]
        if rates:
            g = min(rates)
            peg = g / pe_value
            if peg > 0.8:
                adj = int(base * 0.15)
                steps.append({'因子': 'PEG调整', '调整': adj, '说明': f'PEG={peg:.2f} > 0.8，增速匹配估值，+15%'})
                base = int(base * 1.15)
            elif peg < 0.3:
                adj = -int(base * 0.3)
                steps.append({'因子': 'PEG调整', '调整': adj, '说明': f'PEG={peg:.2f} < 0.3，成长性相对估值偏低，-30%'})
                base = int(base * 0.7)
    final = max(0, min(100, base))
    steps.append({'因子': '合计', '调整': int(final), '说明': f'最终得分 {int(final)} 分'})
    return int(final), steps


def _score_sector(coef, price_range=None):
    steps = []
    sector_info = price_range.get("_板块信息") if price_range else None
    if sector_info:
        stock_pe = sector_info.get("stock_pe")
        sector_pe = sector_info.get("sector_pe")
        stock_pb = sector_info.get("stock_pb")
        sector_pb = sector_info.get("sector_pb")
        sector_name = sector_info.get("sector_name", "")

        pe_score = 50
        pe_ratio = None
        if stock_pe and sector_pe and sector_pe > 0:
            pe_ratio = stock_pe / sector_pe
            pe_score = max(0, min(100, round(50 + (1 - pe_ratio) * 50)))
            steps.append({'因子': 'PE对比', '调整': pe_score - 50,
                         '说明': f'PE={stock_pe:.1f} / {sector_name}中位PE={sector_pe:.1f} = {pe_ratio:.2f}倍'})

        pb_score = 50
        pb_ratio = None
        if stock_pb and sector_pb and sector_pb > 0:
            pb_ratio = stock_pb / sector_pb
            pb_score = max(0, min(100, round(50 + (1 - pb_ratio) * 50)))
            steps.append({'因子': 'PB对比', '调整': pb_score - 50,
                         '说明': f'PB={stock_pb:.2f} / {sector_name}中位PB={sector_pb:.2f} = {pb_ratio:.2f}倍'})

        if pe_ratio is not None and pb_ratio is not None:
            base = round(pe_score * 0.7 + pb_score * 0.3)
        elif pe_ratio is not None:
            base = pe_score
        elif pb_ratio is not None:
            base = pb_score
        else:
            base = 50

        steps.insert(0, {'因子': '基础分', '调整': base, '说明': f'板块估值起始 {base} 分'})
    else:
        keys = list(price_range.keys()) if price_range else "None"
        return 50, [{'因子': '基础分', '调整': 50, '说明': f'无板块数据(price_range keys: {keys})'},
                     {'因子': '合计', '调整': 50, '说明': '最终得分 50 分'}]

    final = max(0, min(100, base))
    steps.append({'因子': '合计', '调整': int(final), '说明': f'最终得分 {int(final)} 分'})
    return int(final), steps


def render_summary_card(
    stock_name,
    code,
    price,
    metrics,
    pe_pct,
    pb_pct,
    coef,
    price_low,
    price_high,
    llm_summary,
    growth_trend=None,
    price_range=None,
    pe_value=None,
    fin_df_q=None,
    fin_df=None,
):
    score, _, fin_steps = calc_ops_risk_score(metrics, growth_trend, fin_df_q, fin_df) if metrics else (50, 1.0, [])
    s_fin = score
    s_hist, hist_steps = _score_historical(pe_pct, coef, growth_trend, pe_value)
    s_sec, sec_steps = _score_sector(coef, price_range)

    col_r, col_t = st.columns([1, 1.6])
    with col_r:
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=[s_fin, s_hist, s_sec, s_fin],
            theta=["经营风险", "历史估值", "板块估值", "经营风险"],
            fill="toself",
            line=dict(color="#0f3460", width=2),
            marker=dict(size=0),
            name="综合评分",
        ))
        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], showticklabels=False),
                bgcolor="rgba(0,0,0,0)",
            ),
            margin=dict(l=20, r=20, t=10, b=10),
            height=220,
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(size=10),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with col_t:
        if stock_name:
            st.markdown("**%s（%s）**　当前 %.2f 元" % (stock_name, code, price))
        st.markdown(
            '<div class="metric-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem">'
            '<div class="metric-item"><div class="label">经营风险</div><div class="value" style="color:%s">%d分</div></div>'
            '<div class="metric-item"><div class="label">历史估值</div><div class="value" style="color:%s">%d分</div></div>'
            '<div class="metric-item"><div class="label">板块估值</div><div class="value" style="color:%s">%d分</div></div>'
            '<div class="metric-item"><div class="label">估值系数</div><div class="value">%s</div></div>'
            "</div>"
            % (
                "#059669" if s_fin >= 70 else "#d97706" if s_fin >= 40 else "#dc2626",
                s_fin,
                "#059669" if s_hist >= 70 else "#d97706" if s_hist >= 40 else "#dc2626",
                s_hist,
                "#059669" if s_sec >= 70 else "#d97706" if s_sec >= 40 else "#dc2626",
                s_sec,
                "%.3f" % coef if coef is not None else "-",
            ),
            unsafe_allow_html=True,
        )

        if price_range:
            r = price_range.get("综合合理价位", {})
            low, high = r.get("低"), r.get("高")
            if low and high:
                css = "percentile-low" if price < low else ("percentile-high" if price > high else "percentile-mid")
                st.markdown(
                    '<div style="margin-top:0.8rem;padding:0.5rem;background:#f8f9fc;border-radius:8px;text-align:center">'
                    '合理价位: <strong>%.2f</strong> ~ <strong>%.2f</strong> 元　'
                    '<span class="%s">当前 %.2f 元</span></div>'
                    % (low, high, css, price),
                    unsafe_allow_html=True,
                )
        elif price_low and price_high:
            css = "percentile-low" if price < price_low else ("percentile-high" if price > price_high else "percentile-mid")
            st.markdown(
                '<div style="margin-top:0.8rem;padding:0.5rem;background:#f8f9fc;border-radius:8px;text-align:center">'
                '合理价位: <strong>%.2f</strong> ~ <strong>%.2f</strong> 元　'
                '<span class="%s">当前 %.2f 元</span></div>'
                % (price_low, price_high, css, price),
                unsafe_allow_html=True,
            )

        # 评分明细
        def _render_steps(title, steps):
            if not steps:
                return
            with st.expander(title, expanded=False):
                for s in steps:
                    adj = s['调整']
                    if s['因子'] in ('基础分', 'PE百分位', '合计'):
                        st.markdown(f"**{s['因子']}**: {s['说明']}")
                    else:
                        color = "#059669" if adj > 0 else "#dc2626" if adj < 0 else "#666"
                        prefix = "+" if adj > 0 else ""
                        st.markdown(f"**{s['因子']}** <span style='color:{color}'>({prefix}{adj})</span>: {s['说明']}", unsafe_allow_html=True)

        _render_steps("📊 经营风险评分明细", fin_steps)
        _render_steps("📈 历史估值评分明细", hist_steps)
        _render_steps("🏷️ 板块估值评分明细", sec_steps)

        # 合理价位计算明细
        if price_range:
            cr = price_range.get("综合合理价位", {})
            comps = price_range.get("_权重明细", [])
            risk_mult = price_range.get("_风险乘数", 1.0)
            if comps and cr:
                pr_lines = []
                for c in comps:
                    pr_lines.append(
                        f"**{c['名称']}** (权重{c['权重']}%): "
                        f"{c['低']}~{c['高']} × {c['权重']}% = "
                        f"**{c['贡献低']}~{c['贡献高']}**"
                    )
                raw_low = sum(c['贡献低'] for c in comps)
                raw_high = sum(c['贡献高'] for c in comps)
                total_w = sum(c['权重'] for c in comps)
                pr_lines.append(
                    f"**加权合计**: "
                    f"{'+'.join(str(c['贡献低']) for c in comps)} = **{raw_low:.2f}** ~ "
                    f"{'+'.join(str(c['贡献高']) for c in comps)} = **{raw_high:.2f}**"
                )
                if total_w < 100:
                    norm = 100 / total_w
                    norm_low = round(raw_low * norm, 2)
                    norm_high = round(raw_high * norm, 2)
                    pr_lines.append(
                        f"**权重归一化** (/ {total_w/100:.0%}): "
                        f"**{norm_low}~{norm_high}**"
                    )
                else:
                    norm_low, norm_high = raw_low, raw_high
                if risk_mult != 1.0:
                    pr_lines.append(
                        f"**风险调整** (× {risk_mult}): "
                        f"**{round(norm_low * risk_mult, 2)}~{round(norm_high * risk_mult, 2)}**"
                    )
                pr_lines.append(
                    f"**综合**: **{cr['低']}~{cr['高']}**"
                )
                with st.expander("💰 合理价位计算明细", expanded=False):
                    for ps in pr_lines:
                        st.markdown(f"- {ps}")

    return {"财务估值": s_fin, "历史估值": s_hist, "板块估值": s_sec}







def render_report(
    stock_name: str,
    stock_code: str,
    price: float,
    price_df,
    fin_df,
    pe_series,
    pb_series,
    metrics: dict,
    pe_pct: float,
    pb_pct: float,
    coef: float,
    price_low: float,
    price_high: float,
    llm_text: str,
    sectors: list = None,
    fin_df_q=None,
    growth_trend: dict = None,
    price_range: dict = None,
    pe_value: float = None,
):
    import re

    # ── Parse LLM sections ──
    segs = re.split(r'\n(?=###?\s*\d)', llm_text.strip())
    sec_body = {}
    for seg in segs:
        m = re.match(r'###?\s*(\d+)', seg)
        if m:
            idx = int(m.group(1))
            lines = seg.split("\n", 1)
            sec_body[idx] = lines[1].strip() if len(lines) > 1 else ""
        else:
            sec_body[0] = seg.strip()

    # Detect old vs new format
    is_old = "历史" in sec_body.get(1, "") and "综合" in sec_body.get(4, "")

    # ── Title ──
    st.markdown("# %s（%s）估值分析报告" % (stock_name, stock_code))
    if sectors:
        tags = " ".join('<span class="tag">%s</span>' % s for s in sectors[:5])
        more = "…" if len(sectors) > 5 else ""
        st.markdown("**%.2f 元**　%s%s" % (price, tags, more), unsafe_allow_html=True)
    else:
        st.markdown("**%.2f 元**" % price)
    st.divider()

    # ── Section 1: 基本结论 ──
    st.markdown("### 1. 基本结论")
    render_summary_card(
        stock_name="", code="", price=price,
        metrics=metrics, pe_pct=pe_pct, pb_pct=pb_pct, coef=coef,
        price_low=price_low, price_high=price_high, llm_summary="",
        growth_trend=growth_trend, price_range=price_range,
        pe_value=pe_value, fin_df_q=fin_df_q, fin_df=fin_df,
    )
    if is_old:
        s1 = sec_body.get(0, "") or sec_body.get(4, "")
    else:
        s1 = sec_body.get(1, "")
    if not s1:
        s1 = sec_body.get(4, "")
    if s1:
        st.markdown(s1)

    if growth_trend:
        trend_items = []
        for k, v in growth_trend.items():
            if v is not None:
                color = "#059669" if v > 10 else "#d97706" if v > 0 else "#dc2626"
                trend_items.append('<span style="color:%s">%s: %s%%</span>' % (color, k, v))
        if trend_items:
            st.markdown("增长趋势: " + " | ".join(trend_items), unsafe_allow_html=True)

    # ── Section 2: 财务估值分析 ──
    st.markdown("---")
    st.markdown("### 2. 财务估值分析")
    s2 = sec_body.get(2, "")
    col_l, col_r = st.columns([1, 1])
    with col_l:
        if s2:
            st.markdown(s2)
    with col_r:
        _render_financial_col(fin_df_q if fin_df_q is not None else fin_df)

    # ── Section 3: 历史估值分析 ──
    st.markdown("---")
    st.markdown("### 3. 历史估值分析")
    if is_old:
        s3 = "\n\n".join(filter(None, [sec_body.get(1, ""), sec_body.get(3, "")]))
    else:
        s3 = sec_body.get(3, "")
    col_l, col_r = st.columns([1, 1])
    with col_l:
        if s3:
            st.markdown(s3)
    with col_r:
        _render_history_col(price_df, pe_series, pb_series)

    # ── Section 4: 板块估值分析 ──
    st.markdown("---")
    st.markdown("### 4. 板块估值分析")
    if sectors:
        tags = " ".join('<span class="tag">%s</span>' % s for s in sectors)
        st.markdown("所属板块: " + tags, unsafe_allow_html=True)
    s4 = sec_body.get(4, "")
    if s4:
        st.markdown(s4)
    else:
        si = (price_range or {}).get("_板块信息", {})
        st.warning(
            "⚠️ 第4段为空（诊断信息）\n\n"
            f"- 板块数据传入: {'是' if si else '否'}\n"
            f"- 板块名称: {si.get('sector_name', '无')}\n"
            f"- 板块PE: {si.get('sector_pe', '无')} | 板块PB: {si.get('sector_pb', '无')}\n"
            f"- 个股PE: {si.get('stock_pe', '无')} | 个股PB: {si.get('stock_pb', '无')}\n"
            f"- LLM回复长度: {len(llm_text)}字\n"
            f"- 解析到的段落: {sorted(sec_body.keys())}\n"
            f"- LLM前200字: {llm_text[:200]}..."
        )
    st.divider()


def _render_financial_col(fin_df):
    if fin_df is None or not isinstance(fin_df, pd.DataFrame) or fin_df.empty:
        return
    fin_c = fin_df.copy()
    if "report_date" not in fin_c.columns:
        return
    fin_c["report_date"] = pd.to_datetime(fin_c["report_date"])
    fin_c = fin_c.sort_values("report_date")
    cols = ["revenue_ps", "basic_eps", "roe_pct", "cash_flow_ps"]
    labels = {"revenue_ps": "每股营业总收入", "basic_eps": "基本每股收益", "roe_pct": "ROE(%)", "cash_flow_ps": "每股现金流"}
    divisors = {"revenue_ps": 1, "basic_eps": 1, "roe_pct": 1, "cash_flow_ps": 1}
    for i, col_name in enumerate(cols):
        if col_name not in fin_c.columns:
            continue
        series = fin_c.set_index("report_date")[col_name].dropna() / divisors[col_name]
        if not series.empty:
            fig = px.line(series.to_frame(labels[col_name]), labels={"value": labels[col_name], "index": "报告期"})
            fig.update_layout(height=200, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption("注：每股指标 = 总量值 ÷ 最新总股本，与前复权价格口径一致；营收/收益/现金流为各季度单独值（已剔除累计）")


def _render_history_col(price_df, pe_series, pb_series):
    has_price = price_df is not None and isinstance(price_df, pd.DataFrame) and not price_df.empty and "close" in price_df.columns
    if has_price:
        p = price_df.copy()
        if "date" in p.columns:
            p = p.set_index("date")
        p.index = pd.to_datetime(p.index)
        close = p[["close"]].rename(columns={"close": "价格"})
        fig1 = px.line(close, labels={"value": "价格(元)", "index": "日期"})
        # Ensure Y-axis covers full data range
        ymin, ymax = close["价格"].min(), close["价格"].max()
        pad = (ymax - ymin) * 0.08 or 1
        fig1.update_layout(
            height=220, margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
            yaxis=dict(range=[ymin - pad, ymax + pad]),
        )
        st.plotly_chart(fig1, use_container_width=True, config={"displayModeBar": False})
    if pe_series is not None and pb_series is not None:
        pe_df = pe_series.to_frame("PE").join(pb_series.to_frame("PB"))
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=pe_df.index, y=pe_df["PE"], mode="lines", name="PE", line=dict(color="#0f3460")))
        fig2.add_trace(go.Scatter(x=pe_df.index, y=pe_df["PB"], mode="lines", name="PB", line=dict(color="#059669"), yaxis="y2"))
        fig2.update_layout(
            height=220, margin=dict(l=10, r=10, t=10, b=10),
            yaxis=dict(title="PE", side="left"),
            yaxis2=dict(title="PB", side="right", overlaying="y"),
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})



