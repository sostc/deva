# Naja 系统退出持久化修复报告

> 日期：2026-04-22
> 状态：✅ 已完成

## 1. 问题描述

系统退出时，部分核心组件的状态没有正确持久化，导致重启后丢失运行时状态。

### 1.1 发现的问题

| 组件 | 问题 | 影响 |
|------|------|------|
| AttentionOS | 缺少 `persist_state()` 方法 | 注意力内核、策略决策、关注管理状态丢失 |
| OSAttentionKernel | 缺少 `persist_state()` 方法 | 最后一次注意力计算结果丢失 |
| StrategyDecisionMaker | 缺少 `persist_state()` 方法 | 题材权重、频率配置丢失 |
| RadarEngine | 缺少 `save_state()` 方法 | 雷达配置和线程状态丢失 |
| CognitionEngine | 只有自动保存，没有显式退出保存 | 两次保存之间的状态丢失 |
| NarrativeTracker | `save_state()` 存在但未被调用 | 叙事追踪状态丢失 |

## 2. 修复方案

### 2.1 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `deva/naja/attention/os/attention_os.py` | 新增 `persist_state()` 方法，协调子组件持久化 |
| `deva/naja/attention/os/os_kernel.py` | 新增 `persist_state()` 方法 |
| `deva/naja/attention/os/strategy_decision.py` | 新增 `persist_state()` 方法 |
| `deva/naja/radar/engine.py` | 新增 `save_state()` 方法 |
| `deva/naja/cognition/engine.py` | 新增 `shutdown()` 方法 |
| `deva/naja/supervisor/recovery.py` | 优化认知组件退出调用逻辑 |

### 2.2 退出调用链路

```
supervisor.shutdown()
  ├→ HistoryTracker.save_state()
  ├→ stop_monitoring()
  └→ _stop_all_components()
       ├→ SignalStream.close(persist=True)
       ├→ ResultStore.close()
       ├→ InsightPool.persist()
       ├→ AttentionOS.persist_state()
       │    ├→ OSAttentionKernel.persist_state()
       │    ├→ StrategyDecisionMaker.persist_state()
       │    ├→ FocusManager.persist_state()
       │    └→ NarrativeTracker.save_state()
       ├→ RadarEngine.save_state()
       ├→ CognitionEngine.shutdown()
       │    ├→ stop_auto_save()
       │    └→ save_state()
       ├→ MarketHotspotIntegration.persist_state()
       └→ Strategy/Datasource/Task.stop()
```

### 2.3 atexit 兜底

在 `bootstrap.py` 中注册的 `atexit` 回调作为兜底保障：

```python
atexit.register(_cleanup)  # 包含 HistoryTracker + Attention + Hotspot
```

## 3. 持久化方法命名约定

| 类型 | 方法名 | 说明 |
|------|--------|------|
| 引擎/系统 | `save_state()` | 返回状态字典，供外部存储 |
| 学习器 | `persist()` | 直接持久化到磁盘/数据库 |
| 管理器 | `persist_state()` | 协调子组件的持久化 |
| 流/监听器 | `close(persist=True)` | 关闭时可选持久化 |
| 带后台任务 | `shutdown()` | 停止后台任务 + 立即保存 |

## 4. 测试结果

### 4.1 方法存在性测试

```
【注意力系统】
✅ AttentionOS.persist_state() 存在
✅ OSAttentionKernel.persist_state() 存在
✅ StrategyDecisionMaker.persist_state() 存在

【雷达系统】
✅ RadarEngine.save_state() 存在

【认知系统】
✅ CognitionEngine.shutdown() 存在
✅ CognitionEngine.save_state() 存在
✅ NarrativeTracker.save_state() 存在

【热点系统】
✅ MarketHotspotIntegration.persist_state() 存在
✅ HotspotIntelligenceSystem.persist_state() 存在
✅ HotspotLearningSystem.persist() 存在
✅ MarketHotspotHistoryTracker.save_state() 存在

【信号系统】
✅ SignalStream.close() 存在
✅ SignalStream.persist() 存在
✅ InsightPool.persist() 存在
✅ SignalListener.stop() 存在

测试通过: 15/15
```

### 4.2 调用链路测试

```
【检查 _stop_all_components 调用链】
✅ SignalStream.close(persist=True)
✅ InsightPool.persist()
✅ AttentionOS.persist_state()
✅ RadarEngine.save_state()
✅ CognitionEngine.shutdown()
✅ CognitionEngine.save_state()（备用）
✅ MarketHotspotIntegration.persist_state()
✅ Strategy/Datasource/Task.stop()

【检查 AttentionOS.persist_state 内部调用链】
✅ OSAttentionKernel.persist_state()
✅ StrategyDecisionMaker.persist_state()
✅ FocusManager.persist_state()
✅ NarrativeTracker.save_state()

【检查 shutdown 流程】
✅ HistoryTracker.save_state()
✅ stop_monitoring()
✅ _stop_all_components()

【检查 atexit 注册】
✅ tracker.save_state()
✅ attention.persist_state()
✅ hotspot_integration.persist_state()
✅ atexit.register(_cleanup)
```

## 5. 持久化数据存储

所有持久化数据存储在 NB 数据库中，表名规范：

| 组件 | 表名 |
|------|------|
| 注意力内核 | `naja_attention_kernel_state` |
| 策略决策 | `naja_attention_strategy_state` |
| 热点系统 | `naja_hotspot_state` |
| 洞察池 | `naja_insights` |
| 叙事追踪 | `naja_narrative_states` |
| 雷达事件 | `naja_radar_events` |
| 信号流 | `recentSignal` |

## 6. 持久化实现规则

1. **每个核心组件必须实现退出持久化方法**
2. **持久化必须带异常捕获**，避免一个组件失败影响其他组件
3. **有后台任务的组件必须先停止再保存**
4. **持久化数据集中存储在 NB 数据库**

## 7. 新增组件的持久化要求

新增核心组件时，必须同时实现：

```python
class MyComponent:
    def save_state(self) -> Dict[str, Any]:
        """保存状态用于持久化"""
        return {
            'key_field': self._key_field,
            # ...
        }
```

并在 `_stop_all_components()` 中添加调用：

```python
try:
    comp = self._get_component('my_component')
    if comp and hasattr(comp, 'save_state'):
        comp.save_state()
except Exception as e:
    log.error(f"保存组件状态失败: {e}")
```

## 8. 总结

本次修复完成了 Naja 系统退出时的完整持久化链路，确保：

- ✅ 所有 15 个核心组件都实现了持久化方法
- ✅ 退出调用链路完整，覆盖注意力、雷达、认知、热点、信号等所有核心模块
- ✅ 有 atexit 兜底保障
- ✅ 所有持久化调用都有异常处理
- ✅ 已更新架构基线文档，将生命周期管理纳入开发规范
