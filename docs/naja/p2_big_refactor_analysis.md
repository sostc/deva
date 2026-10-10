# P2 分析：四项"大手术"到底大不大

> 性质：**评估**，未改代码。本文逐项核实了现状、风险与真实工作量，
> 并对 review_core_async_and_manas.md 里的两处表述作了修正。

---

## 0. 结论先行：只有一项真"大"

| 项 | 原标签 | **重估** | 真实工作量 | 风险 |
|---|--------|----------|-----------|------|
| B `_supply_chain_state` | 字典上帝对象 | ✅ **bug 已修**（增量覆盖）+ 中等重构 | 小→中 | 🔴→🟢 字典拆分仍待做 |
| A `compute()` | 170 行上帝方法 | ✅ **已改 Modifier 链**（快照等价） | 中 | 🟢 15 场景 0 差异 |
| C core 异步模板×8 | 复制粘贴 8 处 | ✅ **已抽 2 个 helper** | 中 | 🟢 异步回归通过 |
| D `pipe.py` builtins | 导入即污染 | ✅ **已删**（实测 149 → 0） | 小 | 🟢 无依赖 |

"大手术"这个说法被我之前的报告**夸大**了。按风险从高到低应为 **B → A → C → D**。

---

## 1. B. `_supply_chain_state`：这里有个已证实的 bug

### 1.1 一个字典装 5 类不相关关注点

`manas_engine.py:1004-1022`：

| 组 | 字段 |
|---|---|
| 叙事风险 | `narrative_risk` / `hot_narratives` / `risk_level` / `last_update` |
| AI 算力 | `ai_compute_trend` / `ai_compute_strength` |
| 自选股 | `watchlist` / `watchlist_bonus` |
| 关注主题 | `focus_themes` |
| 共振 | `resonance_score` / `resonance_sentiment` / `resonance_blocks` / `resonance_updated` |

### 1.2 🔴 实测 bug：事件一来就抹掉 `focus_themes`

`_update_supply_chain_state()` 在 **1302-1318 行整体重建字典**，但重建时
**漏掉了 `focus_themes` 字段**（它只在 `__init__` 的 1016 行设置过一次）。

实测（构造 stub 事件触发一次更新）：

```
事件前 focus_themes 数量: 17
事件后 focus_themes 数量: 0
focus_themes 是否被抹掉: True
```

影响链：

```
_update_supply_chain_state()  重建 dict，无 focus_themes
  → get_focus_themes() 返回 .get("focus_themes", []) → []
    → NarrativeTracker._get_initial_focus_themes() (tracker.py:358-361)
       读到空 → 回落 DEFAULT_NARRATIVE_KEYWORDS
  → _publish_manas_state_change() 广播 focus_themes=[]
    → tracker._on_manas_state_changed() 有 `if new_themes` 守卫 → 忽略
```

**当前是"哑弹"**：`set_focus_themes()` 全仓**零调用方**，所以字段值本来就等于默认值，
即便被抹，回落后的内容也一样。

**但这是埋好的雷**：`set_focus_themes()` 存在、且会发 `MANAS_STATE_CHANGED` 事件，
`NarrativeTracker` 也订阅了该事件——整套机制显然是为「用户自定义关注主题」设计的。
**只要哪天把 UI 接上，用户设的主题会在下一个认知事件到达时被清空。**

修法：重建时带上 `focus_themes`（或从旧 dict 继承），一行的事。

### 1.3 重构方向（中风险，可延后）

五组关注点拆成五个小 dataclass / 独立属性，`_update_supply_chain_state` 改为
"增量更新"而非"整体重建"——整体重建本身就是这次 bug 的成因：
**加字段时要在两个地方同步，漏一处就静默丢数据。**

---

## 2. A. `compute()`：170 行，但结构是线性管道

`manas_engine.py:1492-1660`。通读后，它其实是**一串顺序施加的乘性调节**：

```
base = 0.4*timing + 0.35*(1-risk/1.5) + 0.25*confidence
  × regime 折扣        (1549-1551)
  × narrative_risk 折扣 (1556-1558)
  × AI 算力加成         (1560-1566)
  × 共振加成/惩罚       (1568-1579)
  × 觉醒加成           (1583-1589)
  × bias 纠偏          (1591-1597)
  → clamp [0,1]
  → action_type / alpha / loss / focus / reason
  → ManasOutput(20 字段)
```

