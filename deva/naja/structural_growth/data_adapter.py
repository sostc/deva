"""数据适配层 - 将外部数据转换为产业状态输入

职责：
- 定义外部数据到 IndustryState 的转换契约
- 支持财报、新闻、价格、订单等数据类型
- 不直接依赖 SR() 或网络，数据由调用方传入

输入数据格式（统一事件流）：
{
    "industry_id": "hbm",
    "type": "earnings" | "news" | "price" | "order" | "capacity" | "other",
    "dimension": "demand" | "supply" | "inventory" | "price" | "profit" | "cashflow",
    "value": <float>,
    "source": <str>,
    "timestamp": <float>,
    "confidence": <float 0-1>,
    "content": <str>,           # 新闻/公告文本
    "status": "supporting" | "refuting" | "neutral",
}
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from .evidence import Evidence, EvidenceType, EvidenceStatus
from .industry_state import IndustryState, FACTOR_DIMENSIONS
from .observation_pool import ObservationPool


# 外部数据类型 → EvidenceType 映射
_TYPE_TO_EVIDENCE = {
    "earnings": EvidenceType.EARNINGS,
    "news": EvidenceType.NEWS,
    "price": EvidenceType.PRICE,
    "order": EvidenceType.ORDER,
    "capacity": EvidenceType.CAPACITY,
    "policy": EvidenceType.POLICY,
    "industry_report": EvidenceType.INDUSTRY_REPORT,
    "hiring": EvidenceType.HIRING,
    "other": EvidenceType.OTHER,
}

_STATUS_MAP = {
    "supporting": EvidenceStatus.SUPPORTING,
    "refuting": EvidenceStatus.REFUTING,
    "neutral": EvidenceStatus.NEUTRAL,
}


class IndustryDataAdapter:
    """产业数据适配器

    将外部数据事件转换为 IndustryState 的因子更新和证据添加。
    """

    def __init__(self, pool: Optional[ObservationPool] = None):
        self._pool = pool

    # ---- 单条数据 ----
    def feed(self, state: IndustryState, event: Dict) -> None:
        """处理一条数据事件，更新产业状态"""
        dimension = event.get("dimension", "")
        value = event.get("value")
        source = event.get("source", "")
        timestamp = event.get("timestamp") or time.time()
        confidence = float(event.get("confidence", 0.5))
        content = event.get("content", "")
        status_str = event.get("status", "neutral")
        ev_type_str = event.get("type", "other")

        # 1. 如果有数值且维度合法，更新因子
        if value is not None and dimension in FACTOR_DIMENSIONS:
            state.update_factor(dimension, float(value), source=source, timestamp=timestamp)

        # 2. 如果有文本内容，生成证据
        if content:
            status = _STATUS_MAP.get(status_str, EvidenceStatus.NEUTRAL)
            ev_type = _TYPE_TO_EVIDENCE.get(ev_type_str, EvidenceType.OTHER)
            evidence = Evidence(
                content=content,
                source=source,
                type=ev_type,
                status=status,
                dimension=dimension if dimension in FACTOR_DIMENSIONS else "",
                confidence=confidence,
                timestamp=timestamp,
            )
            is_counter = status == EvidenceStatus.REFUTING
            state.add_evidence(evidence, is_counter=is_counter)

    def feed_many(self, state: IndustryState, events: List[Dict]) -> None:
        """批量处理数据事件"""
        for event in events:
            self.feed(state, event)

    # ---- 便捷方法：财报 ----
    def feed_earnings(self, state: IndustryState, revenue: Optional[float] = None,
                      profit: Optional[float] = None, margin: Optional[float] = None,
                      cashflow: Optional[float] = None, source: str = "",
                      timestamp: Optional[float] = None) -> None:
        """从财报数据更新因子

        Args:
            revenue: 营收（用于推导需求）
            profit: 净利润
            margin: 毛利率 (%)
            cashflow: 自由现金流
        """
        ts = timestamp or time.time()
        if revenue is not None:
            state.update_factor("demand", float(revenue), source=source, timestamp=ts)
        if margin is not None:
            state.update_factor("profit", float(margin), source=source, timestamp=ts)
        if cashflow is not None:
            state.update_factor("cashflow", float(cashflow), source=source, timestamp=ts)

    # ---- 便捷方法：新闻 ----
    def feed_news(self, state: IndustryState, content: str, source: str = "",
                  dimension: str = "", status: str = "neutral",
                  confidence: float = 0.5, timestamp: Optional[float] = None) -> None:
        """添加一条新闻作为证据"""
        self.feed(state, {
            "type": "news",
            "content": content,
            "source": source,
            "dimension": dimension,
            "status": status,
            "confidence": confidence,
            "timestamp": timestamp or time.time(),
        })

    # ---- 便捷方法：价格 ----
    def feed_price(self, state: IndustryState, price: float, source: str = "",
                   timestamp: Optional[float] = None) -> None:
        """更新产品价格"""
        state.update_factor("price", float(price), source=source,
                            timestamp=timestamp or time.time())

    # ---- 通过观察池操作 ----
    def feed_to_pool(self, industry_id: str, event: Dict) -> bool:
        """向观察池中指定行业喂数据"""
        if self._pool is None:
            return False
        tracked = self._pool.get(industry_id)
        if tracked is None:
            return False
        self.feed(tracked.state, event)
        return True
