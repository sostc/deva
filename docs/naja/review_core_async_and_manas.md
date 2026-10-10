# 代码审查报告：deva.core 异步执行系统 & manas 决策中枢

> 范围：`deva/core/`（底层异步执行系统）、`deva/naja/attention/kernel/manas_engine.py` +
> `manas_manager.py` + `kernel.py`（关键决策系统）以及其装配点。
> 性质：只读评估，未改动任何代码。

---

## 0. 结论速览

| 领域 | 核心问题 | 严重度 |
|------|----------|--------|
| deva.core | 异步处理模板 8 处复制粘贴，缺单一抽象 | 🔴 高 |
| deva.core | 模块加载时全局污染 `builtins` | 🔴 高 |
| deva.core | `Stream.emit` 的 `asynchronous` 参数是"假的"，语义失效 | 🟠 中 |
| deva.core | 异步分支不保证顺序、无背压、返回值类型不一致 | 🟠 中 |
| deva.core | core.py 单文件混装 5 类职责（流/HTTP/日志/事件循环/适配器） | 🟠 中 |
| manas | 文档公式与实现完全脱节 | 🔴 高 |
| manas | `compute()` 上帝方法 + `ManasOutput` 20+ 字段 + 状态字典上帝对象 | 🔴 高 |
| manas | 事件订阅写在领域对象 `__init__`，违反架构基准 §6.3，且多实例重复订阅 | 🔴 高 |
| manas | ManasManager **双单例分裂**，三处 ManasEngine 潜在实例 | 🔴 高 |
| manas | 6 处 `SR` 死导入 + 15 处 `bare except` + 多处死变量 | 🟠 中 |

---

## 1. deva.core（底层异步执行系统）

### 1.1 🔴 异步处理模板重复 8 次，缺统一抽象

同一段「拿到 awaitable → convert_yielded → 补 loop → add_future → 回调 _emit」的样板
在 core 层被逐字复制：

- `deva/core/core.py:498`（`Stream.update`）
- `deva/core/core.py:927`（`Stream.catch`）
- `deva/core/core.py:990`（`Stream.catch_except`）
- `deva/core/core.py:1254`（`Sink.update`）
- `deva/core/core.py:1458`（`map.update`）
- `deva/core/core.py:1974`（`run_future.update`）
- `deva/core/when.py:293`（`timer.run`）
- `deva/core/store.py:173`（`DBStream.emit`）

`gen.convert_yielded` 在 core.py 内出现 6 次、when.py/store.py 各 1 次。
**问题**：任何一处 loop 兜底逻辑或异常策略变更，都要改 8 个地方；其中 `SSink.update`
与 `map.update` 的异步分支返回 `[]`，而同步分支返回 `self._emit(...)` 的返回值——
**同一方法返回类型随输入类型漂移**，调用方无法统一处理。

**建议**：抽出 `_handle_awaitable(result, emit_cb)`（或 `Stream._emit_async`）单一入口，
8 处全部改为调用它。

### 1.2 🔴 模块导入即污染 builtins

`deva/core/pipe.py:1525-1528`

```python
for i in builtins.__dict__.copy():
    if callable(builtins.__dict__.get(i)):
        f = 'to_' + i
        builtins.__dict__[f] = Pipe(builtins.__dict__[i])
```

导入 `deva.core.pipe` 会给**整个进程的 builtins** 注入 `to_print` / `to_len` / `to_sum`
等一批符号。同时 pipe.py 模块级还把 `print / range / sum / list / len / max / min / abs /
type / id / eval / iter` 等重新赋值为 `P(...)`，再由 `core/__init__.py` 的星号导出扩散。

**后果**：
- 任何第三方库/用户代码里 `print(...)`（若中途 `from deva.core.pipe import print`）行为
  被替换为 Pipe 包装对象；
- 静态分析与 IDE 无法正确解析内置符号；
- 两个库同时做这类 monkeypatch 时冲突不可预测。

**建议**：删除 builtins 注入；这些 `to_*` 辅助要么删掉，要么收敛到显式命名空间
（如 `deva.core.pipe.P`）。至少要保证"导入不产生全局副作用"。

### 1.3 🟠 `Stream.emit` 的 `asynchronous` 参数名存实亡

`deva/core/core.py:741`

```python
def emit(self, x, asynchronous=False):
    self.update(x)
```

