#!/usr/bin/env python3
"""回归：tasks/manager.py 补作业改为后台串行执行（不再阻塞启动）。

验证：
  1) _dispatch_catchup_tasks 提交后立即返回（不阻塞）；
  2) 后台确实执行了任务；
  3) 多个任务按提交顺序**串行**执行（保序）；
  4) 单个任务抛异常不影响后续任务。

跑法（必须清环境）：
    env -i HOME="$HOME" USER="$USER" PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        TMPDIR="$TMPDIR" python3.13 scripts/verify/verify_task_catchup_async.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from deva.naja.tasks.manager import TaskManager  # noqa: E402


class FakeEntry:
    def __init__(self, i=0, delay=0.0, recorder=None, boom=False):
        self.id = f"fake{i}"
        self.name = f"fake{i}"
        self.i = i
        self.delay = delay
        self.recorder = recorder
        self.boom = boom
        self.ran = 0

    def run_once(self):
        if self.boom:
            raise RuntimeError("boom")
        time.sleep(self.delay)
        self.ran += 1
        if self.recorder is not None:
            self.recorder.append(self.i)


def main():
    m = TaskManager()

    # 1) 非阻塞提交
    e = FakeEntry(0, delay=0.4)
    t = time.perf_counter()
    m._dispatch_catchup_tasks([e])
    elapsed = time.perf_counter() - t
    assert elapsed < 0.1, f"提交耗时 {elapsed:.4f}s，仍阻塞"
    print(f"1) 提交立即返回 OK（{elapsed * 1000:.1f}ms）")

    # 2) 后台确实执行
    time.sleep(0.8)
    assert e.ran == 1, e.ran
    print("2) 后台确实执行 OK")

    # 3) 串行保序（即使后面的任务更快，也必须按提交顺序完成）
    order = []
    batch = [FakeEntry(0, 0.20, order), FakeEntry(1, 0.02, order), FakeEntry(2, 0.02, order)]
    m._dispatch_catchup_tasks(batch)
    time.sleep(0.8)
    assert order == [0, 1, 2], order
    print(f"3) 串行保序 OK {order}")

    # 4) 单条异常不影响后续
    after = []
    m._dispatch_catchup_tasks([FakeEntry(9, boom=True), FakeEntry(10, 0.0, after)])
    time.sleep(0.4)
    assert after == [10], after
    print("4) 单条异常不影响后续 OK")

    print("\nALL PASS")


if __name__ == "__main__":
    main()
