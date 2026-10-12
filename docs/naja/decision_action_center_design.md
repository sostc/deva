# 决策与行动中心 · 设计方案

> 目标：把当前的「注意力内核 + manas 打分引擎」从 *"要不要动"的门 + 标量*，
> 收口成一条**单一权威的决策与行动链**——从判断、到定标的、到定量、到执行、到反馈闭环。
>
> 性质：**评估 + 分期方案**。D0 是纯文档（零行为变化），D1 起逐期确认。
> 诊断部分全部基于源码行号，不含推测。

---

## 0. 一句话结论

**能。而且这是"接线 / 收口"问题，不是"从零造"问题。**

系统里已经有了一个名义决策中心（`TradingCenter`）、一个名义执行中心（`Bandit`）、
一份决策编排（`DecisionOrchestrator`）、一份决策融合（`DecisionFusion`）。
它们的接口都在、事件都在、落盘表也在。

缺的是**三根线没接**：

1. manas 说"要不要动"，但没人负责"**动什么**"（标的 / 方向 / 量）；
2. 执行层建仓**用固定量 10000**，与 manas 的 `alpha` / `risk_temperature` / `action_type` 完全脱钩；
3. 执行结果**不回流**，决策层学不到、manas 的觉醒维度也永远醒不过来。

所以"变成真正的决策与行动中心" = **把这三根线接上 + 定一个唯一权威 + 清掉挡路的死路径**。

---

## 1. 现状测绘

### 1.1 真实链路（唯一通向"行动"的一条）

```
热点策略 emit Signal
  └─ market_hotspot/strategies/base.py:293 emit_signal
     └─ :388 StrategySignalEvent → trading_bus.publish
        └─ application/event_registrar.py:242 on_strategy_signal
           └─ TradingCenter.process_strategy_signal_event   trading_center.py:351
              └─ process_strategy_signal                     trading_center.py:470
                 └─ _full_decision_pipeline                  trading_center.py:265
                    └─ DecisionOrchestrator.run_full_pipeline decision/orchestrator.py:37
                       ├─ AttentionOS.make_decision → OSAttentionKernel → ManasEngine.compute
                       ├─ FirstPrinciplesMind.think（慢思考，可选）
                       ├─ AwakenedAlaya.illuminate（模式回忆，可选）
                       └─ DecisionFusion.fuse               decision/fusion.py:74
        └─ TradeDecisionEvent 发布 → trading_bus
           └─ bandit/signal_listener.py:219 _on_trade_decision_event
              └─ AdaptiveCycle._on_new_signal               bandit/adaptive_cycle.py:294
                 └─ VirtualPortfolio.open_position(amount=10000)  adaptive_cycle.py:353-364
```

另一条（热点调度链）**不驱动建仓**，只出权重/频率：
`AttentionOS._on_hotspot_computed → StrategyDecisionMaker.schedule`
（`strategy_decision.py:39`，`_allocate_weights :129`，`_allocate_strategies :190`）。

### 1.2 承重点（决定成败的几行）

| 位置 | 现状 | 问题 |
|---|---|---|
| `os_kernel.py:220-258` | `alpha *= manas.alpha`，四维分数装进 `AttentionKernelOutput` | manas 输出被当"乘性权重"消费 |
| `fusion.py:139-154` | **自己**按 `final_confidence` 阈值定 `action_type`（4 档） | 与 manas 的 `action_type` 是**两套定义** |
| `fusion.py:168-176` | 再用 manas 的 `action_type` 打补丁，**只有 `hold` / `act_fully` 生效** | `act_carefully` / `act_minimally` 语义**丢失** |
| `trading_center.py:517` | `approved = fusion.should_act and fusion.fused_confidence >= 0.4` | 阈值 **0.4 硬编码**，且与 fusion 的 0.3/0.5/0.7 分档不一致 |
| `adaptive_cycle.py:353-364` | `open_position(amount=10000)` | **固定量**，与 `alpha`/`T`/`action_type` 无关 |
| `adaptive_cycle.py:350` | `_get_adaptive_stop_loss()` 读 manas 分数 | 止盈止损**用**了 manas，建仓量**没用**——不一致 |
| `manas_engine.py:186-191` | `ActionType = HOLD / ACT_FULLY / ACT_CAREFULLY / ACT_MINIMALLY` | 权威定义在此，但下游不认 |

### 1.3 "行动"的真实含义

全仓**没有券商下单**（无 `place_order/submit_order`；`futu` 仅出现在行情/测试脚本）。

目前的"行动" = **`VirtualPortfolio` 虚拟持仓 + NB 表落盘 + 通知**：
- `bandit/virtual_portfolio.py:190` `open_position` / `:276` `update_price` / `:322` `close_position`
- `state/snapshot.py:505` `record_bandit_decision`（落盘 `BanditDecisionContext`）
- `bandit/notifier.py` 通知

