"""
AttentionFusion - 注意力融合层

═══════════════════════════════════════════════════════════════════════════
                              架 构 定 位
═══════════════════════════════════════════════════════════════════════════

【融合层】 AttentionFusion 是架构的核心融合中心

    - 来自 Layer 0（外部世界）的数据在这里汇合
    - 来自 Layer 1（我们的持仓/关注）的数据在这里对比
    - ConvictionValidator 找出的差异在这里被加权
    - BlindSpotInvestigator 的发现在这里被放大
    - 最终输出每个 block 的融合分数，供决策使用

═══════════════════════════════════════════════════════════════════════════
                              融 合 公 式
═══════════════════════════════════════════════════════════════════════════

    final_score[bid] =

        α × conviction_weight[bid]     【桥接-共识/分歧】
                                          外部热 ∩ 我们持有 → 高权重
                                          外部热 ∩ 我们持有但分歧 → 低权重

        + β × market_attention[bid]     【外部-市场】
                                          BlockAttentionEngine 的定价热度
                                          纯粹外部，无我们的立场

        + γ × timing_bonus[bid]         【时机】
                                          热度低 → 布局窗口加成
                                          热度高 → 已反映惩罚

        + δ × discovery_boost[bid]       【被动发现-盲区】
                                          BlindSpotInvestigator 发现的新热点
                                          外部热但我们没关注 → 放大

        + ε × value_score               【主动发现-天道】
                                          NarrativeTracker 检测到的价值信号
                                          我们自己认定的核心变化
                                          "替天行道"的天道

═══════════════════════════════════════════════════════════════════════════
                              数据来源标注
═══════════════════════════════════════════════════════════════════════════

外部层（市场/新闻）:
    market_attention{}     ← BlockAttentionEngine（定价热度）
    world_narrative{}      ← NarrativeTracker（新闻热度）

我们的层:
    portfolio_summary      ← Portfolio（持仓 + watchlist）
    conviction_score       ← ConvictionValidator（信念验证）

被动发现层:
    blind_spot_investigations ← BlindSpotInvestigator（盲区探究）

主动发现层:
    value_score            ← NarrativeTracker.get_value_market_summary()
    value_signals          ← NarrativeTracker（天道信号）

═══════════════════════════════════════════════════════════════════════════
                              核心输出
═══════════════════════════════════════════════════════════════════════════

    consensus_blocks      = 外部热 ∩ 我们持有（方向一致，坚定持有）
    divergence_blocks     = 外部热 ∩ 我们持有（方向分歧，需验证）
    blind_spots          = 外部热 ∩ 我们没关注（被动发现，需探究）
    new_hot_blocks       = 新出现的热点（跟踪）

    每个 block 的 fused_score = 加权融合后的最终注意力分数
"""

from __future__ import annotations
import logging
import time
from typing import Dict, List, Optional, Set, Tuple, Any, TYPE_CHECKING
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from deva.naja.attention.portfolio import Portfolio, PortfolioSummary
    from deva.naja.attention.discovery import ConvictionValidator, ValidationResult, NarrativeBlockLinker
    from deva.naja.attention.block_registry import BlockRegistry


@dataclass
class FusionSignal:
    """
    融合信号（供ManasEngine使用）

    每个 block 的融合结果，包含各通道贡献明细
    """
    block_id: str                          # block标识
    fused_score: float                    # 最终融合分数
    market_attention: float                # 【外部-市场】BlockAttentionEngine热度
    conviction_score: float                # 【桥接】ConvictionValidator信念分数
    timing_signal: str                     # 【时机】timing信号
    holding_status: str                    # 【我们】持仓状态
    action_recommendation: str             # 推荐行动

    conviction_level: str                  # 信念等级
    timing_level: str                      # 时机等级

    should_act: bool                       # 是否应行动
    action_reason: str                     # 行动理由

    value_score: float = 0.0              # 【主动发现-天道】价值分数
    value_signals: Dict[str, List[str]] = field(default_factory=dict)  # 【主动发现-天道】价值信号详情


