# 新闻消化器（News Digest）设计

> 目标：系统里每天都在涌入大量新闻（金十快讯/要闻、公众号、iMessage、AI 聚合、
> 用户投喂），**信息不过载**——按我们的持仓与关注，筛出"到底该看哪几条"，
> 并落成每天可随时查看的报告 + dashboard 面板。
>
> 交付：`deva/naja/news/`（focus / triage / digest）+ `scripts/verify/verify_news_digest.py`
> + `deva/naja/tests/test_news_digest.py`（24 条）+ dashboard「今日新闻消化」面板
> + `news_digest` 每日定时任务。

---

## 1. 内容盘点：系统里目前有哪些新闻

| # | 来源 | 抓取方式 | 频率 | 代码位置 |
|---|---|---|---|---|
| 1 | 金十「重要事件」 | Playwright 渲染 → 读 Vuex store | 30 分钟定时 + 休眠补抓 | `datasource/plugins/jin10_fetcher.py`；`config/tasks/jin10_important_news.yaml` |
| 2 | 金十「实时快讯」 | HTTP `flash_newest.js` | 交易时段 60s / 非交易 300s | `radar/news_fetcher.py` |
| 3 | 金十历史快讯 | POST `flash-api.jin10.com` | 休眠补抓 | `state/system/wake_sync_handlers.py` |
| 4 | 微信公众号 | OpenClaw 网关轮询 | 5s | `tasks/unified_article_monitor.py` |
| 5 | iMessage | `imesg` CLI | 30s（5 分钟内 + 白名单） | 同上 |
| 6 | AI 聚合（arXiv / HF / GitHub / HN / Twitter / TechCrunch / 公众号 RSS / AIbase） | HTTP + Playwright | 每日一次 | `tasks/ai_daily_report.py` |
| 7 | 用户投喂 URL | wechat-to-md / curl / WebFetch | 被动 | `tasks/article_learner.py` |

**存放（两套并存，互不相通）**

* JSON：`~/.naja/jin10_news.json`、`focused_news_cache.json`（**只存 deep 级**，24h / 200 条）、
  `ai_knowledge/*`、`ai_reports/*.txt`
* NB 表：`naja_radar_news`、`naja_news_history`、`naja_watchlist`、`naja_focus_config`
* 事件总线：`TextFetchedEvent` → `TextFocusedEvent`（**内存，明确不落盘**）

**既有筛选机制**：`attention/text_importance_scorer.py` 是唯一面向新闻的筛选器——
`score = 新鲜度×0.15 + 关键词×0.35 + 叙事×0.35 + 来源×0.15`，
`deep≥0.6 / index≥0.3 / drop<0.2`。（`market_hotspot` 里的 noise_filter / panic_analyzer
筛的是**行情**，不筛新闻。）

**既有呈现**：AI 晚报（纯文本 + iMessage）、金十事件面板、供应链面板、跨信号面板、
24h 时间线、雷达 SSE 流、托盘。

---

## 2. 关键发现：一条从没接上的线（静默失效）

`TextImportanceScorer` 的设计意图就是"吃 manas 状态给新闻打分"，专门有
`set_manas_state(focus_topics=...)`。但全仓交叉验证：

```
搜 set_manas_state → 只有定义与 docstring 示例，零个调用方
```

连锁后果：

1. `_manas_state` 恒为 `None` → `_get_focus_topic_matches()` 恒返回 `[]`
2. → `_compute_narrative_relevance([])` 恒返回常数 `0.3`（**叙事那 35% 权重是死的**）
3. → `TextFocusedEvent.matched_focus_topics` 恒为空
4. → 下游叙事追踪器 / 跨信号分析 / 供应链联动读这个字段，**整条链路空转**

这是本项目反复踩的那类静默失效：`try/except` + 默认值让"没接线"与"正好等于默认值"
不可区分，表现为"跑得好好的"。

**修法**（`_resolve_manas_state`）：给评分器加 `set_focus_provider()` 注入点，
**每次评分前惰性拉取**（而不是靠外部 push，漏一个更新点就静默过期）。
provider 失败时沿用上次快照并记 warning——不抛、不静默清空。

---

## 3. 复用 manas 的机制

manas 的本质就是**注意力分配**。它已经维护着"我们关心什么"的三个维度，正好是
新闻筛选的输入：

| manas / 关注体系已有 | 出口 | 用途 |
|---|---|---|
| 关注主题 `focus_themes` | `manas_manager.get_manas_engine().get_focus_themes()` | AI / 芯片 / 新能源 / 医药 … |
| 自选股 | `attention.portfolio.get_portfolio()`（`naja_watchlist`） | 我们的自选 |
| 持仓 | 同上（`get_holdings()`） | 我们的持仓 |
| 关注叙事 / 题材 | `attention.focus_manager`（`naja_focus_config`） | 主动 follow 的东西 |
| 叙事风险 | manas 认知状态 | 当下最需警惕的方向 |

**边界**：manas 的输入契约（`manas_inputs.py` 四契约）**没有** news/text 字段，
`ManasEngine` 本身也不做文本打分。所以这里复用是**复用它的注意力状态**，
不是把它改成新闻引擎——新闻打分仍在 `TextImportanceScorer`。

---

## 4. 三层结构

