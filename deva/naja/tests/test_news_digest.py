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
    TIER_HOLDING,
    TIER_MACRO,
    TIER_PIERCE,
    TIER_THEME,
    TIER_WATCHLIST,
    NewsFocusState,
    NewsTriage,
    TriageConfig,
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


class _Stock:
    """假的 ``StockInfo``（焦点层只读 code / name 两个字段）。"""

    def __init__(self, code, name):
        self.code = code
        self.name = name


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


# ── 持仓链路可达性（反静默）────────────────────────────────────────────

def test_focus_prefers_merged_holdings_across_accounts():
    """合并全部券商账户：只看默认账户会漏掉"我真正持有的票"。"""
    from deva.naja.news.focus import build_focus_state

    class _MultiAccount:
        def get_all_holdings(self):
            return [_Stock("nvda", "英伟达"), _Stock("06666", "EVERG SERVICES")]

        def get_holdings(self):
            raise AssertionError("有 get_all_holdings 时不该再退回单账户")

        def get_watchlist(self):
            return []

        def get_account_status(self):
            return {"brokerage_initialized": ["Spark", "FutuReal"], "failures": []}

    focus = build_focus_state(
        portfolio=_MultiAccount(), focus_manager=None, manas_manager=None, use_cache=False
    )
    assert "英伟达" in focus.holdings and "nvda" in focus.holdings
    assert "EVERG SERVICES" in focus.holdings
    assert any(s.startswith("持仓账户:") for s in focus.sources)


def test_focus_never_silently_reports_empty_holdings():
    """回归：账户一个都没建起来时，持仓为空**必须留痕**。

    历史 bug：``_init_accounts`` 里一个账户抛错中断整个循环，Spark/Cutie 从未创建，
    ``get_holdings()`` 静默返回 ``[]`` —— 用户真实持仓读出来恒为空、新闻的
    「持仓档」永远不命中，而且**不报任何错**。这条就是那次的反静默守卫。
    """
    from deva.naja.news.focus import build_focus_state

    class _NeverInitialized:
        def get_all_holdings(self):
            return []

        def get_watchlist(self):
            return []

        def get_account_status(self):
            return {
                "expected": ["虚拟测试", "Spark"],
                "initialized": [],
                "brokerage_initialized": [],
                "failures": ["虚拟测试"],
                "has_virtual": False,
            }

    focus = build_focus_state(
        portfolio=_NeverInitialized(), focus_manager=None, manas_manager=None,
        use_cache=False,
    )
    assert focus.holdings == ()
    assert focus.degraded, "持仓为空却没有留痕 —— 这正是要防的静默失效"
    assert any("初始化失败" in d or "不太可区分" in d or "不可区分" in d
               for d in focus.degraded), focus.degraded


def test_focus_reports_partial_account_failure():
    """部分账户失败也要说出来（哪怕其它账户读到了持仓）。"""
    from deva.naja.news.focus import build_focus_state

    class _Partial:
        def get_all_holdings(self):
            return [_Stock("nvda", "英伟达")]

        def get_watchlist(self):
            return []

        def get_account_status(self):
            return {"brokerage_initialized": ["Spark"], "failures": ["虚拟测试"]}

    focus = build_focus_state(
        portfolio=_Partial(), focus_manager=None, manas_manager=None, use_cache=False
    )
    assert focus.holdings == ("nvda", "英伟达")
    assert any("初始化失败" in d for d in focus.degraded), focus.degraded


def test_focus_state_field_count_matches_to_dict():
    """dataclass 字段数必须 == to_dict() 键数（本项目已踩过两次，固化成测试）。"""
    import dataclasses

    n_fields = len(dataclasses.fields(NewsFocusState))
    n_keys = len(NewsFocusState().to_dict())
    assert n_fields == n_keys, f"字段 {n_fields} 个，to_dict 出 {n_keys} 个键"


def test_collapse_identifiers_folds_case_variants_for_display():
    """展示层折叠大小写变体（lg新能源 → LG新能源），但不改匹配数据。"""
    from deva.naja.news.focus import collapse_identifiers

    assert collapse_identifiers(["lg新能源", "LG新能源", "宁德时代"]) == (
        "LG新能源", "宁德时代")
    assert collapse_identifiers([]) == ()
    assert collapse_identifiers(["300750"]) == ("300750",)


