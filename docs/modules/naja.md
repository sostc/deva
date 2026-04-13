# Naja 量化交易平台文档

## 概述

Naja 是一个基于 Deva 框架构建的实时数据流与量化交易平台，集成了认知系统、注意力机制、雷达检测、策略引擎等高级功能，为量化交易提供完整的解决方案。

## 核心特性

- **认知系统**：市场叙事追踪、跨信号分析、洞察生成
- **注意力机制**：智能注意力分配、双引擎处理、策略管理
- **雷达系统**：全球市场扫描、异常检测、概念漂移检测
- **策略系统**：完整的策略运行时、River 策略包装器、多数据源支持
- **Bandit 自适应交易**：基于多臂老虎机的自适应交易系统
- **Web 管理界面**：基于 PyWebIO 的可视化管理后台

## 模块结构

```
deva/naja/
├── __main__.py           # 命令行入口
├── register.py           # 模块注册
├── attention/           # 注意力系统
│   ├── discovery/     # 发现模块
│   ├── kernel/      # 核心引擎
│   ├── models/      # 数据模型
│   ├── orchestration/ # 编排
│   ├── os/          # 操作系统层
│   ├── tracking/    # 跟踪
│   ├── ui/          # UI 界面
│   └── values/      # 配置
├── bandit/            # Bandit 自适应交易
├── cognition/         # 认知系统
│   ├── analysis/    # 分析模块
│   ├── insight/     # 洞察生成
│   ├── liquidity/   # 流动性预测
│   ├── merrill_clock/ # 美林时钟
│   ├── narrative/   # 叙事追踪
│   ├── semantic/    # 语义处理
│   └── ui/          # UI 界面
├── config/            # 配置管理
├── datasource/        # 数据源管理
├── dictionary/        # 数据字典
├── docs/            # 文档
├── events/          # 事件系统
├── evolution/         # 进化系统
├── home/            # 首页
├── infra/           # 基础设施
│   ├── lifecycle/   # 生命周期
│   ├── log/         # 日志
│   ├── observability/ # 可观测性
│   ├── registry/    # 注册中心
│   ├── runtime/     # 运行时
│   └── ui/          # UI 工具
├── knowledge/         # 知识库
├── llm_controller/    # LLM 控制器
├── market_hotspot/    # 市场热点
│   ├── core/        # 核心
│   ├── data/        # 数据
│   ├── engine/      # 引擎
│   ├── filters/     # 过滤器
│   ├── integration/ # 集成
│   ├── intelligence/ # 智能
│   ├── processing/  # 处理
│   ├── scheduling/  # 调度
│   ├── strategies/  # 策略
│   ├── tracking/    # 跟踪
│   ├── ui_components/ # UI 组件
│   └── utils/       # 工具
├── radar/            # 雷达系统
│   ├── senses/      # 感知
│   └── ui/          # UI
├── replay/           # 回放系统
├── risk/             # 风险管理
├── scheduler/        # 调度器
├── scripts/          # 脚本
├── signal/           # 信号处理
├── skills/           # 技能
├── state/            # 状态管理
├── static/           # 静态资源
├── strategy/         # 策略系统
│   ├── prompts/     # 提示词
│   ├── tools/       # 工具
│   └── ui/          # UI
├── supervisor/       # 监控器
├── tables/           # 数据表
├── tasks/            # 任务管理
├── tests/            # 测试
└── web_ui/           # Web UI
```

## 核心模块详解

### 1. 认知系统 (Cognition)

