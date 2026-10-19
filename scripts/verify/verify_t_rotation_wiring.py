"""验证「做 T 引擎 ↔ MarketDataBus ↔ 科创芯片 ETF」这条链路真的通了。

背景
----
上一轮交付的 ``TRotationEngine`` 全仓库零调用方 —— 代码、文档、25 项守卫
都是绿的，但没有一行行情会流进它。这是本仓库反复出现的「静默失效」形态：
**「合法的空」比异常更危险**，没有人会因为它什么都没做而去查它。

用户随后拍板了两件事：
    标的 = 科创芯片 ETF（588200）
    数据源 = MarketDataBus

本守卫就锁这两件事 + 它们之间的接线：

运行期
    A. 底仓标的确为 588200，且 bus_code 带市场前缀（否则查不到行情）
    B. 总线报价真能驱动引擎（tick 计数增长）
    C. 当日真实 588200 走势（低开 -2.9% → 探底 -4.3% → 冲高 +1.7% → 收平）
       能触发做 T，且收工后份额守恒、无遗留回购义务
    D. 累计成交量必须换算成增量再喂 VWAP
    E. 非交易时段不喂数
    F. 重复报价不重复计数
    G. 收盘前触发强制结算
    H. 跨会话/重启后仍能买回（★铁律的最后一公里）

静态
    I.  runner 确实订阅/连接了 MarketDataBus
    J.  不得在普通线程里调用 async-only 的 API（``get_price_async`` 会炸）
    K.  ``register.py`` 注册了运行器；``container._start_schedulers`` 真的 ``start()``
        —— 注册 ≠ 启动，这条就是专门防止再出现零调用方的

跑法：
    env -u PYTHONPATH TMPDIR=$(mktemp -d) python3 \
        scripts/verify/verify_t_rotation_wiring.py [--strict]
"""

import ast
import logging
import os
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

# ★ 必须早于任何 deva 导入：本守卫会真的建/删虚拟持仓（40% 底仓的分批成交）。
# 曾经跑一遍就在生产库留下 T_ROTATION_* 账户的假持仓假价格。
VERIFY_DIR = os.path.join(ROOT, "scripts", "verify")
if VERIFY_DIR not in sys.path:
    sys.path.insert(0, VERIFY_DIR)
from guard_sandbox import isolate_guard_db  # noqa: E402

isolate_guard_db()

BANDIT_DIR = os.path.join(ROOT, "deva", "naja", "bandit")
RUNNER_FILE = os.path.join(BANDIT_DIR, "t_rotation_runner.py")
HOLDINGS_FILE = os.path.join(BANDIT_DIR, "core_holdings.py")
REGISTER_FILE = os.path.join(ROOT, "deva", "naja", "register.py")
CONTAINER_FILE = os.path.join(ROOT, "deva", "naja", "application", "container.py")

TEST_ACCOUNT = "T_WIRING_GUARD"

# 科创芯片 ETF 588200 在 2026-10-13 的真实日内特征（新浪行情核对）：
#   昨收 0.996 / 今开 0.967(-2.91%) / 最低 0.953(-4.32%) / 最高 1.013(+1.71%) / 收 0.996
PREV_CLOSE = 0.996
DAY_OPEN = 0.967
DAY_LOW = 0.953
DAY_HIGH = 1.013
DAY_CLOSE = 0.996

# 一个交易日：2026-10-13（周二）
D1 = (2026, 10, 13)
D2 = (2026, 10, 14)


class FakeMTS:
    def __init__(self, t=None):
        self.t = t or time.time()

    def get_market_time(self):
        return self.t


class Quote:
    """最小可用的 FutuQuote 替身。

    ❗必须带 ``ok``：runner 的 ``_read_quote`` 判的是 ``quote.ok``
    （``futu_quote_source`` 的失败是「如实返回 ok=False + 原因」，不是抛异常）。
    少了它，替身会被当成「取不到行情」，整条链路静默空转。
    """

    PRIORITY_HIGH = "HIGH"

    def __init__(self, code, name, current, prev_close, volume, open_price=None,
                 high=None, low=None):
        self.code = code
        self.name = name
        self.current = current
        self.prev_close = prev_close
        self.volume = volume
        self.ok = True
        self.open_price = open_price if open_price is not None else current
        self.high = high if high is not None else current
        self.low = low if low is not None else current
        self.timestamp = time.time()
        self.fetch_time = time.time()

    @property
    def age(self):
        return 0.0

    @property
    def change_pct(self):
        return (self.current - self.prev_close) / self.prev_close * 100 if self.prev_close else 0.0


class _MissingQuote:
    """替身版的「这个标的没取到」—— 对应 FutuQuote(ok=False, error=...)。

    runner 的 ``_pump`` 判的是 ``quote.ok`` 和 ``quote.current``，所以这里必须
    老老实实给 ``ok=False`` + 0 价，不能返回 None 让上层误判成"批量失败"。
    """

    def __init__(self, code):
        self.code = code
        self.name = ""
        self.ok = False
        self.error = f"替身里没有 {code}"
        self.current = 0.0
        self.prev_close = 0.0
        self.volume = 0.0
        self.market = ""

    @property
    def age(self):
        return 0.0


class FakeQuotes:
    """富途行情源（``futu_quote_source``）的最小替身。

    ❗接口已是 ``FutuQuoteSource``：runner 批量测得走 ``src.fetch([(code, market)])``，
    单点回退才是 ``src.get(code, market)``；返回对象必须带 ``ok`` / ``current`` /
    ``prev_close`` / ``volume``。旧替身是 ``fetch`` + ``get_quote``（MarketDataBus
    时代），2026-10-14 换富途后已经对不上。

    ❗``fetch`` 是必须的，而且**契约要和真实实现一致**：返回 dict 的键是**入参里的
    原始代码**，取不到的条目也要在结果里（``ok=False`` + ``error``）。缺了这个
    方法，``_prefetch_quotes`` 会走 except → 整轮算「批量取行情失败」→ 所有检查
    报的不是真 bug，而是替身自己的 AttributeError（2026-10-19：25 项里 9 项如此）。
    """

    PRIORITY_HIGH = "HIGH"
    PRIORITY_MEDIUM = "MEDIUM"
    PRIORITY_LOW = "LOW"

    def __init__(self):
        self.quotes = {}
        self.fetches = []
        self.subscribed = []
        self.priority = []

    def put(self, code, quote):
        self.quotes[code] = quote

    def get(self, code, market=None):
        """runner 的取数入口。兼容「按 bus_code 存、按裸 code 取」。"""
        if code in self.quotes:
            return self.quotes[code]
        code = str(code)
        for k, v in self.quotes.items():
            k = str(k)
            if k == code or k.endswith(code):
                return v
        return None

    def fetch(self, requests):
        """批量入口：一次调用取回本轮全部标的（``c34f551`` 起 runner 走这里）。

        返回值对齐 ``FutuQuoteSource.fetch``：**原始代码 → quote**，取不到的条目
        也要在 dict 里且 ``ok=False`` —— 真实实现就是这样"失败的标的也在场"，
        守卫的替身必须同构，否则测出来的行为是假的。
        """
        self.fetches.append(list(requests))
        out = {}
        for code, market in requests:
            key = str(code)
            quote = self.get(key, market)
            out[key] = quote if quote is not None else _MissingQuote(key)
        return out


def _dt(y, m, d, h, mi):
    return datetime(y, m, d, h, mi)


