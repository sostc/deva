# 需求评估：注意力策略接入策略管理系统

## 需求概述

```
5. 将注意力系统的5个策略接入策略管理系统
6. AttentionStrategy 实现 StrategyEntry 接口或包装层
7. 统一注意力策略和独立策略的结果存储
8. 在策略管理UI中显示注意力策略状态和详情
```

## 现有架构分析

### 注意力策略系统
- **5个注意力策略**：`GlobalMarketSentinel`, `SectorRotationHunter`, `MomentumSurgeTracker`, `AnomalyPatternSniper`, `SmartMoneyFlowDetector`
- **基类**：`AttentionStrategyBase`（位于 `deva/naja/attention/strategies/base.py`）
- **管理器**：`AttentionStrategyManager`（位于 `deva/naja/attention/strategies/strategy_manager.py`）
- **信号类型**：`Signal` dataclass
- **信号转发**：已通过 `StrategyResult` 发送到 `SignalStream`

### 策略管理系统（Strategy V2）
- **核心类**：`StrategyEntry`（继承自 `RecoverableUnit`，位于 `deva/naja/strategy/__init__.py`）
- **结果存储**：`StrategyResult`（位于 `deva/naja/strategy/result_store.py`）
- **UI管理**：`strategy/ui.py`

---

## 靠谱程度评估：**6/10**（可行但有一定工作量）

### 支持因素 ✅

1. **信号已对接**：注意力策略的信号已经通过 `_forward_signal_to_bandit()` 和 `_forward_signal_to_stream()` 发送到 `SignalStream`，使用 `StrategyResult` 格式

2. **结果存储已统一**：`StrategyResult` 是两种策略共用的结果格式

3. **管理器已存在**：`AttentionStrategyManager` 已经有完整的生命周期管理（register/unregister/enable/disable）

4. **架构兼容**：注意力策略和普通策略都是"策略"，概念上一致

### 挑战因素 ⚠️

1. **并行架构**：当前存在两套策略管理系统：
   - `AttentionStrategyManager`（注意力专用）
   - 策略管理系统的各种 Handler（`RadarHandler`, `MemoryHandler` 等）

2. **接口不兼容**：`AttentionStrategyBase` 没有实现 `StrategyEntry` 接口，直接改造会有侵入性

3. **UI 深度整合**：需要在策略管理 UI 中添加注意力策略的专属视图（状态监控、注意力上下文展示等）

4. **数据流整合**：需要确保两种策略的结果能在一个界面统一展示和对比

---

## 推荐实现方案

### 方案：包装层模式（低侵入）

不直接修改 `AttentionStrategyBase`，而是为注意力策略创建一个**适配层**，将其包装成策略管理系统可识别的形式。

```
┌─────────────────────────────────────────────────────────────┐
│                    策略管理系统 (StrategyEntry)              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              AttentionStrategyWrapper                       │
│  - 实现 StrategyEntry 接口                                   │
│  - 代理到 AttentionStrategyManager                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              AttentionStrategyManager                        │
│  - 管理5个注意力策略                                         │
│  - 全局单例模式                                              │
└─────────────────────────────────────────────────────────────┘
```

### 具体任务

#### Task 5: 接入策略管理系统
- [ ] 创建 `AttentionStrategyWrapper` 类，实现 `StrategyEntry` 接口
- [ ] 在 `AttentionStrategyManager` 中添加 `create_strategy_entry()` 方法
- [ ] 注册到策略管理系统的数据库

#### Task 6: 实现包装层
- [ ] `AttentionStrategyWrapper._get_pipeline()` 返回注意力策略的 Pipeline
- [ ] `AttentionStrategyWrapper.process()` 代理到具体的注意力策略
- [ ] 保持原有的注意力感知能力（动态间隔、冷却期等）

#### Task 7: 统一结果存储
- [ ] 确认 `Signal → StrategyResult` 转发链路稳定
- [ ] 在 `SignalStream` 中正确标记注意力策略来源（已有 `metadata['source'] = 'attention_strategy'`）
- [ ] 确保策略管理 UI 可以按类型筛选

#### Task 8: UI 展示
- [ ] 在策略列表中显示注意力策略（带特殊标识）
- [ ] 添加注意力策略详情页入口
- [ ] 展示注意力上下文（全局注意力、板块权重等）

---

## 工作量估算

| 任务 | 复杂度 | 预估工作 |
|------|--------|----------|
| Task 5 | 中 | 包装类 + 注册逻辑 |
| Task 6 | 中 | Pipeline 代理实现 |
| Task 7 | 低 | 已有链路，验证即可 |
| Task 8 | 中高 | UI 页面开发 |
| **总计** | - | **中等规模** |

---

## 结论

**需求是靠谱的**，原因：
1. 架构上可行，不破坏现有结构
2. 已有部分基础（信号转发已完成）
3. 符合系统演进方向（统一管理）
4. UI 展示有实际价值

**需要注意**：
1. 保持 `AttentionStrategyManager` 的独立性和特殊性（注意力感知是核心竞争力）
2. 不要过度耦合，让两套系统可以独立演进
3. 包装层设计要考虑到未来可能的重构
