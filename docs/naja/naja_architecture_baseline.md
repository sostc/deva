# Naja 架构开发基准

> 本文档不是一次性重构说明，而是 Naja 后续开发的长期基准。
> 目标是让人类开发者与 AI 开发工具在同一套思路下工作，避免系统再次滑回“功能能跑、结构失控”的状态。

---

## 1. 为什么要有这份基准

Naja 不是一个单点模块，而是一个持续演化的系统，包含：

- 数据源
- 策略
- 信号
- 注意力
- 认知
- 决策
- Bandit
- 雷达
- Web UI
- 启动与运行时恢复

这类系统最容易出现的问题不是“功能做不出来”，而是：

- 新功能总能塞进去，但边界越来越乱
- 依赖关系越来越隐蔽
- 运行时装配逻辑渗透进业务逻辑
- UI、事件、算法、状态恢复互相穿透
- 每次修改都要靠全局环境才能勉强验证

所以我们需要一份稳定的开发基准，约束今后的设计方向。

---

## 2. 这轮改造的整体思路

本轮改造的核心，不是“把代码拆散”，而是把不同类型的复杂度放回它们应该在的位置。

### 2.1 原来的主要问题

原来的系统复杂度主要集中在以下几件事混在一起：

- 启动
- 模式切换
- 状态恢复
- 单例获取
- 事件订阅
- 决策编排
- UI 查询

这些东西一旦混在一起，系统会呈现出一种典型症状：

- 每个模块都像“核心”
- 每个模块都能直接拿全局对象
- 文档上分层，代码里网状耦合

### 2.2 改造的基本动作

这轮改造做了三类动作：

1. 把运行时装配收口到 `application`
2. 把高阶决策编排收口到 `decision`
3. 把 manager 共性收口到 `infra/management`

同时开始收缩 `SR()` 的使用面，让它从“业务逻辑默认依赖入口”逐渐退回“组合根/兼容层工具”。

### 2.3 这轮改造的本质

一句话概括：

> 运行时问题放到应用层，业务问题留在领域层，通用骨架放到基础设施层。

---

## 3. 当前推荐架构

推荐按照下面这套层次理解 Naja：

```text
入口 / UI / Bootstrap
    ↓
Application（装配、模式、订阅、生命周期）
    ↓
Decision / Attention / Cognition / Signal / Bandit（领域编排与核心能力）
    ↓
Infra / Adapters / Repository / Runtime（通用骨架与技术实现）
```

### 3.1 各层职责

#### 入口层

典型位置：

- `deva/naja/__main__.py`
- `deva/naja/web_ui/`
- `deva/naja/infra/lifecycle/bootstrap.py`

职责：

- 接收命令参数
- 启动系统
- 选择模式
- 装配组件

不负责：

- 深层业务决策
- 领域规则计算

#### Application 层

典型位置：

- `deva/naja/application/`
  - `container.py` - 核心组件装配和依赖注入
  - `event_registrar.py` - 集中事件订阅管理
  - `runtime_config.py` - 运行时配置
  - `runtime_modes.py` - 运行模式初始化

职责：

- 作为组合根（`AppContainer`）
- 管理启动流程
- 组织运行模式
- 集中事件订阅（`EventSubscriberRegistrar`）
- 组织 facade/query service
- 显式依赖注入

Application 层是“怎么把系统拼起来”的地方。

#### Domain / Decision 层

典型位置：

- `deva/naja/decision/`
  - `orchestrator.py` - 决策编排
  - `fusion.py` - 决策融合
- `deva/naja/attention/`
  - `os/` - 注意力操作系统
  - `kernel/` - 注意力内核
  - `values/` - 价值系统
- `deva/naja/cognition/`
  - `engine.py` - 认知引擎
  - `insight/` - 洞察系统
- `deva/naja/signal/` - 信号处理
- `deva/naja/bandit/` - 交易执行

职责：

- 表达核心业务能力
- 处理决策、推理、融合、调度、评分等领域逻辑

这层关注的是“系统如何思考和行动”。

#### Infra 层

典型位置：

- `deva/naja/infra/`
  - `lifecycle/` - 生命周期管理
  - `log/` - 日志系统
  - `management/` - 通用管理器骨架
  - `observability/` - 可观测性
  - `registry/` - 注册管理
  - `runtime/` - 运行时服务
    - `recoverable.py` - 可恢复单元基类（含执行环境注入）