参数接收但完全不使用。文档字符串却宣称 `True` 会返回可等待 Future。同类问题见
`DBStream.emit`（`store.py:166`）、`scheduler.emit`（`when.py:166`）、`TCPStream.emit`。
**建议**：要么实现，要么删参并修正文档——不要留"看起来可配其实是空转"的开关。

### 1.4 🟠 无背压 / 顺序无保证 / 错误吞没

- **顺序**：`map.update` 对异步结果走 `add_future`，立即返回 `[]`，结果在 future 完成时
  才 `_emit`。同一源快速 emit 多条时，**下游收到顺序由 future 完成顺序决定**，与输入顺序
  不一致，且无序号/缓冲来纠正。
- **背压**：只有 `buffer` 用 Queue 做阻塞，其余节点同步 `_emit` 直接扇出，
  慢消费者会阻塞整条链（`_emit` 里 `for downstream in ...: downstream.update(x)` 同步调用）。
- **错误**：`httpx`（core.py:1662-1666）与 `crawler._request` 捕获异常后 **返回 None**
  而不抛出，"测试脚本能继续跑"的妥协被写进了生产 HTTP 层；`Sink.update` / `map.update`
  却 `logger.exception + raise`。**同一框架内两种相反的异常策略**，使用者无法预判。

**建议**：明确一套错误传播约定（抛出 vs 入流），HTTP 层单独用显式 `try` 语义，
不要在通用 `httpx` 里静默返回 None。

### 1.5 🟠 单文件职责过载（core.py 2087 行）

`deva/core/core.py` 同时容纳：
1. `Stream`/`Sink`/`map`/`filter`/`starmap` 等流算子
2. `httpx` / `crawler` 异步 HTTP 客户端（依赖 requests_html）
3. `sync()`（与 tornado 语义重复的同步桥）
4. `Deva` 事件循环启动器
5. 日志适配器（`normalize_record` / `format_line` / `DevaFormatter` /
   `setup_deva_logging`，注释直书"merged from logging_adapter.py"）

**建议**：按职责拆 `core/stream.py`、`core/http.py`、`core/logging.py`、`core/loop.py`。
文件顶部 340 行的巨型 docstring 也建议移入 README/docs。

### 1.6 🟠 循环导入网 + 星号导出

`core/__init__.py` 依次 `from .core import *` / `.pipe` / `.bus` / `.when` / `.sources` /
`.compute` / `.namespace` / `.store`；而 `namespace.py` 又反过来 `from .core import Stream`、
`from .store import DBStream`、`from .sources import Topic`；`bus.py` `from .core import ...`；
`when.py` `from .bus import log`。这是一张互相耦合的图，靠"导入顺序 + 星号导出"维持，
`__all__` 里列的名字（如 `IndexStream` / `FileLogStream`）在 core 目录里根本不存在。

**建议**：改为显式导入，取消跨模块星号；`core/__init__` 只做聚合导出，不反向参与运行时逻辑。

### 1.7 🟡 其他具体坏味道

- `get_io_loop(asynchronous=None)`（`utils/ioloop.py`）：`None` 与 `False` 走"新建全局守护
  线程 loop"的同一分支，语义不显；创建的 loop 从不停机（`_io_loops` 只增不减）。
- `timer.run`（when.py:286-291）`thread` 分支两个 `if/else` 体**完全相同**，是死分支；
  同时 `scheduler`（apscheduler）与 `timer`（裸 `gen.sleep` 循环）是两套重叠的定时抽象。
- `to_textfile`（core.py:1281,1324）同时用 `weakref.finalize` 和 `__del__` 关闭文件句柄，
  可能双重 close。
- `namespace.NT/NWT` 失败时 `return None`（namespace.py:200-213），而 `NS` 抛异常——
  同族 API 两种错误契约，调用方到处都是隐式 `if x is None`。
- `when.py:377` 模块导入即执行 `when('exit').then(...)`；`bus.py` 导入即 `start()` 心跳线程
  并注册 `atexit`——**import 副作用**，难以在测试中隔离。

---

## 2. manas（关键决策系统）

### 2.1 🔴 文档公式与实现完全脱节

`manas_engine.py` 头部（第 69-83 行）声明：

```
manas_score = 0.4 * timing + 0.3 * regime + 0.3 * confidence
T = base_T / (1 + manas_score)
```

实际实现（第 925-928、1439-1443 行）：

