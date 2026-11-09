# -*- coding: utf-8 -*-
"""公告抓取（东方财富，ann_type=H 港股）。无 LLM、无 key，只取港交所披露的事实性公告标题。"""
import datetime
import re
import time
import urllib.parse

from common import FetchError, http_get_json

ANN_URL = ("https://np-anotice-stock.eastmoney.com/api/security/ann"
           "?sr=-1&page_size=%d&page_index=1&ann_type=H&client_source=web&stock_list=%s")
DETAIL_URL = "https://data.eastmoney.com/notices/detail/%s/%s.html"

# 视为「可能影响股价」的公告关键词（用于 01 核心观察的排序）
HOT_KEYWORDS = ("业绩", "盈警", "盈喜", "盈利", "亏损", "配股", "供股", "回购", "增持", "减持",
                "股权转让", "收购", "并购", "出售", "合作", "框架", "中标", "合同", "订单",
                "可转债", "授出", "行使", "期权", "股息", "分红", "停牌", "复牌", "配售", "定增")
# 例行公告：每月都会发，不当作「实质性披露」
ROUTINE_KEYWORDS = ("月报表", "翌日披露报表", "组织章程", "章程", "董事名单", "股东周年大会通告",
                    "重选董事", "委任表格", "代表委任")


def _parse_dt(s):
    s = (s or "").strip().replace("/", "-")
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def fetch_notices(code, page_size=15):
    """返回 [{code,title,date,column,url,hot}]，按日期倒序。"""
    url = ANN_URL % (page_size, code)
    try:
        js = http_get_json(url)
    except FetchError:
        return []
    items = ((js.get("data") or {}).get("list")) or []
    out = []
    for it in items:
        art = it.get("art_code")
        title = (it.get("title_ch") or it.get("title") or "").strip()
        if not art or not title:
            continue
        d = _parse_dt(it.get("notice_date") or it.get("display_time"))
        cols = it.get("columns") or [{}]
        col = (cols[0] or {}).get("column_name") or ""
        out.append({
            "code": code,
            "title": title,
            "date": d.isoformat() if d else "",
            "date_obj": d,
            "column": col,
            "url": DETAIL_URL % (code, art),
            "routine": any(k in title for k in ROUTINE_KEYWORDS),
            "hot": (not any(k in title for k in ROUTINE_KEYWORDS)) and any(k in title for k in HOT_KEYWORDS),
        })
    out.sort(key=lambda x: (x["date"], x["hot"]), reverse=True)
    return out


def fetch_all(codes, days=5, page_size=15):
    """按标的批量取公告，只保留最近 days 天内。返回 {code: [公告...]}"""
    today = datetime.date.today()
    since = today - datetime.timedelta(days=days)
    out = {}
    for c in codes:
        recent = [n for n in fetch_notices(c, page_size) if n["date_obj"] and n["date_obj"] >= since]
        out[c] = recent
        time.sleep(0.12)
    return out


def latest(n_list):
    return n_list[0] if n_list else None


def summarize(n_list, limit=2):
    """把公告列表压成一行要点：标题 + 日期。"""
    if not n_list:
        return ""
    parts = []
    for n in n_list[:limit]:
        parts.append("《%s》（%s）" % (n["title"], n["date"][5:]))
    return "；".join(parts)


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    got = fetch_all(["01384", "02513", "03317"], days=10)
    for k, v in got.items():
        print(k, len(v))
        for n in v[:3]:
            print("  ", n["date"], n["column"], n["title"][:40], n["url"])
