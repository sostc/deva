"""
AttentionScorer - 注意力评分器

从 core.py 提取，负责对 NewsEvent 进行多维度注意力评分：
- 新颖度（novelty）
- 情绪强度（sentiment）
- 市场波动（market）
- 关键词匹配（keywords）
- 传播速度（velocity）
- 数据源重要性（importance）
"""

import numpy as np
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, List

from .news_event import NewsEvent


class AttentionScorer:
    """注意力评分器"""

    KEYWORDS = {
        "high": ["突破", "暴涨", "暴跌", "涨停", "跌停", "重大", "紧急", "突发",
                "AI", "人工智能", "算力", "芯片", "GPU", "英伟达", "OpenAI",
                "政策", "监管", "改革", "创新", "革命"],
        "medium": ["上涨", "下跌", "增长", "下降", "利好", "利空",
                   "技术", "产品", "发布", "合作", "收购", "并购"],
    }

    def __init__(self, history_size: int = 1000):
        self.history = deque(maxlen=history_size)
        self.recent_events = deque(maxlen=100)

    def score(self, event: NewsEvent) -> float:
        """计算注意力评分"""
        scores = {
            "novelty": self._novelty_score(event),
            "sentiment": self._sentiment_score(event),
            "market": self._market_score(event),
            "keywords": self._keyword_score(event),
            "velocity": self._velocity_score(event),
            "importance": self._importance_score(event),  # 新增：数据源标记的重要性
        }

        weights = {
            "novelty": 0.20,
            "sentiment": 0.12,
            "market": 0.20,
            "keywords": 0.15,
            "velocity": 0.13,
            "importance": 0.20,  # 数据源标记的重要性权重
        }

        total = sum(scores[k] * weights[k] for k in scores)

        self.history.append(event)
        self.recent_events.append({
            "time": event.timestamp,
            "type": event.event_type,
        })

        return min(1.0, max(0.0, total))

    def peek_score(self, event: NewsEvent) -> float:
        """计算注意力评分（不写入历史，用于预筛选）"""
        scores = {
            "novelty": self._novelty_score(event),
            "sentiment": self._sentiment_score(event),
            "market": self._market_score(event),
            "keywords": self._keyword_score(event),
            "velocity": self._velocity_score(event),
            "importance": self._importance_score(event),
        }
        weights = {
            "novelty": 0.20,
            "sentiment": 0.12,
            "market": 0.20,
            "keywords": 0.15,
            "velocity": 0.13,
            "importance": 0.20,
        }
        total = sum(scores[k] * weights[k] for k in scores)
        return min(1.0, max(0.0, total))

    def _importance_score(self, event: NewsEvent) -> float:
        """数据源标记的重要性评分

        如果数据源标记了 importance="high"，则直接给高分
        """
        # 从 meta 中获取 importance
        importance = event.meta.get('importance', '')

        if isinstance(importance, str):
            importance = importance.lower()
            if importance == 'high':
                return 1.0
            elif importance == 'medium':
                return 0.6
            elif importance == 'normal':
                return 0.3

        # 也检查 meta 中的其他可能字段
        if event.meta.get('important'):
            return 0.9

        return 0.0

    def _novelty_score(self, event: NewsEvent) -> float:
        """新颖度评分"""
        if not self.history or event.vector is None:
            return 0.5

        similarities = []
        for hist in self.history:
            if hist.vector is not None:
                sim = self._cosine_similarity(event.vector, hist.vector)
                similarities.append(sim)

        if not similarities:
            return 0.5

        return 1.0 - np.mean(similarities)

    def _sentiment_score(self, event: NewsEvent) -> float:
        """情绪强度评分"""
        text = event.content.lower()
        score = 0.0

        strong_words = ["暴涨", "涨停", "突破", "重大利好", "暴跌", "跌停", "崩盘", "危机"]
        for word in strong_words:
            if word in text:
                score += 0.3

        score += min(0.2, text.count("!") * 0.05)
        return min(1.0, score)

    def _market_score(self, event: NewsEvent) -> float:
        """市场波动评分"""
        if event.event_type != "tick":
            return 0.0

        meta = event.meta
        score = 0.0

        change_pct = meta.get("change_pct", 0)
        if abs(change_pct) > 10:
            score += 0.5
        elif abs(change_pct) > 5:
            score += 0.3
        elif abs(change_pct) > 2:
            score += 0.1

        return min(1.0, score)

    def _keyword_score(self, event: NewsEvent) -> float:
        """关键词评分"""
        text = event.content.lower()
        score = 0.0

        for keyword in self.KEYWORDS["high"]:
            if keyword.lower() in text:
                score += 0.25

        for keyword in self.KEYWORDS["medium"]:
            if keyword.lower() in text:
                score += 0.1

        return min(1.0, score)

    def _velocity_score(self, event: NewsEvent) -> float:
        """传播速度评分"""
        if not self.recent_events:
            return 0.0

        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_count = sum(
            1 for e in self.recent_events
            if e["time"] > one_hour_ago and e["type"] == event.event_type
        )

        if recent_count > 20:
            return 1.0
        elif recent_count > 10:
            return 0.7
        elif recent_count > 5:
            return 0.4
        return 0.1

    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """余弦相似度"""
        v1, v2 = np.array(v1), np.array(v2)
        norm = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norm == 0:
            return 0.0
        return float(np.dot(v1, v2) / norm)
