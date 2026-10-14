# P0 链路深挖与「合理方案」定案（认知 ↔ 交易 / Manas 风险上下文）

> 背景：2026-10-15 审计（`architecture_gap_audit_2026-10-15.md`）挖出两个 P0。
> 用户指令：「我拍吧，我也不懂啊。你最好把它背后这个深挖一下，看看怎么样是合理的。」
> 本文就是把「什么是合理的」用**可核对的证据**钉死，而不是拍脑袋。
> 所有结论都带 `文件:行号`；标注【事实】的是核查过的，标注【判断】的是工程取舍。

---

## 0. 一句话结论

| P0 | 有没有「唯一正确答案」？ | 本次处置 |
|---|---|---|
| **P0-2 Manas 风险上下文假接** | **有** —— 数据源与姿势都能从既有代码里定死 | ✅ **已修并默认生效**（带 `NAJA_MANAS_ADAPTIVE_SL=0` 回滚） |
| **P0-1 认知↔交易桥** | **没有** —— 方向映射是策略决策，代码里无既有约定 | ⚠️ **代码已修正确并接上装配点，但默认仍关**（`NAJA_BUS_BRIDGE=1` 开） |
| （挖掘过程中新发现）**认知事件家族半个不存在** | **有** | ✅ 已修 —— 这是本次挖出的最深一层，见 §4 |

---

## 1. P0-1：认知层到底在发什么、交易层到底在收什么

### 1.1 两条互不可见的通道【事实】

`NajaEventBus`（`events/cognitive_bus.py:149`）同时承载两条通道：

| 通道 | 订阅 | 发布 | 路由键 |
|---|---|---|---|
| 认知信号通道 | `subscribe_cognitive`（:339） | `publish_cognitive_event`（:379） | `CognitiveEventType` **枚举** |
| dataclass 通道 | `subscribe('类名', cb)`（:185 → `_subscribe_dataclass` :220） | `publish(obj)`（:243） | `type(event).__name__` **字符串** |

`publish()` 里 `isinstance(event, CognitiveSignalEvent)` 决定走哪条（:255-258），两条通道的订阅表是**两个不同的 dict**（`_cognitive_subscribers` vs `_dc_subscriptions`）。

**桥原来的实现订阅的是前者**（`subscribe_cognitive`），而认知层实际在发的全是 dataclass → 一个事件也收不到。

### 1.2 认知层实际在发的事件【事实】

| 事件 | 发布位置 | 调用链是否可达 | 载荷 | 能否过桥 |
|---|---|---|---|---|
| `NarrativeStateEvent` | `narrative/tracker.py:750` | ✅ 可达：`_publish_narrative_state_event`(693) ← `_process_external_narratives`(625) ← `ingest_event`(600) ← `_on_text_focused`(订阅 `TextFocusedEvent`) | `current_narratives: List[str]`（叙事**名**）、`narrative_strength`、`narrative_risk`、`sentiment_score ∈[0,1]`。**无 `symbols`、无 `importance`、无 `confidence`** | ✅（需解析叙事名→标的） |
| `ResonanceDetectedEvent` | `analysis/cross_signal_analyzer.py:1206` | ✅ 可达：`_emit_to_cognitive_bus` ← `_check_pending_resonance`(596) ← :463 | `symbols=[resonance.block_id]` —— **是板块ID不是股票代码**；`strength`；`importance`；`metadata.sentiment` | ✅（需解析板块ID→标的） |
| `NarrativeUpdateEvent` | `narrative/tracker.py:470`（`create_narrative_update`） | ❌ **方法无调用方** | `symbols`（**真实股票代码**）、`narrative_type`、`strength_change ∈[-1,1]` | 发射端未接 |
| `TimingNarrativeShiftEvent` | `narrative/timing.py:200` | ❌ **方法无调用方**，且传了非法 kwarg | `new_regime`、`regime_strength` | 发射端未接 |
| `RiskAlertEvent` | 无 | ❌ 全库从未构造 | `level`、`symbols`、`suggested_action` | 无生产者 |

### 1.3 交易层是完全接好的【事实】

`application/event_registrar.py:275`
→ `trading_bus.subscribe("StrategySignalEvent", on_strategy_signal)`
→ `trading_center.process_strategy_signal_event`（`trading_center.py:560`）
→ `process_strategy_signal`（:679）→ 融合/Manas 闸门 → `DecisionPlan` → `TradeDecisionEvent`