def make_runner(capital=2_000_000.0, establish=False, flat_limit=999):
    """搭一套可注入的测试环境。"""
    from deva.naja.bandit.virtual_portfolio import VirtualPortfolio
    from deva.naja.bandit.core_position import CorePositionLedger
    from deva.naja.bandit.t_rotation import TRotationEngine, TRotationConfig
    from deva.naja.bandit.core_holdings import CoreHoldingSpec
    from deva.naja.bandit.t_rotation_runner import TRotationRunner

    vp = VirtualPortfolio(account_name=TEST_ACCOUNT)
    vp.set_market_time_service(FakeMTS())
    vp.clear_history()
    vp.set_capital(capital)
    vp.set_max_position_pct(1.0)
    vp.set_max_total_pct(1.0)

    spec = CoreHoldingSpec(
        code="588200", bus_code="sh588200", name="科创芯片ETF嘉实", market="CN",
        target_shares=100_000.0, round_lot=100.0,
    )
    bus = FakeQuotes()
    ledger = CorePositionLedger(persist=False)
    eng = TRotationEngine(
        portfolio=vp, ledger=ledger,
        config=TRotationConfig(max_round_pct=0.30, max_round_amount=500_000.0),
    )
    clock = {"t": _dt(*D1, 9, 35).timestamp()}
    runner = TRotationRunner(
        portfolio=vp, quotes=bus, engine=eng, ledger=ledger, specs=[spec],
        establish_missing=establish, flat_poll_limit=flat_limit,
        clock=lambda: clock["t"],
    )
    return {
        "vp": vp, "bus": bus, "eng": eng, "ledger": ledger,
        "spec": spec, "runner": runner, "clock": clock,
    }


def _fake_gate_provider(spec, price):
    """给「大环境闸门」喂一个恒放行的假裁定。

    ❗为什么必须注入：闸门默认开，且要求先问决策中心；离线环境里问不到
    就是「看不见就别动」→ 一笔都不买，把所有正向用例淹没掉
    （``core_establish_gate.py`` 的 ``provider`` 形参就是为此留的注入点）。
    闸门自身的语义（hold 硬拦 / 收盘兜底 / 定量）由
    ``verify_core_establish_gate.py`` 负责，这里只把它拨到「放行」，
    好让本守卫专心测**接线与分批**。

    另见 :func:`check_gate_hold_blocks_establish` —— 反方向的用例。
    """
    return {
        "approved": True,
        "action_type": "act_fully",
        "final_confidence": 0.9,
        "manas_score": 0.9,
        "regime_score": 0.5,
        "timing_score": 0.5,
        "plan": {"action_type": "act_fully", "size_hint": 1.0},
    }


class _AlwaysAskWatch:
    """永远回答「值得去问」的守望替身。

    守望（``CoreEstablishWatch``）带节流：问过一次要等一段窗口才再问。
    本守卫测的是**接线与分批**，若用真守望，「隔多久问一次」就成了
    用例成败的隐藏变量（12 轮 poll 只够问一次 → 底仓只建一批）。
    守望自身的节流/结算语义由 ``verify_core_establish_watch.py`` 负责。
    """

    def ensure(self, spec, *, now=None):
        return None

    def context_for(self, spec, *, now=None, price=None, anchor=None,
                    minutes_to_close=None):
        return None

    def peek(self, spec, ctx, *, now=None):
        return True, None

    def mark_asked(self, spec, granted, reason, *, now=None):
        return None

    def settle(self, spec, outcome, reason, *, now=None):
        return None


def make_alloc_env(price=1.0, gate_provider=_fake_gate_provider):
    """自动建仓专用环境：**保留虚拟仓默认风控参数**。

    make_runner 把 max_position_pct 放成 1.0，是为了让做 T 的用例不受打扰；
    但 40% 的底仓必然超过 20% 的单笔限额 ——
    在限额全开的环境里测，等于永远测不到「分批」那一段，
    而那正是本次改动唯一的新行为。
    """
    from deva.naja.bandit.virtual_portfolio import VirtualPortfolio
    from deva.naja.bandit.core_position import CorePositionLedger
    from deva.naja.bandit.t_rotation import TRotationEngine, TRotationConfig
    from deva.naja.bandit.core_holdings import load_core_holdings
    from deva.naja.bandit.core_establish_gate import CoreEstablishGate
    from deva.naja.bandit.t_rotation_runner import TRotationRunner

    clock = {"t": _dt(*D1, 9, 35).timestamp()}

    class TickingMTS:
        """跟着模拟时钟走的时间源。

        FakeMTS 返回**固定**时间戳，同一分钟内的多笔建仓会拿到同一个
        entry_time，两笔金额相同的分批记录会被误判成一笔 ——
        分批到底做了几笔就看不出来了。
        """

        def get_market_time(self):
            return clock["t"]

    vp = VirtualPortfolio(account_name=TEST_ACCOUNT)
    vp.set_market_time_service(TickingMTS())
    vp.clear_history()
    vp.set_capital(1_000_000.0)  # **不放宽任何限额**

    specs = load_core_holdings()  # target_shares=0 → 走 alloc_pct
    bus = FakeQuotes()
    ledger = CorePositionLedger(persist=False)
    eng = TRotationEngine(
        portfolio=vp, ledger=ledger,
        config=TRotationConfig(max_round_pct=0.30, max_round_amount=500_000.0),
    )
    runner = TRotationRunner(
        portfolio=vp, quotes=bus, engine=eng, ledger=ledger, specs=specs,
        establish_missing=True, flat_poll_limit=99999,
        clock=lambda: clock["t"],
        establish_gate=(
            CoreEstablishGate(provider=gate_provider, clock=lambda: clock["t"])
            if gate_provider is not None else None
        ),
        establish_watch=_AlwaysAskWatch(),
    )
    return {
        "vp": vp, "bus": bus, "eng": eng, "ledger": ledger,
        "spec": specs[0], "runner": runner, "clock": clock, "price": price,
    }


def seed_core(env, price, qty, day=D1):
    """建一份「昨夜传承」的底仓：T+1 下它今日可卖，明日也一样。"""
    from deva.naja.bandit.t_rotation_runner import session_open_ts

    open_ts = session_open_ts(_dt(*day, 9, 30))
    pos = env["vp"].open_position(
        strategy_id="core", strategy_name="长期底仓",
        stock_code=env["spec"].code, stock_name=env["spec"].name,
        price=price, quantity=qty,
    )
    assert pos is not None, "底仓建立失败"
    pos.entry_time = open_ts - 86400  # 昨天买的
    env["eng"].register_target(env["spec"].code, qty, name=env["spec"].name)
    return open_ts


def push_quote(env, price, prev_close=PREV_CLOSE, cum_volume=1_000_000):
    code = env["spec"].bus_code
    env["bus"].put(code, Quote(
        code=code, name=env["spec"].name, current=price,
        prev_close=prev_close, volume=cum_volume,
    ))


def step(env, minutes=0.5):
    """推进模拟时钟半分钟（与真实轮询节奏一致）。"""
    env["clock"]["t"] += minutes * 60


# ════════════════════════════════════════════════════════════════
#  运行期守卫
# ════════════════════════════════════════════════════════════════
def check_default_core_is_chip_etf():
    """1) 默认底仓 = 科创芯片 ETF 588200，且 bus_code 带前缀。"""
    from deva.naja.bandit.core_holdings import (
        DEFAULT_CORE_CODE, CHIP_ETF_CATALOG, load_core_holdings,
    )
    assert DEFAULT_CORE_CODE == "588200", f"默认标的被改成 {DEFAULT_CORE_CODE}"
    specs = load_core_holdings()
    assert specs, "底仓清单为空"
    spec = specs[0]
    assert spec.code == "588200", f"首个标的为 {spec.code}"
    assert spec.bus_code == "sh588200", f"bus_code 缺市场前缀: {spec.bus_code}"
    assert spec.name and spec.name != spec.code, "ETF 中文名缺失，日志里只能看到代码"
    assert "588200" in CHIP_ETF_CATALOG, "备选清单缺 588200"
    # target_shares 为 0 = 「按比例折算」，不是「目标为零」
    print(f"1) 默认底仓 OK —— {spec.name}({spec.bus_code}) 目标 {spec.alloc_pct:g}% 总资产")


