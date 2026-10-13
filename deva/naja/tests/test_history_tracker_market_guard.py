"""跨市场快照守卫 —— 防止 A 股板块被写进美股事件库（反之亦然）。

背景（2026-10-13）：CN / US **共用同一个 ``MarketHotspotHistoryTracker`` 单例**，
两个市场的快照被交错追加进同一个 ``self.snapshots`` 列表，于是
``record_snapshot`` → ``_detect_changes(old, new)`` 的 ``old`` / ``new``
**常常分属不同市场**。而该方法内部：

* ``all_blocks = set(old.block_weights) | set(new.block_weights)`` —— 取**两市场并集**；
* 落盘分流只看 ``old.market`` —— 写进的是"old 的市场"。

结果 ``old=US + new=CN`` 时，A 股板块（次新股 / 生物疫苗 / 中特估…）被打上 US
写进 ``us_block_events.json``。实测污染程度：us 库 300 条里 **269 条(90%) 是中文板块名**，
去重 140 个名字 **100% 是 cn 库的子集**；且 90% 的条目是 ``999`` 哨兵
（跨市场比对时"对方市场的板块在本市场恒为 0"），并产出过 **73613%** 这种无意义变化率。

修法：``_detect_changes`` 入口加一道「同市场才可比」守卫。本文件把它固化下来。
"""

import logging

import pytest


def _tracker():
    """构造一个副作用被屏蔽的 tracker（不推送事件、不落盘）。"""
    from deva.naja.market_hotspot.tracking.history_tracker import (
        MarketHotspotHistoryTracker,
    )

    tracker = MarketHotspotHistoryTracker()
    tracker.block_names = {"crypto": "加密", "ev": "电动车", "次新股": "次新股"}
    tracker.symbol_names = {}
    tracker._emit_hotspot_event = lambda **kw: None
    return tracker


def _snapshot(market, block_weights):
    from deva.naja.market_hotspot.tracking.history_tracker import HotspotSnapshot

    return HotspotSnapshot(
        timestamp=0.0,
        global_hotspot=0.5,
        block_weights=block_weights,
        symbol_weights={},
        market=market,
    )


def _events(tracker):
    return (list(tracker.block_hotspot_events_low)
            + list(tracker.block_hotspot_events_medium)
            + list(tracker.block_hotspot_events_high))


@pytest.fixture
def store_recorder(monkeypatch):
    """拦截两个落盘入口，记录「本该写到哪个库」。"""
    from deva.naja.market_hotspot.storing import block_events_store as bes

    written = {"cn": [], "us": []}
    monkeypatch.setattr(bes, "add_cn_block_event",
                        lambda data: written["cn"].append(data) or True)
    monkeypatch.setattr(bes, "add_us_block_event",
                        lambda data: written["us"].append(data) or True)
    return written


@pytest.fixture
def warning_records():
    """捕获 history_tracker 的 warning。

    项目日志配置成 ``propagate=False``（走自有 handler），pytest 的 ``caplog``
    挂在 root 上抓不到 —— 这里直接挂一个 handler 到模块 logger。
    """
    logger = logging.getLogger("deva.naja.market_hotspot.tracking.history_tracker")
    records = []

    class _Catcher(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Catcher(level=logging.WARNING)
    old_level, old_propagate = logger.level, logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)


# ── ① _market_key：只认明确的 CN / US ────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("CN", "CN"),
    ("US", "US"),
    ("cn", "CN"),          # 大小写不敏感
    (" us ", "US"),        # 去空白
    ("UNKNOWN", None),     # 兜底值必须视为不可比
    ("", None),
    (None, None),
    ("HK", None),          # 未知标识不猜
])
def test_market_key_only_accepts_known_markets(raw, expected):
    """``UNKNOWN`` 不能被静默当成 CN —— 否则又变成跨市场比对。"""
    from deva.naja.market_hotspot.tracking.history_tracker import _market_key

    assert _market_key(raw) == expected


# ── ② 跨市场配对：完全不产生事件 ─────────────────────────────────────────


