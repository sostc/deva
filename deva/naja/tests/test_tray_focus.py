"""托盘信息聚焦 —— 时间线分类配额 + 通知聚合限流。

背景（2026-10-13）：托盘原来用 ``all_events[:15]`` 只按时间硬截断，
而 cn/us 板块异动是**秒级持续更新**的，时间戳永远最新 → 永远霸占全部名额
→ ``high_score_news`` / ``jin10_news`` 几乎永不进列表。连带
``_check_and_send_notifications``（只认新闻类、遍历同一列表）**实际永不触发** ——
典型「链路写了、数据不在同一条路上」的静默失效。

修完截断后单轮又可能出现多条达标新闻，于是通知必须**聚合 + 限流**，
否则从"从不响"直接跳到"轰炸"。
"""

import time

import pytest


# ── ① 时间线分类配额 select_timeline_events ──────────────────────────────


def _events():
    """30 条秒级板块异动 + 3 条高分新闻 + 1 条金十，按时间降序。"""
    ev = [{"type": "cn_event", "timestamp": 1000 + i, "block_name": f"X{i}"}
          for i in range(30)]
    ev += [{"type": "high_score_news", "timestamp": 900 + i, "title": f"N{i}"}
           for i in range(3)]
    ev += [{"type": "jin10_news", "timestamp": 800, "title": "J"}]
    ev.sort(key=lambda x: x["timestamp"], reverse=True)
    return ev


def test_quota_none_keeps_legacy_behaviour():
    """不传配额 → 保持旧的 [:15]（/market 等既有调用方行为完全不变）。"""
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        select_timeline_events,
    )

    picked = select_timeline_events(_events(), None)
    assert len(picked) == 15
    # 旧行为下全是秒级异动，新闻一条都进不来
    assert {e["type"] for e in picked} == {"cn_event"}


def test_quota_lets_news_through():
    """配额让新闻类一定有机会出现 —— 这是本次修复的核心。"""
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        TRAY_TIMELINE_LIMITS,
        select_timeline_events,
    )

    picked = select_timeline_events(_events(), TRAY_TIMELINE_LIMITS)
    types = [e["type"] for e in picked]
    assert "high_score_news" in types
    assert "jin10_news" in types


def test_quota_respects_per_type_limits():
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        select_timeline_events,
    )

    limits = {"high_score_news": 2, "jin10_news": 1, "cn_event": 1, "us_event": 0}
    picked = select_timeline_events(_events(), limits)
    counts = {}
    for e in picked:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    assert counts.get("high_score_news") == 2
    assert counts.get("jin10_news") == 1
    assert counts.get("cn_event") == 1
    assert "us_event" not in counts  # 配额 0 → 完全不出现


def test_quota_output_sorted_desc():
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        TRAY_TIMELINE_LIMITS,
        select_timeline_events,
    )

    picked = select_timeline_events(_events(), TRAY_TIMELINE_LIMITS)
    ts = [e["timestamp"] for e in picked]
    assert ts == sorted(ts, reverse=True)


def test_quota_empty_input():
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        TRAY_TIMELINE_LIMITS,
        select_timeline_events,
    )

    assert select_timeline_events([], TRAY_TIMELINE_LIMITS) == []


def test_tray_limits_cover_all_news_types():
    """配额表必须给两类新闻都留名额，否则又回到"新闻进不来"。"""
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        TRAY_TIMELINE_LIMITS,
    )

    assert TRAY_TIMELINE_LIMITS["high_score_news"] > 0
    assert TRAY_TIMELINE_LIMITS["jin10_news"] > 0


def test_timeline_api_applies_quota_only_when_passed():
    """get_timeline_data_for_api：传配额才生效，不传维持旧行为。"""
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        get_timeline_data_for_api,
    )

    # 真实链路（数据由外部决定），只断言不抛且 list 是列表
    d = get_timeline_data_for_api(hours=24)
    assert isinstance(d.get("list"), list)


