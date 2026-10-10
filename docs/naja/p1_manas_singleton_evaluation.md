# P1 评估：ManasManager 单例分裂与事件订阅归属

> 目标：review_core_async_and_manas.md §P1 第 8、9 项。
> 性质：**评估 + 方案**，尚未改代码。因为修复会改变运行时行为（kernel 是否启用末那识），
> 按 AGENTS.md「先评估、再执行」先出报告。

---

## 1. 现状：三处 ManasManager / ManasEngine 定义点

| # | 位置 | 是否真被实例化 | kernel | 是否 enable | 实际持有的 Engine |
|---|------|----------------|--------|-------------|-------------------|
| A | `register.py:195-207`（`SR('manas_manager')`） | ❌ **从未实例化** | attention_os 的 kernel | ✅ `set_enabled(True)` | 无（死注册） |
| B | `container.py:856-884`（`container.manas_manager`） | ✅ 启动时创建 | ❌ `kernel=None` | ❌ 从不 enable | `None`（未 enable 时不建引擎） |
| C | UI 懒创建 | ✅ 首次调用接口时 | — | ✅ 由 UI 补 enable | B 自建的**新** ManasEngine |

### 1.1 关键发现：A 是死注册

`register_singleton(name, factory, ...)` 是**惰性**的（只有 `SR(name)` 被调用才执行 factory）。
全仓检索 `SR('manas_manager')` 与 `get_manas_manager`：

- `SR('manas_manager')` —— **零调用**
- `get_manas_manager()` —— 返回的是 `container.manas_manager`（即 B）

所以 A 的 factory 从未执行，**kernel 永远不会被 `set_manas_enabled(True)`**。

> **更正（执行阶段补记）**：上面只证明了"没人调用"，还有更硬的证据。
> 容器在 `_register_container_components_as_singletons()` 里用
> `"manas_manager": self._manas_manager` **覆盖注册**了同一个名字
> （`container.py:172`；未初始化时注册为 `getattr(container, name)` 懒工厂）。
> 顺序上 `register_all_singletons()`（第 103 行）先跑，容器覆盖（第 111 行）后跑，
> **后者生效**。所以即便将来有人调用 `SR('manas_manager')`，拿到的也是 B。
> → A 是确定性死代码，不是"待启用的备用路径"，已直接删除。
> → 顺带说明：评估 §2 方案 1 提出的"让 factory 委托给 container"已无必要，
>   容器自身的覆盖机制天然保证了 A/B 同一实例。

### 1.2 连带的实际后果

`AttentionKernel.process()` 走末那识分支的条件是：

```python
# kernel.py:315
if self._enable_manas and self._manas_engine is not None:
    return self._process_with_manas(Q, raw_events)
```

而 `self._enable_manas` 只有在构造参数 `enable_manas=True` 或
`kernel.set_manas_enabled(True)` 时才为真——后者**只由 ManasManager.set_enabled 在
kernel 非 None 时触发**，而唯一会注入 kernel 的 manager（A）从不实例化。

→ **kernel 的末那识决策通路实际是关闭的**。
→ 当前真正在跑的末那识计算，是 UI 首次调用 `/api/manas/state` 时由 B 懒建出来的
   Engine C，且**只服务于 UI 展示**，不参与 kernel 的注意力打分。

> **更正（方案 2 执行时补记）：上面这段结论只对 `AttentionKernel` 成立，而该类
> 从未被实例化**（全仓唯一出现处是 `decision_attention.py:44` 的 docstring 示例）。
> 真正在用的 `OSAttentionKernel` 是**无条件**计算末那识的：
> `os_kernel.py:194` 直接 `self.manas_engine.compute(...)`，前面没有任何
> `_enable_manas` 门闩。所以「kernel 末那识通路关闭」这个判断是错的，
> 内核其实一直在跑末那识。
>
> 真正的病灶不是"没启用"，而是**状态分裂**：内核用自己那份引擎打分，
> UI / manager 读的是另一份引擎，`_supply_chain_state` 与 `_recent_pnl`
> 互不可见。方案 2 的价值也从"打开一条未生效通路"降级为"合并两个引擎"，
> 行为风险随之大幅降低。

### 1.3 Engine C 的时序隐患

Engine C 在 `__init__` 里订阅事件总线（`manas_engine.py:1027`），但它是**延迟到用户
首次打开 UI 才创建**的。此前流过的 BLOCK_NARRATIVE_UPDATE / RESONANCE_DETECTED 事件
全部错过，`_supply_chain_state`（叙事风险、共振分数、AI 算力趋势）停留在默认值，
直到下一个事件到来才被刷新。

### 1.4 重复订阅

`_subscribe_to_event_bus()` 用**固定字符串** `"ManasEngine"` 作为订阅者名
（`manas_engine.py:1126`）。若将来存在多个实例，`cognitive_bus` 的同名 subscriber
列表会 append 多条 → 同一事件被处理多次。当前只有 C 一个实例，问题尚未显现，
但一旦按 1.1 修复（kernel 也建引擎）就会立刻触发。