def test_focus_labels_prefer_human_names_over_codes():
    """展示名优先中文名 —— 否则报告里会列成"baba、阿里巴巴、nvda、英伟达"。"""
    from deva.naja.news.focus import build_focus_state

    class _Paired:
        def get_all_holdings(self):
            return [_Stock("baba", "阿里巴巴"), _Stock("nvda", "英伟达")]

        def get_watchlist(self):
            return [_Stock("lg新能源", "LG新能源")]

        def get_account_status(self):
            return {"brokerage_initialized": ["Spark"], "failures": []}

    focus = build_focus_state(
        portfolio=_Paired(), focus_manager=None, manas_manager=None, use_cache=False
    )
    # 匹配仍保留代码+名称两套写法
    assert focus.holdings == ("baba", "阿里巴巴", "nvda", "英伟达")
    # 展示只要人可读名
    assert focus.holdings_labels == ("阿里巴巴", "英伟达")
    assert focus.watchlist_labels == ("LG新能源",)
    assert focus.to_dict()["holdings_labels"] == ["阿里巴巴", "英伟达"]


# ── 相关度筛选 ──────────────────────────────────────────────────────────

def test_holding_news_outranks_high_importance_macro_news():
    """核心口径：命中持仓的新闻要压过"重要度 0.95 但与我们无关"的新闻。"""
    result = NewsTriage(_SAMPLE_FOCUS).analyze(_items(), per_group_limit=10)
    groups = result["groups"]

    holding = groups[GROUP_HOLDING]
    assert len(holding) == 1, "自选（特斯拉）已归入外部要闻，不再与持仓同组"
    assert holding[0]["title"].startswith("宁德时代")

    others = [row for g in (GROUP_THEME, GROUP_MACRO) for row in groups[g]]
    assert holding[0]["relevance"] > max(r["relevance"] for r in others)

    eu = next(m for m in groups[GROUP_MACRO] if "欧盟" in m["title"])
    assert eu["base_importance"] > holding[0]["base_importance"], "前提：宏观那条本身更重要"
    assert eu["relevance"] < holding[0]["relevance"], "但相关度必须被持仓压过"


def test_watchlist_never_outranks_holding_at_any_importance():
    """硬分层的数学保证：自选**在任何重要度下**都压不过持仓。

    这是从加分制改成分档制的**理由**——旧版 `base*0.45 + bonus` 下，
    自选条只要重要度高 0.267 就能反超持仓条（自选你"在看"的票
    挤掉了你"持有"的票）。现在穷举档位区间两端验证不变量。
    """
    cfg = TriageConfig()
    holding_top = cfg.band(TIER_HOLDING)
    watchlist_top = cfg.band(TIER_WATCHLIST)

    worst_holding = holding_top.apply(0.0)      # 持仓条重要度垫底
    best_watchlist = watchlist_top.apply(1.0)   # 自选条重要度拉满
    assert best_watchlist < worst_holding, (
        f"自选最优 {best_watchlist:.3f} 不得 ≥ 持仓最差 {worst_holding:.3f}"
    )


def test_tier_bands_are_strictly_disjoint():
    """档位区间必须从高到低严丝合缝——重叠了「持仓永远优先」就失效。"""
    cfg = TriageConfig()
    assert cfg.validate() == [], cfg.validate()

    holding = cfg.band(TIER_HOLDING)
    theme = cfg.band(TIER_THEME)
    watchlist = cfg.band(TIER_WATCHLIST)
    macro = cfg.band(TIER_MACRO)

    assert macro.ceiling + cfg.theme_nudge < watchlist.floor
    assert watchlist.ceiling < theme.floor
    assert theme.ceiling < holding.floor
    assert holding.ceiling == 1.0


def test_watchlist_item_lands_in_macro_group_not_holding():
    """自选并入「外部要闻」：它在组内排得比纯宏观高，但不和持仓并列。"""
    result = NewsTriage(_SAMPLE_FOCUS).analyze(_items(), per_group_limit=10)
    groups = result["groups"]

    assert all("特斯拉" not in r["title"] for r in groups[GROUP_HOLDING])
    tesla = next(r for r in groups[GROUP_MACRO] if "特斯拉" in r["title"])
    assert tesla["tier"] == TIER_WATCHLIST
    assert tesla["watchlist_hits"] == ["特斯拉"]

    nvidia = next(r for r in groups[GROUP_MACRO] if "英伟达" in r["title"])
    assert tesla["relevance"] > nvidia["relevance"], "自选应排在纯宏观之上"