### 1.4 死路径（挡路的陈年断点）

- `TradingCenter.process_market_data`（`trading_center.py`）—— 生产环境**无调用者**。
- `TradingCenter.make_decision`（`trading_center.py:314`）—— **无调用者**。
- `TradingCenter.process_datasource_data`（`trading_center.py:337`）—— 访问
  `self.attention_os.market_scheduler`，而 `AttentionOS` **没有这个属性**，
  异常被 `try/except` 吞掉 → **静默死路**（`datasource/entry.py:797` 还在调）。
- `attention/kernel/kernel.py:21` 的 `AttentionKernel`（889 行）、
  `decision_attention.py:57` 的 `DecisionAttention` —— **无生产实例化**（休眠）。

---

## 2. 缺口清单

| # | 缺口 | 后果 |
|---|---|---|
| **G1** | `action_type` 有三套定义（manas / fusion 自算 / 补丁），无唯一权威 | 中档指令（谨慎/轻仓）在链路上蒸发 |
| **G2** | 没有"动什么"的承载结构（无标的+方向+量的决策产物） | 决策止步于"批准/否决"，标的与量靠下游各猜 |
| **G3** | 执行定量与信号无关（固定 10000） | manas 算得再准，落到仓位上也归零 |
| **G4** | 审批阈值硬编码且与融合分档两套 | 改一处要动多处，且口径不自洽 |
| **G5** | 执行结果不回流 | 决策层学不到；觉醒维度恒 ×1.0（三重断点，见 `manas_upgrade_plan.md`） |
| **G6** | 死路径 / 休眠模块占位 | 阅读成本高，误触时静默失效 |

---

## 3. 目标架构

**三层权威链**（沿用项目既有命名，不新造词）：

```
┌───────────────────────────────────────────────────────────────┐
│ 判断层  ManasEngine  ──  要不要动？为什么？多确信？多危险？      │
│   产出：should_act / action_type(权威) / alpha / T / 四维分数   │
│   职责边界：不做标的与仓位决策，保持"门 + 标量"本色             │
└───────────────────────────┬───────────────────────────────────┘
                            │  唯一权威：action_type 由 manas 定义
┌───────────────────────────▼───────────────────────────────────┐
│ 决策层  DecisionOrchestrator + DecisionFusion                  │
│   产出：DecisionPlan（唯一决策产物）                            │
│     { symbol, side, size_hint, action_type, confidence,        │
│       risk_temperature, gate_reason, reasons, source_signal }  │
│   职责边界：融合外部洞察；不做执行、不落盘                       │
└───────────────────────────┬───────────────────────────────────┘
                            │  单一出口
┌───────────────────────────▼───────────────────────────────────┐
│ 执行层  Bandit / AdaptiveCycle                                 │
│   按 DecisionPlan 定量建仓 / 调仓 / 离场；落盘 + 通知           │
│   size = base × f(action_type, alpha, T)，带上下限              │
└───────────────────────────┬───────────────────────────────────┘
                            │  结果回流
┌───────────────────────────▼───────────────────────────────────┐
│ 反馈  执行结果 → Bandit 学习 + Manas 觉醒/偏差                  │
└───────────────────────────────────────────────────────────────┘
```

**核心契约：`DecisionPlan`**（新增 dataclass，`deva/naja/decision/plan.py`）

| 字段 | 来源 | 说明 |
|---|---|---|
| `symbol` / `side` | 信号 + 判断层 | 动什么 |
| `action_type` | **manas（唯一权威）** | 动多大档位 |
| `size_hint` | 决策层计算 | 建议仓位增量（0~1 权重 或 绝对额），带上下限 |
| `confidence` | fusion | 融合置信度（保留现有语义） |
| `risk_temperature` | manas | 风控可读 |
| `gate_reason` | manas | 为什么不动 / 为什么只轻仓（可解释） |
| `reasons` / `source_signal` | fusion / 上游 | 审计与追溯 |

### 3.1 权威规则（D0 定稿）

**规则一：`action_type` 的唯一权威是 `ManasEngine`。**

四档严格程度（数值越大越激进）：

| 档位 | severity | 含义 |
|---|---|---|
| `hold` | 0 | 不动 |
| `act_minimally` | 1 | 轻仓试探 |
| `act_carefully` | 2 | 谨慎行动 |
| `act_fully` | 3 | 全力行动 |

**规则二：融合层只能下调，不能上调。**

`DecisionFusion` 可以因外部证据（风险温度、逆风 regime、偏差纠正）把档位**降**到更保守的一档，
并**必须**在 `reasoning` 里记录降级理由；**不得**上调。上调只能由判断层给——
否则等于给决策层偷偷加仓权限。

