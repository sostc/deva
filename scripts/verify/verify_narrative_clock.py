"""守卫：叙事追踪的两个时钟不许混用，停更的叙事必须真的衰减。

背景（2026-10-19 实测，不是推测）：

``NarrativeTracker.ingest_event`` 曾把**新闻发布时间**当成"现在"用：

    now_ts = self._get_timestamp(event)      # ← 新闻时间，不是摄入时间
    state.hits.append((now_ts, ...))
    self._prune_hits(state, now_ts)
    metrics = self._compute_metrics(state, now_ts)
    state.last_updated = now_ts

实测新闻时间比摄入时间**滞后 13~176 分钟（中位 ~65）**，且每条叙事滞后量
不同。三条后果：

1. **跨叙事不可比**：6 小时窗口的端点 = 各叙事最后一条新闻的时间，于是"医药"
   的窗口是 15:51~21:51、"流动性紧张"是 16:44~22:44 —— 同一时刻不同叙事的
   recent_count 根本不是同一个窗口算出来的。
2. **停更即定格（假新鲜）**：热度只在 ingest 那一刻算。某叙事此后不再有新文本，
   now_ts 冻结在最后一条新闻时间，recent_count / attention_score / stage 永远
   不变；而读取路径 ``get_summary`` 直接返回这些缓存字段、不重算 —— 页面显示
   「最近更新 3 小时前」，热度条却是 3 小时前的样子。
3. **跨时钟比较**：``get_value_market_summary`` 用 ``time.time() - 72h`` 作
   cutoff，却拿滞后的新闻时间 ``signal.timestamp`` / ``state.last_updated``
   去比 → 系统性漏掉最近一小时的叙事。

修法：**摄入时钟**（``time.time()``）做全部窗口算术与活性判据，**事件时钟**
（新闻发布时间）只落进 ``last_event_ts`` 供展示/滞后观测；读取路径按当前时间
重算派生量。
"""

from __future__ import annotations

import argparse
import ast
import importlib
import sys
import time
from collections import deque
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NAJA = REPO / "deva" / "naja"

TRACKER_PY = NAJA / "cognition" / "narrative" / "tracker.py"
NARRATIVE_UI_PY = NAJA / "cognition" / "ui" / "components" / "narrative_track.py"


def _parse(path: Path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def _func(tree: ast.AST, name: str, cls: str | None = None):
    """找函数/方法。

    ❗``to_dict`` 这种通用名在本文件里有多个类都在用（`NarrativeState`、
    `ValueSignal`...），不限定类会取到第一个 —— 守卫就变成在检查别的东西，
    还全绿。
    """
    if cls is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == cls:
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == name:
                        return sub
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _is_wall_clock(node: ast.AST) -> bool:
    """``time.time()``。"""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "time"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "time"
    )


def _is_event_clock(node: ast.AST) -> bool:
    """``self._get_timestamp(...)`` —— 新闻发布时间。"""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_get_timestamp"
    )


def _assigned_names(fn: ast.AST) -> dict:
    """``{变量名: 'wall' | 'event' | 'other'}`` —— 只认函数体内的普通赋值。"""
    out: dict = {}
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if not isinstance(tgt, ast.Name):
            continue
        if _is_wall_clock(node.value):
            out[tgt.id] = "wall"
        elif _is_event_clock(node.value):
            out[tgt.id] = "event"
    return out


# ── 检查项 ───────────────────────────────────────────────────────────────────

def check_ingest_uses_wall_clock() -> list:
    """窗口算术必须走摄入时钟，新闻时间不许当 now 用。"""
    tree = _parse(TRACKER_PY)
    if tree is None:
        return [f"{_rel(TRACKER_PY)} 解析失败"]
    fn = _func(tree, "ingest_event", cls="NarrativeTracker")
    if fn is None:
        return [f"{_rel(TRACKER_PY)} 找不到 ingest_event —— 守卫锚点腐烂"]

    names = _assigned_names(fn)
    wall = [n for n, k in names.items() if k == "wall"]
    event = [n for n, k in names.items() if k == "event"]
    if not wall:
        return [
            f"{_rel(TRACKER_PY)}:ingest_event 里没有 ``time.time()`` —— "
            f"窗口算术只能认摄入时钟"
        ]
    if not event:
        return [
            f"{_rel(TRACKER_PY)}:ingest_event 里没有取新闻时间 —— "
            f"「这条叙事讲的事发生在什么时候」就没有了"
        ]

    # 传给下游的 now_ts 必须是摄入时钟那个变量
    for node in ast.walk(fn):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("_process_external_narratives", "_process_value_signals")
            and len(node.args) >= 2
        ):
            continue
        arg = node.args[1]
        if not isinstance(arg, ast.Name):
            continue
        if arg.id in event:
            return [
                f"{_rel(TRACKER_PY)}:{node.lineno} {node.func.attr} 收到的 now 是"
                f"``{arg.id}``（新闻时间）—— 窗口端点会随每条叙事的最后一条新闻漂移，"
                f"跨叙事不可比，且停更叙事的热度永不衰减"
            ]
        if arg.id not in wall:
            return [
                f"{_rel(TRACKER_PY)}:{node.lineno} {node.func.attr} 的 now 既不是"
                f"``time.time()`` 也算不上新闻时间（``{arg.id}``），口径不明"
            ]
    return []


