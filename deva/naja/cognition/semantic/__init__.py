"""Cognition Semantic - 语义子域

包含：
- NewsEvent/SignalType: 新闻事件数据结构
- AttentionScorer: 注意力评分器
- Topic/TopicManager: 主题管理
- SemanticColdStart: 语义图谱冷启动
- KeywordRegistry: 统一关键词注册表
"""

from .news_event import (
    NewsEvent,
    SignalType,
    DATASOURCE_TYPE_MAP,
    get_datasource_type,
)
from .attention_scorer import AttentionScorer
from .topic_manager import (
    Topic,
    STOCK_RELEVANT_PREFIXES,
    STOCK_RELEVANT_SOURCES,
    _get_market_activity,
    _is_stock_relevant_topic,
)
from .semantic_cold_start import SemanticColdStart
from .keyword_registry import (
    DEFAULT_NARRATIVE_KEYWORDS,
    DYNAMICS_KEYWORDS,
    SENTIMENT_KEYWORDS,
    SUPPLY_DEMAND_KEYWORDS,
    MARKET_NARRATIVE_KEYWORDS,
    NEWS_TOPIC_KEYWORDS,
)

__all__ = [
    # 新闻事件
    "NewsEvent",
    "SignalType",
    "DATASOURCE_TYPE_MAP",
    "get_datasource_type",
    # 注意力评分
    "AttentionScorer",
    # 主题管理
    "Topic",
    "STOCK_RELEVANT_PREFIXES",
    "STOCK_RELEVANT_SOURCES",
    "_get_market_activity",
    "_is_stock_relevant_topic",
    # 语义冷启动
    "SemanticColdStart",
    # 关键词注册表
    "DEFAULT_NARRATIVE_KEYWORDS",
    "DYNAMICS_KEYWORDS",
    "SENTIMENT_KEYWORDS",
    "SUPPLY_DEMAND_KEYWORDS",
    "MARKET_NARRATIVE_KEYWORDS",
    "NEWS_TOPIC_KEYWORDS",
]
