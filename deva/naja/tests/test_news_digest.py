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

def test_news_page_fragment_renders_and_shows_honest_empty_state():
    """``/news`` 页面用的片段：自带样式、不带 <h1>、空态诚实。"""
    from deva.naja.news import render_digest_fragment

    digest = build_digest(items=_items(), focus_state=_SAMPLE_FOCUS)
    frag = render_digest_fragment(digest)
    assert frag.startswith("<style>"), "样式必须和正文一起输出（一次 put_html）"
    assert "持仓相关" in frag
    assert 'class="nj-digest' in frag
    assert "nj-digest-embed" in frag, "内嵌模式要铺纸底，否则卡片和白背景糊成一片"
    assert "<h1>" not in frag, "页面自己有标题，片段再来一个就成双标题"

    empty = render_digest_fragment({"available": False, "reason": "没有数据"})
    assert "没有数据" in empty


def test_dashboard_no_longer_carries_news_digest():
    """新闻消化已搬到独立页 ``/news``，觉醒页的数据出口不再背它。

    这条守的是「**不留两份 UI 各自漂移**」：面板删了但 dashboard 还在取数，
    或者反回来又塞一份紧凑面板，都会让两边口径慢慢分家。
    接线（页面函数 / 路由 / 导航）由 ``verify_news_digest`` ⑦ 静态守卫覆盖。
    """
    from deva.naja.attention.ui.dashboard import _get_empty_monitor_data

    assert "news_digest" not in _get_empty_monitor_data()


# ── 关注管理：持仓 → 主题推导 ────────────────────────────────────────────
#
# 这一段守的是「主题要长在持仓上」这条口径，以及三件容易静默出错的事：
#   1. 只取**直接**上下游（图谱的传递闭包会把二级供应商也塞进来）
#   2. 过宽词（AI）不得成为主题（否则分组失去区分度）
#   3. source 可审计 —— 撤销只删推导来源，绝不误伤用户手动关注


class _Meta:
    """假的板块元数据（advisor 只读 narrative / blocks）。"""

    def __init__(self, narrative="", blocks=()):
        self.narrative = narrative
        self.blocks = list(blocks)


class _FakeBlockMap:
    """假的板块映射（advisor 只调 get_metadata）。"""

    def __init__(self, mapping):
        self._m = dict(mapping)

    def get_metadata(self, code):
        return self._m.get(code)


class _Node:
    """假的图谱节点（advisor 只读 id / stock_code / name / type）。"""

    def __init__(self, node_id, stock_code=None, name="", node_type="company"):
        self.id = node_id
        self.stock_code = stock_code
        self.name = name
        self.type = node_type  # 注意：字符串没有 .value，走"非产品节点"分支


class _FakeGraph:
    """只实现 advisor 用到的最小面：get_stock_node + get_direct_*。"""

    def __init__(self):
        self.nodes = {}
        self._up = {}
        self._down = {}

    def add(self, code, name):
        self.nodes[code] = _Node(f"n:{code}", stock_code=code, name=name)
        return self.nodes[code]

    def wire(self, code, up=(), down=()):
        self._up[f"n:{code}"] = list(up)
        self._down[f"n:{code}"] = list(down)

    def get_stock_node(self, code):
        return self.nodes.get(code)

    def get_direct_upstream(self, node_id):
        return self._up.get(node_id, [])

    def get_direct_downstream(self, node_id):
        return self._down.get(node_id, [])


def _chain_graph():
    """nvda ← 台积电 ← 阿斯麦（二级）；nvda → 微软（需求端）。"""
    g = _FakeGraph()
    g.add("nvda", "英伟达")
    g.add("tsm", "台积电")
    g.add("asml", "阿斯麦")
    g.add("msft", "微软")
    g.wire("nvda", up=[g.nodes["tsm"]], down=[g.nodes["msft"]])
    g.wire("tsm", up=[g.nodes["asml"]])
    return g


