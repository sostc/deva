# Naja 启动模式指南

> 最后更新：2026-03-27

## 📋 概述

Naja 系统支持多种启动模式，用于不同的使用场景。本文档详细介绍所有启动模式及其组合方式。

---

## 🚀 快速开始

### 默认启动（正常交易模式）

```bash
python -m deva.naja
```

**默认行为**：
- ✅ 启用注意力系统
- ✅ 启用新闻雷达（真实数据源）
- ✅ 启动实时数据获取（RealtimeDataFetcher）
- ✅ 从 Sina Finance API 获取实时行情

---

## 🎛️ 启动模式详解

### 1. 正常交易模式 (Normal Trading Mode)

**命令**: 无特殊参数（默认）

```bash
python -m deva.naja
python -m deva.naja --port 8080
```

**特点**:
| 组件 | 状态 | 说明 |
|------|------|------|
| RealtimeDataFetcher | ✅ 启动 | 从 Sina 获取实时数据 |
| 新闻雷达 | ✅ 启用 | 真实数据源，正常频率 |
| AttentionModeManager | MODE_NORMAL | 正常交易模式 |

**数据流**:
```
Sina Finance API → RealtimeDataFetcher → AttentionSystem → 策略
                 ↓
           新闻雷达（独立数据流）
```

---

### 2. 实验室模式 (Lab Mode)

**命令**: `--lab`

```bash
# 基础实验室模式
python -m deva.naja --lab --lab-table quant_snapshot_5min_window

# 自定义回放参数
python -m deva.naja --lab \
    --lab-table quant_snapshot_5min_window \
    --lab-interval 0.5 \
    --lab-speed 2.0
```

**⚠️ 重要约束**: 交易时间禁止启动实验室模式！

**特点**:
| 组件 | 状态 | 说明 |
|------|------|------|
| ReplayScheduler | ✅ 启动 | 从 NB 数据库回放历史数据 |
| RealtimeDataFetcher | ❌ 停止 | 被实验室模式接管 |
| 新闻雷达 | 可选 | 可组合加速或模拟模式 |
| AttentionModeManager | MODE_LAB | 实验室模式 |

**数据流**:
```
NB Database → ReplayScheduler → AttentionSystem → 策略
```

**参数说明**:

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--lab` | false | 启用实验室模式 |
| `--lab-table` | - | 回放数据表名（如 `quant_snapshot_5min_window`） |
| `--lab-interval` | 1.0 | 回放间隔（秒） |
| `--lab-speed` | 1.0 | 回放速度倍数 |
| `--lab-debug` | false | 启用调试日志 |

---

### 3. 新闻雷达模式 (News Radar Mode)

新闻雷达是用于监控和分析新闻/舆情数据的子系统，始终与正常交易模式绑定。

#### 3.1 默认模式（真实数据源）

```bash
# 默认启用
python -m deva.naja

# 显式指定
python -m deva.naja --news-radar
```

#### 3.2 加速模式（真实数据源 + 加快频率）

```bash
# 10倍速
python -m deva.naja --news-radar-speed 10

# 50倍速
python -m deva.naja --news-radar-speed 50
```

**使用场景**: 非交易时间测试，快速验证新闻雷达策略效果

#### 3.3 模拟模式（模拟数据源）

```bash
# 模拟模式
python -m deva.naja --news-radar-sim

# 自定义模拟间隔
python -m deva.naja --news-radar-sim --news-radar-speed 2.0
```

**使用场景**: 开发调试，不依赖真实新闻数据源

---

### 4. 认知调试模式 (Cognition Debug Mode)

**命令**: `--cognition-debug`

```bash
python -m deva.naja --cognition-debug
```

**自动组合**:
- ✅ 实验室模式（表: `quant_snapshot_5min_window`）
- ✅ 新闻雷达模拟模式
- ✅ 调试日志

**使用场景**: 完整测试注意力系统 + 认知系统的协同工作

---

## 🔧 模式组合

### 常用组合

| 命令 | 模式组合 | 使用场景 |
|------|---------|---------|
| `python -m deva.naja` | 正常交易 | 日常实盘 |
| `python -m deva.naja --lab --lab-table xxx` | 实验室 + 新闻雷达 | 历史数据回放测试 |
| `python -m deva.naja --lab --lab-table xxx --news-radar-speed 10` | 实验室 + 新闻雷达加速 | 快速回放测试 |
| `python -m deva.naja --lab --lab-table xxx --news-radar-sim` | 实验室 + 新闻雷达模拟 | 离线开发调试 |
| `python -m deva.naja --cognition-debug` | 认知调试模式 | 完整功能调试 |

---

## 📊 模式互斥关系

```
┌─────────────────────────────────────────────────────────────┐
│                    AttentionModeManager                      │
│                    (注意力系统模式管理器)                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌───────────────────┐    互斥    ┌───────────────────┐    │
│   │   正常交易模式      │ ←──────→ │   实验室模式        │    │
│   │ MODE_NORMAL       │           │ MODE_LAB          │    │
│   │ • RealtimeFetcher │           │ • ReplayScheduler │    │
│   │ • 新闻雷达         │           │ • 新闻雷达(可选)    │    │
│   └───────────────────┘           └───────────────────┘    │
│                                                             │
│   ⚠️ 交易时间只能选择正常交易模式                              │
│   ⚠️ 非交易时间可选择实验室模式                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 调参模式

启用调参模式以过滤日志，只显示关键信息：

```bash
python -m deva.naja --tuning-mode --lab --lab-table xxx
```

---

## 📝 完整参数参考

```
python -m deva.naja [选项]

位置参数:
  无

选项:
  --help, -h                显示帮助信息
  --version, -v             显示版本

服务器选项:
  --port PORT               Web 服务器端口 (默认: 8080)
  --host HOST               绑定地址 (默认: 0.0.0.0)
  --log-level LEVEL         日志级别 (默认: INFO)

注意力系统选项:
  --attention               显式启用注意力系统
  --no-attention            禁用注意力系统
  --attention-report        显示注意力系统状态报告

实验室模式选项:
  --lab                     启用实验室模式
  --lab-table TABLE         回放数据表名
  --lab-interval INTERVAL   回放间隔(秒) (默认: 1.0)
  --lab-speed SPEED         回放速度倍数 (默认: 1.0)
  --lab-debug               启用实验室调试日志

新闻雷达选项:
  --news-radar              启用新闻雷达 (默认)
  --news-radar-speed SPEED  新闻雷达加速倍数 (默认: 1.0)
  --news-radar-sim          启用新闻雷达模拟模式

其他选项:
  --cognition-debug         启用认知系统调试模式
  --tuning-mode             启用调参模式
```

---

## 🔍 调试与故障排除

### 查看当前模式

启动时会显示当前配置：

```
📡 新闻雷达已启用（真实数据源模式）
🧠 注意力系统初始化完成
🚀 Web 服务器启动: http://0.0.0.0:8080
```

### 常见问题

**Q: 交易时间启动实验室模式失败**
```
⚠️ 当前处于交易时间，实验模式需要在非交易时间启动
```
**A**: 这是预期行为。实验室模式仅在非交易时间可用。

**Q: 新闻雷达未启动**
**A**: 检查是否指定了 `--no-attention` 参数。

---

## 📚 相关文档

- [注意力系统指南](attention_guide.md)
- [策略指南](strategy_guide.md)
- [数据源指南](datasource_guide.md)
- [认知系统指南](cognition_guide.md)
