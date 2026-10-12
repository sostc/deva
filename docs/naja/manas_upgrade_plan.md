# Manas 升级规划

> 性质：**评估 + 分期方案 + 执行记录**。P0–P3 已全部落地；P1/P3 改变运行时行为，
> 已按 `AGENTS.md`「先评估、再执行」逐期确认并各自留 commit。
>
> 诊断部分全部基于源码与实际校验脚本输出，不含推测。
>
> | 期 | 状态 | commit |
> |---|---|---|
> | P0 契约固化（零行为变化） | 已完成 | `b7a2f45` |
> | P1 接线修复（含 5 处计划外 bug） | 已完成 | `67a8699` |
> | P2 可见性（含 2 处计划外 bug） | 已完成 | `9baecf3` |
> | P3 通用原语（可验证子集，含 1 处计划外 bug） | 已完成 | `480079f` |
> | P3 复查更正（觉醒维度误判 + 计数口径） | 已完成 | `2a1d75d` / `19522ad` |
>
> 一句话验收：**快照基线 diff=0（15 场景）；契约 `--strict` 退出码 0；全量单测 206 passed。**
>
> 计数口径：文中「全量单测」= `pytest deva/naja/tests --ignore=test_action_executor.py`
> （该文件是既有故障，与本轮无关）；「manas 单测」= 只跑 `test_manas_engine.py`。
> 两个口径的实测值：全量 186(P0) → 199(P1/P2) → 206(P3)；manas 单文件 38 → 51 → 58。

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

## 1. 诊断：4 处静默失效 + 2 条不一致的调用路径（执行期又发现 8 处，见 §1.4）

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

### 1.4 执行期新发现的 bug（计划外，已随期修复）

诊断阶段定位的是「4 处接线缺口」。真正动手接线时，又暴露出 **8 处**此前看不见的
缺陷——它们全部属于同一族：**静默失效 / 口径不一致 / 死代码**。

| # | 期 | 问题 | 后果 | 修法 |
|---|---|---|---|---|
| 5 | P1 | `GLOBAL_MARKET_CONFIGS` 里**没有 `china_a`** | manas 查 `china_a` → `MarketStatus.NA` → 时间压力恒 0.2 | 补 `china_a` 时段配置 |
| 6 | P1 | `MarketInfo.get_current_status()` **不判周末** | 周末所有市场被判 OPEN | 加 `weekday() >= 5 → CLOSED` |
| 7 | P1 | `_get_market_status_map()` 返回**枚举对象**而非 `.value` | 下游 `v == "open"` 恒 False → open_count 恒 0 | 出口统一 `.value` 归一 |
| 8 | P1 | `VirtualPortfolio.get_summary()` **缺 `total_capital`** | 调用方兜底分母=1 → `cash_ratio` 变成资金绝对额 → `base_T` 大负 → **T 撞下限 0.5** | 补字段 + `_get_cash_ratio` 健壮回退并 clamp |
| 9 | P1 | `total_return` **百分数 vs 小数**口径冲突 | manas 以小数阈值配 `abs(raw)`，任何非零收益都触发 `>0.1` 加档 → T 恒 ×1.3 | manas 侧 `/100` 归一（策略阈值不动） |
| 10 | P2 | UI manas 面板读**不存在的属性**（`_time_pressure` / `_volatility` / `_density` / `_structure` / `_trend`） | 面板恒空（死面板） | 子引擎记录 `_last_components` + `get_last_components()`，UI 改读它 |
| 11 | P2 | `awakening.py` 的 `bias_text` 映射**键写错**（`bullish`/`bearish` vs `neutral`/`greed`/`fear`） | 永远落默认分支 | 修正映射键 |
| 12 | P3 | `_get_awakening_level()` 导入**全仓不存在的** `get_awakening_controller` | ImportError 被吞 → 恒 `dormant`，调节链 awakening 环节恒 ×1.0 | 删死导入，改显式 `set_awakening_level_provider()`；**并查明生产者其实存在**（`alaya.AwakeningEngine`），只是三重断点未解，见 P3 小节边界 #2 |

教训（与 `manas_inputs.py` 模块 docstring 同源）：**`try/except` 兜底 + 鸭子类型 = 静默失效**。
「方法不存在」与「数据恰好等于默认值」必须可区分——要么抽契约（P0），
要么把兜底写成显式、可读、留痕的降级（P1/P3）。

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

### P1 — 接线修复（**已完成** `67a8699`，真实行为变化）

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

**实际落地**：

