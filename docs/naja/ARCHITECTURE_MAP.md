# Naja 架构地图（ARCHITECTURE MAP）

> **这份文档回答两个问题：**
> 1. **系统现在长什么样**（分层 / 能力 / 主干链路 / 装配方式）
> 2. **新功能该放哪里**（§6 扩展点索引 —— 加需求先查这张表）
>
> **定位**：这是「导航图」，不是「规范」。规范在 `naja_architecture_baseline.md`，
> 审计与定案在 `architecture_gap_audit_2026-10-15.md` / `cognition_to_decision_paths_2026-10-15.md`。
> **维护约定**：新增顶层包 / 改主干链路 / 改装配方式 → 必须同步本文。
> 行号只是「锚点」，代码会移动，**以符号名（函数 / 类名）为准**。

---

## 0. 三十秒速览

Naja 是一个**持续运行的智能交易助手**，把「感知 → 认知 → 决策 → 执行 → 学习」做成一条闭环。

```
策略信号 ──▶ 交易总线 ──▶ TradingCenter（决策中心）──▶ 闸门 ──▶ 执行 ──▶ 成交回流
   ▲                                                                    │
   └──────────────── 策略层是「方向」的唯一合法来源 ◀──────────────────┘
```

**一句话铁律**：
> 方向（买 / 卖）只能由**策略层**判定；认知层只提供「证据 / 叙事 / 热度」，不提供方向。

---

## 1. 分层总览

按「谁负责什么」分七层。**加功能时先判断它属于哪一层**，再进 §6 找精确落点。

```
┌─ ① 入口层 ────────────────────────────────────────────────────────┐
│ __main__.py（CLI + 服务管理）   scripts/start_tray.py（菜单栏托盘）  │
└───────────────────────────┬───────────────────────────────────────┘
                            ▼
┌─ ② 应用层 / 组合根（怎么把系统拼起来）─────────────────────────────┐
│ application/  container.py(装配) event_registrar.py(集中订阅)      │
│               runtime_config.py runtime_modes.py wake_orchestrator  │
│ supervisor/   生命周期、监控、恢复                                  │
└───────────────────────────┬───────────────────────────────────────┘
                            ▼
┌─ ③ 领域层（系统如何思考 / 行动）───────────────────────────────────┐
│ attention/  感知·注意力        cognition/  认知·叙事·洞察            │
│ decision/   决策编排·融合      manas/      决策中枢门面              │
│ bandit/     执行·交易          risk/       风控                      │
│ watch/      守望（等待机会）   market_hotspot/ 市场热点·策略         │
└───────────────────────────┬───────────────────────────────────────┘
                            ▼
┌─ ④ 资源层（可插拔的「内容」）─────────────────────────────────────┐
│ strategy/（策略）  datasource/（数据源）  tasks/（任务）             │
│ dictionary/（字典） knowledge/（知识）   config/（配置驱动）         │
└───────────────────────────┬───────────────────────────────────────┘
                            ▼
┌─ ⑤ 基础设施层（底座，不含业务目标）───────────────────────────────┐
│ infra/  registry（单例） runtime（执行环境/守护） management（管理器骨架）│
│         log observability adapters（外部适配） notification autostart │
│ events/ 双事件总线 + 桥   state/ 运行状态   signal/ 信号流            │
└───────────────────────────┬───────────────────────────────────────┘
                            ▼
┌─ ⑥ 交付层（人看的 / 人点的）─────────────────────────────────────┐
│ web_ui/（PyWebIO 页面 + API）  home/（首页）  tables/（表管理）      │
│ 各领域自带 ui.py / ui/ 子包（attention/ui、bandit/ui、radar/ui…）    │
└──────────────────────────────────────────────────────────────────┘
```

### 1.1 各层含哪些包 / 规模（2026-10-15 实测）

> 领域层（③）与资源层（④）是加需求最常动的两层 —— **它们的展开详解见 §1.2 / §1.3**。