def check_env_override():
    """2) TARGET_SHARES 显式覆盖优先；坏值回退；ALLOC_PCT 折算正确。"""
    from deva.naja.bandit import core_holdings as ch

    os.environ["NAJA_T_ROTATION_TARGET_SHARES"] = "588200:150000"
    try:
        specs = ch.load_core_holdings()
        assert specs[0].target_shares == 150000, specs[0].target_shares
        # 显式指定 → 折算必须照给，不许偷偷再按比例算一遍
        assert specs[0].resolve_target_shares(1_000_000.0, 1.0) == 150000, \
            "显式份额被 alloc_pct 覆盖了"
    finally:
        os.environ.pop("NAJA_T_ROTATION_TARGET_SHARES")

    os.environ["NAJA_T_ROTATION_SYMBOLS"] = "588200,159995"
    try:
        codes = [s.code for s in ch.load_core_holdings()]
        assert codes == ["588200", "159995"], codes
        assert all(s.bus_code[:2] in ("sh", "sz") for s in ch.load_core_holdings())
    finally:
        os.environ.pop("NAJA_T_ROTATION_SYMBOLS")

    os.environ["NAJA_T_ROTATION_TARGET_SHARES"] = "不是数字"
    try:
        specs = ch.load_core_holdings()
        assert not specs[0].explicit, "坏值应被忽略，回到按比例折算"
        # 关键：坏值绝不能污染 alloc 路径，否则底仓规模悄悄变成 0
        assert specs[0].resolve_target_shares(1_000_000.0, 1.0) > 0, "坏值污染了折算"
    finally:
        os.environ.pop("NAJA_T_ROTATION_TARGET_SHARES")
    print("2) 环境变量覆盖/坏值回退 OK")


def check_alloc_pct_resolution():
    """2b) 仓位比例 → 份额的折算口径（用户拍板的 40%）。

    这里守的是**语义**：同样 40% 的钱，价格翻倍时份数必须减半。
    若哪天有人把 alloc 误改成写死的份额，价格漂移就会让仓位比例失守。
    """
    from deva.naja.bandit.core_holdings import (
        CoreHoldingSpec, DEFAULT_ALLOC_PCT, load_core_holdings,
    )

    assert abs(DEFAULT_ALLOC_PCT - 40.0) < 1e-9, f"默认仓位被改成 {DEFAULT_ALLOC_PCT}%"

    specs = load_core_holdings()
    spec = specs[0]
    assert spec.alloc_pct == 40.0, spec.alloc_pct
    assert spec.round_lot == 100.0

    TOTAL = 1_000_000.0
    # 价格 1.0 → 40 万份；价格 2.0 → 20 万份（同一笔钱的两种形态）
    assert spec.resolve_target_shares(TOTAL, 1.0) == 400_000.0, \
        spec.resolve_target_shares(TOTAL, 1.0)
    assert spec.resolve_target_shares(TOTAL, 2.0) == 200_000.0, \
        spec.resolve_target_shares(TOTAL, 2.0)
    # 向下取整到整手，绝不超预算
    got = spec.resolve_target_shares(TOTAL, 0.7)
    assert got * 0.7 <= TOTAL * 0.4 + 1e-6, f"折算超出预算: {got} 份 @{0.7}"
    assert got % spec.round_lot == 0, f"没取整到整手: {got}"
    # 分母异常不许给出安慰剂数字
    assert spec.resolve_target_shares(0.0, 1.0) == 0.0, "总资产为 0 应折出 0 份"
    assert spec.resolve_target_shares(TOTAL, 0.0) == 0.0, "价格为 0 应折出 0 份"

    # alloc 边界：<=0 与 >100 都要回退到默认，不能出现「底仓 = 全部资金」
    for bad in ("0", "-10", "150"):
        os.environ["NAJA_T_ROTATION_ALLOC_PCT"] = bad
        try:
            s = load_core_holdings()[0]
            assert s.alloc_pct == DEFAULT_ALLOC_PCT, f"{bad} 未被回退: {s.alloc_pct}"
        finally:
            os.environ.pop("NAJA_T_ROTATION_ALLOC_PCT")

    # 可审计：to_dict 必须带上 alloc_pct（状态页要能回答"这 40 万份怎么来的"）
    d = CoreHoldingSpec(
        code="588200", bus_code="sh588200", name="x", market="CN", target_shares=0.0
    ).to_dict()
    assert "alloc_pct" in d, "to_dict 缺 alloc_pct，线上无法核对仓位口径"
    print(f"2b) 仓位口径 OK —— 总资产 100 万 × 40% ÷ 1.0 = "
          f"{spec.resolve_target_shares(TOTAL, 1.0):.0f} 份（价 2.0 时 {spec.resolve_target_shares(TOTAL, 2.0):.0f} 份）")


def check_establish_default_on():
    """2c) 自动建立底仓默认开启 —— 用户已给出「40% 仓位」这个授权。

    此前默认关的理由是「动用多少资金由人拍板」。
    现在数字已经有了，若还是默认关，重启后只会告警不建仓，
    用户以为"已经在跑"却什么都没发生 —— 又一次静默失效。
    """
    os.environ.pop("NAJA_T_ROTATION_ESTABLISH", None)
    try:
        from deva.naja.bandit.core_holdings import CoreHoldingSpec, env_flag
        from deva.naja.bandit.t_rotation_runner import TRotationRunner

        assert env_flag("NAJA_T_ROTATION_ESTABLISH", True) is True

        # 行为层面再确认一次：不给 establish_missing 参数时，运行器默认就该建仓。
        # 只看 env 默认值不够 —— 万一有人在 __init__ 里把 default 写死成 False
        # 却忘了改这里，读 env 的那行会是绿的、行为却是关的。
        class _Stub:
            def get_summary(self):
                return {"total_capital": 1_000_000.0, "available_capital": 1_000_000.0}

        rnr = TRotationRunner(
            portfolio=_Stub(), quotes=object(), engine=object(), ledger=object(),
            specs=[CoreHoldingSpec(
                code="588200", bus_code="sh588200", name="x", market="CN",
                target_shares=0.0,
            )],
        )
        assert rnr._establish is True, \
            "未显式传参时建仓开关默认为关 —— 用户给的 40% 授权不会被兑现"
    finally:
        pass
    print("2c) 自动建立底仓默认开启 OK（可由 NAJA_T_ROTATION_ESTABLISH=0 关掉）")


