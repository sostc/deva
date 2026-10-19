#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：认知页搬出去的两块，不许被悄悄搬回来，也不许在新家接断。

背景（2026-10-19）
----------------
认知页原本 18 个卡片平铺、9,420px，其中两块属于**放错家**：

  * **金十实时快讯**（268px）—— 它是未经消化的原始新闻流，不是认知层的产出。
    认知页「概览」问的是「系统此刻看到了什么/得出了什么」，放一条外部快讯流
    在这里会被读成认知结论。→ 搬去 ``/news``（``news/jin10.py``）
  * **供应链-叙事联动**（172px）—— 它是供应链视图的另一半，不是认知结论。
    ``/supplychain`` 原本只有静态知识图谱，缺的正是「叙事这一侧现在发生了什么」。
    → 搬去 ``/supplychain``（``attention/ui/supply_chain/linkage.py``）

搬移有一类特别隐蔽的坏法：**代码还在，但没人调**。页面照样 200，那两块内容
安静地消失，没有异常、没有日志。第二类是**配色搬错**：认知页强制深色底
（``body.webio-theme-default !important``），而 ``/news`` 是白底 —— 深色卡
原样搬过去就是白底白字，整块看不见（本项目的「假正常」老毛病）。

所以钉四件事：

① 金十面板搬过去后**必须是浅色配色**（白底上不许出现深色主题的字色）；
② 金十条目的「标题 + 正文同句」折叠仍然有效（否则每条多 18px 纯重复）；
③ ``/supplychain`` 真的调了联动面板，且有数据/无数据两条路都出得了内容；
④ 认知页既不许再直接渲染这两块，也必须保留通往新家的入口（搬走 ≠ 够不着）。

用法
----
    python scripts/verify/verify_cognition_module_homes.py
    python scripts/verify/verify_cognition_module_homes.py --strict
    python scripts/verify/verify_cognition_module_homes.py --exercise-injections
