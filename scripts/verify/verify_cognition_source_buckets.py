#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：认知页「事件来源」分桶不许恒为 0。

背景（2026-10-19）
----------------
/cognition 的事件流卡片左边写「事件来源（98 种活跃）」，右边三行却是
``新闻事件 0 / 行情 0 / 认知 0``，屏上自相矛盾，而人只会把它读成「没有事件」。

真凶不是没数据：``insight['source']`` 的实际取值是
``strategy:<策略名>``、``hotspot``、``llm_reflection:refl_1781357512835``、
``attention_os.make_decision`` 这类「来源类型 + 实例 id」的串，
NB 库实测 198 个互不相同的值。而旧实现拿 ``DATA_SOURCES = {news, market, cognitive}``
去**全等**匹配，一个都命中不了 —— 计数恒 0，但页面依旧显示「98 种活跃」。

这类错**不抛异常、不报错**，只是安静地把「有事件」显示成「没事件」。
所以必须钉死三件事：

① 分桶必须按前缀推导，且真实取值都要落到预期桶；
② 「有多少种来源」与「每个桶多少条」必须自洽（总数 = 明细之和）；
③ 未知前缀不许被吞进 ``other`` —— 吞掉就等于又制造一次「看不见的数据」。

用法
----
    python scripts/verify/verify_cognition_source_buckets.py
    python scripts/verify/verify_cognition_source_buckets.py --strict
    python scripts/verify/verify_cognition_source_buckets.py --exercise-injections
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVENT_BUS_PY = ROOT / "deva/naja/cognition/ui/components/event_bus.py"
MODULE_NAME = "deva.naja.cognition.ui.components.event_bus"

#: NB 库实测的真实 source 取值 → 期望落到的桶。
#: 这些不是编的：`select distinct source from insight pool` 里就是这些形态。
REAL_SOURCES = {
    "llm_reflection:refl_1781357512835": "llm_reflection",
    "llm_reflection:refl_1781357512836": "llm_reflection",
    "strategy:merrill_clock": "strategy",
    "strategy:news_sentiment": "strategy",
    "hotspot": "hotspot",
    "attention_os.make_decision": "attention_os.make_decision",
    "insight_engine": "insight_engine",
    "news": "news",
    "bandit": "bandit",
    "radar:scan": "radar",
}

#: 旧的写死白名单：只认这三个值，任何带实例 id 的串都命不中
LEGACY_DATA_SOURCES = ("news", "market", "cognitive")


def _mod():
    return importlib.import_module(MODULE_NAME)


def _reload():
    importlib.reload(_mod())


def _src() -> str:
    return EVENT_BUS_PY.read_text(encoding="utf-8")


# ── ① 真实取值必须落到预期桶 ──────────────────────────────────────────────────
def check_real_sources_bucket() -> list:
    E = _mod()
    failures: list = []
    for source, expected in REAL_SOURCES.items():
        got = E._bucket_of(source)
        if got != expected:
            failures.append(f"source={source!r} 应分到 {expected!r}，实得 {got!r}")
    return failures


# ── ② 分桶与总数必须自洽，且已知桶不许全 0 ────────────────────────────────────
def check_counts_self_consistent() -> list:
    E = _mod()
    failures: list = []

    sources = list(REAL_SOURCES.keys())
    counts = {}
    for s in sources:
        b = E._bucket_of(s)
        counts[b] = counts.get(b, 0) + 1

    if sum(counts.values()) != len(sources):
        failures.append(f"分桶总数 {sum(counts.values())} != 来源数 {len(sources)}（有数据被吞）")

    # 真实数据里最常见的两类，绝不允许为 0
    for must in ("llm_reflection", "strategy"):
        if counts.get(must, 0) <= 0:
            failures.append(f"桶 {must} 计数为 0 —— 正是「有 98 种却全是 0」的复现")

    # 已知前缀必须都能在 _BUCKET_META 里拿到中文名，否则会显示成裸英文
    for bucket in counts:
        name, _icon, _color = E._bucket_style(bucket)
        if name == bucket:
            failures.append(f"桶 {bucket} 没有中文名（会原样显示英文前缀）")
    return failures


# ── ③ 未知前缀不许被吞 ────────────────────────────────────────────────────────
def check_unknown_prefix_not_swallowed() -> list:
    E = _mod()
    failures: list = []

    for source, expected in (
        ("brand_new_source:abc", "brand_new_source"),
        ("some_plugin.v2", "some_plugin"),
        # ❗必须有一条「既不在 _BUCKET_META、也不带任何分隔符」的：
        # 带分隔符的串靠前缀分支就能落桶，兜底 return 根本走不到，
        # 少了这一条，把兜底改成 other 也抓不出来（会漏掉「整类来源消失」）。
        ("standalone_source", "standalone_source"),
    ):
        got = E._bucket_of(source)
        if got != expected:
            failures.append(f"未知前缀 {source!r} 应保留为 {expected!r}，实得 {got!r}")
        if got in LEGACY_DATA_SOURCES + ("other", "unknown"):
            failures.append(f"未知前缀 {source!r} 被吞进 {got!r} —— 数据会凭空消失")
    return failures