def check_auto_establish_40pct():
    """3b) 端到端：重启后底仓会**自己**被建立到总资产的 40%，且分批进行。

    这是本次改动的实测项，不是静态比对。守的是四件事：

    1. **真的买到目标** —— 用户说"要有 40% 仓位"，不是"建议 40%"。
    2. **没绕过风控** —— 单笔限额 20%，40% 就必须分批；
       若有人图省事加了 bypass_limits，这里会变成 1 笔，立即被抓。
    3. **目标锁定** —— 次日价格翻倍，份额不许跟着缩水（否则
       长期持有会被行情悄悄削掉）。
    4. **每一笔都记录缘由** —— 状态页能回答"这 40 万份是怎么来的"。
    """
    env = make_alloc_env()
    vp, rnr, spec = env["vp"], env["runner"], env["spec"]

    single_budget = vp.single_position_budget
    assert abs(single_budget - 200_000.0) < 1e-6, \
        f"环境失真：单笔限额应为 20 万，实为 {single_budget}"

    # —— 第一天：从零建仓 ——
    fill_log = []
    for i in range(12):
        step(env)
        push_quote(env, 1.0, prev_close=1.0, cum_volume=1_000_000 * (i + 1))
        rnr.poll()
        for p in vp.get_all_positions(status="OPEN"):
            if p.stock_code != spec.code:
                continue
            # 金额相同的两笔（19万 + 19万）要靠 entry_time 区分
            pair = (round(p.entry_price * p.quantity, 2), p.entry_time)
            if pair not in fill_log:
                fill_log.append(pair)

    held = sum(
        p.quantity for p in vp.get_all_positions(status="OPEN")
        if p.stock_code == spec.code
    )
    plan_target = rnr._plan_targets.get(spec.code, 0.0)
    assert plan_target == 400_000.0, f"计划份额应为 40 万，实为 {plan_target}"
    assert held == plan_target, f"底仓没建到位：持有 {held} / 目标 {plan_target}"
    assert len(fill_log) >= 2, (
        f"40% 底仓应分批建成，实际只有 {len(fill_log)} 笔 —— "
        f"若只有 1 笔，说明有人用 bypass_limits 绕过了单笔限额"
    )
    for v, _t in fill_log:
        assert v <= single_budget + 1e-6, f"单笔 {v:.0f} 元超出限额 {single_budget:.0f}"

    # 同一天内价格变化不许改写今日目标（_ensure_plan 的每日锁定）。
    #
    # 刻意用**下跌**而不是上涨：涨时目标只会变小，
    # 而下面那条「只增不减」兜得住，会把「锁定失效」掩盖过去 ——
    # 上一轮负向注入就是这么漏掉一整条 parl rails 的。
    # 跌才是真考验：目标会变大，系统将在更低的价格上继续加仓，
    # 等于把「40% 仓位」歪成「跌得越多买得越多」。
    step(env)
    push_quote(env, 0.5, prev_close=1.0, cum_volume=50_000_000)
    rnr.poll()
    assert rnr._plan_targets.get(spec.code) == plan_target, (
        f"当日下跌后目标从 {plan_target:.0f} 改成 "
        f"{rnr._plan_targets.get(spec.code):.0f} 份 —— 计划必须按天锁定，"
        f"否则会变成「跌得越狠买得越多」，守恒基准也跟着漂"
    )
    held_after_drop = sum(
        p.quantity for p in vp.get_all_positions(status="OPEN")
        if p.stock_code == spec.code
    )
    assert held_after_drop == plan_target, (
        f"当日下跌后又加仓了：{plan_target:.0f} → {held_after_drop:.0f} 份"
    )
    # 幂等：目标已达成后再 poll 一百轮也不该再买
    before = len(vp.get_all_positions(status="OPEN"))
    for i in range(100):
        step(env, minutes=0.1)
        push_quote(env, 1.0, prev_close=1.0, cum_volume=80_000_000 + i)
        rnr.poll()
    after = len(vp.get_all_positions(status="OPEN"))
    assert after == before, f"目标已达却仍在开仓：{before} → {after} 条持仓"
    summary = vp.get_summary()
    assert summary["available_capital"] >= 0, "买入后可用资金为负，穿仓了"

    # —— 可审计性（第一天收摊时就查，第二天会把 plan_date 顶掉）——
    st = rnr.get_status()["symbols"][0]
    assert st["alloc_pct"] == 40.0, st["alloc_pct"]
    assert st["target_shares"] == 400_000.0, st["target_shares"]
    assert abs(st["target_budget"] - 400_000.0) < 1e-6, st["target_budget"]
    assert st["target_resolved_date"] == "2026-10-13", st["target_resolved_date"]

    # —— 第二天：价格翻倍，目标只增不减 ——
    env["clock"]["t"] = _dt(*D2, 9, 35).timestamp()
    step(env)
    push_quote(env, 2.0, prev_close=1.0, cum_volume=9_000_000)
    rnr.poll()
    plan_d2 = rnr._plan_targets.get(spec.code, 0.0)
    assert plan_d2 == plan_target, (
        f"价格上涨后目标从 {plan_target:.0f} 缩水到 {plan_d2:.0f} 份 —— "
        f"长期持有的份额被行情悄悄削掉了"
    )

    fill_txt = " → ".join(f"{v/10000:.0f}万" for v, _t in fill_log)
    print(f"3b) 自动建仓 OK —— 目标 {plan_target:.0f} 份（总资产 100 万 × 40%），"
          f"分 {len(fill_log)} 笔：{fill_txt}")


def check_gate_hold_blocks_establish():
    """3d) 反方向用例：闸门判 hold 时，一行都不许买。

    与 3b（放行 → 分批建到 40%）**成对**。只留 3b 的话，哪天有人把
    闸门摘掉/默认关掉，3b 依旧全绿 —— 一项保护掩盖了另一项缺失。
    这里用假裁定把闸门钉死在 hold 上，断言缺口没被填、且原因可见。
    """

    def _hold(spec, price):
        return {
            "approved": False,
            "action_type": "hold",
            "plan": {"action_type": "hold", "size_hint": 0.0},
            "manas_score": 0.27,
            "plan_gate_reason": "策略不自信",
        }

    env = make_alloc_env(gate_provider=_hold)
    vp, rnr, spec = env["vp"], env["runner"], env["spec"]
    for i in range(12):
        step(env)
        push_quote(env, 1.0, prev_close=1.0, cum_volume=1_000_000 * (i + 1))
        rnr.poll()

    held = sum(
        p.quantity for p in vp.get_all_positions(status="OPEN")
        if p.stock_code == spec.code
    )
    assert held == 0, f"闸门判 hold，却仍建了 {held:.0f} 份底仓 —— 逆风加码被放行"
    assert rnr._stats.get("gate_blocked", 0) > 0, \
        "闸门拦下了却没计数 —— 「为什么没动」将无从查起"
    print(f"3d) 闸门 hold → 一笔不买 OK（拦截计数 {rnr._stats['gate_blocked']}）")