职责：

- 提供运行骨架
- 提供通用管理器能力
- 提供日志、线程、注册、恢复、监控等基础设施
- 为 Task/Strategy/DataSource 的 func_code 提供统一执行环境（注入 `SR`、`NB` 等工具）

这层不定义业务目标，只提供底座能力。

---

## 4. 这套架构的优点

### 4.1 优点一：复杂度被分流了

以前的复杂度集中在少数大模块里，现在开始按类型分流：

- 运行时复杂度 -> `application`
- 决策复杂度 -> `decision`
- 通用框架复杂度 -> `infra`

这意味着以后新增功能时，不需要再把所有复杂度继续往 `TradingCenter`、`server.py`、`register.py` 里堆。

### 4.2 优点二：依赖关系更可见

以前模块一上来就 `SR('xxx')`，外表几乎没有依赖，真实依赖全藏在运行时。

现在的方向是：

- 依赖显式注入
- 装配集中在 container
- 核心模块少碰全局注册表

这会让：

- 测试更容易
- 重构更容易
- AI 工具更容易理解代码意图

### 4.3 优点三：更适合持续演化

Naja 不是“写完就封板”的项目，而是持续增加模块、策略、页面、工作流的系统。

这套架构不是追求“最纯粹”，而是追求：

- 能兼容旧系统
- 能逐步迁移
- 能让下一轮迭代更便宜

这点非常重要，因为 AI 开发工具最擅长的是在已有骨架上持续推进，而不是无限制地推倒重来。

### 4.4 优点四：更适合多 AI 协作

未来多个 AI 工具同时参与开发时，最怕的是：

- 每个工具都从不同角度“自己理解架构”
- 每个工具都在不同地方偷偷加全局依赖
- 每个工具都觉得自己是在“快速修一下”

这套基准的意义就在于：

- 给 AI 一个统一的设计边界
- 给代码评审一个统一的判断标准
- 给后续维护一个统一的收敛方向

---

## 5. 未来开发必须遵循的精髓

这部分是全文最重要的内容。

如果以后只记住几条，请记住这里。

### 5.1 精髓一：运行时装配不要渗透进业务逻辑

业务模块不要自己决定：

- 去哪里拿依赖
- 什么时候订阅事件
- 什么时候初始化别的系统

这些应该由 `application` 层负责。

判断标准：

- 如果一个模块在思考“怎么拼系统”，它不属于纯领域逻辑

### 5.2 精髓二：核心逻辑优先显式依赖

凡是核心路径：

- 决策
- 注意力
- 信号
- 认知融合
- 事件路由

优先使用：

- 构造注入
- 参数注入
- facade 注入

不要默认 `SR()`。

### 5.3 精髓三：新复杂度要放到正确层次

以后加功能时，先问一句：

“这个复杂度属于哪一层？”

常见判断方式：

- 启动、模式、订阅、恢复 -> `application`
- 决策、评分、融合、推理 -> `decision / domain`
- 线程、日志、注册、管理器骨架 -> `infra`
- 页面渲染、接口拼装 -> `web_ui`

### 5.4 精髓四：兼容层可以脏，但核心层必须越来越干净

老系统一定会有兼容需求，这是正常的。

允许脏的地方：

- `get_xxx()` 兼容函数
- `web_ui` 临时查询入口
- 启动适配层

不允许继续变脏的地方：

- `decision`
- `events` 核心分发
- `attention` 核心逻辑
- `bandit` 运行链

### 5.5 精髓五：重构要先换骨架，再换器官

Naja 不能大爆炸式重写。

正确方式是：

1. 先建立新骨架
2. 再把旧逻辑慢慢迁进去
3. 保持兼容入口
4. 一条链一条链替换

这也是为什么我们先做：

- `application`
- `decision`
- `infra/management`

而不是一开始就全量删旧代码。

---

## 6. 未来 AI 开发必须遵守的规范

这部分专门给以后接手项目的 AI 工具。

### 6.1 新功能开发前必须先判断归属层

新增任何功能前，先判断它属于：

- `application`
- `domain / decision`
- `infra`
- `web_ui`

