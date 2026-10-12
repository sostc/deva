"""新闻焦点状态 —— 「我们到底该看什么」。

为什么放在 news 层：焦点状态是「新闻相关度」的**输入**，是新闻侧的概念。
manas 只负责提供它的注意力状态（关注主题 / 自选股 / 叙事风险），
本模块把它们抽成一个**纯数据快照**——既不重写 manas 的任何逻辑，
也让新闻筛选可以脱离容器单独测试（注入一个手搓的 ``NewsFocusState`` 即可）。

三条数据链（全部优雅降级，**降级必留痕**——本项目反复踩过的静默失效）：

  1. 持仓 / 自选股   ← ``attention.portfolio.get_portfolio()``（表 ``naja_watchlist``）
  2. 关注叙事 / 题材 ← ``attention.focus_manager``（表 ``naja_focus_config``）
  3. 关注主题        ← manas ``get_focus_themes()``（退化为 ``keyword_registry`` 预设）

实测坑（2026-10-12）：``naja_watchlist`` 里存的可能是**中文名**而不是代码
（如 ``宁德时代`` / ``lg新能源``），所以匹配必须**同时认代码与名称**，
只比代码会漏掉全部持仓相关新闻。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

# 焦点快照缓存：provider 会被**每条新闻**调用一次，不缓存会在 NB 读表上打爆
_FOCUS_CACHE_TTL: float = 60.0
_focus_cache: Optional["NewsFocusState"] = None
_focus_cache_ts: float = 0.0
_focus_cache_lock = threading.Lock()

# 太短的标识符（1 字符）做子串匹配会大量误命中，直接忽略
_MIN_IDENTIFIER_LEN = 2


@dataclass(frozen=True)
class NewsFocusState:
    """「我们关心什么」的不可变快照。

    冻结是为了让它可以安全地被缓存、被多条新闻并发读取、被当字典键用；
    需要一份改过的就 ``dataclasses.replace()`` 造新的一份。
    """

    # 【我们】持仓 / 自选（代码与中文名混在一起，都用来做文本匹配）
    holdings: Tuple[str, ...] = ()
    watchlist: Tuple[str, ...] = ()
    # 【关注】主动 follow 的叙事 / 题材
    narratives: Tuple[str, ...] = ()
    blocks: Tuple[str, ...] = ()
    # 【主题】manas 关注的叙事主题 → ((名称, (关键词...)), ...)
    themes: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()
    # 【风险】当前叙事风险（0-1，越高越该警惕）
    narrative_risk: float = 0.5
    # 【溯源】这份快照的数据来源（人可读）与降级原因（留痕，不做静默）
    sources: Tuple[str, ...] = ()
    degraded: Tuple[str, ...] = ()

    # ── 派生视图 ────────────────────────────────────────────────────────

    def own_identifiers(self) -> Tuple[str, ...]:
        """持仓 + 自选的标识符（代码/名称），去重保序。"""
        seen: Dict[str, None] = {}
        for ident in (*self.holdings, *self.watchlist):
            if ident:
                seen.setdefault(ident, None)
        return tuple(seen)

    def theme_names(self) -> Tuple[str, ...]:
        return tuple(name for name, _ in self.themes)

    def is_empty(self) -> bool:
        """完全没有焦点信息（用于如实报告「没数据」而不是「没命中」）。"""
        return not (self.holdings or self.watchlist or self.narratives or self.blocks or self.themes)

    # ── 匹配 ────────────────────────────────────────────────────────────

    def matched_own(self, *texts: str) -> Tuple[str, ...]:
        """命中持仓/自选标识符的部分。"""
        return _match_identifiers(self.own_identifiers(), *texts)

    def matched_holdings(self, *texts: str) -> Tuple[str, ...]:
        """只命中**持仓**的部分（权重高于自选）。"""
        return _match_identifiers(self.holdings, *texts)

    def matched_watchlist(self, *texts: str) -> Tuple[str, ...]:
        """只命中**自选**（不含持仓）的部分。"""
        holdings_lower = {h.lower() for h in self.holdings if h}
        rest = tuple(w for w in self.watchlist if w and w.lower() not in holdings_lower)
        return _match_identifiers(rest, *texts)

    def matched_narratives(self, *texts: str) -> Tuple[str, ...]:
        return _match_identifiers((*self.narratives, *self.blocks), *texts)

    def matched_themes(self, *texts: str) -> Tuple[str, ...]:
        """命中关注主题的名称或关键词。"""
        haystack = _haystack(texts)
        if not haystack:
            return ()
        hits: List[str] = []
        for name, keywords in self.themes:
            if name and name.lower() in haystack:
                hits.append(name)
                continue
            if any(_eligible(k) and k.lower() in haystack for k in keywords):
                hits.append(name)
        return tuple(dict.fromkeys(hits))

    def is_own(self, identifier: str) -> bool:
        ident = (identifier or "").strip()
        if not _eligible(ident):
            return False
        lowered = ident.lower()
        return any(lowered == x.lower() for x in self.own_identifiers())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "holdings": list(self.holdings),
            "watchlist": list(self.watchlist),
            "narratives": list(self.narratives),
            "blocks": list(self.blocks),
            "themes": [{"name": n, "keywords": list(k)} for n, k in self.themes],
            "narrative_risk": self.narrative_risk,
            "sources": list(self.sources),
            "degraded": list(self.degraded),
        }


def _eligible(text: str) -> bool:
    """长度太短的标识符不做子串匹配（防 1 字符噪声）。"""
    return bool(text) and len(text.strip()) >= _MIN_IDENTIFIER_LEN


def _haystack(texts: Sequence[str]) -> str:
    return " ".join(str(t) for t in texts if t).lower()


def _match_identifiers(identifiers: Sequence[str], *texts: str) -> Tuple[str, ...]:
    """在文本里找标识符（不区分大小写）。保持 identifiers 的原始大小写回传。"""
    haystack = _haystack(texts)
    if not haystack:
        return ()
    hits: List[str] = []
    for ident in identifiers:
        if not _eligible(ident):
            continue
        if ident.lower() in haystack and ident not in hits:
            hits.append(ident)
    return tuple(hits)


# ── 快照构建 ────────────────────────────────────────────────────────────


def build_focus_state(
    *,
    portfolio: Any = None,
    focus_manager: Any = None,
    manas_manager: Any = None,
    use_cache: bool = True,
) -> NewsFocusState:
    """构建当前焦点快照。每一步单独降级，失败只记 ``degraded`` 不抛。

    三个可选参数用于**依赖注入**（测试与验证脚本传假对象，
    生产走默认的全局单例访问器）。
    """
    global _focus_cache, _focus_cache_ts

    if use_cache:
        with _focus_cache_lock:
            if _focus_cache is not None and (time.time() - _focus_cache_ts) < _FOCUS_CACHE_TTL:
                return _focus_cache

    sources: List[str] = []
    degraded: List[str] = []
    holdings: Tuple[str, ...] = ()
    watchlist: Tuple[str, ...] = ()
    narratives: Tuple[str, ...] = ()
    blocks: Tuple[str, ...] = ()

    # 1. 持仓 / 自选
    try:
        pf = portfolio if portfolio is not None else _default_portfolio()
        if pf is None:
            degraded.append("持仓/自选：Portfolio 不可用")
        else:
            holdings = _collect_identifiers(_safe_call(pf, "get_holdings"), degraded, "持仓")
            watchlist = _collect_identifiers(_safe_call(pf, "get_watchlist"), degraded, "自选")
            sources.append("portfolio")
    except Exception as e:  # pragma: no cover - 防御
        degraded.append(f"持仓/自选：{type(e).__name__}: {e}")

    # 2. 关注叙事 / 题材
    try:
        fm = focus_manager if focus_manager is not None else _default_focus_manager()
        if fm is None:
            degraded.append("关注叙事：FocusManager 不可用")
        else:
            summary = _safe_call(fm, "get_summary")
            narratives = _collect_focus_ids(getattr(summary, "narratives", None))
            blocks = _collect_focus_ids(getattr(summary, "blocks", None))
            sources.append("focus_manager")
    except Exception as e:  # pragma: no cover - 防御
        degraded.append(f"关注叙事：{type(e).__name__}: {e}")

    # 3. 关注主题（manas）+ 叙事风险
    themes: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()
    narrative_risk = 0.5
    try:
        mgr = manas_manager if manas_manager is not None else _default_manas_manager()
        engine = mgr.get_manas_engine() if mgr is not None else None
        if engine is None:
            degraded.append("关注主题：manas 引擎不可用，退化为 keyword_registry 预设")
            themes = _fallback_themes()
        else:
            themes = _collect_themes(_safe_call(engine, "get_focus_themes"))
            if not themes:
                themes = _fallback_themes()
            sources.append("manas")
            narrative_risk = _read_narrative_risk(mgr, engine)
    except Exception as e:  # pragma: no cover - 防御
        degraded.append(f"关注主题：{type(e).__name__}: {e}")
        themes = _fallback_themes()

    state = NewsFocusState(
        holdings=holdings,
        watchlist=watchlist,
        narratives=narratives,
        blocks=blocks,
        themes=themes,
        narrative_risk=narrative_risk,
        sources=tuple(sources),
        degraded=tuple(degraded),
    )

    if degraded:
        log.info("[NewsFocus] 焦点快照降级 %d 处：%s", len(degraded), "；".join(degraded))

    if use_cache:
        with _focus_cache_lock:
            _focus_cache = state
            _focus_cache_ts = time.time()

    return state


def invalidate_focus_cache() -> None:
    """清掉焦点快照缓存（测试 / 验证脚本用）。"""
    global _focus_cache, _focus_cache_ts
    with _focus_cache_lock:
        _focus_cache = None
        _focus_cache_ts = 0.0


def build_manas_focus_state() -> Dict[str, Any]:
    """给 ``TextImportanceScorer`` 的 provider 适配器。

    ``TextImportanceScorer._get_focus_topic_matches`` 读的是
    ``{"focus_topics": [{"topic": ...}, ...]}``，而 manas 的
    ``get_focus_themes()`` 给的是 ``{"id","name","keywords"}``——形状不同，
    这层适配就是当年"看起来接了、其实从没接上"的地方，现在显式化。
    """
    state = build_focus_state()
    return {
        "focus_topics": [
            {"topic": name, "keywords": list(keywords)}
            for name, keywords in state.themes
        ],
        "watchlist": list(state.own_identifiers()),
        "narrative_risk": state.narrative_risk,
        "sources": list(state.sources),
        "degraded": list(state.degraded),
    }


# ── 内部：默认单例访问器（可失败，全部返回 None 走降级）──────────────


def _default_portfolio() -> Any:
    try:
        from deva.naja.attention.portfolio import get_portfolio

        return get_portfolio()
    except Exception as e:
        log.debug("[NewsFocus] Portfolio 访问失败: %s", e)
        return None


def _default_focus_manager() -> Any:
    try:
        from deva.naja.attention.focus_manager import get_attention_focus_manager

        return get_attention_focus_manager()
    except Exception as e:
        log.debug("[NewsFocus] FocusManager 访问失败: %s", e)
        return None


def _default_manas_manager() -> Any:
    try:
        from deva.naja.attention.kernel.manas_manager import get_manas_manager

        return get_manas_manager()
    except Exception as e:
        log.debug("[NewsFocus] ManasManager 访问失败: %s", e)
        return None


def _safe_call(obj: Any, method: str) -> Any:
    """调用可选方法；缺失或抛错都返回 None（由调用方决定降级语义）。"""
    fn = getattr(obj, method, None)
    if not callable(fn):
        return None
    try:
        return fn()
    except Exception as e:
        log.debug("[NewsFocus] %s.%s 调用失败: %s", type(obj).__name__, method, e)
        return None


def _collect_identifiers(items: Any, degraded: List[str], label: str) -> Tuple[str, ...]:
    """从 ``StockInfo`` 列表同时收 code 与 name —— 实测这两者都可能是中文名。"""
    if items is None:
        degraded.append(f"{label}：读取失败")
        return ()
    out: List[str] = []
    for it in items:
        code = getattr(it, "code", None)
        name = getattr(it, "name", None)
        for value in (code, name):
            if value and value not in out:
                out.append(str(value))
    return tuple(out)


def _collect_focus_ids(items: Any) -> Tuple[str, ...]:
    if not items:
        return ()
    out: List[str] = []
    for it in items:
        focus_id = getattr(it, "focus_id", None)
        if focus_id and focus_id not in out:
            out.append(str(focus_id))
    return tuple(out)


def _collect_themes(raw: Any) -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    if not raw:
        return ()
    out: List[Tuple[str, Tuple[str, ...]]] = []
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name") or item.get("id") or item.get("topic")
            keywords = item.get("keywords") or ()
        else:
            name, keywords = str(item), ()
        if not name:
            continue
        out.append((str(name), tuple(str(k) for k in keywords if k)))
    return tuple(out)


def _fallback_themes() -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    """manas 不可用时的退化路径：直接用认知层预设词表（与 manas 同源）。"""
    try:
        from deva.naja.cognition.semantic.keyword_registry import (
            DEFAULT_NARRATIVE_KEYWORDS,
        )
    except Exception as e:
        log.info("[NewsFocus] keyword_registry 亦不可用（%s），关注主题为空", e)
        return ()
    return tuple(
        (str(name), tuple(str(k) for k in keywords if k))
        for name, keywords in DEFAULT_NARRATIVE_KEYWORDS.items()
    )


def _read_narrative_risk(manager: Any, engine: Any) -> float:
    """尽力读叙事风险；读不到就返回中性 0.5（不假装知道）。"""
    state = _safe_call(manager, "get_state")
    if isinstance(state, dict) and "narrative_risk" in state:
        try:
            return float(state["narrative_risk"])
        except (TypeError, ValueError):
            pass
    cognitive = getattr(engine, "_cognitive_state", None)
    narrative = getattr(cognitive, "narrative", None)
    risk = getattr(narrative, "risk", None)
    if isinstance(risk, (int, float)):
        return float(risk)
    return 0.5


__all__ = [
    "NewsFocusState",
    "build_focus_state",
    "build_manas_focus_state",
    "invalidate_focus_cache",
]
