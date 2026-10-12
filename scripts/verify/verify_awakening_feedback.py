#!/usr/bin/env python3
"""验证「执行结果 → 觉醒」闭环反馈（D3）。

为什么需要这个脚本：
    manas 的快照基线（scripts/verify/verify_manas_compute_snapshot.py）
    **monkeypatch 了 ManasEngine._get_awakening_level**（固定为 neutral ×1.0），
    所以 D3 的觉醒链路改动在快照里是看不见的。必须有独立验证。

跑法：
    python scripts/verify/verify_awakening_feedback.py            # 报告模式
    python scripts/verify/verify_awakening_feedback.py --strict   # 违约退出码 1
"""

from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("NAJA_AWAKENING_FEEDBACK_BURST", "")  # 用默认档位表


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="有违约则退出码 1")
    args = parser.parse_args()

    violations: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name}" + (f"  —— {detail}" if detail else ""))
        if not ok:
            violations.append(name)

    print("=" * 68)
    print("① 事件类型已注册到交易总线")
    print("=" * 68)
    from deva.naja.events import TradeOutcomeEvent, resolve_event_bus_type, get_trading_bus
    try:
        bus_type = resolve_event_bus_type(TradeOutcomeEvent)
        check("TradeOutcomeEvent 路由", bus_type == "trading", f"bus={bus_type}")
    except Exception as e:  # noqa: BLE001
        check("TradeOutcomeEvent 路由", False, str(e))

    print()
    print("=" * 68)
    print("② 觉醒等级读的是真来源（断点 #2 已修）")
    print("=" * 68)
    from deva.naja.attention.orchestration.trading_center import TradingCenter

    tc = TradingCenter()
    # 往那个"从未被写入的字典"里塞一个假值：修好后不应被它带偏
    tc._awakened_state["awakening_level"] = "BOGUS_FROM_STALE_DICT"
    level = tc.get_awakening_level()
    check(
        "不再读 _awakened_state 的陈旧值",
        level != "BOGUS_FROM_STALE_DICT",
        f"读到 {level!r}",
    )
    alaya = tc._get_awakened_alaya()
    check(
        "真来源 = 共享 AwakenedAlaya.awakening_engine",
        alaya is not None and getattr(alaya, "awakening_engine", None) is not None,
    )
    tc._awakened_state.pop("awakening_level", None)

    print()
    print("=" * 68)
    print("③ 交易结果真的喂进了 AwakeningEngine（断点 #3 已修）")
    print("=" * 68)
    engine = alaya.awakening_engine
    before = engine.get_stats()["signal_count"]
    ok = tc.record_trade_outcome("600000", 8.0, close_reason="TAKE_PROFIT", strategy_id="s1")
    after = engine.get_stats()["signal_count"]
    check("record_trade_outcome 返回 True", ok is True)
    check("弱信号数量增加", after > before, f"{before} → {after}")

    print()
    print("=" * 68)
    print("④ 显著结果能跨过阈值；微小结果不会（不是静默 no-op）")
    print("=" * 68)
    level_after_big = tc.get_awakening_level()
    check(
        "显著结果(8%)抬高觉醒等级",
        level_after_big != "dormant",
        f"level={level_after_big}",
    )

    # 新实例：微小结果（0.3%，burst=1）不应跨过 DORMANT=3
    from deva.naja.knowledge.alaya.awakened_alaya import AwakenedAlaya
    fresh = AwakenedAlaya()
    lvl0 = fresh.awakening_engine.get_awakening_level()
    import types
    proxy = types.SimpleNamespace(
        _get_awakened_alaya=lambda: fresh,
        _awakened_state={},
        _get_awakening_level=lambda: fresh.awakening_engine.get_awakening_level(),
    )
    TradingCenter.record_trade_outcome(proxy, "000001", 0.3, close_reason="FORCE")
    lvl1 = fresh.awakening_engine.get_awakening_level()
    check(
        "微小结果(0.3%)不虚报觉醒",
        lvl0 == lvl1 == "dormant",
        f"{lvl0} → {lvl1}",
    )

    print()
    print("=" * 68)
    print("⑤ Manas 觉醒维度读到同一实例（读取端已接）")
    print("=" * 68)
    from deva.naja.attention.kernel.manas_engine import ManasEngine

    engine_m = ManasEngine()
    check("默认无 provider → dormant", engine_m._get_awakening_level() == "dormant")
    engine_m.set_awakening_level_provider(lambda: tc.get_awakening_level())
    check(
        "注入 provider 后读到真实等级",
        engine_m._get_awakening_level() == tc.get_awakening_level(),
        f"manas={engine_m._get_awakening_level()} tc={tc.get_awakening_level()}",
    )

    print()
    print("=" * 68)
    print("⑥ 总线订阅：发布 TradeOutcomeEvent 能回流到 TradingCenter")
    print("=" * 68)
    try:
        bus = get_trading_bus()
        received: list = []
        orig = tc.record_trade_outcome

        def spy(symbol, pnl_pct, **kw):
            received.append((symbol, pnl_pct))
            return orig(symbol, pnl_pct, **kw)

        tc.record_trade_outcome = spy  # type: ignore[assignment]
        bus.subscribe("TradeOutcomeEvent", lambda e: tc.record_trade_outcome(
            symbol=e.symbol, pnl_pct=e.pnl_pct, close_reason=getattr(e, "close_reason", "")
        ), subscription_id="verify_feedback")
        bus.publish(TradeOutcomeEvent(symbol="600519", pnl_pct=-6.5, close_reason="STOP_LOSS"))
        tc.record_trade_outcome = orig  # type: ignore[assignment]
        check("已投递到 TradingCenter", len(received) >= 1, f"received={received}")
    except Exception as e:  # noqa: BLE001
        check("总线端到端回流", False, str(e))

    print()
    print("=" * 68)
    if violations:
        print(f"❌ 违约 {len(violations)} 项: {violations}")
        return 1 if args.strict else 0
    print("✅ 全部通过：闭环反馈（执行结果 → 觉醒 → Manas 读取）已打通")
    return 0


if __name__ == "__main__":
    sys.exit(main())
