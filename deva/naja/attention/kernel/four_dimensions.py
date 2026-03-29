"""
FourDimensions - 四维决策框架

系统的核心内心：
1. 天时 (Time) - 时间合不合适
2. 资金 (Capital) - 资产情况允不允许
3. 能力 (Capability) - 自己能力允不允许
4. 市场 (Market) - 有没有这个机会

所有外部系统只进不出（单向依赖），四维不反向修改外部系统。
"""

import time
import logging
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)


class TimeDimension:
    """天时维度 - 时间是否合适"""

    def __init__(self):
        self.is_trading_open = False
        self.seconds_to_close = 0
        self.seconds_to_open = 0
        self.is_event_window = False
        self.pressure = 0.5
        self.market_status = "unknown"

    def update(self, session_manager=None):
        """从 TradingClock/MarketSessionManager 获取状态"""
        try:
            if session_manager is None:
                try:
                    from deva.naja.radar.trading_clock import get_trading_clock
                    tc = get_trading_clock()
                    if tc:
                        session_manager = tc
                except ImportError:
                    pass

            if session_manager is None:
                return

            if hasattr(session_manager, 'get_market_status'):
                status = session_manager.get_market_status("china_a")
                self.market_status = status.value if hasattr(status, 'value') else str(status)
                self.is_trading_open = (status.value == "open") if hasattr(status, 'value') else False

            if hasattr(session_manager, 'get_session_remaining_seconds'):
                self.seconds_to_close = session_manager.get_session_remaining_seconds("china_a") or 0

            self._calc_pressure()
        except Exception as e:
            log.debug(f"[TimeDimension] update failed: {e}")

    def _calc_pressure(self):
        """计算时间压力"""
        if not self.is_trading_open:
            self.pressure = 0.2
        elif self.seconds_to_close < 1800:
            self.pressure = 0.4
        elif self.seconds_to_close < 900:
            self.pressure = 0.2
        else:
            self.pressure = 0.8

    def get_state(self) -> Dict[str, Any]:
        return {
            "is_trading_open": self.is_trading_open,
            "seconds_to_close": self.seconds_to_close,
            "pressure": self.pressure,
            "market_status": self.market_status,
        }


class CapitalDimension:
    """资金维度 - 资产情况"""

    def __init__(self):
        self.total_capital = 0.0
        self.available_capital = 0.0
        self.used_capital = 0.0
        self.cash_ratio = 0.5
        self.has_bullets = True
        self.action_ratio = 1.0

    def update(self, portfolio=None):
        """从 VirtualPortfolio 获取状态"""
        try:
            if portfolio is None:
                try:
                    from deva.naja.bandit import get_virtual_portfolio
                    portfolio = get_virtual_portfolio()
                except ImportError:
                    return

            if portfolio is None:
                return

            summary = portfolio.get_summary()
            self.total_capital = portfolio._total_capital
            self.available_capital = summary.get("available_capital", 0.0)
            self.used_capital = summary.get("used_capital", 0.0)
            self.cash_ratio = self.available_capital / max(self.total_capital, 1.0)
            self.has_bullets = self.cash_ratio > 0.2
            self.action_ratio = self._calc_action_ratio()
        except Exception as e:
            log.debug(f"[CapitalDimension] update failed: {e}")

    def _calc_action_ratio(self) -> float:
        """计算行动就绪度"""
        if self.cash_ratio < 0.1:
            return 0.0
        elif self.cash_ratio < 0.2:
            return 0.3
        elif self.cash_ratio < 0.3:
            return 0.6
        return 1.0

    def get_state(self) -> Dict[str, Any]:
        return {
            "total_capital": self.total_capital,
            "available_capital": self.available_capital,
            "cash_ratio": self.cash_ratio,
            "has_bullets": self.has_bullets,
            "action_ratio": self.action_ratio,
        }


class CapabilityDimension:
    """能力维度 - 自身能力"""

    def __init__(self):
        self.strategy_count = 0
        self.is_ready = True
        self.multiplier = 1.0
        self.learning_mode = False
        self.cooldown_remaining = 0

    def update(self, strategy_manager=None):
        """从 StrategyManager 获取状态"""
        try:
            if strategy_manager is None:
                try:
                    from deva.naja.attention.strategies import get_strategy_manager
                    strategy_manager = get_strategy_manager()
                except ImportError:
                    return

            if strategy_manager is None:
                return

            self.strategy_count = len(strategy_manager.strategies)
            self.is_ready = (
                strategy_manager.is_running and
                self.strategy_count > 0 and
                self.cooldown_remaining <= 0
            )
            self.multiplier = self._calc_multiplier()
        except Exception as e:
            log.debug(f"[CapabilityDimension] update failed: {e}")

    def _calc_multiplier(self) -> float:
        """计算能力乘数"""
        if not self.is_ready:
            return 0.3
        if self.learning_mode:
            return 0.7
        if self.strategy_count < 3:
            return 0.7
        return 1.0

    def get_state(self) -> Dict[str, Any]:
        return {
            "strategy_count": self.strategy_count,
            "is_ready": self.is_ready,
            "multiplier": self.multiplier,
            "learning_mode": self.learning_mode,
        }