| 层 | 包 | 规模 | 核心职责 |
|---|---|---|---|
| 入口 | `__main__.py` `scripts/` | — | CLI、服务管理、托盘 |
| 应用 | `application/` | 10 文件 / 3.3k 行 | **组合根**：装配、模式、订阅、唤醒 |
| 应用 | `supervisor/` | 6 文件 / 0.9k 行 | 生命周期、健康检查、恢复 |
| 领域-感知 | `attention/` | 61 文件 / 20.4k 行 | AttentionOS、注意力内核、发现、跟踪 |
| 领域-认知 | `cognition/` | 79 文件 / 27.7k 行 | 叙事、洞察、流动性、语义、美林时钟 |
| 领域-决策 | `decision/` | 7 文件 / 1.2k 行 | 决策编排、融合、计划、sizing、日志 |
| 领域-决策 | `manas/` | 1 文件 | **公共门面**（真正引擎在 `attention/kernel/manas_engine.py`） |
| 领域-执行 | `bandit/` | 34 文件 / 21.6k 行 | 执行、组合、做 T、富途对接、自适应循环 |
| 领域-风控 | `risk/` | 3 文件 / 1.4k 行 | 仓位 sizing、风险管理 |
| 领域-守望 | `watch/` | 13 文件 / 5.6k 行 | 目标→机会→守望→结算 |
| 领域-热点 | `market_hotspot/` | 95 文件 / 31.5k 行 | 热点计算、策略、River/PyTorch 引擎 |
| 资源 | `strategy/` `datasource/` `tasks/` `dictionary/` `knowledge/` `config/` | — | 四类**可插拔资源** + 知识库 + 配置驱动（详见 §1.3） |
| 基础 | `infra/` | 46 文件 / 13.2k 行 | 单例、运行时、管理骨架、日志、适配 |
| 基础 | `events/` | 13 文件 / 3.7k 行 | **双总线 + 桥 + 事件定义** |
| 基础 | `state/` | 7 文件 / 3.0k 行 | 运行状态、唤醒补作业 |
| 基础 | `signal/` `news/` `radar/` `scheduler/` | — | 信号流 / 新闻消化 / 雷达感知 / 调度 |
| 交付 | `web_ui/` `home/` `tables/` | 20+ 文件 | 页面、API、首页、表管理 |
| 其它 | `structural_growth/` `llm_controller/` `tools/` `business/` | — | 结构增长雷达 / LLM 控制 / 工具 |

---

## 1.2 领域层详解 ★（系统「如何思考 / 行动」）

> 领域层是「能力」所在。**加功能时，先判断它属于哪个领域包**。下面每个包都标了
> 「定位 / 关键文件 / 对外入口」。

### attention/ —— 感知 · 注意力（拟人化的「感官」）
**定位**：决定「此刻该关注什么」。含注意力计算内核、协调层、发现、跟踪。

| 子包 / 文件 | 关键类 | 职责 |
|---|---|---|
| `os/attention_os.py` | `AttentionOS` | 注意力操作系统（总入口，被容器装配） |
| `os/os_kernel.py` | `OSAttentionKernel` | AttentionOS 专用内核；**`make_decision` / `get_manas_inputs` 在此** |
| `os/strategy_decision.py` | `StrategyDecisionMaker` | 策略决策器 |
| `kernel/kernel.py` | `AttentionKernel` | 事件级注意力中枢 |
| `kernel/manas_engine.py` | `ManasEngine` `TimingEngine` `RegimeEngine` `RiskEngine` `ConfidenceEngine` | **真·决策中枢**（「要不要动 / 多确信 / 多危险 / 动多大」） |
| `kernel/manas_manager.py` | `ManasManager` | Manas 引擎管理器（单例） |
| `kernel/manas_inputs.py` | `INPUT_CONTRACTS` `DictBackedInputs` | Manas **输入契约**（喂什么给它） |
| `kernel/state.py` | `QueryState` | 全局查询状态 |
| **`orchestration/trading_center.py`** | **`TradingCenter`** | **决策中心！** 收到策略信号后的全流程 |
| `orchestration/signal_executor.py` | `SignalExecutor` | 信号执行 |
| `orchestration/cognition_orchestrator.py` | `CognitionOrchestrator` | 认知协调 |
| `discovery/conviction_validator.py` | `ConvictionValidator` | 价值验证（⚠️ 整层空转，见 §8） |
| `discovery/narrative_block_linker.py` | `NarrativeBlockLinker` | 叙事-题材联动 |
| `tracking/` | `PositionMonitor` `HotspotSignalTracker` | 监控跟踪 |
| `values/system.py` | `ValueSystem` | 价值观系统 |
| `attention_fusion.py` | `AttentionFusion` | 注意力融合层（⚠️ 产出无消费者，见 §8） |
| `block_registry.py` | `BlockRegistry` | **题材的统一语义注册中心**（英文抽象 id） |
| `focus_manager.py` | `AttentionFocusManager` | 主动关注统一管理器 |
| `portfolio.py` | `Portfolio` | 持仓与自选股统一入口 |

