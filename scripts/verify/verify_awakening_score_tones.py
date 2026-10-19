#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：觉醒页分数着色 + 解释 + 数据口径。

背景（2026-10-19）
----------------
用户在 /awakening 的末那识卡片上看到两件怪事：一个没有单位的 ``unknown``，
以及所有分数一律固定颜色（时机蓝、趋势紫、自信度绿、风险温度橙）——
于是「自信度 0.29（策略失灵）」和「自信度 0.95（正常）」长得一模一样，
「风险温度 1.30（安全余量只剩 13%）」还是一片橙色，读起来像「还好」。

体检出四类问题，本守卫钉住其中三条，防止回退：

① **风险温度是反向指标**（``risk_safety = 1 - min(T,1.5)/1.5``，T 越大越危险）。
   着色一旦写成正向（越高越绿），页面会把「最危险」渲染成「最健康」——
   这种错**没有任何异常**，只是安静地把人骗了。所以必须成对断言：
   高温=红、低温=绿，且 1.5（安全余量归零）绝不能落在蓝/绿。
② **内部枚举名不许上屏**：``QueryState.economic_cycle.phase`` 的初值是
   字符串 ``"unknown"``，历史版本直接 f-string 插进 HTML，页面上就那么一个
   ``unknown``。必须有中文映射；没有真值时必须显示「未采集」+ 灰。
③ **觉醒等级只认引擎真值**：历史版本在引擎给 ``dormant`` 时用
   ``_compute_awakening_from_manas()`` 反推一个更高档位，导致页头「觉醒中 40%」
   与卡片「末那识 dormant」同时挂在屏幕上。反推值只许作为「参考活动度」。
④ **流动性必须走唯一口径** ``read_macro_liquidity_signal()``：读
   ``query_state['liquidity_state']['signal']`` 拿到的是构造默认值 0.5，
   而 ``LiquidityCognition`` 全仓只在测试里被实例化 —— 那格永远「0.50」，
   看着像读数，其实是字面量。

用法
----
    python scripts/verify/verify_awakening_score_tones.py
    python scripts/verify/verify_awakening_score_tones.py --strict
    python scripts/verify/verify_awakening_score_tones.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AWAKENING_PY = ROOT / "deva/naja/attention/ui/awakening.py"
MODULE_NAME = "deva.naja.attention.ui.awakening"


def _mod():
    return importlib.import_module(MODULE_NAME)


def _reload():
    importlib.reload(_mod())


def _src() -> str:
    return AWAKENING_PY.read_text(encoding="utf-8")


def _func_node(name: str):
    tree = ast.parse(_src())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _func_source(name: str) -> str:
    node = _func_node(name)
    if node is None:
        return ""
    src = _src()
    lines = src.splitlines()
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def _return_dict(function_name: str):
    """取函数里 ``return { ... }`` 那个字典节点（第一个）。"""
    node = _func_node(function_name)
    if node is None:
        return None
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and isinstance(child.value, ast.Dict):
            return child.value
    return None


# ── ① 风险温度反向 + 其余指标方向 ──────────────────────────────────────────────
def check_risk_temperature_is_inverted() -> list:
    """高温必须红、低温必须绿，且 1.5（安全余量归零）不许是蓝/绿。"""
    A = _mod()
    failures: list = []

    high_tone, high_label = A._risk_tone(1.40)
    low_tone, low_label = A._risk_tone(0.70)

    if high_tone != A.TONE_RED:
        failures.append(f"风险温度 1.40 应为红色（很危险），实得 {high_tone} / {high_label}")
    if low_tone != A.TONE_GREEN:
        failures.append(f"风险温度 0.70 应为绿色（宽松），实得 {low_tone} / {low_label}")
    if not high_label or not low_label:
        failures.append("风险温度没有判读文案（裸数字读不出好坏）")

    # 反方向用例：跨越「安全余量归零」的几个点都不许落到冷色
    for value in (1.30, 1.50, 1.75, 2.00):
        tone, label = A._risk_tone(value)
        if tone not in (A.TONE_RED, A.TONE_AMBER):
            failures.append(f"风险温度 {value} 落在冷色 {tone}（{label}）—— 危险被渲染成健康")

    # 单调性：同一轴上不能出现「更高温反而更绿」
    order = {A.TONE_GREEN: 0, A.TONE_BLUE: 1, A.TONE_AMBER: 2, A.TONE_RED: 3}
    seq = [order.get(A._risk_tone(v)[0], -1) for v in (0.60, 0.95, 1.20, 1.35)]
    if seq != sorted(seq):
        failures.append(f"风险温度色阶不单调（温度越高应越危险）：0.60/0.95/1.20/1.35 → {seq}")
    return failures


