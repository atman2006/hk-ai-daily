# -*- coding: utf-8 -*-
"""生成两张 PNG 图表（钉钉消息内嵌用）：
  01 当日涨跌幅排行（横向条形）
  02 总市值 vs PS(TTM) 散点（双对数）
依赖 matplotlib；中文字体按平台自动探测。
"""
import os

from common import fmt_cap, fmt_ps, hk_today

CHART_DIR = None  # 由 run.py 注入


def _pick_font():
    import matplotlib
    from matplotlib import font_manager

    candidates = [
        r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                font_manager.fontManager.addfont(p)
                name = font_manager.FontProperties(fname=p).get_name()
                matplotlib.rcParams["font.family"] = name
                return name
            except Exception:  # noqa: BLE001
                continue
    return None


def make_charts(snap, out_dir):
    """返回 {"chg": path, "valuation": path}；matplotlib 不可用时返回 {}。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # noqa: BLE001
        print("charts skipped: %s" % e)
        return {}

    os.makedirs(out_dir, exist_ok=True)
    _pick_font()
    plt.rcParams["axes.unicode_minus"] = False
    bg, panel, ink, dim = "#07090d", "#0d1117", "#d7e0ea", "#8b98a8"
    up, down, orange, amber, blue = "#1fd475", "#ff4d5e", "#ff8c1a", "#ffc94d", "#4aa3ff"

    rows = [r for r in snap["rows"] if r["chg_pct"] is not None]
    rows.sort(key=lambda r: r["chg_pct"])
    out = {"chg": os.path.join(out_dir, "%s-chg.png" % hk_today()),
           "valuation": os.path.join(out_dir, "%s-ps.png" % hk_today())}

    # ---------- 01 涨跌幅排行
    fig, ax = plt.subplots(figsize=(7.2, 8.2), dpi=150)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(panel)
    names = [r["name"][:7] for r in rows]
    vals = [r["chg_pct"] for r in rows]
    colors = [up if v >= 0 else down for v in vals]
    bars = ax.barh(names, vals, color=colors, height=0.66)
    ax.axvline(0, color="#33404f", lw=1)
    for b, v in zip(bars, vals):
        ax.text(v + (0.12 if v >= 0 else -0.12), b.get_y() + b.get_height() / 2,
                "%+.2f%%" % v, va="center", ha="left" if v >= 0 else "right",
                color=up if v >= 0 else down, fontsize=8.5)
    ax.tick_params(colors=dim, labelsize=8.5)
    for s in ax.spines.values():
        s.set_color("#1d2733")
    ax.set_title("当日涨跌幅排行（24 家）", color=orange, fontsize=11, loc="left", pad=10)
    ax.grid(axis="x", color="#161e28", lw=0.6)
    lim = max(abs(min(vals)), abs(max(vals))) * 1.18
    ax.set_xlim(-lim, lim)
    fig.tight_layout()
    fig.savefig(out["chg"], facecolor=bg)
    plt.close(fig)

    # ---------- 02 市值 vs PS
    pts = [r for r in snap["rows"] if r["mcap_yi"] and r["ps_ttm"] and r["ps_ttm"] > 0]
    fig, ax = plt.subplots(figsize=(7.2, 4.8), dpi=150)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(panel)
    tier_color = {1: orange, 2: amber, 3: blue}
    for t, label in ((3, "第三梯队"), (2, "第二梯队"), (1, "第一梯队")):
        sel = [r for r in pts if r["tier"] == t]
        if not sel:
            continue
        ax.scatter([r["mcap_yi"] for r in sel], [r["ps_ttm"] for r in sel],
                   s=46, c=tier_color[t], label=label, alpha=0.9, edgecolors="none")
    for r in pts:
        if r["tier"] in (1, 2):
            ax.annotate(r["name"][:6], (r["mcap_yi"], r["ps_ttm"]), textcoords="offset points",
                        xytext=(5, 4), fontsize=7.5, color=dim)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("总市值（亿 HKD，对数）", color=dim, fontsize=9)
    ax.set_ylabel("PS(TTM，对数)", color=dim, fontsize=9)
    ax.tick_params(colors=dim, labelsize=8)
    for s in ax.spines.values():
        s.set_color("#1d2733")
    ax.grid(color="#161e28", lw=0.6, which="both")
    ax.set_title("总市值 vs PS(TTM)", color=orange, fontsize=11, loc="left", pad=10)
    leg = ax.legend(fontsize=8, facecolor=panel, edgecolor="#1d2733", labelcolor=ink, loc="lower right")
    leg.get_frame().set_alpha(0.9)
    fig.tight_layout()
    fig.savefig(out["valuation"], facecolor=bg)
    plt.close(fig)

    return out


if __name__ == "__main__":
    import json
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    snap = json.load(open(sys.argv[1], encoding="utf-8")) if len(sys.argv) > 1 else None
    if snap:
        print(make_charts(snap, sys.argv[2] if len(sys.argv) > 2 else "."))
