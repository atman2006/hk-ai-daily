# 港股AI日报 · 自动化推送

监控 24 家港股 AI 相关公司，每日两次（北京时间 09:05 早盘前 / 17:05 收盘）自动生成行情 + 估值（总市值、PS(TTM)）+ 港交所公告速览，并推送到钉钉群机器人。

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
| 公告（港交所披露） | 东方财富公告库 `ann_type=H` | 只取标题+日期+链接，不做归纳 |

`PS(TTM) = 总市值(HKD) ÷ 滚动 12 个月营业总收入`；中报口径为「上年年报 + 本期 − 上年同期」；取不到营收就写 `N/A`，绝不估算。

## 本地运行

```bash
# 只生成报告，不推送（推荐先这样验一遍）
python scripts/run.py --mode close --dry-run

# 早盘前版
python scripts/run.py --mode early

# 调公告回溯天数 / 强制刷新财务缓存
python scripts/run.py --mode close --days 7 --refresh-fin
```

产物：`reports/港股AI日报-YYYY-MM-DD-{收盘|早盘前}.md` 与同名 `.html`（深色终端风，可直接打开看）。

## 部署到 GitHub Actions

1. 新建仓库并推送本目录内容。
2. 仓库 **Settings → Secrets and variables → Actions** 添加：
   - `DINGTALK_WEBHOOK`（推荐，完整 webhook URL）或 `DINGTALK_TOKEN`（只要 access_token）
   - 可选 `REPORT_URL_BASE`（放在 Variables，比如 `https://<user>.github.io/<repo>`，消息里就会带可点链接）
3. Settings → Pages → Source 选 **GitHub Actions**（想用报告链接才需要；没开也不影响推送，部署步骤是 `continue-on-error`）。
4. 想立刻跑一次：Actions → 港股AI日报 → Run workflow（可选 `dry_run`）。

## 注意事项

- **时区**：GitHub Actions 的 cron 是 UTC。本仓库用 `5 1 * * 1-5`（北京 09:05）和 `5 9 * * 1-5`（北京 17:05）。
- **延迟**：Actions 定时任务常延迟 5–20 分钟，不要拿来卡整点。
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
