"""
ConvictionValidator - 价值验证层

═══════════════════════════════════════════════════════════════════════════
                              架 构 定 位
═══════════════════════════════════════════════════════════════════════════

【桥接层】ConvictionValidator 是"我们"与"外部世界"的差异检测器

    它回答三个核心问题：
    1. 我们坚信的，外部认可吗？ → consensus_blocks（坚定持有）
    2. 我们坚信的，外部不认可？ → divergence_blocks（需验证）
    3. 外部热的，我们没关注？ → blind_spots（→ BlindSpotInvestigator探究）

═══════════════════════════════════════════════════════════════════════════
                              核 心 逻 辑
═══════════════════════════════════════════════════════════════════════════

外部层（市场/新闻）:
    market_attention{}  ← BlockAttentionEngine（定价热度）
    world_narrative{}   ← NarrativeTracker（新闻热度）

我们的层:
    portfolio_summary   ← Portfolio（持仓 + watchlist）

差异检测:
    consensus_blocks   = 外部热 ∩ 我们持有/关注（方向一致 → 坚定）
    divergence_blocks  = 我们持有/关注 ∩ 外部冷（方向分歧 → 验证）
    blind_spots       = 外部热 ∩ 我们没关注（→ BlindSpotInvestigator探究）
    new_hot_blocks    = 新热点 ∩ 我们没关注（→ 跟踪）

═══════════════════════════════════════════════════════════════════════════
                              数 据 流
═══════════════════════════════════════════════════════════════════════════

    Portfolio + MarketAttention + WorldNarrative
                    ↓
         ConvictionValidator.validate()
                    ↓
    consensus/divergence/blind_spots/new_hot_blocks
                    ↓
         AttentionFusion.fuse()
                    ↓
         融合分数 + BlindSpotInvestigator
                    ↓
         最终注意力分配

═══════════════════════════════════════════════════════════════════════════
                              使 用 方 式
═══════════════════════════════════════════════════════════════════════════

    validator = ConvictionValidator()
    result = validator.validate(
        portfolio=portfolio_summary,
        market_attention={"AI": 0.8, "芯片": 0.6},
        world_narrative={"AI": 0.7, "新能源": 0.5},
    )
    print(f"信念度: {result.conviction_score}")
    print(f"共识: {result.consensus_blocks}")
    print(f"盲区: {result.blind_spots}")
"""

from __future__ import annotations
import logging
import time
from typing import Dict, List, Optional, Set, Tuple, Any, TYPE_CHECKING
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from deva.naja.attention.portfolio import Portfolio, PortfolioSummary
    from deva.naja.attention.discovery import NarrativeBlockLinker
    from deva.naja.attention.block_registry import BlockRegistry


@dataclass
class ValidationResult:
    """
    验证结果

    【桥接层】的核心输出，描述"我们"与"外部世界"的差异

    ════════════════════════════════════════════════════════════════════════════
                                字 段 归 属
    ════════════════════════════════════════════════════════════════════════════

    【差异检测结果】
        consensus_blocks   = 外部热 ∩ 我们持有/关注（坚定持有）
        divergence_blocks  = 我们持有/关注 ∩ 外部冷（需验证）
        blind_spots      = 外部热 ∩ 我们没关注（→探究）
        new_hot_blocks   = 新热点 ∩ 我们没关注（→跟踪）
        conviction_score  = 整体信念强度

    【内部状态】
        watched_blocks    = 我们关注的block（持仓+watchlist）
        market_hot_blocks = 市场热的block（top block）
        holding_blocks    = 持仓所在block
        watchlist_blocks  = watchlist所在block

    【参考数据】
        market_narrative_heat    = 市场叙事热度
        watched_narrative_heat  = 我们关注叙事的热度
        market_coverage          = 我们对市场热点的覆盖度
        conviction_signal        = 信念信号描述
    """
    conviction_score: float                              # 【差异检测】信念分数
    consensus_blocks: List[Tuple[str, float]]            # 【差异检测】共识block
    divergence_blocks: List[Tuple[str, float]]           # 【差异检测】分歧block
    blind_spots: List[Tuple[str, float]]                 # 【差异检测】盲区block
    new_hot_blocks: List[Tuple[str, float]]              # 【差异检测】新热点block

    watched_blocks: Set[str]                            # 【我们】关注的block
    market_hot_blocks: Set[str]                          # 【外部】市场热的block

    holding_blocks: Set[str]                            # 【我们】持仓block
    watchlist_blocks: Set[str]                          # 【我们】watchlist block

    market_narrative_heat: Dict[str, float]             # 【外部】市场叙事热度
    watched_narrative_heat: Dict[str, float]           # 【我们】关注叙事的热度

    market_coverage: float                               # 【参考】市场覆盖度
    conviction_signal: str                               # 【参考】信念信号
    timestamp: float = field(default_factory=time.time)

    def summary(self) -> Dict[str, Any]:
        return {
            "conviction_score": self.conviction_score,
            "consensus_count": len(self.consensus_blocks),
            "divergence_count": len(self.divergence_blocks),
            "blind_spot_count": len(self.blind_spots),
            "new_hot_count": len(self.new_hot_blocks),
            "conviction_signal": self.conviction_signal,
            "market_coverage": self.market_coverage,
        }


