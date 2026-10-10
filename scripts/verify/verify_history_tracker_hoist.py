#!/usr/bin/env python3
"""回归验证：history_tracker._detect_changes 的 O(板块×个股) → O(板块+个股)。

原实现把「个股变化 + 排序 + 取前3」放在 block 循环内部，而这段逻辑
**只依赖 symbol_weights，与 block 无关** → 每个 block 都全量重扫一遍所有个股。
本脚本同时验证：
  1. 结果语义不变（每个 block 事件的 top_symbols 与独立参考实现一致）
  2. 个股变化确实只算了一次（get_symbol_name 调用次数 == Q + G，而非 Q*B + G）

跑法：
    env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        TMPDIR="$TMPDIR" python3.13 scripts/verify/verify_history_tracker_hoist.py
"""

import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 预先导入 bandit：仓库存在既有循环导入
#   market_hotspot.data.global_market_futures → bandit.runner → radar.global_market_scanner
#    → market_hotspot.data.global_market_futures
# 生产启动顺序里 bandit 先于 market_hotspot，所以能正常启动；这里保持同样顺序。
import deva.naja.bandit  # noqa: F401

from deva.naja.market_hotspot.tracking.history_tracker import (
    MarketHotspotHistoryTracker, HotspotSnapshot,
)

random.seed(20261010)

N_BLOCKS = 20
N_SYMBOLS = 200

tracker = MarketHotspotHistoryTracker()
tracker.block_names = {f"B{i}": f"板块{i}" for i in range(N_BLOCKS)}
tracker.symbol_names = {f"S{i}": f"名称{i}" for i in range(N_SYMBOLS)}
tracker._emit_hotspot_event = lambda **kw: None  # 屏蔽事件推送副作用

old_bw = {f"B{i}": round(random.uniform(1.0, 9.0), 3) for i in range(N_BLOCKS)}
new_bw = {f"B{i}": round(random.uniform(0.0, 9.0), 3) for i in range(N_BLOCKS)}

old_sw = {f"S{i}": round(random.uniform(1.0, 9.0), 4) for i in range(N_SYMBOLS)}
new_sw = {}
for i in range(N_SYMBOLS):
    # 制造幅度各异的变化（高精度，避免排序出现并列）
    new_sw[f"S{i}"] = max(0.0, round(old_sw[f"S{i}"] * (1 + random.uniform(-0.9, 2.0)), 5))

old = HotspotSnapshot(timestamp=0.0, global_hotspot=0.5,
                      block_weights=old_bw, symbol_weights=old_sw, market="CN")
new = HotspotSnapshot(timestamp=1.0, global_hotspot=0.6,
                      block_weights=new_bw, symbol_weights=new_sw, market="CN")


# ── 独立参考实现（照抄「原始」循环内逻辑，用于比对） ──────────────────
def reference_top_symbols():
    changes = []
    for symbol in set(old_sw.keys()) | set(new_sw.keys()):
        s_old, s_new = old_sw.get(symbol, 0), new_sw.get(symbol, 0)
        if s_old > 0:
            pct = (s_new - s_old) / s_old * 100
            if abs(pct) > 5:
                changes.append({'symbol': symbol, 'name': f"名称{symbol[1:]}",
                                'old': s_old, 'new': s_new, 'change_pct': pct})
    changes.sort(key=lambda x: abs(x['change_pct']), reverse=True)
    return changes[:3]


expected_top = reference_top_symbols()
qualifying = len([
    s for s in set(old_sw) | set(new_sw)
    if old_sw.get(s, 0) > 0 and abs((new_sw.get(s, 0) - old_sw.get(s, 0)) / old_sw[s] * 100) > 5
])
significant = len([
    s for s in set(old_sw) | set(new_sw)
    if old_sw.get(s, 0) > 2.0 or new_sw.get(s, 0) > 2.0
])
assert expected_top, "参考实现没算出个股变化，测试数据无效"

# ── 计数 get_symbol_name 调用 ────────────────────────────────────────
calls = {"n": 0}
_orig_get_symbol_name = tracker.get_symbol_name


def _counting_get_symbol_name(symbol):
    calls["n"] += 1
    return _orig_get_symbol_name(symbol)


tracker.get_symbol_name = _counting_get_symbol_name

tracker._detect_changes(old, new, "2026-10-10 10:00:00")

# ── 1) 语义不变：所有 block 事件的 top_symbols == 参考实现 ────────────
events = (list(tracker.block_hotspot_events_low)
          + list(tracker.block_hotspot_events_medium)
          + list(tracker.block_hotspot_events_high))
assert events, "没有产生任何 block 事件"
for ev in events:
    assert ev.top_symbols == expected_top, (ev.block_id, ev.top_symbols, expected_top)
print(f"1) 语义不变 OK：{len(events)} 个事件 top_symbols 全部与参考实现一致")

# ── 2) 复杂度：个股变化只算了一次 ────────────────────────────────────
assert calls["n"] == qualifying + significant, (calls["n"], qualifying, significant)
print(f"2) 复杂度 OK：get_symbol_name 调用 {calls['n']} 次 "
      f"(= Q {qualifying} + G {significant})，"
      f"原实现为 Q×B + G = {qualifying * N_BLOCKS + significant} 次")

# ── 3) 事件之间不共享可变列表（浅拷贝隔离） ──────────────────────────
if len(events) >= 2:
    assert events[0].top_symbols is not events[1].top_symbols, "事件共享了同一个 list"
print("3) 事件列表隔离 OK")

print("ALL PASS")
