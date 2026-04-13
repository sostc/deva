# Deva 项目 Code Wiki

## 目录

1. [项目概述](#项目概述)
2. [系统架构](#系统架构)
3. [核心模块详解](#核心模块详解)
4. [关键类与函数](#关键类与函数)
5. [依赖关系](#依赖关系)
6. [项目运行方式](#项目运行方式)

---

## 项目概述

### 项目简介

**Deva** 是一个智能量化与数据处理平台，提供完整的数据流处理、事件驱动架构、AI 认知系统和量化交易功能。该平台包含以下核心组件：

| 组件 | 说明 | 路径 |
|------|------|------|
| **Deva Core** | 核心引擎（消息总线、管道、数据源、调度） | [deva/core/](file:///workspace/deva/core/) |
| **Admin UI** | Web 管理后台（PyWebIO） | [deva/admin/](file:///workspace/deva/admin/) |
| **Naja** | 量化交易平台 | [deva/naja/](file:///workspace/deva/naja/) |
| **Skills** | 用户技能（OpenClaw） | [skills/](file:///workspace/skills/) |
| **CLI** | 命令行工具 | [cli/](file:///workspace/cli/) |

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
│  (PyWebIO - 统一管理界面 / 数据源 / 策略 / 认知 / 注意力)        │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                      Naja 量化交易平台                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ 认知系统  │  │ 注意力系统│  │ 雷达检测  │  │ Bandit   │    │
│  │ Cognition│  │ Attention │  │ Radar     │  │ Trading  │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              策略系统 / 数据源 / 信号流                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                      Deva Core 核心引擎                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Stream   │  │ Bus      │  │ Pipe     │  │ Store    │    │
│  │ 流处理   │  │ 消息总线  │  │ 管道     │  │ 存储     │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Sources  │  │ When     │  │ HTTP     │  │ Namespace│    │
│  │ 数据源   │  │ 调度器   │  │ 客户端   │  │ 命名空间  │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Naja 数据流架构

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

## 核心模块详解

### 1. Deva Core 核心引擎

#### 1.1 Stream 流处理系统

**位置**：[deva/core/core.py](file:///workspace/deva/core/core.py#L391)

Stream 类是整个框架的核心，提供无限数据序列的处理能力。

**主要特性**：
- 流之间可以相互订阅、传递和转换数据
- 支持同步和异步操作
- 提供丰富的操作符：map、filter、reduce、sink 等
- 支持缓存和最近数据回放
- 支持路由函数、异常捕获
- 支持发布/订阅模式

**核心方法**：

| 方法 | 说明 |
|------|------|
| `emit(x)` | 将数据推入流 |
| `map(func)` | 对流中的每个元素应用函数 |
| `filter(predicate)` | 只允许满足谓词的元素通过 |
| `sink(func)` | 对流中的每个元素应用函数（终点） |
| `route(occasion)` | 路由函数，根据条件分发数据 |
| `catch(func)` | 捕获函数执行结果到流内 |
| `catch_except(func)` | 捕获函数执行异常到流内 |
| `recent(n, seconds)` | 获取最近的缓存数据 |
| `pub(topic, message)` | 发布消息到特定主题 |
| `sub(topic)` | 装饰器，订阅特定主题 |

**使用示例**：

```python
from deva import Stream

# 创建数据流
source = Stream()

# 转换和处理
result = (source.map(lambda x: x * 2)
                .filter(lambda x: x > 0)
                .rate_limit(0.5))

# 输出结果
result.sink(print)

# 输入数据
for i in range(5):
    source.emit(i)
```

#### 1.2 Bus 消息总线

**位置**：[deva/core/bus.py](file:///workspace/deva/core/bus.py)

提供事件驱动的消息总线功能，支持：
- 事件发布和订阅
- 远程过程调用 (RPC)
- 共享状态管理
- 分布式锁
- 任务队列

#### 1.3 Pipe 管道操作

**位置**：[deva/core/pipe.py](file:///workspace/deva/core/pipe.py)

提供链式调用风格的数据处理，使用 `>>` 操作符组合操作。

**使用示例**：

```python
from deva import P

data = [{'name': 'foo', 'value': 1}, 
        {'name': 'bar', 'value': 2}]

(data >> P.map(lambda x: x['value'])  # 提取value字段
      >> P.filter(lambda x: x > 1)    # 过滤
      >> P.reduce(lambda x,y: x + y)  # 求和
      >> print)                        # 打印结果
```

#### 1.4 HTTP 客户端

**位置**：[deva/core/core.py#L1561](file:///workspace/deva/core/core.py#L1561)

基于 requests-html 的异步 HTTP 客户端，支持：
- 异步并发请求
- JavaScript 渲染
- 网页抓取和解析

**核心函数**：`httpx(req, render=False, timeout=30, workers=10, **kwargs)`

### 2. Naja 量化交易平台

#### 2.1 认知系统 (Cognition)

**位置**：[deva/naja/cognition/](file:///workspace/deva/naja/cognition/)

认知系统是平台级认知输入输出入口，提供：
- **NarrativeTracker**：管理市场叙事生命周期
- **SemanticColdStart**：处理新概念的快速学习
- **CrossSignalAnalyzer**：合并新闻和注意力信号
- **InsightEngine**：管理认知产物

**入口**：
```python
from deva.naja.cognition import CognitionEngine, get_cognition_engine
engine = get_cognition_engine()
```

#### 2.2 注意力系统 (Attention)

**位置**：[deva/naja/attention/](file:///workspace/deva/naja/attention/)

注意力协调器统一管理注意力分配，提供：
- **AttentionEngine**：注意力核心引擎
- **DualEngine**：双引擎处理动量和噪声
- **StrategyManager**：托管多种注意力策略
- **BudgetSystem**：智能分配注意力预算
- **FeedbackLoop**：持续优化注意力分配

**入口**：
```python
from deva.naja.attention import AttentionOrchestrator
orchestrator = AttentionOrchestrator()
```

#### 2.3 雷达系统 (Radar)

**位置**：[deva/naja/radar/](file:///workspace/deva/naja/radar/)

雷达引擎用于检测市场模式、异常和概念漂移，提供：
- 全球市场扫描器
- 流动性预测体系
- 信号共振检测
- 主题扩散预测

**核心文件**：
- [radar/engine.py](file:///workspace/deva/naja/radar/engine.py) - 雷达引擎
- [radar/news_fetcher.py](file:///workspace/deva/naja/radar/news_fetcher.py) - 新闻获取器
- [radar/global_market_scanner.py](file:///workspace/deva/naja/radar/global_market_scanner.py) - 全球市场扫描器

**入口**：
```python
from deva.naja.radar import RadarEngine, get_radar_engine
radar = get_radar_engine()

from deva.naja.radar.global_market_scanner import get_global_market_scanner
scanner = get_global_market_scanner()
```

#### 2.4 策略系统 (Strategy)

**位置**：[deva/naja/strategy/](file:///workspace/deva/naja/strategy/)

策略系统提供完整的量化策略运行环境：
- **Strategy Runtime**：策略运行时
- **Strategy Registry**：策略注册表
- **River Wrapper**：River 策略包装器
- **River Tick Strategies**：Tick 级别策略
- **Multi Datasource**：多数据源策略
- **Signal Processor**：信号处理器
- **Result Store**：结果存储

**核心文件**：
- [strategy/runtime.py](file:///workspace/deva/naja/strategy/runtime.py) - 策略运行时
- [strategy/registry.py](file:///workspace/deva/naja/strategy/registry.py) - 策略注册表
- [strategy/result_store.py](file:///workspace/deva/naja/strategy/result_store.py) - 结果存储

#### 2.5 Bandit 自适应交易系统

**位置**：[deva/naja/bandit/](file:///workspace/deva/naja/bandit/)

基于多臂老虎机的自适应交易系统，提供：
- **Virtual Portfolio**：虚拟组合管理
- **Market Observer**：市场观察
- **Adaptive Cycle**：自适应周期
- **Signal Listener**：信号监听
- **Optimizer**：优化器
- **Portfolio Manager**：组合管理器

**核心文件**：
- [bandit/runner.py](file:///workspace/deva/naja/bandit/runner.py) - Bandit 运行器
- [bandit/optimizer.py](file:///workspace/deva/naja/bandit/optimizer.py) - 优化器
- [bandit/virtual_portfolio.py](file:///workspace/deva/naja/bandit/virtual_portfolio.py) - 虚拟组合

**入口**：
```python
from deva.naja.bandit import BanditRunner
runner = BanditRunner()
runner.start()
```

#### 2.6 Supervisor 监控器

**位置**：[deva/naja/supervisor/](file:///workspace/deva/naja/supervisor/)

Supervisor 模块负责 Naja 系统的启动、监控和恢复。

**核心文件**：
- [supervisor/core.py](file:///workspace/deva/naja/supervisor/core.py) - 监控器核心
- [supervisor/bootstrap.py](file:///workspace/deva/naja/supervisor/bootstrap.py) - 启动引导

**入口**：
```python
from deva.naja.supervisor.bootstrap import get_naja_supervisor, start_supervisor
supervisor = get_naja_supervisor()
start_supervisor()
```

### 3. Admin UI 管理后台

**位置**：[deva/admin/](file:///workspace/deva/admin/)

基于 PyWebIO 的 Web 管理后台，提供统一的管理界面。

**主要模块**：
- 数据源管理 (`/dsadmin`)
- 任务管理 (`/taskadmin`)
- 策略管理 (`/strategyadmin`)
- 信号流可视化 (`/signaladmin`)
- 认知系统 (`/cognition`)
- 注意力系统 (`/attentionadmin`)
- 雷达事件 (`/radaradmin`)
- Bandit 交易 (`/banditadmin`)
- LLM 调节 (`/llmadmin`)
- 字典管理 (`/dictadmin`)
- 数据表管理 (`/tableadmin`)

### 4. Skills 技能系统

**位置**：[skills/](file:///workspace/skills/)

OpenClaw 用户技能系统，提供可扩展的功能模块。

**可用技能**：

| 技能 | 说明 | 路径 |
|------|------|------|
| proactive-agent | 主动式 AI Agent 架构 | [skills/proactive-agent/](file:///workspace/skills/proactive-agent/) |
| self-improving-agent | 自改进 Agent | [skills/self-improving-agent/](file:///workspace/skills/self-improving-agent/) |
| github-trend-observer | GitHub 趋势追踪 | [skills/github-trend-observer/](file:///workspace/skills/github-trend-observer/) |
| agent-browser | 浏览器自动化 | [skills/agent-browser/](file:///workspace/skills/agent-browser/) |
| stock-info-explorer | 股票信息探索 | [skills/stock-info-explorer/](file:///workspace/skills/stock-info-explorer/) |
| tavily-search | Tavily 搜索 | [skills/tavily-search/](file:///workspace/skills/tavily-search/) |
| xiaohongshu-mcp | 小红书 MCP | [skills/xiaohongshu-mcp/](file:///workspace/skills/xiaohongshu-mcp/) |

---

## 关键类与函数

### Deva Core 核心类

#### Stream 类

**文件**：[deva/core/core.py#L391](file:///workspace/deva/core/core.py#L391)

流是一个无限的数据序列，提供数据处理和转换功能。

**核心方法**：

| 方法 | 签名 | 说明 |
|------|------|------|
| `__init__` | `(upstream=None, upstreams=None, name=None, ...)` | 初始化流对象 |
| `emit` | `(x, asynchronous=False)` | 将数据推入流 |
| `update` | `(x, who=None)` | 更新流中的数据 |
| `map` | `(func, *args, **kwargs)` | 对流中的每个元素应用函数 |
| `filter` | `(predicate, *args, **kwargs)` | 只允许满足谓词的元素通过 |
| `sink` | `(func, *args, **kwargs)` | 对流中的每个元素应用函数 |
| `connect` | `(downstream)` | 将此流连接到下游元素 |
| `disconnect` | `(downstream)` | 断开此流与下游元素的连接 |
| `destroy` | `(streams=None)` | 断开此流与任何上游源的连接 |
| `route` | `(occasion)` | 路由函数装饰器 |
| `catch` | `(func)` | 捕获函数执行结果到流内 |
| `catch_except` | `(func)` | 捕获函数执行异常到流内 |
| `recent` | `(n=5, seconds=None)` | 获取最近的缓存数据 |
| `pub` | `(topic, message)` | 发布消息到特定主题 |
| `sub` | `(topic)` | 订阅特定主题的装饰器 |

#### map 类

**文件**：[deva/core/core.py#L1327](file:///workspace/deva/core/core.py#L1327)

对流中的每个元素应用一个函数，支持同步和异步操作。

**核心方法**：
- `__init__(upstream, func=None, *args, **kwargs)` - 初始化映射流
- `update(x, who=None)` - 处理输入数据，应用映射函数

#### filter 类

**文件**：[deva/core/core.py#L1522](file:///workspace/deva/core/core.py#L1522)

只允许满足谓词的元素通过。

**核心方法**：
- `__init__(upstream, predicate, *args, **kwargs)` - 初始化过滤器
- `update(x, who=None)` - 过滤数据

#### sink 类

**文件**：[deva/core/core.py#L1180](file:///workspace/deva/core/core.py#L1180)

对流中的每个元素应用一个函数（终点）。

**核心方法**：
- `__init__(upstream, func, *args, **kwargs)` - 初始化 sink
- `update(x, who=None, metadata=None)` - 执行函数并处理结果

#### crawler 类

**文件**：[deva/core/core.py#L1656](file:///workspace/deva/core/core.py#L1656)

基于流的网页爬虫类，支持同步和异步 HTTP 请求。

### Deva Core 核心函数

#### httpx 函数

**文件**：[deva/core/core.py#L1561](file:///workspace/deva/core/core.py#L1561)

异步 HTTP 请求函数。

**签名**：
```python
@gen.coroutine
def httpx(req, render=False, timeout=30, workers=10, **kwargs)
```

**参数**：
- `req` - 请求参数，可以是 URL 字符串或请求参数字典
- `render` - 是否渲染 JavaScript，默认 False
- `timeout` - 请求超时时间（秒），默认 30
- `workers` - 并发工作线程数，默认 10

### Naja 关键类与函数

#### NajaSupervisor 类

**文件**：[deva/naja/supervisor/core.py](file:///workspace/deva/naja/supervisor/core.py)

Naja 系统监控器，负责系统的启动、监控和恢复。

#### get_naja_supervisor 函数

**文件**：[deva/naja/supervisor/bootstrap.py#L20](file:///workspace/deva/naja/supervisor/bootstrap.py#L20)

获取 Naja 监控器单例。

**签名**：
```python
def get_naja_supervisor() -> "NajaSupervisor"
```

#### start_supervisor 函数

**文件**：[deva/naja/supervisor/bootstrap.py#L73](file:///workspace/deva/naja/supervisor/bootstrap.py#L73)

启动 Naja 监控器。

**签名**：
```python
def start_supervisor(force_realtime: bool = False, lab_mode: bool = False) -> None
```

#### main 函数

**文件**：[deva/naja/__main__.py#L24](file:///workspace/deva/naja/__main__.py#L24)

Naja 命令行入口函数。

**签名**：
```python
def main()
```

---

## 依赖关系

### 核心依赖

**文件**：[requirements.txt](file:///workspace/requirements.txt)

| 依赖 | 版本 | 用途 |
|------|------|------|
| tornado | >=6.0 | 异步 Web 框架和事件循环 |
| pandas | >=1.0 | 数据分析和处理 |
| dill | >=0.3 | 对象序列化 |
| toolz | >=0.10 | 函数式编程工具 |
| openai | >=1.0.0 | OpenAI API |
| whoosh | >=2.7 | 全文搜索 |
| jieba | >=0.39 | 中文分词 |
| pywebio | >=1.8 | Web UI 框架 |
| pywebio-battery | >=0.2 | PyWebIO 扩展 |
| sqlalchemy | >=2.0 | SQL 数据库 ORM |
| walrus | >=0.3 | Redis 封装 |
| apscheduler | >=3.9 | 任务调度 |
| requests | >=2.28 | HTTP 请求 |
| requests-html | >=0.10 | HTML 解析和 JavaScript 渲染 |
| aiohttp | >=3.8 | 异步 HTTP |
| akshare | >=1.0 | 财经数据接口 |
| pymaybe | - | 可选值处理 |
| pampy | >=0.3 | 模式匹配 |
| expiringdict | >=1.2 | 过期字典 |
| newspaper3k | >=0.2 | 新闻提取 |
| sockjs-tornado | >=1.0 | WebSocket |
| Werkzeug | >=2.0 | WSGI 工具 |

### 模块依赖关系

```
Naja 量化平台
├── 依赖 Deva Core
│   ├── Stream 流处理
│   ├── Bus 消息总线
│   ├── Pipe 管道
│   └── Store 存储
├── 依赖 Admin UI
│   └── PyWebIO
└── 依赖第三方库
    ├── Tornado (事件循环)
    ├── Pandas (数据处理)
    ├── SQLAlchemy (数据库)
    └── OpenAI (LLM)
```

---

## 项目运行方式

### 环境要求

- Python 3.7+
- 依赖包：见 [requirements.txt](file:///workspace/requirements.txt)

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动 Naja 平台

#### 默认启动（启用新闻雷达）

```bash
python -m deva.naja
```

#### 指定端口

```bash
python -m deva.naja --port 8080
```

#### 实验室模式（回放历史数据测试）

```bash
python -m deva.naja --lab --lab-table quant_snapshot_5min_window
```

#### 新闻雷达模式

```bash
# 正常模式（真实数据源）
python -m deva.naja --news-radar

# 加速模式
python -m deva.naja --news-radar-speed 10

# 模拟模式
python -m deva.naja --news-radar-sim
```

#### 认知调试模式

```bash
python -m deva.naja --cognition-debug
```

#### 调参模式

```bash
# 网格搜索
python -m deva.naja --tune --lab-table quant_snapshot_5min_window

# 随机搜索
python -m deva.naja --tune --tune-method random --tune-samples 50
```

### 访问 Web UI

启动后访问：`http://localhost:8080/`

### 主要页面

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

### 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--port` | Web 服务器端口 | 8080 |
| `--host` | 绑定地址 | 0.0.0.0 |
| `--log-level` | 日志级别 | INFO |
| `--attention` | 启用注意力调度系统 | - |
| `--no-attention` | 禁用注意力调度系统 | - |
| `--lab` | 启用实验室模式 | False |
| `--lab-table` | 实验室模式回放数据表名 | None |
| `--lab-interval` | 实验室模式回放间隔（秒） | 1.0 |
| `--lab-speed` | 实验室模式回放速度倍数 | 1.0 |
| `--force-realtime` | 强制实盘调试模式 | False |
| `--debug-market` | 调试模式：强制指定市场状态 | None |
| `--news-radar` | 启用新闻雷达 | True |
| `--news-radar-speed` | 新闻雷达加速倍数 | 1.0 |
| `--news-radar-sim` | 启用新闻雷达模拟模式 | False |
| `--cognition-debug` | 启用认知系统调试日志 | False |
| `--tune` | 启用调参模式 | False |
| `--tune-method` | 调参搜索方法 (grid/random) | grid |
| `--tune-samples` | 随机搜索模式下的最大采样数 | 100 |
| `--tune-export` | 导出调参结果到指定文件路径 | None |

---

## 附录

### 相关文档

- [NAJA_OVERVIEW.md](file:///workspace/docs/NAJA_OVERVIEW.md) - Naja 架构详细说明
- [docs/README.md](file:///workspace/docs/README.md) - Deva 文档中心
- [CHANGELOG.md](file:///workspace/CHANGELOG.md) - 版本变更日志

### 项目结构

```
/workspace/
├── bin/                    # 可执行文件
├── cli/                    # 命令行工具
├── config/                 # 配置文件
├── deva/                   # 主项目目录
│   ├── admin/              # Admin UI 管理后台
│   ├── config/             # 配置模块
│   ├── core/               # Deva Core 核心引擎
│   ├── examples/           # 示例代码
│   ├── llm/                # LLM 模块
│   ├── naja/               # Naja 量化交易平台
│   ├── page_ui/            # 页面 UI
│   └── utils/              # 工具函数
├── docs/                   # 文档
├── examples/               # 示例
├── memory/                 # 记忆文件
├── scripts/                # 脚本
├── skills/                 # 技能系统
├── source/                 # 源码文档
├── requirements.txt        # 依赖文件
└── CODE_WIKI.md           # 本文档
```

---

**文档版本**：1.0  
**最后更新**：2026-04-13  
**维护者**：Deva 项目团队