**只要有人往交易总线发一个合规的 `StrategySignalEvent`，它就会进决策中心。** 断的从来不是这一段。

**另有既有生产者可参照**：`market_hotspot/strategies/base.py:388` —— 它在**上游**就已经产出了 `signal.symbol`，所以不需要解析器。这是「合理写法」的样板。

### 1.4 结论：合理的做法不是「翻开关」，是「先补解析器 + 先修发射端」

`_resolve_symbols` 的三级解析（已实现，见 §3）：

1. token 本身已是可交易代码 → 直接采用；
2. `BlockRegistry`（`attention/block_registry.py`，`get_block_registry()`）：
   `get_blocks_for_narrative(叙事名)` → `BlockDescriptor.symbols`
   —— `symbols` 由 `FocusManager._update_block_link_to_stock`(:364) → `link_symbol_to_block`(:152-156) **真实填充**；
3. `cognition.narrative.block_mapping.get_linked_blocks(叙事名)` → 题材ID
   → `dictionary.blocks.get_block_stocks(题材ID, market)`（A股题材名形如「3D打印」，数据在 `cn_blocks.yaml`）。

**❗注意两套 block 命名空间不可混用**【事实】：
`attention/block_registry.py` 的 block_id 是抽象英文（`semiconductor` / `AI`），
`dictionary/blocks/*.yaml` 的 id 是通达信中文题材名（`3D打印` / `AIGC概念`）。
所以两级解析**必须串联**，不能用一套查另一套。

### 1.5 为什么默认仍然关（【判断】，需人拍板的部分）

`_narrative_state_to_signals` / `_resonance_to_signals` 里的方向判定，用的是：

- 叙事：`sentiment_score`（0.5 中性）> 0.6 买 / < 0.4 卖，中间**不发信号**；
- 共振：`metadata.sentiment`（0 中性）> 0.1 买 / < -0.1 卖，中间**不发信号**。

这两条阈值是**占位口径**，代码里**没有任何既有约定**可以依据 —— 「叙事转强 = 买还是卖」在真钱链路里是策略决策。硬开等于把一条拍脑袋的规则接进下单路径。

因此处置是：**把桥修到「结构正确、只差一个开关」**，开关交给环境变量，并保证「关」是一个**显式且被记录**的状态（`enable_bridge_from_env()` 无论如何都打日志），而不是修复前那种「只能靠读代码才知道没接」。

---

## 2. P0-2：Manas 风险上下文 —— 有唯一正确答案

### 2.1 现在的实际后果（比审计里写的「全返 0」更精确）【事实】

`adaptive_cycle.py:177` 传的是**一个 dict**：
```python
portfolio_state = {"position_pct": 0.0, "total_value": 100000, "cash": 30000}
manas_engine.compute(session_manager=None, portfolio=portfolio_state, scanner=None, ...)
```
而 `RiskEngine`（`manas_engine.py:992`）按 `portfolio.get_summary()` 取数 → **dict 没有该方法** → `AttributeError` 被 `_get_cash_ratio`(:1031) 内部 `except` 吞掉 → `cash_ratio ≡ 0.5`、`drawdown ≡ 0`；`scanner=None` → `volatility ≡ 1.0`。

于是 `base_T = 1.0 + (1 - 0.5) × 0.5 = 1.25` → **`risk_temperature` 恒 1.25**。

`_get_adaptive_stop_loss`(:205) 的档位是 `>1.5` / `>1.3` / `timing<0.4` / else —— 1.25 **永远进不了前两档**，于是恒走 else：

> **「自适应」止盈止损从未生效过一次，实际恒为 -8% / +15%。**

（`core_establish_gate.py:11` 已经记录过这个假接，但记的后果是「regime 恒中性」；这里补上更致命的那一半：风险温度恒定。）

### 2.2 正确答案：`virtual_portfolio`，不是 `portfolio_manager`【事实】

三条独立证据同向：

| 证据 | 位置 | 内容 |
|---|---|---|
| 容器装配（内核侧） | `application/container.py:1168` | `kernel.set_manas_dependencies(portfolio=self._virtual_portfolio, bandit_tracker=self._bandit_tracker)` |
| 容器装配（周期侧） | `application/container.py:1340` | `AdaptiveCycle(portfolio=self._virtual_portfolio, ...)` |
| 引擎契约 | `manas_engine.py:997` docstring | `portfolio: VirtualPortfolio` |

