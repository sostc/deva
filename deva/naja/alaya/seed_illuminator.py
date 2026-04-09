"""
SeedIlluminator - 光明藏种子发光

让沉睡的种子主动发光，从历史模式中"预见"当前机会

能力：
1. PatternRecall: 模式召回 - 从历史中发现当前机会
2. CrossMarketTransfer: 跨市场迁移 - 期市经验用到股市
3. SeedGlow: 种子发光 - 主动照亮机会

使用方式：
    illuminator = SeedIlluminator()
    pattern = illuminator.recall(current_market_state)
    if pattern:
        print(f"想起了: {pattern.name}")
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from collections import deque, defaultdict
import math

log = logging.getLogger(__name__)


class PatternType(Enum):
    """模式类型"""
    MOMENTUM = "momentum"
    REVERSAL = "reversal"
    BREAKOUT = "breakout"
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    BLOCK_ROTATION = "block_rotation"
    LIQUIDITY_TURN = "liquidity_turn"
    SENTIMENT_EXTREME = "sentiment_extreme"


@dataclass
class IlluminatedPattern:
    """被照亮的模式"""
    pattern_type: PatternType
    name: str
    description: str
    confidence: float
    illumination_strength: float
    historical_matches: int
    success_rate: float
    avg_holding_period: float
    symbols: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    direction: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_type": self.pattern_type.value,
            "name": self.name,
            "description": self.description,
            "confidence": self.confidence,
            "illumination_strength": self.illumination_strength,
            "historical_matches": self.historical_matches,
            "success_rate": self.success_rate,
            "avg_holding_period": self.avg_holding_period,
            "symbols": self.symbols,
            "direction": self.direction,
        }


class PatternTemplate:
    """模式模板"""

    def __init__(
        self,
        pattern_type: PatternType,
        name: str,
        conditions: Dict[str, Any],
        description: str = ""
    ):
        self.pattern_type = pattern_type
        self.name = name
        self.conditions = conditions
        self.description = description


class SeedIlluminator:
    """
    光明藏 - 种子发光引擎

    核心思想：
    - 种子不再沉睡，主动发光
    - 从历史模式中"顿悟"当前机会
    - 跨市场迁移学习
    """

    TEMPLATES = [
        PatternTemplate(
            PatternType.MOMENTUM,
            "动量加速",
            {"price_change": (0.02, 1.0), "volume_ratio": 1.5, "time_window": 5},
            "价格持续上涨且成交量放大"
        ),
        PatternTemplate(
            PatternType.REVERSAL,
            "超跌反弹",
            {"price_change": (-1.0, -0.05), "volume_ratio": 2.0, "breadth_ratio": 0.3},
            "超跌后放量反弹"
        ),
        PatternTemplate(
            PatternType.BREAKOUT,
            "突破新高",
            {"price_position": 0.95, "volume_ratio": 1.8, "volatility_compression": 0.5},
            "盘整后放量突破"
        ),
        PatternTemplate(
            PatternType.ACCUMULATION,
            "主力吸筹",
            {"price_change": (-0.03, 0.03), "main_flow_ratio": 0.7, "volume_ratio": 0.8},
            "震荡中主力悄悄吸筹"
        ),
        PatternTemplate(
            PatternType.BLOCK_ROTATION,
            "题材轮动",
            {"block_breadth_change": 0.3, "rotation_speed": 0.5},
            "资金从一个题材流向另一个题材"
        ),
        PatternTemplate(
            PatternType.LIQUIDITY_TURN,
            "流动性拐点",
            {"liquidity_change": 0.5, "volatility_change": 0.3},
            "流动性突然宽松"
        ),
        PatternTemplate(
            PatternType.SENTIMENT_EXTREME,
            "情绪极端",
            {"breadth_ratio": 0.8, "advancing_ratio": 0.9},
            "市场情绪极度乐观/悲观"
        ),
    ]

    def __init__(self):
        self._pattern_history: List[IlluminatedPattern] = []
        self._market_state_history: deque = deque(maxlen=100)
        self._pattern_match_stats: Dict[str, Dict[str, float]] = defaultdict(lambda: {
            "matches": 0,
            "successes": 0,
            "total_holding_period": 0.0
        })
        self._cross_market_memory: Dict[str, List[Dict]] = defaultdict(list)

    def register_market_state(self, state: Dict[str, Any]):
        """注册市场状态"""
        self._market_state_history.append({
            "timestamp": time.time(),
            "state": state.copy()
        })

    def recall(
        self,
        current_state: Dict[str, Any],
        min_confidence: float = 0.5,
        max_patterns: int = 3
    ) -> List[IlluminatedPattern]:
        """
        召回匹配的模式

        Args:
            current_state: 当前市场状态
            min_confidence: 最低置信度
            max_patterns: 最多返回的模式数

        Returns:
            List[IlluminatedPattern]
        """
        illuminated = []

        for template in self.TEMPLATES:
            match_result = self._check_template_match(template, current_state)
            if match_result["matched"]:
                pattern = self._create_illuminated_pattern(template, match_result, current_state)
                if pattern.confidence >= min_confidence:
                    illuminated.append(pattern)

        illuminated.sort(key=lambda p: p.illumination_strength * p.confidence, reverse=True)

        self._pattern_history.extend(illuminated[:max_patterns])
        if len(self._pattern_history) > 100:
            self._pattern_history = self._pattern_history[-100:]

        return illuminated[:max_patterns]

    def _check_template_match(
        self,
        template: PatternTemplate,
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """检查模板是否匹配"""
        conditions = template.conditions
        matched = True
        match_details = {}

        if "price_change" in conditions:
            pc = state.get("price_change", 0)
            min_pc, max_pc = conditions["price_change"]
            if not (min_pc <= pc <= max_pc):
                matched = False
            match_details["price_change"] = pc

        if "volume_ratio" in conditions and matched:
            vr = state.get("volume_ratio", 1.0)
            if vr < conditions["volume_ratio"]:
                matched = False
            match_details["volume_ratio"] = vr

        if "price_position" in conditions and matched:
            pp = state.get("price_position", 0.5)
            if pp < conditions["price_position"]:
                matched = False
            match_details["price_position"] = pp

        if "main_flow_ratio" in conditions and matched:
            mfr = state.get("main_flow_ratio", 0)
            if mfr < conditions["main_flow_ratio"]:
                matched = False
            match_details["main_flow_ratio"] = mfr

        if "breadth_ratio" in conditions and matched:
            br = state.get("breadth_ratio", 0)
            if abs(br) < conditions["breadth_ratio"]:
                matched = False
            match_details["breadth_ratio"] = br

        if "advancing_ratio" in conditions and matched:
            ar = state.get("advancing_ratio", 0.5)
            if ar < conditions["advancing_ratio"]:
                matched = False
            match_details["advancing_ratio"] = ar

        if "block_breadth_change" in conditions and matched:
            sbc = state.get("block_breadth_change", 0)
            if abs(sbc) < conditions["block_breadth_change"]:
                matched = False
            match_details["block_breadth_change"] = sbc

        illumination = self._calculate_illumination(template.pattern_type, match_details)

        return {
            "matched": matched,
            "match_details": match_details,
            "illumination": illumination
        }

    def _calculate_illumination(self, pattern_type: PatternType, match_details: Dict) -> float:
        """计算照明强度"""
        base = 0.5

        recency_boost = self._get_recency_boost(pattern_type)
        historical_boost = self._get_historical_boost(pattern_type)

        illumination = base + recency_boost * 0.3 + historical_boost * 0.2

        return min(1.0, illumination)

    def _get_recency_boost(self, pattern_type: PatternType) -> float:
        """根据近期是否出现过类似模式计算加成"""
        recent = [p for p in self._pattern_history if
                  p.pattern_type == pattern_type and
                  time.time() - p.timestamp < 3600]

        if not recent:
            return 1.0

        if len(recent) >= 3:
            return 0.3

        return 1.0 - len(recent) * 0.2

    def _get_historical_boost(self, pattern_type: PatternType) -> float:
        """根据历史成功率计算加成"""
        stats = self._pattern_match_stats.get(pattern_type.value)
        if stats is None or stats.get("matches", 0) == 0:
            return 0.5

        success_rate = stats.get("successes", 0) / stats.get("matches", 1)
        return success_rate

    def _create_illuminated_pattern(
        self,
        template: PatternTemplate,
        match_result: Dict,
        current_state: Dict[str, Any]
    ) -> IlluminatedPattern:
        """创建被照亮的模式"""
        pattern_type = template.pattern_type
        stats = self._pattern_match_stats.get(pattern_type.value, {})

        historical_matches = stats.get("matches", 0)
        success_rate = stats.get("successes", 0) / max(1, historical_matches)
        avg_holding = stats.get("total_holding_period", 0) / max(1, historical_matches)

        direction = 0
        if pattern_type == PatternType.MOMENTUM:
            direction = 1
        elif pattern_type == PatternType.REVERSAL:
            direction = 1
        elif pattern_type == PatternType.BREAKOUT:
            direction = 1
        elif pattern_type == PatternType.DISTRIBUTION:
            direction = -1

        illumination = match_result["illumination"]
        confidence = illumination * (0.5 + success_rate * 0.5)

        return IlluminatedPattern(
            pattern_type=pattern_type,
            name=template.name,
            description=template.description,
            confidence=confidence,
            illumination_strength=illumination,
            historical_matches=historical_matches,
            success_rate=success_rate,
            avg_holding_period=avg_holding,
            symbols=current_state.get("symbols", []),
            direction=direction
        )

    def record_outcome(
        self,
        pattern_type: PatternType,
        success: bool,
        holding_period: float,
        market_context: Optional[Dict[str, Any]] = None
    ):
        """记录模式结果（用于学习）

        Args:
            pattern_type: 模式类型
            success: 是否成功
            holding_period: 持仓周期
            market_context: 市场上下文（可选），包含 volume_ratio, price_change 等
        """
        key = pattern_type.value
        self._pattern_match_stats[key]["matches"] += 1
        if success:
            self._pattern_match_stats[key]["successes"] += 1
        self._pattern_match_stats[key]["total_holding_period"] += holding_period

        if market_context:
            self._pattern_history.append({
                "pattern_type": pattern_type,
                "success": success,
                "holding_period": holding_period,
                "market_context": market_context,
                "timestamp": time.time()
            })

    def transfer_from_market(
        self,
        source_market: str,
        pattern_type: PatternType,
        pattern_data: Dict[str, Any]
    ):
        """从其他市场迁移模式记忆"""
        self._cross_market_memory[source_market].append({
            "pattern_type": pattern_type,
            "data": pattern_data,
            "timestamp": time.time()
        })

    def recall_cross_market(
        self,
        target_market: str,
        current_state: Dict[str, Any]
    ) -> List[IlluminatedPattern]:
        """跨市场召回"""
        source_patterns = self._cross_market_memory.get(target_market, [])
        if not source_patterns:
            return []

        recent_source = [p for p in source_patterns
                        if time.time() - p["timestamp"] < 86400]

        if not recent_source:
            return []

        illuminated = []
        for sp in recent_source[:3]:
            pattern_type = sp["pattern_type"]
            pattern_data = sp["data"]

            for template in self.TEMPLATES:
                if template.pattern_type == pattern_type:
                    pattern = IlluminatedPattern(
                        pattern_type=pattern_type,
                        name=f"[迁移]{template.name}",
                        description=f"从{target_market}迁移的经验",
                        confidence=0.4,
                        illumination_strength=0.5,
                        historical_matches=1,
                        success_rate=0.6,
                        avg_holding_period=3600
                    )
                    illuminated.append(pattern)

        return illuminated

    def get_glowing_seeds(self) -> List[Dict[str, Any]]:
        """获取正在发光的种子"""
        return [p.to_dict() for p in self._pattern_history[-10:]]

    def get_state(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "pattern_history_count": len(self._pattern_history),
            "cross_market_markets": list(self._cross_market_memory.keys()),
            "pattern_stats": {
                k: {
                    "matches": v["matches"],
                    "success_rate": v["successes"] / max(1, v["matches"])
                }
                for k, v in self._pattern_match_stats.items()
            }
        }
