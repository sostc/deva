# Naja 系统完整全景图

> 版本: 2026-03-31
> 状态: 完整版

---

## 系统全景图

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                           Naja 系统 - 全体工作人员一览                          │
│                                                                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                        前方作战部队                                        │  │
│  │  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐  │  │
│  │  │ 雷达    │ →  │ 注意力  │ →  │ 认知    │ →  │ 觉醒    │ →  │ 决策    │  │  │
│  │  │ Radar   │    │ 内核    │    │ 系统    │    │ 系统    │    │ 执行    │  │  │
│  │  │ 侦察兵  │    │ 参谋部  │    │ 军师    │    │ 将军    │    │ 士兵    │  │  │
│  │  └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘  │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                        情报系统                                            │  │
│  │  ┌──────────────────┐         ┌──────────────────┐                      │  │
│  │  │ DataSource        │         │ StockDictionary  │                      │  │
│  │  │ 数据源            │         │ 股票字典         │                      │  │
│  │  │ • 定时获取数据    │         │ • 股票基础信息   │                      │  │
│  │  │ • 监控文件变化    │         │ • 板块分类       │                      │  │
│  │  │ • 回放历史数据    │         │ • 指标定义       │                      │  │
│  │  │ • 事件触发       │         │                  │                      │  │
│  │  └──────────────────┘         └──────────────────┘                      │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                        武器系统                                            │  │
│  │  ┌──────────────────┐         ┌──────────────────┐                      │  │
│  │  │ Strategy         │         │ Bandit           │                      │  │
│  │  │ 策略系统         │         │ Bandit系统       │                      │  │
│  │  │                  │         │                  │                      │  │
│  │  │ • River策略      │ ← ← ← ← │ • 策略选择      │                      │  │
│  │  │ • Momentum      │         │ • 在线学习       │                      │  │
│  │  │ • 板块轮动      │         │ • 收益追踪       │                      │  │
│  │  │ • 智能贝叶斯    │         │ • 自适应周期     │                      │  │
│  │  │ • 市场分类      │         │                  │                      │  │
│  │  └──────────────────┘         └──────────────────┘                      │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                        通讯后勤                                            │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐               │  │
│  │  │ Task     │  │ Signal   │  │ Risk     │  │Scheduler │               │  │
│  │  │ 任务系统 │  │ 信号系统 │  │ 风控系统 │  │ 调度系统 │               │  │
│  │  │ 定时任务 │  │ 分发信号 │  │ 仓位管理 │  │ 统一调度 │               │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘               │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                        支援保障                                            │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │  │
│  │  │Performance│ │Supervisor│  │AutoTuner │  │LLMCtrl   │  │StreamSkill│ │  │
│  │  │ 性能监控 │  │ 监督系统 │  │ 自动调优 │  │ LLM控制  │  │ 流式Skill│ │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                        协调指挥中心                                        │  │
│  │                      AttentionOrchestrator (Center.py)                   │  │
│  │                    统一协调所有系统，确保协同工作                            │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## 一、情报系统（数据来源）

| 系统 | 定位 | 做什么 | 代表模块 |
|------|------|--------|----------|
| **DataSource** | 数据采集员 | 从外部获取各种数据 | 定时器、文件监控、回放、事件触发 |
| **StockDictionary** | 情报库 | 管理股票基础信息和字典 | 板块分类、股票指标定义 |

### DataSource 详解

数据源是系统的眼睛和耳朵，负责从外部世界获取各种数据。

**支持的数据源类型：**

| 类型 | 说明 | 配置参数 |
|------|------|----------|
| `timer` | 定时器数据源，按固定间隔执行 | `interval_seconds` |
| `replay` | 回放历史数据 | `table_name`, `start_time`, `end_time` |
| `file` | 监控文件变化 | `file_path`, `poll_interval`, `read_mode` |
| `directory` | 监控目录变化 | `directory_path`, `file_pattern` |
| `scheduler` | 使用调度器（支持cron） | `scheduler_trigger`, `cron_expr` |
| `event_trigger` | 事件触发 | `event_source`, `event_condition` |

