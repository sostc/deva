"""证据与反证数据结构

每条证据必须携带：
- 时间戳
- 数据来源
- 可信度 (0-1)
- 指向的维度（需求/供给/库存/价格/利润/现金流）
- 状态：支持 / 反证 / 中性

EvidenceChain 汇总一条假设下的所有证据，
并可统计支持与反证的权重。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class EvidenceType(Enum):
    """证据类型"""
    NEWS = "news"                   # 产业新闻
    EARNINGS = "earnings"           # 财报/电话会
    ORDER = "order"                 # 订单/交付周期
    PRICE = "price"                 # 产品价格
    CAPACITY = "capacity"           # 产能/资本开支
    POLICY = "policy"               # 政策
    INDUSTRY_REPORT = "industry_report"  # 产业调研/研报
    HIRING = "hiring"               # 招聘
    OTHER = "other"


class EvidenceStatus(Enum):
    """证据对假设的态度"""
    SUPPORTING = "supporting"       # 支持
    REFUTING = "refuting"           # 反证
    NEUTRAL = "neutral"             # 中性/不确定


# 产业状态六维度
FACTOR_DIMENSIONS = (
    "demand",       # 需求
    "supply",       # 供给
    "inventory",    # 库存
    "price",        # 价格
    "profit",       # 利润率
    "cashflow",     # 自由现金流
)


@dataclass
class Evidence:
    """单条证据"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    content: str = ""                          # 证据内容摘要
    source: str = ""                           # 数据来源（如 "某公司Q3财报"、"行业新闻"）
    type: EvidenceType = EvidenceType.OTHER
    status: EvidenceStatus = EvidenceStatus.NEUTRAL
    dimension: str = ""                        # 关联维度（FACTOR_DIMENSIONS 之一）
    timestamp: float = field(default_factory=time.time)
    confidence: float = 0.5                    # 可信度 0-1
    raw_value: Optional[float] = None          # 原始数值（可选，用于量化证据）
    raw_unit: str = ""                         # 数值单位
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "content": self.content,
            "source": self.source,
            "type": self.type.value if isinstance(self.type, EvidenceType) else self.type,
            "status": self.status.value if isinstance(self.status, EvidenceStatus) else self.status,
            "dimension": self.dimension,
            "timestamp": self.timestamp,
            "confidence": float(self.confidence),
            "raw_value": self.raw_value,
            "raw_unit": self.raw_unit,
            "metadata": self.metadata,
        }


@dataclass
class EvidenceChain:
    """证据链：汇总一条假设下的所有证据"""
    hypothesis_id: str = ""
    items: List[Evidence] = field(default_factory=list)

    # ---- 查询 ----
    @property
    def supporting(self) -> List[Evidence]:
        return [e for e in self.items if e.status == EvidenceStatus.SUPPORTING]

    @property
    def refuting(self) -> List[Evidence]:
        return [e for e in self.items if e.status == EvidenceStatus.REFUTING]

    @property
    def neutral(self) -> List[Evidence]:
        return [e for e in self.items if e.status == EvidenceStatus.NEUTRAL]

    def support_score(self) -> float:
        """加权支持分 = Σ(支持证据 confidence) - Σ(反证 confidence)"""
        pos = sum(e.confidence for e in self.supporting)
        neg = sum(e.confidence for e in self.refuting)
        return round(pos - neg, 4)

    def support_ratio(self) -> float:
        """支持占比：支持权重 / (支持+反证权重)，无证据返回 0.5"""
        pos = sum(e.confidence for e in self.supporting)
        neg = sum(e.confidence for e in self.refuting)
        total = pos + neg
        if total <= 0:
            return 0.5
        return round(pos / total, 4)

    def evidence_count(self) -> int:
        return len(self.items)

    # ---- 操作 ----
    def add(self, evidence: Evidence) -> None:
        if not isinstance(evidence, Evidence):
            raise TypeError("evidence must be an Evidence instance")
        self.items.append(evidence)

    def add_many(self, evidences: List[Evidence]) -> None:
        for e in evidences:
            self.add(e)

    def by_dimension(self, dimension: str) -> List[Evidence]:
        return [e for e in self.items if e.dimension == dimension]

    def to_dict(self) -> Dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "items": [e.to_dict() for e in self.items],
            "summary": {
                "total": self.evidence_count(),
                "supporting": len(self.supporting),
                "refuting": len(self.refuting),
                "neutral": len(self.neutral),
                "support_score": self.support_score(),
                "support_ratio": self.support_ratio(),
            },
        }
