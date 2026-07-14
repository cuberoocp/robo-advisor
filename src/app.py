import sys
import time
import json
import threading
import queue
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd

from src.config import CACHE_DIR, get_llm_config
from src.database.models import get_conn, init_db
from src.database import cache as db
from src.database import report as rdb
from src.data.fetcher import (
    get_stock_info,
    get_daily_price,
    get_financial_data,
    get_financial_data_quarterly,
    search_stock,
)
from src.analysis.financial import calc_financial_metrics, calc_current_pe_pb, get_eps_bvps
from src.analysis import historical as historical_mod
from src.analysis.historical import calc_pe_pb_history, calc_price_range, calc_growth_trend, _calc_ops_risk_multiplier
from src.analysis.sector import get_sector_pe, get_sector_name
from src.agent.llm_client import chat
from src.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from src.report.formatter import format_markdown_report
from src.report import render as rrender

DATA_TIMEOUT = 60
LLM_TIMEOUT = 90


def _run_with_timeout(func, timeout, *args, **kwargs):
    result = [None]
    error = [None]
    done = [False]

    def wrapper():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            error[0] = e
        finally:
            done[0] = True

    t = threading.Thread(target=wrapper, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if not done[0]:
        return None
    if error[0]:
        raise error[0]
    return result[0]


def _analysis_worker(code: str, cache_dir: str, llm_cfg: dict, log_q: queue.Queue, sector_pe_info=None):
    """Run analysis in a background thread, logging progress to log_q."""
    import src.database.models as dbm
    import src.database.cache as dbc

    conn = dbm.get_conn(cache_dir)
    _t0 = [time.perf_counter()]
    _t_last = [time.perf_counter()]

    def log(idx, total, text, done=False, error=None, result=None):
        now = time.perf_counter()
        elapsed = now - _t0[0]
        step_time = now - _t_last[0]
        _t_last[0] = now
        log_q.put(dict(idx=idx, total=total, text=text, done=done,
                       error=error, result=result,
                       elapsed=elapsed, step_time=step_time))

    try:
        log(1, 8, "📡 获取股票基本信息...")
        # Wait for background cache to warm up (max 15s)
        for _ in range(15):
            if _fetcher.CODE_NAME_CACHE is not None:
                break
            time.sleep(1)
        info = _run_with_timeout(get_stock_info, DATA_TIMEOUT, code)
        if info is None:
            info = dbc.get_stock_info(conn, code)
        if info:
            dbc.save_stock_info(conn, info["code"], info["name"], "", "")
        else:
            log(1, 8, "❌ 未找到该股票", error="未找到股票信息")
            return
        log(1, 8, f"✅ {info['name']}（{info['code']}）")

        log(2, 8, "📈 获取历史行情数据...")
        latest_cached_date = dbc.get_latest_price_date(conn, code)
        from datetime import datetime, timedelta
        today_str = datetime.now().strftime("%Y-%m-%d")
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        is_fresh = latest_cached_date and latest_cached_date >= yesterday_str
        if not is_fresh:
            if latest_cached_date:
                log(2, 8, "  → 缓存数据已过期，增量获取...")
                next_day = (datetime.strptime(latest_cached_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
                new_df = _run_with_timeout(get_daily_price, DATA_TIMEOUT, code, start=next_day)
                if new_df is not None and not new_df.empty:
                    dbc.save_daily_price(conn, new_df, code)
                    log(2, 8, f"  → 增量更新 {len(new_df)} 条")
                else:
                    log(2, 8, "  → 无新数据")
            else:
                price_df = _run_with_timeout(get_daily_price, DATA_TIMEOUT, code, years=5)
                if price_df is None:
                    log(2, 8, "  ⚠️ 行情数据获取超时")
                    price_df = pd.DataFrame()
                elif not price_df.empty:
                    dbc.save_daily_price(conn, price_df, code)
                    log(2, 8, f"  → 从AKShare获取 {len(price_df)} 条日线数据")
        price_df = dbc.get_daily_price(conn, code, "2021-01-01")
        if not is_fresh and latest_cached_date and price_df.empty:
            price_df = _run_with_timeout(get_daily_price, DATA_TIMEOUT, code, years=5)
            if price_df is not None and not price_df.empty:
                dbc.save_daily_price(conn, price_df, code)
                log(2, 8, f"  → 完整获取 {len(price_df)} 条日线数据")

        log(3, 8, "📋 获取财务数据...")
        has_fin = dbc.has_financial_data(conn, code)
        if has_fin:
            fin_df = dbc.get_latest_financial_reports(conn, code)
            log(3, 8, f"  → 从缓存读取 {len(fin_df)} 期财报")
        else:
            fin_df = _run_with_timeout(get_financial_data, DATA_TIMEOUT, code)
            if fin_df is None:
                log(3, 8, "  ⚠️ 财务数据获取超时")
                fin_df = pd.DataFrame()
            elif not fin_df.empty:
                dbc.save_financial_report(conn, fin_df, code)
            log(3, 8, f"  → 从AKShare获取 {len(fin_df)} 期财报")

        log(4, 8, "🔢 计算财务指标...")
        metrics = calc_financial_metrics(fin_df)
        log(4, 8, "  → 完成")

        log(5, 8, "📅 获取季度财报...")
        has_q = dbc.has_quarterly_data(conn, code)
        if has_q:
            fin_df_q = dbc.get_quarterly_reports(conn, code)
            log(5, 8, f"  → 从缓存读取 {len(fin_df_q)} 期季度数据")
        else:
            fin_df_q = _run_with_timeout(get_financial_data_quarterly, DATA_TIMEOUT, code)
            if fin_df_q is not None and not fin_df_q.empty:
                dbc.save_quarterly_reports(conn, fin_df_q, code)
                log(5, 8, f"  → 从AKShare获取 {len(fin_df_q)} 期季度数据")
        if fin_df_q is None or fin_df_q.empty:
            fin_df_q = fin_df
            log(5, 8, "  → 季度数据不可用，使用年度数据")

        log(6, 8, "📊 计算历史估值百分位...")
        current_price = price_df.iloc[-1]["close"] if not price_df.empty else 0
        pe_pb = calc_current_pe_pb(current_price, fin_df, fin_df_q)
        history_analysis = calc_pe_pb_history(price_df, fin_df, fin_df_q)
        log(6, 8, f"  → PE={pe_pb.get('PE')}, PB={pe_pb.get('PB')}")

        pe_analysis = history_analysis.get("PE历史", {})
        pb_analysis = history_analysis.get("PB历史", {})

        eps, bvps = get_eps_bvps(fin_df, fin_df_q)
        growth_trend = calc_growth_trend(fin_df)
        roe = metrics.get("ROE(%)")
        ops_risk_mult = _calc_ops_risk_multiplier(metrics, growth_trend, fin_df_q, fin_df)
        price_range = {}  # will be recalculated with sector PE data in step 6

        pe_series, pb_series = historical_mod._calc_historical_pe_pb_series(price_df, fin_df, fin_df_q)
        pe_series = pe_series if pe_series is not None and not pe_series.empty else None
        pb_series = pb_series if pb_series is not None and not pb_series.empty else None

        log(7, 9, "🏷️ 检测所属板块...")
        # Pre-fetched in _start_analysis (main thread) — worker cannot call
        # ak.sw_index_second_info() due to threading issue (BeautifulSoup None)
        sector_pe_val = None
        sector_pb_val = None
        sector_name = None
        for sn, sinfo in (sector_pe_info or {}).items():
            sector_pe_val = sinfo.get('median_pe')
            sector_pb_val = sinfo.get('median_pb')
            sector_name = sinfo.get('sector_label')
            break
        # Cap sector PE for price calculation only (keep raw for LLM prompt)
        stock_pe = pe_pb.get('PE')
        sector_pe_capped = sector_pe_val
        if sector_pe_capped and stock_pe:
            sector_pe_capped = min(sector_pe_capped, stock_pe * 1.5, 60)
        sector_str = sector_name or ""
        log(7, 9, f"  → 板块: {sector_str or '未检测到'}")

        log(8, 9, "📊 获取板块估值数据...")
        if sector_pe_capped:
            log(8, 9, f"  → {sector_name} 中位PE={sector_pe_capped}, PB={sector_pb_val}")
        else:
            log(8, 9, "  → 板块估值数据不可用")

        price_range = calc_price_range(
            pe_analysis, pb_analysis, eps, bvps, current_price,
            growth_trend, roe, ops_risk_mult, sector_pe=sector_pe_capped,
        )
        if price_range and sector_name:
            price_range["_板块信息"] = {
                "sector_pe": sector_pe_val,
                "sector_pb": sector_pb_val,
                "sector_name": sector_name,
                "stock_pe": pe_pb.get('PE'),
                "stock_pb": pe_pb.get('PB'),
            }

        log(9, 9, "🤖 AI 分析中...")
        user_prompt = build_user_prompt(
            stock_info=info,
            price=current_price,
            financial_metrics=metrics,
            current_pe_pb=pe_pb,
            history_analysis=history_analysis,
            sectors_str=sector_str,
            price_range=price_range,
            sector_pe_info=sector_pe_info,
        )

        try:
            llm_result = _run_with_timeout(chat, LLM_TIMEOUT, messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ])
            if llm_result is None:
                llm_result = "⚠️ LLM 响应超时，请稍后重试或更换模型。"
        except Exception as e:
            llm_result = f"⚠️ LLM 调用失败: {e}\n\n请检查 API Key 配置是否正确。"

        report = format_markdown_report(
            stock_info=info,
            price=current_price,
            financial_metrics=metrics,
            current_pe_pb=pe_pb,
            history_analysis=history_analysis,
            industry_name=sector_str,
            llm_analysis=llm_result,
            price_range=price_range,
        )

        result = {
            "info": info,
            "price": current_price,
            "financial_metrics": metrics,
            "pe_pb": pe_pb,
            "history_analysis": history_analysis,
            "growth_trend": growth_trend,
            "sectors": [sector_str] if sector_str else [],
            "llm_analysis": llm_result,
            "report": report,
            "price_range": price_range,
            "price_df": price_df,
            "fin_df": fin_df,
            "fin_df_q": fin_df_q,
            "pe_series": pe_series,
            "pb_series": pb_series,
            "sector_pe_info": sector_pe_info,
        }

        import src.database.report as rdr
        try:
            rdr.save_report(
                conn, code, info["name"], current_price,
                price_range.get("综合合理价位", {}).get("估值系数"),
                price_range.get("综合合理价位", {}).get("低"),
                price_range.get("综合合理价位", {}).get("高"),
                pe_pb.get("PE"), pe_pb.get("PB"),
                pe_analysis.get("当前百分位(%)"),
                pb_analysis.get("当前百分位(%)"),
                sector_str, json.dumps(metrics, ensure_ascii=False),
                llm_result, report,
            )
        except Exception:
            pass

        log(9, 9, f"✅ 分析完成", done=True, result=result)

    except Exception as e:
        log(0, 9, f"❌ 分析出错: {e}", error=str(e))
    finally:
        conn.close()

st.set_page_config(
    page_title="A股估值分析助手",
    page_icon="📊",
    layout="wide",
)

conn = get_conn(CACHE_DIR)
init_db(conn)

llm_cfg = get_llm_config()

# Warm cache in background so first analysis doesn't timeout
import src.data.fetcher as _fetcher
threading.Thread(target=_fetcher._get_code_name_map, daemon=True).start()

st.markdown("""
<style>
    .stApp { background: #f5f7fa; }
    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 2rem 2rem 1.5rem 2rem;
        border-radius: 16px;
        margin: -1rem -1rem 1.5rem -1rem;
        color: white;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    }
    .main-header h1 { color: white !important; font-size: 1.8rem !important; margin: 0 !important; font-weight: 700; }
    .main-header p { color: rgba(255,255,255,0.7) !important; margin: 0.3rem 0 0 0 !important; font-size: 0.9rem; }
    .card {
        background: white;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        border: 1px solid #e8ecf1;
    }
    .card h3 { margin: 0 0 0.8rem 0; font-size: 1rem; color: #1a1a2e; font-weight: 600; }
    .percentile-low { color: #059669; font-weight: 700; }
    .percentile-mid { color: #d97706; font-weight: 700; }
    .percentile-high { color: #dc2626; font-weight: 700; }
    div[data-testid="stStatusWidget"] { background: white !important; border: 1px solid #e8ecf1 !important; border-radius: 12px !important; }
    section[data-testid="stSidebar"] { background: white !important; border-right: 1px solid #e8ecf1 !important; }
    .stMetric { background: white; border-radius: 10px; padding: 0.8rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04); border: 1px solid #e8ecf1; }
    .stMetric label { font-size: 0.75rem !important; color: #6b7280 !important; }
    .stMetric .value { font-size: 1.3rem !important; font-weight: 700 !important; }
    .stSelectbox label, .stTextInput label { font-weight: 600 !important; color: #374151 !important; }
    h2 { font-size: 1.2rem !important; font-weight: 600 !important; color: #1a1a2e !important; }
    .report-card { background: white; border-radius: 8px; padding: 0.6rem 1rem; margin-bottom: 0.4rem; border: 1px solid #e8ecf1; cursor: pointer; }
    .report-card:hover { border-color: #0f3460; box-shadow: 0 1px 6px rgba(0,0,0,0.1); }
    .tag { display: inline-block; background: #e8ecf1; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 0.75rem; margin: 0.1rem; }
    .stButton>button[kind="secondary"] { font-size: 0.8rem !important; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header"><h1>📊 A股估值分析助手</h1><p>多维基本面 + AI 的 A 股估值分析工具</p></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 设置")

    provider = st.selectbox(
        "LLM 供应商",
        ["deepseek", "openai", "qwen", "ollama"],
        index=["deepseek", "openai", "qwen", "ollama"].index(llm_cfg["provider"]),
    )

    model = st.text_input("模型名称", value=llm_cfg["model"])
    api_key = st.text_input("API Key", value=llm_cfg["api_key"], type="password")

    if st.button("保存配置"):
        from dotenv import set_key
        env_path = Path(".env")
        if not env_path.exists():
            env_path.write_text("")
        set_key(str(env_path), "LLM_PROVIDER", provider)
        set_key(str(env_path), "LLM_MODEL", model)
        if api_key:
            set_key(str(env_path), "LLM_API_KEY", api_key)
        st.success("配置已保存，刷新后生效")
        st.rerun()

    st.divider()
    st.caption(f"缓存路径: `{CACHE_DIR}`")

tab1, tab2 = st.tabs(["🔍 分析", "📋 报告一览"])


def _start_analysis(code):
    st.session_state.analysis_code = code
    st.session_state.analysis_log_q = queue.Queue()
    st.session_state.analysis_done = False
    st.session_state.analysis_error = None
    st.session_state.analysis_result_data = None
    st.session_state.analysis_lines = []
    st.session_state.analysis_start_time = time.time()
    sector_pe_info = st.session_state.get("_sector_cache") or {}
    t = threading.Thread(
        target=_analysis_worker,
        args=(code, CACHE_DIR, get_llm_config(), st.session_state.analysis_log_q, sector_pe_info),
        daemon=True,
    )
    t.start()


with tab1:
    code_input = st.text_input(
        "输入股票代码或名称",
        placeholder="例如: 600519（贵州茅台）、000858（五粮液）",
    ).strip()

    code = None
    if code_input:
        if not code_input.isdigit() and len(code_input) < 6:
            results = search_stock(code_input)
            if results:
                selected = st.selectbox(
                    "找到多个匹配，请选择：",
                    results,
                    format_func=lambda x: f"{x['code']} - {x['name']}",
                )
                code = selected["code"]
            else:
                st.error(f"未找到匹配 {code_input} 的股票")
                st.stop()
        else:
            code = code_input.zfill(6)[:6]

    if code:
        sector_name = get_sector_name(code)
        pe_info = get_sector_pe(code, sector_name)
        st.session_state["_sector_cache"] = pe_info
        if sector_name:
            st.markdown(
                "<div style='margin-bottom:0.5rem'>所属板块：<span class='tag'>%s</span></div>" % sector_name,
                unsafe_allow_html=True,
            )

    if code and st.button("🔍 开始分析", type="primary", use_container_width=True):
        st.session_state.last_code = code
        _start_analysis(code)
        st.rerun()

    # ── 后台分析进度轮询 ──
    if st.session_state.get("analysis_log_q") is not None and not st.session_state.get("analysis_done"):
        t_start = st.session_state.get("analysis_start_time", time.time())
        if "analysis_start_time" not in st.session_state:
            st.session_state.analysis_start_time = t_start

        q = st.session_state.analysis_log_q
        new_lines = []
        while True:
            try:
                msg = q.get_nowait()
                if msg.get("done"):
                    st.session_state.analysis_result_data = msg["result"]
                    st.session_state.analysis_done = True
                    st.session_state.analysis_log_q = None
                    break
                if msg.get("error"):
                    st.session_state.analysis_error = msg["error"]
                    st.session_state.analysis_done = True
                    st.session_state.analysis_log_q = None
                    break
                new_lines.append((msg["idx"], msg["total"], msg["text"], msg.get("elapsed", 0), msg.get("step_time", 0)))
            except queue.Empty:
                break
        if new_lines:
            st.session_state.analysis_lines.extend(new_lines)

        # ── 渲染进度（含实时耗时） ──
        lines = st.session_state.analysis_lines
        live_elapsed = time.time() - t_start
        status = st.status("分析中...", expanded=True)
        status.write(f"⏱️ 已耗时 {live_elapsed:.0f}s")
        if lines:
            last = lines[-1]
            progress_val = last[0] / last[1] if last[1] > 0 else 0
            st.progress(progress_val, text=f"步骤 {last[0]}/{last[1]}  ({live_elapsed:.0f}s)")
            for idx, total, text, elapsed, step_time in lines:
                status.write(f"[{idx}/{total}] ({elapsed:5.1f}s, +{step_time:4.1f}s) {text}")
        else:
            st.progress(0.0, text=f"等待中... ({live_elapsed:.0f}s)")

        if st.session_state.get("analysis_done"):
            err = st.session_state.get("analysis_error")
            if err:
                status.update(label=f"❌ 分析失败（{live_elapsed:.0f}s）", state="error")
            elif st.session_state.get("analysis_result_data"):
                st.session_state.result = st.session_state.analysis_result_data
                status.update(label=f"✅ 分析完成（{live_elapsed:.0f}s）", state="complete", expanded=False)
            st.rerun()
        else:
            time.sleep(0.5)
            st.rerun()

    result = st.session_state.get("result", {})

    if result:
        if "error" in result:
            st.error(result["error"])
        else:
            r = result
            rrender.render_report(
                stock_name=r["info"]["name"],
                stock_code=r["info"]["code"],
                price=r["price"],
                price_df=r.get("price_df"),
                fin_df=r.get("fin_df"),
                fin_df_q=r.get("fin_df_q"),
                pe_series=r.get("pe_series"),
                pb_series=r.get("pb_series"),
                metrics=r.get("financial_metrics", {}),
                pe_pct=r.get("history_analysis", {}).get("PE历史", {}).get("当前百分位(%)"),
                pb_pct=r.get("history_analysis", {}).get("PB历史", {}).get("当前百分位(%)"),
                coef=r.get("price_range", {}).get("综合合理价位", {}).get("估值系数"),
                price_low=r.get("price_range", {}).get("综合合理价位", {}).get("低"),
                price_high=r.get("price_range", {}).get("综合合理价位", {}).get("高"),
                llm_text=r["llm_analysis"],
                sectors=r.get("sectors"),
                growth_trend=r.get("growth_trend"),
                price_range=r.get("price_range"),
                pe_value=r.get("pe_pb", {}).get("PE"),
            )

    if not code and not result and not st.session_state.get("analysis_log_q"):
        st.info("👆 输入股票代码或名称开始分析")
        st.divider()
        st.subheader("示例股票")
        examples = ["600519", "000858", "300750", "601318", "000333"]
        cols = st.columns(len(examples))
        for col, code in zip(cols, examples):
            info = db.get_stock_info(conn, code)
            label = f"{info['name']}({code})" if info else code
            if col.button(label, key=code):
                st.session_state.last_code = code
                _start_analysis(code)
                st.rerun()

with tab2:
    view_id = st.session_state.get("view_report_id")

    if view_id is not None:
        report = rdb.get_report_by_id(conn, view_id)
        if report:
            col_back, col_re = st.columns([1, 1])
            with col_back:
                if st.button("← 返回报告一览"):
                    st.session_state.view_report_id = None
                    st.rerun()
            with col_re:
                if st.button("🔄 重新分析", type="primary"):
                    st.session_state.last_code = report["code"]
                    _start_analysis(report["code"])
                    st.session_state.view_report_id = None
                    st.rerun()

            metrics = json.loads(report["metrics_json"]) if report.get("metrics_json") else {}
            sectors = report.get("sectors", "").split(",") if report.get("sectors") else []
            import json

            with st.status("📥 读取数据渲染图表...", expanded=False) as s:
                price_df = _run_with_timeout(get_daily_price, DATA_TIMEOUT, report["code"], years=5)
                price_df = price_df if price_df is not None else pd.DataFrame()
                fin_df = _run_with_timeout(get_financial_data, DATA_TIMEOUT, report["code"])
                fin_df = fin_df if fin_df is not None else pd.DataFrame()
                s.write("→ 获取季度财务数据...")
                fin_df_q = _run_with_timeout(get_financial_data_quarterly, DATA_TIMEOUT, report["code"])
                if fin_df_q is None or fin_df_q.empty:
                    fin_df_q = fin_df
                s.write("→ 计算PE/PB序列...")
                pe_series, pb_series = historical_mod._calc_historical_pe_pb_series(price_df, fin_df, fin_df_q)
                pe_series = pe_series if pe_series is not None and not pe_series.empty else None
                pb_series = pb_series if pb_series is not None and not pb_series.empty else None
                s.update(label="✓ 数据就绪", state="complete")

            rrender.render_report(
                stock_name=report["stock_name"],
                stock_code=report["code"],
                price=report["price"],
                price_df=price_df,
                fin_df=fin_df,
                fin_df_q=fin_df_q,
                pe_series=pe_series,
                pb_series=pb_series,
                metrics=metrics,
                pe_pct=report.get("pe_pct"),
                pb_pct=report.get("pb_pct"),
                coef=report.get("valuation_coef"),
                price_low=report.get("price_range_low"),
                price_high=report.get("price_range_high"),
                llm_text=report["llm_analysis"],
                sectors=sectors,
            )
        else:
            st.session_state.view_report_id = None
            st.rerun()
    else:
        st.subheader("📋 分析报告一览")
        df = rdb.get_reports(conn)
        if df.empty:
            st.info("暂无保存的分析报告，先在「分析」页面运行一次分析。")
        else:
            sort_by = st.radio("排序方式", ["报告时间", "估值系数", "股票代码"], horizontal=True)
            asc = st.checkbox("升序", value=False)
            sort_map = {"报告时间": "created_at", "估值系数": "valuation_coef", "股票代码": "code"}
            col = sort_map[sort_by]
            df = df.sort_values(col, ascending=asc)

            for _, row in df.iterrows():
                coef = row["valuation_coef"]
                if pd.notna(coef):
                    css = "percentile-low" if coef < 0.95 else "percentile-high" if coef > 1.05 else "percentile-mid"
                    icon = "❄️" if coef < 0.95 else "🔥" if coef > 1.05 else "⚡"
                    badge = '<span class="%s">%s %s</span>' % (css, round(coef, 3), icon)
                else:
                    badge = "-"
                sectors = (row["sectors"] or "").replace(",", "、")

                created = pd.to_datetime(row["created_at"]).strftime("%m-%d %H:%M") if pd.notna(row["created_at"]) else "-"
                row_key = "row_%s" % row["id"]
                cols = st.columns([2.2, 1.5, 1, 0.8, 0.8, 0.7])
                with cols[0]:
                    st.write("**%s**  (%s)" % (row["stock_name"], row["code"]))
                with cols[1]:
                    st.write(created)
                with cols[2]:
                    st.markdown('<span class="tag">%s</span>' % sectors if sectors else "-", unsafe_allow_html=True)
                with cols[3]:
                    st.write("%s元" % row["price"])
                with cols[4]:
                    st.markdown(badge, unsafe_allow_html=True)
                with cols[5]:
                    if st.button("查看", key=row_key):
                        st.session_state.view_report_id = row["id"]
                        st.rerun()

conn.close()
