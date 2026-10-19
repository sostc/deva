#!/usr/bin/env python3
"""守卫：QueryState 的上下游是否真的接上了。

守什么
------
QueryState 长期存在「字段写了没人读、读了没人写」的静默失效：

* ``SignalStream.set_query_state()`` 全仓无调用 → ``compute_priority`` 恒按基础分；
* ``portfolio_state`` 只有死代码 ``update(feedback)`` 写 → 线上恒 None，
  「已持仓 ×0.3」从未生效；
* ``market_regime`` 单批覆盖，12 只的批次能把 62 只的结论翻面；
* ``avg_change`` 存的是 ``mean(|r|)``，跌市里显示为正数；
* ``attention_focus`` 按 max 归一化，榜首恒 1.0，下游加成失去区分度；
* ``macro_liquidity_signal`` 的量能项是横截面离散度，且无基准时垫 0.3。

本脚本用行为用例守这些点，而不是 grep 字符串。

用法：
    python scripts/verify/verify_query_state_wiring.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

failures = []


def _check(cond, msg):
    if not cond:
        failures.append(msg)


def test_health():
    from deva.naja.attention.kernel.state import QueryState, FIELD_TTL

    qs = QueryState()
    _check(qs.is_stale("market_regime"), "从未写入的字段必须判为 stale")

    qs._mark("market_regime", ts=1000.0, source="test", sample_size=62)
    _check(qs.is_stale("market_regime", now=1100.0) is False, "100s 前的 regime 不该过期")
    _check(
        qs.is_stale("market_regime", now=1000.0 + FIELD_TTL["market_regime"] + 1) is True,
        "超过 TTL 的 regime 必须判为 stale",
    )

    h = qs.health(now=1000.0)
    _check("market_regime" in h["live_fields"], "health 应把新鲜字段列入 live_fields")
    _check("portfolio_state" in h["stale_fields"], "health 应把未写字段列入 stale_fields")


def test_regime_window():
    from deva.naja.attention.kernel.state import QueryState

    qs = QueryState()
    # 62 只全涨 2%
    qs._detect_and_update_regime([2.0] * 62, 1000.0)
    _check(qs.market_regime["type"] == "trend_up", f"62 只全涨应判 trend_up，实得 {qs.market_regime}")
    _check(qs.market_regime["sample_size"] == 62, "sample_size 应记录当窗口样本量")
    _check(qs.market_regime["avg_change"] > 0, "avg_change 必须是有符号均值（涨市为正）")

    # 30 秒后一批 12 只全跌 2% —— 单批覆盖会把 regime 翻面，加权窗口不该翻
    qs._detect_and_update_regime([-2.0] * 12, 1030.0)
    _check(
        qs.market_regime["type"] == "trend_up",
        f"12 只的薄批次不该翻转 62 只的结论，实得 {qs.market_regime['type']}",
    )
    _check(qs.market_regime["sample_size"] == 74, "窗口应按样本量累加（62+12）")
    _check(qs.market_regime["avg_change"] > 0, "加权后仍应为正（62 涨 vs 12 跌）")

    # 90 秒后（62 只那批已出窗）再来 12 只全跌 → 这时才允许翻面
    qs._detect_and_update_regime([-2.0] * 12, 1120.0)
    _check(qs.market_regime["type"] == "trend_down", "窗口内的旧批次出窗后应反映新方向")
    _check(qs.market_regime["sample_size"] == 12, "出窗后只应剩最新一批（1000/1030 都已超过 60s）")


def test_attention_focus_strength():
    from deva.naja.attention.kernel.state import QueryState

    weak = QueryState()
    weak._derive_and_update_attention_focus(["aaa", "bbb"], [0.9, 0.8], [1e7, 1e7], None, None, 1.0)
    strong = QueryState()
    strong._derive_and_update_attention_focus(["aaa", "bbb"], [9.0, 8.0], [1e7, 1e7], None, None, 1.0)

    _check(
        strong.attention_focus["aaa"] > weak.attention_focus["aaa"] + 0.2,
        f"强度不同的题材必须有不同的 focus，实得 weak={weak.attention_focus}, strong={strong.attention_focus}",
    )
    _check(
        weak.attention_focus["aaa"] < 1.0,
        "focus 不应再强制归一化到 1.0（否则下游加成恒为 1.5×）",
    )


def test_volume_baseline():
    from deva.naja.attention.kernel.state import QueryState

    qs = QueryState()
    symbols = [f"s{i}" for i in range(10)]
    # 第一批只建立基准，不该给分
    score1 = qs._volume_rate_score(symbols, [1e6] * 10, 1000.0)
    _check(score1 is None, "首次没有基准时必须返回 None（中性），不能凭横截面离散度给分")

    score2 = qs._volume_rate_score(symbols, [1e6 + 1e5] * 10, 1010.0)
    _check(score2 is None, "第二批建立 EMA，仍不该立刻给分")
    _check(qs._vol_rate_ema and qs._vol_rate_ema > 0, "EMA 应已被首批速率初始化")

    # 速率翻倍 → 正分
    score3 = qs._volume_rate_score(symbols, [1e6 + 3e5] * 10, 1020.0)
    _check(score3 is not None and score3 > 0.3, f"放量应给出正分，实得 {score3}")

    # 速率骤降 → 负分
    score4 = qs._volume_rate_score(symbols, [1e6 + 3.05e5] * 10, 1030.0)
    _check(score4 is not None and score4 < 0, f"缩量应给出负分，实得 {score4}")

    # 间隔不足 5 秒的批次**不许重置基准**：热点事件 2~3 秒推一批同一快照，
    # 若每批都重置时间戳，dt 永远 < 5s，量能项就永远算不出来。
    qs2 = QueryState()
    qs2._volume_rate_score(symbols, [1e6] * 10, 2000.0)
    qs2._volume_rate_score(symbols, [1e6 + 1e5] * 10, 2002.0)
    _check(
        qs2._vol_snapshot.get("s0") == (1e6, 2000.0),
        f"dt<5s 的批次不该推进基准，实得 {qs2._vol_snapshot.get('s0')}",
    )


def test_liquidity_direction():
    """跌市必须给出偏紧的流动性（文档契约），而不是偏松。"""
    from deva.naja.attention.kernel.state import QueryState

    up = QueryState()
    up.update_from_market([f"s{i}" for i in range(20)], [2.0] * 20, [1e6] * 20,
                          [100] * 20, timestamp=1000.0, source="test")
    down = QueryState()
    down.update_from_market([f"s{i}" for i in range(20)], [-2.0] * 20, [1e6] * 20,
                            [100] * 20, timestamp=1000.0, source="test")

    _check(
        up.liquidity_components.get("change_score", 0) > 0
        > down.liquidity_components.get("change_score", 0),
        "change_score 必须跟随涨跌方向（涨为正、跌为负），"
        f"实得 up={up.liquidity_components}, down={down.liquidity_components}",
    )
    _check(
        up.macro_liquidity_signal > down.macro_liquidity_signal,
        "涨市流动性应高于跌市（旧实现取 -avg_change，方向是反的）："
        f"up={up.macro_liquidity_signal:.3f}, down={down.macro_liquidity_signal:.3f}",
    )


def test_compute_priority():
    from deva.naja.attention.kernel.state import QueryState
    from deva.naja.strategy.result_store import StrategyResult

    qs = QueryState()
    qs.portfolio_state = {"held_symbols": ["nvda"]}
    qs.mark_field("portfolio_state", source="test")
    qs.attention_focus = {"nvda": 0.8, "amd": 0.05}
    qs.mark_field("attention_focus", source="test")
    qs.market_regime = {"type": "neutral"}
    qs.mark_field("market_regime", source="test")

    held = StrategyResult(id="1", strategy_id="s", strategy_name="s", ts=0, success=True,
                          metadata={"symbol": "NVDA", "score": 0.5})
    other = StrategyResult(id="2", strategy_id="s", strategy_name="s", ts=0, success=True,
                           metadata={"symbol": "AMD", "score": 0.5})

    p_held = held.compute_priority(qs)
    p_other = other.compute_priority(qs)
    _check(held.matches_held_symbol, "持仓标的必须被识别（大小写不敏感）")
    _check(p_held < p_other * 0.5, f"持仓标的应被压到 0.3 倍：held={p_held}, other={p_other}")

    # 过期后不该再打折：旧快照不能当新事实用
    qs.portfolio_state = {"held_symbols": ["nvda"]}
    qs._field_meta["portfolio_state"]["ts"] = 0.0
    p_stale = StrategyResult(id="3", strategy_id="s", strategy_name="s", ts=0, success=True,
                             metadata={"symbol": "NVDA", "score": 0.5}).compute_priority(qs)
    _check(not p_stale < p_other * 0.5, "portfolio_state 过期后不应继续套用持仓折价")


def test_t_rotation_env_gate():
    from deva.naja.bandit.t_rotation import TRotationEngine

    ok, why, scale = TRotationEngine._env_gate(None)
    _check(ok and scale == 1.0, "无环境信息时不该拦开仓")

    ok, why, scale = TRotationEngine._env_gate({"allow_open": False, "reason": "trend_down"})
    _check(not ok and "trend_down" in why, "allow_open=False 必须拦住并带出原因")

    ok, why, scale = TRotationEngine._env_gate({"size_scale": 0.5})
    _check(ok and abs(scale - 0.5) < 1e-9, "逆风缩放应传递到仓位")

    ok, why, scale = TRotationEngine._env_gate({"size_scale": -3})
    _check(ok and scale >= 0.1, "缩放必须被夹到安全区间")

    # 分动作解析：下跌日里倒 T 是顺风的，不该被 allow_open=False 一起关掉
    ok, why, scale = TRotationEngine._env_gate(
        {"allow_open": False, "allow_reverse": True, "reverse_size_scale": 0.8},
        "SELL_T",
    )
    _check(ok and abs(scale - 0.8) < 1e-9, "倒 T 应被放行并按 reverse_size_scale 缩放")
    ok, why, scale = TRotationEngine._env_gate(
        {"allow_open": False, "allow_forward": False, "reason": "个股走弱"}, "BUY_T"
    )
    _check(not ok and "个股走弱" in why, "allow_forward=False 必须拦住正 T 并带出原因")


def test_dip_license():
    """逆风日的正 T：跌够深才买、按批递减、个股走弱不买。"""
    from deva.naja.bandit.t_rotation import (
        TRotationEngine, RotationRound, RotationSignal, KIND_FORWARD,
    )
    from deva.naja.bandit.intraday_deviation import RotationThresholds

    eng = TRotationEngine.__new__(TRotationEngine)
    eng._thr_by_code = {}
    eng._thresholds = RotationThresholds()          # buy_dev_close=1.5
    eng._rounds = {}

    env = {
        "allow_open": False, "allow_forward": True, "allow_reverse": True,
        "forward_size_scale": 1.0, "require_dip": True, "dip_ratio": 1.5,
        "dip_batch_scales": [0.5, 0.3, 0.2], "dip_ok": True,
    }
    sig = RotationSignal(stock_code="000001", action="BUY_T", ret=-1.0)
    ok, why, scale = eng._forward_gate(sig, env, 1000.0)
    _check(not ok and "浅跌" in why, f"跌幅不足阈值 1.5 倍时应拦下，实得 ok={ok} why={why}")

    sig.ret = -3.0                                   # 3.0 > 1.5*1.5=2.25
    ok, why, scale = eng._forward_gate(sig, env, 1000.0)
    _check(ok and abs(scale - 0.5) < 1e-9, f"第一批应为 0.5 倍，实得 {scale}")

    eng._rounds["r1"] = RotationRound(
        round_id="r1", stock_code="000001", kind=KIND_FORWARD,
        planned_qty=100, first_price=10.0, first_time=1000.0,
    )
    ok, why, scale = eng._forward_gate(sig, env, 1100.0)
    _check(ok and abs(scale - 0.3) < 1e-9, f"第二批应递减到 0.3 倍，实得 {scale}")

    env_weak = dict(env, dip_ok=False, dip_reason="弱于中位数 4pct")
    ok, why, scale = eng._forward_gate(sig, env_weak, 1100.0)
    _check(not ok and "弱于中位数" in why, "个股明显弱于同批时应拒绝抄底")

    # 三批用完就该停手，不能无限接
    eng._rounds["r2"] = RotationRound(
        round_id="r2", stock_code="000001", kind=KIND_FORWARD,
        planned_qty=100, first_price=9.0, first_time=1200.0,
    )
    eng._rounds["r3"] = RotationRound(
        round_id="r3", stock_code="000001", kind=KIND_FORWARD,
        planned_qty=100, first_price=8.0, first_time=1300.0,
    )
    ok, why, scale = eng._forward_gate(sig, env, 1400.0)
    _check(not ok and "批次已用完" in why, "三批用完必须停手")


def test_relative_strength():
    """相对强度必须能区分「跟跌」与「自己出事」，样本不足时不许瞎猜。"""
    from deva.naja.attention.kernel import state as st

    qs = st.QueryState()
    qs._market_history["symbols"] = ["AAA", "BBB", "CCC", "DDD", "EEE", "nvda"]
    qs._market_history["returns"] = [-2.0, -3.0, -1.0, -2.5, -1.5, -1.0]
    rel = qs.relative_strength("NVDA")
    _check(rel is not None and rel > 0, f"跌得比中位数少应给正相对强度，实得 {rel}")

    qs._market_history["returns"] = [-2.0, -3.0, -1.0, -2.5, -1.5, -9.0]
    rel = qs.relative_strength("NVDA")
    _check(rel is not None and rel < -2.0, f"自己暴跌应给显著负值，实得 {rel}")

    rel = qs.relative_strength("9999.HK")
    _check(rel is None, "不在快照里的标的必须返回 None，不能假装相对强度为 0")

    qs._market_history["symbols"] = ["AAA", "BBB"]
    qs._market_history["returns"] = [1.0, 2.0]
    _check(qs.relative_strength("AAA") is None, "样本过少时不许下相对强度结论")


def test_signal_stream_wiring():
    """容器必须把 QueryState 注入 SignalStream（字符串检查，因为这里是启动路径）。"""
    container = (ROOT / "deva/naja/application/container.py").read_text(encoding="utf-8")
    _check(
        "stream.set_query_state(self.query_state)" in container,
        "container.init_signal_stream 未注入 QueryState —— 优先级规则会再次变成死代码",
    )


def main():
    for fn in (
        test_health,
        test_regime_window,
        test_attention_focus_strength,
        test_volume_baseline,
        test_liquidity_direction,
        test_compute_priority,
        test_t_rotation_env_gate,
        test_dip_license,
        test_relative_strength,
        test_signal_stream_wiring,
    ):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            failures.append(f"{fn.__name__} 抛异常: {type(e).__name__}: {e}")

    if failures:
        print("❌ 失败：")
        for f in failures:
            print("  -", f)
        return 1

    print("✅ QueryState 上下游接线校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
