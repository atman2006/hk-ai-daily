# 港股AI日报 · 自动化推送

monitor 24 家港股 AI 相关公司，**每日收盘后自动跑一次**（港股 16:20），生成行情 + 估值（总市值、PS(TTM)）+ 港交所公告速览，并推送到钉钉群机器人。

**运行时零依赖**：只用 Python 3.11 标准库，不装任何第三方包（`requirements.txt` 为空壳）。

## 消息长什么样

钉钉消息固定 6 节（`01–06`），超长自动按小节拆成 2–3 条，每条都含关键词「港股AI日报」：

```
> 恒生指数 24448.95 (-0.13%) ｜ 恒生科技指数 4040.73 (-0.92%)
> 港股AI日报 ｜ 覆盖 24 家 ｜ 收盘 2026/11/09 16:08 ｜ 估值口径 PS(TTM)

### 01 · 核心观察        ← 涨幅第一 / 跌幅第一 / 涨跌结构 / 公告面
### 02 · 第一梯队（5 家 · 深挖）   ← 每家：收｜涨跌｜市值｜PS + 公告 + 链接
### 03 · 第二梯队（7 家）          ← 同上，迅策标「（重点）」
### 04 · 其他异动        ← 第三梯队 |涨跌| ≥ 3%
### 05 · 估值速览        ← 三个梯队各一行「公司 市值/PS」
### 06 · 今日观察        ← 板块结构 / 公告面 / 估值分化
📄 完整报告（仓库内）：reports/港股AI日报-YYYY-MM-DD-收盘.md
```

## 数据来源

| 内容 | 来源 | 说明 |
|---|---|---|
| 行情 / 总市值 / PE / PB | 东方财富 `push2` 批量接口 | 一次请求取 24 家 |
| 营业总收入（算 PS） | 东方财富港股 F10 `RPT_HKF10_FN_MAININDICATOR` | 本地缓存 7 天 |
| 恒指 / 恒生科技 | 新浪 `hq.sinajs.cn` | 需 Referer |
| 公司新闻（舆情） | 东方财富「个股资讯」`np-listapi` | 按公司名相关度排序，取最新 2 条，标日期 |
| 公司新闻（补充） | Bing News RSS / Google News RSS | 东财没有点名新闻时才用 |
| 公告（港交所披露） | 东方财富公告库 `ann_type=H` | 只推送实质性公告，月报表等例行公告不进消息 |

新闻只取「标题 + 媒体 + 日期 + 链接」，**不做 LLM 归纳**；同一家公司按相关性取最新 2 条，标题里会标「今日 / 昨日 / MM-DD」，覆盖薄的标的会显示其最近一条（日期能看出新旧）。

`PS(TTM) = 总市值(HKD) ÷ 滚动 12 个月营业总收入`；中报口径为「上年年报 + 本期 − 上年同期」；取不到营收就写 `N/A`，绝不估算。

## 本地运行

```bash
# 只生成报告，不推送（推荐先这样验一遍）
python scripts/run.py --mode close --dry-run

# 盘中快照 / 早盘前（手动场景）
python scripts/run.py --mode intraday

# 今日已推过还想重发
python scripts/run.py --phase push --force

# 调公告回溯天数 / 强制刷新财务缓存
python scripts/run.py --mode close --days 7 --refresh-fin
```

产物：`reports/YYYY-MM-DD-{close|intraday|early}.md` 与同名 `.html`（纯 ASCII 文件名，避开了钉钉 PC 端打不开中文 URL 的坑）。

> **版本标签自动纠正**：`--mode auto`（默认）按香港时间判定——`<09:30` 早盘前、`09:30–16:10` 盘中、`≥16:10` 收盘。即使 cron 被 GitHub 延迟几小时，也不会再把盘中数据标成「收盘」。

## 部署到 GitHub Actions

1. 新建仓库并推送本目录内容。
2. 仓库 **Settings → Secrets and variables → Actions** 添加：
   - `DINGTALK_WEBHOOK`（推荐，完整 webhook URL）或 `DINGTALK_TOKEN`（只要 access_token）
   - 可选 `REPORT_URL_BASE`（放在 Variables，比如 `https://<user>.github.io/<repo>`，消息里就会带可点链接）
