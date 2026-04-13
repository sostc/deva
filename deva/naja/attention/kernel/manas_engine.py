"""
ManasEngine - 末那识引擎

🧠 定位：天-地-人框架中的「人」
    - 「人」= 决策中枢
    - 回答：「我该怎么做？」
    - 感知天（时机）和地（题材）的变化后做出决策

一个持续输出"是否行动"的内在决策中枢

核心职责：
    • 要不要看（注意力方向 Q）
    • 要不要信（置信度 α）
    • 要不要上（仓位 T）
    • 要不要停（风险）

================================================================================
🌌 天-地-人 框架
================================================================================

ManasEngine（人）
    │
    ├── 感知「天」（TimingNarrative）
    │       时机成熟度 → timing_score
    │       现在是不是该动的时候？
    │
    ├── 感知「地」（BlockNarrative）
    │       题材状态 → spatial_score
    │       我关心的主题现在怎么样了？
    │
    └── 综合判断 → manas_score → 交易决策

================================================================================
内部架构（4引擎 + 1观照层）
================================================================================

ManasEngine
    ├── TimingEngine（时机节律）  ← 天时
    │       判断"现在能不能动"
    │       视角：微观时机
    │
    ├── RegimeEngine（环境感）  ← 地利
    │       判断"最近大方向顺不顺"
    │       视角：宏观环境
    │
    ├── ConfidenceEngine（自信）  ← 自知
    │       判断"我的策略还管用吗"
    │       视角：策略适配度
    │
    ├── RiskEngine（风险）  ← 生存本能
    │       判断"还能承受多少波动"
    │       视角：客观风险（市场杀的）
    │
    ├── MetaManas（观照层）  ← 觉知偏差
    │       判断"我自己会不会犯错"
    │       视角：主观偏差（自己作的）

各引擎视角总结：
┌──────────────────┬────────────────┬─────────────────┐
│ 引擎             │ 看的角度        │ 简单理解         │
├──────────────────┼────────────────┼─────────────────┤
│ TimingEngine     │ 微观时机        │ 现在能动手吗？   │
│ RegimeEngine     │ 宏观环境        │ 大方向顺吗？     │
│ ConfidenceEngine │ 策略适配度      │ 策略还管用吗？   │
│ RiskEngine       │ 客观风险        │ 市场能杀我多少？ │
│ MetaManas        │ 主观偏差        │ 我自己会作死吗？ │
└──────────────────┴────────────────┴─────────────────┘

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

================================================================================
事件驱动（新架构）
================================================================================

ManasEngine 订阅 NajaEventBus，感知认知层变化：
    - BLOCK_NARRATIVE_UPDATE（地）：我们关注的题材更新了
    - RESONANCE_DETECTED（共振）：天-地共振事件
    - TIMING_NARRATIVE_UPDATE（天）：时机状态变化了

收到事件后 → _invalidate_cache() → 下次 compute() 会重新计算
"""

import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from deva.naja.register import SR

log = logging.getLogger(__name__)


class AttentionFocus(Enum):
    """注意力聚焦类型"""
    WATCH = "watch"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    REBALANCE = "rebalance"
    ACCUMULATE = "accumulate"


class HarmonyState(Enum):
    """和谐状态"""
    RESONANCE = "resonance"
    NEUTRAL = "neutral"
    RESISTANCE = "resistance"


class BiasState(Enum):
    """偏差状态"""
    NEUTRAL = "neutral"
    GREED = "greed"
    FEAR = "fear"


class ActionType(Enum):
    """行动类型"""
    HOLD = "hold"
    ACT_FULLY = "act_fully"
    ACT_CAREFULLY = "act_carefully"
    ACT_MINIMALLY = "act_minimally"


class PortfolioSignal(Enum):
    """持仓信号"""
    NONE = "none"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    REBALANCE = "rebalance"
    ACCUMULATE = "accumulate"


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

    ai_compute_direction: str = "unknown"
    awakening_level: str = "dormant"

    harmony_state: HarmonyState = HarmonyState.NEUTRAL
    harmony_strength: float = 0.5
    action_type: ActionType = ActionType.HOLD

    portfolio_loss_pct: float = 0.0
    market_deterioration: bool = False

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
            "awakening_level": self.awakening_level,
            "harmony_state": self.harmony_state.value,
            "harmony_strength": self.harmony_strength,
            "action_type": self.action_type.value,
            "portfolio_loss_pct": self.portfolio_loss_pct,
            "market_deterioration": self.market_deterioration,
        }


