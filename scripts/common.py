# -*- coding: utf-8 -*-
"""公共工具：HTTP 请求、JSON 读写、格式化。仅依赖标准库。"""
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, ".cache")
REPORT_DIR = os.path.join(ROOT, "reports")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


class FetchError(RuntimeError):
    pass


def http_get(url, headers=None, timeout=25, tries=3, encoding="utf-8"):
    """带重试的 GET，返回文本。"""
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
                raw = r.read()
            return raw.decode(encoding, "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            if i < tries - 1:
                time.sleep(1.5 * (i + 1))
    raise FetchError("%s -> %s" % (url[:90], last))


def http_get_json(url, headers=None, timeout=25, tries=3):
    return json.loads(http_get(url, headers=headers, timeout=timeout, tries=tries))


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def num(v, default=None):
    """东财常把缺失值写成 '-'。"""
    try:
        if v in (None, "-", ""):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def fmt_cap(hkd):
    """市值：>=1万亿 用「X.XX万亿」，否则「X.X亿」。"""
    if not hkd:
        return "N/A"
    if hkd >= 1e12:
        return "%.2f万亿" % (hkd / 1e12)
    return "%.1f亿" % (hkd / 1e8)


def fmt_pct(v):
    if v is None:
        return "—"
    return "%+.2f%%" % v


def fmt_ps(v):
    if v is None:
        return "N/A"
    if v <= 0:
        return "亏损"
    return "%.1fx" % v


def fmt_amount(hkd):
    """成交额：亿/万。"""
    if not hkd:
        return "—"
    if hkd >= 1e8:
        return "%.2f亿" % (hkd / 1e8)
    return "%.0f万" % (hkd / 1e4)


def ensure_utf8_stdout():
    """管道捕获时用 UTF-8；GBK 控制台降到 errors=replace，避免 emoji 报 UnicodeEncodeError。"""
    try:
        if not sys.stdout.isatty():
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        else:
            sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass


# ---------------------------------------------------------------- 交易日
def hk_now():
    """香港时间（不依赖 tzdata，用固定 +8）。"""
    return time.gmtime(time.time() + 8 * 3600)


def hk_datetime_str(gm=None):
    g = gm or hk_now()
    return time.strftime("%Y-%m-%d %H:%M", g)


def hk_today(gm=None):
    return time.strftime("%Y-%m-%d", gm or hk_now())