```python
WEIGHT_TIMING = 0.4
WEIGHT_RISK = 0.35        # ← 用 risk_temperature 而非 regime
WEIGHT_CONFIDENCE = 0.25
harmony_strength = timing*0.4 + (1-min(risk_T,1.5)/1.5)*0.35 + confidence*0.25
```

- 权重三者不一致（0.3 regime 变成 0.35 risk）；
- 组合量是 `risk_temperature` 的**反函数**，不是 `regime`；
- `T` 与 `manas_score` 在实现里**毫无关系**（`RiskEngine.compute` 自算 base_T）；
- 对外主指标叫 `harmony_strength`，`manas_score` 只是它的别名（第 1533 行）。

**后果**：任何人（包括后续 AI）按文档改代码必然改错，是最高优先级的"信息污染"。

### 2.2 🔴 `compute()` 上帝方法 + 状态字典上帝对象

- `ManasEngine.compute()`（第 1388-1560，约 170 行）串行堆叠了：依赖解析、4 子引擎调用、
  harmony 计算、regime 折扣、narrative 风险折扣、AI 算力加成、共振加成/惩罚、觉醒加成、
  偏差纠偏、action 判定、alpha、持仓损失、注意力聚焦、自选股加成、原因拼装、Output 组装。
- `ManasOutput` 有 20+ 字段（第 163-222），全部在同一个 dataclass 里。
- `self._supply_chain_state`（第 951-969）是一个 dict，塞进了 **6 类不相关关注点**：
  叙事风险、热点叙事、AI 算力趋势、自选股注意力、关注主题、共振状态。

**建议**：
- 把每类「加成/折扣」抽成独立 `Modifier`（`apply(strength) -> strength`），`compute`
  退化为「基础融合 → 依次应用 modifiers → 组装输出」；
- `_supply_chain_state` 拆成 3 个小的 dataclass：`NarrativeRisk` / `AiComputeTrend` /
  `ResonanceState` / `WatchlistAttention`；
- `ManasOutput` 按用途分组（决策/风险/叙事）或引入子结构。

### 2.3 🔴 事件订阅写进领域对象 `__init__`，且重复订阅

`manas_engine.py:974` 在 `__init__` 里调用 `self._subscribe_to_event_bus()`，
使用**固定模块名 `"ManasEngine"`** 订阅（第 1072 行）。

- 直接违反架构基准 §6.3（订阅应集中于 application 层 `EventSubscriberRegistrar`）；
- 因为存在多个 ManasEngine 实例（见 2.4），`cognitive_bus._cognitive_subscribers["ManasEngine"]`
  会被 append 多条 → **同一逻辑事件被处理多次**；
- 领域对象持有对全局 bus 的隐式依赖，测试时无法脱离全局注册表。

### 2.4 🔴 ManasManager 双单例分裂 + 三处 ManasEngine

同一个概念存在**两套 ManasManager 单例**，且互不感知：

| 来源 | 位置 | 是否 enable | 是否持 kernel |
|------|------|-------------|---------------|
| 注册表单例 | `register.py:195-207`（`SR('manas_manager')`） | ✅ `set_enabled(True)` | ✅ 注入 attention_os 的 kernel |
| 容器属性 | `container.py:882-910`（`container.manas_manager`） | ❌ 从不 enable | ❌ kernel=None |

而 `manas_manager.get_manas_manager()`（`manas_manager.py:188-195`）读的是**容器那一个**，
web_ui `attention_api.py:105` 也走它 → 对 UI 而言 manager 长期处于未启用态。

连带死代码：
- `container.py:856 _create_manas_engine()` —— **定义了但无人调用**；
- `manas_manager.py:184-185 _global_manager / _global_manager_initialized` —— 只写不读；
- `manas_manager.py:198 setup_manas_manager()` —— 只导出无调用。

叠加 `AttentionKernel._init_manas_engine()`（`kernel.py:160`）→ 系统里潜在存在
**3 个 ManasEngine 实例**，各自订阅、各自维护历史滑窗，决策状态互相不可见。

**建议**：单一来源（container 或 register 二选一），ManasEngine 只应有一个实例；
删除 `_create_manas_engine` / `_global_manager` / `setup_manas_manager` 死代码。

### 2.5 🟠 依赖三通道注入，语义重叠

`ManasEngine` 的 `session_manager / portfolio / bandit_tracker` 可通过**三种途径**进入：
1. 构造参数（第 930 行）
2. `set_session_manager / set_portfolio / set_bandit_tracker`（第 976-989）
3. `compute(..., session_manager=, portfolio=, bandit_tracker=, ...)`（第 1388）

