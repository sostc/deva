# Naja 架构断链审计

> 审计日期：2026-10-15
> 方法：AST 静态比对（事件定义/构造/订阅三向）+ 单例注册表双向比对（注册 vs 取用）+ 关键链路人工追踪
> 代码基线：`deva/naja/`，604 个 py 文件，约 21.4 万行

---

## 0. 一句话结论

系统**主干链路是通的**（策略信号 → 交易总线 → 决策中心 → 执行 → 成交回流），
但**「认知层 → 交易层」这条横向桥梁从未被打开**，导致占代码量约一半的认知系统
（叙事/洞察/流动性/共振/风险）实际上**不影响任何一笔交易**。
另有 1 处硬编码假数据、4 个取用了未注册的单例、若干定义了永不发出的事件。

---

## 1. 整体分层（现状）

```text
┌─ 入口 ─────────────────────────────────────────────────┐
│ __main__.py / infra/lifecycle/bootstrap.py             │
└──────────────────────┬─────────────────────────────────┘
                       ↓
┌─ Application（组合根）─────────────────────────────────┐
│ container.py (1646行)  ← 装配 + 覆盖注册              │
│ event_registrar.py     ← 集中订阅（✅ 已接上）         │
│ runtime_modes / wake_orchestrator                      │
└──────────────────────┬─────────────────────────────────┘
                       ↓
┌─ 认知总线 CognitiveBus ────┐   ┌─ 交易总线 TradingBus ─┐
│ NarrativeStateEvent        │   │ StrategySignalEvent    │
│ MerrillClockEvent          │ ⇋ │ TradeDecisionEvent     │
│ LiquiditySignalEvent       │   │ TradeOutcomeEvent      │
│ GlobalMarketDataEvent      │   └───────────┬────────────┘
└───────────┬────────────────┘               │
            │      ❌ BusBridge 从未启用      │
            └──────────────╳─────────────────┘
                                             ↓
                       ┌────────────────────────────────┐
                       │ TradingCenter.process_strategy │
                       │  → decision/(fusion,sizing,    │
                       │     plan,journal) → 闸门       │
                       │  → bandit/adaptive_cycle       │
                       │  → execution.submit()          │
                       └───────────────┬────────────────┘
                                       ↓
                       TradeOutcomeEvent → record_trade_outcome
                       （✅ 闭环已通）
```

---

## 2. 断链清单（按严重度）

### 🔴 P0 — 架构级断链

#### P0-1 认知↔交易桥梁（BusBridge）从未启用

| 项 | 内容 |
|---|---|
| 位置 | `deva/naja/events/bus_bridge.py:54`（初始化日志明写"未启用"） |
| 证据 | 全库 `enable_bridge(True)` 只出现在 `events/__init__.py:22` 的 **docstring 示例** 与 `:296` 的文档说明里，**无任何生产代码调用** |
| 后果 | `bus_bridge.py:38-42` 定义的四条转换规则永不执行：<br>`NARRATIVE_UPDATE`(0.7) / `TIMING_NARRATIVE_SHIFT`(0.8) / `RESONANCE_DETECTED`(0.75) / `RISK_ALERT`(0.9) |
| 影响面 | 叙事、时机、共振、风险四条认知产出**永远到不了交易侧** |

> 这是本次审计发现的最大断点：认知层（narrative tracker 2446 行、insight、liquidity cognition
> 1189 行、cross_signal_analyzer 1343 行、first_principles_mind 1707 行）的产出，
> 除 Manas 少数几个直读点外，无法驱动交易。

#### P0-2 Manas 风险上下文是硬编码假接

| 项 | 内容 |
|---|---|
| 位置 | `deva/naja/bandit/adaptive_cycle.py:177` |
| 代码 | `portfolio_state = {"position_pct": 0.0, "total_value": 100000, "cash": 30000}` |
| 附带 | 同函数 `_get_manas_risk_context()` 传 `session_manager=None` |
| 后果 | `adaptive_cycle.py:215-232` 的止盈止损调整（`risk_t > 1.5` → `stop_loss *= 0.4`）建立在**永远为 0 的持仓率**之上，风险温度事实上恒为默认值 |

---

### 🟠 P1 — 装配/注册断链

#### P1-1 取用了但从未注册（运行时 KeyError 或静默降级）

