"""新闻相关度筛选器 —— 复用 manas 的注意力原则，落到「该看什么」。

manas 的本质是**注意力分配**：它输出「要不要动 / 多确信 / 多危险」。
新闻侧要的是同一个问题的另一种问法：「这条新闻值不值得占我的注意力」。

本模块不重造打分器。它站在已有的两层之上：

  1. ``TextImportanceScorer``      —— 通用新闻打分（新鲜度·关键词·叙事·来源）
  2. ``NewsFocusState``（本包）    —— 我们关心什么（持仓 / 自选 / 叙事 / 主题）

然后按**持仓优先**的口径给每条新闻算一个 ``relevance`` 并分组。
刻意与上面两层分开：评分器是通用能力（不认识持仓），本模块是应用口径。

────────────────────────────────────────────────────────────────────────
口径（2026-10-12 二次修订：从「加分制」改为「分档制」）
────────────────────────────────────────────────────────────────────────

**为什么不再用加分制**。旧版是 ``relevance = base*0.45 + bonus``，把持仓 +0.50、
自选 +0.38 之类的加成直接往上加。问题在于 ``base*0.45`` 是**所有新闻共享的地板**，
于是「持仓优先」只是*倾向于*成立，而不是*必然*成立。实测反例：

  * 自选反超持仓：自选条只要重要度高 0.267 就能压过持仓条
    （持仓 0.60 → 0.770；自选 0.90 → 0.785）——你**在看的票**挤掉了**你口袋里的票**。
  * 纯宏观反超持仓：持仓条重要度 0.05（一条无聊公告）→ 0.522，
    而宏观条重要度 1.00 且沾一个宽泛主题 → 0.550。

**新口径**：每条新闻按「最强命中」落进唯一一档，档位给出 ``relevance`` 的
**区间**，``base`` 只在区间内部做区分。四个区间**严格不重叠**：

    档位        归属分组     relevance 区间      计算式
    持仓命中    holding     [0.78, 1.00]       0.78 + 0.22 * base
    关注叙事    theme       [0.50, 0.74]       0.50 + 0.24 * base
    自选命中    macro       [0.32, 0.48]       0.32 + 0.16 * base
    外部宏观    macro       [0.00, 0.28]       0.00 + 0.24 * base（+ 主题微调 0.04）

于是有了**数学保证**：任何一条持仓新闻都排在所有非持仓新闻之前
（持仓下限 0.78 > 叙事上限 0.74）；关注列表整体弱于自己的叙事
（自选上限 0.48 < 叙事下限 0.50）。

**分组为什么不是四组而是三组**（用户 2026-10-12 选定）：自选股**不单独成组**，
并入「外部要闻」——用户的原话是"集中精力把自己的事情管管好，
不要太多想法去关注外面的机会"。自选虽然有独立档位（在组内排得比纯宏观高），
但视觉上它属于"外面"，不配和持仓并列。

**唯一例外：风险穿透**。挡机会 ≠ 挡风险——你持仓的公司恰恰最怕外部宏观冲击
（加息 / 制裁 / 供应链）。所以给外部条留一条窄缝，两条触发路径任一成立即抬档：

  * **严重度**：``base >= 0.85`` 且 ``sentiment <= 0.40``；
  * **manas 风险**：``narrative_risk >= 0.60`` 且 ``sentiment <= 0.40`` 且 ``base >= 0.60``。

命中就把它从宏观档抬到叙事档（``[0.50, 0.74]``），并在 reason 里标出来。
这是**刻意**的例外，不是 bug；``pierced=True`` 会在输出里留痕。
**已知副作用**：穿透条的数值可能高于主题组里的某几条，但因为它归属
「外部要闻」组、渲染在主题组之后，看起来会"数字大却排后面"。
这是刻意让**政策**（我的事优先）与**度量**（这条多值得看）分属两条轴——
不是排序 bug。

已知边界：穿透是**纯数值**判定，不认语义。一条重要度高、恰好被判为偏负面的
无关新闻也会被抬档。宁可多抬一条，也不要漏掉一条真的外部风险。

**分组里"叙事"和"主题"的区别**（实测踩到的坑，2026-10-12）：
manas 的默认主题集是 17 个**宽泛大类**（全球宏观 / 债券市场 / 外汇与美元 /
地缘政治…），它们的共同点是——**几乎命中所有新闻**。如果拿它来分组，
每条新闻都会进「关注主题」，分组就失去了区分度（实测 39 条全进 theme，
macro 恒空）。所以：

  * **theme 组** 只认**主动 follow** 的叙事 / 题材（``narratives`` / ``blocks``），
    这是窄而准的信号；
  * manas 默认主题只作**同档内的微调**（``THEME_NUDGE``），让"沾边但没关注"的
    新闻排在同分噪声之上，但不升级成一组、也不跨档。

**可调**：所有档位都能用环境变量 ``NAJA_NEWS_TIERS`` 覆盖，不必改代码：

    NAJA_NEWS_TIERS="holding=0.78/0.22,theme=0.50/0.24,watchlist=0.32/0.16,macro=0.00/0.24"

格式 ``档位=下限/权重``。解析失败或**区间重叠**时**回退到默认值并留痕**
（``config.degraded``）——本项目的规矩：宁可退回已知安全的口径，
也不要拿着一组算错的权重去排序。
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .dedup import detect_lang, find_groups, pick_representative
from .focus import NewsFocusState

log = logging.getLogger(__name__)


# ── 档位定义 ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TierBand:
    """一个档位的 ``relevance`` 区间：``[floor, floor + weight]``。

    ``floor`` 是**下限**（这条新闻最差也值这么多注意力），
    ``weight`` 决定 ``base`` 能在区间内把它抬多高。
    """

    floor: float
    weight: float

    @property
    def ceiling(self) -> float:
        return min(1.0, self.floor + self.weight)

    def apply(self, base: float) -> float:
        return min(1.0, max(0.0, self.floor + self.weight * base))

    def to_dict(self) -> Dict[str, float]:
        return {
            "floor": round(self.floor, 4),
            "ceiling": round(self.ceiling, 4),
            "weight": round(self.weight, 4),
        }


# 档位名（也是排序强度序：holding > theme > watchlist > macro）
TIER_HOLDING = "holding"
TIER_THEME = "theme"
TIER_WATCHLIST = "watchlist"
TIER_MACRO = "macro"
TIER_PIERCE = "pierce"
# 档位强度从高到低（供校验与展示）
TIER_ORDER: Tuple[str, ...] = (TIER_HOLDING, TIER_THEME, TIER_WATCHLIST, TIER_MACRO)

# 默认档位区间（设计意图见模块 docstring 的表格）
_DEFAULT_BANDS: Mapping[str, TierBand] = {
    TIER_HOLDING: TierBand(0.78, 0.22),    # [0.78, 1.00]
    TIER_THEME: TierBand(0.50, 0.24),      # [0.50, 0.74]
    TIER_WATCHLIST: TierBand(0.32, 0.16),  # [0.32, 0.48]
    TIER_MACRO: TierBand(0.00, 0.24),      # [0.00, 0.24]
}

# 宽泛主题命中时，在外部分组内做的微调（不跨档）
THEME_NUDGE = 0.04

# 风险穿透：宏观条越过这道门槛才被抬档
PIERCE_MIN_IMPORTANCE = 0.85
PIERCE_MAX_SENTIMENT = 0.40
# 穿透的第二条触发路径：manas 说叙事风险高 + 这条偏负面 + 中等重要度
# （旧版的 WEIGHT_RISK 就是这么门控的，现在把它从「+0.10」升级成「抬档」）
PIERCE_RELAXED_IMPORTANCE = 0.60
PIERCE_NARRATIVE_RISK = 0.60
# 穿透后落到哪一档（与叙事同档：足以被看见，但不冒充"我的钱"）
_PIERCE_BAND = TierBand(0.50, 0.24)

_ENV_VAR = "NAJA_NEWS_TIERS"


@dataclass(frozen=True)
class TriageConfig:
    """打分口径的可调快照。冻结 + 可校验，防止有人把区间调重叠了还不知道。"""

    bands: Mapping[str, TierBand] = field(default_factory=lambda: dict(_DEFAULT_BANDS))
    theme_nudge: float = THEME_NUDGE
    pierce_band: TierBand = _PIERCE_BAND
    pierce_min_importance: float = PIERCE_MIN_IMPORTANCE
    pierce_max_sentiment: float = PIERCE_MAX_SENTIMENT
    pierce_relaxed_importance: float = PIERCE_RELAXED_IMPORTANCE
    pierce_narrative_risk: float = PIERCE_NARRATIVE_RISK
    # 【溯源】配置来源与降级原因（不做静默）
    origin: str = "default"
    degraded: Tuple[str, ...] = ()

    def band(self, tier: str) -> TierBand:
        return self.bands.get(tier, _DEFAULT_BANDS[TIER_MACRO])

    # ── 校验：严格分层 ──────────────────────────────────────────────────

    def validate(self) -> List[str]:
        """返回违反「严格不重叠」的问题清单（空列表 = 合规）。

        这是本口径的**核心不变量**：档位必须从高到低严丝合缝，
        高位的下限要压住低位的上限。一旦重叠，
        "持仓永远优先"就不再是数学保证，而退回到"倾向于"。
        """
        problems: List[str] = []
        holding = self.band(TIER_HOLDING)
        theme = self.band(TIER_THEME)
        watchlist = self.band(TIER_WATCHLIST)
        macro = self.band(TIER_MACRO)

        for name in TIER_ORDER:
            band = self.band(name)
            if band.floor < 0:
                problems.append(f"{name}.floor 为负：{band.floor}")
            if band.floor + band.weight > 1.0 + 1e-9:
                problems.append(
                    f"{name} 区间越界：[{band.floor}, {band.floor + band.weight}]"
                )

        macro_top = macro.ceiling + self.theme_nudge
        if macro_top >= watchlist.floor - 1e-9:
            problems.append(
                f"宏观上限 {macro_top:.3f} 未压住自选下限 {watchlist.floor:.3f}"
            )
        if watchlist.ceiling >= theme.floor - 1e-9:
            problems.append(
                f"自选上限 {watchlist.ceiling:.3f} 未压住叙事下限 {theme.floor:.3f}"
            )
        if theme.ceiling >= holding.floor - 1e-9:
            problems.append(
                f"叙事上限 {theme.ceiling:.3f} 未压住持仓下限 {holding.floor:.3f}"
            )
        if self.pierce_band.floor < watchlist.ceiling - 1e-9:
            problems.append(
                f"穿透档下限 {self.pierce_band.floor:.3f} 低于自选上限 "
                f"{watchlist.ceiling:.3f}（穿透必须明显高于自选）"
            )
        return problems

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bands": {name: self.band(name).to_dict() for name in TIER_ORDER},
            "tier_order": list(TIER_ORDER),
            "theme_nudge": round(self.theme_nudge, 4),
            "pierce": {
                "band": self.pierce_band.to_dict(),
                "min_importance": self.pierce_min_importance,
                "max_sentiment": self.pierce_max_sentiment,
            },
            "origin": self.origin,
            "degraded": list(self.degraded),
        }

    # ── 环境变量覆盖 ────────────────────────────────────────────────────

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "TriageConfig":
        """从 ``NAJA_NEWS_TIERS`` 读覆盖；解析失败或区间重叠则回退默认并留痕。"""
        raw = (env if env is not None else os.environ).get(_ENV_VAR)
        if not raw or not raw.strip():
            return cls()

        try:
            bands: Dict[str, TierBand] = dict(_DEFAULT_BANDS)
            for chunk in raw.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                name, _, spec = chunk.partition("=")
                name = name.strip()
                if name not in _DEFAULT_BANDS:
                    raise ValueError(f"未知档位 {name!r}")
                floor_s, _, weight_s = spec.strip().partition("/")
                if not floor_s or not weight_s:
                    raise ValueError(f"档位 {name} 缺少 下限/权重")
                bands[name] = TierBand(float(floor_s), float(weight_s))
        except (ValueError, TypeError) as e:
            return cls(degraded=(f"{_ENV_VAR} 解析失败（{e}），已回退默认档位",))

        candidate = cls(bands=bands, origin=f"env:{_ENV_VAR}")
        problems = candidate.validate()
        if problems:
            return cls(
                degraded=(
                    f"{_ENV_VAR} 违反严格分层（{'；'.join(problems)}），已回退默认档位",
                )
            )
        return candidate


# ── 分组 ────────────────────────────────────────────────────────────────

GROUP_HOLDING = "holding"
GROUP_THEME = "theme"
GROUP_MACRO = "macro"
GROUP_ORDER: Tuple[str, ...] = (GROUP_HOLDING, GROUP_THEME, GROUP_MACRO)
GROUP_LABELS: Dict[str, str] = {
    GROUP_HOLDING: "持仓相关",
    GROUP_THEME: "关注叙事",
    GROUP_MACRO: "外部要闻（自选 / 宏观）",
}


@dataclass
class ScoredNews:
    """一条新闻的相关度判定结果（含判定理由，便于回溯"为什么推给我"）。"""

    item: Dict[str, Any]
    relevance: float
    base_importance: float
    group: str
    tier: str = TIER_MACRO
    tier_floor: float = 0.0
    tier_ceiling: float = 0.0
    pierced: bool = False
    holding_hits: Tuple[str, ...] = ()
    watchlist_hits: Tuple[str, ...] = ()
    narrative_hits: Tuple[str, ...] = ()
    theme_hits: Tuple[str, ...] = ()
    reasons: List[str] = field(default_factory=list)
    #: 这条代表了多少条原始记录（同一事件的中英双版/重发会折叠成一条）。
    #: 1 = 没有重复。UI 只在 >1 时显示 ``×N``。
    dup_count: int = 1

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
            "tier": self.tier,
            "tier_band": [round(self.tier_floor, 3), round(self.tier_ceiling, 3)],
            "pierced": self.pierced,
            # 呈现层只用它显示条数；1 表示这条没有并过别的记录
            "dup_count": int(self.dup_count or 1),
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

    def __init__(
        self,
        focus_state: Optional[NewsFocusState] = None,
        config: Optional[TriageConfig] = None,
    ) -> None:
        self.focus = focus_state if focus_state is not None else NewsFocusState()
        self.config = config if config is not None else TriageConfig.from_env()
        if self.config.degraded:
            log.warning("[NewsTriage] 口径配置降级：%s", "；".join(self.config.degraded))
        problems = self.config.validate()
        if problems:  # pragma: no cover - 防御：注入的 config 也可能是坏的
            log.error("[NewsTriage] 档位区间重叠，口径不安全：%s", "；".join(problems))

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
        sentiment = _as_float(item.get("sentiment"), default=0.5)

        holding_hits = self.focus.matched_holdings(*haystack)
        watchlist_hits = self.focus.matched_watchlist(*haystack)
        narrative_hits = self.focus.matched_narratives(*haystack)
        theme_hits = self.focus.matched_themes(*haystack)

        # ① 定档：取「最强命中」，一条新闻只落一档
        if holding_hits:
            tier = TIER_HOLDING
        elif narrative_hits:
            tier = TIER_THEME
        elif watchlist_hits:
            tier = TIER_WATCHLIST
        else:
            tier = TIER_MACRO

        # ② 风险穿透：挡机会不挡风险——重大负面外部新闻允许越过自选档
        pierced = False
        pierce_reason: Optional[str] = None
        if tier == TIER_MACRO:
            pierce_reason = self._pierce_reason(base, sentiment)
            if pierce_reason:
                tier = TIER_PIERCE
                pierced = True

        band = self.config.pierce_band if pierced else self.config.band(tier)

        # ③ 同档内微调：命中 manas 宽泛主题者排在同分噪声之上（不跨档）
        nudge = (
            self.config.theme_nudge
            if (tier == TIER_MACRO and theme_hits)
            else 0.0
        )

        relevance = min(1.0, max(0.0, band.apply(base) + nudge))

        reasons: List[str] = []
        if holding_hits:
            reasons.append(f"持仓命中：{'、'.join(holding_hits)}")
        if narrative_hits:
            reasons.append(f"关注叙事命中：{'、'.join(narrative_hits)}")
        if watchlist_hits:
            reasons.append(f"自选命中：{'、'.join(watchlist_hits)}（外部机会）")
        if theme_hits:
            reasons.append(
                f"关注主题命中：{'、'.join(theme_hits)}（宽泛主题，仅同档微调）"
            )
        if pierced:
            reasons.append(f"⚠️ 重大外部风险穿透：{pierce_reason}（挡机会不挡风险）")
        reasons.append(
            f"档位 {tier} [{band.floor:.2f}, {band.ceiling:.2f}] · 基础重要度 {base:.2f}"
        )

        return ScoredNews(
            item=item,
            relevance=relevance,
            base_importance=base,
            group=_group_for(holding_hits, narrative_hits),
            tier=tier,
            tier_floor=band.floor,
            tier_ceiling=band.ceiling,
            pierced=pierced,
            holding_hits=holding_hits,
            watchlist_hits=watchlist_hits,
            narrative_hits=narrative_hits,
            theme_hits=theme_hits,
            reasons=reasons,
        )

    def _pierce_reason(self, base: float, sentiment: float) -> Optional[str]:
        """判断这条外部新闻是否构成「风险穿透」，返回人话理由（不成立返回 None）。

        两条触发路径，任一成立即可（都是**刻意**的例外）：

          * 严重度：``base >= 0.85`` 且 ``sentiment <= 0.40``
            —— 突然的制裁 / 加息 / 黑天鹅，无需事先关注也该看见；
          * manas 风险：``narrative_risk >= 0.60`` 且 ``sentiment <= 0.40``
            且 ``base >= 0.60`` —— 沿用旧版 WEIGHT_RISK 的门控条件，
            让 manas 的叙事风险状态仍然**活着**（不是死代码）。

        已知边界：这是**纯数值**判定，不认语义。一条重要度高、
        恰好被判为偏负面的无关新闻也会被抬档——宁可多抬一条，
        也不要漏掉一条真的外部风险。
        """
        if sentiment > self.config.pierce_max_sentiment:
            return None
        if base >= self.config.pierce_min_importance:
            return f"重要度 {base:.2f} ≥ {self.config.pierce_min_importance:.2f} 且偏负面"
        if (
            self.focus.narrative_risk >= self.config.pierce_narrative_risk
            and base >= self.config.pierce_relaxed_importance
        ):
            return (
                f"叙事风险 {self.focus.narrative_risk:.2f} ≥ "
                f"{self.config.pierce_narrative_risk:.2f}，本条重要度 {base:.2f} 且偏负面"
            )
        return None

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

        deduped, dedup_stats = _dedupe(scanned)

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
            "tier_config": self.config.to_dict(),
            "focus": self.focus.to_dict(),
            "stats": {
                "scanned": len(scanned),
                "deduped": len(deduped),
                "shown": shown,
                "holding": len(groups[GROUP_HOLDING]),
                "theme": len(groups[GROUP_THEME]),
                "macro": len(groups[GROUP_MACRO]),
                "pierced": sum(1 for s in deduped if s.pierced),
                # 折叠掉的条数必须能看见——否则"去重了"与"去重没生效"不可区分
                # （旧版判据是标题全等，实测 101→101，一条都没去掉还不报错）。
                "merged": int(dedup_stats.get("merged", 0)),
                "merged_by_rule": dict(dedup_stats.get("by_rule") or {}),
            },
        }


def _group_for(
    holding_hits: Sequence[str], narrative_hits: Sequence[str]
) -> str:
    """档位 → 分组。自选档刻意归到「外部要闻」，不单独成组。

    分组看的是**语义**（这是不是我自己的钱 / 我自己的判断），
    与档位强弱是两条轴：自选在「外部要闻」组里排得比纯宏观高，但不和持仓并列。
    """
    if holding_hits:
        return GROUP_HOLDING
    if narrative_hits:
        return GROUP_THEME
    return GROUP_MACRO


def _dedupe(scored: Sequence[ScoredNews]) -> Tuple[List[ScoredNews], Dict[str, Any]]:
    """把**同一事件**的多条记录折成一条，返回 ``(代表列表, 统计)``。

    判据在 ``deva/naja/news/dedup.py``（L1 规范化精确 / L2 前缀包含 /
    L3 中英一对一配对）。旧版只按标题字符串全等去重，在真实数据上
    命中率是 0——金十每条快讯的中文版与英文版标题字符交集为 0，
    靠"长得像"永远合不上，所以改成按**发布时间结构**配对。

    折叠后的代表条有两个细节：
      * ``relevance`` 取簇内**最大值**——折叠不该让一条新闻排名下降；
      * ``pierced`` 取**或**——风险不能因为被并进英文版就丢掉。
    """
    if not scored:
        return [], {"input": 0, "output": 0, "merged": 0, "by_rule": {}}

    records = [{"title": s.title, "timestamp": s.timestamp} for s in scored]
    groups, stats = find_groups(records)

    out: List[ScoredNews] = []
    for members in groups:
        rep_i = pick_representative(records, members)
        rep = scored[rep_i]
        if len(members) > 1:
            langs = sorted({detect_lang(records[i]["title"]) for i in members})
            # 「判定」取簇内最强的一版，「文本」取中文代表条：
            # 同一事件的两版里，关键词命中往往只落在其中一版（中文原文提到
            # "越南"、英文版只写 Vietnam），单纯取相关度最大会让代表条
            # 挂着 0.42 分却落在错误的分组里。所以以最强证据为基底，
            # 只把 item（标题/时间/来源）换成中文那条。
            # 分档制保证档位区间**严格不重叠**，所以"相关度最高"就是"档位最强"，
            # 不需要再排一遍档位表。
            best_i = max(members, key=lambda i: scored[i].relevance)
            rep = replace(
                scored[best_i],
                item=rep.item,
                pierced=any(scored[i].pierced for i in members),
                dup_count=len(members),
                reasons=list(scored[best_i].reasons) + [
                    f"同一事件合并 {len(members)} 条（{'+'.join(langs)}）"
                ],
            )
        out.append(rep)
    return out, stats


def _as_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "NewsTriage",
    "ScoredNews",
    "TierBand",
    "TriageConfig",
    "GROUP_HOLDING",
    "GROUP_THEME",
    "GROUP_MACRO",
    "GROUP_ORDER",
    "GROUP_LABELS",
    "TIER_HOLDING",
    "TIER_THEME",
    "TIER_WATCHLIST",
    "TIER_MACRO",
    "TIER_PIERCE",
    "TIER_ORDER",
    "THEME_NUDGE",
    "PIERCE_MIN_IMPORTANCE",
    "PIERCE_MAX_SENTIMENT",
]
