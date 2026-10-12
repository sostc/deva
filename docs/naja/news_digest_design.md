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

### 4.1 口径（2026-10-12 二次修订：加分制 → 分档制）

**第一版是加分制**，`relevance = clamp(base*0.45 + bonus, 0, 1)`，加成
持仓 +0.50 / 自选 +0.38 / 叙事 +0.28 / 主题 +0.10。

用户的反馈是：「持仓是最关键的，毕竟是自己的资金；关注列表应该弱很多」。
按这个方向复核，发现**这不是数字没调好，而是公式形状不对**——
`base*0.45` 是所有新闻共享的"地板"，于是"持仓优先"只是*倾向于*成立：

| 缺陷 | 实测反例 |
|---|---|
| 1. 自选能压过持仓 | 自选条重要度高 **0.267** 即反超：持仓 0.60→**0.770**，自选 0.90→**0.785** |
| 2. 纯宏观能压过持仓 | 持仓条重要度 0.05（无聊公告）→ **0.522**；宏观条重要度 1.00 沾个宽泛主题 → **0.550** |
| 3. 持仓与自选同组 | `GROUP_HOLDING` 标签就是「持仓 / 自选相关」，视觉上分不出"我的钱"和"在看的票" |

**现在改成"分档制"**：每条新闻按**最强命中**落进唯一一档，档位给出 `relevance`
的**区间**，`base` 只在区间内做区分。四个区间**严格不重叠**：

| 档位 | 归属分组 | 区间 | 计算式 |
|---|---|---|---|
| 持仓命中 | `holding` | `[0.78, 1.00]` | `0.78 + 0.22*base` |
| 关注叙事 | `theme` | `[0.50, 0.74]` | `0.50 + 0.24*base` |
| 自选命中 | `macro` | `[0.32, 0.48]` | `0.32 + 0.16*base` |
| 外部宏观 | `macro` | `[0.00, 0.28]` | `0.00 + 0.24*base`（+ 主题微调 0.04） |

于是有了**数学保证**：持仓下限 0.78 > 叙事上限 0.74 > 自选上限 0.48 > 外部上限 0.28。
`TriageConfig.validate()` 把"严格不重叠"做成**可校验的不变量**，
`test_tier_bands_are_strictly_disjoint` 与验证脚本 §① 都会守它——
以后谁调数字调重叠了，测试立刻炸，不会静默退化回"倾向于"。

**唯一例外：风险穿透**（用户选定「挡机会不挡风险」）。你持仓的公司恰恰最怕
外部宏观冲击（加息 / 制裁 / 供应链），所以给外部条留一条窄缝，两条路径任一成立即抬档：

* **严重度**：`base >= 0.85` 且 `sentiment <= 0.40`（突发制裁 / 加息 / 黑天鹅）；
* **manas 风险**：`narrative_risk >= 0.60` 且 `sentiment <= 0.40` 且 `base >= 0.60`
  ——沿用旧版 `WEIGHT_RISK` 的门控条件，让 manas 的叙事风险仍然是**活的**（不是死代码）。

命中就抬到 `[0.50, 0.74]`，`pierced=True` 留痕，HTML 上标 `⚠️ 风险穿透`（红色进度条）。
已知边界：这是**纯数值**判定，不认语义——一条重要度高、恰好被判为偏负面的无关新闻
也会被抬档。宁可多抬一条，也不要漏掉一条真的外部风险。

**副作用（刻意）**：穿透条的数值可能高于主题组里的某几条，但它归属「外部要闻」组、
渲染在主题组之后，看起来会"数字大却排后面"。这是刻意让**政策**（我的事优先）
与**度量**（这条多值得看）分属两条轴。

**可调**：`NAJA_NEWS_TIERS="holding=0.78/0.22,theme=0.50/0.24,watchlist=0.32/0.16,macro=0.00/0.24"`
（格式 `档位=下限/权重`）。解析失败或**区间重叠**时回退默认并写入 `config.degraded`。

### 4.2 分组规则与一个实测踩到的坑

| 组 | 标签 | 进入条件 |
|---|---|---|
| `holding` | 持仓相关 | 命中**持仓**标识符 |
| `theme` | 关注叙事 | 命中**主动 follow** 的叙事 / 题材 |
| `macro` | 外部要闻（自选 / 宏观） | 其余（自选 / 穿透风险 / 纯宏观，按相关度排序） |

**为什么自选不单独成组**（用户 2026-10-12 选定）：用户的原话是"集中精力把自己的事情
管管好，不要太多想法去关注外面的机会"。自选虽然有独立档位（组内排得比纯宏观高），
但视觉上它属于"外面"，不配和持仓并列。