**不是乱麻，是有序管道** —— 这正是 P2 提的 "Modifier 链" 能落地的原因：
每一步都是 `(strength, ctx) -> strength` 的纯函数，可逐个抽出、逐个测。

难点不在结构，在于：

- **魔法数散落**：`0.6 / 0.5 / 0.7 / 0.3 / 0.2 / 0.05 / 0.03 / 1.15 / 1.10 / 1.05 / 0.7~1.0`
  十几个阈值与系数内联在表达式里，抽链时要一并收敛成命名常量，否则"抽出去了但更难懂"。
- **行为敏感**：任一系数写错都会改变交易决策。必须**先固化基线**
  （用固定输入跑一批 `compute()`，把 `ManasOutput` 全字段存成快照），
  重构后逐字段比对，才能证明等价。
- `detect_and_correct(harmony_strength, self._recent_pnl, harmony_strength)`
  第 1、3 个参数传了同一个值，曾疑为笔误。**已判定：第 3 参是有意的**（详见附录 A）。
  真正的多余项是**第 1 参 `manas_score`**——函数体内一次都没用到，是死参数。
  改造时不能顺手"修好"第 3 参，但删第 1 参是安全的。

建议：Modifier 链 + `ManasConfig` 收敛常量 + 快照回归。工作量中等，但不是"不可控"。

---

## 3. C. core 异步模板×8：变体只有 3 个差异维度

8 处调用点：`core.py` 748 / 923 / 986 / 1256 / 1458 / 1972，`when.py` 293，`store.py` 174。

逐处比对后，**公共骨架完全一致**，差异只有三个维度：

| # | 位置 | 回调（异步完成后） | 同步分支 | 异常 |
|---|------|------------------|---------|------|
| 1 | `Stream.update` 748 | `self._emit(r)` | `return self._emit(x)` | raise |
| 2 | `catch.wraper` 923 | `self._emit(r)` | `_emit(result)`; return result | 无 try |
| 3 | `catch_except.wraper` 986 | `r`（丢弃结果） | 无; return result | 发错误 dict |
| 5 | `map.update` 1458 | `self._emit(r)` + **`return []`** | `return self._emit(result)` | raise |
| 6 | `run_future.update` 1972 | `self._emit(r)` | 无（assert 必须 awaitable） | 无 |
| 8 | `DBStream.emit` 166 | `self.update(r)` | `self.update(x)` | 无 |

（`run_future` 无 loop 补建代码，因其构造时 `ensure_io_loop=True`）

**所以不需要一个八参数的万能函数**，拆两个小 helper 就够：

```python
def _ensure_loop(self):          # 6 处逐字相同的 3 行
def _defer(self, value, cb):     # convert_yielded + add_future，8 处
```

调用点变成：

```python
if isinstance(x, gen.Awaitable):
    self._ensure_loop()
    self._defer(x, lambda f: self._emit(f.result()))
else:
    return self._emit(x)
```

纯机械替换，逐处 diff 可审。

顺带两个已确认的小问题（可一并处理）：

- `Stream.emit(x, asynchronous=False)`（741）与 `DBStream.emit`（166）的
  `asynchronous` 参数**收下后完全没用**，文档却声称它控制返回 Future
- `map.update` 异步分支 `return []`、同步分支 `return self._emit(...)`——
  **返回类型随输入漂移**

---

## 4. D. `pipe.py` builtins：删 4 行，实测无依赖

### 4.1 对原报告的一处修正

原报告说"把 `print/range/sum/list/len/...` 重绑为 Pipe"——**表述不准确**。
实测：

```
导入 deva 后新增的 builtins 名称数: 149
样例: ['to_ArithmeticError', 'to_AssertionError', 'to_AttributeError', ...]
内置 print 是否被改: builtin_function_or_method   ← 未被改
内置 len 是否可用: 3                               ← 正常
```

真实情况是：

- **builtins 只被"新增"149 个 `to_*` 名字**，没有任何一个真内置被覆盖
  （注入的是 `to_X = Pipe(X)`，不是 `X = Pipe(X)`）
- `print = P(print)` 等是 **pipe.py 的模块级全局**，再通过 `pipe.py` 的 `__all__`
  （第 23-52 行，确实列了 `print/len/type/id/eval/...`）导出到 `deva.core` 命名空间
  → 所以 `deva.core.len` 是 Pipe，但 `builtins.len` 没动

