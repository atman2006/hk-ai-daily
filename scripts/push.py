# -*- coding: utf-8 -*-
"""钉钉群机器人推送：密钥取 DINGTALK_WEBHOOK（完整 URL）或 DINGTALK_TOKEN（本地可回退 MEMORY.md）。
超长自动按 `### 小节` 边界拆条，每条都含关键词「港股AI日报」。"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

from common import ensure_utf8_stdout

ensure_utf8_stdout()

KEYWORD = "港股AI日报"
HARD_LIMIT = 3900
SOFT_LIMIT = 2600
MEM_PATH = os.environ.get("DINGTALK_MEM", r"C:\Users\25239\AppData\Roaming\NextWork\openclaw-8.1\state\workspace-ai\MEMORY.md")
MARK = "access_" + "token="


def get_webhook():
    """优先 DINGTALK_WEBHOOK（完整 URL），其次 DINGTALK_TOKEN，最后回退本地 MEMORY.md。"""
    wh = os.environ.get("DINGTALK_WEBHOOK", "").strip()
    if wh:
        return wh
    tok = os.environ.get("DINGTALK_TOKEN", "").strip()
    if not tok:
        try:
            with open(MEM_PATH, encoding="utf-8") as f:
                for line in f:
                    if "Webhook" in line and MARK in line:
                        tok = line.split(MARK)[1].strip().strip("`").strip()
                        break
        except OSError:
            pass
    if not tok:
        raise SystemExit("缺少 DINGTALK_WEBHOOK / DINGTALK_TOKEN（本地也没有 MEMORY.md Webhook）")
    return "https://oapi.dingtalk.com/robot/send?" + MARK + tok


def _post(payload, timeout=25):
    url = get_webhook()
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    opener = urllib.request.build_opener()
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"https": proxy, "http": proxy}))
    try:
        with opener.open(req, timeout=timeout) as r:
            return "HTTP %s %s" % (r.status, r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return "HTTP %s %s" % (e.code, e.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        return "ERR %s" % e


def _blocks(text):
    blocks, cur = [], []
    for ln in text.split("\n"):
        if ln.startswith("### ") and any(x.strip() for x in cur):
            blocks.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    if any(x.strip() for x in cur):
        blocks.append(cur)
    return ["\n".join(b).strip("\n") for b in blocks]


def _line_split(text, limit):
    out, cur, size = [], [], 0
    for ln in text.split("\n"):
        n = len(ln.encode("utf-8")) + 1
        if cur and size + n > limit:
            out.append("\n".join(cur))
            cur, size = [], 0
        cur.append(ln)
        size += n
    if cur:
        out.append("\n".join(cur))
    return out


def split_text(text, title="港股AI日报"):
    chunks, cur, size = [], [], 0
    for b in _blocks(text):
        n = len(b.encode("utf-8")) + 2
        if cur and (size + n > SOFT_LIMIT or size + n > HARD_LIMIT):
            chunks.append("\n\n".join(cur))
            cur, size = [], 0
        cur.append(b)
        size += n
    if cur:
        chunks.append("\n\n".join(cur))

    fixed = []
    for c in chunks:
        fixed.extend(_line_split(c, HARD_LIMIT) if len(c.encode("utf-8")) > HARD_LIMIT else [c])
    chunks = fixed

    out, n = [], len(chunks)
    for i, c in enumerate(chunks, 1):
        body = c if i == 1 else "### 港股AI日报（续 %d/%d）\n\n%s" % (i, n, c)
        if KEYWORD not in body:
            body = "**%s**\n%s" % (title, body)
        out.append(body)
    return out


def push_text(text, title="港股AI日报", dry_run=False):
    chunks = split_text(text, title=title)
    if dry_run:
        for i, c in enumerate(chunks, 1):
            print("--- chunk %d/%d  %d bytes ---" % (i, len(chunks), len(c.encode("utf-8"))))
            print(c)
        return True, [len(c.encode("utf-8")) for c in chunks]

    ok = True
    sizes = []
    for i, c in enumerate(chunks, 1):
        ttl = title if len(chunks) == 1 else "%s（%d/%d）" % (title, i, len(chunks))
        res = _post({"msgtype": "markdown", "markdown": {"title": ttl, "text": c}})
        sizes.append(len(c.encode("utf-8")))
        print("[%d/%d] %d bytes -> %s" % (i, len(chunks), sizes[-1], res))
        if '"errcode":0' not in res:
            ok = False
    return ok, sizes


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("用法: python push.py <markdown文件> [--dry-run]")
    txt = open(sys.argv[1], encoding="utf-8").read()
    ok, sizes = push_text(txt, dry_run="--dry-run" in sys.argv)
    sys.exit(0 if ok else 1)
