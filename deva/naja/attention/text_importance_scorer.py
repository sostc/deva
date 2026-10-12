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
from deva.naja.cognition.semantic.keyword_registry import (
    DEFAULT_NARRATIVE_KEYWORDS,
    MARKET_NARRATIVE_KEYWORDS,
    NEWS_TOPIC_KEYWORDS,
    SENTIMENT_KEYWORDS,
)

log = logging.getLogger(__name__)

# 预编译正则表达式
_ASTOCK_CODE_RE = re.compile(r"\b\d{6}\b")
_US_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
_US_TICKER_EXCLUDE = {"AI", "GDP", "CPI", "PMI", "FOMC", "M2"}


THRESHOLD_DEEP = 0.6
THRESHOLD_INDEX = 0.3
THRESHOLD_DROP = 0.2


class TextImportanceScorer:
    """
    文本重要程度评分器

    根据 ManasState 计算文本的重要程度分数
    高于阈值的内容发布 TextFocusedEvent

    使用方式（容器接线，注意是**注入 provider** 而不是手动 push 状态）::

        from deva.naja.news import build_manas_focus_state

        scorer = TextImportanceScorer(attention_os)
        scorer.set_focus_provider(build_manas_focus_state)

    手动测试时也可以直接给一份快照::

        scorer.set_manas_state({"focus_topics": [{"topic": "芯片"}]})
    """

    def __init__(self, attention_os: Optional[Any] = None):
        """
        初始化文本评分器

        Args:
            attention_os: AttentionOS 实例，用于获取 ManasState
        """
        self._attention_os = attention_os
        self._manas_state: Optional[Dict[str, Any]] = None
        # 「注意力状态提供者」——容器接线注入。None 表示不感知关注主题
        # （见 _resolve_manas_state 的说明：这条线历史上一直是断的）。
        self._focus_provider: Optional[Any] = None
        self._focus_keyword_map: Dict[str, List[str]] = defaultdict(list)
        self._init_focus_keywords()

        self._stats = {
            "total_received": 0,
            "deep_count": 0,
            "index_count": 0,
            "drop_count": 0,
        }
        # 去重缓存：防止同一 url 的内容被重复发布 TextFocusedEvent
        self._published_urls: set = set()
        self._max_published_urls: int = 500

    def _init_focus_keywords(self):
        """初始化焦点关键词映射"""
        if DEFAULT_NARRATIVE_KEYWORDS:
            self._focus_keyword_map = DEFAULT_NARRATIVE_KEYWORDS
        else:
            self._focus_keyword_map = {}

    def set_focus_provider(self, provider: Optional[Any]) -> None:
        """注入「注意力状态提供者」（容器接线用）。

        provider 是**无参可调用对象**，返回形如
        ``{"focus_topics": [{"topic": "AI", "keywords": [...]}, ...]}`` 的 dict，
        或返回 ``None`` 表示拿不到。

        为什么是"拉"而不是"推"：每次评分前惰性拉取，状态永远是最新的；
        外部 push 需要保证每个更新点都记得推一次，漏一处就静默过期。
        """
        self._focus_provider = provider

    def _resolve_manas_state(self) -> Optional[Dict[str, Any]]:
        """拉取最新注意力状态；provider 缺失/失败时沿用上次的快照。

        ⚠️ 这里修的是一个**静默失效**：``set_manas_state`` 全仓**从未被调用**，
        于是 ``_manas_state`` 恒为 None →
          * ``_get_focus_topic_matches()`` 恒返回 ``[]``
          * ``_compute_narrative_relevance([])`` 恒返回常数 0.3（叙事那 35% 权重是死的）
          * ``TextFocusedEvent.matched_focus_topics`` 恒为空 →
            下游叙事追踪 / 跨信号 / 供应链联动整条链路空转
        因为「方法缺失」与「正好等于默认值」不可区分，表现为"跑得好好的"。
        """
        provider = self._focus_provider
        if provider is None:
            return self._manas_state
        try:
            state = provider()
        except Exception as e:
            log.warning(
                f"[TextImportanceScorer] 焦点状态拉取失败，沿用上次快照: {e}"
            )
            return self._manas_state
        if isinstance(state, dict):
            self._manas_state = state
        return self._manas_state

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

        # 去重：同一 url 的内容只处理一次
        if event.url and event.url in self._published_urls:
            return
        if event.url:
            self._published_urls.add(event.url)
            if len(self._published_urls) > self._max_published_urls:
                # 淘汰最旧的 50 条
                for _ in range(50):
                    self._published_urls.pop()

        # 评分前刷新注意力状态（惰性拉取，见 _resolve_manas_state）。
        # 放在去重之后：重复内容不必多拉一次。
        self._resolve_manas_state()

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
        """匹配 ManasState 中的关注主题。

        主题既可以用**名称**命中，也可以用**关键词**命中——provider
        （``news.build_manas_focus_state``）两者都会带过来，
        关键词命中能显著提高召回（如正文出现"晶圆"应归入"芯片"主题）。
        """
        if not self._manas_state:
            return []

        focus_topics = self._manas_state.get("focus_topics", [])
        if not focus_topics:
            return []

        search_text = (title + " " + text).lower()
        matched = []
        for topic in focus_topics:
            if isinstance(topic, dict):
                topic_name = str(topic.get("topic") or topic.get("name") or "")
                keywords = topic.get("keywords") or ()
            else:
                topic_name, keywords = str(topic), ()
            if not topic_name:
                continue
            hit = topic_name.lower() in search_text or any(
                str(k).lower() in search_text for k in keywords if k
            )
            if hit and topic_name not in matched:
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

        # A股 6位数字代码 (使用预编译正则)
        for match in _ASTOCK_CODE_RE.findall(text):
            if bd:
                info = bd.get_stock_info(f"sh{match}") or bd.get_stock_info(f"sz{match}")
                codes.add(match if not info else f"sh{match}" if info.market == 'SH' else f"sz{match}" if info.market == 'SZ' else match)
            else:
                codes.add(match)
        # 美股 ticker (1-5 大写字母, 使用预编译正则)
        for match in _US_TICKER_RE.findall(text):
            if match not in _US_TICKER_EXCLUDE:
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
            
            if event.routing_level == 'deep':
                try:
                    from deva.naja.events.focused_news_store import add_focused_news
                    add_focused_news(event)
                except Exception as store_err:
                    log.warning(f"[TextImportanceScorer] 保存到持久化存储失败: {store_err}")
            
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
