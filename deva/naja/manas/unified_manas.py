"""
UnifiedManas - 统一末那识

整合 ManasEngine + AdaptiveManas 为单一决策框架

同时服务：
1. AttentionKernel - 用它的 manas_score 塑造 Q
2. AwakenedAlaya - 用它的 harmony_state 触发顿悟
"""

import time
import logging
from typing import Dict, Any, Optional, List
from collections import deque

from .output import (
    UnifiedManasOutput,
    AttentionFocus,
    HarmonyState,
    BiasState,
    ActionType,
    PortfolioSignal,
)
from .event_recall import PortfolioDrivenEventRecall, RecalledEvent
from .feedback_loop import ManasFeedbackLoop

log = logging.getLogger(__name__)


class TimingEngine:
    """时机引擎 - 判断市场"能不能动" """

    def __init__(self):
        self._volatility_history: List[float] = []

    def compute(self, session_manager=None, scanner=None) -> float:
        time_pressure = self._get_time_pressure(session_manager)
        volatility = self._get_volatility_regime(scanner)
        density = self._get_trade_density(scanner)
        structure = self._get_structure_break(scanner)

        timing = (
            time_pressure * 0.4 +
            volatility * 0.25 +
            density * 0.2 +
            structure * 0.15
        )

        return max(0.0, min(1.0, timing))

    def _get_time_pressure(self, session_manager) -> float:
        if session_manager is None:
            return 0.5
        try:
            if hasattr(session_manager, 'get_market_status'):
                status = session_manager.get_market_status("china_a")
                is_open = (status.value == "open") if hasattr(status, 'value') else False
                if not is_open:
                    return 0.2
            if hasattr(session_manager, 'get_session_remaining_seconds'):
                remaining = session_manager.get_session_remaining_seconds("china_a") or 0
                if remaining < 900:
                    return 0.3
                elif remaining < 1800:
                    return 0.7
                return 0.8
        except:
            pass
        return 0.5

    def _get_volatility_regime(self, scanner) -> float:
        if scanner is None:
            return 0.5
        try:
            vol = scanner.get_market_volatility()
            if vol is None:
                return 0.5
            self._volatility_history.append(vol)
            if len(self._volatility_history) > 20:
                self._volatility_history.pop(0)
            if len(self._volatility_history) < 5:
                return 0.5
            recent = self._volatility_history[-5:]
            avg_vol = sum(recent) / len(recent)
            current_vol = recent[-1]
            if current_vol < avg_vol * 0.7:
                return 0.8
            elif current_vol > avg_vol * 1.3:
                return 0.3
            return 0.5
        except:
            return 0.5

    def _get_trade_density(self, scanner) -> float:
        if scanner is None:
            return 0.5
        try:
            market_data = scanner.get_last_data()
            if not market_data:
                return 0.5
            total_change = 0.0
            count = 0
            for code, md in market_data.items():
                if hasattr(md, 'change_pct') and md.change_pct != 0:
                    total_change += abs(md.change_pct)
                    count += 1
            if count == 0:
                return 0.5
            avg_change = total_change / count
            if avg_change < 0.5:
                return 0.4
            elif avg_change < 1.0:
                return 0.6
            elif avg_change < 2.0:
                return 0.8
            return 0.9
        except:
            return 0.5

    def _get_structure_break(self, scanner) -> float:
        if scanner is None:
            return 0.5
        try:
            summary = scanner.get_market_summary()
            phase = summary.get('us_trading_phase', 'closed')
            if phase == 'trading':
                return 0.8
            elif phase in ('pre_market', 'after_hours'):
                return 0.5
            return 0.3
        except:
            return 0.5


