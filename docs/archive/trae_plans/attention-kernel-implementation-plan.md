# Attention Kernel 改进分析

## 一、现状问题诊断

### 1.1 聚焦问题：系统不知道"该关注什么"

**现状：**
- Radar / DataSource 产生全量事件
- 各策略独立处理，互不关联
- 没有统一的"该关注什么"机制

**症状：**
- 信号过多但有效信号少
- 策略之间没有优先级区分
- 资源平均分配到所有事件

### 1.2 清晰问题：多头注意力缺失

**现状：**
- GlobalAttentionEngine 是单头计算
- 市场/新闻/资金流 没有分别关注
- 输出是单一数值，无法解释

**症状：**
- 无法知道"是市场涨导致还是新闻导致"
- 注意力分数无法归因
- 调试时黑盒

### 1.3 结果问题：缺乏反馈闭环

**现状：**
- Bandit 优化策略选择
- 但策略内部的注意力分配没有优化
- 注意力不随结果学习

**症状：**
- 同样的错误重复发生
- 好的信号没有被强化
- 系统无法"记住教训"

### 1.4 错误问题：缺乏事件级记忆

**现状：**
- WeightPool 有历史缓冲
- 但事件级别没有持久记忆
- 重要事件被时间稀释

**症状：**
- 突发新闻被后续行情淹没
- 短期异常被长期平均稀释
- 无法追踪"刚才发生了什么"

---

## 二、改进方案及对应效果

### 2.1 QueryState（聚焦改进）

**机制：**
```python
class QueryState:
    def __init__(self):
        self.strategy_state = {}      # 当前策略关注什么
        self.portfolio_state = {}     # 当前持仓关注什么
        self.market_regime = {}       # 市场状态（趋势/震荡）
        self.attention_focus = {}     # 当前的注意力焦点
        self.risk_bias = 0.5         # 风险偏好
```

**改进效果：**

| 问题 | 改进前 | 改进后 |
|-----|-------|-------|
| 不知道关注什么 | 全量处理 | 基于 Q 动态决定 |
| 策略独立 | 各自为战 | Q 统一协调 |
| 资源平均 | 100% 均分 | 按 Q 分配优先级 |

### 2.2 多头 Attention（清晰改进）

**机制：**
```python
heads = [
    AttentionHead("market", scorer=lambda Q, K: K.get("price_change", 0)),
    AttentionHead("news", scorer=lambda Q, K: K.get("sentiment", 0)),
    AttentionHead("flow", scorer=lambda Q, K: K.get("volume_spike", 0)),
    AttentionHead("meta", scorer=lambda Q, K: K.get("historical_alpha", 0))
]
```

**改进效果：**

| 问题 | 改进前 | 改进后 |
|-----|-------|-------|
| 单头黑盒 | 单一数值 | 四头并行，可归因 |
| 无法解释 | "注意力0.7" | "市场头0.3 + 新闻头0.4" |
| 调试困难 | 黑盒 | 每个头独立可观测 |

### 2.3 AttentionMemory（记忆改进）

**机制：**
```python
class AttentionMemory:
    def update(self, event, score):
        self.store.append({"event": event, "score": score, "time": time.time()})

    def decay(self):
        # 5分钟半衰期衰减
        for item in self.store:
            dt = now - item["time"]
            item["score"] *= math.exp(-dt / 300)

    def reinforce(self, event, reward):
        # 正奖励强化
        item["score"] *= (1 + reward)
```

**改进效果：**

| 问题 | 改进前 | 改进后 |
|-----|-------|-------|
| 事件被稀释 | 时间平均 | 重要性随时间衰减 |
| 突发被淹没 | 全量平均 | 突发事件保持高权重 |
| 无法追踪 | 事后无法追溯 | 历史可查 |

### 2.4 Bandit 反馈闭环（结果改进）

**机制：**
```python
def process_with_feedback(self, Q, raw_events, feedback):
    result = self.process(Q, raw_events)

    if "reward" in feedback:
        self.memory.reinforce(raw_events, feedback["reward"])

    Q.update(feedback)  # 心随境转

    return result
```

**改进效果：**

| 问题 | 改进前 | 改进后 |
|-----|-------|-------|
| 错误重复 | 无记忆 | 强化/抑制机制 |
| 好信号流失 | 无反馈 | 正奖励强化 |
| 注意力不学习 | 静态 | 动态演化 |

---

## 三、改进对比总结

### 3.1 聚焦改进

```
改进前：事件 → 各模块分别处理（无重点）
改进后：事件 → QueryState 决定优先级 → 注意力分配
```

**效果：**
- 系统资源向高优先级事件倾斜
- 减少无效处理
- 响应更快

### 3.2 清晰改进

```
改进前：单一注意力数值
改进后：多头归因（市场/新闻/资金/元）
```

**效果：**
- 每个决策可解释
- 问题可定位到具体头
- 调参有依据

### 3.3 结果改进

```
改进前：Bandit 仅优化策略选择
改进后：Bandit 同时优化注意力分配
```

**效果：**
- 系统从结果中学习
- 错误率下降
- 收益率提升

### 3.4 错误减少

```
改进前：事件随时间稀释，无法追踪
改进后：持久记忆 + 衰减 + 强化
```

**效果：**
- 异常事件不被淹没
- 问题可追溯
- 预防重复犯错

---

## 四、一句话总结

| 维度 | 改进前 | 改进后 |
|-----|-------|-------|
| 聚焦 | 无重点，全量处理 | Q 驱动，优先级分明 |
| 清晰 | 单头黑盒 | 多头可归因 |
| 结果 | 无反馈闭环 | Bandit 驱动学习 |
| 错误 | 事件稀释 | 持久记忆 + 强化 |

---

## 五、与现有系统协同

```
现有 AttentionSystem (Symbol/板块级)
           ↓
新增 AttentionKernel (Event 级)
           ↓
   聚焦 + 清晰 + 可学习
```