"""

from __future__ import annotations

import argparse
import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

JIN10_PY = ROOT / "deva/naja/news/jin10.py"
LINKAGE_PY = ROOT / "deva/naja/attention/ui/supply_chain/linkage.py"
GRAPH_PY = ROOT / "deva/naja/attention/ui/supply_chain/graph.py"
COG_UI_PY = ROOT / "deva/naja/cognition/ui/ui.py"
COG_COMPONENTS = ROOT / "deva/naja/cognition/ui/components"

#: 深色主题专用字色 —— 搬到白底的页面上一律看不见。
#: 只收「在白底上必然不可读」的那几个，别把 #94a3b8 也收进来（它是浅灰，能用）。
DARK_ONLY_COLORS = ("#e2e8f0", "#cbd5e1", "#f1f5f9", "#f8fafc")

#: 合成用例：标题够长（>24 字），这样「标题截断 50 / 正文截断 80」都会保留全文，
#: 「同一句话排两行」才会真的在上屏出现两次。
LONG_TITLE = "测试用长标题：流动性信号持续缺失但风险偏好回升的完整描述用于验证去重"


def _jin10():
    return importlib.import_module("deva.naja.news.jin10")


def _linkage():
    return importlib.import_module("deva.naja.attention.ui.supply_chain.linkage")


def _render_jin10(events) -> str:
    """用合成数据渲染金十面板（不碰事件总线、不碰文件缓存）。"""
    M = _jin10()
    original = M.get_jin10_important_events
    M.get_jin10_important_events = lambda limit=15: list(events)
    try:
        return M.render_jin10_fragment()
    finally:
        M.get_jin10_important_events = original


def _sample_events():
    return [
        {
            "title": LONG_TITLE,
            "text": LONG_TITLE,          # 金十真实形态：text 就是 title 的完整版
            "url": "https://www.jin10.com/news/1",
            "timestamp": 1,
            "datetime": "2026-10-19 21:00:00",
        },
        {
            "title": "芝商所将推出钨期货",
            "text": "芝商所将推出钨期货，最迟于 2027 年第一季度初开始交易",
            "url": "",
            "timestamp": 2,
            "datetime": "2026-10-19 18:10:52",
        },
    ]


# ── ① 搬过去后必须是浅色配色 ──────────────────────────────────────────────────
def check_jin10_is_light_theme() -> list:
    failures: list = []
    html = _render_jin10(_sample_events())
    if "金十重要事件" not in html:
        failures.append("金十面板没有标题 —— 渲染路径断了")
        return failures

    # ❗只判**字色**，不判边框/底色：`#e2e8f0` 当边框色（白底上的浅灰线）是
    # 正当用法，裸子串扫会把它误判成「深色字」。这里只取 ``color: #xxxxxx``。
    text_colors = set(re.findall(r"(?<![-\w])color:\s*(#[0-9a-fA-F]{6})", html))
    bad = text_colors & {c.lower() for c in DARK_ONLY_COLORS}
    if bad:
        failures.append(
            f"金十面板的字色用了深色主题色 {sorted(bad)} —— /news 是白底，这块会看不见"
        )

    # 空态也要能用（没有快讯时不许整块消失）
    empty_html = _render_jin10([])
    if "暂无金十重要事件" not in empty_html:
        failures.append("无快讯时没有诚实空态（不能安静地什么都不输出）")
    return failures


# ── ② 「标题 + 正文同句」必须仍然只排一行 ────────────────────────────────────
def check_jin10_no_duplicated_line() -> list:
    html = _render_jin10(_sample_events())
    head = LONG_TITLE[:24]
    times = html.count(head)
    if times != 1:
        return [
            f"同一条快讯的标题在屏上出现 {times} 次（期望 1）—— "
            "text 是 title 的完整版时排两行，每条白占 18px"
        ]
    # 反向：正文确实**不同**的内容不许被误删（否则就是真丢信息）
    if "最迟于 2027 年第一季度初开始交易" not in html:
        return ["正文与标题不同的那条，正文被误删了 —— 去重条件写宽了"]
    return []


# ── ③ /supplychain 真的调了联动面板，两条路都出内容 ──────────────────────────
def check_linkage_wired() -> list:
    failures: list = []
    src = GRAPH_PY.read_text(encoding="utf-8")
    if "build_supply_chain_linkage_html" not in src:
        failures.append(
            "/supplychain 页没有调用 build_supply_chain_linkage_html —— "
            "联动面板成了没人调的孤儿代码，内容等于消失"
        )
    if 'put_html("".join(html_parts))' not in src:
        failures.append("供应链页不再是「拼完一次性输出」—— 一份 HTML 不许拆多次 put_html")

    M = _linkage()

    # 有数据
    class _FakeLinker:
        def get_hot_narratives(self, n):
            return [("AI算力", 2.0), ("国产替代", 1.2)]

        def get_recent_events(self, n):
            return []

        def get_supply_chain_summary(self):
            return {"total_narratives": 19, "total_stocks_mapped": 28, "recent_events_count": 0}

    original = M._get_linker
    M._get_linker = lambda: _FakeLinker()
    try:
        html = M.build_supply_chain_linkage_html()
    finally:
        M._get_linker = original

    if "供应链-叙事联动" not in html:
        failures.append("有数据时联动面板没有标题")
    if "最热叙事" not in html or "AI算力" not in html:
        failures.append("有数据时看不到最热叙事 —— 面板空转")

    # 无数据 / 引擎挂了
    def _boom():
        raise RuntimeError("linker 不可用")

    M._get_linker = _boom
    try:
        empty = M.build_supply_chain_linkage_html()
    finally:
        M._get_linker = original
    if "等待供应链数据" not in empty:
        failures.append("linker 挂了时没有诚实空态（会整块消失）")
    return failures


# ── ④ 认知页：不许再直接渲染，但必须留入口 ───────────────────────────────────
def check_cognition_home() -> list:
    failures: list = []
    src = COG_UI_PY.read_text(encoding="utf-8")

    for gone in ("render_jin10_events", "render_supply_chain_knowledge_graph_page"):
        if gone in src:
            failures.append(f"认知页又在直接渲染 {gone} —— 搬出去的内容被搬回来了")

    if (COG_COMPONENTS / "jin10_events.py").exists():
        failures.append(
            "cognition/ui/components/jin10_events.py 又出现了 —— 同一块内容两个实现，"
            "迟早只改一处"
        )

    # ❗判据不能是裸的 "/news"：ui.py 的**模块 docstring 里就写着** `/news`，
    # 裸子串会被说明文字蒙过去（本项目已被坑过）。这里钉实际调用行的 href，
    # 且两块入口分别在两个文件里：金十在 ui.py、供应链在 supply_chain.py。
    if 'href="/news"' not in src:
        failures.append("认知页缺少通往 /news 的入口卡（金十快讯会变得够不着）")
    supply_src = (COG_COMPONENTS / "supply_chain.py").read_text(encoding="utf-8")
    if 'href="/supplychain"' not in supply_src:
        failures.append("认知页缺少通往 /supplychain 的入口卡（供应链联动会变得够不着）")
    return failures


def _all_checks() -> list:
    failures: list = []
    failures += check_jin10_is_light_theme()
    failures += check_jin10_no_duplicated_line()
    failures += check_linkage_wired()
    failures += check_cognition_home()
    return failures


# ── 负向注入：证明守卫真的在守 ────────────────────────────────────────────────
#: ❗锚点全部落在**真被执行**的分支上：改配色要改实际输出那一句、
#: 去掉重要去重要删真正把 text 清空的那行、拆接线要删真正调用那行。
INJECTIONS = [
    {
        "name": "金十面板字色改回深色主题（白底上变成看不见的一块）",
        "path": JIN10_PY,
        "old": "color:#0f172a;line-height:1.5;",
        "new": "color:#e2e8f0;line-height:1.5;",
    },
    {
        "name": "去掉「标题与正文重叠」折叠（每条白占 18px）",
        "path": JIN10_PY,
        "old": "        if full_text and full_title:\n            head_n = min(len(full_title), 24)",
        "new": "        if False and full_text and full_title:\n            head_n = min(len(full_title), 24)",
    },
    {
        "name": "去重写宽：正文整条丢掉（「标题 + 补充」的补充被吃掉）",
        "path": JIN10_PY,
        "old": '                full_text = tail if len(tail) >= 4 else ""',
        "new": '                full_text = ""',
    },
    {
        "name": "/supplychain 不再接联动面板（代码变孤儿）",
        "path": GRAPH_PY,
        "old": "        html_parts.append(build_supply_chain_linkage_html())",
        "new": "        pass",
    },
    {
        "name": "认知页删掉通往 /news 的入口（内容凭空消失）",
        "path": COG_UI_PY,
        "old": '            href="/news",',
        "new": '            href="/cognition",',
    },
    {
        "name": "供应链入口卡删掉通往 /supplychain 的链接",
        "path": COG_COMPONENTS / "supply_chain.py",
        "old": '        href="/supplychain",',
        "new": '        href="/cognition",',
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
        print("❌ 认知页模块归属守卫 失败：")
        for f in failures:
            print(f"   - {f}")
        return 1 if args.strict else 0
    print("✅ 认知页模块归属守卫全绿"
          "（金十浅色·不排重复行 · 联动接线两条路 · 认知页不再渲染且留入口）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
