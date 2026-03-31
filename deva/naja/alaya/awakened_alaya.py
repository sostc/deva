"""
AwakenedAlaya - 觉醒阿赖耶识

增强光明藏和顿悟引擎，实现：
1. 完整顿悟机制
2. 跨市场迁移增强
3. 全量模式召回
"""

import time
import logging
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

log = logging.getLogger(__name__)


class AwakeningLevel(Enum):
    """觉醒层次"""
    DORMANT = "dormant"          # 沉睡
    AWAKENING = "awakening"     # 觉醒中
    ILLUMINATED = "illuminated" # 已照亮
    ENLIGHTENED = "enlightened" # 顿悟


@dataclass
class PatternArchive:
    """模式归档"""
    pattern_id: str
    pattern_type: str
    market_context: Dict[str, Any]
    outcome: Dict[str, Any]
    success: bool
    archived_at: float


@dataclass
class AwakeningSignal:
    """觉醒信号"""
    signal_type: str            # "pattern_match", "contradiction", "timing"
    trigger_conditions: List[str]
    confidence: float
    illumination_content: str
    timestamp: float = field(default_factory=time.time)


class CrossMarketMemory:
    """
    跨市场记忆

    存储和迁移跨市场的经验
    """

    def __init__(self):
        self._source_memories: Dict[str, List[Dict[str, Any]]] = {
            "futures": [],
            "us_stock": [],
            "hk_stock": [],
            "crypto": []
        }
        self._transfer_success_rate: Dict[str, float] = {}

    def store_success_pattern(
        self,
        source_market: str,
        pattern: Dict[str, Any]
    ):
        """存储成功模式"""
        if source_market not in self._source_memories:
            self._source_memories[source_market] = []

        memory_entry = {
            **pattern,
            "stored_at": time.time(),
            "usage_count": 0
        }

        self._source_memories[source_market].append(memory_entry)

        if len(self._source_memories[source_market]) > 500:
            self._source_memories[source_market] = self._source_memories[source_market][-500:]

    def recall_applicable_patterns(
        self,
        target_market: str,
        current_conditions: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """召回适用模式"""
        patterns = []

        market_transfer_map = {
            "a_stock": ["futures", "hk_stock"],
            "hk_stock": ["us_stock", "a_stock"],
        }

        source_markets = market_transfer_map.get(target_market, list(self._source_memories.keys()))

        for source_market in source_markets:
            if source_market not in self._source_memories:
                continue

            for memory in self._source_memories[source_market]:
                if self._check_applicability(memory, current_conditions):
                    memory["usage_count"] += 1
                    memory["source_market"] = source_market
                    patterns.append(memory)

        patterns.sort(key=lambda x: x.get("usage_count", 0), reverse=True)
        return patterns[:5]

    def _check_applicability(
        self,
        memory: Dict[str, Any],
        conditions: Dict[str, Any]
    ) -> bool:
        """检查是否适用"""
        memory_conditions = memory.get("conditions", {})

        for key, value in conditions.items():
            if key in memory_conditions:
                mem_val = memory_conditions[key]
                if isinstance(value, (int, float)) and isinstance(mem_val, (int, float)):
                    if abs(value - mem_val) > mem_val * 0.5:
                        return False

        return True

    def record_transfer_outcome(
        self,
        pattern_id: str,
        success: bool
    ):
        """记录迁移结果"""
        if pattern_id not in self._transfer_success_rate:
            self._transfer_success_rate[pattern_id] = 0.5

        current = self._transfer_success_rate[pattern_id]
        if success:
            self._transfer_success_rate[pattern_id] = min(0.95, current + 0.1)
        else:
            self._transfer_success_rate[pattern_id] = max(0.1, current - 0.1)


class PatternArchiveManager:
    """
    模式归档管理器

    管理所有历史模式的全量召回
    """

    def __init__(self):
        self._archives: Dict[str, List[PatternArchive]] = {
            "momentum": [],
            "reversal": [],
            "breakout": [],
            "accumulation": [],
            "distribution": [],
            "sector_rotation": []
        }
        self._index: Dict[str, Set[str]] = {
            "by_symbol": {},
            "by_sector": {},
            "by_time": {}
        }

    def archive(
        self,
        pattern_id: str,
        pattern_type: str,
        market_context: Dict[str, Any],
        outcome: Dict[str, Any]
    ):
        """归档模式"""
        if pattern_type not in self._archives:
            self._archives[pattern_type] = []

        success = outcome.get("return", 0) > 0

        archive_entry = PatternArchive(
            pattern_id=pattern_id,
            pattern_type=pattern_type,
            market_context=market_context,
            outcome=outcome,
            success=success,
            archived_at=time.time()
        )

        self._archives[pattern_type].append(archive_entry)

        self._update_index(archive_entry)

        for pattern_list in self._archives.values():
            if len(pattern_list) > 1000:
                pattern_list[:] = pattern_list[-500:]

    def _update_index(self, archive: PatternArchive):
        """更新索引"""
        symbol = archive.market_context.get("symbol")
        if symbol:
            if symbol not in self._index["by_symbol"]:
                self._index["by_symbol"][symbol] = set()
            self._index["by_symbol"][symbol].add(archive.pattern_id)

        sector = archive.market_context.get("sector")
        if sector:
            if sector not in self._index["by_sector"]:
                self._index["by_sector"][sector] = set()
            self._index["by_sector"][sector].add(archive.pattern_id)

    def recall(
        self,
        pattern_type: Optional[str] = None,
        symbol: Optional[str] = None,
        sector: Optional[str] = None,
        limit: int = 10
    ) -> List[PatternArchive]:
        """召回匹配的模式"""
        candidates = []

        if pattern_type and pattern_type in self._archives:
            candidates.extend(self._archives[pattern_type])

        if symbol and symbol in self._index["by_symbol"]:
            pattern_ids = self._index["by_symbol"][symbol]
            for pattern_list in self._archives.values():
                candidates.extend([p for p in pattern_list if p.pattern_id in pattern_ids])

        if sector and sector in self._index["by_sector"]:
            pattern_ids = self._index["by_sector"][sector]
            for pattern_list in self._archives.values():
                candidates.extend([p for p in pattern_list if p.pattern_id in pattern_ids])

        unique_candidates = {id(c): c for c in candidates}.values()

        successful = [c for c in unique_candidates if c.success]
        successful.sort(key=lambda x: x.archived_at, reverse=True)

        return successful[:limit]

    def get_archive_stats(self) -> Dict[str, Any]:
        """获取归档统计"""
        return {
            pattern_type: len(archives)
            for pattern_type, archives in self._archives.items()
        }


class AwakeningEngine:
    """
    觉醒引擎

    当多个弱信号汇聚时，触发顿悟
    """

    def __init__(self):
        self._weak_signals: deque = deque(maxlen=30)
        self._awakenings: deque = deque(maxlen=50)
        self._awakening_level = AwakeningLevel.DORMANT

    def receive_signal(self, signal_type: str, content: str, confidence: float, conditions: Dict[str, Any]):
        """接收弱信号"""
        self._weak_signals.append({
            "type": signal_type,
            "content": content,
            "confidence": confidence,
            "conditions": conditions,
            "timestamp": time.time()
        })

        self._update_awakening_level()

    def _update_awakening_level(self):
        """更新觉醒层次"""
        if len(self._weak_signals) < 5:
            self._awakening_level = AwakeningLevel.DORMANT
        elif len(self._weak_signals) < 15:
            self._awakening_level = AwakeningLevel.AWAKENING
        else:
            self._awakening_level = AwakeningLevel.ILLUMINATED

    def check_for_awakening(self) -> Optional[AwakeningSignal]:
        """检查是否顿悟"""
        if len(self._weak_signals) < 10:
            return None

        recent = list(self._weak_signals)[-10:]

        types = [s["type"] for s in recent]
        type_counts: Dict[str, int] = {}
        for t in types:
            type_counts[t] = type_counts.get(t, 0) + 1

        if len(type_counts) >= 3:
            return AwakeningSignal(
                signal_type="pattern_match",
                trigger_conditions=[f"{k}:{v}" for k, v in type_counts.items()],
                confidence=0.8,
                illumination_content="多类型信号汇聚，可能存在重大模式机会"
            )

        conflicting = 0
        for i, s1 in enumerate(recent):
            for s2 in recent[i+1:]:
                if self._are_conflicting(s1, s2):
                    conflicting += 1

        if conflicting >= 3:
            return AwakeningSignal(
                signal_type="contradiction",
                trigger_conditions=[f"冲突信号数:{conflicting}"],
                confidence=0.85,
                illumination_content="多空信号冲突严重，市场可能即将转折"
            )

        timing_signals = [s for s in recent if s["type"] == "timing"]
        if len(timing_signals) >= 3:
            return AwakeningSignal(
                signal_type="timing",
                trigger_conditions=["timing信号多次出现"],
                confidence=0.75,
                illumination_content="多个时机信号共振，入场时机成熟"
            )

        return None

    def _are_conflicting(self, s1: Dict[str, Any], s2: Dict[str, Any]) -> bool:
        """判断两个信号是否冲突"""
        c1 = s1.get("conditions", {}).get("direction", 0)
        c2 = s2.get("conditions", {}).get("direction", 0)

        if c1 != 0 and c2 != 0 and c1 != c2:
            return True

        return False

    def record_outcome(self, awakening: AwakeningSignal, success: bool):
        """记录顿悟结果"""
        awakening.usefulness = 0.8 if success else 0.3
        self._awakenings.append(awakening)

        if success:
            self._awakening_level = AwakeningLevel.ENLIGHTENED

    def get_awakening_level(self) -> str:
        """获取觉醒层次"""
        return self._awakening_level.value


class AwakenedAlaya:
    """
    觉醒阿赖耶识

    整合光明藏、顿悟引擎、跨市场记忆
    支持 UnifiedManas 持仓盈亏触发顿悟
    """

    def __init__(self):
        self.cross_market_memory = CrossMarketMemory()
        self.pattern_archive = PatternArchiveManager()
        self.awakening_engine = AwakeningEngine()
        self._epiphany_engine = None

        self._integration_count = 0
        self._last_illumination_time = 0.0

    def set_epiphany_engine(self, epiphany_engine):
        """设置顿悟引擎（用于持仓顿悟）"""
        self._epiphany_engine = epiphany_engine

    def illuminate(
        self,
        market_data: Dict[str, Any],
        signals: Optional[List[Dict[str, Any]]] = None,
        unified_manas_output: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        照亮模式

        Args:
            market_data: 市场数据
            signals: 信号列表
            unified_manas_output: UnifiedManas 输出（包含持仓信息）

        Returns:
            包含 illumination, awakenings, archived_patterns 的字典
        """
        self._integration_count += 1

        awakening_result = self._process_awakening(signals or [])

        portfolio_awakening = self._process_portfolio_awakening(unified_manas_output)

        recalled_patterns = self._recall_relevant_patterns(market_data)

        illumination = self._generate_illumination(
            market_data, recalled_patterns, awakening_result, portfolio_awakening
        )

        if illumination:
            self._last_illumination_time = time.time()

        return {
            "illumination": illumination,
            "awakening": awakening_result,
            "portfolio_awakening": portfolio_awakening,
            "recalled_patterns": recalled_patterns,
            "awakening_level": self.awakening_engine.get_awakening_level()
        }

    def _process_portfolio_awakening(
        self,
        unified_manas_output: Optional[Dict[str, Any]]
    ) -> Optional[AwakeningSignal]:
        """处理持仓驱动的顿悟"""
        if not unified_manas_output:
            return None

        if self._epiphany_engine is None:
            try:
                from deva.naja.alaya.epiphany_engine import EpiphanyEngine
                self._epiphany_engine = EpiphanyEngine()
            except ImportError:
                return None

        portfolio_loss = unified_manas_output.get("portfolio_loss_pct", 0.0)
        market_deterioration = unified_manas_output.get("market_deterioration", False)
        regime = "unknown"

        regime_score = unified_manas_output.get("regime_score", 0.0)
        if regime_score < -0.3:
            regime = "bear"
        elif regime_score > 0.3:
            regime = "bull"
        else:
            regime = "neutral"

        epiphany = self._epiphany_engine.check_portfolio_epiphany(
            portfolio_loss=portfolio_loss,
            market_deterioration=market_deterioration,
            regime=regime
        )

        if epiphany:
            return AwakeningSignal(
                signal_type=epiphany.epiphany_type,
                trigger_conditions=epiphany.triggered_by,
                confidence=epiphany.confidence,
                illumination_content=epiphany.content
            )

        return None

    def _process_awakening(self, signals: List[Dict[str, Any]]) -> Optional[AwakeningSignal]:
        """处理顿悟"""
        for signal in signals:
            self.awakening_engine.receive_signal(
                signal_type=signal.get("type", "unknown"),
                content=signal.get("content", ""),
                confidence=signal.get("confidence", 0.5),
                conditions=signal.get("conditions", {})
            )

        return self.awakening_engine.check_for_awakening()

    def _recall_relevant_patterns(self, market_data: Dict[str, Any]) -> List[PatternArchive]:
        """召回相关模式"""
        symbol = market_data.get("symbol")
        sector = market_data.get("sector")
        pattern_type = market_data.get("pattern_type")

        patterns = self.pattern_archive.recall(
            pattern_type=pattern_type,
            symbol=symbol,
            sector=sector
        )

        cross_patterns = self.cross_market_memory.recall_applicable_patterns(
            target_market="a_stock",
            current_conditions=market_data
        )

        return patterns[:5]

    def _generate_illumination(
        self,
        market_data: Dict[str, Any],
        recalled_patterns: List[PatternArchive],
        awakening: Optional[AwakeningSignal],
        portfolio_awakening: Optional[AwakeningSignal] = None
    ) -> Optional[Dict[str, Any]]:
        """生成照亮结果"""
        if not recalled_patterns and not awakening and not portfolio_awakening:
            return None

        content_parts = []

        if awakening:
            content_parts.append(f"顿悟: {awakening.illumination_content}")
            content_parts.append(f"置信度: {awakening.confidence:.2f}")

        if portfolio_awakening:
            content_parts.append(f"持仓顿悟: {portfolio_awakening.illumination_content}")
            content_parts.append(f"持仓置信度: {portfolio_awakening.confidence:.2f}")

        if recalled_patterns:
            avg_success_rate = sum(1 for p in recalled_patterns if p.success) / len(recalled_patterns)
            content_parts.append(f"历史模式匹配数: {len(recalled_patterns)}, 成功率: {avg_success_rate:.1%}")

        return {
            "content": " | ".join(content_parts),
            "awakening": awakening,
            "patterns": [
                {
                    "pattern_id": p.pattern_id,
                    "type": p.pattern_type,
                    "success": p.success
                }
                for p in recalled_patterns[:3]
            ],
            "timestamp": time.time()
        }

    def archive_pattern(
        self,
        pattern_id: str,
        pattern_type: str,
        market_context: Dict[str, Any],
        outcome: Dict[str, Any]
    ):
        """归档模式"""
        self.pattern_archive.archive(pattern_id, pattern_type, market_context, outcome)

        if outcome.get("return", 0) > 0.05:
            self.cross_market_memory.store_success_pattern(
                source_market=market_context.get("source_market", "a_stock"),
                pattern={
                    "pattern_id": pattern_id,
                    "conditions": market_context
                }
            )

    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "integration_count": self._integration_count,
            "awakening_level": self.awakening_engine.get_awakening_level(),
            "pattern_archive": self.pattern_archive.get_archive_stats(),
            "cross_market_sources": list(self.cross_market_memory._source_memories.keys())
        }
