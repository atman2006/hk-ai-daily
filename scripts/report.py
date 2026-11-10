# -*- coding: utf-8 -*-
"""生成钉钉 markdown（01-06 分节）与本地 HTML 报告。全部规则化，无 LLM。"""
import datetime
import html
import os
import statistics

from common import fmt_amount, fmt_cap, fmt_pct, fmt_ps, hk_datetime_str, hk_today

TIER_LABEL = {1: "第一梯队", 2: "第二梯队", 3: "第三梯队"}
MODE_LABEL = {"close": "收盘", "early": "早盘前", "intraday": "盘中"}


def _pct_rows(rows):
    return [r for r in rows if r.get("chg_pct") is not None]


def _bench_line(benchmarks):
    parts = []
    for b in benchmarks:
        if b.get("last") is None:
            continue
        arrow = "🟢" if (b.get("chg_pct") or 0) >= 0 else "🔴"
        parts.append("%s **%s %.2f** %s%.2f%%" % (arrow, b["name"], b["last"],
                                                  "+" if (b.get("chg_pct") or 0) >= 0 else "-",
                                                  abs(b.get("chg_pct") or 0)))
    return " ｜ ".join(parts) if parts else "**指数数据缺失**"


def _dot(v):
    if v is None:
        return "⚪"
    return "🟢" if v >= 0 else "🔴"


def _mini_bar(v, vmax, width=10):
    n = int(round(abs(v) / vmax * width)) if vmax else 0
    return ("▇" * max(n, 1))


def _date_label(d, today):
    """把 2026-11-09 这类日期转成 今日/昨日/MM-DD。"""
    if not d:
        return ""
    if d == today:
        return "今日"
    try:
        dt = datetime.date.fromisoformat(d)
        if (datetime.date.fromisoformat(today) - dt).days == 1:
            return "昨日"
    except ValueError:
        pass
    return d[5:]


