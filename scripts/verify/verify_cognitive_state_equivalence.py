#!/usr/bin/env python3
"""差分回归：`_supply_chain_state`(dict) → `_cognitive_state`(dataclass) 行为等价。

改动：ManasEngine 的认知层状态从 13 字段混合 dict 换成嵌套 dataclass
（NarrativeState / AiComputeState / WatchlistState / ResonanceState），
`_update_supply_chain_state` → `_update_cognitive_state`。

验证方式：把重构前的 dict 实现原样搬到这里当参照物，喂同一串事件，
逐字段比对新旧状态。覆盖：
  - 普通叙事事件 / 高重要性 / 高风险等级
  - AI 关键词 0、1、3 命中（对应衰减 / 轻增强 / 转 up）
  - 命中与未命中自选股
  - 共振事件（正向 / 负向 / 低分不生效）
  - focus_themes 是否在事件流中存活（旧实现曾把它清空）

跑法：
    TMPDIR=$(mktemp -d) python3 scripts/verify/verify_cognitive_state_equivalence.py
"""
import os
import sys
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from deva.naja.attention.kernel.manas_engine import (  # noqa: E402
    ManasEngine, CognitiveState, _RISK_LEVEL_SCORES, _AI_COMPUTE_KEYWORDS_LOWER,
)


# ── 参照物：重构前的 dict 实现（原样搬运，不做任何"顺手修正"）─────────────
def old_update(state, event):
    try:
        from deva.naja.events import CognitiveEventType
        event_type = event.event_type
    except Exception:
        CognitiveEventType = None
        event_type = getattr(event, "event_type", None)

    risk_level = event.risk_level if hasattr(event, 'risk_level') and event.risk_level else "LOW"
    new_risk = _RISK_LEVEL_SCORES.get(risk_level, 0.5)

    current_risk = state.get("narrative_risk", 0.5)
    updated_risk = current_risk * 0.7 + new_risk * event.importance * 0.3

    current_narratives = state.get("hot_narratives", [])
    new_narratives = []
    for narrative in event.narratives[:5]:
        new_narratives.append((narrative, event.importance))

    existing = {n[0]: n[1] for n in current_narratives}
    for narrative, importance in new_narratives:
        if narrative in existing:
            existing[narrative] = max(existing[narrative], importance)
        else:
            existing[narrative] = importance
    hot_narratives = sorted(existing.items(), key=lambda x: x[1], reverse=True)[:5]

    ai_compute_trend = state.get("ai_compute_trend", "neutral")
    ai_compute_strength = state.get("ai_compute_strength", 0.5)

    narratives_lower = [n.lower() for n in event.narratives]
    ai_hits = sum(1 for kw in _AI_COMPUTE_KEYWORDS_LOWER if any(kw in n for n in narratives_lower))

    if ai_hits >= 3:
        ai_compute_trend = "up"
        ai_compute_strength = min(1.0, ai_compute_strength * 0.8 + event.importance * 0.2)
    elif ai_hits >= 1 and event.importance > 0.7:
        ai_compute_strength = min(1.0, ai_compute_strength * 0.9 + event.importance * 0.1)
    else:
        ai_compute_strength = max(0.3, ai_compute_strength * 0.98)

    watchlist = state.get("watchlist", [])
    watchlist_bonus = state.get("watchlist_bonus", 1.0)
    event_stock_codes = getattr(event, 'stock_codes', []) or []

    watchlist_upper = [s.upper() for s in watchlist]
    event_stocks_upper = [s.upper() for s in event_stock_codes]

    if any(s in watchlist_upper for s in event_stocks_upper) and event_stocks_upper:
        watchlist_bonus = min(1.5, watchlist_bonus * 1.2)
    else:
        watchlist_bonus = max(1.0, watchlist_bonus * 0.99)

    resonance_score = state.get("resonance_score", 0.0)
    resonance_sentiment = state.get("resonance_sentiment", 0.0)
    resonance_blocks = state.get("resonance_blocks", [])
    resonance_updated = state.get("resonance_updated", 0.0)

    is_res = (
        event_type == getattr(CognitiveEventType, "RESONANCE_DETECTED", None)
        or str(getattr(event_type, "value", event_type)) == "resonance_detected"
    )
    if is_res:
        meta = getattr(event, "metadata", {}) or {}
        resonance_score = max(resonance_score, float(getattr(event, "importance", 0.0) or 0.0))
        resonance_sentiment = float(meta.get("sentiment", resonance_sentiment) or 0.0)
        block_id = meta.get("block_id") or meta.get("block_name") or ""
        if block_id:
            if block_id not in resonance_blocks:
                resonance_blocks = (resonance_blocks + [block_id])[-5:]
        resonance_updated = time.time()

        if resonance_sentiment < -0.2 and resonance_score > 0.7:
            updated_risk = min(1.0, updated_risk + 0.05)
        elif resonance_sentiment > 0.2 and resonance_score > 0.7:
            updated_risk = max(0.0, updated_risk - 0.03)

    state.update({
        "narrative_risk": max(0.0, min(1.0, updated_risk)),
        "hot_narratives": hot_narratives,
        "risk_level": risk_level if event.importance > 0.7 else state.get("risk_level", "LOW"),
        "last_update": time.time(),
        "ai_compute_trend": ai_compute_trend,
        "ai_compute_strength": ai_compute_strength,
        "watchlist": watchlist,
        "watchlist_bonus": watchlist_bonus,
        "resonance_score": resonance_score,
        "resonance_sentiment": resonance_sentiment,
        "resonance_blocks": resonance_blocks,
        "resonance_updated": resonance_updated,
    })
    return state


