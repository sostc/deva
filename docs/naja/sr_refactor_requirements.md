# Naja `SR()` 收口改造需求文档

## 1. 背景

Naja 当前大量使用 `deva.naja.register.SR()` 作为全局服务定位器。

这带来了几个问题：

- 依赖关系隐藏，模块表面上无参数，实际在运行时偷偷依赖多个全局单例
- 核心领域逻辑与运行时装配强耦合，难以拆分 `application / domain / infra`
- 测试困难，很多模块只能靠全局环境启动后才能工作
- 迁移困难，模块无法轻易复用、替换、裁剪
- 循环依赖和初始化顺序问题被推迟到运行时才暴露

当前仓库已经完成了第一轮架构整理：

- 新增 `deva/naja/application/` 作为运行时组合根
- 新增 `deva/naja/decision/` 承接决策编排
- 新增 `deva/naja/infra/management/` 承接 manager 公共骨架

下一阶段需要继续推进：把 `SR()` 从“全局通用依赖获取方式”收口成“组合根 / 兼容层 / UI 层可用的受限工具”。

---

## 2. 目标

本需求的核心目标不是“删除所有 `SR()`”，而是：

1. 让核心路径不再依赖 `SR()`
2. 让 `SR()` 只保留在少数边界层
3. 让依赖关系显式化，优先改成构造注入或参数注入
4. 在不打爆现有系统的前提下，分阶段迁移

目标状态：

- `application` 层负责装配对象
- `domain / decision / orchestration` 核心逻辑不主动调用 `SR()`
- `web_ui / compatibility shim / legacy bootstrap` 可以暂时继续调用 `SR()`
- 单例注册表继续保留，但使用面明显缩小

---

## 3. 非目标

本次改造不要求：

- 一次性删除 `register.py`
- 一次性消灭全部单例
- 一次性重写整个事件系统
- 一次性改掉所有 UI/API handler
- 重构策略逻辑本身或交易算法本身

这是一轮“依赖边界治理”，不是全面重写。

---

## 4. 改造原则

### 4.1 总原则

- 兼容优先，逐步迁移
- 先核心，后外围
- 先新增显式依赖，再删除 `SR()`
- 优先处理高频调用、深层领域逻辑、运行时关键路径

### 4.2 分层原则

允许使用 `SR()` 的层：

- `application/`
- `web_ui/`
- `__main__.py`
- `bootstrap`
- 明确标注为兼容层的 `get_xxx()` 包装函数

应逐步禁用 `SR()` 的层：

- `decision/`
- `attention/os/`
- `attention/orchestration/`
- `cognition/analysis/`
- `events/` 的核心分发逻辑
- `bandit/` 的核心运行链

### 4.3 设计原则

- 优先构造注入：`__init__(dep_a, dep_b, ...)`
- 次选 setter 注入：用于历史类过大、难以一次改造时
- 再次选 method 参数注入：用于调用链短、依赖只在单次调用中使用
- `get_xxx()` 可以保留，但内部应逐渐从 `SR()` 包装迁到 container 提供

---

## 5. 当前问题概览

当前仓库中 `SR()` 的典型问题分布：

### 5.1 核心路径中的隐式依赖

例如：

- `attention/kernel/*`
- `attention/os/*`
- `attention/orchestration/*`
- `bandit/*`
- `signal/*`
- `events/*`

这些模块一旦直接 `SR('xxx')`，就会让领域逻辑反向依赖运行时注册表。

### 5.2 事件处理链中的隐藏依赖

很多订阅者 / 发布者内部自行 `SR()` 取对象，导致：

- 无法从事件入口看出依赖
- 无法局部测试事件处理器
- 事件链调试困难

### 5.3 UI/API 与领域对象直接耦合

这块短期允许保留，但应逐步改成：

- UI -> app facade / query service
- query service -> injected dependency

---

## 6. 改造范围

本需求分三批实施。

