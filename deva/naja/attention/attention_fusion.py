"""
AttentionFusion - 注意力融合层（四层架构）

Layer 0: 外部世界（External World）
  WorldNarrativeTracker → 新闻/舆论分析出的热点
  BlockAttentionEngine → 市场定价过程的热度

Layer 1: 我们的价值追求（Our Value Pursuit）
  Portfolio → 持仓 + 自选股
  WatchedNarratives → 我们关注的叙事（从持仓/自选推导）

Layer 2: 价值验证（Conviction Validation）
  ConvictionValidator → 外部热点 vs 我们关注的一致性

Layer 3: 时机选择（Timing）
  热度低 = 可能是布局窗口
  热度高 = 可能已反映价值

融合公式：
  final_score[bid] =
      α × conviction_weight[bid]     # 信念权重（价值验证层）
    + β × market_attention[bid]       # 市场热度
    + γ × timing_bonus[bid]           # 时机加成

作者: AI
日期: 2026-04-05
"""

from __future__ import annotations
import time
from typing import Dict, List, Optional, Set, Tuple, Any, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from deva.naja.attention.portfolio import Portfolio, PortfolioSummary
    from deva.naja.attention.conviction_validator import ConvictionValidator, ValidationResult
    from deva.naja.attention.narrative_block_linker import NarrativeBlockLinker
    from deva.naja.attention.block_registry import BlockRegistry


@dataclass
class FusionSignal:
    """融合信号（供ManasEngine使用）"""
    block_id: str
    fused_score: float
    market_attention: float
    conviction_score: float
    timing_signal: str
    holding_status: str
    action_recommendation: str

    conviction_level: str
    timing_level: str

    should_act: bool
    action_reason: str


@dataclass
class FullFusionResult:
    """完整融合结果"""
    signals: List[FusionSignal]
    consensus_blocks: List[Tuple[str, float]]
    divergence_blocks: List[Tuple[str, float]]
    blind_spots: List[Tuple[str, float]]
    new_hot_blocks: List[Tuple[str, float]]

    conviction_score: float
    timing_signal: str
    overall_should_act: bool
    overall_action_reason: str

    portfolio_blocks: Set[str]
    watchlist_blocks: Set[str]
    holding_codes: Set[str]
    watchlist_codes: Set[str]

    timestamp: float = field(default_factory=time.time)


