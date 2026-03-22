# 注意力反馈系统改进 - 复盘与潜在问题分析

## 一、已完成的工作

### 1.1 核心改动

| 改动 | 文件 | 说明 |
|------|------|------|
| 启用 feedback 默认值 | `attention_config.py` | `enable_feedback=True`, `enable_strategy_learning=True` |
| BanditAutoRunner 自动启动 | `supervisor.py` | 当 feedback 启用时自动启动 |
| AttentionTracker | `attention/tracker.py` | 新的观察跟踪器，不需要实际成交 |
| PriceMonitor | `attention/price_monitor.py` | 价格监控服务 |
| FeedbackLoop 扩展 | `feedback_loop.py` | 新增 `record_observation()` 和 `record_price_feedback()` |
| 策略基类集成 | `attention/strategies/base.py` | 信号产生时自动调用 AttentionTracker |
| Supervisor 集成 | `supervisor.py` | 启动 tracker、monitor 并建立反馈链路 |

### 1.2 新反馈流程（实时 + 回放）

```
注意力策略产生信号
       ↓
  emit_signal()
       ↓
  _track_attention_signal() → AttentionTracker.track_attention()
       ↓
  PriceMonitor 订阅数据源流（实时/回放）
       ↓
  _on_data_received() 接收 tick 数据
       ↓
  _update_price() 更新价格（首次价格自动设为入场价）
       ↓
  FeedbackLoop.record_price_feedback() (实时)
  FeedbackLoop.record_observation() (观察结束时)
       ↓
  BanditUpdater.update() → 学习更新
```

**回放模式支持**:
- PriceMonitor 订阅数据源流，回放数据会自动推送
- 即使信号先于价格到达，也能正常创建跟踪
- 首次价格更新会自动设为入场价
- 不依赖 `naja_realtime_quotes` 缓存

---

## 二、潜在问题分析

### 2.1 数据源依赖问题

**问题**: PriceMonitor 从市场 tick 数据源获取价格（已修复）

```python
# price_monitor.py
# 优先使用市场 tick 数据源订阅流
# 备用从 NB("naja_realtime_quotes") 缓存获取

数据源:
1. 市场 tick 数据源 (MarketDataObserver 机制)
2. NB("naja_realtime_quotes") 缓存 (备用)
```

**风险**:
- 数据源未运行时需要主动获取
- 非交易时间可能获取不到数据

**缓解措施**:
- 数据源运行时自动订阅流
- 数据源停止时自动切换到主动获取模式
- 备用模式从 `naja_realtime_quotes` 缓存获取

**建议**:
- [ ] 监控数据源连接状态
- [ ] 非交易时间降低更新频率

---

### 2.2 观察时长配置问题

**问题**: `observation_duration=3600` (1小时) 可能是任意设置

```python
# supervisor.py
attention_tracker = ensure_attention_tracker(
    observation_duration=3600.0,  # 1小时
    min_confidence=0.5,
)
```

**风险**:
- 1小时可能不够观察中期趋势
- 不同股票特性不同，统一时长不 optimal

**建议**:
- [ ] 观察时长应该根据市场状态动态调整
- [ ] 可以考虑根据 volatility 设置不同时长

---

### 2.3 冷启动问题

**问题**: Bandit 算法需要一定样本量才能有效学习

**风险**:
- 初期 feedback 可能噪声较大
- 初期注意力权重调整可能不准确

**建议**:
- [ ] 添加冷启动保护，前 N 个样本不更新 Bandit
- [ ] 初期使用更高的 exploration factor
- [ ] 添加样本量阈值检查

---

### 2.4 多策略冲突问题

**问题**: 同一标的可能被多个策略同时跟踪

**风险**:
- 多个策略对同一标的产生不同信号
- feedback 可能相互矛盾

**当前处理**:
```python
# tracker.py
if symbol in self._tracked:
    existing = self._tracked[symbol]
    if existing.status == "TRACKING":
        return existing  # 复用已有跟踪
```

**建议**:
- [ ] 添加策略ID记录，区分不同策略的观察
- [ ] 或允许多策略同时跟踪同一标的（分别记录）