### 1.5 依赖三通道（与 §2.5 呼应）

B 传入的是 `trading_clock / virtual_portfolio / bandit_tracker`，而
`ManasEngine.compute()` 每次调用时又由 manager 的 getter 再传一遍，
`ManasEngine` 自身构造参数还有第三份。三处谁优先不明确。

---

## 2. 建议方案（按风险从低到高）

### 方案 1（低风险，纯结构收敛）—— 推荐先做

不改运行时行为，只消灭分裂：

1. `register.py` 的 `manas_manager` factory 改为返回 `container.manas_manager`，
   使 `SR('manas_manager')` 与 `container.manas_manager` **指向同一实例**（A 与 B 合并）。
2. `container._create_manas_manager()` 保留 `kernel=None` 现状（不改行为），
   但补注释说明「kernel 末那识默认关闭，启用需显式调用」。
3. `get_manas_manager()` 语义保持不变。

收益：消除"两套 manager"的概念分裂；代价为零行为变化。

### 方案 2（中风险，行为修复）

在方案 1 基础上，让 container 的 manager 注入 kernel 并启动时 enable：

```python
manas_manager = ManasManager(
    kernel=self._attention_os.get_kernel(),   # 与 register.py 原本意图一致
    trading_clock=..., virtual_portfolio=..., bandit_tracker=...,
)
manas_manager.set_enabled(True)
```

→ kernel 的 `_enable_manas=True` 且 `_manas_engine` 指向同一个 engine，
**全进程只剩一个 ManasEngine**，UI 与 kernel 共享同一份 `_supply_chain_state`
与 `_recent_pnl`。

⚠️ 行为变化：kernel 的注意力打分将开始走 `_process_with_manas` 分支，
alpha/注意力权重会变。**需要你确认这是否是预期**——从 `register.py` 的注释
「manas_manager: 注入 attention_os 的 kernel」看，这应该是原设计意图，
但当前线上实际是关闭的，启用等于打开一条此前未生效的决策通路。

### 方案 3（中风险，架构对齐 §6.3）

把事件订阅从 `ManasEngine.__init__` 移出，改由 application 层显式注册：

- `ManasEngine` 新增 `attach_event_bus(bus=None)` / `detach_event_bus()`；
- `__init__` 不再订阅，构造即纯净（可测试）；
- 订阅者名改为唯一（如 `f"ManasEngine#{id(self)}"` 或由注册方指定），避免同名重复；
- 由 composition root 在 engine 创建后调用一次。

⚠️ 风险：任何"创建后忘记 attach"的路径都会导致 `_supply_chain_state` 不再更新，
静默退化。需要把 attach 调用放在唯一创建点旁边，并加日志。

---

## 3. 建议执行顺序

1. 先做**方案 1**（零风险，收敛结构）
2. 再做**方案 3**（订阅移出 + 订阅者名唯一化），此时只有单实例，风险可控
3. **方案 2** 需要你拍板：是否要让 kernel 真正启用末那识

---

---

## 4. 执行记录

已落地（4 个文件）：`manas_engine.py` / `manas_manager.py` /
`application/event_registrar.py` / `register.py`。

### 4.1 顺带发现的真 bug：`ManasManager.compute()` 必抛 AttributeError

评估阶段漏看，执行时补齐。`compute()` 第 135 行调用 `self._get_session_manager()`，
但类里**根本没有这个方法**（只有一个无人调用的 `_get_trading_clock`）：

```
AttributeError: 'ManasManager' object has no attribute '_get_session_manager'
```

影响面：两处 UI 调用方 `attention/ui/components.py:232`（无 try 包裹，直接抛异常）
与 `attention/ui/awakening.py:118`（被 try 吞掉，静默返回默认值）。
也就是说**末那识状态面板一启用就崩、觉醒度面板永远显示默认值**。

修法：把死方法 `_get_trading_clock` 重命名为 `_get_session_manager`
（一次改动同时修 bug + 清死代码，语义与 `ManasEngine` 的 `session_manager` 参数对齐）。

### 4.2 事件订阅迁移（方案 3，按 §6.3）

沿用仓库既有约定——其它领域对象（NarrativeTracker / TimingNarrativeTracker /
SupplyChainLinker / CrossSignalAnalyzer）都是「`__init__` 留迁移注释 +
暴露 `subscribe_xxx_events(event_bus)` 由 Registrar 调用」：

- `ManasEngine.__init__` 不再订阅；新增 `_cognitive_subscribed` /
  `_cognitive_subscriber_name`（`f"ManasEngine#{id(self)}"`）
- `_subscribe_to_event_bus()` → `subscribe_cognitive_events(event_bus=None)`
  （幂等、订阅者名唯一、返回值可判定成败）
- 新增 `unsubscribe_cognitive_events()`，供重建/销毁时摘除
- `ManasManager.set_enabled(True)` 引擎就绪后调 `_attach_event_bus()`
  （离创建点最近的装配位置，覆盖懒创建场景）