**接口形状对不上**（决定性）：`RiskEngine` 读的是
`available_capital` / `total_capital` / `used_capital` / `total_return`
—— 这正是 `VirtualPortfolio.get_summary()`（`virtual_portfolio.py:515-535`）的键。
而 `PortfolioManager`（多账户）与账户类 `get_summary()`（`portfolio_manager.py:328`）返回的是
`account_name` / `total_value` / …，**没有 `available_capital` / `total_capital`**。

→ 传 `portfolio_manager` 会让 `cash_ratio` 掉进 `total_value` 兜底甚至 0.5，等于换一种假接。

### 2.3 正确姿势：复用内核的**单出口**【事实 + 判断】

`attention/os/os_kernel.py:420` 的 `get_manas_inputs()`，其 docstring 已经把这类事故写成规则：

> 「内核打分路径（process / make_decision）与 ManasManager 展示路径共用这一个出口，消除「同一个引擎被两种喂法喂」——历史问题：内核侧传 portfolio=None … 而 manager 侧传真实对象，于是内核打分与 UI 展示可以给出不一致的结论。」

所以合理实现就是**照抄这个出口**：`manas_inputs = kernel.get_manas_inputs()`，缺 `portfolio` 时用 `self._portfolio` 兜底（它与容器注入内核的是**同一个 `virtual_portfolio` 单例**）。

顺带接上的两条（都是**只读**，不写任何状态）：

- `narratives`：从认知总线读最近一次 `NarrativeStateEvent` 的 `current_narratives`（`_current_narratives_for_manas()`）。原本传的是 `narratives=[]`。
- `session_manager` / `scanner` / `bandit_tracker`：随 `get_manas_inputs()` 一并拿到真实对象（原本全是 `None`）。

### 2.4 影响面与风险（【判断】）

- **只影响新开仓**：`_get_adaptive_stop_loss()` 唯一的业务调用点是 `_on_new_signal`（`adaptive_cycle.py:401`），在**创建持仓**时把止损止盈写进 `VirtualPosition`。**存量持仓不受影响**。
- `AdaptiveCycle` 只在**操作员从 bandit 管理页启动**时才跑（`bandit/ui.py:737` 唯一 `cycle.start()`，页面入口 `web_ui/pages.py:106`）→ 不是无人工干预的自动链路。
- 方向是**收紧**（高波动时 -8% → -4.8% / -3.2%），偏保守。
- 回滚：`NAJA_MANAS_ADAPTIVE_SL=0` 立即恢复固定 -8%/+15%。
- 补齐可观测性：else 分支以前**不打日志**，现在显式打印所用档位，否则「一直用同一对常数」看起来像在工作。

---

## 3. 本次改了什么（逐文件）

| 文件 | 改动 | 性质 |
|---|---|---|
| `events/bus_bridge.py` | 重写：① 订阅改 dataclass 通道；② 新增 `_resolve_symbols` 三级解析；③ 按**真实字段**推导 importance/confidence；④ 方向判不出就**不发信号**（不猜）；⑤ `_looks_like_code` 收紧为「必须带市场标记」；⑥ 新增 `NAJA_BUS_BRIDGE` 开关与 `enable_bridge_from_env()`；⑦ 统计区分「映射缺失」与「链路故障」 | 结构修正 |
| `application/container.py` | 装配点 9b：调用 `enable_bridge_from_env()` | 接线 |
| `events/__init__.py` | 导入名单逐名对齐实际定义 + 失败改**告警**；`EVENT_TYPE_MAP` 别名到 `EVENT_TYPE_MAPPING`；`__all__` 同步 | **根因修复**（见 §4） |
| `cognition/analysis/cross_signal_analyzer.py` | 5 处 `from .narrative_block_mapping import` → `..narrative.block_mapping`（前者模块**不存在**） | 断链修复 |
| `cognition/ingestion.py` | `GlobalMarketEvent`（**全库不存在**）→ 改走 `publish_cognitive_event(GLOBAL_MARKET_EVENT)`；`_ingest_market_alert_legacy` 从「仅 ImportError 时」改为**每次都调** | 断链修复 |
| `bandit/adaptive_cycle.py` | `_get_manas_risk_context` 用真实输入 + `_current_narratives_for_manas()`；else 档补日志；`NAJA_MANAS_ADAPTIVE_SL` 开关 | P0-2 修复 |
| `cognition/narrative/tracker.py` | `_publish_cognitive_update` 参数修正（`narrative_id="narratives..."` 是字面量垃圾）；标注「无调用方」 | 半死代码修正 |
| `cognition/narrative/timing.py` | 去非法 kwarg `event_type=`（property 不可写）；标注「无调用方」 | 半死代码修正 |