**为什么 theme 组只认"主动关注"，不认 manas 默认主题集**：
manas 默认主题集是 **17 个宽泛大类**（全球宏观 / 债券市场 / 外汇与美元 / 地缘政治…），
它们的共同特点是——**几乎命中所有新闻**。实测拿它分组的结果是 39 条全进 `theme`、
`macro` 恒空，分组失去区分度。所以默认主题只作**同档内的微调**（`THEME_NUDGE = 0.04`），
让"沾边但没关注"的新闻排在同分噪声之上，但不跨档、也不构成一组。

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

## 6. 持仓为什么一直是空的（本轮最重的一个 bug）

改口径时发现：系统里的**「持仓」恒为空**，于是「持仓档」在真实数据下**永远不命中**，
而且不报任何错。追下去是一条五步静默链（全部在 news 之外，但直接决定 news 有没有用）：

```
_init_accounts() 按 ['虚拟测试','Spark','Cutie'] 顺序建账户
  → 「虚拟测试」在虚拟盘未注入时 raise RuntimeError
    而内层只写了 except KeyError          ← 异常穿透
  → 被外层 except Exception 吞掉 → 整个循环中断
    Spark / Cutie 从未被创建                ← 一个账户连累全部
  → _load_config_positions() 取不到账户 → 静默 continue
  → Portfolio.get_holdings() 账户为 None → 静默 return []
    「没有持仓」与「账户没建起来」不可区分   ← 静默失效
  → 新闻焦点的 holdings 恒空 → 持仓档永不命中
```

实测：`_accounts=[]`、`_us_portfolios=[]`（全空），而磁盘上躺着真实持仓
（Spark 2 只：NVDA 英伟达 / CRWV CoreWeave；FutuReal 实盘 9 只；Cutie 1 只）。

**三层修复，缺一不可**：

1. **逐账户兜错**：`_init_accounts` 内层改抓 `Exception`，失败记入 `_init_failures`
   并跳过该账户——一个账户坏掉不许连累其它；
2. **区分两种「空」**：新增 `PortfolioManager.get_account_status()` /
   `Portfolio.get_account_status()`，把「账户没建起来」与「账户真的为空」分开；
3. **空持仓必须留痕**：`focus._note_account_health()` 在持仓为空却无任何券商账户时
   写入 `degraded`，报告与面板都显示出来。

**顺带**：新增 `Portfolio.get_all_holdings()` 合并**所有已初始化券商账户**——
钱散在多个账户里（Spark + FutuReal），只看默认账户会把「我真正持有的票」的新闻
错当成「外部机会」。焦点快照的 `sources` 里会记 `持仓账户:Spark,Cutie`，可回溯
钱是从哪读的。

另外展示层加了 `holdings_labels` / `watchlist_labels`：匹配必须同时保留
`code` 与 `name`（新闻里两种写法都会出现），但报告里列成
"baba、阿里巴巴、nvda、英伟达" 太吵，所以展示走「优先中文名」的一列。
（`NewsFocusState` 字段数 == `to_dict()` 键数，已固化成测试。）

### 6.1 顺带修掉的另一个既有隐患

`import deva.naja.attention.os.attention_os` 作为**第一个**被导入的 deva 模块会
`ImportError`：`attention_os` → `text_importance_scorer` → `cognition` → `bandit`
→ `attention_os` 成环。生产因加载顺序侥幸不炸（典型的结构性脆弱）。
已把该导入改为 `__init__` 内惰性导入，并在验证脚本里加了**子进程冷启动回归守卫**。

---

## 7. 验证

```bash
/Users/spark/.local/bin/python3 scripts/verify/verify_news_digest.py --strict
```

9 组检查：① 硬分层不变量 + 持仓优先 + 风险穿透 ② 分组区分度（宽泛主题不升级）
③ 去重 ④ 断线已修（注入 provider 后 `matched_focus_topics` 非空）⑤ 降级诚实
（含档位调重叠时回退并留痕）⑥ 报告可渲染 / 可落盘 ⑦ 静态守卫（容器确实接线）
⑧ 冷启动回归 ⑨ **持仓链路可达性**（券商账户真的被创建；持仓为空必须留痕；
真实新闻里已出现「持仓相关」命中）。

验收：全量 **287 passed**（277 → 287）；快照 **差异字段 0**；
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
* **持仓只认「已初始化的券商账户」**。富途实盘账户由 `futu_portfolio_syncer`
  通过 `register_futu_account()` 注册（默认 `FutuReal`）；**在同步器跑起来之前，
  富途那 9 只持仓不在焦点里**。这是已知时序依赖，不是静默——`sources` 里能看出
  实际读了哪几个账户。
* **穿透是纯数值判定**，不认语义：一条重要度高、恰好被判为偏负面的无关新闻
  也会被抬档。刻意的取舍——宁可多抬一条，也不漏掉一条真的外部风险。
* **穿透条可能"数字大却排后面"**：它数值可高于主题组某几条，但归属「外部要闻」组、
  渲染在主题组之后。这是刻意让**政策**（我的事优先）与**度量**（这条多值得看）
  分属两条轴。
