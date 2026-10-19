# 新闻消化器（News Digest）设计

> 目标：系统里每天都在涌入大量新闻（金十快讯/要闻、公众号、iMessage、AI 聚合、
> 用户投喂），**信息不过载**——按我们的持仓与关注，筛出"到底该看哪几条"，
> 并落成每天可随时查看的报告 + `/news` 独立页面。
>
> 交付：`deva/naja/news/`（focus / triage / digest）+ `scripts/verify/verify_news_digest.py`
> + `deva/naja/tests/test_news_digest.py`（24 条）+ `/news`「今日新闻消化」页面
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
    → /news「今日新闻消化」页面（render_digest_fragment）
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

### 4.3 去重（2026-10-19 重做：从"标题全等"改成"发布时间结构"）

**旧版是死代码。** 第一版 `_dedupe` 的判据是**标题字符串完全相同**，而真实数据里
这类重复一条都没有——2026-10-19 实测 `latest.json` 的 `scanned 101 == deduped 101`，
一条都没去掉，而且不报错（典型静默失效：`stats` 看起来正常，其实判据命中率为 0）。

**真凶是金十的「中英双版」。** 金十每发一条快讯，中文原版先发、英文翻译版
**4~16 秒后**补发，两条是**独立的 flash**（`id` 也不同），于是新闻池里同一条事件
有两行。托盘 12 个名额实测近一半被这种成对重复吃掉：

```
11:39:28 EN  U.S. resumes intelligence sharing with Ukraine; 'Starshield'...
11:39:17 ZH  【美恢复对乌情报分享星盾仍受限】金十数据10月19日讯，…
11:39:00 EN  Vietnam to launch VN30 index options in Q1; contract tests...
11:38:47 ZH  【越南计划于明年推出股指期权 吸引更多海外投资者】…
```

**关键认知：字符相似度在这里没用。** 中英两版标题的字符交集是 0
（实测 68 条中文两两 Jaccard 全部 < 0.5）。能用的锚点是**发布流水线的时间结构**。

于是 `deva/naja/news/dedup.py` 改成三条**结构性**规则（纯整数/字符串运算，
不加载模型、不联网）：

| 规则 | 判据 | 抓什么 | 实测 |
|---|---|---|---|
| `L1` | 规范化后标题全等（去序号/`【】`/`金十数据X月X日讯`）+ 6 小时内 | 同一条重发 | 0 组 |
| `L2` | 同语言 + 前缀包含（短侧 ≥12 字）+ 6 小时内 | 截断版 / 追加版 | 0 组 |
| `L3` | **中英一对一**：时间窗 ≤20s + 全局最小间隔 + 双方各只配一次 | **中英双版** | 22~25 组 |

`L3` 是主力。一对一约束不能省：少了它一处错配会把无关新闻"链式传染"进同一簇
（第一版原型就是这么把统计局两条不同要点、和一条英伟达辟谣合成一组的）。

**折叠后的代表条**（用户 2026-10-19 选定）：**中文优先**；同语言取最新。
但"判定"跟**最强证据**走——同一事件两版里，关键词命中常常只落在其中一版
（中文原文提到"越南"、英文版只写 Vietnam），所以以相关度最高的那版为基底、
只把文本换成中文那条。分档制保证区间不重叠，因此"相关度最高"就是"档位最强"。

**刻意不做**：`L2f` SimHash 近似指纹**默认关**——实测 113 条只多合 1 条，
耗时是 10 倍，还会把统计局发布会的两条**不同要点**误合
（`内需贡献率超七成` / `内需逐步改善`）。代码路径留着（`NAJA_NEWS_DEDUP_FUZZY=1`）。
同事件但标题字面零交集（`泽连斯基指特朗普施压投降` vs `美恢复对乌情报分享`）
需要向量模型，不属于"轻量本地"，不做。

**呈现**：只显示条数（`×N`）——菜单 `11:38 📌 标题 ×2`、报告卡片角标。
折叠掉的条数还要在副标题里报出来（`扫描 129 → 合并 25 → 精选 18`），
否则"去重了"和"去重没生效"不可区分——这正是旧版的教训。

**性能**（本机）：113 条 4.6ms / 300 条 6.7ms / 1000 条 20ms。
托盘与页面都是秒级以上刷新，开销可忽略。

