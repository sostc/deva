"""Bandit 盈亏归因分析系统

提供完整的策略收益归因分析，包括：
1. 策略贡献度分析 - 每个策略赚了/亏了多少钱
2. 收益归因分解 - 选股收益、时机收益、仓位管理收益
3. 信号质量分析 - 高信心 vs 低信心信号的表现差异
4. 市场条件关联 - 不同市场环境下策略表现

使用方式：
    from deva.naja.bandit.attribution import get_attribution

    attr = get_attribution()
    report = attr.get_full_attribution_report()
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from deva import NB

log = logging.getLogger(__name__)

ATTRIBUTION_TABLE = "naja_bandit_attribution"
POSITION_REWARD_TABLE = "naja_bandit_position_rewards"


@dataclass
class TradeAttribution:
    """交易归因记录"""
    position_id: str
    strategy_id: str
    stock_code: str
    stock_name: str

    total_return_pct: float
    selection_return_pct: float
    timing_return_pct: float
    position_return_pct: float

    market_liquidity: float
    market_volatility: float

    signal_confidence: float
    signal_timestamp: float

    entry_time: float
    exit_time: float
    holding_seconds: float

    close_reason: str

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "strategy_id": self.strategy_id,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "total_return_pct": self.total_return_pct,
            "selection_return_pct": self.selection_return_pct,
            "timing_return_pct": self.timing_return_pct,
            "position_return_pct": self.position_return_pct,
            "market_liquidity": self.market_liquidity,
            "market_volatility": self.market_volatility,
            "signal_confidence": self.signal_confidence,
            "signal_timestamp": self.signal_timestamp,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "holding_seconds": self.holding_seconds,
            "close_reason": self.close_reason,
        }


@dataclass
class StrategyContribution:
    """策略贡献度"""
    strategy_id: str
    total_return: float
    total_trades: int
    win_trades: int
    win_rate: float
    avg_return: float
    best_return: float
    worst_return: float
    avg_holding_seconds: float
    total_profit: float
    total_loss: float
    profit_loss_ratio: float
    rank: int = 0


@dataclass
class SignalQualityAnalysis:
    """信号质量分析"""
    strategy_id: str
    high_confidence_trades: int
    high_confidence_avg_return: float
    medium_confidence_trades: int
    medium_confidence_avg_return: float
    low_confidence_trades: int
    low_confidence_avg_return: float
    confidence_return_correlation: float


@dataclass
class MarketConditionAttribution:
    """市场条件归因"""
    strategy_id: str
    liquidity_high_avg: float
    liquidity_high_count: int
    liquidity_mid_avg: float
    liquidity_mid_count: int
    liquidity_low_avg: float
    liquidity_low_count: int
    volatility_high_avg: float
    volatility_high_count: int
    volatility_low_avg: float
    volatility_low_count: int


class StrategyAttribution:
    """策略归因分析器

    核心功能：
    1. 策略贡献度分析 - 每个策略的收益、交易次数、胜率
    2. 收益归因分解 - 选股收益、时机收益、仓位管理收益
    3. 信号质量分析 - 不同信心度信号的表现
    4. 市场条件关联 - 不同市场环境下策略表现
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._db = NB(ATTRIBUTION_TABLE)
        self._reward_db = NB(POSITION_REWARD_TABLE)
        self._cache: Dict[str, Any] = {}
        self._cache_time: float = 0
        self._cache_ttl = 60

        self._initialized = True
        log.info("[Attribution] 策略归因分析器初始化完成")

    def _get_cached(self, key: str) -> Optional[Any]:
        now = time.time()
        if now - self._cache_time < self._cache_ttl and key in self._cache:
            return self._cache[key]
        return None

    def _set_cached(self, key: str, value: Any):
        self._cache[key] = value
        self._cache_time = time.time()

    def record_trade(
        self,
        position_id: str,
        strategy_id: str,
        stock_code: str,
        stock_name: str,
        entry_price: float,
        exit_price: float,
        entry_time: float,
        exit_time: float,
        holding_seconds: float,
        close_reason: str,
        signal_confidence: float = 0.5,
        market_liquidity: float = 0.5,
        market_volatility: float = 0.5,
    ) -> TradeAttribution:
        """记录一笔交易的归因数据

        Args:
            position_id: 持仓ID
            strategy_id: 策略ID
            stock_code: 股票代码
            stock_name: 股票名称
            entry_price: 入场价格
            exit_price: 出场价格
            entry_time: 入场时间戳
            exit_time: 出场时间戳
            holding_seconds: 持仓秒数
            close_reason: 平仓原因
            signal_confidence: 信号信心度
            market_liquidity: 入场时市场流动性
            market_volatility: 入场时市场波动率

        Returns:
            TradeAttribution: 归因记录
        """
        total_return = (exit_price - entry_price) / entry_price * 100

        selection_return = self._calculate_selection_return(total_return, holding_seconds)
        timing_return = self._calculate_timing_return(total_return, holding_seconds)
        position_return = total_return - selection_return - timing_return

        attribution = TradeAttribution(
            position_id=position_id,
            strategy_id=strategy_id,
            stock_code=stock_code,
            stock_name=stock_name,
            total_return_pct=total_return,
            selection_return_pct=selection_return,
            timing_return_pct=timing_return,
            position_return_pct=position_return,
            market_liquidity=market_liquidity,
            market_volatility=market_volatility,
            signal_confidence=signal_confidence,
            signal_timestamp=entry_time,
            entry_time=entry_time,
            exit_time=exit_time,
            holding_seconds=holding_seconds,
            close_reason=close_reason,
        )

        self._save_attribution(attribution)
        self._invalidate_cache()

        return attribution

    def _calculate_selection_return(self, total_return: float, holding_seconds: float) -> float:
        """计算选股贡献

        选股贡献 = 总收益 * (持仓时间因子)
        持仓时间越长，选股贡献权重越高
        """
        hour_factor = min(holding_seconds / 3600, 24) / 24
        return total_return * (0.3 + 0.4 * hour_factor)

    def _calculate_timing_return(self, total_return: float, holding_seconds: float) -> float:
        """计算时机贡献

        时机贡献 = 总收益 * (1 - 持仓时间因子)
        持仓时间越短，时机贡献权重越高
        """
        hour_factor = min(holding_seconds / 3600, 24) / 24
        return total_return * (0.7 - 0.4 * hour_factor)

    def _calculate_position_return(self, total_return: float, selection: float, timing: float) -> float:
        """计算仓位管理贡献"""
        return total_return - selection - timing

    def _save_attribution(self, attr: TradeAttribution):
        """保存归因记录"""
        try:
            key = f"{attr.position_id}_{int(attr.exit_time * 1000)}"
            self._db[key] = attr.to_dict()
        except Exception as e:
            log.error(f"保存归因记录失败: {e}")

    def _invalidate_cache(self):
        """使缓存失效"""
        self._cache.clear()
        self._cache_time = 0

    def get_strategy_contribution(self, strategy_id: str) -> StrategyContribution:
        """获取策略贡献度

        Returns:
            StrategyContribution: 策略贡献度数据
        """
        cached = self._get_cached(f"contribution_{strategy_id}")
        if cached:
            return cached

        records = self._get_strategy_records(strategy_id)

        if not records:
            return StrategyContribution(
                strategy_id=strategy_id,
                total_return=0.0,
                total_trades=0,
                win_trades=0,
                win_rate=0.0,
                avg_return=0.0,
                best_return=0.0,
                worst_return=0.0,
                avg_holding_seconds=0.0,
                total_profit=0.0,
                total_loss=0.0,
                profit_loss_ratio=0.0,
            )

        total_return = sum(r["total_return_pct"] for r in records)
        returns = [r["total_return_pct"] for r in records]
        wins = sum(1 for r in returns if r > 0)
        profits = sum(r for r in returns if r > 0)
        losses = abs(sum(r for r in returns if r < 0))

        contribution = StrategyContribution(
            strategy_id=strategy_id,
            total_return=total_return,
            total_trades=len(records),
            win_trades=wins,
            win_rate=wins / len(records) * 100 if records else 0,
            avg_return=sum(returns) / len(returns) if returns else 0,
            best_return=max(returns) if returns else 0,
            worst_return=min(returns) if returns else 0,
            avg_holding_seconds=sum(r["holding_seconds"] for r in records) / len(records),
            total_profit=profits,
            total_loss=losses,
            profit_loss_ratio=profits / losses if losses > 0 else float("inf"),
        )

        self._set_cached(f"contribution_{strategy_id}", contribution)
        return contribution

    def get_all_strategy_contributions(self) -> List[StrategyContribution]:
        """获取所有策略贡献度（按总收益排序）

        Returns:
            List[StrategyContribution]: 策略贡献度列表
        """
        strategy_ids = set()
        for key in self._db.keys():
            try:
                data = self._db[key]
                if isinstance(data, dict):
                    strategy_ids.add(data.get("strategy_id", ""))
            except Exception:
                pass

        contributions = [self.get_strategy_contribution(sid) for sid in strategy_ids]
        contributions.sort(key=lambda x: x.total_return, reverse=True)

        for i, c in enumerate(contributions):
            c.rank = i + 1

        return contributions

    def get_signal_quality_analysis(self, strategy_id: str) -> SignalQualityAnalysis:
        """获取信号质量分析

        按信心度分为高(>0.7)、中(0.4-0.7)、低(<0.4)三档

        Returns:
            SignalQualityAnalysis: 信号质量分析
        """
        cached = self._get_cached(f"signal_quality_{strategy_id}")
        if cached:
            return cached

        records = self._get_strategy_records(strategy_id)

        high_conf = [r for r in records if r.get("signal_confidence", 0) > 0.7]
        mid_conf = [r for r in records if 0.4 <= r.get("signal_confidence", 0) <= 0.7]
        low_conf = [r for r in records if r.get("signal_confidence", 0) < 0.4]

        def avg_return(recs):
            if not recs:
                return 0.0
            return sum(r["total_return_pct"] for r in recs) / len(recs)

        correlation = self._calculate_correlation(records)

        analysis = SignalQualityAnalysis(
            strategy_id=strategy_id,
            high_confidence_trades=len(high_conf),
            high_confidence_avg_return=avg_return(high_conf),
            medium_confidence_trades=len(mid_conf),
            medium_confidence_avg_return=avg_return(mid_conf),
            low_confidence_trades=len(low_conf),
            low_confidence_avg_return=avg_return(low_conf),
            confidence_return_correlation=correlation,
        )

        self._set_cached(f"signal_quality_{strategy_id}", analysis)
        return analysis

    def _calculate_correlation(self, records: List[dict]) -> float:
        """计算信心度与收益的相关性"""
        if len(records) < 3:
            return 0.0

        confidences = [r.get("signal_confidence", 0) for r in records]
        returns = [r["total_return_pct"] for r in records]

        n = len(records)
        mean_c = sum(confidences) / n
        mean_r = sum(returns) / n

        cov = sum((c - mean_c) * (r - mean_r) for c, r in zip(confidences, returns)) / n
        std_c = (sum((c - mean_c) ** 2 for c in confidences) / n) ** 0.5
        std_r = (sum((r - mean_r) ** 2 for r in returns) / n) ** 0.5

        if std_c == 0 or std_r == 0:
            return 0.0

        return cov / (std_c * std_r)

    def get_market_condition_attribution(self, strategy_id: str) -> MarketConditionAttribution:
        """获取市场条件归因

        按流动性和波动率分档分析策略表现

        Returns:
            MarketConditionAttribution: 市场条件归因
        """
        cached = self._get_cached(f"market_condition_{strategy_id}")
        if cached:
            return cached

        records = self._get_strategy_records(strategy_id)

        liq_high = [r for r in records if r.get("market_liquidity", 0.5) > 0.7]
        liq_mid = [r for r in records if 0.3 <= r.get("market_liquidity", 0.5) <= 0.7]
        liq_low = [r for r in records if r.get("market_liquidity", 0.5) < 0.3]

        vol_high = [r for r in records if r.get("market_volatility", 0.5) > 0.7]
        vol_low = [r for r in records if r.get("market_volatility", 0.5) < 0.3]

        def avg_return(recs):
            if not recs:
                return 0.0
            return sum(r["total_return_pct"] for r in recs) / len(recs)

        attribution = MarketConditionAttribution(
            strategy_id=strategy_id,
            liquidity_high_avg=avg_return(liq_high),
            liquidity_high_count=len(liq_high),
            liquidity_mid_avg=avg_return(liq_mid),
            liquidity_mid_count=len(liq_mid),
            liquidity_low_avg=avg_return(liq_low),
            liquidity_low_count=len(liq_low),
            volatility_high_avg=avg_return(vol_high),
            volatility_high_count=len(vol_high),
            volatility_low_avg=avg_return(vol_low),
            volatility_low_count=len(vol_low),
        )

        self._set_cached(f"market_condition_{strategy_id}", attribution)
        return attribution

    def get_attribution_breakdown(self, strategy_id: str) -> dict:
        """获取收益归因分解

        Returns:
            dict: {
                "selection_return": 选股贡献总收益,
                "timing_return": 时机贡献总收益,
                "position_return": 仓位管理贡献总收益,
                "total_return": 总收益,
            }
        """
        records = self._get_strategy_records(strategy_id)

        if not records:
            return {
                "selection_return": 0.0,
                "timing_return": 0.0,
                "position_return": 0.0,
                "total_return": 0.0,
            }

        return {
            "selection_return": sum(r["selection_return_pct"] for r in records),
            "timing_return": sum(r["timing_return_pct"] for r in records),
            "position_return": sum(r["position_return_pct"] for r in records),
            "total_return": sum(r["total_return_pct"] for r in records),
        }

    def get_full_attribution_report(self, strategy_id: Optional[str] = None) -> dict:
        """获取完整归因报告

        Args:
            strategy_id: 策略ID (None 表示所有策略)

        Returns:
            dict: 完整归因报告
        """
        if strategy_id:
            contributions = [self.get_strategy_contribution(strategy_id)]
            signal_quality = self.get_signal_quality_analysis(strategy_id)
            market_condition = self.get_market_condition_attribution(strategy_id)
            breakdown = self.get_attribution_breakdown(strategy_id)
        else:
            contributions = self.get_all_strategy_contributions()
            signal_quality = None
            market_condition = None
            breakdown = {
                "selection_return": sum(c.total_return for c in contributions),
                "timing_return": 0.0,
                "position_return": 0.0,
                "total_return": sum(c.total_return for c in contributions),
            }

        return {
            "timestamp": time.time(),
            "strategy_id": strategy_id or "ALL",
            "contributions": [self._contrib_to_dict(c) for c in contributions],
            "signal_quality": self._signal_to_dict(signal_quality) if signal_quality else None,
            "market_condition": self._market_to_dict(market_condition) if market_condition else None,
            "breakdown": breakdown,
            "summary": self._generate_summary(contributions),
        }

    def _generate_summary(self, contributions: List[StrategyContribution]) -> dict:
        """生成归因摘要"""
        if not contributions:
            return {
                "total_strategies": 0,
                "total_trades": 0,
                "total_return": 0.0,
                "best_strategy": None,
                "worst_strategy": None,
                "avg_win_rate": 0.0,
            }

        winning = [c for c in contributions if c.total_return > 0]
        losing = [c for c in contributions if c.total_return <= 0]

        return {
            "total_strategies": len(contributions),
            "total_trades": sum(c.total_trades for c in contributions),
            "total_return": sum(c.total_return for c in contributions),
            "best_strategy": contributions[0].strategy_id if contributions else None,
            "worst_strategy": contributions[-1].strategy_id if contributions else None,
            "winning_strategies": len(winning),
            "losing_strategies": len(losing),
            "avg_win_rate": sum(c.win_rate for c in contributions) / len(contributions),
        }

    def _get_strategy_records(self, strategy_id: str) -> List[dict]:
        """获取策略的所有归因记录"""
        records = []
        for key in self._db.keys():
            try:
                data = self._db[key]
                if isinstance(data, dict) and data.get("strategy_id") == strategy_id:
                    records.append(data)
            except Exception:
                pass
        return records

    def _contrib_to_dict(self, c: StrategyContribution) -> dict:
        return {
            "rank": c.rank,
            "strategy_id": c.strategy_id,
            "total_return": c.total_return,
            "total_trades": c.total_trades,
            "win_rate": c.win_rate,
            "avg_return": c.avg_return,
            "best_return": c.best_return,
            "worst_return": c.worst_return,
            "avg_holding_seconds": c.avg_holding_seconds,
            "total_profit": c.total_profit,
            "total_loss": c.total_loss,
            "profit_loss_ratio": c.profit_loss_ratio,
        }

    def _signal_to_dict(self, s: SignalQualityAnalysis) -> dict:
        return {
            "strategy_id": s.strategy_id,
            "high_confidence_trades": s.high_confidence_trades,
            "high_confidence_avg_return": s.high_confidence_avg_return,
            "medium_confidence_trades": s.medium_confidence_trades,
            "medium_confidence_avg_return": s.medium_confidence_avg_return,
            "low_confidence_trades": s.low_confidence_trades,
            "low_confidence_avg_return": s.low_confidence_avg_return,
            "confidence_return_correlation": s.confidence_return_correlation,
        }

    def _market_to_dict(self, m: MarketConditionAttribution) -> dict:
        return {
            "strategy_id": m.strategy_id,
            "liquidity_high_avg": m.liquidity_high_avg,
            "liquidity_high_count": m.liquidity_high_count,
            "liquidity_mid_avg": m.liquidity_mid_avg,
            "liquidity_mid_count": m.liquidity_mid_count,
            "liquidity_low_avg": m.liquidity_low_avg,
            "liquidity_low_count": m.liquidity_low_count,
            "volatility_high_avg": m.volatility_high_avg,
            "volatility_high_count": m.volatility_high_count,
            "volatility_low_avg": m.volatility_low_avg,
            "volatility_low_count": m.volatility_low_count,
        }

    def get_trade_history(
        self,
        strategy_id: Optional[str] = None,
        limit: int = 50,
        sort_by: str = "exit_time",
    ) -> List[dict]:
        """获取交易历史

        Args:
            strategy_id: 策略ID (None 表示所有)
            limit: 返回数量
            sort_by: 排序字段 (exit_time, total_return)

        Returns:
            List[dict]: 交易历史
        """
        records = []
        for key in self._db.keys():
            try:
                data = self._db[key]
                if isinstance(data, dict):
                    if strategy_id is None or data.get("strategy_id") == strategy_id:
                        records.append(data)
            except Exception:
                pass

        reverse = sort_by in ("exit_time", "total_return")
        if sort_by == "exit_time":
            records.sort(key=lambda x: x.get("exit_time", 0), reverse=reverse)
        elif sort_by == "total_return":
            records.sort(key=lambda x: x.get("total_return_pct", 0), reverse=reverse)

        return records[:limit]


