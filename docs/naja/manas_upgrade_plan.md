# Manas 升级规划

> 性质：**评估 + 分期方案**。P0 已落地（零行为变化），P1 起会改变运行时行为，按
> `AGENTS.md`「先评估、再执行」逐期确认。
>
> 诊断部分全部基于源码与实际校验脚本输出，不含推测。

---

## 0. 起点：manas 是什么，以及它的缺口在哪

上一轮盘点的结论是：`ManasEngine` 本质是一台通用的**「行动门 + 置信缩放器」**——
输入多路分数，输出"要不要动"与"缩放到多少"。它现在被当作交易模块使用，代码里的
交易语义（现金比、回撤、bandit 命中率）都在**子引擎内部**，而 `compute()` 的外部
接口已经是抽象对象（clock / scanner / portfolio / tracker）。

问题出在**接线**：`compute()` 的取数全部是「鸭子类型 + `try/except` 兜底」。

```python
try:
    vol = scanner.get_market_volatility()     # 方法不存在 → AttributeError
except Exception:
    return 1.0                                # 静默吞掉，返回默认值
```

方法缺失与「数据恰好等于默认值」在外部**完全无法区分**，唯一的痕迹是一行
`log.debug`。于是「接口接错了」看起来就像「市场恰好很平静」。

---

## 1. 诊断：4 处静默失效 + 2 条不一致的调用路径

### 1.1 四路输入在真实运行路径上退化为常数

校验脚本：`scripts/verify/verify_manas_input_contract.py`

| # | 维度 | 期望来源 | 实际情况 | 退化结果 |
|---|------|---------|---------|---------|
| 1 | 时间压力 | `MarketSessionManager.get_market_status` / `get_session_remaining_seconds` | `os_kernel.py:63-65` 传的是 `TradingClock`，而 `TradingClock` 只有 `cn_phase` / `us_phase` / `get_global_status`，**没有这两个方法** | `time_pressure` 恒 **0.5** |
| 2 | 波动率 | `scanner.get_market_volatility()` | 全仓检索：**该方法不存在于任何类**（`manas_engine.py:513` 与 `:971` 是仅有的两处调用） | Timing 波动率维恒 **0.5**；RiskEngine 波动率恒 **1.0**（`>1.5` / `>2.0` 两个保守档永不触发） |
| 3 | 持仓 | `VirtualPortfolio` | `os_kernel.py:423-424` `_get_portfolio()` **直接 `return None`** | `cash_ratio` 恒 0.5、`drawdown` 恒 0 → 风险温度 **T 恒 1.25** |
| 4 | 策略表现 | `BanditPositionTracker` | `os_kernel.py:433-434` `_get_bandit_tracker()` **直接 `return None`** | `hit_rate` 恒 0.5、`rolling_pnl` 恒 0、`bandit_conf` 恒 0.5 → **confidence 恒 0.35** |

`VirtualPortfolio` 与 `BanditPositionTracker` **本身满足契约**（校验脚本已验证），
它们只是**没被传进来**。所以问题分两类：

- **契约缺口 2 处**：#1 传错了对象、#2 方法根本不存在；
- **装配缺口 2 处**：#3 #4 是 `return None` 占位，真实对象在 container 里是有的。

### 1.2 同一个引擎，两条入参不同的调用路径

```
路径 A（内核打分，真正影响 α）
  os_kernel.py:42      self.manas_engine = ManasEngine()          ← 无依赖注入
  os_kernel.py:194     manas_engine.compute(
                           session_manager=self._trading_clock,   ← 错对象
                           portfolio=None,                        ← 恒 None
                           scanner=self._get_scanner(),           ← 缺 volatility
                           bandit_tracker=None,                   ← 恒 None
                       )
  → manas_output.alpha 直接乘进注意力权重 α（os_kernel.py:203）

路径 B（UI / manager）
  container._create_manas_manager()  ManasManager(kernel=..., trading_clock=...,
                                                  virtual_portfolio=..., bandit_tracker=...)
  manas_manager.py:120-123           get_manas_engine() 优先返回 kernel 的引擎
  manas_manager.py:148-154           compute() 传入真实 portfolio / bandit_tracker
```

