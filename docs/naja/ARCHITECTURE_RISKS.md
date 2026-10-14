# Naja 架构易错点登记册（2026-10-15）

> 配套文档：`ARCHITECTURE_MAP.md`（架构 + 扩展点索引）｜`architecture_gap_audit_2026-10-15.md`（断链审计）
> 本文回答：**「这套架构里，哪些地方天生容易出错、现在还有哪些没修」**，并记录本轮处置。
> 方法：① 全套守卫严格档实跑；② AST 静态扫描（裸吞异常 / 空实现 / 未注册单例 / 事件三向比对）；③ 逐条人工核实。

---

## 0. 一句话结论

守卫套件的**“红”是可信的，但必须用 `--strict` 跑、且必须用项目自己的解释器跑**——
本轮踩到的两个假象（56 个"失败"其实一个都不是、`verify_t_rotation_wiring` 24 项里 17 项早已崩掉）
都源于此。真正的问题**不在架构设计**，而在两类"没人看的地方"：
**静默失效家族**（420+ 处裸吞异常）和**守卫自身的腐烂**（改完产品没回头更新用例）。

---

## 1. 头号病理：静默失效家族

本仓反复出事的形态，**共同点是「不报错、不告警、看上去正常」**。按出现频次排序：

| # | 形态 | 本次实锤 | 防线 |
|---|---|---|---|
| S1 | **裸吞异常**（`except Exception: pass`）→ 故障伪装成"没发生" | 全仓 **422** 处裸吞，其中 **360** 处是 `Exception`/裸 `except` | 见 §3.1 已修的 3 处；其余属"清扫级"债，未动 |
| S2 | **`create()` 忘了初始化** → AttributeError 被上层吞掉 | `dictionary.Manager.create` / `tasks.Manager.create` 漏调 `_ensure_initialized()`（§3.1） | 已修 + `datasource` 侧本有 `@_require_initialized` 可对齐 |
| S3 | **产品的 API 变了，守卫的用例没跟着变** → 检查项一进去就抛，等于没检查 | `verify_t_rotation_wiring` 17/24 项崩掉（§2） | `run_all_guards.py`（§5） |
| S4 | **指向不存在模块的守卫** → 永久飘红 → 训练人忽略红 | `verify_gen_quant_storage` / `verify_ui_integration` 依赖 `deva.admin.*`（git 中从不存在）（§3.4） | 自述式报错 + 待拍板 |
| S5 | **「设计了但从未实现」的读点** → 永远走降级分支 | `SR('connector')` / `SR('replay_scheduler')`：类在全仓不存在（§4.3） | 守卫豁免清单已登记原因 |
| S6 | **空实现 / 声称未实现** → 看着像接好了 | 全仓 **46** 个（多数是合理的抽象方法；`_reinforce_narrative` 等已在 docstring 标注） | 已在 §8「装配了但没生效」清单登记 |
| S7 | **部分初始化对象** → 只在"非正常构造路径"下炸 | `MenuBarTray._op_status` 只在 `__init__` 里设（§3.2） | 已改为类级默认 |
| S8 | **假值当量纲用** | `record_bandit_decision(quantity=amount)`：把**金额**塞进**股数**字段（`bandit/adaptive_cycle.py:544`）（§4.4） | 待拍板 |

> **S1 的量化**：422 处裸吞里大部分是 UI render guard / 清理路径，属"合理的静默"。
> 但**没有基线就无从判断新增的是不是合理** —— 所以真正该做的是给「新增裸吞」设闸，而不是一次性清扫 422 处（详见 §5.3）。

---

## 2. 本次最大的发现：守卫（眼睛）自己会腐烂

**这是本轮最值得记住的一条。**

`verify_t_rotation_wiring.py`（做 T 接线守卫，1158 行，24 项检查）在做 T 全面换用**富途行情**
（commit `b80dba1`，「做 T 支持三市场 —— 行情换富途、时段按市场、参数分档」）之后，
**仍然在测 MarketDataBus（新浪）时代的接口**：

