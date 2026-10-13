"""验证「做 T 降成本」模块的核心不变量。

背景：
    用户要求长期持有半导体指数 ETF 作为底仓，中间用做 T 降低成本，
    但**做完必须买回、保证长期持有份额不减**。
    这条约束一旦被违反，整个策略的前提（永远有票可做 T）就没了，
    而且表现得很安静——份额悄悄少掉，没人报警。

本守卫锁死的不变量：
    A. 份额守恒   —— 任何一轮做 T 结束，约定持有份额不低于开始前
    B. 强制买回   —— 到期/收盘未买回的份额必须被补回，哪怕价格不利
    C. 底仓不侵蚀 —— target 以内的份额永不参与卖出；未登记计划的标的一律不许倒 T
    D. T+1        —— 当日买入的份额当日不可卖出
    E. 摩擦门槛   —— 预期空间覆盖不了佣金+滑点就不动手
    F. 锚必须是昨收 —— VWAP 会跟随价格漂移，低开低走时把偏离低估 7.6 倍

跑法：
    env -u PYTHONPATH TMPDIR=$(mktemp -d) python3 \
        scripts/verify/verify_t_rotation_core.py [--strict]
"""

import ast
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

# ★ 必须早于任何 deva 导入：本守卫会用 VirtualPortfolio 建/删持仓，
# 不隔离就会把假标的价格写进生产库 ~/.deva/nb.sqlite。
VERIFY_DIR = os.path.join(ROOT, "scripts", "verify")
if VERIFY_DIR not in sys.path:
    sys.path.insert(0, VERIFY_DIR)
from guard_sandbox import isolate_guard_db  # noqa: E402

isolate_guard_db()

BANDIT_DIR = os.path.join(ROOT, "deva", "naja", "bandit")
TR_FILE = os.path.join(BANDIT_DIR, "t_rotation.py")
VP_FILE = os.path.join(BANDIT_DIR, "virtual_portfolio.py")
CP_FILE = os.path.join(BANDIT_DIR, "core_position.py")
ID_FILE = os.path.join(BANDIT_DIR, "intraday_deviation.py")

TEST_ACCOUNT = "T_ROTATION_GUARD"

# 今天（2026-10-13）科创芯片指数的真实分时特征
PREV_CLOSE = 3350.25
OPEN_P = 3249.72
LOW_P = 3206.47
HIGH_P = 3402.35
CLOSE_P = 3350.20


# ────────────────────────────────────────────────────────────────
#  测试环境
# ────────────────────────────────────────────────────────────────
class FakeMTS:
    """VirtualPortfolio 依赖 market_time_service 单例，测试时注入。"""

    def __init__(self):
        self.t = time.time()

    def get_market_time(self):
        return self.t


def make_env(capital=50_000_000.0, max_round_pct=0.10, **cfg_over):
    from deva.naja.bandit.virtual_portfolio import VirtualPortfolio
    from deva.naja.bandit.core_position import CorePositionLedger
    from deva.naja.bandit.t_rotation import TRotationEngine, TRotationConfig
    from deva.naja.bandit.intraday_deviation import RotationThresholds

    vp = VirtualPortfolio(account_name=TEST_ACCOUNT)
    vp.set_market_time_service(FakeMTS())
    vp.clear_history()
    vp.set_capital(capital)
    vp.set_max_position_pct(1.0)
    vp.set_max_total_pct(1.0)

    cfg = TRotationConfig(
        max_round_pct=max_round_pct,
        max_round_amount=5_000_000.0,
        **cfg_over,
    )
    eng = TRotationEngine(
        portfolio=vp,
        ledger=CorePositionLedger(persist=False),
        thresholds=RotationThresholds(),
        config=cfg,
    )
    return vp, eng


def seed_base(vp, eng, code, price, qty, session_open, target=None):
    """建立"昨夜传承"的底仓，返回 baseline 份额。"""
    pos = vp.open_position(
        strategy_id="core", strategy_name="长期底仓",
        stock_code=code, stock_name=code, price=price, quantity=qty,
    )
    assert pos is not None, "底仓建立失败"
    pos.entry_time = session_open - 86400  # 昨天
    eng.register_target(code, target if target is not None else qty, name=code)
    eng.set_prev_close(code, PREV_CLOSE, name=code)
    eng._ctx[code].session_open_ts = session_open
    return qty


def v_shape_seq():
    """今天的 V 型：低开 → 探底 → 拉升创新高 → 回落收平。"""
    seq = [OPEN_P + (LOW_P - OPEN_P) * (i / 30.0) for i in range(31)]
    seq += [LOW_P + (HIGH_P - LOW_P) * (i / 80.0) for i in range(1, 81)]
    seq += [HIGH_P + (CLOSE_P - HIGH_P) * (i / 30.0) for i in range(1, 31)]
    return seq