> ❗**反直觉但重要**：**`TradingCenter` 住在 `attention/orchestration/`，不在 `decision/`**。
> 找「决策中心」别去 `decision/` 找。

### cognition/ —— 认知（拟人化的「大脑」）
**定位**：把信息变成**叙事、洞察、因果、流动性判断**。

| 子包 / 文件 | 关键类 | 职责 |
|---|---|---|
| `engine.py` | `CognitionEngine` | 认知引擎 |
| `core.py` | `NewsMindStrategy` | 新闻认知 / 话题跟踪 |
| **`bridge.py`** | **`CognitionBridge`** | **统一认知能力访问接口 —— 对外只走这个** |
| `ingestion.py` | `CognitionIngestion` | Radar → 认知 的统一数据流入口 |
| `narrative/tracker.py` | `NarrativeTracker` | 叙事追踪（天-地框架） |
| `narrative/timing.py` | `TimingNarrative` | 时机叙事感知 |
| `narrative/block_mapping.py` | — | 叙事 → 题材映射（**中文题材名**，与 `block_registry` 不同命名空间） |
| `insight/engine.py` | `InsightPool` | 洞察池（认知产物） |
| `insight/llm_reflection.py` | `LLMReflectionEngine` | 慢思考模块 |
| `analysis/first_principles_mind.py` | `FirstPrinciplesMind` | **第一性原理因果分析**（路径 C 的来源） |
| `analysis/cross_signal_analyzer.py` | `CrossSignalAnalyzer` | 共振分析 / 题材联动 |
| `liquidity/liquidity_cognition.py` | `LiquidityCognition` | 跨市场流动性认知 |
| `liquidity/liquidity_predictor.py` | `LiquidityPredictor` | 流动性预测 |
| `semantic/topic_manager.py` | `TopicManager` | 主题管理 |
| `merrill_clock/` | — | 美林时钟 |

### decision/ —— 决策编排（**薄层**，只有 7 个文件）
**定位**：**只负责编排与契约，不含重逻辑**。

| 文件 | 关键类 | 职责 |
|---|---|---|
| `orchestrator.py` | `DecisionOrchestrator` | 决策工作流（调 FP 洞察等） |
| `fusion.py` | `DecisionFusion` `FusionOutput` | **决策融合**（含 `_normalize_fp_insight`） |
| `plan.py` | `DecisionPlan` | 决策产物契约 |
| `sizing.py` | — | 仓位定量（档位 + α + 风险温度 → 0~1 乘子） |
| `journal.py` | `DecisionJournal` | 决策留痕**落盘**（重启可回放） |
| `query.py` | — | 把 `DecisionPlan` 以**纯 dict** 暴露给 UI |

### manas/ —— 决策中枢门面（只有 1 个 `__init__.py`）
**定位**：**纯 re-export，不重写逻辑**。让外部应用只认 `deva.naja.manas`，内部结构怎么变都不影响使用方。
**能力**：「要不要动 / 多确信 / 多危险 / 动多大」，**可脱离交易系统独立使用**。
对外：`ManasEngine` / `ManasSession` / `create_engine` / 输入契约。
> ❗`compute()` 默认**缓存 1 秒**（`ManasConfig.update_interval`）；要立即重算传 `throttle=False`。

### bandit/ —— 执行（拟人化的「手脚」）
**定位**：把 `DecisionPlan` 真正变成一笔单，并管理组合、做 T、学习。