子引擎同样：`TimingEngine.__init__(session_manager)` + `set_session_manager()` +
`compute(session_manager=)`。**"当前值到底以哪个为准"不明确**，任何一处漏传就静默回退到
`self._xxx`（可能为 None → 走默认 0.5/1.0 分支）。

**建议**：只保留构造注入（composition root 一次性装配），`compute()` 只接真正每帧变化的
输入（如 `macro_signal`），状态依赖不进方法签名。

### 2.6 🟠 服务定位器穿透 / 私有属性访问

- `_get_awakening_level()`（第 1364-1373）在领域逻辑里 `import get_awakening_controller`，
  并直接读 `controller._awakened_state`（跨模块**私有**属性）。
- `_get_scanner()`（`manas_manager.py:173`）、`kernel._get_scanner`
  （`kernel.py:215`）函数内部 `from ...radar.global_market_scanner import get_global_market_scanner`
  —— 领域层反向依赖全局 getter。
- `set_narratives` / `_current_narratives`（第 1379-1386）与构造函数订阅的 narratives
  来源并存，职责重复。

### 2.7 🟠 15 处 `bare except` 静默吞异常

`manas_engine.py` 第 341、371、403、420、546、556、586、669、684、704、780、796、807、
1281、1515 行全部是裸 `except:`。裸 except 会连 `KeyboardInterrupt` / `SystemExit` 一起吞掉，
使 Ctrl-C 失效、故障被静默降级为默认值。

**建议**：统一改 `except Exception as e: log.debug(...)`，让不可恢复异常正常向上传播。

### 2.8 🟠 死变量 + 阈值双轨

- `compute()` 里 `detected_problems / opportunities / resolvers`
  （第 1477-1479）创建后从未使用；
- `raw_manas = harmony_strength`（第 1502）赋值后从未使用；
- 阈值双轨：类常量 `ACTION_THRESHOLD = 0.5`（第 928），
  但 `_determine_action_type`（第 1313-1316）实际用 `>0.6` / `>0.4` 分档，
  `_get_gate_reason`（第 1602）又按 `>0.5` 判定"✓通过"。
  → **可能出现 should_act=True 但 reason 显示"✗未通过"** 的自相矛盾输出。

### 2.9 🟠 子引擎各自维护滑窗 + 魔法数，无统一配置

`TimingEngine`（volatility_history）、`RegimeEngine`（trend_history）、
`ConfidenceEngine`（pnl/hit_rate_history）、`RiskEngine`（drawdown_history）、
`MetaManas`（pnl_trend/aggressiveness）各自维护滑动窗口与硬编码阈值
（0.7 / 1.3 / 0.05 / 0.6 / 0.02 / 5 …），窗口长度、衰减方式、阈值全部散落在方法里。

**建议**：抽 `ManasConfig`（权重、阈值、窗口长度集中）+ 一个
`RollingWindow` 小工具类，消除 5 处重复的 append/pop/裁剪逻辑。

---

## 3. 两者共有的结构性问题

1. **"能跑即通过"的异常策略**：core 层 HTTP 静默返回 None；manas 层 15 处裸 except。
   故障只会被降级、不会暴露。
2. **import 副作用**：core 的 builtins 污染 + 导入即启动线程；manas 的 `__init__` 即订阅。
   都无法在测试中干净隔离。
3. **单例/装配不收敛**：core 的 `Namespace` 全局字典 + `SR()` 注册表 + `AppContainer`
   三套对象定位并存；manas 直接体现为双 Manager 分裂。
4. **文档与实现漂移**：core.py 340 行 docstring 描述的行为与代码多处不符
   （`asynchronous` 参数、`__all__` 里不存在的名字）；manas 头部公式完全错位。

---

## 4. 建议的重构优先级（按性价比）

### P0（低风险、高收益，可立即做）
1. 删除 6 处 `SR` 死导入：`manas_engine.py:102`、`kernel.py:17`、`state_updater.py:13`、
   `state.py:11`、`values/system.py:13`、`os_kernel.py:23`。
2. 删除死代码：`container._create_manas_engine`、`manas_manager._global_manager(+_initialized)`、
   `setup_manas_manager`、`compute()` 里的 `detected_problems/opportunities/resolvers/raw_manas`。
