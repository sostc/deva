#!/usr/bin/env python3
"""验证「新闻去重（同一事件折叠）」——把同一件事的多条记录折成一条，只留条数。

守的是什么
----------
金十每发一条快讯，会有**中文原版 + 英文翻译版**两条独立记录（时间相隔
4~16 秒、id 不同），都进新闻池。托盘的 12 个名额实测近一半被这种成对重复
吃掉；「今日新闻消化」面板同理。

旧去重的判据是**标题字符串完全相同**，在这批数据上命中率为 0
（``scanned 101 == deduped 101``，一条都没去掉且不报错）——典型静默。
本守卫守的是新判据（``deva/naja/news/dedup.py``）以及它接线的三处呈现。

覆盖什么
--------
① **L3 中英一对一**：5 秒内合、40 秒外不合、一个英文只折一条中文（防链式传染）
② **L1 精确**：去序号/标点后同名合、隔 7 小时不合（防止把固定栏目当重复）
③ **L2 包含**：截断版合、跨语言前缀相同不合
④ **代表条**：中文优先；判定取最强证据（英文命中持仓时，文本仍是中文）
⑤ **不误伤**：两条中文不同内容不合；板块异动不参与折叠
⑥ **接线**：triage 的 stats 有 ``merged``；托盘折叠发生在配额**之前**；
   ``/market`` 旧路径行为不变
⑦ **性能**：1000 条 < 500ms（纯本地纯整数运算）
⑧ **静态守卫**：triage 真的调 dedup；托盘/面板真的读 ``dup_count``；
   SimHash 默认关
⑨ **注入自证**：``--exercise-injections`` 把每条护栏逐个打断，必须被抓到

跑法
----
    cd <项目根>
    /Users/spark/.local/bin/python3 scripts/verify/verify_news_dedup.py
    /Users/spark/.local/bin/python3 scripts/verify/verify_news_dedup.py --strict
    /Users/spark/.local/bin/python3 scripts/verify/verify_news_dedup.py --exercise-injections

退出码：0 = PASS；``--strict`` 下有违约则 1。
本脚本**只读**生产数据；``--exercise-injections`` 会临时改源码，结束时还原。
"""

from __future__ import annotations

import argparse
import importlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

NEWS_DIR = ROOT / "deva" / "naja" / "news"
DEDUP_PY = NEWS_DIR / "dedup.py"
TRIAGE_PY = NEWS_DIR / "triage.py"
TIMELINE_PY = (ROOT / "deva" / "naja" / "market_hotspot" / "ui_components"
               / "timeline" / "market_24h_timeline.py")
TRAY_PY = ROOT / "deva" / "naja" / "infra" / "ui" / "menu_bar_tray.py"
DIGEST_PY = NEWS_DIR / "digest.py"
PAGE_PY = NEWS_DIR / "page.py"

#: 注入验证时静默（只报被抓住的注入，不刷屏）
_QUIET = False
_FAILS: list = []


def _section(title: str) -> None:
    """分组标题。注入自证时静音——那时只需要看哪条注入被抓住。"""
    if not _QUIET:
        print(title)


def check(name: str, ok: bool, detail: str = "") -> bool:
    if not ok:
        _FAILS.append(name)
    if not _QUIET:
        print(f"  {'✅' if ok else '❌'} {name}" + (f"  —— {detail}" if detail else ""))
    return ok


def _reload_chain() -> None:
    """注入后必须整条链 reload —— ``triage`` 用 ``from .dedup import``
    拿的是**模块对象里的符号**，只 reload dedup 它仍指向旧函数（假通过）。"""
    for name in (
        "deva.naja.news.dedup",
        "deva.naja.news.triage",
        "deva.naja.news.digest",
        "deva.naja.news",
        "deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline",
    ):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "__file__", None):
            importlib.reload(mod)


# ─────────────────────────────────────────────────────────────
# 用例数据（确定性，不读真实新闻池）
# ─────────────────────────────────────────────────────────────

ZH_UKRAINE = (
    "【美恢复对乌情报分享星盾仍受限】金十数据10月19日讯，"
    "当地时间10月18日，乌克兰总统泽连斯基表示美国已恢复情报分享"
)
EN_UKRAINE = "U.S. resumes intelligence sharing with Ukraine; 'Starshield' service remains suspended"


