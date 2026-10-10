#!/usr/bin/env python3
"""回归验证：4 处零散 bug 修复。

覆盖：
    1. tracker.py        同名 detect_value_signals 重复定义（后者覆盖前者）→ 删除死副本
    2. tracker.py        关键词元组里 "block" 重复
    3. signal_listener.py 行情提取 key ' Price'（前导空格）永不匹配 → 'Price'
    4. kernel.py         self._unified_manas 未在 __init__ 声明 → AttributeError

跑法：
    env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        TMPDIR="$TMPDIR" python3.13 scripts/verify/verify_misc_bugfixes.py
"""

import sys
import os
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from deva.naja.cognition.narrative.tracker import NarrativeTracker

# ── 1) detect_value_signals 只剩一个定义，且可正常调用 ─────────────────
src = inspect.getsource(NarrativeTracker)
assert src.count("def detect_value_signals") == 1, src.count("def detect_value_signals")
tracker = NarrativeTracker()
out = tracker.detect_value_signals({"title": "铜矿供应严重短缺，库存告急"})
assert isinstance(out, dict)
print("1) detect_value_signals 去重 OK, 返回类别 =", list(out))

# 向后兼容别名仍指向同一实现
assert tracker.detect_tiandao_signals({"title": "铜矿供应严重短缺"}) == \
    tracker.detect_value_signals({"title": "铜矿供应严重短缺"})
print("1b) 兼容别名 detect_tiandao_signals 一致 OK")

# ── 2) 关键词元组无重复 ───────────────────────────────────────────────
lines = [ln for ln in inspect.getsource(NarrativeTracker).splitlines()
         if '"title", "topic"' in ln]
assert lines, "未找到关键词元组"
assert lines[0].count('"block"') == 1, lines[0]
print("2) 关键词元组去重 OK")

# ── 3) _extract_price 支持 'Price' 键 ────────────────────────────────
import deva.naja.bandit.signal_listener as sl_mod

cls = None
for name, obj in vars(sl_mod).items():
    if inspect.isclass(obj) and "_extract_price" in getattr(obj, "__dict__", {}):
        cls = obj
        break
assert cls is not None, "未找到含 _extract_price 的类"
inst = cls.__new__(cls)
assert cls._extract_price(inst, {"Price": 12.5}) == 12.5
assert cls._extract_price(inst, {"last": 7.0}) == 7.0
assert cls._extract_price(inst, {"nope": 1}) == 0.0
print("3) _extract_price 支持 'Price' OK")

# ── 4) process_with_feedback 不再 AttributeError ─────────────────────
from deva.naja.attention.kernel.kernel import AttentionKernel
assert hasattr(AttentionKernel, "__init__")
init_src = inspect.getsource(AttentionKernel.__init__)
assert "_unified_manas = None" in init_src, "构造未声明 _unified_manas"
# 构造一个最小 kernel 并直接触碰 feedback 分支
try:
    kernel = AttentionKernel(encoder=None, multi_head=None, enable_manas=False)
    kernel.process_with_feedback(Q=None, raw_events=[], feedback={"pnl_pct": 0.01})
except AttributeError as e:
    if "_unified_manas" in str(e):
        raise AssertionError(f"仍存在 _unified_manas AttributeError: {e}")
    print("4) feedback 分支 OK（Q=None 触发其他异常，已排除 _unified_manas）")
except TypeError as e:
    raise AssertionError(f"构造签名变化: {e}")
else:
    print("4) process_with_feedback OK")

print("ALL PASS")