| 分组 | 关键文件 | 职责 |
|---|---|---|
| **执行链** | `execution.py`（`ExecutionBackend` / `VirtualPortfolioBackend` / `FutuSimBackend`）、`adaptive_cycle.py`、`runner.py`、`signal_listener.py` | 下单、自适应循环、自动运行 |
| **行情** | `market_data_bus.py`（`MarketDataBus`）、`futu_quote_source.py`、`us_stock_price_manager.py` | 行情总线、三市场快照 |
| **组合** | `virtual_portfolio.py`（`VirtualPortfolio`）、`portfolio_manager.py`、`futu_sim_portfolio.py`、`futu_portfolio_syncer.py` | 持仓、富途同步 |
| **做 T** | `t_rotation.py`、`t_rotation_runner.py`、`core_position.py`、`intraday_deviation.py`、`core_holdings.py` | 做 T 引擎、底仓账本、日内偏离度 |
| **闸门 / 守望** | `core_establish_gate.py`、`core_establish_watch.py`、`intent_runner.py` | 大环境闸门、意向盯盘 |
| **学习** | `optimizer.py`、`tuner.py`、`attribution.py`、`tracker.py` | UCB 优化、调参、盈亏归因 |
| **供应链** | `supply_chain_graph.py`、`supply_chain_valuation.py`、`fundamental_data_fetcher.py` | 产业链知识图谱、估值 |

### watch/ —— 守望（「等待机会」的一等公民）
**定位**：把「等待」做成可查、可结算的对象。

```
objective.py（要达成什么） → opportunity.py（值得重问决策中心的时刻）
   → watch.py（把目标挂到一组机会上，然后休眠） → registry.py（登记表 + 扫描器）
   → Settlement（结算）
```
| 文件 | 关键类 | 职责 |
|---|---|---|
| `objective.py` | `Objective` `WatchContext` | 目标声明（不含做法） |
| `opportunity.py` | `Opportunity` `PriceDeviation` | 机会 |
| `watch.py` | `Watch` `WatchState` `Settlement` | 守望本体 |
| `registry.py` | `WatchRegistry` | 登记表与扫描器 |
| `intent.py` / `allocation.py` / `rotation.py` | `Intent` / `Allocation` / `RotationIntent` | 三类：意向 / 长期配置 / 做 T |
| `desk.py` / `awakener.py` / `clock.py` | `WatchDesk` / `WatchAwakener` / `MarketClock` | 周期问一次 / 事件腿 / 市场时钟 |

> ❗五条硬纪律：**机会 ≠ 放行 / 不准无限期 / `None ≠ []` / 活性催醒 / 守望不落盘不下单**。

### risk/ —— 风控
| 文件 | 关键类 | 职责 |
|---|---|---|
| `risk_manager.py` | `RiskManager` `RiskAlert` | 风险管理 |
| `position_sizer.py` | `KellySizer` `VolatilitySizer` | 仓位 sizing |

### market_hotspot/ —— 市场热点（**最大的领域包**，31.5k 行）
| 子包 | 职责 |
|---|---|
| **`strategies/`** | **★ 基于热点的交易策略 —— 方向判定的唯一合法来源（`base.py`）** |
| `core/` | 核心热点计算引擎 |
| `engine/` | River + PyTorch 双引擎 |
| `intelligence/` | 智能增强（signal_tuner 等） |
| `integration/` | `MarketHotspotIntegration`（单例名 `attention_integration`） |
| `processing/` `filters/` `scheduling/` `tracking/` `storing/` | 预处理 / 过滤 / 频率调度 / 历史追踪 / 存储 |
| `ui_components/` `push_center.py` | UI 组件、实时推送中心 |

---

## 1.3 资源层详解 ★（可插拔的「内容」）

### 统一机制：RecoverableUnit 条目

`strategy` / `datasource` / `tasks` / `dictionary` 四类**共享同一套抽象**
（`infra/runtime/recoverable.py` 的 **`RecoverableUnit`**：状态保存恢复 + 执行函数恢复）：

```
每个资源包 = Entry（运行实体，继承 RecoverableUnit）
           + Manager（单例管理器，负责 create / 落盘 / 加载）
           + models.py（数据模型 + 落盘表名常量）
```

| 资源 | Entry | Manager | 落盘表（NB） | 对外单例名 |
|---|---|---|---|---|
| 策略 | `strategy/entry.py` `StrategyEntry` | `strategy/manager.py` `StrategyManager` | `naja_strategies`（+ results / experiment） | `strategy_manager` |
| 数据源 | `datasource/entry.py` `DataSourceEntry` | `datasource/manager.py` `DataSourceManager` | `naja_datasources`（+ ds_latest_data） | `datasource_manager` |
| 任务 | `tasks/entry.py` `TaskEntry` | `tasks/manager.py` `TaskManager` | `naja_tasks`（+ task_history） | `task_manager` |
| 字典 | `dictionary/entry.py` `DictionaryEntry` | `dictionary/manager.py` `DictionaryManager` | — | `dictionary_manager` |