def _chain_blocks():
    return _FakeBlockMap({
        "nvda": _Meta("AI芯片", ["AI", "半导体"]),   # AI 是过宽词
        "tsm": _Meta("晶圆代工", ["半导体"]),
        "asml": _Meta("光刻机", ["半导体设备"]),
        "msft": _Meta("云计算", ["云服务"]),
    })


class _TopicItem:
    """假的关注项（advisor 只读 focus_id / source / priority 等）。"""

    def __init__(self, focus_id, source="investigation", priority=0.7,
                 linked_blocks=(), display_name="", status="active"):
        self.focus_id = focus_id
        self.source = source
        self.priority = priority
        self.linked_blocks = list(linked_blocks)
        self.display_name = display_name or focus_id
        self.status = status
        self.add_time = 0.0


class _Summary:
    def __init__(self, narratives):
        self.narratives = narratives


class _FakeFocusManager:
    """记录 follow / unfollow 的关注管理器替身（不碰真实 DB）。"""

    def __init__(self, items=None):
        self._items = dict(items or {})
        self.followed = []
        self.unfollowed = []

    def get_watched_narratives(self):
        return list(self._items)

    def follow_narrative(self, name, priority=0.7, source="investigation", blocks=None):
        item = _TopicItem(name, source=source, priority=priority,
                          linked_blocks=blocks or ())
        self._items[name] = item
        self.followed.append((name, priority, source))
        return item

    def unfollow_narrative(self, name):
        self.unfollowed.append(name)
        self._items.pop(name, None)

    def get_summary(self):
        return _Summary(list(self._items.values()))

    def source_of(self, name):
        return self._items[name].source


def test_derive_topics_covers_self_upstream_downstream():
    """自身板块 / 直接上游 / 直接下游都要覆盖，且各按档位给分。"""
    from deva.naja.news.focus_advisor import (
        DERIVE_DOWNSTREAM_WEIGHT,
        DERIVE_SELF_WEIGHT,
        DERIVE_UPSTREAM_WEIGHT,
        derive_topics,
    )

    res = derive_topics([_Stock("nvda", "英伟达")],
                        graph=_chain_graph(), block_map=_chain_blocks())
    assert res["available"] is True, res
    topics = {t["topic"]: t for t in res["topics"]}

    assert topics["AI芯片"]["score"] == DERIVE_SELF_WEIGHT          # 自身
    assert topics["晶圆代工"]["score"] == DERIVE_UPSTREAM_WEIGHT     # 上游
    assert topics["云计算"]["score"] == DERIVE_DOWNSTREAM_WEIGHT     # 下游
    # 每个主题都要能解释"为什么推给我"
    assert all(t["evidence"] for t in res["topics"])
    assert any("上游供应链 → 台积电" in e for e in topics["晶圆代工"]["evidence"])
    assert any("下游需求端 → 微软" in e for e in topics["云计算"]["evidence"])


def test_derive_topics_only_walks_direct_neighbors():
    """只取**直接**上下游：二级上游（阿斯麦）不得混进来。

    图谱的 ``get_upstream(id, 1)`` 因 max_depth 语义（"额外跳数"）实走两跳，
    正是这条口径踩过的坑。
    """
    from deva.naja.news.focus_advisor import derive_topics

    res = derive_topics([_Stock("nvda", "英伟达")],
                        graph=_chain_graph(), block_map=_chain_blocks())
    names = {t["topic"] for t in res["topics"]}
    assert "晶圆代工" in names            # 一跳：台积电
    assert "光刻机" not in names          # 两跳：阿斯麦，属噪声
    assert "半导体设备" not in names


def test_derive_topics_filters_too_broad_words():
    """过宽词（AI）不得成为候选主题——否则"啥都命中"，分组失去区分度。"""
    from deva.naja.news.focus_advisor import TOO_BROAD_TOPICS, derive_topics

    res = derive_topics([_Stock("nvda", "英伟达")],
                        graph=_chain_graph(), block_map=_chain_blocks())
    names = {t["topic"] for t in res["topics"]}
    assert not (names & set(TOO_BROAD_TOPICS)), names
    assert "半导体" in names, "非过宽的同源主题应保留"