### 第一批：核心路径收口

目标：把最关键的领域执行链从 `SR()` 中拉出来。

优先范围：

- `deva/naja/decision/`
- `deva/naja/attention/orchestration/trading_center.py`
- `deva/naja/attention/os/attention_os.py`
- `deva/naja/attention/kernel/*`
- `deva/naja/events/*`

### 第二批：运行链与执行链收口

目标：让信号、bandit、risk 这几条链减少全局查找。

优先范围：

- `deva/naja/signal/*`
- `deva/naja/bandit/*`
- `deva/naja/risk/*`
- `deva/naja/radar/*` 中直接参与决策 / 发布事件的部分

### 第三批：查询链与 UI 边界整理

目标：让 UI 通过 facade/query service 访问，而不是直接 `SR()`。

优先范围：

- `deva/naja/web_ui/*`
- `deva/naja/home/ui/*`
- `deva/naja/*/ui/*`

---

## 7. 目标架构

### 7.1 推荐依赖方向

```text
__main__ / web_ui / bootstrap
        ↓
application container / app services
        ↓
decision / attention / cognition / signal / bandit
        ↓
infra / adapters / repositories
```

规则：

- 只有最上层装配对象时允许触碰 `SR()`
- 中间层只能接收依赖，不能自己去全局找依赖
- 底层基础设施可以被注入，但不能反向依赖 container

### 7.2 目标对象模型

推荐新增或继续扩展以下对象：

- `AppContainer`
- `DecisionOrchestrator`
- `EventPublisher`
- `EventSubscriberRegistrar`
- `QueryServices`
- `AppServicesFacade`

目标不是全部新建复杂框架，而是让依赖承载位置更清楚。

---

## 8. 详细需求

### 8.1 需求 A：为 `SR()` 使用建立分层约束

要求：

1. 统计全仓库 `SR()` 使用点
2. 按目录分为三类：
   - Allowed
   - Transitional
   - Forbidden
3. 新增一份可机读或半机读的约束清单，至少文档化

建议产物：

- `docs/naja/sr_usage_policy.md`
- 或 `deva/naja/docs/sr_usage_policy.md`

最低要求：

- 明确哪些目录禁止新增 `SR()`
- 明确哪些文件属于兼容层

### 8.2 需求 B：核心模块改为显式依赖

针对核心模块，要求逐步从：

```python
dep = SR("xxx")
```

改为：

```python
class SomeService:
    def __init__(self, dep):
        self.dep = dep
```

重点对象：

- `TradingCenter`
- `DecisionOrchestrator`
- `AttentionOS`
- `attention/kernel` 中直接使用 `SR()` 的对象
- `events` 中的发布与订阅协调对象

要求：

- 构造函数参数可以先设为可选，保证兼容
- 若兼容需要，可保留 fallback，但 fallback 必须集中在边界层，不能继续深藏在领域方法内部

### 8.3 需求 C：把事件依赖装配移到应用层

当前很多模块内部自行订阅事件。

目标：

- 订阅动作集中到 `application` 层或专门的 registrar
- 领域对象只暴露 handler，不自己决定何时订阅

要求：

1. 新增类似 `EventSubscriberRegistrar` 的装配对象
2. 由 `AppContainer` 或 `bootstrap` 调用 registrar
3. `TradingCenter`、`AttentionOS` 等不再在 `__init__` 中直接订阅总线

允许的过渡态：

- 可以先保留旧订阅逻辑
- 但要提供新的 registrar 路径，并逐步切换

### 8.4 需求 D：减少查询类代码中的 `SR()`

对只读查询接口，要求增加显式 query service/facade。

例如：

- `AttentionContextQueryService`
- `SystemStatusQueryService`
- `BanditStatsQueryService`

目标：

- UI/API handler 不再自己拼依赖
- handler 只调用 facade/service

### 8.5 需求 E：保留兼容包装，但标注淘汰方向