> ❗**关键认知**：资源是**落 NB 表的「条目」**，不是在目录里放个文件就被自动发现。
> `config/{strategies,datasources,tasks}/_examples/*.yaml` 只是**示例模板**（`trend_following.yaml` 等），
> 不是自动加载目录。真正的创建路径是 `Manager.create()` → 写表 → 在 UI 里启动。

### 各包补充

- **`strategy/`**：通用策略**框架**（非具体策略）。
  - `runtime.py` 定义 `BaseStrategy` / `RiverStrategyAdapter` / `LegacyStrategyAdapter`；
  - `registry.py` 管版本与变更历史；`output_controller.py` + `output_schema.py` 管**结果分发与结构规范**；
  - 具体策略样例在 `advanced_river_strategies.py` / `bandit_stock_strategies.py` / `hotspot_aware_strategies.py`。
  - ❗**别与 `market_hotspot/strategies/` 混淆**：这里是通用框架，那里是**具体热点策略 + 方向判定**。
- **`datasource/`**：`hotspot_mixin.py` 让数据源具备热点感知；`debouncer.py` 防抖；`plugins/` 放插件。
- **`tasks/`**：具体任务有 `ai_daily_report.py`（AI 日报）、`ai_knowledge_injector.py`、`article_learner.py`、
  `unified_article_monitor.py`（合并 iMessage + 微信文章学习）、`update_economic_data.py`（更新美林时钟）。
- **`dictionary/`**：`tongdaxin_blocks.py` 解析通达成题材；`blocks/` 统一管理 Block 信息；`stock/` 股票字典。
  - ❗**两套 block 命名空间不可混用**：`attention/block_registry`（英文抽象 id `semiconductor`）
    vs `dictionary/blocks/*.yaml` + `config/dictionaries/tongdaxin_blocks.yaml`（通达信**中文题材名** `3D打印`）。
- **`knowledge/`**：`alaya/`（阿赖耶识层）、`wisdom/`（知识库检索）、`knowledge_store.py`、
  `state_manager.py`（状态迁移）、`cognition_interface.py`（**学习层 ↔ 认知层的接口**）。
- **`config/`**：**配置驱动**的落点。`souls/`（人格 JSON）、`keywords/`（叙事/动态/情绪关键词 YAML）、
  `dictionaries/tongdaxin_blocks.yaml`、`narrative/`、`values/`、`system/`；
  加载器 `soul_config_loader.py` / `soul_manager.py` / `file_config.py`。

---

## 2. 主干链路（真钱链路 —— 最该保护）

这是**唯一会动真钱**的路径。任何改动先看这里。

```
① 策略层产出方向
   market_hotspot/strategies/base.py
     · Signal.direction = SignalDirection.from_str(signal.signal_type)   ← 方向唯一合法来源
     · _publish_strategy_event()  →  StrategySignalEvent  →  交易总线

② 集中订阅把信号交给决策中心
   application/event_registrar.py :: _register_trading_center()
     · trading_bus.subscribe("StrategySignalEvent", on_strategy_signal)

③ 决策中心全流程
   attention/orchestration/trading_center.py
     · process_strategy_signal()          ← 入口
     · _full_decision_pipeline(market_state, snapshot)
         ├─ attention_os.make_decision(market_state)   → Manas 闸门（attention/os/os_kernel.py）
         ├─ DecisionOrchestrator（decision/orchestrator.py）→ FP 洞察
         └─ DecisionFusion（decision/fusion.py）        → fused_confidence / action_type
     · gate_ok  = fusion.should_act            （Manas 闸门放行？）
     · conf_ok  = fused_confidence ≥ 阈值       （融合置信度够？）
     · DecisionPlan.from_fusion(...)           → 交易计划

④ 执行
   bandit/adaptive_cycle.py  →  bandit/execution.py  →  券商（目前只到模拟账户）

⑤ 成交回流（闭环）
   bandit/adaptive_cycle.py 发 TradeOutcomeEvent
     → event_registrar.py :: _register_trade_outcome_feedback()
     → TradingCenter.record_trade_outcome()
```