def arc_seq():
    """高开 → 拉升 → 见顶回落 → 低位企稳。

    注意必须包含**转折**：require_stabilize 要求高抛前先出现下行 bar，
    否则会在单边拉升中卖飞。这不是 bug，是刻意的保护。
    """
    # 注意：这里必须用显式循环 append。写成列表推导 `seq += [seq[-1] + d ...]`
    # 的话，右侧会在 seq 扩展之前一次性求值，seq[-1] 恒为同一个值，
    # 整段序列变成一排常数 —— 行情压根没动过，信号自然永不触发。
    seq = [PREV_CLOSE * 1.02]
    for _ in range(40):
        seq.append(seq[-1] + PREV_CLOSE * 0.0010)   # 拉到 ~+5.9%
    for _ in range(30):
        seq.append(seq[-1] - PREV_CLOSE * 0.0015)   # 见顶回落
    for _ in range(25):
        seq.append(seq[-1] + PREV_CLOSE * 0.0008)   # 低位企稳反弹
    return seq


def run_seq(eng, code, seq, base_ts, session_open, minutes_to_close=True, start=0):
    actions = []
    for i, p in enumerate(seq):
        mtc = 240.0 * (1 - i / len(seq)) if minutes_to_close else None
        d = eng.on_tick(
            code, p, timestamp=base_ts + (start + i) * 60,
            minutes_to_close=mtc, session_open_ts=session_open,
        )
        if d["action"] != "NONE":
            actions.append((i, p, d["action"], d["reason"]))
    return actions


NOW = time.time()
SESSION_OPEN = NOW - 3 * 3600


# ════════════════════════════════════════════════════════════════
#  A/B. 份额守恒 & 强制买回
# ════════════════════════════════════════════════════════════════
def check_forward_t_conservation():
    """正 T 全链路：份额守恒且收益正确。"""
    vp, eng = make_env()
    base = seed_base(vp, eng, "TEST001", PREV_CLOSE, 10000.0, SESSION_OPEN)

    acts = run_seq(eng, "TEST001", v_shape_seq(), NOW, SESSION_OPEN)
    assert acts, "今天的 V 型行情应当至少触发一次做 T"

    after = vp.get_all_positions(status="OPEN")
    total = sum(p.quantity for p in after)
    assert abs(total - base) < 1.0, (
        f"正T 后份额不守恒: {base} -> {total}"
    )

    closed = [r for r in eng.list_rounds() if r.status == "CLOSED"]
    assert closed, "应当有完整闭环的轮次"
    rnd = closed[0]
    assert rnd.kind == "正T", rnd.kind
    expect = (rnd.second_price - rnd.first_price) * rnd.planned_qty
    assert abs(rnd.realized_edge - expect) < 1.0, (
        f"兑现差价算错: {rnd.realized_edge} vs {expect}"
    )
    # 今天的行情应该有像样的空间（跟踪回撤，不该是早早就走）
    assert rnd.edge_pct > 3.0, (
        f"跟踪回撤失效，仅吃到 {rnd.edge_pct:.2f}%（今天应有 ~5.7%）"
    )
    print(f"1) 正T 份额守恒 OK（{base:.0f}→{total:.0f}，兑现 {rnd.realized_edge:+.2f} / {rnd.edge_pct:+.2f}%）")


def check_reverse_t_conservation():
    """倒 T 全链路：卖出→义务→买回，份额必须回来。"""
    vp, eng = make_env()
    # 留一半超出 target 作为可轮换额度
    base = seed_base(vp, eng, "TEST002", PREV_CLOSE, 10000.0, SESSION_OPEN, target=5000.0)

    acts = run_seq(eng, "TEST002", arc_seq(), NOW, SESSION_OPEN)
    kinds = [a[2] for a in acts]
    assert "SELL_T" in kinds, f"高开见顶未触发倒 T: {kinds}"
    assert "CLOSE_BUY" in kinds, f"回落后未买回: {kinds}"

    ledger = eng._ledger
    assert ledger.outstanding_qty("TEST002") == 0, "买回后仍有未履行义务"
    total = sum(p.quantity for p in vp.get_all_positions(status="OPEN"))
    assert abs(total - base) < 1.0, f"倒T 后份额不守恒: {base} -> {total}"

    rnd = [r for r in eng.list_rounds() if r.kind == "倒T"][0]
    expect = (rnd.first_price - rnd.second_price) * rnd.planned_qty
    assert abs(rnd.realized_edge - expect) < 1.0, "倒T 差价算错"
    assert rnd.realized_edge > 0, (
        f"高抛低吸应当正收益，实为 {rnd.realized_edge:+.2f}"
    )
    print(
        f"2) 倒T 份额守恒 OK（{rnd.planned_qty:.0f} 份 @{rnd.first_price:.0f}→"
        f"@{rnd.second_price:.0f}，兑现 {rnd.realized_edge:+.2f}，{total:.0f} 份归位）"
    )


