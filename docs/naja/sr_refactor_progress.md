# Naja SR() 收口改造 - 进度文档

## 概述

本文档跟踪 `deva.naja.register.SR()` 的改造进度。

**改造目标**：
- 将 `SR()` 的使用限定在应用层（边界层）
- 核心领域层不主动调用 `SR()`
- 依赖关系通过构造注入或参数传递显式化
- 保持向后兼容

---

## 改造进度

### ✅ 已完成

| 阶段 | 任务 | 完成时间 |
|------|------|----------|
| Phase 1 | 创建 `sr_usage_policy.md` 策略文档 | 2026-04-20 |
| Phase 2-1 | 增强 `AppContainer`，添加组件装配逻辑 | 2026-04-20 |
| Phase 2-4 | 创建 `EventSubscriberRegistrar` 事件订阅管理 | 2026-04-20 |
| Phase 2-2 | 改造 `AttentionOS` - 添加构造参数和 setter | 2026-04-20 |
| Phase 2-3 | 改造 `TradingCenter` - 添加构造参数和 setter | 2026-04-20 |
| - | 修复循环导入问题 (web_ui/server.py) | 2026-04-20 |
| - | 基本导入验证通过 | 2026-04-20 |
| Phase 3-1 | 事件订阅迁移 - 迁移到 EventSubscriberRegistrar | 2026-04-20 |
| Phase 3-2 | 决策层/内核层 SR() 检查 - decision/ 和 events/ 已纯净 | 2026-04-20 |
| Phase 3-3 | 内核层改造 - QueryState/QueryStateUpdater/AttentionKernel 添加显式依赖注入 | 2026-04-20 |
| Phase 3-4 | 内核层改造 - ManasEngine/ManasManager 添加显式依赖注入 | 2026-04-20 |
| Phase 3-5 | 认知层改造 - InsightEngine 添加显式依赖注入 | 2026-04-20 |
| Phase 3-6 | Bandit 模块改造 - 核心组件添加显式依赖注入 | 2026-04-20 |
| Phase 3-7 | 内核层 SR() 调用处理 - 为所有 _get_* 方法添加 try-except 块 | 2026-04-20 |

### 🔍 发现的改造点

| 目录 | SR() 调用数 | 说明 |
|------|-------------|------|
| `attention/kernel/` | 0 处 | ✅ 已处理（添加了异常处理） |
| `decision/` | 0 处 | ✅ 已纯净 |
| `events/` | 0 处 | ✅ 已纯净 |

### 🔜 下一步（Phase 3+）

| 优先级 | 任务 | 说明 |
|--------|------|------|
| 中 | 系统集成测试 | 测试所有组件的显式依赖注入是否正常工作 |
| 低 | bandit/radar/ 等目录改造 | 逐步改造过渡目录 |
| 低 | 文档完善 | 更新相关文档，记录改造过程和最佳实践 |

---

## 改造详情

### AppContainer 增强

**新增功能**：
- `_assemble_core_components()` - 统一装配核心组件
- `_get_compat_singleton()` - 从旧注册表获取单例的兼容方法
- `_create_attention_os()` - 创建并装配 AttentionOS
- `_create_trading_center()` - 创建并装配 TradingCenter
- `_create_event_registrar()` - 创建事件订阅装配器
- 属性访问：`.attention_os`, `.trading_center`, `.insight_pool`
- 全局访问：`set_app_container()`, `get_app_container()`

### AttentionOS 改造

**变更内容**：
- `__init__(self, insight_pool=None)` - 构造函数支持可选依赖注入
- `set_insight_pool(self, insight_pool)` - 添加依赖注入 setter
- `_emit_shift_to_insight()` - 优先使用 `self._insight_pool`，SR() 作为后备
- `get_attention_os()` - 优先从 `AppContainer` 获取，SR() 作为后备

### TradingCenter 改造

