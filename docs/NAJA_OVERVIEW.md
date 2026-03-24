# Naja 架构与使用文档（2026-03-24）

本文用于系统性说明 Naja 的架构、流程、思想、使用方法与注意事项，并总结近期的结构调整与改动，方便理解与后续演进。

**目录**
1. 架构与核心思想
2. 数据流与运行流程
3. 使用方法
4. 关键模块说明
5. 注意事项
6. 核心模块详解

---

## 1. 架构与核心思想

Naja 是一个"可恢复单元（RecoverableUnit）驱动的统一管理平台"，目标是把数据源、策略、任务、信号、注意力调度、认知系统、雷达检测、LLM 调节统一在一个平台里。

核心思想包含以下几点：
- **可恢复与自动化**：关键组件用 RecoverableUnit 抽象，支持状态恢复与自动运行
- **数据驱动**：所有结果都回流为信号与事件，并进入雷达检测与认知系统
- **认知系统优先**：认知系统不再只是单一策略，而是平台级能力，作为长期与跨场景的上下文
- **注意力调度**：注意力系统根据市场状态和策略表现动态分配资源
- **统一 UI**：管理平台以 Web UI 统一入口，按模块组织能力

---

## 2. 数据流与运行流程

```
数据源 → 策略系统 → ResultStore → 信号流
                              ↓
              ┌───────────────┼───────────────┐
              ↓               ↓               ↓
        RadarEngine     CognitionEngine   AttentionOrchestrator
        (雷达检测)      (认知中枢)        (注意力调度)
              ↓               ↓               ↓
        雷达事件         叙事追踪          策略管理
        异常检测         跨信号分析         预算分配
        漂移检测         洞察生成
              ↓               ↓               ↓
              └───────────────┼───────────────┘
                              ↓
                    LLMController (LLM调节)
```

---

## 3. 使用方法

**启动与访问：**
```bash
python -m deva.naja
```

**主要页面：**
| 页面 | 路径 | 说明 |
|------|------|------|
| 首页 | `/` | 系统概览 |
| 数据源管理 | `/dsadmin` | 数据源配置 |
| 任务管理 | `/taskadmin` | 定时任务 |
| 策略管理 | `/strategyadmin` | 量化策略 |
| 信号流 | `/signaladmin` | 策略结果可视化 |
| 认知系统 | `/cognition` | 认知中枢、叙事追踪 |
| 注意力系统 | `/attentionadmin` | 注意力调度面板 |
| 雷达事件 | `/radaradmin` | 雷达检测事件 |
| Bandit交易 | `/banditadmin` | 自适应交易 |
| LLM调节 | `/llmadmin` | 模型控制与优化 |
| 字典管理 | `/dictadmin` | 数据字典 |
| 数据表 | `/tableadmin` | 数据表管理 |
| 配置 | `/configadmin` | 系统配置 |
| 性能监控 | `/performance` | 性能指标 |
| 日志流 | `/logstream` | 实时日志 |

---

## 4. 关键模块说明

### 4.1 认知系统 (Cognition)
| 文件 | 功能 |
|------|------|
| `cognition/core.py` | NewsMindStrategy、AttentionScorer |
| `cognition/engine.py` | CognitionEngine 认知引擎 |
| `cognition/narrative_tracker.py` | NarrativeTracker 叙事追踪 |
| `cognition/semantic_cold_start.py` | SemanticColdStart 语义冷启动 |
| `cognition/insight/engine.py` | InsightEngine 洞察引擎 |
| `cognition/cross_signal_analyzer.py` | CrossSignalAnalyzer 跨信号分析 |
| `cognition/ui.py` | 认知系统 UI |

### 4.2 注意力系统 (Attention)
| 目录 | 功能 |
|------|------|
| `attention/core/` | 核心引擎（AttentionEngine、SectorEngine、WeightPool） |
| `attention/engine/` | 双引擎（DualEngine） |
| `attention/strategies/` | 注意力策略实现 |
| `attention/intelligence/` | 智能系统（BudgetSystem、FeedbackLoop） |
| `attention/pipeline/` | 处理流水线 |
| `attention/processing/` | 数据处理（NoiseFilter、TickFilter） |