### 3.1 `_looks_like_code` 收紧 —— 一个真实踩到的坑【事实】

初版用「纯字母大写」判定股票代码，结果：

```python
'不存在的叙事XYZ'.isupper()  →  True     # CJK 不参与大小写判定！
```

于是任何「中文名 + 大写字母」的叙事名都被当成股票代码，**凭空造出一个标的**送进决策中心。改为必须带市场标记：

- `^(sh|sz|bj)\d{6}$`（无点前缀，与行情总线/题材策略实际写法一致）或裸 6 位数字；
- `^[A-Z0-9]{1,10}\.(us|hk)$`（显式市场后缀）。

附带修正：旧规则**漏认** `00700.HK`（港股 5 位）→ 新规则认。

### 3.2 与交易总线去重的相互作用（必须知道）【事实】

`trading_bus.py:275` 的指纹是 `strategy:{symbol}:{direction}:{minute}`。
因此**同一分钟内、同一标的、同一方向**的认知信号与策略信号会合并成一条 —— 这是**期望行为**（认知不该给同一标的加码），但排查时容易误判成「桥没生效」。

---

## 4. 挖出来的最深一层：认知 dataclass 事件家族「半个不存在」

`events/__init__.py:109` 的导入名单里写了 **三个 `cognition_events.py` 并不存在**的名字：
`GlobalMarketEvent` / `create_risk_alert` / `EVENT_TYPE_MAP`（实际叫 `EVENT_TYPE_MAPPING`）。

`from X import (a, b, c)` 编译成**逐名** `IMPORT_FROM` + `STORE_NAME`，因此：

```
✅ NarrativeUpdateEvent      ← 缺失名之前，侥幸已绑定
✅ TimingNarrativeShiftEvent
✅ ResonanceDetectedEvent
✅ SupplyChainRiskEvent
✅ RiskAlertEvent
❌ GlobalMarketEvent          ← 第一个缺失名，在此抛 ImportError
❌ PortfolioSignalEvent      ← 之后全部没有绑定
❌ CognitionResetEvent
❌ create_narrative_update
❌ create_risk_alert
❌ EVENT_TYPE_MAP
COGNITION_EVENTS_AVAILABLE = False
```

而所有消费方写的都是 `except ImportError: pass` → **完全无声**。

**实测后果**：`tracker._publish_cognitive_update` 的 `from deva.naja.events import create_narrative_update` 必然 ImportError → 一句 `pass` 收场。也就是说，即使把方法里的参数写对，它仍然是死的 —— 这是「发射端没接」的**真正原因之一**。

**修法**：导入名单改为与实际定义逐名对齐；失败从静默改为 `log.warning`；新增守卫 ① 长期看住这件事。

---

## 5. 修复顺序（为什么是这个顺序）

```
① 事件家族导出对齐  ──→  ② 发射端参数修正  ──→  ③ 桥的内部正确性  ──→  ④ 装配点接线  ──→  ⑤ 方向口径（人拍）
   （§4，根因）            （tracker/timing）      （dataclass 通道+解析器）  （env 开关）        （默认关）
```

前三步都是**纯缺陷**，不改变任何既有行为；④ 是接线但默认关；⑤ 才是策略决策。
反过来做（先开桥）只会得到「开关开了、事件还是收不到」的假绿。

---

## 6. 验证记录

