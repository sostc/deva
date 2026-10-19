#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：认知页「叙事追踪」不许再变成看不见的一块，也不许再把数字读歪。

背景（2026-10-19）
----------------
认知页原来那块叫「💎 叙事价值发现」，实测是两个毛病叠在一起：

1. **空态是假的**：取数写 ``engine._news_mind._narrative_tracker``（多了个下划线），
   真名是 ``narrative_tracker``（``cognition/core.py``）。``getattr`` 带默认值
   ``None`` → 写错名字**不抛异常**，再被 ``except Exception: pass`` 一吞，卡片
   长年显示「叙事追踪器未就绪」。而追踪器其实一直在跑：NB 库
   ``naja_narrative_tracker_state`` 里躺着 10 条叙事状态，每分钟都在落库。
2. **名不副实**：它讲的是「供需 → 机会映射表 / 解决者追踪」，不是「市场在讲
   什么故事、热不热」。位置又在④深度分析、且常年空 → 被并进「等待数据的板块」
   状态带，等于整块不存在。

现在改成叙事榜（②思考节）：名称 / 阶段 / 热度 / 趋势 / 关键词 / 最近更新。
守卫钉六件事：

① UI 引用的 tracker 属性名必须在 ``NewsMindStrategy`` 里**真的存在**
   （getattr 带默认值 = 写错不报错，只能靠名字核对）；
② 趋势除零：``prev_count=0`` 时 trend 被算成 ``recent_count``（实测 376），
   必须显示「无可比」，不许上屏 ``+37600%``，也不许说成「新出现」；
   反向（真有 prev）不许误判；
③ 阶段饱和必须如实标注（实测 10 条全「高潮」是阈值 ≥8 次命中惹的）；
④ 空态三态：「两个实例都没拿到」≠「拿到了但 0 条」，且不许再用
   「未就绪」这种不含信息来源的模糊词；
⑤ 渲染位置在 **②思考节**（叙事是结论不是下钻），且卡片带风险色图例；
⑥ 有数据时榜上真的出现叙事名 / 阶段 / 热度。

用法
----
    python scripts/verify/verify_narrative_track.py
    python scripts/verify/verify_narrative_track.py --strict
    python scripts/verify/verify_narrative_track.py --exercise-injections