def check_state_records_both_clocks() -> list:
    """``state.last_updated`` 是摄入时钟，``state.last_event_ts`` 是新闻时间。"""
    tree = _parse(TRACKER_PY)
    if tree is None:
        return [f"{_rel(TRACKER_PY)} 解析失败"]
    fn = _func(tree, "_process_external_narratives", cls="NarrativeTracker")
    if fn is None:
        return [f"{_rel(TRACKER_PY)} 找不到 _process_external_narratives —— 锚点腐烂"]

    failures: list = []
    seen_updated = False
    seen_event = False
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if not (isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name)):
                continue
            attr = tgt.attr
            rhs = node.value
            rhs_name = rhs.id if isinstance(rhs, ast.Name) else None
            if attr == "last_updated":
                seen_updated = True
                # ❗必须是摄入时钟（参数 now_ts），不许回落成新闻时间
                if rhs_name != "now_ts":
                    touched_event = any(
                        isinstance(n, ast.Name) and n.id.startswith("event")
                        for n in ast.walk(rhs)
                    )
                    if touched_event:
                        failures.append(
                            f"{_rel(TRACKER_PY)}:{node.lineno} state.last_updated 被写成"
                            f"新闻时间 —— 活性判据失效：停更的实例看起来仍是「刚刚更新」"
                        )
            elif attr == "last_event_ts":
                seen_event = True

    if not seen_updated:
        failures.append(f"{_rel(TRACKER_PY)}:_process_external_narratives 没有写 last_updated")
    if not seen_event:
        failures.append(
            f"{_rel(TRACKER_PY)}:_process_external_narratives 没有写 last_event_ts —— "
            f"新闻发布时间就没了，两个时钟会重新退化成一个说不清的「最近更新」"
        )
    return failures


def check_state_persists_event_clock() -> list:
    """``last_event_ts`` 必须进 to_dict / from_dict，否则重启就丢。"""
    tree = _parse(TRACKER_PY)
    if tree is None:
        return [f"{_rel(TRACKER_PY)} 解析失败"]
    failures: list = []
    for name, must_have in (
        ("to_dict", "last_event_ts"),
        ("from_dict", "last_event_ts"),
    ):
        fn = _func(tree, name, cls="NarrativeState")
        if fn is None:
            failures.append(f"{_rel(TRACKER_PY)} 找不到 NarrativeState.{name}")
            continue
        if must_have not in ast.dump(fn):
            failures.append(
                f"{_rel(TRACKER_PY)}:NarrativeState.{name} 没有带上 {must_have} —— "
                f"重启后新闻时间丢失"
            )
    return failures


def check_read_paths_recompute() -> list:
    """读取路径必须按当前时间重算，否则停更叙事的热度永久定格。

    ❗只测"有没有调用重算"是不够的（绿 ≠ 在守），所以本文件另有行为验证
    ``check_stale_narrative_decays`` —— 真把 hits 推到窗口外，看它会不会衰减。
    """
    tree = _parse(TRACKER_PY)
    if tree is None:
        return [f"{_rel(TRACKER_PY)} 解析失败"]
    failures: list = []
    for name in ("get_summary", "get_active_narratives"):
        fn = _func(tree, name, cls="NarrativeTracker")
        if fn is None:
            failures.append(f"{_rel(TRACKER_PY)} 找不到 NarrativeTracker.{name} —— 锚点腐烂")
            continue
        calls = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "_refresh_all"
        ]
        if not calls:
            failures.append(
                f"{_rel(TRACKER_PY)}:{fn.lineno} {name} 没有重算 —— "
                f"热度只在 ingest 那一刻算过，停更叙事会一直显示旧热度（假新鲜）"
            )
    return failures


