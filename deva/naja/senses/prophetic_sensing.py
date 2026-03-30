"""
ProphetSense - 天眼通预感知引擎

感知"正在酝酿"但尚未发生的机会

能力：
1. MomentumPrecipice: 动量即将衰竭的预兆
2. SentimentTransition: 情绪即将转换的预兆
3. FlowTaste: 资金流动的"味道"
4. VolatilitySurface: 波动率曲面异常

使用方式：
    prophet = ProphetSense()
    signal = prophet.sense(market_data, flow_data)
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

log = logging.getLogger(__name__)


class PresageType(Enum):
    """预兆类型"""
    MOMENTUM_EXHAUSTION = "momentum_exhaustion"
    SENTIMENT_REVERSAL = "sentiment_reversal"
    FLOW_REVERSAL = "flow_reversal"
    VOLATILITY_SPIKE = "volatility_spike"
    NARRATIVE_TURNING = "narrative_turning"
    NARRATIVE_DOMINANCE = "narrative_dominance"
    REGIME_SHIFT = "regime_shift"
    SECTOR_ROTATION = "sector_rotation"
    NONE = "none"


@dataclass
class ProphetSignal:
    """预感知信号"""
    presage_type: PresageType = PresageType.NONE
    intensity: float = 0.0
    horizon_seconds: int = 300
    confidence: float = 0.5
    symbol: Optional[str] = None
    reason: str = ""
    direction: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "presage_type": self.presage_type.value,
            "intensity": self.intensity,
            "horizon_seconds": self.horizon_seconds,
            "confidence": self.confidence,
            "symbol": self.symbol,
            "reason": self.reason,
            "direction": self.direction,
        }


class MomentumPrecipice:
    """
    动量悬崖预判

    检测动量即将衰竭的预兆：
    - 价格创新高但成交量萎缩
    - 动量指标背离
    - 涨跌家数比率下降
    """

    def __init__(self):
        self._price_history: Dict[str, deque] = {}
        self._volume_history: Dict[str, deque] = {}
        self._max_history = 20

    def detect(self, symbol: str, price: float, volume: float, price_change: float) -> Optional[ProphetSignal]:
        """
        检测动量衰竭预兆

        Args:
            symbol: 股票代码
            price: 当前价格
            volume: 当前成交量
            price_change: 价格变动百分比

        Returns:
            ProphetSignal 或 None
        """
        if symbol not in self._price_history:
            self._price_history[symbol] = deque(maxlen=self._max_history)
            self._volume_history[symbol] = deque(maxlen=self._max_history)

        self._price_history[symbol].append(price_change)
        self._volume_history[symbol].append(volume)

        if len(self._price_history[symbol]) < 10:
            return None

        recent_changes = list(self._price_history[symbol])[-5:]
        recent_volumes = list(self._volume_history[symbol])[-5:]

        avg_change = sum(recent_changes) / len(recent_changes)
        avg_volume = sum(recent_volumes) / len(recent_volumes)

        if avg_change > 1.0 and volume < avg_volume * 0.7:
            return ProphetSignal(
                presage_type=PresageType.MOMENTUM_EXHAUSTION,
                intensity=0.7,
                horizon_seconds=180,
                confidence=0.6,
                symbol=symbol,
                reason=f"价格创新高但成交量萎缩至{volume/avg_volume:.1%}",
                direction=-1
            )

        if len(recent_changes) >= 5:
            early_avg = sum(recent_changes[:3]) / 3
            late_avg = sum(recent_changes[-3:]) / 3
            if early_avg > late_avg * 1.5 and late_avg > 0:
                return ProphetSignal(
                    presage_type=PresageType.MOMENTUM_EXHAUSTION,
                    intensity=0.8,
                    horizon_seconds=120,
                    confidence=0.7,
                    symbol=symbol,
                    reason="动量持续衰减",
                    direction=-1
                )

        return None


class SentimentTransitionSense:
    """
    情绪转换预判

    检测情绪即将转换的预兆：
    - 涨跌家数比率变化
    - 板块内部分化
    - 连板股开板
    """

    def __init__(self):
        self._breadth_history: deque = deque(maxlen=20)
        self._sector_coherence_history: Dict[str, deque] = {}

    def detect(self, advancing: int, declining: int, sector_symbols: List[str] = None) -> Optional[ProphetSignal]:
        """
        检测情绪转换预兆

        Args:
            advancing: 上涨家数
            declining: 下跌家数
            sector_symbols: 板块内股票列表

        Returns:
            ProphetSignal 或 None
        """
        total = advancing + declining
        if total == 0:
            return None

        breadth_ratio = (advancing - declining) / total

        self._breadth_history.append(breadth_ratio)

        if len(self._breadth_history) < 5:
            return None

        recent = list(self._breadth_history)[-3:]
        trend = recent[-1] - recent[0]

        if trend < -0.2 and recent[-1] < 0:
            return ProphetSignal(
                presage_type=PresageType.SENTIMENT_REVERSAL,
                intensity=abs(recent[-1]),
                horizon_seconds=300,
                confidence=0.65,
                reason="市场情绪即将由多转空",
                direction=-1
            )

        if trend > 0.3 and recent[-1] > 0.3:
            return ProphetSignal(
                presage_type=PresageType.SENTIMENT_REVERSAL,
                intensity=recent[-1],
                horizon_seconds=300,
                confidence=0.65,
                reason="市场情绪即将由空转多",
                direction=1
            )

        return None


class FlowTasteSense:
    """
    资金流向"味道"

    感知资金流动的深层含义，不只是净流入/流出：
    - 主力意图（大单vs散户）
    - 板块轮动味道
    - 情绪拐点味道
    """

    def __init__(self):
        self._flow_history: deque = deque(maxlen=30)
        self._main_flow_history: deque = deque(maxlen=30)
        self._retail_flow_history: deque = deque(maxlen=30)

    def detect(
        self,
        main_flow: float,
        retail_flow: float,
        total_flow: float
    ) -> Optional[ProphetSignal]:
        """
        检测资金流向味道

        Args:
            main_flow: 主力资金净流入
            retail_flow: 散户资金净流入
            total_flow: 总资金净流入

        Returns:
            ProphetSignal 或 None
        """
        self._flow_history.append(total_flow)
        self._main_flow_history.append(main_flow)
        self._retail_flow_history.append(retail_flow)

        if len(self._flow_history) < 10:
            return None

        recent_main = list(self._main_flow_history)[-5:]
        recent_retail = list(self._retail_flow_history)[-5:]

        main_avg = sum(recent_main) / len(recent_main)
        retail_avg = sum(recent_retail) / len(recent_retail)

        if main_avg > 0 and retail_avg < -main_avg * 0.5:
            return ProphetSignal(
                presage_type=PresageType.FLOW_REVERSAL,
                intensity=0.75,
                horizon_seconds=240,
                confidence=0.7,
                reason="主力流入但散户大幅流出，可能见顶",
                direction=-1
            )

        if main_avg < 0 and retail_avg > abs(main_avg) * 0.8:
            return ProphetSignal(
                presage_type=PresageType.FLOW_REVERSAL,
                intensity=0.6,
                horizon_seconds=300,
                confidence=0.6,
                reason="主力流出但散户接盘，可能见底",
                direction=1
            )

        return None


class VolatilitySurfaceSense:
    """
    波动率曲面感知

    检测隐含波动率异常：
    - IV明显高于HV（隐含恐慌）
    - Skew异常（看涨/看跌期权需求异常）
    - 近期期权异常（事件预期）
    """

    def __init__(self):
        self._iv_history: Dict[str, deque] = {}
        self._hv_history: Dict[str, deque] = {}
        self._skew_history: Dict[str, deque] = {}

    def detect(
        self,
        symbol: str,
        implied_volatility: float,
        historical_volatility: float,
        skew: float = 0.0
    ) -> Optional[ProphetSignal]:
        """
        检测波动率异常

        Args:
            symbol: 股票代码
            implied_volatility: 隐含波动率
            historical_volatility: 历史波动率
            skew: 波动率偏度（正=看涨期权更贵，负=看跌期权更贵）

        Returns:
            ProphetSignal 或 None
        """
        if symbol not in self._iv_history:
            self._iv_history[symbol] = deque(maxlen=20)
            self._hv_history[symbol] = deque(maxlen=20)
            self._skew_history[symbol] = deque(maxlen=20)

        self._iv_history[symbol].append(implied_volatility)
        self._hv_history[symbol].append(historical_volatility)
        self._skew_history[symbol].append(skew)

        if len(self._iv_history[symbol]) < 5:
            return None

        iv_avg = sum(self._iv_history[symbol]) / len(self._iv_history[symbol])
        hv_avg = sum(self._hv_history[symbol]) / len(self._hv_history[symbol])

        iv_ratio = implied_volatility / iv_avg if iv_avg > 0 else 1.0
        hv_ratio = historical_volatility / hv_avg if hv_avg > 0 else 1.0

        if iv_ratio > 1.3 and hv_ratio < 1.1:
            return ProphetSignal(
                presage_type=PresageType.VOLATILITY_SPIKE,
                intensity=min(iv_ratio - 1.0, 1.0),
                horizon_seconds=600,
                confidence=0.7,
                symbol=symbol,
                reason=f"隐含波动率异常偏高({iv_ratio:.1%})，可能事件驱动",
                direction=0
            )

        recent_skew = list(self._skew_history[symbol])[-3:]
        skew_trend = recent_skew[-1] - recent_skew[0]

        if skew_trend > 0.1:
            return ProphetSignal(
                presage_type=PresageType.SENTIMENT_REVERSAL,
                intensity=abs(skew_trend),
                horizon_seconds=300,
                confidence=0.65,
                symbol=symbol,
                reason="看涨期权需求增加，可能情绪转多",
                direction=1
            )

        return None


class ProphetSense:
    """
    天眼通 - 预感知引擎

    综合各种预兆信号，输出统一的预感知结果
    """

    def __init__(self):
        self.momentum = MomentumPrecipice()
        self.sentiment = SentimentTransitionSense()
        self.flow_taste = FlowTasteSense()
        self.volatility = VolatilitySurfaceSense()

        self._last_signal_time = 0.0
        self._min_interval = 10.0
        self._recent_signals: List[ProphetSignal] = []

    def sense(
        self,
        market_data: Optional[Dict[str, Any]] = None,
        flow_data: Optional[Dict[str, Any]] = None,
        options_data: Optional[Dict[str, Any]] = None,
        narrative_data: Optional[Dict[str, Any]] = None
    ) -> Optional[ProphetSignal]:
        """
        执行预感知

        Args:
            market_data: 市场数据
                - symbol: 股票代码
                - price: 当前价格
                - volume: 成交量
                - price_change: 价格变动百分比
                - advancing: 上涨家数
                - declining: 下跌家数
            flow_data: 资金流向数据
                - main_flow: 主力资金净流入
                - retail_flow: 散户资金净流入
                - total_flow: 总资金净流入
            options_data: 期权数据
                - symbol: 股票代码
                - implied_volatility: 隐含波动率
                - historical_volatility: 历史波动率
                - skew: 波动率偏度
            narrative_data: 叙事数据（新增）
                - narratives: List[str] 当前叙事列表
                - sector: str 板块名称
                - trend: str 叙事趋势 "emerging"|"growing"|"fading"
                - intensity: float 叙事强度 0-1
        """
        current_time = time.time()
        if current_time - self._last_signal_time < self._min_interval:
            return None

        signals = []

        if market_data:
            symbol = market_data.get('symbol', 'market')

            if 'price' in market_data and 'volume' in market_data:
                sig = self.momentum.detect(
                    symbol=symbol,
                    price=market_data.get('price', 0),
                    volume=market_data.get('volume', 0),
                    price_change=market_data.get('price_change', 0)
                )
                if sig:
                    signals.append(sig)

            if 'advancing' in market_data and 'declining' in market_data:
                sig = self.sentiment.detect(
                    advancing=market_data.get('advancing', 0),
                    declining=market_data.get('declining', 0)
                )
                if sig:
                    signals.append(sig)

        if flow_data:
            sig = self.flow_taste.detect(
                main_flow=flow_data.get('main_flow', 0),
                retail_flow=flow_data.get('retail_flow', 0),
                total_flow=flow_data.get('total_flow', 0)
            )
            if sig:
                signals.append(sig)

        if options_data:
            sig = self.volatility.detect(
                symbol=options_data.get('symbol', ''),
                implied_volatility=options_data.get('implied_volatility', 0),
                historical_volatility=options_data.get('historical_volatility', 0),
                skew=options_data.get('skew', 0)
            )
            if sig:
                signals.append(sig)

        if narrative_data:
            sig = self._detect_narrative_signal(narrative_data)
            if sig:
                signals.append(sig)

        if not signals:
            return None

        best_signal = max(signals, key=lambda s: s.intensity * s.confidence)
        self._recent_signals.append(best_signal)
        if len(self._recent_signals) > 10:
            self._recent_signals.pop(0)

        self._last_signal_time = current_time

        return best_signal

    def get_recent_signals(self) -> List[ProphetSignal]:
        """获取最近的预兆信号"""
        return self._recent_signals.copy()

    def _detect_narrative_signal(self, narrative_data: Dict[str, Any]) -> Optional[ProphetSignal]:
        """
        检测叙事转折信号

        叙事生命周期：emerging → growing → fading

        - emerging → growing：叙事兴起，可能推动市场
        - growing → fading：叙事衰退，上涨动能减弱
        - 新兴叙事突然被压制：可能反转
        """
        narratives = narrative_data.get("narratives", [])
        trend = narrative_data.get("trend", "growing")
        intensity = narrative_data.get("intensity", 0.5)
        sector = narrative_data.get("sector", "")

        if not narratives:
            return None

        recent_narratives_count = len(narratives)
        high_intensity = intensity > 0.7

        if trend == "fading" and high_intensity:
            return ProphetSignal(
                presage_type=PresageType.NARRATIVE_TURNING,
                intensity=intensity * 0.8,
                horizon_seconds=600,
                confidence=0.7,
                reason=f"叙事衰退但强度仍高({sector})，警惕反转",
                direction=-1
            )

        if trend == "emerging" and high_intensity:
            return ProphetSignal(
                presage_type=PresageType.NARRATIVE_TURNING,
                intensity=intensity * 0.9,
                horizon_seconds=900,
                confidence=0.75,
                reason=f"新叙事兴起({sector})，动能强劲",
                direction=1
            )

        if recent_narratives_count >= 5 and high_intensity:
            return ProphetSignal(
                presage_type=PresageType.NARRATIVE_DOMINANCE,
                intensity=intensity * 0.6,
                horizon_seconds=1200,
                confidence=0.65,
                reason=f"多叙事并行({sector})，市场分歧加大",
                direction=0
            )

        return None

    def get_state(self) -> Dict[str, Any]:
        """获取天眼通状态"""
        return {
            "recent_signals_count": len(self._recent_signals),
            "last_signal": self._recent_signals[-1].to_dict() if self._recent_signals else None,
        }