| 子项 | 落地内容 |
|---|---|
| P1.1 | `MarketVolatilityTracker.get_volatility()`（只读，不写历史）+ `GlobalMarketScanner.get_market_volatility()` |
| P1.2 | `os_kernel._get_session_manager()` 改返回 `scanner.session_manager`（`MarketSessionManager`）；`TradingClock` 被划为「不再用于本角色」的信息性目标（不给它塞时段方法），见 `INFORMATIONAL_TARGETS` |
| P1.3 | `OSAttentionKernel.__init__` 接受 `session_manager/portfolio/bandit_tracker`；`_get_portfolio()` / `_get_bandit_tracker()` 去掉 `return None`；新增 `set_manas_dependencies()`，由 `container._create_manas_manager()` 调用注入 |
| P1.4 | 新增 `OSAttentionKernel.get_manas_inputs()` 作为**单一事实来源**，`process()` 与 `ManasManager.compute()` 共用 |
| 计划外 | 见 §1.4 的 #5–#9（全在 P1 修复） |

**验证结果**：契约 `--strict` 退出码 0；契约脚本新增「运行期接线检查」与「行为增量」
两段，实测四路输入全部复活（场景 B：timing 0.5→0.725、T 1.25→1.10、
confidence 0.35→0.6136、manas_score 0.294→0.5126、α 0.300→0.3145 离开下限）；
快照基线差异逐条解释后重建；**manas 单测 38 → 51、全量单测 186 → 199 passed**。

### P2 — 只增不改的可见性（**已完成** `9baecf3`，低风险）

| 子项 | 内容 | 为什么值得做 |
|---|---|---|
| **P2.1** 行为偏差镜子 | 把 `MetaManas` 的 `bias_state` / `bias_direction` 从"内部打分乘子"提升为**对外可读信号**（导出 + UI 提醒）。现在 `get_state()` 已经有了，缺的是把它接到人看得见的地方 | 这是当前最被低估的用途：同一份检测，对内是纠偏、对外是"你最近连赢后仓位在放大"的教练 |
| **P2.2** gate 审计留痕 | 把 `action_gate_reason` 按次落库，形成"为什么不动"的可解释记录 | 风控留痕几乎零成本，且是合规友好的 |

两项都**不动打分链路**，只是读取既有输出，因此风险独立于 P1。

**实际落地**：

| 子项 | 落地内容 |
|---|---|
| P2.0 死面板修复 | 四个子引擎在 `compute()` 里记录 `self._last_components` 并暴露 `get_last_components()`；UI `_get_manas_engine_state()` 改读它（原先读不存在的私有属性 → 面板恒空）。实测恢复为 time_pressure 0.2 / cash_ratio 0.59 / drawdown 0.0488 / T 1.205 |
| P2.1 | `MetaManas.bias_message()` 输出教练语（GREED/FEAR/NEUTRAL 三态）；`ManasEngine.get_state()` 增 `bias` / `gate_audit` 两键；`awakening.py` 增「🚦 行动门」「🪞 行为偏差镜子」两块，并修 `bias_text` 映射键错 |
| P2.2 | 新增 `attention/kernel/manas_gate_audit.py`：`GateAuditLog` 有界 deque（maxlen=500）+ 连续同判折叠（`occurrences`）+ 每 50 次落盘（`NB("naja_manas_gate_audit")`）。**旁路设计：任何异常只丢一条记录，绝不影响决策** |
| 计划外 | 见 §1.4 的 #10–#11 |

**验证结果**：快照 diff=0；新增 `TestVisibility` 6 例；全量单测 199 passed。

### P3 — 抽成通用原语（**已完成可验证子集** `480079f`，跨域，中期）

| 子项 | 内容 | 状态 |
|---|---|---|
| **P3.1** | 去掉 `manas_engine.py` 对交易/认知层的**硬依赖**：跨层导入（cognition / events / tables / awakening）一律降为可选，缺席时显式降级（置空 / 记日志），不崩溃、不静默 | 已完成 |
| **P3.2** | 运行期无对象证明：裸构造 `ManasEngine()` + `DictBackedInputs`，四维分数非退化且跨场景有差异 | 已完成 |
| **P3.3** | 复用样板写进文档（见下文小节） | 已完成 |
| **P3.4** | 低功耗门控：用 manas 的"要不要动"决定系统是否唤醒干重活（衔接 `docs/naja/upstream_low_power_mode_design.md`） | **未做**（设计文档在，门控接线属独立工作项，未纳入本轮） |

**前置条件**：P1 必须先完成。在输入还是常数的情况下抽通用原语，等于把一个
"半盲"的引擎搬到新地方——复用会复制缺陷，而不是复制能力。（P1 已完成，前置满足。）

**计划外修复**：§1.4 的 #12 —— `_get_awakening_level()` 死代码。

**曾经如实记录的两处「未解耦」**（现状如下）：