3. Settings → Pages → Source 选 **GitHub Actions**（想用报告链接才需要；没开也不影响推送——`Get pages` 返回 404 时那两步会被 `continue-on-error` 跳过，本次已验证）。
4. 想立刻跑一次：Actions → 港股AI日报 → Run workflow（可选 `dry_run`）。

> **当前状态**：仓库 `atman2006/hk-ai-daily`（private）已配好 `DINGTALK_WEBHOOK` secret，首次 `workflow_dispatch`（dry_run）已跑通：数据抓取、报告生成、commit 回仓库全部成功（commit `454e38a`）。Pages 未启用（private 仓库需付费计划才支持），如需报告公网链接可改成 public 仓库或在 Variables 配 `REPORT_URL_BASE` 指向自己的托管地址。

## 报告链接 / 图表（已启用）

钉钉聊天**不渲染 HTML**，只接受链接或图片（都要求公网 URL）。本仓库已配好：

| 配置 | 当前值 | 作用 |
|---|---|---|
| 仓库可见性 | **public** | 图片/页面可被钉钉直接拉取 |
| `REPORT_URL_BASE`（Variable） | `https://atman2006.github.io/hk-ai-daily` | 消息底部的「📄 查看完整图表版报告」按钮 |
| `IMG_URL_BASE`（Variable） | `https://raw.githubusercontent.com/atman2006/hk-ai-daily/main/reports` | 图表 PNG 内嵌到消息里 |
| GitHub Pages | 已开（Source: GitHub Actions） | 托管 `reports/` 里的 HTML |

推送流程因此拆两段（`.github/workflows/daily.yml`）：

1. `--phase build`：抓数 → 生成 markdown / HTML / 图表 SVG → 无头 Chrome 截图成 PNG
2. 提交 `reports/`（**先上线，保证图片和链接可访问**）
3. `--phase push`：把图片 URL 插进消息，用 `actionCard`（带按钮）推送

本地跑依然是一键：`python scripts/run.py --mode close`（本机有 Edge/Chrome 就会出图）。

要拿公网 URL 的备选方案（如果以后想关掉 public）：
1. `raw.githack.com/<user>/<repo>/main/reports/xxx.html`（仍需 public）
2. 自建服务器 / OSS，把 `REPORT_URL_BASE`、`IMG_URL_BASE` 指过去

## 注意事项

- **时区与频率**：GitHub Actions 的 cron 是 UTC。本仓库只用 `20 8 * * 1-5`（港股 16:20，收盘竞价 16:10 结束后取正式收盘价），**每天只跑一次、只推一次**。
- **推送去重**：`.cache/pushed.json` 记录今日已推送的日期+版本，重复运行会直接跳过（要重发加 `--force`）。
- **延迟**：Actions 定时任务可能延迟，极端情况可达数小时；标签会按实际港时自动纠正。
- **60 天停用**：仓库 60 天无提交，GitHub 会自动停用定时任务；本工作流每次运行都会把报告 commit 回来，只要还在跑就不会触发停用。
- **非交易日**：工作日仍会在节假日触发，此时行情为最近交易日数据，消息里会带上报价时间。
- **无 LLM 的边界**：本版本只做「公告标题 + 行情 + 估值」的规则化拼装，**没有舆情归纳和因果判断**；要恢复后者需接 LLM + 搜索 API（见 `requirements-dev.txt`）。

## 目录结构

```
config/watchlist.json   24 家名单（tier 1/2/3，key=true 表示重点）
scripts/common.py       HTTP / 格式化 / 缓存工具
scripts/market.py       行情、市值、PS(TTM)
scripts/news.py         港交所公告抓取
scripts/report.py       钉钉 markdown + HTML 报告生成
scripts/push.py         钉钉推送（拆条、关键词兜底）
scripts/run.py          入口
.github/workflows/daily.yml
reports/                每日产物（会被 commit 回仓库）
```