### 4.3 雷达系统 (Radar)
| 文件 | 功能 |
|------|------|
| `radar/engine.py` | 雷达引擎 |
| `radar/news_fetcher.py` | 新闻获取器 |
| `radar/ui.py` | 雷达 UI |

### 4.4 策略系统 (Strategy)
| 文件 | 功能 |
|------|------|
| `strategy/runtime.py` | 策略运行时 |
| `strategy/registry.py` | 策略注册表 |
| `strategy/river_wrapper.py` | River 策略包装器 |
| `strategy/river_tick_strategies.py` | Tick 级别策略 |
| `strategy/multi_datasource.py` | 多数据源策略 |
| `strategy/signal_processor.py` | 信号处理器 |
| `strategy/result_store.py` | 结果存储 |

### 4.5 Bandit 系统
| 文件 | 功能 |
|------|------|
| `bandit/runner.py` | Bandit 运行器 |
| `bandit/optimizer.py` | 优化器 |
| `bandit/virtual_portfolio.py` | 虚拟组合 |
| `bandit/market_observer.py` | 市场观察 |
| `bandit/adaptive_cycle.py` | 自适应周期 |

### 4.6 LLM 调节
| 文件 | 功能 |
|------|------|
| `llm_controller/controller.py` | LLM 控制器 |
| `llm_controller/ui.py` | LLM UI |

### 4.7 Web UI
| 文件 | 功能 |
|------|------|
| `web_ui.py` | Web UI 入口与路由 |
| `bootstrap.py` | 系统启动引导器 |

---

## 5. 注意事项

- **注意力策略**：注意力系统提供多种策略（异常狙击、动量追踪、板块狩猎等），可通过 UI 配置
- **RadarEngine 与 CognitionEngine**：都依赖 ResultStore 的回流数据，若策略未运行则无事件与认知沉淀
- **认知系统**：整合了之前的记忆系统，提供叙事追踪、跨信号分析、洞察生成等能力
- **注意力调度**：注意力系统根据市场状态动态分配资源，优化策略执行优先级
- **持久化**：各管理器支持从数据库加载状态，支持断电恢复

---

## 6. 核心模块详解

### 6.1 认知引擎 (CognitionEngine)

认知引擎是平台级认知输入输出入口：

```python
from deva.naja.cognition import CognitionEngine, get_cognition_engine

engine = get_cognition_engine()
```

核心功能：
- **NarrativeTracker**：管理市场叙事生命周期
- **SemanticColdStart**：处理新概念的快速学习
- **CrossSignalAnalyzer**：合并新闻和注意力信号
- **InsightEngine**：管理认知产物

### 6.2 注意力协调器 (AttentionOrchestrator)

注意力协调器统一管理注意力分配：

```python
from deva.naja.attention import AttentionOrchestrator

orchestrator = AttentionOrchestrator()
```

核心功能：
- **AttentionEngine**：注意力核心引擎
- **DualEngine**：双引擎处理动量和噪声
- **StrategyManager**：托管多种注意力策略
- **BudgetSystem**：智能分配注意力预算
- **FeedbackLoop**：持续优化注意力分配

### 6.3 雷达引擎 (RadarEngine)

雷达引擎用于检测市场模式、异常和概念漂移：

```python
from deva.naja.radar import RadarEngine, get_radar_engine

radar = get_radar_engine()
```

### 6.4 Bandit 自适应交易

Bandit 系统是基于多臂老虎机的自适应交易系统：

```python
from deva.naja.bandit import BanditRunner

runner = BanditRunner()
runner.start()
```

核心功能：
- **Virtual Portfolio**：虚拟组合管理
- **Market Observer**：市场观察
- **Adaptive Cycle**：自适应周期
- **Signal Listener**：信号监听