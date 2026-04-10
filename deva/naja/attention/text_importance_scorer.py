"""
TextImportanceScorer - 文本重要程度评分器

根据 ManasState（末那识状态）对文本进行重要性评分
高分文本发布 TextFocusedEvent 供 Cognition 深度处理
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
import re

from deva.naja.events.text_events import TextFetchedEvent, TextFocusedEvent
from deva.naja.cognition.keyword_registry import (
    DEFAULT_NARRATIVE_KEYWORDS,
    MARKET_NARRATIVE_KEYWORDS,
    NEWS_TOPIC_KEYWORDS,
    SENTIMENT_KEYWORDS,
)

log = logging.getLogger(__name__)


THRESHOLD_DEEP = 0.6
THRESHOLD_INDEX = 0.3
THRESHOLD_DROP = 0.2


class TextImportanceScorer:
    """
    文本重要程度评分器

    根据 ManasState 计算文本的重要程度分数
    高于阈值的内容发布 TextFocusedEvent

    使用方式：
        scorer = TextImportanceScorer(attention_os)
        scorer.set_manas_state(focus_topics=["AI算力", "芯片"], harmony=0.7)
    """

    def __init__(self, attention_os: Optional[Any] = None):
        """
        初始化文本评分器

        Args:
            attention_os: AttentionOS 实例，用于获取 ManasState
        """
        self._attention_os = attention_os
        self._manas_state: Optional[Dict[str, Any]] = None
        self._focus_keyword_map: Dict[str, List[str]] = defaultdict(list)
        self._init_focus_keywords()

        self._stats = {
            "total_received": 0,
            "deep_count": 0,
            "index_count": 0,
            "drop_count": 0,
        }

    def _init_focus_keywords(self):
        """初始化焦点关键词映射"""
        if DEFAULT_NARRATIVE_KEYWORDS:
            self._focus_keyword_map = DEFAULT_NARRATIVE_KEYWORDS
        else:
            self._focus_keyword_map = {}

    def set_manas_state(self, state: Dict[str, Any]):
        """设置末那识状态"""
        self._manas_state = state
        focus_topics = state.get("focus_topics", [])
        log.debug(f"[TextImportanceScorer] 更新末那识状态: {len(focus_topics)} 个焦点")

    def on_text_fetched(self, event: TextFetchedEvent):
        """
        处理文本获取事件

        Args:
            event: TextFetchedEvent 实例
        """
        self._stats["total_received"] += 1

        keywords, topics = self._extract_keywords_topics(event.text, event.title)
        sentiment = self._compute_sentiment(event.text, event.title)
        stock_codes = self._extract_stock_codes(event.text + " " + event.title)
        matched_focus_topics = self._get_focus_topic_matches(event.text, event.title)

        score = self._compute_importance(event, matched_focus_topics)

        if score >= THRESHOLD_DEEP:
            level = "deep"
            self._stats["deep_count"] += 1
        elif score >= THRESHOLD_INDEX:
            level = "index"
            self._stats["index_count"] += 1
        else:
            level = "drop"
            self._stats["drop_count"] += 1
            log.debug(f"[TextImportanceScorer] 丢弃低重要程度文本: {event.title[:30]}... score={score:.2f}")
            return

        focused_event = TextFocusedEvent(
            text=event.text,
            title=event.title,
            source=event.source,
            url=event.url,
            timestamp=event.timestamp,
            importance_score=score,
            routing_level=level,
            keywords=event.keywords or keywords,
            topics=event.topics or topics,
            sentiment=sentiment if event.sentiment == 0.5 else event.sentiment,
            stock_codes=event.stock_codes or stock_codes,
            manas_state=self._manas_state.copy() if self._manas_state else None,
            summary=self._generate_summary(event.title, event.text),
            narrative_tags=self._extract_narrative_tags(event.text, event.title, topics),
            matched_focus_topics=matched_focus_topics,
            metadata={
                "keyword_score": self._compute_keyword_match(event.text, event.title),
                "narrative_score": self._compute_narrative_relevance(matched_focus_topics),
                "source_weight": self._get_source_weight(event.source),
            },
        )

        self._publish_text_focused(focused_event)

    def _compute_importance(self, event: TextFetchedEvent, matched_focus_topics: Optional[List[str]] = None) -> float:
        """
        计算文本重要程度分数

        公式: score = w1*新鲜度 + w2*关键词匹配 + w3*叙事关联 + w4*来源权重

        Args:
            event: TextFetchedEvent 实例

        Returns:
            重要程度分数 0-1
        """
        freshness = self._compute_freshness(event.timestamp)
        keyword_score = self._compute_keyword_match(event.text, event.title)
        narrative_score = self._compute_narrative_relevance(matched_focus_topics or [])
        source_weight = self._get_source_weight(event.source)

        score = (
            freshness * 0.15 +
            keyword_score * 0.35 +
            narrative_score * 0.35 +
            source_weight * 0.15
        )

        return min(1.0, max(0.0, score))

    def _compute_freshness(self, timestamp: float) -> float:
        """计算新鲜度分数（半衰期 1 小时）"""
        age_hours = (time.time() - timestamp) / 3600
        if age_hours < 0:
            return 1.1
        freshness = 2 ** (-age_hours / 1.0)
        return min(1.0, freshness)

    def _compute_keyword_match(self, text: str, title: str) -> float:
        """计算关键词匹配度"""
        search_text = (title + " " + text).lower()
        matched_categories = set()

        for category, keywords in self._focus_keyword_map.items():
            for kw in keywords:
                if kw.lower() in search_text:
                    matched_categories.add(category)
                    break

        if not matched_categories:
            return 0.1

        base_score = min(0.8, len(matched_categories) * 0.2)
        return base_score + 0.2

    def _get_focus_topic_matches(self, text: str, title: str) -> List[str]:
        """匹配 ManasState 中的关注主题"""
        if not self._manas_state:
            return []

        focus_topics = self._manas_state.get("focus_topics", [])
        if not focus_topics:
            return []

        search_text = (title + " " + text).lower()
        matched = []
        for topic in focus_topics:
            topic_name = topic.get("topic", "") if isinstance(topic, dict) else str(topic)
            if topic_name and topic_name.lower() in search_text:
                matched.append(topic_name)
        return matched

    def _compute_narrative_relevance(self, matched_focus_topics: List[str]) -> float:
        """计算叙事关联度（基于匹配到的关注主题）"""
        if not self._manas_state:
            return 0.5
        if not matched_focus_topics:
            return 0.3
        return min(0.9, 0.5 + len(matched_focus_topics) * 0.2)

    def _get_source_weight(self, source: str) -> float:
        """获取来源权重"""
        source_weights = {
            "news_feed": 0.7,
            "user_article": 0.8,
            "social_media": 0.4,
            "imsg": 0.6,
            "wechat": 0.5,
            "system": 0.3,
            "radar_news": 0.7,
            "news": 0.7,
        }
        return source_weights.get(source, 0.5)

    def _extract_keywords_topics(self, text: str, title: str) -> Tuple[List[str], List[str]]:
        """提取关键词与主题候选"""
        search_text = (title + " " + text).lower()
        matched_keywords: List[str] = []
        matched_topics: List[str] = []

        for category, keywords in self._focus_keyword_map.items():
            for kw in keywords:
                if kw.lower() in search_text:
                    matched_keywords.append(kw)
                    if category not in matched_topics:
                        matched_topics.append(category)

        # 基于新闻主题关键词补充标签
        for kw, (_, label) in NEWS_TOPIC_KEYWORDS.items():
            if kw.lower() in search_text and label not in matched_topics:
                matched_topics.append(label)

        return list(set(matched_keywords)), matched_topics

    def _compute_sentiment(self, text: str, title: str) -> float:
        """简化情感判断"""
        search_text = (title + " " + text).lower()
        trend_words = SENTIMENT_KEYWORDS.get("行情涨跌", [])
        positive_words = [w for w in trend_words if "涨" in w or "牛" in w or "反弹" in w]
        negative_words = [w for w in trend_words if "跌" in w or "熊" in w or "回调" in w]

        pos_count = sum(1 for w in positive_words if w.lower() in search_text)
        neg_count = sum(1 for w in negative_words if w.lower() in search_text)
        if pos_count + neg_count == 0:
            return 0.5
        return pos_count / (pos_count + neg_count)

    def _extract_narrative_tags(self, text: str, title: str, topics: List[str]) -> List[str]:
        """提取叙事标签"""
        tags = list(topics)
        search_text = (title + " " + text).lower()
        for tag, keywords in MARKET_NARRATIVE_KEYWORDS.items():
            if any(kw.lower() in search_text for kw in keywords):
                tags.append(tag)

        return list(set(tags))

    def _extract_stock_codes(self, text: str) -> List[str]:
        """简单提取股票代码"""
        codes: Set[str] = set()
        bd = None
        try:
            from deva.naja.dictionary.blocks import get_block_dictionary
            bd = get_block_dictionary()
        except Exception:
            bd = None

        # A股 6位数字代码
        for match in re.findall(r"\b\d{6}\b", text):
            if bd:
                info = bd.get_stock_info(f"sh{match}") or bd.get_stock_info(f"sz{match}")
                codes.add(match if not info else f"sh{match}" if info.market == 'SH' else f"sz{match}" if info.market == 'SZ' else match)
            else:
                codes.add(match)
        # 美股 ticker (1-5 大写字母)
        for match in re.findall(r"\b[A-Z]{1,5}\b", text):
            if match not in {"AI", "GDP", "CPI", "PMI", "FOMC", "M2"}:
                if bd:
                    info = bd.get_stock_info(match.lower())
                    if info:
                        codes.add(match.lower())
                        continue
                codes.add(match)
        return list(codes)

    def _generate_summary(self, title: str, text: str) -> str:
        """生成一句话摘要"""
        if title:
            return title[:100]
        return text[:100] + "..." if len(text) > 100 else text

    def _publish_text_focused(self, event: TextFocusedEvent):
        """发布文本聚焦事件"""
        try:
            from deva.naja.events import get_event_bus
            event_bus = get_event_bus()
            event_bus.publish(event)
            log.debug(
                f"[TextImportanceScorer] 发布 TextFocusedEvent: "
                f"importance={event.importance_score:.2f}, level={event.routing_level}, "
                f"title={event.title[:30]}..."
            )
        except Exception as e:
            log.warning(f"[TextImportanceScorer] 发布 TextFocusedEvent 失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "focus_topics_count": len(self._manas_state.get("focus_topics", [])) if self._manas_state else 0,
        }