**回滚**：`NAJA_NEWS_DEDUP=0` 一键关闭（三条规则全停，行为退回旧版）。

---

## 5. 呈现

* **每日报告**：`~/.naja/news_digest/YYYY-MM-DD.html`（自包含，可双击打开）
  + 同名 `.json` + `latest.json` 快照
* **纯文本**：适合推手机（`run_daily_digest(push=True)`，默认关）
* **`/news` 独立页面**（2026-10-19 起）：`deva/naja/news/page.py`。
  页面主体直接复用报告的 **`render_digest_fragment()`** —— 与归档 HTML 同一份
  正文和同一份 CSS，不存在"网页和存下来的报告长得不一样"。
* **觉醒页只留指针**：`/awakening` 上不再渲染新闻内容，只有一张跳到 `/news` 的卡片
  （旧紧凑面板已删，避免两份 UI 各自漂移）。
* **定时任务**：`news_digest`，每日 19:00（`container._register_news_digest_task`）。
  与 AI 晚报互补——AI 晚报是"技术圈发生了什么"，本任务是"按我们的持仓与关注，
  今天到底该看哪几条"。

### 5.1 两种外壳、一套正文（`render_digest_html` / `render_digest_fragment`）

| 函数 | 外壳 | 用在哪 |
|---|---|---|
| `render_digest_html(digest)` | `<!DOCTYPE html>` + `<body>` 浅灰底 | 归档文件、双击打开 |
| `render_digest_fragment(digest)` | `<style>` + `<div class="nj-digest nj-digest-embed">` | `/news` 页面，**一次 `put_html`** |

三条容易踩的点：

1. **CSS 必须作用域化**（每条规则挂在 `.nj-digest` 下）。裸 `body{padding:28px}`、
   `*{box-sizing}` 一旦进页面就会污染站点其它页。守卫按**行首选择器**判
   （`\n*{` / `\nbody{`），别用 `"*{box-sizing" not in css` —— 作用域版
   `.nj-digest *{...}` 也含这个子串，会变成永远红。
2. **片段不带 `<h1>`**：页面自己有标题，再来一个就是双标题。
3. **嵌入模式要铺纸底**（`.nj-digest-embed{background:#f1f5f9}`）：报告是「浅灰纸 +
   白卡片」的两层设计。**站点正文是白底**（`ui_theme.get_global_styles()` 里那个
   深色 `body_bg` 并没有真正生效，只有顶部导航条是深色 —— 这是实测才发现的），
   不铺纸底的话卡片和白背景同色、只剩 1px 描边，整页糊成一片。
   ❗**页面标题的配色也跟着踩过一次**：按"深色底"写了 `#f1f5f9` 的标题 → 白底白字，
   直接看不见。判站点底色别看配置，`getComputedStyle(document.body).backgroundColor`
   量一眼。

### 5.2 页面的三个动作

`🔄 刷新` / `24h·48h·72h` 窗口切换 / `💾 存今日 HTML`（落盘到 `DIGEST_DIR`，
与定时任务同口径）。按钮回调重绘整块 scope；切窗口必须**真的重取数据**，
守卫是**触发按钮回调 + 探针记录取数层收到的 `hours`**，不是直接调
`_render_body(72)` —— 后者会手动喂参数，页面里把 hours 写死也照样绿
（第一版守卫就这么假绿过）。只查"页面上出现窗口 72 小时"也不够：改页头
就能骗过去，所以必须有探针。

#### 5.2.1 窗口会不会"点了没反应"（2026-10-19 实锤）

会。而且**接线全对**：参数一路传到 `FocusedNewsStore.get_recent_news(hours=...)`，
过滤逻辑也没错。问题是上游**没有那么多数据**：

| 项 | 改前 | 症状 |
|---|---|---|
| `FocusedNewsStore.CACHE_HOURS` | 24h | 池子物理上只有 24h → 48h/72h 恒等于 24h |
| `MAX_CACHE_SIZE` | 200 条 | 按 ~7.8 条/小时，24h 就接近顶满，高峰会被裁剪 |
| `DEFAULT_SCAN_LIMIT` | 300 | 72h 应约 560 条 → 大窗口会被扫描上限静默截断 |