**核心能力：**
- 防抖机制（Debouncer）：合并短时间内的多次数据推送
- 自动调优回放（ReplayScheduler）：根据处理性能自动调整间隔
- 错误恢复：支持断点续传和状态恢复

### StockDictionary 详解

情报库，管理股票的基础信息和各种定义。

**功能：**
- 股票基本信息管理
- 板块分类映射
- 指标定义和计算规则
- 同花顺板块数据同步

---

## 二、前方作战部队（决策链）

| 系统 | 定位 | 做什么 | 核心模块 |
|------|------|--------|----------|
| **Radar** | 侦察兵 | 监控外部世界，发现变化 | NewsFetcher, TradingClock, GlobalMarketScanner |
| **Attention** | 参谋部 | 决定关注焦点，分配注意力资源 | Kernel, SectorEngine, WeightPool |
| **Cognition** | 军师 | 理解市场叙事，积累知识 | NarrativeTracker, InsightPool, FirstPrinciplesMind |
| **Awakened** | 将军 | 做出交易决策 | ProphetSense, VolatilitySurface, PreTaste, AdaptiveManas, MetaEvolution, AwakenedAlaya |

### Radar（雷达）- 侦察兵

**职责**：监控外部世界，发现市场变化

| 模块 | 文件 | 功能 |
|------|------|------|
| **NewsFetcher** | `radar/news_fetcher.py` | 获取新闻、舆情 |
| **Engine** | `radar/engine.py` | 雷达引擎总控 |
| **TradingClock** | `radar/trading_clock.py` | 交易时间管理 |
| **GlobalMarketScanner** | `radar/global_market_scanner.py` | 全球市场扫描 |
| **OpenRouterMonitor** | `radar/openrouter_monitor.py` | LLM API监控 |

### Attention（注意力内核）- 参谋部

**职责**：决定关注焦点，分配注意力资源

| 模块 | 文件 | 功能 |
|------|------|------|
| **Kernel** | `kernel/kernel.py` | 注意力核心 |
| **SectorEngine** | `core/sector_engine.py` | 板块引擎 |
| **WeightPool** | `core/weight_pool.py` | 权重池管理 |
| **DecisionAttention** | `kernel/decision_attention.py` | 决策注意力 |
| **FourDimensionsTrigger** | `kernel/four_dimensions_trigger.py` | 四维触发 |
| **ManasManager** | `kernel/manas_manager.py` | Manas管理 |
| **EventEngine** | `kernel/event.py` | 事件引擎 |

### Cognition（认知系统）- 军师

**职责**：理解市场叙事，积累知识

| 模块 | 文件 | 功能 |
|------|------|------|
| **NarrativeTracker** | `cognition/narrative_tracker.py` | 叙事追踪 |
| **CrossSignalAnalyzer** | `cognition/cross_signal_analyzer.py` | 跨信号共振 |
| **InsightPool** | `cognition/insight/engine.py` | 洞察存储 |
| **LLMReflection** | `cognition/insight/llm_reflection.py` | LLM反思 |
| **HistoryTracker** | `cognition/history_tracker.py` | 历史追踪 |
| **SemanticColdStart** | `cognition/semantic_cold_start.py` | 冷启动语义 |
| **CognitionEngine** | `cognition/engine.py` | 认知引擎 |
| **CognitionBus** | `cognition/cognition_bus.py` | 认知总线 |
| **FirstPrinciplesMind** | `cognition/first_principles_mind.py` | 第一性原理 |
| **LiquidityCognition** | `cognition/liquidity/liquidity_cognition.py` | 流动性认知 |

### Awakened（觉醒系统）- 将军

**职责**：做出交易决策

