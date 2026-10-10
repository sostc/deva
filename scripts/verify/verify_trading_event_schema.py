#!/usr/bin/env python3
"""回归验证：StrategySignalEvent schema 与交易总线快捷发布方法。

背景（修复的 bug）：
    ``StrategySignalEvent`` 缺少 ``importance`` / ``market`` 字段，但
    ``trading_bus.publish_strategy_signal()`` 与 ``bus_bridge`` 的 4 个转换器
    都按这两个字段构造事件 → 一调用就 TypeError（整条认知→交易桥接是死代码）。
    同时 ``direction`` 只接受枚举，字符串会让 ``to_dict()`` / ``is_buy`` 崩。

跑法（必须用干净环境，否则会被 shim 干扰）：
    env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        TMPDIR="$TMPDIR" python3.13 scripts/verify/verify_trading_event_schema.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from deva.naja.events.trading_events import (
    StrategySignalEvent, TradeDecisionEvent, SignalDirection, DecisionResult,
)
from deva.naja.events.trading_bus import TradingEventBus


# ── 1) 字段存在 + bus_bridge 风格构造（原先必然 TypeError） ──────────────
e = StrategySignalEvent(
    symbol="AAPL.US", direction=SignalDirection.BUY, confidence=0.6,
    strategy_name="认知驱动", signal_type="cognitive_driven", current_price=None,
    price_change_pct=0.0, importance=0.9, market="us", metadata={"a": 1}, timestamp=0.0,
)
assert e.importance == 0.9, e.importance
assert e.market == "US", e.market  # 自动大写
print("1) bus_bridge 风格构造 OK")

# ── 2) direction 字符串归一化 ───────────────────────────────────────────
for raw, expect in [("buy", SignalDirection.BUY), ("卖出", SignalDirection.SELL),
                    ("unknown-xyz", SignalDirection.NEUTRAL), (None, SignalDirection.NEUTRAL)]:
    ev = StrategySignalEvent(symbol="X", direction=raw, confidence=0.1,
                             strategy_name="x", signal_type="t",
                             current_price=0.0, price_change_pct=0.0)
    assert ev.direction is expect, (raw, ev.direction)
    assert isinstance(ev.to_dict()["direction"], str)
print("2) direction 归一化 OK")

# ── 3) 默认路由字段 ─────────────────────────────────────────────────────
d = StrategySignalEvent(symbol="X", direction="buy", confidence=0.1,
                        strategy_name="x", signal_type="t",
                        current_price=0.0, price_change_pct=0.0)
assert d.importance == 0.5 and d.market == "CN"
assert {"importance", "market"} <= set(d.to_dict())
print("3) 默认 importance/market OK")

# ── 4) 快捷方法：publish_strategy_signal 可由字符串方向触发 ─────────────
bus = TradingEventBus()
got = []
bus.subscribe("StrategySignalEvent", lambda ev: got.append(ev), subscription_id="v_sig")
n = bus.publish_strategy_signal("000001", "buy", confidence=0.8,
                                strategy_name="BlockRotationHunter", market="CN",
                                importance=0.9, price_change_pct=0.02)
assert n == 1 and len(got) == 1, (n, got)
assert got[0].direction is SignalDirection.BUY
assert got[0].signal_type == "buy", got[0].signal_type  # 不再产生 "signalDirection.buy"
print("4) publish_strategy_signal OK, delivered =", n)

# ── 5) 总线路由过滤真的生效（min_importance / markets） ─────────────────
high = []
bus.subscribe("StrategySignalEvent", lambda ev: high.append(ev),
              subscription_id="v_hi", min_importance=0.8)
bus.publish_strategy_signal("000002", "buy", importance=0.3)   # 应被过滤
bus.publish_strategy_signal("000003", "buy", importance=0.95)  # 应通过
assert [ev.symbol for ev in high] == ["000003"], [ev.symbol for ev in high]

us_only = []
bus.subscribe("StrategySignalEvent", lambda ev: us_only.append(ev),
              subscription_id="v_us", markets={"US"})
bus.publish_strategy_signal("000004", "buy", market="CN", importance=0.9)  # 应被过滤
bus.publish_strategy_signal("AAPL.US", "buy", market="US", importance=0.9)  # 应通过
assert [ev.symbol for ev in us_only] == ["AAPL.US"], [ev.symbol for ev in us_only]
print("5) 重要性/市场过滤 OK")

# ── 6) 快捷方法：publish_trade_decision 容错解析 ────────────────────────
decisions = []
bus.subscribe("TradeDecisionEvent", lambda ev: decisions.append(ev), subscription_id="v_dec")
sig = StrategySignalEvent(symbol="AAPL.US", direction="buy", confidence=0.7,
                          strategy_name="x", signal_type="t",
                          current_price=100.0, price_change_pct=0.0, importance=0.9, market="US")
n2 = bus.publish_trade_decision(sig, "approved", approval_score=0.8, reason="ok")
assert n2 == 1 and len(decisions) == 1, (n2, decisions)
assert decisions[0].decision is DecisionResult.APPROVED
assert decisions[0].approved_direction is SignalDirection.BUY
assert decisions[0].to_dict()["approved_direction"] == "buy"
print("6) publish_trade_decision OK")

print("ALL PASS")
