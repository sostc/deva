"""守卫：数据源的「空」必须分三种，不许合并成一种。

背景（2026-10-20 实查，三条都是真的在跑的数据源上出现的）：

1. ``realtime_tick_5s`` 收盘后 ``fetch_data`` 返回 ``None``（"今天没有盘中行情"）。
   调度层把 ``None`` 一律当失败 → ``error_count`` 涨到 67、``last_error``
   永远是「fetch_data 返回 None」。**收盘造成的"故障"把真正的抓取失败埋掉了**，
   ``emitted=0`` 看上去像坏了，其实是按设计不取数。

2. ``金十财经快讯`` 的 ``fetch_data`` 是 ``try: ... except: return []``。
   抓 brotli 失败也返回 ``[]``，和「真的这 5 分钟没有快讯」完全相同，
   而旧代码两者都走 ``last_data_ts=now`` + ``record_success()`` ——
   页面显示「刚刚有数据」，实际最近一次成功在半年前（假新鲜）。

3. ``OpenRouter_TOKEN_消耗`` 取数失败返回 ``{"success": False, ...}``，
   旧代码只看 ``data is not None``，把「失败通知」当正常产出 emit 出去。

所以本守卫钉的不是「代码里有没有那一行」，而是**状态字段有没有被写坏**：

· ``{"skipped": ...}`` → 只写 ``last_skip_*``，``error_count`` / ``last_data_ts``
  / ``total_emitted`` 一个都不许动，也**不许 emit**；
· ``[]`` → 允许刷新 ``last_data_ts``（真的跑完了），但**不许 emit**、
  不许记 error、不许加 ``total_emitted``；
· ``{"success": False}`` / ``None`` → 记 error，不许刷新 ``last_data_ts``、
  不许 emit、不许加 ``total_emitted``。
"""

from __future__ import annotations

import argparse
import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DS_ENTRY = ROOT / "deva/naja/datasource/entry.py"
DS_MODELS = ROOT / "deva/naja/datasource/models.py"
PERF = ROOT / "deva/naja/infra/observability/performance_monitor.py"


class _FakeSelf:
    """把 DataSourceEntry 的实例依赖全部替换成可观测的替身。

    ❗替身必须跟产品 API 同构：``id`` / ``name`` / ``_state`` / ``_log`` /
    ``save`` / ``_emit_data`` 一个都不能少，少一个就会在 finally 里被
    ``except: pass`` 吞掉，守卫变全绿但什么都没测。
    """

    def __init__(self, state):
        self.id = "fake_ds"
        self.name = "fake_ds"
        self._state = state
        self._latest_data = None
        self._first_tick_logged = False
        self._skip_reason_logged = ""
        self.saved = 0
        self.emit_calls = 0
        self.emitted = []
        self.logs = []

    # —— 产品 API 替身 ——
    def _log(self, level, msg, **kw):
        self.logs.append((level, msg, kw))

    def save(self):
        self.saved += 1

    def _emit_data(self, data, is_batch=False):
        self.emit_calls += 1
        self.emitted.append(data)

    def _invoke_fetch_func(self, func, event_payload=None):
        return func()


def _patch_perf():
    """性能监控不许在守卫里写盘 / 打点。"""
    try:
        mod = importlib.import_module("deva.naja.infra.observability.performance_monitor")
        mod.record_component_execution = lambda **kw: None
        return True
    except Exception:
        return False