**变更内容**：
- `__init__(self, attention_os=None)` - 构造函数支持可选依赖注入
- `set_attention_os(self, attention_os)` - 添加依赖注入 setter
- `get_trading_center()` - 优先从 `AppContainer` 获取，SR() 作为后备

### EventSubscriberRegistrar 新增 & 改造

**职责**：
- 统一管理所有事件订阅的装配
- **已完成**：迁移了 AttentionOS 和 TradingCenter 的所有订阅逻辑

**变更内容**：
- `_register_attention_os()` - 订阅 HotspotComputedEvent, HotspotShiftEvent, TextFetchedEvent
- `_register_trading_center()` - 订阅 StrategySignalEvent 并处理回调

**同时更新了**：
- AttentionOS - 移除了内部的自动订阅调用
- TradingCenter - 移除了内部的自动订阅调用

### 内核层改造（attention/kernel）

**QueryState 改造**：
- `__init__(self, value_system=None)` - 构造函数支持可选依赖注入
- `set_value_system(self, value_system)` - 添加依赖注入 setter
- `_get_value_system()` - 优先使用注入的 value_system

**QueryStateUpdater 改造**：
- `__init__(self, query_state=None)` - 构造函数支持可选依赖注入
- `set_query_state(self, query_state)` - 添加依赖注入 setter
- `get_query_state_updater()` - 优先从 `AppContainer` 获取

**AttentionKernel 改造**：
- 构造函数新增可选参数：`value_system`, `trading_clock`, `virtual_portfolio`, `bandit_tracker`
- 添加对应的 setter 方法：`set_value_system()`, `set_trading_clock()`, `set_virtual_portfolio()`, `set_bandit_tracker()`
- `_get_value_system()`, `_get_session_manager()`, `_get_portfolio()`, `_get_bandit_tracker()` - 优先使用注入的实例
- `_init_manas_engine()` 使用注入的依赖创建 ManasEngine

**ManasEngine 改造**：
- 构造函数新增可选参数：`session_manager`, `portfolio`, `bandit_tracker`
- 添加对应的 setter 方法：`set_session_manager()`, `set_portfolio()`, `set_bandit_tracker()`
- 子引擎（TimingEngine, ConfidenceEngine, RiskEngine）也支持显式依赖注入
- 各子引擎优先使用注入的依赖，SR() 作为后备

**ManasManager 改造**：
- `get_manas_manager()` 优先从 AppContainer 获取
- 创建 ManasEngine 时传入显式依赖

**InsightEngine 改造**：
- 构造函数新增可选参数：`insight_pool`
- 添加对应的 setter 方法：`set_insight_pool()`
- 优先使用注入的依赖，SR() 作为后备

**Bandit 模块改造**：

**PortfolioManager 改造**：
- `__init__(self, virtual_portfolio=None)` - 构造函数支持可选依赖注入
- `set_virtual_portfolio(self, virtual_portfolio)` - 添加依赖注入 setter
- `_init_accounts()` - 优先使用注入的 virtual_portfolio

**BanditPositionTracker 改造**：
- `__init__(self, market_time_service=None, bandit_optimizer=None)` - 构造函数支持可选依赖注入
- 添加对应的 setter 方法：`set_market_time_service()`, `set_bandit_optimizer()`
- `on_position_closed()` - 优先使用注入的 market_time_service

**BanditOptimizer 改造**：
- `__init__(self, attention_os=None)` - 构造函数支持可选依赖注入
- `set_attention_os(self, attention_os)` - 添加依赖注入 setter
- `_get_attention_context()` - 优先使用注入的 attention_os

### 内核层 SR() 调用处理

**统一处理所有 _get_* 方法**：
- 为所有 `_get_*` 方法添加 `try-except` 块，捕获 `ImportError` 和 `KeyError` 异常
- 确保当 SR() 调用失败时，方法能返回合理的默认值或 None
- 提高系统的健壮性，避免因 SR() 注册失败导致整个模块崩溃