def test_quota_dedups_same_block():
    """同类事件按标的去重：2 个 cn_event 名额 = 2 个不同板块。

    板块异动是同一板块每几秒刷一条，若不去重，配额会被同一板块的重复刷新吃光。
    """
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        select_timeline_events,
    )

    ev = [{"type": "cn_event", "timestamp": 2000 - i, "block_name": "同板块"}
          for i in range(5)]
    ev.append({"type": "cn_event", "timestamp": 1000, "block_name": "另一个板块"})
    ev.sort(key=lambda x: x["timestamp"], reverse=True)

    picked = select_timeline_events(ev, {"cn_event": 2})
    assert [e["block_name"] for e in picked] == ["同板块", "另一个板块"]


def test_quota_dedup_not_applied_in_legacy_mode():
    """不传配额 → 旧行为逐字保持（含不做去重），/market 不受影响。"""
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        select_timeline_events,
    )

    ev = [{"type": "cn_event", "timestamp": 100 - i, "block_name": "同板块"}
          for i in range(5)]
    assert len(select_timeline_events(ev, None)) == 5


def test_quota_input_order_independent():
    """内部自行排序，不依赖调用方先排好。"""
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        select_timeline_events,
    )

    ev = [{"type": "cn_event", "timestamp": t, "block_name": f"X{t}"}
          for t in (100, 300, 200)]
    picked = select_timeline_events(ev, {"cn_event": 1})
    assert picked[0]["timestamp"] == 300


def test_menu_cap_equals_quota_sum():
    """上屏上限只有一个来源：配额之和。"""
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        TRAY_MENU_MAX_EVENTS,
        TRAY_TIMELINE_LIMITS,
    )

    assert TRAY_MENU_MAX_EVENTS == sum(TRAY_TIMELINE_LIMITS.values())


def test_event_quota_below_news_quota():
    """速率最高的类型反而给得最少——按信息密度分配，不按产生速率。"""
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        TRAY_TIMELINE_LIMITS,
    )

    events = TRAY_TIMELINE_LIMITS["cn_event"] + TRAY_TIMELINE_LIMITS["us_event"]
    news = TRAY_TIMELINE_LIMITS["high_score_news"] + TRAY_TIMELINE_LIMITS["jin10_news"]
    assert events < news


# ── ①b 源端哨兵值渲染（999 = inf 编码）────────────────────────────────────


def test_format_change_percent_sentinel():
    """源端把 inf 写成 999，不能原样渲染成「+999.0%」。"""
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        format_change_percent,
    )

    assert format_change_percent(999) == "新进榜"
    assert format_change_percent(-999) == "新进榜"


def test_format_change_percent_normal():
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        format_change_percent,
    )

    assert format_change_percent(12.34) == "+12.3%"
    assert format_change_percent(-5) == "-5.0%"
    assert format_change_percent(0) == "+0.0%"


def test_format_change_percent_bad_input():
    """脏输入不炸——渲染层不该因为一个字段丢掉整条事件。"""
    from deva.naja.market_hotspot.ui_components.timeline.market_24h_timeline import (
        format_change_percent,
    )

    assert format_change_percent(None) == ""
    assert format_change_percent("x") == ""


# ── ② 托盘通知聚合限流 ──────────────────────────────────────────────────


def _tray(monkeypatch, news):
    """造一个托盘实例 + 捕获通知；隔离真实焦点快照。"""
    from deva.naja.infra.ui import menu_bar_tray as mbt

    t = mbt.MenuBarTray()
    t._naja_ready = True
    t._last_notify_ts = 0.0
    t._menu_cache = {"timeline": {"success": True, "list": list(news)}}
    sent = []
    monkeypatch.setattr(
        t, "_send_notification",
        lambda title, subtitle="", message="": sent.append((title, subtitle, message)),
    )
    monkeypatch.setattr(t, "_relevance_keywords", lambda: set())
    return t, sent