1. ~~**加载期耦合仍在**。~~ **已解（2026-10-12 抽象轮）**。原先
   `import deva.naja.attention.kernel.manas_engine` 会先执行
   `deva/naja/attention/__init__.py`，而它 eager 导入 `.os`（→ os_kernel → bandit …）
   与 `.orchestration`——实测 **3.4s / 3158 个模块**，其中 10 个是交易域模块。
   现已把 `attention/__init__.py` 与 `kernel/__init__.py` 改成
   `deva/naja/__init__.py` 那样的 **PEP 562 惰性导出**，并抽出公共门面
   `deva.naja.manas`。改造后：**~0.9s / ~1338 模块 / 交易域模块 0**。
   验证：`scripts/verify/verify_manas_standalone.py --strict`（6 组检查，含子进程
   与静态守卫）。复用指南见 `docs/naja/manas_reuse_guide.md`。
2. **没有把引擎物理挪出 `attention/kernel/`**。移动文件会改动大量 import 路径，
   收益只是目录语义；本轮只保证「可脱离交易对象运行」+「加载期不拖交易域」，
   不搬文件。物理抽成独立包（可 pip 装）属独立立项，见复用指南 §7。

#### 复用样板：把 ManasEngine 搬出交易域

运行期要复用的只有两样：**四个 Protocol** 和 **`ManasEngine.compute()`**。
宿主只要能提供这四路数据，就不需要 `VirtualPortfolio` / `BanditPositionTracker` /
`GlobalMarketScanner` / `MarketSessionManager` 中的任何一个。

最小可运行样板（与 `TestObjectFreeReuse` 完全一致）：

```python
from deva.naja.attention.kernel.manas_engine import ManasEngine
from deva.naja.attention.kernel.manas_inputs import DictBackedInputs

src = DictBackedInputs(
    # —— ClockView ——
    market_status="open", remaining_seconds=5400,
    # —— MarketView ——
    market_volatility=0.8,
    ticks={"600000": 1.2, "000001": 0.9},
    us_trading_phase="trading",
    # —— PortfolioView ——（total_return 是百分数：6.0 表示 +6%）
    available_capital=70.0, total_capital=100.0, total_return=6.0,
    # —— StrategyView ——
    position_returns=[0.02, 0.03, -0.01], total_trades=30,
)

out = ManasEngine().compute(
    session_manager=src, scanner=src, portfolio=src, bandit_tracker=src
)
print(out.action_type, out.harmony_strength, out.alpha, out.action_gate_reason)
```

`DictBackedInputs` 一个实例同时充当四个角色。真实宿主只需实现
`manas_inputs.INPUT_CONTRACTS` 里列的方法（4 契约 / 9 个方法），
**不必继承任何基类**——`runtime_checkable` Protocol 只做结构检查。
接入新数据源时，先跑 `scripts/verify/verify_manas_input_contract.py` 确认无违约。

**宿主可选的注入点**（不注入则走内置中性值）：

| 注入点 | 作用于 | 缺省行为 |
|---|---|---|
| `compute(session_manager=...)` | 时间压力 | 恒 0.5 |
| `compute(scanner=...)` | 波动率 / 成交密度 / 结构断裂 / 流动性 | 各维常数（见 `manas_inputs.py` 对照表） |
| `compute(portfolio=...)` | 风险温度 T | 恒 1.25 |
| `compute(bandit_tracker=...)` | 自信度 | 恒 0.35 |
| `set_awakening_level_provider(fn)` | 调节链 awakening 环节 | 恒 dormant（×1.0） |
| `subscribe_cognitive_events()`（可选） | 叙事风险 / 共振演化 | 认知状态不演化，但不影响四维打分 |

**复用前必读的两条边界**：

1. **`α` 常被下限支配**。`α = clamp(confidence × harmony, 0.3, 1.5)`，
   而这两个乘子实测自然落在 [0, 0.6]，故 `α` 多数场景撞 `alpha_min=0.3`。
   这是**打分公式维度**的问题，本轮明确不改（见 §4）。复用方若需要 `α` 有区分度，
   应重新定标公式，而不是调 clamp。
