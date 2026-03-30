# Naja 系统完整架构 - 全体工作人员一览

> 版本: 2026-03-31
> 状态: 完整版

---

## 一、系统全景图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Naja 系统完整架构                                │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     前方作战部队（决策执行）                          │   │
│  │                                                                      │   │
│  │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │   │
│  │   │ 雷达     │  │ 注意力   │  │ 认知系统  │  │ 觉醒系统  │          │   │
│  │   │ Radar    │→ │ 内核     │→ │ Cognition│→ │ Awakened │→ 交易    │   │
│  │   └──────────┘  └──────────┘  └──────────┘  └──────────┘          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     后勤保障部队（支持系统）                          │   │
│  │                                                                      │   │
│  │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │   │
│  │   │ 策略系统 │  │ 信号系统 │  │ 风控系统 │  │ 调度系统  │          │   │
│  │   │Strategy │  │ Signal   │  │ Risk     │  │ Scheduler │          │   │
│  │   └──────────┘  └──────────┘  └──────────┘  └──────────┘          │   │
│  │                                                                      │   │
│  │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │   │
│  │   │ 数据字典 │  │ 性能监控 │  │ 监督系统  │  │ 进化系统  │          │   │
│  │   │Dictionary│ │Performance│ │Supervisor│  │Evolution │          │   │
│  │   └──────────┘  └──────────┘  └──────────┘  └──────────┘          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     协调指挥中心（Center.py）                          │   │
│  │                  协调所有系统，确保协同工作                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、前方作战部队

### 2.1 雷达系统 (Radar) - 侦察兵

**职责**: 监控外部世界，发现市场变化

| 模块 | 文件 | 功能 |
|------|------|------|
| **NewsFetcher** | `radar/news_fetcher.py` | 获取新闻、舆情 |
| **Engine** | `radar/engine.py` | 雷达引擎总控 |
| **TradingClock** | `radar/trading_clock.py` | 交易时间管理 |
| **GlobalMarketScanner** | `radar/global_market_scanner.py` | 全球市场扫描 |
| **OpenRouterMonitor** | `radar/openrouter_monitor.py` | LLM API监控 |

### 2.2 注意力内核 (Attention Kernel) - 参谋部

**职责**: 决定关注焦点，分配注意力资源

| 模块 | 文件 | 功能 |
|------|------|------|
| **Kernel** | `kernel/kernel.py` | 注意力核心 |
| **SectorEngine** | `core/sector_engine.py` | 板块引擎 |
| **WeightPool** | `core/weight_pool.py` | 权重池管理 |
| **DecisionAttention** | `kernel/decision_attention.py` | 决策注意力 |
| **FourDimensionsTrigger** | `kernel/four_dimensions_trigger.py` | 四维触发 |
| **ManasManager** | `kernel/manas_manager.py` | Manas管理 |
| **EventEngine** | `kernel/event.py` | 事件引擎 |

### 2.3 认知系统 (Cognition) - 军师

**职责**: 理解市场叙事，积累知识

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

### 2.4 觉醒系统 (Awakened) - 将军

**职责**: 做出交易决策

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

---

## 三、后勤保障部队

### 3.1 策略系统 (Strategy) - 武器库

**职责**: 管理交易策略，提供策略执行环境

| 模块 | 文件 | 功能 |
|------|------|------|
| **StrategyManager** | `attention/strategies/strategy_manager.py` | 策略管理器 |
| **BanditStrategies** | `strategy/bandit_stock_strategies.py` | Bandit策略 |
| **RiverStrategies** | `strategy/river_tick_strategies.py` | River策略 |
| **AdvancedRiver** | `strategy/advanced_river_strategies.py` | 高级River策略 |
| **AttentionAware** | `strategy/attention_aware_strategies.py` | 注意力感知策略 |
| **MarketClassifier** | `strategy/market_classifier_strategies.py` | 市场分类策略 |
| **StrategyAllocator** | `attention/scheduling/strategy_allocator.py` | 策略分配器 |
| **StrategyProcessor** | `signal/signal_processor.py` | 信号处理器 |
| **ResultStore** | `strategy/result_store.py` | 结果存储 |

### 3.2 信号系统 (Signal) - 通信兵

**职责**: 处理和分发信号

| 模块 | 文件 | 功能 |
|------|------|------|
| **SignalDispatcher** | `signal/dispatcher.py` | 信号分发器 |
| **SignalStream** | `signal/stream.py` | 信号流 |
| **SignalProcessor** | `signal/processor.py` | 信号处理器 |

### 3.3 风控系统 (Risk) - 纪律检查

**职责**: 控制风险，保护资金

