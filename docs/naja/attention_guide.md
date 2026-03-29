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

## 宏观流动性集成

注意力系统与流动性预测体系集成，接收 GlobalMarketScanner 的宏观流动性信号：

- `_update_macro_liquidity_from_scanner()`：从扫描器获取宏观流动性信号
- `_apply_liquidity_to_sector_attention()`：根据流动性调整板块注意力
- `_apply_liquidity_to_strategy_budget()`：根据流动性调整策略预算
- `_apply_liquidity_to_frequency()`：根据流动性调整交易频率

详见：[cross_market_liquidity_prediction.md](cross_market_liquidity_prediction.md)

## 四维决策框架

四维决策框架是注意力内核的"核心内心"，所有注意力计算都必须服从于这四个维度。

> **条件触发**：系统启动时默认关闭，通过条件自动启用。运行时根据资金/市场状态自动开关。

### 四维概述

| 维度 | 名称 | 核心问题 |
|------|------|----------|
| 天时 | Time | 时间合不合适？ |
| 资金 | Capital | 资产情况允不允许？ |
| 能力 | Capability | 自己能力允不允许？ |
| 市场 | Market | 有没有这个机会？ |

### 架构

```
四维框架
  ├── 天时：交易时段是否开放、距收盘剩余时间、时间压力
  ├── 资金：现金比例、是否有子弹（闲钱）、行动就绪度
  ├── 能力：策略是否就绪、策略数量、能力乘数
  └── 市场：流动性信号、是否极端、机会评分
         ↓
  shape_query(Q) → 塑造 Query
  apply_gates(result) → 应用门控
```

### 门控逻辑

1. **时间门控**：非交易时段 → `alpha *= 0`
2. **资金门控**：现金比例 < 10% → `alpha *= 0`（保留子弹）
3. **能力门控**：策略未就绪 → `alpha *= 0.3`
4. **特殊机会**：流动性极端 + 有子弹 → 识别为"逆向布局机会"

### 智能触发器

四维框架支持智能触发模式，根据条件自动启用/禁用：

```python
from deva.naja.attention.kernel import (
    FourDimensionsTrigger,
    FourDimensionsManager,
    TriggerConfig,
)

# 触发条件配置
config = TriggerConfig(
    auto_enable_low_cash=True,       # 资金不足时启用
    auto_enable_extreme_market=True, # 市场极端时启用
    low_cash_threshold=0.2,          # 现金比例 < 20% 触发
    extreme_low_signal=0.3,         # 流动性信号 < 0.3 触发
    extreme_high_signal=0.8,         # 流动性信号 > 0.8 触发
)

# 创建触发器
trigger = FourDimensionsTrigger(config)

# 创建管理器
manager = FourDimensionsManager(kernel, config)

# 在主循环中调用
manager.update()  # 自动检查并更新四维状态

# 手动控制
manager.set_enabled(True)    # 强制启用
manager.set_auto_mode(True)  # 恢复自动模式
```

#### 触发条件

| 条件 | 默认 | 说明 |
|------|------|------|
| 资金不足 | ✅ 启用 | cash_ratio < 20% |
| 市场极端恐慌 | ✅ 启用 | signal < 0.3 |
| 市场极端贪婪 | ✅ 启用 | signal > 0.8 |
| 非交易时段 | ❌ 禁用 | 可配置 |

#### 使用场景建议

| 场景 | 建议 |
|------|------|
| 实盘交易 | ✅ 使用触发器，自动模式 |
| 回测/模拟 | ❌ 关闭四维，看信号能力 |
| 新手阶段 | ✅ 使用触发器，保守 |

详见：[four_dimensions_trigger.py](../../deva/naja/attention/kernel/four_dimensions_trigger.py)

### 文件结构

```
attention/kernel/
    four_dimensions.py              # 四维决策框架
    four_dimensions_trigger.py     # 四维智能触发器
    kernel.py                      # 修改：集成四维开关
```

### UI 集成

四维决策框架状态在 Attention Admin UI 中展示，位于页面顶部，包含：
- 启用/关闭状态
- 四维实时状态（天时/资金/能力/市场）
- 自动触发条件状态和使用说明

查看路径：`/attentionadmin` 页面顶部

### 测试

```bash
# 四维核心测试
python3 test_four_dimensions.py

# 四维触发器测试
python3 test_four_dimensions_trigger.py
```

### 初始化

**条件触发模式**：系统启动时四维默认关闭，由 FourDimensionsManager 根据条件自动启用/禁用。每次处理数据时会检查并更新状态。

| 条件 | 行为 |
|------|------|
| 资金 < 20% | 自动启用四维（保守模式） |
| 市场信号 < 0.3 或 > 0.8 | 自动启用四维（保守模式） |
| 条件不满足 | 自动关闭四维 |

如需手动控制：

```python
orchestrator = get_attention_orchestrator()
manager = orchestrator.get_four_dimensions_manager()
if manager:
    manager.set_enabled(True)         # 强制启用
    manager.set_enabled(False)        # 强制关闭
    manager.set_auto_mode(True)      # 恢复自动模式
```

详见源码：[four_dimensions.py](../../deva/naja/attention/kernel/four_dimensions.py)

## 相关文档

- [cognition_guide.md](cognition_guide.md) - 认知系统
- [radar_guide.md](radar_guide.md) - 雷达系统
- [strategy_guide.md](strategy_guide.md) - 策略系统
- [NAJA_OVERVIEW.md](../NAJA_OVERVIEW.md) - Naja 架构总览