| 单例名 | 取用位置 |
|---|---|
| `SR('connector')` | `home/ui/stats.py:48`、`knowledge/wisdom/ui.py:19` |
| `SR('replay_scheduler')` | `infra/observability/auto_tuner.py:32`、`web_ui/modes.py:365`、`bandit/market_observer.py:91` |
| `SR('block_noise_detector')` | `market_hotspot/core/block_engine.py:35` |

> 三处都在 `try/except` 或惰性取用路径里，不会崩，但**功能永久缺失且不报错**——典型静默失效。

#### P1-2 注册了但全库零引用（死装配）

| 单例名 | 说明 |
|---|---|
| `cognition_bus` | `register.py:243` 注册；实际都用 `get_event_bus()` 模块级单例 |
| `strategy_result_store` | 零引用；而 `bandit_attribution` 的 deps 依赖它 → 连带不实例化 |
| `signal_dispatcher` | 零引用 |

#### P1-3 双实例风险（注册表一套 + 模块级一套）

| 名字 | 注册表 | 模块级单例 |
|---|---|---|
| `snapshot_manager` | `register.py:69` | `state/snapshot.py:484` `_snapshot_manager` |
| `scheduler_manager` | `register.py:106` | `datasource/models.py:20` `_scheduler_manager` |

> 违反项目既有规则「禁止两个不同语义的名字指向同一对象」的反向形态：
> **一个语义、两个实例**，状态可能各写各的。

---

### 🟡 P2 — 事件层断链

#### P2-1 定义了但从未被构造的事件类（永不发出）

```
BlockNarrativeUpdateEvent   cognition_events.py
CognitionResetEvent         cognition_events.py
MarketSnapshotEvent         hotspot_events.py
PortfolioSignalEvent        cognition_events.py
RiskAlertEvent              cognition_events.py   ← 见下
SymbolUpdateEvent           hotspot_events.py
```

> 讽刺点：`bus_bridge.py:42` 为 `RISK_ALERT` 写了转换规则，
> 但 `RiskAlertEvent` 全库**从未被构造过一次** —— 规则和事件两头都有，中间没人发。

#### P2-2 认知事件枚举 21 个成员，实际显式发布仅 2 个

`CognitiveEventType`（`events/cognitive_bus.py`）共 21 个成员；
代码中以 `event_type=CognitiveEventType.X` 形式发布的只有：

- `NARRATIVE_UPDATE`
- `MANAS_STATE_CHANGED`

其余（约 17 个）从未发布，含：`RISK_ALERT`、`SUPPLY_CHAIN_RISK`、`RESONANCE_DETECTED`、
`TIMING_NARRATIVE_SHIFT`、`INSIGHT_GENERATED`、`PORTFOLIO_SIGNAL`、`NEWS_SIGNAL`、
`COGNITION_RESET`、`COGNITION_FEEDBACK`、`SEMANTIC_GRAPH_UPDATE`、`HOTSPOT_SNAPSHOT`、
`NARRATIVE_BOOST`、`NARRATIVE_DECAY`、`RESONANCE_DECAY`、`BLOCK_NARRATIVE_UPDATE`、
`NARRATIVE_SUPPLY_LINK`、`SUPPLY_CHAIN_IMPACT`。

> 注：部分认知事件改走 dataclass 直接 `publish()`（不传枚举），故此项为**枚举冗余**而非全断链，
> 但仍意味着按枚举订阅的消费者永远收不到。

---

### 🟢 P3 — 消费方偏弱 / 半接

| # | 断点 | 位置 | 说明 |
|---|---|---|---|
| 3-1 | 流动性预测仅 2 个消费方 | `manas_engine.py:749`、`bandit/tracker.py:31` | 无独立交易出口；`tracker._get_liquidity_signal` 用 `except Exception: pass` 吞异常，回落 0.5 且不记录 |
| 3-2 | `decision/query.py` 仅 UI 使用 | `attention/ui/dashboard.py:184`、`components.py:358` | 不参与决策闭环，纯展示 |
| 3-3 | 富途持仓同步无自动触发 | `bandit/execution.py:622`、`bandit/ui.py:801` | 只在执行器内部构造与 UI 手动点击，无定时同步 |
| 3-4 | 认知类事件构造后未跨模块 | 见 AST 扫描 | `GlobalMarketDataEvent`、`LiquiditySignalEvent`、`MerrillClockEvent`、`NarrativeStateEvent`、`NewsEvent`、`SupplyChainRiskEvent`、`TextFocusedEvent` 均只在单一文件内构造，需确认是否真上总线 |

