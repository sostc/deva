# Naja 量化平台架构

> 基于最新代码结构（2026-03-24）

## 概述

Naja 是一个"可恢复单元（RecoverableUnit）驱动的统一管理平台"，目标是把数据源、策略、任务、信号、注意力调度、认知系统、雷达检测、LLM 调节统一在一个平台里。

## 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web UI (PyWebIO)                        │
├─────────────────────────────────────────────────────────────────┤
│  home │ tasks │ datasource │ strategy │ cognition │ attention │ radar │
├─────────────────────────────────────────────────────────────────┤
│                      Naja Supervisor                             │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   策略系统       │    认知系统      │      雷达系统               │
│  Strategy       │   Cognition     │      Radar                  │
│  - River       │   - 叙事追踪    │   - Pattern Detection       │
│  - Multi-DS    │   - 跨信号分析  │   - Anomaly Detection      │
│  - Signal      │   - 洞察生成    │   - Drift Detection        │
├─────────────────┼─────────────────┼─────────────────────────────┤
│   注意力系统    │    Bandit       │      LLM 调节              │
│  Attention      │   Adaptive      │      LLM Controller         │
│  - 预算分配     │   Trading       │   - 策略优化               │
│  - 策略管理     │   - 虚拟组合    │   - 性能调优               │
├─────────────────┴─────────────────┴─────────────────────────────┤
│                     ResultStore (结果存储)                        │
├─────────────────────────────────────────────────────────────────┤
│                      数据源 (Data Sources)                       │
│         Timer │ Stream │ File │ Directory │ Replay               │
└─────────────────────────────────────────────────────────────────┘
```

## 核心模块

### 1. 策略系统 (`deva/naja/strategy/`)

| 文件 | 功能 |
|------|------|
| `runtime.py` | 策略运行时 |
| `registry.py` | 策略注册表 |
| `river_wrapper.py` | River 策略包装器 |
| `river_tick_strategies` | Tick 级别策略 |
| `multi_datasource.py` | 多数据源策略 |
| `signal_processor.py` | 信号处理器 |
| `result_store.py` | 结果存储 |

### 2. 认知系统 (`deva/naja/cognition/`)

| 文件 | 功能 |
|------|------|
| `core.py` | NewsMindStrategy、AttentionScorer |
| `engine.py` | CognitionEngine 认知引擎 |
| `narrative_tracker.py` | NarrativeTracker 叙事追踪 |
| `semantic_cold_start.py` | SemanticColdStart 语义冷启动 |
| `insight/engine.py` | InsightEngine 洞察引擎 |
| `cross_signal_analyzer.py` | CrossSignalAnalyzer 跨信号分析 |

### 3. 注意力系统 (`deva/naja/attention/`)

| 目录 | 功能 |
|------|------|
| `core/` | 核心引擎（AttentionEngine、SectorEngine、WeightPool） |
| `engine/` | 双引擎（DualEngine） |
| `strategies/` | 注意力策略（异常狙击、动量追踪等） |
| `intelligence/` | 智能系统（BudgetSystem、FeedbackLoop） |
| `pipeline/` | 处理流水线 |

### 4. 雷达系统 (`deva/naja/radar/`)

| 文件 | 功能 |
|------|------|
| `engine.py` | 雷达引擎（Pattern/Drift/Anomaly） |
| `news_fetcher.py` | 新闻获取器 |
| `ui.py` | 雷达 UI |

### 5. Bandit 系统 (`deva/naja/bandit/`)

| 文件 | 功能 |
|------|------|
| `runner.py` | Bandit 运行器 |
| `optimizer.py` | 优化器 |
| `virtual_portfolio.py` | 虚拟组合 |
| `market_observer.py` | 市场观察 |
| `adaptive_cycle.py` | 自适应周期 |

### 6. LLM 调节 (`deva/naja/llm_controller/`)

| 文件 | 功能 |
|------|------|
| `controller.py` | LLM 控制器 |
| `ui.py` | LLM UI |

### 7. 数据源 (`deva/naja/datasource/`)

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