---

### 2.5 数据持久化问题

**问题**: AttentionTracker 和 PriceMonitor 的状态没有完全持久化

**风险**:
- 重启后丢失跟踪状态
- 历史反馈数据丢失

**当前处理**:
- AttentionTracker 会从数据库恢复 `TRACKING` 状态的跟踪
- FeedbackLoop 有 `persist()` 和 `load()` 方法

**建议**:
- [ ] PriceMonitor 的 `_tracked` 状态也应该持久化
- [ ] 定期持久化反馈历史到数据库
- [ ] 考虑使用更持久的存储（如 SQLite）

---

### 2.6 反馈延迟问题

**问题**: 实时价格反馈可能不够精确

**风险**:
- 60秒更新间隔可能错过短期波动
- 收盘价 vs 实时价的差异

**建议**:
- [ ] 添加分时数据获取（更高频）
- [ ] 或使用快照价格而非实时价格

---

### 2.7 与现有 Bandit 系统的关系

**问题**: AttentionTracker 和 BanditVirtualPortfolio 功能有重叠

```
BanditVirtualPortfolio: 需要实际成交
AttentionTracker: 不需要成交
```

**风险**:
- 同一信号可能被两个系统同时跟踪
- 重复的 feedback 可能导致过度学习

**当前设计**:
- 两者独立运行
- BanditAutoRunner 仍按原逻辑工作

**建议**:
- [ ] 考虑合并或明确区分两者的职责
- [ ] 或添加标记避免重复反馈

---

### 2.8 内存泄漏风险

**问题**: `_price_history` 和 `_tracked` 可能无限增长

```python
# tracker.py
self._price_history: Dict[str, deque] = {}
self._max_history_len = 100  # 有界
self._tracked: Dict[str, TrackedAttention] = {}  # 无界
```

**风险**:
- 大量标的被跟踪后内存占用增加
- 关闭的跟踪不会被清理

**缓解**:
- `close_tracking()` 后状态变为 `CLOSED`
- 但字典不会自动清理

**建议**:
- [ ] 定期清理过期的 CLOSED 状态
- [ ] 添加 `_tracked` 字典大小限制

---

## 三、测试建议

### 3.1 单元测试
- [ ] `AttentionTracker.track_attention()` 基本跟踪
- [ ] `AttentionTracker.update_price()` 价格更新
- [ ] `AttentionTracker.close_tracking()` 观察结束
- [ ] `FeedbackLoop.record_observation()` 反馈记录
- [ ] `FeedbackLoop.record_price_feedback()` 实时反馈

### 3.2 集成测试
- [ ] 策略信号 → AttentionTracker → PriceMonitor → FeedbackLoop 完整链路
- [ ] 重启后状态恢复
- [ ] 多标的同时跟踪

### 3.3 压力测试
- [ ] 大量信号同时产生
- [ ] 价格获取失败的处理
- [ ] 内存占用监控

---

## 四、后续优化方向

### 4.1 短期 (1-2周)
1. 添加单元测试覆盖
2. 完善持久化机制
3. 添加监控指标面板

### 4.2 中期 (1个月)
1. 实现动态观察时长
2. 多策略冲突处理
3. 冷启动保护机制

### 4.3 长期
1. 与现有 Bandit 系统深度整合
2. 强化学习替代 Bandit
3. 跨市场注意力分配

---

## 五、总结

本次改进实现了用户「不需要买入，只要注意力识别到就跟踪价格形成反馈」的思路：

**优势**:
- 反馈样本量大幅增加（所有注意力标的 vs 只有成交标的）
- 学习速度更快（观察开始即可学习）
- 反馈更及时（实时更新 vs 平仓后更新）

**风险**:
- 数据源依赖
- 冷启动问题
- 与现有系统的关系
- 持久化和内存管理

**建议**:
1. 先观察运行一段时间，确认数据流正常
2. 逐步增加样本量，避免冷启动问题
3. 监控内存使用，及时优化

---

*文档生成时间: 2026-03-22*
