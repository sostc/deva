# Naja 量化平台架构

> 基于最新代码结构（2026-04-21）

## 概述

Naja 是一个"可恢复单元（RecoverableUnit）驱动的统一管理平台"，目标是把数据源、策略、任务、信号、注意力调度、认知系统、雷达检测、LLM 调节统一在一个平台里。

## 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web UI (PyWebIO)                        │
├─────────────────────────────────────────────────────────────────┤
│  home │ tasks │ datasource │ strategy │ cognition │ attention │ radar │
├─────────────────────────────────────────────────────────────────┤
│                      Application 层                             │
│  - AppContainer (依赖注入)                                      │
│  - EventSubscriberRegistrar (事件订阅)                          │
│  - RuntimeConfig (运行时配置)                                  │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   决策层         │    认知系统      │      雷达系统               │
│  Decision       │   Cognition     │      Radar                  │
│  - Orchestrator │   - 洞察引擎    │   - 市场扫描               │
│  - Fusion       │   - 语义处理    │   - 异常检测               │
├─────────────────┼─────────────────┼─────────────────────────────┤
│   注意力系统    │    Bandit       │      LLM 调节              │
│  Attention      │   Adaptive      │      LLM Controller         │
│  - AttentionOS  │   - 虚拟组合    │   - 策略优化               │
│  - ManasEngine  │   - 自适应周期  │   - 性能调优               │
├─────────────────┴─────────────────┴─────────────────────────────┤
│                     Infra 层 (基础设施)                          │
│  - 生命周期管理                                                │
│  - 日志系统                                                    │
│  - 可观测性                                                    │
├─────────────────────────────────────────────────────────────────┤
│                     ResultStore (结果存储)                        │
├─────────────────────────────────────────────────────────────────┤
│                      数据源 (Data Sources)                       │
│         Timer │ Stream │ File │ Directory │ Replay               │
└─────────────────────────────────────────────────────────────────┘
```

## 核心模块

### 1. 应用层 (`deva/naja/application/`)

| 文件 | 功能 |
|------|------|
| `container.py` | AppContainer 核心组件装配和依赖注入 |
| `event_registrar.py` | EventSubscriberRegistrar 集中事件订阅管理 |
| `runtime_config.py` | 运行时配置 |
| `runtime_modes.py` | 运行模式初始化 |

### 2. 决策层 (`deva/naja/decision/`)

| 文件 | 功能 |
|------|------|
| `orchestrator.py` | DecisionOrchestrator 决策编排 |
| `fusion.py` | DecisionFusion 决策融合 |

### 3. 策略系统 (`deva/naja/strategy/`)

| 文件 | 功能 |
|------|------|
| `runtime.py` | 策略运行时 |
| `registry.py` | 策略注册表 |
| `river_wrapper.py` | River 策略包装器 |
| `river_tick_strategies.py` | Tick 级别策略 |
| `multi_datasource.py` | 多数据源策略 |
| `signal_processor.py` | 信号处理器 |
| `result_store.py` | 结果存储 |

### 4. 认知系统 (`deva/naja/cognition/`)

| 文件 | 功能 |
|------|------|
| `engine.py` | CognitionEngine 认知引擎 |
| `insight/engine.py` | InsightEngine 洞察引擎 |
| `analysis/` | 分析模块 |
| `semantic/` | 语义处理 |

### 5. 注意力系统 (`deva/naja/attention/`)

| 目录 | 功能 |
|------|------|
| `os/` | 注意力操作系统（AttentionOS） |
| `kernel/` | 注意力内核（ManasEngine、QueryState、StateUpdater） |
| `values/` | 价值系统（ValueSystem） |
| `tracking/` | 注意力追踪 |
| `discovery/` | 注意力发现 |

### 6. 雷达系统 (`deva/naja/radar/`)

| 文件 | 功能 |
|------|------|
| `engine.py` | 雷达引擎 |
| `news_fetcher.py` | 新闻获取器 |
| `trading_clock.py` | 交易时钟 |
| `global_market_scanner.py` | 全球市场扫描器 + 流动性预测 |
| `senses/` | 感知模块（波动率曲面、先知感知、预尝味、实时尝味） |

### 7. Bandit 系统 (`deva/naja/bandit/`)

| 文件 | 功能 |
|------|------|
| `runner.py` | Bandit 运行器 |
| `optimizer.py` | 优化器 |
| `virtual_portfolio.py` | 虚拟组合 |
| `market_observer.py` | 市场观察 |
| `adaptive_cycle.py` | 自适应周期 |
| `tracker.py` | 持仓追踪 |

### 8. 基础设施层 (`deva/naja/infra/`)

| 目录 | 功能 |
|------|------|
| `lifecycle/` | 生命周期管理（Bootstrap） |
| `log/` | 日志系统 |
| `management/` | 通用管理器骨架 |
| `observability/` | 可观测性（健康检查、自动调优） |
| `registry/` | 注册管理 |
| `runtime/` | 运行时服务（线程池、市场时间） |

### 9. LLM 调节 (`deva/naja/llm_controller/`)

| 文件 | 功能 |
|------|------|
| `controller.py` | LLM 控制器 |
| `ui.py` | LLM UI |

### 10. 数据源 (`deva/naja/datasource/`)

| 类型 | 说明 |
|------|------|
| timer | 定时拉取数据 |
| stream | 实时数据流 |
| file | 文件监控 |
| directory | 目录监控 |
| replay | 历史数据回放 |

## 数据流

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

## 启动方式

```bash
python -m deva.naja
```

访问 http://localhost:8080/

## 主要页面

| 路径 | 功能 |
|------|------|
| `/` | 首页 |
| `/taskadmin` | 任务管理 |
| `/dsadmin` | 数据源管理 |
| `/strategyadmin` | 策略管理 |
| `/signaladmin` | 信号流 |
| `/cognition` | 认知系统 |
| `/attentionadmin` | 注意力系统 |
| `/radaradmin` | 雷达事件 |
| `/banditadmin` | Bandit 自适应交易 |
| `/llmadmin` | LLM 调节 |
| `/dictadmin` | 字典管理 |
| `/tableadmin` | 数据表管理 |
| `/performance` | 性能监控 |
| `/configadmin` | 配置 |
| `/logstream` | 日志流 |

## 相关文档

- [NAJA_OVERVIEW.md](../NAJA_OVERVIEW.md) - 详细架构说明
- [strategy_guide.md](strategy_guide.md)
- [datasource_guide.md](datasource_guide.md)
- [cognition_guide.md](cognition_guide.md)
- [attention_guide.md](attention_guide.md)
- [radar_guide.md](radar_guide.md)
- [bandit_guide.md](bandit_guide.md)