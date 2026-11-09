# -*- coding: utf-8 -*-
"""把快照画成一张双面板图（纯 SVG），再用无头浏览器截成 PNG。

- 无第三方 Python 依赖
- 找得到 Chrome/Chromium/Edge 就出 PNG；找不到就只写 HTML（不报错）
"""
import html
import math
import os
import shutil
import subprocess

CHROME_CANDIDATES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                     "msedge", "chrome")


def _find_chrome():
    for name in CHROME_CANDIDATES:
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(p):
            return p
    return None


def _panel_bars(rows):
    W, rowH, padL, padR = 520, 24, 118, 64
    H = len(rows) * rowH + 44
    maxabs = max((abs(r["chg_pct"]) for r in rows), default=1) or 1
    mid = padL + (W - padL - padR) / 2
    scale = (W - padL - padR) / 2 / maxabs
    parts = ['<text x="%d" y="20" fill="#ff8c1a" font-size="12" font-family="Consolas">'
             '01 · 当日涨跌幅排行（%d 家）</text>' % (padL, len(rows)),
             '<line x1="%.1f" y1="28" x2="%.1f" y2="%d" stroke="#1d2733"/>' % (mid, mid, H - 6)]
    for i, r in enumerate(rows):
        y = 34 + i * rowH
        v = r["chg_pct"]
        w = abs(v) * scale
        x = mid if v >= 0 else mid - w
        col = "#1fd475" if v >= 0 else "#ff4d5e"
        parts.append('<rect x="%.1f" y="%d" width="%.1f" height="13" fill="%s" opacity="0.85"/>'
                     % (x, y, max(w, 1), col))
        parts.append('<text x="%d" y="%d" fill="#d7e0ea" font-size="11" text-anchor="end">%s</text>'
                     % (padL - 8, y + 10, html.escape(r["name"][:9])))
        tx = mid + w + 5 if v >= 0 else mid - w - 5
        parts.append('<text x="%.1f" y="%d" fill="%s" font-size="10.5" font-family="Consolas" '
                     'text-anchor="%s">%+.2f%%</text>'
                     % (tx, y + 10, col, "start" if v >= 0 else "end", v))
    return '<svg width="%d" height="%d">%s</svg>' % (W, H, "".join(parts))