def test_derive_topics_consensus_bonus_uses_max_not_sum():
    """两只持仓共同指出同一主题 → 共识加分；同源重复贡献只取 max。"""
    from deva.naja.news.focus_advisor import (
        DERIVE_CONSENSUS_BONUS,
        DERIVE_MAX_SCORE,
        DERIVE_SELF_WEIGHT,
        DERIVE_UPSTREAM_WEIGHT,
        derive_topics,
    )

    g = _chain_graph()
    g.add("amd", "AMD")
    g.wire("amd", up=[g.nodes["tsm"]], down=[])
    blocks = _FakeBlockMap({
        "nvda": _Meta("AI芯片", ["AI", "半导体"]),
        "tsm": _Meta("晶圆代工", ["半导体"]),
        "msft": _Meta("云计算", ["云服务"]),
        "amd": _Meta("GPU", ["半导体"]),
    })

    res = derive_topics([_Stock("nvda", "英伟达"), _Stock("amd", "AMD")],
                        graph=g, block_map=blocks)
    topics = {t["topic"]: t for t in res["topics"]}

    assert topics["晶圆代工"]["score"] == round(
        DERIVE_UPSTREAM_WEIGHT + DERIVE_CONSENSUS_BONUS, 4)
    # 半导体同时被自身(0.60)命中 → max 取 0.60，再叠加共识
    assert topics["半导体"]["score"] == round(
        DERIVE_SELF_WEIGHT + DERIVE_CONSENSUS_BONUS, 4)
    assert topics["晶圆代工"]["from_holdings"] == ["amd", "nvda"]
    # 上限保护
    assert all(t["score"] <= DERIVE_MAX_SCORE for t in res["topics"])


def test_derive_topics_sorted_by_score_desc_then_name():
    from deva.naja.news.focus_advisor import derive_topics

    res = derive_topics([_Stock("nvda", "英伟达")],
                        graph=_chain_graph(), block_map=_chain_blocks())
    keys = [(-t["score"], t["topic"]) for t in res["topics"]]
    assert keys == sorted(keys), [t["topic"] for t in res["topics"]]


def test_derive_topics_no_holdings_is_honest():
    """没持仓 → available=False + reason，绝不兜底造主题。"""
    from deva.naja.news.focus_advisor import derive_topics

    res = derive_topics([], graph=_chain_graph(), block_map=_chain_blocks())
    assert res["available"] is False
    assert res["reason"]
    assert res["topics"] == []


def test_derive_topics_records_degradation_for_unmapped_and_missing():
    """图谱里有但板块表无映射 / 持仓不在图谱里 —— 都要留痕，不许静默漏掉。"""
    from deva.naja.news.focus_advisor import derive_topics

    g = _FakeGraph()
    g.add("nvda", "英伟达")
    g.add("xyz", "某未映射公司")
    g.wire("nvda", up=[g.nodes["xyz"]])
    res = derive_topics([_Stock("nvda", "英伟达")],
                        graph=g, block_map=_FakeBlockMap({"nvda": _Meta("AI芯片", ["半导体"])}))
    assert any("无映射" in d for d in res["degraded"]), res["degraded"]

    # 持仓压根不在图谱里 → 退化为"仅自身板块"并写明
    res2 = derive_topics([_Stock("nvda", "英伟达")],
                         graph=_FakeGraph(), block_map=_chain_blocks())
    assert res2["available"] is True
    assert any("图谱" in d for d in res2["degraded"]), res2["degraded"]


def test_derived_topic_to_dict_has_display_only_label():
    """to_dict 比 dataclass 多一个仅供展示的 relation_labels（有意为之）。"""
    from deva.naja.news.focus_advisor import DerivedTopic

    row = DerivedTopic(topic="晶圆代工", score=0.5, relations=("upstream",)).to_dict()
    assert row["relation_labels"] == ["上游供应链"]
    assert set(row) == {"topic", "score", "relations", "relation_labels",
                        "from_holdings", "evidence"}