禁止一上来直接往“大文件”里塞逻辑。

### 6.2 不要在核心模块里新增 `SR()`

默认规则：

- `decision/` 不应新增 `SR()`
- `events/` 核心逻辑不应新增 `SR()`
- `attention/` 深层逻辑不应新增 `SR()`

若确实必须使用，必须说明原因，并优先放在：

- container
- facade
- compatibility wrapper

### 6.3 事件订阅优先集中管理

新订阅逻辑不要随手写在对象 `__init__` 里。

优先方式：

- 在 `application` 层通过 `EventSubscriberRegistrar` 集中注册
- 领域对象只暴露 event handler 方法
- 由 registrar 负责订阅和管理订阅关系

示例实现：`deva/naja/application/event_registrar.py`

### 6.4 UI 不要直接深入核心对象

UI/API handler 尽量不要直接：

- `SR('xxx')`
- 直接拼复杂业务对象
- 同时调多个深层 manager

优先方式：

- 调用 facade
- 调用 query service
- 把页面/接口当成边界层

### 6.5 新增公共模式先抽骨架，再复用

如果两个以上模块出现同类模式，比如：

- manager
- query service
- event handler
- runtime mode

优先抽象公共骨架，而不是复制粘贴。

但注意：

- 抽象必须为真实重复服务
- 不要为想象中的未来过度设计

---

## 7. 日常开发的判断准则

以后无论人还是 AI，只要改代码，都建议用下面这组问题自检。

### 7.1 这个改动是不是把运行时逻辑塞进了业务逻辑？

如果是，通常方向不对。

### 7.2 这个模块是不是又开始自己去全局找依赖？

如果是，优先考虑注入。

### 7.3 这个新复杂度是不是加到了最顺手但最错误的地方？

典型坏味道：

- 往 `TradingCenter` 再塞 300 行
- 往 `server.py` 再加启动分支
- 往 `events/__init__.py` 再加启发式判断

### 7.4 这个抽象是真解决重复，还是只是换个名字包起来？

如果只是“把混乱包一层”，不算真正升级。

### 7.5 这个改动有没有让下一次修改更便宜？

这是最重要的判断标准之一。

好架构不是“这次写得优雅”，而是“下次更容易继续写对”。

---

## 8. 推荐的后续演进方向

未来优先继续沿这条线推进：

### 8.1 继续收口 `SR()`

方向：

- 核心路径减量
- UI/query 层逐步 facade 化
- 注册表退居边界层

### 8.2 把事件订阅集中到 application registrar

目标：

- 订阅动作集中
- 领域对象只处理事件，不自己注册

### 8.3 补 facade / query service

目标：

- UI 访问逻辑更稳定
- 查询链更可测试

### 8.4 逐步拆胖类

优先关注：

- `TradingCenter`
- `AttentionOS`
- 若还有类似“大而全协调器”

拆法不是横向乱切，而是按职责切：

- orchestration
- query
- action
- adapter

### 8.5 统一执行环境注入

目标：

- 所有通过 Task/Strategy/DataSource 运行的 func_code，自动获得 `SR` 和 `NB` 工具
- 无需在用户代码中重复 `from deva.naja.register import SR` 或 `from deva import NB`
- 执行环境由 `RecoverableUnit._build_execution_env` 统一构建和注入

实现位置：

- `deva/naja/infra/runtime/recoverable.py` 中的 `_build_execution_env` 方法
- 已注入：`SR`（单例访问）、`NB`（数据库访问）
- 保持注入：`pd`、`np`、`json`、`datetime`、`time` 等基础库

编写 func_code 时的推荐写法：

```python
def execute() -> dict:
    # SR 和 NB 已自动注入，无需 import
    state_mgr = SR('system_state_manager')
    state_mgr.record_active()
    return {"success": True}
```

### 8.6 系统状态模块迁移

目标：

- 系统状态管理从 `deva.naja.system_state` 迁移至 `deva.naja.state.system.system_state`
- 统一通过 SR('system_state_manager') 访问，不直接 import 模块

实现位置：

- `deva/naja/state/system/system_state.py` - SystemStateManager
- `deva/naja/state/system/wake_sync_manager.py` - WakeSyncManager
- `deva/naja/register.py` 第104行 - 单例注册入口