"""

from __future__ import annotations

import argparse
import ast
import importlib
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TRACK_PY = ROOT / "deva/naja/cognition/ui/components/narrative_track.py"
CORE_PY = ROOT / "deva/naja/cognition/core.py"
COG_UI_PY = ROOT / "deva/naja/cognition/ui/ui.py"

#: 旧版那句：既没说清是哪个实例、也没说清是没接入还是没数据。
VAGUE_WORD = "未就绪"


def _mod():
    """取被测模块 —— ❗必须 reload。

    注入会改磁盘上的源码，而 ``sys.modules`` 里是**第一次 import 时的对象**：
    不 reload 的话，第一条注入会把坏版本 load 进内存，之后每条注入都只是被
    这份坏对象的连带失败抓住（表现为所有注入的失败原因一模一样），
    看上去 N/N 全绿，其实每条对应的检查都没真正生效。
    """
    m = importlib.import_module("deva.naja.cognition.ui.components.narrative_track")
    return importlib.reload(m)


def _sample_rows():
    """合成叙事：形态照抄 NB 库里的真实快照（trend == recent_count 即 prev=0）。"""
    now = time.time()
    return [
        {
            "name": "医药", "stage": "高潮", "attention_score": 0.737,
            "recent_count": 52, "trend": 52.0, "last_updated": now - 30,
            "keywords": ["医疗", "试验", "药品"],
        },
        {
            "name": "流动性紧张", "stage": "高潮", "attention_score": 0.722,
            "recent_count": 376, "trend": 376.0, "last_updated": now - 300,
            "keywords": ["流动性", "融资"],
        },
        {
            "name": "贵金属", "stage": "高潮", "attention_score": 0.714,
            "recent_count": 57, "trend": 4.18, "last_updated": now - 7200,
            "keywords": ["金价"],
        },
    ]


class _FakeTracker:
    """形态照抄真实 NarrativeTracker：有 get_summary（字段全）"""

    def __init__(self, rows):
        self._rows = rows

    def get_summary(self, limit=10):
        return list(self._rows)[:limit]

    def get_active_narratives(self):
        return list(self._rows)


class _FallbackTracker:
    """只有 get_active_narratives 的老形态 —— 走回落路径不许变空。

    ❗真实形态是**没有 keywords / last_updated 字段**（这就是当初上屏
    「无关键词 · 从未更新」的原因），所以这里要把这两个字段剥掉再喂。
    """

    def __init__(self, rows):
        self._rows = rows

    def get_active_narratives(self):
        return [
            {k: v for k, v in r.items() if k not in ("keywords", "last_updated")}
            for r in self._rows
        ]

    def get_problem_opportunity_summary(self):
        return {"problems": [], "opportunities": [], "resolvers": []}

    def get_value_market_summary(self):
        return {
            "value_score": 0.42,
            "market_narrative_score": 0.31,
            "recommendation": "WATCH",
            "reason": "供需缺口尚未收敛",
        }


def _render(rows, *, tracker_ok=True, tracker_cls=_FakeTracker):
    """渲染叙事卡并捕获输出（❗守卫碰输出口必须 monkeypatch）。"""
    M = _mod()

    class _Mind:
        narrative_tracker = tracker_cls(rows) if tracker_ok else None

    class _UI:
        engine = type("E", (), {"_news_mind": _Mind()})()

    captured = {"html": "", "empty": []}
    orig_put = M.put_html
    orig_empty = M.report_empty
    M.put_html = lambda s: captured.__setitem__("html", captured["html"] + s)
    M.report_empty = lambda *a: captured["empty"].append(a)

    import deva.naja.cognition.narrative.tracker as T

    orig_get = T.get_narrative_tracker
    T.get_narrative_tracker = lambda: None
    try:
        M.render_narrative_track(_UI())
    finally:
        M.put_html = orig_put
        M.report_empty = orig_empty
        T.get_narrative_tracker = orig_get
    return captured


# ── ① tracker 属性名必须真的存在 ───────────────────────────────────────────────
def check_attribute_name() -> list:
    tree = ast.parse(TRACK_PY.read_text(encoding="utf-8"))
    referenced = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
            args = node.args
            if len(args) >= 2 and isinstance(args[1], ast.Constant) and isinstance(args[1].value, str):
                referenced.add(args[1].value)

    if not referenced:
        return ["组件里没找到 getattr(..., '属性名', None) —— 取数方式改了，守卫要跟着改"]

    core_tree = ast.parse(CORE_PY.read_text(encoding="utf-8"))
    defined = set()
    for node in ast.walk(core_tree):
        if isinstance(node, ast.ClassDef) and node.name == "NewsMindStrategy":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    for tgt in sub.targets:
                        if (isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name)
                                and tgt.value.id == "self"):
                            defined.add(tgt.attr)

    missing = referenced - defined
    if missing:
        return [
            f"UI 引用的 tracker 属性 {sorted(missing)} 在 NewsMindStrategy 里不存在 —— "
            "getattr 带默认值 None，写错名字不报错，卡片会静默变空"
        ]
    return []


# ── ② 趋势除零 ────────────────────────────────────────────────────────────────
def check_trend_no_divzero() -> list:
    M = _mod()
    failures: list = []

    # prev_count == 0 → trend == recent_count（实测 376）
    cell = M._trend_cell(376.0, 376)
    if "无可比" not in cell:
        failures.append("prev=0 时没有显示「无可比」—— 趋势会被读成 +37600%")
    if "新出现" in cell:
        failures.append("prev=0 被说成「新出现」—— 实测那批叙事并不新（持久化只留 50 条命中）")
    if "37600" in cell:
        failures.append(f"趋势直接上屏了除零结果：{cell}")

    # 反向：真有 prev 时不许被误判成「无可比」
    real = M._trend_cell(0.5, 57)
    if "无可比" in real or "50%" not in real:
        failures.append(f"真有上一窗口时被误判成「无可比」：{real}")

    down = M._trend_cell(-0.4, 57)
    if "↓" not in down or "40%" not in down:
        failures.append(f"降温趋势显示异常：{down}")

    # 上屏验收：整卡渲染里不许出现四位数百分比
    html = _render(_sample_rows())["html"]
    if re.search(r"[↑↓]\s*\d{4,}%", html):
        failures.append("渲染结果里出现了四位数百分比 —— 除零值漏到屏上了")
    if "无可比" not in html:
        failures.append("渲染结果里没有「无可比」")
    return failures


# ── ③ 阶段饱和如实标注 ───────────────────────────────────────────────────────
def check_saturation_note() -> list:
    M = _mod()
    rows = _sample_rows()

    failures: list = []

    note = M._saturation_note(rows)
    if "饱和" not in note or "阈值" not in note:
        failures.append("3 条叙事全同阶段时没有说明阈值饱和 —— 「全高潮」会被读成「都很热」")

    # 反向：阶段确实有区分度时不许乱标（2 条高潮 + 1 条萌芽 = 67%）
    varied = [dict(rows[0]), dict(rows[1], stage="萌芽")]
    if M._saturation_note(varied) != "":
        failures.append("阶段有区分度时仍然弹饱和提示 —— 提示变成常驻噪音")

    # ❗边界：判据是「同阶段占比 ≥80%」，不是「全部相同」。
    # 实测 15 条里有 1 条不同 —— 写死"全部相同"会让提示在真实数据上永远不出现。
    mostly = [dict(rows[0]) for _ in range(4)] + [dict(rows[0], stage="萌芽")]
    if "4/5 条" not in M._saturation_note(mostly):
        failures.append("4/5 条同阶段时没有提示（判据被写成「全部相同」了）")

    # 反方向：4 条里 3 条同（75%）还不够，不许提示
    borderline = [dict(rows[0]) for _ in range(3)] + [dict(rows[0], stage="萌芽")]
    if M._saturation_note(borderline) != "":
        failures.append("75% 同阶段也弹提示 —— 阈值写松了")
    return failures

    # 上屏验收
    if "阈值已饱和" not in _render(rows)["html"]:
        return ["渲染结果里看不到阈值饱和提示"]
    return []


# ── ④ 空态三态 ───────────────────────────────────────────────────────────────
def check_empty_states() -> list:
    failures: list = []

    # (a) 两个实例都拿不到 —— 真故障，必须说清是哪两个
    no_instance = _render([], tracker_ok=False)["empty"]
    if not no_instance:
        return ["两个 tracker 都拿不到时没有任何空态输出（整块消失）"]
    text_a = " ".join(str(x) for x in no_instance[0])
    if "叙事追踪" not in text_a or "都没拿到" not in text_a:
        failures.append(f"「拿不到实例」的空态文案不达意：{text_a}")

    # (b) 拿到了但 0 条 —— 这是"真没数据"，文案必须和 (a) 不同
    zero = _render([], tracker_ok=True)
    if not zero["empty"]:
        failures.append("tracker 在但 0 条叙事时没有空态输出")
    else:
        text_b = " ".join(str(x) for x in zero["empty"][0])
        if "活跃叙事" not in text_b:
            failures.append(f"「有实例但 0 条」的空态文案不达意：{text_b}")
        if text_b == text_a:
            failures.append("两种空态文案一模一样 —— None 和 [] 被当成一回事")

    # (c) 全程不许出现不含来源信息的模糊词
    for label, cap in (("没实例", text_a), ("0 条", zero["empty"])):
        blob = " ".join(str(x) for x in cap) if isinstance(cap, list) else str(cap)
        if VAGUE_WORD in blob:
            failures.append(f"{label} 的空态又用了「{VAGUE_WORD}」—— 看不出是没接入还是没数据")
    return failures


# ── ⑤ 位置在②思考节 + 带风险色图例 ──────────────────────────────────────────
def check_placement_and_legend() -> list:
    failures: list = []
    src = COG_UI_PY.read_text(encoding="utf-8")

    # ❗锚点要取 render_section 那一行里的 id，不能取顶部 render_anchor_nav：
    # 导航区里五个 id 全都出现过，用它当界碑会把 "sec-memory" 定位到文件前部。
    thinking = src.find('"sec-thinking", "💡", "思考"')
    if thinking < 0:
        return ["认知页找不到②思考节的分节抬头 —— 版式骨架改了，守卫要跟着改"]

    call_insight = src.find("render_insight(self)")
    call = src.find("render_narrative_track(self)")
    call_semantic = src.find("render_semantic(self)")
    if call < 0:
        return ["认知页没有渲染叙事追踪卡 —— 内容又消失了"]
    if not (thinking < call):
        failures.append(
            "叙事追踪卡不在②思考节 —— 它是「系统认定市场在讲什么」的结论，"
            "不是要下钻的分析"
        )
    # 紧跟洞察：叙事是洞察里那堆无排序 pill 的"有量纲版本"，两者要挨着
    if not (call_insight < call < call_semantic):
        failures.append(
            "叙事追踪卡没有紧跟洞察卡（应在 render_insight 与 render_semantic 之间）"
        )

    html = _render(_sample_rows())["html"]
    if "红 = 危险" not in html:
        failures.append("卡片用了红/绿阶段徽标却没有风险色图例 —— 会被按股价涨跌读反")
    return failures


# ── ⑥ 有数据时榜上真有内容 ───────────────────────────────────────────────────
def check_board_content() -> list:
    html = _render(_sample_rows())["html"]
    failures: list = []
    for token in ("医药", "流动性紧张", "高潮", "0.74", "0.72"):
        if token not in html:
            failures.append(f"叙事榜上看不到 {token} —— 卡片空转")
    if "医疗" not in html:
        failures.append("叙事榜上看不到关键词")
    if "分钟前" not in html and "秒前" not in html:
        failures.append("叙事榜上看不到最近更新时间")
    if "来源" not in html:
        failures.append("卡片没有标明数据来自哪个 tracker 实例")

    # 回落路径：tracker 只有 get_active_narratives（没有 keywords/last_updated）
    fb = _render(_sample_rows(), tracker_cls=_FallbackTracker)["html"]
    if "医药" not in fb:
        failures.append("只有 get_active_narratives 的老形态 tracker 渲染不出内容 —— 回落路径断了")
    if "无关键词" not in fb:
        failures.append("关键词缺失时没有可见占位（会变成一块空白）")
    return failures


def _all_checks() -> list:
    failures: list = []
    failures += check_attribute_name()
    failures += check_trend_no_divzero()
    failures += check_saturation_note()
    failures += check_empty_states()
    failures += check_placement_and_legend()
    failures += check_board_content()
    return failures


# ── 负向注入：证明守卫真的在守 ────────────────────────────────────────────────
#: ❗锚点全部钉在**真被执行**的分支上，且每条都必须唯一命中。
INJECTIONS = [
    {
        "name": "属性名写回 _narrative_tracker（getattr 带默认值 → 静默变空卡）",
        "path": TRACK_PY,
        "old": 'getattr(ui.engine._news_mind, "narrative_tracker", None)',
        "new": 'getattr(ui.engine._news_mind, "_narrative_tracker", None)',
    },
    {
        "name": "去掉趋势除零保护（376 上屏成 +37600%）",
        "path": TRACK_PY,
        "old": "    if t > 0 and recent > 0 and abs(t - recent) < 1e-6:",
        "new": "    if False:",
    },
    {
        "name": "去掉阶段饱和提示（10 条全高潮却不解释）",
        "path": TRACK_PY,
        "old": "    if hit / len(rows) < 0.8:\n        return \"\"",
        "new": "    if True:\n        return \"\"",
    },
    {
        "name": "空态退回模糊词「未就绪」（看不出没接入还是没数据）",
        "path": TRACK_PY,
        "old": '"📖", "叙事追踪", "两个 tracker 实例都没拿到",',
        "new": '"📖", "叙事追踪", "叙事追踪器未就绪",',
    },
    {
        "name": "两种空态合并成一句（None 与 [] 不分）",
        "path": TRACK_PY,
        "old": '        have_instance = any(t is not None for _, t in trackers)',
        "new": "        have_instance = False",
    },
    {
        "name": "叙事卡搬回④深度分析（结论区之外的角落）",
        "path": COG_UI_PY,
        "old": "        render_narrative_track(self)\n        render_semantic(self)",
        "new": "        render_semantic(self)\n        render_narrative_track(self)",
    },
    {
        "name": "去掉风险色图例（红绿阶段徽标被读反）",
        "path": TRACK_PY,
        "old": "        + legend_bar()\n",
        "new": "        + \"\"\n",
    },
]


def run_injections() -> int:
    caught = 0
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
        if found:
            caught += 1
            print(f"  ✅ 被捕获（{len(found)} 项）")
            # ❗打印全部而不是第一条：所有注入都报同一句 = 检查之间互相掩盖
            for f in found[:4]:
                print(f"       · {f[:110]}")
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
        ok = run_injections() == len(INJECTIONS)
        return 0 if ok else 1

    failures = _all_checks()
    if failures:
        print("❌ 叙事追踪守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 叙事追踪守卫全绿"
          "（属性名存在 · 趋势除零 · 饱和标注 · 空态三态 · ②思考节+图例 · 榜上有内容）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