class ConvictionValidator:
    """
    【桥接层】价值验证器

    比较"我们"与"外部世界"的注意力差异

    输入：
        portfolio_summary   = Portfolio（持仓 + watchlist）
        market_attention   = BlockAttentionEngine（定价热度）
        world_narrative   = NarrativeTracker（新闻热度）

    验证类型：
        consensus   = 外部热 ∩ 我们持有/关注（坚定持有）
        divergence  = 我们持有/关注 ∩ 外部冷（方向分歧）
        blind_spots = 外部热 ∩ 我们没关注（→探究）
        new_hot    = 新热点 ∩ 我们没关注（→跟踪）

    使用方式:

        validator = ConvictionValidator()

        result = validator.validate(
            portfolio=pf.get_summary(),
            market_attention=block_engine.get_all_weights(filter_noise=True),
            world_narrative={"AI": 0.8, "芯片": 0.6, "新能源": 0.4},
        )

        log.info(f"信念度: {result.conviction_score}")
        log.info(f"共识题材: {[b for b,_ in result.consensus_blocks]}")
        log.info(f"盲区: {[b for b,_ in result.blind_spots]}")
    """

    def __init__(
        self,
        portfolio: Optional["Portfolio"] = None,
        linker: Optional["NarrativeBlockLinker"] = None,
        registry: Optional["BlockRegistry"] = None,
    ):
        from deva.naja.attention.portfolio import get_portfolio
        from deva.naja.attention.discovery import get_narrative_block_linker
        from deva.naja.attention.block_registry import get_block_registry

        self.portfolio = portfolio or get_portfolio()
        self.linker = linker or get_narrative_block_linker()
        self.registry = registry or get_block_registry()

        self._hot_threshold: float = 0.3
        self._cold_threshold: float = 0.1
        self._last_result: Optional[ValidationResult] = None

    def validate(
        self,
        portfolio: Optional["PortfolioSummary"] = None,
        market_attention: Optional[Dict[str, float]] = None,
        world_narrative: Optional[Dict[str, float]] = None,
    ) -> ValidationResult:
        """
        执行价值验证

        Args:
            portfolio: 持仓汇总（可选，不传则自动获取）
            market_attention: 市场热度 {block_id: weight}（可选，不传则用BlockRegistry）
            world_narrative: 外部叙事热度 {narrative: weight}（可选）
        """
        if portfolio is None:
            portfolio = self.portfolio.get_summary()

        holding_blocks = portfolio.holding_codes
        watchlist_blocks = portfolio.watchlist_codes

        watched_blocks = set(portfolio.block_alloc.keys())

        if market_attention is None:
            market_attention = {}

        market_hot_blocks = {
            bid for bid, w in market_attention.items()
            if w >= self._hot_threshold
        }

        watched_hot = watched_blocks & market_hot_blocks
        watched_cold = watched_blocks - market_hot_blocks

        watched_narratives: Set[str] = set()
        for block_id in watched_blocks:
            watched_narratives.update(self.registry.get_narratives_for_block(block_id))

        world_narratives = world_narrative or {}
        world_hot_narratives = {n for n, w in world_narratives.items() if w >= 0.5}

        market_narratives: Set[str] = set()
        for bid in market_hot_blocks:
            market_narratives.update(self.registry.get_narratives_for_block(bid))

        narrative_overlap = watched_narratives & market_narratives
        narrative_coverage = len(narrative_overlap) / max(len(watched_narratives | market_narratives), 1)

        block_overlap = watched_hot
        block_coverage = len(block_overlap) / max(len(watched_blocks | market_hot_blocks), 1)

        conviction_score = (
            0.4 * block_coverage +
            0.3 * narrative_coverage +
            0.3 * (len(watched_hot) / max(len(watched_blocks), 1))
        )
        conviction_score = min(1.0, max(0.0, conviction_score))

        market_avg = sum(market_attention.values()) / max(len(market_attention), 1)
        market_coverage = market_avg / self._hot_threshold if self._hot_threshold > 0 else 0

        consensus_blocks = [
            (bid, market_attention.get(bid, 0))
            for bid in watched_hot
        ]
        consensus_blocks = sorted(consensus_blocks, key=lambda x: x[1], reverse=True)

        divergence_blocks = [
            (bid, market_attention.get(bid, 0))
            for bid in watched_cold
        ]
        divergence_blocks = sorted(divergence_blocks, key=lambda x: x[1], reverse=True)

        blind_spots = [
            (bid, market_attention.get(bid, 0))
            for bid in (market_hot_blocks - watched_blocks)
        ]
        blind_spots = sorted(blind_spots, key=lambda x: x[1], reverse=True)[:10]

        new_hot_blocks = [
            (bid, market_attention.get(bid, 0))
            for bid in (market_hot_blocks - watched_blocks - set(holding_blocks))
        ]
        new_hot_blocks = sorted(new_hot_blocks, key=lambda x: x[1], reverse=True)[:5]

        if conviction_score >= 0.7:
            if len(consensus_blocks) >= 3:
                signal = "strong_conviction"
            else:
                signal = "moderate_conviction"
        elif conviction_score >= 0.4:
            if len(new_hot_blocks) > 0:
                signal = "expanding_conviction"
            elif len(divergence_blocks) > 2:
                signal = "weak_conviction"
            else:
                signal = "neutral_conviction"
        else:
            if len(blind_spots) > 5:
                signal = "blind_spot_warning"
            elif len(divergence_blocks) > 0:
                signal = "conviction_weak"
            else:
                signal = "low_conviction"

        result = ValidationResult(
            conviction_score=conviction_score,
            consensus_blocks=consensus_blocks,
            divergence_blocks=divergence_blocks,
            blind_spots=blind_spots,
            new_hot_blocks=new_hot_blocks,
            watched_blocks=watched_blocks,
            market_hot_blocks=market_hot_blocks,
            holding_blocks=set(holding_blocks),
            watchlist_blocks=set(watchlist_blocks),
            market_narrative_heat=world_narratives,
            watched_narrative_heat={n: world_narratives.get(n, 0) for n in watched_narratives},
            market_coverage=market_coverage,
            conviction_signal=signal,
        )

        self._last_result = result
        return result

    def get_timing_signal(self) -> Tuple[str, float]:
        """
        获取时机信号

        Returns:
            (signal, confidence)
            - "timing_good": 时机好（热度低但信念强）
            - "timing_hot": 时机热（热度高）
            - "timing_wait": 等待（分歧大）
        """
        if self._last_result is None:
            return "no_data", 0.0

        r = self._last_result

        if r.conviction_score >= 0.5 and len(r.divergence_blocks) > 0:
            avg_div_heat = sum(w for _, w in r.divergence_blocks) / max(len(r.divergence_blocks), 1)
            if avg_div_heat < self._cold_threshold:
                return "timing_good", r.conviction_score

        if len(r.consensus_blocks) > 0:
            avg_cons_heat = sum(w for _, w in r.consensus_blocks) / max(len(r.consensus_blocks), 1)
            if avg_cons_heat > 0.5:
                return "timing_hot", r.conviction_score

        return "timing_wait", r.conviction_score * 0.5

    def should_add_position(self) -> Tuple[bool, str]:
        """
        判断是否应该加仓

        Returns:
            (should_add, reason)
        """
        if self._last_result is None:
            return False, "no_data"

        r = self._last_result
        signal, confidence = self.get_timing_signal()

        if signal == "timing_good" and r.conviction_score >= 0.6:
            return True, f"good_timing: conviction={r.conviction_score:.2f}"
        elif signal == "timing_hot" and r.conviction_score >= 0.7:
            return True, f"hot_but_confirmed: conviction={r.conviction_score:.2f}"
        else:
            return False, f"{signal}: confidence={confidence:.2f}"


_conviction_validator_instance: Optional[ConvictionValidator] = None


def get_conviction_validator() -> ConvictionValidator:
    """获取ConvictionValidator单例"""
    global _conviction_validator_instance
    if _conviction_validator_instance is None:
        _conviction_validator_instance = ConvictionValidator()
    return _conviction_validator_instance
