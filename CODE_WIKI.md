# Deva 项目 Code Wiki

## 目录

1. [项目概述](#项目概述)
2. [系统架构](#系统架构)
3. [核心模块详解](#核心模块详解)
4. [关键类与函数](#关键类与函数)
5. [依赖关系](#依赖关系)
6. [项目运行方式](#项目运行方式)
7. [开发指南](#开发指南)
8. [附录](#附录)

---

## 项目概述

### 项目简介

**Deva** 是一个智能量化与数据处理平台，以 Naja 子系统为核心，提供完整的数据流处理、事件驱动架构、AI 认知系统和量化交易功能。Naja 是一个具有人类般感知、思考和决策能力的智能交易助手。

### 核心特性

- **流式处理**：基于 Stream 类的异步数据流处理框架
- **事件驱动**：基于 Tornado 的事件循环和异步处理
- **认知系统**：提供市场叙事追踪、跨信号分析、洞察生成
- **注意力调度**：智能资源分配和策略优先级管理
- **雷达检测**：市场模式、异常和概念漂移检测
- **量化策略**：支持 River 策略、多数据源、信号处理
- **自适应交易**：基于多臂老虎机的 Bandit 交易系统
- **Web UI**：统一的 PyWebIO 管理界面
- **可恢复性**：RecoverableUnit 抽象的统一管理

### 版本信息

- 项目版本：2.0.0
- Naja 系统版本：2.0.0

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
│  ┌──────────────────────────────────────────────────────────┐   │
│  │     Application 应用层 (容器、配置、事件注册)            │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐             │   │
│  │  │ 认知系统  │  │ 注意力系统│  │ 雷达检测  │             │   │
│  │  │Cognition │  │ Attention│  │ Radar    │             │   │
│  │  └──────────┘  └──────────┘  └──────────┘             │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐             │   │
│  │  │ Bandit   │  │ 市场热点 │  │ 策略系统 │             │   │
│  │  │ Trading  │  │Hotspot   │  │ Strategy │             │   │
│  │  └──────────┘  └──────────┘  └──────────┘             │   │
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

### Naja 三层架构设计

Naja 采用清晰的三层架构设计：

```
入口 / UI / Bootstrap
    ↓
Application（装配、模式、订阅、生命周期）
    ↓
Decision / Attention / Cognition / Signal / Bandit（领域编排与核心能力）
    ↓
Infra / Adapters / Repository / Runtime（通用骨架与技术实现）
```

### Naja 核心模块

| 模块 | 说明 | 路径 |
|------|------|------|
| **application** | 应用容器、运行时配置、事件注册 | [naja/application/](file:///Users/spark/pycharmproject/deva/deva/naja/application) |
| **attention** | 注意力调度系统 | [naja/attention/](file:///Users/spark/pycharmproject/deva/deva/naja/attention) |
| **bandit** | 多臂老虎机交易系统 | [naja/bandit/](file:///Users/spark/pycharmproject/deva/deva/naja/bandit) |
| **cognition** | 认知引擎、洞察生成 | [naja/cognition/](file:///Users/spark/pycharmproject/deva/deva/naja/cognition) |
| **datasource** | 数据源管理 | [naja/datasource/](file:///Users/spark/pycharmproject/deva/deva/naja/datasource) |
| **decision** | 决策系统 | [naja/decision/](file:///Users/spark/pycharmproject/deva/deva/naja/decision) |
| **knowledge** | 知识管理系统 | [naja/knowledge/](file:///Users/spark/pycharmproject/deva/deva/naja/knowledge) |
| **llm_controller** | LLM 控制器 | [naja/llm_controller/](file:///Users/spark/pycharmproject/deva/deva/naja/llm_controller) |
| **market_hotspot** | 市场热点监测 | [naja/market_hotspot/](file:///Users/spark/pycharmproject/deva/deva/naja/market_hotspot) |
| **radar** | 雷达检测系统 | [naja/radar/](file:///Users/spark/pycharmproject/deva/deva/naja/radar) |
| **strategy** | 策略系统 | [naja/strategy/](file:///Users/spark/pycharmproject/deva/deva/naja/strategy) |
| **infra** | 基础设施层 | [naja/infra/](file:///Users/spark/pycharmproject/deva/deva/naja/infra) |
| **state** | 状态管理 | [naja/state/](file:///Users/spark/pycharmproject/deva/deva/naja/state) |

---

## 核心模块详解

### 1. Application 应用层

应用层是 Naja 的组合根，负责核心组件的装配和依赖注入。

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
- 后台初始化线程

**关键方法：**
- `boot()` - 启动应用容器
- `_register_singletons()` - 注册所有单例
- `_assemble_core_components()` - 装配核心组件
- `_start_background_initialization()` - 后台异步初始化

**文件位置：** [application/container.py](file:///Users/spark/pycharmproject/deva/deva/naja/application/container.py)

#### 1.2 AppRuntimeConfig

运行时配置管理，统一管理所有运行时配置项。

```python
from deva.naja.application.runtime_config import AppRuntimeConfig

config = AppRuntimeConfig.from_legacy(
    host="0.0.0.0",
    port=8080,
    lab_config=lab_config,
    news_radar_config=news_radar_config,
)
```

**包含配置：**
- `WebServerConfig` - Web 服务器配置（host, port）
- `LabModeConfig` - 实验室模式配置
- `NewsRadarModeConfig` - 新闻雷达模式配置
- `CognitionDebugConfig` - 认知调试配置
- `TuneModeConfig` - 调参模式配置

**文件位置：** [application/runtime_config.py](file:///Users/spark/pycharmproject/deva/deva/naja/application/runtime_config.py)

#### 1.3 EventSubscriberRegistrar

事件订阅注册器，集中管理所有事件订阅。

**主要职责：**
- 统一注册事件订阅关系
- 保持领域对象纯净
- 管理订阅生命周期

**文件位置：** [application/event_registrar.py](file:///Users/spark/pycharmproject/deva/deva/naja/application/event_registrar.py)

### 2. Attention 注意力系统

注意力调度系统是 Naja 的核心，负责智能分配计算资源。

#### 2.1 AttentionOS 分层架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Attention OS (注意力操作系统)                          │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    OS 应用层 (Applications)                            │   │
│  │                                                                      │   │
│  │  • StrategyDecisionMaker - 市场调度（题材/个股权重 + 频率控制）               │   │
│  │  • StrategyAllocator - 策略分配                                      │   │
│  │  • FrequencyController - 频率控制器                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Attention Kernel (注意力内核)                       │   │
│  │                                                                      │   │
│  │  • QKV 注意力计算 - 智能分配注意力权重                                │   │
│  │  • ManasEngine - 三维融合决策中枢（天时+地势+人和）                    │   │
│  │  • Encoder - 事件编码器                                              │   │
│  │  • MultiHeadAttention - 多头注意力                                    │   │
│  │  • ValueSystem - 价值观驱动                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 2.2 AttentionOS 核心类

注意力操作系统，统一入口，管理内核和应用层。

```python
from deva.naja.attention.os.attention_os import AttentionOS

attention_os = AttentionOS()
attention_os.initialize()

# 注意力计算
result = attention_os.compute_attention(events, market_state)

# 决策
decision = attention_os.make_decision(market_state, portfolio)
```

**核心能力：**
- `compute_attention()` - QKV 注意力计算
- `make_decision()` - ManasEngine 决策
- `get_harmony()` - 获取和谐状态

**文件位置：** [attention/os/attention_os.py](file:///Users/spark/pycharmproject/deva/deva/naja/attention/os/attention_os.py)

#### 2.3 价值观系统

| 组件 | 说明 |
|------|------|
| **ValueProfile** | 价值观配置 |
| **ValueSystem** | 价值观系统 |
| **ValueMapping** | 价值观映射 |

#### 2.4 编排层

| 组件 | 说明 |
|------|------|
| **CognitionOrchestrator** | 认知编排器 |
| **LiquidityManager** | 流动性管理器 |
| **TradingCenter** | 交易中枢 |
| **SignalExecutor** | 信号执行器 |

#### 2.5 追踪系统

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

#### 4.1 CognitionEngine

认知引擎，平台级认知输入输出入口。

```python
from deva.naja.cognition.engine import CognitionEngine

engine = CognitionEngine()

# 摄入策略结果
engine.ingest_result(result)

# 获取认知摘要
summary = engine.summarize_for_llm()

# 获取完整记忆报告
report = engine.get_memory_report()
```

**核心功能：**
- `ingest_result()` - 摄入策略结果
- `summarize_for_llm()` - 返回紧凑的认知摘要
- `get_memory_report()` - 获取完整记忆报告
- `save_state()` / `load_state()` - 状态持久化

**文件位置：** [cognition/engine.py](file:///Users/spark/pycharmproject/deva/deva/naja/cognition/engine.py)

#### 4.2 核心组件

| 组件 | 说明 |
|------|------|
| **InsightPool** | 洞察池 |
| **InsightEngine** | 洞察引擎 |
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

### 8. Infra 基础设施层

| 模块 | 说明 |
|------|------|
| **management** | 通用管理器骨架（BaseManager） |
| **runtime** | 运行时服务（RecoverableUnit、线程池、市场时间） |
| **log** | 日志系统（彩色日志） |
| **observability** | 可观测性（性能监控、健康检查） |
| **registry** | 注册管理 |

---

## 关键类与函数

### Application 关键类

```python
# 应用容器
class AppContainer:
    def boot(self) -> None: ...
    def _register_singletons(self) -> None: ...
    def _assemble_core_components(self) -> None: ...
    def restore_runtime_state(self) -> None: ...

# 运行时配置
class AppRuntimeConfig:
    @classmethod
    def from_legacy(cls, *, host, port, lab_config, ...) -> "AppRuntimeConfig": ...
```

### Attention 关键类

```python
# 注意力操作系统
class AttentionOS:
    def compute_attention(self, events, market_state): ...
    def make_decision(self, market_state, portfolio): ...
    def initialize_strategies(self): ...
    def get_strategy_signals(self, strategy_id=None, n=20): ...

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

### Cognition 关键类

```python
# 认知引擎
class CognitionEngine:
    def ingest_result(self, result: Any) -> Optional[list]: ...
    def summarize_for_llm(self, max_topics=5, max_events=5) -> Dict[str, Any]: ...
    def get_memory_report(self) -> Dict[str, Any]: ...
    def save_state(self) -> dict: ...
    def load_state(self) -> dict: ...
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

### Register 单例访问

```python
from deva.naja.register import SR, register_all_singletons

# 注册所有单例
register_all_singletons()

# 获取单例
attention_os = SR('attention_os')
trading_clock = SR('trading_clock')
```

---

## 依赖关系

### 核心依赖

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | >= 3.10 | 运行环境 |
| PyWebIO | >= 1.8.0 | Web UI 框架 |
| Tornado | >= 6.0 | 异步 web 框架 |
| aiohttp | >= 3.8.0 | 异步 HTTP 客户端 |
| pandas | >= 2.0.0 | 数据处理 |
| sqlitedict | >= 2.1.0 | SQLite 字典存储 |
| numpy | >= 1.24.0 | 数值计算 |

### 其他依赖（requirements.txt）

- dill >= 0.3
- toolz >= 0.10
- openai >= 1.0.0
- whoosh >= 2.7
- jieba >= 0.39
- sqlalchemy >= 2.0
- walrus >= 0.3
- apscheduler >= 3.9
- requests >= 2.28
- requests-html >= 0.10
- akshare >= 1.0
- pymaybe
- pampy >= 0.3
- expiringdict >= 1.2
- newspaper3k >= 0.2
- sockjs-tornado >= 1.0
- Werkzeug >= 2.0

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

- Python 3.10+
- 依赖包：见 [requirements.txt](file:///Users/spark/pycharmproject/deva/requirements.txt)

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
| `--port <port>` | 指定 Web 服务端口（默认 8080） |
| `--host <host>` | 指定绑定地址（默认 0.0.0.0） |
| `--lab` | 启用实验室模式 |
| `--lab-table <table>` | 实验室模式回放数据表 |
| `--lab-interval <seconds>` | 实验室模式回放间隔 |
| `--lab-speed <multiplier>` | 实验室模式回放速度倍数 |
| `--news-radar` | 启用新闻雷达（默认启用） |
| `--news-radar-sim` | 新闻雷达模拟模式 |
| `--news-radar-speed <multiplier>` | 新闻雷达加速倍数 |
| `--cognition-debug` | 启用认知系统调试日志 |
| `--tune` | 启用调参模式 |
| `--tune-method <grid|random>` | 调参搜索方法 |
| `--tune-samples <n>` | 随机搜索模式最大采样数 |
| `--no-color` | 禁用彩色日志输出 |

### 服务管理命令

```bash
# 后台启动服务
python -m deva.naja -s start

# 停止服务
python -m deva.naja -s stop

# 热重启服务
python -m deva.naja -s reload

# 重启服务
python -m deva.naja -s restart

# 查看服务状态
python -m deva.naja -s status

# 查看日志
python -m deva.naja -s log

# 查看调试日志
python -m deva.naja -s debug
```

### 主要页面

| 页面 | 说明 |
|------|------|
| `/` | 首页/仪表盘 |
| `/hotspot` | 市场热点监测 |
| `/attention` | 注意力系统 |
| `/strategy` | 策略管理 |
| `/knowledge` | 知识管理 |
| `/cognition` | 认知系统 |
| `/radar` | 雷达检测 |
| `/bandit` | Bandit 交易 |

---

## 开发指南

### 架构开发规则

新增功能时，请遵循以下规则：

1. **先判断归属层** - 确定新功能属于哪一层（Application/Domain/Infra）
2. **显式依赖注入** - 核心模块不使用 SR()，依赖通过构造函数传入
3. **事件订阅集中管理** - 新订阅逻辑使用 EventSubscriberRegistrar
4. **UI 不深入核心** - UI 使用 facade 或 query service
5. **新增组件实现持久化** - 所有核心组件实现 save_state()/load_state()

### SR() 使用策略

SR() 仅在边界层使用：

| 位置 | 是否允许 | 说明 |
|------|----------|------|
| `application/` | ✅ 允许 | 应用层（组合根） |
| `web_ui/` | ✅ 允许 | Web UI 层 |
| `__main__.py` | ✅ 允许 | 程序入口 |
| `infra/lifecycle/` | ✅ 允许 | 启动引导 |
| `register.py` | ✅ 允许 | 注册表本身 |
| `decision/` | ❌ 禁止 | 决策模块 |
| `attention/kernel/` | ❌ 禁止 | 注意力内核 |
| `attention/os/` | ❌ 禁止 | Attention OS |
| `events/` | ❌ 禁止 | 事件核心逻辑 |

### 新增唤醒同步任务

在 `state/system/wake_sync_handlers.py` 中新增类：

```python
class MyFeatureWakeSync:
    """我的功能同步器"""

    @property
    def name(self) -> str:
        return "My_Feature"  # 唯一标识

    @property
    def description(self) -> str:
        return "我的功能描述"

    @property
    def priority(self) -> int:
        return 2  # 优先级

    def should_wake_sync(self, last_active: datetime) -> bool:
        """判断是否需要同步"""
        return True

    def get_wake_sync_range(self, last_active: datetime, max_hours: int = 24):
        """获取需要同步的时间范围"""
        now = datetime.now()
        start = now - timedelta(hours=max_hours)
        return start, now

    def execute_wake_sync(self, start: datetime, end: datetime):
        """执行同步"""
        # 实现同步逻辑
        pass
```

然后在 `register.py` 的 `_create_wake_sync_manager()` 中注册。

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
│   ├── __init__.py     # 模块初始化
│   ├── __main__.py     # 命令行入口
│   ├── application/    # 应用层
│   ├── attention/      # 注意力系统
│   ├── bandit/         # Bandit 交易
│   ├── cognition/      # 认知系统
│   ├── config/         # 配置
│   ├── datasource/     # 数据源
│   ├── decision/       # 决策系统
│   ├── dictionary/     # 数据字典
│   ├── docs/           # 文档
│   ├── events/         # 事件系统
│   ├── home/           # 首页
│   ├── infra/          # 基础设施
│   ├── knowledge/      # 知识系统
│   ├── llm_controller/ # LLM 控制器
│   ├── market_hotspot/ # 市场热点
│   ├── radar/          # 雷达系统
│   ├── register.py     # 单例注册表
│   ├── risk/           # 风险管理
│   ├── scheduler/      # 调度器
│   ├── scripts/        # 脚本
│   ├── signal/         # 信号系统
│   ├── skills/         # 技能
│   ├── state/          # 状态管理
│   ├── static/         # 静态资源
│   ├── strategy/       # 策略系统
│   ├── supervisor/     # 监管模块
│   ├── tables/         # 数据表
│   ├── tasks/          # 任务管理
│   └── web_ui/         # Web UI
└── skills/             # 用户技能
```

### 相关文档

- [项目 README](file:///Users/spark/pycharmproject/deva/README.md)
- [Naja 架构基线](file:///Users/spark/pycharmproject/deva/docs/naja/naja_architecture_baseline.md)
- [SR() 使用策略](file:///Users/spark/pycharmproject/deva/docs/naja/sr_usage_policy.md)
- [CHANGELOG](file:///Users/spark/pycharmproject/deva/CHANGELOG.md)

---

*本文档最后更新于 2026-05-25*