| 守卫还在用的旧接口 | 产品早已改成 | 后果 |
|---|---|---|
| `CoreHoldingSpec(code, bus_code, name, target_shares)` | 多了一个**必填**字段 `market` | 10 项检查 `TypeError` |
| `TRotationRunner(..., bus=...)` | 形参改名 `quotes=`（行情源换成富途） | 3 项 `TypeError` |
| `from t_rotation_runner import cn_phase` | 挪到 `market_session.market_phase(market, dt)` | 1 项 `ImportError` |
| `bus.fetch` / `bus.get_quote` | `src.get(code, market)`（富途源入口） | 静态检查失准 |
| `minutes_to_close(dt)` 返回墙钟分钟（10:00→300） | `minutes_to_close(market, dt)` 返回**剩余交易分钟**（10:00→210，午休不算） | 断言值过期 |
| 顶层 `phase` / `minutes_to_close` | 改成逐市场 `phases[code].{phase,minutes_to_close}` | 断言键过期 |
| 拉升 + 一根回落即触发高抛 | 新增 `require_stabilize`：创新高后需 **≥3 根 bar** 企稳确认 | `SELL_T` 永不触发 |

**它就这样躺了一个版本**：24 项里 17 项进去就崩，屏幕上一路 `❌`。
没被发现的原因**不是**退出码策略（本仓约定 `--strict` 才是闸门档，其它 14 份守卫同款写法），
而是**没有人有一条命令能把全套守卫跑一遍**。→ 修法见 §5.1。

**教训**：改产品 API（尤其改必填参数、改函数所在模块、改返回值口径）时，
**grep 一遍 `scripts/verify/`**。守卫是用例，用例不跟上就是零覆盖。

---

## 3. 本次已修（全部做过负向验证）

### 3.1 两处 `Manager.create()` 漏初始化（S2）

`dictionary/manager.py:create` 与 `tasks/manager.py:create` 都碰 `self._items` / `self._items_lock`，
但**只有它们没调 `_ensure_initialized()`**（同文件其它公开方法都调了；`datasource` 侧有
`@_require_initialized` 装饰器兜着）。冷启动时若 `create()` 是第一个被调到的方法 →
`AttributeError` → 被调用方 `except Exception` 吞掉 → 表现为"点了创建没反应"。

- 修法：两处各补一行 `self._ensure_initialized()` + 说明注释。
- 反方向核对：`dictionary.update` 经 `self.get()` 间接保证了初始化，**无需改**（避免过度修补）。

### 3.2 托盘 `_op_status` 缺类级默认（S7）

`MenuBarTray.__init__` 才设 `self._op_status = None`；而 `verify_naja_restart` 用
`object.__new__(MenuBarTray)` 跳过 rumps 初始化，随后 `_do_restart_tray → _do_restart → _update_op`
读 `self._op_status` → `AttributeError`。**它正是"重启服务"第一步要走的路径**。

- 修法：类级 `_op_status = None`（既兜底，又让"未初始化"与"空闲"同义，不会误报"有任务在跑"）。

### 3.3 复活 `verify_t_rotation_wiring`（S3）—— 本轮主要工作量

对齐当前架构重写全部 fixture，并把静态检查指向**富途**而非已弃用的新浪总线：

- fixture：`FakeBus` → `FakeQuotes`（`.get(code, market)`，含 `ok` 字段）；
  `CoreHoldingSpec` 补 `market="CN"`；`bus=` → `quotes=`；
  `cn_phase` → `market_session.market_phase`；收盘倒计时断言 300 → 210。
- **闸门注入**：`CoreEstablishGate(provider=...)` 提供恒放行裁定，
  并注入 `_AlwaysAskWatch`（守望自身有节流，会变成用例成败的隐藏变量）。