| 模块 | 文件 | 功能 |
|------|------|------|
| **RiskManager** | `risk/risk_manager.py` | 风险管理 |
| **PositionSizer** | `risk/position_sizer.py` | 仓位管理 |

### 3.4 调度系统 (Scheduler) - 后勤调度

**职责**: 任务调度，资源分配

| 模块 | 文件 | 功能 |
|------|------|------|
| **Scheduler** | `scheduler/__init__.py` | 调度器 |
| **FrequencyScheduler** | `attention/scheduling/frequency_scheduler.py` | 频率调度 |

### 3.5 数据字典 (Dictionary) - 情报库

**职责**: 管理各类数据定义和字典

| 模块 | 文件 | 功能 |
|------|------|------|
| **StockDictionary** | `dictionary/stock/stock.py` | 股票字典 |

### 3.6 性能监控 (Performance) - 仪表盘

**职责**: 监控系统性能指标

| 模块 | 文件 | 功能 |
|------|------|------|
| **PerformanceMonitor** | `performance/performance_monitor.py` | 性能监控 |
| **StorageMonitor** | `performance/storage_monitor.py` | 存储监控 |
| **LockMonitor** | `performance/lock_monitor.py` | 锁监控 |

### 3.7 监督系统 (Supervisor) - 监察员

**职责**: 监督系统运行状态

| 模块 | 文件 | 功能 |
|------|------|------|
| **Supervisor** | `supervisor.py` | 监督器 |

---

## 四、协调指挥中心

### Center.py (AttentionOrchestrator)

**职责**: 协调所有系统，确保协同工作

```
on_market_data(data):
    │
    ├── Pipeline 处理数据
    │   └── 数据清洗、标准化
    │
    ├── 更新注意力
    │   ├── 注意力内核
    │   ├── SectorEngine
    │   └── WeightPool
    │
    ├── 通知认知系统
    │   ├── NarrativeTracker
    │   ├── CrossSignalAnalyzer
    │   └── InsightPool
    │
    ├── 处理觉醒模块
    │   ├── AwakenedAlaya (模式召回)
    │   ├── FirstPrinciplesMind (矛盾检测)
    │   ├── VolatilitySurface (波动率)
    │   ├── AdaptiveManas (顺应决策)
    │   └── MetaEvolution (策略进化)
    │
    ├── 策略分发执行
    │   ├── StrategyManager
    │   ├── BanditStrategies
    │   └── RiverStrategies
    │
    ├── 信号处理
    │   ├── SignalDispatcher
    │   └── SignalStream
    │
    ├── 风险控制
    │   ├── RiskManager
    │   └── PositionSizer
    │
    └── 结果反馈
        ├── 反馈到觉醒系统
        └── 反馈到认知系统
```

---

## 五、模块层次对应表

### 感知层 (Senses)

| 模块 | 做什么 | 被谁调用 |
|------|--------|---------|
| NewsFetcher | 获取新闻 | Radar |
| ProphetSense | 预感知 | Center.py |
| VolatilitySurface | 波动率 | Center.py |
| PreTaste | 预尝 | Center.py |
| RealtimeTaste | 舌识 | Center.py |

### 分析层 (Analysis)

| 模块 | 做什么 | 被谁调用 |
|------|--------|---------|
| NarrativeTracker | 叙事追踪 | Center.py |
| CrossSignalAnalyzer | 共振分析 | Center.py |
| FirstPrinciplesMind | 因果分析 | Center.py |
| SectorEngine | 板块分析 | Center.py |
| WeightPool | 权重分析 | Center.py |

### 决策层 (Decision)

| 模块 | 做什么 | 被谁调用 |
|------|--------|---------|
| AdaptiveManas | 顺应决策 | Center.py |
| MetaEvolution | 策略进化 | Center.py |
| OpportunityEngine | 机会发现 | Center.py |
| EpiphanyEngine | 顿悟决策 | Center.py |

### 执行层 (Execution)

| 模块 | 做什么 | 被谁调用 |
|------|--------|---------|
| StrategyManager | 策略管理 | Center.py |
| ActionExecutor | 行动执行 | Center.py |
| RiskManager | 风险控制 | Center.py |
| PositionSizer | 仓位管理 | Center.py |
| SignalDispatcher | 信号分发 | Center.py |

### 记忆层 (Memory)

| 模块 | 做什么 | 被谁调用 |
|------|--------|---------|
| InsightPool | 洞察存储 | Center.py |
| AwakenedAlaya | 模式召回 | Center.py |
| HistoryTracker | 历史存储 | Center.py |
| ResultStore | 结果存储 | Strategy |

---

