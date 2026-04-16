"""
认知事件定义 - 所有认知模块使用统一的 dataclass 事件

重构目标：
1. 删除 CognitiveEventType 枚举，改用事件类名路由
2. 删除 CognitiveSignalEvent 数据类，每个事件类型独立定义
3. 所有认知模块通过同一个事件总线 publish() 发布事件
4. 保留所有认知事件特性（去重窗口、重要性阈值、类型过滤）

使用方式：
    from deva.naja.events import get_event_bus
    from deva.naja.events.cognition_events import NarrativeUpdateEvent
    
    bus = get_event_bus()
    
    # 发布认知事件（和普通事件一样）
    event = NarrativeUpdateEvent(
        source="NarrativeTracker",
        narrative_id="new_energy_2026",
        narrative_type="block",
        summary="新能源政策加码",
        confidence=0.8,
        symbols=["000001", "300750"],
        strength_change=0.15,
        market="CN",
        importance=0.7
    )
    bus.publish(event)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# ============== 认知事件基础类 ==============

@dataclass
class BaseCognitiveEvent:
    """认知事件基类 - 包含所有认知事件共有的特性"""
    source: str = ""                    # 事件源（模块名）
    timestamp: float = field(default_factory=time.time)
    importance: float = 0.5             # 重要性阈值过滤（0-1）
    confidence: float = 0.5             # 置信度（0-1）
    market: Optional[str] = None        # 市场过滤（CN/US/HK）
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def event_type(self) -> str:
        """事件类型，用于总线路由 - 返回类名"""
        return self.__class__.__name__


# ============== 具体认知事件 ==============

@dataclass
class NarrativeUpdateEvent(BaseCognitiveEvent):
    """叙事更新事件 - 原 CognitiveEventType.NARRATIVE_UPDATE"""
    narrative_id: str = ""               # 叙事ID
    narrative_type: str = "block"        # block/global
    summary: str = ""                    # 更新摘要
    symbols: List[str] = field(default_factory=list)  # 相关股票
    strength_change: float = 0.0         # 强度变化（-1到1）
    new_strength: Optional[float] = None # 新强度值


@dataclass
class TimingNarrativeShiftEvent(BaseCognitiveEvent):
    """时机叙事切换事件 - 原 CognitiveEventType.TIMING_NARRATIVE_SHIFT"""
    narrative_id: str = ""
    new_regime: str = ""                 # 新阶段：accumulation/uptrend/distribution/downtrend
    old_regime: str = ""
    regime_strength: float = 0.5         # 新阶段的强度
    volatility_change: float = 0.0       # 波动率变化
    liquidity_change: float = 0.0        # 流动性变化


@dataclass
class BlockNarrativeUpdateEvent(BaseCognitiveEvent):
    """板块叙事更新 - 原 CognitiveEventType.BLOCK_NARRATIVE_UPDATE"""
    block_name: str = ""                 # 板块名称
    narrative_id: str = ""
    catalysts: List[str] = field(default_factory=list)  # 催化剂
    sentiment_change: float = 0.0        # 情绪变化
    momentum_score: float = 0.0          # 动量评分


@dataclass
class ResonanceDetectedEvent(BaseCognitiveEvent):
    """共振检测事件 - 原 CognitiveEventType.RESONANCE_DETECTED"""
    resonance_id: str = ""               # 共振ID
    resonance_type: str = ""             # price/volume/narrative/technical
    symbols: List[str] = field(default_factory=list)
    strength: float = 0.0                # 共振强度
    duration: float = 0.0                # 持续时间（秒）


@dataclass
class SupplyChainRiskEvent(BaseCognitiveEvent):
    """供应链风险事件 - 原 CognitiveEventType.SUPPLY_CHAIN_RISK"""
    risk_id: str = ""
    risk_type: str = ""                  # supply/demand/logistic/political
    severity: float = 0.0                # 严重程度（0-1）
    impacted_symbols: List[str] = field(default_factory=list)
    upstream_symbols: List[str] = field(default_factory=list)
    downstream_symbols: List[str] = field(default_factory=list)
    expected_impact: str = ""            # 预期影响


@dataclass
class PortfolioSignalEvent(BaseCognitiveEvent):
    """组合级信号事件 - 原 CognitiveEventType.PORTFOLIO_SIGNAL"""
    signal_type: str = ""                # allocation/risk/rotation
    target_allocation: Dict[str, float] = field(default_factory=dict)  # 符号→权重
    reason: str = ""
    confidence: float = 0.5


@dataclass
class RiskAlertEvent(BaseCognitiveEvent):
    """风险警报事件 - 原 CognitiveEventType.RISK_ALERT"""
    alert_id: str = ""
    alert_type: str = ""                 # market/position/liquidity/volatility
    level: str = "warning"               # warning/alert/critical
    symbols: List[str] = field(default_factory=list)
    description: str = ""
    suggested_action: str = ""


@dataclass
class CognitionResetEvent(BaseCognitiveEvent):
    """认知重置事件 - 原 CognitiveEventType.COGNITION_RESET"""
    reset_scope: str = "all"             # all/narratives/timing/resonance
    reason: str = ""
    new_epoch_id: str = ""


# ============== 事件工厂函数（简化创建） ==============

def create_narrative_update(
    source: str,
    narrative_id: str,
    narrative_type: str = "block",
    summary: str = "",
    confidence: float = 0.5,
    symbols: Optional[List[str]] = None,
    strength_change: float = 0.0,
    market: Optional[str] = None,
    importance: float = 0.5,
    **metadata
) -> NarrativeUpdateEvent:
    """创建叙事更新事件"""
    return NarrativeUpdateEvent(
        source=source,
        narrative_id=narrative_id,
        narrative_type=narrative_type,
        summary=summary,
        confidence=confidence,
        symbols=symbols or [],
        strength_change=strength_change,
        market=market,
        importance=importance,
        metadata=metadata
    )


def create_timing_shift(
    source: str,
    narrative_id: str,
    new_regime: str,
    old_regime: str = "",
    regime_strength: float = 0.5,
    volatility_change: float = 0.0,
    liquidity_change: float = 0.0,
    market: Optional[str] = None,
    importance: float = 0.5,
    **metadata
) -> TimingNarrativeShiftEvent:
    """创建时机叙事切换事件"""
    return TimingNarrativeShiftEvent(
        source=source,
        narrative_id=narrative_id,
        new_regime=new_regime,
        old_regime=old_regime,
        regime_strength=regime_strength,
        volatility_change=volatility_change,
        liquidity_change=liquidity_change,
        market=market,
        importance=importance,
        metadata=metadata
    )


def create_resonance_detected(
    source: str,
    resonance_id: str,
    resonance_type: str,
    symbols: List[str],
    strength: float,
    duration: float = 0.0,
    market: Optional[str] = None,
    importance: float = 0.5,
    **metadata
) -> ResonanceDetectedEvent:
    """创建共振检测事件"""
    return ResonanceDetectedEvent(
        source=source,
        resonance_id=resonance_id,
        resonance_type=resonance_type,
        symbols=symbols,
        strength=strength,
        duration=duration,
        market=market,
        importance=importance,
        metadata=metadata
    )


# ============== 事件类型映射（用于向后兼容） ==============

# 旧枚举值到新事件类的映射（临时兼容，可逐步删除）
EVENT_TYPE_MAPPING = {
    "narrative_update": NarrativeUpdateEvent,
    "timing_narrative_shift": TimingNarrativeShiftEvent,
    "block_narrative_update": BlockNarrativeUpdateEvent,
    "resonance_detected": ResonanceDetectedEvent,
    "supply_chain_risk": SupplyChainRiskEvent,
    "portfolio_signal": PortfolioSignalEvent,
    "risk_alert": RiskAlertEvent,
    "cognition_reset": CognitionResetEvent,
}