- **补反方向用例** `check_gate_hold_blocks_establish`：闸门判 hold 时**必须一笔不买**。
  （只留正向用例的话，哪天闸门被摘掉，正向用例照样绿 —— 一项保护掩盖另一项缺失。）
- 静态检查改为断言当前实现，并保留**反方向断言**（`_read_quote` 里不许再出现 `get_market_data_bus`）。
- 样本序列补上「创新高后 ≥3 根企稳 bar」（`require_stabilize` 新门槛）。
- 退出策略回归本仓约定（`--strict` 为闸门档），并修掉 `main()` 返回值被丢弃（`main()` → `sys.exit(main())`）。

**结果：17/24 失败 → 25/25 全过。**

**负向注入（3/3 全抓）**：

| 注入 | 结果 |
|---|---|
| 闸门恒放行（摘掉 hold 硬拦） | ✅ 抓：「闸门判 hold，却仍建了 400000 份底仓」 |
| `_read_quote` 丢掉 `quote.ok` 校验 | ✅ 抓：「未校验 quote.ok —— 会把失败报价当有效数据喂进引擎」 |
| 取数改回 `MarketDataBus` | ✅ 抓：「取行情不走行情源同步入口 src.get()」 |

### 3.4 守卫卫生

- `verify_manas_compute_snapshot`：**补 `--strict`**（此前会让统一扫描以
  `unrecognized arguments` 退出 rc=2，被误当成"守卫 ERROR"）。语义 = 与内置基线比对，有差异即失败。
- `verify_ui_integration`：第 4 项依赖从未存在的 `deva.admin.ai.ai_code_generator` →
  标为 **RETIRED 且不计入总数**（其余 5 项仍在实打实验），并使脚本恢复 `exit 0`。
- `verify_gen_quant_storage`：依赖从未存在的 `deva.admin.strategy.datasource`，
  整份守卫**测的是不存在的功能** → 改为**自述式报错**（打印原因 + 处置建议，仍 exit 1）。

### 3.5 静态扫描（量化基线，本次未修）

| 项 | 数量 |
|---|---|
| 裸吞 `except`（体里只有 `pass`/`continue`） | **422**（其中 `Exception`/裸 `except` **360**） |
| 空实现 / docstring 声称未实现 | **46**（多为合理的抽象方法） |

---

## 4. 待拍板（都需要"改行为"或"删代码"，不宜由 AI 单方面决定）

### 4.1 买入路径忽略调用方给定的 `quantity`（真钱链路，**优先级最高**）

`bandit/execution.py:753-758`：

```python
if side_norm == "buy":
    qty = floor_to_lot(amount, limit_price, lot_size)   # ❗完全没用 quantity
```

而同函数 docstring 写的是「`quantity`：**要卖/买的股数**……不传时按 `amount` 折算」。
即**买入分支与自己的契约不符**。记忆里那条「计划 5900、实成交 5800」的现象与此一致。

- 两个选项：① 买入也认 `quantity`（改真钱下单量，**需明确授权**）；
  ② 明确"买入只认金额"并改 docstring（那调用方就别再传 quantity）。
- **未动**：任何改变真实下单量的改动都不该由 AI 单方面落地。

### 4.2 两处「设计了但从未实现」的单例读点（S5）

| 读点 | 实况 |
|---|---|
| `SR('connector')` × 2（`home/ui/stats.py:48`、`knowledge/wisdom/ui.py:19`） | 类与注册表条目**都不存在**；调用方 `except` 后回落 0/`-` |
| `SR('replay_scheduler')` × 3（`auto_tuner.py:32`、`market_observer.py:100`、`web_ui/modes.py:365`） | 类在全仓**不存在**；调用方 `except` 后回落 `None` |

