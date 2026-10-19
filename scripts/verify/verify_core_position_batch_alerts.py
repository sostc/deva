"""验证「底仓分批补不齐」的告警时机：分批过程不许喊人，真卡住才喊。

背景（2026-10-14 真事）
----------------------
40% 的底仓必然超过虚拟仓 20% 的单笔上限，**分批是设计意图，不是故障**。
但旧实现只要发现「本轮买不满目标」就发一条 ERROR 并写「需要人工介入」：

    🚨 科创芯片ETF嘉实(588200) 底仓受额度限制，本轮只能补 192500 份、
    仍缺 212700 份 —— 单笔/总额度限制。需要人工介入：……

而真实结局是：**60 秒后系统自己分三批补满 405200/405200**。
中间态被当成终态报，后果有两个：

1. 把能自愈的分批伪装成「必须人工处理的故障」—— 人真的跑去「清理持仓」了；
2. 因为按天去重，这条假故障整天挂在日志里，看上去像一直没解决，
   真正的故障（比如当时的 get_market_time AttributeError）反而被淹没。

新的判据是**有没有进展**：份额在涨 = 分批正常（静默）；
连续 N 轮份额零增长 = 真的卡住，那时才升 ERROR，按天去重。

本守卫锁三件事：

运行期
    A. 分批补仓全程零 ERROR —— 分批不属于告警
    B. 分批过程必须留可读痕迹（第几批/共几批），静默的后台任务等于没有后台任务
    C. 目标真的被补满，且每一笔都不超单笔限额（不许用 bypass_limits 绕过风控）
    D. 额度被别的策略占死时：先按剩余空间买，**连续零增长 N 轮后**才告警一次
    E. 告警必须说清「连续几轮零增长」，让人能区分「正在分批」与「卡死」

跑法：
    env -u PYTHONPATH TMPDIR=$(mktemp -d) python3 \\
        scripts/verify/verify_core_position_batch_alerts.py
"""

import logging
import os
import sys
import time
from datetime import datetime
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

# ★ 必须早于任何 deva 导入：本守卫会真的建/删虚拟持仓。
VERIFY_DIR = os.path.join(ROOT, "scripts", "verify")
if VERIFY_DIR not in sys.path:
    sys.path.insert(0, VERIFY_DIR)
from guard_sandbox import isolate_guard_db  # noqa: E402

isolate_guard_db()

TEST_ACCOUNT = "T_BATCH_ALERT_GUARD"
PREV_CLOSE = 1.0
D1 = (2026, 10, 13)


# ------------------------------------------------------------------
# 替身们
# ------------------------------------------------------------------
class TickingMTS:
    """跟着模拟时钟走的时间源。

    固定时间戳会让同一分钟内的多笔分批拿到同一个 entry_time，
    两笔金额相同的记录会被合并 —— 分批到底做了几笔就看不出来了。
    """

    def __init__(self, clock):
        self._clock = clock

    def get_market_time(self):
        return self._clock["t"]


class Quote:
    """最小可用的行情替身（`_read_quote` 只认 ok/current/prev_close/volume）。"""

    def __init__(self, code, name, current, prev_close, volume):
        self.code = code
        self.name = name
        self.current = current
        self.prev_close = prev_close
        self.volume = volume
        self.ok = True

    @property
    def age(self):
        return 0.0