class Ev:
    def __init__(self, risk_level="LOW", importance=0.5, narratives=None,
                 stock_codes=None, event_type=None, metadata=None):
        self.risk_level = risk_level
        self.importance = importance
        self.narratives = narratives or []
        self.stock_codes = stock_codes or []
        self.event_type = event_type or types.SimpleNamespace(value="block_narrative_update")
        self.metadata = metadata


def old_snapshot(state):
    """把旧 dict 摊平成与新版同名的字段集合"""
    return {
        "narrative.risk": state.get("narrative_risk", 0.5),
        "narrative.level": state.get("risk_level", "LOW"),
        "narrative.hot_narratives": [tuple(x) for x in state.get("hot_narratives", [])],
        "ai_compute.trend": state.get("ai_compute_trend", "neutral"),
        "ai_compute.strength": state.get("ai_compute_strength", 0.5),
        "watchlist.codes": list(state.get("watchlist", [])),
        "watchlist.bonus": state.get("watchlist_bonus", 1.0),
        "resonance.score": state.get("resonance_score", 0.0),
        "resonance.sentiment": state.get("resonance_sentiment", 0.0),
        "resonance.blocks": list(state.get("resonance_blocks", [])),
        "focus_themes": state.get("focus_themes"),
    }


def new_snapshot(st):
    return {
        "narrative.risk": st.narrative.risk,
        "narrative.level": st.narrative.level,
        "narrative.hot_narratives": [tuple(x) for x in st.narrative.hot_narratives],
        "ai_compute.trend": st.ai_compute.trend,
        "ai_compute.strength": st.ai_compute.strength,
        "watchlist.codes": list(st.watchlist.codes),
        "watchlist.bonus": st.watchlist.bonus,
        "resonance.score": st.resonance.score,
        "resonance.sentiment": st.resonance.sentiment,
        "resonance.blocks": list(st.resonance.blocks),
        "focus_themes": st.focus_themes,
    }


EVENTS = [
    ("普通低重要性", Ev(importance=0.2, narratives=["无关新闻"])),
    ("高重要性高风险", Ev(risk_level="HIGH", importance=0.95, narratives=["地缘冲突升级"])),
    ("AI 3命中", Ev(importance=0.8, narratives=["AI算力需求爆发", "GPU供不应求", "数据中心扩张"])),
    ("AI 1命中+高重要性", Ev(importance=0.9, narratives=["芯片涨价"])),
    ("AI 1命中+低重要性", Ev(importance=0.4, narratives=["芯片涨价"])),
    ("无命中衰减", Ev(importance=0.5, narratives=["消费复苏"])),
    ("命中自选股", Ev(importance=0.8, narratives=["AI"], stock_codes=["NVDA"])),
    ("未命中自选股", Ev(importance=0.8, narratives=["AI"], stock_codes=["AAPL"])),
    ("共振正向", Ev(importance=0.9, event_type=types.SimpleNamespace(value="resonance_detected"),
                    metadata={"sentiment": 0.5, "block_id": "AI"})),
    ("共振负向", Ev(importance=0.85, event_type=types.SimpleNamespace(value="resonance_detected"),
                    metadata={"sentiment": -0.5, "block_name": "半导体"})),
    ("共振低分不生效", Ev(importance=0.5, event_type=types.SimpleNamespace(value="resonance_detected"),
                          metadata={"sentiment": 0.9})),
    ("共振重复板块", Ev(importance=0.8, event_type=types.SimpleNamespace(value="resonance_detected"),
                        metadata={"sentiment": 0.3, "block_id": "AI"})),
    # 连续衰减：让 bonus / strength 走到底再拉起来
    ("衰减x5", Ev(importance=0.3, narratives=["无关"])),
    ("衰减x6", Ev(importance=0.3, narratives=["无关"])),
    ("衰减x7", Ev(importance=0.3, narratives=["无关"])),
]


def main():
    # 旧实现：dict 起手，focus_themes 用默认主题（与新版同源）
    themes = [{"id": "AI", "name": "AI", "keywords": ["AI"]}] * 3
    old = {
        "narrative_risk": 0.5, "hot_narratives": [], "risk_level": "LOW", "last_update": 0.0,
        "ai_compute_trend": "neutral", "ai_compute_strength": 0.5,
        "watchlist": ["NVDA", "AMD"], "watchlist_bonus": 1.0,
        "focus_themes": themes,
        "resonance_score": 0.0, "resonance_sentiment": 0.0,
        "resonance_blocks": [], "resonance_updated": 0.0,
    }

    eng = ManasEngine.__new__(ManasEngine)
    st = CognitiveState(focus_themes=themes)
    st.watchlist.codes = ["NVDA", "AMD"]
    eng._cognitive_state = st

    checked = 0
    for name, ev in EVENTS:
        old_update(old, ev)
        eng._update_cognitive_state(ev)

        o, n = old_snapshot(old), new_snapshot(st)
        assert set(o) == set(n), (name, set(o) ^ set(n))
        for k in o:
            ov, nv = o[k], n[k]
            if isinstance(ov, float) and isinstance(nv, float):
                same = abs(ov - nv) < 1e-12
            else:
                same = ov == nv
            assert same, f"[{name}] {k}: 旧 {ov} != 新 {nv}"
            checked += 1

        # 每轮都确认 focus_themes 活着（旧实现靠 update 保留，新版靠不动它）
        assert len(st.focus_themes) == len(themes), f"[{name}] focus_themes 被清空"

    # 共振时间戳与 last_update 都已刷新
    assert st.resonance.updated > 0, "resonance.updated 未刷新"
    assert st.last_update > 0, "last_update 未刷新"

    print(f"{len(EVENTS)} 个事件 x {len(old_snapshot(old))} 个字段，"
          f"共 {checked} 次比对全部一致")
    print("focus_themes 全程存活 OK")
    print("\nALL PASS")


if __name__ == "__main__":
    main()