### 8.6 完善生命周期管理（持久化/优雅退出）

目标：

- 所有核心组件实现 `save_state()` / `persist_state()` / `shutdown()`
- 退出流程集中到 `supervisor.shutdown()` → `_stop_all_components()`
- 注册 `atexit` 兜底保障

已实现的退出调用链（见 `§9`）：

- `SignalStream.close(persist=True)`
- `InsightPool.persist()`
- `AttentionOS.persist_state()` → Kernel + StrategyDecisionMaker + FocusManager + NarrativeTracker
- `RadarEngine.save_state()`
- `CognitionEngine.shutdown()` → stop_auto_save + save_state
- `MarketHotspotIntegration.persist_state()` → HotspotLearning + StrategyLearner + HotspotSystem
- `HistoryTracker.save_state()`
- 策略/数据源/任务逐个 `stop()`

---

## 9. 生命周期与持久化规范

### 9.1 退出调用链路

系统退出时有两条路径：

1. **优雅退出**：`SIGINT/SIGTERM` → `shutdown_handler` → `supervisor.shutdown()`
2. **兜底退出**：`atexit.register(_cleanup)`

完整调用链：

```
supervisor.shutdown() (supervisor/recovery.py)
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
       │    ├→ HotspotLearning.persist()
       │    ├→ StrategyLearner.persist()
       │    └→ HotspotSystem.save_state()
       ├→ Strategy/Datasource/Task.stop()
       └→ ...
```

### 9.2 持久化方法命名约定

根据组件类型选择合适的命名：

| 类型 | 方法名 | 说明 |
|------|--------|------|
| 引擎/系统 | `save_state()` | 返回状态字典，供外部存储 |
| 学习器 | `persist()` | 直接持久化到磁盘/数据库 |
| 管理器 | `persist_state()` | 协调子组件的持久化 |
| 流/监听器 | `close(persist=True)` | 关闭时可选持久化 |
| 带后台任务 | `shutdown()` | 停止后台任务 + 立即保存 |

### 9.3 持久化实现规则

1. **每个核心组件必须实现退出持久化方法**
   - 方法可以是 `save_state()`、`persist_state()`、`shutdown()` 之一
   - `_stop_all_components()` 通过 `hasattr()` 检测并调用

2. **持久化必须带异常捕获**
   - 每个持久化调用必须 `try/except`，避免一个组件失败影响其他组件
   - 失败时记录 `log.warning`，不抛异常

3. **有后台任务的组件必须先停止再保存**
   - 例如 `CognitionEngine.shutdown()` 先 `stop_auto_save()` 再 `save_state()`
   - 避免保存过程中状态被修改

4. **持久化数据集中存储在 NB 数据库**
   - 表名规范：`naja_<component>_state`
   - 例如：`naja_attention_kernel_state`、`naja_hotspot_state`

### 9.4 新增组件的持久化要求

新增核心组件时，必须同时实现：

```python
class MyComponent:
    def save_state(self) -> Dict[str, Any]:
        """保存状态用于持久化"""
        return {
            'key_field': self._key_field,
            'cache': self._cache,
            # ...
        }
    
    def load_state(self) -> bool:
        """从持久化存储加载状态"""
        # ...
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

---

## 10. 一句话基准

以后开发 Naja，请始终遵循这句话：

> 让运行时装配留在应用层，让核心能力留在领域层，让通用骨架留在基础设施层；不要让全局依赖、启动逻辑、事件注册和 UI 查询继续侵入核心业务。

---

## 10.1 唤醒补作业开发指南

### 10.1.1 什么是唤醒补作业

系统从休眠中唤醒（启动或心跳检测上次活跃时间超过阈值）时，需要"补作业"——补齐休眠期间缺失的数据和状态，例如：
- 获取错过的新闻
- 同步持仓价格
- 执行盘后复盘
- 生成 AI 日报

### 10.1.2 架构层次

```
AppContainer._perform_wake_sync()     ← 应用层入口
    └→ WakeOrchestrator.wake()         ← 统一编排（application/wake_orchestrator.py）
       ├→ RecoveryManager.restore_all() ← 组件状态恢复（infra）
       └→ WakeSyncManager.perform_wake_sync() ← 外部数据补齐（state/system）
          └→ [WakeSyncable 组件列表]    ← 具体同步逻辑（state/system/wake_sync_handlers.py）