def test_apply_marks_derived_and_never_overwrites_existing():
    """采纳写 source=derived；已存在的主题只记 already，绝不篡改其 source。"""
    from deva.naja.news.focus_advisor import SOURCE_DERIVED, apply_derived_topics

    fm = _FakeFocusManager(items={"已有关注": _TopicItem("已有关注", source="user")})
    topics = [
        {"topic": "晶圆代工", "score": 0.50},
        {"topic": "已有关注", "score": 0.90},
        {"topic": "太弱", "score": 0.30},
        {"topic": "", "score": 0.90},
    ]
    res = apply_derived_topics(topics, manager=fm)

    assert res["ok"] is True
    assert res["applied"] == ["晶圆代工"]
    assert res["already"] == ["已有关注"]
    assert fm.source_of("晶圆代工") == SOURCE_DERIVED
    assert fm.source_of("已有关注") == "user", "手动的 source 必须原样保留"
    assert any(s["topic"] == "太弱" for s in res["skipped"])

    # 幂等：再采纳一次不再重复写入
    again = apply_derived_topics(topics, manager=fm)
    assert again["applied"] == []


def test_apply_min_score_boundary_is_inclusive():
    """阈值是「低于才跳过」——恰好等于 0.50 的主题应被采纳。"""
    from deva.naja.news.focus_advisor import DEFAULT_APPLY_MIN_SCORE, apply_derived_topics

    fm = _FakeFocusManager()
    res = apply_derived_topics(
        [{"topic": "边界", "score": DEFAULT_APPLY_MIN_SCORE}], manager=fm)
    assert res["applied"] == ["边界"]


def test_apply_respects_revoked_only_when_asked(monkeypatch):
    """自动采纳跳过用户撤销过的主题；用户主动点采纳则照做。"""
    from deva.naja.news import focus_advisor as fa

    monkeypatch.setattr(fa, "_load_revoked", lambda: ["曾被撤销"])
    topics = [{"topic": "曾被撤销", "score": 0.8}]

    fm = _FakeFocusManager()
    auto = fa.apply_derived_topics(topics, manager=fm, respect_revoked=True)
    assert auto["applied"] == []
    assert any("撤销" in s["reason"] for s in auto["skipped"])

    fm2 = _FakeFocusManager()
    manual = fa.apply_derived_topics(topics, manager=fm2, respect_revoked=False)
    assert manual["applied"] == ["曾被撤销"]


def test_revoke_removes_only_derived_and_records_it(monkeypatch):
    """撤销只删 source=derived 的主题，并把它们记进"已撤销"名单。"""
    from deva.naja.news import focus_advisor as fa

    recorded = {}
    monkeypatch.setattr(fa, "_record_revoked",
                        lambda topics: (recorded.setdefault("topics", list(topics)), [])[1])

    fm = _FakeFocusManager()
    fm.follow_narrative("云计算", source=fa.SOURCE_DERIVED, priority=0.6)
    fm.follow_narrative("我的判断", source="user", priority=0.8)

    res = fa.revoke_derived_topics(manager=fm)

    assert res["ok"] is True
    assert res["removed"] == ["云计算"]
    assert "我的判断" in fm.get_watched_narratives(), "手动关注不得被误删"
    assert recorded["topics"] == ["云计算"]


