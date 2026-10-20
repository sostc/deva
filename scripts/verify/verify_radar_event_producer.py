"""守卫：雷达事件必须真的有生产者，且生产者传什么形状都不能被静默吃掉。

背景（2026-10-20 实查，`naja_radar_events` 长期 **0 行**，三条断链同时存在）：

1. **主要生产者根本没接上**。热点策略（`market_hotspot/strategies/base.py`
   的 ``_publish_strategy_event``）直接写 ``SignalStream.update(result)`` ——
   那只是给 WebUI 看的展示流，**不经过 SignalDispatcher**，所以策略配置里
   「雷达 ✅」是假的。真正会 dispatch 的只有走 ``ResultStore.save()`` 的
   普通策略，而它们最近一次产出还在 3 月。

2. **传 dict 等于没传**。``openrouter_monitor.send_to_radar()`` 把一个 dict
   交给 ``ingest_result``，而 ``_extract_payload`` 只认 ``result.output_full``
   属性：``getattr(dict, 'output_full', None)`` 恒 None → 立刻 return。
   「雷达事件已发送」的日志天天打，事件表一行没有。

3. **写失败没人知道**。``_store_event`` 是裸 ``except: return``，
   写不进去就什么也不说，于是「没产生事件」和「写不进去」长得一模一样。

本守卫钉的是行为（能不能落库），不是「代码里有没有那一行」。
"""

from __future__ import annotations

import argparse
import ast
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RADAR_ENGINE = ROOT / "deva/naja/radar/engine.py"
HOTSPOT_BASE = ROOT / "deva/naja/market_hotspot/strategies/base.py"


def _make_engine():
    """构造一个「不起线程、不联网、不写生产表」的雷达引擎。

    ``_db`` 在构造后被换成内存 dict —— 守卫绝不许往生产 NB 里写事件。
    """
    import deva.naja.radar.engine as E
    from deva.naja.config import get_radar_config

    get_radar_config().update({
        "auto_start_news_fetcher": False,
        "auto_start_global_scanner": False,
        "event_retention_days": 0,
        "cleanup_interval_seconds": 0,
        "macro_only": True,
    })
    eng = E.RadarEngine(trading_clock=object())
    eng._db = {}
    eng._threads.clear()
    return eng, E


class _Result:
    def __init__(self, output_full):
        self.strategy_id = "test_strategy"
        self.strategy_name = "测试策略"
        self.success = True
        self.output_full = output_full


class _OutputObj:
    """模拟「策略返回的不是 dict，而是带 to_dict() 的对象」。"""

    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


def _reachable_calls(node):
    """收集**真的会被执行**的调用：常量假分支（``if False:``）里的不算。

    ``ast.walk`` 会把不可达分支里的调用也数进来，于是「接线」检查
    在被 ``if False:`` 短路之后照样全绿 —— 那是摆设，不是守卫。
    """
    if isinstance(node, (ast.If, ast.While)):
        test = node.test
        if isinstance(test, ast.Constant) and not test.value:
            for sub in node.orelse:
                yield from _reachable_calls(sub)
            return
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.Call):
            yield child
        yield from _reachable_calls(child)


