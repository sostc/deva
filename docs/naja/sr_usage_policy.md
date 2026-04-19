# SR() 使用策略文档

## 1. 概述

本文档定义了 `deva.naja.register.SR()` 的使用规则和约束。

**核心原则：**
- `SR()` 仅在**边界层**使用
- **核心领域层**不允许主动调用 `SR()`
- 依赖关系应通过**构造注入**或**参数传递**显式化

---

## 2. 目录分类

### 2.1 ✅ 允许使用 SR() 的目录

这些是应用的边界层，可以使用 `SR()`：

| 目录 | 说明 |
|------|------|
| `/deva/naja/application/` | 应用层（组合根） |
| `/deva/naja/web_ui/` | Web UI 层 |
| `/deva/naja/__main__.py` | 程序入口 |
| `/deva/naja/infra/lifecycle/` | 启动引导 |
| `/deva/naja/register.py` | 注册表本身 |

### 2.2 🟡 过渡目录（暂时允许，目标移除）

这些目录中的 `SR()` 调用需要逐步改造：

| 目录 | 优先级 | 说明 |
|------|--------|------|
| `/deva/naja/bandit/` | 中 | Bandit 模块 |
| `/deva/naja/radar/` | 中 | 雷达模块 |
| `/deva/naja/knowledge/` | 低 | 知识模块 |
| `/deva/naja/cognition/` | 中 | 认知模块 |
| `/deva/naja/market_hotspot/` | 中 | 市场热点模块 |
| `/deva/naja/strategy/` | 中 | 策略模块 |
| `/deva/naja/datasource/` | 低 | 数据源模块 |
| `/deva/naja/dictionary/` | 低 | 字典模块 |
| `/deva/naja/state/` | 低 | 状态模块 |

### 2.3 🔴 禁止使用 SR() 的目录（核心领域层）

这些目录**不得新增** `SR()` 调用，现有调用需要改造：

| 目录 | 优先级 | 说明 |
|------|--------|------|
| `/deva/naja/decision/` | 高 | 决策模块 |
| `/deva/naja/attention/kernel/` | 高 | 注意力内核 |
| `/deva/naja/attention/os/` | 高 | Attention OS |
| `/deva/naja/attention/orchestration/` | 高 | 编排层 |
| `/deva/naja/events/` | 高 | 事件核心逻辑 |
| `/deva/naja/infra/management/` | 低 | 管理骨架（已完成） |

---

## 3. 改造原则

### 3.1 依赖注入优先级

1. **构造函数注入**（首选）
```python
class TradingCenter:
    def __init__(self, attention_os, insight_pool=None):
        self.attention_os = attention_os
        self.insight_pool = insight_pool
```

2. **Setter 注入**（适用于大对象）
```python
class SomeModule:
    def set_insight_pool(self, pool):
        self.insight_pool = pool
```

3. **方法参数注入**（适用于单次调用）
```python
def process(self, data, insight_pool=None):
    ...
```

### 3.2 兼容层包装

保留 `get_xxx()` 函数，但实现改为从容器获取：

```python
# 旧实现（直接 SR()）
def get_trading_center():
    return SR('trading_center')

# 新实现（从容器获取，或保持 SR() 作为后备）
def get_trading_center():
    try:
        from deva.naja.application import get_app_container
        return get_app_container().trading_center
    except Exception:
        return SR('trading_center')  # 兼容性后备
```

---

## 4. 已完成改造清单

### 4.1 Managers 统一骨架

| Manager | 状态 |
|---------|------|
| DataSourceManager | ✅ 已迁移到 base_manager |
| StrategyManager | ✅ 已迁移到 base_manager |

---

## 5. 待改造模块（按优先级）

### 5.1 高优先级

- [ ] TradingCenter
- [ ] AttentionOS
- [ ] DecisionOrchestrator（已部分完成）
- [ ] 事件订阅机制

### 5.2 中优先级

- [ ] Bandit 模块
- [ ] Radar 模块
- [ ] Market Hotspot 模块

---

## 6. 检查清单

添加新代码时，请确认：

- [ ] 是否在 🔴 禁止目录中新增了 `SR()`？
- [ ] 是否可以通过依赖注入替代？
- [ ] 是否需要更新本文档？

