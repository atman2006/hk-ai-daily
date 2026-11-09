# -*- coding: utf-8 -*-
"""入口：抓数据 → 抓公告/资讯 → 生成 markdown + HTML + 图表 PNG → 推送钉钉。

两阶段（CI 用，保证图片链接先可访问再推送）：
  python scripts/run.py --phase build   # 只生成（报告 + 图表 + 待推送消息）
  python scripts/run.py --phase push    # 读取上一次生成的待推送消息并推送

本地一键：
  python scripts/run.py --mode close              # 抓数 + 生成 + 推送
  python scripts/run.py --mode close --dry-run    # 只打印，不推送
  python scripts/run.py --mode close --no-push    # 只生成
  python scripts/run.py --mode close --no-chart   # 不生成图表
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import REPORT_DIR, ensure_utf8_stdout, hk_today, load_json, save_json  # noqa: E402

ensure_utf8_stdout()
from charts import build_chart_html, render_png  # noqa: E402
from market import build_snapshot  # noqa: E402
from news import fetch_all as fetch_all_notices, fetch_all_news  # noqa: E402
from push import push_text  # noqa: E402
from report import build_html, build_markdown  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST = os.path.join(ROOT, "config", "watchlist.json")
STATE = os.path.join(ROOT, ".cache", "last_message.json")


def _build(args):
    wl = load_json(WATCHLIST)
    if not wl:
        raise SystemExit("读不到 config/watchlist.json")

    print("[1/5] 行情 + 市值 + PS …")
    snap = build_snapshot(wl, refresh_fin=args.refresh_fin)

    print("[2/5] 公告（近 %d 天）+ 最新资讯 …" % args.days)
    codes = [c["code"] for c in wl["companies"]]
    notices = fetch_all_notices(codes, days=args.days)
    deep = [c for c in wl["companies"] if c.get("tier") in (1, 2)]
    news = fetch_all_news(deep, days=0, limit=2)

    today = hk_today()
    mode_cn = "收盘" if args.mode == "close" else "早盘前"
    fname = "港股AI日报-%s-%s" % (today, mode_cn)
    md_path = os.path.join(REPORT_DIR, fname + ".md")
    html_path = os.path.join(REPORT_DIR, fname + ".html")
    png_name = fname + "-图表.png"
    png_path = os.path.join(REPORT_DIR, png_name)

    data_ts = ""
    for b in snap["benchmarks"]:
        if b.get("date"):
            data_ts = "%s %s" % (b["date"], b.get("time", ""))
            break
    report_url = (args.report_url_base.rstrip("/") + "/" + fname + ".html") if args.report_url_base else ""

    print("[3/5] 生成报告 …")
    text = build_markdown(snap, notices, news=news, mode=args.mode,
                          report_path="reports/" + fname + ".md",
                          report_url=report_url, data_ts=data_ts, days=args.days)
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(text)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(snap, notices, news=news, mode=args.mode, data_ts=data_ts, days=args.days))

    png_ok = False
    if not args.no_chart:
        print("[3b] 生成图表 PNG …")
        chart_html = build_chart_html(snap, "港股 AI 监控 · %s %s" % (today, mode_cn),
                                      "数据：东方财富 / 新浪 · 覆盖 %d 家 · PS(TTM)=总市值÷滚动12个月营收" % len(snap["rows"]))
        chart_path = os.path.join(REPORT_DIR, fname + "-图表.html")
        with open(chart_path, "w", encoding="utf-8") as f:
            f.write(chart_html)
        png_ok = render_png(chart_path, png_path)
        print("      图表 %s" % ("OK %d bytes" % os.path.getsize(png_path) if png_ok else "未生成（本机无 Chrome/Edge）"))

    n_wire = sum(1 for c in deep if news.get(c["code"]))
    print("      覆盖 %d 家 ｜ 深挖 12 家中 %d 家有资讯 ｜ 报告 %s" % (len(snap["rows"]), n_wire, fname))

    save_json(STATE, {
        "title": "港股AI日报 %s %s" % (today[5:], mode_cn),
        "text": text,
        "md_path": "reports/" + fname + ".md",
        "report_url": report_url,
        "png_name": png_name if png_ok else "",
        "today": today,
        "mode": args.mode,
    })
    return 0


def _push(args):
    st = load_json(STATE)
    if not st:
        raise SystemExit("没有待推送消息，请先跑 --phase build")
    text = st["text"]
    if st.get("png_name") and args.img_base:
        url = "%s/%s" % (args.img_base.rstrip("/"), st["png_name"])
        text = text.replace("\n\n### 🔥", "\n\n![](%s)\n\n### 🔥" % url, 1)
        print("      内嵌图表：%s" % url)
    print("[4/5] 推送钉钉 …")
    ok, sizes = push_text(text, title=st["title"], dry_run=args.dry_run,
                          card_url=st.get("report_url") or None)
    print("[5/5] 完成 ｜ %s ｜ 分条 %s ｜ markdown %s"
          % ("dry-run 未推送" if args.dry_run else ("推送成功 OK" if ok else "推送失败 FAILED"),
             sizes, st.get("md_path")))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["close", "early"], default="close")
    ap.add_argument("--phase", choices=["all", "build", "push"], default="all")
    ap.add_argument("--days", type=int, default=5, help="公告回溯天数")
    ap.add_argument("--dry-run", action="store_true", help="只打印消息，不推送")
    ap.add_argument("--no-push", action="store_true", help="不推送，只生成")
    ap.add_argument("--no-chart", action="store_true", help="不生成图表 PNG")
    ap.add_argument("--refresh-fin", action="store_true", help="强制刷新财务缓存")
    ap.add_argument("--report-url-base", default=os.environ.get("REPORT_URL_BASE", ""),
                    help="报告页面公网基址（如 GitHub Pages）")
    ap.add_argument("--img-base", default=os.environ.get("IMG_URL_BASE", ""),
                    help="图表 PNG 的公网基址（如 raw.githubusercontent.com/<user>/<repo>/main/reports）")
    args = ap.parse_args()

    if args.phase == "build":
        return _build(args)
    if args.phase == "push":
        return _push(args)
    rc = _build(args)
    if rc:
        return rc
    if args.no_push:
        print("[4/5] 跳过推送（--no-push）")
        return 0
    return _push(args)


if __name__ == "__main__":
    sys.exit(main())