def check_forced_buyback():
    """★ 核心：卖出去到期不买回，必须被强制补回。"""
    vp, eng = make_env()
    base = seed_base(vp, eng, "TEST003", PREV_CLOSE, 10000.0, SESSION_OPEN, target=5000.0)

    seq = arc_seq()
    for i, p in enumerate(seq[:70]):  # 只走到"见顶回落"，不给它买回的机会
        eng.on_tick("TEST003", p, timestamp=NOW + i * 60,
                    minutes_to_close=200.0, session_open_ts=SESSION_OPEN)

    ledger = eng._ledger
    outstanding = ledger.outstanding("TEST003")
    assert outstanding, "未产生回购义务"
    ob_qty = outstanding[0].quantity

    held_now = sum(p.quantity for p in vp.get_all_positions(status="OPEN"))
    assert held_now < base, "卖出后份额应减少（此刻尚未买回）"

    # 价格一路向上，绝不会自然回落 → 只能靠强制买回兜底
    report = eng.settle_before_close(
        "TEST003", PREV_CLOSE * 1.09, now=NOW + 4 * 3600,
        session_open_ts=SESSION_OPEN,
    )
    assert report["forced_buyback"] > 0, "收盘结算没有强制买回"

    total = sum(p.quantity for p in vp.get_all_positions(status="OPEN"))
    assert abs(total - base) < 1.0, (
        f"强制买回后份额仍不守恒: {base} -> {total}"
    )
    assert ledger.outstanding_qty("TEST003") == 0, "仍有未履行义务"
    print(
        f"3) 强制买回 OK（追高 {ob_qty:.0f} 份也买回，{total:.0f} 份归位）"
    )


def do_reverse_sell(vp, ledger, code, qty, price, now, session_open):
    """真实地倒 T 卖出：减仓 + 挂回购义务（两步必须成对）。

    ⚠️ 减仓数量必须是 qty 而不是 p.quantity 的全部。减多了会让
    carried_in 本来就归零，正确实现和"忘记扣当日已卖"的坏实现
    算出同一个答案，这条守卫就变成摆设了 —— 踩过一次。
    """
    for p in vp.get_positions_by_stock(code):
        vp.reduce_position(p.position_id, qty, price, reason="T_ROTATION")
        break
    return ledger.open_obligation(
        code, qty, price, now=now, session_open_ts=session_open
    )


def check_no_double_sell():
    """已挂回购义务的份额不能被重复卖第二遍。"""
    vp, eng = make_env()
    seed_base(vp, eng, "TEST004", PREV_CLOSE, 10000.0, SESSION_OPEN, target=5000.0)

    ledger = eng._ledger
    q0 = ledger.session_quota("TEST004", vp, now=NOW, session_open_ts=SESSION_OPEN)
    assert q0 > 0

    ob = do_reverse_sell(vp, ledger, "TEST004", q0, PREV_CLOSE, NOW, SESSION_OPEN)
    q1 = ledger.session_quota("TEST004", vp, now=NOW, session_open_ts=SESSION_OPEN)
    assert abs(q1) < 1.0, (
        f"真实卖出 {q0:.0f} 份后当日额度应耗尽，实为 {q1:.0f} "
        f"—— 同一份额可被重复卖出，会一点点啃掉底仓"
    )
    ok, reason = ledger.can_sell("TEST004", 100.0, vp, now=NOW,
                                 session_open_ts=SESSION_OPEN)
    assert not ok, "重复使用同一配额竟然被放行"
    assert reason, "拒绝必须给出原因"

    # 买回之后，因为是当日买入，额度同样不能恢复（T+1）
    ledger.fulfill_obligation(ob.obligation_id, PREV_CLOSE, now=NOW)
    q2 = ledger.session_quota("TEST004", vp, now=NOW, session_open_ts=SESSION_OPEN)
    assert abs(q2) < 1.0, (
        f"买回的份额是当日买入，当日不可再卖，额度不应恢复，实为 {q2:.0f}"
    )
    print(f"4) 卖出配额不重复 OK（卖出 {q0:.0f} 份后额度归零，买回也不恢复）")


# ════════════════════════════════════════════════════════════════
#  C. 底仓不侵蚀
# ════════════════════════════════════════════════════════════════
def check_core_never_sold():
    """target 以内的份额，任何情况下都不允许卖出。"""
    vp, eng = make_env()
    seed_base(vp, eng, "TEST005", PREV_CLOSE, 10000.0, SESSION_OPEN, target=10000.0)

    ledger = eng._ledger
    quota = ledger.session_quota("TEST005", vp, now=NOW, session_open_ts=SESSION_OPEN)
    assert quota == 0, f"底仓全部是 target 时应无倒T额度，实为 {quota}"

    ok, reason = ledger.can_sell("TEST005", 100.0, vp, now=NOW,
                                 session_open_ts=SESSION_OPEN)
    assert not ok, "竟然允许卖出核心底仓"
    print(f"5) 底仓不可侵蚀 OK（target=10000 时额度 0，拒绝: {reason}）")


