# -*- coding: utf-8 -*-
"""资讯 + 公告抓取（无 key、无 LLM）。

资讯：RSS 检索（Bing News 为主，Google News 兜底），只取标题 / 媒体 / 时间 / 链接。
公告：东方财富公告库（ann_type=H，港交所披露），标题 + 日期 + 原文链接。
"""
import datetime
import email.utils
import re
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET

from common import FetchError, http_get, http_get_json


# ---------------------------------------------------------------- 资讯 RSS
BING_RSS = "https://www.bing.com/news/search?q=%s&format=rss&count=20&setlang=zh-CN&cc=cn"
GOOGLE_RSS = "https://news.google.com/rss/search?q=%s&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"

# 标题里出现这些词，说明与公司经营相关（仅用于排序，不做判断）
BIZ_KEYWORDS = ("签约", "合作", "中标", "订单", "发布", "上市", "回购", "增持", "减持", "配股",
                "业绩", "财报", "盈警", "盈喜", "异动", "纳入", "评级", "目标价", "解禁",
                "融资", "收购", "并购", "大模型", "智能体", "算力")
# 纯盘面综述类，只有当标题里带公司名时才保留
NOISE_KEYWORDS = ("港股午评", "港股收评", "港股收盘", "港股开盘", "早报", "晚报", "复盘",
                  "南向资金", "恒指", "恒生科技指数", "ETF", "新股申购")


def _aliases(company):
    """公司名 → 可用于匹配的别名列表。"""
    name = company["name"]
    out = {name, name.replace("-W", "").replace("-", ""), company.get("en", "")}
    for tok in re.split(r"[ \u3000]+", name):
        if len(tok) >= 2:
            out.add(tok)
    out.add(company["code"])
    return {a.strip() for a in out if a and len(a.strip()) >= 2}


def _clean_title(t):
    t = re.sub(r"<[^>]+>", "", t or "")
    for a, b in (("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"), ("&lt;", "<"), ("&gt;", ">")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip()


def _parse_date(s):
    if not s:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(s)
        if dt.tzinfo:
            dt = dt.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
        return dt.date()
    except (TypeError, ValueError):
        return None


def _rss_items(xml_text):
    """解析 RSS，返回 [(title, link, source, date)]。"""
    items = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return items
    for node in root.iter():
        if not node.tag.endswith("item"):
            continue
        title = link = src = pub = ""
        for ch in node:
            tag = ch.tag.split("}")[-1].lower()
            if tag == "title":
                title = ch.text or ""
            elif tag == "link":
                link = (ch.text or "").strip()
            elif tag == "pubdate":
                pub = ch.text or ""
            elif tag == "source":
                src = (ch.text or "").strip()
        if title and link:
            items.append((_clean_title(title), link, src, _parse_date(pub)))
    return items


# ---------------------------------------------------------------- 资讯：东财个股资讯（主源）
EM_STOCK_NEWS = ("https://np-listapi.eastmoney.com/comm/web/getListInfo"
                 "?client=web&biz=web_stock_news&mTypeAndCode=116.%s&type=1"
                 "&page_index=1&page_size=%d&req_trace=%s")


def _norm(s):
    return re.sub(r"[\s\-_—·・|丨丨]+", "", (s or "")).lower()


def _relevant(title, aliases):
    t = _norm(title)
    return any(_norm(a) and _norm(a) in t for a in aliases)


def fetch_em_stock_news(company, days=0, page_size=50):
    """东方财富「个股资讯」接口。days=0 表示不限时间，直接取最新。
    相关性评分：标题含公司名 3分；异动/概念类 2分；纯盘面综述且不含名 → 丢弃。
    """
    since = (datetime.date.today() - datetime.timedelta(days=days)) if days else None
    aliases = _aliases(company)
    url = EM_STOCK_NEWS % (company["code"], page_size, uuid.uuid4())
    try:
        js = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/hk/%s.html" % company["code"]})
    except FetchError:
        return []
    items = ((js.get("data") or {}).get("list")) or []
    out, seen = [], set()
    for it in items:
        title = _clean_title(it.get("Art_Title") or "")
        link = it.get("Art_Url") or it.get("Art_OriginUrl") or ""
        if not title or not link:
            continue
        d = _parse_date_simple(it.get("Art_ShowTime"))
        if since and d and d < since:
            continue

        named = _relevant(title, aliases)
        noisy = any(k in title for k in NOISE_KEYWORDS) and not named
        if noisy:
            continue
        score = 3 if named else (2 if any(k in title for k in ("异动", "概念", "板块", "大涨", "大跌")) else 1)

        key = re.sub(r"\W+", "", title)[:40]
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "title": title,
            "url": link,
            "source": "东方财富",
            "date": d.isoformat() if d else "",
            "note_date": (d.isoformat() if d else ""),
            "score": score,
            "named": named,
            "hot": any(k in title for k in BIZ_KEYWORDS),
        })
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def _parse_date_simple(s):
    m = re.match(r"(\d{4}-\d{2}-\d{2})", (s or "").strip())
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def fetch_news(company, days=0, limit=2):
    """最新资讯：东财个股资讯为主，RSS 补充。
    默认不限时间（days=0）——取最近几条，日期随标题展示；不再因“不是今天”而丢掉。
    排序：标题含公司名 > 异动/概念 > 其他，再按时间倒序。
    """
    since = (datetime.date.today() - datetime.timedelta(days=days)) if days else None
    aliases = _aliases(company)
    out = fetch_em_stock_news(company, days=days)

    if not any(x.get("named") for x in out):      # 东财没有点名新闻，去 RSS 补
        q = urllib.parse.quote('"%s" 港股' % company["name"].replace("-W", ""))
        raw = []
        for url in (BING_RSS % q, GOOGLE_RSS % q):
            try:
                raw = _rss_items(http_get(url, timeout=25, tries=2))
            except FetchError:
                raw = []
            if raw:
                break
        seen = {re.sub(r"\W+", "", x["title"])[:40] for x in out}
        for title, link, src, d in raw:
            if since and d and d < since:
                continue
            if not _relevant(title, aliases):
                continue
            key = re.sub(r"\W+", "", title)[:40]
            if key in seen:
                continue
            if not src and " - " in title:
                title, _, src = title.rpartition(" - ")
            seen.add(key)
            out.append({"title": title.strip(), "url": link, "source": src or "新闻",
                        "date": d.isoformat() if d else "", "note_date": d.isoformat() if d else "",
                        "score": 3, "named": True,
                        "hot": any(k in title for k in BIZ_KEYWORDS)})

    out.sort(key=lambda x: (x.get("score", 0), x["date"]), reverse=True)
    # 近似标题去重（同一事件多发）
    dedup, seen = [], set()
    for n in out:
        sig = re.sub(r"\W+", "", n["title"])[:14]
        if sig in seen:
            continue
        seen.add(sig)
        dedup.append(n)
    return dedup[:limit]


def fetch_all_news(companies, days=0, limit=2):
    out = {}
    for c in companies:
        out[c["code"]] = fetch_news(c, days=days, limit=limit)
        time.sleep(0.12)
    return out


# ---------------------------------------------------------------- 公告
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
