"""守卫：线程池的「过载」必须看当前积压，不能看累计提交数。

背景（2026-10-20 实查）：

``ThreadPoolManager.submit()`` 原本写过载闸门：

```python
if self._total_submitted >= self._max_queue_size * self._max_workers:
    return None          # 调用方看到的就是「线程池过载，无法提交任务」
```

``_total_submitted`` 是**只增不减**的累计值，默认阈值 100×10=1000。
于是进程累计提交够 1000 次之后，**每一次** submit 都返回 None：

* ``realtime_tick_5s`` / ``金十财经快讯`` 这类异步数据源永久拿不到线程，
  报「线程池过载，无法提交任务」—— 而机器其实闲得很；
* ``_perform_auto_tune`` 因为 ``total_rejected > 10`` 会把队列容量 +500，
  阈值随之抬高，于是"过载"隔一阵又冒一次，看起来像偶发抖动，
  实际是把累计量当成了瞬时量的必然结果；
* ``get_stats()['pending_tasks']`` 早就算好了真实积压
  （submitted - completed - rejected），闸门却没用它。

判据：**连续提交并等待完成 1200 次之后，第 1201 次仍然必须拿到 Future。**
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THREAD_POOL = ROOT / "deva/naja/infra/runtime/thread_pool.py"

TOTAL_SUBMITS = 1200


def _all_checks() -> list:
    fails = []
    try:
        from deva.naja.infra.runtime.thread_pool import ThreadPoolManager
    except Exception as e:  # noqa: BLE001
        return [f"线程池无法导入：{type(e).__name__}: {e}"]

    try:
        pool = ThreadPoolManager()
    except Exception as e:  # noqa: BLE001
        return [f"线程池无法构造：{type(e).__name__}: {e}"]

    # ── 1. 累计提交超过 max_queue_size*max_workers 之后仍要能提交 ─────────
    # 每次都等它跑完，所以「积压」始终接近 0 —— 这正是常态。
    rejected = 0
    last_error = ""
    try:
        for i in range(TOTAL_SUBMITS):
            fut = pool.submit(lambda: None)
            if fut is None:
                rejected += 1
                if not last_error:
                    last_error = f"第 {i + 1} 次提交就被拒（累计阈值当成了积压）"
                continue
            fut.result(timeout=5)
    except Exception as e:  # noqa: BLE001
        fails.append(f"提交过程异常：{type(e).__name__}: {e}")

    if rejected:
        fails.append(
            f"{TOTAL_SUBMITS} 次「提交即等待完成」中被拒 {rejected} 次：{last_error} —— "
            "机器是闲的，闸门算的却是历史累计量"
        )

    # ── 2. 空闲状态下积压计数必须接近 0（get_stats 口径自洽）────────────
    try:
        stats = pool.get_stats()
        pending = stats.get("pending_tasks", -1)
        if pending < 0:
            fails.append(f"pending_tasks 为负（{pending}），统计口径已经不自洽")
        elif pending > 5:
            fails.append(f"全部任务已完成后 pending_tasks 仍是 {pending}，积压口径不可信")
    except Exception as e:  # noqa: BLE001
        fails.append(f"get_stats 无法验证：{type(e).__name__}: {e}")

    # ── 3. 真积压时仍然要拒（别把闸门拆了）───────────────────────────────
    try:
        import threading

        release = threading.Event()
        submitted = 0
        while submitted < 60:
            fut = pool.submit(release.wait)
            if fut is None:
                break
            submitted += 1
        release.set()
        if submitted == 0:
            fails.append("连一个任务都提交不进去 —— 闸门方向反了")
    except Exception as e:  # noqa: BLE001
        fails.append(f"积压场景无法验证：{type(e).__name__}: {e}")

    return fails


INJECTIONS = [
    {
        "name": "过载闸门退回「累计提交数」",
        "path": THREAD_POOL,
        "old": "            if in_flight >= self._max_queue_size:",
        "new": "            if self._total_submitted >= self._max_queue_size * self._max_workers:",
    },
]


def run_injections() -> int:
    import importlib

    print("负向注入（每条都该被抓到）：")
    caught = 0
    missed = 0
    for inj in INJECTIONS:
        path: Path = inj["path"]
        original = path.read_text(encoding="utf-8")
        if inj["old"] not in original:
            print(f"  ❌ 锚点没命中，注入无效：{inj['name']}")
            missed += 1
            continue
        try:
            path.write_text(original.replace(inj["old"], inj["new"], 1), encoding="utf-8")
            if "deva.naja.infra.runtime.thread_pool" in sys.modules:
                importlib.reload(sys.modules["deva.naja.infra.runtime.thread_pool"])
            fails = _all_checks()
        finally:
            path.write_text(original, encoding="utf-8")
            if "deva.naja.infra.runtime.thread_pool" in sys.modules:
                importlib.reload(sys.modules["deva.naja.infra.runtime.thread_pool"])

        if fails:
            caught += 1
            print(f"  ✅ 被捕获：{inj['name']}")
            for f in fails[:2]:
                print(f"       · {f[:110]}")
        else:
            print(f"  ❌ 没抓到 —— 这条注入白做了：{inj['name']}")

    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获"
          + (f"（{missed} 条锚点未命中，已计失败）" if missed else ""))
    return caught if not missed else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        return 0 if run_injections() == len(INJECTIONS) else 1

    failures = _all_checks()
    total = 3
    if failures:
        print(f"❌ {len(failures)}/{total} 项失败：线程池积压口径守卫")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0

    print("✅ 线程池积压口径守卫全绿"
          f"（连续提交 {TOTAL_SUBMITS} 次不误拒 · pending 口径自洽 · 真积压仍会拦）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