2. **觉醒环节需要宿主先解决接线，再谈注入**。⚠️ 更正一处早先的误记：
   本仓觉醒等级**是有生产者的**——`knowledge/alaya/awakened_alaya.py` 的
   `AwakeningEngine.get_awakening_level()`，四档
   （dormant / awakening / illuminated / enlightened）与
   `ManasConfig.awakening_factors` 同一套词汇。它之所以不生效，是**三重断点**叠加：

   | # | 断点 | 位置 |
   |---|---|---|
   | 1 | manas 从未接线（旧代码指向全仓不存在的 `get_awakening_controller`） | 已修，改注入点 |
   | 2 | `TradingCenter._get_awakening_level()` 读 `_awakened_state`（从未写入的字典），而非它缓存的 `AwakenedAlaya.awakening_engine` | **未修** |
   | 3 | 所有可达的 `AwakenedAlaya.illuminate()` 调用点都不喂弱信号（`bridge.py` 新建临时实例、`decision/orchestrator.py` 不传 signals），而等级只能靠累积弱信号上升 | **未修** |

   所以现在 ×1.0 是"未接线 + 无信号喂入"的**事实**，不是"没有生产者"。
   **在 #2/#3 解决前不要硬接**——接上去只会得到又一个恒 DORMANT 的静默 no-op
   （正是本轮一路在清理的那类缺陷）。`TestObjectFreeReuse` 里有一条
   `test_awakening_producer_exists_but_is_unwired` 专门钉住这个事实。

---

## 3. 全局验收标准与结果

| 期 | 标准 | 实际结果 |
|---|---|---|
| P0 | 契约校验可运行并稳定复现 2 处违约；单测全绿；运行时行为零变化 | ✅ 2 处违约复现；manas 单测 38 / 全量 186 passed；行为零变化 |
| P1 | 契约违约清零（`--strict` 通过）；快照基线差异有逐条解释；α 与 T 落在合理区间 | ✅ `--strict` exit 0；差异逐条解释后 `--save` 重建基线；T ∈ [0.5, 2.0]、场景 B α 离开下限 |
| P2 | 偏差信号可在 UI 读到；gate 理由按次可查；打分链路 diff 为空 | ✅ UI 双块 + `GateAuditLog`；快照 diff=0 |
| P3 | `ManasEngine` 可在无任何交易对象的情况下跑出非退化分数（P0 已初步证明） | ✅ `TestObjectFreeReuse` 7 例（含觉醒生产者事实核查）；认知层缺席也能构造并出分 |

**全量回归（P3 收尾时一次性复跑）**：

```
快照基线     --check  →  比对场景数 15，差异字段 0
输入契约     --strict →  exit 0（四路对象全部合规）
全量单测     pytest   →  206 passed（186 → 199 → 206，逐期递增）
manas 单文件 pytest   →  58 passed（38 → 51 → 58）
```

---

## 4. 明确不做的事（边界）

- **不重构打分公式**。融合权重、调节链、门控阈值一律不动——本次只修"输入没接上"，
  不碰"怎么算"。两者混在一起会让基线差异无法归因。
- **不在核心模块新增 `SR()`**（架构基准 §6.2）。P1.3 的装配走 application 层注入。
- **不删除任何兜底默认值**。兜底本身是合理的（回测、冷启动都要用）；
  要修的是"真实路径上也在兜底"。
- **不动四维门控 / AdaptiveManas**。它们与本次诊断无关，避免扩大爆炸半径。
- **不搬 `manas_engine.py` 的物理位置**。P3 只保证**运行期**可脱离交易对象；
  目录搬迁不在本轮范围（加载期包耦合后已于「抽象轮」解决，见 P3 小节末）。

---

## 5. 一句话总结

> 上一轮修的是「两个引擎各算各的」；这一轮要修的是「一个引擎被两种喂法喂」。
> 先把输入接上（P1），再谈复用（P3）——**在输入是常数的情况下谈架构升级，
> 升级的只是复杂度，不是能力。**

四期跑完的净收益：**四路输入从常数变回活信号**（timing / T / confidence /
manas_score 全部复活），**12 处同族缺陷被清掉**（诊断期 4 处 §1.1 + 执行期 8 处 §1.4），
**可见性与留痕补齐**（分量 / 偏差镜子 / 行动门审计），
**引擎获得脱离交易对象运行的运行期保证**。

原本仍未动的三件事（**现状已更新**）：

1. `α` 下限支配（公式维度）——**仍未动**，属打分公式维度，需重新定标。
2. 加载期包耦合（架构维度）——**已解（2026-10-12 抽象轮）**：
   包入口改 PEP 562 惰性导出 + 抽 `deva.naja.manas` 门面，
   加载期交易域依赖从 10 个模块降到 **0**。
3. 觉醒维度三重断点（P3 事实核查时发现）——**已解（2026-10-12，D3 `b7e73d6`）**：
   ①manas 侧改为注入点并由容器注入 provider；②`TradingCenter._get_awakening_level()`
   改读共享 `AwakenedAlaya.awakening_engine`；③平仓结果投影为弱信号回流。
   验证：`scripts/verify/verify_awakening_feedback.py --strict`。
   详见 `docs/naja/decision_action_center_design.md`。
