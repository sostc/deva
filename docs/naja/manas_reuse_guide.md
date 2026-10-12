# manas 复用指南（把决策中枢当通用原语用）

> 面向**本仓之外**的使用方：如何在不引入交易系统的前提下，单独使用 manas 的决策能力。
>
> 公共入口只有一个：`deva.naja.manas`
> 验证脚本：`scripts/verify/verify_manas_standalone.py --strict`
> 最小示例：`deva/examples/manas_standalone.py`
> 典型案例（完整小应用）：`deva/examples/manas_decision_desk.py`（见 §8）

---

## 1. manas 是什么

一个**持续输出「是否行动 / 多确信 / 多危险」的内在决策中枢**。它不决定「买什么」
（那是方向层的活），只决定「现在该不该动、动多少」。

四个子引擎各看一个角度：

| 子引擎 | 看的角度 | 回答的问题 | 对应输出 |
|---|---|---|---|
| `TimingEngine` | 微观时机 | 现在能动手吗？ | `timing_score` |
| `RegimeEngine` | 宏观环境 | 大方向顺吗？ | `regime_score` |
| `ConfidenceEngine` | 策略适配度 | 我的策略还管用吗？ | `confidence_score` |
| `RiskEngine` | 客观风险 | 市场能杀我多少？ | `risk_temperature`（T） |
| `MetaManas` | 主观偏差 | 我自己会作死吗？ | `bias_correction` |

融合后产出 `manas_score` + 行动门 `should_act` / `action_type` + 置信度 `alpha`。

**关键在于：它不需要任何交易对象。** 四路输入全部通过显式契约（Protocol）提供，
喂 dict 即可跑出真实分数。

---

## 2. 三种用法

### 2.1 最直接：自己 new 引擎，自己喂输入

```python
from deva.naja.manas import DictBackedInputs, ManasEngine, ManasConfig

src = DictBackedInputs(
    market_status="open", remaining_seconds=3600, market_volatility=1.8,
    ticks={"600000": 1.2, "000001": -0.4}, us_trading_phase="trading",
    available_capital=30.0, total_capital=100.0, total_return=-4.0,
    position_returns=[0.02, -0.01, 0.03], total_trades=12,
)
out = ManasEngine(config=ManasConfig(update_interval=0.0)).compute(
    session_manager=src, scanner=src, portfolio=src, bandit_tracker=src
)
print(out.manas_score, out.action_type.value, out.alpha, out.risk_temperature)
```

### 2.2 便利封装：引擎 + 输入源一起管

```python
from deva.naja.manas import create_engine

session = create_engine(throttle=False,            # 关掉 1 秒结果缓存
                        market_status="open", remaining_seconds=3600, ...)
out = session.compute()

session.update(market_volatility=2.6)               # 改输入
out2 = session.compute()                            # 立即重算
```

`ManasSession` 只是「引擎 + 一个可变 `DictBackedInputs`」的转发，**不含任何决策逻辑**。

### 2.3 接自己的数据源：实现四个契约

不要用 `DictBackedInputs` 硬凑——把你自己的对象实现成契约要求的形状即可
（鸭子类型，无需继承）：

```python
from deva.naja.manas import check_contract

print(check_contract(my_clock, "ClockView"))        # [] 表示满足，非空 = 缺哪些方法
```

`check_contract` 对**类**也能用（按类属性检查，不必实例化）。

---

## 3. 输入契约（改数据源前先看这张表）

| 契约 | 必需方法 | 生产实现（本仓） |
|---|---|---|
| `ClockView` | `get_market_status(market_id)` / `get_session_remaining_seconds(market_id)` | `MarketSessionManager` |
| `MarketView` | `get_market_volatility()` / `get_last_data()` / `get_market_summary()` / `get_liquidity_adjustment(target_market)` | `GlobalMarketScanner` |
| `PortfolioView` | `get_summary()` | `VirtualPortfolio` |
| `StrategyView` | `get_position_history(limit)` / `get_strategy_summary(strategy_id)` | `BanditPositionTracker` |