def _all_checks() -> list:
    fails = []
    try:
        eng, E = _make_engine()
    except Exception as e:  # noqa: BLE001
        return [f"雷达引擎无法构造（跳过后续所有判据）：{type(e).__name__}: {e}"]

    # ── 1. dict 也要能进（openrouter_monitor 就是这么调的）───────────────
    try:
        payload = eng._extract_payload({"signal_type": "openrouter_trend", "score": 0.9})
        if not payload:
            fails.append(
                "ingest_result 收到 dict 直接被丢弃 —— "
                "openrouter_monitor.send_to_radar() 传的就是 dict，这条生产者是死的"
            )
        elif payload.get("signal_type") != "openrouter_trend":
            fails.append(f"dict 的 signal_type 没取到：{payload.get('signal_type')!r}")
    except Exception as e:  # noqa: BLE001
        fails.append(f"dict 入参无法验证：{type(e).__name__}: {e}")

    # ── 2. output_full 是 dict（ResultStore 路径）────────────────────────
    try:
        payload = eng._extract_payload(_Result({"signal_type": "BUY", "score": 0.7}))
        if not payload or payload.get("signal_type") != "BUY":
            fails.append(f"output_full=dict 解析失败：{payload}")
    except Exception as e:  # noqa: BLE001
        fails.append(f"output_full=dict 无法验证：{type(e).__name__}: {e}")

    # ── 3. output_full 是带 to_dict() 的对象（策略不保证返回 dict）───────
    try:
        payload = eng._extract_payload(_Result(_OutputObj({"type": "sell", "score": 0.6})))
        if not payload or payload.get("signal_type") != "sell":
            fails.append(
                f"output_full 是对象时被丢弃：{payload} —— "
                "策略返回值不保证是 dict，按类型分流等于按运气工作"
            )
    except Exception as e:  # noqa: BLE001
        fails.append(f"output_full=对象 无法验证：{type(e).__name__}: {e}")

    # ── 4. score=None 必须变成数字，不许把 None 带进算术 ─────────────────
    try:
        payload = eng._extract_payload({"signal_type": "BUY"})
        score = (payload or {}).get("score")
        if not isinstance(score, float):
            fails.append(
                f"score 不是 float 而是 {type(score).__name__}={score!r} —— "
                "scan_anomaly 里 score-mean 会抛 TypeError，整轮 ingest 全废"
            )
    except Exception as e:  # noqa: BLE001
        fails.append(f"score 归一无法验证：{type(e).__name__}: {e}")

    # ── 5. 端到端：连续 3 次同模式必须落一条事件 ─────────────────────────
    try:
        stored = 0
        for _ in range(3):
            stored += len(eng.ingest_result({"signal_type": "BUY", "score": 0.7}))
        rows = len(eng._db)
        if stored == 0 or rows == 0:
            fails.append(
                f"连续 3 次同模式信号没有产生任何事件（stored={stored}, rows={rows}）—— "
                "radar_pattern 是唯一能过 macro_only 的通道，它不响就永远是 0 行"
            )
    except Exception as e:  # noqa: BLE001
        fails.append(f"端到端落库无法验证：{type(e).__name__}: {e}")

    # ── 6. 热点策略这条主生产者必须真的接上雷达 ──────────────────────────
    # ❗判据是「这行调用会被执行吗」，不是「文件里出现过 ingest_result」：
    # 把条件改成 `if False:` 之后 AST 里那个 Call 还在，只是永远走不到 ——
    # 那样的守卫是摆设。所以常量假分支里的调用一律不算数。
    try:
        tree = ast.parse(HOTSPOT_BASE.read_text(encoding="utf-8"))
        body_calls = set()
        found_fn = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_publish_strategy_event":
                found_fn = True
                for call in _reachable_calls(node):
                    fn = call.func
                    if isinstance(fn, ast.Attribute):
                        body_calls.add(fn.attr)
                    elif isinstance(fn, ast.Name):
                        body_calls.add(fn.id)
        if not found_fn:
            fails.append("没找到 _publish_strategy_event —— 热点策略发布路径变了，守卫过期")
        else:
            if "get_radar_engine" not in body_calls or "ingest_result" not in body_calls:
                fails.append(
                    "_publish_strategy_event 里没有可达的 radar.ingest_result —— "
                    "热点策略只写展示流，naja_radar_events 就永远是 0 行"
                )
    except Exception as e:  # noqa: BLE001
        fails.append(f"热点策略接线无法验证：{type(e).__name__}: {e}")

    # ── 7. 写事件失败必须喊出来（裸 except 会让 0 行无从追查）────────────
    try:
        src = RADAR_ENGINE.read_text(encoding="utf-8")
        tree = ast.parse(src)
        warn = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_store_event":
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                        if sub.func.attr in ("warning", "error", "exception"):
                            warn = True
        if not warn:
            fails.append("_store_event 写失败仍然是静默的 —— 事件表 0 行时分不清「没事件」和「写不进去」")
    except Exception as e:  # noqa: BLE001
        fails.append(f"_store_event 可见性无法验证：{type(e).__name__}: {e}")

    return fails


INJECTIONS = [
    {
        "name": "ingest_result 又不认 dict 了（openrouter 生产者变哑巴）",
        "path": RADAR_ENGINE,
        "old": "        if isinstance(result, dict):\n            source = result",
        "new": "        if False:\n            source = result",
    },
    {
        "name": "score 不归一，None 直接进算术",
        "path": RADAR_ENGINE,
        "old": '            "score": _clamp_event_score(raw_score),',
        "new": '            "score": raw_score,',
    },
    {
        "name": "写事件失败重新变静默",
        "path": RADAR_ENGINE,
        "old": 'logger.warning("[Radar] 事件写入 %s 失败，雷达事件表将为空：%s", RADAR_EVENTS_TABLE, msg)',
        "new": "pass",
    },
    {
        "name": "热点策略不再喂雷达",
        "path": HOTSPOT_BASE,
        "old": "            if should_send_to_radar(self.strategy_id):",
        "new": "            if False:",
    },
]


def _reload():
    for mod in ("deva.naja.radar.engine", "deva.naja.market_hotspot.strategies.base"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])


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
            # 单例必须重置，否则注入后的类根本没被实例化
            import deva.naja.radar.engine as E
            E.RadarEngine._instance = None
            fails = _all_checks()
        finally:
            path.write_text(original, encoding="utf-8")
            _reload()
            import deva.naja.radar.engine as E
            E.RadarEngine._instance = None

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
    total = 7
    if failures:
        print(f"❌ {len(failures)}/{total} 项失败：雷达事件生产者守卫")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0

    print("✅ 雷达事件生产者守卫全绿"
          "（dict/to_dict/属性三种入参都认 · score 归一 · 热点策略已接雷达 · 写失败可见）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