_attribution: Optional[StrategyAttribution] = None
_attribution_lock = threading.Lock()


def get_attribution() -> StrategyAttribution:
    global _attribution
    if _attribution is None:
        with _attribution_lock:
            if _attribution is None:
                _attribution = StrategyAttribution()
    return _attribution


def record_trade_attribution(
    position_id: str,
    strategy_id: str,
    stock_code: str,
    stock_name: str,
    entry_price: float,
    exit_price: float,
    entry_time: float,
    exit_time: float,
    holding_seconds: float,
    close_reason: str,
    signal_confidence: float = 0.5,
    market_liquidity: float = 0.5,
    market_volatility: float = 0.5,
) -> TradeAttribution:
    """便捷函数：记录交易归因"""
    return get_attribution().record_trade(
        position_id=position_id,
        strategy_id=strategy_id,
        stock_code=stock_code,
        stock_name=stock_name,
        entry_price=entry_price,
        exit_price=exit_price,
        entry_time=entry_time,
        exit_time=exit_time,
        holding_seconds=holding_seconds,
        close_reason=close_reason,
        signal_confidence=signal_confidence,
        market_liquidity=market_liquidity,
        market_volatility=market_volatility,
    )


__all__ = [
    "StrategyAttribution",
    "TradeAttribution",
    "StrategyContribution",
    "SignalQualityAnalysis",
    "MarketConditionAttribution",
    "get_attribution",
    "record_trade_attribution",
]