def check_unregistered_no_sell():
    """没登记计划的标的，一律不许倒 T（保守默认，不能反之）。"""
    vp, eng = make_env()
    vp.open_position(
        strategy_id="core", strategy_name="x", stock_code="TEST006",
        stock_name="TEST006", price=PREV_CLOSE, quantity=10000.0,
    )
    ledger = eng._ledger
    quota = ledger.session_quota("TEST006", vp, now=NOW, session_open_ts=SESSION_OPEN)
    assert quota == 0, f"未登记标的竟然有倒T额度 {quota}"
    ok, reason = ledger.can_sell("TEST006", 100.0, vp, now=NOW,
                                 session_open_ts=SESSION_OPEN)
    assert not ok, "未登记标的竟然能卖"
    assert "未登记" in reason, f"拒绝原因没说明是未登记: {reason}"
    print(f"6) 未登记不放行 OK（拒绝: {reason}）")


def check_partial_target_protect():
    """只有超出 target 的那部分可以动。"""
    vp, eng = make_env()
    seed_base(vp, eng, "TEST007", PREV_CLOSE, 10000.0, SESSION_OPEN, target=7000.0)
    ledger = eng._ledger
    quota = ledger.session_quota("TEST007", vp, now=NOW, session_open_ts=SESSION_OPEN)
    assert abs(quota - 3000.0) < 1.0, f"可用额度应为 3000，实为 {quota}"

    ok, _ = ledger.can_sell("TEST007", 3000.0, vp, now=NOW, session_open_ts=SESSION_OPEN)
    assert ok, "额度内应允许卖出"
    ok, reason = ledger.can_sell("TEST007", 3001.0, vp, now=NOW,
                                 session_open_ts=SESSION_OPEN)
    assert not ok, "超额度竟然允许，会咬到核心份额"
    print(f"7) 超额部分才可动 OK（10000持有/7000目标 → 额度 {quota:.0f}，3001 被拒）")


# ════════════════════════════════════════════════════════════════
#  D. T+1
# ════════════════════════════════════════════════════════════════
def check_t_plus_one():
    """当日买入的份额当日不可卖。"""
    vp, eng = make_env()
    # 只有今天买的仓位（entry_time = 现在）
    vp.open_position(
        strategy_id="core", strategy_name="x", stock_code="TEST008",
        stock_name="TEST008", price=PREV_CLOSE, quantity=10000.0,
    )
    eng.register_target("TEST008", 5000.0)
    ledger = eng._ledger
    sellable = ledger.sellable_today_shares(
        "TEST008", vp, now=NOW, session_open_ts=SESSION_OPEN
    )
    assert sellable == 0, f"当日新建仓位当日不可卖，实为 {sellable}"

    # 传给正T：没有昨夜传承份额 → 拒绝开仓
    ok = ledger.session_quota("TEST008", vp, now=NOW, session_open_ts=SESSION_OPEN)
    assert ok == 0
    print(f"8) T+1 约束 OK（当日新仓 0 份可卖，正T 也拒绝开仓）")




# ════════════════════════════════════════════════════════════════
#  E. 摩擦门槛与闸门
# ════════════════════════════════════════════════════════════════
def check_round_trip_cost():
    """往返摩擦成本必须算对：双边佣金+双边滑点+单边印花税。"""
    from deva.naja.bandit.intraday_deviation import RotationThresholds

    th = RotationThresholds(commission_pct=0.03, slippage_pct=0.05, stamp_duty_pct=0.0)
    # ETF: 2*(0.03+0.05) = 0.16
    assert abs(th.round_trip_cost_pct() - 0.16) < 1e-9, th.round_trip_cost_pct()

    stock = RotationThresholds(commission_pct=0.03, slippage_pct=0.05, stamp_duty_pct=0.05)
    assert abs(stock.round_trip_cost_pct() - 0.21) < 1e-9, stock.round_trip_cost_pct()
    print(f"9) 摩擦成本 OK（ETF {th.round_trip_cost_pct():.2f}% / 股票 {stock.round_trip_cost_pct():.2f}%）")


