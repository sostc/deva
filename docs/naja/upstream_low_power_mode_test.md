# 上游依赖低频模式测试方案

> 基于最新代码实现（2026-03-27）

## 1. 测试概述

### 1.1 测试目标

验证上游依赖低频模式的双层保障机制：
1. **主动恢复机制**：下游组件在检测到上游恢复时立即恢复正常间隔
2. **AutoTuner 兜底机制**：AutoTuner 能够检测并调整不活跃消费者的间隔

### 1.2 测试范围

| 测试对象 | 测试内容 |
|---------|---------|
| SignalListener | 低功耗模式进入/退出、间隔调整、主动恢复 |
| MarketObserver | 低功耗模式进入/退出、间隔调整、主动恢复 |
| AutoTuner | upstream_inactive 检测、adjust_consumer_interval 执行 |

---

## 2. 测试用例

### 2.1 SignalListener 测试用例

#### TC-001: 进入低频模式

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-001 |
| **用例名称** | SignalListener 进入低频模式 |
| **前置条件** | SignalListener 运行中，`active_count > 0`，`_low_power_mode = False` |
| **测试步骤** | 1. 设置所有策略 `is_processing_data() = False`<br>2. 调用 `_process_signals()` |
| **预期结果** | 1. `_low_power_mode = True`<br>2. `_poll_interval = 60.0`<br>3. 日志输出 "进入低频模式，间隔: 60s" |

#### TC-002: 主动退出低频模式

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-002 |
| **用例名称** | SignalListener 主动退出低频模式 |
| **前置条件** | SignalListener 运行中，`_low_power_mode = True`，`_poll_interval = 60.0` |
| **测试步骤** | 1. 设置至少一个策略 `is_processing_data() = True`<br>2. 调用 `_process_signals()` |
| **预期结果** | 1. `_low_power_mode = False`<br>2. `_poll_interval = 2.0`<br>3. 日志输出 "退出低频模式，间隔恢复: 2s" |

#### TC-003: set_poll_interval 在低功耗模式下不覆盖正常间隔

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-003 |
| **用例名称** | set_poll_interval 正确处理低功耗模式 |
| **前置条件** | `_low_power_mode = True`，`_normal_poll_interval = 2.0`，`_low_power_poll_interval = 60.0` |
| **测试步骤** | 调用 `set_poll_interval(120)` |
| **预期结果** | 1. `_low_power_poll_interval = 120`<br>2. `_poll_interval` 保持为 60.0<br>3. `_normal_poll_interval` 保持为 2.0 |

#### TC-004: set_poll_interval 在正常模式下更新正常间隔

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-004 |
| **用例名称** | set_poll_interval 在正常模式下正确工作 |
| **前置条件** | `_low_power_mode = False`，`_normal_poll_interval = 2.0` |
| **测试步骤** | 调用 `set_poll_interval(5)` |
| **预期结果** | 1. `_normal_poll_interval = 5`<br>2. `_poll_interval = 5`<br>3. 退出低功耗模式时，`_poll_interval` 会恢复到 5.0 |

---

### 2.2 MarketObserver 测试用例

#### TC-101: 进入低频模式

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-101 |
| **用例名称** | MarketObserver 进入低频模式 |
| **前置条件** | MarketObserver 运行中，`_current_datasource = None`，`_low_power_mode = False` |
| **测试步骤** | 在 `_fetch_loop()` 中执行一次循环 |
| **预期结果** | 1. `_low_power_mode = True`<br>2. `_fetch_interval = 60.0`<br>3. 日志输出 "数据源不可用，进入低功耗模式，间隔: 60s" |

#### TC-102: 主动退出低频模式

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-102 |
| **用例名称** | MarketObserver 主动退出低频模式 |
| **前置条件** | MarketObserver 运行中，`_low_power_mode = True`，`_fetch_interval = 60.0` |
| **测试步骤** | 设置 `_current_datasource` 不为 None，在 `_fetch_loop()` 中执行一次循环 |
| **预期结果** | 1. `_low_power_mode = False`<br>2. `_fetch_interval = 5.0`<br>3. 日志输出 "数据源恢复，退出低功耗模式，间隔恢复: 5s" |

#### TC-103: adjust_interval 在低功耗模式下更新低功耗间隔

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-103 |
| **用例名称** | adjust_interval 正确处理低功耗模式 |
| **前置条件** | `_low_power_mode = True`，`_normal_fetch_interval = 5.0`，`_low_power_fetch_interval = 60.0` |
| **测试步骤** | 调用 `adjust_interval(120, "test reason")` |
| **预期结果** | 1. `_low_power_fetch_interval = 120`<br>2. `_fetch_interval` 保持为 60.0 |

#### TC-104: adjust_interval 在正常模式下更新正常间隔

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-104 |
| **用例名称** | adjust_interval 在正常模式下正确工作 |
| **前置条件** | `_low_power_mode = False`，`_normal_fetch_interval = 5.0` |
| **测试步骤** | 调用 `adjust_interval(10, "test reason")` |
| **预期结果** | 1. `_normal_fetch_interval = 10`<br>2. `_fetch_interval = 10` |

---

### 2.3 AutoTuner 测试用例