def _fresh_tracker():
    """拿到一份**刚 reload** 的 tracker 模块 + 一个不会写生产数据的实例。

    ❗三个必须堵的副作用：
      * ``_load_state`` / ``save_state`` —— 守卫**不得写生产数据**；
      * ``_publish_narrative_state_event`` —— 会把「跑一次守卫」变成「往事件总线
        发一轮叙事状态」，可能惊动决策链路。
    ❗每次都 reload：注入改的是源码文本，不 reload 就还是旧对象 —— 那正是
    "注入全绿但什么也没验证"的假通过。
    """
    T = importlib.import_module("deva.naja.cognition.narrative.tracker")
    T = importlib.reload(T)
    T.NarrativeTracker._load_state = lambda self: False
    T.NarrativeTracker.save_state = lambda self: False
    T.NarrativeTracker._maybe_save_state = lambda self: None
    T.NarrativeTracker._publish_narrative_state_event = lambda self, ts: None
    t = T.NarrativeTracker()
    t.enabled = True
    t._states = {}
    return T, t


def check_stale_narrative_decays() -> list:
    """行为验证：命中全在窗口外 → 读出来必须已衰减，不能还是旧热度。"""
    try:
        T, t = _fresh_tracker()
    except Exception as e:  # noqa: BLE001
        return [f"构造 tracker 失败：{type(e).__name__}: {e}"]

    now = time.time()
    stale = T.NarrativeState(name="停更叙事")
    # 全部命中都在 10 小时前，远超 6 小时 recent_window
    stale.hits = deque([(now - 10 * 3600, 0.8, ["关键词"]) for _ in range(20)])
    stale.recent_count = 20
    stale.attention_score = 0.9
    stale.stage = "高潮"
    stale.last_updated = now - 10 * 3600
    t._states["停更叙事"] = stale

    row = t.get_summary(limit=10)[0]
    if int(row["recent_count"]) != 0:
        return [
            f"停更 10 小时的叙事 recent_count 仍是 {row['recent_count']} —— "
            f"读取路径没有按当前时间重算，热度永久定格（假新鲜比异常更毒）"
        ]
    if float(row["attention_score"]) > 0.01:
        return [
            f"停更叙事 attention_score 仍是 {row['attention_score']} —— 没有衰减"
        ]
    if row["stage"] == "高潮":
        return [
            "停更 10 小时的叙事仍判为「高潮」—— 阶段不随窗口重算，"
            "页面会继续把死叙事当热点"
        ]
    return []


def check_fresh_narrative_stays_hot() -> list:
    """反方向：窗口内的命中不许被误判成衰减（重算不许矫枉过正）。"""
    try:
        T, t = _fresh_tracker()
    except Exception as e:  # noqa: BLE001
        return [f"构造 tracker 失败：{type(e).__name__}: {e}"]

    now = time.time()
    live = T.NarrativeState(name="活跃叙事")
    live.hits = deque([(now - 60, 0.8, ["关键词"]) for _ in range(20)])
    live.recent_count = 20
    live.attention_score = 0.9
    live.stage = "高潮"
    live.last_updated = now - 60
    t._states["活跃叙事"] = live

    row = t.get_summary(limit=10)[0]
    if int(row["recent_count"]) != 20:
        return [
            f"刚刚命中的叙事 recent_count 被算成 {row['recent_count']}（期望 20）—— "
            f"重算把窗口内的命中也丢了"
        ]
    if row["stage"] != "高潮":
        return [f"刚刚命中的叙事被判为「{row['stage']}」—— 重算矫枉过正"]
    return []


def check_ingest_splits_two_clocks() -> list:
    """行为验证：ingest 一条 2 小时前的新闻，两个时钟必须各记各的。"""
    try:
        T, t = _fresh_tracker()
    except Exception as e:  # noqa: BLE001
        return [f"构造 tracker 失败：{type(e).__name__}: {e}"]

    class _Ev:
        attention_score = 0.6

        def __init__(self, ts: float):
            self.timestamp = ts

    t.detect_narratives = lambda e: {"测试叙事": ["芯片"]}

    now = time.time()
    before = now - 2 * 3600
    t.ingest_event(_Ev(before))

    state = t._states.get("测试叙事")
    if state is None:
        return ["ingest 后没有生成叙事状态 —— 守卫自身的假事件不被识别"]

    lag = abs(state.last_updated - now)
    if lag > 60:
        return [
            f"last_updated 偏离摄入时刻 {lag:.0f}s —— 它记的不是摄入时间，"
            f"活性判据（「最近更新」走不走）就失效了"
        ]
    if abs(state.last_event_ts - before) > 60:
        return [
            f"last_event_ts={state.last_event_ts:.0f} 不是新闻时间 {before:.0f} —— "
            f"两个时钟没有分开，新闻发布时间丢失"
        ]
    if state.last_updated <= state.last_event_ts:
        return [
            "摄入时间没有晚于新闻时间 —— 两个时钟仍然指向同一个值"
        ]
    return []


