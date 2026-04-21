# Deva 项目 Code Wiki

## 目录

1. [项目概述](#项目概述)
2. [系统架构](#系统架构)
3. [核心模块详解](#核心模块详解)
4. [关键类与函数](#关键类与函数)
5. [依赖关系](#依赖关系)
6. [项目运行方式](#项目运行方式)
7. [附录](#附录)

---

## 项目概述

### 项目简介

**Deva** 是一个智能量化与数据处理平台，提供完整的数据流处理、事件驱动架构、AI 认知系统和量化交易功能。

### 核心特性

- **流式处理**：基于 Stream 类的异步数据流处理框架
- **事件驱动**：基于 Tornado 的事件循环和异步处理
- **认知系统**：Naja 子系统提供市场叙事追踪、跨信号分析、洞察生成
- **注意力调度**：智能资源分配和策略优先级管理
- **雷达检测**：市场模式、异常和概念漂移检测
- **量化策略**：支持 River 策略、多数据源、信号处理
- **自适应交易**：基于多臂老虎机的 Bandit 交易系统
- **Web UI**：统一的 PyWebIO 管理界面

---

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web UI Layer                              │
│  (PyWebIO - 统一管理界面)                                        │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                      Naja 量化交易平台                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ 认知系统  │  │ 注意力系统│  │ 雷达检测  │  │ Bandit   │    │
│  │Cognition │  │ Attention│  │ Radar    │  │ Trading  │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │     市场热点 │ 策略系统 │ 信号流 │ LLM控制器             │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                      Deva Core 核心引擎                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Stream   │  │ Bus      │  │ Pipe     │  │ Store    │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Naja 核心模块

| 模块 | 说明 | 路径 |
|------|------|------|
| **application** | 应用容器、运行时配置 | `naja/application/` |
| **attention** | 注意力调度系统 | `naja/attention/` |
| **bandit** | 多臂老虎机交易系统 | `naja/bandit/` |
| **business** | 业务逻辑层 | `naja/business/` |
| **cognition** | 认知引擎、洞察生成 | `naja/cognition/` |
| **datasource** | 数据源管理 | `naja/datasource/` |
| **decision** | 决策系统 | `naja/decision/` |
| **knowledge** | 知识管理系统 | `naja/knowledge/` |
| **llm_controller** | LLM 控制器 | `naja/llm_controller/` |
| **market_hotspot** | 市场热点监测 | `naja/market_hotspot/` |
| **radar** | 雷达检测系统 | `naja/radar/` |
| **strategy** | 策略系统 | `naja/strategy/` |
| **supervisor** | 监管模块 | `naja/supervisor/` |
| **state** | 状态管理 | `naja/state/` |

---

## 核心模块详解

### 1. Application 应用层

#### 1.1 AppContainer

应用容器，负责初始化和管理所有核心组件。

```python
from deva.naja.application.container import AppContainer

container = AppContainer(runtime_config)
result = container.boot()
```

**主要职责：**
- 单例注册与管理
- 组件初始化顺序控制
- 持久化状态恢复

**关键方法：**
- `boot()` - 启动应用容器
- `_register_singletons()` - 注册所有单例
- `_assemble_core_components()` - 装配核心组件

#### 1.2 AppRuntimeConfig

运行时配置管理。

### 2. Attention 注意力系统

注意力调度系统是 Naja 的核心，负责智能分配计算资源。

#### 2.1 核心组件

| 组件 | 说明 |
|------|------|
| **AttentionFusion** | 注意力融合引擎 |
| **NarrativeBlockLinker** | 叙事块链接器 |
| **BlindSpotInvestigator** | 盲点调查器 |
| **ConvictionValidator** | 信念验证器 |

#### 2.2 价值观系统

| 组件 | 说明 |
|------|------|
| **ValueProfile** | 价值观配置 |
| **ValueSystem** | 价值观系统 |
| **ValueMapping** | 价值观映射 |

#### 2.3 编排层

| 组件 | 说明 |
|------|------|
| **CognitionOrchestrator** | 认知编排器 |
| **LiquidityManager** | 流动性管理器 |
| **TradingCenter** | 交易中枢 |
| **SignalExecutor** | 信号执行器 |

#### 2.4 追踪系统

| 组件 | 说明 |
|------|------|
| **PositionMonitor** | 持仓监控 |
| **ReportGenerator** | 报告生成器 |
| **HotspotSignalTracker** | 热点信号追踪 |

### 3. Bandit 交易系统

基于多臂老虎机的自适应交易系统。

#### 3.1 核心组件

| 组件 | 说明 |
|------|------|
| **BanditAutoRunner** | 自动运行器 |
| **BanditPositionTracker** | 持仓追踪 |
| **BanditOptimizer** | 优化器 |
| **SignalListener** | 信号监听 |
| **AdaptiveCycle** | 自适应周期 |

#### 3.2 虚拟组合

| 组件 | 说明 |
|------|------|
| **VirtualPortfolio** | 虚拟持仓 |
| **PortfolioManager** | 组合管理器 |

### 4. Cognition 认知系统

#### 4.1 核心组件

| 组件 | 说明 |
|------|------|
| **InsightPool** | 洞察池 |
| **InsightEngine** | 洞察引擎 |
| **CognitionEngine** | 认知引擎 |
| **NarrativeTracker** | 叙事追踪 |
| **ManasEngine** | Manas 引擎 |

### 5. Radar 雷达系统

市场模式、异常和概念漂移检测。

| 组件 | 说明 |
|------|------|
| **GlobalMarketScanner** | 全球市场扫描器 |
| **NewsFetcher** | 新闻获取器 |
| **TradingClock** | 交易时钟 |
| **GlobalMarketFutures** | 全球期货数据 |

### 6. MarketHotspot 市场热点

市场热点监测与预测。

| 组件 | 说明 |
|------|------|
| **GlobalHotspotEngine** | 全局热点引擎 |
| **BlockHotspotEngine** | 板块热点引擎 |
| **MarketContext** | 市场上下文 |
| **StrategyAllocator** | 策略分配器 |
| **SignalTuner** | 信号调谐器 |

### 7. Strategy 策略系统

#### 7.1 核心组件

| 组件 | 说明 |
|------|------|
| **StrategyManager** | 策略管理器 |
| **StrategyRegistry** | 策略注册表 |

#### 7.2 数据源

| 组件 | 说明 |
|------|------|
| **DataSourceManager** | 数据源管理器 |
| **HotspotMixin** | 热点混入 |

### 8. Knowledge 知识系统

| 组件 | 说明 |
|------|------|
| **KnowledgeStore** | 知识存储 |
| **KnowledgeExporter** | 知识导出 |
| **CognitionInterface** | 认知接口 |

### 9. LLM Controller

LLM 控制器，管理与大语言模型的交互。

---

## 关键类与函数

### Application 关键类

```python
# 应用容器
class AppContainer:
    def boot(self) -> BootResult: ...
    def _register_singletons(self) -> None: ...
    def _assemble_core_components(self) -> None: ...

# 运行时配置
class AppRuntimeConfig: ...
```

### Attention 关键类

```python
# 注意力融合
class AttentionFusion: ...

# Manas 引擎
class ManasEngine:
    def subscribe(self, event_type: str, callback: Callable): ...
    def get_narrative_tracker(self) -> NarrativeTracker: ...

# 叙事追踪
class NarrativeTracker:
    def update_theme(self, theme: str): ...
    def get_keywords(self) -> List[str]: ...
```

### Bandit 关键类

```python
# Bandit 自动运行器
class BanditAutoRunner:
    def start(self): ...
    def stop(self): ...

# 自适应周期
class AdaptiveCycle:
    def _restore_running_state(self): ...
```

### MarketHotspot 关键类

```python
# 市场热点系统
class MarketHotspotIntegration:
    def initialize(self) -> MarketHotspotSystem: ...
    def start_monitoring(self): ...
    def get_hotspot_report(self) -> Dict: ...

# 信号调谐器
class SignalTuner:
    def get_stats(self) -> Dict: ...
```

---

## 依赖关系

### 核心依赖

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | >= 3.9 | 运行环境 |
| PyWebIO | - | Web UI 框架 |
| Tornado | - | 异步 web 框架 |
| aiohttp | - | 异步 HTTP 客户端 |
| pandas | - | 数据处理 |

### 模块依赖关系

```
Application
    ├── Attention (注意力系统)
    │       ├── Cognition (认知系统)
    │       ├── Bandit (交易系统)
    │       └── Radar (雷达系统)
    ├── MarketHotspot (市场热点)
    │       ├── Radar (雷达系统)
    │       └── Strategy (策略系统)
    └── Knowledge (知识系统)
```

---

## 项目运行方式

### 环境要求

- Python 3.9+
- 依赖包：见 requirements.txt

### 启动 Naja 平台

```bash
# 方式一：直接启动
python -m deva.naja

# 方式二：通过模块启动
python -m deva.naja --config config.yaml

# 方式三：开发模式启动
python deva/naja/__main__.py
```

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--config <path>` | 指定配置文件路径 |
| `--debug` | 启用调试模式 |
| `--port <port>` | 指定 Web 服务端口 |

### 主要页面

| 页面 | 说明 |
|------|------|
| `/` | 首页/仪表盘 |
| `/hotspot` | 市场热点监测 |
| `/attention` | 注意力系统 |
| `/strategy` | 策略管理 |
| `/knowledge` | 知识管理 |

---

## 附录

### 项目结构

```
deva/
├── core/               # Deva 核心引擎
│   ├── bus.py          # 消息总线
│   ├── pipe.py         # 管道
│   ├── sources.py      # 数据源
│   ├── store.py        # 存储
│   ├── stream.py       # 流处理
│   └── when.py         # 调度器
├── llm/                # LLM 相关
├── naja/               # Naja 量化平台
│   ├── application/    # 应用层
│   ├── attention/      # 注意力系统
│   ├── bandit/         # Bandit 交易
│   ├── business/       # 业务逻辑
│   ├── cognition/      # 认知系统
│   ├── datasource/     # 数据源
│   ├── decision/       # 决策系统
│   ├── knowledge/      # 知识系统
│   ├── market_hotspot/ # 市场热点
│   ├── radar/          # 雷达系统
│   ├── strategy/       # 策略系统
│   ├── supervisor/     # 监管模块
│   └── state/          # 状态管理
└── skills/             # 用户技能
```

### 相关文档

- [项目 README](../README.md)
- [Naja 架构文档](./docs/architecture.md)
- [API 文档](./docs/api.md)

---

*本文档由 AI 自动生成，最后更新于 2026-04-21*
