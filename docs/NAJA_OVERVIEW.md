# Naja 智能交易助手 - 架构与使用文档（2026-04-21）

本文用于系统性说明 Naja 智能交易助手的架构、流程、思想、使用方法与注意事项，并总结近期的结构调整与改动，方便理解与后续演进。

Naja 是一个具有人类般感知、思考和决策能力的智能交易助手，它能够感知市场环境、分析信息、做出决策、执行交易并从经验中学习。

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

### 1.1 核心架构层次

Naja 采用三层架构设计：

```text
入口 / UI / Bootstrap
    ↓
Application（装配、模式、订阅、生命周期）
    ↓
Decision / Attention / Cognition / Signal / Bandit（领域编排与核心能力）
    ↓
Infra / Adapters / Repository / Runtime（通用骨架与技术实现）
```

### 1.2 核心思想

- **可恢复与自动化**：关键组件用 RecoverableUnit 抽象，支持状态恢复与自动运行
- **数据驱动**：所有结果都回流为信号与事件，并进入雷达检测与认知系统
- **认知系统优先**：认知系统不再只是单一策略，而是平台级能力，作为长期与跨场景的上下文
- **注意力调度**：注意力系统根据市场状态和策略表现动态分配资源
- **统一 UI**：管理平台以 Web UI 统一入口，按模块组织能力
- **显式依赖注入**：核心组件通过 AppContainer 进行显式依赖注入，减少全局依赖
- **集中事件订阅**：通过 EventSubscriberRegistrar 统一管理事件订阅，保持领域对象纯净

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

### 4.1 应用层 (Application)
| 文件 | 功能 |
|------|------|
| `application/container.py` | AppContainer 核心组件装配和依赖注入 |
| `application/event_registrar.py` | EventSubscriberRegistrar 集中事件订阅管理 |
| `application/runtime_config.py` | 运行时配置 |
| `application/runtime_modes.py` | 运行模式初始化 |

### 4.2 决策层 (Decision)
| 文件 | 功能 |
|------|------|
| `decision/orchestrator.py` | DecisionOrchestrator 决策编排 |
| `decision/fusion.py` | DecisionFusion 决策融合 |

### 4.3 注意力系统 (Attention)
| 目录 | 功能 |
|------|------|
| `attention/os/` | 注意力操作系统（AttentionOS） |
| `attention/kernel/` | 注意力内核（ManasEngine、QueryState、StateUpdater） |
| `attention/values/` | 价值系统（ValueSystem） |
| `attention/tracking/` | 注意力追踪 |
| `attention/discovery/` | 注意力发现 |

### 4.4 认知系统 (Cognition)
| 文件 | 功能 |
|------|------|
| `cognition/engine.py` | CognitionEngine 认知引擎 |
| `cognition/insight/engine.py` | InsightEngine 洞察引擎 |
| `cognition/analysis/` | 分析模块 |
| `cognition/semantic/` | 语义处理 |

### 4.5 雷达系统 (Radar)
| 文件 | 功能 |
|------|------|
| `radar/engine.py` | 雷达引擎 |
| `radar/news_fetcher.py` | 新闻获取器 |
| `radar/trading_clock.py` | 交易时钟 |
| `radar/global_market_scanner.py` | 全球市场扫描器 + 流动性预测 |
| `radar/senses/` | 感知模块（波动率曲面、先知感知、预尝味、实时尝味） |

### 4.6 策略系统 (Strategy)
| 文件 | 功能 |
|------|------|
| `strategy/runtime.py` | 策略运行时 |
| `strategy/registry.py` | 策略注册表 |
| `strategy/river_wrapper.py` | River 策略包装器 |
| `strategy/river_tick_strategies.py` | Tick 级别策略 |
| `strategy/multi_datasource.py` | 多数据源策略 |
| `strategy/signal_processor.py` | 信号处理器 |
| `strategy/result_store.py` | 结果存储 |

### 4.7 Bandit 系统
| 文件 | 功能 |
|------|------|
| `bandit/runner.py` | Bandit 运行器 |
| `bandit/optimizer.py` | 优化器 |
| `bandit/virtual_portfolio.py` | 虚拟组合 |
| `bandit/market_observer.py` | 市场观察 |
| `bandit/adaptive_cycle.py` | 自适应周期 |
| `bandit/tracker.py` | 持仓追踪 |

### 4.8 基础设施层 (Infra)
| 目录 | 功能 |
|------|------|
| `infra/lifecycle/` | 生命周期管理（Bootstrap） |
| `infra/log/` | 日志系统 |
| `infra/management/` | 通用管理器骨架 |
| `infra/observability/` | 可观测性（健康检查、自动调优） |
| `infra/registry/` | 注册管理 |
| `infra/runtime/` | 运行时服务（线程池、市场时间） |

