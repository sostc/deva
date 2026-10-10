import os
import sys
import tempfile

os.environ["DEVA_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="naja_bus_test_"), "nb.sqlite")
sys.path.insert(0, "/Users/spark/pycharmproject/deva")

from deva.naja.events.trading_bus import TradingEventBus
from deva.naja.events.trading_events import StrategySignalEvent, SignalDirection


def make_event(symbol, direction=SignalDirection.BUY):
    return StrategySignalEvent(
        symbol=symbol,
        direction=direction,
        confidence=0.8,
        strategy_name="TestStrat",
        signal_type="test",
        current_price=199.0,
        price_change_pct=1.0,
    )


bus = TradingEventBus(use_stream=False, dedup_window=30.0)

received = []
bus.subscribe('StrategySignalEvent', lambda e: received.append(e), subscription_id='modA_sub')

n = bus.publish(make_event('NVDA'))
assert n == 1, n
assert len(received) == 1

# 去重：同分钟内同 symbol+direction 应被丢弃
n2 = bus.publish(make_event('NVDA'))
assert n2 == 0, n2

st = bus.get_stats()
assert st.total_published == 2, st.total_published
assert st.total_dropped == 1, st.total_dropped
assert st.total_delivered == 1, st.total_delivered
assert st.by_module.get('modA') == 1, st.by_module
print("deliver + dedup + stats OK")

# 异常回调不应影响其它订阅者
bus2 = TradingEventBus(use_stream=False)
ok = []
def boom(e):
    raise RuntimeError("boom")
bus2.subscribe('StrategySignalEvent', boom, subscription_id='bad_sub')
bus2.subscribe('StrategySignalEvent', lambda e: ok.append(e), subscription_id='good_sub')
n3 = bus2.publish(make_event('TSLA', SignalDirection.SELL))
assert n3 == 1, n3
assert len(ok) == 1
print("exception isolation OK")

# 重入：回调内再 publish 同一总线，不应死锁（锁外回调的关键收益）
bus3 = TradingEventBus(use_stream=False)
count = []
def reenter(e):
    count.append(1)
    if len(count) == 1:
        bus3.publish(make_event('AMD_INNER', SignalDirection.BUY))
bus3.subscribe('StrategySignalEvent', reenter, subscription_id='re_sub')
n4 = bus3.publish(make_event('AMD', SignalDirection.BUY))
assert count == [1, 1], count
print("reentrant publish OK (无死锁), delivered=", n4)

# 无订阅者时应返回 0
bus4 = TradingEventBus(use_stream=False)
assert bus4.publish(make_event('NONE')) == 0
print("no-subscriber OK")

print("ALL PASS")
