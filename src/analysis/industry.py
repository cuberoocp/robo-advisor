import re
from typing import Optional
import urllib.request
import akshare as ak

_INDUSTRY_LIST_CACHE = None


def get_industry_list() -> list:
    global _INDUSTRY_LIST_CACHE
    if _INDUSTRY_LIST_CACHE is not None:
        return _INDUSTRY_LIST_CACHE
    try:
        df = ak.stock_board_industry_name_ths()
        _INDUSTRY_LIST_CACHE = df["name"].dropna().tolist()
    except Exception:
        _INDUSTRY_LIST_CACHE = []
    return _INDUSTRY_LIST_CACHE


def auto_detect_industry(code: str) -> Optional[str]:
    url = (
        f"https://vip.stock.finance.sina.com.cn/corp/go.php/"
        f"vCI_CorpOtherInfo/stockid/{code}/menu_num/2.phtml"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        text = resp.read().decode("gbk")
        m = re.search(
            r"同行业个股\s*</td>\s*</tr>[^<]*<tr>\s*<td[^>]*>\s*([^<]+)\s*</td>",
            text,
            re.DOTALL,
        )
        if m:
            raw = m.group(1).strip()
            ths_list = get_industry_list()
            # Best match: exact or contains
            for t in ths_list:
                if raw == t or raw in t or t in raw:
                    return t
            return raw
    except Exception:
        pass
    return None
