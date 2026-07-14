def format_markdown_report(
    stock_info: dict,
    price: float,
    financial_metrics: dict,
    current_pe_pb: dict,
    history_analysis: dict,
    industry_name: str,
    llm_analysis: str,
    price_range: dict = None,
) -> str:
    from datetime import datetime

    lines = []

    name = stock_info.get("name", "未知")
    code = stock_info.get("code", "")
    date_str = datetime.now().strftime("%Y-%m-%d")

    lines.append(f"# {name}（{code}）估值分析报告")
    lines.append(f"**分析日期**: {date_str} | **当前价格**: {price} 元")
    if industry_name:
        lines.append(f"**所属板块**: {industry_name}")
    lines.append("---")
    lines.append("")

    # ── 一、核心财务概览 ──
    if financial_metrics:
        lines.append("## 一、核心财务概览")
        profit_keys = ["营业总收入(亿)", "扣非净利润(亿)", "营收同比(%)", "净利润同比(%)"]
        profit_items = [(k, financial_metrics[k]) for k in profit_keys if k in financial_metrics]
        if profit_items:
            lines.append("**经营业绩**")
            for k, v in profit_items:
                suffix = "%" if "同比" in k else ""
                lines.append(f"- {k}：**{v}{suffix}**")
            lines.append("")

        eff_keys = ["ROE(%)", "毛利率(%)", "净利率(%)", "资产负债率(%)"]
        eff_items = [(k, financial_metrics[k]) for k in eff_keys if k in financial_metrics]
        if eff_items:
            lines.append("**盈利能力与资本结构**")
            for k, v in eff_items:
                lines.append(f"- {k}：**{v}**")
            lines.append("")

        per_share_keys = ["基本每股收益", "每股净资产"]
        per_share_items = [(k, financial_metrics[k]) for k in per_share_keys if k in financial_metrics]
        if per_share_items:
            lines.append("**每股数据**")
            for k, v in per_share_items:
                lines.append(f"- {k}：**{v}**")
            lines.append("")

    # ── 二、当前估值 ──
    lines.append("## 二、当前估值")
    if current_pe_pb:
        pe = current_pe_pb.get("PE")
        pb = current_pe_pb.get("PB")
        parts = []
        if pe:
            parts.append(f"市盈率(PE)：**{pe}**")
        if pb:
            parts.append(f"市净率(PB)：**{pb}**")
        if parts:
            lines.append(" | ".join(parts))
        else:
            lines.append("数据不足，无法计算当前估值")
    else:
        lines.append("数据不足，无法计算当前估值")
    lines.append("")

    # ── 三、历史估值百分位 ──
    if history_analysis:
        lines.append("## 三、历史估值百分位")
        for key, data in history_analysis.items():
            label = {"PE历史": "PE（市盈率）", "PB历史": "PB（市净率）"}.get(key, key)
            lines.append(f"**{label}**")
            pct = data.get("当前百分位(%)")
            if pct is not None:
                level = "偏高 🔥" if pct > 70 else "偏低 ❄️" if pct < 30 else "合理 ⚡"
                lines.append(f"- 当前百分位：**{pct}%**（{level}）")
            for k, v in data.items():
                if not k.startswith("_") and k != "当前百分位(%)":
                    lines.append(f"- {k}：**{v}**")
            lines.append("")

    # ── 四、合理价位估算 ──
    if price_range:
        lines.append("## 四、合理价位估算")
        combined = price_range.get("综合合理价位", {})
        if combined:
            low = combined.get("低")
            high = combined.get("高")
            mid = combined.get("中轴")
            coef = combined.get("估值系数")
            if low and high:
                verdict = "低估" if coef and coef < 0.95 else "高估" if coef and coef > 1.05 else "合理"
                lines.append(f"综合判断：合理价位区间 **{low} ~ {high}** 元（中轴 **{mid}** 元）")
                lines.append(f"当前价格 **{price}** 元 → 估值系数 **{coef}** → 判断：**{verdict}**")
                risk_mult = price_range.get("_风险乘数")
                if risk_mult is not None and risk_mult != 1.0:
                    lines.append(f"> 风险乘数：**{risk_mult}**（经营风险调整，<1.0 表示折价）")
                lines.append("")
        for method, values in price_range.items():
            if method == "综合合理价位":
                continue
            if not isinstance(values, dict):
                continue
            coef = values.pop("估值系数", None)
            parts = [f"{k}：**{v}**" for k, v in values.items()]
            if coef is not None:
                parts.append(f"估值系数：**{coef}**")
            lines.append(f"- **{method}**：{' | '.join(parts)}")
            if coef is not None:
                values["估值系数"] = coef
        lines.append("")

    # ── 五、AI 分析师结论 ──
    lines.append("## 五、AI 分析师结论")
    lines.append("")
    lines.append(llm_analysis)

    return "\n".join(lines)
