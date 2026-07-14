import json
import os
import time

import akshare as ak
import requests

_CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'cache')
_SW_CLF_PATH = os.path.join(_CACHE_DIR, 'sw_classification.json')
_SW_MAP_PATH = os.path.join(_CACHE_DIR, 'sw_code_map.json')
_SW_NAMES_PATH = os.path.join(_CACHE_DIR, 'sw_names.json')

_sw_code_cache = None
_sw_stock_cache = None


def _ensure_sw_cache():
    """Load SW classification cache + build code→name mapping from static JSON."""
    global _sw_code_cache, _sw_stock_cache
    if _sw_stock_cache is not None:
        return

    if os.path.exists(_SW_CLF_PATH):
        try:
            with open(_SW_CLF_PATH, 'r', encoding='utf-8') as f:
                _sw_stock_cache = json.load(f)
        except Exception:
            pass

    if _sw_stock_cache is not None and os.path.exists(_SW_MAP_PATH):
        try:
            with open(_SW_MAP_PATH, 'r', encoding='utf-8') as f:
                _sw_code_cache = json.load(f)
            if _sw_stock_cache:
                return
        except Exception:
            pass

    # Download SW classification if missing
    if not _sw_stock_cache:
        import warnings
        warnings.filterwarnings('ignore')
        original_get = requests.get
        def _patched_get(url, **kwargs):
            kwargs['verify'] = False
            return original_get(url, **kwargs)
        requests.get = _patched_get
        try:
            clf = ak.stock_industry_clf_hist_sw()
            latest = clf.sort_values('update_time').groupby('symbol').last().reset_index()
            _sw_stock_cache = dict(zip(latest['symbol'].astype(str), latest['industry_code'].astype(str)))
            os.makedirs(_CACHE_DIR, exist_ok=True)
            with open(_SW_CLF_PATH, 'w', encoding='utf-8') as f:
                json.dump(_sw_stock_cache, f, ensure_ascii=False)
        except Exception as e:
            _sw_stock_cache = {}
            return
        finally:
            requests.get = original_get

    _sw_code_cache = _build_map_from_names()
    if _sw_code_cache:
        try:
            with open(_SW_MAP_PATH, 'w', encoding='utf-8') as f:
                json.dump(_sw_code_cache, f, ensure_ascii=False)
        except Exception:
            pass


def _build_map_from_names() -> dict:
    """Build {6-digit-code: [name]} from sw_names.json + prefix fallback."""
    if not os.path.exists(_SW_NAMES_PATH):
        return {}

    with open(_SW_NAMES_PATH, 'r', encoding='utf-8') as f:
        names = json.load(f)
    l1_prefix = names.get('l1', {})
    l2_prefix = names.get('l2', {})

    all_codes = set()
    if os.path.exists(_SW_CLF_PATH):
        try:
            with open(_SW_CLF_PATH, 'r', encoding='utf-8') as f:
                all_codes = set(json.load(f).values())
        except Exception:
            pass

    result = {}
    for sw_code in all_codes:
        name = l2_prefix.get(sw_code[:4]) or l1_prefix.get(sw_code[:2])
        if name:
            result[sw_code] = [name]
    return result


def get_sector_name(code: str) -> str:
    """Get Shenwan industry name for a stock code from static cache (no API call)."""
    _ensure_sw_cache()
    if not _sw_stock_cache or code not in _sw_stock_cache:
        return ""
    sw_code = _sw_stock_cache.get(code)
    if not sw_code or not _sw_code_cache:
        return ""
    resolved = _sw_code_cache.get(sw_code)
    if not resolved:
        return ""
    return resolved[0]


def _fetch_sw_source(max_retries=5, delay=3.0):
    """Fetch SW index info with retry. Tries L2 first, falls back to L1."""
    for attempt in range(max_retries):
        try:
            src = ak.sw_index_second_info()
            if src is not None and not src.empty:
                return src
        except Exception:
            pass
        if attempt < max_retries - 1:
            time.sleep(delay)
    for attempt in range(max_retries):
        try:
            src = ak.sw_index_first_info()
            if src is not None and not src.empty:
                return src
        except Exception:
            pass
        if attempt < max_retries - 1:
            time.sleep(delay)
    return None


def get_sector_pe(code: str, sector_label: str = "") -> dict:
    """Get Shenwan industry PE/PB for a stock code.
    Returns {code: {sector_label, median_pe?, median_pb?}}.
    sector_label is always included; PE/PB may be absent when API fails.
    """
    source = _fetch_sw_source()
    info = {'sector_label': sector_label}
    if source is not None and not source.empty and sector_label:
        try:
            row = source[source['行业名称'] == sector_label]
            if not row.empty:
                r = row.iloc[0]
                pe_ttm = float(r['TTM(滚动)市盈率']) if 'TTM(滚动)市盈率' in source.columns else None
                info['median_pe'] = pe_ttm or float(r['静态市盈率'])
                info['median_pb'] = float(r['市净率'])
        except Exception:
            pass
    return {code: info}