def check_thresholds_validate():
    """参数非法必须当场抛错，不能等到实盘才发现一直给券商打工。"""
    from deva.naja.bandit.intraday_deviation import RotationThresholds
    from deva.naja.bandit.t_rotation import TRotationEngine

    bad = RotationThresholds(reversion_ratio=1.5)
    assert bad.validate(), "非法 reversion_ratio 未被检出"

    worse = RotationThresholds(commission_pct=3.0)
    assert any("往返成本" in e for e in worse.validate()), "超高成本未被检出"

    vp = None
    try:
        from deva.naja.bandit.virtual_portfolio import VirtualPortfolio
        from deva.naja.bandit.core_position import CorePositionLedger
        vp = VirtualPortfolio(account_name=TEST_ACCOUNT)
        vp.set_market_time_service(FakeMTS())
        TRotationEngine(portfolio=vp, ledger=CorePositionLedger(persist=False),
                        thresholds=worse)
    except ValueError as e:
        assert "非法" in str(e), e
    else:
        raise AssertionError("非法参数竟然构造成功")
    finally:
        if vp is not None:
            vp.clear_history()
    print("10) 参数即错即报 OK（非法 reversion/超高成本均被拦截）")


def check_no_signal_without_prev_close():
    """缺昨收就没有任何百分比基准，必须拒绝而非假装知道。"""
    from deva.naja.bandit.core_position import CorePositionLedger
    from deva.naja.bandit.virtual_portfolio import VirtualPortfolio

    vp = VirtualPortfolio(account_name=TEST_ACCOUNT)
    vp.set_market_time_service(FakeMTS())
    vp.clear_history()
    from deva.naja.bandit.t_rotation import TRotationEngine
    eng = TRotationEngine(portfolio=vp, ledger=CorePositionLedger(persist=False))
    d = eng.on_tick("TEST009", 100.0, timestamp=NOW)
    assert d["action"] == "NONE", "没有昨收竟然还能做 T"
    assert "昨收" in d["reason"], f"原因没说明缺昨收: {d['reason']}"
    vp.clear_history()
    print(f"11) 缺昨收不做 T OK（{d['reason']}）")


def check_low_amplitude_no_action():
    """死水行情不动手。"""
    from deva.naja.bandit.intraday_deviation import (
        IntradayDeviationTracker, RotationThresholds, evaluate_deviation,
    )

    tr = IntradayDeviationTracker("X")
    tr.set_prev_close(100.0)
    for i in range(40):
        tr.update(99.5 + (i % 3) * 0.01, timestamp=i * 60)
    snap = tr.snapshot()
    assert snap.amplitude < 0.1, f"应为极小振幅，实为 {snap.amplitude}"

    sig = evaluate_deviation(snap, RotationThresholds(), bars_since_last_action=99)
    assert sig.action == "NONE", "死水行情竟然触发"
    assert "振幅" in sig.reason, sig.reason
    print(f"12) 死水行情不动手 OK（振幅 {snap.amplitude:.3f}%）")


def check_no_catching_falling_knife():
    """连跌途中不抄底，必须等转折确认。"""
    from deva.naja.bandit.intraday_deviation import (
        IntradayDeviationTracker, RotationThresholds, evaluate_deviation,
    )

    tr = IntradayDeviationTracker("X")
    tr.set_prev_close(100.0)
    for i in range(30):  # 一路向下
        tr.update(98.0 - i * 0.08, timestamp=i * 60)
    snap = tr.snapshot()
    assert snap.consecutive_down > 0, "应处于连跌中"

    sig = evaluate_deviation(snap, RotationThresholds(), bars_since_last_action=99)
    assert sig.action == "NONE", "连跌途中竟然抄底了"
    assert "连跌" in sig.reason or "企稳" in sig.reason, sig.reason

    # 打断了连跌就应该放行
    tr.update(snap.last + 0.05, timestamp=31 * 60)
    snap2 = tr.snapshot()
    sig2 = evaluate_deviation(snap2, RotationThresholds(), bars_since_last_action=99)
    assert sig2.action == "BUY_T", f"已企稳仍拒: {sig2.reason}"
    print(f"13) 右侧确认 OK（连跌拒: {sig.reason[:30]}... → 企稳放行）")


def check_no_new_reverse_near_close():
    """临近收盘不开新的倒 T。"""
    from deva.naja.bandit.intraday_deviation import (
        IntradayDeviationTracker, RotationThresholds, evaluate_deviation,
    )

    tr = IntradayDeviationTracker("X")
    tr.set_prev_close(100.0)
    seq = [101.0 + i * 0.05 for i in range(30)]
    for i, p in enumerate(seq):
        tr.update(p, timestamp=i * 60)
    tr.update(seq[-1] - 0.02, timestamp=30 * 60)  # 见回落（能过 require_stabilize）
    snap = tr.snapshot()
    assert snap.ret > 1.5, f"应已明显高于昨收，实为 {snap.ret}"

    near = evaluate_deviation(snap, RotationThresholds(), minutes_to_close=5.0,
                              bars_since_last_action=99)
    assert near.action == "NONE", "临近收盘竟然开了倒 T"
    assert "收盘" in near.reason, near.reason

    none = evaluate_deviation(snap, RotationThresholds(), minutes_to_close=None,
                              bars_since_last_action=99)
    assert none.action == "NONE", "距收盘时间未知时应保守拒单"
    print(f"14) 临近收盘不开倒T OK（{near.reason[:34]}...）")