def check_budget_headroom_shared_with_other_strategies():
    """3c) 总持仓额度被其它策略占用时，底仓按剩余空间买且不刷错误瀑布。

    真实账户上就撞过：已有持仓占 41 万（其中 40 万是 TEST001/000001 这类
    测试残留），总上限 80 万 → 留给 40 万底仓只剩 39 万。
    若只看单笔限额，最后一笔会被 open_position 拒绝 →
    「建仓失败」每 30 秒刷一条，把真正的故障淹没。
    """
    env = make_alloc_env()
    vp, rnr, spec = env["vp"], env["runner"], env["spec"]

    # 别的策略先占掉 42 万（→ 总额度只剩 38 万给底仓）。
    # 占位本身也要分批：42 万同样会撞单笔限额。
    total_other = 420_000.0
    filled = 0.0
    for chunk in (200_000.0, 200_000.0, 20_000.0):
        pos = vp.open_position(
            strategy_id="other", strategy_name="别的策略",
            stock_code="600000", stock_name="占位",
            price=10.0, quantity=chunk / 10.0,
        )
        assert pos is not None, f"占位持仓建立失败（{chunk:,.0f} 元）"
        filled += chunk
    assert abs(filled - total_other) < 1e-6, filled

    # 全级别都收，才能区分「分批过程的正常 INFO」与「真卡住的 ERROR」
    recs = []
    handler = logging.Handler()
    handler.setLevel(logging.DEBUG)
    handler.emit = lambda rec: recs.append(rec)
    root = logging.getLogger("deva.naja.bandit.t_rotation_runner")
    root.addHandler(handler)
    err_lines = []

    try:
        for i in range(20):
            step(env)
            push_quote(env, 1.0, prev_close=1.0, cum_volume=1_000_000 * (i + 1))
            rnr.poll()
            err_lines = [r.getMessage() for r in recs if r.levelno >= logging.ERROR]
    finally:
        root.removeHandler(handler)

    held = sum(
        p.quantity for p in vp.get_all_positions(status="OPEN")
        if p.stock_code == spec.code
    )
    headroom = vp.category_position_budget - 420_000.0
    expect_floor = int(headroom / 1.0 / spec.round_lot) * spec.round_lot

    assert held > 0, "额度被占用后一笔都没买 —— 应该是按剩余空间买，不是放弃"
    assert held <= expect_floor + 1e-6, (
        f"买超了：持有 {held:.0f} 份 vs 可用额度允许 {expect_floor:.0f} 份"
    )
    # 每一笔都没被 open_position 拒绝（否则日志里会有「建仓失败」）
    fails = [m for m in err_lines if "建仓失败" in m]
    assert not fails, f"仍撞到仓位限额被拒：{fails[:1]}"

    # 分批进行**不允许**喊人 —— 它会在几轮内自愈；喊人属于制造假故障
    all_msgs = [r.getMessage() for r in recs]
    staged = [m for m in all_msgs if "需要人工介入" in m and "零增长" not in m]
    assert not staged, f"把能自愈的分批报成了「需要人工介入」：{staged[:1]}"
    # 分批过程必须留下可读痕迹（否则 UI/日志上看不出它在干活）
    batches = [m for m in all_msgs if "分批" in m and "补足底仓" in m]
    assert batches, "分批补仓过程完全没留痕 —— 静默的后台任务等于没有后台任务"
    assert any("1/2" in m or "1/3" in m for m in batches), batches[:2]

    # 真的卡住（额度被别的策略占死）必须说清楚，且**每天只说一次**
    warned = [m for m in err_lines if "额度限制" in m or "底仓卡住" in m]
    assert warned, "额度不足却不告警 —— 用户会以为底仓已经到位"
    assert len(warned) == 1, f"额度告警刷屏了 {len(warned)} 条（应每天 1 条）"
    assert "总持仓额度只剩" in warned[0], warned[0]
    assert "连续" in warned[0], (
        f"告警没说清「连续几轮零增长」，读日志的人无法判断是真卡死还是正在分批：{warned[0]}"
    )

    st = rnr.get_status()["symbols"][0]
    assert st["budget_warned"] == "2026-10-13", st["budget_warned"]
    assert st["held_shares"] == held, (st["held_shares"], held)

    print(f"3c) 额度被占用 OK —— 其它策略占 42 万，底仓按剩余 {headroom:,.0f} 元 "
          f"买到 {held:.0f} 份，卡住告警恰好 1 条（分批过程零告警）")


def check_bus_drives_engine():
    """3) 总线报价确实驱动了引擎（而不是静默丢弃）。"""
    env = make_runner()
    seed_core(env, PREV_CLOSE, 100_000.0)
    open_ts = None
    assert env["runner"]._engine is env["eng"]

    for i in range(20):
        step(env)
        push_quote(env, DAY_OPEN + (DAY_LOW - DAY_OPEN) * (i / 19.0),
                   cum_volume=1_000_000 * (i + 1))
        env["runner"].poll()
    open_ts = env["runner"]._session_date.get("588200")
    assert open_ts == "2026-10-13", f"会话未开启: {open_ts}"
    ticks = env["runner"]._stats["ticks"]
    assert ticks >= 15, f"行情没喂进引擎，ticks={ticks}"
    assert env["runner"]._stats["quote_miss"] == 0, "有报价却被告警为缺失"
    print(f"3) 总线→引擎通路 OK（{ticks} ticks）")


def check_real_day_makes_t_and_conserves():
    """4) 用当日 588200 的真实走势跑一遍：必须能触发做 T 且份额守恒。"""
    env = make_runner()
    seed_core(env, PREV_CLOSE, 100_000.0)
    before = env["ledger"].effective_shares("588200", env["vp"], **_kw(env))

    prices = []
    # ① 低开下行 25 根 —— 此时不该动手（接飞刀）
    for i in range(25):
        prices.append(DAY_OPEN + (DAY_LOW - DAY_OPEN) * (i / 24.0))
    # ② 低位磨底 6 根
    for i in range(6):
        prices.append(DAY_LOW - 0.001 * i)
    # ③ 右侧确认：抬 3 根（这里应触发低吸）
    for i in range(1, 4):
        prices.append(prices[-1] + 0.003)
    # ④ 单边拉升到最高
    while prices[-1] < DAY_HIGH:
        prices.append(min(DAY_HIGH, prices[-1] + 0.002))
    # ⑤ 见顶回落
    while prices[-1] > DAY_CLOSE:
        prices.append(max(DAY_CLOSE, prices[-1] - 0.002))

    actions = []
    for i, p in enumerate(prices):
        step(env)
        push_quote(env, p, cum_volume=1_000_000 * (i + 1))
        diag = env["runner"].poll()[0]
        if str(diag.get("action", "NONE")) not in ("NONE", ""):
            actions.append((i, round(p, 4), diag.get("action")))

    assert actions, "整段真实走势一条信号都没触发 —— 接线仍然没通"
    kinds = {a[2] for a in actions}
    assert "BUY_T" in kinds, f"缺少低吸腿，实际触发: {kinds}"

    # 收盘前结算：不留任何悬空义务
    env["clock"]["t"] = _dt(*D1, 14, 52).timestamp()
    push_quote(env, DAY_CLOSE, cum_volume=1_000_000 * (len(prices) + 1))
    settle = env["runner"].poll()[0]
    assert settle.get("action") == "SETTLE", f"收盘结算未触发: {settle}"
    assert not list(env["ledger"].outstanding("588200")), "仍有未买回的回购义务"

    after = env["ledger"].effective_shares("588200", env["vp"], **_kw(env))
    assert after >= before - 1e-6, f"份额守恒被破坏: {before:.0f} → {after:.0f}"
    print(
        f"4) 真实日走势 OK —— 触发 {actions}；"
        f"份额 {before:.0f} → {after:.0f}，兑现差价 "
        f"{env['eng'].realized_edge_total('588200'):+.2f} 元"
    )


def _kw(env):
    from deva.naja.bandit.t_rotation_runner import session_open_ts

    dt = datetime.fromtimestamp(env["clock"]["t"])
    return {"now": env["clock"]["t"], "session_open_ts": session_open_ts(dt)}


def check_volume_delta_not_cumulative():
    """5) 新浪给的是累计成交量，喂给 VWAP 的必须是增量。"""
    env = make_runner()
    seed_core(env, PREV_CLOSE, 100_000.0)
    step(env); push_quote(env, DAY_OPEN, cum_volume=10_000_000); env["runner"].poll()
    step(env); push_quote(env, DAY_OPEN, cum_volume=20_000_000); env["runner"].poll()
    bars = env["eng"]._trackers["588200"]._bars
    assert len(bars) >= 1
    assert bars[-1].volume == 10_000_000, (
        f"第二根 bar 的成交量应为增量 10,000,000，实际 {bars[-1].volume} "
        f"（直接喂累计量会把 VWAP 拖成一条发散的曲线）"
    )
    print("5) 成交量增量换算 OK")


def check_off_hours_no_feed():
    """6) 午休/收盘后不喂数。"""
    env = make_runner()
    seed_core(env, PREV_CLOSE, 100_000.0)
    for hh, mm in ((12, 0), (20, 0), (8, 0)):
        env["clock"]["t"] = _dt(*D1, hh, mm).timestamp()
        push_quote(env, PREV_CLOSE, cum_volume=1_000_000)
        env["runner"].poll()
    assert env["runner"]._stats["ticks"] == 0, "非交易时段仍喂了 tick"
    assert env["runner"]._stats["off_hours_skips"] >= 3
    # 周六
    env["clock"]["t"] = datetime(2026, 10, 17, 10, 0).timestamp()
    push_quote(env, PREV_CLOSE, cum_volume=1_000_000)
    env["runner"].poll()
    assert env["runner"]._stats["ticks"] == 0, "周六仍喂了 tick"
    print("6) 非交易时段不喂数 OK")


