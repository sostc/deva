# 认知 → 决策链路定案（2026-10-15）

> 起因：审计报告 `architecture_gap_audit_2026-10-15.md` 的 P0-1「BusBridge 从未启用」。
> 深挖后结论：**「开不开桥」是个假问题**。真正的断点在决策管线内部，与桥无关。
> 本文取代报告中关于 P0-1 的判断。

---

## 0. 一句话结论

**不开桥。** 认知（叙事）影响决策的路径**本来就存在**，且是**拉取式**的——
但其中最关键的一路（FirstPrinciplesMind）被一个**参数错位**掐断，
并且这个错误被**第二个 bug 掩盖**，两者必须成对修复。

---

## 1. 为什么原问题是假问题

原判断「认知层产出到不了交易侧」**不准确**。实际是：

- 认知层 → 决策层**有 4 条候选路径**，全都不经过 BusBridge
- BusBridge 试图做的事（把认知事件直接变成带方向的 `StrategySignalEvent`）**在架构上越权**：
  方向判定的唯一合法来源是**策略层** —— `market_hotspot/strategies/base.py:386`
  `direction = SignalDirection.from_str(signal.signal_type)`
- 所以桥不是"一条没启用的路"，而是"**一条不该存在的路**"

---

## 2. 四条路径实测

| # | 路径 | 形态 | 实测结果 |
|---|---|---|---|
| **A** | `BusBridge`：认知事件 → `StrategySignalEvent` | 事件推送 | ❌ 从未启用 **且设计越权**（越过策略层直产方向） |
| **B** | `NarrativeTracker` → `market_state['narratives']` → `ManasEngine.compute(narratives=)` | 拉取 | ⚠️ **链路通但末端未消费**：`manas_engine.py:1954` 存入 `_current_narratives` 后**从未被任何计算读取** |
| **C** | `NarrativeTracker` → `FirstPrinciplesMind` → `fp_insights` → **`DecisionFusion`（可达 ±20% 仓位）** | 拉取 | ❌ **被参数错位掐断**（本次修复，见 §3） |
| **D** | `NarrativeTracker` → `world_narrative` → `ConvictionValidator` | 拉取 | ❌ 存入零消费字段；所在 `AttentionFusion` **整层产出无任何消费者** |

### 2.1 路径 B 的细节（通而不用）

```
trading_center.py:737  narratives = self._get_current_narratives()   # 读单例 tracker
trading_center.py:741  market_state['narratives'] = narratives
orchestrator.py:43     kernel_output = self.attention_os.make_decision(market_state)
os_kernel.py:221-222   manas_engine.compute(narratives=market_state.get("narratives"), ...)
manas_engine.py:1954   if narratives is not None: self._current_narratives = narratives
manas_engine.py:X      ← `_current_narratives` 全文仅 3 处出现：:1280 初始化 / :1802 setter / :1955 赋值
```

**赋值后没有任何计算读取它。** 同层的 `narrative_risk` / `hot_narratives` 虽进 Manas 输出，
但决策层（`decision/`）对其**零引用**；`DecisionFusion` 实际只读
`kernel_output.timing_score` 与 `regime_score`（`fusion.py:117,125`），而这两者由
`TimingEngine.compute(session_manager, scanner)` / `RegimeEngine.compute(scanner, macro_signal)`
产出，**参数里根本没有叙事**。

### 2.2 路径 D 的细节（整层空转）

`ValidationResult.summary()` 零调用、`AttentionKernelOutput` 在 `web_ui/` · `home/` 零引用、
`.fusion_output` 全库（除定义处）零读取。即 `AttentionFusion` + `ConvictionValidator`
（千余行）的产出**没有任何消费者**。其中 `conviction_validator.py:226`
`world_hot_narratives` 算完即弃，`:302-303` 写入的 `market_narrative_heat` /
`watched_narrative_heat` 全库无读取。

> 这解释了"认知看起来影响不了交易"的**错觉来源**：大家默认注意力融合层是决策输入，
> 实际上它是**展示层遗留物**。真正的决策链是 `ManasEngine` + `DecisionOrchestrator` + `DecisionFusion`。

---

## 3. 本次真正修复的：一对互相掩盖的 bug

### bug A —— 参数错位（`decision/orchestrator.py`）

```python
# 原写法
fp_result = fp_mind.think(market_state, snapshot)
#                        ^^^^^^^^^^^^ ^^^^^^^^
#                        形参1: market_data
#                                    形参2: narratives: List[str]  ← 收到的却是 {'symbol':…, 'price':…}
```

`FirstPrinciplesAnalyzer.analyze:896` `if narratives:` 对**非空 dict 判真**，
`_analyze_narratives:990` 随即 `enumerate(dict)` 遍历出 `'symbol'` / `'price'`。

**实测后果（而非推测）**：

| 输入 | 产出洞察数 |
|---|---|
| `think(ms, {'symbol':'600487','price':10.0})`（原 bug） | **0** |
| `think(ms, ['AI芯片','贵金属','算力'])`（真实叙事） | **1** |

原因：`_analyze_narratives:1006` 的「多重叙事同时存在」洞察要求 `len(narratives) >= 3`，
而 dict 只有 2 个键 → **恒不触发**；同时 `:990-992` 把 `'symbol'`/`'price'`
注册进 `contradiction_detector` 作为伪叙事（**状态污染**）。

