from deva import Stream, timer, Deva, log, warn, NB
import random
import time

# 命名存储：信号表（时间键模式）
signals = NB('signals', key_mode='time')

# 模拟实时信号流
source = Stream()


def make_signal():
    price = round(10 + random.uniform(-0.8, 0.8), 3)
    score = round(random.uniform(0, 1), 3)
    side = "BUY" if score > 0.7 else "HOLD" if score > 0.4 else "SELL"
    return {
        "ts": time.time(),
        "symbol": "600519.SH",
        "price": price,
        "score": score,
        "side": side,
    }


# 每秒产出一条信号
timer(interval=1, start=True, func=make_signal) >> source

# 写入存储（事件模式，append 到时间键）
source.sink(signals.append)

# 实时观察
source.map(lambda x: f"RT {x['symbol']} {x['side']} score={x['score']} price={x['price']}") >> log

# 异常信号告警
source.filter(lambda x: x["score"] > 0.9).map(lambda x: f"ALERT high score: {x}") >> warn


# 10秒后回放最近8秒数据（2倍速）
def replay_recent():
    end_ts = time.time()
    start_ts = end_ts - 8
    start_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_ts))
    end_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_ts))
    f"Replaying from {start_iso} to {end_iso}" >> log
    # interval=0.5 表示回放更快
    signals.replay(start=start_iso, end=end_iso, interval=0.5)


timer(interval=10, start=True, func=replay_recent)

Deva.run()