---

## 3. 已确认**接上**的链路（避免误报）

| 链路 | 证据 |
|---|---|
| 集中事件订阅 | `container.py:386-387` → `_create_event_registrar()` → `register_all()` |
| 策略信号 → 决策 | `market_hotspot/strategies/base.py:411` 发 `StrategySignalEvent` 到交易总线 → `event_registrar.py` 订阅 → `trading_center.py:560/679` |
| decision 层被真正使用 | `trading_center.py:37-45` 引入 `DecisionOrchestrator / FusionOutput / compute_plan_size_hint / side_from_signal_type`；`adaptive_cycle.py:22` 引入 `compute_order_amount, manas_sizing_enabled` |
| 成交回流闭环 | `adaptive_cycle.py:546-567` 发 `TradeOutcomeEvent` → `event_registrar.py:308` 订阅 → `TradingCenter.record_trade_outcome` |
| 守望系统 | `t_rotation_runner.py:154` 装配 `CoreEstablishWatch`；`pages.py:114` + `routes.py:947` 挂 `/watchdesk` |
| 唤醒补作业 | `container.py` → `wake_orchestrator` → `wake_sync_handlers` |

---

## 4. 建议修复顺序

1. **开桥**：在 `container.py` 装配阶段调用 `get_bus_bridge().enable_bridge(True)`，
   并补一条守卫验证「桥已启用 + 至少一次认知→交易转换成功」。（P0-1）
2. **拆假数据**：`adaptive_cycle._get_manas_risk_context` 改为真实持仓输入；
   取不到时**如实返回 None 并记原因**，不要回落 0.0。（P0-2）
3. **补注册 or 删取用**：3 个未注册单例要么补进 `register.py`，要么删除取用点。（P1-1）
4. **清理死装配**：`cognition_bus` / `strategy_result_store` / `signal_dispatcher` 三选一
   （删注册 / 接上消费者 / 标注为预留）。（P1-2）
5. **统一双实例**：`snapshot_manager`、`scheduler_manager` 收敛到注册表一处。（P1-3）
6. **事件层减冗余**：要么补发 `RiskAlertEvent` 等，要么删除对应枚举与转换规则，
   避免「规则写了、事件没人发」的假象。（P2）

---

## 5. 审计脚本

本次使用的静态分析脚本（可复跑）：

- `/tmp/arch_ast.py` — 事件类定义 / 构造 / 订阅三向 AST 比对
- `/tmp/sr_cmp.py` — 单例注册 vs 取用双向比对
- `/tmp/idle2.py` — 零引用单例二次筛选

已固化：`scripts/verify/verify_singleton_registry_consistency.py`（见 §7）。

---

## 6. 修复记录（2026-10-15）

### 已修

| # | 项 | 改动 | 验证 |
|---|---|---|---|
| 1 | P1-1 `SR('block_noise_detector')` 未注册 | `register.py` 增补工厂 → `get_block_noise_detector()` | 注册表 69 项含它；`SR()` 与 `get_instance()` 同一实例 ✓ |
| 2 | P1-3 `snapshot_manager` 双实例 | 从 `SIMPLE_SINGLETONS` 移出，改工厂复用 `state.snapshot.get_snapshot_manager()` | `SR('snapshot_manager') is get_snapshot_manager()` ✓ |
| 3 | P1-3 `scheduler_manager` 双实例 | 同上，复用 `datasource.models._scheduler_manager` | `SR('scheduler_manager') is _scheduler_manager` ✓ |
| 4 | P2-2 桥规则表 key 大小写不匹配 | `_process_cognitive_event` 改用**枚举成员名**匹配（原用 `.value` 恒不命中） | 规则表命中 True（旧写法 False）✓ |
| 5 | 桥 `unsubscribe_cognitive` 调用错误 | 改用公开入口 `unsubscribe('bus_bridge')`（原方法名不存在、参数类型也错） | 反复 enable/disable 不再 AttributeError ✓ |
| 6 | P1-2 死装配 | `strategy_result_store` / `signal_dispatcher` 就地标注「无消费者」，保留声明 | — |
| 7 | 新增守卫 | `scripts/verify/verify_singleton_registry_consistency.py` | 自证通过；真实注入 `SR('negtest_...')` 被抓出 exit 1 ✓ |

### 有意未修（需决策）

