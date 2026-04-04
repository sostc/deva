"""
TextSignalBus - 文本信号总线

📰 定位：原始信息的入口
    - 「原材料」：来自新闻、研报、社交媒体的文本
    - 将原始文本转化为带注意力分数的信号

📋 核心功能：
    1. 统一的文本信号发布/订阅机制
    2. 按注意力阈值自动分发（高分信号才能被订阅者收到）
    3. 支持多消费者订阅

🔄 数据流：
    📰 原始文本 → TextProcessingPipeline（处理） → TextSignalBus（分发）
                                                     ↓
    SectorNarrative（订阅，min_attention=0.7）  ← 「地」感知
    TimingNarrative（订阅，min_attention=0.6）  ← 「天」感知
    SupplyChainLinker（订阅，min_attention=0.4）← 供应链风险感知

💡 阈值说明：
    - 0.7+：只关心高注意力内容（重大新闻）
    - 0.6：中等注意力（一般新闻）
    - 0.4：低阈值（怕错过风险事件）

使用方式：
    bus = TextSignalBus()

    # 订阅者注册
    bus.subscribe("SectorNarrative", on_signal, min_attention=0.7)   # 地
    bus.subscribe("TimingNarrative", on_signal, min_attention=0.7)   # 天
    bus.subscribe("BanditHead", on_signal, min_attention=0.5)
    bus.subscribe("SupplyChainLinker", on_signal, min_attention=0.4)

    # 发布信号
    bus.publish(item)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from deva.naja.cognition.attention_text_router import (
    AttentionTextItem,
    StructuredSignal,
    THRESHOLD_DEEP,
)

log = logging.getLogger(__name__)


# ============== 数据结构 ==============

@dataclass
class Subscriber:
    """
    订阅者

    代表一个模块对文本信号的订阅
    """
    module_name: str                          # 模块名称
    callback: Callable[[AttentionTextItem], None]  # 回调函数
    min_attention: float = 0.5               # 最小注意力阈值
    topics: List[str] = field(default_factory=list)  # 感兴趣的主题（空=全部）
    enabled: bool = True                      # 是否启用


@dataclass
class BusStats:
    """总线统计"""
    total_published: int = 0
    total_delivered: int = 0
    by_module: Dict[str, int] = field(default_factory=dict)
    by_level: Dict[str, int] = field(default_factory=dict)
    dropped: int = 0


# ============== 文本信号总线 ==============

class TextSignalBus:
    """
    文本信号总线

    核心机制：
    1. 发布者只需发送一次，所有订阅者自动接收
    2. 每个订阅者可设置注意力阈值，低分信号自动跳过
    3. 支持主题过滤（只关心特定主题的订阅者）

    使用示例：
        # 初始化
        bus = TextSignalBus()

        # SectorNarrative 订阅高注意力信号
        bus.subscribe(
            "SectorNarrative",
            on_narrative_signal,
            min_attention=0.7
        )

        # BanditHead 订阅中等以上
        bus.subscribe(
            "BanditHead",
            on_bandit_signal,
            min_attention=0.5
        )

        # SupplyChainLinker 怕错过风险，阈值较低
        bus.subscribe(
            "SupplyChainLinker",
            on_supply_chain_signal,
            min_attention=0.4
        )

        # 发布信号
        bus.publish(attention_item)
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Subscriber]] = defaultdict(list)
        self._topic_modules: Dict[str, Set[str]] = defaultdict(set)  # topic -> modules

        # 统计
        self._stats = BusStats()

        # 订阅者注册表（用于调试）
        self._module_names: Set[str] = set()

        log.info("[TextSignalBus] 文本信号总线初始化完成")

    def subscribe(
        self,
        module_name: str,
        callback: Callable[[AttentionTextItem], None],
        min_attention: float = 0.5,
        topics: Optional[List[str]] = None,
    ) -> Subscriber:
        """
        订阅文本信号

        Args:
            module_name: 模块名称（唯一标识）
            callback: 回调函数，接收 AttentionTextItem
            min_attention: 最小注意力阈值，低于此分数的信号不会发送
            topics: 感兴趣的主题列表（空=全部主题）

        Returns:
            Subscriber 实例
        """
        subscriber = Subscriber(
            module_name=module_name,
            callback=callback,
            min_attention=min_attention,
            topics=topics or [],
        )

        self._subscribers[module_name].append(subscriber)
        self._module_names.add(module_name)

        # 更新主题映射
        for topic in subscriber.topics:
            self._topic_modules[topic].add(module_name)

        log.info(
            f"[TextSignalBus] 模块 '{module_name}' 订阅成功 "
            f"(min_attention={min_attention}, topics={topics or '全部'})"
        )

        return subscriber

    def unsubscribe(self, module_name: str) -> bool:
        """
        取消订阅

        Args:
            module_name: 模块名称

        Returns:
            是否成功取消
        """
        if module_name not in self._subscribers:
            return False

        # 清理主题映射
        for topic, modules in self._topic_modules.items():
            modules.discard(module_name)

        del self._subscribers[module_name]
        self._module_names.discard(module_name)

        log.info(f"[TextSignalBus] 模块 '{module_name}' 已取消订阅")
        return True

    def enable_module(self, module_name: str, enabled: bool = True):
        """启用/禁用模块的订阅"""
        if module_name not in self._subscribers:
            return

        for sub in self._subscribers[module_name]:
            sub.enabled = enabled

        status = "启用" if enabled else "禁用"
        log.debug(f"[TextSignalBus] 模块 '{module_name}' 已{status}")

    def publish(self, item: AttentionTextItem) -> Dict[str, bool]:
        """
        发布文本信号到所有订阅者

        Args:
            item: 注意力文本项

        Returns:
            各模块的接收结果 {module_name: success}
        """
        self._stats.total_published += 1
        results = {}

        routing_level = item.routing_level()
        self._stats.by_level[routing_level] = self._stats.by_level.get(routing_level, 0) + 1

        delivered_count = 0

        for module_name, subs in self._subscribers.items():
            for sub in subs:
                if not sub.enabled:
                    continue

                # 1. 检查注意力阈值
                if item.attention_score < sub.min_attention:
                    continue

                # 2. 检查主题过滤
                if sub.topics and not self._matches_topics(item, sub.topics):
                    continue

                # 3. 发送信号
                try:
                    sub.callback(item)
                    results[module_name] = True
                    delivered_count += 1

                    # 统计
                    self._stats.total_delivered += 1
                    self._stats.by_module[module_name] = \
                        self._stats.by_module.get(module_name, 0) + 1

                except Exception as e:
                    log.error(f"[TextSignalBus] 模块 '{module_name}' 回调失败: {e}")
                    results[module_name] = False

        if delivered_count == 0 and item.attention_score >= THRESHOLD_DEEP:
            self._stats.dropped += 1

        return results

    def _matches_topics(self, item: AttentionTextItem, topics: List[str]) -> bool:
        """检查文本是否匹配订阅的主题"""
        # 检查主题候选
        for topic in topics:
            if topic in item.topic_candidates:
                return True
            if topic in item.narrative_tags:
                return True
            if any(topic.lower() in kw.lower() for kw in item.raw_keywords):
                return True

        # 如果订阅者没有设置主题过滤，返回 True
        return False

    def broadcast(self, items: List[AttentionTextItem]) -> Dict[str, Any]:
        """
        批量发布信号

        Args:
            items: 注意力文本项列表

        Returns:
            发布统计
        """
        total_delivered = 0

        for item in items:
            result = self.publish(item)
            total_delivered += sum(1 for v in result.values() if v)

        return {
            "total_items": len(items),
            "total_delivered": total_delivered,
            "avg_delivery": round(total_delivered / max(1, len(items)), 2),
        }

    def get_subscribers(self, module_name: Optional[str] = None) -> List[Subscriber]:
        """获取订阅者列表"""
        if module_name:
            return self._subscribers.get(module_name, [])
        return [s for subs in self._subscribers.values() for s in subs]

    def get_stats(self) -> Dict[str, Any]:
        """获取总线统计"""
        return {
            "total_published": self._stats.total_published,
            "total_delivered": self._stats.total_delivered,
            "delivery_rate": round(
                self._stats.total_delivered / max(1, self._stats.total_published) * 100, 1
            ),
            "by_module": dict(self._stats.by_module),
            "by_level": dict(self._stats.by_level),
            "dropped": self._stats.dropped,
            "active_modules": len(self._module_names),
        }

    def reset_stats(self):
        """重置统计"""
        self._stats = BusStats()

    def list_modules(self) -> List[str]:
        """列出所有订阅的模块"""
        return sorted(list(self._module_names))


# ============== 单例访问 ==============

_bus: Optional[TextSignalBus] = None


def get_text_bus() -> TextSignalBus:
    """获取文本信号总线单例"""
    global _bus
    if _bus is None:
        _bus = TextSignalBus()
    return _bus


def reset_text_bus():
    """重置总线（用于测试）"""
    global _bus
    _bus = None
