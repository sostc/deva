"""守卫：恐慌分接线 + 超跌机会判定 + 美林事件循环 + 洞察事件链。

钉住四件事（都是「看起来在跑、其实永远不生效」这一类）：

1. `PanicAnalyzer` 的权重归一 —— 缺维度时必须从**分母**里剔除。
   否则生产环境缺 spread/event，最高只能到 70，而阈值也是 70 → 永不触发。
2. `probe_panic` / `evaluate_dip` —— 拿不到数据必须是 None，不许返回 0 分
   冒充「不恐慌」；三个条件缺一即不成立。
3. 美林时钟任务 —— func_code 里不许再出现 `nest_asyncio`（它 patch 掉
   `asyncio.run`，在调度线程里取到已关闭的默认 loop → Event loop is closed）。
4. 洞察池 → CognitiveInsightEvent —— 回调必须在锁外调用，且容器真的装配了它。

两级制：裸跑=提示档(exit 0)，`--strict`=闸门档(exit 1)。
"""

from __future__ import annotations

import argparse
import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CONTAINER = ROOT / "deva/naja/application/container.py"
POOL = ROOT / "deva/naja/cognition/insight/engine.py"
PROBE = ROOT / "deva/naja/attention/kernel/panic_probe.py"
AWAKENING = ROOT / "deva/naja/attention/ui/awakening.py"
MANAS = ROOT / "deva/naja/attention/kernel/manas_engine.py"
PANIC = ROOT / "deva/naja/market_hotspot/filters/panic_analyzer.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_panic_normalization() -> list:
    """缺维度必须从分母剔除，而不是拿默认值顶替。"""
    failures = []
    from deva.naja.market_hotspot.filters.panic_analyzer import PanicAnalyzer

    analyzer = PanicAnalyzer()
    full = analyzer._calculate_panic_score({
        "price_destabilization_speed": 3.0,
        "volume_shrink_ratio": 1.0,
        "spread_ratio": 1.0,
        "fear_score": 90,
        "event_impact": 0,
    })
    partial = analyzer._calculate_panic_score({
        "price_destabilization_speed": 3.0,
        "volume_shrink_ratio": None,
        "spread_ratio": None,
        "fear_score": 90,
        "event_impact": None,
    })

    # 同样的「跌 3% + 恐慌 90」，全维只有 33 分；缺维重归一后应显著更高。
    if full >= 40:
        failures.append(f"全维基准值异常（{full:.1f}），用例前提不成立")
    if partial <= 70:
        failures.append(
            f"缺维场景只得 {partial:.1f} 分 —— 权重没有重归一，"
            "生产环境（缺 spread/event）将永远到不了 70 阈值"
        )
    if partial <= full:
        failures.append("缺维分不高于全维分，说明缺失维度仍被当成 0/默认值计入")

    # 全维缺失时必须返回 0，而不是崩或者 NaN
    try:
        empty = analyzer._calculate_panic_score({
            "price_destabilization_speed": None,
            "volume_shrink_ratio": None,
            "spread_ratio": None,
            "fear_score": None,
            "event_impact": None,
        })
        if empty != 0.0:
            failures.append(f"全维缺失应得 0，实得 {empty}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"全维缺失时抛异常: {exc}")
    return failures


def check_probe_semantics() -> list:
    """拿不到数据必须 None；机会判定三条件缺一不可。"""
    failures = []
    from deva.naja.attention.kernel.panic_probe import PanicSample, evaluate_dip, probe_panic

    if probe_panic(None) is not None:
        failures.append("probe_panic(None) 应返回 None（拿不到 ≠ 0 分）")

    def sample(panic=80.0, avg=-3.0, delta=0.2, used=("price", "fear")):
        return PanicSample(
            panic_score=panic,
            level="high",
            avg_change=avg,
            delta_breadth=delta,
            dimensions_used=list(used),
            sample_size=50,
            ts=0.0,
        )

    ok = evaluate_dip(sample())
    if not ok.opportunity:
        failures.append(f"三条件全满足却不判机会：{ok.blockers}")
    if ok.size_hint <= 0 or ok.size_hint > 0.5:
        failures.append(f"首笔仓位比例异常: {ok.size_hint}（应 >0 且 <=0.5）")

    cases = {
        "恐慌不足": sample(panic=65.0),
        "没在跌": sample(avg=0.4),
        "止跌未确认": sample(delta=None),
        "广度仍恶化": sample(delta=-0.3),
    }
    for name, s in cases.items():
        r = evaluate_dip(s)
        if r.opportunity:
            failures.append(f"「{name}」这一条不满足却仍判机会 —— 会变成逢跌必抄")
        if not r.blockers:
            failures.append(f"「{name}」被拦下但没写原因（页面读不出差在哪）")

    none_case = evaluate_dip(None)
    if none_case.available or none_case.opportunity:
        failures.append("无数据时不应判为「已判定/有机会」")
    if not none_case.blockers:
        failures.append("无数据时没有说明原因")
    return failures


def _code_only(src: str) -> str:
    """剥掉注释与 docstring，只留可执行代码。

    ❗必须剥：func_code 的 docstring 里写着「不要用 asyncio.run」，
    不剥就会把自己的说明文字当成违规代码判失败。
    """
    import ast as _ast

    tree = _ast.parse(src)
    for node in _ast.walk(tree):
        if isinstance(node, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if (
                isinstance(first, _ast.Expr)
                and isinstance(first.value, _ast.Constant)
                and isinstance(first.value.value, str)
            ):
                node.body = body[1:] or [_ast.Pass()]
    return _ast.unparse(tree)


def _merrill_func_code() -> str:
    """取出 _start_merrill_clock_task 里那段 func_code 字符串。"""
    import ast as _ast

    tree = _ast.parse(_text(CONTAINER))
    for node in _ast.walk(tree):
        if isinstance(node, _ast.FunctionDef) and node.name == "_start_merrill_clock_task":
            for sub in _ast.walk(node):
                if (
                    isinstance(sub, _ast.Constant)
                    and isinstance(sub.value, str)
                    and "def execute" in sub.value
                ):
                    return sub.value
    return ""


def check_merrill_loop() -> list:
    """func_code 不许再用 nest_asyncio / asyncio.run。"""
    failures = []
    raw = _merrill_func_code()
    if not raw:
        return ["取不到美林任务的 func_code —— 锚点失配"]
    code = _code_only(raw)

    if "nest_asyncio" in code:
        failures.append(
            "美林任务仍引用 nest_asyncio：它会替换 asyncio.run，"
            "在调度线程里取到已关闭的默认 loop → Event loop is closed"
        )
    if re.search(r"asyncio\.run\(", code):
        failures.append("美林任务仍用 asyncio.run()，应改为 new_event_loop()")
    if "new_event_loop" not in code:
        failures.append("美林任务没有 new_event_loop —— 没有真正换掉事件循环")
    if "merrill_clock_update_v2" not in _text(CONTAINER):
        failures.append(
            "任务名没有版本号：func_code 存在 NB 里，改源码不会更新已存在的任务，"
            "旧任务会继续用坏代码跑"
        )
    if "use_mock" not in code:
        failures.append("没有标记 mock 数据 —— 用假数据算出的周期会被当成真信号")
    return failures


def _notify_inside_lock(src: str, func_name: str = "_append_or_merge") -> bool:
    """`self._notify(...)` 是否被包在 `with self._lock` 里。

    ❗不能用「最后一次 with 的字符位置」去比：判断的是**包含关系**，
    行号前后比大小在嵌套/新增块时一律失真。
    """
    import ast as _ast

    tree = _ast.parse(src)
    for node in _ast.walk(tree):
        if not (isinstance(node, _ast.FunctionDef) and node.name == func_name):
            continue
        parents = {}
        for parent in _ast.walk(node):
            for child in _ast.iter_child_nodes(parent):
                parents[child] = parent
        for sub in _ast.walk(node):
            if (
                isinstance(sub, _ast.Call)
                and isinstance(sub.func, _ast.Attribute)
                and sub.func.attr == "_notify"
            ):
                cur = sub
                while cur in parents:
                    cur = parents[cur]
                    if isinstance(cur, _ast.With):
                        return True
    return False


def check_insight_wiring() -> list:
    """洞察池回调必须在锁外调用，且容器装配了它。"""
    failures = []
    pool_src = _text(POOL)
    if "on_insight" not in pool_src:
        failures.append("InsightPool 没有 on_insight 回调 → 池里有洞察也送不到 QueryState")
    if "self._notify(" not in pool_src:
        failures.append("_append_or_merge 里没有调用 _notify")
    elif _notify_inside_lock(pool_src):
        failures.append("_notify 在 with self._lock 内部调用 —— 回调发布事件会造成重入死锁")

    container_src = _text(CONTAINER)
    if "_wire_insight_pool_events" not in container_src:
        failures.append("容器没有装配洞察事件链（_wire_insight_pool_events）")
    elif "_wire_insight_pool_events()" not in container_src:
        failures.append("_wire_insight_pool_events 定义了但没被调用")

    manas_src = _text(MANAS)
    if "_panic_score" not in manas_src or "set_panic_score" not in manas_src:
        failures.append("Manas 没有接收恐慌分（set_panic_score）")
    gate = manas_src[manas_src.find("def _get_gate_reason"):]
    if "_panic_score" not in gate[:6000]:
        failures.append("门理由里没有恐慌分 —— 恐慌只算不用，等于没接线")

    os_kernel = ROOT / "deva/naja/attention/os/os_kernel.py"
    if "_refresh_panic" not in _text(os_kernel):
        failures.append("生产内核 os_kernel 没有调用 _refresh_panic（恐慌分接在死代码上）")
    return failures


def check_dip_on_page() -> list:
    """页面必须真的渲染出这两格（读 HTML，不读源码文本）。"""
    failures = []

    probe_stub = {
        "available": True,
        "panic": {
            "panic_score": 78.0,
            "level": "high",
            "dimensions_used": ["price", "fear"],
            "dimensions_missing": ["volume", "spread", "event"],
            "quality": 0.6,
            "sample_size": 50,
        },
        "dip": {
            "opportunity": False,
            "score": 0.0,
            "reasons": ["当日均跌 -2.8%"],
            "blockers": ["广度仍在恶化 -0.25"],
            "size_hint": 0.0,
        },
    }

    try:
        from deva.naja.attention.ui import awakening as A

        A._probe_dip_state = lambda _m: probe_stub
        html = A._render_system_overview(
            {"awakening_level": "dormant", "should_act": False, "action_type": "hold", "regime_score": -0.55},
            {"market_regime": "trend_down", "attention_focus_count": 1, "top_attention": [],
             "narrative_state": {"current_narratives": []}, "economic_cycle": {"phase": "unknown"},
             "cognitive_insights": {"insights": []}},
        )
    except Exception as exc:  # noqa: BLE001
        return [f"渲染概览抛异常: {type(exc).__name__}: {exc}"]

    for label in ("恐慌指数", "超跌机会", "78", "仅price/fear维", "广度仍在恶化"):
        if label not in html:
            failures.append(f"概览里没有「{label}」—— 恐慌/超跌没真正上屏")

    try:
        from deva.naja.attention.ui import awakening as A

        A._probe_dip_state = lambda _m: {"available": False, "reason": "scanner 无实时行情也无广度数据"}
        html2 = A._render_system_overview(
            {"should_act": False, "action_type": "hold"},
            {"market_regime": "neutral", "attention_focus_count": 0, "top_attention": [],
             "narrative_state": {"current_narratives": []}, "economic_cycle": {"phase": "unknown"},
             "cognitive_insights": {"insights": []}},
        )
    except Exception as exc:  # noqa: BLE001
        return [f"降级渲染抛异常: {type(exc).__name__}: {exc}"]

    if "未采集" not in html2:
        failures.append("拿不到恐慌数据时没有「未采集」（会显示成 0 分假装安全）")
    return failures


def _all_checks() -> list:
    failures = []
    for fn in (
        check_panic_normalization,
        check_probe_semantics,
        check_merrill_loop,
        check_insight_wiring,
        check_dip_on_page,
    ):
        try:
            failures.extend(fn())
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{fn.__name__} 抛异常: {type(exc).__name__}: {exc}")
    return failures


INJECTIONS = [
    {
        "name": "PanicAnalyzer 退回默认值（缺失维度按 0 计）",
        "path": PANIC,
        "old": '        value = features.get("spread_ratio")\n        if value is not None:',
        "new": '        value = features.get("spread_ratio", 1.0) or 1.0\n        if value is not None:',
    },
    {
        "name": "超跌判定去掉「止跌确认」",
        "path": PROBE,
        "old": '    if panic.delta_breadth is None:\n        blockers.append("无广度环比，止跌未确认")',
        "new": '    if False:\n        blockers.append("无广度环比，止跌未确认")',
    },
    {
        "name": "美林任务改回 asyncio.run",
        "path": CONTAINER,
        "old": "        data = _run_coro(_fetch())",
        "new": "        data = asyncio.run(_fetch())",
    },
    {
        "name": "洞察回调挪回锁内",
        "path": POOL,
        "old": "        self._notify(published)\n        return published",
        "new": "        with self._lock:\n            self._notify(published)\n        return published",
    },
    {
        "name": "页面去掉超跌机会格",
        "path": AWAKENING,
        "old": "<div style=\"font-size: 11px; color: #94a3b8; margin-bottom: 4px;\">超跌机会</div>",
        "new": "<div style=\"font-size: 11px; color: #94a3b8; margin-bottom: 4px;\">（已删除）</div>",
    },
]


def _reload():
    for name in (
        "deva.naja.attention.kernel.panic_probe",
        "deva.naja.market_hotspot.filters.panic_analyzer",
        "deva.naja.attention.ui.awakening",
    ):
        mod = sys.modules.get(name)
        if mod is not None:
            importlib.reload(mod)


def run_injections() -> int:
    caught = 0
    missed = []
    for inj in INJECTIONS:
        path = inj["path"]
        original = path.read_text(encoding="utf-8")
        if original.count(inj["old"]) != 1:
            missed.append(inj["name"])
            print(f"❌ 注入锚点出现 {original.count(inj['old'])} 次（期望 1，守卫腐烂信号）：{inj['name']}")
            continue
        print(f"· 注入：{inj['name']}")
        path.write_text(original.replace(inj["old"], inj["new"]), encoding="utf-8")
        try:
            _reload()
            found = _all_checks()
        except Exception as exc:  # noqa: BLE001
            found = [f"守卫自身抛异常: {type(exc).__name__}: {exc}"]
        finally:
            path.write_text(original, encoding="utf-8")
            _reload()
        if found:
            caught += 1
            print(f"  ✅ 被捕获（{len(found)} 项）")
            print(f"       · {found[0][:110]}")
        else:
            print("  ❌ 没抓到 —— 这条守卫是摆设！")
        if path.read_text(encoding="utf-8") != original:
            print("  🚨 还原失败，强制重写")
            path.write_text(original, encoding="utf-8")
    print(f"\n负向注入：{caught}/{len(INJECTIONS)} 被捕获"
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
        print("❌ 恐慌/超跌/美林/洞察 守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 恐慌分重归一 · 超跌三条件 · 美林事件循环 · 洞察事件链 全绿")
    return 0


if __name__ == "__main__":
    sys.exit(main())