class RegimeEngine:
    """环境引擎 - 判断当前是"顺风"还是"逆风" """

    def __init__(self):
        self._trend_history: List[float] = []

    def compute(self, scanner=None, macro_signal: float = 0.5) -> float:
        trend = self._get_index_trend(scanner)
        liquidity = self._get_liquidity_signal(scanner, macro_signal)
        diffusion = self._get_sector_diffusion(scanner)

        regime = (
            trend * 0.4 +
            liquidity * 0.35 +
            diffusion * 0.25
        )

        return max(-1.0, min(1.0, regime))

    def _get_index_trend(self, scanner) -> float:
        if scanner is None:
            return 0.0
        try:
            market_data = scanner.get_last_data()
            if not market_data:
                return 0.0
            total_change = 0.0
            count = 0
            for code, md in market_data.items():
                if hasattr(md, 'change_pct') and md.change_pct != 0:
                    total_change += md.change_pct
                    count += 1
            if count == 0:
                return 0.0
            avg_change = total_change / count
            self._trend_history.append(avg_change)
            if len(self._trend_history) > 10:
                self._trend_history.pop(0)
            if avg_change > 1.0:
                return 1.0
            elif avg_change < -1.0:
                return -1.0
            return avg_change
        except:
            return 0.0

    def _get_liquidity_signal(self, scanner, macro_signal: float) -> float:
        if scanner is not None:
            try:
                adj = scanner.get_liquidity_adjustment("CHINA_A")
                if adj:
                    return adj.get("adjusted_signal", macro_signal) * 2 - 1
            except:
                pass
        return macro_signal * 2 - 1

    def _get_sector_diffusion(self, scanner) -> float:
        if scanner is None:
            return 0.0
        try:
            market_data = scanner.get_last_data()
            if not market_data:
                return 0.0
            advancing = 0
            declining = 0
            for code, md in market_data.items():
                if hasattr(md, 'change_pct'):
                    if md.change_pct > 0:
                        advancing += 1
                    elif md.change_pct < 0:
                        declining += 1
            total = advancing + declining
            if total == 0:
                return 0.0
            diffusion = (advancing - declining) / total
            return max(-1.0, min(1.0, diffusion))
        except:
            return 0.0


class ConfidenceEngine:
    """自信引擎 - 判断"策略是否适配当前市场" """

    def __init__(self):
        self._rolling_pnl_history: List[float] = []
        self._hit_rate_history: List[float] = []

    def compute(self, bandit_tracker=None) -> float:
        hit_rate = self._get_hit_rate(bandit_tracker)
        rolling_pnl = self._get_rolling_pnl(bandit_tracker)
        bandit_conf = self._get_bandit_confidence(bandit_tracker)

        confidence = (
            hit_rate * 0.4 +
            min(max(rolling_pnl / 10, 0), 1.0) * 0.3 +
            bandit_conf * 0.3
        )

        return max(0.0, min(1.5, confidence))

    def _get_hit_rate(self, tracker) -> float:
        if tracker is None:
            return 0.5
        try:
            history = tracker.get_position_history(limit=20)
            if not history:
                return 0.5
            wins = sum(1 for r in history if r.get('return_pct', 0) > 0)
            hit_rate = wins / len(history)
            self._hit_rate_history.append(hit_rate)
            if len(self._hit_rate_history) > 10:
                self._hit_rate_history.pop(0)
            recent_avg = sum(self._hit_rate_history) / len(self._hit_rate_history)
            return recent_avg
        except:
            return 0.5

    def _get_rolling_pnl(self, tracker) -> float:
        if tracker is None:
            return 0.0
        try:
            history = tracker.get_position_history(limit=10)
            if not history:
                return 0.0
            total_pnl = sum(r.get('return_pct', 0) for r in history)
            return total_pnl
        except:
            return 0.0

    def _get_bandit_confidence(self, tracker) -> float:
        if tracker is None:
            return 0.5
        try:
            stats = tracker.get_strategy_summary("default")
            total_trades = stats.get('total_trades', 0)
            if total_trades < 5:
                return 0.3
            elif total_trades < 20:
                return 0.5
            elif total_trades < 50:
                return 0.7
            return 0.9
        except:
            return 0.5


