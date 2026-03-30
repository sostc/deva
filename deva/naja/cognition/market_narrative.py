"""
MarketNarrativeSense - 市场叙事理解

"妙观察智"的具体实现

核心能力：
1. NarrativeTracker: 追踪当前市场叙事
2. NarrativeTransitionSense: 感知叙事转换
3. StoryConflictDetector: 检测叙事冲突
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from collections import deque
from enum import Enum

log = logging.getLogger(__name__)


class NarrativeType(Enum):
    """叙事类型"""
    POLICY = "policy"           # 政策驱动
    EARNINGS = "earnings"       # 业绩驱动
    LIQUIDITY = "liquidity"     # 流动性驱动
    SENTIMENT = "sentiment"     # 情绪驱动
    SECTOR = "sector"           # 板块轮动
    GLOBAL = "global"           # 全球联动
    UNKNOWN = "unknown"          # 未知


class NarrativeStage(Enum):
    """叙事阶段"""
    EMERGING = "emerging"       # 萌芽期
    BUILDING = "building"       # 构建期
    PEAK = "peak"              # 高潮期
    FADING = "fading"           # 消退期
    DEAD = "dead"              # 死亡期


@dataclass
class MarketNarrative:
    """市场叙事"""
    narrative_type: NarrativeType
    stage: NarrativeStage
    confidence: float           # 置信度 [0, 1]
    evidence: List[str]         # 支撑证据
    start_time: float           # 开始时间
    strength: float             # 强度 [0, 1]
    related_sectors: List[str]   # 相关板块
    key_stocks: List[str]       # 关键股票


@dataclass
class NarrativeTransition:
    """叙事转换信号"""
    from_narrative: NarrativeType
    to_narrative: NarrativeType
    confidence: float
    trigger_signals: List[str]
    expected_timing: str        # "immediate", "within_day", "within_week"
    intensity: float


@dataclass
class StoryConflict:
    """故事冲突"""
    narrative_a: NarrativeType
    narrative_b: NarrativeType
    conflict_type: str          # "contradictory", "competing", "unrelated"
    resolution_hint: str         # 解决线索
    recommended_action: str     # 建议行动


class NarrativeTracker:
    """
    叙事追踪器

    追踪当前市场在讲什么故事
    """

    def __init__(self):
        self._current_narratives: deque = deque(maxlen=5)
        self._narrative_history: deque = deque(maxlen=100)
        self._last_update: float = time.time()

    def track(
        self,
        market_data: Dict[str, Any],
        news_signals: Optional[List[str]] = None,
        flow_data: Optional[Dict[str, Any]] = None
    ) -> List[MarketNarrative]:
        """
        追踪当前叙事

        Args:
            market_data: 市场数据
            news_signals: 新闻信号
            flow_data: 资金流向数据

        Returns:
            当前活跃的叙事列表
        """
        narratives = []

        # 检测政策叙事
        policy_narrative = self._detect_policy_narrative(market_data, news_signals)
        if policy_narrative:
            narratives.append(policy_narrative)

        # 检测业绩叙事
        earnings_narrative = self._detect_earnings_narrative(market_data)
        if earnings_narrative:
            narratives.append(earnings_narrative)

        # 检测流动性叙事
        liquidity_narrative = self._detect_liquidity_narrative(market_data, flow_data)
        if liquidity_narrative:
            narratives.append(liquidity_narrative)

        # 检测情绪叙事
        sentiment_narrative = self._detect_sentiment_narrative(market_data)
        if sentiment_narrative:
            narratives.append(sentiment_narrative)

        # 检测板块叙事
        sector_narrative = self._detect_sector_narrative(market_data)
        if sector_narrative:
            narratives.append(sector_narrative)

        self._current_narratives = deque(narratives, maxlen=5)
        self._last_update = time.time()

        for n in narratives:
            self._narrative_history.append(n)

        return narratives

    def _detect_policy_narrative(
        self,
        market_data: Dict[str, Any],
        news_signals: Optional[List[str]]
    ) -> Optional[MarketNarrative]:
        """检测政策叙事"""
        if not news_signals:
            return None

        policy_keywords = ["政策", "央行", "证监会", "降准", "降息", "刺激", "改革"]
        policy_signals = [n for n in news_signals if any(k in n for k in policy_keywords)]

        if len(policy_signals) >= 2:
            return MarketNarrative(
                narrative_type=NarrativeType.POLICY,
                stage=self._estimate_stage(len(policy_signals)),
                confidence=min(1.0, len(policy_signals) / 5),
                evidence=policy_signals[:5],
                start_time=time.time(),
                strength=self._estimate_strength(policy_signals),
                related_sectors=["金融", "地产", "基建"],
                key_stocks=[]
            )

        return None

    def _detect_earnings_narrative(self, market_data: Dict[str, Any]) -> Optional[MarketNarrative]:
        """检测业绩叙事"""
        changes = market_data.get("price_changes", [])
        if not changes:
            return None

        # 业绩驱动特征：个股分化严重，龙头强
        avg_change = sum(changes) / len(changes)
        std_change = (sum((c - avg_change) ** 2 for c in changes) / len(changes)) ** 0.5

        # 高分化度可能意味着业绩筛选
        if std_change > 2.0 and avg_change > 0.5:
            return MarketNarrative(
                narrative_type=NarrativeType.EARNINGS,
                stage=NarrativeStage.BUILDING,
                confidence=0.6,
                evidence=[f"个股分化度: {std_change:.2f}%"],
                start_time=time.time(),
                strength=min(1.0, std_change / 5),
                related_sectors=self._get_top_sectors(market_data),
                key_stocks=[]
            )

        return None

    def _detect_liquidity_narrative(
        self,
        market_data: Dict[str, Any],
        flow_data: Optional[Dict[str, Any]]
    ) -> Optional[MarketNarrative]:
        """检测流动性叙事"""
        if not flow_data:
            return None

        net_flow = flow_data.get("net_flow", 0)
        big_deal_ratio = flow_data.get("big_deal_ratio", 0)

        if abs(net_flow) > 1000000000 and big_deal_ratio > 0.5:
            direction = "流入" if net_flow > 0 else "流出"
            return MarketNarrative(
                narrative_type=NarrativeType.LIQUIDITY,
                stage=NarrativeStage.PEAK if abs(net_flow) > 5000000000 else NarrativeStage.BUILDING,
                confidence=0.7,
                evidence=[f"主力净{direction}: {net_flow/1e8:.1f}亿", f"大单占比: {big_deal_ratio:.1%}"],
                start_time=time.time(),
                strength=min(1.0, abs(net_flow) / 1e10),
                related_sectors=[],
                key_stocks=[]
            )

        return None

    def _detect_sentiment_narrative(self, market_data: Dict[str, Any]) -> Optional[MarketNarrative]:
        """检测情绪叙事"""
        changes = market_data.get("price_changes", [])
        if not changes:
            return None

        advancing = sum(1 for c in changes if c > 0)
        declining = sum(1 for c in changes if c < 0)
        breadth = (advancing - declining) / len(changes)

        if abs(breadth) > 0.3:
            sentiment = "乐观" if breadth > 0 else "悲观"
            return MarketNarrative(
                narrative_type=NarrativeType.SENTIMENT,
                stage=NarrativeStage.PEAK if abs(breadth) > 0.5 else NarrativeStage.BUILDING,
                confidence=0.6,
                evidence=[f"市场广度: {breadth:.1%}", f"上涨: {advancing}, 下跌: {declining}"],
                start_time=time.time(),
                strength=abs(breadth),
                related_sectors=[],
                key_stocks=[]
            )

        return None

    def _detect_sector_narrative(self, market_data: Dict[str, Any]) -> Optional[MarketNarrative]:
        """检测板块叙事"""
        sector_changes = market_data.get("sector_changes", {})
        if len(sector_changes) < 3:
            return None

        top_sectors = sorted(sector_changes.items(), key=lambda x: x[1], reverse=True)[:3]
        bottom_sectors = sorted(sector_changes.items(), key=lambda x: x[1])[:3]

        if top_sectors[0][1] - bottom_sectors[0][1] > 3.0:
            return MarketNarrative(
                narrative_type=NarrativeType.SECTOR,
                stage=NarrativeStage.BUILDING,
                confidence=0.7,
                evidence=[f"领涨: {top_sectors[0][0]}({top_sectors[0][1]:.1f}%)"],
                start_time=time.time(),
                strength=min(1.0, (top_sectors[0][1] - bottom_sectors[0][1]) / 10),
                related_sectors=[s[0] for s in top_sectors],
                key_stocks=[]
            )

        return None

    def _estimate_stage(self, signal_count: int) -> NarrativeStage:
        """估算叙事阶段"""
        if signal_count <= 2:
            return NarrativeStage.EMERGING
        elif signal_count <= 5:
            return NarrativeStage.BUILDING
        elif signal_count <= 8:
            return NarrativeStage.PEAK
        else:
            return NarrativeStage.FADING

    def _estimate_strength(self, signals: List[str]) -> float:
        """估算叙事强度"""
        base = min(1.0, len(signals) / 10)
        quality_boost = sum(1 for s in signals if len(s) > 20) * 0.05
        return min(1.0, base + quality_boost)

    def _get_top_sectors(self, market_data: Dict[str, Any]) -> List[str]:
        """获取领涨板块"""
        sector_changes = market_data.get("sector_changes", {})
        return [s[0] for s in sorted(sector_changes.items(), key=lambda x: x[1], reverse=True)[:3]]

    def get_current_narratives(self) -> List[MarketNarrative]:
        """获取当前叙事"""
        return list(self._current_narratives)

    def get_narrative_summary(self) -> Dict[str, Any]:
        """获取叙事摘要"""
        if not self._current_narratives:
            return {"status": "no_narrative"}

        return {
            "status": "active",
            "narrative_count": len(self._current_narratives),
            "dominant": self._current_narratives[0].narrative_type.value,
            "stage": self._current_narratives[0].stage.value,
            "strength": self._current_narratives[0].strength,
            "time_since_update": time.time() - self._last_update
        }


class NarrativeTransitionSense:
    """
    叙事转换感知器

    感知当前叙事何时会转换
    """

    def __init__(self):
        self._transition_history: deque = deque(maxlen=50)

    def sense_transition(
        self,
        current_narratives: List[MarketNarrative],
        market_data: Dict[str, Any],
        flow_data: Optional[Dict[str, Any]] = None
    ) -> Optional[NarrativeTransition]:
        """
        感知叙事转换

        Returns:
            叙事转换信号，如果没检测到转换则返回 None
        """
        if not current_narratives:
            return None

        dominant = current_narratives[0]

        # 检测到高潮期，可能即将消退
        if dominant.stage == NarrativeStage.PEAK:
            transition = self._predict_transition(dominant, market_data, flow_data)
            if transition:
                self._transition_history.append(transition)
                return transition

        return None

    def _predict_transition(
        self,
        narrative: MarketNarrative,
        market_data: Dict[str, Any],
        flow_data: Optional[Dict[str, Any]]
    ) -> Optional[NarrativeTransition]:
        """预测叙事转换"""
        if narrative.narrative_type == NarrativeType.LIQUIDITY:
            if flow_data and abs(flow_data.get("net_flow", 0)) > 5000000000:
                return NarrativeTransition(
                    from_narrative=narrative.narrative_type,
                    to_narrative=NarrativeType.SENTIMENT,
                    confidence=0.6,
                    trigger_signals=["流动性高潮预警", "大单开始撤退"],
                    expected_timing="within_day",
                    intensity=0.7
                )

        elif narrative.narrative_type == NarrativeType.SECTOR:
            sector_changes = market_data.get("sector_changes", {})
            top_strength = max(sector_changes.values()) if sector_changes else 0
            if top_strength > 5.0:
                return NarrativeTransition(
                    from_narrative=narrative.narrative_type,
                    to_narrative=NarrativeType.EARNINGS,
                    confidence=0.5,
                    trigger_signals=["板块轮动加速", "个股分化"],
                    expected_timing="within_week",
                    intensity=0.6
                )

        return None


class StoryConflictDetector:
    """
    故事冲突检测器

    检测不同叙事之间的冲突
    """

    def __init__(self):
        self._conflicts: deque = deque(maxlen=30)

    def detect_conflict(
        self,
        narratives: List[MarketNarrative]
    ) -> List[StoryConflict]:
        """
        检测叙事冲突

        Returns:
            冲突列表
        """
        conflicts = []

        for i, n1 in enumerate(narratives):
            for n2 in narratives[i+1:]:
                conflict = self._check_pair_conflict(n1, n2)
                if conflict:
                    conflicts.append(conflict)

        self._conflicts = deque(conflicts, maxlen=30)
        return conflicts

    def _check_pair_conflict(
        self,
        n1: MarketNarrative,
        n2: MarketNarrative
    ) -> Optional[StoryConflict]:
        """检查两个叙事是否有冲突"""
        # 政策利多 vs 业绩利空
        if n1.narrative_type == NarrativeType.POLICY and n2.narrative_type == NarrativeType.EARNINGS:
            if n1.strength > 0.7 and n2.strength > 0.7:
                return StoryConflict(
                    narrative_a=n1.narrative_type,
                    narrative_b=n2.narrative_type,
                    conflict_type="contradictory",
                    resolution_hint="政策权重更高，等待业绩验证",
                    recommended_action="轻仓观望，等待明确信号"
                )

        # 流动性流入 vs 情绪悲观
        if n1.narrative_type == NarrativeType.LIQUIDITY and n2.narrative_type == NarrativeType.SENTIMENT:
            if (n1.strength > 0.6 and n2.strength > 0.6 and
                ((n1.evidence and "流入" in str(n1.evidence)) or (n2.evidence and "流出" in str(n2.evidence)))):
                return StoryConflict(
                    narrative_a=n1.narrative_type,
                    narrative_b=n2.narrative_type,
                    conflict_type="competing",
                    resolution_hint="资金是更底层的驱动",
                    recommended_action="跟资金走"
                )

        return None

    def get_active_conflicts(self) -> List[StoryConflict]:
        """获取活跃冲突"""
        return list(self._conflicts)


class MarketNarrativeSense:
    """
    市场叙事感知（妙观察智核心）

    整合叙事追踪、转换感知、冲突检测
    """

    def __init__(self):
        self.tracker = NarrativeTracker()
        self.transition_sense = NarrativeTransitionSense()
        self.conflict_detector = StoryConflictDetector()

    def sense(
        self,
        market_data: Dict[str, Any],
        news_signals: Optional[List[str]] = None,
        flow_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        感知市场叙事

        Args:
            market_data: 市场数据
            news_signals: 新闻信号列表
            flow_data: 资金流向数据

        Returns:
            包含 narratives, transitions, conflicts 的字典
        """
        narratives = self.tracker.track(market_data, news_signals, flow_data)

        transitions = []
        if narratives:
            transition = self.transition_sense.sense_transition(narratives, market_data, flow_data)
            if transition:
                transitions.append(transition)

        conflicts = []
        if len(narratives) >= 2:
            conflicts = self.conflict_detector.detect_conflict(narratives)

        return {
            "narratives": narratives,
            "transitions": transitions,
            "conflicts": conflicts,
            "summary": self._build_summary(narratives, transitions, conflicts)
        }

    def _build_summary(
        self,
        narratives: List[MarketNarrative],
        transitions: List[NarrativeTransition],
        conflicts: List[StoryConflict]
    ) -> str:
        """构建叙事摘要"""
        if not narratives:
            return "当前无明显叙事，市场混沌"

        dominant = narratives[0]
        summary_parts = [f"主叙事: {dominant.narrative_type.value}"]

        summary_parts.append(f"阶段: {dominant.stage.value}")
        summary_parts.append(f"强度: {dominant.strength:.0%}")

        if transitions:
            t = transitions[0]
            summary_parts.append(f"⚠️ 转换预警: {t.from_narrative.value}→{t.to_narrative.value}")

        if conflicts:
            summary_parts.append(f"⚡ 冲突: {len(conflicts)}个")

        return " | ".join(summary_parts)

    def get_dominant_narrative(self) -> Optional[MarketNarrative]:
        """获取主导叙事"""
        narratives = self.tracker.get_current_narratives()
        return narratives[0] if narratives else None