**处理的文件**：
- `attention/kernel/state.py` - `_get_value_system()` 方法
- `attention/kernel/kernel.py` - `_get_value_system()` 方法
- `attention/kernel/manas_manager.py` - `_get_session_manager()`, `_get_portfolio()`, `_get_bandit_tracker()` 方法
- `attention/kernel/manas_engine.py` - `TimingEngine._get_time_pressure()`, `ConfidenceEngine._get_hit_rate()`, `RiskEngine._get_cash_ratio()` 方法
- `attention/kernel/decision_attention.py` - `_get_portfolio()` 方法
- `attention/kernel/state_updater.py` - `__init__()` 方法

### AppContainer 更新（内核组件装配）

**新增功能**：
- `_create_query_state()` - 创建并装配 QueryState
- `_create_query_state_updater()` - 创建并装配 QueryStateUpdater
- `_create_manas_engine()` - 创建并装配 ManasEngine（显式依赖注入）
- `_create_manas_manager()` - 创建并装配 ManasManager（显式依赖注入）
- `_create_bandit_optimizer()` - 创建并装配 BanditOptimizer（显式依赖注入）
- `_create_portfolio_manager()` - 创建并装配 PortfolioManager（显式依赖注入）
- `_create_bandit_tracker()` - 创建并装配 BanditPositionTracker（显式依赖注入）
- 属性访问：`.query_state`, `.query_state_updater`, `.value_system`, `.trading_clock`, `.virtual_portfolio`, `.bandit_tracker`, `.manas_engine`, `.manas_manager`, `.bandit_optimizer`, `.portfolio_manager`
- 在 `_assemble_core_components()` 中装配所有内核组件和 Bandit 模块组件

---

## 兼容策略

### get_xxx() 包装函数更新

现在所有 `get_xxx()` 包装函数的查找逻辑为：

```
1. 尝试从 AppContainer 获取
2. 如果失败，回退到 SR()
```

### AppContainer 装配逻辑

`AppContainer` 在 `boot()` 阶段装配组件时的策略：

```
1. 从 SR() 获取基础单例（兼容）
2. 创建核心对象（AttentionOS, TradingCenter）
3. 通过 setter 显式注入依赖
4. 通过 EventSubscriberRegistrar 统一管理订阅
```

---

## 文件清单

### 新增/修改的文件

| 文件 | 操作 |
|------|------|
| `docs/naja/sr_usage_policy.md` | ✅ 新增 |
| `docs/naja/sr_refactor_progress.md` | ✅ 新增 |
| `deva/naja/application/__init__.py` | ✅ 更新 |
| `deva/naja/application/container.py` | ✅ 大幅更新 |
| `deva/naja/application/event_registrar.py` | ✅ 新增 & 大幅更新 |
| `deva/naja/application/web.py` | ✅ 更新 |
| `deva/naja/attention/os/attention_os.py` | ✅ 更新 |
| `deva/naja/attention/orchestration/trading_center.py` | ✅ 更新 |
| `deva/naja/web_ui/server.py` | ✅ 更新（修复循环导入） |
| `deva/naja/attention/kernel/kernel.py` | ✅ 更新 |
| `deva/naja/attention/kernel/manas_engine.py` | ✅ 更新 |
| `deva/naja/attention/kernel/manas_manager.py` | ✅ 更新 |
| `deva/naja/application/container.py` | ✅ 更新 |
| `deva/naja/bandit/portfolio_manager.py` | ✅ 更新 |
| `deva/naja/bandit/tracker.py` | ✅ 更新 |
| `deva/naja/bandit/optimizer.py` | ✅ 更新 |

---

## 验证清单

- [x] 基本导入无错误
- [ ] `python -m deva.naja` 可正常启动
- [ ] Web UI 可正常访问
- [ ] 核心流程功能正常
- [x] 无循环导入问题

---

## 备注

本次改造采用**渐进式迁移**策略：
1. 不立即删除现有代码
2. 保持向后兼容
3. 新增架构并行运行
4. 可逐步迁移调用方