@dataclass
class FullFusionResult:
    """
    完整融合结果

    融合公式：
        fused = α×conviction + β×market + γ×timing + δ×discovery + ε×value

    ════════════════════════════════════════════════════════════════════════════
                                字 段 归 属
    ════════════════════════════════════════════════════════════════════════════

    【桥接-差异检测】
        consensus_blocks    = 外部热 ∩ 我们持有（方向一致，坚定持有）
        divergence_blocks   = 外部热 ∩ 我们持有（方向分歧，需验证）
        blind_spots        = 外部热 ∩ 我们没关注（被动发现，需探究）
        new_hot_blocks     = 新出现的热点（跟踪）
        conviction_score   = 整体信念强度

    【外部-市场】
        market_attention    = BlockAttentionEngine 定价热度

    【我们-持仓】
        portfolio_blocks    = 我们持仓所在的block
        watchlist_blocks   = 我们watchlist所在的block
        holding_codes       = 持仓股票代码
        watchlist_codes     = watchlist股票代码

    【被动发现-盲区】
        blind_spot_investigations = BlindSpotInvestigator探究结果

    【主动发现-天道】
        value_score                    = 天道价值分数
        market_narrative_score         = 民心市场叙事分数（参考）
        value_signals                  = 天道信号详情
        market_narrative_signals       = 民心信号详情（参考）
    """
    signals: List[FusionSignal]                    # 所有block的融合信号
    consensus_blocks: List[Tuple[str, float]]       # 【桥接】共识block
    divergence_blocks: List[Tuple[str, float]]      # 【桥接】分歧block
    blind_spots: List[Tuple[str, float]]           # 【被动发现】盲区block
    new_hot_blocks: List[Tuple[str, float]]        # 【外部】新热点block

    conviction_score: float                         # 【桥接】整体信念分数
    timing_signal: str                              # 【时机】时机信号
    overall_should_act: bool                        # 是否整体应行动
    overall_action_reason: str                      # 整体行动理由

    portfolio_blocks: Set[str]                     # 【我们】持仓block
    watchlist_blocks: Set[str]                      # 【我们】watchlist block
    holding_codes: Set[str]                         # 【我们】持仓股票
    watchlist_codes: Set[str]                      # 【我们】watchlist股票

    value_score: float = 0.0                       # 【主动发现-天道】天道价值分数
    market_narrative_score: float = 0.0            # 【主动发现-民心】市场叙事分数（参考）
    value_signals: Dict[str, List[str]] = field(default_factory=dict)      # 【主动发现-天道】天道信号详情
    market_narrative_signals: Dict[str, List[str]] = field(default_factory=dict)  # 【主动发现-民心】市场叙事详情（参考）

    blind_spot_investigations: List[Dict[str, Any]] = field(default_factory=list)  # 【被动发现】盲区探究结果

    timestamp: float = field(default_factory=time.time)


