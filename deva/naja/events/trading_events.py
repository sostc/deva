"""
Trading Events - 交易信号与决策事件

核心流程事件（新架构）：
1. StrategySignalEvent - 热点策略产出信号（买入/卖出/观望）
2. TradeDecisionEvent - TradingCenter 审批结果（批准/拒绝）

信号链路（目标）：
市场热点策略 → StrategySignalEvent → NajaEventBus → TradingCenter 订阅处理
TradingCenter（Manas + FP Mind + Alaya）→ TradeDecisionEvent → NajaEventBus → Bandit 执行
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import time


class SignalDirection(Enum):
    """信号方向"""
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"  # 观望，不操作
    
    @classmethod
    def from_str(cls, value: str) -> 'SignalDirection':
        """从字符串转换"""
        value = value.lower()
        if value in {'buy', '买入', 'long', '做多'}:
            return cls.BUY
        elif value in {'sell', '卖出', 'short', '做空'}:
            return cls.SELL
        else:
            return cls.NEUTRAL


class DecisionResult(Enum):
    """交易决策结果"""
    APPROVED = "approved"      # 批准执行
    REJECTED = "rejected"      # 拒绝执行
    MODIFIED = "modified"      # 修改后执行（如调整持仓比例）
    DEFERRED = "deferred"      # 延期执行，等待更好时机
    
    @classmethod
    def from_str(cls, value: str) -> 'DecisionResult':
        """从字符串转换"""
        value = value.lower()
        for member in cls:
            if member.value == value:
                return member
        return cls.REJECTED  # 默认拒绝


@dataclass
class StrategySignalEvent:
    """
    策略信号事件
    
    市场热点策略（或其他策略）产出的原始信号。
    此事件由策略模块发布到 NajaEventBus，供 TradingCenter 订阅处理。
    """
    # 核心信号
    symbol: str                    # 股票代码，如 "AAPL.US"
    direction: SignalDirection    # 信号方向：买入/卖出/观望
    confidence: float             # 策略置信度 0.0-1.0
    
    # 策略信息
    strategy_name: str            # 策略名称，如 "BlockRotationHunter", "MomentumSurgeTracker"
    signal_type: str              # 信号类型，如 "rotation", "momentum", "pattern"
    
    # 市场状态
    current_price: float          # 当前价格
    price_change_pct: float       # 价格变化百分比
    volume_ratio: float = 1.0     # 成交量相对于均值的倍数
    
    # 上下文
    narrative_tags: List[str] = field(default_factory=list)  # 相关叙事标签
    block_name: Optional[str] = None  # 所属板块/题材
    timeframe: str = "intraday"   # 时间框架: "intraday", "daily", "weekly"
    
    # 元数据
    timestamp: float = field(default_factory=time.time)
    position_size: float = 0.01   # 建议持仓比例（0.01=1%）
    stop_loss_pct: Optional[float] = None  # 建议止损百分比
    take_profit_pct: Optional[float] = None  # 建议止盈百分比
    
    # 额外字段（用于策略传递内部信息）
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)
    
    @property
    def is_buy(self) -> bool:
        return self.direction == SignalDirection.BUY
    
    @property
    def is_sell(self) -> bool:
        return self.direction == SignalDirection.SELL
    
    @property
    def is_neutral(self) -> bool:
        return self.direction == SignalDirection.NEUTRAL
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（便于JSON序列化）"""
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "confidence": self.confidence,
            "strategy_name": self.strategy_name,
            "signal_type": self.signal_type,
            "current_price": self.current_price,
            "price_change_pct": self.price_change_pct,
            "volume_ratio": self.volume_ratio,
            "narrative_tags": self.narrative_tags,
            "block_name": self.block_name,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "position_size": self.position_size,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "metadata": self.metadata,
            "_type": "StrategySignalEvent"
        }


@dataclass
class TradeDecisionEvent:
    """
    交易决策事件
    
    TradingCenter 处理完 StrategySignalEvent 后的审批结果。
    此事件由 TradingCenter 发布到 NajaEventBus，供 Bandit 订阅执行。
    """
    # 核心决策
    signal_event: StrategySignalEvent  # 原始信号事件
    decision: DecisionResult          # 决策结果：批准/拒绝/修改/延期
    approval_score: float             # 审批分数 0.0-1.0（各子系统综合评分）
    
    # 决策详情（当 decision == APPROVED 或 MODIFIED 时有值）
    approved_symbol: Optional[str] = None      # 批准的股票代码（可能与原始不同）
    approved_direction: Optional[SignalDirection] = None  # 批准的方向
    position_size: Optional[float] = None      # 最终批准的持仓比例
    entry_price: Optional[float] = None        # 建议入场价格
    stop_loss_price: Optional[float] = None    # 止损价
    take_profit_price: Optional[float] = None  # 止盈价
    
    # 决策理由
    reason: str = ""                          # 决策理由文本
    subsystems_opinions: Dict[str, Dict] = field(default_factory=dict)  # 各子系统意见
    # 例如: {"manas_engine": {"score": 0.8, "reason": "叙事共振"}, ...}
    
    # 元数据
    timestamp: float = field(default_factory=time.time)
    processing_time_ms: float = 0.0           # 处理耗时（毫秒）
    
    # 额外字段
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)
    
    @property
    def is_approved(self) -> bool:
        return self.decision in {DecisionResult.APPROVED, DecisionResult.MODIFIED}
    
    @property
    def is_rejected(self) -> bool:
        return self.decision == DecisionResult.REJECTED
    
    @property
    def is_deferred(self) -> bool:
        return self.decision == DecisionResult.DEFERRED
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（便于JSON序列化）"""
        return {
            "signal_event": self.signal_event.to_dict(),
            "decision": self.decision.value,
            "approval_score": self.approval_score,
            "approved_symbol": self.approved_symbol,
            "approved_direction": self.approved_direction.value if self.approved_direction else None,
            "position_size": self.position_size,
            "entry_price": self.entry_price,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "reason": self.reason,
            "subsystems_opinions": self.subsystems_opinions,
            "timestamp": self.timestamp,
            "processing_time_ms": self.processing_time_ms,
            "metadata": self.metadata,
            "_type": "TradeDecisionEvent"
        }