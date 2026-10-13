#!/usr/bin/env python3
"""验证「新闻消化器」——复用 manas 注意力原则筛新闻，做到信息不过载。

覆盖什么
--------
① **硬分层不变量**（用户选定的口径，2026-10-12 二次修订）：
   持仓在**数学上必然**优先于任何非持仓新闻（不再是"倾向于"）；
   自选并入外部要闻组；重大负面外部新闻允许「风险穿透」
② **分组区分度**：manas 默认主题集是宽泛大类（几乎命中一切），单独命中**不得**升级成「关注主题」组
③ **去重**：同标题只留相关度最高的一条
④ **断线已修**：``TextImportanceScorer`` 接上 provider 后 ``matched_focus_topics`` 不再恒空
⑤ **降级诚实**：没有新闻时 ``available=False`` + reason；provider 抛错不炸、沿用上次快照；
   档位配置调坏（区间重叠）时回退默认并留痕
⑥ **报告可渲染 / 可落盘**：HTML + 纯文本结构完整，能写到指定目录
⑦ **静态守卫**：容器确实做了接线（防回退成死线）；dashboard 确实有出口
⑧ **冷启动回归**：``attention_os`` 作为第一个被 import 的模块不再触发循环导入
⑨ **持仓链路可达性（反静默）**：券商账户真的被创建；持仓为空时**必须留痕**
   ——守 ``_init_accounts`` 那个"一个账户抛错中断整个循环"的历史 bug

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

    # ── ① 硬分层不变量 + 持仓优先 + 风险穿透 ──────────────────────────
    print("=" * 68)
    print("① 硬分层不变量：持仓数学上必然优先（不再是「倾向于」）")
    print("=" * 68)
    from deva.naja.news import TIER_HOLDING, TIER_WATCHLIST, TriageConfig

    cfg = TriageConfig()
    problems = cfg.validate()
    check("档位区间严格不重叠（配置自校验）", not problems,
          "；".join(problems) if problems else "4 档严丝合缝，无重叠")

    holding_band = cfg.band(TIER_HOLDING)
    watchlist_band = cfg.band(TIER_WATCHLIST)
    check("自选拉满重要度也压不过持仓垫底（旧版的缺陷 1）",
          watchlist_band.apply(1.0) < holding_band.apply(0.0),
          f"自选最优 {watchlist_band.apply(1.0):.3f} < 持仓最差 {holding_band.apply(0.0):.3f}")

    result = NewsTriage(focus).analyze(items, per_group_limit=10)
    groups = result["groups"]

    holding = groups["holding"]
    check("持仓组只放持仓（自选已归入外部要闻）",
          len(holding) == 1 and holding[0]["title"] == "宁德时代发布新款麒麟电池",
          f"{[h['title'] for h in holding]}")

    top_rel = holding[0]["relevance"] if holding else 0.0
    others_max = max((r["relevance"] for g in ("theme", "macro") for r in groups[g]), default=0.0)
    check("持仓相关度 > 所有非持仓新闻（硬保证，旧版的缺陷 2）",
          top_rel > others_max, f"holding={top_rel:.3f} vs 其它最高={others_max:.3f}")

    euva = next((m for m in groups["macro"] if "欧盟" in m["title"]), None)
    check("重要度 0.95 的无关新闻落在外部要闻组", euva is not None, "")
    check("它排不上持仓新闻之前",
          euva is not None and euva["relevance"] < top_rel,
          f"euva={euva['relevance']:.3f} vs holding={top_rel:.3f}")

    # 风险穿透：挡机会 ≠ 挡风险
    check("重大负面外部新闻被「风险穿透」抬档（挡机会不挡风险）",
          bool(euva and euva.get("pierced")),
          f"tier={euva.get('tier')} rel={euva['relevance']:.3f}" if euva else "未找到该条")
    check("穿透条仍属外部要闻组，不冒充持仓",
          bool(euva and euva["group"] == "macro" and not euva["holding_hits"]),
          f"group={euva.get('group')} holding_hits={euva.get('holding_hits')}" if euva else "")

    tesla = next((m for m in groups["macro"] if "特斯拉" in m["title"]), None)
    nvidia_for_order = next((m for m in groups["macro"] if "英伟达" in m["title"]), None)
    check("自选条归入外部要闻组（不再与持仓并列）",
          bool(tesla and tesla.get("tier") == "watchlist"),
          f"tier={tesla.get('tier')}" if tesla else "未找到该条")
    check("同组内自选排在纯宏观之前（自选仍有独立档位）",
          bool(tesla and nvidia_for_order
               and tesla["relevance"] > nvidia_for_order["relevance"]),
          f"自选={tesla['relevance']:.3f} vs 纯宏观={nvidia_for_order['relevance']:.3f}"
          if tesla and nvidia_for_order else "")

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

    # 档位口径调坏时必须回退（本项目的规矩：宁可退回已知安全的口径）
    bad_env = TriageConfig.from_env(
        {"NAJA_NEWS_TIERS": "holding=0.30/0.10,theme=0.50/0.20,"
                            "watchlist=0.32/0.16,macro=0.00/0.24"}
    )
    check("档位区间被调重叠 → 回退默认并留痕（不静默算错）",
          bool(bad_env.degraded) and bad_env.validate() == [],
          bad_env.degraded[0] if bad_env.degraded else "无降级记录（不应如此）")
    good_env = TriageConfig.from_env(
        {"NAJA_NEWS_TIERS": "holding=0.85/0.15,theme=0.55/0.20,"
                            "watchlist=0.35/0.15,macro=0.00/0.25"}
    )
    check("合法调参生效（无需改代码就能调口径）",
          good_env.degraded == () and good_env.band(TIER_HOLDING).floor == 0.85,
          f"holding.floor={good_env.band(TIER_HOLDING).floor}")

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
          html.startswith("<!DOCTYPE html>") and "持仓相关" in html
          and "关注叙事" in html and "外部要闻" in html, f"len={len(html)}")
    check("HTML 摊开了排序口径（数字可见，不是黑箱）",
          "排序口径" in html and "0.78" in html, "")
    check("HTML 标出了风险穿透条",
          "风险穿透" in html and "tag-pierce" in html, "")
    check("纯文本含分组标题与精选计数",
          "持仓相关" in text and "扫描" in text, f"len={len(text)}")
    check("纯文本把持仓与自选分行（不再混为一谈）",
          "持仓：宁德时代" in text and "自选：特斯拉" in text, "")
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

    # ── ⑨ 持仓链路可达性（反静默）──────────────────────────────────────
    print()
    print("=" * 68)
    print("⑨ 持仓链路可达性：账户真的建起来了；持仓为空必须留痕")
    print("=" * 68)
    from deva.naja.attention.portfolio import get_portfolio
    from deva.naja.news.digest import _load_scored_news
    from deva.naja.news.focus import build_focus_state, invalidate_focus_cache

    pf = get_portfolio()
    status = pf.get_account_status()
    brokerage = list(status.get("brokerage_initialized") or [])
    failures = list(status.get("failures") or [])

    # 历史 bug：虚拟测试抛 RuntimeError 逃过 except KeyError → 循环中断 →
    # Spark / Cutie 从未创建 → get_holdings() 静默返回 []
    check("券商账户确实被创建（历史上被一个失败账户连累，全部没建起来）",
          bool(brokerage),
          f"brokerage_initialized={brokerage} failures={failures}")

    invalidate_focus_cache()
    live = build_focus_state(use_cache=False)

    if brokerage:
        check("真实持仓被读到（不再恒为空）", bool(live.holdings),
              f"holdings={list(live.holdings)[:8]}")
    else:
        check("账户未初始化时持仓为空**必须留痕**",
              any("初始化失败" in d or "不可区分" in d for d in live.degraded),
              f"degraded={list(live.degraded)}")

    check("焦点快照记录了持仓来源账户（可回溯钱是从哪个账户读的）",
          any(str(s).startswith("持仓账户:") for s in live.sources),
          f"sources={list(live.sources)}")

    # 核心反静默断言：绝不允许出现「持仓为空却没有任何解释」的状态
    check("不存在「持仓为空却零解释」的静默状态",
          bool(live.holdings) or bool(live.degraded),
          f"holdings={len(live.holdings)} degraded={len(live.degraded)}")

    # 持仓链路通了之后，AI/英伟达类新闻应当能进「持仓相关」档
    if live.holdings:
        live_items, _ = _load_scored_news(hours=168, limit=300)
        # 先看池子里**有没有**本可以命中持仓的条目。
        # 一条都没有时 holding=0 是数据条件（近 7 天没抓到这几只的新闻），
        # 而不是链路坏了——报成"死档"就是**假警报**；本项目铁律：
        # 假警报比不报警更伤（谎报一次，之后没人再看这块）。
        candidates = [
            it for it in live_items
            if live.matched_holdings(it.get("title") or "", it.get("text") or "")
        ]
        if not candidates:
            print(f"  ⏭️  跳过「持仓档命中」：近 7 天新闻池（{len(live_items)} 条）里"
                  "没有任何一条提到持仓标的——本项无法判定，非链路故障")
        else:
            live_result = NewsTriage(live).analyze(live_items, per_group_limit=20)
            n_holding = live_result["stats"]["holding"]
            check("真实新闻里已出现「持仓相关」命中（持仓档不再是死档）",
                  n_holding > 0,
                  f"holding={n_holding} theme={live_result['stats']['theme']} "
                  f"macro={live_result['stats']['macro']} 候选={len(candidates)}")

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