> ⚠️ **否决必须区分两个独立原因**：`!gate_ok`（Manas 没放行）和 `!conf_ok`（置信度不够）
> 不能混成一个「被拒」。日志里要分开打。

---

## 3. 认知 → 决策：四条路径（2026-10-15 定案）

认知（叙事 / 洞察 / 流动性 / 共振）如何影响交易 —— **只有拉取式路径是真的**。

| # | 路径 | 形态 | 现状 |
|---|---|---|---|
| **A** | `BusBridge`：认知事件 → `StrategySignalEvent` | 推送 | ❌ **不该启用**（越过策略层直产方向）。结构已修，默认关，`NAJA_BUS_BRIDGE=1` 才开 |
| **B** | 叙事 → `market_state['narratives']` → `Manas.compute(narratives=)` | 拉取 | ⚠️ 链路通，但 Manas 存入 `_current_narratives` 后**无计算读取** |
| **C** | 叙事 → `FirstPrinciplesMind` → `fp_insights` → **`DecisionFusion`（可达 ±20% 仓位）** | 拉取 | ✅ **本次修通**（一对互相掩盖的 bug，见下） |
| **D** | `world_narrative` → `ConvictionValidator` | 拉取 | ❌ 存入零消费字段；其所在 `AttentionFusion` 整层产出无消费者 |

**必须记住的一对 bug（成对修，不能只修一个）**：
- `decision/orchestrator.py` 曾把 `snapshot` 误当叙事列表传给 `think()` → FP 洞察恒空；
- `decision/fusion.py` 按 dict 访问而生产者给的是 dataclass 对象 → 被上一项掩盖。
- **只修前者 → 决策链从「静默无认知」变成「直接崩溃」。** 现已两者都修。
- 回滚开关：`NAJA_FP_NARRATIVES=0`。

> 完整证据链见 `cognition_to_decision_paths_2026-10-15.md`。

---

## 4. 双事件总线

系统有**两条总线**，职责分离，互不自动串门。

| 总线 | 文件 | 传什么 | 谁订阅 |
|---|---|---|---|
| **认知总线** | `events/cognitive_bus.py` | 叙事更新、时机、风险、共振（**不带股票代码**） | 认知域组件 |
| **交易总线** | `events/trading_bus.py` | `StrategySignalEvent` / `TradeDecisionEvent` / `TradeOutcomeEvent`（StreamBacked，可持久化） | `event_registrar` → TradingCenter |
| **桥** | `events/bus_bridge.py` | 认知事件 → 交易信号 | 默认关（见 §3 路径 A） |

**两条关键纪律**：
- ❗交易总线对 `StrategySignalEvent` 的**去重指纹 = `symbol:direction:分钟`** → 同分钟同标的同方向会合并。别把去重误判成「链路没生效」。
- ❗认知事件**都不带股票代码**：`NarrativeStateEvent` 给叙事**名**、`ResonanceDetectedEvent.symbols` 是**板块 ID**。过桥必须做「叙事名/板块 ID → 代码」解析（三级：`BlockRegistry` → `block_mapping` + `dictionary`）。

---

## 5. 装配与生命周期

### 5.1 启动（组合根 `AppContainer.boot()`，`application/container.py`）

```
__main__.py
  └─ application/web.py :: run_web_application(config)
       └─ AppContainer(boot)                      ← 组合根
            ├─ ① _register_singletons()            注册声明式单例（只注册工厂，不实例化）
            ├─ ② _assemble_core_components()        装配核心（见下）
            ├─ ③ _register_container_components_as_singletons()  容器实例「覆盖注册」
            ├─ ④ _register_health_checks()         注册健康检查项
            └─ ⑤ restore_runtime_state()           恢复运行状态

_assemble_core_components() 内部顺序：
  加载持久化管理器 → 基础组件(trading_clock / market_time / virtual_portfolio / value_system)
  → AttentionOS → Kernel 层(query_state / manas) → event_registrar.register_all()
  → BusBridge 装配（enable_bridge_from_env）→ 各依赖注入 → 后台初始化线程
```

### 5.2 单例机制（`register.py` + `infra/registry/singleton_registry.py`）

两种注册方式，**优先第一种**：