3. `manas_engine.py` 15 处 `except:` → `except Exception as e:`（附日志）。
4. 修正 `manas_engine.py` 头部公式，或让实现回归公式——至少先让二者一致。
5. 统一 action 阈值（`ACTION_THRESHOLD` 与 `_determine_action_type` 的 0.6/0.4 二选一）。

### P1（中等改动，结构性收益）
6. core：抽 `_handle_awaitable()`，消除 8 处异步模板复制。
7. core：删除 `builtins` 注入 + 移除模块级内置名遮蔽（`print/range/sum/...`）。
8. manas：`ManasManager` 单例收敛到一处；保证全进程只有一个 ManasEngine。
9. manas：事件订阅移出 `__init__`，改由 application 层注册（对齐 §6.3），
   并解决同名重复订阅。
10. manas：`_supply_chain_state` 字典拆分为语义化 dataclass。

### P2（较大重构，需排期）
11. core：`core.py` 按职责拆分；`core/__init__` 去星号、消除循环导入。
12. manas：`compute()` 的加成/折扣抽成 `Modifier` 链；`ManasOutput` 分组。
13. manas：引入 `ManasConfig` + `RollingWindow`，收敛魔法数与滑窗逻辑。
14. core：明确统一的错误传播契约，HTTP 层不再静默返回 None。

---

*评估基于对 deva/core 全量模块、manas_engine/manas_manager/kernel、
container/register/cognitive_bus 装配点的通读。*

---

## 5. P0 执行记录（2026-10-10）

P0 五项已全部落地并验证。**未改动任何实现语义**，公式类问题采用「文档回归实现」
而非「实现回归文档」，避免影响线上交易决策行为。

| # | 项目 | 改动 | 验证 |
|---|------|------|------|
| 1 | 6 处 `SR` 死导入 | 删除 `manas_engine.py` / `kernel.py` / `state.py` / `state_updater.py` / `values/system.py` / `os_kernel.py` 的 `from deva.naja.register import SR` | 六文件 `grep SR` 为空 |
| 2 | 死代码 | 删 `container._create_manas_engine`、`manas_manager._global_manager(+_initialized)`、`setup_manas_manager`（含 `kernel/__init__` 的导入与 `__all__` 项）；删 `compute()` 内 `detected_problems/opportunities/resolvers/raw_manas` | 全仓 grep 无残留；`__all__` 全部可解析 |
| 3 | 裸 except | 19 处 `except:` → `except Exception as e:` + `log.debug`（manas_engine 16、kernel 2、decision_attention 1）；`decision_attention.py` 新增 logger | `attention/kernel` 包内 `grep "except:"` 为空 |
| 4 | 公式脱节 | 重写模块头部「公式」段，改为与实现一致的描述（risk 反函数、乘性调节链、T 与 manas_score 无关、"increase T" 未落地） | 人工核对 `compute()` / `RiskEngine.compute` / `MetaManas` |
| 5 | 阈值双轨 | 新增 `STRONG_ACTION_THRESHOLD = 0.6`；`_determine_action_type` 移除恒真的 `> 0.4` 死条件；`_get_gate_reason` 改为按 `action_type != HOLD` 判定，并在豁免时显式标注 | 30603 组输入穷举对比，**0 差异** |

### 5.1 阈值矛盾的成因与修法

`_determine_action_type` 有一条**共振通道**：`RESONANCE 且 timing > 0.7 → ACT_FULLY`，
**完全不看分数**。而 `_get_gate_reason` 只按 `manas_score > ACTION_THRESHOLD` 判定，
于是「分数 0.30 但判 ACT_FULLY」时会出现 `should_act=True` 却显示 `✗未通过`。

修法：gate 结论统一由 `action_type != HOLD` 导出（与 `compute()` 的 `should_act` 同源），
并在分数未达门槛却放行时追加 `(分数0.30≤0.5，由共振/强时机豁免)` 说明，
**既不改变放行行为，又消除了自相矛盾的输出**。

### 5.2 遗留（未处理，属 P1/P2）

- 2.3 事件订阅写在 `__init__` + 固定名重复订阅
- 2.4 `ManasManager` 双单例分裂（register 注入 kernel 并 enable / container 不 enable），
  叠加 `AttentionKernel._init_manas_engine` → 潜在 3 个 `ManasEngine`
- 2.2 `compute()` 上帝方法、`_supply_chain_state` 字典上帝对象
- 1.1 core 异步模板 8 处复制、1.2 builtins 污染
