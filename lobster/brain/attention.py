"""
注意力评分系统 - 思想雷达核心

评分维度:
- 新颖度: 与历史事件的相似度
- 情绪强度: 文本情绪分析
- 市场波动: 价格/成交量变化
- 关键词权重: 重要关键词匹配
- 传播速度: 信息扩散速度
"""

import numpy as np
from typing import List, Dict, Set
from datetime import datetime, timedelta
from collections import deque
import re

from ..core.event import Event, EventType


class AttentionScorer:
    """注意力评分器"""
    
    # 重要关键词库
    KEYWORDS = {
        "high": ["突破", "暴涨", "暴跌", "涨停", "跌停", "重大", "紧急", "突发",
                "AI", "人工智能", "算力", "芯片", "GPU", "英伟达", "OpenAI",
                "政策", "监管", "改革", "创新", "革命"],
        "medium": ["上涨", "下跌", "增长", "下降", "利好", "利空",
                   "技术", "产品", "发布", "合作", "收购", "并购"],
    }
    
    def __init__(self, history_size: int = 1000):
        """
        初始化评分器
        
        Args:
            history_size: 历史事件缓存大小（用于计算新颖度）
        """
        self.history = deque(maxlen=history_size)
        self.recent_events = deque(maxlen=100)  # 最近事件（用于计算传播速度）
        
    def score(self, event: Event) -> float:
        """
        计算事件的注意力评分
        
        Returns:
            0-1之间的评分，越高越值得关注
        """
        scores = {
            "novelty": self._novelty_score(event),
            "sentiment": self._sentiment_score(event),
            "market": self._market_score(event),
            "keywords": self._keyword_score(event),
            "velocity": self._velocity_score(event),
        }
        
        # 加权平均
        weights = {
            "novelty": 0.25,
            "sentiment": 0.15,
            "market": 0.25,
            "keywords": 0.20,
            "velocity": 0.15,
        }
        
        total_score = sum(scores[k] * weights[k] for k in scores)
        
        # 记录到历史
        self.history.append(event)
        self.recent_events.append({
            "time": event.time,
            "type": event.type,
            "source": event.source,
        })
        
        return min(1.0, max(0.0, total_score))
    
    def _novelty_score(self, event: Event) -> float:
        """
        新颖度评分
        
        与历史事件越不相似，评分越高
        """
        if not self.history or event.vector is None:
            return 0.5  # 默认中等新颖度
        
        # 计算与历史事件的平均相似度
        similarities = []
        for hist_event in self.history:
            if hist_event.vector is not None:
                sim = self._cosine_similarity(event.vector, hist_event.vector)
                similarities.append(sim)
        
        if not similarities:
            return 0.5
        
        avg_similarity = np.mean(similarities)
        # 相似度越低，新颖度越高
        novelty = 1.0 - avg_similarity
        
        return novelty
    
    def _sentiment_score(self, event: Event) -> float:
        """
        情绪强度评分
        
        基于文本情绪分析
        """
        text = event.text.lower()
        
        # 强烈情绪词
        strong_positive = ["暴涨", "涨停", "突破", "重大利好", "革命性", "颠覆"]
        strong_negative = ["暴跌", "跌停", "崩盘", "危机", "风险", "警告"]
        
        score = 0.0
        
        for word in strong_positive:
            if word in text:
                score += 0.3
        
        for word in strong_negative:
            if word in text:
                score += 0.3
        
        # 感叹号和问号增加情绪强度
        score += min(0.2, text.count("!") * 0.05)
        score += min(0.1, text.count("?") * 0.03)
        
        return min(1.0, score)
    
    def _market_score(self, event: Event) -> float:
        """
        市场波动评分
        
        基于tick数据的价格/成交量变化
        """
        if event.type != EventType.TICK:
            return 0.0
        
        meta = event.meta
        score = 0.0
        
        # 价格变化
        change_pct = meta.get("change_pct", 0)
        if abs(change_pct) > 10:
            score += 0.5
        elif abs(change_pct) > 5:
            score += 0.3
        elif abs(change_pct) > 2:
            score += 0.1
        
        # 成交量异常
        volume_ratio = meta.get("volume_ratio", 1.0)
        if volume_ratio > 5:
            score += 0.3
        elif volume_ratio > 2:
            score += 0.15
        
        return min(1.0, score)
    
    def _keyword_score(self, event: Event) -> float:
        """
        关键词权重评分
        """
        text = event.text.lower()
        score = 0.0
        
        # 高权重关键词
        for keyword in self.KEYWORDS["high"]:
            if keyword.lower() in text:
                score += 0.25
        
        # 中权重关键词
        for keyword in self.KEYWORDS["medium"]:
            if keyword.lower() in text:
                score += 0.1
        
        return min(1.0, score)
    
    def _velocity_score(self, event: Event) -> float:
        """
        传播速度评分
        
        基于最近相似事件的数量
        """
        if not self.recent_events:
            return 0.0
        
        # 检查最近1小时内同类事件数量
        one_hour_ago = event.time - timedelta(hours=1)
        recent_count = sum(
            1 for e in self.recent_events
            if e["time"] > one_hour_ago and e["type"] == event.type
        )
        
        # 事件越多，传播越快
        if recent_count > 20:
            return 1.0
        elif recent_count > 10:
            return 0.7
        elif recent_count > 5:
            return 0.4
        else:
            return 0.1
    
    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """计算余弦相似度"""
        v1, v2 = np.array(v1), np.array(v2)
        norm = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norm == 0:
            return 0.0
        return float(np.dot(v1, v2) / norm)
    
    def get_stats(self) -> Dict:
        """获取评分器统计信息"""
        return {
            "history_size": len(self.history),
            "recent_events": len(self.recent_events),
            "high_attention_count": sum(
                1 for e in self.history if hasattr(e, 'attention_score') and e.attention_score >= 0.7
            ),
        }