def build_markdown(snap, notices, news=None, mode="close", report_path="", report_url="", data_ts="", days=5):
    rows = snap["rows"]
    tiers = {1: [r for r in rows if r["tier"] == 1],
             2: [r for r in rows if r["tier"] == 2],
             3: [r for r in rows if r["tier"] == 3]}
    mode_cn = MODE_LABEL.get(mode, "收盘")
    today = hk_today()
    priced = _pct_rows(rows)
    ups = [r for r in priced if r["chg_pct"] > 0]
    downs = [r for r in priced if r["chg_pct"] < 0]
    median = statistics.median([r["chg_pct"] for r in priced]) if priced else 0.0

    # ---- 资讯 / 公告汇总
    news = news or {}
    deep_codes = [r["code"] for r in rows if r["tier"] in (1, 2)]
    deep_with_news = [c for c in deep_codes if notices.get(c)]
    deep_with_wire = [c for c in deep_codes if news.get(c)]
    today_wire = [c for c in deep_codes if any(n["date"] == today for n in (news.get(c) or []))]
    hot_news = []
    for c in deep_codes:
        for n in notices.get(c, []):
            if n["hot"]:
                hot_news.append((c, n))

    L = []
    # ---------- 抬头
    L.append("> " + _bench_line(snap["benchmarks"]))
    L.append("> 🗓 港股AI日报 ｜ 📦 覆盖 %d 家 ｜ ⏱ %s %s ｜ 📊 PS = 市值/TTM营收"
             % (len(rows), mode_cn, data_ts or today))
    if mode == "intraday":
        L.append("> ⚠️ 以上为**盘中快照**，非收盘价，收盘后以 17:05 那份为准")
    L.append("")

    # ---------- 01 核心观察
    L.append("### 🔥 01 · 核心观察")
    if priced:
        best = max(priced, key=lambda r: r["chg_pct"])
        worst = min(priced, key=lambda r: r["chg_pct"])
        L.append("- 🚀 **%s（%s）** %s：池内最强，市值 %sHKD、PS %s"
                 % (best["name"], best["code"], fmt_pct(best["chg_pct"]), fmt_cap(best["mcap_hkd"]), fmt_ps(best["ps_ttm"])))
        L.append("- 🩸 **%s（%s）** %s：池内最弱，市值 %sHKD、PS %s"
                 % (worst["name"], worst["code"], fmt_pct(worst["chg_pct"]), fmt_cap(worst["mcap_hkd"]), fmt_ps(worst["ps_ttm"])))
    L.append("- ⚖️ **涨跌结构**：%d 家上涨 / %d 家下跌，中位数 %s"
             % (len(ups), len(downs), fmt_pct(median)))
    if today_wire:
        L.append("- 📰 **今日新资讯**：%d/12 家有新闻（%s）"
                 % (len(today_wire), "、".join(_name_of(rows, c) for c in today_wire[:4])))
    else:
        L.append("- 📰 **今日新资讯**：今日暂无新增，下方为各家最新一条（带日期）")
    if hot_news:
        L.append("- 📢 **公告**：%s 有新公告（%s）"
                 % ("、".join(dict.fromkeys(_name_of(rows, c) for c, _ in hot_news)),
                    "；".join("《%s》" % h[1]["title"][:14] for h in hot_news[:2])))
    L.append("")

    # ---------- 02 / 03 逐家
    for tier, head_extra, icon in ((1, "（5 家 · 深挖）", "🥇"), (2, "（7 家）", "🥈")):
        L.append("### %s 0%d · %s%s" % (icon, tier + 1, TIER_LABEL[tier], head_extra))
        for r in tiers[tier]:
            tag = " 🔑" if r.get("key") else ""
            L.append("**%s**%s `%s`｜💵 **%.3f** %s**%s**｜🏷 **%sHKD**｜📊 **%s**"
                     % (r["name"], tag, r["code"], r["price"] or 0, _dot(r["chg_pct"]), fmt_pct(r["chg_pct"]),
                        fmt_cap(r["mcap_hkd"]), fmt_ps(r["ps_ttm"])))
            ns = notices.get(r["code"]) or []
            hot = [n for n in ns if n["hot"]]
            for n in hot[:1]:
                L.append("- 📢 《%s》%s [原文](%s)" % (n["title"], _date_label(n["date"], today), n["url"]))
            ws = news.get(r["code"]) or []
            if ws:
                for n in ws[:2]:
                    L.append("- 📰 %s（%s）[%s](%s)"
                             % (n["title"], _date_label(n["date"], today), n["source"][:4], n["url"]))
            elif not hot:
                L.append("- 💤 暂无相关新闻；%s" % (r["note"] or "行情异动待核"))
            L.append("")

    # ---------- 04 其他异动
    L.append("### ⚡ 04 · 其他异动")
    movers = [r for r in tiers[3] if r["chg_pct"] is not None and abs(r["chg_pct"]) >= 3]
    if movers:
        for r in sorted(movers, key=lambda r: -abs(r["chg_pct"])):
            L.append("- %s **%s** `%s` **%s**：成交 %s"
                     % (_dot(r["chg_pct"]), r["name"], r["code"], fmt_pct(r["chg_pct"]), fmt_amount(r["turnover"])))
    else:
        third = [r for r in tiers[3] if r["chg_pct"] is not None]
        if third:
            top = max(third, key=lambda r: abs(r["chg_pct"]))
            L.append("- 💤 第三梯队无 |涨跌| ≥ 3%% 异动（波动最大：%s %s）" % (top["name"], fmt_pct(top["chg_pct"])))
        else:
            L.append("- ⚪ 第三梯队无行情数据")
    L.append("")

    # ---------- 05 估值速览
    L.append("### 💎 05 · 估值速览")
    for t, icon in ((1, "🥇"), (2, "🥈"), (3, "🥉")):
        seg = " · ".join("%s %s/%s" % (r["name"], fmt_cap(r["mcap_hkd"]), fmt_ps(r["ps_ttm"]))
                         for r in tiers[t] if r["mcap_hkd"])
        if seg:
            L.append("- %s **%s**：%s" % (icon, TIER_LABEL[t], seg))
    L.append("")

    # ---------- 06 今日观察
    L.append("### 🧭 06 · 今日观察")
    obs = _observations(rows, tiers, notices, news=news, today=today)
    for o in obs:
        L.append("- " + o)
    L.append("")
    if report_url:
        L.append("📄 完整报告：[%s](%s)" % (os.path.basename(report_path or "report.html"), report_url))
    else:
        L.append("📄 完整报告（仓库内）：%s" % (report_path or "reports/"))
    return "\n".join(L)