def check_other_scores_direction() -> list:
    """时机 / 趋势 / 自信度：越高越绿（与风险温度相反的方向）。"""
    A = _mod()
    failures: list = []

    if A._timing_tone(0.10)[0] != A.TONE_RED:
        failures.append("时机 0.10 应为红色（不宜动）")
    if A._timing_tone(0.80)[0] != A.TONE_GREEN:
        failures.append("时机 0.80 应为绿色（成熟）")
    if A._regime_tone(-0.90)[0] != A.TONE_RED:
        failures.append("趋势 -0.90 应为红色（强逆风）")
    if A._regime_tone(0.90)[0] != A.TONE_GREEN:
        failures.append("趋势 +0.90 应为绿色（顺风）")
    if A._confidence_tone(0.20)[0] != A.TONE_RED:
        failures.append("自信度 0.20 应为红色（策略失灵）")
    if A._confidence_tone(0.90)[0] == A.TONE_RED:
        failures.append("自信度 0.90 不该是红色（正常范围）")

    # 反方向用例：高时机不能被判成危险色
    for value in (0.60, 0.75, 0.95):
        if A._timing_tone(value)[0] == A.TONE_RED:
            failures.append(f"时机 {value} 被判成红色 —— 方向反了")
    return failures


# ── ② 内部枚举名不许上屏 + 历史信号必须标新鲜度 ────────────────────────────────
def check_economic_cycle_is_honest() -> list:
    A = _mod()
    failures: list = []
    original = A._read_merrill_signal
    manas = {"awakening_level": "dormant", "should_act": False,
             "action_type": "hold", "available": True}
    query_state = {
        "market_regime": "trend_down", "risk_bias": 0.1,
        "attention_focus_count": 0, "top_attention": [],
        "narrative_state": {"current_narratives": []},
        "economic_cycle": {"phase": "unknown"},
        "cognitive_insights": {"insights": []},
    }
    try:
        # 1) 完全没有信号 → 中文「未采集」，不许露出 unknown
        A._read_merrill_signal = lambda: None
        html = A._render_system_overview(manas, query_state)
        if "unknown" in html:
            failures.append("经济周期把内部枚举名 unknown 渲染上屏了")
        if "未采集" not in html:
            failures.append("经济周期无数据时没显示「未采集」")

        # 2) 只有 4 天前的历史信号 → 必须标出「多久前」，且判为过期
        A._read_merrill_signal = lambda: SimpleNamespace(
            phase=SimpleNamespace(value="过热"),
            timestamp=time.time() - 4 * 86400,
        )
        html = A._render_system_overview(manas, query_state)
        if "4 天前" not in html:
            failures.append("历史信号没标采集时间（假新鲜比异常更毒）")
        if "历史信号" not in html:
            failures.append("历史信号没被标成「历史信号」")
        if "unknown" in html:
            failures.append("历史信号分支又把 unknown 渲染出来了")

        # 3) 事件已到 → 直接显示真值
        A._read_merrill_signal = lambda: None
        query_state["economic_cycle"] = {"phase": "过热"}
        html = A._render_system_overview(manas, query_state)
        if "过热" not in html or "本次运行已更新" not in html:
            failures.append("economic_cycle 已有真值时没正确显示")
    finally:
        A._read_merrill_signal = original
    return failures


# ── ③ 觉醒等级：引擎真值优先，反推只作「参考活动度」 ────────────────────────────
def check_awakening_level_comes_from_engine() -> list:
    """AST 检查 ``_get_manas_state`` 返回的 awakening_level 绑定的是引擎值。"""
    failures: list = []
    body = _return_dict("_get_manas_state")
    if body is None:
        return ["_get_manas_state 里找不到 return {...}，守卫锚点失效"]

    mapping = {}
    for key, value in zip(body.keys, body.values):
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            mapping[key.value] = value

    level_node = mapping.get("awakening_level")
    if not (isinstance(level_node, ast.Name) and level_node.id == "engine_level"):
        failures.append(
            "awakening_level 必须直接绑定引擎真值 engine_level"
            f"（实得 {ast.dump(level_node)[:60] if level_node is not None else 'None'}）"
            " —— 反推值不许顶替引擎档位"
        )

    activity_node = mapping.get("activity_level")
    if not (isinstance(activity_node, ast.Name) and activity_node.id == "activity_level"):
        failures.append("反推值应存进 activity_level（「参考活动度」），不许丢掉")

    src = _func_source("_get_manas_state")
    if "_compute_awakening_from_manas" not in src:
        failures.append("_get_manas_state 应保留反推值作为参考活动度（助记：不删，只降级）")
    return failures