**关键**：`ManasManager.get_manas_engine()` 返回的就是路径 A 那一个引擎
（上一轮 P1 已经把"两个引擎"合并成一个）。所以现在是**同一个引擎被两条路径以不同
入参调用**——路径 A 的 T/confidence/时间压力/波动率是常数，路径 B 的部分维度是活的。
内核打分与 UI 展示仍然可能给出不一致的结论。

> 上一轮修掉的是「两个引擎各算各的」，这一轮暴露的是「一个引擎两种喂法」。
> 属于同一类病灶的残余。

### 1.3 影响面判断

`alpha = confidence_score × harmony_strength`，`harmony_strength` 里
`timing` 权重 0.4、风险反函数权重 0.35。也就是说：

- **timing 有两个维度（0.4 权重里的一部分）是常数** → 择时能力被削弱一半；
- **confidence 在路径 A 恒 0.35**（正常区间是 0~1.5）→ α 被系统性压在下限附近；
- **T 恒 1.25** → 无论持仓多危险、市场多疯狂，风控档位都不动。

结论：**不是"效果不好"，是"一半输入没接上"。** 这也解释了为什么 manas 的输出
看起来"温吞"——它的参数空间有一半是扁的。

---

## 2. 分期规划

### P0 — 契约固化（**已完成**，零行为变化）

| 项 | 内容 |
|---|---|
| 目标 | 把「静默回退」变成「可检测的违约」，为后续各期提供验证基线 |
| 新增 | `deva/naja/attention/kernel/manas_inputs.py`：`ClockView` / `MarketView` / `PortfolioView` / `StrategyView` 四个 `runtime_checkable` Protocol + 静默回退对照表 + `DictBackedInputs` 纯 dict 适配器 |
| 新增 | `scripts/verify/verify_manas_input_contract.py`：类级契约校验，输出违约表与后果 |
| 新增 | `test_manas_engine.py` 追加 `TestManasInputContract` / `TestManasEngineDecoupling` |
| 风险 | **零**。不 import 到任何生产路径，不改 `manas_engine.py` 一行 |
| 验证 | 契约校验脚本；`test_manas_engine.py` 38 passed；全量单测无新增失败 |

`DictBackedInputs` 是刻意放在 P0 的：它既是单测夹具，也是 P3「抽成通用原语」的
最薄适配层样板——**现在就能证明 `ManasEngine` 可以脱离任何交易对象运行**。

### P1 — 接线修复（**需确认**，真实行为变化）

这是本规划的核心。四件事，建议按此顺序：

| 子项 | 改动 | 风险 |
|---|---|---|
| **P1.1** 补 `GlobalMarketScanner.get_market_volatility()` | 已有 `self._volatility_tracker`（`global_market_scanner.py:371`）与 `MarketVolatilityTracker.update()`（返回 `volatility`），包一个只读方法即可 | 低。新增只读方法，不改现有调用 |
| **P1.2** session_manager 换成 `MarketSessionManager` | 用现成的 `scanner.session_manager`（`global_market_scanner.py:400-404`，懒加载单例）。**不要**给 `TradingClock` 硬塞两个方法——那是把时段语义混进 clock | 低。改 `os_kernel._get_session_manager` 的返回 |
| **P1.3** 装配真实 portfolio / tracker | `OSAttentionKernel.__init__` 的 `ManasEngine()` 改为接受注入；`_get_portfolio()` / `_get_bandit_tracker()` 去掉 `return None`。装配点在 `container._create_manas_manager()` 附近，按 §6.3 走 application 层 | **中**。这是唯一需要动装配链的一步 |
| **P1.4** 统一两条路径的入参 | 让 `os_kernel.process()` 与 `ManasManager.compute()` 共用同一套依赖（同一个 getter），消除"一引擎两喂法" | 中。会改变 UI 与内核的一致性 |

**风险与必须做的事**：