- `EventSubscriberRegistrar` 新增 `_register_manas()`，覆盖启动即存在的
  attention_os 内核引擎与容器 manager 引擎

⚠️ 关于"忘记 attach 就静默退化"的风险：两处装配点互相兜底
（Registrar 管启动时已有实例，Manager 管懒创建实例），且 `subscribe_cognitive_events`
幂等，重复调用无副作用；未订阅时 Registrar 会打日志说明。

### 4.3 删除死注册（方案 1，结论有修正）

见 §1.1 更正：容器已覆盖注册，register.py 的 factory 永不执行，
其注释「注入 attention_os 的 kernel」会误导后来者以为末那识已接入内核。已删除。

### 4.4 验证

| 项 | 结果 |
|---|---|
| 构造后是否自动订阅 | `False` ✅ |
| 两实例订阅者名是否唯一 | 是，总线上各 1 条（不再重复挂载）✅ |
| 重复订阅是否幂等 | 是 ✅ |
| 按名退订是否只摘自己 | 是 ✅ |
| manager 启用后引擎是否已订阅 | 是 ✅ |
| `manager.compute()` | 正常返回 dict（修复前必抛 AttributeError）✅ |
| `register_all_singletons()` | 67 个组件注册成功，`manas_manager` 已不在其中 ✅ |
| 4 个文件编译 | 通过 ✅ |

### 4.5 当时未处理：方案 2（已由 §5 执行）

（原文保留）kernel 的末那识通路当前仍是**关闭**的（`_enable_manas` 永为真不了）：
唯一会注入 kernel 的 manager 是已删除的 A，容器的 B 传的是 `kernel=None`。
要打开需让 container 注入 `attention_os.get_kernel()` 并启动即 `set_enabled(True)`，
这会让 kernel 的注意力打分开始走 `_process_with_manas` 分支——
**等于启用一条此前从未生效的决策通路**，需确认是否为预期设计。

> 该段的风险判断基于 §1.2 的错误前提，见 §1.2 更正。实际风险远低于此。

---

## 5. 方案 2 执行记录：合并引擎，消除状态分裂

已落地：`application/container.py` 的 `_create_manas_manager()`。

```python
kernel = self._attention_os.get_kernel()      # attention_os 先于本方法创建（第 233 行）
manas_manager = ManasManager(kernel=kernel, trading_clock=..., ...)
manas_manager.set_enabled(True)               # 启动即启用
```

### 5.1 实际效果（与评估预期不同）

| 评估时的预期 | 实际情况 |
|---|---|
| 打开一条从未生效的决策通路，改变 alpha 与注意力权重 | **不改变内核行为**——`OSAttentionKernel` 本来就无条件跑末那识 |
| 风险：中 | 风险：**低**，只是让 manager 停止自建第二个引擎 |
| — | 额外修复：`container.manas_engine` 此前**恒为 None**（因 manager 从未启用），现在返回内核那一份 |

收益是**状态合并**：内核打分用的引擎 == UI / manager 读的引擎，
`_supply_chain_state`（叙事风险、共振分数、AI 算力趋势）与 `_recent_pnl` 不再分裂。

### 5.2 为什么启用放在创建处而不是别处

- 容器的 `_assemble_core_components()` 第 241 行紧接着就取
  `self._manas_engine = self._manas_manager.get_manas_engine()`，
  若此时未启用，该值恒为 None
- 用 `self._attention_os` 直接属性访问（不用 property），与同方法内
  `_bandit_tracker` 的处理一致，避免触发 `_assemble_core_components()` 递归
- `get_kernel()` 失败时降级为 `kernel=None`，manager 退回自建引擎，不阻断启动

### 5.3 验证

| 项 | 结果 |
|---|---|
| manager 引擎 `is` kernel 引擎 | `True` ✅ |
| `container.manas_engine` 不再为 None | 是 ✅ |
| 未另建第二个引擎（`m._manas_engine is` kernel 引擎） | 是 ✅ |
| 启用时自动挂载事件订阅 | 是（订阅者名唯一）✅ |
| `manager.compute()` | 正常返回，manas_score=0.284 ✅ |
| `get_state()` | `enabled=True, kernel_manas_enabled=True`，gate 理由与 action 一致 ✅ |
| 编译 | 通过 ✅ |

### 5.4 P1 收尾状态

三处 engine 定义点现状：
- ~~A register.py factory~~ 已删（永不生效）
- B `container.manas_manager` —— 现在注入 kernel，**与内核共用同一引擎**
- C UI 懒建引擎 —— 不再产生（`kernel is not None` 分支不会自建）

→ **全进程只剩一个 ManasEngine**。P1 的目标（消灭单例分裂 / 重复订阅 /
订阅归属）已全部达成。

*评估基于 register.py / container.py / kernel.py / manas_engine.py /
manas_manager.py / attention_api.py 与 singleton_registry.py 的实际调用链核对。*