def _run_checks() -> None:
    # 故意在函数内 import：注入验证时模块会被 reload，这里每次调用都重新绑定
    from deva.naja.news.dedup import (
        collapse, detect_lang, format_dup_suffix, normalize_title,
    )
    from deva.naja.news.focus import NewsFocusState
    from deva.naja.news.triage import NewsTriage

    # ── ① L3 中英一对一 ────────────────────────────────────────────
    _section("\n① L3 中英一对一：按发布时间的结构配对，不靠标题相似度")
    got, st = collapse([
        {"title": ZH_UKRAINE, "timestamp": 1000.0},
        {"title": EN_UKRAINE, "timestamp": 1005.0},
    ])
    check("相隔 5 秒的中英两版 → 折成 1 条", len(got) == 1 and st["by_rule"]["L3"] == 1,
          f"out={len(got)} rules={st['by_rule']}")
    check("折叠后带条数 dup_count=2", got and got[0]["dup_count"] == 2,
          f"dup={got[0]['dup_count'] if got else None}")

    got, _ = collapse([
        {"title": ZH_UKRAINE, "timestamp": 1000.0},
        {"title": EN_UKRAINE, "timestamp": 1040.0},
    ])
    check("相隔 40 秒 → 不合并（窗口 20s，宁可漏合不可错合）", len(got) == 2,
          f"out={len(got)}")

    # 一对一：一个英文 + 两个中文，只有时间最近的该被折
    got, _ = collapse([
        {"title": "【央行开展逆回购操作】央行今日开展7天期逆回购操作，净投放500亿元", "timestamp": 2000.0},
        {"title": "【财政部发布会】财政部介绍近期财政收支情况与政策安排", "timestamp": 2008.0},
        {"title": "PBOC conducts 7-day reverse repo, net injection 50 billion yuan", "timestamp": 2006.0},
    ])
    check("一个英文只折一条中文（缺一对一约束会链式传染成 1 条）",
          len(got) == 2, f"out={len(got)}")

    # ── ② L1 精确 ──────────────────────────────────────────────────
    _section("\n② L1 精确：序号/标点/金十模板语不同也算同一条")
    got, st = collapse([
        {"title": "1. 英伟达辟谣 RTX 5090 停产：只是产能不足", "timestamp": 1000.0},
        {"title": "英伟达辟谣 RTX 5090 停产：只是产能不足。", "timestamp": 1300.0},
    ])
    check("同标题（序号+句号不同）→ 合并", len(got) == 1 and st["by_rule"]["L1"] == 1,
          f"out={len(got)} rules={st['by_rule']}")
    check("归一化确实吃掉了序号与模板语",
          normalize_title("1. 英伟达辟谣") == normalize_title("英伟达辟谣。"),
          normalize_title("1. 英伟达辟谣"))

    got, _ = collapse([
        {"title": "本周重要事件与数据预告", "timestamp": 1000.0},
        {"title": "本周重要事件与数据预告", "timestamp": 1000.0 + 7 * 3600},
    ])
    check("同标题但隔 7 小时 → 不合并（固定栏目不是重复推送）", len(got) == 2,
          f"out={len(got)}")

    # ── ③ L2 包含 ──────────────────────────────────────────────────
    _section("\n③ L2 前缀包含：截断版 / 追加版")
    got, st = collapse([
        {"title": "【A股午评：创业板指探底回升跌1.07% 工商银行股价再创新高】金十数据10月19日讯，三大股指早盘低开低走",
         "timestamp": 3000.0},
        {"title": "【A股午评：创业板指探底回升跌1.07% 工商银行股价再创新高】金十数据10月19日讯，三大股指早盘低开低走，创业板指一度跌超2%",
         "timestamp": 3060.0},
    ])
    check("长标题含短标题（同语言）→ 合并", len(got) == 1,
          f"out={len(got)} rules={st['by_rule']}")
    got, _ = collapse([
        {"title": "【国家统计局：前三季度内需对经济增长贡献率超过七成】金十数据10月19日讯，统计局发言人表示内需贡献率提升",
         "timestamp": 4000.0},
        {"title": "【国家统计局：前三季度内需逐步改善】金十数据10月19日讯，统计局发言人表示消费在恢复",
         "timestamp": 4004.0},
    ])
    check("同主题但不同要点的两条（开头相同、后续分叉）→ 不许合",
          len(got) == 2, f"out={len(got)}")

    # ── ④ 代表条：中文优先 + 判定取最强证据 ────────────────────────
    _section("\n④ 代表条：文本取中文、判定取最强证据")
    got, _ = collapse([
        {"title": EN_UKRAINE, "timestamp": 1005.0},
        {"title": ZH_UKRAINE, "timestamp": 1000.0},
    ])
    check("中英两版 → 代表条是中文", got and got[0]["title"] == ZH_UKRAINE,
          (got[0]["title"][:30] if got else ""))
    check("语言判定：中文夹英文公司名仍算 zh",
          detect_lang("英伟达发布 NVDA 新一代芯片") == "zh",
          detect_lang("英伟达发布 NVDA 新一代芯片"))

    focus = NewsFocusState(holdings=("英伟达", "NVDA"), watchlist=("越南",))
    result = NewsTriage(focus).analyze([
        {"title": "【台积电上调资本开支】台积电宣布上调今年资本开支",
         "importance_score": 0.60, "timestamp": 2000.0, "sentiment": 0.7},
        {"title": "TSMC raises capex guidance; NVDA supply to improve",
         "importance_score": 0.62, "timestamp": 2005.0, "sentiment": 0.7},
    ], per_group_limit=10)
    holding = result["groups"]["holding"]
    check("英文版命中持仓、中文版不命中 → 仍进持仓组（判定跟最强证据）",
          len(holding) == 1, f"holding={len(holding)} groups={ {k: len(v) for k, v in result['groups'].items()} }")
    check("但显示的标题是中文（文本跟代表条）",
          bool(holding) and holding[0]["title"].startswith("【台积电"),
          holding[0]["title"][:30] if holding else "")
    check("持仓档分值不被折叠拉低（≥0.78）",
          bool(holding) and holding[0]["relevance"] >= 0.78,
          holding[0]["relevance"] if holding else None)

    # ── ⑤ 不误伤 ───────────────────────────────────────────────────
    _section("\n⑤ 不误伤：内容不同就不许合")
    got, _ = collapse([
        {"title": "A股午评：创业板指跌1.07%，银行股普涨", "timestamp": 5000.0},
        {"title": "A股收评：创业板指涨0.52%，半导体走强", "timestamp": 5006.0},
    ])
    check("同一分钟两条不同内容的新闻 → 各留一条", len(got) == 2, f"out={len(got)}")
    got, _ = collapse([
        {"title": "", "timestamp": 6000.0},
        {"title": "   ", "timestamp": 6001.0},
    ])
    check("空标题不参与合并、也不崩", len(got) == 2, f"out={len(got)}")
    got, st = collapse([])
    check("空输入返回空，不抛", got == [] and st["input"] == 0, str(st))

    # ── ⑥ 接线：triage stats / 托盘配额 / market 不变 ──────────────
    _section("\n⑥ 接线：统计留痕、折叠发生在配额之前、/market 不受影响")
    stats = NewsTriage(focus).analyze([
        {"title": ZH_UKRAINE, "importance_score": 0.62, "timestamp": 1000.0},
        {"title": EN_UKRAINE, "importance_score": 0.62, "timestamp": 1005.0},
        {"title": "某地天气转凉", "importance_score": 0.61, "timestamp": 900.0},
    ], per_group_limit=10)["stats"]
    check("stats 带 merged（合了几条必须能看见）", stats.get("merged") == 1, str(stats))
    check("stats 带 merged_by_rule（哪条规则干的活也能看见）",
          bool(stats.get("merged_by_rule")), str(stats.get("merged_by_rule")))

    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        TRAY_TIMELINE_LIMITS, select_timeline_events,
    )
    now = time.time()
    events = [
        {"type": "high_score_news", "timestamp": now - i * 300,
         "block_name": f"独立新闻{i} 内容完全不同{i}"}
        for i in range(6)
    ] + [
        {"type": "high_score_news", "timestamp": now - 60, "block_name": ZH_UKRAINE},
        {"type": "high_score_news", "timestamp": now - 55, "block_name": EN_UKRAINE},
    ]
    picked = select_timeline_events(events, TRAY_TIMELINE_LIMITS)
    check("托盘：中英两版只占 1 个名额（折叠发生在配额之前）",
          sum(1 for e in picked if "intelligence" in str(e.get("block_name"))) == 0,
          f"picked={len(picked)}")
    check("托盘：折叠后的那条带 dup_count",
          any(int(e.get("dup_count") or 1) >= 2 for e in picked),
          str([e.get("dup_count") for e in picked]))
    legacy = select_timeline_events(events, None)
    check("/market 旧路径（per_type_limits=None）保持原样、不做折叠",
          any("intelligence" in str(e.get("block_name")) for e in legacy),
          f"out={len(legacy)}")

    check("format_dup_suffix：1 条不加标记、>1 才标",
          format_dup_suffix(1) == "" and format_dup_suffix(3) == " ×3",
          f"{format_dup_suffix(1)!r} / {format_dup_suffix(3)!r}")

    # ── ⑦ 性能 ─────────────────────────────────────────────────────
    _section("\n⑦ 性能：纯本地整数运算，1000 条也要在毫秒级")
    batch = []
    for i in range(1000):
        if i % 3 == 0:
            batch.append({"title": f"独立新闻编号{i} 内容各不相同{chr(65 + i % 20)}",
                          "timestamp": float(10_000 + i)})
        elif i % 3 == 1:
            batch.append({"title": f"【事件{i}】金十数据10月19日讯，这是第{i}条消息",
                          "timestamp": float(10_000 + i)})
        else:
            batch.append({"title": f"Event {i} happened on Monday, reports say",
                          "timestamp": float(10_000 + i + 1)})
    t0 = time.perf_counter()
    got, st = collapse(batch)
    cost = (time.perf_counter() - t0) * 1000
    check(f"1000 条耗时 {cost:.0f}ms < 500ms", cost < 500, f"{st['output']} 条")

    # ── ⑧ 静态守卫 ─────────────────────────────────────────────────
    _section("\n⑧ 静态守卫：接线不能断，SimHash 别偷偷开")
    dedup_src = DEDUP_PY.read_text(encoding="utf-8")
    triage_src = TRIAGE_PY.read_text(encoding="utf-8")
    timeline_src = TIMELINE_PY.read_text(encoding="utf-8")
    tray_src = TRAY_PY.read_text(encoding="utf-8")
    digest_src = DIGEST_PY.read_text(encoding="utf-8")
    page_src = PAGE_PY.read_text(encoding="utf-8")

    check("dedup 模块存在且定义了三条规则",
          all(k in dedup_src for k in ("RULE_EXACT", "RULE_PREFIX", "RULE_XLANG")), "")
    check("SimHash 默认关闭（实测只多合 1 条却慢 10 倍、还会误合）",
          "enable_fuzzy: bool = False" in dedup_src, "")
    check("triage 真的用了 dedup（而不是留着自己那套标题全等）",
          "from .dedup import" in triage_src and "find_groups(" in triage_src, "")
    check("triage 的 stats 暴露 merged",
          '"merged"' in triage_src, "")
    check("时间线折叠函数存在且在配额分支里被调用",
          "def _collapse_news_events" in timeline_src
          and "ordered = _collapse_news_events(ordered)" in timeline_src, "")
    check("托盘渲染读 dup_count 并拼 ×N",
          "dup_suffix" in tray_src and '{dup_suffix}' in tray_src
          and 'if _dup > 1' in tray_src, "")
    # 2026-10-19：呈现层从 /awakening 的紧凑面板搬到 /news 独立页面，
    # 折叠计数在「报告卡片」与「页面标题说明」两处都要露出来，
    # 否则用户以为系统没去重（少一条却看不出是因为合并）。
    check("报告卡片读 dup_count 并拼 ×N",
          'format_dup_suffix(row.get("dup_count"))' in digest_src, "")
    check("/news 页面说明里点出 ×N 的含义",
          "×N" in page_src, "")


