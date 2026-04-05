"""
AttentionTextRouter - 注意力文本路由器

核心功能：
1. 根据末那识状态计算文本注意力分数
2. 快速预过滤，低价值文本直接丢弃
3. 将文本路由到不同处理管道

核心原则：只对注意力权重高的内容做深度处理

时间尺度：
- 实时新闻：新鲜度衰减快，需要快速评估
- 文章/报告：半衰期较长，可稍慢处理
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

log = logging.getLogger(__name__)


# ============== 常量定义 ==============

class TextSource(Enum):
    """文本来源"""
    NEWS_FEED = "news_feed"           # 东方财富等新闻源
    USER_ARTICLE = "user_article"     # 用户分享的文章链接
    SOCIAL_MEDIA = "social_media"     # 社交媒体
    IMSG = "imsg"                     # iMessage
    WECHAT = "wechat"                 # 微信
    SYSTEM = "system"                 # 系统通知
    RADAR_NEWS = "radar_news"        # 雷达新闻


# 来源权威权重
SOURCE_WEIGHTS: Dict[TextSource, float] = {
    TextSource.NEWS_FEED: 0.7,       # 财经新闻
    TextSource.USER_ARTICLE: 0.8,    # 用户文章通常更深度
    TextSource.SOCIAL_MEDIA: 0.4,    # 社交媒体噪音多
    TextSource.IMSG: 0.6,            # iMessage
    TextSource.WECHAT: 0.5,          # 微信
    TextSource.SYSTEM: 0.3,          # 系统通知
}


# 注意力分数阈值
THRESHOLD_DEEP = 0.6    # 深度处理
THRESHOLD_INDEX = 0.3   # 索引存储
THRESHOLD_DROP = 0.2    # 直接丢弃


@dataclass
class ManasState:
    """
    末那识状态快照

    用于计算注意力分数时的上下文参考
    """
    # 当前焦点主题及权重
    focus_topics: List[Dict[str, Any]] = field(default_factory=list)
    # 示例: [{"topic": "AI算力", "weight": 0.9}, {"topic": "芯片", "weight": 0.7}]

    # 当前情绪状态
    fear_greed: float = 0.5  # 0=恐惧, 1=贪婪
    harmony: float = 0.5     # 和谐度 0-1

    # 组合眼状态
    portfolio_risk: float = 0.5    # 组合风险敞口
    market_timing: float = 0.5    # 时机成熟度
    market_env: str = "neutral"    # 市场环境

    # 时间戳
    timestamp: float = field(default_factory=0)

    def get_focus_keywords(self) -> Set[str]:
        """从焦点主题提取关键词"""
        keywords = set()
        for item in self.focus_topics:
            topic = item.get("topic", "")
            # 简单分词（实际应该用更好的分词器）
            keywords.update(topic.split())
            # 添加相关词
            keywords.update(self._topic_related.get(topic, set()))
        return keywords

    # 主题相关词映射（可扩展）
    _topic_related: Dict[str, Set[str]] = field(default_factory=lambda: {
        "AI算力": {"英伟达", "AMD", "GPU", "算力", "芯片", "HBM", "台积电"},
        "芯片": {"半导体", "光刻", "封装", "晶圆", "制造"},
        "新能源": {"锂电", "光伏", "储能", "电动车", "宁德", "比亚迪"},
        "美联储": {"加息", "降息", "通胀", "美债", "美元"},
        "中美关系": {"关税", "制裁", "出口管制", "贸易战"},
    })


@dataclass
class AttentionTextItem:
    """
    注意力文本项

    贯穿整个处理流程的统一数据结构
    """
    # 唯一标识
    item_id: str = ""

    # 原始内容
    text: str = ""
    title: str = ""
    url: str = ""

    # 来源信息
    source: TextSource = TextSource.NEWS_FEED
    source_name: str = ""           # 具体来源名称（如"东方财富"）
    timestamp: float = field(default_factory=time.time)

    # 注意力评分（核心）
    attention_score: float = 0.5    # 0-1

    # 快速提取（预过滤器阶段）
    raw_keywords: List[str] = field(default_factory=list)
    topic_candidates: List[str] = field(default_factory=list)
    matched_focus_topics: List[str] = field(default_factory=list)  # 匹配到哪些焦点

    # 深度提取（深度处理阶段后填充）
    structured_signal: Optional[StructuredSignal] = None
    sentiment: float = 0.5          # 情感倾向 0-1
    narrative_tags: List[str] = field(default_factory=list)
    stock_codes: List[str] = field(default_factory=list)           # 提及的股票
    supply_chain_impacts: List[str] = field(default_factory=list)

    # 处理状态
    processed: bool = False
    processed_at: float = 0

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.item_id and self.url:
            self.item_id = hashlib.md5(self.url.encode()).hexdigest()[:12]
        elif not self.item_id:
            self.item_id = hashlib.md5(self.text.encode()).hexdigest()[:12]

    def routing_level(self) -> str:
        """根据注意力分数确定处理级别"""
        if self.attention_score >= THRESHOLD_DEEP:
            return "deep"
        elif self.attention_score >= THRESHOLD_INDEX:
            return "index"
        else:
            return "drop"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "source": self.source.value,
            "attention_score": round(self.attention_score, 3),
            "routing_level": self.routing_level(),
            "matched_focus": self.matched_focus_topics,
            "processed": self.processed,
        }


@dataclass
class StructuredSignal:
    """
    结构化信号

    深度处理后的统一信号格式
    """
    # 基础信息
    item_id: str = ""
    timestamp: float = 0

    # 语义理解
    summary: str = ""               # 一句话总结
    key_points: List[str] = field(default_factory=list)
    sentiment: float = 0.5         # 情感 0-1
    sentiment_reason: str = ""

    # 主题分类
    primary_topic: str = ""
    secondary_topics: List[str] = field(default_factory=list)

    # 实体
    mentioned_stocks: List[str] = field(default_factory=list)
    mentioned_sectors: List[str] = field(default_factory=list)
    mentioned_companies: List[str] = field(default_factory=list)

    # 供需分析
    demand_signals: List[str] = field(default_factory=list)
    supply_signals: List[str] = field(default_factory=list)
    supply_demand_imbalance: str = ""  # 供不应求/供过于求/平衡

    # 叙事标签
    narrative_tags: List[str] = field(default_factory=list)
    narrative_alignment: str = ""      # 支持/反对/中性

    # 投资信号
    investment_opportunities: List[str] = field(default_factory=list)
    investment_risks: List[str] = field(default_factory=list)
    confidence: float = 0.5

    # 原始文本保留
    original_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "sentiment": round(self.sentiment, 2),
            "primary_topic": self.primary_topic,
            "narrative_tags": self.narrative_tags,
            "mentioned_stocks": self.mentioned_stocks,
            "supply_demand": self.supply_demand_imbalance,
            "confidence": round(self.confidence, 2),
        }


# ============== 注意力文本路由器 ==============

class AttentionTextRouter:
    """
    注意力文本路由器

    核心功能：
    1. 计算文本注意力分数（结合末那识状态）
    2. 快速预过滤
    3. 路由到不同处理管道

    使用方式：
        router = AttentionTextRouter()
        router.set_manas_state(current_state)

        for item in incoming_texts:
            score = router.compute_attention_score(item)
            if score >= THRESHOLD_DEEP:
                deep_queue.put(item)
            elif score >= THRESHOLD_INDEX:
                index_queue.put(item)
    """

    def __init__(self):
        self._manas_state: Optional[ManasState] = None

        # 关键词注册表（用于快速匹配）
        self._focus_keyword_map: Dict[str, List[str]] = defaultdict(list)

        # 统计
        self._stats = {
            "total_processed": 0,
            "deep": 0,
            "index": 0,
            "drop": 0,
        }

        self._init_keyword_map()

    def _init_keyword_map(self):
        """初始化关键词映射"""
        # 从 keyword_registry 导入（如果可用）
        try:
            from deva.naja.cognition.keyword_registry import DEFAULT_NARRATIVE_KEYWORDS
            for category, keywords in DEFAULT_NARRATIVE_KEYWORDS.items():
                for kw in keywords[:20]:  # 只取前20个核心词
                    self._focus_keyword_map[category].append(kw)
        except ImportError:
            # 使用内置默认关键词
            self._focus_keyword_map = self._get_default_keywords()

    def _get_default_keywords(self) -> Dict[str, List[str]]:
        """内置默认关键词"""
        return {
            "AI算力": ["英伟达", "AMD", "GPU", "算力", "AI", "大模型", "HBM", "台积电"],
            "芯片": ["半导体", "芯片", "光刻", "封装", "晶圆", "制造", "台积电", "中芯"],
            "新能源": ["锂电", "光伏", "储能", "电动车", "新能源", "宁德", "比亚迪", "特斯拉"],
            "美联储": ["加息", "降息", "通胀", "美债", "美元", "美联储", "鲍威尔"],
            "中美关系": ["关税", "制裁", "出口管制", "贸易战", "中美", "美国"],
            "流动性": ["流动性", "资金", "降准", "M2", "央行", "货币"],
            "地缘政治": ["战争", "中东", "俄乌", "朝鲜", "台海"],
        }

    def set_manas_state(self, state: ManasState):
        """设置末那识状态（用于注意力计算）"""
        self._manas_state = state
        log.debug(f"[AttentionRouter] 更新末那识状态: {len(state.focus_topics)} 个焦点")

    def compute_attention_score(
        self,
        text: str,
        title: str = "",
        source: TextSource = TextSource.NEWS_FEED,
        timestamp: Optional[float] = None,
    ) -> float:
        """
        计算文本注意力分数

        公式: score = w1*新鲜度 + w2*关键词匹配 + w3*来源权重 + w4*叙事关联

        Args:
            text: 文本内容
            title: 标题（权重更高）
            source: 来源
            timestamp: 时间戳

        Returns:
            注意力分数 0-1
        """
        timestamp = timestamp or time.time()

        # 1. 新鲜度衰减（半衰期 1 小时）
        freshness = self._compute_freshness(timestamp)

        # 2. 关键词匹配度
        keyword_score = self._compute_keyword_match(text, title)

        # 3. 来源权重
        source_weight = SOURCE_WEIGHTS.get(source, 0.5)

        # 4. 叙事关联度（与末那识焦点相关）
        narrative_score = self._compute_narrative_relevance(text, title)

        # 加权计算
        score = (
            freshness * 0.15 +
            keyword_score * 0.35 +
            source_weight * 0.15 +
            narrative_score * 0.35
        )

        return min(1.0, max(0.0, score))

    def _compute_freshness(self, timestamp: float) -> float:
        """
        计算新鲜度分数

        半衰期: 1小时（新闻），4小时（文章）
        """
        age_hours = (time.time() - timestamp) / 3600

        if age_hours < 0:
            return 1.1  # 未来内容给加分

        # 指数衰减，半衰期 1 小时
        freshness = 2 ** (-age_hours / 1.0)
        return min(1.0, freshness)

    def _compute_keyword_match(
        self,
        text: str,
        title: str = ""
    ) -> float:
        """
        计算关键词匹配度

        检查文本是否包含当前热门的关键词
        """
        search_text = (title + " " + text).lower()
        matched_categories = set()

        for category, keywords in self._focus_keyword_map.items():
            for kw in keywords:
                if kw.lower() in search_text:
                    matched_categories.add(category)
                    break

        # 有多少比例的焦点类别被匹配
        if not self._focus_keyword_map:
            return 0.5

        return len(matched_categories) / max(3, len(self._focus_keyword_map))

    def _compute_narrative_relevance(
        self,
        text: str,
        title: str = ""
    ) -> float:
        """
        计算叙事关联度

        基于末那识状态判断文本与当前焦点的关联程度
        """
        if not self._manas_state:
            return 0.5  # 无状态时给中间值

        search_text = (title + " " + text).lower()
        focus_keywords = self._manas_state.get_focus_keywords()

        matched = 0
        total = len(focus_keywords) if focus_keywords else 1

        for kw in focus_keywords:
            if kw.lower() in search_text:
                matched += 1

        # 考虑权重
        weighted_score = 0.0
        for item in self._manas_state.focus_topics:
            topic = item.get("topic", "").lower()
            weight = item.get("weight", 0.5)
            if topic.lower() in search_text or any(kw.lower() in search_text for kw in self._manas_state._topic_related.get(topic, [])):
                weighted_score += weight

        if self._manas_state.focus_topics:
            normalized = weighted_score / sum(item.get("weight", 0.5) for item in self._manas_state.focus_topics)
            return (normalized + matched / total) / 2

        return matched / total if total > 0 else 0.5

    def route(self, items: List[AttentionTextItem]) -> Dict[str, List[AttentionTextItem]]:
        """
        批量路由文本到不同处理管道

        Returns:
            {
                "deep": [...],   # 深度处理
                "index": [...],  # 仅索引
                "drop": [...]     # 丢弃
            }
        """
        buckets = {"deep": [], "index": [], "drop": []}

        for item in items:
            item.attention_score = self.compute_attention_score(
                text=item.text,
                title=item.title,
                source=item.source,
                timestamp=item.timestamp,
            )

            level = item.routing_level()
            buckets[level].append(item)

            self._stats["total_processed"] += 1
            self._stats[level] += 1

        log.info(
            f"[AttentionRouter] 路由完成: "
            f"深度={len(buckets['deep'])}, "
            f"索引={len(buckets['index'])}, "
            f"丢弃={len(buckets['drop'])}"
        )

        return buckets

    def quick_score(self, text: str, title: str = "") -> float:
        """
        快速评分（仅关键词匹配，不查末那识状态）

        用于初步筛选
        """
        return self._compute_keyword_match(text, title) * 0.7 + 0.15

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "pass_rate": round(
                (self._stats["deep"] + self._stats["index"]) /
                max(1, self._stats["total_processed"]) * 100, 1
            )
        }

    def reset_stats(self):
        """重置统计"""
        self._stats = {
            "total_processed": 0,
            "deep": 0,
            "index": 0,
            "drop": 0,
        }


# ============== 单例访问 ==============

_router: Optional[AttentionTextRouter] = None


def get_attention_router() -> AttentionTextRouter:
    """获取注意力路由器单例"""
    global _router
    if _router is None:
        _router = AttentionTextRouter()
    return _router