→ `fp_insights` **恒为空列表**。认知通过 FP 路径对决策的贡献**为零**，且全程无声。

### bug B —— 类型不匹配（`decision/fusion.py`）

`DecisionFusion.fuse` 全程按 dict 访问（`:95,96,97,102,166,169,172,190` 共 6 处
`insight.get(...)` / `insight["type"]`），而生产者
`FirstPrinciplesAnalyzer.analyze` 返回的是 `FirstPrinciplesInsight` **dataclass 对象**。

**实测**：

```
DecisionFusion().fuse(fp_insights=[FirstPrinciplesInsight(...)], kernel_output=K())
→ AttributeError: 'FirstPrinciplesInsight' object has no attribute 'get'
```

### 为什么必须成对修

**bug B 被 bug A 掩盖**：`fp_insights` 恒空 → `for insight in fp_insights` 从不执行 → 从不触发。

> ❗**只修 A 不修 B，会让决策链从"静默无认知"变成"直接崩溃"——比修复前更糟。**
> 这是审计报告里那条纪律的又一实例：**一项缺失会掩盖另一项缺失**。

### 修复方式

| 文件 | 改动 | 回滚开关 |
|---|---|---|
| `decision/orchestrator.py` | `think(market_state, narratives=market_state.get("narratives") or None)`；snapshot 不再误传（它已在 `_process_sensation_modules:163-164` 被消费） | `NAJA_FP_NARRATIVES=0` |
| `decision/fusion.py` | 新增 `_normalize_fp_insight()`，`fuse` 开头顶层归一化一次（对象→dict，`insight_type`→`type`，`ThoughtLevel`→`.value`），兼容 dict 透传 | 随上游开关 |

**验证**：归一化三态（对象/dict/None）正确；`fuse` 吃对象列表不再抛异常；
**纯 dict 输入回归正常**（`first_principles` opportunity 仍得 `+0.15 +0.05`）；
27 项存量测试通过。

---

## 4. 修复后的实际影响力（如实说明）

当前叙事输入能产生的最高级别洞察是 `pattern`
（`ThoughtLevel.PATTERN` = `"pattern"`，来自「多重叙事同时存在」），
而 `DecisionFusion.LEVEL_BONUS` 只给 `first_principles`(0.15) / `causal`(0.08) / `surface`(0) 加分
—— **`pattern` 不在表内，加成为 0**。

所以本次修复的**直接**效果是：
1. **消除崩溃风险**（这是无条件的收益）
2. **恢复通道**：叙事洞察能进入 `fused_confidence` 的推理链（`reasoning` 可见）
3. **解除掩盖**：真正高价值的是 `first_principles` / `causal` 级洞察
   （`+0.15/+0.08` 置信度、`+20%/+10%/-30%` 仓位调整），它们需要 `signals` /
   `liquidity_data` 等更多输入 —— 修好管道后这些才有机会流通

---

## 5. 不做的事及理由

| 项 | 为什么不做 |
|---|---|
| **开 BusBridge** | 越权（认知层不该判方向）+ 冗余（已有 3 条拉取路径）+ 即使开了也到不了决策（路径 B/D 末端不通） |
| **让叙事影响 Manas 的 `_current_narratives`** | 需要先定义「叙事 → 风险/时机/仓位」的语义 —— 属**策略决策**，不是 bug 修复 |
| **让 `world_narrative` 进 `conviction_score`** | 同上；且该字段所在整层（路径 D）无消费者，改了也不影响交易 |
| **删掉空转的 `AttentionFusion`** | 千余行、可能承载展示意图 —— 应先确认"接展示"还是"废弃"，不宜擅自删 |

---

## 6. 运行时证据（链路确实在跑）

| 证据 | 值 |
|---|---|
| `~/.naja/focused_news_cache.json` | 200 条，`updated_at` = 2026-10-15 01:42（`TextFocusedEvent` 在发） |
| `NB('naja_narrative_tracker_state')` | `saved_at` = 2026-10-15 01:45:54，10 条叙事实时更新（新能源/芯片/AI…） |
| 服务日志 | `NarrativeTracker 事件订阅完成`、`ManasEngine 事件订阅完成（1 个实例）` |
| 决策链日志 | `[TradingCenter] 收到策略信号` 多条；`信号否决` 352 次（全部因 Manas 档位 hold） |
| `FirstPrinciples` 日志 | **0 次** —— 与 bug A（洞察恒空）吻合 |

---

## 7. 建议

1. **不开桥**；`bus_bridge.py` 模块 docstring 已声明其非正路身份，保持默认关。
2. **决策管线的叙事通道**已修通，但需**策略层拍板**是否给 `pattern` 级洞察权重
   （`LEVEL_BONUS` 加 `"pattern": x`）—— 这会改变交易行为，不应由实现方擅定。
3. **路径 D（`AttentionFusion` 整层）** 需要产品决策：接展示 or 废弃。
4. **常驻守卫** `scripts/verify/verify_cognition_decision_chain.py`：
   钉住「叙事 → `market_state` → Manas」与「FP 洞察 → fuse」两条链的关键环节，
   防止再次被静默掐断。

---

## 附：本次改动文件

- `deva/naja/decision/orchestrator.py` —— 参数错位修复 + `NAJA_FP_NARRATIVES` 开关
- `deva/naja/decision/fusion.py` —— `_normalize_fp_insight()` 归一化
- `scripts/verify/verify_cognition_decision_chain.py` —— 新增守卫