| 方式 | 位置 | 适用 |
|---|---|---|
| **声明式表** | `register.py :: SIMPLE_SINGLETONS` | 纯 `import + Class()` 就能构造的单例 |
| **自定义工厂** | `register.py :: _register_custom_singletons()` | 需要 `_ensure_initialized()` / 复用模块级单例 / 依赖注入 |

- 访问统一走 `SR('名字')`（`from deva.naja.register import SR`）。
- ❗**禁止两个不同语义的名字指向同一对象**（历史事故：`market_time_service` → `trading_clock`）。
- ❗**禁止一个语义两个实例**（历史事故：`snapshot_manager` / `scheduler_manager` 注册表与模块级各造一个）→ 自定义工厂必须**复用**模块级单例。
- ❗`except Exception: 降级` 会把 bug 埋成「长期正常」，**不许静默吞**。

### 5.3 关闭 / 持久化

`supervisor/recovery.py` → `_stop_all_components()`：逐组件调 `save_state()` / `persist_state()` / `shutdown()` / `close(persist=True)`。
新增核心组件**必须实现持久化方法**，并在 `_stop_all_components()` 注册调用。命名约定见 `naja_architecture_baseline.md` §9。

---

## 6. 扩展点索引 ★（加需求先查这张表）

> **用法**：左边找「我要加什么」→ 右边拿到「放哪 + 怎么注册 + 先跑哪个守卫」。

| 我要加… | 放哪 | 怎么注册 / 接线 | 相关守卫 |
|---|---|---|---|
| **新策略（热点类）** | `market_hotspot/strategies/`（继承 `base.py`） | 方向由 `Signal.signal_type` 决定；**这里才是方向合法来源** | — |
| **新策略（框架/适配器）** | `strategy/runtime.py`（`BaseStrategy` / `*Adapter`） | ❗别与上一行混淆：`strategy/` 是通用框架 | — |
| **新策略条目（运行实例）** | — | `StrategyManager.create()` → 写 `naja_strategies` → 在 `strategyadmin` 页启动 | — |
| **新数据源** | `datasource/entry.py`（继承 `RecoverableUnit`） | `DataSourceManager.create()` → 写 `naja_datasources`；带热点感知用 `hotspot_mixin.py` | — |
| **新任务** | `tasks/entry.py`（继承 `RecoverableUnit`） | `TaskManager.create()` → 写 `naja_tasks`；参考 `config/tasks/_examples` | `task_catchup_async` |
| **新字典 / 题材** | `dictionary/` + `config/dictionaries/*.yaml` | ❗注意两套 block 命名空间（§1.3） | — |
| **新认知分析** | `cognition/analysis/`（或 `narrative/` `liquidity/`） | 新子域经 `cognition/bridge.py` 对外暴露 | `cognition_decision_chain` |
| **新风控规则 / 仓位法** | `risk/risk_manager.py` / `risk/position_sizer.py` | 供决策层与 sizing 调用 | — |
| **新执行后端** | `bandit/execution.py`（`ExecutionBackend` 子类） | 现成：`VirtualPortfolioBackend` / `FutuSimBackend` | `futu_sim_execution` |
| **新事件类型** | `events/*_events.py`（dataclass） | 定义 + 在 `events/__init__.py` **逐名导出**（❗导出名单须与定义逐名对齐） | `cognitive_trading_linkage`(①) |
| **新事件消费者** | `application/event_registrar.py` | 新增 `_register_xxx()` 并在 `register_all()` 里调用（**不要**写在对象 `__init__` 里订阅） | — |
| **新单例** | `register.py` | 优先 `SIMPLE_SINGLETONS`；需特殊初始化走 `_register_custom_singletons()` | `singleton_registry_consistency` |
| **新补作业（唤醒同步）** | `state/system/wake_sync_handlers.py` | 实现 `WakeSyncable` → 在 `_create_wake_sync_manager()` 注册 | — |
| **新守望** | `watch/`（`Objective` / `Opportunity` / `Watch`） | `WatchRegistry` 登记；机会 ≠ 放行 | `intent_watch` / `allocation_watch` / `rotation_watch` |
| **新 UI 页面** | `web_ui/pages.py` | 加页面函数 → 在 `web_ui/routes.py` 注册路由 | `health_ui_tabs` / `ui_integration` |
| **新 API 端点** | `web_ui/api_extensions.py` | 继承 `RequestHandler` → 在 `routes.py` 挂路径 | `http_error_contract` |
| **新感知** | `radar/senses/` | 五识层，产出流向认知 | `radar_circular_import` |
| **新警示 / 托盘项** | `infra/notification/` `scripts/` | 托盘改菜单**必须重启** | `tray_*` |
| **新配置项** | `config/`（YAML / Python） | 配置驱动优先，别硬编码 | — |
| **新守卫** | `scripts/verify/verify_xxx.py` | 三段式：正常 exit 0 / `--self-test` / `--strict`；**必须做注入负向验证** | 全部 |