```

### 10.1.3 如何新增一个补作业任务

**第 1 步：创建同步组件类**

在 `deva/naja/state/system/wake_sync_handlers.py` 中新增一个类，实现 `WakeSyncable` 协议：

```python
class MyFeatureWakeSync:
    """我的功能同步器"""

    @property
    def name(self) -> str:
        return "My_Feature"  # 唯一标识，用于去重

    @property
    def description(self) -> str:
        return "我的功能描述"

    @property
    def priority(self) -> int:
        return 2  # 数字越小优先级越高，现有范围 1-5

    def should_wake_sync(self, last_active: datetime) -> bool:
        """判断是否需要同步"""
        # 根据业务逻辑判断，例如：
        # - 检查上次执行时间
        # - 检查是否有未处理的数据
        # - 检查当前时段是否适合执行
        return True  # 或 False

    def get_wake_sync_range(self, last_active: datetime, max_hours: int = 24) -> Tuple[datetime, datetime]:
        """获取需要同步的时间范围"""
        now = datetime.now()
        start = now - timedelta(hours=max_hours)
        return start, now

    def execute_wake_sync(self, start: datetime, end: datetime) -> Dict[str, Any]:
        """执行同步"""
        try:
            # 实际的业务逻辑：拉取数据、处理、发布等
            # ...
            return {
                "success": True,
                "message": "同步成功",
                "details": {"count": 0}
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"同步失败: {e}",
                "details": {}
            }
```

**第 2 步：注册组件**

在 `deva/naja/register.py` 的 `_create_wake_sync_manager()` 函数中注册：

```python
def _create_wake_sync_manager():
    from .state.system.wake_sync_manager import WakeSyncManager
    from .state.system.wake_sync_handlers import (
        AIDailyReportWakeSync,
        NewsFetcherWakeSync,
        GlobalMarketScannerWakeSync,
        DailyReviewWakeSync,
        PortfolioPriceWakeSync,
        MyFeatureWakeSync,  # 新增
    )
    mgr = WakeSyncManager()
    mgr.register(PortfolioPriceWakeSync())
    mgr.register(NewsFetcherWakeSync())
    mgr.register(GlobalMarketScannerWakeSync())
    mgr.register(DailyReviewWakeSync())
    mgr.register(AIDailyReportWakeSync())
    mgr.register(MyFeatureWakeSync())  # 新增
    return mgr
```

**第 3 步（可选）：调整轻量同步范围**

如果你的组件属于核心数据（短时间休眠后也需要同步），需要在 `WakeOrchestrator._light_sync()` 中加入：

```python
def _light_sync(self, last_active: datetime) -> Dict[str, Any]:
    core_names = ["Portfolio_Price", "News_Fetcher", "My_Feature"]  # 加入
```

### 10.1.4 去重机制

系统自动提供两层去重：
1. **时间窗口去重**：同一组件 5 分钟内不重复执行（`DEDUP_INTERVAL_SECONDS`）
2. **组件自主判断**：`should_wake_sync()` 由组件自行决定是否需要执行

### 10.1.5 持久化

同步状态自动持久化到 `~/.naja/wake_sync_state.json`，包含：
- 每个组件上次成功同步的时间戳
- 最后一次唤醒同步时间

重启后自动加载，确保去重逻辑跨进程有效。

---

## 11. 给未来 AI 的执行指令

如果你是后续接手本项目的 AI 开发工具，请默认遵守以下规则：

1. 先读本文档，再决定改动位置
2. 新逻辑先判断属于哪一层
3. 默认不要在核心模块中新增 `SR()`
4. 默认不要把订阅逻辑塞进业务对象 `__init__`
5. 默认不要把 UI 当成业务协调层
6. 遇到重复模式，优先抽稳定骨架
7. 优先做"让后续更容易继续改对"的改动
8. 新增核心组件必须实现持久化方法（`save_state`/`persist_state`/`shutdown`）
9. 在 `_stop_all_components()` 中注册新组件的退出调用

如果你的方案与本文档冲突，优先重新审视方案，而不是直接绕过基准。