def test_risk_pierce_lifts_severe_negative_macro_news():
    """挡机会不挡风险：重大负面外部新闻允许越过自选档。"""
    triage = NewsTriage(NewsFocusState(holdings=("宁德时代",)))

    severe = triage.score(
        {"title": "欧盟推进新一轮制裁", "importance_score": 0.95, "sentiment": 0.30}
    )
    assert severe.pierced is True
    assert severe.tier == TIER_PIERCE
    assert severe.relevance > 0.5
    assert any("穿透" in r for r in severe.reasons)

    # 反例 1：高重要度但情绪不负面 → 不穿透
    neutral = triage.score(
        {"title": "某地举办行业展会", "importance_score": 0.95, "sentiment": 0.80}
    )
    assert neutral.pierced is False and neutral.tier == TIER_MACRO

    # 反例 2：负面但重要度不够（且叙事风险中性）→ 不穿透
    minor = triage.score(
        {"title": "某公司小幅下调指引", "importance_score": 0.50, "sentiment": 0.20}
    )
    assert minor.pierced is False and minor.tier == TIER_MACRO


def test_pierce_never_masquerades_as_holding():
    """穿透可以抬排序，但**绝不能**冒充"我的持仓"（那是两件完全不同的事）。"""
    triage = NewsTriage(NewsFocusState(holdings=("宁德时代",)))
    scored = triage.score(
        {"title": "美联储紧急加息 50bp", "importance_score": 1.0, "sentiment": 0.2}
    )
    assert scored.pierced is True
    assert scored.group == GROUP_MACRO, "穿透条仍属外部要闻，不进行情组"
    assert scored.holding_hits == ()
    assert scored.relevance < TriageConfig().band(TIER_HOLDING).floor


def test_pierce_preserves_manas_narrative_risk_link():
    """穿透的第二条路径走 manas 叙事风险——保证这个信号不是死代码。"""
    risky = NewsFocusState(narrative_risk=0.75)
    calm = NewsFocusState(narrative_risk=0.20)
    item = {"title": "某宏观数据不及预期", "importance_score": 0.70, "sentiment": 0.30}

    assert NewsTriage(risky).score(item).pierced is True
    assert NewsTriage(calm).score(item).pierced is False


def test_bad_tier_env_falls_back_to_defaults_and_records_it():
    """环境变量调坏档位（重叠/语法错）→ 回退默认并留痕，不许静默算错。"""
    overlapping = TriageConfig.from_env(
        {"NAJA_NEWS_TIERS": "holding=0.30/0.10,theme=0.50/0.20,"
                            "watchlist=0.32/0.16,macro=0.00/0.24"}
    )
    assert overlapping.degraded and "回退默认" in overlapping.degraded[0]
    assert overlapping.validate() == []

    syntactically_bad = TriageConfig.from_env({"NAJA_NEWS_TIERS": "holding=0.78"})
    assert syntactically_bad.degraded and "解析失败" in syntactically_bad.degraded[0]

    good = TriageConfig.from_env(
        {"NAJA_NEWS_TIERS": "holding=0.85/0.15,theme=0.55/0.20,"
                            "watchlist=0.35/0.15,macro=0.00/0.25"}
    )
    assert good.degraded == ()
    assert good.band(TIER_HOLDING).floor == 0.85


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
    assert "持仓相关" in text
    assert "外部要闻" in text
    assert "宁德时代" in text


def test_digest_writes_daily_file():
    digest = build_digest(items=_items(), focus_state=_SAMPLE_FOCUS)
    out_dir = Path(tempfile.mkdtemp(prefix="naja_news_digest_test_"))
    path = write_daily_digest(digest, out_dir=out_dir)
    assert path.exists() and path.suffix == ".html"
    assert (out_dir / "latest.json").exists()
    reloaded = json.loads((out_dir / "latest.json").read_text(encoding="utf-8"))
    assert reloaded["stats"]["holding"] == 1
    assert reloaded["stats"]["macro"] == 3, "自选（特斯拉）已并入外部要闻"
    assert reloaded["stats"]["pierced"] == 1, "欧盟制裁那条应被风险穿透抬档"


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
    assert "持仓相关" in panel

    empty = render_news_digest_panel({"available": False, "reason": "没有数据"})
    assert "没有数据" in empty


def test_dashboard_monitor_data_has_news_digest_key():
    from deva.naja.attention.ui.dashboard import _get_empty_monitor_data

    data = _get_empty_monitor_data()
    assert "news_digest" in data
    assert set(data["news_digest"]["groups"]) == {GROUP_HOLDING, GROUP_THEME, GROUP_MACRO}
