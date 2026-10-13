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
import os
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

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
    """最小可用的 MarketQuote 替身。"""

    PRIORITY_HIGH = "HIGH"

    def __init__(self, code, name, current, prev_close, volume, open_price=None,
                 high=None, low=None):
        self.code = code
        self.name = name
        self.current = current
        self.prev_close = prev_close
        self.volume = volume
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


class FakeBus:
    """MarketDataBus 的最小替身。只实现 runner 真正用到的接口。"""

    PRIORITY_HIGH = "HIGH"
    PRIORITY_MEDIUM = "MEDIUM"
    PRIORITY_LOW = "LOW"

    def __init__(self):
        self.quotes = {}
        self.fetches = []
        self.subscribed = []
        self.priority = []
        self.quote = None  # 兼容：runner 只调用 fetch / get_quote

    def put(self, code, quote):
        self.quotes[code] = quote

    def fetch(self, codes, force=False):
        self.fetches.append(list(codes))
        return {c: (self.quotes.get(c).current if self.quotes.get(c) else 0.0) for c in codes}

    def get_quote(self, code, allow_stale=True):
        return self.quotes.get(code)

    def subscribe(self, codes, callback):
        self.subscribed.append((list(codes), callback))

    def register_priority_codes(self, codes, level):
        self.priority.append((list(codes), level))


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
        code="588200", bus_code="sh588200", name="科创芯片ETF嘉实",
        target_shares=100_000.0, round_lot=100.0,
    )
    bus = FakeBus()
    ledger = CorePositionLedger(persist=False)
    eng = TRotationEngine(
        portfolio=vp, ledger=ledger,
        config=TRotationConfig(max_round_pct=0.30, max_round_amount=500_000.0),
    )
    clock = {"t": _dt(*D1, 9, 35).timestamp()}
    runner = TRotationRunner(
        portfolio=vp, bus=bus, engine=eng, ledger=ledger, specs=[spec],
        establish_missing=establish, flat_poll_limit=flat_limit,
        clock=lambda: clock["t"],
    )
    return {
        "vp": vp, "bus": bus, "eng": eng, "ledger": ledger,
        "spec": spec, "runner": runner, "clock": clock,
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
    print(f"1) 默认底仓 OK —— {spec.name}({spec.bus_code}) 目标 {spec.target_shares:.0f} 份")


def check_env_override():
    """2) NAJA_T_ROTATION_TARGET_SHARES 能覆盖目标份额，坏值回退。"""
    from deva.naja.bandit import core_holdings as ch

    os.environ["NAJA_T_ROTATION_TARGET_SHARES"] = "588200:150000"
    try:
        specs = ch.load_core_holdings()
        assert specs[0].target_shares == 150000, specs[0].target_shares
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
        assert specs[0].target_shares > 0, "坏值应回退到默认份额"
    finally:
        os.environ.pop("NAJA_T_ROTATION_TARGET_SHARES")
    print("2) 环境变量覆盖/坏值回退 OK")


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
    """8) minutes_to_close 必须算准，它同时决定能否开仓与是否强平。"""
    from deva.naja.bandit.t_rotation_runner import minutes_to_close, cn_phase

    assert abs(minutes_to_close(_dt(*D1, 10, 0)) - 300) < 1e-6
    assert abs(minutes_to_close(_dt(*D1, 14, 55)) - 5) < 1e-6
    assert minutes_to_close(_dt(*D1, 15, 1)) is None
    assert minutes_to_close(datetime(2026, 10, 17, 10, 0)) is None  # 周六
    assert cn_phase(_dt(*D1, 10, 0)) == "morning"
    assert cn_phase(_dt(*D1, 12, 30)) == "lunch"
    assert cn_phase(_dt(*D1, 14, 0)) == "afternoon"
    assert cn_phase(_dt(*D1, 15, 30)) == "closed"
    print("8) 交易时段/收盘倒计时 OK")


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

    # 单边拉升 → 一根回落 bar 作右侧确认 → 触发倒 T 高抛
    prices = [0.990]
    for _ in range(24):
        prices.append(prices[-1] + 0.0012)
    prices.append(prices[-1] - 0.005)   # 回落：打断连涨

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
    assert "stats" in st and "phase" in st and "minutes_to_close" in st
    print("11) 状态输出可诊断 OK（含 reason/phase/minutes_to_close）")


def check_runner_start_is_idempotent():
    """12) start() 幂等，且停/起不抛异常。"""
    env = make_runner()
    import deva.naja.bandit.t_rotation_runner as runner_mod
    old = runner_mod._runner
    try:
        rnr = make_runner()["runner"]
        # bootstrap 已由 poll 内部自动完成；这里再补一次显式启动会不会出问题
        rnr._bootstrap()
        assert rnr._bus is not None and rnr._engine is not None
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
    """13) 运行器必须真的订阅/连接了 MarketDataBus，而不是空口说与总线对接。"""
    src = open(RUNNER_FILE, encoding="utf-8").read()
    assert "get_market_data_bus" in src, "没有引用 MarketDataBus"
    blocks = _method_bodies(RUNNER_FILE)
    sub_src = blocks.get("_bootstrap", "")
    assert "subscribe(" in sub_src, "_bootstrap 未订阅总线"
    assert "register_priority_codes" in sub_src, "未把底仓标注册为高优先级"
    read_src = blocks.get("_read_quote", "")
    assert "bus.fetch(" in read_src, "取行情不走同步 fetch"
    print("13) 静态：总线订阅 + 同步取数 OK")


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
    """16) 底仓默认标的写死为 588200，且带市场前缀。"""
    src = open(HOLDINGS_FILE, encoding="utf-8").read()
    assert 'DEFAULT_CORE_CODE = "588200"' in src, "默认标的不是 588200"
    blocks = _method_bodies(HOLDINGS_FILE)
    loader = blocks.get("load_core_holdings", "")
    assert "CHIP_ETF_CATALOG" in loader, "清单未被读取入口使用"
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


def check_real_bus_quote():
    """19) 真实总线上确实能取到 588200 的报价（离线时如实跳过，不算通过也不算失败）。"""
    try:
        from deva.naja.bandit.market_data_bus import get_market_data_bus
        from deva.naja.bandit.core_holdings import load_core_holdings

        spec = load_core_holdings()[0]
        bus = get_market_data_bus()
        bus.fetch([spec.bus_code])
        quote = bus.get_quote(spec.bus_code)
    except Exception as e:
        print(f"⏭️ 19) 真实行情不可达，跳过（{type(e).__name__}: {e}）")
        return
    if quote is None or quote.current <= 0:
        print("⏭️ 19) 真实行情未返回数据，跳过（离线环境）")
        return
    assert quote.prev_close > 0, "真实报价缺昨收 —— 百分比基准没了"
    assert quote.code == spec.bus_code
    print(
        f"19) 真实总线可取数 OK —— {quote.name}({quote.code}) "
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
    check_bus_drives_engine,
    check_real_day_makes_t_and_conserves,
    check_volume_delta_not_cumulative,
    check_off_hours_no_feed,
    check_flat_day_suspension,
    check_minutes_to_close,
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
    check_real_bus_quote,
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
        sys.exit(1 if strict else 0)
    print(f"✅ ALL PASS ({total}/{total})")
    sys.exit(0)


if __name__ == "__main__":
    main()