class AttentionFusion:
    """
    四层注意力融合器

    使用方式:

        fusion = AttentionFusion()

        result = fusion.fuse(
            market_attention=block_engine.get_all_weights(filter_noise=True),
            world_narrative={"AI": 0.8, "芯片": 0.6},
            portfolio_summary=pf.get_summary(),
        )

        # 获取交易信号
        signals = result.signals
        for s in signals[:5]:
            if s.should_act:
                print(f"Buy {s.block_id}: {s.action_reason}")

        # 获取信念验证结果
        print(f"信念度: {result.conviction_score}")
        print(f"时机信号: {result.timing_signal}")
    """

    def __init__(
        self,
        portfolio: Optional["Portfolio"] = None,
        validator: Optional["ConvictionValidator"] = None,
        linker: Optional["NarrativeBlockLinker"] = None,
        registry: Optional["BlockRegistry"] = None,
        narrative_tracker: Optional[Any] = None,
        focus_manager: Optional[Any] = None,
    ):
        from deva.naja.attention.portfolio import get_portfolio
        from deva.naja.attention.conviction_validator import get_conviction_validator
        from deva.naja.attention.narrative_block_linker import get_narrative_block_linker
        from deva.naja.attention.block_registry import get_block_registry

        self.portfolio = portfolio or get_portfolio()
        self.validator = validator or get_conviction_validator()
        self.linker = linker or get_narrative_block_linker()
        self.registry = registry or get_block_registry()
        self._narrative_tracker = narrative_tracker
        self._focus_manager = focus_manager

        self._alpha: float = 0.4
        self._beta: float = 0.4
        self._gamma: float = 0.2

        self._hot_threshold: float = 0.3
        self._cold_threshold: float = 0.1

        self._last_result: Optional[FullFusionResult] = None

    def _get_user_focus_narratives(self) -> List[str]:
        """从FocusManager获取用户主动关注的叙事"""
        if self._focus_manager is not None:
            return self._focus_manager.get_watched_narratives()
        try:
            from deva.naja.attention.focus_manager import get_attention_focus_manager
            fm = get_attention_focus_manager()
            return fm.get_watched_narratives()
        except Exception:
            return []

    def _get_world_narrative(self) -> Dict[str, float]:
        """从NarrativeTracker获取外部公共叙事"""
        if self._narrative_tracker is not None:
            return self._narrative_tracker.get_world_narrative()
        try:
            from deva.naja.cognition.narrative_tracker import get_narrative_tracker
            tracker = get_narrative_tracker()
            return tracker.get_world_narrative()
        except Exception:
            return {}

    def fuse(
        self,
        market_attention: Dict[str, float],
        portfolio_summary: Optional["PortfolioSummary"] = None,
        world_narrative: Optional[Dict[str, float]] = None,
        user_focus_narratives: Optional[List[str]] = None,
    ) -> FullFusionResult:
        """
        执行四层融合

        Args:
            market_attention: 市场热度 {block_id: weight}
            portfolio_summary: 持仓汇总（可选，不传则自动获取）
            world_narrative: 外部叙事热点 {narrative: weight}
            user_focus_narratives: 用户额外关注的叙事列表

        Returns:
            FullFusionResult: 完整融合结果
        """
        if portfolio_summary is None:
            portfolio_summary = self.portfolio.get_summary()

        if world_narrative is None:
            world_narrative = self._get_world_narrative()

        validation = self.validator.validate(
            portfolio=portfolio_summary,
            market_attention=market_attention,
            world_narrative=world_narrative,
        )

        timing_signal, timing_confidence = self.validator.get_timing_signal()

        holding_blocks = portfolio_summary.block_alloc.keys()
        watchlist_blocks = self.portfolio.get_watchlist_blocks()
        holding_codes = portfolio_summary.holding_codes
        watchlist_codes = portfolio_summary.watchlist_codes

        conviction_by_block: Dict[str, float] = {}
        for bid, _ in validation.consensus_blocks:
            conviction_by_block[bid] = 0.8
        for bid, _ in validation.divergence_blocks:
            conviction_by_block[bid] = 0.3
        for bid, _ in validation.blind_spots:
            conviction_by_block[bid] = 0.5
        for bid, _ in validation.new_hot_blocks:
            conviction_by_block[bid] = 0.6

        all_blocks = set(market_attention.keys())
        for bid in list(holding_blocks) + list(watchlist_blocks):
            all_blocks.add(bid)

        signals: List[FusionSignal] = []

        for block_id in all_blocks:
            m_attn = market_attention.get(block_id, 0.0)
            conv_w = conviction_by_block.get(block_id, 0.0)

            timing_bonus = 0.0
            if timing_signal == "timing_good":
                timing_bonus = 0.2 if conv_w >= 0.5 else 0.1
            elif timing_signal == "timing_hot":
                timing_bonus = -0.1

            fused_score = (
                self._alpha * conv_w +
                self._beta * m_attn +
                self._gamma * timing_bonus
            )

            if block_id in holding_blocks:
                holding_status = "holding"
            elif block_id in watchlist_blocks:
                holding_status = "watchlist"
            else:
                holding_status = "untracked"

            if holding_status == "untracked" and m_attn >= self._hot_threshold:
                action = "consider_watchlist"
            elif holding_status == "watchlist" and conv_w >= 0.6:
                action = "consider_buy"
            elif holding_status == "holding":
                if conv_w >= 0.5 and timing_signal == "timing_hot":
                    action = "hold_or_add"
                elif conv_w < 0.3:
                    action = "review_exit"
                elif timing_signal == "timing_good" and conv_w >= 0.5:
                    action = "add_position"
                else:
                    action = "hold"
            else:
                action = "monitor"

            conviction_level = (
                "strong" if conv_w >= 0.7
                else "moderate" if conv_w >= 0.4
                else "weak"
            )

            timing_level = (
                "good" if timing_signal == "timing_good"
                else "hot" if timing_signal == "timing_hot"
                else "neutral"
            )

            should_act = (
                action in ("consider_buy", "add_position", "consider_watchlist")
                and conv_w >= 0.5
            )

            signals.append(FusionSignal(
                block_id=block_id,
                fused_score=fused_score,
                market_attention=m_attn,
                conviction_score=conv_w,
                timing_signal=timing_signal,
                holding_status=holding_status,
                action_recommendation=action,
                conviction_level=conviction_level,
                timing_level=timing_level,
                should_act=should_act,
                action_reason=f"{action}: conviction={conv_w:.2f}, timing={timing_signal}",
            ))

        signals.sort(key=lambda s: s.fused_score, reverse=True)

        overall_should_act = (
            timing_signal == "timing_good"
            and validation.conviction_score >= 0.5
            and any(s.should_act for s in signals)
        )

        if overall_should_act:
            top_action = next((s for s in signals if s.should_act), None)
            overall_reason = (
                f"{top_action.block_id}: {top_action.action_reason}"
                if top_action else ""
            )
        else:
            if validation.conviction_score < 0.3:
                overall_reason = f"low_conviction: {validation.conviction_score:.2f}"
            elif timing_signal == "timing_wait":
                overall_reason = "timing_uncertain"
            else:
                overall_reason = f"{timing_signal}: conviction={validation.conviction_score:.2f}"

        result = FullFusionResult(
            signals=signals,
            consensus_blocks=validation.consensus_blocks,
            divergence_blocks=validation.divergence_blocks,
            blind_spots=validation.blind_spots,
            new_hot_blocks=validation.new_hot_blocks,
            conviction_score=validation.conviction_score,
            timing_signal=timing_signal,
            overall_should_act=overall_should_act,
            overall_action_reason=overall_reason,
            portfolio_blocks=set(holding_blocks),
            watchlist_blocks=watchlist_blocks,
            holding_codes=holding_codes,
            watchlist_codes=watchlist_codes,
        )

        self._last_result = result
        return result

    def get_top_signals(self, top_k: int = 10) -> List[FusionSignal]:
        """获取排名最高的信号"""
        if self._last_result is None:
            return []
        return self._last_result.signals[:top_k]

    def get_actionable_signals(self) -> List[FusionSignal]:
        """获取可执行的信号"""
        if self._last_result is None:
            return []
        return [s for s in self._last_result.signals if s.should_act]

    def get_manas_input(self) -> Dict[str, Any]:
        """
        获取供ManasEngine使用的输入

        Returns:
            {
                "conviction_score": 0.65,
                "timing_signal": "timing_good",
                "should_act": True,
                "top_blocks": ["AI", "芯片"],
                "blind_spots": ["固态电池"],
                "holding_blocks": ["AI", "芯片"],
                "watchlist_blocks": ["AMD", "ASML"],
            }
        """
        if self._last_result is None:
            return {}
        r = self._last_result
        return {
            "conviction_score": r.conviction_score,
            "timing_signal": r.timing_signal,
            "should_act": r.overall_should_act,
            "action_reason": r.overall_action_reason,
            "top_block_ids": [s.block_id for s in r.signals[:5]],
            "blind_spot_block_ids": [b for b, _ in r.blind_spots[:3]],
            "new_hot_block_ids": [b for b, _ in r.new_hot_blocks[:3]],
            "consensus_block_ids": [b for b, _ in r.consensus_blocks[:5]],
            "holding_block_ids": list(r.portfolio_blocks)[:10],
            "watchlist_block_ids": list(r.watchlist_blocks)[:10],
            "actionable_count": len(self.get_actionable_signals()),
        }

    def should_act(self) -> Tuple[bool, str]:
        """判断是否应该行动"""
        if self._last_result is None:
            return False, "no_data"
        r = self._last_result
        return r.overall_should_act, r.overall_action_reason


_fusion_instance: Optional[AttentionFusion] = None


def get_attention_fusion() -> AttentionFusion:
    """获取AttentionFusion单例"""
    global _fusion_instance
    if _fusion_instance is None:
        _fusion_instance = AttentionFusion()
    return _fusion_instance
