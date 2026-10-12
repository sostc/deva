#!/usr/bin/env python3
"""验证「新闻消化器」——复用 manas 注意力原则筛新闻，做到信息不过载。

覆盖什么
--------
① **持仓优先排序**（用户选定的口径）：命中持仓的新闻必须压过"高重要度但与我们无关"的宏观新闻
② **分组区分度**：manas 默认主题集是宽泛大类（几乎命中一切），单独命中**不得**升级成「关注主题」组
③ **去重**：同标题只留相关度最高的一条
④ **断线已修**：``TextImportanceScorer`` 接上 provider 后 ``matched_focus_topics`` 不再恒空
⑤ **降级诚实**：没有新闻时 ``available=False`` + reason；provider 抛错不炸、沿用上次快照
⑥ **报告可渲染 / 可落盘**：HTML + 纯文本结构完整，能写到指定目录
⑦ **静态守卫**：容器确实做了接线（防回退成死线）；dashboard 确实有出口
⑧ **冷启动回归**：``attention_os`` 作为第一个被 import 的模块不再触发循环导入

跑法
----
    cd <项目根>
    /Users/spark/.local/bin/python3 scripts/verify/verify_news_digest.py
    /Users/spark/.local/bin/python3 scripts/verify/verify_news_digest.py --strict

退出码：0 = PASS；--strict 下有违约则 1。
本脚本**只读**既有数据，不写任何生产库。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

_CHILD_ENV = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}


def _make_items() -> list[dict]:
    """构造一批有区分度的假新闻（不依赖真实新闻池，结果可复现）。"""
    return [
        # 命中持仓（宁德时代）——重要度中等
        {"title": "宁德时代发布新款麒麟电池", "importance_score": 0.62,
         "timestamp": 1000, "source": "jin10", "sentiment": 0.7},
        # 命中自选（特斯拉）——重要度中等
        {"title": "特斯拉上海工厂扩产", "importance_score": 0.60,
         "timestamp": 990, "source": "jin10", "sentiment": 0.75},
        # 高重要度但与我们无关的宏观新闻——这是"信息过载"的典型
        {"title": "欧盟推进对俄制裁", "importance_score": 0.95,
         "timestamp": 980, "source": "jin10", "sentiment": 0.3},
        # 命中主动关注叙事
        {"title": "量子计算取得新突破", "importance_score": 0.61,
         "timestamp": 970, "source": "jin10", "sentiment": 0.6},
        # 只命中 manas 宽泛主题（英伟达→AI），不命中主动关注叙事
        {"title": "英伟达与思科推出新型光模块", "importance_score": 0.64,
         "timestamp": 960, "source": "jin10", "sentiment": 0.8},
        # 重复标题（不同来源），应被去重
        {"title": "宁德时代发布新款麒麟电池", "importance_score": 0.55,
         "timestamp": 950, "source": "radar", "sentiment": 0.7},
        # 完全无关
        {"title": "某地天气转凉", "importance_score": 0.61,
         "timestamp": 940, "source": "jin10", "sentiment": 0.5},
    ]


def _child_import_check() -> tuple[bool, str]:
    """回归守卫：把 attention_os 作为**第一个** import 的 deva 模块。

    此前这条路径会 ImportError（attention_os → text_importance_scorer →
    cognition → bandit → attention_os 成环），生产因加载顺序侥幸不炸。
    """
    snippet = (
        f"import sys; sys.path.insert(0, {str(PROJECT_ROOT)!r})\n"
        "from deva.naja.attention.os.attention_os import get_attention_os\n"
        "print('COLD_IMPORT_OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        env=_CHILD_ENV, capture_output=True, text=True,
        cwd=str(PROJECT_ROOT), timeout=180,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return (proc.returncode == 0 and "COLD_IMPORT_OK" in out), out.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="有违约则退出码 1")
    args = parser.parse_args()

    violations: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"  {'✅' if ok else '❌'} {name}" + (f"  —— {detail}" if detail else ""))
        if not ok:
            violations.append(name)

    from deva.naja.news import NewsFocusState, NewsTriage

    focus = NewsFocusState(
        holdings=("宁德时代",),
        watchlist=("特斯拉", "比亚迪"),
        narratives=("新能源", "量子计算"),
        themes=(("AI", ("大模型", "算力", "英伟达")), ("芯片", ("半导体", "晶圆"))),
        narrative_risk=0.72,
    )
    items = _make_items()

    # ── ① 持仓优先排序 ────────────────────────────────────────────────
    print("=" * 68)
    print("① 持仓优先：命中持仓的新闻压过高重要度的无关宏观新闻")
    print("=" * 68)
    result = NewsTriage(focus).analyze(items, per_group_limit=10)
    groups = result["groups"]

    holding = groups["holding"]
    check("有新闻进入「持仓/自选相关」组", len(holding) == 2, f"n={len(holding)}")
    check("命中的是持仓(宁德时代)与自选(特斯拉)",
          {h["title"] for h in holding} == {"宁德时代发布新款麒麟电池", "特斯拉上海工厂扩产"},
          f"{[h['title'] for h in holding]}")

    top_rel = holding[0]["relevance"] if holding else 0.0
    macro_rel = max((m["relevance"] for m in groups["macro"]), default=0.0)
    check("持仓相关度 > 宏观最高相关度（口径生效）", top_rel > macro_rel,
          f"holding={top_rel:.3f} vs macro={macro_rel:.3f}")

    euva = next((m for m in groups["macro"] if "欧盟" in m["title"]), None)
    check("重要度 0.95 的无关新闻确实落在 macro 组", euva is not None, "")
    check("它仍然排不上持仓新闻之前", euva is not None and euva["relevance"] < top_rel,
          f"euva={euva['relevance']:.3f} vs holding={top_rel:.3f}")

    # ── ② 分组区分度（回归：宽泛主题不得升级成 theme 组）──────────────
    print()
    print("=" * 68)
    print("② 分组区分度：只命中 manas 宽泛主题 → 不得升级为「关注主题」组")
    print("=" * 68)
    nvidia = next((m for m in groups["macro"] if "英伟达" in m["title"]), None)
    check("命中宽泛主题(AI)但不命中主动关注 → 归入 macro", nvidia is not None,
          f"theme 组={[t['title'] for t in groups['theme']]}")
    check("它仍带上了主题命中留痕（弱信号可见）",
          bool(nvidia and nvidia["theme_hits"]), f"theme_hits={nvidia['theme_hits'] if nvidia else None}")
    check("命中主动关注叙事(量子计算) → 归入 theme",
          {t["title"] for t in groups["theme"]} == {"量子计算取得新突破"},
          f"{[t['title'] for t in groups['theme']]}")
    check("macro 组不空（没有把一切都塞进 theme）", len(groups["macro"]) >= 2,
          f"macro n={len(groups['macro'])}")

    # ── ③ 去重 ────────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("③ 去重：同标题只留相关度最高的一条")
    print("=" * 68)
    check("扫描 7 条 → 去重后 6 条", result["stats"]["scanned"] == 7
          and result["stats"]["deduped"] == 6, f"stats={result['stats']}")
    check("重复的宁德时代合计只出现 1 次",
          sum(1 for g in groups.values() for r in g if "麒麟电池" in r["title"]) == 1, "")

    # ── ④ 断线已修 ────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("④ 断线已修：评分器接上 provider 后 matched_focus_topics 不再恒空")
    print("=" * 68)
    from deva.naja.attention.text_importance_scorer import TextImportanceScorer
    from deva.naja.events.text_events import TextFetchedEvent
    from deva.naja.news.focus import build_manas_focus_state

    text = "宁德时代宣布新一代电池量产，采用大模型优化晶圆良率，新能源汽车产业链受益"
    captured: list = []

    def _feed(scorer, tag):
        scorer._publish_text_focused = lambda ev: captured.append(ev)
        scorer.on_text_fetched(TextFetchedEvent(
            text=text, title=text[:40], source="news_feed", url=f"http://verify/{tag}"))

    before = TextImportanceScorer()
    before.set_manas_state({})          # 等价于历史真实情况（_manas_state 恒 None 的语义）
    _feed(before, "before")
    check("未注入 provider 时 matched_focus_topics 为空（复现旧行为）",
          captured[-1].matched_focus_topics == [], f"{captured[-1].matched_focus_topics}")

    after = TextImportanceScorer()
    after.set_focus_provider(build_manas_focus_state)
    _feed(after, "after")
    matched = captured[-1].matched_focus_topics
    check("注入 provider 后命中关注主题（断线已通）", bool(matched), f"{matched}")
    check("关键词也能命中主题（晶圆→芯片 / 大模型→AI）",
          "芯片" in matched and "AI" in matched, f"{matched}")
    check("事件带上了焦点快照（可回溯当次判定依据）",
          bool((captured[-1].manas_state or {}).get("focus_topics")), "")

    # ── ⑤ 降级诚实 ────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("⑤ 降级诚实：没数据就说没数据；provider 挂了不许炸")
    print("=" * 68)
    from deva.naja.news import build_digest

    empty = build_digest(items=[], focus_state=focus)
    check("无新闻时 available=False", empty["available"] is False, "")
    check("并给出 reason（不兜底伪造报告）", bool(empty.get("reason")), f"{empty.get('reason')}")

    degraded = build_digest(items=items, focus_state=NewsFocusState())  # 完全空的焦点
    check("焦点为空时依然能出报告（不崩）", degraded["available"] is True,
          f"scanned={degraded['stats']['scanned']}")

    boom = TextImportanceScorer()

    def _bad_provider():
        raise RuntimeError("模拟取焦点失败")

    boom.set_focus_provider(_bad_provider)
    # 快照里放一个**确实出现在文本中**的主题名，才能证明"沿用上次快照"真的生效
    boom.set_manas_state({"focus_topics": [{"topic": "新能源"}]})
    _feed(boom, "boom")
    check("provider 抛错 → 沿用上次快照，不抛异常",
          "新能源" in captured[-1].matched_focus_topics, f"{captured[-1].matched_focus_topics}")

    # ── ⑥ 报告可渲染 / 可落盘 ─────────────────────────────────────────
    print()
    print("=" * 68)
    print("⑥ 报告可渲染、可落盘")
    print("=" * 68)
    from deva.naja.news import render_digest_html, render_digest_text, write_daily_digest
    from deva.naja.attention.ui import render_news_digest_panel

    digest = build_digest(items=items, focus_state=focus)
    html = render_digest_html(digest)
    text = render_digest_text(digest)
    panel = render_news_digest_panel(digest)

    check("HTML 是完整文档且含关键区块",
          html.startswith("<!DOCTYPE html>") and "持仓 / 自选相关" in html
          and "关注主题" in html, f"len={len(html)}")
    check("纯文本含分组标题与精选计数",
          "持仓 / 自选相关" in text and "扫描" in text, f"len={len(text)}")
    check("dashboard 面板片段可渲染", "今日新闻消化" in panel and len(panel) > 300,
          f"len={len(panel)}")

    tmp = Path(tempfile.mkdtemp(prefix="naja_news_digest_verify_"))
    out = write_daily_digest(digest, out_dir=tmp)
    check("日报已落盘（.html + .json）",
          out.exists() and out.suffix == ".html" and (tmp / "latest.json").exists(),
          str(out))

    empty_panel = render_news_digest_panel(empty)
    check("空数据面板显示诚实空态（不是假的表格）",
          "没有已评分的新闻" in empty_panel, f"len={len(empty_panel)}")

    # ── ⑦ 静态守卫 ────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("⑦ 静态守卫：容器真的接线了（防回退成死线）")
    print("=" * 68)
    container_src = (PROJECT_ROOT / "deva/naja/application/container.py").read_text(encoding="utf-8")
    check("容器调用了 _wire_news_focus_provider()",
          "_wire_news_focus_provider()" in container_src, "")
    check("容器注入了 set_text_focus_provider",
          "set_text_focus_provider" in container_src, "")
    check("容器注册了 news_digest 定时任务",
          "_register_news_digest_task()" in container_src
          and '"news_digest"' in container_src, "")

    scorer_src = (PROJECT_ROOT / "deva/naja/attention/text_importance_scorer.py").read_text(encoding="utf-8")
    check("评分器暴露 set_focus_provider 注入点",
          "def set_focus_provider" in scorer_src, "")
    check("评分前会刷新焦点状态",
          "self._resolve_manas_state()" in scorer_src, "")

    dashboard_src = (PROJECT_ROOT / "deva/naja/attention/ui/dashboard.py").read_text(encoding="utf-8")
    check("dashboard 有 news_digest 数据出口与渲染",
          '"news_digest": _get_news_digest_state()' in dashboard_src
          and "render_news_digest_panel" in dashboard_src, "")

    # ── ⑧ 冷启动回归 ──────────────────────────────────────────────────
    print()
    print("=" * 68)
    print("⑧ 冷启动回归：attention_os 作为首个 import 不再循环导入")
    print("=" * 68)
    ok_cold, out_cold = _child_import_check()
    check("子进程冷启动导入成功", ok_cold,
          (out_cold.splitlines() or [""])[-1])

    # ── 汇总 ──────────────────────────────────────────────────────────
    print()
    print("=" * 68)
    if violations:
        print(f"❌ 违约 {len(violations)} 项: {violations}")
        return 1 if args.strict else 0
    print("✅ 全部通过：新闻消化器可用——按持仓/关注筛新闻，报告可查、可落盘")
    return 0


if __name__ == "__main__":
    sys.exit(main())