def _name_of(rows, code):
    for r in rows:
        if r["code"] == code:
            return r["name"]
    return code


def _observations(rows, tiers, notices, news=None, today=""):
    obs = []
    priced = _pct_rows(rows)
    if priced:
        up = [r for r in priced if r["chg_pct"] > 0]
        med = statistics.median([r["chg_pct"] for r in priced])
        tone = "普涨" if len(up) >= len(priced) * 0.7 else ("普跌" if len(up) <= len(priced) * 0.3 else "分化")
        obs.append("⚖️ **板块结构**：%d/%d 家上涨，中位数 %s，整体%s；关注是否由权重股或单一事件驱动。"
                   % (len(up), len(priced), fmt_pct(med), tone))

    # 资讯密度
    news = news or {}
    today_wire, latest = [], None
    for tier in (1, 2):
        for r in tiers[tier]:
            for n in (news.get(r["code"]) or []):
                if not latest or n["date"] > latest[1]["date"]:
                    latest = (r["name"], n)
                if today and n["date"] == today and r["name"] not in today_wire:
                    today_wire.append(r["name"])
    if today_wire:
        obs.append("📰 **资讯面**：%s 今日有新消息，可对照股价看是否已透支；其余标的今日无新增。"
                   % "、".join(today_wire[:4]))
    elif latest:
        obs.append("📰 **资讯面**：今日无新增，各家最新为 %s（%s）《%s》。"
                   % (latest[0], _date_label(latest[1]["date"], today or ""), latest[1]["title"][:24]))

    # 公告面
    hot = []
    for tier in (1, 2):
        for r in tiers[tier]:
            for n in (notices.get(r["code"]) or []):
                if n["hot"]:
                    hot.append((r["name"], n))
    if hot:
        names = "、".join(dict.fromkeys(h[0] for h in hot[:4]))
        obs.append("📢 **公告面**：%s 有实质性披露（%s），需核对是否已被价格反映。"
                   % (names, "；".join("《%s》" % h[1]["title"][:16] for h in hot[:2])))
    else:
        obs.append("📢 **公告面**：第一/二梯队近期无实质性公告，当日波动更可能来自板块情绪。")

    # 估值极值（一二梯队）
    pool = [r for r in rows if r["tier"] in (1, 2) and r["ps_ttm"] and r["ps_ttm"] > 0]
    if pool:
        hi = max(pool, key=lambda r: r["ps_ttm"])
        lo = min(pool, key=lambda r: r["ps_ttm"])
        obs.append("💰 **估值分化**：%s PS %s 梯队内最高，%s PS %s 最低；同赛道估值差 %.0f 倍，定价锚仍在形成中。"
                   % (hi["name"], fmt_ps(hi["ps_ttm"]), lo["name"], fmt_ps(lo["ps_ttm"]),
                      hi["ps_ttm"] / lo["ps_ttm"] if lo["ps_ttm"] else 0))
    return obs[:3]