| 项 | 为什么停在这里 |
|---|---|
| **P0-1 开桥** | ❗已按用户指令「深挖 + 定合理方案」处置完毕，见 **§8 与 `p0_linkage_design_2026-10-15.md`**。结论：结构缺陷**全部已修**（通道 / 字段 / 解析器 / 装配点），**默认仍关闭**（`NAJA_BUS_BRIDGE=1` 开）—— 因为「叙事/板块 → 买还是卖」的方向口径是策略决策。 |
| **P0-2 manas 假接** | ✅ **已修并默认生效**：数据源已定死为 `virtual_portfolio`（三条独立证据 + 接口形状比对），姿势复用内核单出口 `get_manas_inputs()`。回滚 `NAJA_MANAS_ADAPTIVE_SL=0`。见 §8。 |
| **P1-1 `connector` / `replay_scheduler`** | 无生产者。`connector` 连类和方法都不存在（纯死路径）；`replay_scheduler` 调用方已 `if scheduler:` 安全降级。补生产者＝新增功能，删调用＝改 UI 可见行为。两条都超出「修断链」范围，已在守卫 `KNOWN_UNREGISTERED` 中登记并留因。 |
| **P2-1 / P2-3** | 事件类「定义了没构造」/ 枚举冗余。删除会丢失设计意图，补发需要对业务重新接线。 |

---

## 7. 常驻守卫

```bash
python3 scripts/verify/verify_singleton_registry_consistency.py            # 正常，exit 0
python3 scripts/verify/verify_singleton_registry_consistency.py --strict   # 有豁免也不许过
python3 scripts/verify/verify_singleton_registry_consistency.py --self-test
```

三段检查：① 取了没注册（硬错误）② 注册了没人取（提示，区分「真零引用」与「经容器装配」）
③ 工厂里直接构造类（提示，可能是一语义两实例）。

豁免清单 `KNOWN_UNREGISTERED` 里每条都必须写清未修原因 —— 不许为了让守卫变绿而堆豁免。

```bash
python3 scripts/verify/verify_cognitive_trading_linkage.py            # 正常，exit 0
python3 scripts/verify/verify_cognitive_trading_linkage.py --self-test
```

六段检查：① 事件导出对齐 ② 失效模块引用 ③ 桥梁订阅通道 ④ 桥梁开关与装配点
⑤ Manas 输入必须真实 ⑥ 叙事名 vs 股票代码的判定基准。
六段均做过**真实注入负向验证**，全部被抓出（exit 1），还原后恢复 exit 0。

---

## 8. 二轮深挖（2026-10-15 晚）：P0 定案

用户指令：「我拍吧，我也不懂啊。你最好把它背后这个深挖一下，看看怎么样是合理的。」

完整设计与证据链见 **`docs/naja/p0_linkage_design_2026-10-15.md`**。此处只放结论。

### 8.1 新挖出的**根因级**缺陷（比首轮 P0 更深一层）

| # | 缺陷 | 文件:行 | 危害 |
|---|---|---|---|
| **R-1** | dataclass 导入名单含 **3 个不存在的名字**（`GlobalMarketEvent` / `create_risk_alert` / `EVENT_TYPE_MAP`）| `events/__init__.py:109` | `from X import (a,b,c)` 逐名绑定 → 在第一个缺失名处抛 ImportError → **缺失名之后的名字全部没绑定**（`PortfolioSignalEvent` / `CognitionResetEvent` / `create_narrative_update`…），`COGNITION_EVENTS_AVAILABLE=False`。消费方一律 `except ImportError: pass` → **完全无声**。这就是「发射端没接」的真正原因之一 |
| **R-2** | 5 处 import 一个**不存在的模块** `.narrative_block_mapping` | `cross_signal_analyzer.py:496/757/815/841/1289` | 舆情→题材联动 / 市场共振 / 指数中文名三条子链路**从未执行过一次**；正确实现一直在 `cognition/narrative/block_mapping.py`（8/8 名字齐全） |
| **R-3** | `GlobalMarketEvent` 引用不存在的类 | `cognition/ingestion.py:91` | 必然 ImportError → 永远走降级路径 → 总线路径从未成功；`radar/engine.py:999` 的全球市场事件只经由 `LiquidityCognition` 落地 |
| **R-4** | 桥的转换函数读**不存在的字段**（`stock_codes` 等），且 `NarrativeStateEvent` 无 `importance`/`confidence` → `getattr` 默认 0.0 | `bus_bridge.py` 原 187-319 | 即使被调用也只会 `return None`（恒被阈值过滤） |
| **R-5** | 「纯字母大写 = 股票代码」判定 | 本轮新写、新踩、新修 | `'不存在的叙事XYZ'.isupper()` 为 **True**（CJK 不参与大小写）→ **凭空造出标的送进决策中心** |