→ 要么删掉死读（保留同样的降级值，行为不变），要么把生产者补出来（新增功能）。
守卫 `verify_singleton_registry_consistency` 已把两条登记在 `KNOWN_UNREGISTERED` 并写明原因，
所以它在 `--strict` 下**仍然红** —— 这是"待决策"信号，不是假绿。

### 4.3 `verify_gen_quant_storage` 的退役 vs 重写

被测功能（`quant_source` 数据源 / `gen_quant` 代码）在全仓零痕迹，模块也从未提交过。
建议**删除**；若确实要保留这条能力，则按 `deva/naja/datasource/manager.py` 重写。

### 4.4 金额当股数记录（S8）

`bandit/adaptive_cycle.py:544`：`record_bandit_decision(action="BUY", ..., quantity=amount)`
—— 把**金额**写进了 `quantity` 字段（`_on_position_closed` 里同一函数用的是 `position.quantity`，
两处量纲不一致）。若该字段只用于展示，影响有限；若被任何计算读取就是隐性错数。
**需先确认消费方**再定改法。

---

## 5. 防复发机制

### 5.1 `scripts/verify/run_all_guards.py`（本次新增，**最重要**）

一条命令跑完全套守卫的严格档，输出通过/失败清单与失败摘要；会动本机状态的守卫
（如 `verify_naja_restart` 会真的重启服务）默认跳过，需 `--include-dangerous` 才跑。

```bash
env -u PYTHONPATH TMPDIR=$(mktemp -d) \
  /opt/homebrew/opt/python@3.13/bin/python3.13 scripts/verify/run_all_guards.py --quiet
```

**它就是本轮的根因对策**：让"24 项里 17 项已崩"这种事不可能再无人知晓。

### 5.2 用项目自己的解释器（本次踩坑）

- 项目真实解释器 = **`/opt/homebrew/opt/python@3.13/bin/python3.13`**
  （`~/Library/LaunchAgents/com.naja.autostart.plist` 里写的就是它）。
- 用 WorkBuddy 的**托管 python**跑守卫 → 缺 `toolz` 等依赖 → **56/72 份守卫"失败"**，
  全是假象。**判断守卫是否失败，先确认解释器。**
- 跑法固定为：`env -u PYTHONPATH` + `TMPDIR=$(mktemp -d)`。

### 5.3 尚未落地的两件（建议）

1. **裸吞异常基线闸**：给"新增 `except Exception: pass`"设闸（存量 422 记白名单，
   新增即失败）。否则永远是"扫出来一堆、没人清、也没法判断新增"。
2. **API 变更连带检查**：改必填参数 / 挪模块 / 改返回值口径时，约定 grep 一遍
   `scripts/verify/`；可在 CI 里跑 `run_all_guards.py` 兜底。

---

## 6. 本轮守卫套件状态

`scripts/verify/verify_*.py` 共 **67** 份。用项目解释器 + `--strict` 实跑：

| | 修复前 | 修复后 |
|---|---|---|
| 通过 / 失败 / 自身出错 | 61 / 5 / 1 | **64 / 2 / 0** |
| 按时跑（`run_all_guards.py`） | — | 66 份：通过 64，失败 2，跳过 1（用时 ~200s） |

剩余 2 项失败 + 1 项跳过，**全部是已明确标注、待拍板**的（不再有静默腐烂）：

| 守卫 | 性质 |
|---|---|
| `verify_singleton_registry_consistency` | §4.2 两条豁免待决策（`--strict` 下按设计为红） |
| `verify_gen_quant_storage` | §4.3 待退役/重写（被测功能从未存在） |
| `verify_naja_restart` | **会真重启服务**，不应进自动化（`run_all_guards.py` 默认跳过） |

---

## 7. 一句话给未来的自己

> 这套架构的**设计**没问题，出事的都是**"没人看的地方"**：
> 异常被吞、API 改了用例没改、模块指向不存在的东西。
> 所以两条纪律：**改动产品 API 就回头 grep 守卫**；**定期跑 `run_all_guards.py`**。
