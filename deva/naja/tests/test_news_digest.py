"""新闻消化器单测 —— 焦点状态 / 相关度筛选 / 每日报告 / UI 出口。

重点守三件事（都是本项目反复踩过的坑）：
  1. 持仓优先的口径真的生效（命中持仓压过高重要度的无关新闻）
  2. 宽泛主题不得升级成「关注主题」组（失去区分度）
  3. 没数据就说没数据，不兜底伪造
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from deva.naja.news import (
    GROUP_HOLDING,
    GROUP_MACRO,
    GROUP_THEME,
    NewsFocusState,
    NewsTriage,
    build_digest,
    get_news_digest_summary,
    render_digest_html,
    render_digest_text,
    write_daily_digest,
)

_SAMPLE_FOCUS = NewsFocusState(
    holdings=("宁德时代",),
    watchlist=("特斯拉", "比亚迪"),
    narratives=("新能源", "量子计算"),
    themes=(("AI", ("大模型", "算力", "英伟达")), ("芯片", ("半导体", "晶圆"))),
    narrative_risk=0.72,
)


def _items():
    return [
        {"title": "宁德时代发布新款麒麟电池", "importance_score": 0.62,
         "timestamp": 1000, "source": "jin10", "sentiment": 0.7},
        {"title": "特斯拉上海工厂扩产", "importance_score": 0.60,
         "timestamp": 990, "source": "jin10", "sentiment": 0.75},
        {"title": "欧盟推进对俄制裁", "importance_score": 0.95,
         "timestamp": 980, "source": "jin10", "sentiment": 0.3},
        {"title": "量子计算取得新突破", "importance_score": 0.61,
         "timestamp": 970, "source": "jin10", "sentiment": 0.6},
        {"title": "英伟达与思科推出新型光模块", "importance_score": 0.64,
         "timestamp": 960, "source": "jin10", "sentiment": 0.8},
        {"title": "宁德时代发布新款麒麟电池", "importance_score": 0.55,
         "timestamp": 950, "source": "radar", "sentiment": 0.7},
    ]


# ── 焦点状态 ────────────────────────────────────────────────────────────

def test_focus_state_matches_both_codes_and_names():
    """自选股表里存的可能是中文名（实测），匹配必须名字/代码通吃。"""
    focus = NewsFocusState(watchlist=("宁德时代", "300750", "TSLA"))
    assert focus.matched_own("宁德时代今日大涨") == ("宁德时代",)
    assert focus.matched_own("300750 发布公告") == ("300750",)
    assert focus.matched_own("TSLA 拆股") == ("TSLA",)
    assert focus.matched_own("与持仓无关的新闻") == ()


def test_focus_state_ignores_too_short_identifiers():
    """1 字符标识符做子串匹配会到处误命中，必须忽略。"""
    focus = NewsFocusState(watchlist=("A", "宁德时代"))
    assert focus.matched_own("A股今日大涨") == ()
    assert focus.matched_own("宁德时代扩产") == ("宁德时代",)


def test_focus_state_holdings_beat_watchlist_when_overlapping():
    """同一只票既在持仓又在自选时，只算持仓（避免双重加权）。"""
    focus = NewsFocusState(holdings=("特斯拉",), watchlist=("特斯拉", "比亚迪"))
    assert focus.matched_holdings("特斯拉扩产") == ("特斯拉",)
    assert focus.matched_watchlist("特斯拉扩产") == ()


def test_focus_state_records_degradation_instead_of_silent_default():
    """取不到数据要留痕（degraded），不能静默当默认值。"""
    from deva.naja.news.focus import build_focus_state

    class _Boom:
        def get_holdings(self):
            raise RuntimeError("模拟失败")

    focus = build_focus_state(
        portfolio=_Boom(), focus_manager=None, manas_manager=None, use_cache=False
    )
    assert focus.holdings == ()
    assert any("持仓" in d for d in focus.degraded), focus.degraded


def test_focus_state_empty_detection():
    assert NewsFocusState().is_empty() is True
    assert NewsFocusState(holdings=("X",)).is_empty() is False


# ── 相关度筛选 ──────────────────────────────────────────────────────────

def test_holding_news_outranks_high_importance_macro_news():
    """核心口径：命中持仓的新闻要压过"重要度 0.95 但与我们无关"的新闻。"""
    result = NewsTriage(_SAMPLE_FOCUS).analyze(_items(), per_group_limit=10)
    groups = result["groups"]

    holding = groups[GROUP_HOLDING]
    assert len(holding) == 2
    assert holding[0]["relevance"] > max(
        (m["relevance"] for m in groups[GROUP_MACRO]), default=0.0
    )

    eu = next(m for m in groups[GROUP_MACRO] if "欧盟" in m["title"])
    assert eu["base_importance"] > holding[0]["base_importance"], "前提：宏观那条本身更重要"
    assert eu["relevance"] < holding[0]["relevance"], "但相关度必须被持仓压过"


def test_broad_theme_hit_does_not_promote_group():
    """回归：只命中 manas 宽泛主题（AI/宏观…）不得升级成「关注主题」组。

    实测教训：默认主题集有 17 个宽泛大类，几乎命中所有新闻；
    若拿它分组，39 条会全进 theme，macro 恒空——分组失去区分度。
    """
    result = NewsTriage(_SAMPLE_FOCUS).analyze(_items(), per_group_limit=10)
    groups = result["groups"]

    nvidia = next(m for m in groups[GROUP_MACRO] if "英伟达" in m["title"])
    assert nvidia["theme_hits"] == ["AI"], "弱信号仍应留痕"
    assert [t["title"] for t in groups[GROUP_THEME]] == ["量子计算取得新突破"]
    assert len(groups[GROUP_MACRO]) >= 2


def test_triage_dedupes_same_title():
    result = NewsTriage(_SAMPLE_FOCUS).analyze(_items(), per_group_limit=10)
    assert result["stats"]["scanned"] == 6
    assert result["stats"]["deduped"] == 5
    dupes = [
        r for g in result["groups"].values() for r in g if "麒麟电池" in r["title"]
    ]
    assert len(dupes) == 1


def test_triage_every_item_lands_in_exactly_one_group():
    result = NewsTriage(_SAMPLE_FOCUS).analyze(_items(), per_group_limit=10)
    shown = sum(len(result["groups"][g]) for g in (GROUP_HOLDING, GROUP_THEME, GROUP_MACRO))
    assert shown == result["stats"]["deduped"]
    assert set(result["groups"]) == {GROUP_HOLDING, GROUP_THEME, GROUP_MACRO}


def test_triage_provides_reasons_for_every_decision():
    """每条判定都要能解释"为什么推给我"。"""
    result = NewsTriage(_SAMPLE_FOCUS).analyze(_items(), per_group_limit=10)
    for rows in result["groups"].values():
        for row in rows:
            assert row["reasons"], f"缺理由: {row['title']}"


def test_triage_survives_malformed_items():
    """单条坏数据不许拖垮整批。"""
    items = [{"title": "正常新闻", "importance_score": 0.6},
             {"no_title_here": True},
             {"title": "坏分新闻", "importance_score": "不是数字"}]
    result = NewsTriage(_SAMPLE_FOCUS).analyze(items, per_group_limit=10)
    assert result["stats"]["scanned"] == 2


# ── 断线修复：评分器 ← 焦点 provider ────────────────────────────────────

def _feed_scorer(scorer, text, tag="t"):
    from deva.naja.events.text_events import TextFetchedEvent

    captured = []
    scorer._publish_text_focused = lambda ev: captured.append(ev)
    scorer.on_text_fetched(TextFetchedEvent(
        text=text, title=text[:40], source="news_feed", url=f"http://test/{tag}"))
    return captured[-1]


def test_scorer_without_provider_has_empty_focus_topics():
    """复现旧行为：没有 provider 时关注主题匹配恒空（那条断线）。"""
    from deva.naja.attention.text_importance_scorer import TextImportanceScorer

    scorer = TextImportanceScorer()
    scorer.set_manas_state({})
    event = _feed_scorer(scorer, "宁德时代宣布新能源汽车产业链受益")
    assert event.matched_focus_topics == []


def test_scorer_with_snapshot_matches_topic_names():
    from deva.naja.attention.text_importance_scorer import TextImportanceScorer

    scorer = TextImportanceScorer()
    scorer.set_manas_state({"focus_topics": [{"topic": "新能源"}, {"topic": "芯片"}]})
    event = _feed_scorer(scorer, "宁德时代宣布新能源汽车产业链受益")
    assert event.matched_focus_topics == ["新能源"]


def test_scorer_matches_topic_keywords_not_only_names():
    """正文里出现关键词（晶圆/大模型）也应归入对应关注主题。"""
    from deva.naja.attention.text_importance_scorer import TextImportanceScorer

    scorer = TextImportanceScorer()
    scorer.set_manas_state({"focus_topics": [
        {"topic": "AI", "keywords": ["大模型"]},
        {"topic": "芯片", "keywords": ["晶圆"]},
    ]})
    event = _feed_scorer(scorer, "某公司用大模型优化晶圆良率")
    assert set(event.matched_focus_topics) == {"AI", "芯片"}


def test_scorer_provider_failure_keeps_last_snapshot():
    """provider 挂了要沿用上次快照，不许抛、不许静默清空。"""
    from deva.naja.attention.text_importance_scorer import TextImportanceScorer

    scorer = TextImportanceScorer()

    def _boom():
        raise RuntimeError("模拟失败")

    scorer.set_focus_provider(_boom)
    scorer.set_manas_state({"focus_topics": [{"topic": "新能源"}]})
    event = _feed_scorer(scorer, "宁德时代宣布新能源汽车产业链受益")
    assert event.matched_focus_topics == ["新能源"]


def test_scorer_provider_pull_overrides_snapshot():
    from deva.naja.attention.text_importance_scorer import TextImportanceScorer

    scorer = TextImportanceScorer()
    scorer.set_manas_state({"focus_topics": [{"topic": "从不出现的主题"}]})
    scorer.set_focus_provider(lambda: {"focus_topics": [{"topic": "新能源"}]})
    event = _feed_scorer(scorer, "宁德时代宣布新能源汽车产业链受益")
    assert event.matched_focus_topics == ["新能源"]


# ── 报告 ────────────────────────────────────────────────────────────────

def test_digest_is_honest_when_no_news():
    digest = build_digest(items=[], focus_state=_SAMPLE_FOCUS)
    assert digest["available"] is False
    assert digest["reason"]
    assert "没有已评分的新闻" in digest["reason"]


def test_digest_shape_is_json_serializable_and_complete():
    digest = build_digest(items=_items(), focus_state=_SAMPLE_FOCUS)
    assert digest["available"] is True
    assert set(digest["groups"]) == {GROUP_HOLDING, GROUP_THEME, GROUP_MACRO}
    assert digest["focus"]["holdings"] == ["宁德时代"]
    json.dumps(digest, ensure_ascii=False)  # 必须能直接序列化


def test_digest_renderers_escape_free_text():
    """新闻标题来自外部，进 HTML 前必须转义。"""
    items = [{"title": "<script>alert(1)</script>持仓新闻", "importance_score": 0.6,
              "timestamp": 1000, "source": "x", "text": "宁德时代"}]
    digest = build_digest(items=items, focus_state=_SAMPLE_FOCUS)
    html = render_digest_html(digest)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_digest_text_renders_groups():
    digest = build_digest(items=_items(), focus_state=_SAMPLE_FOCUS)
    text = render_digest_text(digest)
    assert "持仓 / 自选相关" in text
    assert "宁德时代" in text


def test_digest_writes_daily_file():
    digest = build_digest(items=_items(), focus_state=_SAMPLE_FOCUS)
    out_dir = Path(tempfile.mkdtemp(prefix="naja_news_digest_test_"))
    path = write_daily_digest(digest, out_dir=out_dir)
    assert path.exists() and path.suffix == ".html"
    assert (out_dir / "latest.json").exists()
    reloaded = json.loads((out_dir / "latest.json").read_text(encoding="utf-8"))
    assert reloaded["stats"]["holding"] == 2


def test_get_news_digest_summary_never_raises():
    """UI 出口必须永远可用（内部失败降级成 available=False）。"""
    summary = get_news_digest_summary(hours=1, per_group_limit=3)
    assert isinstance(summary, dict)
    assert "available" in summary
    assert isinstance(summary["groups"], dict)


# ── UI ──────────────────────────────────────────────────────────────────

def test_ui_panel_renders_and_shows_honest_empty_state():
    from deva.naja.attention.ui import render_news_digest_panel

    digest = build_digest(items=_items(), focus_state=_SAMPLE_FOCUS)
    panel = render_news_digest_panel(digest)
    assert "今日新闻消化" in panel
    assert "持仓 / 自选相关" in panel

    empty = render_news_digest_panel({"available": False, "reason": "没有数据"})
    assert "没有数据" in empty


def test_dashboard_monitor_data_has_news_digest_key():
    from deva.naja.attention.ui.dashboard import _get_empty_monitor_data

    data = _get_empty_monitor_data()
    assert "news_digest" in data
    assert set(data["news_digest"]["groups"]) == {GROUP_HOLDING, GROUP_THEME, GROUP_MACRO}