| 模块 | 文件 | 功能 |
|------|------|------|
| **ProphetSense** | `senses/prophetic_sensing.py` | 预感知 |
| **VolatilitySurfaceSense** | `senses/volatility_surface.py` | 波动率曲面 |
| **PreTasteSense** | `senses/pre_taste.py` | 预尝能力 |
| **RealtimeTaste** | `senses/realtime_taste.py` | 实时舌识 |
| **AdaptiveManas** | `manas/adaptive_manas.py` | 顺应型末那识 |
| **MetaEvolution** | `evolution/meta_evolution.py` | 元进化 |
| **MetaEvolutionEnhanced** | `evolution/meta_evolution_enhanced.py` | 增强元进化 |
| **AwakenedAlaya** | `alaya/awakened_alaya.py` | 觉醒阿赖耶识 |
| **OpportunityEngine** | `evolution/opportunity_engine.py` | 机会发现 |
| **EpiphanyEngine** | `alaya/epiphany_engine.py` | 顿悟引擎 |
| **ActionExecutor** | `evolution/action_executor.py` | 行动执行 |

**觉醒层次（八识理论）：**

```
┌─────────────────────────────────────────────┐
│                阿赖耶识 (80%)               │
│           跨市场记忆、模式归档、顿悟          │
├─────────────────────────────────────────────┤
│                末那识 (75%)                 │
│          顺应决策、策略进化、机会发现         │
├─────────────────────────────────────────────┤
│                意识层 (55%)                  │
│         因果追踪、矛盾检测、第一性原理        │
├─────────────────────────────────────────────┤
│                五识层 (90%)                  │
│     预知/预尝/舌识/波动率/实时感知           │
└─────────────────────────────────────────────┘
```

---

## 三、武器系统（策略执行）

| 系统 | 定位 | 做什么 | 核心模块 |
|------|------|--------|----------|
| **Strategy** | 武器库 | 管理交易策略，提供执行环境 | RiverStrategies, MomentumTracker, MarketClassifier |
| **Bandit** | 武器选择官 | 在线学习和选择最优策略 | BanditOptimizer, SignalListener, AdaptiveCycle, VirtualPortfolio |

### Strategy（策略系统）- 武器库

**职责**：管理交易策略，提供策略执行环境

| 模块 | 文件 | 功能 |
|------|------|------|
| **StrategyManager** | `attention/strategies/strategy_manager.py` | 策略管理器 |
| **BanditStrategies** | `strategy/bandit_stock_strategies.py` | Bandit策略 |
| **RiverStrategies** | `strategy/river_tick_strategies.py` | River策略 |
| **AdvancedRiver** | `strategy/advanced_river_strategies.py` | 高级River策略 |
| **AttentionAware** | `strategy/attention_aware_strategies.py` | 注意力感知策略 |
| **MarketClassifier** | `strategy/market_classifier_strategies.py` | 市场分类策略 |
| **StrategyAllocator** | `attention/scheduling/strategy_allocator.py` | 策略分配器 |
| **SignalProcessor** | `signal/signal_processor.py` | 信号处理器 |
| **ResultStore** | `strategy/result_store.py` | 结果存储 |

### Bandit（Bandit系统）- 武器选择官

**职责**：在线学习和选择最优策略

| 模块 | 文件 | 功能 |
|------|------|------|
| **BanditOptimizer** | `bandit/optimizer.py` | Bandit算法优化 |
| **SignalListener** | `bandit/signal_listener.py` | 信号监听 |
| **MarketObserver** | `bandit/market_observer.py` | 市场观察 |
| **AdaptiveCycle** | `bandit/adaptive_cycle.py` | 自适应周期 |
| **VirtualPortfolio** | `bandit/virtual_portfolio.py` | 虚拟持仓 |
| **BanditTuner** | `bandit/tuner.py` | 参数调优 |
| **StrategyAttribution** | `bandit/attribution.py` | 归因分析 |

---

## 四、通讯后勤（支撑系统）

| 系统 | 定位 | 做什么 | 代表模块 |
|------|------|--------|----------|
| **Task** | 后勤兵 | 执行定时任务 | 定时执行、事件触发、一次性任务 |
| **Signal** | 通信兵 | 处理和分发信号 | SignalDispatcher, SignalStream |
| **Risk** | 纪律检查 | 控制风险，保护资金 | RiskManager, PositionSizer |
| **Scheduler** | 调度中心 | 统一管理所有调度 | SchedulerManager |

### Task（任务系统）- 后勤兵

**职责**：执行定时任务