**改哪块先跑哪个守卫**：见 `MEMORY.md`「守护脚本」段（72 个守卫的完整索引）。

### 6.1 三条最容易走错的归属

1. **「决策中心」不是 `decision/`** —— 是 `attention/orchestration/trading_center.py`（`TradingCenter`）。
   `decision/` 只是**编排 + 契约薄层**。
2. **「策略」有两个家** —— 通用框架在 `strategy/`，**具体热点策略（含方向判定）在 `market_hotspot/strategies/`**。
3. **资源是 NB 表里的条目**，不是目录里的文件 —— `config/*/_examples/*.yaml` 只是模板，
   真正的创建是 `Manager.create()` → 落表（`naja_strategies` / `naja_datasources` / `naja_tasks`）。

---

## 7. 守卫与验证（`scripts/verify/`）

- 全部守卫**正常须 exit 0**，`--strict` 不许有豁免。
- 写完守卫**必须注入 bug 做负向验证一次**；负向失败**先怀疑用例再怀疑守卫**。
- **一项保护会掩盖另一项缺失** → 每条守卫都要有**反方向用例**，否则是假绿。
- 静态守卫须「去注释 + 剥 docstring」再扫。

**本次审计新增的三个守卫**（对应 §3 的链路真相）：
- `verify_singleton_registry_consistency.py` —— 取了没注册 / 注册没人取 / 工厂直接构造
- `verify_cognitive_trading_linkage.py` —— 事件导出对齐 / 失效模块引用 / 桥通道 / 桥开关 / Manas 输入真实 / 叙事名 vs 代码
- `verify_cognition_decision_chain.py` —— 叙事读单例 / `market_state.narratives` 写入 / Manas 收 narratives / `think` 不得错位传 snapshot / `fuse` 必须归一化 / 桥默认关

---

## 8. 已知「装配了但没生效」清单（别当已生效）

> 这些是**刻意保留**的现状，不是 bug —— 但**改动前必须知道它们此刻不参与决策**。

| 项 | 现状 |
|---|---|
| `BusBridge` | 默认关（见 §3 A） |
| Manas `_current_narratives` | 存了但无计算读取（路径 B） |
| `AttentionFusion` + `ConvictionValidator` | 千余行，**整层产出零消费者**（展示层遗留物，不是决策输入） |
| `strategy_result_store` / `signal_dispatcher` | 注册了但全库零引用（死装配，保留声明） |
| `RiskAlertEvent` 等 6 个事件类 | 定义了但从未被构造（永不发出） |
| 流动性预测 → 交易 | **是断的**（无独立交易出口） |
| 实盘下单 | `place_order` 只走到模拟账户 |

---

## 9. 相关文档索引

| 文档 | 内容 |
|---|---|
| **本文** `ARCHITECTURE_MAP.md` | 架构地图 + 扩展点索引（加需求先看这里） |
| **`ARCHITECTURE_RISKS.md`** | **易错点登记册**：静默失效家族 / 守卫腐烂 / 待拍板清单 |
| `naja_architecture_baseline.md` | **开发规范**：分层纪律、生命周期、UI 推送规范（4 月） |
| `architecture_gap_audit_2026-10-15.md` | 断链审计：P0/P1/P2 清单 + 修复记录 |
| `cognition_to_decision_paths_2026-10-15.md` | 认知→决策四条路径的实测定案 |
| `p0_linkage_design_2026-10-15.md` | 桥的设计与「开不开」的论证 |
| `naja_anthropomorphic_architecture.md` | 拟人化视角（感知/思考/决策/行动/学习） |
| `..(项目记忆)` `.workbuddy/memory/MEMORY.md` + `DETAILS.md` | AI 会话硬规则 + 细节下沉 |