class AttentionFusion:
    """
    【融合层】四层注意力融合器

    四个输入通道：

        α × conviction   【桥接层】外部热点 ∩ 我们的持仓/关注 → 信念权重
        β × market      【外部-市场】BlockAttentionEngine 定价热度
        γ × timing      【时机】热度低→布局窗口，热度高→已反映
        δ × discovery   【被动发现】BlindSpotInvestigator 盲区探究放大
        ε × value       【主动发现】NarrativeTracker 天道价值信号

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
                log.info(f"Buy {s.block_id}: {s.action_reason}")

        log.info(f"信念度: {result.conviction_score}")
        log.info(f"时机信号: {result.timing_signal}")
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
        from deva.naja.attention.discovery import get_conviction_validator, get_narrative_block_linker
        from deva.naja.attention.block_registry import get_block_registry

        self.portfolio = portfolio or get_portfolio()
        self.validator = validator or get_conviction_validator()
        self.linker = linker or get_narrative_block_linker()
        self.registry = registry or get_block_registry()
        self._narrative_tracker = narrative_tracker
        self._focus_manager = focus_manager

        self._alpha: float = 0.30
        self._beta: float = 0.30
        self._gamma: float = 0.15
        self._delta: float = 0.15
        self._epsilon: float = 0.10

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
            from deva.naja.cognition.narrative import get_narrative_tracker
            tracker = get_narrative_tracker()
            return tracker.get_world_narrative()
        except Exception:
            return {}

    def _get_value_market_summary(self) -> Dict[str, Any]:
        """
        从NarrativeTracker获取价值和市场叙事评分（天道/民心）

        【天道-替天行道】主动价值发现
        【民心-市场叙事】被动热点参考

        Returns:
            包含 value_score, market_narrative_score, value_signals, market_narrative_signals 的字典
        """
        if self._narrative_tracker is not None:
            return self._narrative_tracker.get_value_market_summary()
        try:
            from deva.naja.cognition.narrative import get_narrative_tracker
            tracker = get_narrative_tracker()
            return tracker.get_value_market_summary()
        except Exception:
            return {"value_score": 0.0, "market_narrative_score": 0.0, "signals": {"value": {}, "market_narrative": {}}}

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

        value_market_summary = self._get_value_market_summary()
        value_score = value_market_summary.get("value_score", 0.0)
        market_narrative_score = value_market_summary.get("market_narrative_score", 0.0)
        value_signals = value_market_summary.get("signals", {}).get("value", {})
        market_narrative_signals = value_market_summary.get("signals", {}).get("market_narrative", {})

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

        discovery_boost = self._compute_discovery_boost(
            validation.blind_spots, validation.new_hot_blocks
        )

        signals: List[FusionSignal] = []

        for block_id in all_blocks:
            m_attn = market_attention.get(block_id, 0.0)
            conv_w = conviction_by_block.get(block_id, 0.0)
            disc_boost = discovery_boost.get(block_id, 0.0)

            timing_bonus = 0.0
            if timing_signal == "timing_good":
                timing_bonus = 0.2 if conv_w >= 0.5 else 0.1
            elif timing_signal == "timing_hot":
                timing_bonus = -0.1

            fused_score = (
                self._alpha * conv_w +
                self._beta * m_attn +
                self._gamma * timing_bonus +
                self._delta * disc_boost +
                self._epsilon * value_score
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
                value_score=value_score,
                value_signals=value_signals,
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
            value_score=value_score,
            market_narrative_score=market_narrative_score,
            value_signals=value_signals,
            market_narrative_signals=market_narrative_signals,
        )

        self._last_result = result
        return result

    def _compute_discovery_boost(
        self,
        blind_spots: List[Tuple[str, float]],
        new_hot_blocks: List[Tuple[str, float]],
    ) -> Dict[str, float]:
        """
        计算发现放大权重

        blind_spots: 外部热但我们没关注的 block
        new_hot_blocks: 新热门的 block
        """
        boost: Dict[str, float] = {}

        for block_id, attention_score in blind_spots:
            boost[block_id] = attention_score * 0.5

        for block_id, attention_score in new_hot_blocks:
            if block_id not in boost:
                boost[block_id] = attention_score * 0.3

        return boost

    def investigate_blind_spots(
        self,
        blind_spots: Optional[List[Tuple[str, float]]] = None,
    ) -> "BatchInvestigationResult":
        """
        主动探究盲区热点

        Args:
            blind_spots: 可选，不传则从上次 validation 结果获取

        Returns:
            BatchInvestigationResult: 探究结果
        """
        if blind_spots is None:
            if self._last_result:
                blind_spots = self._last_result.blind_spots
            else:
                from deva.naja.attention.discovery import get_blind_spot_investigator
                investigator = get_blind_spot_investigator()
                return investigator.investigate_all([])

        try:
            from deva.naja.attention.discovery import get_blind_spot_investigator
            investigator = get_blind_spot_investigator()
            return investigator.investigate_all(blind_spots)
        except Exception:
            return None

    def fuse_with_investigation(
        self,
        market_attention: Dict[str, float],
        portfolio_summary: Optional["PortfolioSummary"] = None,
        blind_spots: Optional[List[Tuple[str, float]]] = None,
    ) -> FullFusionResult:
        """
        带主动探究的融合

        自动探究 blind_spots，然后执行融合

        Args:
            market_attention: 市场热度
            portfolio_summary: 持仓汇总
            blind_spots: 盲区列表

        Returns:
            FullFusionResult: 融合结果
        """
        investigation_result = self.investigate_blind_spots(blind_spots)

        if portfolio_summary is None:
            portfolio_summary = self.portfolio.get_summary()

        return self.fuse(
            market_attention=market_attention,
            portfolio_summary=portfolio_summary,
        )

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