| 项 | 方法 | 结果 |
|---|---|---|
| 失效 import | 全库 grep `narrative_block_mapping` | 仅剩注释引用，代码 0 处 |
| 事件家族导出 | 逐名 `hasattr` + `__all__` 未定义名检查 | 13/13 可用；`COGNITION_EVENTS_AVAILABLE=True`；`__all__` 无悬空名 |
| 两个沉寂发射端 | 直接调用并断言总线收到 | 2/2 收到（修复前 0/2） |
| 桥：10 个用例 | 见下 | 10/10 |
| Manas 接线 | 假内核记录入参 | portfolio 是对象而非 dict；session/scanner/bandit 均为真实值；narratives 来自总线 |
| 回滚开关 | `NAJA_MANAS_ADAPTIVE_SL=0` | 回到固定口径，不读 Manas |
| 失败路径 | 内核抛异常 | 退回固定口径 **并告警**（不静默） |
| 存量测试 | `pytest deva/naja/tests/test_decision_fusion.py` | 27 passed |
| 存量守卫 | `undefined_names` / `dataclass_inheritance` / `market_time_alias` / `log_traceback` / `singleton_registry_consistency` | 全部 exit 0 |

桥的 10 个用例：

1. 默认 `enabled=False`，env 未设时 `bridge_enabled_by_env()=False`
2. 反复 enable/disable 幂等，不抛异常、不重复订阅
3. 看多叙事（`sentiment=0.9`）→ 恰好 2 只标的（`sh600487`/`sz000636`），**叙事名 `AI` 没有被当成代码**
4. 中性情绪（`sentiment=0.5`）→ 0 条信号（不猜方向）
5. 共振事件 `symbols=['semiconductor']`（板块ID）→ 解析成标的，负情绪 → SELL
6. 无法解析的叙事 → 0 条信号 + `dropped_unresolved_symbols` +1（**如实为空，不编造**）
7. 重要性低于阈值 → 过滤 + `filtered_by_importance` +1
8. 关闭后 → 0 条信号
9. `NarrativeUpdateEvent`（自带真实股票代码，`strength_change=+0.8`）→ BUY
10. `strength_change=0`（无方向证据）→ 0 条信号

---

## 7. 尚未处置 / 需人拍板

| 项 | 现状 | 为什么没动 |
|---|---|---|
| **开桥（`NAJA_BUS_BRIDGE=1`）** | 默认关 | 方向口径是策略决策（§1.5）。开了之后：叙事/共振事件会以 `confidence = 强度 × 0.6` 进入决策中心，**仍要过 Manas 闸门与融合置信度阈值**，不是直接下单 |
| **`NarrativeUpdateEvent` / `TimingNarrativeShiftEvent` 的发射端接上** | 方法已修对，但仍无调用方 | 接上 = 新增生产者 = 新增行为。属于「要不要让这两类认知事件参与」的决策 |
| **`RiskAlertEvent` 从未被构造** | 无生产者 | 补生产者是新增功能 |
| **`_reinforce_narrative` / `_adjust_risk_cognition`（交易→认知反馈）** | 空实现（只打 debug） | 已在 docstring 里明确标注「尚未实现实质动作」，避免被误当成已生效 |
| **`NAJA_MANAS_ADAPTIVE_SL` 默认值** | 默认 **开** | 依据：只影响新开仓、方向是收紧、操作员手动启动、有回滚开关（§2.4）。若要更保守，置 0 即可 |

---

## 8. 常驻守卫

`scripts/verify/verify_cognitive_trading_linkage.py`

| 段 | 看住什么 |
|---|---|
| ① | `events/__init__.py` 的 dataclass 导入名单必须逐个在 `cognition_events.py` 有定义；`__all__` 不得有悬空名 |
| ② | 全库不得再出现 `from .narrative_block_mapping import`（模块不存在） |
| ③ | `bus_bridge.py` 必须走 dataclass 通道订阅，且规则表 key 必须对应真实存在的 dataclass 事件类 |
| ④ | 容器必须调用 `enable_bridge_from_env`；不设 env 时 `bridge_enabled_by_env()` 必须为 False（默认关） |
| ⑤ | `adaptive_cycle._get_manas_risk_context` 不得再出现硬编码 dict 持仓，且必须经 `get_manas_inputs()` 取输入 |
| ⑥ | `_looks_like_code` 判定基准（硬编码期望值）：`AI`/`不存在的叙事XYZ`/`AI芯片` → False；`sh600487`/`600487`/`AAPL.US`/`00700.HK` → True |

用法：`python3 scripts/verify/verify_cognitive_trading_linkage.py [--strict] [--self-test]`
