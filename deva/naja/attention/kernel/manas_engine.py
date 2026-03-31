"""
ManasEngine - 末那识引擎

一个持续输出"是否行动"的内在决策中枢

核心职责：
    • 要不要看（注意力方向 Q）
    • 要不要信（置信度 α）
    • 要不要上（仓位 T）
    • 要不要停（风险）

================================================================================
架构
================================================================================

ManasEngine
    ├── TimingEngine（时机节律）
    │   └── 判断市场"能不能动"
    │       - 波动率变化
    │       - 成交密度
    │       - 结构断裂
    │
    ├── RegimeEngine（环境感）
    │   └── 判断当前是"顺风"还是"逆风"
    │       - 指数趋势
    │       - 流动性指标
    │       - 板块扩散
    │
    ├── ConfidenceEngine（自信）
    │   └── 判断"策略是否适配当前市场"
    │       - rolling pnl
    │       - recent hit rate
    │       - bandit 权重
    │
    ├── RiskEngine（生存本能）
    │   └── 判断"还能承受多少波动"
    │       - 当前仓位
    │       - 回撤
    │       - 波动率
    │
    ├── MetaManas（观照层）
    │   └── 觉知末那识正在"执"
    │       - 偏差检测（连赢=贪，连亏=惧）
    │       - 纠偏机制
    │
    └── ManasScore（统一判断）
        └── 合一输出：manas_score ∈ [0, 1]

================================================================================
公式
================================================================================

manas_score = 0.4 * timing + 0.3 * regime + 0.3 * confidence

然后：
    • Action Gate: manas_score > threshold → allow_trade
    • Q = market_state * manas_score
    • α = base_alpha * confidence * manas_score
    • T = base_T / (1 + manas_score)

偏差纠偏：
    • 连赢 → reduce α, increase T → 防贪
    • 连亏 → reduce T, keep α → 防惧
"""

import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


class BiasState(Enum):
    """偏差状态"""
    NEUTRAL = "neutral"
    GREED = "greed"
    FEAR = "fear"


@dataclass
class ManasOutput:
    """末那识输出"""
    manas_score: float = 0.5
    timing_score: float = 0.5
    regime_score: float = 0.0
    confidence_score: float = 0.5
    risk_temperature: float = 1.0

    should_act: bool = False
    action_gate_reason: str = ""

    bias_state: BiasState = BiasState.NEUTRAL
    bias_correction: float = 1.0

    alpha: float = 1.0
    attention_focus: float = 1.0

    narrative_risk: float = 0.5
    hot_narratives: List[Tuple[str, float]] = field(default_factory=list)
    supply_chain_risk_level: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manas_score": self.manas_score,
            "timing_score": self.timing_score,
            "regime_score": self.regime_score,
            "confidence_score": self.confidence_score,
            "risk_temperature": self.risk_temperature,
            "should_act": self.should_act,
            "action_gate_reason": self.action_gate_reason,
            "bias_state": self.bias_state.value,
            "bias_correction": self.bias_correction,
            "alpha": self.alpha,
            "attention_focus": self.attention_focus,
            "narrative_risk": self.narrative_risk,
            "hot_narratives": self.hot_narratives,
            "supply_chain_risk_level": self.supply_chain_risk_level,
        }