# ─────────────────────────────────────────────────────────────
# 注入自证
# ─────────────────────────────────────────────────────────────

INJECTIONS = [
    {
        "name": "❗L3 中英配对被关掉（菜单又会满屏英文双版）",
        "file": DEDUP_PY,
        "old": "    if cfg.xlang_gap > 0:",
        "new": "    if False:  # 注入：不配对",
    },
    {
        "name": "❗一对一约束丢失（链式传染，一条英文吃掉两条中文）",
        "file": DEDUP_PY,
        "old": "            if i in used_en or j in used_zh or find(i) == find(j):",
        "new": "            if find(i) == find(j):  # 注入：去掉一对一",
    },
    {
        "name": "❗L1 同标题不再合并（重发会重复显示）",
        "file": DEDUP_PY,
        "old": "                if abs(stamps[i] - stamps[j]) <= cfg.same_title_window:",
        "new": "                if False:  # 注入：同标题也不合",
    },
    {
        "name": "❗代表条改成英文优先（用户要的是中文优先）",
        "file": DEDUP_PY,
        "old": "        return (0 if lang == prefer else 1, -_as_ts(records[i].get(time_key)))",
        "new": "        return (0 if lang != prefer else 1, -_as_ts(records[i].get(time_key)))",
    },
    {
        "name": "❗判定不再取最强证据（只拿簇内第一条当判定）",
        "file": TRIAGE_PY,
        "old": "            best_i = max(members, key=lambda i: scored[i].relevance)",
        "new": "            best_i = members[0]  # 注入：丢掉最强证据",
    },
    {
        "name": "❗托盘不再折叠（配额被重复新闻占满）",
        "file": TIMELINE_PY,
        "old": "    ordered = _collapse_news_events(ordered)",
        "new": "    pass  # 注入：不折叠",
    },
    {
        "name": "❗菜单不显示条数（折叠了但看不见，等于静默）",
        "file": TRAY_PY,
        "old": '                            dup_suffix = f" ×{_dup}" if _dup > 1 else ""',
        "new": '                            dup_suffix = ""  # 注入：不显示条数',
    },
]