def test_focus_admin_crud_via_pure_dict(monkeypatch):
    """后端 API 纯 dict 进出：增 / 改 / 删 三条路径 + 冲突与非法输入。"""
    from deva.naja.news import focus_admin as fadmin

    fm = _FakeFocusManager()
    monkeypatch.setattr(fadmin, "_fm", lambda: fm)
    monkeypatch.setattr(fadmin, "_invalidate_focus_cache", lambda: None)

    assert fadmin.add_topic("")["ok"] is False           # 空名拒绝
    added = fadmin.add_topic("新能源", priority=0.9)
    assert added["ok"] is True and added["topic"]["source"] == "user"
    assert fadmin.add_topic("新能源")["ok"] is False       # 重复拒绝，不覆盖

    listed = fadmin.list_topics()
    assert {r["topic"] for r in listed["manual"]} == {"新能源"}
    assert listed["derived"] == []

    updated = fadmin.update_topic("新能源", priority=0.4)
    assert updated["ok"] is True and updated["topic"]["priority"] == 0.4
    assert updated["topic"]["source"] == "user", "改优先级不得改 source"
    assert fadmin.update_topic("不在列表")["ok"] is False

    assert fadmin.remove_topic("新能源")["ok"] is True
    assert fadmin.remove_topic("新能源")["ok"] is False     # 已删再删拒绝
    assert fm.get_watched_narratives() == []


def test_focus_admin_update_topic_keeps_derived_source(monkeypatch):
    """推导来的主题改优先级后仍是 derived —— 否则撤销会漏掉它。"""
    from deva.naja.news import focus_admin as fadmin
    from deva.naja.news.focus_advisor import SOURCE_DERIVED

    fm = _FakeFocusManager(
        items={"GPU": _TopicItem("GPU", source=SOURCE_DERIVED, priority=0.6)})
    monkeypatch.setattr(fadmin, "_fm", lambda: fm)
    monkeypatch.setattr(fadmin, "_invalidate_focus_cache", lambda: None)

    res = fadmin.update_topic("GPU", priority=0.55)
    assert res["ok"] is True
    assert fm.source_of("GPU") == SOURCE_DERIVED


# ── 自选管理：naja_watchlist 的增删改查 ──────────────────────────────────
#
# 自选写的是 ``naja_watchlist`` 的 ``stocks`` 键。这一段守两件事：
#   1. 写自选**绝不能碰** ``ai_stocks``（预设 AI 股票池，manas 在用）
#   2. 写后用 ``get_watchlist()`` 必须立刻读到（缓存要失效，否则是"改了没生效"）


class _FakeNB:
    """内存版 NB（只实现 Portfolio 用到的那几个方法）。

    真表是全局 sqlite，单测往里写会污染真实自选数据，故整体替换掉。
    """

    _tables: dict = {}

    def __init__(self, name="default"):
        self._name = name
        _FakeNB._tables.setdefault(name, {})

    @classmethod
    def reset(cls):
        cls._tables = {}

    def __len__(self):
        return len(_FakeNB._tables[self._name])

    def keys(self):
        return list(_FakeNB._tables[self._name].keys())

    def __getitem__(self, key):
        return _FakeNB._tables[self._name][key]

    def get(self, key, default=None):
        return _FakeNB._tables[self._name].get(key, default)

    def update(self, mapping):
        _FakeNB._tables[self._name].update(dict(mapping))


def _make_watchlist_portfolio(monkeypatch, *, stocks=None, others=None, ai_stocks=None):
    """造一个只碰内存 NB 的 ``Portfolio``，与真实自选表完全隔离。

    注意 ``Portfolio`` 是 ``__new__`` 单例（``cls._instance``）——``Portfolio()``
    每次都返回**同一个**实例，所以必须显式 ``invalidate_cache()``，
    否则上一个用例留下的 5 分钟缓存会串到这一个（本项目"缓存静默陈旧"的老形状）。
    """
    from deva.naja.attention import portfolio as pfo

    _FakeNB.reset()
    seed = {}
    if stocks is not None:
        seed["stocks"] = list(stocks)
    if others is not None:
        seed["others"] = list(others)
    if ai_stocks is not None:
        seed["ai_stocks"] = ai_stocks
    if seed:
        _FakeNB("__test_watchlist__").update(seed)

    monkeypatch.setattr(pfo, "NB", _FakeNB)
    monkeypatch.setattr(pfo, "WATCHLIST_TABLE", "__test_watchlist__")
    pf = pfo.Portfolio()
    pf.invalidate_cache()
    return pf


