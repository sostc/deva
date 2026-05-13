# SignalTuner 接入 RuntimeStateManager 计划

## 现状分析

### SignalTuner 现有持久化机制

| 项目 | 当前实现 |
|------|----------|
| 存储表 | `naja_signal_tuner` |
| 加载时机 | `__init__()` 中调用 `_load_state()` |
| 保存时机 | `stop()` 和每次参数调整后调用 `_save_state()` |
| 数据内容 | `params`, `weights`, `last_update` |

### 现有方法签名
```python
def _load_state(self):
    # 从 NB("naja_signal_tuner") 读取 tuner_state

def _save_state(self):
    # 保存到 NB("naja_signal_tuner")
```

---

## 可行性评估

### ✅ 靠谱的地方

1. **接口一致** - `SignalTuner` 已有明确的 `save`/`load` 概念，与 `StatefulComponent` 一致
2. **独立存储** - 使用单独的表 `naja_signal_tuner`，不会与其他组件冲突
3. **优先级明确** - SignalTuner 是调参器，在策略之后工作，priority 可以设为 35（介于 strategy_manager 和 attention_center 之间）
4. **UI 已有基础** - RuntimeStateManager UI 已可用，接入后自动获得查看功能

### ⚠️ 需要注意的地方

1. **双重保存问题** - 如果同时保留原有的 `_save_state()` 和新的 `save_state()`，会导致重复保存
   - 解决方案：保留原有逻辑作为"增量保存"，RuntimeStateManager 的 `save_state()` 作为"全量快照"

2. **初始化时机** - SignalTuner 在 `__init__` 中自动加载状态，接入 RuntimeStateManager 后需要确保注册顺序正确

3. **线程安全** - SignalTuner 使用 `RLock`，RuntimeStateManager 调用时需要确保锁的正确使用

---

## 实现方案

### 步骤 1: 创建 SignalTunerAdapter

```python
# adapters.py 中添加
class SignalTunerAdapter(StatefulComponent):
    def __init__(self, tuner):
        self._tuner = tuner

    @property
    def persistence_id(self) -> str:
        return "signal_tuner"

    @property
    def persistence_table(self) -> str:
        return "naja_signal_tuner"

    @property
    def persistence_priority(self) -> int:
        return 35  # 在策略之后，注意力之前

    @property
    def persistence_name(self) -> str:
        return "信号调谐器"

    def load_state(self) -> bool:
        self._tuner._load_state()
        return True

    def save_state(self) -> bool:
        self._tuner._save_state()
        return True

    def verify_state(self) -> bool:
        return True
```

### 步骤 2: 修改 adapters.py 中的 register_all_adapters()

```python
# 在 RadarEngineAdapter 之后添加
try:
    from deva.naja.attention.intelligence import SignalTuner
    # 获取全局 SignalTuner 实例（如果存在）
    tuner = getattr(SignalTuner, '_global_instance', None)
    if tuner:
        mgr.register(SignalTunerAdapter(tuner))
        logger.info("[RuntimeStateManager] 已注册 SignalTuner")
except Exception as e:
    logger.warning(f"[RuntimeStateManager] SignalTuner 注册失败: {e}")
```

### 步骤 3: 验证 SignalTuner 单例访问方式

需要检查 SignalTuner 的全局访问方式：
- 是否使用单例模式？
- 如何获取全局实例？

---

## 工作量估计

| 步骤 | 工作量 | 风险 |
|------|--------|------|
| 创建 Adapter | 小 | 低 |
| 注册到 RuntimeStateManager | 小 | 中（取决于单例访问方式） |
| 测试保存/加载 | 中 | 低 |

---

## 结论

**靠谱程度：8/10**

这是一个合理的扩展请求：
- SignalTuner 已经有完善的持久化机制
- 接入 RuntimeStateManager 可以获得统一的监控和管理界面
- 不需要大幅修改现有代码，只添加适配层

**主要风险：** SignalTuner 的单例访问方式需要先确认。

---

## 待确认问题

1. SignalTuner 是否使用单例模式？如何获取全局实例？
2. 是否需要移除原有的 `_save_state`/`_load_state` 调用，还是保留作为增量保存？