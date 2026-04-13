# 🏗️ 双总线 + 桥梁架构设计

## 📋 架构设计原则

### 1. 职责分离
- **认知总线 (CognitiveEventBus)** - 处理认知层内部信号：叙事更新、时机分析、风险检测等
- **交易总线 (TradingEventBus)** - 处理交易层信号：策略信号、交易决策、订单执行等

### 2. 保持现状
- 认知总线不变，继续使用 `publish_cognitive_event()` 接口
- 交易总线升级为 `StreamBackedEventBus`，支持持久化

### 3. 桥梁通信
- 重要认知事件可以转换为交易信号
- 交易决策可以反馈给认知层

## 🚀 实现方案

### 文件结构
```
events/
├── __init__.py              # 统一导出接口，提供总线选择器
├── cognitive_bus.py         # 认知总线（保持原样）
├── trading_bus.py           # 交易总线（StreamBackedEventBus）
├── bus_bridge.py            # 总线桥梁
├── event_selector.py        # 事件类型选择器
└── (现有事件定义文件不变)
```

### 接口设计

#### 1. 获取不同总线
```python
from deva.naja.events import get_cognitive_bus, get_trading_bus, get_bus_bridge

# 获取认知总线
cognitive_bus = get_cognitive_bus()
cognitive_bus.publish_cognitive_event(
    source="NarrativeTracker",
    event_type=CognitiveEventType.NARRATIVE_UPDATE,
    importance=0.8
)

# 获取交易总线
trading_bus = get_trading_bus()
trading_bus.publish(StrategySignalEvent(...))

# 获取桥梁（可选）
bridge = get_bus_bridge()
```

#### 2. 自动桥接（可选）
- 认知总线的高重要性事件（importance >= 0.7）自动转发到交易总线
- 交易总线的某些决策事件自动反馈到认知总线

#### 3. 统一选择器（简化使用）
```python
from deva.naja.events import publish_event, subscribe_event

# 智能选择总线
publish_event(event)  # 根据事件类型选择总线
subscribe_event(event_type, callback)  # 跨总线订阅
```

## 🔄 通信场景

### 认知 → 交易（重要叙事触发交易）
```
叙事更新（importance=0.9） → 认知总线 → 桥梁 → 交易总线 → 策略信号
```

### 交易 → 认知（交易结果反馈）
```
交易决策（rejected） → 交易总线 → 桥梁 → 认知总线 → 风险调整
```

### 独立使用（大部分情况）
```
热点计算 → 只发到交易总线（不需要认知）
供应链分析 → 只发到认知总线（不需要交易）
```

## 🎯 迁移策略

### 阶段1：现状分析
- 检查哪些模块只使用认知总线
- 检查哪些模块只使用交易信号
- 识别混合使用场景

### 阶段2：实现基础设施
- 创建 `trading_bus.py` (StreamBackedEventBus)
- 创建 `bus_bridge.py`
- 更新 `__init__.py` 选择器

### 阶段3：逐步迁移
1. 热点策略 → 交易总线
2. Bandit 监听器 → 交易总线  
3. TradingCenter → 交易总线
4. 叙事追踪 → 保持认知总线
5. 流动性认知 → 保持认知总线

### 阶段4：桥梁测试
- 测试重要认知事件是否能触发交易信号
- 测试交易决策是否能调整认知

## 📊 优势对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| 全统一 | 概念简单，一个接口 | 丢失认知特殊功能，迁移风险大 |
| 双总线+桥梁 | 保留所有功能，渐进迁移 | 概念稍复杂，需要桥接逻辑 |
| 完全独立 | 职责最清晰 | 沟通困难，需要手动转发 |

**推荐：双总线+桥梁** - 平衡了功能保留和架构清晰度。