# ── ④ 白名单不得复活 ──────────────────────────────────────────────────────────
def check_no_legacy_whitelist() -> list:
    src = _src()
    failures: list = []

    # ❗不能用裸子串判：本文件的 docstring 就在讲「旧实现把 DATA_SOURCES 写死」，
    # 裸 in 会把说明文字判成违规。按「行首是赋值」判。
    assign_lines = [
        ln for ln in src.splitlines()
        if ln.lstrip().startswith("DATA_SOURCES")
    ]
    if assign_lines:
        failures.append(
            "又出现 DATA_SOURCES 白名单赋值 —— 它按全等匹配，带实例 id 的 source 永远命不中"
        )
    if "_bucket_of" not in src:
        failures.append("找不到 _bucket_of（分桶函数被删/改名，本守卫锚点失效）")
    return failures


# ── ⑤ 真正渲染一次：屏上不许出现「已知桶 = 0」 ────────────────────────────────
def check_render_counts() -> list:
    E = _mod()
    failures: list = []

    captured: list = []
    original = E.put_html
    E.put_html = lambda html: captured.append(html)  # 绝不真起会话
    try:
        insights = [
            {"source": "llm_reflection:refl_1", "theme": "AI 叙事", "ts": 1, "user_score": 0.6},
            {"source": "llm_reflection:refl_2", "theme": "美林时钟", "ts": 2, "user_score": 0.6},
            {"source": "strategy:merrill_clock", "theme": "周期", "ts": 3, "user_score": 0.5},
            {"source": "attention_os.make_decision", "theme": "决策", "ts": 4, "user_score": 0.5},
            {"source": "brand_new_source:zzz", "theme": "未知来源", "ts": 5, "user_score": 0.5},
        ]
        entry = E._fetch_insight_data
        E._fetch_insight_data = lambda: (
            {b: sum(1 for i in insights if E._bucket_of(i["source"]) == b)
             for b in {E._bucket_of(i["source"]) for i in insights}},
            {},
            insights,
        )
        try:
            E.render_event_bus(None)
        finally:
            E._fetch_insight_data = entry
    finally:
        E.put_html = original

    html = "".join(captured)
    if not html:
        failures.append("render_event_bus 没有输出任何 HTML（渲染路径断了）")
        return failures

    if "5 条" not in html:
        failures.append("事件流没有显示总条数 5（「有几条」必须自己说得清）")
    if "LLM 反思" not in html:
        failures.append("LLM 反思桶没有出现在屏上")
    if "决策中心" not in html:
        failures.append("attention_os.make_decision 没有映射到「决策中心」")
    if "brand_new_source" not in html:
        failures.append("未知前缀被吞了（屏上看不到它，等于数据消失）")
    return failures


def _all_checks() -> list:
    failures: list = []
    failures += check_real_sources_bucket()
    failures += check_counts_self_consistent()
    failures += check_unknown_prefix_not_swallowed()
    failures += check_no_legacy_whitelist()
    failures += check_render_counts()
    return failures


# ── 负向注入：证明守卫真的在守 ────────────────────────────────────────────────
INJECTIONS = [
    {
        "name": "分桶退回写死白名单（带实例 id 的 source 全部命不中）",
        "old": '    for sep in (":", "."):\n        if sep in s:\n            return s.split(sep, 1)[0]\n    return s',
        "new": '    return s if s in ("news", "market", "cognitive") else "other"',
    },
    {
        "name": "只按点号切分（冒号来源整串进桶，98 种变 98 个桶）",
        "old": '    for sep in (":", "."):',
        "new": '    for sep in (".",):',
    },
    {
        "name": "未知前缀吞进 other",
        "old": "    return s\n\n\ndef _get_insight_pool():",
        "new": '    return "other"\n\n\ndef _get_insight_pool():',
    },
    {
        "name": "决策中心映射被删（attention_os.make_decision 回落成 attention_os）",
        "old": '    "attention_os.make_decision": ("决策中心", "🧭", "#6366f1"),\n',
        "new": "",
    },
]


def run_injections() -> int:
    caught = 0
    missed: list = []
    path = EVENT_BUS_PY
    for inj in INJECTIONS:
        original = path.read_text(encoding="utf-8")
        hits = original.count(inj["old"])
        if hits != 1:
            missed.append(inj["name"])
            print(f"❌ 注入锚点命中 {hits} 次（期望 1，守卫腐烂信号）：{inj['name']}")
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
        ok = run_injections() == len(INJECTIONS)
        return 0 if ok else 1

    failures = _all_checks()
    if failures:
        print("❌ 认知事件来源分桶守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 认知事件来源分桶守卫全绿"
          "（真实 source 落桶 · 总数自洽 · 未知前缀不吞 · 白名单未复活 · 渲染可见）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
