# 单例模式整改计划

> 文档版本: v1.0
> 生成日期: 2026-04-08
> 状态: 待执行

---

## 一、现状分析

### 1.1 问题总结

项目中存在 **42+ 个单例模式实现**，分散在各个模块中：

```
deva/naja/
├── attention/
│   ├── integration/extended.py     # NajaAttentionIntegration, AttentionModeManager
│   ├── attention_os.py             # AttentionOS
│   ├── signal_executor.py          # SignalExecutor
│   ├── data_processor.py           # DataProcessor
│   ├── trading_center.py           # TradingCenter
│   ├── realtime_data_fetcher.py    # RealtimeDataFetcher
│   ├── processing/noise_manager.py
│   ├── processing/block_noise_detector.py
│   ├── cognition_orchestrator.py
│   ├── state_querier.py
│   ├── focus_manager.py
│   ├── liquidity_manager.py
│   └── ...
├── bandit/
│   ├── market_data_bus.py
│   ├── optimizer.py
│   ├── tuner.py
│   └── portfolio_manager.py
├── cognition/
│   ├── history_tracker.py
│   └── insight/llm_reflection.py
├── common/
│   ├── stock_registry.py
│   ├── auto_tuner.py
│   ├── thread_pool.py
│   └── recoverable.py
├── radar/
│   └── engine.py
├── strategy/
│   ├── result_store.py
│   ├── output_controller.py
│   └── daily_review_scheduler.py
├── config/
│   └── __init__.py
├── signal/
│   ├── stream.py
│   └── dispatcher.py
├── supervisor.py
└── ...
```

### 1.2 单例模式分类

| 类别 | 数量 | 示例 | 问题 |
|------|------|------|------|
| **核心系统级** | ~5 | AttentionOS, Supervisor, RadarEngine | 全局唯一必需 |
| **管理器/服务** | ~15 | StockRegistry, ModeManager, DataSourceManager | 共享状态 |
| **业务组件** | ~15 | AttentionFusion, Portfolio, FocusManager | 业务状态 |
| **工具/辅助** | ~7 | AutoTuner, ThreadPool, NoiseManager | 全局配置 |

### 1.3 现有解决方案