### 8.2 已修

| 项 | 改动 | 验证 |
|---|---|---|
| R-1 | 导入名单逐名对齐实际定义；失败从 `pass` 改 `log.warning`；`EVENT_TYPE_MAP` 别名到 `EVENT_TYPE_MAPPING`；`__all__` 同步 | 13/13 名字可用；`COGNITION_EVENTS_AVAILABLE=True`；`__all__` 无悬空名 ✓ |
| R-2 | 5 处改 `..narrative.block_mapping` | 全库残留仅注释；8 个名字可导入并返回真实数据 ✓ |
| R-3 | 改走 `publish_cognitive_event(GLOBAL_MARKET_EVENT)`；`_ingest_market_alert_legacy` 由「仅 ImportError」改为**每次都调**（它本来就一直在跑，摘掉等于切断 LiquidityCognition 输入） | 语法 + 路径核对 ✓ |
| R-4 + P0-1 | 桥重写：dataclass 通道订阅 + 三级标的解析（`BlockRegistry` → `block_mapping`+`dictionary`）+ 真实字段推导 + 判不出方向就**不发**；新增 `NAJA_BUS_BRIDGE` 开关，容器装配点接线，默认关 | 10 个用例全过 ✓ |
| R-5 | 收紧为「必须带市场标记」（`sh/sz/bj`+6 位 / 裸 6 位 / `.US` / `.HK`） | 10 条基准断言全过；附带修好旧规则**漏认 `00700.HK`** ✓ |
| P0-2 | `_get_manas_risk_context` 复用内核单出口 `get_manas_inputs()` + `self._portfolio` 兜底；`narratives` 只读接上认知总线；else 档补日志；新增 `NAJA_MANAS_ADAPTIVE_SL` 回滚开关 | 假内核记录入参：portfolio 是对象非 dict；session/scanner/bandit 均为真实值；风险温度正确透出 ✓ |
| 半死代码 | `tracker._publish_cognitive_update` 参数修正（`narrative_id="narratives..."` 是字面量垃圾）；`timing._publish_cognitive_update` 去非法 kwarg `event_type=`（property 不可写）；两者均标注「无调用方」 | 直接调用后总线如期收到（修复前 0/2）✓ |

### 8.3 P0-2 的定案依据（「合理」怎么定的）

**数据源 = `virtual_portfolio`，不是 `portfolio_manager`** —— 三条独立证据同向：

| 证据 | 位置 |
|---|---|
| 容器已把 `self._virtual_portfolio` 注入内核 | `application/container.py:1168` |
| 容器已把同一对象注入 `AdaptiveCycle` | `application/container.py:1340` |
| 引擎 docstring 写明 | `manas_engine.py:997` `portfolio: VirtualPortfolio` |

**接口形状是决定性的**：`RiskEngine` 读 `available_capital` / `total_capital` / `used_capital` / `total_return`
—— 正是 `VirtualPortfolio.get_summary()`（`virtual_portfolio.py:515-535`）的键；
而 `PortfolioManager` 一侧返回 `account_name` / `total_value` / …，**没有那两个键**。

**姿势 = 复用内核单出口** `os_kernel.get_manas_inputs()`（`os_kernel.py:420`），
其 docstring 已把这类事故写成规则：「消除『同一个引擎被两种喂法喂』」。

**修复前的精确后果**（比首轮记的「regime 恒中性」更致命）：
dict 假持仓 → `RiskEngine._get_cash_ratio` 调 `portfolio.get_summary()` → AttributeError 被吞
→ `cash_ratio≡0.5`、`drawdown≡0`；`scanner=None` → `volatility≡1.0`
→ **`risk_temperature ≡ 1.25`** → 永远进不了 `>1.3`/`>1.5` 档
→ **自适应止盈止损从未生效，恒 -8% / +15%**。

影响面：只影响**新开仓**（`_get_adaptive_stop_loss` 唯一业务调用点在 `_on_new_signal:401`），
存量持仓不受影响；且 `AdaptiveCycle` 由操作员从 bandit 管理页手动启动
（`bandit/ui.py:737`）。方向是**收紧**（更保守）。回滚 `NAJA_MANAS_ADAPTIVE_SL=0`。