```
deva/naja/news/
  focus.py    「我们关心什么」  NewsFocusState（冻结快照）+ build_focus_state()
  triage.py   「哪条更值得看」  NewsTriage：相关度打分 + 分组（纯计算，无 I/O）
  digest.py   「呈现出来」      build_digest / HTML / 纯文本 / 落盘 / UI 出口
```

数据流：

```
已评分新闻池（FocusedNewsStore，仅 deep）
    → NewsTriage（持仓优先相关度）
    → build_digest（纯 dict）
    → render_digest_html / render_digest_text
    → ~/.naja/news_digest/YYYY-MM-DD.html（可回看）
    → dashboard「今日新闻消化」面板
```

### 4.1 口径（用户 2026-10-12 选定：持仓/自选最高优先）

```
持仓命中  +0.50    自选命中  +0.38
关注叙事  +0.28    关注主题  +0.10（弱信号）
风险加成  +0.10（叙事风险 ≥0.6 且该条偏负面）

relevance = clamp(base * 0.45 + bonus, 0, 1)
```

`base` 取评分器的 `importance_score`，只占 45%——保证一条"高重要度但与我们无关"的
宏观新闻（0.95）压不过一条"中等重要度但命中持仓"的新闻（0.62）。
实测：`holding=0.779 vs macro=0.527`。

### 4.2 分组规则与一个实测踩到的坑

| 组 | 进入条件 |
|---|---|
| `holding` 持仓 / 自选相关 | 命中持仓或自选标识符 |
| `theme` 关注主题 | 命中**主动 follow** 的叙事 / 题材 |
| `macro` 宏观与其它要闻 | 其余（仍按相关度排序） |

**为什么 theme 组只认"主动关注"，不认 manas 默认主题集**：
manas 默认主题集是 **17 个宽泛大类**（全球宏观 / 债券市场 / 外汇与美元 / 地缘政治…），
它们的共同特点是——**几乎命中所有新闻**。实测拿它分组的结果是 39 条全进 `theme`、
`macro` 恒空，分组失去区分度。所以默认主题只作**弱加权**（+0.10），
让"沾边但没关注"的新闻仍排在同分噪声之上，但不构成一组。

### 4.3 去重

同标题只留相关度最高的一条——重复推送本身就是信息过载的主要来源。

---

## 5. 呈现

* **每日报告**：`~/.naja/news_digest/YYYY-MM-DD.html`（自包含，可双击打开）
  + 同名 `.json` + `latest.json` 快照
* **纯文本**：适合推手机（`run_daily_digest(push=True)`，默认关）
* **dashboard 面板**：`render_news_digest_panel()`，经
  `get_attention_monitor_data()["news_digest"]` 出口
* **定时任务**：`news_digest`，每日 19:00（`container._register_news_digest_task`）。
  与 AI 晚报互补——AI 晚报是"技术圈发生了什么"，本任务是"按我们的持仓与关注，
  今天到底该看哪几条"。

三条守约（与 decision 模块一致）：

1. **不兜底合成**：没有新闻 → `available=False` + `reason`，绝不伪造一份"看起来像"的报告。
2. **降级要留痕**：焦点信息取不到 → 原因写进 `focus.degraded`，并在报告与面板上显示。
3. **UI 只吃 dict**：`get_news_digest_summary()` 返回纯 dict，UI 不深入核心对象。

---

## 6. 顺带修掉的一个既有隐患

`import deva.naja.attention.os.attention_os` 作为**第一个**被导入的 deva 模块会
`ImportError`：`attention_os` → `text_importance_scorer` → `cognition` → `bandit`
→ `attention_os` 成环。生产因加载顺序侥幸不炸（典型的结构性脆弱）。
已把该导入改为 `__init__` 内惰性导入，并在验证脚本里加了**子进程冷启动回归守卫**。

---

## 7. 验证

```bash
/Users/spark/.local/bin/python3 scripts/verify/verify_news_digest.py --strict
```

8 组检查：① 持仓优先排序 ② 分组区分度（宽泛主题不升级）③ 去重
④ 断线已修（注入 provider 后 `matched_focus_topics` 非空）⑤ 降级诚实
⑥ 报告可渲染 / 可落盘 ⑦ 静态守卫（容器确实接线，防回退成死线）
⑧ 冷启动回归。

验收：全量 **277 passed**（253 → 277）；快照 **差异字段 0**；
契约 / 觉醒闭环 / 决策落盘 / manas 独立可用 / 新闻消化 五个 `--strict` 全部 exit 0。

---

## 8. 边界（如实记录）

* **只吃已评分新闻池**（`FocusedNewsStore`，deep 级，24h/200 条）。
  也就是说"先用 `TextImportanceScorer` 粗筛，再用本模块精筛"。若需要覆盖
  `drop` 级的原始新闻，应扩大新闻池而不是放宽本模块。
* **不做语义匹配**。当前是关键词/标识符子串匹配，同义改写会漏（如"宁王"不会命中
  "宁德时代"）。要提升需引入向量召回。
* **自选股表存的是中文名**（实测 `宁德时代` / `lg新能源`），匹配已同时认代码与名称，
  但若表里只写了一个别名，仍会漏。
* **报告是"快照"不是"事件流"**：每次生成覆盖当天文件，不做增量。
* 叙事风险 `narrative_risk` 在容器未初始化时读不到，退化为中性 `0.5`（会记 degraded）。