# ════════════════════════════════════════════════════════════════
#  F. 锚必须是「昨收」
# ════════════════════════════════════════════════════════════════
def check_anchor_is_prev_close():
    """低开低走时 VWAP 会跟随漂移，把偏离严重低估。

    这条守卫防止有人日后"优化"回 VWAP 锚 —— 今天实测会低估 7.6 倍，
    净空间从 1.97% 压到 0.41%，几乎撞不上门槛。
    """
    from deva.naja.bandit.intraday_deviation import (
        IntradayDeviationTracker, RotationThresholds, evaluate_deviation,
    )

    tr = IntradayDeviationTracker("X")
    tr.set_prev_close(PREV_CLOSE)
    seq = [OPEN_P + (LOW_P - OPEN_P) * (i / 30.0) for i in range(31)]
    seq += [LOW_P + (LOW_P * 0.0004) * (i / 3.0) for i in range(1, 4)]
    for i, p in enumerate(seq):
        tr.update(p, timestamp=i * 60)
    snap = tr.snapshot()

    assert snap.ret < -3.0, f"应显著低于昨收，实为 {snap.ret}"
    ratio = abs(snap.ret) / max(abs(snap.dev_vwap), 1e-9)
    assert ratio > 3.0, (
        f"昨收锚/ VWAP锚 的偏离比仅 {ratio:.1f}x，本用例不足以证明昨收锚的必要性"
    )

    th = RotationThresholds()
    edge_prev = abs(snap.ret) * th.reversion_ratio - th.round_trip_cost_pct()
    edge_vwap = abs(snap.dev_vwap) - th.round_trip_cost_pct()
    assert edge_prev > edge_vwap * 2, (
        f"昨收锚的净空间 {edge_prev:.2f}% 未显著优于 VWAP 锚 {edge_vwap:.2f}%"
    )

    sig = evaluate_deviation(snap, th, bars_since_last_action=99)
    assert sig.action == "BUY_T", f"昨收锚下应触发低吸: {sig.reason}"
    print(
        f"15) 锚=昨收 OK（昨收 {snap.ret:+.2f}% vs VWAP {snap.dev_vwap:+.2f}%，"
        f"低估 {ratio:.1f}x；净空间 {edge_prev:.2f}% vs {edge_vwap:.2f}%）"
    )


def check_trailing_close_not_early():
    """跟踪回撤：单边拉升要拿住，不能刚翻红就跑。"""
    vp, eng = make_env()
    base = seed_base(vp, eng, "TEST010", PREV_CLOSE, 10000.0, SESSION_OPEN)
    acts = run_seq(eng, "TEST010", v_shape_seq(), NOW, SESSION_OPEN)

    buy = [a for a in acts if a[2] == "BUY_T"]
    assert buy, "未触发低吸"
    buy_price = buy[0][1]
    closes = [a for a in acts if a[2] == "CLOSE_SELL"]
    assert closes, "未触发了结"
    sell_price = closes[0][1]

    # 最低点 3206.47，最高 3402.35 → 好的了结点应远在两者中位之上
    mid = (LOW_P + HIGH_P) / 2
    assert sell_price > mid, (
        f"卖得太早: @{sell_price:.2f} 低于中位 {mid:.2f}（跟踪回撤失效）"
    )
    gain_pct = (sell_price - buy_price) / buy_price * 100
    assert gain_pct > 3.0, f"仅吃到 {gain_pct:.2f}%，跟踪回撤没生效"

    total = sum(p.quantity for p in vp.get_all_positions(status="OPEN"))
    assert abs(total - base) < 1.0, "份额不守恒"
    print(
        f"16) 跟踪回撤 OK（买 @{buy_price:.2f} 卖 @{sell_price:.2f}，"
        f"吃到 {gain_pct:+.2f}%，份额 {total:.0f}）"
    )


