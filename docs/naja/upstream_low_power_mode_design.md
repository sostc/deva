# 上游依赖低频模式设计方案

> 基于最新代码实现（2026-03-27）

## 1. 背景与问题

### 1.1 问题描述

在 Naja 交易系统中，存在多个"消费者"组件，它们依赖于"上游"数据源产生的数据。当上游没有数据时，这些消费者组件仍然以正常的频率轮询，导致：

1. **资源浪费**：在无数据时仍然高频轮询
2. **日志刷屏**：SignalListener 每 2 秒打印一次"没有策略在处理数据"
3. **响应延迟**：当上游恢复时，无法及时感知

### 1.2 涉及组件

| 消费者组件 | 上游依赖 | 正常间隔 | 原低频间隔 |
|-----------|---------|---------|-----------|
| SignalListener | 策略处理数据 (`active_count > 0`) | 2s | 不变 |
| MarketObserver | 数据源可用 (`_current_datasource != None`) | 5s | 不变 |

---

## 2. 设计方案

### 2.1 核心思想

**双层保障机制**：
1. **主动恢复**：下游组件在每次轮询时检测上游状态，**立即**恢复
2. **AutoTuner 兜底**：如果主动恢复失败，AutoTuner 每 60 秒检查一次，确保最终能调整间隔

### 2.2 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        上游数据层                                │
│  ┌─────────────────┐       ┌─────────────────┐                 │
│  │  数据源 (Datasource)│     │  策略 (Strategy) │                 │
│  └────────┬────────┘       └────────┬────────┘                 │
│           │                          │                          │
│           │ 产生数据                  │ 产生信号                 │
└───────────┼──────────────────────────┼──────────────────────────┘
            │                          │
            ▼                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                        下游消费层                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    SignalListener                       │    │
│  │  - _low_power_mode: bool                               │    │
│  │  - _normal_poll_interval: 2.0                          │    │
│  │  - _low_power_poll_interval: 60.0                      │    │
│  │  - 主动检测: active_count > 0 时立即恢复                 │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    MarketObserver                        │    │
│  │  - _low_power_mode: bool                               │    │
│  │  - _normal_fetch_interval: 5.0                         │    │
│  │  - _low_power_fetch_interval: 60.0                      │    │
│  │  - 主动检测: _current_datasource != None 时立即恢复      │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                          │
                          │ AutoTuner 兜底（60秒检查一次）
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                        AutoTuner                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              upstream_inactive 检测条件                 │    │
│  │  - _check_upstream_inactive()                          │    │
│  │  - _check_signal_listener_upstream()                    │    │
│  │  - _check_market_observer_upstream()                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              _execute_auto_action()                     │    │
│  │  - adjust_consumer_interval: 批量调整间隔               │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 状态机

#### SignalListener 状态机

```
                    ┌─────────────────────────────────────┐
                    │                                     │
                    ▼                                     │
              ┌──────────┐     active_count==0     ┌──────────────┐
    normal ──▶│  NORMAL  │ ─────────────────────▶  │ LOW_POWER    │
              │ interval=2s│                          │ interval=60s │
              └──────────┘◀──────────────────────  └──────────────┘
                    │     active_count>0 (立即恢复)            │
                    │                                         │
                    └─────────────────────────────────────────┘
                              upstream recovered
```

#### MarketObserver 状态机

```
                    ┌─────────────────────────────────────┐
                    │                                     │
                    ▼                                     │
              ┌──────────┐   datasource=None       ┌──────────────┐
    normal ──▶│  NORMAL  │ ─────────────────────▶    │ LOW_POWER    │
              │ interval=5s│                          │ interval=60s │
              └──────────┘◀──────────────────────  └──────────────┘
                    │     datasource!=None (立即恢复)             │
                    │                                         │
                    └─────────────────────────────────────────┘
                              upstream recovered
```

---

## 3. 实现细节

### 3.1 SignalListener 变更

**文件**：`deva/naja/bandit/signal_listener.py`

**新增字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `_low_power_mode` | bool | False | 是否处于低功耗模式 |
| `_normal_poll_interval` | float | 2.0 | 正常轮询间隔 |
| `_low_power_poll_interval` | float | 60.0 | 低功耗轮询间隔 |

**核心逻辑变更**：

```python
# _process_signals() 中的变更
if active_count == 0:
    if not self._low_power_mode:
        self._low_power_mode = True
        self._poll_interval = self._low_power_poll_interval
        log.info(f"[SignalListener] 没有策略在处理数据，进入低频模式，间隔: {self._poll_interval}s")
    return

# ... 处理信号 ...

if self._low_power_mode:
    self._low_power_mode = False
    self._poll_interval = self._normal_poll_interval
    log.info(f"[SignalListener] 上游恢复，退出低频模式，间隔恢复: {self._poll_interval}s")
```

**新增方法**：

| 方法 | 说明 |
|------|------|
| `set_poll_interval(seconds)` | 设置轮询间隔，正确处理低功耗模式 |

### 3.2 MarketObserver 变更

**文件**：`deva/naja/bandit/market_observer.py`

**新增字段**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `_low_power_mode` | bool | False | 是否处于低功耗模式 |
| `_normal_fetch_interval` | float | 5.0 | 正常获取间隔 |
| `_low_power_fetch_interval` | float | 60.0 | 低功耗获取间隔 |
| `_last_datasource_available` | bool | True | 上次数据源是否可用 |

**核心逻辑变更**：

