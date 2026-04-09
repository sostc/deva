"""
Text Events - 文本处理相关事件

用于 Radar、Attention、Cognition 之间的文本处理流程

事件流程：
1. Radar → TextFetchedEvent（获取外部文本，基础处理）
2. Attention → TextFocusedEvent（根据 ManasState 评分，高分内容）
3. Cognition（深度处理 TextFocusedEvent）
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import time


@dataclass
class TextFetchedEvent:
    """
    文本获取事件

    Radar 获取外部文本/新闻后发布此事件
    Attention 订阅此事件进行重要性评分
    """
    text: str
    title: str
    source: str  # "news_feed", "social_media", "imsg", "wechat", "user_article", "radar_news"
    url: str = ""
    timestamp: float = field(default_factory=time.time)
    keywords: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    sentiment: float = 0.5  # 0-1, 0=负面, 0.5=中性, 1=正面
    stock_codes: List[str] = field(default_factory=list)

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text[:200] + "..." if len(self.text) > 200 else self.text,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "timestamp": self.timestamp,
            "datetime": self.datetime.isoformat(),
            "keywords": self.keywords,
            "topics": self.topics,
            "sentiment": round(self.sentiment, 2),
            "stock_codes": self.stock_codes,
        }


@dataclass
class TextFocusedEvent:
    """
    文本聚焦事件

    Attention 根据 ManasState 评分后发布此事件
    Cognition 订阅此事件进行深度处理
    """
    text: str
    title: str
    source: str
    url: str = ""
    timestamp: float = field(default_factory=time.time)
    importance_score: float = 0.5  # 0-1 重要程度评分
    routing_level: str = "index"  # "deep"=深度处理, "index"=仅索引
    keywords: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    sentiment: float = 0.5
    stock_codes: List[str] = field(default_factory=list)
    manas_state: Optional[Dict[str, Any]] = None  # 评分时的 Manas 状态快照
    summary: str = ""
    narrative_tags: List[str] = field(default_factory=list)
    matched_focus_topics: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)

    @property
    def is_deep(self) -> bool:
        return self.routing_level == "deep"

    def __post_init__(self):
        """轻量字段校验与归一化，避免下游处理分支爆炸"""
        if self.importance_score < 0:
            self.importance_score = 0.0
        elif self.importance_score > 1:
            self.importance_score = 1.0

        if self.sentiment < 0:
            self.sentiment = 0.0
        elif self.sentiment > 1:
            self.sentiment = 1.0

        if self.routing_level not in {"deep", "index", "drop"}:
            self.routing_level = "index"

        self.keywords = list(self.keywords or [])
        self.topics = list(self.topics or [])
        self.stock_codes = list(self.stock_codes or [])
        self.narrative_tags = list(self.narrative_tags or [])
        self.matched_focus_topics = list(self.matched_focus_topics or [])

        if self.summary is None:
            self.summary = ""
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text[:200] + "..." if len(self.text) > 200 else self.text,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "timestamp": self.timestamp,
            "datetime": self.datetime.isoformat(),
            "importance_score": round(self.importance_score, 3),
            "routing_level": self.routing_level,
            "keywords": self.keywords,
            "topics": self.topics,
            "sentiment": round(self.sentiment, 2),
            "stock_codes": self.stock_codes,
            "summary": self.summary,
            "narrative_tags": self.narrative_tags,
            "matched_focus_topics": self.matched_focus_topics,
            "metadata": self.metadata,
        }