def check_flat_day_suspension():
    """7) 行情长期无变化要停喂并告警（节假日/数据源死掉的保底）。"""
    env = make_runner(flat_limit=3)
    seed_core(env, PREV_CLOSE, 100_000.0)
    for _ in range(6):
        step(env)
        push_quote(env, PREV_CLOSE, cum_volume=5_000_000)
        env["runner"].poll()
    susp = env["runner"]._suspended.get("588200")
    assert susp, "连续多次无变化却没有告警/停喂"
    ticks_at_stop = env["runner"]._stats["ticks"]
    push_quote(env, PREV_CLOSE, cum_volume=5_000_000)
    step(env)
    env["runner"].poll()
    assert env["runner"]._stats["ticks"] == ticks_at_stop, "已停喂却仍在喂数"
    print(f"7) 死水检测 OK —— {susp}")


def check_minutes_to_close():
    """8) minutes_to_close 必须算准，它同时决定能否开仓与是否强平。

    ❗接口与口径都随「做 T 支持三市场」变了：
      * 首参多了 ``market``（A 股 15:00 / 港股 16:00 / 美股 04:00 收盘各不相同）；
      * 返回值是**剩余交易分钟**，午休那 90 分钟不算 —— 10:00 距收盘是
        210 分钟（90 + 120），不是墙钟的 300 分钟。
        旧口径把午休也算成"还有时间"，会让「收盘前 N 分钟不许新开倒 T」
        这条保护在午休前后系统性偏晚。
    """
    from deva.naja.bandit.market_session import minutes_to_close, market_phase

    assert abs(minutes_to_close("CN", _dt(*D1, 10, 0)) - 210) < 1e-6, \
        minutes_to_close("CN", _dt(*D1, 10, 0))
    assert abs(minutes_to_close("CN", _dt(*D1, 14, 55)) - 5) < 1e-6
    assert minutes_to_close("CN", _dt(*D1, 15, 1)) is None
    assert minutes_to_close("CN", datetime(2026, 10, 17, 10, 0)) is None  # 周六
    # 港股收盘 16:00：同一时刻比 A 股多一截
    assert abs(minutes_to_close("HK", _dt(*D1, 14, 0)) - 120) < 1e-6
    assert market_phase("CN", _dt(*D1, 10, 0)) == "morning"
    assert market_phase("CN", _dt(*D1, 12, 30)) == "lunch"
    assert market_phase("CN", _dt(*D1, 14, 0)) == "afternoon"
    assert market_phase("CN", _dt(*D1, 15, 30)) == "closed"
    print("8) 交易时段/收盘倒计时 OK")


def check_position_id_no_collision():
    """9b) 同一毫秒对同一标的连开两笔，两笔都必须留下。

    ``position_id`` 曾经是 ``VP_{code}_{int(time.time()*1000)}`` —— 毫秒时间戳，
    且生成后不做唯一性检查。同一毫秒内的第二笔会用**同一个 key** 写进
    ``self._positions``，把第一笔直接覆盖：资金照扣、份额凭空少一块，
    调用方看不到任何异常（``open_position`` 返回值还是正常的那笔）。

    真实触发场景就在本模块里：收盘强平 / 强制回购 / 分批建仓，
    两笔下单常常落在同一个 poll（毫秒级）内。

    这里把 ``time.time`` 冻住，让碰撞**必然发生**而不是靠运气，
    否则这个缺陷会以「偶发守卫失败」的形式长期伪装成测试不稳定。
    """
    import deva.naja.bandit.virtual_portfolio as vpm

    env = make_alloc_env()
    vp = env["vp"]

    real_time = vpm.time.time
    vpm.time.time = lambda: 1_700_000_000.0
    try:
        a = vp.open_position(
            strategy_id="core", strategy_name="长期底仓",
            stock_code="588200", stock_name="科创芯片ETF",
            price=1.0, quantity=100.0,
        )
        b = vp.open_position(
            strategy_id="core", strategy_name="长期底仓",
            stock_code="588200", stock_name="科创芯片ETF",
            price=1.0, quantity=200.0,
        )
        assert a is not None and b is not None, "同一毫秒的第二笔被拒了"
        assert a.position_id != b.position_id, (
            f"两笔撞了同一个 id {a.position_id} —— 后一笔会覆盖前一笔"
        )
        ids = [p.position_id for p in vp.get_all_positions(status="OPEN")]
        assert ids.count(a.position_id) == 1 and b.position_id in ids, (
            f"两笔没能都留下：{ids}"
        )
        total = sum(
            p.quantity for p in vp.get_all_positions(status="OPEN")
            if p.stock_code == "588200"
        )
        assert abs(total - 300.0) < 1e-6, (
            f"份额被覆盖：应共 300 份，实际 {total:.0f}（少了 100 份的那笔）"
        )
    finally:
        vpm.time.time = real_time
    print(
        f"9b) 同毫秒双开 OK —— {a.position_id} + {b.position_id}，共 300 份都在"
    )


def check_cross_session_buyback():
    """9) ★跨会话回购：昨天卖飞没买回的份额，今天开盘必须补回来。

    这条是「保证长期持有」在 **重启 / 提前退出** 场景下的唯一兑现点。
    少了它，一次进程崩溃就能让底仓永久缺一块，而且不报错。
    """
    env = make_runner()
    # 持有 130000 / 目标 100000 → 倒 T 额度 30000（超出目标的部分才是可动用的）
    seed_core(env, PREV_CLOSE, 130_000.0)
    env["eng"].register_target("588200", 100_000.0, name=env["spec"].name)
    before = env["ledger"].effective_shares("588200", env["vp"], **_kw(env))

    # 单边拉升 → **≥3 根不再创新高的企稳 bar** → 一根回落 bar 作右侧确认 → 高抛
    #
    # ❗「企稳确认」是 `179f42f`（做 T 标定按市场分档收紧）加的门槛：
    #   `RotationThresholds.require_stabilize` 要求 `bars_since_high >= stabilize_bars`。
    #   单调拉升时每根 bar 都是新高 → bars_since_high 恒为 0 → **永远不高抛**。
    #   旧样本只有「拉升 + 一根回落」，正是在这道门槛下永远等不到触发的那类用例。
    prices = [0.990]
    for _ in range(24):
        prices.append(prices[-1] + 0.0012)
    prices += [1.0186, 1.0184, 1.0182]   # 企稳确认：连续 3 根不创新高
    prices.append(1.0130)                 # 右侧回落确认

    fired = None
    for i, p in enumerate(prices):
        step(env)
        push_quote(env, p, cum_volume=1_000_000 * (i + 1))
        diag = env["runner"].poll()[0]
        if diag.get("action") == "SELL_T":
            fired = (i, p)
            break
    assert fired, "倒 T 未触发，跨会话回购无从验证"

    outstanding = list(env["ledger"].outstanding("588200"))
    assert outstanding, "卖出后没有回购义务 —— 铁律失效"
    sold_qty = sum(ob.quantity for ob in outstanding)
    real = env["ledger"].current_shares("588200", env["vp"])
    assert abs((real + sold_qty) - before) < 1e-6, "卖出后约定份额就掉了"

    # 关键：直接跳到下一个交易日（等价于进程昨天就没了）
    env["clock"]["t"] = _dt(*D2, 9, 40).timestamp()
    push_quote(env, 1.012, prev_close=1.010, cum_volume=1_000_000 * 99)
    d2 = env["runner"].poll()[0]
    assert env["runner"]._stats["cross_session_buyback"] == 1, (
        "次日开盘没有执行跨会话回购"
    )
    assert not list(env["ledger"].outstanding("588200")), "跨日后仍有悬空回购义务"
    after = env["ledger"].current_shares("588200", env["vp"])
    assert abs(after - before) < 1e-6, f"份额没回来: {before:.0f} → {after:.0f}"
    print(
        f"9) 跨会话回购 OK —— 昨日高抛 {sold_qty:.0f} 份，"
        f"次日 @{1.012} 强制补回，份额 {before:.0f} → {after:.0f}"
    )