# ════════════════════════════════════════════════════════════════
#  虚拟仓基础能力
# ════════════════════════════════════════════════════════════════
def check_reduce_keeps_avg_cost():
    """按数量比例减仓后，剩余持仓的加权平均成本必须不变。"""
    from deva.naja.bandit.virtual_portfolio import VirtualPortfolio

    vp = VirtualPortfolio(account_name=TEST_ACCOUNT)
    vp.set_market_time_service(FakeMTS())
    vp.clear_history()
    vp.set_capital(10_000_000.0)
    vp.set_max_position_pct(1.0)

    a = vp.open_position(strategy_id="s", strategy_name="s", stock_code="T011",
                         stock_name="T011", price=10.0, quantity=1000.0)
    b = vp.open_position(strategy_id="s", strategy_name="s", stock_code="T011",
                         stock_name="T011", price=20.0, quantity=1000.0)
    assert a and b
    avg = (10.0 * 1000 + 20.0 * 1000) / 2000
    assert abs(avg - 15.0) < 1e-9

    qty_to_sell = 1000.0
    for p in (a, b):
        vp.reduce_position(p.position_id, qty_to_sell * 0.5, 15.0, reason="T")
    remain = vp.get_positions_by_stock("T011")
    total_qty = sum(p.quantity for p in remain)
    assert abs(total_qty - 1000.0) < 1e-6, f"剩余份额应为 1000，实为 {total_qty}"
    cost_now = sum(p.entry_price * p.quantity for p in remain) / total_qty
    assert abs(cost_now - avg) < 1e-6, (
        f"加权平均成本被改变: {avg} -> {cost_now}"
    )
    for p in remain:
        assert p.entry_time == a.entry_time or p.entry_time == b.entry_time
    vp.clear_history()
    print(f"17) 减仓维持加权均价 OK（剩余 {total_qty:.0f} 份，成本仍 {cost_now:.2f}）")


def check_capital_release():
    """减仓必须正确释放占用资金，否则可用资金会虚低导致无法再开仓。"""
    from deva.naja.bandit.virtual_portfolio import VirtualPortfolio

    vp = VirtualPortfolio(account_name=TEST_ACCOUNT)
    vp.set_market_time_service(FakeMTS())
    vp.clear_history()
    vp.set_capital(1_000_000.0)
    vp.set_max_position_pct(1.0)
    before = vp.get_summary()["available_capital"]

    p = vp.open_position(strategy_id="s", strategy_name="s", stock_code="T012",
                         stock_name="T012", price=100.0, quantity=1000.0)
    used = vp.get_summary()["available_capital"]
    assert abs((before - used) - 100_000.0) < 1.0, f"开仓占用资金错: {before-used}"

    vp.reduce_position(p.position_id, 500.0, 100.0, reason="T")
    after = vp.get_summary()["available_capital"]
    assert abs((after - used) - 50_000.0) < 1.0, f"减仓释放资金错: {after-used}"
    vp.clear_history()
    print(f"18) 资金释放 OK（减 500 份释放 {(after-used):.0f}）")


def check_dataclass_to_dict_parity():
    """项目约束：dataclass 字段数 == to_dict 键数，防止漏同步。"""
    from dataclasses import fields
    from deva.naja.bandit.core_position import CorePlan, BuybackObligation
    from deva.naja.bandit.intraday_deviation import (
        DeviationSnapshot, RotationSignal, RotationThresholds, IntradayBar,
    )
    from deva.naja.bandit.t_rotation import RotationRound, SymbolContext

    for cls, extra in [
        (CorePlan, 0), (BuybackObligation, 3),   # +3 个 @property
        (DeviationSnapshot, 0), (RotationSignal, 1),
        (RotationRound, 2), (IntradayBar, 0),
    ]:
        if not hasattr(cls, "to_dict"):
            continue
        try:
            inst = cls()
        except TypeError:
            continue
        n_fields = len(fields(cls))
        n_keys = len(inst.to_dict())
        assert n_fields + extra == n_keys, (
            f"{cls.__name__}: {n_fields} 字段 +{extra} 属性 vs {n_keys} 键"
        )
    print("19) dataclass/to_dict 字段数一致 OK")


# ════════════════════════════════════════════════════════════════
#  静态守卫
# ════════════════════════════════════════════════════════════════
def _method_bodies(path):
    """按方法/函数块切源码 + 去注释，避免整文件 grep 造成假警报。"""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    lines = src.splitlines()
    cleaned = []
    for ln in lines:
        s = ln.strip()
        cleaned.append("" if s.startswith("#") else ln)
    new_src = "\n".join(cleaned)
    tree2 = ast.parse(new_src)
    blocks = {}
    node_map = {id(n): n for n in ast.walk(tree)}
    for node in ast.walk(tree2):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                blocks[node.name] = ast.get_source_segment(new_src, node) or ""
            except Exception:
                blocks[node.name] = ""
    del node_map
    return blocks


def check_static_no_real_order():
    """做 T 模块不得出现任何真实下单动词。只读 + 虚拟仓是最好的风控。"""
    bad = ("place_order", "submit_order", "OpenSecTradeContext", "unlock_trade")
    for path in (TR_FILE, CP_FILE, ID_FILE):
        src = open(path, encoding="utf-8").read()
        for b in bad:
            assert b not in src, f"{os.path.basename(path)} 出现真实下单调用 {b}"
    print("20) 静态：无真实下单动词 OK（place_order 等 0 处）")