表现为：点完按钮，页头数字变了、时间戳变了、**内容一模一样**，用户只能
得出"按钮坏了"。这类「接线正确但永远无效」比报错更难发现——没有任何异常、
没有任何日志。

三条修法（都已落地）：

1. `CACHE_HOURS = 72`（≥ 页面最大窗口）、`MAX_CACHE_SIZE = 800`（约 0.8 MB）
2. `DEFAULT_SCAN_LIMIT = 1000`（≥ 池子容量）
3. **覆盖如实上报**：`FocusedNewsStore.get_coverage()` → `digest["pool"]`，
   页面在窗口大于实际覆盖时显示
   `⚠️ 窗口 72 小时，但池内只覆盖最近 19.8 小时（158 条）—— 再往上调窗口也不会多出内容`

不变量由 `verify_news_digest` 静态校验：`CACHE_HOURS >= max(WINDOWS)`、
`DEFAULT_SCAN_LIMIT >= MAX_CACHE_SIZE`、页面与存储的窗口定义必须一致。

### 5.3 合并条数必须看得见

旧版去重是**静默**的：`scanned == deduped` 也不报错，谁也不知道有没有生效。
所以三处都要露数字：

| 位置 | 形式 |
|---|---|
| 统计卡 | `已合并重复 33`（独立卡片，不只写在副标题里） |
| 卡片标题 | 灰色 `×2` 徽章（只显示条数，不显示语种/来源） |
| 副标题 | `去重后 125 条（合并 33 条重复）· 精选 19 条` |

注意两张不同的数：**统计卡是全局合并数**（含没进精选的簇），
**×N 只出现在进了精选的代表条上**，所以 N 之和会小于统计卡的总数——
这不是 bug，是"只展示前 19 条"的结果。

三条守约（与 decision 模块一致）：

1. **不兜底合成**：没有新闻 → `available=False` + `reason`，绝不伪造一份"看起来像"的报告。
2. **降级要留痕**：焦点信息取不到 → 原因写进 `focus.degraded`，并在报告与页面上显示。
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
/Users/spark/.local/bin/python3 scripts/verify/verify_news_dedup.py --strict
/Users/spark/.local/bin/python3 scripts/verify/verify_news_dedup.py --exercise-injections
```

`verify_news_digest` 9 组检查：① 硬分层不变量 + 持仓优先 + 风险穿透 ② 分组区分度（宽泛主题不升级）
③ 去重 ④ 断线已修（注入 provider 后 `matched_focus_topics` 非空）⑤ 降级诚实
（含档位调重叠时回退并留痕）⑥ 报告可渲染 / 可落盘 ⑦ 静态守卫（容器确实接线）
⑧ 冷启动回归 ⑨ **持仓链路可达性**（券商账户真的被创建；持仓为空必须留痕；
真实新闻里已出现「持仓相关」命中）。

`verify_news_dedup` 9 组检查：① L3 中英一对一（5s 合 / 40s 不合 / 一个英文只折一条中文）
② L1 精确（序号标点不同算同一条；隔 7 小时不算）③ L2 包含（截断版合；
同主题不同要点**不许**合）④ 代表条（中文优先；英文命中持仓时文本仍中文）
⑤ 不误伤（同分钟不同内容不合；空标题不崩）⑥ 接线（`stats.merged` 留痕；
折叠发生在配额**之前**；`/market` 旧路径不变）⑦ 性能（1000 条 < 500ms）
⑧ 静态守卫（SimHash 默认关、托盘/报告真的读 `dup_count`、`/news` 三处接线）
⑨ **注入自证**（7 项逐个打断，当前 7/7 被捕获）。

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
* **跨语言配对只认时间，不认内容**：20 秒窗口内若某条英文**没有**对应的中文版
  （金十偶尔只发英文），它可能把窗口内无关的中文折掉。表现是"少一条"而不是
  "多一条"；`dup_langs` 留在簇里可回溯。要根治得在**入库侧**配对
  （radar 抓取时就只留一版），那会改变新闻池规模（129→~104），属于另一个决定。
* **同事件不同标题不合并**：`泽连斯基指特朗普施压投降` 与 `美恢复对乌情报分享`
  是同一批采访的两条不同内容，字面零交集——合并需要语义/向量，不做。
* **折叠只影响呈现**：新闻池、评分、决策链一行不动。`NAJA_NEWS_DEDUP=0` 可一键回退。