**位置**：[deva/naja/cognition/](file:///workspace/deva/naja/cognition/)

认知系统是平台级认知输入输出入口，提供：

#### 主要功能

- **NarrativeTracker**：管理市场叙事生命周期
- **SemanticColdStart**：处理新概念的快速学习
- **CrossSignalAnalyzer**：合并新闻和注意力信号
- **InsightEngine**：管理认知产物
- **LiquidityPredictor**：跨市场流动性预测
- **MerrillClock**：美林时钟经济周期分析

#### 入口

```python
from deva.naja.cognition import CognitionEngine, get_cognition_engine
engine = get_cognition_engine()
```

### 2. 注意力系统 (Attention)

**位置**：[deva/naja/attention/](file:///workspace/deva/naja/attention/)

注意力协调器统一管理注意力分配，提供：

#### 主要功能

- **AttentionEngine**：注意力核心引擎
- **DualEngine**：双引擎处理动量和噪声
- **StrategyManager**：托管多种注意力策略
- **BudgetSystem**：智能分配注意力预算
- **FeedbackLoop**：持续优化注意力分配

#### 入口

```python
from deva.naja.attention import AttentionOrchestrator
orchestrator = AttentionOrchestrator()
```

### 3. 雷达系统 (Radar)

**位置**：[deva/naja/radar/](file:///workspace/deva/naja/radar/)

雷达引擎用于检测市场模式、异常和概念漂移，提供：

#### 主要功能

- 全球市场扫描器
- 流动性预测体系
- 信号共振检测
- 主题扩散预测
- 实时味觉感知

#### 核心文件

- [radar/engine.py](file:///workspace/deva/naja/radar/engine.py) - 雷达引擎
- [radar/news_fetcher.py](file:///workspace/deva/naja/radar/news_fetcher.py) - 新闻获取器
- [radar/global_market_scanner.py](file:///workspace/deva/naja/radar/global_market_scanner.py) - 全球市场扫描器

#### 入口

```python
from deva.naja.radar import RadarEngine, get_radar_engine
radar = get_radar_engine()
```

### 4. 策略系统 (Strategy)

**位置**：[deva/naja/strategy/](file:///workspace/deva/naja/strategy/)

策略系统提供完整的量化策略运行环境：

#### 主要功能

- **Strategy Runtime**：策略运行时
- **Strategy Registry**：策略注册表
- **River Wrapper**：River 策略包装器
- **River Tick Strategies**：Tick 级别策略
- **Multi Datasource**：多数据源策略
- **Signal Processor**：信号处理器
- **Result Store**：结果存储

#### 核心文件

- [strategy/runtime.py](file:///workspace/deva/naja/strategy/runtime.py) - 策略运行时
- [strategy/registry.py](file:///workspace/deva/naja/strategy/registry.py) - 策略注册表
- [strategy/result_store.py](file:///workspace/deva/naja/strategy/result_store.py) - 结果存储

### 5. Bandit 自适应交易系统

**位置**：[deva/naja/bandit/](file:///workspace/deva/naja/bandit/)

基于多臂老虎机的自适应交易系统，提供：

#### 主要功能

- **Virtual Portfolio**：虚拟组合管理
- **Market Observer**：市场观察
- **Adaptive Cycle**：自适应周期
- **Signal Listener**：信号监听
- **Optimizer**：优化器
- **Portfolio Manager**：组合管理器

#### 核心文件

- [bandit/runner.py](file:///workspace/deva/naja/bandit/runner.py) - Bandit 运行器
- [bandit/optimizer.py](file:///workspace/deva/naja/bandit/optimizer.py) - 优化器
- [bandit/virtual_portfolio.py](file:///workspace/deva/naja/bandit/virtual_portfolio.py) - 虚拟组合

#### 入口

```python
from deva.naja.bandit import BanditRunner
runner = BanditRunner()
runner.start()
```

### 6. Supervisor 监控器

**位置**：[deva/naja/supervisor/](file:///workspace/deva/naja/supervisor/)

Supervisor 模块负责 Naja 系统的启动、监控和恢复。

#### 核心文件

- [supervisor/core.py](file:///workspace/deva/naja/supervisor/core.py) - 监控器核心
- [supervisor/bootstrap.py](file:///workspace/deva/naja/supervisor/bootstrap.py) - 启动引导

#### 入口

```python
from deva.naja.supervisor.bootstrap import get_naja_supervisor, start_supervisor
supervisor = get_naja_supervisor()
start_supervisor()
```

## 启动方式

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

## 命令行参数

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

## 相关文档

- [NAJA_OVERVIEW.md](file:///workspace/docs/NAJA_OVERVIEW.md) - Naja 架构详细说明
- [CODE_WIKI.md](file:///workspace/CODE_WIKI.md) - 项目总览文档
- [docs/README.md](file:///workspace/docs/README.md) - Deva 文档中心

---

**文档版本**：1.0
**最后更新**：2026-04-13