class TimingEngine:
    """
    时机引擎 - 判断市场"能不能动"

    输出 timing_score ∈ [0, 1]
    0 = 不宜动
    1 = 可以出手
    """

    def __init__(self):
        self._last_volatility = 0.0
        self._volatility_history: List[float] = []
        self._trade_density_history: List[float] = []

    def compute(self, session_manager=None, scanner=None) -> float:
        """
        计算时机分数

        Args:
            session_manager: TradingClock/MarketSessionManager
            scanner: GlobalMarketScanner

        Returns:
            timing_score ∈ [0, 1]
        """
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
        """获取时间压力"""
        if session_manager is None:
            try:
                from deva.naja.radar.trading_clock import get_trading_clock
                session_manager = get_trading_clock()
            except ImportError:
                return 0.5

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
        """获取波动率状态"""
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
        """获取成交密度"""
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
        """检测结构断裂"""
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
    """
    环境引擎 - 判断当前是"顺风"还是"逆风"

    输出 regime_score ∈ [-1, 1]
    -1 = 强逆风
    +1 = 强顺风
    """

    def __init__(self):
        self._trend_history: List[float] = []

    def compute(self, scanner=None, macro_signal: float = 0.5) -> float:
        """
        计算宏观环境分数

        Args:
            scanner: GlobalMarketScanner
            macro_signal: 宏观流动性信号

        Returns:
            regime_score ∈ [-1, 1]
        """
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
        """获取指数趋势"""
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
        """获取流动性信号"""
        if scanner is not None:
            try:
                adj = scanner.get_liquidity_adjustment("CHINA_A")
                if adj:
                    return adj.get("adjusted_signal", macro_signal) * 2 - 1
            except:
                pass

        return macro_signal * 2 - 1

    def _get_sector_diffusion(self, scanner) -> float:
        """获取板块扩散程度"""
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
    """
    自信引擎 - 判断"策略是否适配当前市场"

    输出 confidence ∈ [0, 1.5]
    """

    def __init__(self):
        self._rolling_pnl_history: List[float] = []
        self._hit_rate_history: List[float] = []

    def compute(self, bandit_tracker=None) -> float:
        """
        计算策略自信度

        Args:
            bandit_tracker: BanditPositionTracker

        Returns:
            confidence ∈ [0, 1.5]
        """
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
        """获取近期命中率"""
        if tracker is None:
            try:
                from deva.naja.bandit import get_bandit_tracker
                tracker = get_bandit_tracker()
            except ImportError:
                return 0.5

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
        """获取 rolling 盈亏"""
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
        """获取 bandit 置信度"""
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
    """
    风险引擎 - 判断"还能承受多少波动"

    输出 temperature ∈ (0, 2]
    T 大 = 更保守
    T 小 = 更激进
    """

    def __init__(self):
        self._drawdown_history: List[float] = []

    def compute(self, portfolio=None, scanner=None) -> float:
        """
        计算风险温度

        Args:
            portfolio: VirtualPortfolio
            scanner: GlobalMarketScanner

        Returns:
            temperature ∈ (0, 2]
        """
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
        """获取现金比例"""
        if portfolio is None:
            try:
                from deva.naja.bandit import get_virtual_portfolio
                portfolio = get_virtual_portfolio()
            except ImportError:
                return 0.5

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
        """获取当前回撤"""
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
        """获取当前市场波动率"""
        if scanner is None:
            return 1.0

        try:
            vol = scanner.get_market_volatility()
            return vol if vol else 1.0
        except:
            return 1.0


class MetaManas:
    """
    观照层 - 觉知末那识正在"执"

    检测偏差：
        • 连赢 → 越来越激进 → 标记"贪"
        • 连亏 → 完全不动 → 标记"惧"

    纠偏：
        • 贪时 → reduce α, increase T
        • 恐时 → keep α, moderate T
    """

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
        """
        检测偏差并纠偏

        Args:
            manas_score: 原始 manas 分数
            recent_pnl: 最近 N 笔交易的盈亏列表
            decision_aggressiveness: 最近的决策激进程度

        Returns:
            tuple: (bias_state, bias_correction)
        """
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


