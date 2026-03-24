# Naja 注意力调度系统指南

> 基于最新代码结构（2026-03-24）

## 概述

Naja 注意力调度系统（Attention）是一个智能资源调度系统，能够根据市场状态和策略表现动态分配注意力资源。系统支持多种注意力策略，包括异常狙击、动量追踪、板块狩猎、智能资金检测等。

## 核心架构

```
AttentionOrchestrator
├── AttentionEngine (核心引擎)
│   ├── SectorEngine (板块引擎)
│   └── WeightPool (权重池)
├── DualEngine (双引擎)
│   ├── MomentumTracker (动量追踪)
│   └── NoiseFilter (噪声过滤)
└── StrategyManager (策略管理器)
    ├── AnomalySniper (异常狙击)
    ├── MomentumTracker (动量追踪)
    ├── SectorHunter (板块狩猎)
    ├── SmartMoneyDetector (智能资金检测)
    └── GlobalSentinel (全局哨兵)
```

## 核心功能

| 功能 | 说明 |
|------|------|
| AttentionOrchestrator | 注意力协调器，统一管理注意力分配 |
| AttentionEngine | 注意力核心引擎 |
| DualEngine | 双引擎，处理动量和噪声 |
| StrategyManager | 策略管理器，托管多种注意力策略 |
| BudgetSystem | 预算系统，智能分配注意力预算 |
| FeedbackLoop | 反馈循环，持续优化注意力分配 |

## 核心文件

| 目录 | 功能 |
|------|------|
| `attention/core/` | 核心引擎（AttentionEngine、SectorEngine、WeightPool） |
| `attention/engine/` | 双引擎（DualEngine） |
| `attention/strategies/` | 注意力策略实现 |
| `attention/intelligence/` | 智能系统（BudgetSystem、FeedbackLoop、PredictiveEngine） |
| `attention/pipeline/` | 处理流水线 |
| `attention/processing/` | 数据处理（NoiseFilter、TickFilter） |
| `attention/scheduling/` | 调度系统 |
| `attention/ui_components/` | UI 组件 |

## 访问方式

访问 `/attentionadmin` 查看注意力调度面板。

## 注意力策略

### 1. AnomalySniper（异常狙击）
检测市场异常波动，快速响应价格突变。

### 2. MomentumTracker（动量追踪）
追踪市场动量，识别趋势方向。

### 3. SectorHunter（板块狩猎）
聚焦板块轮动机会，捕捉热点板块。

### 4. SmartMoneyDetector（智能资金检测）
监测大资金动向，跟随机构行为。

### 5. GlobalSentinel（全局哨兵）
全局市场监控，识别系统性风险和机会。

## 预算系统

注意力预算系统根据策略表现和市场状态动态分配资源：

```python
# 预算分配伪代码
total_budget = 1000
strategy_scores = {
    'anomaly_sniper': 0.8,
    'momentum_tracker': 0.6,
    'sector_hunter': 0.7,
}
# 根据得分分配注意力预算
```

## 相关文档

- [cognition_guide.md](cognition_guide.md) - 认知系统
- [radar_guide.md](radar_guide.md) - 雷达系统
- [strategy_guide.md](strategy_guide.md) - 策略系统
- [NAJA_OVERVIEW.md](../NAJA_OVERVIEW.md) - Naja 架构总览