# ── ④ 流动性唯一口径 ──────────────────────────────────────────────────────────
def check_liquidity_uses_single_source() -> list:
    """流动性只许走 ``read_macro_liquidity_signal()``。

    ❗判据用「赋值给 liquidity_state」而不是裸子串 ``liquidity_state`` ——
    本函数的注释里也写着这个键名（说明为什么不许读它），裸子串会永远红。
    """
    failures: list = []
    src = _func_source("_render_system_overview")
    if "read_macro_liquidity_signal" not in src:
        failures.append("_render_system_overview 没走唯一口径 read_macro_liquidity_signal()")
    if re.search(r"\bliquidity_state\s*=", src):
        failures.append(
            "又在给 liquidity_state 赋值/读 query_state['liquidity_state'] —— 那是构造"
            "默认值 0.5，LiquidityCognition 全仓只在测试里实例化，事件从未发出"
        )
    return failures


#: 四个主指标格：``<数值div>`` 紧跟 ``<判读div>``（用正则同时取色与判读文案）。
#: ❗只取色不取文案，会漏掉「某格判读被清空」——别的格文案还能让断言通过
#:   （一项保护掩盖另一项），负向注入实测过。
_METRIC_CELL_RE = re.compile(
    r'font-size: 16px; font-weight: 600; color: (#[0-9a-fA-F]{6});">([^<]*)</div>\s*'
    r'<div style="font-size: 9px; color: #[0-9a-fA-F]{6}; margin-top: 2px;">([^<]*)</div>'
)


def _metric_cells(html: str) -> list:
    return _METRIC_CELL_RE.findall(html)


# ── ⑤ 每个分数都有颜色 + 判读，且随数值变化 ────────────────────────────────────
def check_manas_core_colors_and_labels() -> list:
    A = _mod()
    failures: list = []

    def render(**overrides):
        state = {
            "available": True, "awakening_level": "dormant", "activity_level_pct": 40,
            "action_type": "hold", "should_act": False, "harmony_state": "neutral",
            "harmony_strength": 0.22, "bias_state": "neutral", "bias_correction": 1.0,
            "alpha": 0.30, "supply_chain_risk_level": "LOW", "effective_threshold": 0.5,
            "timing_score": 0.35, "regime_score": 0.02, "confidence_score": 0.29,
            "risk_temperature": 1.30, "manas_score": 0.22, "action_gate_reason": "x",
            "bias_message": "",
        }
        state.update(overrides)
        return A._render_manas_core(state)

    weak = render()
    strong = render(timing_score=0.85, regime_score=0.8, confidence_score=0.9,
                    risk_temperature=0.7, harmony_strength=0.72, manas_score=0.72,
                    alpha=1.2, should_act=True, action_type="buy")

    if weak == strong:
        failures.append("强/弱两组输入渲染出完全相同的卡片 —— 颜色没有跟着数值走")

    weak_cells = _metric_cells(weak)
    strong_cells = _metric_cells(strong)
    weak_tones = [c[0] for c in weak_cells]
    strong_tones = [c[0] for c in strong_cells]
    if len(weak_cells) != 4:
        failures.append(f"四个主指标格应各有「数值+判读」，实得 {len(weak_cells)} 组（锚点可能被改）")
    if any(not label.strip() for _, _, label in weak_cells):
        failures.append(f"有指标格缺少判读文案：{[c[1] for c in weak_cells]} —— 裸数字读不出好坏")
    if A.TONE_RED not in weak_tones:
        failures.append("弱场景（信心 0.29 / 风险 1.30）的指标格竟然没有红色")
    if A.TONE_GREEN not in strong_tones:
        failures.append("强场景（风险 0.70）的指标格竟然没有绿色")

    # 逐个指标核对判读（不能靠「别处也有这个词」蒙混）
    timing_cell = weak_cells[0] if len(weak_cells) > 0 else ("", "", "")
    risk_cell = weak_cells[3] if len(weak_cells) > 3 else ("", "", "")
    if "偏弱" not in timing_cell[2]:
        failures.append(f"时机 0.35 的判读不是「偏弱」，实得 {timing_cell[2]!r}")
    if "危险" not in risk_cell[2]:
        failures.append(f"风险温度 1.30 的判读没写危险，实得 {risk_cell[2]!r}")

    for label in ("偏弱", "策略失灵", "很危险", "远低于门槛"):
        if label not in weak:
            failures.append(f"弱场景缺少判读文案「{label}」—— 裸数字读不出好坏")
    if "分数怎么读" not in weak:
        failures.append("卡片里没有「分数怎么读」的区间/阈值说明")

    # 门槛对比：低于门槛要写「差」，高于门槛要写「过线」
    if "差 " not in weak:
        failures.append("综合分低于门槛时没写出来差多少")
    if "过线" not in strong:
        failures.append("综合分过线时没写「过线」")

    # 引擎未产出时必须是灰色 + 明示，不许把占位 0.5 当读数
    fallback = A._render_manas_core(A._get_default_state(error="boom"))
    if "引擎本轮未产出" not in fallback:
        failures.append("引擎未产出时没有提示（占位 0.5 会被当成真读数）")
    fallback_tones = [c[0] for c in _metric_cells(fallback)]
    if not fallback_tones:
        failures.append("兜底渲染里找不到指标格（锚点失效）")
    if any(tone != A.TONE_GREY for tone in fallback_tones):
        failures.append(f"引擎未产出时指标格仍有彩色 {fallback_tones} —— 占位值被当成真实好坏")
    return failures