```python
# _fetch_loop() 中的变更
if self._current_datasource:
    datasource_available = is_running
else:
    datasource_available = False

# 低功耗模式管理
if not datasource_available:
    if not self._low_power_mode:
        self._low_power_mode = True
        self._fetch_interval = self._low_power_fetch_interval
        log.info(f"[MarketObserver] 数据源不可用，进入低功耗模式，间隔: {self._fetch_interval}s")
else:
    if self._low_power_mode:
        self._low_power_mode = False
        self._fetch_interval = self._normal_fetch_interval
        log.info(f"[MarketObserver] 数据源恢复，退出低功耗模式，间隔恢复: {self._fetch_interval}s")
```

**新增方法**：

| 方法 | 说明 |
|------|------|
| `adjust_interval(interval, reason)` | 调整获取间隔，正确处理低功耗模式 |

### 3.3 AutoTuner 变更

**文件**：`deva/naja/common/auto_tuner.py`

**新增调优条件**：

```python
self._conditions['upstream_inactive'] = TuneCondition(
    cooldown=30,
    threshold=0,
    action='adjust_consumer_interval'
)
```

**新增检测方法**：

| 方法 | 说明 |
|------|------|
| `_check_upstream_inactive()` | 主检测函数，协调检测 SignalListener 和 MarketObserver |
| `_check_signal_listener_upstream()` | 检测 SignalListener 上游是否不活跃 |
| `_check_market_observer_upstream()` | 检测 MarketObserver 上游是否不活跃 |
| `_adjust_consumer_intervals()` | 批量调整消费者组件的轮询间隔 |

**新增执行方法**：

| 方法 | 说明 |
|------|------|
| `_execute_auto_action()` | 通用自动动作执行器，新增对 `adjust_consumer_interval` 的处理 |

**检测流程**：

```
_perform_checks() 每 60 秒执行
    │
    ├── _check_upstream_inactive()
    │       │
    │       ├── _check_signal_listener_upstream()
    │       │       └── 检测 active_count == 0 ?
    │       │
    │       └── _check_market_observer_upstream()
    │               └── 检测 _current_datasource is None ?
    │
    └── _execute_auto_action()
            └── adjust_consumer_interval
                    └── _adjust_consumer_intervals()
                            ├── SignalListener.set_poll_interval(60)
                            └── MarketObserver.adjust_interval(60)
```

---

## 4. 响应时间对比

| 场景 | 之前 | 现在 |
|------|------|------|
| **进入低频** | 立即检测，但间隔不变 | 立即检测 + 进入低功耗模式 + 增大间隔 |
| **退出低频** | 最多 120 秒（AutoTuner 60s + 轮询 60s） | **立即**（主动检测） |

---

## 5. 日志输出示例

### 5.1 SignalListener 日志

```
# 进入低频
[SignalListener] 没有策略在处理数据，进入低频模式，间隔: 60s

# 退出低频（主动恢复）
[SignalListener] 上游恢复，退出低频模式，间隔恢复: 2s

# AutoTuner 兜底调整
[AutoTuner] SignalListener 间隔调整: 2s → 60s (无策略处理数据)
```

### 5.2 MarketObserver 日志

```
# 进入低频
[MarketObserver] _fetch_loop: _current_datasource is None, waiting...
[MarketObserver] 数据源不可用，进入低功耗模式，间隔: 60s

# 退出低频（主动恢复）
[MarketObserver] 数据源恢复，退出低功耗模式，间隔恢复: 5s

# AutoTuner 兜底调整
[AutoTuner] MarketObserver 间隔调整: 5s → 60s (数据源不可用)
```

---

## 6. 扩展性设计

### 6.1 添加新的消费者组件

如需添加新的消费者组件（如 `RadarNewsFetcher`），按照以下步骤：

1. **添加状态字段**：
   ```python
   self._low_power_mode = False
   self._normal_interval = 10.0
   self._low_power_interval = 300.0
   ```

2. **实现主动恢复逻辑**：
   ```python
   if upstream_available:
       if self._low_power_mode:
           self._low_power_mode = False
           self._interval = self._normal_interval
   else:
       if not self._low_power_mode:
           self._low_power_mode = True
           self._interval = self._low_power_interval
   ```

3. **在 AutoTuner 中注册**：
   ```python
   def _check_new_consumer_upstream(self) -> Optional[Dict]:
       # 检测逻辑
       if not available:
           return {
               'consumer_name': 'new_consumer',
               'current_interval': self._interval,
               'target_interval': self._low_power_interval,
               'reason': '...'
           }
       return None
   ```

4. **在 `_adjust_consumer_intervals` 中添加处理**：
   ```python
   elif consumer_name == 'new_consumer':
       from module.path import get_new_consumer
       consumer = get_new_consumer()
       consumer.set_interval(target_interval)
   ```

### 6.2 调整低功耗间隔

如需调整低功耗模式的间隔阈值，修改以下常量：

| 组件 | 常量 | 默认值 | 说明 |
|------|------|--------|------|
| SignalListener | `_low_power_poll_interval` | 60.0 | 低频轮询间隔（秒） |
| MarketObserver | `_low_power_fetch_interval` | 60.0 | 低频获取间隔（秒） |
| AutoTuner | `upstream_inactive.cooldown` | 30 | 检测冷静期（秒） |

---

## 7. 相关文件清单

| 文件 | 修改类型 | 说明 |
|------|---------|------|
| `deva/naja/bandit/signal_listener.py` | 修改 | 新增低功耗模式支持 |
| `deva/naja/bandit/market_observer.py` | 修改 | 新增低功耗模式支持 + `adjust_interval()` |
| `deva/naja/common/auto_tuner.py` | 修改 | 新增 `upstream_inactive` 检测条件 |

---

## 8. 参考文档

- [bandit_guide.md](bandit_guide.md) - Bandit 系统指南
- [performance_guide.md](performance_guide.md) - 性能优化指南
- [AutoTuner 源码](../common/auto_tuner.py) - 自动调优器实现
