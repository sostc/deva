# Naja 量化平台架构

> 基于最新代码结构（2026-03-17）

## 概述

Naja 是一个"可恢复单元（RecoverableUnit）驱动的统一管理平台"，目标是把数据源、策略、任务、信号、雷达检测、记忆系统、LLM 调节统一在一个平台里。

## 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web UI (PyWebIO)                        │
├─────────────────────────────────────────────────────────────────┤
│  home │ tasks │ datasource │ strategy │ memory │ radar │ agent   │
├─────────────────────────────────────────────────────────────────┤
│                      Naja Supervisor                             │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   策略系统       │    记忆系统      │      雷达系统               │
│  Strategy       │   Memory        │      Radar                  │
│  - River        │   - 短期记忆     │   - Pattern Detection       │
│  - Multi-DS     │   - 长期记忆     │   - Anomaly Detection      │
│  - Signal       │   - 主题沉淀     │   - Drift Detection        │
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

### 2. 记忆系统 (`deva/naja/memory/`)

| 文件 | 功能 |
|------|------|
| `core.py` | 记忆核心（短期/长期记忆） |
| `engine.py` | 记忆引擎（沉淀逻辑） |
| `ui.py` | 记忆 UI |

### 3. 雷达系统 (`deva/naja/radar/`)

| 文件 | 功能 |
|------|------|
| `engine.py` | 雷达引擎（Pattern/Drift/Anomaly） |
| `ui.py` | 雷达 UI |

### 4. Bandit 系统 (`deva/naja/bandit/`)

| 文件 | 功能 |
|------|------|
| `runner.py` | Bandit 运行器 |
| `optimizer.py` | 优化器 |
| `virtual_portfolio.py` | 虚拟组合 |
| `market_observer.py` | 市场观察 |

### 5. Agent 系统 (`deva/naja/agent/`)

| Agent | 功能 |
|-------|------|
| Hanxin | 交易执行 |
| Liubang | 持仓分析 |
| Zhangliang | 策略调度 |
| Xiaohe | 对话交互 |

### 6. 数据源 (`deva/naja/datasource/`)

| 类型 | 说明 |
|------|------|
| timer | 定时拉取数据 |
| stream | 实时数据流 |
| file | 文件监控 |
| directory | 目录监控 |
| replay | 历史数据回放 |

## 数据流

```
数据源 → 策略系统 → ResultStore
                ↓
        ┌───────┴───────┐
        ↓               ↓
    RadarEngine    MemoryEngine
        ↓               ↓
    雷达事件         记忆沉淀
        ↓               ↓
        ┌───────┬───────┘
                ↓
          LLM 调节器
          (策略优化建议)
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
| `/memory` | 记忆系统 |
| `/radaradmin` | 雷达事件 |
| `/agentadmin` | Agent 管理 |
| `/llmadmin` | LLM 调节 |
| `/signaladmin` | 信号流 |
| `/configadmin` | 配置 |

## 记忆策略注册

```bash
python deva/naja/strategy/tools/register_memory.py
```

## 相关文档

- [NAJA_OVERVIEW.md](../NAJA_OVERVIEW.md) - 详细架构说明
- [策略指南](strategy_guide.md)
- [数据源指南](datasource_guide.md)
- [记忆系统指南](memory_guide.md)
- [雷达系统指南](radar_guide.md)