def test_watchlist_crud_roundtrip(monkeypatch):
    pf = _make_watchlist_portfolio(
        monkeypatch, stocks=[{"code": "TSLA", "name": "特斯拉", "add_time": 100.0}])

    items = pf.list_watchlist_items()
    assert [i["code"] for i in items] == ["TSLA"]
    assert items[0]["name"] == "特斯拉"

    # 增：name 缺省时用 code 兜底
    added = pf.add_watchlist_item("nvda")
    assert added["ok"] is True and added["item"]["name"] == "nvda"
    assert {i["code"] for i in pf.list_watchlist_items()} == {"TSLA", "nvda"}

    assert pf.add_watchlist_item("NVDA")["ok"] is False, "重复应拒绝（大小写不敏感）"
    assert pf.add_watchlist_item("")["ok"] is False, "空代码应拒绝"

    # 改
    assert pf.update_watchlist_item("nvda", "英伟达")["ok"] is True
    assert any(i["code"] == "nvda" and i["name"] == "英伟达"
               for i in pf.list_watchlist_items())
    assert pf.update_watchlist_item("不存在", "x")["ok"] is False
    assert pf.update_watchlist_item("nvda", "")["ok"] is False, "空名称应拒绝"

    # 删
    assert pf.remove_watchlist_item("NVDA")["ok"] is True
    assert pf.remove_watchlist_item("NVDA")["ok"] is False
    assert [i["code"] for i in pf.list_watchlist_items()] == ["TSLA"]


def test_watchlist_write_never_touches_ai_stocks_pool(monkeypatch):
    """写自选绝不能碰 ``ai_stocks`` —— 那是预设 AI 股票池，manus/market_observer 在用。"""
    from deva.naja.attention import portfolio as pfo

    pf = _make_watchlist_portfolio(
        monkeypatch, stocks=[],
        ai_stocks={"stocks": [{"code": "AMD"}], "updated_at": 1})

    pf.add_watchlist_item("nvda", "英伟达")
    pf.update_watchlist_item("nvda", "NVIDIA")
    data = dict(pfo.NB("__test_watchlist__"))

    assert data["ai_stocks"]["stocks"][0]["code"] == "AMD", "预设池被动了"
    assert [s["code"] for s in data["stocks"]] == ["nvda"]


def test_watchlist_manages_legacy_others_bucket_too(monkeypatch):
    """历史 ``others`` 键里的自选也会被 ``get_watchlist()`` 读到，故也必须能删。"""
    pf = _make_watchlist_portfolio(
        monkeypatch, stocks=[], others=[{"code": "旧票", "name": "旧票", "add_time": 1.0}])

    assert "旧票" in {i["code"] for i in pf.list_watchlist_items()}
    assert pf.remove_watchlist_item("旧票")["ok"] is True
    assert pf.list_watchlist_items() == []


def test_watchlist_write_is_visible_to_get_watchlist(monkeypatch):
    """写后缓存必须失效 —— 否则新闻筛选要等 5 分钟才看到，会被当成 bug。"""
    pf = _make_watchlist_portfolio(monkeypatch, stocks=[])
    pf.add_watchlist_item("nvda", "英伟达")
    assert {s.code for s in pf.get_watchlist()} == {"nvda"}
    pf.remove_watchlist_item("nvda")
    assert pf.get_watchlist() == []