def _reload():
    for mod in ("deva.naja.datasource.models", "deva.naja.datasource.entry"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    _patch_perf()


def _run_case(func_impl):
    from deva.naja.datasource.entry import DataSourceEntry
    from deva.naja.datasource.models import DataSourceState

    state = DataSourceState()
    fake = _FakeSelf(state)
    DataSourceEntry._execute_scheduled_fetch(fake, func_impl)
    return state, fake


def _all_checks() -> list:
    fails = []
    _patch_perf()

    def case(impl):
        return _run_case(impl)

    # ── 1. {"skipped": ...} 只写 last_skip_*，别的字段一个都不许动 ──────
    try:
        st, fake = case(lambda: {"skipped": "收盘", "reason": "收盘"})
        if st.last_skip_reason != "收盘":
            fails.append(f"跳过原因没落盘：last_skip_reason={st.last_skip_reason!r}")
        if st.last_skip_ts <= 0:
            fails.append("跳过没记 last_skip_ts —— 页面上看不出「在跑但没取数」")
        if st.error_count != 0:
            fails.append(
                f"「按设计跳过」被记成了 {st.error_count} 次故障 "
                "（realtime_tick_5s 的 67 次 error 全是这么来的）"
            )
        if st.last_data_ts != 0:
            fails.append(
                "跳过刷新了 last_data_ts —— 页面会显示「刚刚有数据」，"
                "而一条都没采到（假新鲜）"
            )
        if st.total_emitted != 0:
            fails.append(f"跳过把 total_emitted 加了 {st.total_emitted}")
        if fake.emit_calls != 0:
            fails.append(f"跳过载荷被当成数据 emit 了 {fake.emit_calls} 次")
    except Exception as e:  # noqa: BLE001
        fails.append(f"跳过语义无法验证：{type(e).__name__}: {e}")

    # ── 2. [] 是真跑完了但没内容：可刷 last_data_ts，不许 emit ──────────
    try:
        st, fake = case(lambda: [])
        if st.error_count != 0:
            fails.append(f"空列表被记成了 {st.error_count} 次故障")
        if fake.emit_calls != 0:
            fails.append(f"空列表被 emit 了 {fake.emit_calls} 次（下游会收到 []）")
        if st.total_emitted != 0:
            fails.append(f"空列表把 total_emitted 加了 {st.total_emitted}")
        if st.last_data_ts <= 0:
            fails.append("空列表没刷新 last_data_ts —— 「跑完了但没内容」也是有效信息")
    except Exception as e:  # noqa: BLE001
        fails.append(f"空列表语义无法验证：{type(e).__name__}: {e}")

    # ── 3. {"success": False} 是失败：记 error，不许刷 last_data_ts ─────
    try:
        st, fake = case(lambda: {"success": False, "error": "boom"})
        if st.error_count != 1:
            fails.append(f"失败通知没记 error（error_count={st.error_count}）")
        if "boom" not in st.last_error:
            fails.append(f"失败原因丢了：last_error={st.last_error!r}")
        if st.last_data_ts != 0:
            fails.append("失败通知刷新了 last_data_ts（假新鲜）")
        if fake.emit_calls != 0:
            fails.append(f"失败通知被 emit 了 {fake.emit_calls} 次")
    except Exception as e:  # noqa: BLE001
        fails.append(f"失败语义无法验证：{type(e).__name__}: {e}")

    # ── 4. None 是"没说明原因的空"，只能按失败计，但话要说清 ────────────
    try:
        st, fake = case(lambda: None)
        if st.error_count != 1:
            fails.append(f"None 没记 error（error_count={st.error_count}）")
        if st.last_data_ts != 0:
            fails.append("None 刷新了 last_data_ts")
        if fake.emit_calls != 0:
            fails.append(f"None 被 emit 了 {fake.emit_calls} 次")
        if "skipped" not in st.last_error:
            fails.append(
                "None 的错误信息没给出正确写法提示"
                "（应在 last_error 里告诉调用方用 {'skipped': 原因}）"
            )
    except Exception as e:  # noqa: BLE001
        fails.append(f"None 语义无法验证：{type(e).__name__}: {e}")

    # ── 5. 正常数据要清掉上一条跳过原因 ──────────────────────────────────
    try:
        from deva.naja.datasource.entry import DataSourceEntry
        from deva.naja.datasource.models import DataSourceState

        st = DataSourceState()
        fake = _FakeSelf(st)
        DataSourceEntry._execute_scheduled_fetch(fake, lambda: {"skipped": "收盘"})
        DataSourceEntry._execute_scheduled_fetch(
            fake, lambda: [{"code": "sh600000"}, {"code": "sz000001"}]
        )
        if st.last_skip_reason:
            fails.append(
                f"取到数据后 last_skip_reason 还是 {st.last_skip_reason!r} —— "
                "页面会挂着「非交易时段」而 last_data_ts 是新的"
            )
        if st.total_emitted != 2:
            fails.append(f"两条数据只记了 {st.total_emitted} 条产出")
        if st.error_count != 0:
            fails.append(f"正常数据路径记了 {st.error_count} 次 error")
    except Exception as e:  # noqa: BLE001
        fails.append(f"跳过→数据的清理无法验证：{type(e).__name__}: {e}")

    # ── 6. 状态字段必须能存进 NB（to_dict/from_dict 漏字段＝重启即丢）───
    try:
        from deva.naja.datasource.models import DataSourceState

        st = DataSourceState(last_skip_ts=123.0, last_skip_reason="收盘")
        d = st.to_dict()
        back = DataSourceState.from_dict(d)
        if back.last_skip_ts != 123.0 or back.last_skip_reason != "收盘":
            fails.append("DataSourceState 的 last_skip_* 没进 to_dict/from_dict，重启就丢")
    except Exception as e:  # noqa: BLE001
        fails.append(f"last_skip_* 持久化无法验证：{type(e).__name__}: {e}")

    return fails


INJECTIONS = [
    {
        "name": "跳过分支被短路（if False）→ 跳过载荷被当成数据 emit",
        "path": DS_ENTRY,
        "old": '            if isinstance(data, dict) and (data.get("skipped") or data.get("skip")):',
        "new": "            if False and isinstance(data, dict):",
    },
    {
        "name": "跳过改写 last_data_ts（假新鲜）",
        "path": DS_ENTRY,
        "old": "                self._state.last_skip_ts = time.time()",
        "new": "                self._state.last_data_ts = time.time()",
    },
    {
        "name": "空列表不再单独留痕（和「抓到 N 条」同路）",
        "path": DS_ENTRY,
        "old": "                if isinstance(data, list) and not data:",
        "new": "                if isinstance(data, list) and not data and False:",
    },
    {
        "name": "last_skip_* 不落 NB",
        "path": DS_MODELS,
        "old": '            "last_skip_reason": self.last_skip_reason,',
        "new": "",
    },
]


def run_injections() -> int:
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
            _reload()
            fails = _all_checks()
        finally:
            path.write_text(original, encoding="utf-8")
            _reload()

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
    total = 6
    if failures:
        print(f"❌ {len(failures)}/{total} 项失败：数据源空语义守卫")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0

    print("✅ 数据源空语义守卫全绿"
          "（跳过≠失败≠空列表：last_skip_* 独立留痕 · 空列表不 emit · 失败不刷 last_data_ts）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