1. 这会改变 `manas_score` → `alpha` → 注意力权重 → 落盘决策。
   **必须重建 `scripts/verify/manas_compute_baseline.json` 并逐字段解释差异**
   （按项目既有约定：动 manas 打分前先 `--save`，改完 `--check`）。
2. 差异方向预期：α 不再被压在下限、T 会随持仓/波动真实变化。
   如果差异**超出预期范围**（例如 T 超出 `[0.5, 2.0]` 或 α 大面积撞 clamp），
   说明接线引入的不是"复活维度"而是新偏差，需要停下来查。
3. 回退方案：P1 的改动集中在 3 个文件（`global_market_scanner.py` /
   `os_kernel.py` / `container.py`），`git revert` 单个 commit 即可回到现状。

**验收标准**：

- `verify_manas_input_contract.py --strict` **退出码 0**（当前是 2 处违约）；
- `TestManasInputContract.KNOWN_GAPS` 收紧为空集；
- 单测全绿 + 快照基线差异逐条有解释。

### P2 — 只增不改的可见性（低风险）

| 子项 | 内容 | 为什么值得做 |
|---|---|---|
| **P2.1** 行为偏差镜子 | 把 `MetaManas` 的 `bias_state` / `bias_direction` 从"内部打分乘子"提升为**对外可读信号**（导出 + UI 提醒）。现在 `get_state()` 已经有了，缺的是把它接到人看得见的地方 | 这是当前最被低估的用途：同一份检测，对内是纠偏、对外是"你最近连赢后仓位在放大"的教练 |
| **P2.2** gate 审计留痕 | 把 `action_gate_reason` 按次落库，形成"为什么不动"的可解释记录 | 风控留痕几乎零成本，且是合规友好的 |

两项都**不动打分链路**，只是读取既有输出，因此风险独立于 P1。

### P3 — 抽成通用原语（跨域，中期）

| 子项 | 内容 |
|---|---|
| **P3.1** | 用 P0 的四个 Protocol + `DictBackedInputs` 把 `ManasEngine` 从 `attention/kernel/` 提到决策层通用位置，去掉 `bandit` / `virtual_portfolio` 等交易词汇的硬依赖（子引擎的数据源全部走契约） |
| **P3.2** | 低功耗门控：用 manas 的"要不要动"决定系统是否唤醒干重活（衔接 `upstream_low_power_mode_design.md`） |

**前置条件**：P1 必须先完成。在输入还是常数的情况下抽通用原语，等于把一个
"半盲"的引擎搬到新地方——复用会复制缺陷，而不是复制能力。

---

## 3. 全局验收标准

| 期 | 标准 |
|---|---|
| P0 | 契约校验可运行并稳定复现 2 处违约；单测 38 passed；运行时行为零变化 |
| P1 | 契约违约清零（`--strict` 通过）；快照基线差异有逐条解释；α 与 T 落在合理区间 |
| P2 | 偏差信号可在 UI 读到；gate 理由按次可查；打分链路 diff 为空 |
| P3 | `ManasEngine` 可在无任何交易对象的情况下跑出非退化分数（P0 已初步证明） |

---

## 4. 明确不做的事（边界）

- **不重构打分公式**。融合权重、调节链、门控阈值一律不动——本次只修"输入没接上"，
  不碰"怎么算"。两者混在一起会让基线差异无法归因。
- **不在核心模块新增 `SR()`**（架构基准 §6.2）。P1.3 的装配走 application 层注入。
- **不删除任何兜底默认值**。兜底本身是合理的（回测、冷启动都要用）；
  要修的是"真实路径上也在兜底"。
- **不动四维门控 / AdaptiveManas**。它们与本次诊断无关，避免扩大爆炸半径。

---

## 5. 一句话总结

> 上一轮修的是「两个引擎各算各的」；这一轮要修的是「一个引擎被两种喂法喂」。
> 先把输入接上（P1），再谈复用（P3）——**在输入是常数的情况下谈架构升级，
> 升级的只是复杂度，不是能力。**
