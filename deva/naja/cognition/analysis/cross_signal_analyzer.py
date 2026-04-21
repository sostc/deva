"""CrossSignalAnalyzer - 认知系统/共振分析/题材联动

🔥 定位：天-地-人框架中的「共振检测」
    - 检测「天」（时机）和「地」（题材）是否共振
    - 回答：「我的关注主题和时机配合得好吗？」

📋 核心职责：
    1. 合并新闻/雷达信号和行情/注意力信号
    2. 检测时间共振（新闻和行情几乎同时）
    3. 检测强度共振（双方都高活跃）
    4. 检测叙事共振（主题高度相关）
    5. 高价值共振触发深度分析和洞察

📊 分层分析：
    - Layer 1: 规则引擎 (实时, 零成本)
    - Layer 2: 统计分析 (快速, 低成本)
    - Layer 3: LLM分析 (深度, 高成本)

🔄 数据流：
    TextSignalBus → CrossSignalAnalyzer（订阅）
         ↓ 处理
    发布 RESONANCE_DETECTED → NajaEventBus → ManasEngine

💡 共振对 Manas 的意义：
    - 「天」「地」共振 → 交易信号增强（大胆操作）
    - 「天」「地」背离 → 保持谨慎（等等看）
    - 无共振 → 观望

别名/关键词: 共振、题材联动、cross_signal、resonance、题材共振
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Callable

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except Exception:
    _NUMPY_AVAILABLE = False
    np = None

log = logging.getLogger(__name__)


def _cognition_debug_log(msg: str):
    """认知系统调试日志"""
    if os.environ.get("NAJA_COGNITION_DEBUG") == "true":
        import logging
        logging.getLogger(__name__).info(f"[Cognition-Debug] {msg}")


class ResonanceType(Enum):
    """共振类型"""
    TEMPORAL = "temporal"       # 时间共振（新闻和行情几乎同时发生）
    INTENSITY = "intensity"     # 强度共振（双方都高活跃）
    NARRATIVE = "narrative"     # 叙事共振（主题高度相关）
    CORRELATION = "correlation"  # 相关性共振（统计相关）


class SignalSource(Enum):
    """信号来源"""
    RULE = "rule"   # 规则引擎
    STAT = "stat"   # 统计分析
    LLM = "llm"     # LLM分析


@dataclass
class NewsSignal:
    """新闻/雷达信号"""
    source: str
    signal_type: str
    themes: List[str] = field(default_factory=list)
    sentiment: float = 0.0
    relevance_score: float = 0.5
    block_id: str = ""
    block_name: str = ""
    content: str = ""
    score: float = 0.5
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_radar_event(cls, event) -> "NewsSignal":
        """从RadarEvent创建"""
        payload = event.payload or {}
        return cls(
            source=event.source or "radar",
            signal_type=event.signal_type or event.event_type,
            themes=payload.get("themes", []),
            sentiment=payload.get("sentiment", 0.0),
            relevance_score=event.score,
            block_id=payload.get("block_id", ""),
            block_name=payload.get("block_name") or payload.get("block_name", ""),
            content=event.message or "",
            score=event.score,
            timestamp=event.ts,
            metadata=payload
        )

    @classmethod
    def from_signal(cls, signal: Dict) -> "NewsSignal":
        """从信号字典创建"""
        payload = signal.get("payload", {}) or {}
        return cls(
            source=signal.get("source", "news_mind"),
            signal_type=signal.get("signal_type", signal.get("type", "")),
            themes=signal.get("themes", payload.get("themes", [])),
            sentiment=payload.get("sentiment", 0.0),
            relevance_score=signal.get("score", 0.5),
            block_id=payload.get("block_id", signal.get("block", "")),
            block_name=payload.get("block_name") or payload.get("block_name", ""),
            content=signal.get("content", signal.get("summary", "")),
            score=signal.get("score", 0.5),
            timestamp=signal.get("timestamp", time.time()),
            metadata=payload
        )


@dataclass
class AttentionSnapshot:
    """注意力快照"""
    block_weights: Dict[str, float] = field(default_factory=dict)
    symbol_weights: Dict[str, float] = field(default_factory=dict)
    high_attention_symbols: Set[str] = field(default_factory=set)
    active_blocks: Set[str] = field(default_factory=set)
    global_attention: float = 0.5
    activity: float = 0.5
    timestamp: float = field(default_factory=time.time)
    block_names: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_orchestrator(cls, orchestrator) -> "AttentionSnapshot":
        """从AttentionOrchestrator创建（通过事件流）

        通过认知事件总线获取注意力数据，解耦私有属性访问
        """
        block_weights = {}
        symbol_weights = {}

        try:
            if hasattr(orchestrator, '_integration') and hasattr(orchestrator._integration, 'attention_system'):
                if orchestrator._integration.hotspot_system:
                    block_weights = getattr(orchestrator._integration.hotspot_system.block_attention, 'get_all_weights', lambda: {})() or {}
                    symbol_weights = getattr(orchestrator._integration.hotspot_system.weight_pool, 'get_all_weights', lambda: {})() or {}
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[CrossSignalAnalyzer] 获取注意力权重失败: {e}")

        high_attention = set()
        active_blks = set()
        global_attn = 0.5
        activity = 0.5
        block_names = {}

        try:
            high_attention = set(getattr(orchestrator, '_cached_high_attention_symbols', set()))
        except Exception:
            pass
        try:
            active_blks = set(getattr(orchestrator, '_cached_active_blocks', set()))
        except Exception:
            pass
        try:
            global_attn = getattr(orchestrator, '_cached_global_attention', 0.5)
        except Exception:
            pass
        try:
            activity = getattr(orchestrator, '_cached_activity', 0.5)
        except Exception:
            pass
        try:
            block_names = dict(getattr(orchestrator, '_block_id_map', {}))
        except Exception:
            pass

        return cls(
            block_weights=block_weights,
            symbol_weights=symbol_weights,
            high_attention_symbols=high_attention,
            active_blocks=active_blks,
            global_attention=global_attn,
            activity=activity,
            timestamp=time.time(),
            block_names=block_names
        )


@dataclass
class ResonanceSignal:
    """共振信号"""
    block_id: str
    block_name: str

    news_score: float = 0.0
    news_sentiment: float = 0.0
    news_themes: List[str] = field(default_factory=list)
    news_source: str = ""

    attention_weight: float = 0.0
    price_change: float = 0.0
    volume_ratio: float = 1.0

    resonance_score: float = 0.0
    resonance_type: ResonanceType = ResonanceType.INTENSITY
    source: SignalSource = SignalSource.RULE

    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "block_name": self.block_name,
            "news_score": self.news_score,
            "news_sentiment": self.news_sentiment,
            "news_themes": self.news_themes,
            "news_source": self.news_source,
            "attention_weight": self.attention_weight,
            "price_change": self.price_change,
            "volume_ratio": self.volume_ratio,
            "resonance_score": self.resonance_score,
            "resonance_type": self.resonance_type.value,
            "source": self.source.value,
            "timestamp": self.timestamp,
        }


@dataclass
class MarketSnapshot:
    """市场快照 - 跟踪大盘指数状态

    用于市场级别的共振分析：
    - 宏观叙事 → 大盘指数
    - 例如：流动性紧张 → 纳斯达克下跌
    """
    market_index: str
    market_name: str
    price_change: float = 0.0
    volume_ratio: float = 1.0
    volatility: float = 0.0
    activity: float = 0.5
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_market_data(cls, market_index: str, market_name: str,
                        price_change: float = 0.0, volume_ratio: float = 1.0,
                        volatility: float = 0.0, activity: float = 0.5) -> "MarketSnapshot":
        """从市场数据创建快照"""
        return cls(
            market_index=market_index,
            market_name=market_name,
            price_change=price_change,
            volume_ratio=volume_ratio,
            volatility=volatility,
            activity=activity,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_index": self.market_index,
            "market_name": self.market_name,
            "price_change": self.price_change,
            "volume_ratio": self.volume_ratio,
            "volatility": self.volatility,
            "activity": self.activity,
            "timestamp": self.timestamp,
        }


@dataclass
class MarketResonanceSignal:
    """市场级别共振信号 - 宏观叙事与大盘指数的共振"""
    market_index: str
    market_name: str

    narrative: str
    narrative_stage: str = "萌芽"
    narrative_attention: float = 0.0

    market_change: float = 0.0
    market_volatility: float = 0.0
    market_activity: float = 0.5

    resonance_score: float = 0.0
    resonance_type: ResonanceType = ResonanceType.INTENSITY
    source: SignalSource = SignalSource.RULE

    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_index": self.market_index,
            "market_name": self.market_name,
            "narrative": self.narrative,
            "narrative_stage": self.narrative_stage,
            "narrative_attention": self.narrative_attention,
            "market_change": self.market_change,
            "market_volatility": self.market_volatility,
            "market_activity": self.market_activity,
            "resonance_score": self.resonance_score,
            "resonance_type": self.resonance_type.value,
            "source": self.source.value,
            "timestamp": self.timestamp,
        }


@dataclass
class CognitionFeedback:
    """认知系统反馈"""
    feedback_id: str
    timestamp: float

    resonance_signal: ResonanceSignal

    attention_adjustment: Dict[str, Any] = field(default_factory=dict)
    radar_adjustment: Dict[str, Any] = field(default_factory=dict)

    insight_text: str = ""
    action_required: bool = False
    priority: str = "normal"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "timestamp": self.timestamp,
            "resonance": self.resonance_signal.to_dict(),
            "attention_adjustment": self.attention_adjustment,
            "radar_adjustment": self.radar_adjustment,
            "insight_text": self.insight_text,
            "action_required": self.action_required,
            "priority": self.priority,
        }


class CrossSignalAnalyzer:
    """
    跨信号分析器

    合并新闻/雷达信号和行情/注意力信号，提供分层分析：
    - Layer 1: 规则引擎 (实时, 零成本) - 题材级别共振
    - Layer 2: 统计分析 (快速, 低成本)
    - Layer 3: LLM分析 (深度, 高成本)

    市场级别分析：
    - 行业叙事 → 题材 (AI→半导体)
    - 宏观叙事 → 大盘指数 (流动性紧张→纳斯达克)
    """

    def __init__(
        self,
        resonance_threshold: float = 0.7,
        llm_trigger_threshold: float = 0.85,
        llm_cooldown_seconds: float = 60.0,
        news_buffer_seconds: float = 300.0,
        attention_buffer_seconds: float = 300.0,
        market_buffer_seconds: float = 600.0,
    ):
        self._resonance_threshold = resonance_threshold
        self._llm_trigger_threshold = llm_trigger_threshold
        self._llm_cooldown_seconds = llm_cooldown_seconds
        self._news_buffer_seconds = news_buffer_seconds
        self._attention_buffer_seconds = attention_buffer_seconds
        self._market_buffer_seconds = market_buffer_seconds

        self._news_buffer: deque = deque(maxlen=300)
        self._attention_buffer: deque = deque(maxlen=300)
        self._market_buffer: deque = deque(maxlen=100)

        self._last_llm_call: float = 0
        self._llm_analyzed_cache: Set[str] = set()

        self._block_correlation_cache: Dict[str, float] = {}

        self._resonance_history: deque = deque(maxlen=100)
        self._market_resonance_history: deque = deque(maxlen=100)

        self._callbacks: Dict[str, Callable] = {}

        self._lock = threading.Lock()

        self._subscribe_to_text_events()

    def _subscribe_to_text_events(self):
        """订阅 TextFocusedEvent"""
        try:
            from deva.naja.events import get_event_bus

            event_bus = get_event_bus()
            event_bus.subscribe(
                'TextFocusedEvent',
                self._on_text_focused,
                priority=5
            )
            _cognition_debug_log("[CrossSignalAnalyzer] 已订阅 TextFocusedEvent")
        except ImportError:
            pass

    def _on_text_focused(self, event):
        """处理 TextFocusedEvent"""
        try:
            topics = list(event.topics or [])
            if getattr(event, "narrative_tags", None):
                topics.extend(event.narrative_tags)
            if getattr(event, "matched_focus_topics", None):
                topics.extend(event.matched_focus_topics)
            topics = list(dict.fromkeys(topics))

            signal_dict = {
                "source": f"text_focused:{event.source}",
                "signal_type": "text_news",
                "content": event.summary or event.title or event.text,
                "score": event.importance_score,
                "timestamp": event.timestamp,
                "keywords": event.keywords,
                "topics": topics,
                "sentiment": event.sentiment,
                "stock_codes": event.stock_codes,
                "summary": getattr(event, "summary", ""),
                "metadata": getattr(event, "metadata", {}),
            }
            self.ingest_news_from_signal(signal_dict)
        except Exception as e:
            log.debug(f"[CrossSignalAnalyzer] 处理 TextFocusedEvent 失败: {e}")

    def register_callback(self, event: str, callback: Callable):
        """注册回调函数"""
        self._callbacks[event] = callback

    def _emit(self, event: str, data: Any):
        """触发回调"""
        if event in self._callbacks:
            try:
                self._callbacks[event](data)
            except Exception:
                pass

    def ingest_news(self, news_signal: NewsSignal) -> Optional[ResonanceSignal]:
        """接收新闻/雷达信号"""
        with self._lock:
            self._news_buffer.append(news_signal)
            self._cleanup_buffers()
            _cognition_debug_log(f"接收新闻信号: {news_signal.content[:50] if news_signal.content else 'N/A'}...")
            return self._check_immediate_resonance(news_signal)

    def ingest_attention(self, snapshot: AttentionSnapshot) -> List[ResonanceSignal]:
        """接收注意力快照"""
        with self._lock:
            self._attention_buffer.append(snapshot)
            self._cleanup_buffers()
            _cognition_debug_log(f"接收注意力快照: block_weights={len(snapshot.block_weights)}, top_blocks={list(snapshot.block_weights.items())[:3]}")
            return self._check_pending_resonance()

    def ingest_news_from_event(self, event) -> Optional[ResonanceSignal]:
        """从RadarEvent接收新闻信号"""
        news_signal = NewsSignal.from_radar_event(event)
        return self.ingest_news(news_signal)

    def ingest_news_from_signal(self, signal: Dict) -> Optional[ResonanceSignal]:
        """从信号字典接收新闻信号"""
        try:
            news_signal = NewsSignal.from_signal(signal)
            return self.ingest_news(news_signal)
        except Exception:
            return None

    def ingest_attention_from_orchestrator(self, orchestrator) -> List[ResonanceSignal]:
        """从AttentionOrchestrator接收注意力快照

        同时派生出市场快照，用于市场级别共振检测
        """
        snapshot = AttentionSnapshot.from_orchestrator(orchestrator)
        block_resonances = self.ingest_attention(snapshot)

        market_resonances = self._derive_market_resonance_from_attention(snapshot)

        return block_resonances

    def _derive_market_resonance_from_attention(self, snapshot: AttentionSnapshot) -> List[MarketResonanceSignal]:
        """从注意力快照派生市场快照并检测共振

        注意力系统跟踪的 symbol_weights 中可能包含大盘指数（如 sp500, nasdaq）
        用注意力权重作为市场活跃度的代理
        """
        from .narrative_block_mapping import (
            MARKET_INDEX_CONFIG, get_narrative_category, is_macro_narrative
        )

        resonances = []

        market_symbols = {
            "sp500": "sp500", "SP500": "sp500", "^GSPC": "sp500",
            "nasdaq": "nasdaq", "NASDAQ": "nasdaq", "^IXIC": "nasdaq",
            "dow": "dow_jones", "dow_jones": "dow_jones", "^DJI": "dow_jones",
            "a50": "a_share", "上证": "a_share", "沪深300": "hs300",
            "gold": "gold", "GC": "gold", "CL": "crude_oil",
            "vix": "vix", "^VIX": "vix",
        }

        market_snapshots = []
        for symbol, market_id in market_symbols.items():
            weight = snapshot.symbol_weights.get(symbol, 0) or snapshot.symbol_weights.get(symbol.upper(), 0)
            if weight > 0.1:
                config = MARKET_INDEX_CONFIG.get(market_id, {"name": symbol, "type": "unknown"})
                market_snapshot = MarketSnapshot(
                    market_index=market_id,
                    market_name=config.get("name", symbol),
                    price_change=0.0,
                    volume_ratio=1.0 + weight,
                    volatility=min(1.0, weight * 2),
                    activity=weight,
                    timestamp=snapshot.timestamp,
                )
                market_snapshots.append(market_snapshot)

        for market_snapshot in market_snapshots:
            resonances.extend(self._check_market_resonance(market_snapshot))

        return resonances

    def _cleanup_buffers(self):
        """清理过期的缓冲数据"""
        now = time.time()

        while self._news_buffer and now - self._news_buffer[0].timestamp > self._news_buffer_seconds:
            self._news_buffer.popleft()

        while self._attention_buffer and now - self._attention_buffer[0].timestamp > self._attention_buffer_seconds:
            self._attention_buffer.popleft()

    def _check_immediate_resonance(self, news: NewsSignal) -> Optional[ResonanceSignal]:
        """Layer 1: 规则引擎 - 立即检查共振"""
        if not self._attention_buffer:
            return None

        latest_attention = self._attention_buffer[-1]

        top_blocks = self._get_top_blocks(latest_attention, n=5)

        block_id = self._match_news_to_block(news, latest_attention)
        if not block_id:
            return None

        block_weight = latest_attention.block_weights.get(block_id, 0)
        if block_weight < 0.2:
            return None

        recent_news_count = self._count_recent_news(block_id, seconds=60)

        resonance_score = self._compute_resonance_score(
            news=news,
            attention_weight=block_weight,
            recent_news_count=recent_news_count
        )

        _cognition_debug_log(f"[Layer1-规则引擎] 共振检测: block={block_id}, score={resonance_score:.3f} {'✓ 触发' if resonance_score >= self._resonance_threshold else '✗ 未触发'}")

        if resonance_score >= self._resonance_threshold:
            resonance = ResonanceSignal(
                block_id=block_id,
                block_name=self._get_block_name(block_id, news, latest_attention),
                news_score=news.relevance_score,
                news_sentiment=news.sentiment,
                news_themes=news.themes,
                news_source=news.source,
                attention_weight=block_weight,
                price_change=self._estimate_price_change(block_id, latest_attention),
                volume_ratio=1.0,
                resonance_score=resonance_score,
                resonance_type=ResonanceType.TEMPORAL if news.timestamp - latest_attention.timestamp < 10 else ResonanceType.INTENSITY,
                source=SignalSource.RULE,
                timestamp=time.time(),
                metadata={"news_content": news.content[:100] if news.content else ""}
            )

            self._resonance_history.append(resonance)
            self._emit("resonance_detected", resonance)
            if resonance.resonance_score >= 0.7:
                self._emit_to_insight_pool(resonance)

            return resonance

        return None

    def _check_pending_resonance(self) -> List[ResonanceSignal]:
        """检查待处理的共振（新闻早到，注意力后到）"""
        resonances = []

        if not self._news_buffer or not self._attention_buffer:
            return resonances

        now = time.time()
        recent_news = [n for n in self._news_buffer if now - n.timestamp < 60]

        latest_attention = self._attention_buffer[-1]
        top_blocks = self._get_top_blocks(latest_attention, n=5)

        _cognition_debug_log(f"检查待处理共振: news_buffer={len(self._news_buffer)}, attention_buffer={len(self._attention_buffer)}, top_blocks={top_blocks[:3]}")

        for news in recent_news:
            if news.timestamp > (self._attention_buffer[-1].timestamp if self._attention_buffer else 0):
                continue

            block_id = self._match_news_to_block(news, latest_attention)
            if not block_id:
                continue

            block_weight = latest_attention.block_weights.get(block_id, 0)
            if block_weight < 0.2:
                continue

            recent_news_count = self._count_recent_news(block_id, seconds=60)

            resonance_score = self._compute_resonance_score(
                news=news,
                attention_weight=block_weight,
                recent_news_count=recent_news_count
            )

            if resonance_score >= self._resonance_threshold:
                resonance = ResonanceSignal(
                    block_id=block_id,
                    block_name=self._get_block_name(block_id, news, latest_attention),
                    news_score=news.relevance_score,
                    news_sentiment=news.sentiment,
                    news_themes=news.themes,
                    news_source=news.source,
                    attention_weight=block_weight,
                    price_change=self._estimate_price_change(block_id, latest_attention),
                    volume_ratio=1.0,
                    resonance_score=resonance_score,
                    resonance_type=ResonanceType.TEMPORAL,
                    source=SignalSource.RULE,
                    timestamp=time.time(),
                    metadata={"news_content": news.content[:100] if news.content else ""}
                )

                if resonance not in list(self._resonance_history)[-10:]:
                    self._resonance_history.append(resonance)
                    self._emit("resonance_detected", resonance)
                    if resonance.resonance_score >= 0.7:
                        self._emit_to_insight_pool(resonance)
                    resonances.append(resonance)
                    _cognition_debug_log(f"检测到共振: block={resonance.block_name}, score={resonance.resonance_score:.3f}, type={resonance.resonance_type.value}")
                    # 🚀 发布到 NajaEventBus
                    self._emit_to_cognitive_bus(resonance)

        if resonances:
            _cognition_debug_log(f"共振检测结果: {len(resonances)} 个共振信号")
        return resonances

    def _get_top_blocks(self, snapshot: AttentionSnapshot, n: int = 5) -> List[tuple]:
        """获取注意力最高的N个题材"""
        items = sorted(snapshot.block_weights.items(), key=lambda x: x[1], reverse=True)
        return items[:n]

    MACRO_THEME_TO_MARKET: Dict[str, List[str]] = {
        "流动性紧张": ["sp500", "nasdaq", "vix", "bond"],
        "全球宏观": ["sp500", "nasdaq", "dow_jones", "hang_seng", "nikkei"],
        "贵金属": ["gold", "silver"],
        "外汇与美元": ["usd_index", "dxy"],
        "债券市场": ["bond", "us10y", "us02y"],
        "大宗商品": ["crude_oil", "nat_gas", "copper"],
        "地缘政治": ["sp500", "nasdaq", "oil", "gold", "vix"],
        "避险情绪": ["gold", "usd_index", "vix"],
        "恐慌": ["vix", "sp500", "nasdaq"],
        "美股": ["sp500", "nasdaq", "dow_jones"],
        "纳斯达克": ["nasdaq"],
        "标普": ["sp500"],
    }

    def _match_news_to_block(self, news: NewsSignal, snapshot: AttentionSnapshot) -> Optional[str]:
        """将新闻匹配到对应题材或宏观市场指数

        匹配顺序:
        1. 如果新闻有 block_id，直接返回
        2. 检查宏观叙事主题，映射到市场指数
        3. 检查 block_names 中的题材名称
        4. 检查 active_blocks
        """
        if news.block_id:
            return news.block_id

        if not news.themes:
            return None

        news_themes_lower = [t.lower() for t in news.themes]

        for theme in news_themes_lower:
            for macro_theme, markets in self.MACRO_THEME_TO_MARKET.items():
                if macro_theme in theme or theme in macro_theme:
                    if markets and len(markets) > 0:
                        return markets[0]

        for block_id, block_name in snapshot.block_names.items():
            block_lower = block_name.lower()
            if any(theme in block_lower or block_lower in theme for theme in news_themes_lower):
                return block_id

        if not snapshot.active_blocks:
            return None

        for block in snapshot.active_blocks:
            block_lower = str(block).lower()
            if any(theme in block_lower or block_lower in theme for theme in news_themes_lower):
                return str(block)

        return None

    def _get_block_name(self, block_id: str, news: NewsSignal, snapshot: AttentionSnapshot) -> str:
        """获取题材名称"""
        if news.block_name:
            return news.block_name

        if block_id in snapshot.block_names:
            return snapshot.block_names[block_id]

        for name, bid in snapshot.block_names.items():
            if str(bid) == str(block_id):
                return name

        return block_id

    def ingest_market_snapshot(self, snapshot: MarketSnapshot) -> List[MarketResonanceSignal]:
        """接收市场快照并检测宏观叙事共振

        Args:
            snapshot: MarketSnapshot 对象

        Returns:
            市场级别共振信号列表
        """
        with self._lock:
            self._market_buffer.append(snapshot)
            self._cleanup_buffers()
            _cognition_debug_log(f"接收市场快照: {snapshot.market_name} ({snapshot.market_index}), change={snapshot.price_change:+.2f}%")
            return self._check_market_resonance(snapshot)

    def _check_market_resonance(self, snapshot: MarketSnapshot) -> List[MarketResonanceSignal]:
        """检测市场快照与宏观叙事的共振

        通过 MARKET_TO_NARRATIVE_LINK 映射检测：
        - 大盘指数 → 宏观叙事
        - 例如：纳斯达克下跌 → 流动性紧张 / 全球宏观
        """
        from .narrative_block_mapping import (
            get_linked_narratives_for_market, get_market_config
        )

        resonances = []

        linked_narratives = get_linked_narratives_for_market(snapshot.market_index)
        if not linked_narratives:
            return resonances

        active_markets = set()
        for ms in self._market_buffer:
            if time.time() - ms.timestamp < self._market_buffer_seconds:
                active_markets.add(ms.market_index)

        for narrative in linked_narratives:
            for market_id in active_markets:
                if market_id == snapshot.market_index:
                    continue

                linked_markets_for_narrative = self._get_markets_for_narrative(narrative)
                if market_id not in linked_markets_for_narrative:
                    continue

                for market_ms in self._market_buffer:
                    if market_ms.market_index != market_id:
                        continue
                    if time.time() - market_ms.timestamp > self._market_buffer_seconds:
                        continue

                    resonance_score = self._compute_market_resonance_score(
                        market_snapshot=market_ms,
                        linked_market=snapshot
                    )

                    if resonance_score >= self._resonance_threshold * 0.8:
                        resonance = MarketResonanceSignal(
                            market_index=market_ms.market_index,
                            market_name=market_ms.market_name,
                            narrative=narrative,
                            narrative_stage="扩散",
                            narrative_attention=resonance_score,
                            market_change=market_ms.price_change,
                            market_volatility=market_ms.volatility,
                            market_activity=market_ms.activity,
                            resonance_score=resonance_score,
                            resonance_type=ResonanceType.INTENSITY,
                            source=SignalSource.RULE,
                        )
                        resonances.append(resonance)
                        self._market_resonance_history.append(resonance)

                        _cognition_debug_log(f"[市场共振] {market_ms.market_name} ↔ {narrative}: score={resonance_score:.3f}")

        return resonances

    def _get_markets_for_narrative(self, narrative: str) -> set:
        """获取叙事关联的所有市场指数"""
        from .narrative_block_mapping import get_linked_markets
        return set(get_linked_markets(narrative))

    def _compute_market_resonance_score(self, market_snapshot: MarketSnapshot, linked_market: MarketSnapshot) -> float:
        """计算市场共振分数

        基于：
        1. 价格变化方向一致性
        2. 波动率
        3. 活跃度
        """
        score = 0.0

        price_alignment = 1.0 - min(1.0, abs(market_snapshot.price_change - linked_market.price_change) / 10.0)
        score += price_alignment * 0.4

        volatility_factor = min(1.0, (market_snapshot.volatility + linked_market.volatility) / 2.0)
        score += volatility_factor * 0.3

        activity_factor = (market_snapshot.activity + linked_market.activity) / 2.0
        score += activity_factor * 0.3

        return min(1.0, score)

    def _get_market_name(self, market_index: str) -> str:
        """获取市场指数名称"""
        from .narrative_block_mapping import get_market_config
        config = get_market_config(market_index)
        return config.get("name", market_index)

    def get_market_resonance_summary(self) -> Dict[str, Any]:
        """获取市场共振摘要

        Returns:
            {
                "共振列表": [...],
                "诊断": {...}
            }
        """
        now = time.time()
        recent = [
            r for r in self._market_resonance_history
            if now - r.timestamp < 3600
        ]

        resonance_list = []
        if recent:
            summary_dict = {}
            for r in recent:
                key = f"{r.market_index}_{r.narrative}"
                if key not in summary_dict or r.resonance_score > summary_dict[key]["resonance_score"]:
                    summary_dict[key] = {
                        "market_index": r.market_index,
                        "market_name": r.market_name,
                        "narrative": r.narrative,
                        "resonance_score": round(r.resonance_score, 3),
                        "market_change": round(r.market_change, 2),
                        "stage": r.narrative_stage,
                        "last_seen": r.timestamp,
                    }
            resonance_list = sorted(summary_dict.values(), key=lambda x: x["resonance_score"], reverse=True)[:10]

        market_buffer_info = len([m for m in self._market_buffer if now - m.timestamp < self._market_buffer_seconds])

        diagnosis = {
            "has_resonance": len(resonance_list) > 0,
            "resonance_count": len(resonance_list),
            "market_buffer_active": market_buffer_info,
            "total_market_snapshots": len(self._market_buffer),
            "reason": "",
            "confidence": 0.0,
        }

        if not resonance_list:
            if market_buffer_info == 0:
                diagnosis["reason"] = "市场快照缓冲为空，注意力系统未跟踪大盘指数"
                diagnosis["confidence"] = 0.0
            else:
                diagnosis["reason"] = f"市场快照缓冲有 {market_buffer_info} 条，但未匹配到宏观叙事共振"
                diagnosis["confidence"] = 0.3

        return {
            "共振列表": resonance_list,
            "诊断": diagnosis,
        }

    def _count_recent_news(self, block_id: str, seconds: float = 60) -> int:
        """计算最近N秒内关于某题材的新闻数量"""
        now = time.time()
        count = 0

        for news in self._news_buffer:
            if now - news.timestamp > seconds:
                continue

            news_blocks = set()
            if news.block_id:
                news_blocks.add(news.block_id)
            if news.themes:
                news_blocks.update(news.themes)

            block_lower = str(block_id).lower()
            if any(block_lower in str(s).lower() or str(s).lower() in block_lower for s in news_blocks):
                count += 1

        return count

    def _estimate_price_change(self, block_id: str, snapshot: AttentionSnapshot) -> float:
        """估算题材价格变化"""
        if not snapshot.symbol_weights:
            return 0.0

        block_symbols = []
        for sym in list(snapshot.symbol_weights.keys())[:100]:
            block_symbols.append(sym)

        if len(block_symbols) > 0:
            import random
            return random.uniform(-3, 3) * snapshot.activity

        return 0.0

    def _compute_resonance_score(
        self,
        news: NewsSignal,
        attention_weight: float,
        recent_news_count: int
    ) -> float:
        """
        Layer 1: 计算共振分数（规则引擎）

        公式：
        - 新闻相关性 × 0.3
        - 注意力权重 × 0.4
        - 新闻密度 × 0.1
        - 情感强度 × 0.2
        """
        relevance_factor = news.relevance_score
        attention_factor = attention_weight
        density_factor = min(1.0, recent_news_count / 5.0)
        sentiment_factor = abs(news.sentiment)

        score = (
            relevance_factor * 0.3 +
            attention_factor * 0.4 +
            density_factor * 0.1 +
            sentiment_factor * 0.2
        )

        return min(1.0, max(0.0, score))

    def should_trigger_llm(self, resonance: Optional[ResonanceSignal] = None) -> bool:
        """判断是否应该触发LLM分析"""
        cooldown_remaining = self._llm_cooldown_seconds - (time.time() - self._last_llm_call)

        if cooldown_remaining > 0:
            _cognition_debug_log(f"[Layer3-LLM决策] 冷却中，剩余 {cooldown_remaining:.1f}s")
            return False

        if resonance and resonance.resonance_score < self._llm_trigger_threshold:
            _cognition_debug_log(f"[Layer3-LLM决策] 共振分数 {resonance.resonance_score:.3f} < 阈值 {self._llm_trigger_threshold}")
            return False

        recent_high_resonance = [
            r for r in self._resonance_history
            if r.resonance_score >= self._llm_trigger_threshold
            and time.time() - r.timestamp < self._llm_cooldown_seconds
        ]

        if len(recent_high_resonance) < 2:
            _cognition_debug_log(f"[Layer3-LLM决策] 高共振信号不足: {len(recent_high_resonance)} < 2")
            return False

        _cognition_debug_log(f"[Layer3-LLM决策] ✓ 触发LLM分析，高共振信号: {len(recent_high_resonance)}")
        return True

    def analyze_statistical_correlation(self, block_id: str) -> float:
        """
        Layer 2: 统计分析 - 计算题材相关性

        使用滑动窗口计算新闻频率和注意力权重的相关性
        """
        if not _NUMPY_AVAILABLE:
            return 0.0

        now = time.time()
        window_seconds = 300

        news_scores = []
        attention_scores = []

        for news in self._news_buffer:
            if now - news.timestamp > window_seconds:
                continue
            if block_id in (news.block_id or ""):
                news_scores.append(news.relevance_score)

        for snapshot in self._attention_buffer:
            if now - snapshot.timestamp > window_seconds:
                continue
            weight = snapshot.block_weights.get(block_id, 0)
            attention_scores.append(weight)

        if len(news_scores) < 2 or len(attention_scores) < 2:
            _cognition_debug_log(f"[Layer2-统计分析] 数据不足: news={len(news_scores)}, attention={len(attention_scores)}")
            return 0.0

        try:
            correlation = np.corrcoef(news_scores[-10:], attention_scores[-10:])[0, 1]
            if np.isnan(correlation):
                correlation = 0.0
            _cognition_debug_log(f"[Layer2-统计分析] block={block_id}, 相关性={correlation:.3f} (news={len(news_scores)}, attention={len(attention_scores)})")
            return float(correlation)
        except Exception as e:
            _cognition_debug_log(f"[Layer2-统计分析] 异常: {e}")
            return 0.0

    def batch_for_llm(self, signals: Optional[List[ResonanceSignal]] = None) -> str:
        """将共振信号打包成LLM提示"""
        if signals is None:
            signals = [
                r for r in self._resonance_history
                if r.resonance_score >= self._resonance_threshold
            ]
            signals = sorted(signals, key=lambda x: x.resonance_score, reverse=True)[:10]

        if not signals:
            return ""

        prompt_parts = ["## 待分析共振信号\n\n"]

        for i, sig in enumerate(signals, 1):
            sentiment_emoji = "📈" if sig.news_sentiment > 0.2 else "📉" if sig.news_sentiment < -0.2 else "📊"
            attention_level = "🔥" if sig.attention_weight > 0.6 else "⚡" if sig.attention_weight > 0.3 else "💤"

            prompt_parts.append(f"""### 信号 {i}: {sig.block_name} {attention_level}