def test_notification_aggregates_multiple(monkeypatch):
    """多条达标新闻 → 只弹一条聚合通知，不再逐条轰炸。"""
    t, sent = _tray(monkeypatch, [
        {"type": "high_score_news", "timestamp": 1, "score": 0.9, "title": "A"},
        {"type": "jin10_news", "timestamp": 2, "score": 0.8, "title": "B"},
    ])
    t._check_and_send_notifications()
    assert len(sent) == 1
    assert "2 条" in sent[0][0]


def test_notification_single_passthrough(monkeypatch):
    """只有一条候选 → 原文直发（不套"1 条重要新闻"）。"""
    t, sent = _tray(monkeypatch, [
        {"type": "high_score_news", "timestamp": 1, "score": 0.9, "title": "A"},
    ])
    t._check_and_send_notifications()
    assert len(sent) == 1
    assert sent[0][0] == "A"


def test_notification_ignores_non_news(monkeypatch):
    """板块异动（cn/us event）永远不弹通知，哪怕分数很高。"""
    t, sent = _tray(monkeypatch, [
        {"type": "cn_event", "timestamp": 1, "score": 0.99, "title": "板块"},
    ])
    t._check_and_send_notifications()
    assert sent == []


def test_notification_score_threshold(monkeypatch):
    """低于分数线（0.7）不发。"""
    t, sent = _tray(monkeypatch, [
        {"type": "high_score_news", "timestamp": 1, "score": 0.5, "title": "低分"},
    ])
    t._check_and_send_notifications()
    assert sent == []


def test_notification_rate_limited(monkeypatch):
    """时间窗内即使有新候选也不重复发。"""
    t, sent = _tray(monkeypatch, [
        {"type": "high_score_news", "timestamp": 1, "score": 0.9, "title": "A"},
    ])
    t._check_and_send_notifications()
    assert len(sent) == 1

    # 新候选 + 时间窗未过 → 仍不发
    t._menu_cache = {"timeline": {"success": True, "list": [
        {"type": "high_score_news", "timestamp": 2, "score": 0.9, "title": "B"},
    ]}}
    t._check_and_send_notifications()
    assert len(sent) == 1


def test_notification_resumes_after_window(monkeypatch):
    """时间窗过后新候选正常发。"""
    t, sent = _tray(monkeypatch, [
        {"type": "high_score_news", "timestamp": 1, "score": 0.9, "title": "A"},
    ])
    t._check_and_send_notifications()
    assert len(sent) == 1

    t._last_notify_ts = time.time() - (t.NOTIFY_MIN_INTERVAL + 10)
    t._menu_cache = {"timeline": {"success": True, "list": [
        {"type": "high_score_news", "timestamp": 2, "score": 0.9, "title": "B"},
    ]}}
    t._check_and_send_notifications()
    assert len(sent) == 2
    assert sent[1][0] == "B"


def test_notification_relevance_first(monkeypatch):
    """持仓/关注主题命中的新闻排前面（副标题即最重要那条）。"""
    t, sent = _tray(monkeypatch, [
        {"type": "high_score_news", "timestamp": 1, "score": 0.99, "title": "无关新闻"},
        {"type": "jin10_news", "timestamp": 2, "score": 0.75, "title": "NVDA 获大单"},
    ])
    monkeypatch.setattr(t, "_relevance_keywords", lambda: {"nvda"})
    t._check_and_send_notifications()
    assert len(sent) == 1
    assert "NVDA" in sent[0][1]


def test_notification_dedup_within_window(monkeypatch):
    """已通知过的条目不会在窗口过期后重复出现。"""
    t, sent = _tray(monkeypatch, [
        {"type": "high_score_news", "timestamp": 1, "score": 0.9, "title": "A"},
    ])
    t._check_and_send_notifications()
    assert len(sent) == 1

    # 窗口过期，但列表内容没变（同一条已被标记）→ 不该重复发
    t._last_notify_ts = time.time() - (t.NOTIFY_MIN_INTERVAL + 10)
    t._check_and_send_notifications()
    assert len(sent) == 1