def check_static_bypass_only_on_buyback():
    """bypass_limits 只能出现在回购义务路径，不能给日常开仓开后门。"""
    blocks = _method_bodies(TR_FILE)
    hits = [n for n, b in blocks.items() if "bypass_limits=True" in (b or "")]
    assert hits, "未找到使用 bypass_limits 的方法"
    for name in hits:
        low = name.lower()
        assert (
            "close_reverse" in low or "settle_before_close" in low
        ), f"{name} 不应使用 bypass_limits —— 只有回购义务可以绕过限额"
    print(f"21) 静态：bypass 仅限回购路径 OK（{', '.join(hits)}）")


def check_static_legs_no_stop():
    """做 T 的两条腿必须把止盈止损推到不可达，否则会被 update_price 半路强平。"""
    blocks = _method_bodies(TR_FILE)
    openers = [
        n for n in blocks
        if n.startswith("_open_") or n == "settle_before_close"
    ]
    assert openers, "未找到开仓方法"
    for name in openers:
        body = blocks[name] or ""
        if "open_position(" not in body:
            continue
        assert "stop_loss_pct=-95.0" in body, (
            f"{name} 未把 stop_loss 推到不可达 —— "
            f"update_price 会在触发时自动平仓，导致做 T 闭环失败"
        )
        assert "take_profit_pct=995.0" in body, f"{name} 未把 take_profit 推到不可达"
    print(f"22) 静态：做T腿禁用止盈止损 OK（{len(openers)} 处开仓路径）")


def check_static_conservation_called():
    """每一条了结路径都必须做份额守恒校验，漏一条就是静默失效。"""
    blocks = _method_bodies(TR_FILE)
    closers = [n for n in blocks if n.startswith("_close_")]
    assert len(closers) >= 2, f"了结路径不足: {closers}"
    for name in closers:
        body = blocks[name] or ""
        assert "_verify_conservation" in body, (
            f"{name} 未调用份额守恒校验 —— 违反铁律且不会报错"
        )
    print(f"23) 静态：了结路径必做守恒校验 OK（{', '.join(sorted(closers))}）")


def check_static_settle_has_forced_path():
    """收盘结算必须包含强制买回，且 _verify_conservation 一并跟上。"""
    blocks = _method_bodies(TR_FILE)
    body = blocks.get("settle_before_close", "")
    assert body, "缺少 settle_before_close"
    assert "mark_forced" in body, "收盘结算没有调用强制买回标记"
    assert "_verify_conservation" in body, "强制买回后也要校验守恒"
    print("24) 静态：收盘强制买回链路完整 OK")


def check_static_obligation_paired_with_sell():
    """挂回购义务必须伴随真实减仓。

    账本本身是纯粹的（只记账），所以这条容易被绕过去：若有人只调
    open_obligation 而不减仓，账面上"欠着 5000 份"但实际一股没卖，
    carried_in 会凭空多出一倍，额度跟着虚增。
    open_obligation 本身无法自证，只能靠调用方约束。
    """
    blocks = _method_bodies(TR_FILE)
    callers = [
        n for n, b in blocks.items()
        if "open_obligation(" in (b or "")
    ]
    assert callers, "没有人调用 open_obligation？那义务机制就成摆设了"
    for name in callers:
        body = blocks[name] or ""
        assert (
            "_reduce_symbol" in body or "reduce_position" in body
        ), (
            f"{name} 调用了 open_obligation 却没有真实减仓，"
            f"会导致 carried_in 虚增、卖出额度被重复占用"
        )
    print(f"25) 静态：挂义务必伴随减仓 OK（{', '.join(sorted(callers))}）")


# ════════════════════════════════════════════════════════════════
def main():
    check_forward_t_conservation()
    check_reverse_t_conservation()
    check_forced_buyback()
    check_no_double_sell()

    check_core_never_sold()
    check_unregistered_no_sell()
    check_partial_target_protect()

    check_t_plus_one()

    check_round_trip_cost()
    check_thresholds_validate()
    check_no_signal_without_prev_close()
    check_low_amplitude_no_action()
    check_no_catching_falling_knife()
    check_no_new_reverse_near_close()

    check_anchor_is_prev_close()
    check_trailing_close_not_early()

    check_reduce_keeps_avg_cost()
    check_capital_release()
    check_dataclass_to_dict_parity()

    check_static_no_real_order()
    check_static_bypass_only_on_buyback()
    check_static_legs_no_stop()
    check_static_conservation_called()
    check_static_settle_has_forced_path()
    check_static_obligation_paired_with_sell()

    # 清理测试账户，别污染真实持仓
    try:
        from deva.naja.bandit.virtual_portfolio import VirtualPortfolio

        vp = VirtualPortfolio(account_name=TEST_ACCOUNT)
        vp.set_market_time_service(FakeMTS())
        vp.clear_history()
    except Exception:
        pass

    print("\nALL PASS (25)")


if __name__ == "__main__":
    main()