**方法缺失不是「安全兜底」，而是把整个维度摘掉**：

| 缺失的东西 | 后果 |
|---|---|
| `ClockView.get_market_status` / `get_session_remaining_seconds` | `time_pressure` 恒 0.5 |
| `MarketView.get_market_volatility` | Timing 波动率维恒 0.5、**Risk 恒 1.0** |
| `MarketView.get_last_data` | 成交密度、指数趋势、题材扩散恒 0 |
| `PortfolioView.get_summary` | `cash_ratio` 恒 0.5、`drawdown` 恒 0 → **T 恒 1.25** |
| `StrategyView.*` | `hit_rate` 恒 0.5 → **confidence 恒 0.35** |

> 这正是本仓踩过的「静默失效」：`try/except` + 鸭子类型下，
> 「对象没这个方法」与「数据恰好等于默认值」在外部完全不可区分。
> 接新数据源时**先跑 `check_contract`**。

### 单位口径（踩过坑，务必对齐）

- `PortfolioView.get_summary().total_return`：**百分数**口径（`-4.0` 表示 −4%）。
  与生产实现、其 UI、`attention/kernel/state.py` 的阈值（−5 / −2 / 10）一致；
  manas 内部加档阈值是小数口径（0.05 / 0.1），消费时自行 `/100` 归一。
- `total_capital` 是 `cash_ratio = available / total` 的**分母**，缺了会退化成
  「可用资金的数值本身」，T 随之撞下限。
- `MarketView.get_liquidity_adjustment(...)['adjusted_signal']`：0~1。

---

## 4. 输出

`compute()` 返回 `ManasOutput`（dataclass，**23 个字段**）。两种取法：

```python
out = session.compute()
out.manas_score              # 扁平取，既有写法
out.to_dict()                # 扁平 dict（23 键）
out.to_grouped_dict()        # 8 组嵌套视图，可直接 json.dumps
out.group("gate")            # 取单组；未知组名抛 KeyError（不静默返回空）
```

分组见模块级 `MANAS_OUTPUT_GROUPS`（`deva.naja.manas.MANAS_OUTPUT_GROUPS`）：
`scores` / `harmony` / `gate` / `bias` / `attention` / `cognition` / `portfolio` / `focus`。

**`action_type` 的档位严格程度**（`ActionType`）：
`hold(0) < act_minimally(1) < act_carefully(2) < act_fully(3)`。
本仓的铁律是「决策/融合层只能下调、不能上调」——你复用时可以沿用这条，
也可以按自己的授权模型重定义，但**别让下游偷偷加仓权限**。

---

## 5. 复用时的四个坑

1. **`compute()` 默认缓存 1 秒**（`ManasConfig.update_interval`）。
   同一秒内改输入再算，拿到的是上一次的输出——这是设计不是 bug。
   要每次立即重算：`ManasConfig(update_interval=0.0)` 或 `create_engine(throttle=False)`。
2. **`alpha` 常被下限支配**。`α = clamp(confidence × harmony, 0.3, 1.5)`，
   两个乘子自然落在 [0, 0.6]，多数场景撞 `alpha_min = 0.3`。
   这是**打分公式**维度的问题，想让 α 有区分度得重新定标，不是调 clamp。
3. **觉醒等级默认恒 `dormant`**。本仓的觉醒是**短时放大器**（弱信号半衰期 60 秒），
   仓外使用时通常不注入——调节链的 awakening 环节恒 ×1.0，这是正常状态。
   确有需要可以 `engine.set_awakening_level_provider(fn)` 注入 `() -> str`。
4. **`ManasEngine` 的觉醒默认不订阅事件**。构造期不自动订阅（历史上多实例会重复
   挂载同名订阅者）。仓外一般用不到；要用再调 `subscribe_cognitive_events(event_bus)`。

---

## 6. 加载期代价（已解耦，附数字）

改造前：`import deva.naja.attention.kernel.manas_engine` = **3.4s / 3158 个模块**，
其中 10 个是 `TradingCenter` / `AttentionOS` / `orchestration.*` ——纯粹被包入口的
eager 重导出拖进来的。

