"""
CognitiveSignalBus - 认知信号事件总线

统一事件系统的一部分，处理认知层的高级信号事件。
与 NajaEventBus（处理 dataclass 事件）共同构成 Naja 统一事件系统。

🧠 定位：天-地-人框架中的「人」
    - ManasEngine 订阅此总线，感知认知层变化

📡 事件类型：见 CognitiveEventType 枚举

使用方式：
    from deva.naja.events import get_cognitive_bus, CognitiveEventType

    bus = get_cognitive_bus()
    bus.publish_cognitive_event(
        source="BlockNarrative",
        event_type=CognitiveEventType.BLOCK_NARRATIVE_UPDATE,
        narratives=[...],
        importance=0.8
    )
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

log = logging.getLogger(__name__)


# ============== 事件类型 ==============

class CognitiveEventType(Enum):
    """认知事件类型"""
    # 地 - BlockNarrative 叙事更新
    # 新事件名：题材叙事更新
    BLOCK_NARRATIVE_UPDATE = "block_narrative_update"
    NARRATIVE_BOOST = "narrative_boost"                  # 叙事重要性提升
    NARRATIVE_DECAY = "narrative_decay"                  # 叙事衰退

    # 天 - TimingNarrative 时机更新
    TIMING_NARRATIVE_UPDATE = "timing_narrative_update"  # 时机叙事更新
    TIMING_NARRATIVE_SHIFT = "timing_narrative_shift"    # 时机叙事切换

    # 🔥 共振分析（CrossSignalAnalyzer）
    RESONANCE_DETECTED = "resonance_detected"           # 检测到共振
    RESONANCE_DECAY = "resonance_decay"                 # 共振减弱/消失

    # 供应链风险
    SUPPLY_CHAIN_RISK = "supply_chain_risk"         # 供应链风险事件
    SUPPLY_CHAIN_IMPACT = "supply_chain_impact"     # 供应链影响分析
    NARRATIVE_SUPPLY_LINK = "narrative_supply_link"  # 叙事-供应链关联

    # 🚀 全球市场事件（给 LiquidityCognition）
    GLOBAL_MARKET_EVENT = "global_market_event"     # 全球市场行情变化

    # 组合级信号
    PORTFOLIO_SIGNAL = "portfolio_signal"            # 组合级信号
    RISK_ALERT = "risk_alert"                        # 风险警报

    # 通用
    COGNITION_RESET = "cognition_reset"              # 认知系统重置

    # ── 以下从 cognition_bus.py 合并（原 CognitionEventType） ──
    ATTENTION_SNAPSHOT = "attention_snapshot"         # 注意力快照
    NEWS_SIGNAL = "news_signal"                      # 新闻信号
    INSIGHT_GENERATED = "insight_generated"           # 洞察生成
    COGNITION_FEEDBACK = "cognition_feedback"         # 认知反馈
    NARRATIVE_UPDATE = "narrative_update"             # 叙事更新（通用）
    SEMANTIC_GRAPH_UPDATE = "semantic_graph_update"   # 语义图谱更新


@dataclass
class CognitiveSignalEvent:
    """
    认知信号事件

    代表认知层内部模块的重要状态变化
    """
    source: str                                      # 事件来源模块
    event_type: CognitiveEventType                   # 事件类型
    timestamp: float = field(default_factory=time.time)  # 事件时间戳

    # 事件数据
    narratives: List[str] = field(default_factory=list)   # 相关叙事
    importance: float = 0.5                               # 重要性 [0, 1]
    confidence: float = 0.5                               # 置信度 [0, 1]

    # 可选附加数据
    stock_codes: List[str] = field(default_factory=list)  # 相关股票
    risk_level: str = "unknown"                           # 风险等级
    metadata: Dict[str, Any] = field(default_factory=dict)  # 其他元数据

    def __str__(self) -> str:
        return (
            f"CognitiveSignalEvent(source={self.source}, "
            f"type={self.event_type.value}, "
            f"narratives={self.narratives[:2]}{'...' if len(self.narratives) > 2 else ''}, "
            f"importance={self.importance:.2f})"
        )


@dataclass
class CognitiveSubscriber:
    """认知事件订阅者"""
    module_name: str                                          # 模块名称
    callback: Callable[[CognitiveSignalEvent], None]           # 回调函数
    event_types: List[CognitiveEventType] = field(default_factory=list)  # 感兴趣的事件类型
    min_importance: float = 0.3                               # 最小重要性阈值
    enabled: bool = True


@dataclass
class CognitiveBusStats:
    """总线统计"""
    total_published: int = 0
    total_delivered: int = 0
    by_module: Dict[str, int] = field(default_factory=dict)
    by_event_type: Dict[str, int] = field(default_factory=dict)
    dropped: int = 0


# ============== 认知信号事件总线 ==============

class CognitiveSignalBus:
    """
    认知信号事件总线

    核心机制：
    1. 认知层模块发布重要事件
    2. 其他模块订阅并响应
    3. 支持事件类型过滤和重要性阈值

    使用示例：
        # NarrativeTracker 发布叙事更新
        bus = get_cognitive_bus()
        bus.publish_cognitive_event(
            source="NarrativeTracker",
            event_type=CognitiveEventType.NARRATIVE_UPDATE,
            narratives=["AI芯片需求爆发"],
            importance=0.85
        )

        # ManasEngine 订阅
        bus.subscribe(
            "ManasEngine",
            on_cognitive_event,
            event_types=[CognitiveEventType.NARRATIVE_UPDATE, ...]
        )
    """

    def __init__(self):
        self._subscribers: Dict[str, List[CognitiveSubscriber]] = defaultdict(list)
        self._event_type_modules: Dict[CognitiveEventType, Set[str]] = defaultdict(set)

        # 统计
        self._stats = CognitiveBusStats()

        # 订阅者注册表
        self._module_names: Set[str] = set()

        # 最近事件缓存（用于去重）
        self._recent_events: List[CognitiveSignalEvent] = []
        self._dedup_window = 30.0  # 30秒内相同事件去重

        log.info("[CognitiveSignalBus] 认知信号事件总线初始化完成")

    def subscribe(
        self,
        module_name: str,
        callback: Callable[[CognitiveSignalEvent], None],
        event_types: Optional[List[CognitiveEventType]] = None,
        min_importance: float = 0.3,
    ) -> CognitiveSubscriber:
        """
        订阅认知事件

        Args:
            module_name: 模块名称（唯一标识）
            callback: 回调函数，接收 CognitiveSignalEvent
            event_types: 感兴趣的事件类型列表（空=全部）
            min_importance: 最小重要性阈值

        Returns:
            CognitiveSubscriber 实例
        """
        subscriber = CognitiveSubscriber(
            module_name=module_name,
            callback=callback,
            event_types=event_types or [],
            min_importance=min_importance,
        )

        self._subscribers[module_name].append(subscriber)
        self._module_names.add(module_name)

        # 更新事件类型映射
        for event_type in subscriber.event_types:
            self._event_type_modules[event_type].add(module_name)

        event_type_str = [et.value for et in (event_types or [])]
        log.info(
            f"[CognitiveSignalBus] 模块 '{module_name}' 订阅成功 "
            f"(event_types={event_type_str or '全部'}, min_importance={min_importance})"
        )

        return subscriber

    def unsubscribe(self, module_name: str) -> bool:
        """取消订阅"""
        if module_name not in self._subscribers:
            return False

        # 清理事件类型映射
        for event_type, modules in self._event_type_modules.items():
            modules.discard(module_name)

        del self._subscribers[module_name]
        self._module_names.discard(module_name)

        log.info(f"[CognitiveSignalBus] 模块 '{module_name}' 已取消订阅")
        return True

    def publish_cognitive_event(
        self,
        source: str,
        event_type: CognitiveEventType,
        narratives: Optional[List[str]] = None,
        importance: float = 0.5,
        confidence: float = 0.5,
        stock_codes: Optional[List[str]] = None,
        risk_level: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, bool]:
        """
        发布认知事件

        Args:
            source: 事件来源模块
            event_type: 事件类型
            narratives: 相关叙事列表
            importance: 重要性 [0, 1]
            confidence: 置信度 [0, 1]
            stock_codes: 相关股票代码
            risk_level: 风险等级
            metadata: 其他元数据

        Returns:
            各模块的接收结果
        """
        event = CognitiveSignalEvent(
            source=source,
            event_type=event_type,
            narratives=narratives or [],
            importance=importance,
            confidence=confidence,
            stock_codes=stock_codes or [],
            risk_level=risk_level,
            metadata=metadata or {},
        )

        # 去重检查
        if self._is_duplicate(event):
            log.debug(f"[CognitiveSignalBus] 事件去重: {event}")
            return {}

        self._recent_events.append(event)
        # 清理旧事件
        self._recent_events = [
            e for e in self._recent_events
            if time.time() - e.timestamp < self._dedup_window
        ]

        self._stats.total_published += 1
        self._stats.by_event_type[event_type.value] = \
            self._stats.by_event_type.get(event_type.value, 0) + 1

        results = {}
        delivered_count = 0

        for module_name, subs in self._subscribers.items():
            for sub in subs:
                if not sub.enabled:
                    continue

                # 检查重要性阈值
                if event.importance < sub.min_importance:
                    continue

                # 检查事件类型过滤
                if sub.event_types and event.event_type not in sub.event_types:
                    continue

                # 发送事件
                try:
                    sub.callback(event)
                    results[module_name] = True
                    delivered_count += 1

                    self._stats.total_delivered += 1
                    self._stats.by_module[module_name] = \
                        self._stats.by_module.get(module_name, 0) + 1

                except Exception as e:
                    log.error(f"[CognitiveSignalBus] 模块 '{module_name}' 回调失败: {e}")
                    results[module_name] = False

        if delivered_count == 0 and event.importance >= 0.7:
            self._stats.dropped += 1
            log.debug(f"[CognitiveSignalBus] 高重要性事件无人接收: {event}")

        return results

    def _is_duplicate(self, event: CognitiveSignalEvent) -> bool:
        """检查是否为重复事件"""
        current_time = time.time()
        for recent in self._recent_events:
            if current_time - recent.timestamp > self._dedup_window:
                continue
            # 相同来源、相同类型、相同叙事 = 重复
            if (
                recent.source == event.source and
                recent.event_type == event.event_type and
                set(recent.narratives) == set(event.narratives)
            ):
                return True
        return False

    def publish(self, event: CognitiveSignalEvent) -> Dict[str, bool]:
        """
        直接发布事件对象

        Args:
            event: CognitiveSignalEvent 实例

        Returns:
            各模块的接收结果
        """
        return self.publish_cognitive_event(
            source=event.source,
            event_type=event.event_type,
            narratives=event.narratives,
            importance=event.importance,
            confidence=event.confidence,
            stock_codes=event.stock_codes,
            risk_level=event.risk_level,
            metadata=event.metadata,
        )

    def enable_module(self, module_name: str, enabled: bool = True):
        """启用/禁用模块的订阅"""
        if module_name not in self._subscribers:
            return

        for sub in self._subscribers[module_name]:
            sub.enabled = enabled

        status = "启用" if enabled else "禁用"
        log.debug(f"[CognitiveSignalBus] 模块 '{module_name}' 已{status}")

    def get_subscribers(self, module_name: Optional[str] = None) -> List[CognitiveSubscriber]:
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
            "by_event_type": dict(self._stats.by_event_type),
            "dropped": self._stats.dropped,
            "active_modules": len(self._module_names),
        }

    def list_modules(self) -> List[str]:
        """列出所有订阅的模块"""
        return sorted(list(self._module_names))

    def reset_stats(self):
        """重置统计"""
        self._stats = CognitiveBusStats()


# ============== 单例访问 ==============

_cognitive_bus: Optional[CognitiveSignalBus] = None


def get_cognitive_bus() -> CognitiveSignalBus:
    """获取认知信号事件总线单例"""
    global _cognitive_bus
    if _cognitive_bus is None:
        _cognitive_bus = CognitiveSignalBus()
    return _cognitive_bus


def reset_cognitive_bus():
    """重置总线（用于测试）"""
    global _cognitive_bus
    _cognitive_bus = None