class _FakeWatchPortfolio:
    """focus_admin 只调这四个方法，替换掉真实 Portfolio（不碰 DB）。"""

    def __init__(self, items=None):
        self._items = {i["code"]: dict(i) for i in (items or [])}

    def list_watchlist_items(self):
        return list(self._items.values())

    def add_watchlist_item(self, code, name=""):
        if not str(code or "").strip():
            return {"ok": False, "reason": "空"}
        code = str(code).strip()
        if code.lower() in {k.lower() for k in self._items}:
            return {"ok": False, "reason": "已存在"}
        row = {"code": code, "name": name or code, "add_time": 1.0, "bucket": "stocks"}
        self._items[code] = row
        return {"ok": True, "reason": "", "item": row}

    def update_watchlist_item(self, code, name=None):
        hit = next((k for k in self._items if k.lower() == str(code).lower()), None)
        if hit is None or not name:
            return {"ok": False, "reason": "不存在"}
        self._items[hit]["name"] = name
        return {"ok": True, "reason": "", "item": self._items[hit]}

    def remove_watchlist_item(self, code):
        hit = next((k for k in self._items if k.lower() == str(code).lower()), None)
        if hit is None:
            return {"ok": False, "reason": "不存在"}
        del self._items[hit]
        return {"ok": True, "reason": "", "removed": code}


def test_focus_admin_watchlist_crud_via_pure_dict(monkeypatch):
    """后端 API 纯 dict 进出：增 / 改 / 删 + 冲突与非法输入 + 缓存失效。"""
    from deva.naja.news import focus_admin as fadmin

    fake = _FakeWatchPortfolio()
    invalidated = []
    monkeypatch.setattr(fadmin, "_pf", lambda: fake)
    monkeypatch.setattr(fadmin, "_invalidate_focus_cache", lambda: invalidated.append(1))

    listed = fadmin.list_watchlist()
    assert listed["ok"] is True and listed["count"] == 0

    assert fadmin.add_watchlist("")["ok"] is False          # 空拒绝
    added = fadmin.add_watchlist("nvda", "英伟达")
    assert added["ok"] is True
    assert fadmin.add_watchlist("NVDA")["ok"] is False       # 重复拒绝
    assert fadmin.list_watchlist()["count"] == 1

    assert fadmin.update_watchlist("nvda", "NVIDIA")["ok"] is True
    assert fadmin.update_watchlist("不在自选", "x")["ok"] is False

    assert fadmin.remove_watchlist("nvda")["ok"] is True
    assert fadmin.remove_watchlist("nvda")["ok"] is False     # 已删再删拒绝
    assert invalidated, "写操作必须失效焦点缓存"


def test_focus_admin_watchlist_degrades_honestly(monkeypatch):
    """读不到要如实报错（ok=False + reason），不兜底造空列表糊弄。"""
    from deva.naja.news import focus_admin as fadmin

    class _Boom:
        def list_watchlist_items(self):
            raise RuntimeError("模拟失败")

    monkeypatch.setattr(fadmin, "_pf", lambda: _Boom())
    res = fadmin.list_watchlist()
    assert res["ok"] is False and "模拟失败" in res["reason"]


def test_focus_overview_includes_watchlist_block(monkeypatch):
    """首屏总览必须带上自选块，否则 UI 里那一块没有数据源。"""
    from deva.naja.news import focus_admin as fadmin

    monkeypatch.setattr(fadmin, "list_topics", lambda: {"ok": True, "topics": []})
    monkeypatch.setattr(fadmin, "list_positions", lambda: {"ok": True, "accounts": []})
    monkeypatch.setattr(fadmin, "list_watchlist",
                        lambda: {"ok": True, "items": [], "count": 0})
    monkeypatch.setattr(fadmin, "derive_preview",
                        lambda max_topics=8: {"available": False})

    ov = fadmin.get_focus_overview()
    assert "watchlist" in ov and ov["watchlist"]["ok"] is True


def test_ui_watchlist_block_escapes_and_self_closes():
    """自选块：外部文本要转义；HTML 片段必须自闭合（PyWebIO 的老坑）。"""
    from deva.naja.news.ui import _watchlist_html

    html = _watchlist_html({"ok": True, "items": [
        {"code": "<b>x</b>", "name": "Tesla", "bucket": "stocks"}]})
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;" in html
    assert html.count("<div") == html.count("</div>"), "片段未闭合会被浏览器补成空壳"

    assert "（空）" in _watchlist_html({"ok": True, "items": []})
    assert "读取失败" in _watchlist_html({"ok": False, "reason": "挂了"})

