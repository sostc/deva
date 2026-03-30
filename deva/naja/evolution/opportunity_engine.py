"""
OpportunityEngine - 主动机会创造引擎

"主动型末那识"的具体实现

核心能力：
1. OpportunityScanner: 主动扫描潜在机会
2. TimingOptimizer: 时机优化
3. PatternPredictor: 模式预测
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from collections import deque
from enum import Enum

log = logging.getLogger(__name__)


class OpportunityType(Enum):
    """机会类型"""
    MOMENTUM = "momentum"           # 动量机会
    REVERSAL = "reversal"           # 反转机会
    BREAKOUT = "breakout"           # 突破机会
    ACCUMULATION = "accumulation"   # 蓄势机会
    SECTOR_ROTATION = "sector_rotation"  # 板块轮动
    EVENT_DRIVEN = "event_driven"   # 事件驱动


class OpportunityStage(Enum):
    """机会阶段"""
    SCANNING = "scanning"          # 扫描中
    IDENTIFIED = "identified"       # 已识别
    CONFIRMING = "confirming"       # 确认中
    READY = "ready"               # 就绪
    EXECUTED = "executed"          # 已执行
    EXPIRED = "expired"           # 已过期


@dataclass
class Opportunity:
    """交易机会"""
    opportunity_type: OpportunityType
    symbol: str
    confidence: float              # 置信度 [0, 1]
    stage: OpportunityStage
    expected_return: float         # 预期收益
    risk_level: float              # 风险等级
    entry_timing: str              # 入场时机描述
    entry_horizon: float           # 入场时间窗口（秒）
    evidence: List[str]           # 支撑证据
    created_at: float
    expires_at: float
    related_narrative: Optional[str] = None


@dataclass
class TimingSignal:
    """时机信号"""
    signal_type: str               # "entry", "exit", "increase", "decrease"
    urgency: float                 # 紧迫度 [0, 1]
    confidence: float
    reason: str
    best_before: float             # 最佳执行时间戳


class OpportunityScanner:
    """
    机会扫描器

    主动扫描市场，发现潜在机会
    """

    def __init__(self):
        self._opportunities: Dict[str, Opportunity] = {}
        self._scan_history: deque = deque(maxlen=100)

    def scan(
        self,
        market_data: Dict[str, Any],
        narrative_result: Optional[Dict[str, Any]] = None,
        seed_patterns: Optional[List[str]] = None
    ) -> List[Opportunity]:
        """
        扫描机会

        Args:
            market_data: 市场数据
            narrative_result: 叙事感知结果
            seed_patterns: 光明藏召回的模式

        Returns:
            发现的机会列表
        """
        opportunities = []

        momentum_opp = self._scan_momentum(market_data)
        if momentum_opp:
            opportunities.append(momentum_opp)

        reversal_opp = self._scan_reversal(market_data)
        if reversal_opp:
            opportunities.append(reversal_opp)

        breakout_opp = self._scan_breakout(market_data)
        if breakout_opp:
            opportunities.append(breakout_opp)

        sector_opp = self._scan_sector_rotation(market_data, narrative_result)
        if sector_opp:
            opportunities.append(sector_opp)

        self._update_opportunities(opportunities)
        self._clean_expired()

        return opportunities

    def _scan_momentum(self, market_data: Dict[str, Any]) -> Optional[Opportunity]:
        """扫描动量机会"""
        sector_changes = market_data.get("sector_changes", {})
        if not sector_changes:
            return None

        top_sectors = sorted(sector_changes.items(), key=lambda x: x[1], reverse=True)[:2]
        if len(top_sectors) < 2:
            return None

        top_change = top_sectors[0][1]
        second_change = top_sectors[1][1]

        if top_change > 2.0 and second_change > 1.5:
            return Opportunity(
                opportunity_type=OpportunityType.MOMENTUM,
                symbol=top_sectors[0][0],
                confidence=min(1.0, top_change / 5),
                stage=OpportunityStage.READY if top_change > 3 else OpportunityStage.CONFIRMING,
                expected_return=top_change * 0.5,
                risk_level=0.3,
                entry_timing="立即" if top_change > 3 else "等待确认",
                entry_horizon=300 if top_change > 3 else 1800,
                evidence=[f"领涨板块: {top_sectors[0][0]}(+{top_change:.1f}%)", f"跟随: {top_sectors[1][0]}(+{second_change:.1f}%)"],
                created_at=time.time(),
                expires_at=time.time() + 3600
            )

        return None

    def _scan_reversal(self, market_data: Dict[str, Any]) -> Optional[Opportunity]:
        """扫描反转机会"""
        sector_changes = market_data.get("sector_changes", {})
        if not sector_changes:
            return None

        bottom_sectors = sorted(sector_changes.items(), key=lambda x: x[1])[:2]
        if len(bottom_sectors) < 2:
            return None

        bottom_change = bottom_sectors[0][1]

        if bottom_change < -2.5:
            return Opportunity(
                opportunity_type=OpportunityType.REVERSAL,
                symbol=bottom_sectors[0][0],
                confidence=min(1.0, abs(bottom_change) / 5),
                stage=OpportunityStage.SCANNING,
                expected_return=abs(bottom_change) * 0.6,
                risk_level=0.6,
                entry_timing="等待超卖确认",
                entry_horizon=3600,
                evidence=[f"超跌板块: {bottom_sectors[0][0]}({bottom_change:.1f}%)"],
                created_at=time.time(),
                expires_at=time.time() + 7200
            )

        return None

    def _scan_breakout(self, market_data: Dict[str, Any]) -> Optional[Opportunity]:
        """扫描突破机会"""
        price_data = market_data.get("price_volatility", {})
        if not price_data:
            return None

        high_volatility = [(k, v) for k, v in price_data.items() if v > 2.0]
        if not high_volatility:
            return None

        symbol, vol = high_volatility[0]

        return Opportunity(
            opportunity_type=OpportunityType.BREAKOUT,
            symbol=symbol,
            confidence=min(1.0, vol / 4),
            stage=OpportunityStage.IDENTIFIED,
            expected_return=vol * 0.8,
            risk_level=0.5,
            entry_timing="等待突破确认",
            entry_horizon=1800,
            evidence=[f"高波动: {symbol}(IV={vol:.1f})"],
            created_at=time.time(),
            expires_at=time.time() + 3600
        )

    def _scan_sector_rotation(
        self,
        market_data: Dict[str, Any],
        narrative_result: Optional[Dict[str, Any]]
    ) -> Optional[Opportunity]:
        """扫描板块轮动机会"""
        sector_changes = market_data.get("sector_changes", {})
        if not sector_changes or len(sector_changes) < 5:
            return None

        sorted_sectors = sorted(sector_changes.items(), key=lambda x: x[1])
        changes = [s[1] for s in sorted_sectors]

        if len(changes) >= 3:
            first_third_avg = sum(changes[:len(changes)//3]) / (len(changes)//3)
            last_third_avg = sum(changes[-len(changes)//3:]) / (len(changes)//3)

            if last_third_avg - first_third_avg > 1.5:
                laggard = sorted_sectors[0][0]
                leader = sorted_sectors[-1][0]

                return Opportunity(
                    opportunity_type=OpportunityType.SECTOR_ROTATION,
                    symbol=f"{laggard} → {leader}",
                    confidence=0.6,
                    stage=OpportunityStage.CONFIRMING,
                    expected_return=abs(last_third_avg - first_third_avg) * 0.7,
                    risk_level=0.4,
                    entry_timing="等待轮动确认",
                    entry_horizon=3600,
                    evidence=[f"板块轮动: 从{laggard}到{leader}"],
                    created_at=time.time(),
                    expires_at=time.time() + 7200,
                    related_narrative="板块轮动叙事"
                )

        return None

    def _update_opportunities(self, opportunities: List[Opportunity]):
        """更新机会池"""
        for opp in opportunities:
            self._opportunities[opp.symbol] = opp
            self._scan_history.append(opp)

    def _clean_expired(self):
        """清理过期机会"""
        now = time.time()
        expired = [k for k, v in self._opportunities.items() if v.expires_at < now]
        for k in expired:
            del self._opportunities[k]

        for opp in self._opportunities.values():
            if opp.expires_at < now:
                opp.stage = OpportunityStage.EXPIRED

    def get_active_opportunities(self) -> List[Opportunity]:
        """获取活跃机会"""
        return [v for v in self._opportunities.values() if v.stage not in [OpportunityStage.EXPIRED, OpportunityStage.EXECUTED]]

    def get_opportunity_by_symbol(self, symbol: str) -> Optional[Opportunity]:
        """根据股票代码获取机会"""
        return self._opportunities.get(symbol)


class TimingOptimizer:
    """
    时机优化器

    优化入场/出场时机
    """

    def __init__(self):
        self._timing_history: deque = deque(maxlen=50)

    def optimize_entry(
        self,
        opportunity: Opportunity,
        market_data: Dict[str, Any]
    ) -> TimingSignal:
        """
        优化入场时机

        Args:
            opportunity: 交易机会
            market_data: 市场数据

        Returns:
            时机信号
        """
        if opportunity.stage == OpportunityStage.READY:
            time_remaining = opportunity.expires_at - time.time()
            urgency = 1.0 - min(1.0, time_remaining / opportunity.entry_horizon)

            return TimingSignal(
                signal_type="entry",
                urgency=urgency,
                confidence=opportunity.confidence,
                reason=f"{opportunity.opportunity_type.value}机会就绪",
                best_before=opportunity.expires_at
            )

        elif opportunity.stage == OpportunityStage.CONFIRMING:
            return TimingSignal(
                signal_type="entry",
                urgency=0.5,
                confidence=opportunity.confidence * 0.7,
                reason="等待确认信号",
                best_before=time.time() + opportunity.entry_horizon
            )

        return TimingSignal(
            signal_type="entry",
            urgency=0.2,
            confidence=opportunity.confidence * 0.5,
            reason="机会尚不明确",
            best_before=time.time() + 7200
        )

    def optimize_exit(
        self,
        position: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> TimingSignal:
        """
        优化出场时机

        Args:
            position: 持仓信息
            market_data: 市场数据

        Returns:
            时机信号
        """
        pnl = position.get("floating_pnl", 0)
        holding_time = position.get("holding_time", 0)

        if pnl > 0.05:
            if holding_time < 300:
                return TimingSignal(
                    signal_type="increase",
                    urgency=0.3,
                    confidence=0.7,
                    reason="盈利中，可适当加仓",
                    best_before=time.time() + 600
                )
            else:
                return TimingSignal(
                    signal_type="exit",
                    urgency=0.6,
                    confidence=0.8,
                    reason="盈利可观，考虑止盈",
                    best_before=time.time() + 300
                )

        elif pnl < -0.03:
            return TimingSignal(
                signal_type="exit",
                urgency=0.8,
                confidence=0.7,
                reason="亏损扩大，建议止损",
                best_before=time.time() + 180
            )

        return TimingSignal(
            signal_type="hold",
            urgency=0.1,
            confidence=0.5,
            reason="持仓观望",
            best_before=time.time() + 1800
        )

    def record_timing_result(self, timing: TimingSignal, success: bool):
        """记录时机结果"""
        self._timing_history.append({
            "timing": timing,
            "success": success,
            "timestamp": time.time()
        })

    def get_timing_stats(self) -> Dict[str, Any]:
        """获取时机统计"""
        if not self._timing_history:
            return {"total": 0, "success_rate": 0}

        total = len(self._timing_history)
        successes = sum(1 for h in self._timing_history if h["success"])

        return {
            "total": total,
            "success_rate": successes / total if total > 0 else 0
        }


class OpportunityEngine:
    """
    机会创造引擎（主动型末那识）

    整合机会扫描和时机优化，主动发现并把握机会
    """

    def __init__(self):
        self.scanner = OpportunityScanner()
        self.timing_optimizer = TimingOptimizer()

    def discover(
        self,
        market_data: Dict[str, Any],
        narrative_result: Optional[Dict[str, Any]] = None,
        seed_patterns: Optional[List[str]] = None
    ) -> List[Opportunity]:
        """
        发现机会

        Returns:
            发现的机会列表
        """
        return self.scanner.scan(market_data, narrative_result, seed_patterns)

    def get_timing(
        self,
        opportunity: Opportunity,
        market_data: Dict[str, Any]
    ) -> TimingSignal:
        """
        获取时机信号

        Returns:
            时机信号
        """
        return self.timing_optimizer.optimize_entry(opportunity, market_data)

    def get_exit_timing(
        self,
        position: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> TimingSignal:
        """
        获取出场时机信号

        Returns:
            出场时机信号
        """
        return self.timing_optimizer.optimize_exit(position, market_data)

    def get_active_opportunities(self) -> List[Opportunity]:
        """获取活跃机会"""
        return self.scanner.get_active_opportunities()

    def get_summary(self) -> Dict[str, Any]:
        """获取引擎摘要"""
        active = self.get_active_opportunities()
        timing_stats = self.timing_optimizer.get_timing_stats()

        return {
            "active_opportunities": len(active),
            "opportunity_types": [opp.opportunity_type.value for opp in active],
            "timing_stats": timing_stats
        }