### 4.2 为什么真风险低

`Pipe.__call__` 就是 `self.func(*args, **kwargs)`（pipe.py:170-172），
所以 `len(x)` 即便 `len` 是 Pipe 对象也**照常返回 int**；
Pipe 只是额外支持 `data | len` 语法。遮蔽是良性的。

检索 `to_list|to_dict|to_str|to_int|...` 全仓命中项**全是对象的 `.to_dict()` 方法**，
没有任何一处依赖注入的 `to_*`。

### 4.3 做法

删掉 `pipe.py:1525-1528` 那个循环即可：

```python
for i in builtins.__dict__.copy():
    if callable(builtins.__dict__.get(i)):
        f = 'to_' + i
        builtins.__dict__[f] = Pipe(builtins.__dict__[i])
```

注意别删 `1531-1556` 的模块级别名（`print = P(print)`、`to_list = P(list)` 等）——
那是管道的**公共 API**，删了会破坏 `data | len` 这类用法。

---

## 5. 建议顺序

1. ~~**B 的 bug 先行**（1 行，零风险，且有实证）~~ ✅ 已完成（改为增量覆盖，见 A.4）
2. ~~**D**（删 4 行）~~ ✅ 已完成，实测 builtins 新增名 149 → 0
3. ~~**C**（抽 2 个 helper，8 处替换）~~ ✅ 已完成，异步路径回归通过
4. ~~**A**（Modifier 链）~~ ✅ 已完成，快照基线 15 场景 0 差异

---

## 6. 当前状态

P2 四项全部完成。额外的收获：

- 修掉了 `ManasManager.compute()` 必崩的 AttributeError（P1 期间）
- 给 `MetaManas` 补了 `get_state()`，`attention/ui/dashboard.py` 的末那识面板
  从"恒显默认值的死面板"变成真实可用

**剩余可选项**（都非阻塞）：

1. **B 的字典拆分**：`_supply_chain_state` 仍是 13 字段的混合字典
   （叙事风险 / AI算力 / 自选股 / 共振 / 主题）。bug 已修，但结构仍混乱。
   建议与后续新增字段一起做，避免两次回归成本。
2. **A 的魔法数收敛**：十几个内联阈值（0.6 / 0.7 / 0.2 / 0.10 / 0.08 / 1.15…）
   抽成 `ManasConfig`。有了快照脚本后这项风险已很低。
3. `detect_and_correct` 的第 1 参 `manas_score` 仍是死参数（docstring 已标注）。

---

## 附录 A：`detect_and_correct` 参数疑点的判定

调用点 `manas_engine.py:1591`：

```python
bias_state, bias_correction = self.meta_manas.detect_and_correct(
    harmony_strength,      # manas_score
    self._recent_pnl,      # recent_pnl
    harmony_strength       # decision_aggressiveness
)
```

### A.1 第 3 参传 `harmony_strength` —— 判定：**故意，不是笔误**

四条证据：

1. **语义自洽**：docstring 写 `decision_aggressiveness: 最近的决策激进程度`。
   `harmony_strength` 正是"本次该不该全力行动"的强度，用它当"这次决策有多激进"
   的样本是直接度量，不是凑数。
2. **量纲吻合**：判贪的条件 `avg_aggressiveness > 0.6`，与 `ACTION_THRESHOLD = 0.5`、
   `STRONG_ACTION_THRESHOLD = 0.6` 处在同一个 0-1 分数空间。若这里本该传 pnl
   之类的量，0.6 这个阈值完全不成立。
3. **时序正确**：记录的是**纠偏前**的强度（`harmony_strength *= bias_correction`
   在下一行 1597 才发生）。作为历史样本入 `_decision_aggressiveness` 窗口合理。
4. **没有更合理的候选**：alpha 要到 1603 行才算出来（在本次调用之后），
   不可能传；`timing_score` / `confidence_score` 都不是"决策激进程度"。

结论：**保留第 3 参，不要顺手改**。真要提升可读性，可以改个局部变量名
（`aggressiveness = harmony_strength`）把意图写明。

### A.2 第 1 参 `manas_score` —— 判定：**死参数**

函数体（887-949 行）内 `manas_score` 出现 **0 次**，完全没被使用。
实测确认。删掉是安全的，但属于 API 变更。

