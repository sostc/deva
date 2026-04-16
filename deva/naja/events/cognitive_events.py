"""
Cognitive Events - 认知系统相关事件

用于认知系统与其他系统之间的通信
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import time


@dataclass
class CognitiveInsightEvent:
    """
    认知洞察事件
    
    当InsightEngine生成新的市场洞察时发布
    """
    insights: List[Dict[str, Any]]
    confidence: float
    timestamp: float
    source: str = "insight_engine"
    market: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)


@dataclass
class NarrativeStateEvent:
    """
    叙事状态事件
    
    当NarrativeTracker更新叙事状态时发布
    """
    current_narratives: List[str]
    narrative_strength: float
    narrative_risk: float
    sentiment_score: float
    timestamp: float
    source: str = "narrative_tracker"
    market: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)


@dataclass
class LiquiditySignalEvent:
    """
    流动性信号事件
    
    当LiquidityCognition生成流动性预测时发布
    """
    prediction: float
    risk: float
    signal: float
    timestamp: float
    source: str = "liquidity_cognition"
    market: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)


@dataclass
class MerrillClockEvent:
    """
    美林时钟事件
    
    当MerrillClock更新经济周期判断时发布
    """
    phase: str
    asset_allocation: Dict[str, float]
    timestamp: float
    source: str = "merrill_clock"
    market: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)