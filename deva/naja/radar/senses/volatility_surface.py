"""
VolatilitySurfaceSense - 波动率曲面感知

"天眼通"的最后一环：感知市场即将发生极端情况

核心能力：
1. IVSurfaceAnalyzer: 隐含波动率曲面分析
2. Volatility Regime Detector: 波动率状态检测
3. BlackScholesImpliedVol: 从期权价格反推IV
4. VolatilitySignalGenerator: 波动率信号生成
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)


class VolatilityRegime(Enum):
    """波动率状态"""
    LOW_STABLE = "low_stable"         # 低位稳定
    LOW_VOLATILE = "low_volatile"     # 低位波动
    HIGH_STABLE = "high_stable"       # 高位稳定
    HIGH_VOLATILE = "high_volatile"   # 高位波动
    SPIKE = "spike"                 # 波动率飙升
    CRASH = "crash"                 # 波动率暴跌
    UNKNOWN = "unknown"


class VolatilitySignal(Enum):
    """波动率信号"""
    IV_LOW = "iv_low"               # IV偏低，买入期权机会
    IV_HIGH = "iv_high"             # IV偏高，卖出期权机会
    IV_SKEW = "iv_skew"             # IV偏度异常
    TERM_STRUCTURE = "term_structure" # 期限结构异常
    REGIME_CHANGE = "regime_change"   # 状态转换预警
    SPIKE_WARNING = "spike_warning"   # 波动率飙升预警


@dataclass
class VolatilitySurface:
    """波动率曲面"""
    symbol: str
    current_iv: float                # 当前隐含波动率
    iv_skew: float                  # IV偏度
    term_structure: float            # 期限结构 (短期/长期)
    regime: VolatilityRegime
    regime_confidence: float
    historical_vol: float            # 历史波动率
    iv_hv_ratio: float              # IV/HV比率
    timestamp: float


@dataclass
class VolatilityAlert:
    """波动率警报"""
    signal: VolatilitySignal
    intensity: float                 # 强度 [0, 1]
    confidence: float               # 置信度
    description: str
    opportunity: str                # 建议操作
    horizon: str                   # 预期时间窗口


class IVSkewAnalyzer:
    """
    IV偏度分析器

    分析期权隐含波动率的偏斜程度
    """

    def __init__(self):
        self._skew_history: List[float] = []

    def calculate_skew(
        self,
        otm_put_iv: float,
        atm_iv: float,
        otm_call_iv: float
    ) -> float:
        """
        计算IV偏度

        Skew = (OTM Put IV - ATM IV) / ATM IV

        正常市场：Skew > 0 (puts more expensive than calls)
        恐慌市场：Skew >> 0
        乐观市场：Skew ≈ 0 or < 0
        """
        if atm_iv <= 0:
            return 0

        skew = (otm_put_iv - atm_iv) / atm_iv

        self._skew_history.append(skew)
        if len(self._skew_history) > 100:
            self._skew_history.pop(0)

        return skew

    def detect_skew_anomaly(self, current_skew: float) -> Optional[VolatilityAlert]:
        """检测偏度异常"""
        if len(self._skew_history) < 10:
            return None

        avg_skew = sum(self._skew_history[-10:]) / 10
        std_skew = (sum((s - avg_skew) ** 2 for s in self._skew_history[-10:]) / 10) ** 0.5

        if std_skew <= 0:
            return None

        z_score = (current_skew - avg_skew) / std_skew

        if z_score > 2:
            return VolatilityAlert(
                signal=VolatilitySignal.IV_SKEW,
                intensity=min(1.0, abs(z_score) / 4),
                confidence=0.8,
                description=f"IV偏度异常偏高: {current_skew:.2%} (均值: {avg_skew:.2%})",
                opportunity="市场可能过度恐慌，关注反转机会",
                horizon="1-5天"
            )

        return None


class TermStructureAnalyzer:
    """
    期限结构分析器

    分析不同期限期权波动率的关系
    """

    def __init__(self):
        self._term_history: List[float] = []

    def calculate_term_structure(
        self,
        short_term_iv: float,
        mid_term_iv: float,
        long_term_iv: float
    ) -> float:
        """
        计算期限结构

        Term Structure = (Short IV / Long IV)

        正常市场：Term Structure < 1 (期限曲线向上)
        反转市场：Term Structure > 1 (期限曲线向下)
        """
        if long_term_iv <= 0:
            return 1.0

        term_structure = short_term_iv / long_term_iv

        self._term_history.append(term_structure)
        if len(self._term_history) > 100:
            self._term_history.pop(0)

        return term_structure

    def detect_term_anomaly(self, current_term: float) -> Optional[VolatilityAlert]:
        """检测期限结构异常"""
        if len(self._term_history) < 10:
            return None

        avg_term = sum(self._term_history[-10:]) / 10

        if abs(current_term - avg_term) > 0.3:
            return VolatilityAlert(
                signal=VolatilitySignal.TERM_STRUCTURE,
                intensity=min(1.0, abs(current_term - avg_term)),
                confidence=0.75,
                description=f"期限结构异常: 当前 {current_term:.2f}, 均值 {avg_term:.2f}",
                opportunity="关注波动率期限交易机会" if current_term < avg_term else "市场预期稳定",
                horizon="1-4周"
            )

        return None


class VolatilityRegimeDetector:
    """
    波动率状态检测器

    检测当前波动率所处的状态
    """

    def __init__(self):
        self._regime_history: List[VolatilityRegime] = []

    def detect_regime(
        self,
        current_iv: float,
        historical_vol: float,
        iv_change: float
    ) -> VolatilityRegime:
        """
        检测波动率状态

        状态判断：
        - 低位稳定：IV < 15% and 变化小
        - 低位波动：IV < 15% and 变化大
        - 高位稳定：IV > 30% and 变化小
        - 高位波动：IV > 30% and 变化大
        - 飙升：IV 突然大幅上升
        - 暴跌：IV 突然大幅下降
        """
        if current_iv <= 0:
            return VolatilityRegime.UNKNOWN

        if iv_change > 0.3:
            regime = VolatilityRegime.SPIKE
        elif iv_change < -0.3:
            regime = VolatilityRegime.CRASH
        elif current_iv < 0.15:
            regime = VolatilityRegime.LOW_STABLE if abs(iv_change) < 0.1 else VolatilityRegime.LOW_VOLATILE
        elif current_iv > 0.30:
            regime = VolatilityRegime.HIGH_STABLE if abs(iv_change) < 0.1 else VolatilityRegime.HIGH_VOLATILE
        else:
            regime = VolatilityRegime.LOW_VOLATILE if current_iv < 0.22 else VolatilityRegime.HIGH_VOLATILE

        self._regime_history.append(regime)
        if len(self._regime_history) > 50:
            self._regime_history.pop(0)

        return regime

    def predict_regime_change(self) -> Optional[VolatilityAlert]:
        """预测状态转换"""
        if len(self._regime_history) < 10:
            return None

        recent = self._regime_history[-5:]
        previous = self._regime_history[-10:-5]

        recent_stable = all(r == recent[0] for r in recent)
        all_same_prev = all(r == previous[0] for r in previous)

        if recent_stable and not all_same_prev:
            prev_regime = previous[0]
            curr_regime = recent[0]

            if prev_regime != curr_regime:
                return VolatilityAlert(
                    signal=VolatilitySignal.REGIME_CHANGE,
                    intensity=0.7,
                    confidence=0.8,
                    description=f"波动率状态即将转换: {prev_regime.value} → {curr_regime.value}",
                    opportunity="调整期权策略以适应新状态",
                    horizon="近期"
                )

        return None


class IVSurfaceAnalyzer:
    """
    隐含波动率曲面分析器

    综合分析IV曲面各维度
    """

    def __init__(self):
        self.skew_analyzer = IVSkewAnalyzer()
        self.term_analyzer = TermStructureAnalyzer()
        self.regime_detector = VolatilityRegimeDetector()

    def analyze(
        self,
        symbol: str,
        atm_iv: float,
        otm_put_iv: float,
        otm_call_iv: float,
        short_term_iv: float,
        long_term_iv: float,
        historical_vol: float,
        iv_history: List[float]
    ) -> VolatilitySurface:
        """分析波动率曲面"""
        skew = self.skew_analyzer.calculate_skew(otm_put_iv, atm_iv, otm_call_iv)
        term_structure = self.term_analyzer.calculate_term_structure(short_term_iv, atm_iv, long_term_iv)

        iv_change = 0
        if len(iv_history) >= 2 and iv_history[-2] > 0:
            iv_change = (atm_iv - iv_history[-2]) / iv_history[-2]

        regime = self.regime_detector.detect_regime(atm_iv, historical_vol, iv_change)

        regime_confidence = self._calculate_regime_confidence(regime, iv_history)

        return VolatilitySurface(
            symbol=symbol,
            current_iv=atm_iv,
            iv_skew=skew,
            term_structure=term_structure,
            regime=regime,
            regime_confidence=regime_confidence,
            historical_vol=historical_vol,
            iv_hv_ratio=atm_iv / historical_vol if historical_vol > 0 else 1.0,
            timestamp=0
        )

    def _calculate_regime_confidence(self, regime: VolatilityRegime, history: List[float]) -> float:
        """计算状态置信度"""
        if len(history) < 5:
            return 0.5

        recent_std = (sum((v - sum(history[-5:])/5)**2 for v in history[-5:]) / 5) ** 0.5
        avg_vol = sum(history[-5:]) / 5

        if avg_vol <= 0:
            return 0.5

        cv = recent_std / avg_vol

        if regime in [VolatilityRegime.SPIKE, VolatilityRegime.CRASH]:
            return min(1.0, cv * 3)
        elif regime in [VolatilityRegime.LOW_STABLE, VolatilityRegime.HIGH_STABLE]:
            return max(0.3, 1.0 - cv)
        else:
            return 0.6


class VolatilitySignalGenerator:
    """
    波动率信号生成器

    从波动率曲面生成交易信号
    """

    def __init__(self):
        self._surface_history: List[VolatilitySurface] = []

    def generate_signals(self, surface: VolatilitySurface) -> List[VolatilityAlert]:
        """生成波动率信号"""
        alerts = []

        if surface.iv_hv_ratio < 0.7:
            alerts.append(VolatilityAlert(
                signal=VolatilitySignal.IV_LOW,
                intensity=1.0 - surface.iv_hv_ratio,
                confidence=0.8,
                description=f"IV偏低: {surface.current_iv:.1%} vs HV {surface.historical_vol:.1%}",
                opportunity="买入期权（IV修复机会）",
                horizon="1-4周"
            ))

        elif surface.iv_hv_ratio > 1.5:
            alerts.append(VolatilityAlert(
                signal=VolatilitySignal.IV_HIGH,
                intensity=min(1.0, surface.iv_hv_ratio - 1.0),
                confidence=0.8,
                description=f"IV偏高: {surface.current_iv:.1%} vs HV {surface.historical_vol:.1%}",
                opportunity="卖出期权（IV压缩机会）",
                horizon="1-4周"
            ))

        if surface.regime == VolatilityRegime.SPIKE:
            alerts.append(VolatilityAlert(
                signal=VolatilitySignal.SPIKE_WARNING,
                intensity=0.9,
                confidence=surface.regime_confidence,
                description=f"波动率飙升: {surface.current_iv:.1%}",
                opportunity="买入Vega对冲或观望",
                horizon="立即"
            ))

        return alerts

    def add_surface(self, surface: VolatilitySurface):
        """添加曲面历史"""
        self._surface_history.append(surface)
        if len(self._surface_history) > 100:
            self._surface_history.pop(0)


class VolatilitySurfaceSense:
    """
    波动率曲面感知（天眼通的最后一环）

    感知市场即将发生的极端情况
    """

    def __init__(self):
        self.surface_analyzer = IVSurfaceAnalyzer()
        self.signal_generator = VolatilitySignalGenerator()
        self._last_surface: Optional[VolatilitySurface] = None

    def sense(
        self,
        market_data: Dict[str, Any],
        options_data: Optional[Dict[str, Any]] = None
    ) -> Optional[VolatilityAlert]:
        """
        感知波动率曲面

        Args:
            market_data: 市场数据
            options_data: 期权数据（如果有）

        Returns:
            波动率警报，如果有的话
        """
        if options_data is None:
            options_data = self._estimate_from_market_data(market_data)

        surface = self.surface_analyzer.analyze(
            symbol=options_data.get("symbol", "000001"),
            atm_iv=options_data.get("atm_iv", 0.25),
            otm_put_iv=options_data.get("otm_put_iv", 0.28),
            otm_call_iv=options_data.get("otm_call_iv", 0.23),
            short_term_iv=options_data.get("short_term_iv", 0.22),
            long_term_iv=options_data.get("long_term_iv", 0.28),
            historical_vol=options_data.get("historical_vol", 0.20),
            iv_history=options_data.get("iv_history", [0.25, 0.24, 0.26, 0.25, 0.27])
        )

        self._last_surface = surface
        self.signal_generator.add_surface(surface)

        alerts = self.signal_generator.generate_signals(surface)

        if alerts:
            return max(alerts, key=lambda a: a.intensity)

        return None

    def _estimate_from_market_data(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """从市场数据估算波动率信息"""
        price = market_data.get("price", 10.0)
        change = market_data.get("price_change", 0)

        estimated_iv = abs(change / price) * 20 if abs(change / price) > 0.001 else 0.20

        return {
            "symbol": market_data.get("symbol", "000001"),
            "atm_iv": estimated_iv,
            "otm_put_iv": estimated_iv * 1.1,
            "otm_call_iv": estimated_iv * 0.95,
            "short_term_iv": estimated_iv,
            "long_term_iv": estimated_iv * 1.15,
            "historical_vol": market_data.get("volatility", 0.18),
            "iv_history": market_data.get("iv_history", [estimated_iv] * 5)
        }

    def get_current_surface(self) -> Optional[VolatilitySurface]:
        """获取当前曲面"""
        return self._last_surface

    def get_regime(self) -> Optional[VolatilityRegime]:
        """获取当前波动率状态"""
        if self._last_surface:
            return self._last_surface.regime
        return None