def _exercise_injections() -> int:
    global _QUIET
    src_backup = {p: p.read_text(encoding="utf-8") for p in {i["file"] for i in INJECTIONS}}
    caught = 0
    try:
        _QUIET = True
        _FAILS.clear()
        _run_checks()
        assert not _FAILS, f"未注入时就有失败：{_FAILS}"

        for inj in INJECTIONS:
            path = inj["file"]
            text = src_backup[path]
            if inj["old"] not in text:
                print(f"  ⚠️ 锚点失配（守卫已腐烂）：{inj['name']}")
                continue
            path.write_text(text.replace(inj["old"], inj["new"], 1), encoding="utf-8")
            _reload_chain()
            _FAILS.clear()
            try:
                _run_checks()
            finally:
                path.write_text(text, encoding="utf-8")
                _reload_chain()
            if _FAILS:
                caught += 1
                print(f"  ✅ 被捕获：{inj['name']}")
            else:
                print(f"  ❌ 没抓到（守卫在睡觉）：{inj['name']}")
        print(f"\n  注入结果：{caught}/{len(INJECTIONS)} 被捕获")
        return 0 if caught == len(INJECTIONS) else 1
    finally:
        for path, text in src_backup.items():
            path.write_text(text, encoding="utf-8")
        _QUIET = False
        # 注入期间的失败属于"预期内的红"，不能带进主流程去误报
        _FAILS.clear()
        _reload_chain()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="有违约时以 1 退出")
    parser.add_argument("--exercise-injections", action="store_true",
                        help="逐个注入 bug，验证守卫真的会红")
    args = parser.parse_args()

    print("=" * 68)
    print("新闻去重（同一事件折叠）验证")
    print("=" * 68)
    _run_checks()

    injected_ok = True
    if args.exercise_injections:
        print("\n" + "=" * 68)
        print("⑨ 注入自证：把护栏逐个打断，守卫必须变红")
        print("=" * 68)
        injected_ok = _exercise_injections() == 0

    print()
    if _FAILS:
        print(f"❌ 违约 {len(_FAILS)} 项：")
        for f in _FAILS:
            print(f"   · {f}")
        return 1 if args.strict else 0
    print("✅ 全部通过：同一事件的多条记录会折成一条，只显示条数（中文优先）")
    if not injected_ok:
        print("⚠️ 注入自证未全通过（上面的 ❌ 项），说明有护栏在睡觉")
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