**规则三：只有判断层缺席时才允许兜底自算。**

`kernel_output.action_type` 缺失（attention_os 不可用 / 降级路径）时，
才允许按置信度粗分档，且必须在 `gate_reason` 里标明是兜底。

> 实现：排序与收敛工具在 `deva/naja/decision/plan.py`
> （`action_severity` / `more_conservative`）。未知档位一律按 `hold` 处理（保守失败）。

### 3.2 仓位定量公式（单一口径）

```
multiplier = action_factor(action_type) × alpha_factor(α) × risk_factor(T)
```

| 因子 | 取值 | 说明 |
|---|---|---|
| `action_factor` | hold 0 / minimally 0.25 / carefully 0.6 / fully 1.0 | **主驱动** |
| `alpha_factor` | `clamp(α / 0.45, 0.8, 1.2)` | 轻微修正。α 受 `alpha_min=0.3` 支配，故**不作主缩放**；将来重定标 α 只需改参考值 |
| `risk_factor` | T>1.5→0.4；T>1.3→0.6；T>1.0→0.85；否则 1.0 | 风险刹车 |

最终 `multiplier` 夹到 [0, 1]；`hold` 恒为 0。
执行层 `amount = base_amount × multiplier`，有动作时不低于 `min_amount`。

> 实现：`deva/naja/decision/sizing.py`。
> 回滚开关：环境变量 `NAJA_MANAS_SIZING=0` → 执行层回落固定量（灰度和回滚用）。

---

## 4. 分期计划

| 期 | 内容 | 风险 | 验收 | 回滚 |
|---|---|---|---|---|
| **D0** 定义权威链 | 本文档定稿；明确 `action_type` 唯一 owner = manas；列出 `DecisionPlan` 契约草案 | 零行为变化 | 文档评审通过 | 删文档 |
| **D1** 决策产物契约化 | 新增 `DecisionPlan` dataclass；`process_strategy_signal` **附带**返回 plan（向后兼容，不改 `approved` 逻辑） | 低（只增不改） | 既有消费者全绿；新契约有单测 | 去掉附带字段 |
| **D2** 让 action_type 真正驱动定量 | ①fusion 不再自行重定义 action_type（或显式声明 fusion 为 owner）②`AdaptiveCycle` 用 `size = base × f(action_type, alpha, T)` 替代固定 10000 ③`:517` 阈值改配置 | **高（真改行为）** | 快照基线差异逐条解释；单测全绿；端到端 T 非退化 | 保留 `MANAS_SIZING_ENABLED` 开关回落固定量 |
| **D3** 闭环反馈 | 执行结果事件 → Bandit 学习 + Manas 觉醒/偏差；先解觉醒三重断点 #2/#3 | 中 | 觉醒环节从 ×1.0 变活；有端到端验证 | 开关关闭 |
| **D4**（可选）实盘执行 | 券商适配器（`futuapi`），把 `VirtualPortfolio` 换成 `BrokerPortfolio` 接口 | 高 | 纸面/实盘双轨验证 | 接口回退 |

**依赖**：D2 依赖 D1；D3 依赖 D1（且依赖 `manas_upgrade_plan.md` 的觉醒三重断点）。

---

## 5. 明确不做 / 边界

- **不重构 manas 的打分公式**。`α` 下限支配问题（自然落 [0,0.6] 撞 `alpha_min=0.3`）是公式维度，
  复用方若需区分度应重新定标；本方案只让 `action_type` 的**权威定义**进入决策与定量。
- **不在核心模块新增 `SR()`**（架构基准 §6.2）。新增装配走 application 层注入。
- **不物理搬迁模块**。只在语义上收口，不改目录（爆炸半径大，收益只是目录语义）。
- **D4 实盘默认不做**。"行动中心"默认指虚拟组合的动作闭环；接券商是独立立项，需单独确认。

---

## 6. 与既有架构基准的一致性

| 基准条款 | 本方案如何遵守 |
|---|---|
| §3.1 Domain/Decision 层职责 | `DecisionPlan` 属决策层产物，不放应用层 |
| §6.2 核心模块不新增 `SR()` | 装配在 `container.py` 注入 |
| §6.3 事件订阅集中管理 | 反馈事件在 `event_registrar.py` 注册 |
| §6.4 UI 不深入核心对象 | `DecisionPlan` 经 query service / dict 暴露给 UI |

---

## 7. 一句话总结

> 现在这套系统**会判断、会算分、会批准、会模拟建仓**，但四件事各说各话；
> 把它们缝成一条"判断 → 决策 → 定量 → 执行 → 反馈"的单一权威链，
> 就是"变成真正的决策与行动中心"的全部内容。
> **风险不在造不出，而在缝合时动了行为——所以从 D0 文档起步，逐期确认。**