def check_ui_labels_ingest_clock() -> list:
    """UI 上「最近更新」必须标明是摄入时钟，不许把它说成新闻时间。"""
    src = NARRATIVE_UI_PY.read_text(encoding="utf-8")
    failures: list = []
    if "last_event_ts" not in src:
        failures.append(
            f"{_rel(NARRATIVE_UI_PY)} 没有读 last_event_ts —— "
            f"新闻发布时间不上屏，用户看到「最近更新」会以为是新闻发生时间"
        )
    if "_ingest_ago" not in src:
        failures.append(
            f"{_rel(NARRATIVE_UI_PY)} 没有 _ingest_ago —— 摄入时间与新闻时间会混成一个"
        )
    return failures


def _all_checks() -> list:
    failures: list = []
    failures += check_ingest_uses_wall_clock()
    failures += check_state_records_both_clocks()
    failures += check_state_persists_event_clock()
    failures += check_read_paths_recompute()
    failures += check_stale_narrative_decays()
    failures += check_fresh_narrative_stays_hot()
    failures += check_ingest_splits_two_clocks()
    failures += check_ui_labels_ingest_clock()
    return failures


# ── 负向注入 ─────────────────────────────────────────────────────────────────
INJECTIONS = [
    {
        "name": "ingest_event 改回用新闻时间当 now（窗口端点漂移 + 停更定格）",
        "path": TRACKER_PY,
        "old": "        ingest_ts = time.time()",
        "new": "        ingest_ts = self._get_timestamp(event)",
    },
    {
        "name": "get_summary 不再重算（停更叙事热度永久定格）",
        "path": TRACKER_PY,
        "old": "        self._refresh_all()\n        sorted_states = sorted",
        "new": "        sorted_states = sorted",
    },
    {
        "name": "last_updated 改回新闻时间（活性判据失效）",
        "path": TRACKER_PY,
        "old": "            state.last_updated = now_ts\n            state.last_event_ts = event_ts or now_ts",
        "new": "            state.last_updated = event_ts or now_ts\n            state.last_event_ts = now_ts",
    },
    {
        "name": "丢掉 last_event_ts（新闻发布时间消失）",
        "path": TRACKER_PY,
        "old": "            state.last_event_ts = event_ts or now_ts\n",
        "new": "",
    },
    {
        "name": "to_dict 不持久化 last_event_ts（重启即丢）",
        "path": TRACKER_PY,
        "old": '            "last_event_ts": self.last_event_ts,\n',
        "new": "",
    },
    {
        # ❗反方向用例：docstring/注释里出现 _get_timestamp 不许被判成"把新闻时间当 now"
        "name": "注释里出现 self._get_timestamp(event)（反方向：不许误报）",
        "path": TRACKER_PY,
        "old": "        if not self.enabled:\n            return []\n\n        ingest_ts = time.time()",
        # 注释里写一句，真正生效的那行不动
        "new": (
            "        # 别写成 ingest_ts = self._get_timestamp(event)\n"
            "        if not self.enabled:\n            return []\n\n"
            "        ingest_ts = time.time()"
        ),
        "expect_clean": True,
    },
]


def run_injections() -> int:
    caught = 0
    expected = len(INJECTIONS)
    missed: list = []
    for inj in INJECTIONS:
        path: Path = inj["path"]
        original = path.read_text(encoding="utf-8")
        hits = original.count(inj["old"])
        if hits != 1:
            missed.append(inj["name"])
            print(f"❌ 注入锚点命中 {hits} 次（期望 1，守卫腐烂信号）：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        path.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
        try:
            found = _all_checks()
        except Exception as e:  # noqa: BLE001
            found = [f"守卫自身抛异常: {type(e).__name__}: {e}"]
        finally:
            path.write_text(original, encoding="utf-8")

        if inj.get("expect_clean"):
            if found:
                print(f"  ❌ 反方向用例被误报：{found[0][:110]}")
            else:
                caught += 1
                print("  ✅ 正确地没有报警（注释不算把新闻时间当 now）")
        elif found:
            caught += 1
            print(f"  ✅ 被捕获（{len(found)} 项）")
            for f in found[:2]:
                print(f"       · {f[:110]}")
        else:
            print("  ❌ 没抓到 —— 这条守卫是摆设！")

        if path.read_text(encoding="utf-8") != original:
            print("  🚨 还原失败，强制重写")
            path.write_text(original, encoding="utf-8")

    print(f"\n负向注入：{caught}/{expected} 被捕获"
          + (f"（另有 {len(missed)} 条锚点未命中，已计失败）" if missed else ""))
    return caught if not missed else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        return 0 if run_injections() == len(INJECTIONS) else 1

    failures = _all_checks()
    if failures:
        print("❌ 叙事时钟守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 叙事时钟守卫全绿"
          "（窗口用摄入时钟 · 双时钟各记各的 · 读取重算 · 停更会衰减 · 活跃不误判）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