class MarketDimension:
    """市场维度 - 机会识别与流动性管理"""

    def __init__(self):
        self.liquidity_signal = 0.5
        self.is_priced = False
        self.is_extreme = False
        self.opportunity_score = 0.5
        self.signal = 0.5
        self.opportunity_type = None
        self._liquidity_adjustment: Dict[str, Any] = {}
        self._has_liquidity_prediction = False

    def update(self, scanner=None, macro_signal: float = 0.5):
        """从 GlobalMarketScanner 和 QueryState 获取状态"""
        try:
            if scanner is None:
                try:
                    from deva.naja.radar.global_market_scanner import get_global_market_scanner
                    scanner = get_global_market_scanner()
                except ImportError:
                    pass

            if scanner is not None:
                summary = scanner.get_market_summary()
                self.liquidity_signal = summary.get("signal", macro_signal)

                adjustment = scanner.get_liquidity_adjustment("CHINA_A")
                if adjustment:
                    self._liquidity_adjustment = adjustment
                    self._has_liquidity_prediction = True
                else:
                    self._liquidity_adjustment = {}
                    self._has_liquidity_prediction = False
            else:
                self.liquidity_signal = macro_signal
                self._liquidity_adjustment = {}
                self._has_liquidity_prediction = False

            self.is_extreme = self.liquidity_signal < 0.3 or self.liquidity_signal > 0.8
            self.opportunity_score = self._calc_opportunity_score()
            self.signal = self.opportunity_score
            self._determine_opportunity_type()
        except Exception as e:
            log.debug(f"[MarketDimension] update failed: {e}")

    def get_position_adjustment(self) -> float:
        """获取仓位调整系数

        Returns:
            float: 0.0-1.5，流动性紧张时 < 1.0，充裕时 >= 1.0
        """
        if not self._has_liquidity_prediction:
            return 1.0
        adj = self._liquidity_adjustment.get("position_size_multiplier", 1.0)
        return adj

    def get_holding_time_adjustment(self) -> float:
        """获取持仓时间调整系数

        Returns:
            float: 0.0-1.0，流动性紧张时缩短持仓时间
        """
        if not self._has_liquidity_prediction:
            return 1.0
        return self._liquidity_adjustment.get("holding_time_factor", 1.0)

    def get_strategy_budget_adjustment(self, strategy_id: str) -> float:
        """获取策略预算调整系数

        Args:
            strategy_id: 策略ID

        Returns:
            float: 策略预算调整系数
        """
        if not self._has_liquidity_prediction:
            return 0.0
        budget_adj = self._liquidity_adjustment.get("strategy_budget", {})
        return budget_adj.get(strategy_id, 0.0)

    def get_frequency_adjustment(self) -> float:
        """获取交易频率调整系数"""
        if not self._has_liquidity_prediction:
            return 1.0
        return self._liquidity_adjustment.get("frequency_factor", 1.0)

    def should_reduce_position(self) -> bool:
        """是否应该降低仓位"""
        return self.get_position_adjustment() < 0.8

    def should_shorten_holding(self) -> bool:
        """是否应该缩短持仓时间"""
        return self.get_holding_time_adjustment() < 0.7

    def get_liquidity_warning(self) -> str:
        """获取流动性警告信息"""
        if not self._has_liquidity_prediction:
            return ""
        return self._liquidity_adjustment.get("warning", "")

    def _calc_opportunity_score(self) -> float:
        """计算机会评分"""
        if self.liquidity_signal < 0.3:
            return 0.8
        elif self.liquidity_signal < 0.4:
            return 0.6
        elif self.liquidity_signal > 0.7:
            return 0.7
        elif self.liquidity_signal > 0.8:
            return 0.6
        return 0.5

    def _determine_opportunity_type(self):
        """判断机会类型"""
        if self.liquidity_signal < 0.3:
            self.opportunity_type = "liquidity_crisis"
        elif self.liquidity_signal > 0.7:
            self.opportunity_type = "liquidity_宽松"
        else:
            self.opportunity_type = None

    def get_state(self) -> Dict[str, Any]:
        return {
            "liquidity_signal": self.liquidity_signal,
            "is_priced": self.is_priced,
            "is_extreme": self.is_extreme,
            "opportunity_score": self.opportunity_score,
            "opportunity_type": self.opportunity_type,
            "has_liquidity_prediction": self._has_liquidity_prediction,
            "position_adjustment": self.get_position_adjustment(),
            "holding_time_adjustment": self.get_holding_time_adjustment(),
            "liquidity_warning": self.get_liquidity_warning(),
        }


