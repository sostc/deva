"""
TextProcessingPipeline - 分层文本处理流水线

核心功能：
1. 分层处理：根据注意力分数决定处理深度
2. 语义理解：对高注意力内容进行深度处理
3. 广播分发：通过 TextSignalBus 分发给所有订阅者

处理层级：
- deep (>= 0.6): 完整语义理解 + 结构化信号
- index (0.3-0.6): 主题分类 + 关键词提取
- drop (< 0.3): 仅记录，不处理
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from deva.naja.cognition.attention_text_router import (
    AttentionTextItem,
    AttentionTextRouter,
    ManasState,
    StructuredSignal,
    TextSource,
    THRESHOLD_DEEP,
    THRESHOLD_INDEX,
    get_attention_router,
)
from deva.naja.cognition.text_signal_bus import (
    TextSignalBus,
    get_text_bus,
)

log = logging.getLogger(__name__)


# ============== 处理阶段 ==============

class ProcessingStage(Enum):
    """处理阶段"""
    RECEIVED = "received"           # 收到原始文本
    ROUTED = "routed"               # 完成路由分类
    PREFILTERED = "prefiltered"     # 完成预过滤
    INDEXED = "indexed"             # 完成索引
    DEEP_PROCESSED = "deep_processed"  # 完成深度处理
    BROADCASTED = "broadcasted"     # 完成广播


# ============== 处理器接口 ==============

class BaseProcessor:
    """
    基础处理器接口

    各模块可继承此类实现自定义处理逻辑
    """

    def process(self, item: AttentionTextItem) -> AttentionTextItem:
        """
        处理文本项

        Args:
            item: 输入的注意力文本项

        Returns:
            处理后的文本项
        """
        raise NotImplementedError

    @property
    def name(self) -> str:
        """处理器名称"""
        return self.__class__.__name__

    @property
    def min_attention(self) -> float:
        """此处理器要求的最低注意力分数"""
        return 0.5


# ============== 内置处理器 ==============

class KeywordExtractor(BaseProcessor):
    """
    关键词提取处理器

    从文本中提取关键词
    """

    def __init__(self):
        self._keyword_map: Dict[str, List[str]] = {}
        self._init_keywords()

    def _init_keywords(self):
        """初始化关键词映射"""
        try:
            from deva.naja.cognition.keyword_registry import DEFAULT_NARRATIVE_KEYWORDS
            self._keyword_map = DEFAULT_NARRATIVE_KEYWORDS
        except ImportError:
            self._keyword_map = self._get_default_keywords()

    def _get_default_keywords(self) -> Dict[str, List[str]]:
        return {
            "AI算力": ["英伟达", "AMD", "GPU", "算力", "AI", "大模型", "HBM"],
            "芯片": ["半导体", "芯片", "光刻", "封装", "晶圆"],
            "新能源": ["锂电", "光伏", "储能", "电动车", "新能源"],
            "美联储": ["加息", "降息", "通胀", "美债", "美元", "美联储"],
            "中美关系": ["关税", "制裁", "出口管制", "贸易战"],
            "流动性": ["流动性", "资金", "降准", "M2", "央行"],
            "地缘政治": ["战争", "中东", "俄乌", "朝鲜", "台海"],
        }

    @property
    def min_attention(self) -> float:
        return 0.0  # 所有文本都提取关键词

    def process(self, item: AttentionTextItem) -> AttentionTextItem:
        """提取关键词"""
        search_text = (item.title + " " + item.text).lower()

        # 按类别提取关键词
        matched_keywords = []
        matched_topics = []

        for category, keywords in self._keyword_map.items():
            for kw in keywords:
                if kw.lower() in search_text:
                    matched_keywords.append(kw)
                    if category not in matched_topics:
                        matched_topics.append(category)

        item.raw_keywords = list(set(matched_keywords))
        item.topic_candidates = matched_topics

        return item


class TopicClassifier(BaseProcessor):
    """
    主题分类处理器

    将文本分类到不同主题
    """

    def __init__(self):
        # 主题关键词映射
        self._topic_keywords = {
            "AI算力": ["英伟达", "AMD", "GPU", "算力", "AI", "大模型", "HBM", "台积电", "芯片"],
            "美联储": ["美联储", "加息", "降息", "通胀", "美债", "美元", "鲍威尔", "FOMC"],
            "中美关系": ["关税", "制裁", "出口管制", "贸易战", "中美", "美国"],
            "流动性": ["流动性", "降准", "M2", "央行", "货币宽松", "资金面"],
            "地缘政治": ["战争", "中东", "俄乌", "朝鲜", "台海", "以色列"],
            "新能源": ["锂电", "光伏", "储能", "电动车", "新能源", "宁德", "比亚迪"],
            "政策": ["政策", "证监会", "央行", "财政部", "监管"],
            "财报": ["财报", "业绩", "营收", "利润", "季报", "年报"],
        }

    @property
    def min_attention(self) -> float:
        return 0.2  # 索引级别以上都需要分类

    def process(self, item: AttentionTextItem) -> AttentionTextItem:
        """分类主题"""
        search_text = (item.title + " " + item.text).lower()

        # 计算每个主题的匹配度
        topic_scores = {}
        for topic, keywords in self._topic_keywords.items():
            score = sum(1 for kw in keywords if kw.lower() in search_text)
            if score > 0:
                topic_scores[topic] = score / len(keywords)

        # 取最高分的主题作为主主题
        if topic_scores:
            primary = max(topic_scores.items(), key=lambda x: x[1])
            if primary[1] > 0.1:  # 阈值
                item.topic_candidates = [primary[0]] + [
                    t for t, s in sorted(topic_scores.items(), key=lambda x: -x[1])[1:3]
                ]

        return item


class NewsMindProcessor(BaseProcessor):
    """
    NewsMind 语义理解处理器

    对高注意力文本进行深度语义理解
    """

    def __init__(self):
        self._llm_client = None  # 延迟初始化

    @property
    def min_attention(self) -> float:
        return THRESHOLD_DEEP  # 只处理高注意力内容

    def process(self, item: AttentionTextItem) -> AttentionTextItem:
        """深度语义理解"""
        if item.processed:
            return item

        # 1. 生成结构化信号
        item.structured_signal = self._analyze(item)

        # 2. 提取情感
        item.sentiment = item.structured_signal.sentiment

        # 3. 提取叙事标签
        item.narrative_tags = item.structured_signal.narrative_tags

        # 4. 提取股票代码
        item.stock_codes = item.structured_signal.mentioned_stocks

        item.processed = True
        item.processed_at = time.time()

        return item

    def _analyze(self, item: AttentionTextItem) -> StructuredSignal:
        """执行语义分析"""
        # 简化实现：基于关键词的情感判断
        signal = StructuredSignal(
            item_id=item.item_id,
            timestamp=item.timestamp,
            summary=self._generate_summary(item),
            sentiment=self._compute_sentiment(item),
            sentiment_reason=self._get_sentiment_reason(item),
            primary_topic=item.topic_candidates[0] if item.topic_candidates else "其他",
            secondary_topics=item.topic_candidates[1:3] if len(item.topic_candidates) > 1 else [],
            narrative_tags=self._extract_narrative_tags(item),
            original_text=item.text[:500],  # 保留前500字
        )

        return signal

    def _generate_summary(self, item: AttentionTextItem) -> str:
        """生成一句话总结"""
        if item.title:
            return item.title[:100]
        return item.text[:100] + "..." if len(item.text) > 100 else item.text

    def _compute_sentiment(self, item: AttentionTextItem) -> float:
        """计算情感倾向"""
        positive_words = ["涨", "利好", "增长", "突破", "创新", "超预期", "大涨", "反弹", "看好"]
        negative_words = ["跌", "利空", "下降", "风险", "亏损", "不及预期", "大跌", "回调", "警告"]

        text = (item.title + " " + item.text).lower()

        pos_count = sum(1 for w in positive_words if w.lower() in text)
        neg_count = sum(1 for w in negative_words if w.lower() in text)

        if pos_count + neg_count == 0:
            return 0.5

        return pos_count / (pos_count + neg_count)

    def _get_sentiment_reason(self, item: AttentionTextItem) -> str:
        """获取情感判断理由"""
        text = (item.title + " " + item.text).lower()

        if any(w in text for w in ["大涨", "暴涨", "创新高", "超预期"]):
            return "市场情绪积极"
        if any(w in text for w in ["大跌", "暴跌", "创新低", "不及预期"]):
            return "市场情绪消极"
        return "市场情绪中性"

    def _extract_narrative_tags(self, item: AttentionTextItem) -> List[str]:
        """提取叙事标签"""
        tags = list(item.topic_candidates)

        text = (item.title + " " + item.text).lower()

        # 叙事类型判断
        if any(w in text for w in ["政策", "央行", "降准", "降息"]):
            tags.append("政策叙事")
        if any(w in text for w in ["财报", "业绩", "营收", "利润"]):
            tags.append("业绩叙事")
        if any(w in text for w in ["流动性", "资金", "M2"]):
            tags.append("流动性叙事")
        if any(w in text for w in ["情绪", "恐慌", "贪婪", "避险"]):
            tags.append("情绪叙事")

        return list(set(tags))


class SupplyChainProcessor(BaseProcessor):
    """
    供应链联动处理器

    分析文本对供应链的影响
    """

    def __init__(self):
        self._linker = None  # 延迟初始化

    @property
    def min_attention(self) -> float:
        return 0.4  # 供应链相关可以稍微宽松

    def process(self, item: AttentionTextItem) -> AttentionTextItem:
        """分析供应链影响"""
        if not item.structured_signal:
            return item

        # 延迟加载 linker
        if self._linker is None:
            try:
                from deva.naja.cognition import get_supply_chain_linker
                self._linker = get_supply_chain_linker()
            except ImportError:
                log.warning("[SupplyChainProcessor] SupplyChainLinker 不可用")
                return item

        # 分析供应链影响
        impacts = []
        for stock in item.stock_codes:
            related_narratives = self._linker.get_narratives_by_stock(stock)
            if related_narratives:
                impacts.extend(related_narratives)

        item.supply_chain_impacts = list(set(impacts))

        return item


# ============== 分层处理流水线 ==============

class TextProcessingPipeline:
    """
    分层文本处理流水线

    核心设计：
    1. 根据注意力分数决定处理深度
    2. 各层处理器可插拔
    3. 通过 TextSignalBus 分发给订阅者

    处理流程：
    1. 接收原始文本
    2. 预过滤 + 计算注意力分数
    3. 路由到不同处理层级
    4. 执行处理
    5. 广播给订阅者
    """

    def __init__(self):
        self._router = get_attention_router()
        self._bus = get_text_bus()

        # 处理器
        self._preprocessors: List[BaseProcessor] = []   # 预处理器（所有文本）
        self._index_processors: List[BaseProcessor] = []  # 索引处理器
        self._deep_processors: List[BaseProcessor] = []   # 深度处理器

        # 索引存储
        self._index_store: deque = deque(maxlen=1000)

        # 统计
        self._stats = {
            "received": 0,
            "deep": 0,
            "index": 0,
            "drop": 0,
            "broadcasted": 0,
        }

        # 初始化内置处理器
        self._init_default_processors()

    def _init_default_processors(self):
        """初始化默认处理器"""
        # 预处理器
        self.add_preprocessor(KeywordExtractor())

        # 索引处理器
        self.add_index_processor(TopicClassifier())

        # 深度处理器
        self.add_deep_processor(NewsMindProcessor())
        self.add_deep_processor(SupplyChainProcessor())

    def add_preprocessor(self, processor: BaseProcessor):
        """添加预处理器（所有文本都会经过）"""
        self._preprocessors.append(processor)
        log.debug(f"[Pipeline] 添加预处理器: {processor.name}")

    def add_index_processor(self, processor: BaseProcessor):
        """添加索引处理器（index 级别以上）"""
        self._index_processors.append(processor)
        log.debug(f"[Pipeline] 添加索引处理器: {processor.name}")

    def add_deep_processor(self, processor: BaseProcessor):
        """添加深度处理器（deep 级别）"""
        self._deep_processors.append(processor)
        log.debug(f"[Pipeline] 添加深度处理器: {processor.name}")

    def set_manas_state(self, state: ManasState):
        """设置末那识状态"""
        self._router.set_manas_state(state)

    def process(self, item: AttentionTextItem) -> AttentionTextItem:
        """
        处理单个文本项

        Args:
            item: 注意力文本项

        Returns:
            处理后的文本项
        """
        self._stats["received"] += 1

        # 1. 预处理器（所有文本）
        for processor in self._preprocessors:
            item = processor.process(item)

        # 2. 计算注意力分数并路由
        if item.attention_score == 0.5:  # 初始值，说明没有预先计算
            item.attention_score = self._router.compute_attention_score(
                text=item.text,
                title=item.title,
                source=item.source,
                timestamp=item.timestamp,
            )

        # 3. 根据层级处理
        level = item.routing_level()
        self._stats[level] += 1

        if level == "drop":
            log.debug(f"[Pipeline] 丢弃低注意力文本: {item.item_id}")
            return item

        if level == "index":
            # 索引处理器
            for processor in self._index_processors:
                item = processor.process(item)
            self._index_store.append(item)

        elif level == "deep":
            # 深度处理器
            for processor in self._deep_processors:
                if item.attention_score >= processor.min_attention:
                    item = processor.process(item)

            self._index_store.append(item)

        # 4. 广播给订阅者
        self._bus.publish(item)
        self._stats["broadcasted"] += 1

        return item

    def process_batch(self, items: List[AttentionTextItem]) -> Dict[str, Any]:
        """
        批量处理

        Args:
            items: 文本项列表

        Returns:
            处理统计
        """
        results = {"deep": [], "index": [], "drop": []}

        for item in items:
            item = self.process(item)
            results[item.routing_level()].append(item)

        return {
            "total": len(items),
            "deep": len(results["deep"]),
            "index": len(results["index"]),
            "drop": len(results["drop"]),
            "broadcasted": self._bus.get_stats()["total_delivered"],
        }

    def get_recent_index(self, limit: int = 50) -> List[AttentionTextItem]:
        """获取最近的索引内容"""
        return list(self._index_store)[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取处理统计"""
        return {
            **self._stats,
            "router_stats": self._router.get_stats(),
            "bus_stats": self._bus.get_stats(),
            "total_processed": self._stats["received"],
        }