# ---------------------------------------------------------------- HTML
CSS = """
:root{--bg:#07090d;--panel:#0d1117;--panel2:#11161f;--line:#1d2733;--ink:#d7e0ea;--dim:#8b98a8;
--faint:#5d6b7a;--orange:#ff8c1a;--amber:#ffc94d;--up:#1fd475;--down:#ff4d5e;
--mono:Consolas,"SF Mono",monospace;--sans:"Microsoft YaHei","PingFang SC",sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.65}
.wrap{max-width:1080px;margin:0 auto;padding:24px 20px 60px}
header{border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:24px}
.kicker{font-family:var(--mono);font-size:11px;letter-spacing:.22em;color:var(--orange)}
h1{font-size:27px;font-weight:800;margin:6px 0 4px}
.meta{font-family:var(--mono);font-size:12px;color:var(--dim)}
h2{font-family:var(--mono);font-size:13px;letter-spacing:.18em;color:var(--orange);margin:30px 0 12px;
border-left:3px solid var(--orange);padding-left:10px}
.idx{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.card{background:var(--panel);border:1px solid var(--line);padding:14px 16px}
.card .n{font-size:12px;color:var(--dim)}
.card .v{font-family:var(--mono);font-size:23px;font-weight:700;margin:4px 0}
.card .c{font-family:var(--mono);font-size:13px}
.u{color:var(--up)}.d{color:var(--down)}
table{border-collapse:collapse;width:100%;background:var(--panel);border:1px solid var(--line)}
th{font-family:var(--mono);font-size:10.5px;color:var(--orange);text-align:left;padding:9px 10px;
border-bottom:1px solid var(--line);background:var(--panel2);white-space:nowrap}
td{padding:8px 10px;border-bottom:1px solid #161e28;font-size:12.5px;color:var(--dim);vertical-align:top}
tr:last-child td{border-bottom:0}
td.nm{color:var(--ink);font-weight:600;white-space:nowrap}
td.num,th.num{text-align:right;font-family:var(--mono);white-space:nowrap}
.code{font-family:var(--mono);color:var(--amber);font-size:11px}
.key{color:var(--orange);font-size:10px;border:1px solid var(--orange);padding:0 4px;margin-left:4px}
.news{background:var(--panel);border:1px solid var(--line);padding:12px 14px;margin-bottom:10px}
.news b{color:var(--ink)}
.news p{font-size:12.5px;color:var(--dim);margin-top:4px}
.news a{color:var(--amber);text-decoration:none;font-size:11.5px}
footer{margin-top:36px;padding-top:14px;border-top:1px dashed var(--line);
font-family:var(--mono);font-size:11px;color:var(--faint);text-align:center}
@media(max-width:640px){.idx{grid-template-columns:1fr}}
"""