### A.3 顺带发现的两个真 bug（都改变决策行为）

> **状态：bug-1 与 bug-2 均已修复**（见下方"修复记录"）。以下为发现时的原始分析。

**bug-1：`_pnl_trend` 重复累积，暖机保护失效**

`detect_and_correct` 内是 `self._pnl_trend.extend(recent_pnl)`，而调用方每轮
传的是**整个** `self._recent_pnl`（滑动窗口，上限 20）。于是每轮把整窗口再
追加一遍，`len(self._pnl_trend) < 5` 的"至少 5 笔才判定"暖机保护被重复计数绕过。

实测（只有 2 笔真实盈利交易、决策强度 0.7）：

```
第1轮 trend长度=2 -> neutral, corr=1.0
第2轮 trend长度=4 -> neutral, corr=1.0
第3轮 trend长度=6 -> greed,   corr=0.7   ← 仅 2 笔交易就判"贪"
```

稳态下（`_recent_pnl` 满 20 条）截断窗口恰好也是 20，每轮 extend 20 条正好把
旧数据全挤掉，**碰巧等价**于"最近 20 笔"。所以这个 bug 只在冷启动 / 交易稀疏
阶段发作——而那恰恰是最不该乱纠偏的时候。

修法：`_pnl_trend` 只增量追加新发生的盈亏（由 `record_pnl` 直接喂），
而不是每轮 extend 整个窗口。

**bug-2：`bias_correction` 被平方施加**

```python
1597: harmony_strength *= bias_correction        # 第 1 次
1603: alpha = confidence_score * harmony_strength * bias_correction   # 第 2 次
```

`harmony_strength` 已含 correction，alpha 再乘一次 → 实际效应是 c²：

| 状态 | 设计值 c | 实际效应 c² |
|---|---|---|
| 贪（稳态） | 0.7 | 0.49 |
| 惧（首轮） | 0.5 | **0.25** |
| 惧（稳态） | 0.8 | 0.64 |

`alpha` clamp 下限是 0.3，惧首轮的 0.25 会**直接撞底**。而 docstring 只写了
"贪时 → reduce α"，是一次而非平方。

修法二选一：删 1603 的 `* bias_correction`（保留 1597），或删 1597
（只在 alpha 上体现）。按 docstring 语义，倾向前者——让 bias 同时作用于
分数与 alpha 是"经由 harmony_strength 传导"的自然结果。

### A.4 修复记录

**bug-1**：删除 `MetaManas._pnl_trend` 字段，函数内改为
`pnl_trend = list(recent_pnl or [])`，直接以调用方的滑动窗口为样本。

不选择"改成增量追加"是因为那会让 `ManasEngine.record_pnl()` 反向耦合
`meta_manas`，且仍需维护两份状态。样本窗口只应有一份权威来源——
`recent_pnl` 参数本就是为此设计的。

验证：2 笔真实交易反复调用 5 轮，全程 `neutral`（修复前第 3 轮即判"贪"）；
6 笔真实盈利仍能正常判贪 `corr=0.7`。

**bug-2**：采用"删 1603 的 `* bias_correction`"，保留 1597。
与 P0 时写入头部的公式文档一致（bias 是 harmony_strength 乘性调节链的一环，
经 harmony_strength 自然传导到 alpha）。

验证：惧首轮 `corr=0.5` 场景下 alpha 由 0.180（撞下限 0.3）变为 0.360。

**bug-3（focus_themes，见 §1）**：`_update_supply_chain_state` 由整体重建
`self._supply_chain_state = {...}` 改为增量覆盖 `.update({...})`。

不选择"补写 focus_themes 一行"是因为那没解决根因——下次新增字段还是会漏。
本方法语义是"基于旧状态演化"，没有字段需要被清空，增量覆盖天然安全。

验证：事件前后 `focus_themes` 17 → 17；字段集合完全一致；
`set_focus_themes(['我的自定义主题'])` 后经历事件仍存活；`last_update` 正常刷新。

**未动**：第 1 参 `manas_score` 是死参数，但属公开签名，本次只在 docstring
标注"当前未参与计算"，未删除。

---

*基于 manas_engine.py / pipe.py / core.py / when.py / store.py /
container.py / tracker.py 实际代码核对，focus_themes 丢失与 builtins 注入
均为本机实测结果。*
