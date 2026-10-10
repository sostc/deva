"""验证 state/system/system_state.py 的任务记录落盘节流。

用 `__new__` 构造 + 桩替换 `_save_unsafe`，不触碰真实 state.json。
跑法：
    env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        TMPDIR="$TMPDIR" python3.13 scripts/verify/verify_system_state_throttle.py
"""
import os
import sys
import threading
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from deva.naja.state.system.system_state import (  # noqa: E402
    BATCH_WRITE_INTERVAL,
    SystemStateManager,
)


def make_state():
    st = SystemStateManager.__new__(SystemStateManager)
    st._state = {
        "version": "1.0",
        "last_active_time": None,
        "last_wake_time": None,
        "system_uptime_start": datetime.now().isoformat(),
        "task_execution_records": {},
        "created_at": datetime.now().isoformat(),
    }
    st._lock = threading.RLock()
    st._dirty = False
    st._last_save_time = time.time()
    st._save_thread = None
    st._stop_event = threading.Event()
    st._save_calls = 0

    def _stub_save_unsafe():
        st._save_calls += 1
        st._last_save_time = time.time()  # 模拟真实落盘会刷新时间戳

    st._save_unsafe = _stub_save_unsafe
    return st


def main():
    now = datetime.now()

    # ── 1) 间隔内连续记录：不落盘，仅置脏 ──────────────────────────
    st = make_state()
    for i in range(5):
        st.record_task_execution(f"task_{i}", now, "success")
    assert st._save_calls == 0, st._save_calls
    assert st._dirty is True
    assert len(st._state["task_execution_records"]) == 5
    print("1) 60s 内 5 次记录 → 落盘 0 次、内存已更新 OK")

    # ── 2) 距上次落盘超过间隔：写一次 ────────────────────────────
    st._last_save_time = time.time() - (BATCH_WRITE_INTERVAL + 1)
    st.record_task_execution("task_x", now, "success")
    assert st._save_calls == 1, st._save_calls
    assert st._dirty is False
    print("2) 超过 BATCH_WRITE_INTERVAL → 同步落盘 1 次并清脏 OK")

    # ── 3) 落盘后立即再记：又回到不落盘 ──────────────────────────
    st.record_task_execution("task_y", now, "success")
    assert st._save_calls == 1, st._save_calls
    assert st._dirty is True
    print("3) 落盘后紧接记录 → 不再落盘 OK")

    # ── 4) 内存查询可用（were-task-executed-today 读内存） ────────
    st2 = make_state()
    st2.record_task_execution("daily_job", now, "success")
    assert st2.was_task_executed_today("daily_job") is True
    assert st2.was_task_executed_today("never_ran") is False
    print("4) 记录后可即时查询执行状态 OK")

    # ── 5) 每任务记录保留上限 100 条 ─────────────────────────────
    st3 = make_state()
    for i in range(150):
        st3.record_task_execution("many", now)
    recs = st3._state["task_execution_records"]["many"]
    assert len(recs) == 100, len(recs)
    print("5) 单任务记录裁剪至 100 条 OK")

    # ── 6) shutdown 时脏状态兜底落盘 ─────────────────────────────
    st4 = make_state()
    st4.record_task_execution("t", now)
    assert st4._save_calls == 0 and st4._dirty is True
    st4.shutdown()
    assert st4._save_calls == 1, st4._save_calls
    print("6) shutdown() 兜底落盘 OK")

    # ── 7) 对比：旧的「每次立即写」成本 ──────────────────────────
    N = 2000
    st5 = make_state()
    t = time.perf_counter()
    for i in range(N):
        st5.record_task_execution(f"job_{i % 20}", now)
    dt = time.perf_counter() - t
    assert st5._save_calls <= N / BATCH_WRITE_INTERVAL + 2, st5._save_calls
    print(f"7) {N} 次记录 → 实落盘 {st5._save_calls} 次（旧实现为 {N} 次），"
          f"耗时 {dt:.4f}s")

    print("\nALL PASS")


if __name__ == "__main__":
    main()
