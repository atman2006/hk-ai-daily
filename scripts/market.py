# -*- coding: utf-8 -*-
"""行情 / 市值 / PS(TTM) 取数（东方财富 + 新浪指数）。"""
import json
import os
import time

from common import CACHE_DIR, FetchError, http_get, http_get_json, load_json, num, save_json

QUOTE_FIELDS = "f2,f3,f4,f6,f9,f12,f14,f20,f21,f23,f124"
FIN_TTL_DAYS = 7
FX_TO_HKD = {"HKD": 1.0, "CNY": 1.10, "RMB": 1.10, "USD": 7.80}


def fetch_quotes(codes):
    """一次请求取全部标的：价格/涨跌幅/成交额/总市值/PE/PB。"""
    secids = ",".join("116." + c for c in codes)
    url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&invt=2"
           "&secids=%s&fields=%s" % (secids, QUOTE_FIELDS))
    data = (http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"}).get("data") or {})
    out = {}
    for d in (data.get("diff") or []):
        code = d.get("f12")
        if not code:
            continue
        ts = d.get("f124")
        out[code] = {
            "price": num(d.get("f2")),
            "chg_pct": num(d.get("f3")),
            "chg": num(d.get("f4")),
            "turnover": num(d.get("f6")),
            "pe_dyn": num(d.get("f9")),
            "mcap_total": num(d.get("f20")),
            "mcap_float": num(d.get("f21")),
            "pb": num(d.get("f23")),
            "quote_ts": int(ts) if ts else None,
        }
    return out


def fetch_benchmarks(symbols):
    """新浪指数（需 Referer）。返回 [{symbol,label,name,last,chg,chg_pct,date,time}]"""
    url = "https://hq.sinajs.cn/list=" + ",".join(s["symbol"] for s in symbols)
    body = http_get(url, headers={"Referer": "https://finance.sina.com.cn"}, encoding="gbk")
    rows = {}
    for line in body.splitlines():
        if "=" not in line:
            continue
        key = line.split("=")[0].strip().replace("var hq_str_", "")
        val = line.split("=", 1)[1].strip().strip(";").strip('"')
        f = val.split(",")
        if len(f) < 9:
            continue
        rows[key] = {
            "name": f[1],
            "last": num(f[6]),
            "chg": num(f[7]),
            "chg_pct": num(f[8]),
            "date": f[17] if len(f) > 17 else "",
            "time": f[18] if len(f) > 18 else "",
        }
    out = []
    for s in symbols:
        r = rows.get(s["symbol"], {})
        out.append({"symbol": s["symbol"], "label": s["label"], **r})
    return out


# ---------------------------------------------------------------- 财务 / PS
def _fin_url(code):
    return ("https://datacenter.eastmoney.com/securities/api/data/v1/get"
            "?reportName=RPT_HKF10_FN_MAININDICATOR"
            "&columns=SECUCODE,SECURITY_CODE,REPORT_DATE,REPORT_TYPE,CURRENCY,OPERATE_INCOME,"
            "PE_TTM,PB_TTM,TOTAL_MARKET_CAP&pageSize=10&sortColumns=REPORT_DATE&sortTypes=-1"
            "&filter=(SECUCODE%%3D%%22%s.HK%%22)" % code)


def fetch_fin(code):
    res = http_get_json(_fin_url(code)).get("result") or {}
    return res.get("data") or []


def ttm_revenue(rows):
    """(ttm_revenue, currency, basis)。中报用 上年年报 + 本期 - 上年同期。"""
    if not rows:
        return None, None, "无财务数据"
    ordered = sorted(rows, key=lambda r: str(r.get("REPORT_DATE", "")), reverse=True)
    latest = ordered[0]
    rd = str(latest.get("REPORT_DATE", ""))[:10]
    cur = latest.get("CURRENCY") or "HKD"
    oi = num(latest.get("OPERATE_INCOME"))
    if oi is None:
        return None, cur, "最新报告期无营业总收入"
    if rd.endswith("-12-31"):
        return oi, cur, "截至 %s 年报" % rd

    def find(d):
        for r in ordered:
            if str(r.get("REPORT_DATE", ""))[:10] == d:
                return r
        return None

    year = int(rd[:4])
    fy = find("%d-12-31" % (year - 1))
    prev = find("%d-%s" % (year - 1, rd[5:]))
    if fy and prev:
        a, b = num(fy.get("OPERATE_INCOME")), num(prev.get("OPERATE_INCOME"))
        if a is not None and b is not None:
            return a + oi - b, cur, "TTM 滚动至 %s" % rd
    return None, cur, "缺少上年同期，无法算 TTM（%s）" % rd


def load_fin_cache():
    return load_json(os.path.join(CACHE_DIR, "fin_cache.json"), {}) or {}


def get_financials(codes, refresh=False):
    cache = load_fin_cache()
    now = time.time()
    ttl = FIN_TTL_DAYS * 86400
    errors = []
    for c in codes:
        hit = cache.get(c)
        if hit and not refresh and (now - hit.get("fetched_at", 0)) < ttl:
            continue
        try:
            rows = fetch_fin(c)
            if rows:
                cache[c] = {"fetched_at": now, "rows": rows}
            else:
                errors.append("%s 空数据" % c)
        except FetchError as e:
            errors.append("%s %s" % (c, e))
        time.sleep(0.12)
    save_json(os.path.join(CACHE_DIR, "fin_cache.json"), cache)
    return cache, errors


def build_snapshot(watchlist, refresh_fin=False):
    """整合行情 + 财务，返回结构化快照。"""
    companies = watchlist["companies"]
    codes = [c["code"] for c in companies]
    quotes = fetch_quotes(codes)
    bench = fetch_benchmarks(watchlist["benchmarks"])
    fin, errors = get_financials(codes, refresh=refresh_fin)

    rows = []
    for c in companies:
        q = quotes.get(c["code"], {})
        ttm, cur, basis = ttm_revenue((fin.get(c["code"]) or {}).get("rows") or [])
        cap = q.get("mcap_total")
        ps = cap / (ttm * FX_TO_HKD.get(cur or "HKD", 1.0)) if (cap and ttm and ttm > 0) else None
        rows.append({
            "code": c["code"], "name": c["name"], "en": c.get("en", ""),
            "tier": c["tier"], "note": c.get("note", ""), "key": bool(c.get("key")),
            "price": q.get("price"), "chg_pct": q.get("chg_pct"), "chg": q.get("chg"),
            "turnover": q.get("turnover"), "mcap_hkd": cap,
            "mcap_yi": (cap / 1e8) if cap else None,
            "pe_dyn": q.get("pe_dyn"), "pb": q.get("pb"),
            "revenue_ttm": ttm, "revenue_ttm_yi": (ttm / 1e8) if ttm else None,
            "revenue_currency": cur, "ps_ttm": ps, "basis": basis,
            "quote_ts": q.get("quote_ts"),
        })

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "benchmarks": bench,
        "rows": rows,
        "errors": errors,
        "source": "eastmoney push2 / RPT_HKF10_FN_MAININDICATOR + sina index",
    }


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    wl = load_json(os.path.join(os.path.dirname(here), "config", "watchlist.json"))
    snap = build_snapshot(wl)
    print(json.dumps(snap, ensure_ascii=False, indent=1)[:2000])