def _all_checks() -> list:
    return (
        check_risk_temperature_is_inverted()
        + check_other_scores_direction()
        + check_economic_cycle_is_honest()
        + check_awakening_level_comes_from_engine()
        + check_liquidity_uses_single_source()
        + check_manas_core_colors_and_labels()
    )


# ── 负向注入：每条都要被抓到，抓不到说明守卫是摆设 ─────────────────────────────
INJECTIONS = [
    {
        "name": "风险温度方向写反（高温→红 改成 低温→红）",
        "old": '    if value >= 1.30:\n        return TONE_RED, "很危险"',
        "new": '    if value <= 1.30:\n        return TONE_RED, "很危险"',
    },
    {
        "name": "时机色阶写反（偏高反而变弱）",
        "old": '    if value < 0.40:\n        return TONE_AMBER, "偏弱"',
        "new": '    if value > 0.40:\n        return TONE_AMBER, "偏弱"',
    },
    {
        "name": "经济周期把 unknown 直接上屏",
        "old": '    return "未采集", TONE_GREY, "美林时钟未产出"',
        "new": '    return str(phase), TONE_GREY, "美林时钟未产出"',
    },
    {
        "name": "觉醒档位用 UI 反推值顶替引擎真值",
        "old": '            "awakening_level": engine_level,',
        "new": '            "awakening_level": activity_level,',
    },
    {
        "name": "流动性读回 QueryState 的字面量 0.5",
        "old": '    """渲染系统工作原理概览"""\n',
        "new": '    """渲染系统工作原理概览"""\n    liquidity_state = query_state.get("liquidity_state", {})\n',
    },
    {
        "name": "判读文案被清空（分数只剩裸数字）",
        "old": "    timing_color, timing_label = _timing_tone(timing)",
        "new": '    timing_color, timing_label = TONE_BLUE, ""',
    },
]


def run_injections() -> int:
    caught = 0
    missed: list = []
    path = AWAKENING_PY
    for inj in INJECTIONS:
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
        except Exception as e:  # noqa: BLE001
            found = [f"守卫自身抛异常: {type(e).__name__}: {e}"]
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
    return caught


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        return 0 if run_injections() == len(INJECTIONS) else 1

    failures = _all_checks()
    if failures:
        print("❌ 觉醒页分数着色/口径守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 觉醒页分数着色/口径守卫全绿"
          "（风险温度反向 · 分数随值变色 · 判读齐全 · 枚举不外泄 · 流动性唯一口径 · 引擎真值优先）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