#### TC-201: 检测 SignalListener 上游不活跃

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-201 |
| **用例名称** | AutoTuner 检测 SignalListener 上游不活跃 |
| **前置条件** | AutoTuner 已初始化，SignalListener 运行中，所有策略 `is_processing_data() = False` |
| **测试步骤** | 调用 `_check_signal_listener_upstream()` |
| **预期结果** | 返回 dict：<br>`{`<br>`'consumer_name': 'signal_listener',`<br>`'current_interval': 2.0,`<br>`'target_interval': 60.0,`<br>`'reason': '无策略处理数据 (active_count=0)'`<br>`}` |

#### TC-202: 检测 MarketObserver 上游不活跃

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-202 |
| **用例名称** | AutoTuner 检测 MarketObserver 上游不活跃 |
| **前置条件** | AutoTuner 已初始化，MarketObserver 运行中，`_current_datasource = None` |
| **测试步骤** | 调用 `_check_market_observer_upstream()` |
| **预期结果** | 返回 dict：<br>`{`<br>`'consumer_name': 'market_observer',`<br>`'current_interval': 5.0,`<br>`'target_interval': 60.0,`<br>`'reason': '数据源不可用 (_current_datasource is None)'`<br>`}` |

#### TC-203: 上游活跃时不返回检测结果

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-203 |
| **用例名称** | AutoTuner 上游活跃时不返回检测结果 |
| **前置条件** | AutoTuner 已初始化，SignalListener 运行中，至少一个策略 `is_processing_data() = True` |
| **测试步骤** | 调用 `_check_signal_listener_upstream()` |
| **预期结果** | 返回 `None` |

#### TC-204: 批量调整消费者间隔

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-204 |
| **用例名称** | AutoTuner 批量调整消费者间隔 |
| **前置条件** | AutoTuner 已初始化，SignalListener 和 MarketObserver 运行中 |
| **测试步骤** | 调用 `_adjust_consumer_intervals([`<br>`{'consumer_name': 'signal_listener', 'target_interval': 60, 'reason': 'test'},`<br>`{'consumer_name': 'market_observer', 'target_interval': 60, 'reason': 'test'}<br>`])` |
| **预期结果** | 1. SignalListener `_low_power_poll_interval = 60`<br>2. MarketObserver `_low_power_fetch_interval = 60` |

#### TC-205: upstream_inactive 条件注册

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-205 |
| **用例名称** | AutoTuner 正确注册 upstream_inactive 条件 |
| **前置条件** | AutoTuner 已初始化 |
| **测试步骤** | 检查 `_conditions['upstream_inactive']` |
| **预期结果** | `cooldown = 30`, `action = 'adjust_consumer_interval'` |

#### TC-206: _check_upstream_inactive 协调检测

| 项目 | 内容 |
|------|------|
| **用例ID** | TC-206 |
| **用例名称** | AutoTuner _check_upstream_inactive 协调检测 |
| **前置条件** | AutoTuner 已初始化，SignalListener 和 MarketObserver 都处于不活跃状态 |
| **测试步骤** | 调用 `_check_upstream_inactive()` |
| **预期结果** | 返回 dict 包含 `inactive_consumers` 列表，长度为 2 |

---

## 3. 测试数据

### 3.1 Mock 数据

```python
# Mock Strategy Entry
class MockStrategyEntry:
    def __init__(self, is_processing: bool = True):
        self._is_processing = is_processing

    def is_processing_data(self, timeout=300):
        return self._is_processing

# Mock Datasource
class MockDatasource:
    def __init__(self, is_running: bool = True):
        self._running = is_running

    def is_running(self):
        return self._running
```

### 3.2 测试间隔配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `_normal_poll_interval` | 2.0 | SignalListener 正常间隔 |
| `_low_power_poll_interval` | 60.0 | SignalListener 低功耗间隔 |
| `_normal_fetch_interval` | 5.0 | MarketObserver 正常间隔 |
| `_low_power_fetch_interval` | 60.0 | MarketObserver 低功耗间隔 |

---

## 4. 测试执行方式

### 4.1 手动测试

```python
# 测试 SignalListener
from deva.naja.bandit.signal_listener import SignalListener

listener = SignalListener()
listener.start()

# 模拟无策略场景
# ... (见 TC-001)

# 模拟有策略场景
# ... (见 TC-002)

listener.stop()
```

### 4.2 自动化测试

```bash
# 执行测试文件
cd /Users/spark/pycharmproject/deva
python -m pytest deva/naja/common/test_upstream_low_power.py -v
```

---

## 5. 测试通过标准

| 优先级 | 测试用例 | 通过条件 |
|--------|---------|---------|
| P0 | TC-001, TC-002 | 低功耗模式正确进入/退出 |
| P0 | TC-101, TC-102 | 低功耗模式正确进入/退出 |
| P1 | TC-003, TC-004 | set_poll_interval 正确处理低功耗模式 |
| P1 | TC-103, TC-104 | adjust_interval 正确处理低功耗模式 |
| P1 | TC-201, TC-202 | AutoTuner 正确检测不活跃消费者 |
| P2 | TC-203, TC-205 | AutoTuner 边界条件正确处理 |
| P2 | TC-204, TC-206 | AutoTuner 批量调整正确执行 |

---

## 6. 相关文档

- [upstream_low_power_mode_design.md](upstream_low_power_mode_design.md) - 设计方案
- [bandit_guide.md](bandit_guide.md) - Bandit 系统指南