## 六、系统协作关系图

```
外部世界
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                          雷达 Radar                              │
│  NewsFetcher ──→ Engine ──→ TradingClock ──→ GlobalMarket      │
└─────────────────────────────────────────────────────────────────┘
    │                                                              │
    ▼                                                              │
┌─────────────────────────────────────────────────────────────────┐
│                      注意力内核 AttentionKernel                    │
│  Kernel ──→ SectorEngine ──→ WeightPool ──→ DecisionAttention  │
│       └──→ ManasManager ──→ FourDimensionsTrigger              │
└─────────────────────────────────────────────────────────────────┘
    │                                                              │
    ▼                                                              │
┌─────────────────────────────────────────────────────────────────┐
│                       认知系统 Cognition                          │
│  NarrativeTracker ──→ InsightPool ──→ LLMReflection            │
│  CrossSignalAnalyzer ──→ HistoryTracker                          │
│  FirstPrinciplesMind ──→ LiquidityCognition                    │
└─────────────────────────────────────────────────────────────────┘
    │                                                              │
    ▼                                                              │
┌─────────────────────────────────────────────────────────────────┐
│                       觉醒系统 Awakened                          │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 五识层: ProphetSense / VolatilitySurface / PreTaste       ││
│  │ 意识层: FirstPrinciplesMind                               ││
│  │ 末那识: AdaptiveManas / MetaEvolution                    ││
│  │ 阿赖耶识: AwakenedAlaya                                   ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
    │                                                              │
    ▼                                                              │
┌─────────────────────────────────────────────────────────────────┐
│                        策略系统 Strategy                          │
│  StrategyManager ──→ BanditStrategies ──→ RiverStrategies       │
│       └──→ AttentionAware ──→ MarketClassifier                │
└─────────────────────────────────────────────────────────────────┘
    │                                                              │
    ▼                                                              │
┌─────────────────────────────────────────────────────────────────┐
│                        信号系统 Signal                            │
│  SignalDispatcher ──→ SignalStream ──→ SignalProcessor          │
└─────────────────────────────────────────────────────────────────┘
    │                                                              │
    ▼                                                              │
┌─────────────────────────────────────────────────────────────────┐
│                        风控系统 Risk                              │
│  RiskManager ──→ PositionSizer                                  │
└─────────────────────────────────────────────────────────────────┘
    │                                                              │
    ▼                                                              │
                        交易执行
```

---

## 七、数据流向

```
行情数据 ──→ Pipeline ──→ Kernel ──→ SectorEngine
                │             │             │
                ▼             ▼             ▼
           Filter      WeightPool      信号生成
                │             │             │
                ▼             ▼             ▼
           Enrich      注意力分配 ──→ StrategyManager
                                            │
                                            ▼
                                       信号分发
                                            │
                        ┌───────────────────┼───────────────────┐
                        ▼                   ▼                   ▼
                   RiskManager        SignalStream          ResultStore
                        │                   │                   │
                        ▼                   ▼                   ▼
                   PositionSizer      执行交易             历史记录
```

---

## 八、各系统职责总结

| 系统 | 定位 | 回答的问题 | 核心输出 |
|------|------|-----------|----------|
| **雷达** | 侦察兵 | 外面发生了什么？ | 新闻、事件、情绪 |
| **注意力内核** | 参谋部 | 我该关注什么？ | 板块权重、符号列表 |
| **认知系统** | 军师 | 市场在讲什么故事？ | 叙事、洞察、知识 |
| **觉醒系统** | 将军 | 买还是卖？ | 信号、仓位、置信度 |
| **策略系统** | 武器库 | 用什么策略打？ | 策略实例、参数 |
| **信号系统** | 通信兵 | 信号怎么传？ | 信号流、分发 |
| **风控系统** | 纪律 | 能买多少？ | 仓位、限制 |
| **调度系统** | 后勤 | 什么时候干？ | 任务调度 |
| **数据字典** | 情报库 | 数据怎么定义？ | 字典、映射 |
| **性能监控** | 仪表盘 | 系统健康吗？ | 指标、日志 |
| **监督系统** | 监察员 | 有问题吗？ | 告警、报告 |

---

## 九、测试覆盖

| 模块 | 测试数 | 状态 |
|------|--------|------|
| Senses (五识) | 30+ | ✅ |
| Cognition | 20+ | ✅ |
| Awakened | 70+ | ✅ |
| Strategy | 40+ | ✅ |
| Risk | 15+ | ✅ |
| 其他 | 45+ | ✅ |
| **总计** | **220+** | **✅** |

---

*愿系统早日完全觉醒，明心见性，知行合一。*