允许保留：

- `get_trading_center()`
- `get_strategy_manager()`
- `get_datasource_manager()`

但要求：

- 在文档中标明这些是 compatibility access point
- 新代码不要继续在核心模块里到处调用这些包装器

---

## 9. 实施步骤

### Phase 1：盘点与标注

输出：

- `SR()` 使用清单
- 目录级使用策略
- 核心路径优先级排序

验收：

- 能回答“哪些地方先改，哪些地方暂缓”

### Phase 2：核心决策链迁移

目标：

- `decision/` 不直接使用 `SR()`
- `TradingCenter` 构造时通过 container 注入依赖
- `AttentionOS` 中高频依赖尽量改为注入

验收：

- 核心决策调用链中 `SR()` 显著减少

### Phase 3：事件订阅迁移

目标：

- 事件订阅集中到 application registrar
- 领域对象提供 handler，不自己注册

验收：

- 至少 `TradingCenter` 和 `AttentionOS` 订阅链迁移完成

### Phase 4：查询/UI 收口

目标：

- 新增 facade/query service
- UI/API handler 通过 query service 获取数据

验收：

- `web_ui` 中新增代码不再直接 `SR()`

---

## 10. 实现要求

### 10.1 编码要求

- 不允许为了消灭 `SR()` 而引入更隐蔽的全局状态
- 不允许用模块级懒加载变量替代 `SR()`，只是换名字不算完成
- 优先小步提交，单次变更保持可验证
- 每改一条链，要补最小测试或至少语法校验

### 10.2 兼容要求

- 保留现有 `get_xxx()` 入口
- 保留现有 `register.py`
- 不要求一次性改动所有调用方
- 每次迁移后系统应仍可启动

### 10.3 文档要求

每完成一个阶段，需要更新：

- 本文档的进度状态
- 或单独的 `docs/naja/sr_refactor_progress.md`

---

## 11. 验收标准

### 11.1 功能验收

- 现有主入口仍可工作
- `python -m deva.naja` 启动链保持兼容
- Web UI 路由不因依赖迁移而失效
- 核心决策流程功能不回退

### 11.2 架构验收

满足以下至少 4 条：

1. `decision/` 目录中不再新增 `SR()`
2. `events/` 核心路由与发布器不再依赖启发式全局查找
3. `TradingCenter` 不再在深层方法里主动 `SR()`
4. 至少一个事件订阅链迁移到 application registrar
5. 至少一个 UI 查询链迁移到 query service/facade
6. 文档中明确列出 `SR()` 的 allowed / transitional / forbidden 边界

### 11.3 工程验收

- 改动文件可通过 `py_compile`
- 新增测试至少覆盖：
  - 一个事件路由场景
  - 一个显式注入后的决策/查询场景

---

## 12. 风险与注意事项

### 12.1 主要风险

- 循环依赖从运行时转移到导入时
- 某些旧模块默认依赖单例语义，注入后出现多实例行为差异
- UI/API 调用链较长，改一层容易漏一层

### 12.2 风险控制

- 每次只迁一条链
- 优先引入可选构造参数，再逐渐把默认 fallback 删除
- 对核心对象增加最小 smoke test
- 遇到强耦合模块，先做 facade，不要硬拆到底

---

## 13. 建议交付物

实施该需求的 AI 编程工具，最终至少应提交：

1. 代码改造
2. `SR()` 使用策略文档
3. 迁移进度文档
4. 最小测试
5. 变更总结

建议输出格式：

- “已迁移模块”
- “仍保留 `SR()` 的兼容层”
- “下一阶段建议”

---

## 14. 一句话任务定义

把 Naja 的 `SR()` 从“核心业务默认依赖获取方式”，改造成“仅在组合根、兼容层、UI 边界有限使用的运行时装配工具”，并在不破坏现有启动链的前提下分阶段迁移核心模块到显式依赖注入。