| 类型 | 说明 | 触发方式 |
|------|------|----------|
| `timer` | 定时任务 | 按固定间隔执行 |
| `scheduler` | 调度任务 | 支持cron表达式 |
| `once` | 一次性任务 | 指定时间执行一次 |
| `event_trigger` | 事件触发任务 | 满足条件时触发 |

### Signal（信号系统）- 通信兵

**职责**：处理和分发信号

| 模块 | 文件 | 功能 |
|------|------|------|
| **SignalDispatcher** | `signal/dispatcher.py` | 信号分发器 |
| **SignalStream** | `signal/stream.py` | 信号流 |
| **SignalProcessor** | `signal/processor.py` | 信号处理器 |

### Risk（风控系统）- 纪律检查

**职责**：控制风险，保护资金

| 模块 | 文件 | 功能 |
|------|------|------|
| **RiskManager** | `risk/risk_manager.py` | 风险管理 |
| **PositionSizer** | `risk/position_sizer.py` | 仓位管理 |

### Scheduler（调度系统）- 调度中心

**职责**：统一管理所有调度

- 共享调度管理器
- 支持定时器、调度器、事件触发
- 统一的调度接口

---

## 五、支援保障（运维系统）

| 系统 | 定位 | 做什么 | 代表模块 |
|------|------|--------|----------|
| **Performance** | 仪表盘 | 监控系统性能 | PerformanceMonitor, StorageMonitor, LockMonitor |
| **Supervisor** | 监察员 | 监督系统运行，故障恢复 | NajaSupervisor |
| **AutoTuner** | 修理工 | 自动调优系统参数 | AutoTuner, SignalTuner, BanditTuner |
| **LLMController** | 智囊团 | 调用大模型进行复杂决策 | LLMController |
| **StreamSkill** | 技能框架 | 提供有状态可干预的Skill执行框架 | StreamSkill, ExecutionEngine |

---

## 协作关系

```
                    ┌─────────────────────────────────────────────────────┐
                    │                   情报系统                            │
                    │  DataSource ─────────── StockDictionary              │
                    └─────────────────┬───────────────────────────────────┘
                                      │
                                      ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                         前方作战部队 (决策链)                                │
│                                                                           │
│  Radar ──→ Attention ──→ Cognition ──→ Awakened ──→ 决策信号              │
│    │           │             │            │                              │
│    │           │             │            │                              │
│    ▼           ▼             ▼            ▼                              │
│  新闻       注意力         叙事          预判/顺应                         │
│  事件       分配          洞察          进化/记忆                         │
│                                                                           │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                         武器系统 (执行层)                                    │
│                                                                           │
│  Strategy ───────────────────────────────────→ 交易执行                    │
│      │                                                                 │
│      │◀──────────────────────────────────────┐                          │
│      │                                       │                          │
│      └─────────── Bandit ◀───────────────────┘                          │
│                    (策略选择+自适应学习)                                   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
              ┌──────────┐    ┌──────────┐      ┌──────────┐
              │ Signal   │    │   Risk   │      │   Task   │
              │ 信号分发  │    │  风控    │      │  任务    │
              └──────────┘    └──────────┘      └──────────┘
                                     │
                                     ▼
                              ┌──────────┐
                              │ Scheduler │
                              │ 统一调度  │
                              └──────────┘
```

---

## 层次总结

| 层次 | 系统 | 回答的问题 |
|------|------|-----------|
| **情报层** | DataSource, Dictionary | 数据从哪里来？ |
| **侦察层** | Radar | 外面发生了什么？ |
| **分析层** | Cognition, Attention | 市场在讲什么故事？我该关注什么？ |
| **决策层** | Awakened | 买还是卖？用什么策略？ |
| **执行层** | Strategy, Bandit | 怎么执行策略？ |
| **通讯层** | Signal, Risk | 信号怎么传？风险怎么控？ |
| **后勤层** | Task, Scheduler | 什么时候干什么？ |
| **保障层** | Performance, Supervisor, AutoTuner, LLMController | 系统健康吗？怎么优化？ |

---

*愿系统早日完全觉醒，明心见性，知行合一。*