class MissingQuote:
    """替身版的「这个标的没取到」—— 对应 FutuQuote(ok=False, error=...)。

    `ok=False` 必须显式给：runner 判的是 `quote.ok`，返回 None 会被当成
    "批量取行情失败"，把替身的锅甩到被测代码头上。
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


class QuoteSource:
    """runner 的 `quotes` 依赖：批量 `fetch(requests)` + 单点回退 `get(code, market)`。

    ❗`fetch` 必须是必填的最小契约：`c34f551` 起 `_prefetch_quotes` 一轮只
    `fetch` 一次再分给各标的，替身只有 `get` 的话整轮会走 except → 日志里刷
    "批量取行情失败" → 本该被验证的分批逻辑一条没跑（2026-10-19：3/3 全假红）。

    返回契约对齐 `FutuQuoteSource.fetch`：**原始代码 → quote**，取不到的条目
    也要在 dict 里。
    """

    def __init__(self):
        self.store = {}
        self.fetches = []

    def put(self, key, quote):
        self.store[key] = quote

    def get(self, code, market=None):
        return self.store.get(code)

    def fetch(self, requests):
        self.fetches.append(list(requests))
        out = {}
        for code, market in requests:
            key = str(code)
            quote = self.get(key, market)
            out[key] = quote if quote is not None else MissingQuote(key)
        return out


class LogTrap:
    """按级别收集 t_rotation_runner 的日志，用来区分 INFO 与 ERROR。"""

    def __init__(self):
        self.records = []
        self._handler = logging.Handler()
        self._handler.setLevel(logging.DEBUG)
        self._handler.emit = lambda rec: self.records.append(rec)
        self._logger = logging.getLogger("deva.naja.bandit.t_rotation_runner")

    def __enter__(self):
        self._logger.addHandler(self._handler)
        return self

    def __exit__(self, *exc):
        self._logger.removeHandler(self._handler)
        return False

    def errors(self):
        return [r.getMessage() for r in self.records if r.levelno >= logging.ERROR]

    def all_msgs(self):
        return [r.getMessage() for r in self.records]


class _OpenGate:
    """固定放行的大环境闸门，见下方 TRotationRunner 构造处的说明。"""

    def evaluate(self, spec, price, minutes_to_close):
        return SimpleNamespace(
            allowed=True, source="decision_center", action_type="act_fully",
            size_hint=1.0, reason="守卫注入放行", degraded=False,
        )


class _OpenWatch:
    """固定「值得问」的守望，见下方 TRotationRunner 构造处的说明。

    与 :class:`_OpenGate` 是同一层意思：本守卫测的是分批告警，
    不该被「什么时候才值得问」这条链路挡住。守望本身的语义由
    ``verify_core_establish_watch.py`` 覆盖。
    """

    enabled = True

    def ensure(self, spec, *, now, max_wait_seconds=None):
        return None

    def context_for(self, spec, *, now, price, anchor, minutes_to_close,
                    extras=None):
        return None

    def peek(self, spec, ctx, *, now=None):
        return True, None

    def mark_asked(self, spec, granted, reason, *, now=None):
        return None


# ------------------------------------------------------------------
# 环境搭建
# ------------------------------------------------------------------
def make_env(capital=1_000_000.0, alloc_pct=40.0, occlude=0.0):
    """搭一套**保留默认限额**的测试环境。

    ❗刻意不放宽 max_position_pct / max_total_pct：40% 底仓撞 20% 单笔上限
    正是本守卫要测的那一段，把限额放开就永远测不到分批。
    """
    from deva.naja.bandit.core_holdings import CoreHoldingSpec
    from deva.naja.bandit.core_position import CorePositionLedger
    from deva.naja.bandit.t_rotation import TRotationConfig, TRotationEngine
    from deva.naja.bandit.t_rotation_runner import TRotationRunner
    from deva.naja.bandit.virtual_portfolio import VirtualPortfolio

    clock = {"t": datetime(*D1, 9, 35).timestamp()}

    vp = VirtualPortfolio(account_name=TEST_ACCOUNT)
    vp.set_market_time_service(TickingMTS(clock))
    vp.clear_history()
    vp.clear_all_positions()
    vp.set_capital(capital)

    # 别的策略先把总额度占掉一块（`headroom` 就是留给底仓的钱）
    if occlude > 0:
        left = occlude
        while left > 1e-6:
            chunk = min(left, 200_000.0)
            pos = vp.open_position(
                strategy_id="other", strategy_name="别的策略",
                stock_code="600000", stock_name="占位",
                price=10.0, quantity=chunk / 10.0,
            )
            assert pos is not None, f"占位持仓建立失败（{chunk:,.0f} 元）"
            left -= chunk

    spec = CoreHoldingSpec(
        code="588200", bus_code="sh588200", name="科创芯片ETF嘉实",
        market="CN", target_shares=0.0, alloc_pct=alloc_pct, round_lot=100.0,
    )
    quotes = QuoteSource()
    ledger = CorePositionLedger(persist=False)
    eng = TRotationEngine(
        portfolio=vp, ledger=ledger,
        config=TRotationConfig(max_round_pct=0.30, max_round_amount=500_000.0),
    )
    runner = TRotationRunner(
        portfolio=vp, quotes=quotes, engine=eng, ledger=ledger, specs=[spec],
        portfolios={"CN": vp},
        establish_missing=True, flat_poll_limit=99999,
        clock=lambda: clock["t"],
        # ❗本守卫测的是「分批的告警是否恰当」，不是大环境闸门、也不是守望台。
        # 这两层现在默认开，不显式放行的话所有用例都会被「决策中心不可用」
        # /「还不值得问」挡掉，变成一堆看不懂的全红。它们各自有专门守卫：
        #   大环境闸门 → verify_core_establish_gate.py
        #   守望       → verify_core_establish_watch.py
        establish_gate=_OpenGate(),
        establish_watch=_OpenWatch(),
    )
    return {
        "vp": vp, "quotes": quotes, "eng": eng, "ledger": ledger,
        "spec": spec, "runner": runner, "clock": clock,
    }


def push_quote(env, price, cum_volume, prev_close=PREV_CLOSE):
    env["quotes"].put(env["spec"].code, Quote(
        code=env["spec"].code, name=env["spec"].name,
        current=price, prev_close=prev_close, volume=cum_volume,
    ))


def step(env, minutes=0.5):
    """推进模拟时钟半分钟（与真实轮询节奏一致）。"""
    env["clock"]["t"] += minutes * 60


def poll(env, rounds=1, price=1.0, vol0=1_000_000):
    for i in range(rounds):
        step(env)
        push_quote(env, price, vol0 + i)
        env["runner"].poll()


def held_shares(env):
    return sum(
        p.quantity for p in env["vp"].get_all_positions(status="OPEN")
        if p.stock_code == env["spec"].code
    )


# ════════════════════════════════════════════════════════════════
#  守卫
# ════════════════════════════════════════════════════════════════
def check_batch_fill_is_silent():
    """A/B/C) 分批补满目标：全程零 ERROR，且过程要留痕。"""
    env = make_env()
    vp, spec = env["vp"], env["spec"]
    single = vp.single_position_budget

    with LogTrap() as trap:
        poll(env, rounds=12)

    target = env["runner"]._plan_targets.get(spec.code, 0.0)
    assert target > 0, "目标份额没折算出来 —— 底仓计划根本没建立"

    fills = [m for m in trap.all_msgs() if "补足底仓" in m]
    assert len(fills) >= 2, (
        f"40% 底仓应分批建成，实际只有 {len(fills)} 笔 —— "
        f"若只有 1 笔，说明有人用 bypass_limits 绕过了单笔限额"
    )
    # 分批过程要能看出这是第几批 / 共几批，否则人（和日志）看不出它在干活
    assert any("分批 1/" in m for m in fills), f"分批没标注批次号：{fills[:1]}"

    assert trap.errors() == [], (
        f"分批过程就喊人了 —— 这正是把自愈过程伪装成故障的老毛病：{trap.errors()[:1]}"
    )
    assert not [m for m in trap.all_msgs() if "需要人工介入" in m], (
        "底仓正在分批却写了「需要人工介入」"
    )

    held = held_shares(env)
    assert abs(held - target) <= spec.round_lot, (
        f"分批没补满目标：持有 {held:.0f} / 目标 {target:.0f}"
    )
    assert held * 1.0 <= target + spec.round_lot, "买超了目标份额"

    st = env["runner"].get_status()["symbols"][0]
    assert st["budget_warned"] is None, (
        f"底仓已到位却仍标着卡住日期 {st['budget_warned']}"
    )
    assert st["fill_stalled_rounds"] == 0, st["fill_stalled_rounds"]

    print(f"A/B/C) 分批 OK —— 目标 {target:.0f} 份分 {len(fills)} 笔补满，"
          f"单笔上限 {single:,.0f} 元，全程零 ERROR")


def check_true_stall_escalates_once():
    """D/E) 额度被占死：按剩余空间买完后，连续零增长 N 轮才告警一次。"""
    occlude = 420_000.0
    env = make_env(occlude=occlude)
    vp, spec, runner = env["vp"], env["spec"], env["runner"]
    headroom = vp.category_position_budget - occlude
    expect_floor = int(headroom / 1.0 / spec.round_lot) * spec.round_lot

    with LogTrap() as trap:
        poll(env, rounds=20)

    held = held_shares(env)
    assert held > 0, "额度被占用后一笔都没买 —— 应该是按剩余空间买，不是放弃"
    assert held <= expect_floor + 1e-6, (
        f"买超了：持有 {held:.0f} 份 vs 可用额度允许 {expect_floor:.0f} 份"
    )

    errs = trap.errors()
    # 下单被拒是另一类失败，本用例里不该出现
    assert not [m for m in errs if "建仓失败" in m], f"撞到仓位限额被拒：{errs[:1]}"

    stalled = [m for m in errs if "底仓卡住" in m]
    assert stalled, (
        f"真卡住了却不告警 —— 用户会以为底仓已经到位（日志：{errs[:2]}）"
    )
    assert len(stalled) == 1, f"卡住告警刷屏了 {len(stalled)} 条（应每天 1 条）"
    assert "连续" in stalled[0], (
        f"告警没说清「连续几轮零增长」，读日志的人分不清"
        f"「正在分批」与「卡死」：{stalled[0]}"
    )
    assert "需要人工介入" in stalled[0], "真卡住时不提示人工介入，人不会来看"

    # 分批的前几轮仍然不许喊人 —— 那时系统还在往前走
    infos = [m for m in trap.all_msgs() if "补足底仓" in m]
    assert infos, "分批过程完全没留痕"
    assert not [m for m in infos if "需要人工介入" in m], "分批批次里混进了告警文案"

    st = runner.get_status()["symbols"][0]
    assert st["budget_warned"] == f"{D1[0]:04d}-{D1[1]:02d}-{D1[2]:02d}", st["budget_warned"]
    assert st["held_shares"] == held, (st["held_shares"], held)

    print(f"D/E) 真卡住 OK —— 其它策略占 {occlude:,.0f} 元，底仓按剩余 "
          f"{headroom:,.0f} 元买到 {held:.0f} 份，卡住告警恰好 1 条")


def check_stall_limit_is_configurable():
    """F) 「多久才算卡住」要能调，别把 3 轮写死在代码里。"""
    from deva.naja.bandit.t_rotation_runner import TRotationRunner

    assert TRotationRunner.DEFAULT_STALL_LIMIT >= 2, (
        "至少要给分批留出 2 轮容错，否则第一轮没买满就开始喊人 —— 回到老毛病"
    )
    # 隐性入口：构造参数优先于环境变量
    env = make_env()
    env["runner"]._stall_limit = 99
    with LogTrap() as trap:
        poll(env, rounds=6)
    assert trap.errors() == [], f"调高阈值后仍在喊人：{trap.errors()[:1]}"
    print(f"F) 卡住阈值可调 OK —— 默认 {TRotationRunner.DEFAULT_STALL_LIMIT} 轮，"
          f"调到 99 轮后 6 轮内零告警")


def main():
    checks = [
        check_batch_fill_is_silent,
        check_true_stall_escalates_once,
        check_stall_limit_is_configurable,
    ]
    failed = []
    for fn in checks:
        try:
            fn()
        except AssertionError as e:
            failed.append(fn.__name__)
            print(f"  ❌ {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed.append(fn.__name__)
            print(f"  💥 {fn.__name__}: {type(e).__name__}: {e}")
    print()
    if failed:
        print(f"❌ {len(failed)}/{len(checks)} 项失败：{', '.join(failed)}")
        return 1
    print(f"✅ {len(checks)}/{len(checks)} 项通过 —— 分批不喊人，卡住才喊，且只喊一次")
    return 0


if __name__ == "__main__":
    sys.exit(main())