def _panel_scatter(rows):
    W, H, pl, pr, pt, pb = 520, 620, 62, 22, 40, 46
    tiers = {1: "#ff8c1a", 2: "#ffc94d", 3: "#4aa3ff"}
    pts = [r for r in rows if r.get("mcap_yi") and r.get("ps_ttm") and r["ps_ttm"] > 0]
    if len(pts) < 2:
        return '<svg width="%d" height="%d"><text x="20" y="30" fill="#8b98a8">数据不足</text></svg>' % (W, H)
    xs = [math.log10(r["mcap_yi"]) for r in pts]
    ys = [math.log10(r["ps_ttm"]) for r in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x1 == x0:
        x1 = x0 + 1
    if y1 == y0:
        y1 = y0 + 1

    def sx(v):
        return pl + (math.log10(v) - x0) / (x1 - x0) * (W - pl - pr)

    def sy(v):
        return H - pb - (math.log10(v) - y0) / (y1 - y0) * (H - pt - pb)

    out = ['<text x="%d" y="22" fill="#ff8c1a" font-size="12" font-family="Consolas">'
           '02 · 总市值 vs PS(TTM)（对数轴）</text>' % pl]
    for gx in range(int(math.floor(x0)), int(math.ceil(x1)) + 1):
        X = sx(10 ** gx)
        lab = ("%.0f亿" % (10 ** gx)) if 10 ** gx < 10000 else ("%.0f万亿" % (10 ** gx / 10000))
        out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#161e28"/>' % (X, pt, X, H - pb))
        out.append('<text x="%.1f" y="%d" fill="#5d6b7a" font-size="10" text-anchor="middle" '
                   'font-family="Consolas">%s</text>' % (X, H - pb + 14, lab))
    for gy in (1, 3, 10, 30, 100, 300):
        if not (y0 - 0.1 <= math.log10(gy) <= y1 + 0.1):
            continue
        Y = sy(gy)
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#161e28"/>' % (pl, Y, W - pr, Y))
        out.append('<text x="%d" y="%.1f" fill="#5d6b7a" font-size="10" text-anchor="end" '
                   'font-family="Consolas" dy="3">%dx</text>' % (pl - 6, Y, gy))
    for idx, r in enumerate(pts):
        cx, cy = sx(r["mcap_yi"]), sy(r["ps_ttm"])
        out.append('<circle cx="%.1f" cy="%.1f" r="4" fill="%s" opacity="0.9"/>'
                   % (cx, cy, tiers.get(r["tier"], "#8b98a8")))
        if r["tier"] == 1 or r.get("key"):
            dy = -7 if idx % 2 == 0 else 13
            out.append('<text x="%.1f" y="%.1f" fill="#8b98a8" font-size="9.5">%s</text>'
                       % (cx + 6, cy + dy, html.escape(r["name"][:6])))
    return '<svg width="%d" height="%d">%s</svg>' % (W, H, "".join(out))


def build_chart_html(snap, title, subtitle):
    rows = sorted([r for r in snap["rows"] if r.get("chg_pct") is not None],
                  key=lambda r: r["chg_pct"], reverse=True)
    legend = ('<div class="lg"><span><i style="background:#ff8c1a"></i>第一梯队</span>'
              '<span><i style="background:#ffc94d"></i>第二梯队</span>'
              '<span><i style="background:#4aa3ff"></i>第三梯队</span>'
              '<span class="dim">PS(TTM) = 总市值 ÷ 滚动12个月营收</span></div>')
    return """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#07090d;color:#d7e0ea;font-family:"Noto Sans CJK SC","Source Han Sans SC","Microsoft YaHei",sans-serif;padding:20px 24px;width:1160px}
h1{font-size:19px;font-weight:800;margin-bottom:2px}
.sub{font-family:Consolas,monospace;font-size:11px;color:#8b98a8;margin-bottom:14px}
.grid{display:flex;gap:24px;align-items:flex-start}
.card{background:#0d1117;border:1px solid #1d2733;border-radius:6px;padding:8px}
.lg{display:flex;gap:16px;align-items:center;font-size:11px;color:#8b98a8;margin-top:12px;font-family:Consolas,monospace}
.lg i{display:inline-block;width:8px;height:8px;border-radius:50%%;margin-right:5px}
.dim{color:#5d6b7a}
</style></head><body>
<h1>__TITLE__</h1><div class="sub">__SUB__</div>
<div class="grid"><div class="card">__P1__</div><div class="card">__P2__</div></div>
__LEGEND__
</body></html>""".replace("__TITLE__", html.escape(title)).replace("__SUB__", html.escape(subtitle)) \
        .replace("__P1__", _panel_bars(rows)).replace("__P2__", _panel_scatter(snap["rows"])) \
        .replace("__LEGEND__", legend)


def render_png(html_path, png_path, css_width=1170, css_height=750, scale=2):
    """用无头浏览器截图。成功返回 True。

    注意：--window-size 单位是 CSS 像素，--force-device-scale-factor 只放大输出像素。
    """
    chrome = _find_chrome()
    if not chrome:
        return False
    if os.path.exists(png_path):
        os.remove(png_path)
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
           "--force-device-scale-factor=%g" % scale,
           "--user-data-dir=" + os.path.join(os.path.dirname(png_path) or ".", ".chrome-profile"),
           "--screenshot=" + png_path,
           "--window-size=%d,%d" % (int(css_width), int(css_height)),
           "--virtual-time-budget=6000",
           "file:///" + html_path.replace("\\", "/").lstrip("/")]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return os.path.exists(png_path) and os.path.getsize(png_path) > 5000
