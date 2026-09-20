"""产业状态卡模型

每个行业一张动态状态卡，六个核心维度：
- demand    需求
- supply    供给
- inventory 库存
- price     价格
- profit    利润率
- cashflow  自由现金流

每个维度 FactorState 维护历史数据点，
可计算一阶导（变化率 D1）和二阶导（变化率的变化 D2），
用于识别"增速正在加快"这类二阶导信号。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .evidence import Evidence, FACTOR_DIMENSIONS


class FactorTrend(Enum):
    """维度趋势（基于二阶导判断）"""
    ACCELERATING = "accelerating"   # 增速加快
    STABLE = "stable"               # 平稳
    DECELERATING = "decelerating"   # 增速放缓


@dataclass
class HistoryPoint:
    """单个历史数据点"""
    value: float
    timestamp: float
    source: str = ""

    def to_dict(self) -> Dict:
        return {
            "value": float(self.value),
            "timestamp": self.timestamp,
            "source": self.source,
        }


@dataclass
class FactorState:
    """单个维度的状态"""
    dimension: str
    current_value: Optional[float] = None
    unit: str = ""
    confidence: float = 0.0
    sources: List[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)
    history: List[HistoryPoint] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)

    # ---- 历史管理 ----
    def record(self, value: float, source: str = "", timestamp: Optional[float] = None) -> None:
        """记录一个新数据点，自动更新 current_value 和 history"""
        ts = timestamp if timestamp is not None else time.time()
        self.history.append(HistoryPoint(value=float(value), timestamp=ts, source=source))
        # 按时间排序
        self.history.sort(key=lambda p: p.timestamp)
        self.current_value = float(value)
        self.last_updated = ts
        if source and source not in self.sources:
            self.sources.append(source)

    # ---- 一阶导 / 二阶导 ----
    def first_derivative(self) -> Optional[float]:
        """一阶导 D1：最近两点的变化率（单位/秒，调用方按需换算）"""
        if len(self.history) < 2:
            return None
        p0, p1 = self.history[-2], self.history[-1]
        dt = p1.timestamp - p0.timestamp
        if dt <= 0:
            return None
        return (p1.value - p0.value) / dt

    def second_derivative(self) -> Optional[float]:
        """二阶导 D2：一阶导的变化率"""
        d1_list = self._first_derivatives()
        if len(d1_list) < 2:
            return None
        d0, d1 = d1_list[-2], d1_list[-1]
        # 用最新两个历史点的时间间隔近似
        if len(self.history) < 3:
            return None
        p_prev, p_curr = self.history[-2], self.history[-1]
        dt = p_curr.timestamp - p_prev.timestamp
        if dt <= 0:
            return None
        return (d1 - d0) / dt

    def _first_derivatives(self) -> List[float]:
        """返回所有相邻点之间的一阶导序列"""
        ds = []
        for i in range(1, len(self.history)):
            p0, p1 = self.history[i - 1], self.history[i]
            dt = p1.timestamp - p0.timestamp
            if dt > 0:
                ds.append((p1.value - p0.value) / dt)
        return ds

    def trend(self, threshold_pp: float = 1.0) -> FactorTrend:
        """根据增长率变化（百分点）判断趋势方向

        threshold_pp: 判定为加速/减速的最小百分点变化，默认 1.0 pp
        """
        accel = self.growth_acceleration()
        if accel is None:
            return FactorTrend.STABLE
        if accel > threshold_pp:
            return FactorTrend.ACCELERATING
        elif accel < -threshold_pp:
            return FactorTrend.DECELERATING
        return FactorTrend.STABLE

    def growth_rate(self) -> Optional[float]:
        """增长率（百分比）= (最新值 - 前值) / |前值| * 100"""
        if len(self.history) < 2:
            return None
        p0 = self.history[-2].value
        p1 = self.history[-1].value
        if abs(p0) < 1e-12:
            return None
        return ((p1 - p0) / abs(p0)) * 100.0

    def growth_acceleration(self) -> Optional[float]:
        """增长率的变化（二阶导近似，百分点）"""
        if len(self.history) < 3:
            return None
        rates = []
        for i in range(1, len(self.history)):
            p0 = self.history[i - 1].value
            if abs(p0) < 1e-12:
                continue
            p1 = self.history[i].value
            rates.append((p1 - p0) / abs(p0) * 100.0)
        if len(rates) < 2:
            return None
        return rates[-1] - rates[-2]

    def to_dict(self) -> Dict:
        return {
            "dimension": self.dimension,
            "current_value": self.current_value,
            "unit": self.unit,
            "confidence": float(self.confidence),
            "sources": list(self.sources),
            "last_updated": self.last_updated,
            "history": [p.to_dict() for p in self.history],
            "first_derivative": self.first_derivative(),
            "second_derivative": self.second_derivative(),
            "growth_rate_pct": self.growth_rate(),
            "growth_acceleration_pp": self.growth_acceleration(),
            "trend": self.trend().value,
        }


@dataclass
class SecondDerivativeSignals:
    """二阶导信号汇总

    每个字段为 Optional[float]，单位为百分点/单位时间，
    正值表示加速，负值表示减速。
    """
    demand_growth_acceleration: Optional[float] = None     # 需求增速变化
    order_growth_acceleration: Optional[float] = None      # 订单增速变化
    price_change_acceleration: Optional[float] = None      # 价格变化加速
    margin_improvement_speed: Optional[float] = None       # 毛利率改善速度（二阶导）
    margin_improvement_acceleration: Optional[float] = None  # 毛利率改善的加速
    cashflow_conversion_change: Optional[float] = None     # 现金流转化率变化
    supply_growth_acceleration: Optional[float] = None     # 供给增速变化
    inventory_change_acceleration: Optional[float] = None  # 库存变化加速

    def summary(self) -> Dict:
        """给出哪些信号为正（加速）"""
        pos, neg, unknown = [], [], []
        for name, val in self.__dict__.items():
            if val is None:
                unknown.append(name)
            elif val > 0:
                pos.append(name)
            elif val < 0:
                neg.append(name)
        return {"accelerating": pos, "decelerating": neg, "unknown": unknown}

    def to_dict(self) -> Dict:
        return {
            "demand_growth_acceleration": self.demand_growth_acceleration,
            "order_growth_acceleration": self.order_growth_acceleration,
            "price_change_acceleration": self.price_change_acceleration,
            "margin_improvement_speed": self.margin_improvement_speed,
            "margin_improvement_acceleration": self.margin_improvement_acceleration,
            "cashflow_conversion_change": self.cashflow_conversion_change,
            "supply_growth_acceleration": self.supply_growth_acceleration,
            "inventory_change_acceleration": self.inventory_change_acceleration,
            "summary": self.summary(),
        }


@dataclass
class IndustryState:
    """产业状态卡"""
    industry_id: str
    name: str
    updated_at: float = field(default_factory=time.time)

    # 六维度
    demand: FactorState = field(default_factory=lambda: FactorState(dimension="demand"))
    supply: FactorState = field(default_factory=lambda: FactorState(dimension="supply"))
    inventory: FactorState = field(default_factory=lambda: FactorState(dimension="inventory"))
    price: FactorState = field(default_factory=lambda: FactorState(dimension="price"))
    profit: FactorState = field(default_factory=lambda: FactorState(dimension="profit"))
    cashflow: FactorState = field(default_factory=lambda: FactorState(dimension="cashflow"))

    # 二阶导信号
    signals: SecondDerivativeSignals = field(default_factory=SecondDerivativeSignals)

    # 证据
    evidence: List[Evidence] = field(default_factory=list)
    counter_evidence: List[Evidence] = field(default_factory=list)

    # 公司列表（可选）
    companies: List[str] = field(default_factory=list)

    # ---- 维度访问 ----
    def get_factor(self, dimension: str) -> FactorState:
        if dimension not in FACTOR_DIMENSIONS:
            raise ValueError(f"unknown dimension: {dimension}, must be one of {FACTOR_DIMENSIONS}")
        return getattr(self, dimension)

    def all_factors(self) -> Dict[str, FactorState]:
        return {d: getattr(self, d) for d in FACTOR_DIMENSIONS}

    # ---- 更新 ----
    def update_factor(self, dimension: str, value: float, source: str = "",
                      timestamp: Optional[float] = None) -> None:
        factor = self.get_factor(dimension)
        factor.record(value, source=source, timestamp=timestamp)
        self.updated_at = time.time()

    def add_evidence(self, evidence: Evidence, is_counter: bool = False) -> None:
        if is_counter:
            self.counter_evidence.append(evidence)
        else:
            self.evidence.append(evidence)

    # ---- 二阶导信号计算 ----
    def recompute_signals(self) -> None:
        """根据六维度历史重新计算二阶导信号"""
        self.signals.demand_growth_acceleration = self.demand.growth_acceleration()
        self.signals.supply_growth_acceleration = self.supply.growth_acceleration()
        self.signals.price_change_acceleration = self.price.growth_acceleration()
        self.signals.margin_improvement_speed = self.profit.growth_rate()
        self.signals.margin_improvement_acceleration = self.profit.growth_acceleration()
        self.signals.cashflow_conversion_change = self.cashflow.growth_acceleration()
        self.signals.inventory_change_acceleration = self.inventory.growth_acceleration()
        # order 信号：如果有订单数据可挂在 demand.metadata，这里暂从 demand 推导
        self.signals.order_growth_acceleration = self.demand.growth_acceleration()

    # ---- 结构化输出 ----
    def to_dict(self) -> Dict:
        self.recompute_signals()
        return {
            "industry_id": self.industry_id,
            "name": self.name,
            "updated_at": self.updated_at,
            "factors": {d: f.to_dict() for d, f in self.all_factors().items()},
            "signals": self.signals.to_dict(),
            "evidence": [e.to_dict() for e in self.evidence],
            "counter_evidence": [e.to_dict() for e in self.counter_evidence],
            "companies": list(self.companies),
        }