class RiskEngine:
    """风险引擎 - 判断"还能承受多少波动" """

    def __init__(self):
        self._drawdown_history: List[float] = []

    def compute(self, portfolio=None, scanner=None) -> float:
        cash_ratio = self._get_cash_ratio(portfolio)
        drawdown = self._get_drawdown(portfolio)
        volatility = self._get_current_volatility(scanner)

        base_T = 1.0 + (1.0 - cash_ratio) * 0.5

        if drawdown > 0.1:
            base_T *= 1.3
        elif drawdown > 0.05:
            base_T *= 1.1

        if volatility > 2.0:
            base_T *= 1.2
        elif volatility > 1.5:
            base_T *= 1.1

        return max(0.5, min(2.0, base_T))

    def _get_cash_ratio(self, portfolio) -> float:
        if portfolio is None:
            return 0.5
        try:
            summary = portfolio.get_summary()
            available = summary.get('available_capital', 0)
            total = summary.get('total_capital', 1)
            return available / max(total, 1)
        except:
            return 0.5

    def _get_drawdown(self, portfolio) -> float:
        if portfolio is None:
            return 0.0
        try:
            summary = portfolio.get_summary()
            return_pct = abs(summary.get('total_return', 0))
            self._drawdown_history.append(return_pct)
            if len(self._drawdown_history) > 10:
                self._drawdown_history.pop(0)
            return sum(self._drawdown_history) / len(self._drawdown_history) if self._drawdown_history else 0.0
        except:
            return 0.0

    def _get_current_volatility(self, scanner) -> float:
        if scanner is None:
            return 1.0
        try:
            vol = scanner.get_market_volatility()
            return vol if vol else 1.0
        except:
            return 1.0


class MetaManas:
    """观照层 - 觉知末那识正在"执" """

    def __init__(self):
        self.bias_state = BiasState.NEUTRAL
        self._pnl_trend: List[float] = []
        self._decision_aggressiveness: List[float] = []

    def detect_and_correct(
        self,
        manas_score: float,
        recent_pnl: List[float],
        decision_aggressiveness: float
    ) -> tuple[BiasState, float]:
        self._pnl_trend.extend(recent_pnl)
        if len(self._pnl_trend) > 20:
            self._pnl_trend = self._pnl_trend[-20:]

        self._decision_aggressiveness.append(decision_aggressiveness)
        if len(self._decision_aggressiveness) > 10:
            self._decision_aggressiveness.pop(0)

        if len(self._pnl_trend) < 5:
            return BiasState.NEUTRAL, 1.0

        recent_avg = sum(self._pnl_trend[-5:]) / 5
        overall_avg = sum(self._pnl_trend) / len(self._pnl_trend)
        avg_aggressiveness = sum(self._decision_aggressiveness) / len(self._decision_aggressiveness)

        greed_detected = (
            recent_avg > 0.05 and
            overall_avg > 0.03 and
            avg_aggressiveness > 0.6
        )

        fear_detected = (
            recent_avg < -0.03 and
            len([p for p in self._pnl_trend[-5:] if p < 0]) >= 3
        )

        if greed_detected and self.bias_state != BiasState.GREED:
            self.bias_state = BiasState.GREED
            log.warning("[MetaManas] 检测到贪bias，开始纠偏")
            return BiasState.GREED, 0.7

        if fear_detected and self.bias_state != BiasState.FEAR:
            self.bias_state = BiasState.FEAR
            log.warning("[MetaManas] 检测到惧bias，开始纠偏")
            return BiasState.FEAR, 0.5

        if abs(recent_avg) < 0.02 and self.bias_state != BiasState.NEUTRAL:
            self.bias_state = BiasState.NEUTRAL
            return BiasState.NEUTRAL, 1.0

        if self.bias_state == BiasState.GREED:
            return BiasState.GREED, 0.7
        elif self.bias_state == BiasState.FEAR:
            return BiasState.FEAR, 0.8

        return BiasState.NEUTRAL, 1.0

    def record_pnl(self, pnl_pct: float):
        """记录盈亏（用于偏差检测）"""
        self._pnl_trend.append(pnl_pct)
        if len(self._pnl_trend) > 20:
            self._pnl_trend.pop(0)