项目已有 `SingletonRegistry` 机制 ([singleton_registry.py](file:///Users/spark/pycharmproject/deva/deva/naja/common/singleton_registry.py))：

```python
from deva.naja.common.singleton_registry import SR, register_singleton

# 注册
register_singleton('attention_integration',
    factory=lambda: NajaAttentionIntegration(),
    deps=['mode_manager', 'stock_registry'])

# 使用
integration = SR('attention_integration')
```

**已有注册** ([register.py](file:///Users/spark/pycharmproject/deva/deva/naja/register.py))：
- `register_all_singletons()` 函数已存在
- 已注册约 30 个单例
- 但未停止猴子补丁 (`apply_compatibility_patches()`)

### 1.4 核心问题

| 问题 | 描述 | 影响 |
|------|------|------|
| **隐式依赖** | `get_xxx()` 调用时不知道依赖哪些其他单例 | 初始化顺序错误难追踪 |
| **猴子补丁副作用** | `apply_compatibility_patches()` 隐藏了真实调用关系 | 调试困难 |
| **散落各处** | 单例实现在 40+ 文件中 | 难以统一管理 |
| **难以测试** | 全局状态难以 mock | 单元测试困难 |
| **初始化时机不明** | `__init__` 何时被调用不确定 | 行为不可预测 |

---

## 二、目标

### 2.1 清理目标

| 目标 | 描述 | 优先级 |
|------|------|--------|
| **停止猴子补丁** | 移除 `apply_compatibility_patches()` | P0 |
| **统一入口** | 所有单例通过 `SR()` 访问 | P0 |
| **显式依赖** | 所有单例声明其依赖 | P0 |
| **可测试性** | 支持测试时清空/替换单例 | P1 |
| **依赖图可视化** | 能生成依赖拓扑图 | P2 |

### 2.2 非目标

- 不改变单例的业务逻辑
- 不重构类的内部实现
- 不迁移到完整的 DI 框架

---

## 三、迁移计划

### Phase 1: 清理猴子补丁 (P0)

**目标**: 停止使用 `apply_compatibility_patches()`

**当前问题代码** ([singleton_registry.py#L249-344](file:///Users/spark/pycharmproject/deva/deva/naja/common/singleton_registry.py#L249-L344)):

```python
# 当前：在 bootstrap.py 中调用
apply_compatibility_patches()  # 这只是临时兼容
```

**清理步骤**:

1. 删除 `apply_compatibility_patches()` 函数
2. 从 `bootstrap.py` 中移除调用
3. 确保所有 `get_xxx()` 函数直接使用 `SR('xxx')`

**涉及文件**:
- `deva/naja/common/singleton_registry.py` - 删除函数
- `deva/naja/bootstrap.py` - 移除调用

---

### Phase 2: 完善单例注册表 (P0)

**目标**: 补充缺失的单例注册

**当前已注册**: 约 30 个
**应注册总数**: 约 50 个 (排除纯工具函数)

**缺失注册清单**:

| 单例名称 | 文件 | 建议状态 |
|----------|------|----------|
| `supervisor` | `supervisor.py` | 核心，必须注册 |
| `radar_engine` | `radar/engine.py` | 核心，必须注册 |
| `signal_stream` | `signal/stream.py` | 核心，必须注册 |
| `naja_supervisor` | `supervisor.py` | 核心，必须注册 |
| `strategy_result_store` | `strategy/result_store.py` | 业务，必须注册 |
| `output_controller` | `strategy/output_controller.py` | 业务，应注册 |
| `llm_controller` | `llm_controller/controller.py` | 业务，应注册 |
| `attribution` | `bandit/attribution.py` | 业务，应注册 |
| `optimizer` | `bandit/optimizer.py` | 业务，应注册 |
| `tuner` | `bandit/tuner.py` | 业务，应注册 |
| `portfolio_manager` | `bandit/portfolio_manager.py` | 业务，应注册 |
| `thread_pool` | `common/thread_pool.py` | 基础，应注册 |
| `recoverable` | `common/recoverable.py` | 基础，应注册 |
| `log_stream` | `log_stream.py` | 基础，应注册 |
| `scheduler_common` | `scheduler/common.py` | 业务，应注册 |

---

### Phase 3: 替换 get_xxx() 调用 (P1)

**目标**: 将所有 `get_xxx()` 调用替换为 `SR('xxx')`

**涉及 40 个文件**:

```
deva/naja/attention/
├── integration/extended.py
├── attention_os.py
├── realtime_data_fetcher.py
├── signal_executor.py
├── data_processor.py
├── trading_center.py
├── cognition_orchestrator.py
├── focus_manager.py
├── liquidity_manager.py
├── state_querier.py
├── processing/noise_manager.py
├── processing/block_noise_detector.py
├── portfolio.py
├── strategies/block_hunter.py
├── ui_components/common.py
├── ui_components/admin.py
├── ui_components/cards.py
├── ui_components/intelligence.py
├── ui_components/timeline.py
└── ...
deva/naja/bandit/
├── market_data_bus.py
├── optimizer.py
├── tuner.py
├── portfolio_manager.py
└── runner.py
deva/naja/cognition/
├── history_tracker.py
├── insight/llm_reflection.py
└── ui/ui.py
deva/naja/radar/
├── engine.py
└── global_market_scanner.py
deva/naja/strategy/
├── daily_review.py
├── result_store.py
├── output_controller.py
└── __init__.py
deva/naja/config/
└── __init__.py
deva/naja/signal/
├── stream.py
├── dispatcher.py
└── processor.py
deva/naja/supervisor.py
deva/naja/alaya/awakened_alaya.py
deva/naja/web_ui.py
deva/naja/page_help.py
deva/naja/datasource/
├── __init__.py
└── ui.py
deva/naja/knowledge/state_manager.py
deva/naja/scheduler/common.py
deva/naja/senses/prophetic_sensing.py
deva/naja/performance/lock_monitor.py
deva/naja/loop_audit/ui.py
deva/naja/dictionary/stock/stock.py
deva/naja/scripts/naja_lab_monitor.py
deva/naja/tasks/__init__.py
```

**替换规则**:

```python
# 替换前
from deva.naja.attention.integration import get_attention_integration
integration = get_attention_integration()

# 替换后
from deva.naja.register import SR
integration = SR('attention_integration')
```

---

### Phase 4: 完善依赖声明 (P0)

**目标**: 确保所有单例正确声明依赖

**依赖关系图 (待完善)**:

```
基础层 (无依赖)
├── stock_registry
├── mode_manager
├── market_time
├── thread_pool
├── noise_manager
├── block_noise_detector
└── recoverable

中间层 (依赖基础层)
├── attention_integration ──→ mode_manager, stock_registry
├── block_registry ──→ attention_integration
├── state_querier ──→ mode_manager
├── signal_executor ──→ attention_integration
├── data_processor ──→ attention_integration
├── stock_sector_map ──→ stock_registry
├── market_data_bus ──→ mode_manager
└── history_tracker ──→

应用层 (依赖中间层)
├── attention_os ──→ attention_integration
├── focus_manager ──→ attention_integration
├── conviction_validator ──→ attention_integration
├── blind_spot_investigator ──→ attention_integration
├── strategy_manager ──→ attention_integration
├── liquidity_manager ──→ attention_integration
├── attention_router ──→ attention_integration
├── cross_signal_analyzer ──→ attention_integration
├── narrative_block_linker ──→ attention_integration
├── llm_reflection_engine ──→ attention_integration
├── text_pipeline ──→ cognition_bus
└── cognition_bus ──→

系统层 (依赖应用层)
├── trading_center ──→ attention_os, attention_integration
├── attention_fusion ──→ attention_os
├── portfolio ──→
├── snapshot_manager ──→
├── market_observer ──→
├── manas_manager ──→
├── auto_tuner ──→
├── cognition_orchestrator ──→ attention_os
├── realtime_data_fetcher ──→ mode_manager, attention_integration
├── noise_filter ──→
└── strategy_manager ──→ attention_integration

顶层 (依赖系统层)
├── supervisor ──→ (多个子系统)
├── radar_engine ──→ trading_clock
├── signal_stream ──→
├── global_market_scanner ──→
├── daily_review_scheduler ──→ datasource_manager
├── naja_supervisor ──→
├── strategy_result_store ──→
├── output_controller ──→
├── llm_controller ──→
├── attribution ──→
├── optimizer ──→
├── tuner ──→
├── portfolio_manager ──→
└── scheduler_common ──→
```

---

### Phase 5: 添加测试支持 (P1)

**目标**: 支持测试时清空/替换单例

**实现**:

```python
# 在 singleton_registry.py 中添加

def clear_for_test():
    """清空所有单例（用于测试）"""
    _global_registry.clear()

def register_fake_singleton(name: str, instance: Any):
    """注册假单例（用于测试）"""
    _global_registry.register(name, lambda: instance, deps=[])
    _global_registry.get(name)  # 立即初始化

# 使用示例
def test_attention_os():
    clear_for_test()
    register_fake_singleton('attention_integration', MockIntegration())
    # ... 测试代码
```

---

### Phase 6: 移除旧的单例实现 (P2)

**目标**: 清理代码，移除冗余的单例模式

**待清理类**:

| 类名 | 文件 | 清理方式 |
|------|------|----------|
| `NajaAttentionIntegration` | `attention/integration/extended.py` | 保留但通过 SR 访问 |
| `AttentionModeManager` | `attention/integration/extended.py` | 保留但通过 SR 访问 |
| `AttentionOS` | `attention/attention_os.py` | 保留但通过 SR 访问 |
| `SignalExecutor` | `attention/signal_executor.py` | 保留但通过 SR 访问 |
| `DataProcessor` | `attention/data_processor.py` | 保留但通过 SR 访问 |
| `TradingCenter` | `attention/trading_center.py` | 保留但通过 SR 访问 |
| `MarketDataBus` | `bandit/market_data_bus.py` | 保留但通过 SR 访问 |
| `NoiseManager` | `attention/processing/noise_manager.py` | 保留但通过 SR 访问 |
| `BlockNoiseDetector` | `attention/processing/block_noise_detector.py` | 保留但通过 SR 访问 |
| `StateQuerier` | `attention/state_querier.py` | 保留但通过 SR 访问 |
| `FocusManager` | `attention/focus_manager.py` | 保留但通过 SR 访问 |
| `LiquidityManager` | `attention/liquidity_manager.py` | 保留但通过 SR 访问 |
| `CognitionOrchestrator` | `attention/cognition_orchestrator.py` | 保留但通过 SR 访问 |
| `StockInfoRegistry` | `common/stock_registry.py` | 保留但通过 SR 访问 |
| `AutoTuner` | `common/auto_tuner.py` | 保留但通过 SR 访问 |
| `ThreadPool` | `common/thread_pool.py` | 保留但通过 SR 访问 |
| `Recoverable` | `common/recoverable.py` | 保留但通过 SR 访问 |
| `RadarEngine` | `radar/engine.py` | 保留但通过 SR 访问 |
| `ResultStore` | `strategy/result_store.py` | 保留但通过 SR 访问 |
| `OutputController` | `strategy/output_controller.py` | 保留但通过 SR 访问 |
| `SignalStream` | `signal/stream.py` | 保留但通过 SR 访问 |
| `SignalDispatcher` | `signal/dispatcher.py` | 保留但通过 SR 访问 |
| `NajaSupervisor` | `supervisor.py` | 保留但通过 SR 访问 |
| `LLMController` | `llm_controller/controller.py` | 保留但通过 SR 访问 |
| `BanditAttribution` | `bandit/attribution.py` | 保留但通过 SR 访问 |
| `BanditOptimizer` | `bandit/optimizer.py` | 保留但通过 SR 访问 |
| `BanditTuner` | `bandit/tuner.py` | 保留但通过 SR 访问 |
| `PortfolioManager` | `bandit/portfolio_manager.py` | 保留但通过 SR 访问 |
| `DailyReviewScheduler` | `strategy/daily_review_scheduler.py` | 保留但通过 SR 访问 |
| `GlobalMarketScanner` | `radar/global_market_scanner.py` | 保留但通过 SR 访问 |
| `SchedulerCommon` | `scheduler/common.py` | 保留但通过 SR 访问 |
| `LogStream` | `log_stream.py` | 保留但通过 SR 访问 |
| `ManasManager` | `attention/kernel/manas_manager.py` | 保留但通过 SR 访问 |
| `AttentionHistoryTracker` | `cognition/history_tracker.py` | 保留但通过 SR 访问 |
| `LLMReflectionEngine` | `cognition/insight/llm_reflection.py` | 保留但通过 SR 访问 |
| `DataSourceManager` | `datasource/__init__.py` | 保留但通过 SR 访问 |
| `TaskManager` | `tasks/__init__.py` | 保留但通过 SR 访问 |
| `StrategyManager` | `strategy/__init__.py` | 保留但通过 SR 访问 |
| `DictionaryManager` | `dictionary/__init__.py` | 保留但通过 SR 访问 |

> **注意**: Phase 6 是长期目标。这些类的单例模式代码保留，只是不再直接调用 `get_xxx()`，而是通过 `SR()` 统一访问。

---

## 四、实施清单

### 任务 1: 删除猴子补丁 [P0]

| 文件 | 修改内容 |
|------|----------|
| `singleton_registry.py` | 删除 `apply_compatibility_patches()` 函数 |
| `bootstrap.py` | 移除 `apply_compatibility_patches()` 调用 |

### 任务 2: 补充单例注册 [P0]

| 文件 | 修改内容 |
|------|----------|
| `register.py` | 添加缺失的 `register_singleton()` 调用 |

### 任务 3: 替换调用点 [P1]

需要修改 40 个文件，将类似代码:

```python
from deva.naja.attention.integration import get_attention_integration
integration = get_attention_integration()
```

替换为:

```python
from deva.naja.register import SR
integration = SR('attention_integration')
```

### 任务 4: 完善依赖 [P0]

在 `register.py` 中补充 `deps` 参数。

### 任务 5: 添加测试工具 [P1]

在 `singleton_registry.py` 中添加:
- `clear_for_test()`
- `register_fake_singleton()`

### 任务 6: 文档更新 [P2]

- 更新 `AGENTS.md` 中的单例使用规范
- 更新 `SOUL.md` / `USER.md` (如需要)

---

## 五、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 初始化顺序错误 | 系统启动失败 | 仔细梳理依赖关系 |
| 遗漏的 `get_xxx()` 调用 | 功能异常 | 全面测试 |
| 循环依赖 | 启动死循环 | SingletonRegistry 已有检测 |
| 遗漏注册 | KeyError | 启动时验证 |

---

## 六、验收标准

1. ✅ `apply_compatibility_patches()` 已删除
2. ✅ 所有单例通过 `SR()` 访问
3. ✅ 所有单例在 `register.py` 中注册
4. ✅ 所有单例声明依赖关系
5. ✅ 测试支持 `clear_for_test()` 可用
6. ✅ 系统可正常启动

---

## 七、后续优化建议

本次整改后，系统达到"显式依赖、可追踪、可测试"的状态。后续可进一步考虑：

1. **依赖注入框架**: 如 `punq`、`deps` 等，轻量级 DI
2. **插件系统**: 基于服务定位器的延迟解析
3. **配置外部化**: 单例配置可从 YAML/JSON 加载

---

*文档生成时间: 2026-04-08*
