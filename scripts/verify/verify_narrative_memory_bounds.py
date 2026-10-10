#!/usr/bin/env python3
"""回归验证：NarrativeTracker 长跑内存上界。

修复点：
    1. ``_value_signals`` 原先只 append 从不裁剪（消费方只用最近 72h）
       → 新增 ``_prune_value_signals`` + 阈值化摊还调用，并同步重建 ``_value_signal_index``
    2. ``_graph_edges`` 边权重长期只增不减 → 超过 ``_graph_max_edges`` 时按权重保留最高的半数
    3. ``_recent_hits`` 补 ``maxlen`` 兜底（已有按时间窗 popleft 裁剪）

跑法：
    env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        TMPDIR="$TMPDIR" python3.13 scripts/verify/verify_narrative_memory_bounds.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from deva.naja.cognition.narrative.tracker import NarrativeTracker, ValueSignal

now = time.time()


def make_signal(ts, stype="token供需"):
    return ValueSignal(timestamp=ts, signal_type=stype, keywords=["供给"],
                       severity="轻微", source_event="x")


# ── 1) _prune_value_signals 删掉过期信号并重建索引 ────────────────────
t = NarrativeTracker()
t._value_signal_retention_seconds = 3600.0

for i in range(150):
    ts = now - 3 * 3600 if i < 50 else (now - 10 if i < 120 else now - 5)
    t._value_signals.append(make_signal(ts))

# 索引故意建成"过期信号也计入"的状态，验证裁剪后会重建
t._value_signal_index = {"token供需": list(range(len(t._value_signals)))}

dropped = t._prune_value_signals(now)
assert dropped == 50, dropped
assert len(t._value_signals) == 100, len(t._value_signals)
assert all(s.timestamp >= now - 3600 for s in t._value_signals)
print(f"1) 过期信号裁剪 OK：删除 {dropped} 条，剩余 {len(t._value_signals)} 条")

# ── 2) 索引与列表保持一致 ────────────────────────────────────────────
assert set(t._value_signal_index) == {"token供需"}, t._value_signal_index
idxs = t._value_signal_index["token供需"]
assert len(idxs) == len(t._value_signals), (len(idxs), len(t._value_signals))
assert idxs == list(range(len(t._value_signals))), idxs[:5]
for i in idxs:
    assert t._value_signals[i].signal_type == "token供需"
print("2) _value_signal_index 重建一致 OK")

# ── 3) 无过期信号时不误删（返回 0，列表不变） ────────────────────────
before = len(t._value_signals)
assert t._prune_value_signals(now) == 0
assert len(t._value_signals) == before
print("3) 无过期信号时不误删 OK")

# ── 4) 阈值化摊还调用点存在（避免每条 append 都全量扫） ──────────────
import inspect
src = inspect.getsource(NarrativeTracker._process_value_signals)
assert "_prune_value_signals" in src and "_value_signal_prune_at" in src
assert "_value_signal_prune_at" in inspect.getsource(NarrativeTracker.__init__)
print("4) 阈值化摊还裁剪已接入 OK")

# ── 5) _recent_hits 有 maxlen 兜底 ───────────────────────────────────
t2 = NarrativeTracker()
assert t2._recent_hits.maxlen == 50000, t2._recent_hits.maxlen
print("5) _recent_hits maxlen =", t2._recent_hits.maxlen, "OK")

# ── 6) _graph_edges 超上限时按权重裁剪 ───────────────────────────────
t3 = NarrativeTracker()
t3._graph_max_edges = 100
for i in range(300):
    t3._graph_edges[(f"n{i}", f"m{i}")] = (i + 1) * 0.5   # 权重各不相同
t3._update_graph(now, ["A", "B"])
assert len(t3._graph_edges) <= 100, len(t3._graph_edges)
# 保留的是权重更高的那一半
assert ("n299", "m299") in t3._graph_edges, "高权重边被误删"
assert ("n0", "m0") not in t3._graph_edges, "低权重边未被裁掉"
print(f"6) _graph_edges 裁剪 OK：300 → {len(t3._graph_edges)} 条，保留高权重")

# ── 7) 图更新与时间窗裁剪仍正常（window 默认 6h，用 30h 前的时间戳） ──
t4 = NarrativeTracker()
t4._update_graph(now - 30 * 3600, ["X", "Y"])   # 产生边 + 一条过期 hit
t4._update_graph(now, ["Y", "Z"])               # 过期 hit 被裁掉
assert len(t4._recent_hits) == 1, len(t4._recent_hits)
assert len(t4._graph_edges) >= 1, dict(t4._graph_edges)
print("7) 时间窗裁剪与图更新正常 OK")

print("ALL PASS")
