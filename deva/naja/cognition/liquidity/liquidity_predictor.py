"""
LiquidityPredictor - 流动性预测系统

从 radar/global_market_scanner.py 迁移到 cognition 层。
本模块属于认知/推理层职责，负责：
1. 基于全球市场信号，预测对各目标市场的流动性影响
2. 验证预测是否正确，动态调整/解除限制
3. 检测行情-舆论信号共振
4. 预测主题跨市场扩散

原始位置: radar/global_market_scanner.py (GlobalMarketScanner 类的流动性预测方法)
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

import numpy as np

log = logging.getLogger(__name__)


class LiquiditySignalType(Enum):
    """
    流动性信号类型枚举

    用于标识不同市场的流动性预测目标
    注意：这里定义的是 Attention 系统内部使用的市场标识
    与 MarketType（交易时间配置）不同
    """
    CHINA_A = "china_a"       # A股
    HONG_KONG = "hk"          # 港股
    US = "us"                 # 美股
    FUTURES = "futures"       # 期货
    CRYPTO = "crypto"         # 加密货币


@dataclass
class LiquidityPrediction:
    """
    流动性预测

    表示基于某些信号，对某个目标市场的流动性预测

    属性:
        target_market: 预测目标市场
        source_signals: 信号来源描述
        signal: 预测值 0-1 (< 0.4 紧张, > 0.6 宽松)
        confidence: 置信度 0-1
        timestamp: 预测时间
        valid_until: 预测有效期（秒）
        adjustment: 调整指令
    """
    target_market: LiquiditySignalType
    source_signals: List[str]
    signal: float
    confidence: float
    timestamp: float
    valid_until: float
    is_priced: bool = False
    priced_reason: str = ""
    priced_at_open: bool = False
    adjustment: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LiquidityVerification:
    """
    流动性验证

    用于验证预测是否正确

    属性:
        target_market: 目标市场
        actual_signals: 实际信号列表
        expected_signal: 预期信号
        verification_count: 验证次数
        verified: 是否已验证
        should_relax: 是否应该解除限制
    """
    target_market: LiquiditySignalType
    actual_signals: List[float] = field(default_factory=list)
    expected_signal: float = 0.5
    verification_count: int = 0
    verified: bool = False
    should_relax: bool = False

class LiquidityPredictor:
    """
    流动性预测器

    从 GlobalMarketScanner 迁移而来的流动性预测系统。
    独立于感知层，作为认知层的一部分运行。

    功能:
    1. 基于源市场信号，预测对目标市场的流动性影响
    2. 验证预测正确性，动态解除限制
    3. 检测行情-舆论信号共振
    4. 预测主题跨市场扩散
    """

    def __init__(self, session_manager=None):
        """
        初始化流动性预测器

        Args:
            session_manager: MarketSessionManager 实例，用于获取交易时段信息。
                           如果为 None，会延迟从 radar 层获取。
        """
        self._session_manager = session_manager
        self._narrative_signal = 0.0
        self._last_resonance = None
        self._topic_heat: Dict[str, deque] = {}
        self._topic_predictions: Dict[str, Dict] = {}
        self._last_market_data: Dict[str, Any] = {}
        self._init_liquidity_system()

    @property
    def session_manager(self):
        if self._session_manager is None:
            try:
                from deva.naja.radar.global_market_config import MarketSessionManager
                self._session_manager = MarketSessionManager()
            except ImportError:
                log.warning("[LiquidityPredictor] 无法获取 MarketSessionManager")
        return self._session_manager

    def update_market_data(self, market_id: str, data):
        """
        更新市场数据（由外部调用者提供）

        Args:
            market_id: 市场标识
            data: MarketData 对象或 dict
        """
        self._last_market_data[market_id] = data

    def update_market_data_from_scanner(self, scanner_data: Dict[str, Any]):
        """
        从 GlobalMarketScanner 的 _last_market_data 批量同步数据

        Args:
            scanner_data: GlobalMarketScanner._last_market_data 字典
        """
        if scanner_data:
            self._last_market_data.update(scanner_data)

    def _init_liquidity_system(self):
        """初始化流动性预测系统"""
        self._liquidity_predictions: Dict[LiquiditySignalType, LiquidityPrediction] = {}
        self._latest_data: Dict[str, Any] = {}
        self._liquidity_verifications: Dict[LiquiditySignalType, LiquidityVerification] = {}
        self._liquidity_history: Dict[LiquiditySignalType, deque] = {
            lt: deque(maxlen=20) for lt in LiquiditySignalType
        }
        self._market_influences = {
            LiquiditySignalType.CHINA_A: [LiquiditySignalType.HONG_KONG, LiquiditySignalType.US],
            LiquiditySignalType.HONG_KONG: [LiquiditySignalType.CHINA_A, LiquiditySignalType.US],
            LiquiditySignalType.US: [LiquiditySignalType.CHINA_A, LiquiditySignalType.HONG_KONG],
            LiquiditySignalType.FUTURES: [LiquiditySignalType.CHINA_A, LiquiditySignalType.US],
        }
        self._transmission_probabilities = {
            (LiquiditySignalType.CHINA_A, LiquiditySignalType.HONG_KONG): 0.7,
            (LiquiditySignalType.CHINA_A, LiquiditySignalType.US): 0.3,
            (LiquiditySignalType.US, LiquiditySignalType.CHINA_A): 0.5,
            (LiquiditySignalType.US, LiquiditySignalType.HONG_KONG): 0.8,
            (LiquiditySignalType.HONG_KONG, LiquiditySignalType.CHINA_A): 0.6,
            (LiquiditySignalType.HONG_KONG, LiquiditySignalType.US): 0.4,
            (LiquiditySignalType.FUTURES, LiquiditySignalType.CHINA_A): 0.6,
            (LiquiditySignalType.FUTURES, LiquiditySignalType.US): 0.5,
        }
        self._liquidity_initialized = True

    def _get_dynamic_valid_until(self, target: LiquiditySignalType) -> float:
        """
        动态计算预测有效期
        - 市场交易中：有效期 = 当前交易时段结束时间
        - 市场未开盘：有效期 = 下一个交易时段结束时间
        - 市场已收盘：有效期 = 明天交易时段结束时间
        """
        market_id_map = {
            LiquiditySignalType.CHINA_A: "china_a",
            LiquiditySignalType.HONG_KONG: "hk",
            LiquiditySignalType.US: "us_equity",
            LiquiditySignalType.FUTURES: "nasdaq100",
            LiquiditySignalType.CRYPTO: None,
        }
        market_id = market_id_map.get(target)
        if not market_id:
            return time.time() + 3600

        market_status = self.session_manager.get_market_status(market_id)

        if market_status == MarketStatus.OPEN:
            remaining = self.session_manager.get_session_remaining_seconds(market_id)
            if remaining is not None and remaining > 0:
                return time.time() + remaining
        elif market_status in (MarketStatus.PRE_MARKET, MarketStatus.POST_MARKET, MarketStatus.BREAK):
            remaining = self.session_manager.get_session_remaining_seconds(market_id)
            if remaining is not None and remaining > 0:
                duration = self.session_manager.get_market_trading_duration_seconds(market_id) or 0
                return time.time() + remaining + duration

        duration = self.session_manager.get_market_trading_duration_seconds(market_id) or 14400
        return time.time() + duration

    def _check_if_priced(self, target: LiquiditySignalType, source_signal: float, source_market: LiquiditySignalType) -> tuple:
        """
        检测目标市场是否已经对源市场信号完成"定价"

        定价检测逻辑：
        - 目标市场开盘变动方向与源市场信号方向一致 → 已定价（无效干预）
        - 目标市场开盘变动方向与源市场信号方向相反 → 未定价（值得干预）
        - 信号太弱或数据不足 → 无法判断（不干预）

        Args:
            target: 目标市场
            source_signal: 源市场信号（原始，未经过传染率折扣）
            source_market: 源市场

        Returns:
            (is_priced, reason, priced_at_open)
        """
        market_id_map = {
            LiquiditySignalType.CHINA_A: "china_a",
            LiquiditySignalType.HONG_KONG: "hk",
            LiquiditySignalType.US: "us_equity",
            LiquiditySignalType.FUTURES: "nasdaq100",
            LiquiditySignalType.CRYPTO: None,
        }
        market_id = market_id_map.get(target)
        if not market_id:
            return (False, "", False)

        if self.session_manager.get_market_status(market_id) == MarketStatus.CLOSED:
            return (False, "市场已收盘，等待下一交易日", False)

        recent_data = self._get_latest_market_data(market_id)
        if not recent_data:
            return (False, "无市场数据，无法判断定价状态", False)

        open_change = recent_data.get('change_pct', 0)

        if abs(open_change) < 0.1:
            return (False, f"开盘变化微小({open_change:.2f}%),未定价", False)

        signal_threshold = 0.15
        if abs(source_signal - 0.5) <= signal_threshold:
            return (False, "信号不够强，无法判断定价", False)

        source_dir = 1 if source_signal > 0.5 else -1
        open_dir = 1 if open_change > 0 else -1

        if source_dir == open_dir:
            return (True,
                    f"已定价: 源信号方向={source_dir}, 开盘变动={open_change:.2f}%, 方向一致",
                    True)
        else:
            return (False,
                    f"未定价: 源信号方向={source_dir}, 开盘变动={open_change:.2f}%, 方向相反",
                    False)

    def _get_latest_market_data(self, market_id: str) -> Optional[Dict[str, Any]]:
        """获取最近的市场数据"""
        md = self._last_market_data.get(market_id)
        if md:
            if isinstance(md, dict):
                return md
            return {'change_pct': getattr(md, 'change_pct', 0), 'current': getattr(md, 'current', 0)}
        return None

    def predict_liquidity(self, source_market: LiquiditySignalType, signals: Dict[str, Any], breadth_fear: float = None) -> List[LiquidityPrediction]:
        """
        基于信号来源市场，预测对各目标市场的流动性影响

        Args:
            source_market: 信号来源市场
            signals: 信号数据（涨跌、成交量、波动率等）
            breadth_fear: 市场广度恐惧分数 (0-100)，可选

        Returns:
            List[LiquidityPrediction]: 对各目标市场的预测列表
        """
        if not getattr(self, '_liquidity_initialized', False):
            self._init_liquidity_system()

        predictions = []
        source_signal = self._calc_liquidity_signal(signals)

        if breadth_fear is not None:
            breadth_factor = self._get_breadth_fear_factor(breadth_fear)
            source_signal = source_signal * breadth_factor

        target_markets = self._market_influences.get(source_market, [])
        for target in target_markets:
            transmission_prob = self._get_transmission_probability(source_market, target)
            predicted_signal = source_signal * transmission_prob

            is_priced, priced_reason, priced_at_open = self._check_if_priced(target, source_signal, source_market)

            adjustment = self._generate_adjustment(target, predicted_signal, is_priced)

            prediction = LiquidityPrediction(
                target_market=target,
                source_signals=[f"{source_market.value}: {source_signal:.2f}"],
                signal=predicted_signal,
                confidence=transmission_prob,
                timestamp=time.time(),
                valid_until=self._get_dynamic_valid_until(target),
                is_priced=is_priced,
                priced_reason=priced_reason,
                priced_at_open=priced_at_open,
                adjustment=adjustment
            )

            predictions.append(prediction)
            self._liquidity_predictions[target] = prediction

        return predictions

    def _calc_liquidity_signal(self, signals: Dict[str, Any]) -> float:
        """
        计算流动性信号，范围 [0, 1]
        - 暴涨(+5%↑) = 流动性宽松 = signal接近1.0
        - 暴跌(-5%↓) = 流动性紧张 = signal接近0.0
        - 不变(0%) = signal = 0.5
        """
        change = signals.get('change_pct', 0)
        volume_ratio = signals.get('volume_ratio', 1.0)

        change_score = 0.5 + (change / 10.0)
        change_score = float(np.clip(change_score, 0.0, 1.0))

        if volume_ratio < 0.7:
            volume_score = 0.3
        elif volume_ratio < 0.9:
            volume_score = 0.4
        elif volume_ratio > 1.5:
            volume_score = 0.3
        elif volume_ratio > 1.3:
            volume_score = 0.4
        else:
            volume_score = 0.5

        signal = change_score * 0.7 + volume_score * 0.3
        return float(np.clip(signal, 0.0, 1.0))

    def _get_breadth_fear_factor(self, breadth_fear: float) -> float:
        """
        根据广度恐惧分数计算流动性信号调节因子

        breadth_fear 高(>50) → 恐慌加剧 → 信号向极端偏移
        breadth_fear 低(<30) → 市场平稳 → 因子接近1.0

        Returns:
            float: 调节因子 (0.5 ~ 1.5)
        """
        if breadth_fear >= 80:
            return 0.5
        elif breadth_fear >= 70:
            return 0.6
        elif breadth_fear >= 60:
            return 0.7
        elif breadth_fear >= 50:
            return 0.8
        elif breadth_fear <= 20:
            return 1.2
        elif breadth_fear <= 30:
            return 1.1
        else:
            return 1.0

    def _get_transmission_probability(self, source: LiquiditySignalType, target: LiquiditySignalType) -> float:
        """获取市场间传染概率"""
        return self._transmission_probabilities.get((source, target), 0.3)

    def _generate_adjustment(self, target: LiquiditySignalType, signal: float, is_priced: bool = False) -> Dict[str, Any]:
        """生成调整指令"""
        if is_priced:
            return {
                "block_attention_factor": 1.0,
                "strategy_budget": {},
                "frequency_factor": 1.0,
                "position_size_multiplier": 1.0,
                "holding_time_factor": 1.0,
                "is_priced": True,
            }
        if signal < 0.4:
            return {
                "block_attention_factor": 0.8,
                "strategy_budget": {
                    "AnomalySniper": 0.2,
                    "MomentumTracker": -0.2,
                },
                "frequency_factor": 1.3,
                "position_size_multiplier": 0.6,
                "holding_time_factor": 0.7,
                "warning": "流动性紧张信号",
            }
        elif signal > 0.7:
            return {
                "block_attention_factor": 1.1,
                "strategy_budget": {
                    "AnomalySniper": -0.1,
                    "MomentumTracker": 0.1,
                },
                "frequency_factor": 0.9,
                "position_size_multiplier": 1.1,
                "holding_time_factor": 1.0,
            }
        else:
            return {
                "block_attention_factor": 1.0,
                "strategy_budget": {},
                "frequency_factor": 1.0,
                "position_size_multiplier": 1.0,
                "holding_time_factor": 1.0,
            }

    def verify_liquidity(self, target_market: LiquiditySignalType, actual_data: Dict[str, Any]):
        """
        验证对某个市场的预测是否正确

        Args:
            target_market: 目标市场
            actual_data: 实际市场数据（涨跌幅、成交量等）
        """
        if not getattr(self, '_liquidity_initialized', False):
            self._init_liquidity_system()

        if target_market not in self._liquidity_verifications:
            expected = 0.5
            if target_market in self._liquidity_predictions:
                expected = self._liquidity_predictions[target_market].signal
            self._liquidity_verifications[target_market] = LiquidityVerification(
                target_market=target_market,
                expected_signal=expected
            )

        ver = self._liquidity_verifications[target_market]
        actual_signal = self._calc_liquidity_signal(actual_data)
        ver.actual_signals.append(actual_signal)
        ver.verification_count += 1

        if ver.verification_count < 5:
            return

        recent = ver.actual_signals[-10:]
        avg_actual = sum(recent) / len(recent)

        diff = abs(avg_actual - ver.expected_signal)
        if diff > 0.25:
            ver.verified = False
            ver.should_relax = True
            log.info(f"[Liquidity] {target_market.value} 预判错误: 预期={ver.expected_signal:.2f}, 实际={avg_actual:.2f}, 解除限制")
        else:
            ver.verified = True
            ver.should_relax = False

    def get_liquidity_adjustment(self, target_market: LiquiditySignalType, actual_data: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        获取对某个目标市场的调整指令

        Args:
            target_market: 目标市场
            actual_data: 可选的实际数据，用于验证

        Returns:
            dict: 调整指令，如果没有预测则返回 None
        """
        if not getattr(self, '_liquidity_initialized', False):
            return None

        prediction = self._liquidity_predictions.get(target_market)
        if not prediction:
            return None

        if actual_data:
            self.verify_liquidity(target_market, actual_data)

        if time.time() > prediction.valid_until:
            log.info(f"[Liquidity] {target_market.value} 预测过期，解除限制")
            return self._generate_relaxation_adjustment()

        ver = self._liquidity_verifications.get(target_market)
        if ver and ver.should_relax:
            log.info(f"[Liquidity] {target_market.value} 验证失败，解除限制")
            return self._generate_relaxation_adjustment()

        return prediction.adjustment

    def get_all_market_adjustments(self) -> Dict[LiquiditySignalType, Optional[Dict[str, Any]]]:
        """
        获取所有市场的调整指令（用于全局更新）

        Returns:
            Dict[market, adjustment]: 各市场的调整指令
        """
        if not getattr(self, '_liquidity_initialized', False):
            return {}

        adjustments = {}
        for market in self._liquidity_predictions.keys():
            adjustments[market] = self.get_liquidity_adjustment(market)
        return adjustments

    def auto_verify_all_predictions(self, market_data_map: Dict[LiquiditySignalType, Dict[str, Any]]):
        """
        自动验证所有有预测的市场

        Args:
            market_data_map: 各市场的实际数据 {
                LiquiditySignalType.CHINA_A: {'change_pct': -1.5, 'volume_ratio': 0.8},
                LiquiditySignalType.US: {'change_pct': 2.0, 'volume_ratio': 1.2},
                ...
            }
        """
        for market, data in market_data_map.items():
            if market in self._liquidity_predictions:
                self.verify_liquidity(market, data)

    def predict_and_auto_verify(self, source_market: LiquiditySignalType, signals: Dict[str, Any], market_data_map: Dict[LiquiditySignalType, Dict[str, Any]] = None, breadth_fear: float = None) -> List[LiquidityPrediction]:
        """
        预测并自动验证（形成闭环）

        Args:
            source_market: 信号来源市场
            signals: 信号数据
            market_data_map: 各目标市场的实际数据（用于验证）
            breadth_fear: 市场广度恐惧分数 (0-100)

        Returns:
            List[LiquidityPrediction]: 预测列表
        """
        predictions = self.predict_liquidity(source_market, signals, breadth_fear)

        if market_data_map:
            self.auto_verify_all_predictions(market_data_map)

        return predictions

    def _generate_relaxation_adjustment(self) -> Dict[str, Any]:
        """生成解除限制的调整"""
        return {
            "block_attention_factor": 1.2,
            "strategy_budget": {
                "AnomalySniper": -0.2,
                "MomentumTracker": 0.2,
            },
            "frequency_factor": 0.9,
            "is_relaxation": True,
        }

    def get_liquidity_status(self) -> Dict[str, Any]:
        """获取流动性系统状态"""
        if not getattr(self, '_liquidity_initialized', False):
            self._init_liquidity_system()

        predictions = {}
        for market, pred in self._liquidity_predictions.items():
            predictions[market.value] = {
                "signal": pred.signal,
                "confidence": pred.confidence,
                "source_signals": pred.source_signals,
                "is_valid": time.time() <= pred.valid_until,
            }

        verifications = {}
        for market, ver in self._liquidity_verifications.items():
            verifications[market.value] = {
                "expected": ver.expected_signal,
                "verification_count": ver.verification_count,
                "verified": ver.verified,
                "should_relax": ver.should_relax,
            }

        resonance = getattr(self, '_last_resonance', None)
        resonance_info = None
        if resonance:
            resonance_info = {
                "level": resonance["resonance_level"],
                "confidence": resonance["confidence"],
                "alignment": resonance["alignment"],
                "weight": resonance.get("weight", 0),
                "market_signal": resonance["market_signal"],
                "narrative_signal": resonance["narrative_signal"],
            }

        topic_predictions = getattr(self, '_topic_predictions', {})
        topic_info = {}
        for topic, pred in topic_predictions.items():
            topic_info[topic] = {
                "target_blocks": pred.get("target_blocks", []),
                "spread_probability": pred.get("spread_probability", 0),
                "expected_change": pred.get("expected_change", 0),
                "heat_score": pred.get("heat_score", 0),
            }

        return {
            "predictions": predictions,
            "verifications": verifications,
            "resonance": resonance_info,
            "topic_predictions": topic_info,
        }

    def set_narrative_signal(self, signal: float):
        """
        设置舆论信号（供 NarrativeTracker 调用）

        Args:
            signal: 舆论信号 (-1 to 1, 负=利空，正=利多)
        """
        if not getattr(self, '_liquidity_initialized', False):
            self._init_liquidity_system()

        self._narrative_signal = float(np.clip(signal, -1.0, 1.0))

    def detect_resonance(self, market_signal: float, narrative_signal: float = None, breadth_fear: float = None) -> Dict[str, Any]:
        """
        检测信号共振

        Args:
            market_signal: 行情信号 (-1 to 1)
            narrative_signal: 舆论信号 (-1 to 1)，如果为 None 则使用内部存储的舆论信号
            breadth_fear: 市场广度恐惧分数 (0-100)，高恐惧时作为主导信号

        Returns:
            {
                "resonance_level": "high"/"medium"/"low"/"divergent"/"none",
                "confidence": 0.0-1.0,
                "final_signal": float,
                "alignment": float,
                "weight": float,
            }
        """
        if narrative_signal is None:
            narrative_signal = getattr(self, '_narrative_signal', 0.0)

        if breadth_fear is not None and breadth_fear >= 70:
            breadth_norm = (breadth_fear - 50) / 50
            breadth_norm = float(np.clip(breadth_norm, 0.0, 1.0))
            narrative_signal = -breadth_norm
            if market_signal * narrative_signal < 0:
                resonance_level = "high_fear_divergent"
                confidence = 0.85
            else:
                resonance_level = "high_fear"
                confidence = 0.8
            resonance_weights = {"high_fear": 0.9, "high_fear_divergent": 0.6, "none": 0.0}
            weight = resonance_weights.get(resonance_level, 0.5)
            final_signal = market_signal * weight
            self._last_resonance = {
                "resonance_level": resonance_level,
                "confidence": confidence,
                "final_signal": final_signal,
                "alignment": 0.0,
                "weight": weight,
                "market_signal": market_signal,
                "narrative_signal": narrative_signal,
                "breadth_fear": breadth_fear,
            }
            return self._last_resonance

        if abs(market_signal) < 0.1 and abs(narrative_signal) < 0.1:
            resonance_level = "none"
            confidence = 0.0
        elif abs(market_signal) < 0.2 or abs(narrative_signal) < 0.2:
            if market_signal * narrative_signal > 0:
                resonance_level = "low"
                confidence = 0.4
            elif market_signal * narrative_signal < 0:
                resonance_level = "divergent"
                confidence = 0.3
            else:
                resonance_level = "low"
                confidence = 0.3
        elif market_signal * narrative_signal > 0:
            alignment = 1 - abs(market_signal - narrative_signal) / 2
            if alignment > 0.7:
                resonance_level = "high"
                confidence = 0.9
            else:
                resonance_level = "medium"
                confidence = 0.7
        elif market_signal * narrative_signal < 0:
            resonance_level = "divergent"
            confidence = 0.5
        else:
            resonance_level = "low"
            confidence = 0.4

        resonance_weights = {
            "high": 1.0,
            "medium": 0.7,
            "low": 0.5,
            "divergent": 0.3,
            "none": 0.0,
        }
        weight = resonance_weights[resonance_level]
        final_signal = market_signal * weight

        self._last_resonance = {
            "resonance_level": resonance_level,
            "confidence": confidence,
            "final_signal": final_signal,
            "alignment": 1 - abs(market_signal - narrative_signal) / 2 if resonance_level != "none" else 0,
            "weight": weight,
            "market_signal": market_signal,
            "narrative_signal": narrative_signal,
        }

        return self._last_resonance

    TOPIC_SECTOR_MAPPING = {
        "芯片": {"a_share_blocks": ["半导体", "集成电路"], "us_block": "SOX"},
        "AI": {"a_share_blocks": ["人工智能", "软件服务"], "us_block": "AI"},
        "新能源": {"a_share_blocks": ["锂电池", "光伏"], "us_block": "XLE"},
        "电动车": {"a_share_blocks": ["新能源汽车"], "us_block": "TSLA"},
        "云计算": {"a_share_blocks": ["云计算", "数据中心"], "us_block": "CLOUD"},
    }

    CROSS_MARKET_PROB = {
        "芯片": 0.7,
        "AI": 0.6,
        "新能源": 0.5,
        "电动车": 0.4,
        "云计算": 0.5,
    }

    def update_topic_heat(self, topic: str, change_pct: float, volume_ratio: float = 1.0):
        """
        更新主题热度

        Args:
            topic: 主题名称
            change_pct: 涨跌幅
            volume_ratio: 成交量比
        """
        if not hasattr(self, '_topic_heat'):
            self._topic_heat = {}

        if topic not in self._topic_heat:
            self._topic_heat[topic] = deque(maxlen=10)

        heat_score = abs(change_pct) * volume_ratio
        self._topic_heat[topic].append(heat_score)

    def predict_topic_spread(self, topic: str, us_block_change: float) -> Dict[str, Any]:
        """
        预测主题扩散

        Args:
            topic: 主题名称
            us_block_change: 美股该题材的涨跌幅

        Returns:
            {
                "target_blocks": List[str],
                "spread_probability": float,
                "expected_change": float,
                "heat_score": float,
                "confidence": float,
            }
        """
        mapping = self.TOPIC_SECTOR_MAPPING.get(topic, {})
        target_blocks = mapping.get("a_share_blocks", [])

        heat_history = self._topic_heat.get(topic, [])
        heat_score = float(np.mean(list(heat_history))) if heat_history else 0

        base_prob = self.CROSS_MARKET_PROB.get(topic, 0.3)

        heat_factor = min(heat_score / 5.0, 1.5)
        spread_prob = base_prob * heat_factor

        expected_change = us_block_change * spread_prob

        result = {
            "target_blocks": target_blocks,
            "spread_probability": min(spread_prob, 0.95),
            "expected_change": expected_change,
            "heat_score": heat_score,
            "confidence": base_prob * 0.8,
        }

        if not hasattr(self, '_topic_predictions'):
            self._topic_predictions = {}
        self._topic_predictions[topic] = result

        return result

    def get_topic_adjustment_for_block(self, block: str) -> Optional[Dict[str, Any]]:
        """
        获取题材的主题调整指令

        Args:
            block: 题材名称

        Returns:
            {
                "attention_weight_factor": float,
                "hot_topic_score": float,
                "spread_confidence": float,
                "topics": List[str],
            }
        """
        relevant_topics = []
        for topic, mapping in self.TOPIC_SECTOR_MAPPING.items():
            if block in mapping["a_share_blocks"]:
                relevant_topics.append(topic)

        if not relevant_topics:
            return None

        total_heat = 0
        total_prob = 0
        for topic in relevant_topics:
            heat = float(np.mean(list(self._topic_heat.get(topic, [])))) if self._topic_heat.get(topic) else 0
            prob = self.CROSS_MARKET_PROB.get(topic, 0.3)
            total_heat += heat * prob
            total_prob += prob

        avg_heat = total_heat / len(relevant_topics) if relevant_topics else 0
        avg_prob = total_prob / len(relevant_topics) if relevant_topics else 0

        if avg_heat > 3:
            attention_factor = 1.2 + (avg_heat - 3) * 0.05
        else:
            attention_factor = 1.0

        return {
            "attention_weight_factor": min(attention_factor, 1.5),
            "hot_topic_score": avg_heat,
            "spread_confidence": avg_prob,
            "topics": relevant_topics,
        }

    def get_a_share_liquidity_prediction(self) -> Optional[LiquidityPrediction]:
        """获取 A 股流动性预测（便捷方法）"""
        return self._liquidity_predictions.get(LiquiditySignalType.CHINA_A)


# ─── 单例 ───────────────────────────────────────────────────────────────

_predictor_instance: Optional[LiquidityPredictor] = None


def get_liquidity_predictor(session_manager=None) -> LiquidityPredictor:
    """获取 LiquidityPredictor 单例"""
    global _predictor_instance
    if _predictor_instance is None:
        _predictor_instance = LiquidityPredictor(session_manager=session_manager)
    return _predictor_instance
