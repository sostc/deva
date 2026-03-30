"""
AwakenedOrchestrator - 觉醒版注意力编排器

集成天眼通、光明藏、顺应型末那识等觉醒模块

使用方式：
    from deva.naja.attention.enhanced_orchestrator import AwakenedOrchestrator

    orchestrator = get_awakened_orchestrator()
    orchestrator.initialize()

    # 处理数据时自动使用所有觉醒能力
    result = orchestrator.process_market_data(data)
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

log = logging.getLogger(__name__)

_global_orchestrator = None


@dataclass
class AwakenedState:
    """觉醒状态"""
    prophet_signal_count: int = 0
    taste_signals_count: int = 0
    illuminated_patterns_count: int = 0
    adaptive_decision_count: int = 0
    last_prophet_signal: Optional[Dict] = None
    last_taste_signal: Optional[Dict] = None
    last_decision: Optional[Dict] = None


class AwakenedOrchestrator:
    """
    觉醒版注意力编排器

    在原有 AttentionOrchestrator 基础上集成：
    - ProphetSense（天眼通预感知）
    - RealtimeTaste（实时舌识尝受）
    - SeedIlluminator（光明藏模式召回）
    - AdaptiveManas（顺应型末那识）
    """

    def __init__(self, base_orchestrator=None):
        """
        初始化觉醒编排器

        Args:
            base_orchestrator: 基础编排器（可选），如果不提供则使用现有编排器
        """
        self._base = base_orchestrator

        self._awakened_alaya = None
        self._first_principles_mind = None
        self._adaptive_manas = None

        self._state = AwakenedState()
        self._initialized = False

    def initialize(self):
        """初始化所有觉醒模块"""
        if self._initialized:
            return

        try:
            from deva.naja.alaya.awakened_alaya import AwakenedAlaya
            from deva.naja.cognition.first_principles_mind import FirstPrinciplesMind
            from deva.naja.manas import AdaptiveManas

            self._awakened_alaya = AwakenedAlaya()
            self._first_principles_mind = FirstPrinciplesMind()
            self._adaptive_manas = AdaptiveManas()

            self._initialized = True
            log.info("[AwakenedOrchestrator] 觉醒模块初始化完成")

        except ImportError as e:
            log.error(f"[AwakenedOrchestrator] 初始化失败: {e}")

    def process_market_data(
        self,
        market_data: Dict[str, Any],
        flow_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        处理市场数据（集成所有觉醒能力）

        Args:
            market_data: 市场数据
            flow_data: 资金流向数据

        Returns:
            包含所有觉醒能力的处理结果
        """
        if not self._initialized:
            self.initialize()

        result = {
            "base": market_data,
            "awakened": {}
        }

        prophet_signal = self._sense_prophet(market_data, flow_data)
        if prophet_signal:
            result["awakened"]["prophet"] = prophet_signal.to_dict()

        taste_signal = self._sense_taste(market_data)
        if taste_signal:
            result["awakened"]["taste"] = taste_signal.to_dict()

        illuminated_patterns = self._recall_patterns(market_data)
        if illuminated_patterns:
            result["awakened"]["patterns"] = [p.to_dict() for p in illuminated_patterns]

        adaptive_decision = self._make_adaptive_decision(market_data)
        if adaptive_decision:
            result["awakened"]["adaptive"] = adaptive_decision.to_dict()

        return result

    def _sense_prophet(
        self,
        market_data: Dict[str, Any],
        flow_data: Optional[Dict[str, Any]]
    ):
        """天眼通预感知"""
        if self._prophet_sense is None:
            return None

        try:
            signal = self._prophet_sense.sense(market_data, flow_data)
            if signal:
                self._state.prophet_signal_count += 1
                self._state.last_prophet_signal = signal.to_dict()
            return signal
        except Exception as e:
            log.debug(f"[AwakenedOrchestrator] ProphetSense 失败: {e}")
            return None

    def _sense_taste(self, market_data: Dict[str, Any]):
        """舌识尝受"""
        if self._realtime_taste is None:
            return None

        try:
            current_prices = {}
            for symbol, data in market_data.items():
                if isinstance(data, dict) and "price" in data:
                    current_prices[symbol] = data["price"]

            if not current_prices:
                return None

            signals = self._realtime_taste.taste_all(current_prices)
            if signals:
                self._state.taste_signals_count += 1
                self._state.last_taste_signal = list(signals.values())[0].to_dict()
            return signals
        except Exception as e:
            log.debug(f"[AwakenedOrchestrator] RealtimeTaste 失败: {e}")
            return None

    def _recall_patterns(self, market_data: Dict[str, Any]):
        """光明藏模式召回"""
        if self._seed_illuminator is None:
            return None

        try:
            state = self._extract_market_state(market_data)
            patterns = self._seed_illuminator.recall(state)
            if patterns:
                self._state.illuminated_patterns_count += 1
            return patterns
        except Exception as e:
            log.debug(f"[AwakenedOrchestrator] SeedIlluminator 失败: {e}")
            return None

    def _extract_market_state(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """从市场数据提取状态"""
        state = {
            "symbols": list(market_data.keys()) if isinstance(market_data, dict) else []
        }

        if isinstance(market_data, dict):
            for symbol, data in list(market_data.items())[:10]:
                if isinstance(data, dict):
                    state["price_change"] = data.get("change_pct", 0)
                    state["volume_ratio"] = data.get("volume_ratio", 1.0)
                    state["price"] = data.get("price", 0)
                    break

        return state

    def _make_adaptive_decision(self, market_data: Dict[str, Any]):
        """顺应型末那识决策"""
        if self._adaptive_manas is None:
            return None

        try:
            market_state = self._build_market_state(market_data)
            decision = self._adaptive_manas.compute_顺应(market_state)
            if decision:
                self._state.adaptive_decision_count += 1
                self._state.last_decision = decision.to_dict()
            return decision
        except Exception as e:
            log.debug(f"[AwakenedOrchestrator] AdaptiveManas 失败: {e}")
            return None

    def _build_market_state(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建市场状态"""
        state = {
            "is_market_open": True,
            "volatility": 1.0,
            "trend_strength": 0.0,
            "time_of_day": time.localtime().tm_hour + time.localtime().tm_min / 60.0,
            "regime": "unknown",
            "regime_stability": 0.5,
            "market_breadth": 0.0,
        }

        if isinstance(market_data, dict):
            changes = []
            for symbol, data in list(market_data.items())[:20]:
                if isinstance(data, dict):
                    change = data.get("change_pct", 0)
                    if change:
                        changes.append(change)

            if changes:
                state["trend_strength"] = sum(changes) / len(changes) / 100
                advancing = sum(1 for c in changes if c > 0)
                declining = sum(1 for c in changes if c < 0)
                state["market_breadth"] = (advancing - declining) / len(changes)

        return state

    def register_position(
        self,
        symbol: str,
        entry_price: float,
        quantity: int
    ):
        """注册持仓（用于舌识尝受）"""
        if self._realtime_taste:
            self._realtime_taste.register_position(
                symbol=symbol,
                entry_price=entry_price,
                quantity=quantity,
                entry_time=time.time()
            )

    def close_position(self, symbol: str):
        """平仓"""
        if self._realtime_taste:
            self._realtime_taste.close_position(symbol)

    def record_pattern_success(self, pattern_type: str, success: bool, holding_period: float):
        """记录模式结果（用于光明藏学习）"""
        if self._seed_illuminator:
            from deva.naja.alaya import PatternType
            try:
                pt = PatternType[pattern_type.upper()]
                self._seed_illuminator.record_outcome(pt, success, holding_period)
            except KeyError:
                pass

    def get_state(self) -> Dict[str, Any]:
        """获取觉醒状态"""
        return {
            "initialized": self._initialized,
            "prophet_enabled": self._prophet_sense is not None,
            "taste_enabled": self._realtime_taste is not None,
            "illuminator_enabled": self._seed_illuminator is not None,
            "adaptive_enabled": self._adaptive_manas is not None,
            "stats": {
                "prophet_signals": self._state.prophet_signal_count,
                "taste_signals": self._state.taste_signals_count,
                "illuminated_patterns": self._state.illuminated_patterns_count,
                "adaptive_decisions": self._state.adaptive_decision_count,
            },
            "last_prophet": self._state.last_prophet_signal,
            "last_taste": self._state.last_taste_signal,
            "last_decision": self._state.last_decision,
        }


def get_awakened_orchestrator() -> AwakenedOrchestrator:
    """获取觉醒编排器单例"""
    global _global_orchestrator
    if _global_orchestrator is None:
        _global_orchestrator = AwakenedOrchestrator()
    return _global_orchestrator


def initialize_awakened_orchestrator():
    """初始化觉醒编排器"""
    orchestrator = get_awakened_orchestrator()
    orchestrator.initialize()
    return orchestrator