def build_html(snap, notices, news=None, mode="close", data_ts="", days=5):
    rows = snap["rows"]
    mode_cn = MODE_LABEL.get(mode, "收盘")
    today = hk_today()
    e = html.escape

    idx = "".join(
        '<div class="card"><div class="n">%s</div><div class="v">%s</div><div class="c %s">%s · %s</div></div>'
        % (e(b.get("label", "")), ("%.2f" % b["last"]) if b.get("last") else "—",
           "u" if (b.get("chg_pct") or 0) >= 0 else "d", fmt_pct(b.get("chg_pct")),
           ("%+.2f" % (b.get("chg") or 0)))
        for b in snap["benchmarks"])

    def table(tier):
        trs = []
        for r in [x for x in rows if x["tier"] == tier]:
            cls = "u" if (r["chg_pct"] or 0) >= 0 else "d"
            key = '<span class="key">重点</span>' if r.get("key") else ""
            ws = (news or {}).get(r["code"]) or []
            if ws:
                w0 = ws[0]
                latest_news = '<a href="%s">%s</a> <span class="dim">%s · %s</span>' % (
                    w0["url"], e(w0["title"][:40]), e(_date_label(w0["date"], hk_today())), e(w0["source"][:8]))
            else:
                latest_news = "—"
            trs.append("<tr><td class='nm'>%s%s <span class='code'>%s</span></td>"
                       "<td class='num'>%s</td><td class='num %s'>%s</td><td class='num'>%s</td>"
                       "<td class='num'>%s</td><td class='num'>%s</td><td>%s</td></tr>"
                       % (e(r["name"]), key, r["code"],
                          ("%.3f" % r["price"]) if r["price"] else "—", cls, fmt_pct(r["chg_pct"]),
                          fmt_amount(r["turnover"]), fmt_cap(r["mcap_hkd"]), fmt_ps(r["ps_ttm"]), latest_news))
        return ("<table><thead><tr><th>公司 / 代码</th><th class='num'>收盘</th><th class='num'>涨跌幅</th>"
                "<th class='num'>成交额</th><th class='num'>总市值(HKD)</th><th class='num'>PS(TTM)</th>"
                "<th>最新资讯</th></tr></thead><tbody>" + "".join(trs) + "</tbody></table>")

    # 估值对比（一二梯队按 PS 排序）
    pool = sorted([r for r in rows if r["tier"] in (1, 2) and r["ps_ttm"]], key=lambda r: r["ps_ttm"], reverse=True)
    val_rows = "".join("<tr><td class='nm'>%s <span class='code'>%s</span></td><td class='num'>%s</td>"
                       "<td class='num'>%s</td><td class='num'>%s</td></tr>"
                       % (e(r["name"]), r["code"], fmt_cap(r["mcap_hkd"]), fmt_ps(r["ps_ttm"]),
                          ("%.2f亿" % r["revenue_ttm_yi"]) if r["revenue_ttm_yi"] else "—")
                       for r in pool)
    val_tbl = ("<table><thead><tr><th>公司 / 代码</th><th class='num'>总市值</th>"
               "<th class='num'>PS(TTM)</th><th class='num'>TTM 营收</th></tr></thead><tbody>"
               + val_rows + "</tbody></table>")

    # 公告卡片（只列 hot）
    cards = []
    for r in rows:
        if r["tier"] not in (1, 2):
            continue
        for n in (notices.get(r["code"]) or []):
            if not n["hot"]:
                continue
            cards.append('<div class="news"><b>%s（%s）· %s · %s</b><p>%s</p>'
                         '<p><a href="%s">公告原文</a></p></div>'
                         % (e(r["name"]), r["code"], e(n["date"]), e(n["column"]), e(n["title"]), n["url"]))
    cards_html = "".join(cards[:12]) or '<div class="news"><p>深挖 12 家近 %d 日无实质性公告披露。</p></div>' % days

    obs = "".join("<div class='news'><p>▸ %s</p></div>" % e(o.replace("**", "")) for o in
                  _observations(rows, {1: [r for r in rows if r["tier"] == 1],
                                       2: [r for r in rows if r["tier"] == 2],
                                       3: [r for r in rows if r["tier"] == 3]}, notices,
                               news=news, today=hk_today()))

    return """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>港股AI日报 · %(date)s %(mode)s</title><style>%(css)s</style></head><body><div class="wrap">
<header><div class="kicker">● HK AI SECTOR DAILY · 港股AI日报</div>
<h1>港股 AI 行业每日情报简报</h1>
<div class="meta">报告日期 <b>%(date)s</b> · 行情时点 <b>%(ts)s</b> · 覆盖 <b>%(n)d</b> 家 · 生成于 %(gen)s</div>
</header>
<h2>01 · 大盘指数</h2><div class="idx">%(idx)s</div>
<h2>02 · 第一梯队（5 家）</h2>%(t1)s
<h2>03 · 第二梯队（7 家）</h2>%(t2)s
<h2>04 · 第三梯队（12 家）</h2>%(t3)s
<h2>05 · 估值对比（按 PS(TTM) 降序）</h2>%(val)s
<h2>06 · 公告速览</h2>%(cards)s
<h2>07 · 今日观察</h2>%(obs)s
<footer>数据来源：东方财富（行情/市值/财务）、新浪（指数）、东方财富公告库（港交所披露）<br>
PS(TTM) = 总市值(HKD) ÷ 滚动 12 个月营业总收入 · 生成脚本：hk-ai-daily</footer>
</div></body></html>""" % {
        "css": CSS, "date": today, "mode": mode_cn, "ts": data_ts or hk_datetime_str(),
        "n": len(rows), "gen": snap.get("generated_at", ""), "idx": idx,
        "t1": table(1), "t2": table(2), "t3": table(3), "val": val_tbl,
        "cards": cards_html, "obs": obs,
    }