class FourDimensions:
    """
    四维决策框架 - 系统的核心内心

    用四维塑造 Query，应用四维门控到最终结果。

    使用方式：
        kernel = AttentionKernel(encoder, multi_head, memory, enable_four_dimensions=True)

    关闭方式：
        kernel = AttentionKernel(encoder, multi_head, memory, enable_four_dimensions=False)
        # 或
        kernel.set_four_dimensions_enabled(False)
    """

    def __init__(self):
        self.time = TimeDimension()
        self.capital = CapitalDimension()
        self.capability = CapabilityDimension()
        self.market = MarketDimension()
        self._last_update = 0
        self._update_interval = 1.0

    def update(self, session_manager=None, portfolio=None, strategy_manager=None, scanner=None, macro_signal: float = 0.5):
        """
        从外部系统拉取最新状态

        Args:
            session_manager: TradingClock/MarketSessionManager
            portfolio: VirtualPortfolio
            strategy_manager: AttentionStrategyManager
            scanner: GlobalMarketScanner
            macro_signal: 宏观流动性信号（当 scanner 不可用时）
        """
        current_time = time.time()
        if current_time - self._last_update < self._update_interval:
            return

        self.time.update(session_manager)
        self.capital.update(portfolio)
        self.capability.update(strategy_manager)
        self.market.update(scanner, macro_signal)

        self._last_update = current_time

    def shape_query(self, Q) -> Dict[str, Any]:
        """
        用四维塑造 Query

        Args:
            Q: QueryState 或 query dict

        Returns:
            被四维偏见塑造的 query dict
        """
        if isinstance(Q, dict):
            focus = Q.get("focus", {})
            risk = Q.get("risk", 0.5)
            regime = Q.get("regime", "neutral")
        else:
            focus = getattr(Q, "attention_focus", {})
            risk = getattr(Q, "risk_bias", 0.5)
            regime = getattr(Q, "market_regime", {}).get("type", "neutral") if hasattr(Q, "market_regime") else "neutral"

        shaped = {
            "focus": focus,
            "risk": risk,
            "regime": regime,
            "action_readiness": self.capital.action_ratio,
            "opportunity_weight": self.market.signal,
            "time_pressure": self.time.pressure,
            "capability_multiplier": self.capability.multiplier,
        }
        return shaped

    def apply_gates(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用四维门控

        每个维度都可以否决或加权最终结果

        Args:
            result: Attention 计算结果 {alpha, risk, confidence}

        Returns:
            经过门控处理的结果
        """
        original_alpha = result.get("alpha", 0)
        gate_reason = None
        opportunity = None

        if not self.time.is_trading_open and self.time.market_status != "unknown":
            result["alpha"] *= 0.0
            gate_reason = "非交易时段"
        elif self.time.pressure < 0.3:
            result["alpha"] *= self.time.pressure

        if self.capital.cash_ratio < 0.1:
            result["alpha"] *= 0.0
            gate_reason = "资金不足，保留子弹"
        elif self.capital.cash_ratio < 0.2:
            result["alpha"] *= 0.5
            gate_reason = "资金紧张，轻仓操作"

        if not self.capability.is_ready:
            result["alpha"] *= 0.3
            gate_reason = "策略未就绪"
        else:
            result["alpha"] *= self.capability.multiplier

        position_adj = self.market.get_position_adjustment()
        if position_adj < 1.0:
            result["alpha"] *= position_adj
            reason = self.market.get_liquidity_warning() or f"流动性紧张，仓位系数={position_adj:.2f}"
            if gate_reason:
                gate_reason += f" + {reason}"
            else:
                gate_reason = reason

        if self.market.is_extreme and self.capital.has_bullets:
            opportunity = "逆向布局机会"
            result["alpha"] = max(result["alpha"], original_alpha * 0.8)

        result["_gate_reason"] = gate_reason
        result["_opportunity"] = opportunity
        result["_gated"] = gate_reason is not None
        result["_position_adjustment"] = position_adj
        result["_holding_time_adjustment"] = self.market.get_holding_time_adjustment()

        return result

    def get_state(self) -> Dict[str, Any]:
        """获取四维状态摘要"""
        return {
            "time": self.time.get_state(),
            "capital": self.capital.get_state(),
            "capability": self.capability.get_state(),
            "market": self.market.get_state(),
        }

    def should_act(self) -> bool:
        """判断是否应该行动"""
        if not self.time.is_trading_open and self.time.market_status != "unknown":
            return False
        if self.capital.cash_ratio < 0.1:
            return False
        if not self.capability.is_ready:
            return False
        return True