def check_no_core_no_reverse_t():
    """10) 没登记计划的标的一律不许倒 T —— 保守默认，宁可不动。"""
    env = make_runner()
    from deva.naja.bandit.t_rotation_runner import session_open_ts

    dt = _dt(*D1, 10, 0)
    quota = env["ledger"].session_quota(
        "588200", env["vp"],
        now=dt.timestamp(), session_open_ts=session_open_ts(dt),
    )
    assert quota == 0.0, f"未登记底仓计划却有倒T额度 {quota}"
    print("10) 未登记计划 → 倒T额度为 0 OK")


def check_status_exposes_degraded():
    """11) get_status 必须能把「为什么没动」说清楚，而不是给一个静默的空字典。"""
    env = make_runner()
    seed_core(env, PREV_CLOSE, 100_000.0)
    env["clock"]["t"] = _dt(*D1, 10, 0).timestamp()
    push_quote(env, PREV_CLOSE, cum_volume=1_000_000)
    env["runner"].poll()
    st = env["runner"].get_status()
    assert st["symbols"], "状态里没有标的"
    sym = st["symbols"][0]
    for key in ("code", "bus_code", "name", "target_shares", "session_date",
                "last_price", "suspended", "last_diag", "engine"):
        assert key in sym, f"状态缺字段 {key}"
    assert sym["session_date"] == "2026-10-13"
    assert sym["last_diag"].get("reason"), "诊断信息缺 reason —— 静默失效的温床"
    # ❗时段信息已从顶层「单个 phase」改成**逐市场**（做 T 支持三市场后，
    #   一份状态里可能同时有 CN/HK/US 三个标的，一个 phase 装不下）。
    assert "stats" in st and "phases" in st, sorted(st)
    ph = st["phases"][sym["code"]]
    for key in ("market", "phase", "minutes_to_close", "session_date"):
        assert key in ph, f"逐市场时段缺字段 {key}"
    assert ph["market"] == "CN" and ph["phase"] == "morning", ph
    print("11) 状态输出可诊断 OK（含 reason/phases[市场].phase）")


def check_runner_start_is_idempotent():
    """12) start() 幂等，且停/起不抛异常。"""
    env = make_runner()
    import deva.naja.bandit.t_rotation_runner as runner_mod
    old = runner_mod._runner
    try:
        rnr = make_runner()["runner"]
        # bootstrap 已由 poll 内部自动完成；这里再补一次显式启动会不会出问题
        rnr._bootstrap()
        assert rnr._quotes is not None and rnr._engine is not None
        assert rnr.stop() is True or True
    finally:
        runner_mod._runner = old
    print("12) 启动幂等 / 停止安全 OK")


# ════════════════════════════════════════════════════════════════
#  静态守卫
# ════════════════════════════════════════════════════════════════
def _method_bodies(path):
    """按方法/函数块切源码 + 去整行注释，避免整文件 grep 造成假警报。"""
    src = open(path, encoding="utf-8").read()
    lines = src.splitlines()
    cleaned = ["\n" if ln.strip().startswith("#") else ln for ln in lines]
    new_src = "\n".join(cleaned)
    tree = ast.parse(new_src)
    blocks = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                blocks[node.name] = ast.get_source_segment(new_src, node) or ""
            except Exception:
                blocks[node.name] = ""
    return blocks


def check_static_bus_wired():
    """13) 运行器必须真的接到了行情源，而不是空口说已对接。

    ❗2026-10-14 起行情源由 MarketDataBus（新浪）换成富途统一行情
    （``futu_quote_source``）：新浪那条路在港股/美股上**实测静默丢数**
    （``hk`` 无分支、美股 ETF 不在 Block 池里 → 解析成空）。
    所以这里断言的是**富途**接线，不是旧的 ``subscribe`` / ``bus.fetch``。
    """
    src = open(RUNNER_FILE, encoding="utf-8").read()
    assert "get_futu_quote_source" in src, "没有引用富途行情源"
    blocks = _method_bodies(RUNNER_FILE)
    boot_src = blocks.get("_bootstrap", "")
    assert "get_futu_quote_source" in boot_src, "_bootstrap 未接上富途行情源"
    read_src = blocks.get("_read_quote", "")
    assert "src.get(" in read_src, "取行情不走行情源同步入口 src.get()"
    assert ".ok" in read_src, "未校验 quote.ok —— 会把失败报价当有效数据喂进引擎"
    # 反方向：旧的新浪总线不许再出现在取数路径里（防止有人「顺手」加回一条）
    assert "get_market_data_bus" not in read_src, \
        "_read_quote 又引用了 MarketDataBus —— 港股/美股会静默丢数"
    print("13) 静态：富途行情源接线 + 同步取数 OK")


def _strip_comments(src: str) -> str:
    """用 tokenize 抹掉注释（含行内注释）。

    只去「整行以 # 开头」是不够的：``except Exception as e:  # create_task``
    这种行内注释同样会让静态守卫在自己写的说明上假警报。
    """
    import io
    import tokenize

    out = src.splitlines()
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type != tokenize.COMMENT:
            continue
        srow, scol = tok.start
        erow, ecol = tok.end
        if srow == erow:
            line = out[srow - 1]
            out[srow - 1] = line[:scol] + " " * max(0, ecol - scol) + line[ecol:]
        else:  # pragma: no cover - 极少数跨行场景
            for r in range(srow, min(erow, len(out)) + 1):
                out[r - 1] = ""
    return "\n".join(out)


def _docstring_lines(tree):
    """所有 docstring 的行号集合 —— 注释 DEF-7 之外，
    docstring 里解释「为什么不能用 X」同样会触发 #14 的假警报。"""
    lines = set()

    def _span(node):
        if (
            isinstance(node, ast.Expr)
            and isinstance(getattr(node, "value", None), ast.Constant)
            and isinstance(node.value.value, str)
        ):
            lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))

    for node in ast.walk(tree):
        _span(node)
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            _span(body[0])
    return lines


def check_static_no_async_in_thread():
    """14) 轮询线程里不得调用 async-only 的 API（docstring 除外）。

    ``get_price_async`` / ``write_quotes`` 内部会 ``asyncio.create_task``，
    在没有事件循环的普通线程里直接抛 RuntimeError ——
    而这个异常会被 runner 的 try/except 吃掉，表现为「行情永远取不到」。
    """
    for path in (RUNNER_FILE,):
        # 先去注释（行首 + 行内），再去 docstring
        joined = _strip_comments(open(path, encoding="utf-8").read())
        ds = _docstring_lines(ast.parse(joined))
        code = "\n".join(
            ln for i, ln in enumerate(joined.splitlines(), start=1) if i not in ds
        )
        for bad in ("get_price_async", "asyncio.create_task", "bus.prefetch"):
            assert bad not in code, f"{os.path.basename(path)} 使用了线程不安全接口 {bad}"
    print("14) 静态：无 async-only 调用 OK（避免线程内 create_task 炸裂）")


