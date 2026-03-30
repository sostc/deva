"""
EpiphanyEngine - 顿悟引擎

"大圆镜智"的具体实现

核心能力：
1. CrossMarketTransfer: 跨市场模式迁移
2. PatternEpiphany: 模式顿悟
3. FullRecall: 全量召回
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from collections import deque
from enum import Enum

log = logging.getLogger(__name__)


class MarketType(Enum):
    """市场类型"""
    A_SHARE = "a_share"       # A股
    HK_STOCK = "hk_stock"     # 港股
    US_STOCK = "us_stock"     # 美股
    FUTURES = "futures"       # 期货
    CRYPTO = "crypto"         # 加密货币


@dataclass
class CrossMarketPattern:
    """跨市场模式"""
    pattern_id: str
    source_market: MarketType
    target_market: MarketType
    pattern_type: str
    description: str
    transfer_confidence: float
    success_count: int
    last_success_time: float
    conditions: List[str]


@dataclass
class Epiphany:
    """顿悟"""
    epiphany_type: str        # "cross_market", "pattern_discovery", "timing_insight"
    content: str
    confidence: float
    triggered_by: List[str]    # 触发信号
    timestamp: float
    usefulness: float         # 有用性评分


class CrossMarketTransfer:
    """
    跨市场模式迁移

    将一个市场的有效模式迁移到另一个市场
    """

    def __init__(self):
        self._transfer_patterns: Dict[str, CrossMarketPattern] = {}
        self._transfer_history: deque = deque(maxlen=100)

    def register_pattern(
        self,
        source_market: MarketType,
        pattern: Dict[str, Any],
        success: bool
    ):
        """注册跨市场模式"""
        pattern_key = f"{source_market.value}_{pattern.get('type', 'unknown')}"

        if pattern_key in self._transfer_patterns:
            p = self._transfer_patterns[pattern_key]
            if success:
                p.success_count += 1
                p.last_success_time = time.time()
        else:
            self._transfer_patterns[pattern_key] = CrossMarketPattern(
                pattern_id=pattern_key,
                source_market=source_market,
                target_market=MarketType.A_SHARE,
                pattern_type=pattern.get("type", "unknown"),
                description=pattern.get("description", ""),
                transfer_confidence=0.5,
                success_count=1 if success else 0,
                last_success_time=time.time(),
                conditions=pattern.get("conditions", [])
            )

    def find_applicable_patterns(
        self,
        current_market: MarketType,
        market_data: Dict[str, Any]
    ) -> List[CrossMarketPattern]:
        """查找适用的跨市场模式"""
        applicable = []

        for pattern in self._transfer_patterns.values():
            if pattern.target_market != current_market:
                continue

            if self._check_conditions(pattern.conditions, market_data):
                applicable.append(pattern)

        return sorted(applicable, key=lambda x: x.transfer_confidence * x.success_count, reverse=True)[:3]

    def _check_conditions(self, conditions: List[str], market_data: Dict[str, Any]) -> bool:
        """检查条件是否满足"""
        if not conditions:
            return True

        for cond in conditions:
            if "trend" in cond.lower() and market_data.get("trend_strength", 0) < 0.3:
                return False
            if "volatility" in cond.lower() and market_data.get("volatility", 1) < 1.5:
                return False

        return True

    def update_confidence(self):
        """更新迁移置信度"""
        for pattern in self._transfer_patterns.values():
            if pattern.success_count >= 3:
                pattern.transfer_confidence = min(0.95, 0.3 + pattern.success_count * 0.1)

    def get_cross_market_summary(self) -> Dict[str, Any]:
        """获取跨市场摘要"""
        return {
            "total_patterns": len(self._transfer_patterns),
            "by_source": {
                m.value: len([p for p in self._transfer_patterns.values() if p.source_market == m])
                for m in MarketType
            }
        }


class PatternEpiphany:
    """
    模式顿悟

    当多个弱信号组合时，突然想通某个模式
    """

    def __init__(self):
        self._epiphanies: deque = deque(maxlen=50)
        self._weak_signals: deque = deque(maxlen=20)

    def receive_signal(self, signal: Dict[str, Any]):
        """接收弱信号"""
        self._weak_signals.append({
            **signal,
            "timestamp": time.time()
        })

    def check_for_epiphany(self) -> Optional[Epiphany]:
        """检查是否顿悟"""
        if len(self._weak_signals) < 3:
            return None

        recent = list(self._weak_signals)[-5:]

        momentum_signals = [s for s in recent if s.get("type") == "momentum"]
        flow_signals = [s for s in recent if s.get("type") == "flow"]
        sentiment_signals = [s for s in recent if s.get("type") == "sentiment"]

        if (len(momentum_signals) >= 2 and len(flow_signals) >= 1 and
            momentum_signals[0].get("direction") != momentum_signals[1].get("direction")):
            return Epiphany(
                epiphany_type="timing_insight",
                content="动量与资金流向出现分歧，可能是转折点",
                confidence=0.7,
                triggered_by=[s.get("description", "") for s in recent],
                timestamp=time.time(),
                usefulness=0.8
            )

        if len(sentiment_signals) >= 2:
            avg_sentiment = sum(s.get("value", 0) for s in sentiment_signals) / len(sentiment_signals)
            if abs(avg_sentiment) > 0.6:
                return Epiphany(
                    epiphany_type="pattern_discovery",
                    content=f"情绪极端{'乐观' if avg_sentiment > 0 else '悲观'}，注意反转风险",
                    confidence=0.75,
                    triggered_by=[s.get("description", "") for s in recent],
                    timestamp=time.time(),
                    usefulness=0.9
                )

        return None

    def record_epiphany_outcome(self, epiphany: Epiphany, useful: bool):
        """记录顿悟结果"""
        for e in self._epiphanies:
            if e.timestamp == epiphany.timestamp:
                e.usefulness = 0.5 if useful else 0.2
                break

    def get_recent_epiphanies(self) -> List[Epiphany]:
        """获取最近顿悟"""
        return list(self._epiphanies)


class FullRecall:
    """
    全量召回

    从所有历史模式中召回相关的
    """

    def __init__(self):
        self._pattern_archive: Dict[str, List[Dict[str, Any]]] = {
            "momentum": [],
            "reversal": [],
            "breakout": [],
            "accumulation": []
        }

    def archive_pattern(
        self,
        pattern_type: str,
        pattern_data: Dict[str, Any],
        outcome: Dict[str, Any]
    ):
        """归档模式"""
        if pattern_type not in self._pattern_archive:
            self._pattern_archive[pattern_type] = []

        self._pattern_archive[pattern_type].append({
            **pattern_data,
            "outcome": outcome,
            "archived_at": time.time()
        })

        if len(self._pattern_archive[pattern_type]) > 1000:
            self._pattern_archive[pattern_type] = self._pattern_archive[pattern_type][-1000:]

    def recall(
        self,
        pattern_type: str,
        criteria: Dict[str, Any],
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """召回匹配的模式"""
        if pattern_type not in self._pattern_archive:
            return []

        patterns = self._pattern_archive[pattern_type]
        matched = []

        for p in patterns:
            if self._match_criteria(p, criteria):
                matched.append(p)

        matched.sort(key=lambda x: x.get("outcome", {}).get("success_rate", 0), reverse=True)
        return matched[:limit]

    def _match_criteria(self, pattern: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
        """匹配标准"""
        for key, value in criteria.items():
            if key not in pattern:
                return False
            if isinstance(value, (int, float)) and isinstance(pattern[key], (int, float)):
                if abs(pattern[key] - value) > 0.3:  # 固定容差
                    return False
            elif pattern[key] != value:
                return False
        return True

    def get_archive_stats(self) -> Dict[str, int]:
        """获取归档统计"""
        return {k: len(v) for k, v in self._pattern_archive.items()}


class EpiphanyEngine:
    """
    顿悟引擎（大圆镜智）

    整合跨市场迁移、模式顿悟、全量召回
    """

    def __init__(self):
        self.cross_market = CrossMarketTransfer()
        self.pattern_epiphany = PatternEpiphany()
        self.full_recall = FullRecall()

    def receive_signal(self, signal: Dict[str, Any]):
        """接收信号"""
        self.pattern_epiphany.receive_signal(signal)

    def check_epiphany(self) -> Optional[Epiphany]:
        """检查顿悟"""
        return self.pattern_epiphany.check_for_epiphany()

    def archive_outcome(
        self,
        pattern_type: str,
        pattern_data: Dict[str, Any],
        outcome: Dict[str, Any]
    ):
        """归档结果"""
        self.full_recall.archive_pattern(pattern_type, pattern_data, outcome)

    def recall_patterns(
        self,
        pattern_type: str,
        criteria: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """召回模式"""
        return self.full_recall.recall(pattern_type, criteria)

    def find_cross_market_opportunities(
        self,
        current_market: MarketType,
        market_data: Dict[str, Any]
    ) -> List[CrossMarketPattern]:
        """查找跨市场机会"""
        return self.cross_market.find_applicable_patterns(current_market, market_data)

    def get_engine_summary(self) -> Dict[str, Any]:
        """获取引擎摘要"""
        return {
            "cross_market_summary": self.cross_market.get_cross_market_summary(),
            "epiphany_count": len(self.pattern_epiphany._epiphanies),
            "archive_stats": self.full_recall.get_archive_stats()
        }