@pytest.mark.parametrize("old_market,new_market", [
    ("US", "CN"),   # 曾导致 A 股板块写进 us 库
    ("CN", "US"),   # 曾导致 ev/crypto 混进 cn 库
])
def test_cross_market_pair_produces_no_events(old_market, new_market):
    tracker = _tracker()
    # 权重变化 400%（远超 5% 落盘阈值），若无守卫必然产生事件
    old = _snapshot(old_market, {"crypto": 0.1, "次新股": 0.1})
    new = _snapshot(new_market, {"crypto": 0.5, "次新股": 0.5})

    tracker._detect_changes(old, new, "2026-10-13 10:00:00")

    assert _events(tracker) == [], "跨市场配对不应产生任何板块事件"
    assert tracker.changes == [] or len(tracker.changes) == 0, "跨市场配对不应产生个股变化"


def test_cross_market_pair_writes_nothing_to_either_store(store_recorder):
    """核心回归：A 股板块名不得落进 us 库，美股板块名不得落进 cn 库。"""
    tracker = _tracker()
    old = _snapshot("US", {"crypto": 0.1})
    new = _snapshot("CN", {"次新股": 0.1, "复合铜箔": 0.1})

    tracker._detect_changes(old, new, "2026-10-13 10:00:00")
    # 反向配对再来一次
    tracker._detect_changes(new, old, "2026-10-13 10:00:01")

    assert store_recorder["us"] == [], f"us 库被写入: {store_recorder['us']}"
    assert store_recorder["cn"] == [], f"cn 库被写入: {store_recorder['cn']}"


def test_unknown_market_is_incomparable():
    """历史快照可能标 ``UNKNOWN``；与确知市场比对同样应跳过。"""
    tracker = _tracker()
    old = _snapshot("UNKNOWN", {"次新股": 0.1})
    new = _snapshot("CN", {"次新股": 0.5})

    tracker._detect_changes(old, new, "2026-10-13 10:00:00")

    assert _events(tracker) == []


# ── ③ 同市场必须照常工作（守卫不能过度拦截）────────────────────────────


def test_same_market_still_emits_events_and_writes_to_matching_store(store_recorder):
    tracker = _tracker()
    old = _snapshot("CN", {"次新股": 0.1})
    new = _snapshot("CN", {"次新股": 0.5})

    tracker._detect_changes(old, new, "2026-10-13 10:00:00")

    assert _events(tracker), "同市场配对必须照常产生事件"
    assert store_recorder["cn"], "同市场事件必须写入本市场库"
    assert store_recorder["us"] == [], "同市场事件不得写入对方库"
    assert all(e.market == "CN" for e in _events(tracker)), "事件 market 标识应为 new 的市场"


def test_same_us_market_routes_to_us_store(store_recorder):
    tracker = _tracker()
    old = _snapshot("US", {"crypto": 0.1})
    new = _snapshot("US", {"crypto": 0.5})

    tracker._detect_changes(old, new, "2026-10-13 10:00:00")

    assert store_recorder["us"], "美股同市场事件必须写入 us 库"
    assert store_recorder["cn"] == []


# ── ④ 量纲自检：超大变化率要"看得见"，但不能被悄悄丢 ──────────────────


def test_oversized_change_pct_warns_but_is_not_dropped(store_recorder, warning_records):
    """分母趋零算出的脏变化率照旧落盘（不改变行为），但必须留下 warning。"""
    tracker = _tracker()
    # old=1e-5 → new=0.5 ：变化率 ≈ 5,000,000%
    old = _snapshot("CN", {"次新股": 1e-5})
    new = _snapshot("CN", {"次新股": 0.5})

    tracker._detect_changes(old, new, "2026-10-13 10:00:00")

    assert any("超大权重变化率" in r.getMessage() for r in warning_records), \
        "超大变化率必须留下 warning（可发现性），否则又回到静默污染"
    assert store_recorder["cn"], "脏值不拦截——照旧落盘，只是不再静默"


def test_normal_change_pct_does_not_warn(warning_records):
    tracker = _tracker()
    old = _snapshot("CN", {"次新股": 0.1})
    new = _snapshot("CN", {"次新股": 0.5})

    tracker._detect_changes(old, new, "2026-10-13 10:00:00")

    assert not any("超大权重变化率" in r.getMessage() for r in warning_records), \
        "正常变化率不应产生噪音 warning"