class NarrativeSupplyChainEngine:
    """
    叙事供应链引擎 - 觉知市场叙事的供应链风险

    整合 NarrativeSupplyChainLinker 到末那识决策中

    功能：
        • 跟踪叙事重要性变化
        • 检测供应链风险事件
        • 计算叙事风险因子
        • 联动叙事-供应链关注度
    """

    def __init__(self):
        self._linker = None
        self._narrative_importance_history: Dict[str, List[float]] = {}
        self._risk_alert_threshold = 2.0
        self._last_risk_check = 0.0
        self._check_interval = 60.0

    def _get_linker(self):
        """懒加载联动器"""
        if self._linker is None:
            try:
                from deva.naja.cognition import get_supply_chain_linker
                self._linker = get_supply_chain_linker()
            except ImportError:
                log.warning("[NarrativeSupplyChainEngine] 无法导入 NarrativeSupplyChainLinker")
                return None
        return self._linker

    def compute(self, narratives: List[str] = None) -> float:
        """
        计算叙事供应链风险因子

        Args:
            narratives: 当前关注的叙事主题列表

        Returns:
            risk_factor ∈ [0, 1], 1 = 高风险
        """
        linker = self._get_linker()
        if linker is None:
            return 0.5

        if narratives is None:
            narratives = []

        risk_scores = []
        high_risk_stocks = set()

        for narrative in narratives:
            summary = linker.get_supply_chain_for_narrative(narrative)

            if summary.get('total_risk') == 'HIGH':
                risk_scores.append(0.8)
                high_risk_stocks.update(summary.get('high_risk_stocks', []))
            elif summary.get('total_risk') == 'MEDIUM':
                risk_scores.append(0.5)
            else:
                risk_scores.append(0.2)

            importance = summary.get('importance', 1.0)
            if importance > 2.0:
                risk_scores.append(0.7)
            elif importance > 1.5:
                risk_scores.append(0.5)

        if not risk_scores:
            return 0.5

        avg_risk = sum(risk_scores) / len(risk_scores)

        recent_events = linker.get_recent_events(limit=5)
        if recent_events:
            latest_event = recent_events[-1]
            if latest_event.risk_level.value in ['high', 'critical']:
                avg_risk = min(1.0, avg_risk * 1.3)

        return max(0.0, min(1.0, avg_risk))

    def get_hot_narratives(self, top_n: int = 5) -> List[Tuple[str, float]]:
        """
        获取当前最热的叙事主题

        Args:
            top_n: 返回前 N 个

        Returns:
            [(narrative, importance), ...]
        """
        linker = self._get_linker()
        if linker is None:
            return []
        return linker.get_hot_narratives(top_n)

    def on_risk_event(self, stock_code: str, description: str):
        """
        记录供应链风险事件

        Args:
            stock_code: 出问题的股票代码
            description: 事件描述
        """
        linker = self._get_linker()
        if linker is None:
            return

        event = linker.on_stock_risk_event(stock_code, description)
        log.info(f"[NarrativeSupplyChainEngine] 风险事件: {event.description} "
                f"风险等级: {event.risk_level.value} 关联叙事: {event.narratives}")

    def on_narrative_boost(self, narrative: str, boost_factor: float = 1.5):
        """
        提升叙事重要性

        Args:
            narrative: 叙事主题
            boost_factor: 提升因子
        """
        linker = self._get_linker()
        if linker is None:
            return

        linker.on_narrative_boost(narrative, boost_factor)

    def get_risk_attention_focus(self, current_focus: Dict[str, float]) -> Dict[str, float]:
        """
        根据供应链风险调整注意力焦点

        Args:
            current_focus: 原始注意力焦点

        Returns:
            调整后的注意力焦点
        """
        linker = self._get_linker()
        if linker is None:
            return current_focus

        adjusted = dict(current_focus)

        for narrative in list(adjusted.keys()):
            weighted_stocks = linker.get_related_stocks_with_weight(narrative)
            if weighted_stocks:
                for stock_code, weight in weighted_stocks:
                    risk_report = linker.get_supply_chain_risk_report(stock_code)
                    if risk_report and risk_report.overall_risk_level == 'HIGH':
                        adjusted[narrative] = adjusted[narrative] * 0.8
                        break

        return adjusted


