SYSTEM_PROMPT = """你是专业的A股估值分析师。你的任务是基于真实的财务数据和估值指标，从以下四个维度分析一只股票是否被高估或低估：

## 输出要求
- 使用中文，语言简洁专业
- 按以下 4 个段落分析，每个段落以 ### 开头作为标题：
  ### 1. 基本结论
  基于"综合合理价位"范围判断：当前价格在范围内为合理，低于下限为低估，高于上限为高估。用 1-2 句话概括，给出核心依据
  ### 2. 财务估值分析
  分析ROE、毛利率、净利率等核心指标，盈利增长趋势，资产负债结构
  ### 3. 历史估值分析
  分析当前PE/PB在近5年历史中的百分位位置，合理价位估算，是否处于历史高位或低位。
  注意结合公司营收/利润增速趋势判断：增速下降时低百分位可能≠低估，需考虑增长调整后的合理估值
  ### 4. 板块估值分析
  与同板块公司对比PE/PB，个股估值在板块中的相对位置，结合板块特性判断
- 每个段落包含标题和详细分析内容，段落之间用空行分隔
- 每个结论必须标注依据（引用数据百分位、行业数值等）
- 每个段落至少150字
- 禁止给出买卖建议和具体目标价
- 保持客观，同时指出利好和风险因素"""


def build_user_prompt(
    stock_info: dict,
    price: float,
    financial_metrics: dict,
    current_pe_pb: dict,
    history_analysis: dict,
    sectors_str: str,
    price_range: dict = None,
    sector_pe_info: dict = None,
) -> str:
    stock_name = stock_info.get("name", "未知")
    code = stock_info.get("code", "")
    lines = [f"请分析A股股票 {stock_name}（{code}），当前价格 {price} 元。\n"]

    lines.append("## 财务数据")
    if financial_metrics:
        for k, v in financial_metrics.items():
            lines.append(f"- {k}: {v}")
    lines.append("")

    if current_pe_pb:
        lines.append("## 当前PE/PB")
        for k, v in current_pe_pb.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    lines.append("## 历史估值百分位（近5年）")
    if history_analysis:
        for key, data in history_analysis.items():
            label = {"PE历史": "PE", "PB历史": "PB"}.get(key, key)
            lines.append(f"### {label}")
            for k, v in data.items():
                if not k.startswith("_"):
                    lines.append(f"- {k}: {v}")
    else:
        lines.append("（无历史数据）")
    lines.append("")

    if price_range:
        lines.append("## 合理价位估算")
        lines.append("（结论必须基于综合合理价位：当前价在范围内=合理，低于下限=低估，高于上限=高估）")
        for method, values in price_range.items():
            if not isinstance(values, dict):
                continue
            parts = [f"{k}: {v}" for k, v in values.items()]
            lines.append(f"- {method}: {' | '.join(parts)}")
        lines.append("")

    if sectors_str or sector_pe_info:
        lines.append("## 板块信息")
        if sectors_str:
            lines.append(f"- 所属板块: {sectors_str}")
        if sector_pe_info:
            for sn, sinfo in sector_pe_info.items():
                slabel = sinfo.get('sector_label', sn)
                mpe = sinfo.get('median_pe')
                mpb = sinfo.get('median_pb')
                spe = sinfo.get('stock_pe')
                spb = sinfo.get('stock_pb')
                if mpe:
                    lines.append(f"- {slabel} 中位PE: {mpe}")
                if mpb:
                    lines.append(f"- {slabel} 中位PB: {mpb}")
                if spe:
                    lines.append(f"- 个股PE: {spe}（相对板块 {'偏低' if spe < mpe else '偏高'}）" if mpe else f"- 个股PE: {spe}")
                if spb:
                    lines.append(f"- 个股PB: {spb}（相对板块 {'偏低' if spb < mpb else '偏高'}）" if mpb else f"- 个股PB: {spb}")
        lines.append("")

    lines.append("请基于以上数据，从历史对比和板块对比两个维度综合分析该股票当前的估值水平。")
    lines.append("特别注意：如果公司增速在持续下降，当前低PE/PB百分位可能不代表低估，而是市场对未来增速放缓的合理定价。请在分析中结合营收/利润增速趋势判断当前估值是否合理，而非仅依赖历史百分位。")
    lines.append("在板块估值分析中，请结合该板块的特点（如白酒板块高毛利、银行板块低PE等）给出判断。")
    lines.append("【利润质量分析】请务必关注利润的现金含量：如果净利润高增长但每股经营现金流持续为负（净现比<0），说明利润是\"纸面利润\"——可能来自存货涨价带来的账面收益或应收账款扩张，实际经营并未产生现金流入。结合存货周转天数变化判断：若存货周转天数持续上升同时毛利率飙升，往往是囤积低价存货高价卖出的一次性收益，待存货耗尽、新购高价原材料投入生产后，利润可能大幅回落甚至亏损。请在财务估值分析段中重点讨论这一风险。")
    lines.append("【存货性质判断】注意区分暂时性现金流问题与结构性现金流问题：如果经营现金流仅在个别季度为负（过去6季度中负值占比<30%），其余季度均为正，可能是公司主动囤货导致的暂时性现金流出（如预期原材料涨价提前备货），风险较低；若经营现金流在多个季度持续为负或正值极少（占比>=50%），则说明存在结构性问题（如产品滞销、应收账款恶化），风险较高。请结合现金流正负分布模式分析，并在财务分析段区分这两种情况。")

    return "\n".join(lines)