### 8.4 P0-1 的定案：**结构全修，默认仍关**

> ❗**后续修正（同日）**：本节的「开不开桥」被证明是**假问题**。深挖发现认知→决策
> **本来就有拉取式路径**（不经桥），而其中关键一路（`FirstPrinciplesMind` →
> `fp_insights` → `DecisionFusion`，可达 ±20% 仓位）被决策管线内部的**一对互相掩盖
> 的 bug** 掐断 —— **只修上游会让决策链从「静默」变「崩溃」**。结论：**不开桥**，
> 真正该修的是那两个 bug（已修）。完整证据与四条路径实测见
> **`docs/naja/cognition_to_decision_paths_2026-10-15.md`**。

认知层实际会发的事件只有两类，且**都不带股票代码**：
- `NarrativeStateEvent`：`current_narratives`（叙事**名**）
- `ResonanceDetectedEvent`：`symbols=[block_id]`（**板块ID**）

因此过桥必须做「叙事名/板块ID → 股票代码」解析。解析器**已实现**（三级：
`BlockRegistry.get_blocks_for_narrative` → `block_mapping.get_linked_blocks` +
`dictionary.blocks.get_block_stocks`），关掉的唯一原因是**方向口径**：

> 「叙事转强 = 买还是卖」在代码里**没有任何既有约定**。硬开等于把一条拍脑袋的规则
> 接进真钱链路。故把桥修到「结构正确、只差一个开关」，开关交给
> `NAJA_BUS_BRIDGE`，且「关」是**显式且被记录**的状态
> （`enable_bridge_from_env()` 无论如何都打日志）—— 不再是「只能靠读代码才知道」。

**开桥后的实际效果**（不是直接下单）：认知信号以 `confidence = 强度 × 0.6` 进入交易总线
→ 决策中心 → **仍要过 Manas 闸门 + 融合置信度阈值**。
另注：交易总线对 `StrategySignalEvent` 的去重指纹是
`symbol:direction:分钟`（`trading_bus.py:275`），故同一分钟内同标的同方向会与策略信号合并。

### 8.5 修复顺序（为什么是这个顺序）

```
① 事件家族导出对齐 → ② 发射端参数修正 → ③ 桥内部正确性 → ④ 装配点接线 → ⑤ 方向口径（人拍）
   （R-1，根因）       （tracker/timing）   （通道+解析器）    （env 开关）      （默认关）
```

前三步是纯缺陷、不改既有行为；④ 接线但默认关；⑤ 才是策略决策。
**反过来先开桥，只会得到「开关开了、事件还是收不到」的假绿。**

### 8.6 验证汇总

| 项 | 结果 |
|---|---|
| 桥 10 用例（幂等 / 方向不猜 / 叙事名不当代码 / 板块ID解析 / 无法解析如实丢弃 / 阈值过滤 / 关闭不转发） | 10/10 ✓ |
| Manas 接线 7 项（真实入参 / 缓存 / 回滚开关 / 失败告警 / 兜底 / 三档止损） | 全过 ✓ |
| 新守卫六段**真实注入**负向验证 | 6/6 抓出，还原后 exit 0 ✓ |
| 存量守卫（singleton_registry / undefined_names / dataclass_inheritance / market_time_alias / log_traceback） | 全 exit 0 ✓ |
| `pytest deva/naja/tests/test_decision_fusion.py` | 27 passed ✓ |

### 8.7 仍未处置（需人拍板）

| 项 | 说明 |
|---|---|
| **开桥 `NAJA_BUS_BRIDGE=1`** | 方向口径是策略决策。占位规则：叙事 `sentiment_score` >0.6 买 / <0.4 卖，中间不发；共振 `metadata.sentiment` >0.1 买 / <-0.1 卖 |
| **`NarrativeUpdateEvent` / `TimingNarrativeShiftEvent` 接发射端** | 方法已修对，但仍无调用方（接上＝新增生产者＝新增行为） |
| **`RiskAlertEvent`** | 全库从未构造，补生产者是新增功能 |
| **`_reinforce_narrative` / `_adjust_risk_cognition`** | 空实现，已在 docstring 标注「尚未实现实质动作」，避免被误当成已生效 |
| **`NAJA_MANAS_ADAPTIVE_SL` 默认值** | 现为**默认开**。若倾向更保守，置 `0` 即回到固定 -8%/+15% |