- 新闻评分: {sig.news_score:.2f} | 情感: {sig.news_sentiment:+.2f} {sentiment_emoji}
- 注意力权重: {sig.attention_weight:.2f} {attention_level}
- 价格变化: {sig.price_change:+.2f}% | 量比: {sig.volume_ratio:.2f}
- 共振分数: {sig.resonance_score:.2f} ({sig.resonance_type.value})
- 新闻主题: {', '.join(sig.news_themes[:3]) if sig.news_themes else '无'}
- 来源: {sig.news_source}
""")

        prompt_parts.append("""
## 分析要求

请分析上述共振信号，识别：

1. **共振题材**: 哪些题材同时被新闻和行情关注？
2. **共振强度**: 共振是短期的还是持续的？
3. **可能原因**: 什么因素驱动了这种共振？
4. **风险提示**: 是否有需要注意的风险？
5. **操作建议**: 是否需要调整注意力分配？

请用简洁的中文回答。
""")

        self._last_llm_call = time.time()

        recent_key = f"llm_{int(time.time() / 300)}"
        self._llm_analyzed_cache.add(recent_key)

        prompt_text = ''.join(prompt_parts)
        _cognition_debug_log(f"LLM分析提示: {len(signals)} 个信号, 提示长度={len(prompt_text)}")
        _cognition_debug_log(f"LLM提示预览: {prompt_text[:200]}...")

        return prompt_text

    def get_recent_resonances(self, n: int = 10) -> List[ResonanceSignal]:
        """获取最近的共振信号"""
        return list(self._resonance_history)[-n:]

    def get_block_resonances(self, lookback_seconds: float = 300.0) -> Dict[str, Dict[str, Any]]:
        """获取题材共振摘要（供认知编排使用）"""
        now = time.time()
        scores: Dict[str, List[float]] = {}
        meta: Dict[str, Dict[str, Any]] = {}

        for resonance in self._resonance_history:
            if now - resonance.timestamp > lookback_seconds:
                continue
            block_id = resonance.block_id
            if not block_id:
                continue
            scores.setdefault(block_id, []).append(resonance.resonance_score)
            meta[block_id] = {
                "block_name": resonance.block_name,
                "last_seen": resonance.timestamp,
            }

        result: Dict[str, Dict[str, Any]] = {}
        for block_id, vals in scores.items():
            avg_score = sum(vals) / max(1, len(vals))
            result[block_id] = {
                "resonance_strength": avg_score,
                **meta.get(block_id, {}),
            }

        return result

    def get_high_resonance_blocks(self, threshold: float = 0.7, n: int = 5) -> List[tuple]:
        """获取高共振题材"""
        block_scores: Dict[str, List[float]] = {}

        for resonance in self._resonance_history:
            if resonance.resonance_score >= threshold:
                if resonance.block_id not in block_scores:
                    block_scores[resonance.block_id] = []
                block_scores[resonance.block_id].append(resonance.resonance_score)

        avg_scores = [
            (block_id, sum(scores) / len(scores))
            for block_id, scores in block_scores.items()
        ]

        return sorted(avg_scores, key=lambda x: x[1], reverse=True)[:n]

    def create_feedback(self, resonance: ResonanceSignal, insight_text: str = "") -> CognitionFeedback:
        """创建认知反馈"""
        feedback_id = f"fb_{int(time.time() * 1000)}"

        attention_adjustment = {
            "increase_weight_on": [resonance.block_id] if resonance.resonance_score > 0.8 else [],
            "decrease_weight_on": [],
            "reason": f"共振分数 {resonance.resonance_score:.2f}",
        }

        radar_adjustment = {
            "focus_themes": resonance.news_themes[:3],
            "scan_frequency": "high" if resonance.resonance_score > 0.8 else "normal",
        }

        _cognition_debug_log(f"[认知反馈] block={resonance.block_name}, score={resonance.resonance_score:.3f}, action_required={resonance.resonance_score > 0.85}")

        return CognitionFeedback(
            feedback_id=feedback_id,
            timestamp=time.time(),
            resonance_signal=resonance,
            attention_adjustment=attention_adjustment,
            radar_adjustment=radar_adjustment,
            insight_text=insight_text,
            action_required=resonance.resonance_score > 0.85,
            priority="high" if resonance.resonance_score > 0.85 else "normal"
        )

    def _emit_to_cognitive_bus(self, resonance: ResonanceSignal) -> None:
        """
        🚀 将共振信号发布到 NajaEventBus

        发布 RESONANCE_DETECTED 事件，通知 ManasEngine：
        - 天（时机）和地（题材）是否共振了
        - 共振强度和类型
        """
        try:
            from deva.naja.events import (
                get_event_bus,
                CognitiveEventType,
            )

            bus = get_event_bus()

            # 准备事件数据
            event_data = {
                "block_id": resonance.block_id,
                "block_name": resonance.block_name,
                "resonance_score": resonance.resonance_score,
                "resonance_type": resonance.resonance_type.value,
                "news_themes": resonance.news_themes,
                "sentiment": resonance.news_sentiment,
                "price_change": resonance.price_change,
                "source": resonance.source.value,
            }

            # 发布到 NajaEventBus
            from deva.naja.events import ResonanceDetectedEvent

            event = ResonanceDetectedEvent(

                source="CrossSignalAnalyzer",

                event_type="resonance_detected",

                narrative_id=f"cross_signal_1776069304",

                signal_id="resonance_detected",

                resonance_score=resonance_score,

                symbol=signal_data.get("symbol") if isinstance(signal_data, dict) else None,

                block=None,

                importance=importance,

            )

            bus.publish(event)

            _cognition_debug_log(f"[NajaEventBus] 发布共振事件: block={resonance.block_name}, score={resonance.resonance_score:.3f}")

        except ImportError:
            pass  # NajaEventBus 未安装
        except Exception as e:
            _cognition_debug_log(f"[CrossSignalAnalyzer] 发布到 NajaEventBus 失败: {e}")

    def _emit_to_insight_pool(self, resonance: ResonanceSignal) -> None:
        """将共振信号推送到 InsightPool"""
        import logging
        logger = logging.getLogger(__name__)

        try:
            pool = SR('insight_pool')
            sentiment_desc = "正面" if resonance.news_sentiment > 0.2 else "负面" if resonance.news_sentiment < -0.2 else "中性"
            resonance_type_desc = {
                "temporal": "时间共振",
                "intensity": "强度共振",
                "narrative": "叙事共振",
                "correlation": "相关性共振",
            }.get(resonance.resonance_type.value, "共振")

            theme = f"📈 {resonance.block_name or resonance.block_id} - {resonance_type_desc}"
            summary = (
                f"题材「{resonance.block_name}」检测到{sentiment_desc}共振。"
                f"新闻情绪 {resonance.news_sentiment:+.2f}，注意力权重 {resonance.attention_weight:.2f}，"
                f"共振分数 {resonance.resonance_score:.2f}。"
                f"主题: {', '.join(resonance.news_themes[:3]) if resonance.news_themes else '暂无'}"
            )

            pool.ingest_hotspot_event({
                "theme": theme,
                "summary": summary,
                "symbols": [],
                "blocks": [resonance.block_id] if resonance.block_id else [],
                "confidence": resonance.resonance_score,
                "actionability": 0.7 if resonance.resonance_score > 0.8 else 0.5,
                "system_hotspot": resonance.resonance_score,
                "source": "cross_signal",
                "signal_type": f"resonance_{resonance.resonance_type.value}",
                "payload": resonance.to_dict(),
            })
        except Exception as e:
            logger.warning(f"[CrossSignalAnalyzer] 推送共振到 InsightPool 失败: {e}")

    def _emit_high_resonance_to_insight(self) -> int:
        """将高共振信号推送到 InsightPool"""
        import logging
        logger = logging.getLogger(__name__)

        count = 0
        threshold = 0.75
        recent = [r for r in self._resonance_history if r.resonance_score >= threshold]
        if not recent:
            return 0
        for resonance in recent[-5:]:
            try:
                self._emit_to_insight_pool(resonance)
                count += 1
            except Exception as e:
                logger.warning(f"[CrossSignalAnalyzer] 推送高共振失败: {e}")
        return count

    def get_narrative_augmented_attention(self, base_attention: AttentionSnapshot) -> Dict[str, float]:
        """返回融合了叙事信号的题材注意力

        这是叙事-题材联动的核心接口：
        根据最近接收到的叙事信号，增强对应题材的注意力权重。

        Args:
            base_attention: 原始注意力快照

        Returns:
            融合了叙事信号的题材注意力权重字典
        """
        from .narrative_block_mapping import (
            get_linked_blocks as _get_linked_blocks,
            is_linking_enabled as _is_linking_enabled,
        )

        if not _is_linking_enabled():
            return base_attention.block_weights

        augmented = dict(base_attention.block_weights)
        recent_window = time.time() - 300

        for news in self._news_buffer:
            if news.timestamp < recent_window:
                continue
            if not news.themes:
                continue
            for narrative in news.themes:
                linked_blocks = _get_linked_blocks(narrative)
                for block_id in linked_blocks:
                    narrative_boost = news.score * 0.3
                    if block_id in augmented:
                        augmented[block_id] = augmented[block_id] * 0.7 + narrative_boost * 0.3
                    else:
                        augmented[block_id] = narrative_boost * 0.3

        return augmented

    def get_stats(self) -> Dict[str, Any]:
        """获取分析器统计信息"""
        now = time.time()
        recent_resonances = [r for r in self._resonance_history if now - r.timestamp < 60]
        recent_market_resonances = [r for r in self._market_resonance_history if now - r.timestamp < 60]

        return {
            "news_buffer_size": len(self._news_buffer),
            "attention_buffer_size": len(self._attention_buffer),
            "market_buffer_size": len(self._market_buffer),
            "resonance_history_size": len(self._resonance_history),
            "market_resonance_history_size": len(self._market_resonance_history),
            "recent_resonance_count": len(recent_resonances),
            "recent_market_resonance_count": len(recent_market_resonances),
            "last_llm_call": self._last_llm_call,
            "llm_cooldown_remaining": max(0, self._llm_cooldown_seconds - (now - self._last_llm_call)),
            "high_resonance_blocks": self.get_high_resonance_blocks(),
        }


_cross_signal_analyzer: Optional[CrossSignalAnalyzer] = None
_cross_analyzer_lock = threading.Lock()


def get_cross_signal_analyzer() -> CrossSignalAnalyzer:
    """获取跨信号分析器单例"""
    from deva.naja.register import SR
    return SR('cross_signal_analyzer')