改造后（本仓 `attention/__init__.py` 与 `kernel/__init__.py` 改为 PEP 562 惰性导出）：

| 指标 | 改造前 | 改造后 |
|---|---|---|
| 导入耗时 | 3.4s | **~0.9s** |
| 模块总数 | 3158 | **~1338** |
| 交易域模块 | 10 | **0** |
| `import` 门面后 `sys.modules` 含 `trading_center` | 是 | **否** |

剩下的 ~0.9s 是 `deva` 命名空间的固定成本（`import deva` 本身就 ≈1.0s），
与 attention/manas 无关。**若你的应用连这 0.9s 也不想付**，只能把
`manas_engine.py` / `manas_config.py` / `manas_inputs.py` 三个文件物理抽成
不依赖 `deva` 的独立包——那属于独立立项，本轮未做（理由见 §7）。

---

## 7. 明确不做 / 边界

- **不做物理抽包**。三个文件确实零 `deva` 依赖、技术上能抽走，但抽走后就要维护
  两份（或引入 subtree/发布流程）。**等真有第二个应用落地再抽**，现在抽是提前
  给自己造分叉。
- **不重构打分公式**。α 下限支配问题（§5.2）是公式维度，不在复用范围内。
- **不含实盘**。manas 只输出「该不该动」，不下单；本仓的「行动」= 虚拟持仓 + 落盘 + 通知。
- **不做多实例全局单例**。`ManasEngine` 是普通类，随便 new；本仓的全局单例
  （`ManasManager`）是仓库内的装配选择，不是你复用时必须遵守的约束。

---

## 8. 典型案例：独立择时决策台

`manas_standalone.py` 是「最小用法」；想拿一个**完整小应用**当骨架，看：

```
deva/examples/manas_decision_desk.py          # 案例脚本（约 300 行，含控制台与 HTML 报告）
deva/examples/data/manas_typical_day.json     # 一天的 6 个快照（可换成你自己的数据）
```

它模拟一个**不属于交易系统**的独立脚本：读入一天的 6 个市场快照，逐点问 manas
「现在该不该动」，把判断 + 应用自己的仓位纪律落成一张决策时间线。

```
JSON 快照 ──► manas（判断） ──► 应用策略（决策） ──► 控制台 / HTML 报告
```

跑法：

```bash
/Users/spark/.local/bin/python3 deva/examples/manas_decision_desk.py --out /tmp/report.html
```

案例刻意展示的三个边界（**都是真实输出**，不是设定值）：

1. **manas 只给判断，不给决策**。脚本里的 `ACTION_POLICY`（档位 → 目标仓位）是
   *示例应用自己* 的纪律，不属于 manas。要本仓那套乘子公式才去 `import deva.naja.decision`。
2. **行动门保守，只在窄窗口开**：6 个时点只有 1 个开门——`manas_score > 0.5` 要求
   「低回撤 + 高现金 + 低波动」同时成立。关门的理由还各不相同（策略不自信 / 环境阻力 /
   顺风但差一点分数），这也正是 `action_gate_reason` 的用处。
3. **引擎有状态，复用时路径相关**：案例全程复用同一个 `ManasSession`（同一天、同一观察者）。
   RiskEngine 的回撤取**历史均值**，所以流式结果与「每点各新建引擎」会轻微不同——
   案例里 11:15 的 T：流式 `1.488`、独立 `1.637`。要「彼此独立的快照」就每点新建引擎。

---

## 9. 验证

```bash
cd <项目根>
/Users/spark/.local/bin/python3 scripts/verify/verify_manas_standalone.py --strict
```

检查项（7 组）：子进程导入无交易域依赖 / 门面是同一份实现（非副本）/
`__all__` 名字都可取 / 端到端非退化 / 静态守卫（入口保持惰性）/
旧用法未被破坏 / **典型案例端到端**（案例必须至少开一次行动门且有区分度）。