class TimingEngine:
    """
    时机引擎 - 判断市场"能不能动"

    视角：微观时机 - 现在是不是动手的好时机？

    分析四个维度：
        • 时间压力 (time_pressure) - 今天是开盘/盘中/收盘？
        • 波动率状态 (volatility) - 市场是否稳定到可以操作？
        • 成交密度 (trade_density) - 有足够流动性吗？
        • 结构断裂 (structure_break) - 趋势是否被破坏？

    注意：与 RegimeEngine 的区别
        - TimingEngine 看「现在能不能动」→ 微观层面的择时
        - RegimeEngine 看「现在是顺风还是逆风」→ 宏观层面的方向

    简单理解：
        TimingEngine = 今天/现在适不适合动手（微观）
        RegimeEngine = 最近一段时间大方向顺不顺（宏观）

    输出 timing_score ∈ [0, 1]
        0 = 不宜动（时机不对）
        1 = 可以出手（时机成熟）

    支持自适应权重：高波动环境自动调整各因子权重
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

        weights = self._get_adaptive_weights(scanner, volatility)

        timing = (
            time_pressure * weights["time_pressure"] +
            volatility * weights["volatility"] +
            density * weights["density"] +
            structure * weights["structure"]
        )

        return max(0.0, min(1.0, timing))

    def _get_adaptive_weights(self, scanner, current_volatility: float) -> Dict[str, float]:
        """
        根据当前波动率环境自适应调整权重

        高波动：降低波动率权重，提高时间压力和结构断裂权重
        低波动：提高波动率权重，降低成交密度权重
        """
        if len(self._volatility_history) >= 5:
            recent_avg = sum(self._volatility_history[-5:]) / 5
            if current_volatility > recent_avg * 1.3:
                return {
                    "time_pressure": 0.35,
                    "volatility": 0.35,
                    "density": 0.15,
                    "structure": 0.15,
                }
            elif current_volatility < recent_avg * 0.7:
                return {
                    "time_pressure": 0.3,
                    "volatility": 0.15,
                    "density": 0.35,
                    "structure": 0.2,
                }

        return {
            "time_pressure": 0.4,
            "volatility": 0.25,
            "density": 0.2,
            "structure": 0.15,
        }

    def _get_time_pressure(self, session_manager) -> float:
        """获取时间压力"""
        if session_manager is None:
            try:
                session_manager = SR('trading_clock')
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

    视角：宏观环境 - 最近一段时间大方向顺不顺？

    分析三个维度：
        • 指数趋势 (index_trend) - 大盘是在上涨还是下跌？
        • 流动性信号 (liquidity) - 资金是在流入还是流出？
        • 题材扩散 (block_diffusion) - 是普涨还是分化？

    注意：与 TimingEngine 的区别
        - RegimeEngine 看「最近宏观方向」→ 大方向顺不顺
        - TimingEngine 看「现在微观时机」→ 现在能不能动

    简单理解：
        RegimeEngine = 最近一段时间大方向顺不顺（顺风/逆风）
        TimingEngine = 今天/现在适不适合动手（时机）

    输出 regime_score ∈ [-1, 1]
        -1 = 强逆风（市场整体下跌）
         0 = 中性（横盘）
        +1 = 强顺风（市场整体上涨）
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
        diffusion = self._get_block_diffusion(scanner)

        weights = self._get_adaptive_regime_weights(scanner)

        regime = (
            trend * weights["trend"] +
            liquidity * weights["liquidity"] +
            diffusion * weights["diffusion"]
        )

        return max(-1.0, min(1.0, regime))

    def _get_adaptive_regime_weights(self, scanner) -> Dict[str, float]:
        """
        根据当前市场状态自适应调整 RegimeEngine 权重

        提案 2.4.2：美股交易时段更注重趋势，盘前盘后更注重流动性
        """
        weights = {
            "trend": 0.4,
            "liquidity": 0.35,
            "diffusion": 0.25,
        }

        if scanner is None:
            return weights

        try:
            summary = scanner.get_market_summary()
            phase = summary.get('us_trading_phase', 'closed')

            # 美股交易时段：更注重趋势
            if phase == 'trading':
                weights = {
                    "trend": 0.5,
                    "liquidity": 0.3,
                    "diffusion": 0.2,
                }
            # 美股盘前/盘后：更注重流动性
            elif phase in ('pre_market', 'after_hours'):
                weights = {
                    "trend": 0.25,
                    "liquidity": 0.5,
                    "diffusion": 0.25,
                }
        except:
            pass

        return weights

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

    def _get_block_diffusion(self, scanner) -> float:
        """获取题材扩散程度"""
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

    视角：策略自检 - 我的策略现在还管用吗？

    分析三个维度：
        • 命中率 (hit_rate) - 最近策略命中率如何？
        • 滚动盈亏 (rolling_pnl) - 最近是在赚钱还是亏钱？
        • Bandit置信度 (bandit_conf) - 多臂老虎机对策略的信心

    简单理解：
        这个引擎回答「我这套方法现在还能用吗？」
        如果最近一直在亏，可能是策略不适应现在市场了。

    与其他引擎的区别：
        - RiskEngine：看「市场有多危险」（外部）
        - MetaManas：看「我有没有心理偏差」（内部）
        - ConfidenceEngine：看「我的策略现在还管用吗」（策略本身）

    输出 confidence ∈ [0, 1.5]
        < 0.5 = 策略失灵，需要重新审视
        0.5-1.0 = 正常范围
        > 1.0 = 策略非常适配（注意是否过度自信）
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
                tracker = SR('bandit_tracker')
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

    视角：外部风险 - 市场能杀我多少？

    分析三个维度：
        • 现金比例 (cash_ratio) - 我还有多少子弹？
        • 当前回撤 (drawdown) - 我已经亏了多少？
        • 市场波动率 (volatility) - 市场有多疯狂？

    注意：与 MetaManas 的区别
        - RiskEngine 看「绝对亏损量」→ 市场造成的客观损失
        - MetaManas 看「连续盈亏方向」→ 我自己的心理偏差

    输出 temperature ∈ (0, 2]
        T 大 = 更保守（市场太危险，少动）
        T 小 = 更激进（还有子弹，可以干）
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
                portfolio = SR('virtual_portfolio')
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

    视角：内部偏差 - 我自己会怎么犯错？

    检测两种心理偏差：
        • 连赢 → 越来越激进 → 标记"贪"（贪心让我过度自信）
        • 连亏 → 完全不动 → 标记"惧"（恐惧让我错过机会）

    纠偏机制：
        • 贪时 → reduce α（别太信自己）, increase T（仓位别太重）
        • 恐时 → keep α（策略没问题）, moderate T（保持合理仓位）

    注意：与 RiskEngine 的区别
        - MetaManas 看「连续盈亏方向」→ 我自己的心理偏差（主观）
        - RiskEngine 看「绝对亏损量」→ 市场造成的客观损失（客观）

    简单理解：
        RiskEngine = 客观风险（市场杀的）
        MetaManas = 主观偏差（自己作的）
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
    WEIGHT_RISK = 0.35
    WEIGHT_CONFIDENCE = 0.25
    ACTION_THRESHOLD = 0.5

    def __init__(self):
        self.timing_engine = TimingEngine()
        self.regime_engine = RegimeEngine()
        self.confidence_engine = ConfidenceEngine()
        self.risk_engine = RiskEngine()
        self.meta_manas = MetaManas()

        self._last_output: Optional[ManasOutput] = None
        self._last_update = 0.0
        self._update_interval = 1.0
        self._current_narratives: List[str] = []
        self._recent_pnl: List[float] = []

        # 🚀 供应链状态（事件驱动，收到事件后更新）
        self._supply_chain_state: Dict[str, Any] = {
            "narrative_risk": 0.5,
            "hot_narratives": [],
            "risk_level": "LOW",
            "last_update": 0.0,
            # 🚀 AI算力趋势（事件驱动）
            "ai_compute_trend": "neutral",  # up / down / neutral
            "ai_compute_strength": 0.5,       # 0-1
            # 🚀 自选股注意力
            "watchlist": [],                  # 自选股代码列表
            "watchlist_bonus": 1.0,           # 自选股加成系数
            # 🚀 关注主题（我们关心的叙事主题）
            "focus_themes": self._get_default_focus_themes(),
            # 🚀 共振状态（来自 CrossSignalAnalyzer）
            "resonance_score": 0.0,
            "resonance_sentiment": 0.0,
            "resonance_blocks": [],
            "resonance_updated": 0.0,
        }

        self._awakening_level: str = "dormant"

        # 🚀 新架构：订阅 NajaEventBus，感知认知层变化
        self._subscribe_to_event_bus()

    def _get_default_focus_themes(self) -> List[Dict[str, Any]]:
        """
        🚀 获取默认的关注主题列表

        这是我们"地"维度关心的话题，来自 keyword_registry 的预设关键词。
        BlockNarrative（地）只追踪这些主题，而不是所有市场主题。

        返回格式：[{"id": "AI", "name": "AI", "keywords": [...]}, ...]
        """
        from deva.naja.cognition.semantic.keyword_registry import DEFAULT_NARRATIVE_KEYWORDS

        return [
            {
                "id": theme_id,
                "name": theme_id,
                "keywords": keywords,
            }
            for theme_id, keywords in DEFAULT_NARRATIVE_KEYWORDS.items()
        ]

    def get_focus_themes(self) -> List[Dict[str, Any]]:
        """
        🚀 获取当前关注的叙事主题列表

        这是 Manas 关心的话题（地），BlockNarrative 应该只追踪这些主题。
        """
        return self._supply_chain_state.get("focus_themes", [])

    def set_focus_themes(self, themes: List[Dict[str, Any]]):
        """
        🚀 设置关注的叙事主题列表

        可以动态更新我们关心的话题。
        """
        self._supply_chain_state["focus_themes"] = themes
        log.info(f"[ManasEngine] 关注主题已更新: {len(themes)} 个主题")
        self._publish_manas_state_change({"focus_themes": themes})

    def _publish_manas_state_change(self, partial_state: Dict[str, Any] = None):
        """
        🚀 发布 Manas 状态变化事件

        通知订阅者（如 Cognition 层）Manas 状态已更新。
        Cognition 层应订阅 CognitiveEventType.MANAS_STATE_CHANGED 事件。
        """
        try:
            from deva.naja.events import get_event_bus, CognitiveEventType

            bus = get_event_bus()
            state_data = {
                "focus_themes": self._supply_chain_state.get("focus_themes", []),
                "harmony_strength": self._harmony_strength,
                "harmony_state": self._harmony_state.value if hasattr(self._harmony_state, 'value') else str(self._harmony_state),
            }
            if partial_state:
                state_data.update(partial_state)

            bus.publish_cognitive_event(
                source="ManasEngine",
                event_type=CognitiveEventType.MANAS_STATE_CHANGED,
                data=state_data,
                importance=0.6,
            )
            log.debug(f"[ManasEngine] 发布 MANAS_STATE_CHANGED 事件")
        except Exception as e:
            log.debug(f"[ManasEngine] 发布状态变化事件失败: {e}")

    def _subscribe_to_event_bus(self):
        """
        🚀 订阅 NajaEventBus，感知认知层的重要更新

        当 NarrativeTracker / MarketNarrative / SupplyChainLinker 有重要更新时，
        ManasEngine 会收到通知并清缓存，确保决策反映最新认知状态
        """
        try:
            from deva.naja.events import (
                get_event_bus,
                CognitiveEventType,
            )

            bus = get_event_bus()
            bus.subscribe(
                "ManasEngine",
                self._on_cognitive_event,
                event_types=[
                    CognitiveEventType.BLOCK_NARRATIVE_UPDATE,
                    CognitiveEventType.NARRATIVE_BOOST,
                    CognitiveEventType.TIMING_NARRATIVE_UPDATE,
                    CognitiveEventType.NARRATIVE_SUPPLY_LINK,
                    CognitiveEventType.SUPPLY_CHAIN_RISK,
                    CognitiveEventType.RESONANCE_DETECTED,
                ],
                min_importance=0.5,  # 只关心重要事件
            )
            log.info("[ManasEngine] 已订阅 NajaEventBus")
        except ImportError:
            log.debug("[ManasEngine] NajaEventBus 未安装，跳过订阅")

    def _on_cognitive_event(self, event):
        """
        🚀 处理认知事件，感知认知层状态变化

        当收到认知事件时，更新供应链状态，清缓存
        """
        log.info(
            f"[ManasEngine] 收到认知事件: {event.source} -> {event.event_type.value} "
            f"(importance={event.importance:.2f}, narratives={event.narratives[:2]})"
        )

        # 🚀 更新供应链状态
        self._update_supply_chain_state(event)

        # 清缓存，触发重新计算
        self._invalidate_cache()

    def _update_supply_chain_state(self, event):
        """
        🚀 根据认知事件更新供应链状态

        事件驱动更新：不再主动拉取，由事件携带状态

        处理三个维度：
        1. 叙事风险 + 热点叙事
        2. AI算力趋势（从叙事中判断）
        3. 自选股注意力加成
        4. 天-地共振（CrossSignalAnalyzer）
        """
        import time
        try:
            from deva.naja.events import CognitiveEventType
            event_type = event.event_type
        except Exception:
            event_type = getattr(event, "event_type", None)

        # 根据风险等级更新风险分数
        risk_level = event.risk_level if hasattr(event, 'risk_level') and event.risk_level else "LOW"
        risk_scores = {
            "HIGH": 0.8,
            "MEDIUM": 0.5,
            "LOW": 0.2,
        }
        new_risk = risk_scores.get(risk_level, 0.5)

        # 结合事件重要性和原有风险
        current_risk = self._supply_chain_state.get("narrative_risk", 0.5)
        updated_risk = current_risk * 0.7 + new_risk * event.importance * 0.3

        # 更新 hot_narratives
        current_narratives = self._supply_chain_state.get("hot_narratives", [])
        new_narratives = []
        for narrative in event.narratives[:5]:
            # 添加叙事及其重要性
            new_narratives.append((narrative, event.importance))

        # 合并去重
        existing = {n[0]: n[1] for n in current_narratives}
        for narrative, importance in new_narratives:
            if narrative in existing:
                existing[narrative] = max(existing[narrative], importance)
            else:
                existing[narrative] = importance

        hot_narratives = sorted(existing.items(), key=lambda x: x[1], reverse=True)[:5]

        # 🚀 AI算力趋势：从叙事中判断
        ai_keywords = ["AI", "算力", "芯片", "GPU", "数据中心", "大模型", "模型训练",
                       "H100", "B100", "GB200", "Blackwell", "算力需求", "AI服务器"]
        ai_compute_trend = self._supply_chain_state.get("ai_compute_trend", "neutral")
        ai_compute_strength = self._supply_chain_state.get("ai_compute_strength", 0.5)

        narratives_lower = [n.lower() for n in event.narratives]
        ai_hits = sum(1 for kw in ai_keywords if any(kw.lower() in n for n in narratives_lower))

        if ai_hits >= 3:
            # 多个AI关键词命中 → 趋势增强
            ai_compute_trend = "up"
            ai_compute_strength = min(1.0, ai_compute_strength * 0.8 + event.importance * 0.2)
        elif ai_hits >= 1 and event.importance > 0.7:
            # 有AI关键词且重要 → 轻微增强
            ai_compute_strength = min(1.0, ai_compute_strength * 0.9 + event.importance * 0.1)
        else:
            # 自然衰减
            ai_compute_strength = max(0.3, ai_compute_strength * 0.98)

        # 🚀 自选股注意力加成
        watchlist = self._supply_chain_state.get("watchlist", [])
        watchlist_bonus = self._supply_chain_state.get("watchlist_bonus", 1.0)
        event_stock_codes = getattr(event, 'stock_codes', []) or []

        # 检查事件是否涉及自选股
        watchlist_upper = [s.upper() for s in watchlist]
        event_stocks_upper = [s.upper() for s in event_stock_codes]

        if any(s in watchlist_upper for s in event_stocks_upper) and event_stocks_upper:
            # 命中自选股 → 增加注意力
            watchlist_bonus = min(1.5, watchlist_bonus * 1.2)
        else:
            # 自然衰减
            watchlist_bonus = max(1.0, watchlist_bonus * 0.99)

        # 🚀 共振事件：记录共振强度与情绪
        resonance_score = self._supply_chain_state.get("resonance_score", 0.0)
        resonance_sentiment = self._supply_chain_state.get("resonance_sentiment", 0.0)
        resonance_blocks = self._supply_chain_state.get("resonance_blocks", [])
        resonance_updated = self._supply_chain_state.get("resonance_updated", 0.0)

        if event_type == getattr(CognitiveEventType, "RESONANCE_DETECTED", None) or str(getattr(event_type, "value", event_type)) == "resonance_detected":
            meta = getattr(event, "metadata", {}) or {}
            resonance_score = max(resonance_score, float(getattr(event, "importance", 0.0) or 0.0))
            resonance_sentiment = float(meta.get("sentiment", resonance_sentiment) or 0.0)
            block_id = meta.get("block_id") or meta.get("block_name") or ""
            if block_id:
                if block_id not in resonance_blocks:
                    resonance_blocks = (resonance_blocks + [block_id])[-5:]
            resonance_updated = time.time()

            # 共振情绪为负时，轻微增加风险；为正时，轻微降低风险
            if resonance_sentiment < -0.2 and resonance_score > 0.7:
                updated_risk = min(1.0, updated_risk + 0.05)
            elif resonance_sentiment > 0.2 and resonance_score > 0.7:
                updated_risk = max(0.0, updated_risk - 0.03)

        # 更新状态
        self._supply_chain_state = {
            "narrative_risk": max(0.0, min(1.0, updated_risk)),
            "hot_narratives": hot_narratives,
            "risk_level": risk_level if event.importance > 0.7 else self._supply_chain_state.get("risk_level", "LOW"),
            "last_update": time.time(),
            # 🚀 AI算力趋势
            "ai_compute_trend": ai_compute_trend,
            "ai_compute_strength": ai_compute_strength,
            # 🚀 自选股注意力
            "watchlist": watchlist,
            "watchlist_bonus": watchlist_bonus,
            # 🚀 共振状态
            "resonance_score": resonance_score,
            "resonance_sentiment": resonance_sentiment,
            "resonance_blocks": resonance_blocks,
            "resonance_updated": resonance_updated,
        }

        log.debug(
            f"[ManasEngine] 供应链状态已更新: risk={self._supply_chain_state['narrative_risk']:.2f}, "
            f"ai_trend={ai_compute_trend}({ai_compute_strength:.2f}), "
            f"watchlist_bonus={watchlist_bonus:.2f}"
        )

    def _invalidate_cache(self):
        """
        🚀 清除缓存，强制下次计算时重新获取认知数据

        这样可以确保决策反映最新的叙事/供应链状态
        """
        # 清除上次输出，下次 compute 会强制重新计算
        self._last_output = None
        self._last_update = 0.0

        log.debug("[ManasEngine] 缓存已失效，下次计算将重新获取认知数据")

    def refresh_watchlist(self, watchlist: List[str] = None):
        """
        🚀 刷新自选股列表

        可以手动传入，也可以从持仓系统自动获取

        Args:
            watchlist: 自选股代码列表，如 ["NVDA", "AMD", "TSLA"]
        """
        if watchlist is None:
            # 从持仓系统自动获取
            watchlist = self._get_watchlist_from_portfolio()

        self._supply_chain_state["watchlist"] = watchlist
        log.info(f"[ManasEngine] 自选股列表已更新: {len(watchlist)} 只股票")

    def _get_watchlist_from_portfolio(self) -> List[str]:
        """
        🚀 从 NB 数据表读取自选股

        数据来源：naja_watchlist 表的 ai_stocks 字段
        """
        try:
            from deva.naja.tables import get_table_data
            import json

            watchlist_data = get_table_data("naja_watchlist")
            if watchlist_data is None:
                return []

            others = watchlist_data.get("others", [])
            ai_stocks = next((item for item in others if item[0] == "ai_stocks"), None)
            if ai_stocks is None or len(ai_stocks) < 2:
                return []

            stocks_dict = ai_stocks[1]
            if isinstance(stocks_dict, str):
                try:
                    stocks_dict = json.loads(stocks_dict)
                except:
                    pass

            stocks = stocks_dict.get("stocks", []) if isinstance(stocks_dict, dict) else []
            watchlist_codes = [s["code"] for s in stocks if isinstance(s, dict) and "code" in s]

            return watchlist_codes
        except Exception as e:
            log.debug(f"[ManasEngine] 获取自选股失败: {e}")
            return []

    def _determine_harmony_state(self, risk_temperature: float, timing_score: float, regime_score: float) -> HarmonyState:
        """确定和谐状态"""
        if risk_temperature > 1.4 or regime_score < -0.5:
            return HarmonyState.RESISTANCE
        elif risk_temperature < 0.8 and timing_score > 0.6 and regime_score > 0.2:
            return HarmonyState.RESONANCE
        return HarmonyState.NEUTRAL

    def _determine_action_type(
        self,
        harmony_state: HarmonyState,
        harmony_strength: float,
        timing_score: float
    ) -> ActionType:
        """确定行动类型"""
        should_act = harmony_strength > self.ACTION_THRESHOLD

        if harmony_state == HarmonyState.RESISTANCE:
            return ActionType.HOLD
        elif harmony_state == HarmonyState.RESONANCE and timing_score > 0.7:
            return ActionType.ACT_FULLY
        elif should_act and harmony_strength > 0.6:
            return ActionType.ACT_CAREFULLY
        elif should_act and harmony_strength > 0.4:
            return ActionType.ACT_MINIMALLY
        return ActionType.HOLD

    def _determine_attention_focus(self, action_type: ActionType, portfolio_loss: float) -> float:
        """确定注意力聚焦因子"""
        base = 1.0
        if action_type == ActionType.HOLD:
            if portfolio_loss < -0.05:
                return 0.7
            return 1.0
        elif action_type == ActionType.ACT_FULLY:
            return 1.3
        elif action_type == ActionType.ACT_CAREFULLY:
            return 1.1
        return 1.0

    def _get_awakening_level(self) -> str:
        """获取觉醒等级"""
        try:
            from deva.naja.attention import get_awakening_controller
            controller = get_awakening_controller()
            if controller and hasattr(controller, '_awakened_state') and controller._awakened_state:
                return controller._awakened_state.get("awakening_level", "dormant")
        except Exception:
            pass
        return self._awakening_level

    def set_awakening_level(self, level: str):
        """设置觉醒等级（由外部调用）"""
        self._awakening_level = level

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

        使用三维融合逻辑：
        1. 天时 (timing) + 地势 (risk) + 人和 (confidence)
        2. 结合环境状态 (regime)
        3. 叙事风险折扣
        4. AI算力影响
        5. 觉醒加成
        6. 偏差纠偏

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

        harmony_strength = (
            timing_score * self.WEIGHT_TIMING +
            (1.0 - min(risk_temperature, 1.5) / 1.5) * self.WEIGHT_RISK +
            confidence_score * self.WEIGHT_CONFIDENCE
        )

        regime_factor = (regime_score + 1) / 2
        harmony_strength *= (0.7 + regime_factor * 0.3)
        harmony_strength = min(1.0, harmony_strength)

        harmony_state = self._determine_harmony_state(risk_temperature, timing_score, regime_score)

        # 🚀 使用事件驱动更新的供应链状态
        narrative_risk = self._supply_chain_state.get("narrative_risk", 0.5)
        if narrative_risk > 0.6:
            harmony_strength *= (1.0 - (narrative_risk - 0.6) * 0.5)

        # 🚀 AI算力趋势加成（只有上升趋势才加成）
        ai_compute_trend = self._supply_chain_state.get("ai_compute_trend", "neutral")
        ai_compute_strength = self._supply_chain_state.get("ai_compute_strength", 0.5)
        if ai_compute_trend == "up" and ai_compute_strength > 0.6:
            ai_bonus = 1.0 + (ai_compute_strength - 0.6) * 0.3  # 最多+12%
            harmony_strength *= ai_bonus
            log.debug(f"[ManasEngine] AI算力加成: trend={ai_compute_trend}, strength={ai_compute_strength:.2f}, bonus={ai_bonus:.2f}")

        # 🚀 共振加成/惩罚（来自 CrossSignalAnalyzer）
        resonance_score = self._supply_chain_state.get("resonance_score", 0.0)
        resonance_sentiment = self._supply_chain_state.get("resonance_sentiment", 0.0)
        if resonance_score >= 0.7:
            if resonance_sentiment >= 0.2:
                resonance_bonus = 1.0 + min(0.10, (resonance_score - 0.7) * 0.2)
                harmony_strength *= resonance_bonus
                log.debug(f"[ManasEngine] 共振正向加成: score={resonance_score:.2f}, bonus={resonance_bonus:.2f}")
            elif resonance_sentiment <= -0.2:
                resonance_penalty = 1.0 - min(0.08, (resonance_score - 0.7) * 0.2)
                harmony_strength *= resonance_penalty
                log.debug(f"[ManasEngine] 共振负向惩罚: score={resonance_score:.2f}, penalty={resonance_penalty:.2f}")

        detected_problems = []
        opportunities = []
        resolvers = []
        hot_narratives = self._supply_chain_state.get("hot_narratives", [])

        awakening_level = self._get_awakening_level()
        if awakening_level == "enlightened":
            harmony_strength *= 1.15
        elif awakening_level == "illuminated":
            harmony_strength *= 1.10
        elif awakening_level == "awakening":
            harmony_strength *= 1.05

        bias_state, bias_correction = self.meta_manas.detect_and_correct(
            harmony_strength,
            self._recent_pnl,
            harmony_strength
        )

        harmony_strength *= bias_correction
        harmony_strength = max(0.0, min(1.0, harmony_strength))

        action_type = self._determine_action_type(harmony_state, harmony_strength, timing_score)
        should_act = action_type != ActionType.HOLD

        raw_manas = harmony_strength

        alpha = confidence_score * harmony_strength * bias_correction
        alpha = max(0.3, min(1.5, alpha))

        portfolio_loss = 0.0
        if portfolio:
            try:
                if hasattr(portfolio, 'get_summary'):
                    summary = portfolio.get_summary()
                    portfolio_loss = summary.get('total_return', 0.0)
                elif isinstance(portfolio, dict):
                    portfolio_loss = portfolio.get('total_return', 0.0)
            except:
                pass

        market_deterioration = risk_temperature > 1.3

        attention_focus = self._determine_attention_focus(action_type, portfolio_loss)

        # 🚀 自选股注意力加成
        watchlist_bonus = self._supply_chain_state.get("watchlist_bonus", 1.0)
        if watchlist_bonus > 1.0:
            attention_focus *= watchlist_bonus
            log.debug(f"[ManasEngine] 自选股注意力加成: bonus={watchlist_bonus:.2f}")

        reason = self._get_gate_reason(harmony_strength, timing_score, regime_score, confidence_score, bias_state, harmony_state, action_type)

        supply_chain_risk = self._supply_chain_state.get("risk_level", "LOW")

        output = ManasOutput(
            manas_score=harmony_strength,
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
            awakening_level=awakening_level,
            harmony_state=harmony_state,
            harmony_strength=harmony_strength,
            action_type=action_type,
            portfolio_loss_pct=max(-1.0, min(1.0, portfolio_loss)),
            market_deterioration=market_deterioration,
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
        bias: BiasState,
        harmony_state: HarmonyState,
        action_type: ActionType
    ) -> str:
        """生成行动门原因"""
        reasons = []

        if harmony_state == HarmonyState.RESISTANCE:
            reasons.append("环境阻力")
        elif harmony_state == HarmonyState.RESONANCE:
            reasons.append("和谐共振")

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

        reasons.append(f"行动:{action_type.value}")

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