class TianShiResponse:
    """天时响应 - 感受天时，顺势而为 """

    def __init__(self):
        self._market_open_history: deque = deque(maxlen=20)
        self._volatility_history: deque = deque(maxlen=20)
        self._trend_history: deque = deque(maxlen=20)

    def evaluate(self, market_state: Dict[str, Any]) -> float:
        tian_shi = 0.5

        if market_state.get("is_market_open", False):
            tian_shi += 0.2
        else:
            tian_shi -= 0.2

        volatility = market_state.get("volatility", 1.0)
        if 0.5 <= volatility <= 1.5:
            tian_shi += 0.1

        trend = market_state.get("trend_strength", 0.0)
        if abs(trend) > 0.3:
            tian_shi += trend * 0.2

        time_of_day = market_state.get("time_of_day", 0)
        if 9.5 <= time_of_day <= 10.5:
            tian_shi += 0.1
        elif 14.0 <= time_of_day <= 15.0:
            tian_shi += 0.15

        return max(0.0, min(1.0, tian_shi))


class RegimeHarmony:
    """环境和谐 - 与市场环境合一，不强求 """

    def __init__(self):
        self._regime_history: deque = deque(maxlen=30)
        self._current_regime = "unknown"

    def evaluate(
        self,
        current_regime: str,
        regime_stability: float,
        market_breadth: float
    ) -> tuple[float, HarmonyState]:
        self._regime_history.append({
            "regime": current_regime,
            "timestamp": time.time()
        })

        if len(self._regime_history) >= 5:
            recent_regimes = [h["regime"] for h in list(self._regime_history)[-5:]]
            stability = len(set(recent_regimes)) / 5.0
        else:
            stability = 1.0

        harmony = regime_stability * 0.5 + stability * 0.3 + abs(market_breadth) * 0.2

        if harmony > 0.7:
            state = HarmonyState.RESONANCE
        elif harmony < 0.4:
            state = HarmonyState.RESISTANCE
        else:
            state = HarmonyState.NEUTRAL

        return harmony, state


class RenShiResponse:
    """人时响应 - 感知自身的状态 """

    def __init__(self):
        self._recent_decisions: deque = deque(maxlen=20)
        self._recent_outcomes: deque = deque(maxlen=20)

    def evaluate(
        self,
        confidence: float,
        risk_appetite: float,
        recent_success_rate: float
    ) -> float:
        base = confidence

        confidence_boost = (confidence - 0.5) * 0.2
        risk_factor = (risk_appetite - 0.5) * 0.1
        success_factor = (recent_success_rate - 0.5) * 0.3

        ren_shi = base + confidence_boost + risk_factor + success_factor

        if len(self._recent_decisions) > 0:
            recent_aggression = sum(1 for d in list(self._recent_decisions)[-5:]
                                   if d.get("action", "hold") != "hold")
            if recent_aggression >= 4:
                ren_shi *= 0.8

        return max(0.0, min(1.0, ren_shi))


