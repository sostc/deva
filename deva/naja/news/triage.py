"""新闻相关度筛选器 —— 复用 manas 的注意力原则，落到「该看什么」。

manas 的本质是**注意力分配**：它输出「要不要动 / 多确信 / 多危险」。
新闻侧要的是同一个问题的另一种问法：「这条新闻值不值得占我的注意力」。

本模块不重造打分器。它站在已有的两层之上：

  1. ``TextImportanceScorer``      —— 通用新闻打分（新鲜度·关键词·叙事·来源）
  2. ``NewsFocusState``（本包）    —— 我们关心什么（持仓 / 自选 / 叙事 / 主题）

然后按**持仓优先**的口径给每条新闻算一个 ``relevance`` 并分组。
刻意与上面两层分开：评分器是通用能力（不认识持仓），本模块是应用口径。

口径（用户 2026-10-12 选定：持仓/自选最高优先）：

    持仓命中  +0.50   ← 「和我有关」的最强信号
    自选命中  +0.38
    关注叙事  +0.28   （主动 follow 的叙事 / 题材）
    关注主题  +0.10   （manas 默认主题集命中，**弱信号**）
    风险加成  +0.10   （叙事风险高 **且** 该条偏负面）

    relevance = clamp(base * 0.45 + bonus, 0, 1)

``base`` 取评分器的 ``importance_score``，只占 45%——保证一条"高重要度
但与我们无关"的宏观新闻，压不过一条"中等重要度但命中持仓"的新闻。

**分组为什么要区分"叙事"和"主题"**（实测踩到的坑，2026-10-12）：
manas 的默认主题集是 17 个**宽泛大类**（全球宏观 / 债券市场 / 外汇与美元 /
地缘政治…），它们的共同点是——**几乎命中所有新闻**。如果拿它来分组，
每条新闻都会进「关注主题」，分组就失去了区分度（实测 39 条全进 theme，
macro 恒空）。所以：

  * **theme 组** 只认**主动 follow** 的叙事 / 题材（``narratives`` / ``blocks``），
    这是窄而准的信号；
  * manas 默认主题只作**弱加权**，让"沾边但没关注"的新闻仍排在同分噪声之上，
    但不升级成一组。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .focus import NewsFocusState

log = logging.getLogger(__name__)

# 权重
WEIGHT_HOLDING = 0.50
WEIGHT_WATCHLIST = 0.38
WEIGHT_NARRATIVE = 0.28
WEIGHT_THEME = 0.10
WEIGHT_RISK = 0.10
BASE_RATIO = 0.45

# 叙事风险高于此值才算"该警惕"，配合负面情绪给加成
RISK_ALERT_THRESHOLD = 0.6
# 情绪低于此值视为偏负面（0=负面, 0.5=中性, 1=正面）
NEGATIVE_SENTIMENT_THRESHOLD = 0.4

GROUP_HOLDING = "holding"
GROUP_THEME = "theme"
GROUP_MACRO = "macro"
GROUP_ORDER: Tuple[str, ...] = (GROUP_HOLDING, GROUP_THEME, GROUP_MACRO)
GROUP_LABELS: Dict[str, str] = {
    GROUP_HOLDING: "持仓 / 自选相关",
    GROUP_THEME: "关注主题",
    GROUP_MACRO: "宏观与其它要闻",
}


@dataclass
class ScoredNews:
    """一条新闻的相关度判定结果（含判定理由，便于回溯"为什么推给我"）。"""

    item: Dict[str, Any]
    relevance: float
    base_importance: float
    group: str
    holding_hits: Tuple[str, ...] = ()
    watchlist_hits: Tuple[str, ...] = ()
    narrative_hits: Tuple[str, ...] = ()
    theme_hits: Tuple[str, ...] = ()
    reasons: List[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return str(self.item.get("title") or "")

    @property
    def timestamp(self) -> float:
        try:
            return float(self.item.get("timestamp") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def to_dict(self) -> Dict[str, Any]:
        ts = self.timestamp
        return {
            "title": self.title,
            "summary": self.item.get("summary") or self.title[:100],
            "url": self.item.get("url") or "",
            "source": self.item.get("source") or "",
            "timestamp": ts,
            "datetime": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "",
            "base_importance": round(self.base_importance, 3),
            "relevance": round(self.relevance, 3),
            "group": self.group,
            "holding_hits": list(self.holding_hits),
            "watchlist_hits": list(self.watchlist_hits),
            "narrative_hits": list(self.narrative_hits),
            "theme_hits": list(self.theme_hits),
            "stock_codes": list(self.item.get("stock_codes") or []),
            "topics": list(self.item.get("topics") or []),
            "sentiment": self.item.get("sentiment"),
            "reasons": list(self.reasons),
        }


class NewsTriage:
    """按「我们关心什么」给新闻排优先级。

    纯计算，无 I/O、无全局状态——传入什么焦点快照就按什么筛，
    因此可以用手搓的 ``NewsFocusState`` 直接单测。
    """

    def __init__(self, focus_state: Optional[NewsFocusState] = None) -> None:
        self.focus = focus_state if focus_state is not None else NewsFocusState()

    # ── 单条打分 ────────────────────────────────────────────────────────

    def score(self, item: Dict[str, Any]) -> ScoredNews:
        title = str(item.get("title") or "")
        text = str(item.get("text") or "")
        codes = " ".join(str(c) for c in (item.get("stock_codes") or []))
        topics = " ".join(str(t) for t in (item.get("topics") or []))
        # 新闻正文 + 已抽取的代码/主题都进匹配窗口：
        # 代码是上游已归一化的强信号，主题是上游已归类的结果。
        haystack: Tuple[str, ...] = (title, text, codes, topics)

        base = _as_float(item.get("importance_score"), default=0.5)
        base = min(1.0, max(0.0, base))

        holding_hits = self.focus.matched_holdings(*haystack)
        watchlist_hits = self.focus.matched_watchlist(*haystack)
        narrative_hits = self.focus.matched_narratives(*haystack)
        theme_hits = self.focus.matched_themes(*haystack)

        bonus = 0.0
        reasons: List[str] = []

        if holding_hits:
            bonus += WEIGHT_HOLDING
            reasons.append(f"持仓命中：{'、'.join(holding_hits)}")
        if watchlist_hits:
            bonus += WEIGHT_WATCHLIST
            reasons.append(f"自选命中：{'、'.join(watchlist_hits)}")
        if narrative_hits:
            bonus += WEIGHT_NARRATIVE
            reasons.append(f"关注叙事命中：{'、'.join(narrative_hits)}")
        if theme_hits:
            bonus += WEIGHT_THEME
            reasons.append(f"关注主题命中：{'、'.join(theme_hits)}（弱信号）")

        sentiment = _as_float(item.get("sentiment"), default=0.5)
        if (
            self.focus.narrative_risk >= RISK_ALERT_THRESHOLD
            and sentiment <= NEGATIVE_SENTIMENT_THRESHOLD
        ):
            bonus += WEIGHT_RISK
            reasons.append(
                f"叙事风险 {self.focus.narrative_risk:.2f} 偏高且本条偏负面"
            )

        relevance = min(1.0, max(0.0, base * BASE_RATIO + bonus))
        reasons.append(f"基础重要度 {base:.2f}")

        # 分组：只有**主动关注**的命中才升级成「关注主题」；
        # manas 默认主题集是宽泛大类（几乎人人命中），单独命中不构成一组。
        if holding_hits or watchlist_hits:
            group = GROUP_HOLDING
        elif narrative_hits:
            group = GROUP_THEME
        else:
            group = GROUP_MACRO

        return ScoredNews(
            item=item,
            relevance=relevance,
            base_importance=base,
            group=group,
            holding_hits=holding_hits,
            watchlist_hits=watchlist_hits,
            narrative_hits=narrative_hits,
            theme_hits=theme_hits,
            reasons=reasons,
        )

    # ── 批量分析 ────────────────────────────────────────────────────────

    def analyze(
        self,
        items: Iterable[Dict[str, Any]],
        *,
        per_group_limit: int = 8,
    ) -> Dict[str, Any]:
        """扫描一批新闻，返回分组排序结果（纯 dict，可直接 json.dumps）。"""
        scanned: List[ScoredNews] = []
        for item in items or ():
            if not isinstance(item, dict) or not item.get("title"):
                continue
            try:
                scanned.append(self.score(item))
            except Exception as e:  # pragma: no cover - 防御，单条坏了不拖垮整批
                log.debug("[NewsTriage] 单条打分失败，跳过：%s", e)

        deduped = _dedupe(scanned)

        groups: Dict[str, List[Dict[str, Any]]] = {g: [] for g in GROUP_ORDER}
        for scored in deduped:
            groups[scored.group].append(scored.to_dict())
        for group in GROUP_ORDER:
            groups[group].sort(
                key=lambda d: (d["relevance"], d["timestamp"]), reverse=True
            )
            del groups[group][per_group_limit:]

        shown = sum(len(v) for v in groups.values())
        return {
            "groups": groups,
            "group_labels": dict(GROUP_LABELS),
            "focus": self.focus.to_dict(),
            "stats": {
                "scanned": len(scanned),
                "deduped": len(deduped),
                "shown": shown,
                "holding": len(groups[GROUP_HOLDING]),
                "theme": len(groups[GROUP_THEME]),
                "macro": len(groups[GROUP_MACRO]),
            },
        }


def _dedupe(scored: Sequence[ScoredNews]) -> List[ScoredNews]:
    """同标题只留相关度最高的那条（重复推送是信息过载的主要来源之一）。"""
    best: Dict[str, ScoredNews] = {}
    for s in scored:
        key = s.title.strip()
        if not key:
            continue
        current = best.get(key)
        if current is None or s.relevance > current.relevance:
            best[key] = s
    return list(best.values())


def _as_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "NewsTriage",
    "ScoredNews",
    "GROUP_HOLDING",
    "GROUP_THEME",
    "GROUP_MACRO",
    "GROUP_ORDER",
    "GROUP_LABELS",
    "WEIGHT_HOLDING",
    "WEIGHT_WATCHLIST",
    "WEIGHT_NARRATIVE",
    "WEIGHT_THEME",
    "WEIGHT_RISK",
    "RISK_ALERT_THRESHOLD",
]
