"""验证 bandit/signal_listener.py 去重表淘汰去掉全量排序后行为一致。

对照实现：旧版 `sorted(items, key=ts)` 后取最新一半（逐字复刻）。
跑法：
    env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        TMPDIR="$TMPDIR" python3.13 scripts/verify/verify_signal_dedup_eviction.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from deva.naja.bandit.signal_listener import SignalListener  # noqa: E402


class OldDedup:
    """旧实现：超限即 sorted 全量排序，取最新一半。"""

    def __init__(self, max_processed):
        self.seen = {}
        self.max_processed = max_processed

    def mark(self, sid, ts):
        self.seen[sid] = ts
        if len(self.seen) > self.max_processed:
            sorted_items = sorted(self.seen.items(), key=lambda x: x[1])
            self.seen = dict(sorted_items[-self.max_processed // 2:])


def new_listener(max_processed):
    lst = SignalListener.__new__(SignalListener)
    lst._processed_signals = {}
    lst._max_processed = max_processed
    return lst


def main():
    # ── 1) 逐条对照：整个插入序列上旧/新保留集合始终一致 ──────────────
    for maxp in (1, 2, 3, 10, 1000, 999):
        new = new_listener(maxp)
        old = OldDedup(maxp)
        for i in range(maxp * 3 + 7):
            sid, ts = f"s{i}", float(i)
            new._mark_processed(sid, ts)
            old.mark(sid, ts)
            assert set(new._processed_signals) == set(old.seen), \
                f"max={maxp} @i={i}: new={sorted(new._processed_signals)} old={sorted(old.seen)}"
        assert len(new._processed_signals) <= maxp
    print("1) 淘汰语义与旧实现逐条一致 OK（6 组上限）")

    # ── 2) 淘汰后 _is_processed 行为正确 ──────────────────────────
    lst = new_listener(10)
    for i in range(11):
        lst._mark_processed(f"s{i}", float(i))
    assert len(lst._processed_signals) == 5, len(lst._processed_signals)
    assert set(lst._processed_signals) == {f"s{i}" for i in range(6, 11)}
    assert all(lst._is_processed(f"s{i}") for i in range(6, 11))
    assert not any(lst._is_processed(f"s{i}") for i in range(0, 6))
    print("2) 淘汰后保留最新一半、旧 id 判定未处理 OK")

    # ── 3) 重复标记同一 id 不增长、不误删 ─────────────────────────
    lst = new_listener(4)
    for _ in range(50):
        lst._mark_processed("dup", 1.0)
    assert set(lst._processed_signals) == {"dup"}, lst._processed_signals
    print("3) 重复 id 不增长 OK")

    # ── 4) 性能：大量淘汰下的吞吐 ────────────────────────────────
    lst = new_listener(1000)
    N = 200_000
    t = time.perf_counter()
    for i in range(N):
        lst._mark_processed(f"sig{i}", float(i))
    dt = time.perf_counter() - t
    assert len(lst._processed_signals) <= 1000
    print(f"4) {N} 次标记耗时 = {dt:.4f}s（{N / dt:,.0f} 次/秒）")

    print("\nALL PASS")


if __name__ == "__main__":
    main()
