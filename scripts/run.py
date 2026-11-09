# -*- coding: utf-8 -*-
"""入口：抓数据 → 抓公告 → 生成 markdown + HTML → 推送钉钉。

用法：
  python scripts/run.py --mode close            # 收盘版（默认）
  python scripts/run.py --mode early            # 早盘前版
  python scripts/run.py --dry-run               # 只打印不推送
  python scripts/run.py --no-push               # 只生成报告
  python scripts/run.py --refresh-fin           # 强制刷新财务缓存
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import REPORT_DIR, ensure_utf8_stdout, hk_datetime_str, hk_today, load_json, save_json  # noqa: E402

ensure_utf8_stdout()
from market import build_snapshot  # noqa: E402
from news import fetch_all  # noqa: E402
from push import push_text  # noqa: E402
from report import build_html, build_markdown  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST = os.path.join(ROOT, "config", "watchlist.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["close", "early"], default="close")
    ap.add_argument("--days", type=int, default=5, help="公告回溯天数")
    ap.add_argument("--dry-run", action="store_true", help="只打印消息，不推送")
    ap.add_argument("--no-push", action="store_true", help="不推送，只生成报告")
    ap.add_argument("--refresh-fin", action="store_true", help="强制刷新财务缓存")
    ap.add_argument("--report-url-base", default=os.environ.get("REPORT_URL_BASE", ""),
                    help="报告的公网基址（如 GitHub Pages），用于消息里的链接")
    args = ap.parse_args()

    wl = load_json(WATCHLIST)
    if not wl:
        raise SystemExit("读不到 config/watchlist.json")

    print("[1/5] 行情 + 市值 + PS …")
    snap = build_snapshot(wl, refresh_fin=args.refresh_fin)

    print("[2/5] 公告（近 %d 天）…" % args.days)
    notices = fetch_all([c["code"] for c in wl["companies"]], days=args.days)

    today = hk_today()
    mode_cn = "收盘" if args.mode == "close" else "早盘前"
    fname = "港股AI日报-%s-%s" % (today, mode_cn)
    md_path = os.path.join(REPORT_DIR, fname + ".md")
    html_path = os.path.join(REPORT_DIR, fname + ".html")
    report_url = (args.report_url_base.rstrip("/") + "/" + fname + ".html") if args.report_url_base else ""

    print("[3/5] 生成报告 …")
    data_ts = ""
    for b in snap["benchmarks"]:
        if b.get("date"):
            data_ts = "%s %s" % (b["date"], b.get("time", ""))
            break
    text = build_markdown(snap, notices, mode=args.mode, report_path="reports/" + fname + ".md",
                          report_url=report_url, data_ts=data_ts, days=args.days)
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(text)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(snap, notices, mode=args.mode, data_ts=data_ts, days=args.days))
    save_json(os.path.join(ROOT, ".cache", "last_snapshot.json"), snap)

    n_deep_news = sum(1 for r in snap["rows"] if r["tier"] in (1, 2) and notices.get(r["code"]))
    print("      覆盖 %d 家 ｜ 深挖 12 家中 %d 家有新公告 ｜ 报告 %s" % (len(snap["rows"]), n_deep_news, fname))

    ok = True
    sizes = []
    if args.no_push:
        print("[4/5] 跳过推送（--no-push）")
    else:
        print("[4/5] 推送钉钉 …")
        ok, sizes = push_text(text, title="港股AI日报 %s %s" % (today[5:], mode_cn), dry_run=args.dry_run)

    print("[5/5] 完成 ｜ %s ｜ 分条 %s ｜ markdown %s"
          % (("dry-run 未推送" if args.dry_run else ("已跳过推送" if args.no_push else ("推送成功 OK" if ok else "推送失败 FAILED"))),
             sizes, md_path))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
