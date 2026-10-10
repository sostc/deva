import os
import sys
import time
import tempfile

_tmp = tempfile.mkdtemp(prefix="naja_persist_test_")
os.environ["DEVA_DB_PATH"] = os.path.join(_tmp, "nb.sqlite")
sys.path.insert(0, "/Users/spark/pycharmproject/deva")

from deva.naja.cognition.narrative.tracker import NarrativeTracker

t = NarrativeTracker()
print("persist_interval =", t._persist_interval)

# spy 记录 save_state 调用次数
calls = {"n": 0}
def spy():
    calls["n"] += 1
    return True
t.save_state = spy

# 1) 距上次落库很久 → 应触发 save_state
t._last_persist_ts = time.time() - 100
t._pending_persist = False
assert t._maybe_save_state() is True
assert calls["n"] == 1, calls
print("case1 立即落库 OK")

# 2) 刚落过库 → 应跳过，只打脏标记
t._last_persist_ts = time.time()
t._pending_persist = False
assert t._maybe_save_state() is False
assert calls["n"] == 1, calls
assert t._pending_persist is True
print("case2 节流跳过 + 脏标记 OK")

# 3) 间隔过后再次触发
t._last_persist_ts = time.time() - (t._persist_interval + 1)
assert t._maybe_save_state() is True
assert calls["n"] == 2, calls
print("case3 间隔后再次落库 OK")

# 4) 真实 save_state 会重置时间戳与脏标记
t.save_state = real = NarrativeTracker.save_state.__get__(t, NarrativeTracker)
t._pending_persist = True
t._last_persist_ts = 0.0
assert t.save_state() is True
assert t._pending_persist is False
assert abs(t._last_persist_ts - time.time()) < 2
print("case4 save_state 重置时间戳/脏标记 OK")

print("ALL PASS")
