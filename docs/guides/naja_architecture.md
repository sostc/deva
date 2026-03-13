# Naja 架构层次（六层认知系统）

## 概览

Naja 在现有四个核心模块之上新增两层能力，形成更清晰的六层结构：

1. DataSource（感知）
2. Strategy Engine（直觉）
3. Radar Engine（发现）
4. LLM Controller（理解）
5. Task System（行动）
6. Data Dictionary（补全）

## 分层结构

```
DataSource
   ↓
Strategy Engine (legacy/river/plugin)
   ↓
Radar Engine (pattern/drift/anomaly)
   ↓
LLM Controller (meta cognition)
   ↓
Task System
   ↓
Data Dictionary
```

## 模块职责

- Strategy Engine: 统一策略接口 + 运行时管理，兼容 legacy/river/plugin。
- Radar Engine: 统一事件检测与长期信号记录。
- LLM Controller: 基于雷达与策略指标做参数调节与策略调度。

## 声明式策略（Declarative）

策略结构化为配置，执行逻辑统一交给引擎处理：

```
{
  "strategy_name": "momentum",
  "pipeline": [
    {"type": "feature", "name": "price_change"},
    {"type": "feature", "name": "volume_spike"},
    {"type": "scale", "factor": 1.0}
  ],
  "model": {"type": "logistic_regression"},
  "params": {"learning_rate": 0.01},
  "logic": {"type": "threshold", "buy": 0.7, "sell": 0.3}
}
```

当策略类型设置为 `declarative`，系统将自动用统一引擎运行该配置。
