"""NarrativeTracker - 新闻叙事追踪器

═══════════════════════════════════════════════════════════════════════════
                              架 构 定 位
═══════════════════════════════════════════════════════════════════════════

【外部-新闻】 NarrativeTracker 是外部世界的新闻代理
    - 它追踪的是外部新闻/事件中的叙事信号
    - 它本身没有立场，只是记录"外面发生了什么"
    - get_world_narrative() = 外部叙事，给融合层做参考

【我们-Dynamics】 NarrativeTracker 同时承担主动价值发现职责
    - 基于 DYNAMICS_KEYWORDS 检测我们认定的核心价值信号
    - 这是我们自己的价值判断体系，供需动态
    - get_value_market_summary() = 我们主动发现的价值信号

═══════════════════════════════════════════════════════════════════════════
                              两 层 数据
═══════════════════════════════════════════════════════════════════════════

外部层（新闻/事件）:
    get_world_narrative() → world_narrative{} → AttentionFusion.beta通道
    代表：纯粹外部世界正在讨论什么、发生什么

我们层（供需动态-Dynamics）:
    get_value_market_summary() → value_score{} → AttentionFusion.epsilon通道
    代表：我们自己认定什么是重要的、值得的

═══════════════════════════════════════════════════════════════════════════
                              核 心 职 责
═══════════════════════════════════════════════════════════════════════════

1. 【外部-新闻代理】追踪外部新闻/事件中的叙事信号
2. 【我们-Dynamics发现】基于价值关键词检测主动价值信号
3. 【问题-机会-解决者】识别供需失衡并推导投资机会
4. 【认知升级】通过 blind_spot 探究被动扩展认知边界

🔄 数据流：
    文本信号 → TextSignalBus → NarrativeTracker（订阅）
         ↓ 处理
    发布 NARRATIVE_UPDATE → NajaEventBus → ManasEngine

💡 与 TimingNarrative 的区别：
    - NarrativeTracker（地）：关注「空间」—— 炒什么题材/主题
    - TimingNarrative（天）：关注「时间」—— 现在是不是时机

关键词已迁移到 keyword_registry.py，本文件从那里导入以保持向后兼容。
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

log = logging.getLogger(__name__)

# 从统一关键词注册表导入
from deva.naja.cognition.semantic.keyword_registry import (
    DEFAULT_NARRATIVE_KEYWORDS,
    DYNAMICS_KEYWORDS,
    SENTIMENT_KEYWORDS,
    SUPPLY_DEMAND_KEYWORDS,
)

from deva.naja.events import NarrativeStateEvent, publish_event


OPPORTUNITY_TYPES: Dict[str, Dict[str, Any]] = {
    "token供给不足": {
        "opportunity": "扩产机会",
        "beneficiaries": ["台积电", "日月光", "长电科技", "中芯国际"],
        "description": "算力供给不足 → 芯片封装扩产 → 设备商/材料商受益",
        "signal": "产能扩张新闻 + 设备订单增加",
    },
    "token需求爆发": {
        "opportunity": "全产业链机会",
        "beneficiaries": ["英伟达", "AMD", "微软", "谷歌", "OpenAI"],
        "description": "AI需求爆发 → 整个算力产业链受益",
        "signal": "需求新闻 + 涨价 + 排单增加",
    },
    "电力供给不足": {
        "opportunity": "能源基础设施机会",
        "beneficiaries": ["核电运营商", "电网设备商", "电力设备"],
        "description": "电力供给不足 → 能源基础设施扩建 → 电力设备商受益",
        "signal": "电力短缺新闻 + 能源项目批准",
    },
    "电力需求爆发": {
        "opportunity": "绿色能源机会",
        "beneficiaries": ["太阳能", "风电", "核电", "储能"],
        "description": "AI用电需求爆发 → 清洁能源建设 → 能源运营商受益",
        "signal": "能源需求新闻 + 绿色能源项目",
    },
    "芯片供给不足": {
        "opportunity": "国产替代机会",
        "beneficiaries": ["华为昇腾", "寒武纪", "燧原科技", "中芯国际"],
        "description": "芯片被卡脖子 → 国产替代加速 → 突破者受益",
        "signal": "技术突破新闻 + 国产替代加速",
    },
    "芯片需求爆发": {
        "opportunity": "芯片制造机会",
        "beneficiaries": ["台积电", "三星", "中芯国际", "华虹半导体"],
        "description": "芯片需求爆发 → 芯片制造商业绩爆发",
        "signal": "芯片涨价 + 产能满载 + 订单翻倍",
    },
    "技术瓶颈突破": {
        "opportunity": "效率提升机会",
        "beneficiaries": ["效率提升技术商", "新架构开发者"],
        "description": "技术突破 → 效率大幅提升 → 先用新技术的人受益",
        "signal": "技术突破新闻 + 成本下降 + 效率提升",
    },
}


RESOLVERS: Dict[str, Dict[str, Any]] = {
    "AI算力国产化": {
        "problem": "AI芯片被美国制裁",
        "resolvers": ["华为昇腾", "寒武纪", "燧原科技", "海光信息"],
        "progress": {"华为昇腾": "量产级", "寒武纪": "量产级", "燧原科技": "量产级"},
        "opportunity": "国产AI芯片替代",
    },
    "先进封装": {
        "problem": "CoWoS封装产能不足",
        "resolvers": ["日月光", "长电科技", "通富微电", "华天科技"],
        "progress": {"日月光": "扩产中", "长电科技": "扩产中"},
        "opportunity": "封装产能扩张",
    },
    "先进制程": {
        "problem": "先进制程被限制",
        "resolvers": ["中芯国际", "华虹半导体"],
        "progress": {"中芯国际": "14nm量产/扩产中", "华虹半导体": "成熟制程"},
        "opportunity": "成熟制程扩产 + 国产替代",
    },
    "AI电力": {
        "problem": "数据中心电力不足",
        "resolvers": ["核电运营商", "电网设备商", "储能公司"],
        "progress": {"核电": "项目审批加速", "电网": "升级改造中"},
        "opportunity": "能源基础设施建设",
    },
    "算力效率": {
        "problem": "算力成本太高",
        "resolvers": ["效率芯片商", "推理优化公司", "模型压缩公司"],
        "progress": {"各公司": "研发中"},
        "opportunity": "推理效率提升",
    },
}


NARRATIVE_PERSISTENCE_TABLE = "naja_narrative_tracker_state"
MAX_PERSIST_STATES = 10
MAX_PERSIST_HITS = 50


@dataclass
class ValueSignal:
    """
    供需动态信号 - 独立的主动价值发现

    与 NarrativeState 不同，ValueSignal 代表我们主动发现的价值信号，
    不是外部叙事，而是我们对事件价值的判断。

    字段说明：
        - signal_type: 信号类型（token供需、电力供需、技术瓶颈、效率突破、AI落地）
        - keywords: 命中的关键词
        - severity: 严重程度（轻微/中等/严重）
        - source_event: 来源事件摘要
    """
    timestamp: float
    signal_type: str
    keywords: List[str]
    severity: str = "轻微"
    source_event: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "signal_type": self.signal_type,
            "keywords": self.keywords,
            "severity": self.severity,
            "source_event": self.source_event,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValueSignal":
        return cls(
            timestamp=data.get("timestamp", 0.0),
            signal_type=data.get("signal_type", ""),
            keywords=data.get("keywords", []),
            severity=data.get("severity", "轻微"),
            source_event=data.get("source_event", ""),
        )


@dataclass
class NarrativeState:
    name: str
    stage: str = "萌芽"
    attention_score: float = 0.0
    total_count: int = 0
    recent_count: int = 0
    trend: float = 0.0
    last_updated: float = 0.0
    last_stage_change: float = 0.0
    hits: Deque[Tuple[float, float, List[str]]] = field(default_factory=deque)
    last_keywords: List[str] = field(default_factory=list)
    last_emit: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "name": self.name,
            "stage": self.stage,
            "attention_score": self.attention_score,
            "total_count": self.total_count,
            "recent_count": self.recent_count,
            "trend": self.trend,
            "last_updated": self.last_updated,
            "last_stage_change": self.last_stage_change,
            "hits": list(self.hits),
            "last_keywords": self.last_keywords,
            "last_emit": self.last_emit,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NarrativeState":
        """从字典反序列化"""
        state = cls(name=data["name"])
        state.stage = data.get("stage", "萌芽")
        state.attention_score = data.get("attention_score", 0.0)
        state.total_count = data.get("total_count", 0)
        state.recent_count = data.get("recent_count", 0)
        state.trend = data.get("trend", 0.0)
        state.last_updated = data.get("last_updated", 0.0)
        state.last_stage_change = data.get("last_stage_change", 0.0)
        state.hits = Deque(data.get("hits", []))
        state.last_keywords = data.get("last_keywords", [])
        state.last_emit = data.get("last_emit", {})
        return state


class NarrativeTracker:
    """Track narrative lifecycle, attention, and relationship graph.

    🚀 架构定位：地（NarrativeTracker）
    - 只追踪 ManasEngine 关心的主题
    - 不再追踪"市场所有主题"

    【双通道架构】
    - WorldNarrativeTracker（外部叙事）: _states 存储，追踪外部热点
    - SupplyDemandNarrativeTracker（供需叙事）: _value_signals 存储，追踪供需动态

    【输出接口】
    - get_world_narrative() → 外部热点（AttentionFusion β×market_attention）
    - get_value_market_summary() → 供需动态（AttentionFusion ε×value_score）
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.enabled = bool(cfg.get("narrative_enabled", True))

        # 🚀 从 ManasEngine 获取关注的主题，而非预设关键词
        self._focus_themes = self._get_initial_focus_themes()
        self._keywords = self._themes_to_keywords(self._focus_themes)

        self._recent_window = float(cfg.get("narrative_recent_window_seconds", 6 * 3600))
        self._prev_window = float(cfg.get("narrative_prev_window_seconds", 6 * 3600))
        self._history_window = float(cfg.get("narrative_history_window_seconds", 72 * 3600))
        self._graph_window = float(cfg.get("narrative_graph_window_seconds", 6 * 3600))
        self._count_scale = float(cfg.get("narrative_count_scale", 8.0))
        self._peak_score = float(cfg.get("narrative_peak_score", 0.8))
        self._spread_score = float(cfg.get("narrative_spread_score", 0.55))
        self._fade_score = float(cfg.get("narrative_fade_score", 0.25))
        self._peak_count = int(cfg.get("narrative_peak_count", 8))
        self._spread_count = int(cfg.get("narrative_spread_count", 4))
        self._fade_count = int(cfg.get("narrative_fade_count", 1))
        self._trend_threshold = float(cfg.get("narrative_trend_threshold", 0.5))
        self._spike_threshold = float(cfg.get("narrative_attention_spike_threshold", 0.75))
        self._spike_delta = float(cfg.get("narrative_spike_delta", 0.15))
        self._emit_cooldown = float(cfg.get("narrative_emit_cooldown_seconds", 120))
        self._graph_same_weight = float(cfg.get("narrative_graph_same_event_weight", 1.0))
        self._graph_temporal_weight = float(cfg.get("narrative_graph_temporal_weight", 0.3))

        self._states: Dict[str, NarrativeState] = {}
        self._graph_edges: Dict[Tuple[str, str], float] = defaultdict(float)
        self._recent_hits: Deque[Tuple[float, List[str]]] = deque()

        # 🚀 供需动态信号独立存储（与外部叙事状态分离）
        self._value_signals: List[ValueSignal] = []
        self._value_signal_index: Dict[str, List[int]] = {}  # signal_type → indices

        # 上次发布的叙事状态（用于变更检测）
        self._last_published_narratives: List[str] = []
        self._last_published_strength: float = 0.0
        self._last_published_risk: float = 0.0

        self._load_state()

        self._subscribe_to_text_events()
        self._subscribe_to_manas_state()

    def _get_initial_focus_themes(self) -> List[Dict[str, Any]]:
        """
        🚀 初始化时获取关注的主题列表

        仅在 __init__ 时调用一次。后续通过订阅 MANAS_STATE_CHANGED 事件更新。
        """
        try:
            from deva.naja.attention.os.attention_os import get_attention_os
            manas = get_attention_os().kernel.get_manas_engine()
            if manas is None:
                raise RuntimeError("ManasEngine 未初始化")
            themes = manas.get_focus_themes()
            if themes:
                import logging
                logging.getLogger(__name__).info(
                    f"[NarrativeTracker] 初始化时从 Manas 获取到 {len(themes)} 个关注主题"
                )
                return themes
        except ImportError:
            pass
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[NarrativeTracker] 从 Manas 获取主题失败: {e}")

        import logging
        logging.getLogger(__name__).warning(
            "[NarrativeTracker] 无法从 Manas 获取主题，使用默认关键词"
        )
        return [
            {"id": theme_id, "name": theme_id, "keywords": keywords}
            for theme_id, keywords in DEFAULT_NARRATIVE_KEYWORDS.items()
        ]

    def _subscribe_to_manas_state(self):
        """
        🚀 订阅 MANAS_STATE_CHANGED 事件，解耦对 Attention 的直接依赖

        ManasEngine 状态变化时会发布 MANAS_STATE_CHANGED 事件，
        我们收到后更新 _focus_themes，实现单向数据流。
        """
        try:
            from deva.naja.events import get_event_bus, CognitiveEventType

            bus = get_event_bus()
            bus.subscribe(
                "NarrativeTracker",
                self._on_manas_state_changed,
                event_types=[CognitiveEventType.MANAS_STATE_CHANGED],
            )
            import logging
            logging.getLogger(__name__).debug("[NarrativeTracker] 已订阅 MANAS_STATE_CHANGED")
        except ImportError:
            pass
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[NarrativeTracker] 订阅 MANAS_STATE_CHANGED 失败: {e}")

    def _on_manas_state_changed(self, event):
        """
        🚀 处理 MANAS_STATE_CHANGED 事件，更新关注主题

        这是事件驱动的核心：Manas 状态变化 → 发布事件 → Cognition 更新
        """
        try:
            data = getattr(event, 'data', {}) or {}
            new_themes = data.get("focus_themes", [])
            if new_themes and new_themes != self._focus_themes:
                import logging
                logging.getLogger(__name__).info(
                    f"[NarrativeTracker] 收到 Manas 状态更新: {len(new_themes)} 个主题"
                )
                self._focus_themes = new_themes
                self._keywords = self._themes_to_keywords(self._focus_themes)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[NarrativeTracker] 处理 MANAS_STATE_CHANGED 失败: {e}")

    def _themes_to_keywords(self, themes: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        🚀 把主题列表转换为关键词字典

        兼容旧接口：把 [{"id": "AI", "keywords": [...]}] 转成 {"AI": [...], ...}
        """
        result = {}
        for theme in themes:
            theme_id = theme.get("id", theme.get("name", "unknown"))
            keywords = theme.get("keywords", [])
            if isinstance(keywords, list):
                result[theme_id] = keywords
        return result

    def _subscribe_to_text_events(self):
        """订阅 TextFocusedEvent"""
        try:
            from deva.naja.events import get_event_bus

            event_bus = get_event_bus()
            event_bus.subscribe(
                'TextFocusedEvent',
                self._on_text_focused,
                priority=7
            )
            import logging
            logging.getLogger(__name__).debug("NarrativeTracker 已订阅 TextFocusedEvent")
        except ImportError:
            pass

    def _on_text_focused(self, event):
        """处理 TextFocusedEvent，进行叙事追踪"""
        try:
            if event.routing_level != "deep":
                return

            keywords = list(event.keywords or [])
            topics = list(event.topics or [])
            if getattr(event, "narrative_tags", None):
                topics.extend(event.narrative_tags)
            if getattr(event, "matched_focus_topics", None):
                topics.extend(event.matched_focus_topics)
            topics = list(dict.fromkeys(topics))

            signal = {
                "source": f"text_focused:{event.source}",
                "content": event.summary or event.title or event.text,
                "title": event.title,
                "importance_score": event.importance_score,
                "keywords": keywords,
                "topics": topics,
                "sentiment": event.sentiment,
                "stock_codes": event.stock_codes,
            }
            self.ingest_news_signal(signal)
        except Exception as e:
            log.debug(f"[NarrativeTracker] 处理 TextFocusedEvent 失败: {e}")

    def _publish_cognitive_update(self, event, signal):
        """发布认知事件到 NajaEventBus"""
        try:
            from deva.naja.events import (
                get_event_bus,
                CognitiveEventType,
            )

            bus = get_event_bus()

            narratives = list(signal.get('topics', []) if isinstance(signal, dict) else [])
            narratives.extend(list(signal.get('keywords', []) if isinstance(signal, dict) else []))

            importance = signal.get('importance_score', 0.5) if isinstance(signal, dict) else 0.5

            from deva.naja.events import create_narrative_update


            event = create_narrative_update(


                narrative_id="narratives...",


                narrative_type="block",


                summary="外部叙事更新",


                source="NarrativeTracker",


                confidence=0.5,


                symbols=signal.get("stock_codes", []) if isinstance(signal, dict) else [],


                strength_change=0.0,


                market="CN",


                importance=importance


            )


            bus.publish(event)
        except ImportError:
            pass
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"NarrativeTracker 发布认知事件失败: {e}")

    def _load_state(self) -> bool:
        """从数据库加载状态"""
        try:
            from deva import NB
            nb = NB(NARRATIVE_PERSISTENCE_TABLE)
            data = nb.get("narrative_states")
            if not data or not isinstance(data, dict):
                return False

            now_ts = time.time()
            loaded_count = 0

            for name, state_data in data.items():
                if loaded_count >= MAX_PERSIST_STATES:
                    break
                try:
                    state = NarrativeState.from_dict(state_data)
                    if now_ts - state.last_updated < 72 * 3600:
                        self._states[name] = state
                        loaded_count += 1
                except Exception:
                    continue

            if loaded_count > 0:
                log.info(f"[NarrativeTracker] 从持久化恢复 {loaded_count} 个叙事状态")
            return loaded_count > 0
        except Exception:
            return False

    def save_state(self) -> bool:
        """保存状态到数据库"""
        try:
            from deva import NB
            nb = NB(NARRATIVE_PERSISTENCE_TABLE)

            sorted_states = sorted(
                self._states.values(),
                key=lambda s: s.attention_score,
                reverse=True
            )

            persist_data = {}
            for state in sorted_states[:MAX_PERSIST_STATES]:
                state_dict = state.to_dict()
                if len(state_dict.get("hits", [])) > MAX_PERSIST_HITS:
                    state_dict["hits"] = state_dict["hits"][-MAX_PERSIST_HITS:]
                persist_data[state.name] = state_dict

            nb["narrative_states"] = persist_data
            nb["saved_at"] = time.time()
            return True
        except Exception:
            return False

    def detect_narratives(self, event: Any) -> Dict[str, List[str]]:
        if not self.enabled:
            return {}

        texts = self._collect_texts(event)
        if not texts:
            return {}

        combined = " ".join(t for t in texts if t)
        combined_lower = combined.lower()
        matches: Dict[str, List[str]] = {}

        for narrative, keywords in self._keywords.items():
            hit_keywords: List[str] = []
            for keyword in keywords:
                if self._keyword_in_text(keyword, combined, combined_lower):
                    hit_keywords.append(keyword)
            if hit_keywords:
                matches[narrative] = hit_keywords

        return matches

    def ingest_event(self, event: Any) -> List[Dict[str, Any]]:
        """
        处理事件入口

        双重身份处理：
        1. 外部叙事检测 - 更新 _states（现有逻辑）
        2. 供需动态检测 - 更新 _value_signals（新增逻辑）
        """
        if not self.enabled:
            return []

        now_ts = self._get_timestamp(event)
        attention = self._clamp_score(getattr(event, "attention_score", 0.0))
        results: List[Dict[str, Any]] = []

        external_results = self._process_external_narratives(event, now_ts, attention)
        results.extend(external_results)

        value_results = self._process_value_signals(event, now_ts)
        results.extend(value_results)

        self.save_state()
        return results

    def _process_external_narratives(
        self, event: Any, now_ts: float, attention: float
    ) -> List[Dict[str, Any]]:
        """
        🚀 处理外部叙事 (WorldNarrativeTracker)

        从事件中检测外部叙事主题，更新 _states
        """
        matches = self.detect_narratives(event)
        if not matches:
            return []

        results: List[Dict[str, Any]] = []
        narratives = list(matches.keys())
        self._update_graph(now_ts, narratives)

        for narrative, keywords in matches.items():
            state = self._states.get(narrative)
            if state is None:
                state = NarrativeState(name=narrative, last_stage_change=now_ts)
                self._states[narrative] = state

            state.hits.append((now_ts, attention, keywords))
            state.total_count += 1
            state.last_keywords = keywords
            state.last_updated = now_ts

            self._prune_hits(state, now_ts)
            metrics = self._compute_metrics(state, now_ts)
            new_stage = self._determine_stage(metrics)
            new_score = metrics["attention_score"]

            stage_changed = new_stage != state.stage
            spike = new_score >= self._spike_threshold and (new_score - state.attention_score) >= self._spike_delta

            state.recent_count = metrics["recent_count"]
            state.trend = metrics["trend"]
            state.attention_score = new_score

            if stage_changed:
                state.stage = new_stage
                state.last_stage_change = now_ts
                event_payload = self._build_event_payload(
                    narrative=narrative,
                    event_type="narrative_stage_change",
                    stage=new_stage,
                    metrics=metrics,
                    keywords=keywords,
                )
                if self._should_emit(state, "stage", now_ts):
                    results.append(event_payload)

            if spike:
                event_payload = self._build_event_payload(
                    narrative=narrative,
                    event_type="narrative_attention_spike",
                    stage=new_stage,
                    metrics=metrics,
                    keywords=keywords,
                )
                if self._should_emit(state, "spike", now_ts):
                    results.append(event_payload)

        # 发布NarrativeStateEvent事件
        self._publish_narrative_state_event(now_ts)
        
        return results

    def _publish_narrative_state_event(self, timestamp: float):
        """发布叙事状态事件（仅在状态变化时发布）"""
        try:
            # 收集当前叙事状态
            current_narratives = []
            narrative_strength = 0.0
            narrative_risk = 0.0
            sentiment_score = 0.5
            
            # 计算叙事强度和风险
            active_narratives = [s for s in self._states.values() if s.attention_score > 0.3]
            if active_narratives:
                current_narratives = [s.name for s in active_narratives]
                narrative_strength = sum(s.attention_score for s in active_narratives) / len(active_narratives)
                # 计算风险：叙事数量过多或强度过高都增加风险
                narrative_risk = min(1.0, (len(active_narratives) / 10) + (narrative_strength - 0.5))
                
                # 简单的情绪评分计算
                positive_keywords = set()
                negative_keywords = set()
                for state in active_narratives:
                    positive_keywords.update(k for k in state.last_keywords if any(p in k for p in ['增长', '上升', '利好', '突破']))
                    negative_keywords.update(k for k in state.last_keywords if any(n in k for n in ['下降', '风险', '利空', '危机']))
                
                if positive_keywords or negative_keywords:
                    sentiment_score = len(positive_keywords) / (len(positive_keywords) + len(negative_keywords))
            
            # 变更检测：只有状态真的变化了才发布
            narratives_changed = set(current_narratives) != set(self._last_published_narratives)
            strength_changed = abs(narrative_strength - self._last_published_strength) > 0.01
            risk_changed = abs(narrative_risk - self._last_published_risk) > 0.01
            
            if not (narratives_changed or strength_changed or risk_changed):
                return
            
            # 更新上次发布状态
            self._last_published_narratives = current_narratives
            self._last_published_strength = narrative_strength
            self._last_published_risk = narrative_risk
            
            # 创建并发布事件
            event = NarrativeStateEvent(
                current_narratives=current_narratives,
                narrative_strength=narrative_strength,
                narrative_risk=narrative_risk,
                sentiment_score=sentiment_score,
                timestamp=timestamp,
                source="narrative_tracker",
                market="CN"
            )
            
            publish_event(event)
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"发布NarrativeStateEvent失败: {e}")

    def _process_value_signals(self, event: Any, now_ts: float) -> List[Dict[str, Any]]:
        """
        🚀 处理供需动态信号 (SupplyDemandNarrativeTracker)

        直接从事件中检测供需动态信号，存入独立的 _value_signals
        不依赖外部叙事状态 _states
        """
        texts = self._collect_texts(event)
        if not texts:
            return []

        combined = " ".join(t for t in texts if t)
        combined_lower = combined.lower()

        results: List[Dict[str, Any]] = []

        for signal_type, keywords in DYNAMICS_KEYWORDS.items():
            hit_keywords: List[str] = []
            for keyword in keywords:
                if self._keyword_in_text(keyword, combined, combined_lower):
                    hit_keywords.append(keyword)

            if hit_keywords:
                severity = self._assess_signal_severity(hit_keywords)
                source_event = combined[:200] if len(combined) > 200 else combined

                signal = ValueSignal(
                    timestamp=now_ts,
                    signal_type=signal_type,
                    keywords=hit_keywords,
                    severity=severity,
                    source_event=source_event,
                )
                self._value_signals.append(signal)

                if signal_type not in self._value_signal_index:
                    self._value_signal_index[signal_type] = []
                self._value_signal_index[signal_type].append(len(self._value_signals) - 1)

                results.append({
                    "type": "value_signal",
                    "signal_type": signal_type,
                    "keywords": hit_keywords,
                    "severity": severity,
                    "timestamp": now_ts,
                })

        return results

    def _assess_signal_severity(self, hit_keywords: List[str]) -> str:
        """评估信号严重程度"""
        severity_indicators = {
            "严重": ["严重", "极度", "危机", "崩溃", "枯竭", "暴涨", "激增"],
            "中等": ["短缺", "紧张", "不足", "告急"],
        }

        keyword_str = " ".join(hit_keywords).lower()
        for level, indicators in severity_indicators.items():
            if any(ind in keyword_str for ind in indicators):
                return level

        if len(hit_keywords) >= 3:
            return "中等"
        return "轻微"

    def detect_value_signals(self, event: Any) -> Dict[str, List[str]]:
        """检测价值信号（Dynamics）- 真正的供需失衡/效率提升信号

        【Dynamics-供需动态】我们自己的价值判断体系
        - 基于 DYNAMICS_KEYWORDS 命中情况
        - 代表我们认定的重要变化（供需失衡、技术突破等）

        Returns:
            Dict[str, List[str]] - 按价值类别分类的命中关键词
        """
        if not self.enabled:
            return {}

        texts = self._collect_texts(event)
        if not texts:
            return {}

        combined = " ".join(t for t in texts if t)
        combined_lower = combined.lower()
        matches: Dict[str, List[str]] = {}

        for signal_type, keywords in DYNAMICS_KEYWORDS.items():
            hit_keywords: List[str] = []
            for keyword in keywords:
                if self._keyword_in_text(keyword, combined, combined_lower):
                    hit_keywords.append(keyword)
            if hit_keywords:
                matches[signal_type] = hit_keywords

        return matches

    def get_summary(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not self._states:
            return []
        sorted_states = sorted(self._states.values(), key=lambda s: s.attention_score, reverse=True)
        summary = []
        for state in sorted_states[:limit]:
            summary.append({
                "narrative": state.name,
                "stage": state.stage,
                "attention_score": round(state.attention_score, 3),
                "recent_count": state.recent_count,
                "trend": round(state.trend, 3),
                "last_updated": state.last_updated,
                "keywords": state.last_keywords,
            })
        return summary

    def get_graph(self, min_weight: float = 0.2) -> Dict[str, Any]:
        nodes = []
        for state in self._states.values():
            nodes.append({
                "id": state.name,
                "stage": state.stage,
                "attention_score": round(state.attention_score, 3),
                "recent_count": state.recent_count,
            })

        edges = []
        for (left, right), weight in self._graph_edges.items():
            if weight < min_weight:
                continue
            edges.append({
                "source": left,
                "target": right,
                "weight": round(weight, 3),
            })

        return {"nodes": nodes, "edges": edges}

    def get_linked_blocks(self, narrative: str) -> List[str]:
        """获取叙事主题关联的题材列表

        这是叙事-题材联动的关键接口：
        NarrativeTracker 识别叙事主题后，通过此方法获取关联的 block_id，
        从而实现"舆情 → 题材轮动"的联动。

        Args:
            narrative: 叙事主题名称，如 "AI"、"芯片"、"新能源"

        Returns:
            关联的 block_id 列表
        """
        from .block_mapping import get_linked_blocks as _get_linked_blocks
        return _get_linked_blocks(narrative)

    def get_world_narrative(self) -> Dict[str, float]:
        """
        【外部-新闻】获取外部公共叙事热点（供AttentionFusion使用）

        Layer 0: 外部世界的数据出口
        - 纯粹追踪外部新闻/事件中的叙事
        - 无我们的立场，代表"外面发生了什么"
        - 输入到 AttentionFusion.beta×market_attention 通道

        Returns:
            {narrative: heat_score} 外部热点的叙事及其热度
        """
        world_narrative: Dict[str, float] = {}
        for state in self._states.values():
            if state.attention_score > 0:
                world_narrative[state.name] = state.attention_score
        if world_narrative and max(world_narrative.values()) > 0:
            max_score = max(world_narrative.values())
            world_narrative = {k: v / max_score for k, v in world_narrative.items()}
        return world_narrative

    def get_narrative_with_blocks(self) -> List[Dict[str, Any]]:
        """获取所有叙事主题及其关联题材

        Returns:
            包含 narrative 和 linked_blocks 的字典列表
        """
        from .block_mapping import get_linked_blocks as _get_linked_blocks

        result = []
        for state in self._states.values():
            result.append({
                "narrative": state.name,
                "stage": state.stage,
                "attention_score": round(state.attention_score, 3),
                "linked_blocks": _get_linked_blocks(state.name),
            })
        return result

    def get_liquidity_structure(self) -> Dict[str, Any]:
        """获取美林时钟四象限流动性结构

        Returns:
            包含四象限状态的字典，以及流动性结论
        """
        liquidity_quadrants = {
            "股票市场": {"icon": "📈", "color": "#4ade80", "desc": "资金风险偏好"},
            "债券市场": {"icon": "📊", "color": "#60a5fa", "desc": "资金避险"},
            "大宗商品": {"icon": "🛢️", "color": "#f97316", "desc": "通胀预期"},
            "现金与货币": {"icon": "💵", "color": "#a855f7", "desc": "资金观望"},
        }

        related_narratives = {
            "贵金属": {"quadrant": "大宗商品", "icon": "🥇"},
            "全球宏观": {"quadrant": "股票市场", "icon": "🌍"},
            "外汇与美元": {"quadrant": "现金与货币", "icon": "💱"},
            "流动性紧张": {"quadrant": "现金与货币", "icon": "⚠️"},
        }

        quadrants = {}
        for name, info in liquidity_quadrants.items():
            state = self._states.get(name)
            if state:
                quadrants[name] = {
                    "stage": state.stage,
                    "attention_score": round(state.attention_score, 3),
                    "recent_count": state.recent_count,
                    "trend": round(state.trend, 3),
                    "icon": info["icon"],
                    "color": info["color"],
                    "desc": info["desc"],
                }
            else:
                quadrants[name] = {
                    "stage": "无数据",
                    "attention_score": 0,
                    "recent_count": 0,
                    "trend": 0,
                    "icon": info["icon"],
                    "color": info["color"],
                    "desc": info["desc"],
                }

        related = {}
        for nar_name, nar_info in related_narratives.items():
            state = self._states.get(nar_name)
            if state:
                related[nar_name] = {
                    "stage": state.stage,
                    "attention_score": round(state.attention_score, 3),
                    "quadrant": nar_info["quadrant"],
                    "icon": nar_info["icon"],
                }

        active_quadrants = [name for name, data in quadrants.items() if data["stage"] in ("高潮", "扩散")]
        active_related_quadrants = list(set([nar_info["quadrant"] for nar_info in related.values()]))

        conclusion_parts = []
        if active_quadrants:
            conclusion_parts.append(f"资金偏好: {', '.join(active_quadrants)}")
        if active_related_quadrants:
            quadrant_short = {"大宗商品": "商品", "股票市场": "股市", "现金与货币": "货币"}
            short_names = [quadrant_short.get(q, q) for q in active_related_quadrants]
            conclusion_parts.append(f"宏观信号: {', '.join(short_names)}")

        conclusion = " | ".join(conclusion_parts) if conclusion_parts else "象限数据收集中..."

        # ========== 整合美林时钟周期判断 ==========
        try:
            from deva.naja.cognition.merrill_clock import get_merrill_clock_engine
            clock_engine = get_merrill_clock_engine()
            clock_signal = clock_engine.get_current_signal()
            
            if clock_signal:
                clock_phase = clock_signal.phase.value
                clock_confidence = clock_signal.confidence
                asset_ranking = clock_signal.asset_ranking
                clock_reason = clock_signal.reason
                
                phase_best_asset = {
                    "复苏": "股票",
                    "过热": "商品",
                    "滞胀": "现金",
                    "衰退": "债券",
                }
                best_asset = phase_best_asset.get(clock_phase, "")
                
                long_term = f"周期：{clock_phase}({clock_confidence:.0%})→{best_asset}最佳"
            else:
                long_term = "周期数据收集中..."
                clock_phase = None
                asset_ranking = []
        except Exception as e:
            long_term = "周期判断暂不可用"
            clock_phase = None
            asset_ranking = []

        final_conclusion = f"{long_term} | {conclusion}"

        return {
            "quadrants": quadrants,
            "related": related,
            "clock_phase": clock_phase,
            "asset_ranking": asset_ranking,
            "short_term": conclusion,
            "long_term": long_term,
            "conclusion": final_conclusion,
            "timestamp": time.time(),
        }

    def detect_value_signals(self, event: Any) -> Dict[str, List[str]]:
        """检测价值信号（Dynamics）- 真正的供需失衡/效率提升信号

        【Dynamics-供需动态】我们自己的价值判断体系
        - 基于 DYNAMICS_KEYWORDS 命中情况
        - 代表我们认定的重要变化（供需失衡、技术突破等）

        Returns:
            Dict[str, List[str]] - 按价值类别分类的命中关键词
        """
        if not self.enabled:
            return {}

        texts = self._collect_texts(event)
        if not texts:
            return {}

        combined = " ".join(t for t in texts if t)
        combined_lower = combined.lower()
        matches: Dict[str, List[str]] = {}

        for signal_type, keywords in DYNAMICS_KEYWORDS.items():
            hit_keywords: List[str] = []
            for keyword in keywords:
                if self._keyword_in_text(keyword, combined, combined_lower):
                    hit_keywords.append(keyword)
            if hit_keywords:
                matches[signal_type] = hit_keywords

        return matches

    def detect_market_narrative_signals(self, event: Any) -> Dict[str, List[str]]:
        """检测市场叙事信号（Sentiment）- 市场情绪/舆论信号（仅作参考）

        【Sentiment-市场情绪】外部市场/舆论的热门程度
        - 基于 SENTIMENT_KEYWORDS 命中情况
        - 代表市场当前关注的话题/情绪
        - 作为决策参考，不作为主要依据

        Returns:
            Dict[str, List[str]] - 按市场叙事类别分类的命中关键词
        """
        if not self.enabled:
            return {}

        texts = self._collect_texts(event)
        if not texts:
            return {}

        combined = " ".join(t for t in texts if t)
        combined_lower = combined.lower()
        matches: Dict[str, List[str]] = {}

        for signal_type, keywords in SENTIMENT_KEYWORDS.items():
            hit_keywords: List[str] = []
            for keyword in keywords:
                if self._keyword_in_text(keyword, combined, combined_lower):
                    hit_keywords.append(keyword)
            if hit_keywords:
                matches[signal_type] = hit_keywords

        return matches

    def detect_problem_opportunity(self, event: Any) -> Optional[Dict[str, Any]]:
        """
        检测供需问题 → 机会转化 → 解决者溯源

        这是"问题即机会"框架的核心实现：
        1. 从新闻中识别供需失衡（问题）
        2. 判断问题类型（Token/电力/芯片）
        3. 转化为投资机会
        4. 溯源找到解决问题的人（公司）

        Returns:
            包含 detected_problems, opportunities, resolvers 的字典，
            如果没有检测到问题则返回 None
        """
        if not self.enabled:
            return None

        texts = self._collect_texts(event)
        if not texts:
            return None

        combined = " ".join(t for t in texts if t)
        combined_lower = combined.lower()

        detected_problems: List[Dict[str, Any]] = []
        opportunity_types_found: Set[str] = set()

        for category, keywords in SUPPLY_DEMAND_KEYWORDS.items():
            hit_keywords: List[str] = []
            for keyword in keywords:
                if self._keyword_in_text(keyword, combined, combined_lower):
                    hit_keywords.append(keyword)
            if hit_keywords:
                severity = self._assess_problem_severity(category, hit_keywords)
                detected_problems.append({
                    "type": category,
                    "keywords": hit_keywords,
                    "severity": severity,
                })
                opportunity_types_found.add(category)

        if not detected_problems:
            return None

        opportunities: List[Dict[str, Any]] = []
        all_resolvers: List[Dict[str, Any]] = []

        for category in opportunity_types_found:
            opp_info = OPPORTUNITY_TYPES.get(category, {})
            if opp_info:
                opportunities.append({
                    "category": category,
                    "opportunity": opp_info.get("opportunity", ""),
                    "beneficiaries": opp_info.get("beneficiaries", []),
                    "description": opp_info.get("description", ""),
                    "signal": opp_info.get("signal", ""),
                })

            resolvers_info = self._find_resolvers_for_category(category)
            if resolvers_info:
                all_resolvers.extend(resolvers_info)

        confidence = min(1.0, len(detected_problems) / 3.0)

        return {
            "detected_problems": detected_problems,
            "opportunities": opportunities,
            "resolvers": all_resolvers,
            "confidence": confidence,
            "timestamp": time.time(),
        }

    def _assess_problem_severity(self, category: str, hit_keywords: List[str]) -> str:
        """评估问题严重程度"""
        severity_indicators = {
            "供给不足": ["严重", "极度", "危机", "崩溃", "枯竭"],
            "需求爆发": ["暴涨", "激增", "抢购", "疯狂", "爆炸"],
        }

        for kw in hit_keywords:
            for level, indicators in severity_indicators.items():
                if any(ind in kw for ind in indicators):
                    return level

        if len(hit_keywords) >= 3:
            return "严重"
        elif len(hit_keywords) >= 1:
            return "中等"
        return "轻微"

    def _find_resolvers_for_category(self, category: str) -> List[Dict[str, Any]]:
        """根据问题类型找到解决者"""
        category_to_resolver = {
            "token供给不足": "先进封装",
            "token需求爆发": "算力效率",
            "电力供给不足": "AI电力",
            "电力需求爆发": "AI电力",
            "芯片供给不足": "先进制程",
            "芯片需求爆发": "先进封装",
            "技术瓶颈突破": "算力效率",
        }

        resolver_key = category_to_resolver.get(category)
        if not resolver_key:
            return []

        resolver_info = RESOLVERS.get(resolver_key)
        if not resolver_info:
            return []

        resolvers = resolver_info.get("resolvers", [])
        progress = resolver_info.get("progress", {})

        result = []
        for resolver in resolvers:
            result.append({
                "name": resolver,
                "problem": resolver_info.get("problem", ""),
                "opportunity": resolver_info.get("opportunity", ""),
                "progress": progress.get(resolver, "未知"),
            })

        return result

    def get_problem_opportunity_summary(self) -> Dict[str, Any]:
        """
        获取当前问题-机会-解决者汇总

        基于历史追踪的叙事状态，生成问题-机会分析报告

        Returns:
            包含问题列表、机会列表、解决者列表的字典
        """
        if not self._states:
            return {
                "status": "no_data",
                "problems": [],
                "opportunities": [],
                "resolvers": [],
                "recommendation": "WATCH",
            }

        all_keywords: List[str] = []
        for state in self._states.values():
            all_keywords.extend(state.last_keywords)

        detected_categories: Set[str] = set()
        for category, keywords in SUPPLY_DEMAND_KEYWORDS.items():
            for kw in keywords:
                if any(kw in ak or ak in kw for ak in all_keywords):
                    detected_categories.add(category)

        problems = []
        opportunities = []
        resolvers = []

        for category in detected_categories:
            problems.append({
                "category": category,
                "severity": "active",
            })

            opp_info = OPPORTUNITY_TYPES.get(category, {})
            if opp_info:
                opportunities.append({
                    "category": category,
                    "opportunity": opp_info.get("opportunity", ""),
                    "beneficiaries": opp_info.get("beneficiaries", []),
                })

            resolver_info = self._find_resolvers_for_category(category)
            resolvers.extend(resolver_info)

        if not problems:
            return {
                "status": "no_problems_detected",
                "problems": [],
                "opportunities": [],
                "resolvers": [],
                "recommendation": "WATCH",
            }

        recommendation = "STRONG_BUY" if len(problems) >= 3 else "BUY" if len(problems) >= 1 else "WATCH"

        return {
            "status": "active",
            "problems": problems,
            "opportunities": opportunities,
            "resolvers": resolvers,
            "recommendation": recommendation,
            "timestamp": time.time(),
        }

    def get_value_market_summary(self) -> Dict[str, Any]:
        """
        【我们-Dynamics】获取价值/市场评分摘要

        遵循供需动态，驾驭市场情绪的核心接口

        🚀 架构更新：从独立的 _value_signals 读取供需动态数据
        - Dynamics数据：从供需动态信号独立存储 _value_signals 提取
        - Sentiment数据：从外部叙事状态 _states 提取（作为参考）

        【Dynamics-主动价值发现】（epsilon通道）
            - 直接从 _value_signals 读取
            - 代表：我们自己认定什么是真正重要的变化

        【Sentiment-市场参考】（不参与主动决策）
            - 从 _states 中提取市场情绪关键词
            - 仅作参考，不作为主要决策依据

        推荐行动基于价值（供需动态），而非市场叙事（市场情绪）

        Returns:
            包含价值评分、市场叙事评分、投资建议的字典
        """
        recent_cutoff = time.time() - 72 * 3600

        value_signals_by_type: Dict[str, Set[str]] = {
            k: set() for k in ["token供需", "电力供需", "技术瓶颈", "效率突破", "AI落地"]
        }
        for signal in self._value_signals:
            if signal.timestamp >= recent_cutoff:
                if signal.signal_type in value_signals_by_type:
                    value_signals_by_type[signal.signal_type].update(signal.keywords)

        market_signals_by_type: Dict[str, Set[str]] = {
            k: set() for k in ["行情涨跌", "市场情绪", "舆论热点"]
        }
        for state in self._states.values():
            if state.last_updated < recent_cutoff:
                continue
            for keyword in state.last_keywords:
                for minxin_type, minxin_kws in SENTIMENT_KEYWORDS.items():
                    for kw in minxin_kws:
                        if kw in keyword or keyword in kw:
                            if minxin_type in market_signals_by_type:
                                market_signals_by_type[minxin_type].add(kw)

        value_hits = sum(len(v) for v in value_signals_by_type.values())
        market_hits = sum(len(v) for v in market_signals_by_type.values())
        value_score = min(1.0, value_hits / 10.0)
        market_narrative_score = min(1.0, market_hits / 15.0)

        if value_hits >= 3 and market_hits <= 1:
            recommendation = "STRONG_BUY"
            reason = "价值信号强 + 市场错判（价格跌）= 最佳买入时机"
        elif value_score > 0.6:
            recommendation = "ALL_IN"
            reason = "价值信号强劲，继续持有/买入"
        elif value_score > 0.3:
            recommendation = "HOLD"
            reason = "价值信号存在，继续观察"
        elif value_hits > 0 and value_score < 0.2:
            recommendation = "REDUCE"
            reason = "供给可能过剩，价值信号减弱"
        else:
            recommendation = "WATCH"
            reason = "价值信号不明显，继续观察"

        market_opportunity = None
        if value_hits >= 3 and market_hits <= 1:
            market_opportunity = "价值强 + 价格跌 = 最佳买入时机（驾驭市场情绪）"
        elif value_score > 0.5 and market_narrative_score > 0.5:
            market_opportunity = "价值强 + 价格涨 = 顺势持有"

        return {
            "value_score": round(value_score, 3),
            "market_narrative_score": round(market_narrative_score, 3),
            "recommendation": recommendation,
            "reason": reason,
            "signals": {
                "value": {k: list(v) for k, v in value_signals_by_type.items() if v},
                "market_narrative": {k: list(v) for k, v in market_signals_by_type.items() if v},
            },
            "market_opportunity": market_opportunity,
            "principle": "遵循供需动态，驾驭市场情绪",
            "timestamp": time.time(),
        }

    def get_tiandao_minxin_summary(self) -> Dict[str, Any]:
        """向后兼容别名 - 请使用 get_value_market_summary()"""
        return self.get_value_market_summary()

    def detect_tiandao_signals(self, event: Any) -> Dict[str, List[str]]:
        """向后兼容别名 - 请使用 detect_value_signals()"""
        return self.detect_value_signals(event)

    def detect_minxin_signals(self, event: Any) -> Dict[str, List[str]]:
        """向后兼容别名 - 请使用 detect_market_narrative_signals()"""
        return self.detect_market_narrative_signals(event)

    def get_markdown_summary(self) -> str:
        """获取Markdown格式的每日反思摘要 - 用于报告和展示

        简洁格式，适合直接给用户查看
        """
        if not self._states:
            return "## 📊 每日反思\n\n暂无数据"

        value_summary = self.get_value_market_summary()
        trading_signal = self.get_trading_signal()

        value_score = value_summary.get("value_score", 0)
        market_narrative_score = value_summary.get("market_narrative_score", 0)
        recommendation = value_summary.get("recommendation", "WATCH")

        verdict_map = {
            "STRONG_BUY": "✅ 重大机会",
            "ALL_IN": "🟢 顺势持有",
            "HOLD": "🟡 继续观察",
            "REDUCE": "🟠 考虑减仓",
            "WATCH": "⚪ 保持观望",
        }
        verdict = verdict_map.get(recommendation, "⚪ 观察中")

        lines = [
            "## 📊 每日反思",
            "",
            f"**日期**: {time.strftime('%Y-%m-%d')}",
            "",
            "---",
            "",
            "### 🎯 价值 vs 市场叙事（Dynamics vs Sentiment）",
            "",
            f"| 维度 | 评分 | 说明 |",
            f"|------|------|------|",
            f"| 价值(Dynamics) | {value_score:.0%} | {value_summary.get('reason', '待观察')} |",
            f"| 市场叙事(Sentiment) | {market_narrative_score:.0%} | {value_summary.get('market_opportunity', '无特殊')} |",
            "",
            f"**结论**: {verdict} - {recommendation}",
            "",
            "---",
            "",
            "### 📈 交易信号",
            "",
            f"- 信号: **{trading_signal.get('signal', 'WATCH')}**",
            f"- 波动: {trading_signal.get('volatility', 'UNKNOWN')}",
            f"- 操作: {trading_signal.get('action', '正常持有')}",
            f"- 原因: {trading_signal.get('reason', '趋势不明显')}",
            "",
            "---",
            "",
            "### 💡 操作建议",
            "",
        ]

        if recommendation == "STRONG_BUY":
            lines.append("🎯 **重大机会**: Dynamics强 + 价格低，建议加仓")
        elif recommendation == "ALL_IN":
            lines.append("🟢 **顺势持有**: Dynamics支持，继续持有或加仓")
        elif recommendation == "HOLD":
            lines.append("🟡 **继续观察**: 等待更明确信号")
        elif recommendation == "REDUCE":
            lines.append("🟠 **考虑减仓**: Dynamics减弱，注意风险")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(f"*{value_summary.get('principle', '遵循供需动态，驾驭市场情绪')}*")

        return "\n".join(lines)

    def generate_daily_reflection(self) -> Dict[str, Any]:
        """生成每日反思报告 - 将数据分析转化为自我校准

        反思维度：
        1. Dynamics判断：我的价值判断是否正确
        2. Sentiment判断：我对市场的理解是否正确
        3. 交易决策：我的决策是否有效
        4. 进化方向：下一步如何改进
        """
        if not self._states:
            return {
                "date": time.strftime("%Y-%m-%d"),
                "summary": "暂无数据，无法反思",
                "reflections": [],
                "recommendations": [],
            }

        value_summary = self.get_value_market_summary()
        trading_signal = self.get_trading_signal()

        reflections = []
        recommendations = []

        value_score = value_summary.get("value_score", 0)
        market_narrative_score = value_summary.get("market_narrative_score", 0)
        recommendation = value_summary.get("recommendation", "WATCH")

        reflections.append({
            "aspect": "价值判断（Dynamics）",
            "observation": f"价值评分{value_score:.1%}，{value_summary.get('reason', '')}",
            "verdict": "正确" if value_score > 0.5 else "需观察",
        })

        reflections.append({
            "aspect": "市场叙事判断（Sentiment）",
            "observation": f"市场叙事评分{market_narrative_score:.1%}，{value_summary.get('market_opportunity', '无特殊机会')}",
            "verdict": "市场错判" if market_narrative_score < 0.3 and value_score > 0.5 else "正常",
        })

        signal = trading_signal.get("signal", "WATCH")
        volatility = trading_signal.get("volatility", "UNKNOWN")

        if signal == "OVERSOLD":
            reflections.append({
                "aspect": "波动判断",
                "observation": f"检测到超卖信号：{trading_signal.get('reason', '')}",
                "verdict": "可能是买入机会",
            })
            recommendations.append("可以考虑分批买入，等反弹后高抛")
        elif signal == "OVERBOUGHT":
            reflections.append({
                "aspect": "波动判断",
                "observation": f"检测到超买信号：{trading_signal.get('reason', '')}",
                "verdict": "注意风险",
            })
            recommendations.append("可以适当减仓，等回调再买")
        else:
            reflections.append({
                "aspect": "波动判断",
                "observation": f"市场波动正常：{trading_signal.get('reason', '')}",
                "verdict": "正常持有",
            })

        if recommendation == "STRONG_BUY":
            recommendations.append("重大机会：价值信号强+价格低，建议加仓")
        elif recommendation == "ALL_IN":
            recommendations.append("价值支持：继续持有或加仓")
        elif recommendation == "REDUCE":
            recommendations.append("价值减弱：考虑减仓")

        if recommendations:
            recommendations.append("坚持遵循供需动态，驾驭市场情绪，不被市场情绪左右")

        ai_state = self._states.get("AI")
        chip_state = self._states.get("芯片")
        if ai_state and chip_state:
            ai_trend = ai_state.trend
            chip_trend = chip_state.trend
            if ai_trend > 0.3 and chip_trend > 0.3:
                reflections.append({
                    "aspect": "趋势判断",
                    "observation": f"AI叙事趋势{ai_trend:+.1f}，芯片叙事趋势{chip_trend:+.1f}",
                    "verdict": "强势方向，继续持有",
                })
            elif ai_trend < -0.3 or chip_trend < -0.3:
                reflections.append({
                    "aspect": "趋势判断",
                    "observation": f"AI叙事趋势{ai_trend:+.1f}，芯片叙事趋势{chip_trend:+.1f}",
                    "verdict": "趋势减弱，谨慎观望",
                })

        verdict_map = {
            "STRONG_BUY": "✅ 重大机会",
            "ALL_IN": "🟢 顺势持有",
            "HOLD": "🟡 继续观察",
            "REDUCE": "🟠 考虑减仓",
            "WATCH": "⚪ 保持观望",
        }

        return {
            "date": time.strftime("%Y-%m-%d"),
            "verdict": verdict_map.get(recommendation, "⚪ 观察中"),
            "value_score": value_score,
            "market_narrative_score": market_narrative_score,
            "signal": signal,
            "summary": f"价值(Dynamics){value_score:.0%} vs 市场叙事(Sentiment){market_narrative_score:.0%} → {recommendation}",
            "reflections": reflections,
            "recommendations": list(set(recommendations)),
            "principle": "遵循供需动态，驾驭市场情绪",
            "timestamp": time.time(),
        }

    _market_analysis_db = None

    def analyze_market_full(self) -> Dict[str, Any]:
        """全市场深度分析

        步骤1：全量股票 → 题材映射 → River异常检测
        步骤2：只关注行业+持仓 → River二次分析（重点）

        Returns:
            包含全市场分析、持仓分析、综合判断的字典
        """
        import logging
        log = logging.getLogger(__name__)

        log.info("[NarrativeTracker] 开始全市场深度分析...")

        step1_result = self._analyze_full_market()

        step2_result = self._analyze_focused_blocks(step1_result)

        combined_result = {
            "step1_full_market": step1_result,
            "step2_focused": step2_result,
            "summary": self._generate_market_summary(step1_result, step2_result),
            "timestamp": time.time(),
        }

        db = self._get_market_analysis_db()
        db["full_analysis"] = combined_result

        log.info("[NarrativeTracker] 全市场深度分析完成")

        return combined_result

    def _analyze_full_market(self) -> Dict[str, Any]:
        """第一步：全市场分析"""
        import logging
        log = logging.getLogger(__name__)

        stock_data = self._fetch_all_stock_data()
        if not stock_data:
            return {"success": False, "message": "无法获取市场数据"}

        block_analysis = self._map_blocks(stock_data)

        stocks_with_block = self._merge_block_to_stocks(stock_data, block_analysis)

        anomaly_result = self._run_river_anomaly_detection(stocks_with_block)

        return {
            "success": True,
            "stock_count": len(stock_data),
            "block_analysis": block_analysis,
            "anomaly_result": anomaly_result,
            "top_movers": self._get_top_movers(stock_data, limit=5),
        }

    def _merge_block_to_stocks(self, stock_data: Dict[str, Dict], block_analysis: Dict[str, List[Dict]]) -> List[Dict]:
        """把block信息合并到股票数据中"""
        symbol_to_block = {}
        for block, stocks in block_analysis.items():
            for stock in stocks:
                sym = stock.get("symbol", stock.get("code"))
                if sym:
                    symbol_to_block[sym] = {
                        "block": block,
                        "narrative": stock.get("narrative", ""),
                        "blocks": stock.get("blocks", []),
                    }

        result = []
        for sym, data in stock_data.items():
            merged = dict(data)
            if sym in symbol_to_block:
                merged.update(symbol_to_block[sym])
            else:
                merged["block"] = "other"
                merged["narrative"] = ""
                merged["blocks"] = []
            result.append(merged)

        return result

    def _analyze_focused_blocks(self, step1_result: Dict[str, Any]) -> Dict[str, Any]:
        """第二步：持仓+关注题材二次分析（重点）"""
        import logging
        log = logging.getLogger(__name__)

        if not step1_result.get("success"):
            return {"success": False}

        all_stocks = step1_result.get("stock_data", {})
        if not all_stocks:
            all_stocks = self._fetch_all_stock_data()

        focus_symbols = self._get_focus_symbols()

        focus_stocks = {
            symbol: data for symbol, data in all_stocks.items()
            if symbol.upper() in [s.upper() for s in focus_symbols]
        }

        if not focus_stocks:
            log.warning("[NarrativeTracker] 持仓/关注股票无数据")
            return {"success": False, "message": "无持仓/关注股票数据"}

        block_analysis = self._map_blocks(focus_stocks)

        anomaly_result = self._run_river_anomaly_detection(list(focus_stocks.values()))

        holding_analysis = self._analyze_holdings(focus_stocks)

        return {
            "success": True,
            "focus_stock_count": len(focus_stocks),
            "focus_symbols": list(focus_stocks.keys()),
            "block_analysis": block_analysis,
            "anomaly_result": anomaly_result,
            "holding_analysis": holding_analysis,
            "top_movers": self._get_top_movers(focus_stocks, limit=5),
        }

    def _fetch_all_stock_data(self) -> Dict[str, Dict]:
        """获取全量股票数据（A股+美股）"""
        result = {}

        result.update(self._fetch_ashare_data())

        result.update(self._fetch_us_stock_data())

        return result

    def _fetch_ashare_data(self) -> Dict[str, Dict]:
        """获取A股数据 - 使用历史快照数据库（已过滤噪音股票）"""
        try:
            from deva import NB

            snapshot_db = NB('quant_snapshot_5min_window', key_mode='time')
            keys = list(snapshot_db.keys())
            if not keys:
                return {}

            latest_key = keys[-1]
            data_list = snapshot_db.get(latest_key)

            if not data_list or not isinstance(data_list, list):
                return {}

            result = {}
            for item in data_list:
                code = str(item.get("code", ""))
                if not code:
                    continue

                try:
                    now = item.get("now", 0)
                    close = item.get("close", 0)
                    if close > 0:
                        p_change = (now - close) / close
                    else:
                        p_change = 0
                    result[code] = {
                        "code": code,
                        "name": item.get("name", code),
                        "price": now,
                        "change_pct": p_change,
                        "volume": int(item.get("volume", 0)),
                        "high": item.get("high", 0),
                        "low": item.get("low", 0),
                        "prev_close": close,
                        "open": item.get("open", 0),
                        "market": "A",
                    }
                except Exception:
                    continue

            return result
        except Exception:
            return {}

    def _fetch_us_stock_data(self) -> Dict[str, Dict]:
        """获取美股数据"""
        try:
            from deva.naja.market_hotspot.data.global_market_futures import GlobalMarketAPI
            import asyncio
            import nest_asyncio
            nest_asyncio.apply()

            async def fetch():
                async with GlobalMarketAPI() as api:
                    return await api.fetch_us_stocks()

            try:
                loop = asyncio.get_event_loop()
                data = loop.run_until_complete(fetch())
            except RuntimeError:
                asyncio.run(fetch())

            result = {}
            for code, market_data in data.items():
                if market_data and hasattr(market_data, 'code'):
                    change_pct = market_data.change_pct
                    if abs(change_pct) > 1:
                        change_pct = change_pct / 100
                    result[code.upper()] = {
                        "code": market_data.code.upper(),
                        "name": market_data.name,
                        "price": market_data.current,
                        "change_pct": change_pct,
                        "p_change": change_pct,
                        "volume": market_data.volume,
                        "high": market_data.high,
                        "low": market_data.low,
                        "prev_close": market_data.prev_close,
                        "market": "US",
                    }

            return result
        except Exception:
            return {}

    def _get_focus_symbols(self) -> List[str]:
        """获取关注的股票列表：持仓+行业关注"""
        symbols = []

        try:
            from deva.naja.bandit.portfolio_manager import get_portfolio_manager
            pm = get_portfolio_manager()
            if pm:
                for account_name in ["Spark", "Cutie"]:
                    portfolio = pm.get_us_portfolio(account_name)
                    if portfolio:
                        positions = portfolio.get_open_positions()
                        for pos in positions:
                            if hasattr(pos, 'stock_code'):
                                symbols.append(pos.stock_code)
        except Exception:
            pass

        symbols.extend(["NVDA", "AMD", "META", "TSLA", "AAPL", "MSFT", "GOOG", "AMZN"])

        return list(set(symbols))

    def _map_blocks(self, stocks: Dict[str, Dict]) -> Dict[str, List[Dict]]:
        """题材映射分析 - A股用通达信，美股用US_STOCK_BLOCKS"""
        from deva.naja.bandit.stock_block_map import US_STOCK_BLOCKS, INDUSTRY_CODE_TO_NAME, NARRATIVE_INDUSTRY_MAP

        try:
            from deva.naja.dictionary.tongdaxin_blocks import get_stock_blocks, _parse_blocks_file
            _parse_blocks_file()
            has_tdx = True
        except Exception:
            has_tdx = False

        block_map: Dict[str, List[Dict]] = defaultdict(list)

        for symbol, data in stocks.items():
            market = data.get("market", "A")

            if market == "US":
                stock_info = US_STOCK_BLOCKS.get(symbol.lower(), {})
                if stock_info:
                    block = stock_info.get("industry_code", "other")
                    blocks = stock_info.get("blocks", [])
                    narrative = stock_info.get("narrative", "")
                else:
                    block = "other"
                    blocks = []
                    narrative = ""
            else:
                block = "other"
                blocks = []
                narrative = ""

                if has_tdx:
                    code = symbol.replace("sh", "").replace("sz", "")
                    blocks = get_stock_blocks(code)
                    if blocks:
                        block = blocks[0]

            block_map[block].append({
                "symbol": symbol,
                "name": data.get("name", symbol),
                "price": data.get("price", 0),
                "change_pct": data.get("change_pct", 0),
                "blocks": blocks,
                "narrative": narrative,
            })

        return dict(block_map)

    def _run_river_anomaly_detection(self, stocks: List[Dict]) -> Dict[str, Any]:
        """使用River风格进行单日横截面分析

        1. RiverTickSingleDayAnalyzer - 单日全市场横截面分析
        2. 题材表现分析
        3. 异常波动检测
        4. 市场情绪判断
        """
        try:
            from deva.naja.strategy.river_single_day_analyzer import RiverTickSingleDayAnalyzer

            analyzer = RiverTickSingleDayAnalyzer()

            for stock in stocks:
                analyzer.on_data(stock)

            result = analyzer.get_signal()

            if not result:
                return {"error": "无数据"}

            return {
                "total_analyzed": result.stock_count,
                "market_breadth": round(result.market_breadth, 3),
                "market_sentiment": result.market_sentiment,
                "fund_flow": result.fund_flow,
                "market_feature": result.market_feature,
                "avg_change": round(result.avg_change, 3),
                "median_change": round(result.median_change, 3),
                "advancing_count": result.advancing_count,
                "declining_count": result.declining_count,
                "blocks": {
                    block_id: {
                        "stock_count": ba.stock_count,
                        "avg_change": round(ba.avg_change, 3),
                        "gainer_count": ba.gainer_count,
                        "loser_count": ba.loser_count,
                    }
                    for block_id, ba in result.blocks.items()
                    if ba.stock_count >= 1
                },
                "anomalies": result.anomalies[:10],
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_top_movers(self, stocks: Dict[str, Dict], limit: int = 5) -> Dict[str, List]:
        """获取涨幅/跌幅最大的股票"""
        sorted_stocks = sorted(stocks.values(), key=lambda x: x.get("change_pct", 0), reverse=True)
        return {
            "gainers": [{
                "symbol": s.get("code", ""),
                "name": s.get("name", ""),
                "change_pct": s.get("change_pct", 0),
            } for s in sorted_stocks[:limit]],
            "losers": [{
                "symbol": s.get("code", ""),
                "name": s.get("name", ""),
                "change_pct": s.get("change_pct", 0),
            } for s in sorted_stocks[-limit:]],
        }

    def _analyze_holdings(self, stocks: Dict[str, Dict]) -> Dict[str, Any]:
        """分析持仓股票"""
        holdings = []

        try:
            from deva.naja.bandit.portfolio_manager import get_portfolio_manager
            pm = get_portfolio_manager()
            if pm:
                for account_name in ["Spark", "Cutie"]:
                    portfolio = pm.get_us_portfolio(account_name)
                    if portfolio:
                        positions = portfolio.get_open_positions()
                        for pos in positions:
                            symbol = pos.stock_code.upper()
                            if symbol in stocks:
                                stock_data = stocks[symbol]
                                holdings.append({
                                    "account": account_name,
                                    "symbol": symbol,
                                    "name": stock_data.get("name", symbol),
                                    "quantity": pos.quantity,
                                    "entry_price": pos.entry_price,
                                    "current_price": stock_data.get("price", 0),
                                    "profit_loss": pos.profit_loss,
                                    "return_pct": pos.return_pct,
                                    "current_change_pct": stock_data.get("change_pct", 0),
                                })
        except Exception:
            pass

        return {"holdings": holdings}

    def _generate_market_summary(self, step1: Dict, step2: Dict) -> str:
        """生成市场总结"""
        parts = []

        if step1.get("success"):
            top_movers = step1.get("top_movers", {})
            gainers = top_movers.get("gainers", [])
            if gainers:
                best = gainers[0]
                parts.append(f"全市场涨幅最大: {best['name']}({best['symbol']}) {best['change_pct']:+.2f}%")

        if step2.get("success"):
            holding_analysis = step2.get("holding_analysis", {})
            holdings = holding_analysis.get("holdings", [])
            if holdings:
                total_pnl = sum(h.get("profit_loss", 0) for h in holdings)
                parts.append(f"持仓盈亏: ${total_pnl:+.2f}")

        return " | ".join(parts) if parts else "暂无数据"

    @classmethod
    def _get_market_analysis_db(cls):
        if cls._market_analysis_db is None:
            from deva import NB
            cls._market_analysis_db = NB("naja_market_analysis")
        return cls._market_analysis_db

    def analyze_market_data(self) -> Dict[str, Any]:
        """盘后市场分析 - 由定时任务调用

        获取主要指数行情，分析市场状态，存储分析结果
        供LLM反思时收集
        """
        import logging
        log = logging.getLogger(__name__)

        try:
            market_data = self._fetch_market_indices()
            if not market_data:
                return {"success": False, "message": "无法获取市场数据"}

            analysis = self._analyze_market_indices(market_data)

            market_analysis = {
                "data": market_data,
                "analysis": analysis,
                "timestamp": time.time(),
            }

            db = self._get_market_analysis_db()
            db["latest"] = market_analysis

            log.info(f"[NarrativeTracker] 盘后市场分析完成: {analysis.get('summary', 'N/A')}")

            return {
                "success": True,
                "market_data": market_data,
                "analysis": analysis,
            }
        except Exception as e:
            log.error(f"[NarrativeTracker] 盘后市场分析失败: {e}")
            return {"success": False, "message": str(e)}

    def _fetch_market_indices(self) -> Dict[str, Dict]:
        """获取主要指数行情"""
        try:
            import urllib.request
            import json

            indices = ["^NDX", "^SPX", "^QQQ", "^DJI", "^VIX"]
            result = {}

            for symbol in indices:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                try:
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = json.loads(response.read().decode())
                        result_data = data.get("chart", {}).get("result", [{}])[0]
                        meta = result_data.get("meta", {})
                        price = meta.get("regularMarketPrice")
                        prev_close = meta.get("previousClose")
                        change_pct = (price - prev_close) / prev_close * 100 if price and prev_close else 0

                        symbol_name = symbol.replace("^", "")
                        result[symbol_name] = {
                            "price": price,
                            "change_pct": round(change_pct, 2),
                            "prev_close": prev_close,
                        }
                except Exception:
                    continue

            return result
        except Exception:
            return {}

    def _analyze_market_indices(self, data: Dict[str, Dict]) -> Dict[str, Any]:
        """分析市场指数数据"""
        if not data:
            return {"summary": "无数据", "status": "unknown"}

        ndx_change = data.get("NDX", {}).get("change_pct", 0)
        spy_change = data.get("SPX", {}).get("change_pct", 0)
        qqq_change = data.get("QQQ", {}).get("change_pct", 0)
        vix = data.get("VIX", {}).get("price", 20)

        avg_change = (ndx_change + spy_change + qqq_change) / 3

        if avg_change > 2:
            status = "强势上涨"
            description = f"市场强势上涨，纳指{ndx_change:+.2f}%，标普{spy_change:+.2f}%"
        elif avg_change > 0.5:
            status = "小幅上涨"
            description = f"市场温和上涨，纳指{ndx_change:+.2f}%"
        elif avg_change > -0.5:
            status = "震荡整理"
            description = f"市场震荡，纳指{ndx_change:+.2f}%"
        elif avg_change > -2:
            status = "小幅下跌"
            description = f"市场小幅回调，纳指{ndx_change:+.2f}%"
        else:
            status = "大幅下跌"
            description = f"市场大幅下跌，纳指{ndx_change:+.2f}%，标普{spy_change:+.2f}%"

        if vix > 30:
            description += f"，VIX高企({vix:.1f})，市场恐慌"
        elif vix > 20:
            description += f"，VIX中性({vix:.1f})"

        return {
            "status": status,
            "summary": description,
            "ndx_change": ndx_change,
            "spy_change": spy_change,
            "qqq_change": qqq_change,
            "vix": vix,
            "avg_change": round(avg_change, 2),
        }

    def get_market_analysis(self) -> Dict[str, Any]:
        """获取缓存的市场分析结果"""
        try:
            db = self._get_market_analysis_db()
            return db.get("latest", {})
        except Exception:
            return {}

    def get_trading_signal(self) -> Dict[str, Any]:
        """获取交易信号 - 基于叙事状态判断超卖/超买

        利用NarrativeState的trend和stage判断：
        - 超卖：叙事衰退+价格跌 = 买入机会
        - 超买：叙事高潮+价格涨 = 卖出机会
        """
        if not self._states:
            return {
                "signal": "WATCH",
                "volatility": "UNKNOWN",
                "action": "暂无数据，继续观察",
                "reason": "",
            }

        ai_state = self._states.get("AI")
        chip_state = self._states.get("芯片")
        price_state = self._states.get("新能源")  # 用于检测市场整体情绪

        signal = "WATCH"
        volatility = "NORMAL"
        action = "正常持有"
        reason_parts = []

        if ai_state and chip_state:
            ai_trend = ai_state.trend
            chip_trend = chip_state.trend
            ai_stage = ai_state.stage
            chip_stage = chip_state.stage

            if ai_trend < -0.5 and ai_stage in ("消退", "萌芽"):
                signal = "OVERSOLD"
                volatility = "LOW"
                action = "可以考虑买入，等反弹后高抛"
                reason_parts.append("AI叙事衰退，可能是买入机会")
            elif ai_trend > 0.5 and ai_stage in ("高潮", "扩散"):
                signal = "OVERBOUGHT"
                volatility = "HIGH"
                action = "可以考虑减仓，等回调再买"
                reason_parts.append("AI叙事过热，注意风险")

        if price_state:
            price_trend = price_state.trend
            if price_trend < -0.3:
                reason_parts.append("价格下跌趋势")
            elif price_trend > 0.3:
                reason_parts.append("价格上涨趋势")

        value_summary = self.get_value_market_summary()
        value_score = value_summary.get("value_score", 0)

        if signal == "OVERSOLD" and value_score > 0.3:
            action = "最佳买入时机：价值信号好+价格低"
            reason_parts.append("价值信号强+价格低")
        elif signal == "OVERBOUGHT" and value_score > 0.3:
            action = "可以适当减仓：价值信号好+价格高"
            reason_parts.append("价值信号强+价格高")

        reason = "；".join(reason_parts) if reason_parts else "趋势不明显"

        return {
            "signal": signal,
            "volatility": volatility,
            "action": action,
            "reason": reason,
            "value_score": value_score,
            "timestamp": time.time(),
        }

    def _collect_texts(self, event: Any) -> List[str]:
        texts: List[str] = []
        if event is None:
            return texts
        content = getattr(event, "content", None)
        if content:
            texts.append(str(content))
        meta = getattr(event, "meta", {}) or {}

        for key in ("title", "topic", "block", "block", "industry", "theme", "summary"):
            val = meta.get(key)
            if val:
                texts.append(str(val))

        for key in ("tags", "keywords", "narratives", "narrative"):
            val = meta.get(key)
            if isinstance(val, list):
                texts.extend([str(v) for v in val])
            elif val:
                texts.append(str(val))

        return texts

    def _keyword_in_text(self, keyword: str, text: str, text_lower: str) -> bool:
        if not keyword:
            return False
        if keyword.isascii():
            return keyword.lower() in text_lower
        return keyword in text

    def _get_timestamp(self, event: Any) -> float:
        ts = getattr(event, "timestamp", None)
        if ts is None:
            return time.time()
        if hasattr(ts, "timestamp"):
            try:
                return float(ts.timestamp())
            except Exception:
                return time.time()
        try:
            return float(ts)
        except Exception:
            return time.time()

    def _clamp_score(self, score: Any) -> float:
        try:
            value = float(score)
        except Exception:
            return 0.0
        if value < 0:
            return 0.0
        if value <= 1.0:
            return value
        return min(1.0, value / 5.0)

    def _prune_hits(self, state: NarrativeState, now_ts: float) -> None:
        cutoff = now_ts - self._history_window
        while state.hits and state.hits[0][0] < cutoff:
            state.hits.popleft()

    def _compute_metrics(self, state: NarrativeState, now_ts: float) -> Dict[str, Any]:
        recent_cutoff = now_ts - self._recent_window
        prev_cutoff = recent_cutoff - self._prev_window
        recent_hits = [h for h in state.hits if h[0] >= recent_cutoff]
        prev_hits = [h for h in state.hits if prev_cutoff <= h[0] < recent_cutoff]

        recent_count = len(recent_hits)
        prev_count = len(prev_hits)
        recent_attention = sum(h[1] for h in recent_hits) / recent_count if recent_hits else 0.0
        count_score = 1.0 - math.exp(-recent_count / max(self._count_scale, 1e-6))
        attention_score = 0.6 * count_score + 0.4 * recent_attention
        trend = (recent_count - prev_count) / max(prev_count, 1)

        return {
            "recent_count": recent_count,
            "prev_count": prev_count,
            "attention_score": attention_score,
            "recent_attention": recent_attention,
            "trend": trend,
        }

    def _determine_stage(self, metrics: Dict[str, Any]) -> str:
        recent_count = metrics["recent_count"]
        attention_score = metrics["attention_score"]
        trend = metrics["trend"]

        if recent_count <= self._fade_count and attention_score <= self._fade_score:
            return "消退"
        if recent_count >= self._peak_count or attention_score >= self._peak_score:
            return "高潮"
        if recent_count >= self._spread_count or trend >= self._trend_threshold or attention_score >= self._spread_score:
            return "扩散"
        return "萌芽"

    def _should_emit(self, state: NarrativeState, key: str, now_ts: float) -> bool:
        last_ts = state.last_emit.get(key, 0.0)
        if now_ts - last_ts < self._emit_cooldown:
            return False
        state.last_emit[key] = now_ts
        return True

    def _build_event_payload(
        self,
        *,
        narrative: str,
        event_type: str,
        stage: str,
        metrics: Dict[str, Any],
        keywords: List[str],
    ) -> Dict[str, Any]:
        payload = {
            "type": event_type,
            "event_type": event_type,
            "narrative": narrative,
            "stage": stage,
            "attention_score": round(metrics["attention_score"], 3),
            "recent_count": metrics["recent_count"],
            "prev_count": metrics["prev_count"],
            "trend": round(metrics["trend"], 3),
            "keywords": keywords,
            "linked_blocks": self.get_linked_blocks(narrative),
            "timestamp": time.time(),
        }
        return payload

    def _update_graph(self, now_ts: float, narratives: List[str]) -> None:
        cutoff = now_ts - self._graph_window
        while self._recent_hits and self._recent_hits[0][0] < cutoff:
            self._recent_hits.popleft()

        if len(narratives) > 1:
            pairs = self._pairs(narratives)
            for left, right in pairs:
                key = self._edge_key(left, right)
                self._graph_edges[key] += self._graph_same_weight

        for hit_ts, hit_list in self._recent_hits:
            if now_ts - hit_ts > self._graph_window:
                continue
            for left in narratives:
                for right in hit_list:
                    if left == right:
                        continue
                    key = self._edge_key(left, right)
                    self._graph_edges[key] += self._graph_temporal_weight

        self._recent_hits.append((now_ts, narratives))

    @staticmethod
    def _edge_key(left: str, right: str) -> Tuple[str, str]:
        return tuple(sorted((left, right)))

    @staticmethod
    def _pairs(items: Iterable[str]) -> List[Tuple[str, str]]:
        unique = list(dict.fromkeys(items))
        pairs: List[Tuple[str, str]] = []
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                pairs.append((unique[i], unique[j]))
        return pairs

    def tick(self) -> None:
        """Compatibility method - trigger narrative processing.

        In the old NarrativeTracker, tick() would process pending events.
        In the new NarrativeTracker, this is a no-op as processing is event-driven.
        """
        pass

    def get_active_narratives(self) -> List[Dict[str, Any]]:
        """Compatibility method - get active narratives.

        Returns narratives with attention_score > 0, formatted as dicts.
        """
        if not self._states:
            return []
        active = []
        for state in self._states.values():
            if state.attention_score > 0:
                active.append({
                    "name": state.name,
                    "narrative": state.name,
                    "stage": state.stage,
                    "attention_score": state.attention_score,
                    "trend": state.trend,
                    "recent_count": state.recent_count,
                })
        return sorted(active, key=lambda x: x["attention_score"], reverse=True)


_narrative_tracker_instance: Optional["NarrativeTracker"] = None


def get_narrative_tracker() -> Optional["NarrativeTracker"]:
    """Compatibility function - get singleton NarrativeTracker instance.

    Returns the global NarrativeTracker instance (aliased as NarrativeTracker).
    """
    global _narrative_tracker_instance
    if _narrative_tracker_instance is None:
        try:
            _narrative_tracker_instance = NarrativeTracker()
        except Exception:
            return None
    return _narrative_tracker_instance


NarrativeTracker = NarrativeTracker