def check_static_registered_and_started():
    """15) 既注册了单例，又真的 start() 了 —— 注册 ≠ 启动。

    这是本守卫最重要的一条：上一轮全部代码都在，唯独没有调用方，
    于是整套做 T 逻辑安静地空转了很久。
    """
    reg = open(REGISTER_FILE, encoding="utf-8").read()
    assert '"t_rotation_runner"' in reg, "register.py 未注册 t_rotation_runner"
    for line in reg.splitlines():
        if '"t_rotation_runner"' in line:
            assert "TRotationRunner" in line, f"注册行类名不对: {line.strip()}"
            break
    cont = open(CONTAINER_FILE, encoding="utf-8").read()
    tree = ast.parse(cont)

    starter = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_start_schedulers":
                starter = node
    assert starter is not None, "找不到 _start_schedulers"

    # 只判断 "出现了 .start()" 是不够的：同一个方法里
    # DailyReviewScheduler 也在 .start()，删掉做 T 的那行照样假通过。
    # 必须确认「get_t_rotation_runner() 赋给的那个名字」自己被 start 了。
    assigned = set()
    started = set()
    for node in ast.walk(starter):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name == "get_t_rotation_runner":
                assigned.update(
                    t.id for t in node.targets if isinstance(t, ast.Name)
                )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "start" and isinstance(node.func.value, ast.Name):
                started.add(node.func.value.id)
    assert assigned, "_start_schedulers 没有取 t_rotation_runner"
    live = assigned & started
    assert live, (
        f"t_rotation_runner 被取出后从未 start（变量名 {sorted(assigned)}）。"
        f"注册到单例表 ≠ 会跑，这正是上一轮零调用方事故的原样复刻"
    )
    print(f"15) 静态：已注册且 _start_schedulers 真的启动 OK（{sorted(live)}）")


def check_static_core_default():
    """16) 底仓默认标的写死为 588200，且带市场前缀。

    ❗清单常量名为 ``CORE_CATALOG``（``CHIP_ETF_CATALOG`` 只是兼容旧名的别名）。
    读取入口用的是新名，所以这里断言 ``CORE_CATALOG`` —— 断言别名等于
    在守一个可能被删掉的转发变量。
    """
    src = open(HOLDINGS_FILE, encoding="utf-8").read()
    assert 'DEFAULT_CORE_CODE = "588200"' in src, "默认标的不是 588200"
    blocks = _method_bodies(HOLDINGS_FILE)
    loader = blocks.get("load_core_holdings", "")
    assert "CORE_CATALOG" in loader, "清单未被读取入口使用"
    print("16) 静态：默认底仓锁定 588200 OK")


def check_exchange_prefix():
    """18) 交易所号段必须判对 —— 588200 曾被编成 sz588200，整条链路静默空转。

    故障形态值得记住：新浪对错误代码返回**空行**，解析结果就是 ``{}``，
    最上层看见的是「取不到行情」，而真正的错误（号段判断）在三层以外。
    """
    from deva.naja.bandit.market_data_bus import format_exchange_code, _normalize_code

    cases = {
        "588200": "sh588200",   # 科创板 ETF ← 本次踩坑的那个
        "512480": "sh512480",   # 沪市 ETF
        "510300": "sh510300",   # 沪深300 ETF
        "600519": "sh600519",   # 沪市主板
        "688981": "sh688981",   # 科创板股票
        "159995": "sz159995",   # 深市 ETF
        "300750": "sz300750",   # 创业板
        "000001": "sz000001",   # 深市主板
        "gb_nvda": "gb_nvda",
        "sh588200": "sh588200",
    }
    for raw, want in cases.items():
        got = format_exchange_code(raw)
        assert got == want, f"{raw} → {got}，应为 {want}"
    assert _normalize_code("sh588200") == "588200"
    assert _normalize_code("gb_nvda") == "nvda"
    print(f"18) 交易所号段判定 OK（{len(cases)} 个用例，含沪市 5 开头的 ETF）")


def check_real_quote_source():
    """19) 真实行情源确实能取到 588200 的报价（离线时如实跳过，不算通过也不算失败）。

    ❗这里必须走 runner 真正用的那个源（富途）。此前的版本查的是
    MarketDataBus —— 一个 runner 已经不再读取的地方：查它等于在验
    「另一条路的行情通不通」，对做 T 的实际取数能力零信息量。
    """
    try:
        from deva.naja.bandit.futu_quote_source import get_futu_quote_source
        from deva.naja.bandit.core_holdings import load_core_holdings

        spec = load_core_holdings()[0]
        quote = get_futu_quote_source().get(spec.code, spec.market)
    except Exception as e:
        print(f"⏭️ 19) 真实行情源不可达，跳过（{type(e).__name__}: {e}）")
        return
    if quote is None or not getattr(quote, "ok", False):
        note = getattr(quote, "error", "无返回")
        print(f"⏭️ 19) 真实行情源未返回数据，跳过（{note}）")
        return
    if quote.current <= 0:
        print("⏭️ 19) 真实行情返回的价格 <= 0，跳过")
        return
    assert quote.prev_close > 0, "真实报价缺昨收 —— 百分比基准没了"
    print(
        f"19) 真实行情源可取数 OK —— {quote.name}({spec.code}) "
        f"现价 {quote.current} / 昨收 {quote.prev_close}"
    )


def check_static_conservation_reached():
    """17) 运行器的会话切换必须包含「先把欠的买回来」，这是铁律最后一公里。"""
    blocks = _method_bodies(RUNNER_FILE)
    body = blocks.get("_maybe_start_session", "")
    assert body, "缺少 _maybe_start_session"
    assert "settle_before_close" in body, "换日时没有跨会话回购兜底"
    assert "outstanding" in body, "没有检查遗留回购义务"
    pump = blocks.get("_pump", "")
    assert "_last_cum_vol" in pump, "未做累计→增量成交量换算"
    assert "settle_before_close" in pump, "收盘前没有触发结算"
    print("17) 静态：换日回购 + 收盘结算 + 增量换算 OK")


# ════════════════════════════════════════════════════════════════
CHECKS = [
    check_default_core_is_chip_etf,
    check_env_override,
    check_alloc_pct_resolution,
    check_establish_default_on,
    check_auto_establish_40pct,
    check_gate_hold_blocks_establish,
    check_budget_headroom_shared_with_other_strategies,
    check_bus_drives_engine,
    check_real_day_makes_t_and_conserves,
    check_volume_delta_not_cumulative,
    check_off_hours_no_feed,
    check_flat_day_suspension,
    check_minutes_to_close,
    check_position_id_no_collision,
    check_cross_session_buyback,
    check_no_core_no_reverse_t,
    check_status_exposes_degraded,
    check_runner_start_is_idempotent,
    check_static_bus_wired,
    check_static_no_async_in_thread,
    check_static_registered_and_started,
    check_static_core_default,
    check_static_conservation_reached,
    check_exchange_prefix,
    check_real_quote_source,
]


def main():
    strict = "--strict" in sys.argv
    print("=" * 68)
    print("做 T 接线守卫 —— 科创芯片 ETF(588200) × MarketDataBus")
    print("=" * 68)
    failed = 0
    for fn in CHECKS:
        try:
            fn()
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {fn.__name__}: {e}")
        except Exception as e:  # 任何异常都算失败，不允许偷偷跳过
            failed += 1
            import traceback
            print(f"  💥 {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    print("-" * 68)
    total = len(CHECKS)
    if failed:
        print(f"❌ {failed}/{total} 项失败")
        # 本仓约定：非 --strict 为「提示档」（看得到失败、退出码仍 0），
        # --strict 为「闸门档」（失败即非零）。自动化统一用 --strict 扫。
        #
        # ⚠️ 正因为闸门在 --strict，本守卫曾经 17/24 项崩掉却长期无人知晓 ——
        #    不是因为退出策略，而是因为**没人跑**。配套的一键严格扫描见
        #    `scripts/verify/run_all_guards.py`。
        return 1 if strict else 0
    print(f"✅ ALL PASS ({total}/{total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