# ============== 便捷函数 ==============

_pipeline: Optional[TextProcessingPipeline] = None


def get_text_pipeline() -> TextProcessingPipeline:
    """获取文本处理流水线单例"""
    global _pipeline
    if _pipeline is None:
        _pipeline = TextProcessingPipeline()
    return _pipeline


def process_text(
    text: str,
    title: str = "",
    source: TextSource = TextSource.NEWS_FEED,
    url: str = "",
) -> AttentionTextItem:
    """
    便捷函数：处理单条文本

    Args:
        text: 文本内容
        title: 标题
        source: 来源
        url: 原文链接

    Returns:
        处理后的注意力文本项
    """
    pipeline = get_text_pipeline()

    item = AttentionTextItem(
        text=text,
        title=title,
        source=source,
        url=url,
    )

    return pipeline.process(item)


def subscribe_to_signals(
    module_name: str,
    callback: Callable[[AttentionTextItem], None],
    min_attention: float = 0.5,
    topics: Optional[List[str]] = None,
):
    """
    便捷函数：订阅文本信号

    Args:
        module_name: 模块名称
        callback: 回调函数
        min_attention: 最小注意力阈值
        topics: 感兴趣的主题
    """
    bus = get_text_bus()
    bus.subscribe(module_name, callback, min_attention, topics)