class PortfolioAnalyzer:
    """持仓分析 - 检测止盈/止损/再平衡信号 """

    def __init__(self):
        self._portfolio_history: deque = deque(maxlen=10)
        self._stock_sector_map = None

    def _get_sector_map(self):
        """获取板块映射（延迟加载）"""
        if self._stock_sector_map is None:
            try:
                from deva.naja.bandit.stock_sector_map import get_stock_sector_map
                self._stock_sector_map = get_stock_sector_map()
            except ImportError:
                return None
        return self._stock_sector_map

    def enrich_positions(self, positions: List[Dict]) -> List[Dict]:
        """丰富持仓数据，添加板块信息"""
        sector_map = self._get_sector_map()
        if not sector_map or not positions:
            return positions

        enriched = []
        for pos in positions:
            pos_copy = pos.copy()
            sector_map.enrich_position(pos_copy)
            enriched.append(pos_copy)
        return enriched

    def analyze(
        self,
        portfolio_data: Dict[str, Any]
    ) -> tuple[PortfolioSignal, float, float, Dict[str, Any]]:
        """
        分析持仓状态

        Returns:
            (signal, loss_pct, concentration, enriched_data)
        """
        if not portfolio_data:
            return PortfolioSignal.NONE, 0.0, 0.0, {}

        self._portfolio_history.append(portfolio_data)

        positions = portfolio_data.get("position_details", [])
        sector_map = self._get_sector_map()

        enriched_positions = self.enrich_positions(positions)

        total_return = portfolio_data.get("total_return", 0.0)
        cash_ratio = portfolio_data.get("cash_ratio", 0.5)
        concentration = portfolio_data.get("concentration", 0.0)
        held_symbols = portfolio_data.get("held_symbols", [])

        sector_alloc = self._calculate_sector_allocation(enriched_positions)
        sector_performance = portfolio_data.get("sector_performance", {})

        enriched_data = {
            "positions": enriched_positions,
            "sector_alloc": sector_alloc,
            "sector_performance": sector_performance,
            "total_return": total_return,
            "cash_ratio": cash_ratio,
            "concentration": concentration,
        }

        stop_loss_threshold = -0.05
        take_profit_threshold = 0.12
        rebalance_threshold = 0.15

        signal = PortfolioSignal.NONE

        if total_return < stop_loss_threshold:
            signal = PortfolioSignal.STOP_LOSS
        elif total_return > take_profit_threshold:
            signal = PortfolioSignal.TAKE_PROFIT
        elif concentration > 0.5 and len(held_symbols) >= 3:
            signal = PortfolioSignal.REBALANCE
        elif cash_ratio > 0.4 and total_return > 0:
            signal = PortfolioSignal.ACCUMULATE

        return signal, total_return, concentration, enriched_data

    def _calculate_sector_allocation(self, positions: List[Dict]) -> Dict[str, float]:
        """计算板块配置"""
        sector_map = self._get_sector_map()
        if not sector_map or not positions:
            return {}

        return sector_map.get_portfolio_sector_alloc(positions)

    def analyze_sector_risk(
        self,
        enriched_positions: List[Dict],
        sector_performance: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        分析板块风险

        Returns:
            包含板块风险评估的字典
        """
        if not enriched_positions or not sector_performance:
            return {}

        sector_losses: Dict[str, float] = {}
        sector_weights: Dict[str, float] = {}
        total_value = 0.0

        for pos in enriched_positions:
            value = pos.get('current', 0) * pos.get('qty', 0)
            sector = pos.get('sector', 'other')

            sector_weights[sector] = sector_weights.get(sector, 0) + value
            total_value += value

            sector_return = pos.get('return_pct', 0)
            if sector not in sector_losses:
                sector_losses[sector] = []
            sector_losses[sector].append(sector_return)

        if total_value == 0:
            return {}

        sector_risk = {}
        for sector, weight in sector_weights.items():
            sector_risk[sector] = {
                'weight': weight / total_value,
                'performance': sector_performance.get(sector, 0),
                'avg_return': sum(sector_losses[sector]) / len(sector_losses[sector]) if sector_losses[sector] else 0,
            }

        worst_sector = min(sector_risk.items(), key=lambda x: x[1]['performance'])
        best_sector = max(sector_risk.items(), key=lambda x: x[1]['performance'])

        return {
            'sector_risk': sector_risk,
            'worst_sector': worst_sector[0] if worst_sector else None,
            'best_sector': best_sector[0] if best_sector else None,
            'diversification_score': len(sector_risk) / 5.0,
        }

    def is_market_deterioration(self, regime_score: float, volatility: float) -> bool:
        """判断市场是否恶化"""
        return regime_score < -0.3 or volatility > 1.5

    def is_market_improvement(self, regime_score: float, volatility: float) -> bool:
        """判断市场是否好转"""
        return regime_score > 0.3 and volatility < 1.0


class UnifiedManas:
    """
    统一末那识

    整合 ManasEngine 和 AdaptiveManas 的功能，同时服务：
    1. AttentionKernel - 用它的 manas_score 塑造 Q
    2. AwakenedAlaya - 用它的 harmony_state 触发顿悟

    使用方式：
        manas = UnifiedManas()
        output = manas.compute(
            session_manager=session_mgr,
            portfolio_data=portfolio_data,
            scanner=scanner,
            bandit_tracker=bandit_tracker,
            market_state=market_state
        )
    """

    WEIGHT_TIMING = 0.4
    WEIGHT_REGIME = 0.3
    WEIGHT_CONFIDENCE = 0.3
    ACTION_THRESHOLD = 0.5

    def __init__(self):
        self.timing_engine = TimingEngine()
        self.regime_engine = RegimeEngine()
        self.confidence_engine = ConfidenceEngine()
        self.risk_engine = RiskEngine()
        self.meta_manas = MetaManas()

        self.tian_shi = TianShiResponse()
        self.regime_harmony = RegimeHarmony()
        self.ren_shi = RenShiResponse()
        self.portfolio_analyzer = PortfolioAnalyzer()

        self.event_recall = PortfolioDrivenEventRecall()
        self.feedback_loop = ManasFeedbackLoop()

        self._last_output: Optional[UnifiedManasOutput] = None
        self._last_update = 0.0
        self._update_interval = 1.0

        self._recent_pnl: List[float] = []

    def compute(
        self,
        session_manager=None,
        portfolio_data: Optional[Dict[str, Any]] = None,
        scanner=None,
        bandit_tracker=None,
        macro_signal: float = 0.5,
        market_state: Optional[Dict[str, Any]] = None,
    ) -> UnifiedManasOutput:
        """
        计算统一末那识输出

        Args:
            session_manager: TradingClock/MarketSessionManager
            portfolio_data: 持仓数据
                - held_symbols: List[str]
                - position_details: [{symbol, weight, return_pct, ...}]
                - sector_allocations: {sector: weight}
                - total_return: float
                - profit_loss: float
                - cash_ratio: float
                - concentration: float
            scanner: GlobalMarketScanner
            bandit_tracker: BanditPositionTracker
            macro_signal: 宏观流动性信号
            market_state: 市场状态（用于天时响应）

        Returns:
            UnifiedManasOutput
        """
        current_time = time.time()
        if current_time - self._last_update < self._update_interval and self._last_output is not None:
            return self._last_output

        timing_score = self.timing_engine.compute(session_manager, scanner)
        regime_score = self.regime_engine.compute(scanner, macro_signal)
        confidence_score = self.confidence_engine.compute(bandit_tracker)
        risk_temperature = self.risk_engine.compute(
            portfolio_data, scanner
        )

        portfolio_signal, portfolio_loss, concentration, enriched_data = self.portfolio_analyzer.analyze(
            portfolio_data or {}
        )

        enriched_positions = enriched_data.get("positions", [])
        sector_alloc = enriched_data.get("sector_alloc", {})

        if market_state:
            market_deterioration = market_state.get("deterioration", False)
            market_improvement = market_state.get("improvement", False)
        else:
            market_deterioration = self.portfolio_analyzer.is_market_deterioration(
                regime_score, risk_temperature
            )
            market_improvement = self.portfolio_analyzer.is_market_improvement(
                regime_score, risk_temperature
            )

        raw_manas = (
            self.WEIGHT_TIMING * timing_score +
            self.WEIGHT_REGIME * (regime_score + 1) / 2 +
            self.WEIGHT_CONFIDENCE * confidence_score
        )

        bias_state, bias_correction = self.meta_manas.detect_and_correct(
            raw_manas,
            self._recent_pnl,
            raw_manas
        )

        manas_score = raw_manas * bias_correction
        manas_score = max(0.0, min(1.0, manas_score))

        attention_focus = self._determine_attention_focus(
            portfolio_signal, portfolio_loss, market_deterioration, manas_score
        )

        tian_score = 0.5
        if market_state:
            tian_score = self.tian_shi.evaluate(market_state)

        harmony, harmony_state = self.regime_harmony.evaluate(
            "trend" if regime_score > 0 else "reverse",
            abs(regime_score),
            regime_score
        )

        ren_score = self.ren_shi.evaluate(
            confidence_score,
            1.0 / risk_temperature,
            self._get_recent_success_rate()
        )

        harmony_strength = (tian_score * 0.4 + harmony * 0.35 + ren_score * 0.25)

        should_act = manas_score > self.ACTION_THRESHOLD
        if harmony_state == HarmonyState.RESISTANCE:
            should_act = False
        elif harmony_state == HarmonyState.RESONANCE:
            should_act = harmony_strength > 0.4

        action_type = self._determine_action_type(
            should_act, harmony_state, tian_score
        )

        alpha = confidence_score * manas_score * bias_correction
        alpha = max(0.3, min(1.5, alpha))

        reason = self._generate_reason(
            timing_score, regime_score, confidence_score,
            bias_state, harmony_state, portfolio_signal
        )

        sector_risk = self.portfolio_analyzer.analyze_sector_risk(
            enriched_positions, market_state.get("sector_performance", {}) if market_state else {}
        )

        output = UnifiedManasOutput(
            manas_score=manas_score,
            timing_score=timing_score,
            regime_score=regime_score,
            confidence_score=confidence_score,
            risk_temperature=risk_temperature,
            attention_focus=attention_focus,
            alpha=alpha,
            harmony_state=harmony_state,
            harmony_strength=harmony_strength,
            action_type=action_type,
            should_act=should_act,
            bias_state=bias_state,
            bias_correction=bias_correction,
            portfolio_signal=portfolio_signal,
            portfolio_loss_pct=portfolio_loss,
            market_deterioration=market_deterioration,
            sector_alloc=sector_alloc,
            enriched_positions=enriched_positions,
            worst_sector=sector_risk.get("worst_sector", ""),
            best_sector=sector_risk.get("best_sector", ""),
            reason=reason,
        )

        self._last_output = output
        self._last_update = current_time

        return output

    def _determine_attention_focus(
        self,
        portfolio_signal: PortfolioSignal,
        portfolio_loss: float,
        market_deterioration: bool,
        manas_score: float
    ) -> AttentionFocus:
        """确定注意力聚焦类型"""
        if portfolio_signal == PortfolioSignal.STOP_LOSS:
            return AttentionFocus.STOP_LOSS
        if portfolio_signal == PortfolioSignal.TAKE_PROFIT:
            return AttentionFocus.TAKE_PROFIT
        if portfolio_signal == PortfolioSignal.REBALANCE:
            return AttentionFocus.REBALANCE
        if portfolio_signal == PortfolioSignal.ACCUMULATE:
            return AttentionFocus.ACCUMULATE

        if market_deterioration and manas_score < 0.4:
            return AttentionFocus.STOP_LOSS

        if manas_score > 0.7:
            return AttentionFocus.ACCUMULATE

        return AttentionFocus.WATCH

    def _determine_action_type(
        self,
        should_act: bool,
        harmony_state: HarmonyState,
        tian_score: float
    ) -> ActionType:
        """确定行动类型"""
        if not should_act:
            return ActionType.HOLD

        if harmony_state == HarmonyState.RESONANCE and tian_score > 0.7:
            return ActionType.ACT_FULLY
        elif harmony_state == HarmonyState.NEUTRAL:
            return ActionType.ACT_CAREFULLY
        else:
            return ActionType.ACT_MINIMALLY

    def _generate_reason(
        self,
        timing: float,
        regime: float,
        confidence: float,
        bias: BiasState,
        harmony: HarmonyState,
        portfolio_signal: PortfolioSignal
    ) -> str:
        """生成决策原因"""
        reasons = []

        if timing < 0.3:
            reasons.append("时机不佳")
        elif timing > 0.7:
            reasons.append("时机成熟")

        if regime < -0.3:
            reasons.append("逆风环境")
        elif regime > 0.3:
            reasons.append("顺风环境")

        if confidence > 0.8:
            reasons.append("策略自信")
        elif confidence < 0.4:
            reasons.append("策略不自信")

        if bias == BiasState.GREED:
            reasons.append("⚠️检测到贪")
        elif bias == BiasState.FEAR:
            reasons.append("⚠️检测到惧")

        if harmony == HarmonyState.RESONANCE:
            reasons.append("与势共振")
        elif harmony == HarmonyState.RESISTANCE:
            reasons.append("与势相抗")

        if portfolio_signal != PortfolioSignal.NONE:
            reasons.append(f"持仓信号:{portfolio_signal.value}")

        return " | ".join(reasons)

    def _get_recent_success_rate(self) -> float:
        if not self._recent_pnl:
            return 0.5
        recent = list(self._recent_pnl)[-10:]
        if not recent:
            return 0.5
        wins = sum(1 for p in recent if p > 0)
        return wins / len(recent)

    def record_pnl(self, pnl_pct: float):
        """记录盈亏（用于 MetaManas 偏差检测）"""
        self._recent_pnl.append(pnl_pct)
        if len(self._recent_pnl) > 20:
            self._recent_pnl.pop(0)
        self.meta_manas.record_pnl(pnl_pct)

    def record_feedback(
        self,
        outcome: Dict[str, Any],
        market_data: Optional[Dict[str, Any]] = None
    ):
        """记录反馈到闭环"""
        if self._last_output is None:
            return

        recalled_events = self.event_recall.recall(
            attention_focus=self._last_output.attention_focus.value,
            portfolio_state=outcome.get("portfolio_state", {}),
            market_data=market_data or {},
            limit=5
        )

        self.feedback_loop.record(
            attention_focus=self._last_output.attention_focus.value,
            harmony_state=self._last_output.harmony_state.value,
            recalled_event_count=len(recalled_events),
            outcome=outcome,
            market_data=market_data or {}
        )

    def recall_events(
        self,
        portfolio_data: Optional[Dict[str, Any]] = None,
        market_data: Optional[Dict[str, Any]] = None
    ) -> List[RecalledEvent]:
        """召回与当前 attention_focus 相关的事件"""
        if self._last_output is None:
            return []

        enriched_state = {
            **(portfolio_data or {}),
            "sector_alloc": self._last_output.sector_alloc,
            "enriched_positions": self._last_output.enriched_positions,
            "sector_performance": market_data.get("sector_performance", {}) if market_data else {},
        }

        holdings = {}
        for pos in self._last_output.enriched_positions:
            code = pos.get('code', '')
            if code:
                holdings[code] = {
                    'weight': pos.get('weight', 0),
                    'sector': pos.get('sector', ''),
                    'return_pct': pos.get('return_pct', 0),
                }
        enriched_state["holdings"] = holdings

        return self.event_recall.recall(
            attention_focus=self._last_output.attention_focus.value,
            portfolio_state=enriched_state,
            market_data=market_data or {},
            limit=10
        )

    def get_state(self) -> Dict[str, Any]:
        """获取状态"""
        if self._last_output is None:
            return {"status": "not_initialized"}

        return {
            "output": self._last_output.to_dict(),
            "stats": {
                "event_recall": self.event_recall.get_stats(),
                "feedback_loop": self.feedback_loop.get_stats(),
            }
        }

    def reset_bias(self):
        """重置偏差状态"""
        self.meta_manas.bias_state = BiasState.NEUTRAL
        log.info("[UnifiedManas] 偏差状态已重置")