class ManasEngine:
    """
    末那识引擎 - 核心决策中枢

    统一四个引擎的输出，生成最终的 manas_score

    使用方式：
        manas = ManasEngine()
        output = manas.compute(
            session_manager=session_mgr,
            portfolio=portfolio,
            scanner=scanner,
            bandit_tracker=bandit_tracker
        )

        # output.manas_score: 综合分数
        # output.should_act: 是否行动
        # output.alpha: 置信度因子
        # output.risk_temperature: 风险温度
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
        self.narrative_supply_chain_engine = NarrativeSupplyChainEngine()

        self._last_output: Optional[ManasOutput] = None
        self._last_update = 0.0
        self._update_interval = 1.0
        self._current_narratives: List[str] = []
        self._recent_pnl: List[float] = []

    def set_narratives(self, narratives: List[str]):
        """
        设置当前关注的叙事主题

        Args:
            narratives: 叙事主题列表
        """
        self._current_narratives = narratives

    def compute(
        self,
        session_manager=None,
        portfolio=None,
        scanner=None,
        bandit_tracker=None,
        macro_signal: float = 0.5,
        narratives: List[str] = None,
    ) -> ManasOutput:
        """
        计算末那识输出

        Args:
            session_manager: TradingClock/MarketSessionManager
            portfolio: VirtualPortfolio
            scanner: GlobalMarketScanner
            bandit_tracker: BanditPositionTracker
            macro_signal: 宏观流动性信号
            narratives: 当前叙事主题列表（从 NarrativeTracker 获取）

        Returns:
            ManasOutput: 末那识决策输出
        """
        current_time = time.time()
        if current_time - self._last_update < self._update_interval and self._last_output is not None:
            return self._last_output

        if narratives is not None:
            self._current_narratives = narratives

        timing_score = self.timing_engine.compute(session_manager, scanner)
        regime_score = self.regime_engine.compute(scanner, macro_signal)
        confidence_score = self.confidence_engine.compute(bandit_tracker)
        risk_temperature = self.risk_engine.compute(portfolio, scanner)

        narrative_risk = self.narrative_supply_chain_engine.compute(self._current_narratives)

        raw_manas = (
            self.WEIGHT_TIMING * timing_score +
            self.WEIGHT_REGIME * (regime_score + 1) / 2 +
            self.WEIGHT_CONFIDENCE * confidence_score
        )

        if narrative_risk > 0.6:
            raw_manas *= (1.0 - (narrative_risk - 0.6) * 0.5)

        bias_state, bias_correction = self.meta_manas.detect_and_correct(
            raw_manas,
            self._recent_pnl,
            raw_manas
        )

        manas_score = raw_manas * bias_correction
        manas_score = max(0.0, min(1.0, manas_score))

        should_act = manas_score > self.ACTION_THRESHOLD

        alpha = confidence_score * manas_score * bias_correction
        alpha = max(0.3, min(1.5, alpha))

        attention_focus = manas_score * bias_correction

        reason = self._get_gate_reason(manas_score, timing_score, regime_score, confidence_score, bias_state)

        hot_narratives = self.narrative_supply_chain_engine.get_hot_narratives(5)
        supply_chain_risk = "LOW"
        if narrative_risk > 0.7:
            supply_chain_risk = "HIGH"
        elif narrative_risk > 0.5:
            supply_chain_risk = "MEDIUM"

        output = ManasOutput(
            manas_score=manas_score,
            timing_score=timing_score,
            regime_score=regime_score,
            confidence_score=confidence_score,
            risk_temperature=risk_temperature,
            should_act=should_act,
            action_gate_reason=reason,
            bias_state=bias_state,
            bias_correction=bias_correction,
            alpha=alpha,
            attention_focus=attention_focus,
            narrative_risk=narrative_risk,
            hot_narratives=hot_narratives,
            supply_chain_risk_level=supply_chain_risk,
        )

        self._last_output = output
        self._last_update = current_time

        return output

    def _get_gate_reason(
        self,
        manas_score: float,
        timing: float,
        regime: float,
        confidence: float,
        bias: BiasState
    ) -> str:
        """生成行动门原因"""
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

        if manas_score > self.ACTION_THRESHOLD:
            reasons.append("✓通过")
        else:
            reasons.append("✗未通过")

        return " | ".join(reasons)

    def record_pnl(self, pnl_pct: float):
        """记录盈亏（用于 MetaManas 偏差检测）"""
        self._recent_pnl.append(pnl_pct)
        if len(self._recent_pnl) > 20:
            self._recent_pnl.pop(0)

    def get_state(self) -> Dict[str, Any]:
        """获取末那识状态"""
        if self._last_output is None:
            return {"status": "not_initialized"}

        return self._last_output.to_dict()

    def reset_bias(self):
        """重置偏差状态"""
        self.meta_manas.bias_state = BiasState.NEUTRAL
        log.info("[ManasEngine] 偏差状态已重置")