### 4.9 Web UI
| 文件 | 功能 |
|------|------|
| `web_ui/routes.py` | 路由管理 |
| `web_ui/server.py` | 服务器启动 |
| `web_ui/api.py` | API 接口 |

---

## 5. 注意事项

- **注意力策略**：注意力系统提供多种策略（异常狙击、动量追踪、板块狩猎等），可通过 UI 配置
- **RadarEngine 与 CognitionEngine**：都依赖 ResultStore 的回流数据，若策略未运行则无事件与认知沉淀
- **认知系统**：整合了之前的记忆系统，提供叙事追踪、跨信号分析、洞察生成等能力
- **注意力调度**：注意力系统根据市场状态动态分配资源，优化策略执行优先级
- **持久化**：各管理器支持从数据库加载状态，支持断电恢复

---

## 6. 核心模块详解

### 6.1 应用容器 (AppContainer)

应用容器是 Naja 的组合根，负责核心组件的装配和依赖注入：

```python
from deva.naja.application.container import AppContainer, get_app_container

container = get_app_container()
# 获取核心组件
attention_os = container.attention_os
trading_center = container.trading_center
radar_engine = container.radar_engine
```

核心功能：
- **显式依赖注入**：通过构造函数注入依赖，减少全局依赖
- **组件装配**：统一管理核心组件的创建和初始化
- **生命周期管理**：管理组件的启动和关闭

### 6.2 事件注册器 (EventSubscriberRegistrar)

事件注册器统一管理所有事件订阅：

```python
from deva.naja.application.event_registrar import EventSubscriberRegistrar

registrar = EventSubscriberRegistrar(attention_os, trading_center)
registrar.register_all()
```

核心功能：
- **集中事件订阅**：统一管理所有事件订阅关系
- **领域对象纯净**：领域对象只暴露 handler 方法，不负责订阅逻辑
- **订阅管理**：统一处理订阅的注册和管理

### 6.3 决策编排器 (DecisionOrchestrator)

决策编排器负责决策流程的编排和执行：

```python
from deva.naja.decision.orchestrator import DecisionOrchestrator

orchestrator = DecisionOrchestrator(
    attention_os=attention_os,
    awakened_state={},
    get_first_principles_mind=lambda: ...,
    get_awakened_alaya=lambda: ...,
    get_in_context_learner=lambda: ...,
    get_volatility_surface=lambda: ...,
    get_pre_taste=lambda: ...,
    get_prophet_sense=lambda: ...,
    get_realtime_taste=lambda: ...
)

fusion_output = orchestrator.run_full_pipeline(market_state, snapshot)
```

核心功能：
- **决策流程编排**：协调多个模块的决策过程
- **决策融合**：融合多个决策源的结果
- **感知模块处理**：整合波动率曲面、先知感知等感知模块的输入

### 6.4 注意力操作系统 (AttentionOS)

注意力操作系统是注意力系统的核心：

```python
from deva.naja.attention.os.attention_os import AttentionOS

attention_os = AttentionOS(insight_pool=insight_pool)
```

核心功能：
- **注意力分配**：根据市场状态动态分配注意力资源
- **事件处理**：处理热点计算、热点转移等事件
- **决策生成**：基于注意力状态生成决策

### 6.5 认知引擎 (CognitionEngine)

认知引擎是平台级认知输入输出入口：

```python
from deva.naja.cognition import CognitionEngine

engine = CognitionEngine()
```

核心功能：
- **洞察管理**：管理认知产物和洞察
- **语义处理**：处理市场语义信息
- **跨信号分析**：分析多个信号源的信息

### 6.6 雷达引擎 (RadarEngine)

雷达引擎用于检测市场模式、异常和概念漂移：

```python
from deva.naja.radar import RadarEngine

radar = RadarEngine(trading_clock=trading_clock)
```

核心功能：
- **市场扫描**：扫描全球市场信号
- **异常检测**：检测市场异常和概念漂移
- **流动性预测**：预测市场流动性变化

### 6.7 Bandit 自适应交易

Bandit 系统是基于多臂老虎机的自适应交易系统：

```python
from deva.naja.bandit import BanditAutoRunner

runner = BanditAutoRunner()
runner.start()
```

核心功能：
- **Virtual Portfolio**：虚拟组合管理
- **Market Observer**：市场观察
- **Adaptive Cycle**：自适应交易周期
- **Signal Listener**：信号监听
- **Position Tracker**：持仓追踪