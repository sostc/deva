"""
NewsMind - 认知系统/新闻认知/话题跟踪

别名/关键词: 新闻、话题、情绪、sentiment、topic、narrative、舆情

核心思想: 流式学习 + 分层记忆 + 周期性自我反思
作为naja策略系统的一个插件运行

输入: 绑定的数据源（tick、新闻、文本）
输出: 信号流（主题信号、注意力信号、趋势变化信号）
"""

import time
import math
import numpy as np
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, List, Optional, Any, Tuple
import threading
import os

from .narrative import NarrativeTracker
from .semantic import (
    SemanticColdStart,
    NewsEvent,
    SignalType,
    DATASOURCE_TYPE_MAP,
    get_datasource_type,
    AttentionScorer,
    Topic,
    STOCK_RELEVANT_PREFIXES,
    STOCK_RELEVANT_SOURCES,
    _get_market_activity,
    _is_stock_relevant_topic,
)
from .memory_manager import MemoryManager


def _radar_debug_log(msg: str):
    """雷达调试日志"""
    if os.environ.get("NAJA_RADAR_DEBUG") == "true":
        import logging
        logging.getLogger(__name__).info(f"[Radar-Debug] {msg}")


def _cognition_debug_log(msg: str):
    """认知系统调试日志"""
    if os.environ.get("NAJA_COGNITION_DEBUG") == "true":
        import logging
        logging.getLogger(__name__).info(f"[Cognition-Debug] {msg}")

# River流式学习库
try:
    from river import cluster
    from river import drift
    RIVER_AVAILABLE = True
except ImportError:
    RIVER_AVAILABLE = False
    print("[NewsMind] Warning: river not installed, using fallback implementations")

# 持久化数据库
try:
    from deva import NB
    NAJA_DB_AVAILABLE = True
except ImportError:
    NAJA_DB_AVAILABLE = False
    print("[NewsMind] Warning: NB not available, persistence disabled")





class NewsMindStrategy:
    """
    新闻心智策略 - News Mind Strategy

    作为naja策略系统的插件运行，驱动认知流水线：
    信号 → 注意力 → 记忆 → 洞察

    日志标签: [NewsMind]
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """初始化策略"""
        self.config = config or {}
        
        # 配置参数
        self.short_term_size = self.config.get("short_term_size", 1000)
        self.topic_threshold = self.config.get("topic_threshold", 0.5)  # 降低阈值，让新主题更容易创建
        self.attention_threshold = self.config.get("attention_threshold", 0.6)
        self.max_topics = self.config.get("max_topics", 50)
        self.enable_attention_filter = bool(self.config.get("attention_filter_enabled", True))
        self.base_attention_gate = float(self.config.get("attention_gate_base", 0.35))
        self.target_rate_per_min = float(self.config.get("target_rate_per_min", 30))
        self.rate_window_seconds = int(self.config.get("rate_window_seconds", 300))
        self.max_batch_keep = int(self.config.get("max_batch_keep", 80))
        
        # 核心组件
        self.attention_scorer = AttentionScorer(history_size=self.short_term_size)
        
        # 记忆系统
        self.memory = MemoryManager(self.config)
        self.memory.set_market_activity_fn(_get_market_activity)

        # 记忆属性快捷访问
        self.short_memory = self.memory.short_memory
        self.mid_memory = self.memory.mid_memory
        self.long_memory = self.memory.long_memory

        self.topics: Dict[int, Topic] = {}
        self.topic_counter = 0

        # 记忆配置快捷访问
        self.short_term_half_life = self.memory.short_term_half_life
        self.mid_term_half_life = self.memory.mid_term_half_life
        self.topic_half_life = self.memory.topic_half_life
        self.mid_memory_threshold = self.memory.mid_memory_threshold
        self.long_memory_interval = self.memory.long_memory_interval
        self.last_long_memory_time = self.memory.last_long_memory_time
        self.reinforcement_shield = self.memory.reinforcement_shield
        
        # River组件
        if RIVER_AVAILABLE:
            # 使用River的在线聚类
            self.clustering = cluster.DBSTREAM(
                clustering_threshold=self.topic_threshold,
                fading_factor=self.config.get("fading_factor", 0.05),
                cleanup_interval=self.config.get("cleanup_interval", 10),
                intersection_factor=self.config.get("intersection_factor", 0.5),
            )
            # 漂移检测
            self.drift_detector = drift.ADWIN()
        else:
            self.clustering = None
            self.drift_detector = None
        
        # 统计信息
        self.stats = {
            "total_events": 0,
            "high_attention_events": 0,
            "topics_created": 0,
            "drifts_detected": 0,
            "filtered_events": 0,
        }

        # 频率控制
        self._rate_buckets: Dict[str, deque] = {}

        # 叙事追踪器
        self.narrative_tracker = NarrativeTracker(self.config)
        self.narrative_events: deque = deque(maxlen=200)

        # 全球流动性传播引擎
        self._init_propagation_engine()

        # 语义冷启动（种子词 -> 语义图谱）
        self.semantic_cold_start = SemanticColdStart(self.config)
        self.semantic_graph: Dict[str, Any] = dict(self.semantic_cold_start.graph)
        


    def _init_propagation_engine(self):
        """初始化全球流动性传播引擎"""
        try:
            from .liquidity import PropagationEngine
            self.propagation_engine = PropagationEngine()
            self.propagation_engine.initialize()
            _cognition_debug_log("[NewsMind] 全球流动性传播引擎初始化完成")
        except Exception as e:
            _cognition_debug_log(f"[NewsMind] 全球流动性传播引擎初始化失败: {e}")
            self.propagation_engine = None

    def update_liquidity_market(
        self,
        market_id: str,
        price: float,
        volume: float = 0,
        narrative_score: float = 0.0,
    ):
        """更新市场状态到流动性传播引擎"""
        if not self.propagation_engine:
            return
        self.propagation_engine.update_market(
            market_id=market_id,
            price=price,
            volume=volume,
            narrative_score=narrative_score,
        )

    def update_liquidity_narrative(self, narrative: str, attention_score: float):
        """更新叙事状态到流动性传播引擎"""
        if not self.propagation_engine:
            return
        self.propagation_engine.update_narrative_state(narrative, attention_score)

    def get_liquidity_structure(self) -> Dict[str, Any]:
        """获取全球流动性结构"""
        if not self.propagation_engine:
            return {"error": "传播引擎未初始化"}
        return self.propagation_engine.get_liquidity_structure()

    def decay_liquidity_attention(self):
        """衰减流动性注意力（周期性调用）"""
        if not self.propagation_engine:
            return
        self.propagation_engine.decay_all_attention()

    def _get_dynamic_mid_memory_threshold(self) -> float:
        """获取动态中期记忆阈值（委托给 MemoryManager）"""
        return self.memory.get_dynamic_mid_threshold()

    def _compute_freshness_weight(self, timestamp: float, half_life: float) -> float:
        """计算时间戳的新鲜度权重（委托给 MemoryManager）"""
        return MemoryManager.compute_freshness(timestamp, half_life)

    def _decay_memory(self):
        """惰性衰减记忆（委托给 MemoryManager）"""
        self.memory.decay(topics=self.topics)

    def reinforce_event(self, event_id: str, reward: float):
        """强化记忆事件（委托给 MemoryManager）"""
        self.memory.reinforce(event_id, reward)

    def process_record(self, record: Dict) -> List[Dict]:
        """
        处理单条记录（naja策略接口）


            record: 数据源记录（单个dict或包含data字段的dict）


            信号列表
        """
        # 惰性衰减记忆
        self._decay_memory()

        # 检测是否是 numpy 数组
        # Defensive: ensure stats has required keys
        import numpy as np
        if isinstance(record, np.ndarray):
            import logging
            logging.warning(f"[NewsMind] 收到 numpy 数组数据，已跳过: type={type(record)}, shape={getattr(record, 'shape', 'N/A')}")
            return []
        
        # 检测是否是批量数据（列表）
        if isinstance(record, list):
            return self.process_batch(record)
        
        # 检测是否是包装格式（包含data字段，data是列表）
        if isinstance(record, dict) and 'data' in record:
            data = record['data']
            if isinstance(data, list):
                return self.process_batch(data)
        
        # 单条数据处理
        signals = []

        # ========== 雷达调试日志 ==========
        if os.environ.get("NAJA_RADAR_DEBUG") == "true":
            import logging
            log = logging.getLogger(__name__)
            _type = record.get('type', 'unknown') if isinstance(record, dict) else type(record).__name__
            _title = record.get('title', '')[:50] if isinstance(record, dict) else str(record)[:50]
            log.info(f"[Radar-Debug] process_record: type={_type}, title={_title}")

        # 1. 转换为龙虾事件
        event = NewsEvent.from_datasource_record(record)

        # 1.5 注意力门控（频率+重要性）
        if self.enable_attention_filter and not self._should_ingest_event(event):
            self.stats["filtered_events"] = self.stats.get("filtered_events", 0) + 1
            return []

        # 2. 语义编码（改进版：使用关键词特征向量 + 数据源特征 + 事件类型特征）
        event.attention_score = self.attention_scorer.score(event)

        # 4. 主题聚类
        topic_id = self._assign_topic(event)
        event.topic_id = topic_id

        _cognition_debug_log(f"注意力评分: {event.attention_score:.3f}, 阈值={self.attention_threshold}, 主题ID={topic_id}")
        _radar_debug_log(f"  [process_record] attention_score={event.attention_score:.3f}, threshold={self.attention_threshold}, topic_id={topic_id}")

        # 4.5 叙事追踪（避免对叙事/雷达/注意力事件重复触发）
        narrative_signals = self._process_narratives(event)
        if narrative_signals:
            _cognition_debug_log(f"叙事信号: {len(narrative_signals)} 个")

        # 5. 存入短期记忆
        self.short_memory.append(event)
        self.stats["total_events"] += 1

        # 6. 归档到中期记忆（高注意力事件，使用动态阈值）
        dynamic_threshold = self._get_dynamic_mid_memory_threshold()
        if event.attention_score >= dynamic_threshold:
            self.mid_memory.append({
                "id": event.id,
                "timestamp": event.timestamp,
                "source": event.source,
                "event_type": event.event_type,
                "content": event.content,
                "attention_score": event.attention_score,
                "topic_id": event.topic_id,
            })
            _cognition_debug_log(f"归档中期记忆: attention_score={event.attention_score:.3f} >= threshold={dynamic_threshold:.3f}")

        # 7. 检查是否需要生成长期记忆
        self._update_long_memory()

        # 8. 生成信号
        signals.extend(self._generate_signals_for_event(event, topic_id))

        # 9. 漂移检测
        if self.drift_detector and event.vector:
            signals.extend(self._check_drift(event))

        signals.extend(narrative_signals)

        # ========== 雷达调试日志 ==========
        if os.environ.get("NAJA_RADAR_DEBUG") == "true" and signals:
            import logging
            log = logging.getLogger(__name__)
            for sig in signals:
                sig_type = sig.get('signal_type', 'unknown')
                sig_score = sig.get('score', 0)
                log.info(f"[Radar-Debug] 生成信号: type={sig_type}, score={sig_score:.3f}")

        # ========== 认知调试日志 ==========
        if signals:
            _cognition_debug_log(f"生成信号: {[sig.get('type', 'unknown') for sig in signals]}")
        else:
            _cognition_debug_log(f"未生成信号: attention_score={event.attention_score:.3f} < threshold={self.attention_threshold}")

        return signals
    
    def process_batch(self, records: List[Dict]) -> List[Dict]:
        """
        批量处理记录列表（支持一次性处理多条数据）

        Args:
            records: 数据源记录列表

        Returns:
            信号列表
        """
        # 惰性衰减记忆
        self._decay_memory()

        all_signals = []
        
        if not records:
            return all_signals
        
        # 用于去重的已见内容集合
        seen_contents = set()
        
        # 检测 numpy 数组
        # Defensive: ensure stats has required keys (in case of loaded state without them)
        import numpy as np
        filtered_records = [r for r in records if not isinstance(r, np.ndarray)]
        removed_count = len(records) - len(filtered_records)
        if removed_count > 0:
            import logging
            logging.warning(f"[NewsMind] 批量数据中包含 {removed_count} 个 numpy 数组，已过滤")
        records = filtered_records
        
        # 逐条处理，但进行去重检测
        candidates = []
        for record in records:
            event = NewsEvent.from_datasource_record(record)
            
            # 简单去重：基于内容hash
            content_hash = hash(event.content[:100])
            if content_hash in seen_contents:
                continue
            seen_contents.add(content_hash)

            if self.enable_attention_filter and not self._should_ingest_event(event):
                self.stats["filtered_events"] = self.stats.get("filtered_events", 0) + 1
                continue

            # 预评分用于批量筛选
            event.attention_score = self.attention_scorer.peek_score(event)
            candidates.append(event)

        if len(candidates) > self.max_batch_keep:
            candidates.sort(key=lambda e: e.attention_score, reverse=True)
            candidates = candidates[: self.max_batch_keep]

        for event in candidates:
            # 语义编码
            event.vector = self._simple_embedding(event.content, event.source, event.event_type)
            
            # 注意力评分（批量模式下使用相同的scorer）
            event.attention_score = self.attention_scorer.score(event)
            
            # 主题聚类
            topic_id = self._assign_topic(event)
            event.topic_id = topic_id

            narrative_signals = self._process_narratives(event)
            
            # 存入短期记忆
            self.short_memory.append(event)
            self.stats["total_events"] += 1
            
            # 归档到中期记忆（使用动态阈值）
            dynamic_threshold = self._get_dynamic_mid_memory_threshold()
            if event.attention_score >= dynamic_threshold:
                self.mid_memory.append({
                    "id": event.id,
                    "timestamp": event.timestamp,
                    "source": event.source,
                    "event_type": event.event_type,
                    "content": event.content,
                    "attention_score": event.attention_score,
                    "topic_id": event.topic_id,
                })
            
            # 生成信号
            all_signals.extend(self._generate_signals_for_event(event, topic_id))
            all_signals.extend(narrative_signals)
            
            # 漂移检测
            if self.drift_detector and event.vector:
                all_signals.extend(self._check_drift(event))
        
        # 批量处理后检查是否需要生成长期记忆
        self._update_long_memory()
        
        # 批量处理完成后，如果累积数据足够，进行窗口分析
        if len(self.short_memory) >= 100:
            window_signals = self._analyze_window()
            all_signals.extend(window_signals)
        
        return all_signals

    def _should_ingest_event(self, event: NewsEvent) -> bool:
        """
        根据频率与注意力门控决定是否纳入记忆
        
        改进版：增加价值驱动豁免逻辑，确保高价值事件不被过滤
        """
        # ========== 价值驱动豁免逻辑 ==========
        
        # 1. 注意力/雷达事件直接放行
        if event.source.startswith("attention:") or event.source.startswith("radar:"):
            return True

        # 2. 高重要性直接放行
        importance = str(event.meta.get("importance", "")).lower()
        if importance == "high":
            return True

        # 3. 首次出现的话题（新主题）直接放行
        if self._is_first_appearance_topic(event):
            return True

        # 4. 重大关键词触发（政策、突发、革命性变化）直接放行
        if self._has_critical_keywords(event):
            return True

        # 5. 新数据源类型首次出现直接放行
        if self._is_new_event_type(event):
            return True
        
        # ========== 频率/评分门控逻辑 ==========
        
        # 计算当前频率
        bucket = self._rate_buckets.setdefault(event.event_type, deque())
        now_ts = time.time()
        cutoff = now_ts - self.rate_window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        bucket.append(now_ts)
        rate_per_min = len(bucket) / max(1.0, self.rate_window_seconds / 60.0)

        # 动态门槛：频率越高，门槛越高
        rate_factor = min(1.5, rate_per_min / max(1.0, self.target_rate_per_min))
        dynamic_gate = min(0.9, self.base_attention_gate + rate_factor * 0.25)

        # 预评分（不写历史）
        pre_score = self.attention_scorer.peek_score(event)
        if pre_score >= dynamic_gate:
            return True

        return False
    
    def _is_first_appearance_topic(self, event: NewsEvent) -> bool:
        """检测是否是首次出现的话题（新话题萌芽期）"""
        if not self.topics:
            return True
        
        if event.vector is None:
            return False
        
        for topic in self.topics.values():
            if topic.event_count <= 2:
                sim = self._cosine_similarity(event.vector, topic.center)
                if sim > self.topic_threshold * 0.8:
                    return False
        
        return True
    
    def _has_critical_keywords(self, event: NewsEvent) -> bool:
        """检测是否包含重大关键词（政策、突发等）"""
        CRITICAL_KEYWORDS = [
            "政策", "监管", "改革", "革命", "突破", "重大", "紧急", "突发",
            "制裁", "禁止", "限制", "放开", "降准", "加息", "缩表",
            "战争", "灾难", "黑天鹅", "灰犀牛",
            "OpenAI", "英伟达", "ChatGPT", "AI", "人工智能",
        ]
        
        content_lower = event.content.lower()
        for kw in CRITICAL_KEYWORDS:
            if kw in event.content or kw.lower() in content_lower:
                return True
        
        return False
    
    def _is_new_event_type(self, event: NewsEvent) -> bool:
        """检测是否是新的事件类型（数据源的首条消息）"""
        seen_types = set()
        for e in self.short_memory:
            seen_types.add((e.source, e.event_type))
        
        return (event.source, event.event_type) not in seen_types
    
    def _generate_signals_for_event(self, event: NewsEvent, topic_id: Optional[int]) -> List[Dict]:
        """为单个事件生成信号"""
        signals = []

        _radar_debug_log(f"[_generate_signals_for_event] event: attention_score={event.attention_score:.3f}, threshold={self.attention_threshold}, topic_id={topic_id}")

        # 高注意力信号
        if event.attention_score >= self.attention_threshold:
            sig = self._create_signal(
                SignalType.TOPIC_HIGH_ATTENTION,
                event,
                f"高注意力事件: {event.content[:50]}...",
                {"attention_score": event.attention_score}
            )
            signals.append(sig)
            _radar_debug_log(f"  -> 生成 TOPIC_HIGH_ATTENTION 信号: score={sig.get('score', 0):.3f}")
            self.stats["high_attention_events"] += 1

        # 主题相关信号
        if topic_id is not None and topic_id in self.topics:
            topic = self.topics[topic_id]
            topic_name = topic.display_name

            _radar_debug_log(f"  主题: {topic_name}, event_count={topic.event_count}, growth_rate={topic.growth_rate:.3f}")

            # 新主题信号
            if topic.event_count == 1:
                sig = self._create_signal(
                    SignalType.TOPIC_EMERGE,
                    event,
                    f"新主题出现: {topic_name}",
                    {"topic_id": topic_id, "topic_name": topic_name, "event_type": event.event_type}
                )
                signals.append(sig)
                _radar_debug_log(f"  -> 生成 TOPIC_EMERGE 信号: {topic_name}")

            # 主题增长信号
            elif topic.growth_rate > 0.5:
                sig = self._create_signal(
                    SignalType.TOPIC_GROW,
                    event,
                    f"主题快速增长: {topic_name}",
                    {"topic_id": topic_id, "topic_name": topic_name, "growth_rate": topic.growth_rate}
                )
                signals.append(sig)
                _radar_debug_log(f"  -> 生成 TOPIC_GROW 信号: {topic_name}, growth={topic.growth_rate:.3f}")

        if not signals:
            _radar_debug_log(f"  -> 未生成任何信号")

        return signals
    
    def _check_drift(self, event: NewsEvent) -> List[Dict]:
        """检查叙事漂移 (Cognition 认知层职责)"""
        signals = []
        if self.drift_detector and event.vector:
            self.drift_detector.update(event.attention_score)
            if self.drift_detector.drift_detected:
                signals.append(self._create_signal(
                    SignalType.NARRATIVE_DRIFT,
                    event,
                    "Cognition认知层检测到叙事漂移",
                    {"drift_point": self.stats["total_events"]}
                ))
                self.stats["drifts_detected"] += 1
        return signals

    def _process_narratives(self, event: NewsEvent) -> List[Dict]:
        """叙事追踪与事件桥接"""
        if not self.narrative_tracker or not self.narrative_tracker.enabled:
            return []
        if event.source.startswith(("narrative:", "radar:", "attention:")):
            return []
        narrative_events = self.narrative_tracker.ingest_event(event)
        if narrative_events:
            self.narrative_events.extend(narrative_events)
            self._emit_narrative_events(narrative_events)
        return narrative_events

    def _emit_narrative_events(self, events: List[Dict[str, Any]]) -> None:
        try:
            from deva.naja.cognition.insight import emit_to_insight_pool
        except Exception:
            return

        for event in events:
            event_type = str(event.get("event_type", "narrative_event"))
            narrative = str(event.get("narrative", "unknown"))
            score = float(event.get("attention_score", 0.0) or 0.0)
            message = (
                f"叙事{narrative}进入{event.get('stage', '')}"
                if event_type == "narrative_stage_change"
                else f"叙事{narrative}注意力飙升"
            )

            insight_data = {
                "source": "narrative_tracker",
                "signal_type": event_type,
                "narrative": narrative,
                "stage": event.get("stage", ""),
                "attention_score": score,
                "score": score,
                "message": message,
                "keywords": event.get("keywords", []),
                "metrics": event.get("metrics", {}),
                "timestamp": event.get("timestamp", time.time()),
            }
            emit_to_insight_pool(insight_data)

            if self.propagation_engine:
                self.propagation_engine.update_narrative_state(narrative, score)

    def build_semantic_cold_start_prompt(self, seeds: Optional[List[str]] = None) -> str:
        """构建语义冷启动 prompt（给 LLM 使用）"""
        if not self.semantic_cold_start:
            return ""
        return self.semantic_cold_start.build_prompt(seeds)

    def apply_semantic_cold_start(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """应用 LLM 冷启动输出，更新语义图谱"""
        if not self.semantic_cold_start:
            return {}
        self.semantic_graph = self.semantic_cold_start.apply_graph_payload(payload)
        return self.semantic_graph
    
    def process_window(self, records: List[Dict]) -> List[Dict]:
        """
        处理窗口数据（naja策略接口）
        
        Args:
            records: 窗口内的记录列表
            
        Returns:
            信号列表
        """
        all_signals = []
        for record in records:
            signals = self.process_record(record)
            all_signals.extend(signals)
        
        # 窗口级别的分析
        if len(self.short_memory) >= 100:
            window_signals = self._analyze_window()
            all_signals.extend(window_signals)
        
        return all_signals
    
    def _simple_embedding(self, text: str, source: str = "unknown", event_type: str = "text") -> List[float]:
        """
        简化版语义编码 - 改进版
        
        使用关键词特征向量 + 数据源特征 + 事件类型特征
        数据源特征权重更高，确保不同数据源的数据形成不同主题
        """
        text_lower = text.lower()
        vector = []
        
        # 1. 数据源类型特征 (10维，高权重) - 让不同数据源的数据更容易区分
        # 使用 one-hot 编码，每个数据源有独立的维度
        source_onehot = {
            "行情回放":    [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "tick":        [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "quant":       [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "系统日志监控": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "日志":        [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "log":         [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "下载目录监控": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "文件":        [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "file":        [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "财经新闻":    [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "新闻":        [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "news":        [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }
        
        source_vec = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        matched = False
        for key, vec in source_onehot.items():
            if key in source:
                source_vec = vec
                matched = True
                break
        
        # 如果没有匹配到已知数据源，使用最后一个维度作为"其他"
        if not matched:
            source_vec = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        
        vector.extend(source_vec)
        
        # 2. 事件类型特征 (3维)
        type_features = {
            "tick": [1.0, 0.0, 0.0],
            "trade": [0.8, 0.2, 0.0],
            "array": [0.0, 1.0, 0.0],
            "text": [0.0, 0.0, 1.0],
            "dict": [0.3, 0.3, 0.4],
        }
        type_vec = type_features.get(event_type, [0.0, 0.0, 1.0])
        vector.extend(type_vec)
        
        # 3. 金融关键词特征 (5维) - 行情数据
        finance_keywords = ["price", "volume", "涨", "跌", "买", "卖"]
        for kw in finance_keywords:
            count = text_lower.count(kw.lower())
            vector.append(min(1.0, count * 0.3))
        
        # 4. 日志关键词特征 (3维) - 日志数据
        log_keywords = ["error", "warn", "info"]
        for kw in log_keywords:
            count = text_lower.count(kw.lower())
            vector.append(min(1.0, count * 0.3))
        
        # 5. 文件关键词特征 (3维) - 文件数据
        file_keywords = [".py", ".txt", ".csv"]
        for kw in file_keywords:
            count = text_lower.count(kw.lower())
            vector.append(min(1.0, count * 0.3))
        
        # 6. 文本统计特征 (3维)
        vector.append(min(1.0, len(text) / 1000))  # 长度
        vector.append(min(1.0, text.count("!") * 0.1))  # 感叹号
        vector.append(min(1.0, sum(c.isdigit() for c in text) / max(len(text), 1)))  # 数字比例
        
        return vector
    
    def _assign_topic(self, event: NewsEvent) -> Optional[int]:
        """分配主题"""
        if event.vector is None:
            return None
        
        # 使用River聚类
        if self.clustering:
            # River DBSTREAM 期望输入是字典格式，不是 numpy 数组
            vector_dict = {i: v for i, v in enumerate(event.vector)}
            self.clustering.learn_one(vector_dict)
            # DBSTREAM不直接返回标签，我们使用距离最近的主题
            topic_id = self._find_nearest_topic(event.vector)
        else:
            topic_id = self._find_nearest_topic(event.vector)
        
        # 创建新主题
        if topic_id is None or topic_id not in self.topics:
            if len(self.topics) < self.max_topics:
                self.topic_counter += 1
                topic_id = self.topic_counter
                self.topics[topic_id] = Topic(
                    id=topic_id,
                    center=event.vector.copy(),
                    events=deque(maxlen=1000),
                    created_at=datetime.now(),
                    last_updated=datetime.now(),
                )
                self.stats["topics_created"] += 1
        
        # 更新主题
        if topic_id in self.topics:
            topic = self.topics[topic_id]
            topic.events.append(event)
            topic.last_updated = datetime.now()
            topic.attention_sum += event.attention_score
            topic.event_count += 1
            
            # 更新主题中心（移动平均）
            alpha = 0.1
            topic.center = [
                (1 - alpha) * c + alpha * v
                for c, v in zip(topic.center, event.vector)
            ]
            
            # 更新主题名称
            topic.update_name()
        
        return topic_id
    
    def _find_nearest_topic(self, vector: List[float]) -> Optional[int]:
        """找到最近的现有主题"""
        if not self.topics:
            return None
        
        best_topic = None
        best_similarity = -1
        
        for topic_id, topic in self.topics.items():
            sim = self._cosine_similarity(vector, topic.center)
            if sim > best_similarity and sim > self.topic_threshold:
                best_similarity = sim
                best_topic = topic_id
        
        return best_topic
    
    def _analyze_window(self) -> List[Dict]:
        """分析窗口数据，生成高级信号"""
        signals = []
        
        # 检查主题消退
        one_hour_ago = datetime.now() - timedelta(hours=1)
        for topic_id, topic in self.topics.items():
            if topic.last_updated < one_hour_ago and topic.event_count > 10:
                topic_name = topic.display_name
                signals.append(self._create_signal(
                    SignalType.TOPIC_FADE,
                    None,
                    f"主题消退: {topic_name}",
                    {"topic_id": topic_id, "topic_name": topic_name, "last_active": topic.last_updated.isoformat()}
                ))
        
        return signals
    
    def _update_long_memory(self):
        """更新长期记忆（委托给 MemoryManager）"""
        self.memory.update_long_memory(topics=self.topics)
    
    
    def _create_signal(self, signal_type: SignalType, event: Optional[NewsEvent],
                       message: str, data: Dict) -> Dict:
        """创建信号"""
        return {
            "type": signal_type.value,
            "timestamp": datetime.now().isoformat(),
            "event_id": event.id if event else None,
            "message": message,
            "data": data,
            "priority": "high" if signal_type in [SignalType.TOPIC_HIGH_ATTENTION, SignalType.NARRATIVE_DRIFT] else "normal",
        }
    
    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """余弦相似度"""
        v1, v2 = np.array(v1), np.array(v2)
        norm = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norm == 0:
            return 0.0
        return float(np.dot(v1, v2) / norm)
    
    def get_memory_report(self) -> Dict:
        """获取记忆报告"""
        # 主题排序（按活跃度），过滤掉噪音主题
        sorted_topics = sorted(
            self.topics.values(),
            key=lambda t: t.event_count,
            reverse=True
        )
        # 只保留股票相关主题
        stock_topics = [t for t in sorted_topics if _is_stock_relevant_topic(t)]
        
        # 三层记忆统计
        short_term_data = self._get_short_term_memory_data()
        mid_term_data = self._get_mid_term_memory_data()
        long_term_data = self._get_long_term_memory_data()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "stats": self.stats,
            "memory_layers": {
                "short": {
                    "size": len(self.short_memory),
                    "capacity": self.short_term_size,
                    "description": "最近的事件流",
                    "data": short_term_data,
                },
                "mid": {
                    "size": len(self.mid_memory),
                    "capacity": 5000,
                    "threshold": self.mid_memory_threshold,
                    "description": "高注意力事件归档",
                    "data": mid_term_data,
                },
                "long": {
                    "size": len(self.long_memory),
                    "capacity": 30,
                    "interval_hours": self.long_memory_interval,
                    "description": "周期性总结",
                    "data": long_term_data,
                },
            },
            "active_topics": len(stock_topics),
            "top_topics": [
                {
                    "id": t.id,
                    "name": t.display_name,
                    "keywords": t.keywords,
                    "event_count": t.event_count,
                    "avg_attention": round(t.avg_attention, 3),
                    "growth_rate": round(t.growth_rate, 3),
                    "created_at": t.created_at.isoformat(),
                    "last_updated": t.last_updated.isoformat(),
                }
                for t in stock_topics[:10]
            ],
            "recent_high_attention": [
                {
                    "id": e.id,
                    "timestamp": e.timestamp.isoformat() if isinstance(e.timestamp, datetime) else str(e.timestamp),
                    "source": e.source,
                    "type": e.event_type,
                    "score": round(e.attention_score, 3),
                    "content": e.content[:100] + "..." if len(e.content) > 100 else e.content,
                }
                for e in list(self.short_memory)[-20:]
                if e.attention_score >= self.attention_threshold
            ][-5:],
            "user_focus": self._get_user_focus_events(limit=8),
            "narratives": self._get_narratives_report(),
            "semantic_graph": self.semantic_cold_start.get_summary(limit=10) if self.semantic_cold_start else {},
        }

    def _get_narratives_report(self) -> Dict[str, Any]:
        """从短期记忆动态计算叙事报告"""
        if not self.narrative_tracker:
            return {"summary": [], "graph": {"nodes": [], "edges": []}, "events": []}

        recent_events = list(self.short_memory)[-500:]
        if not recent_events:
            return {
                "summary": self.narrative_tracker.get_summary(limit=10),
                "graph": self.narrative_tracker.get_graph(),
                "events": list(self.narrative_events)[-10:],
            }

        keyword_hits: Dict[str, Dict[str, Any]] = {}
        cooccurrence: Dict[Tuple[str, str], int] = {}
        now_ts = datetime.now().timestamp()
        recent_window = 6 * 3600
        prev_window = 6 * 3600

        for event in recent_events:
            event_ts = getattr(event, "timestamp", None)
            if isinstance(event_ts, datetime):
                event_ts = event_ts.timestamp()
            elif not isinstance(event_ts, float):
                event_ts = now_ts

            if now_ts - event_ts > recent_window + prev_window:
                continue

            content = getattr(event, "content", "") or ""
            meta = getattr(event, "meta", {}) or {}
            for key in ("title", "topic", "block", "industry", "theme", "summary"):
                val = meta.get(key)
                if val:
                    content += " " + str(val)

            for key in ("tags", "keywords", "narratives", "narrative"):
                val = meta.get(key)
                if isinstance(val, list):
                    content += " " + " ".join(str(v) for v in val)
                elif val:
                    content += " " + str(val)

            if not content:
                continue

            content_lower = content.lower()
            matched_narratives: List[str] = []

            for narrative, keywords in self.narrative_tracker._keywords.items():
                if narrative not in keyword_hits:
                    keyword_hits[narrative] = {
                        "name": narrative,
                        "recent_hits": 0,
                        "prev_hits": 0,
                        "attention_sum": 0.0,
                        "recent_ts": 0.0,
                        "last_keywords": [],
                    }

                hit_kws = []
                for kw in keywords:
                    if kw.lower() in content_lower if kw.isascii() else kw in content:
                        hit_kws.append(kw)

                if hit_kws:
                    matched_narratives.append(narrative)
                    event_age = now_ts - event_ts
                    if event_age <= recent_window:
                        keyword_hits[narrative]["recent_hits"] += 1
                        if event_ts > keyword_hits[narrative]["recent_ts"]:
                            keyword_hits[narrative]["recent_ts"] = event_ts
                            keyword_hits[narrative]["last_keywords"] = hit_kws
                    elif event_age <= recent_window + prev_window:
                        keyword_hits[narrative]["prev_hits"] += 1

                    att_score = float(getattr(event, "attention_score", 0.0))
                    keyword_hits[narrative]["attention_sum"] += att_score

            for i, nar1 in enumerate(matched_narratives):
                for nar2 in matched_narratives[i + 1:]:
                    key = tuple(sorted([nar1, nar2]))
                    cooccurrence[key] = cooccurrence.get(key, 0) + 1

        summary = []
        for narrative, data in keyword_hits.items():
            recent_count = data["recent_hits"]
            prev_count = data["prev_hits"]
            attention_avg = data["attention_sum"] / max(1, recent_count + prev_count)
            trend = (recent_count - prev_count) / max(1, prev_count)

            import math
            count_score = 1.0 - math.exp(-recent_count / max(self.narrative_tracker._count_scale, 1e-6))
            attention_score = 0.6 * count_score + 0.4 * attention_avg

            if recent_count <= self.narrative_tracker._fade_count and attention_score <= self.narrative_tracker._fade_score:
                stage = "消退"
            elif recent_count >= self.narrative_tracker._peak_count or attention_score >= self.narrative_tracker._peak_score:
                stage = "高潮"
            elif recent_count >= self.narrative_tracker._spread_count or trend >= self.narrative_tracker._trend_threshold or attention_score >= self.narrative_tracker._spread_score:
                stage = "扩散"
            else:
                stage = "萌芽"

            summary.append({
                "narrative": data["name"],
                "stage": stage,
                "attention_score": round(attention_score, 3),
                "recent_count": recent_count,
                "trend": round(trend, 3),
                "last_updated": data["recent_ts"],
                "keywords": data["last_keywords"][:5],
            })

        summary.sort(key=lambda x: x["attention_score"], reverse=True)

        tracker_summary = self.narrative_tracker.get_summary(limit=10)
        if not summary and tracker_summary:
            summary = tracker_summary

        graph = self.narrative_tracker.get_graph()
        if not graph.get("nodes") and summary:
            max_score = max(s["attention_score"] for s in summary) if summary else 1.0
            nodes = []
            for s in summary:
                nodes.append({
                    "id": s["narrative"],
                    "stage": s["stage"],
                    "attention_score": s["attention_score"],
                    "recent_count": s["recent_count"],
                })

            edges = []
            min_weight = 0.2
            for (src, tgt), weight in cooccurrence.items():
                norm_weight = min(1.0, weight / 10.0)
                if norm_weight >= min_weight:
                    edges.append({
                        "source": src,
                        "target": tgt,
                        "weight": round(norm_weight, 3),
                    })

            edges.sort(key=lambda e: e["weight"], reverse=True)
            graph = {"nodes": nodes, "edges": edges[:15]}

        return {
            "summary": summary[:10],
            "graph": graph,
            "events": list(self.narrative_events)[-10:],
        }

    def _get_user_focus_events(self, limit: int = 8) -> List[Dict[str, Any]]:
        """基于双注意力计算用户重点记忆"""
        events = list(self.short_memory)[-200:]
        if not events:
            return []

        scored = []
        now_ts = datetime.now().timestamp()
        for event in events:
            system_attention = float(getattr(event, "attention_score", 0.0))
            confidence = 0.4
            actionability = 0.3
            novelty = 0.5

            meta = getattr(event, "meta", {}) or {}
            importance = str(meta.get("importance", "")).lower()
            if importance == "high":
                confidence = 0.8
            elif importance == "medium":
                confidence = 0.6

            if event.event_type in {"tick"}:
                actionability = 0.6
            if meta.get("symbol") or meta.get("code"):
                actionability = max(actionability, 0.7)

            # 简单新颖度：用时间差近似
            ts = event.timestamp.timestamp() if isinstance(event.timestamp, datetime) else now_ts
            delta = max(0.0, now_ts - ts)
            novelty = min(1.0, delta / 3600.0)

            user_score = (
                0.4 * system_attention
                + 0.2 * confidence
                + 0.2 * actionability
                + 0.2 * novelty
            )

            theme = meta.get("topic") or meta.get("block") or meta.get("industry") or event.event_type
            summary = event.content[:80] + ("..." if len(event.content) > 80 else "")

            scored.append(
                {
                    "id": event.id,
                    "timestamp": event.timestamp.isoformat() if isinstance(event.timestamp, datetime) else str(event.timestamp),
                    "theme": str(theme),
                    "summary": summary,
                    "user_score": round(user_score, 3),
                    "system_attention": round(system_attention, 3),
                }
            )

        scored.sort(key=lambda x: x["user_score"], reverse=True)
        return scored[: max(1, int(limit))]

    def get_attention_hints(self, lookback: int = 200) -> Dict[str, Any]:
        """
        从记忆中提取可用于注意力系统的提示（带权重版）。

        返回:
            {
                "symbols": {"SYMBOL": weight, ...},  # 权重 = 平均注意力 * 频率归一化
                "blocks": {"BLOCK": weight, ...},
            }
        """
        symbol_scores: Dict[str, List[float]] = {}
        block_scores: Dict[str, List[float]] = {}

        recent_events = list(self.short_memory)[-max(1, int(lookback)):]
        for event in recent_events:
            meta = getattr(event, "meta", {}) or {}
            attention = getattr(event, "attention_score", 0.5)

            for key in ("symbol", "code", "ticker", "stock"):
                val = meta.get(key)
                if val:
                    symbol = str(val)
                    if symbol not in symbol_scores:
                        symbol_scores[symbol] = []
                    symbol_scores[symbol].append(attention)

            for key in ("block", "industry", "block_id"):
                val = meta.get(key)
                if val:
                    block = str(val)
                    if block not in block_scores:
                        block_scores[block] = []
                    block_scores[block].append(attention)

        def compute_weight(scores: List[float]) -> float:
            if not scores:
                return 0.0
            avg_attention = sum(scores) / len(scores)
            frequency_factor = min(1.0, len(scores) / 10.0)
            return avg_attention * 0.7 + frequency_factor * 0.3

        symbols_weighted = {
            sym: compute_weight(scores)
            for sym, scores in symbol_scores.items()
        }
        blocks_weighted = {
            sec: compute_weight(scores)
            for sec, scores in block_scores.items()
        }

        return {
            "symbols": symbols_weighted,
            "blocks": blocks_weighted,
        }
    
    def _get_short_term_memory_data(self) -> List[Dict]:
        """获取短期记忆数据（委托给 MemoryManager）"""
        return self.memory.get_short_term_data(limit=10)

    def _get_mid_term_memory_data(self) -> List[Dict]:
        """获取中期记忆数据（委托给 MemoryManager）"""
        return self.memory.get_mid_term_data(limit=10)

    def _get_long_term_memory_data(self) -> List[Dict]:
        """获取长期记忆数据（委托给 MemoryManager）"""
        return self.memory.get_long_term_data(limit=5)
    
    def generate_thought_report(self) -> str:
        """生成思想报告"""
        report = self.get_memory_report()
        
        lines = [
            "=" * 50,
            "🦞 龙虾思想雷达报告",
            "=" * 50,
            f"生成时间: {report['timestamp']}",
            "",
            "📊 统计概览",
            f"  总事件数: {report['stats']['total_events']}",
            f"  高注意力事件: {report['stats']['high_attention_events']}",
            f"  主题数: {report['stats']['topics_created']}",
            f"  漂移检测: {report['stats']['drifts_detected']}",
            "",
            "🔥 热门主题 TOP 5",
        ]
        
        for i, topic in enumerate(report['top_topics'][:5], 1):
            topic_name = topic.get('name', f"主题{topic['id']}")
            keywords = topic.get('keywords', [])
            kw_str = f"[{', '.join(keywords)}]" if keywords else ""
            lines.append(f"  {i}. {topic_name} {kw_str}: {topic['event_count']}事件, "
                        f"注意力{topic['avg_attention']}, 增长率{topic['growth_rate']}")
        
        lines.extend([
            "",
            "⚡ 最近高注意力事件",
        ])
        
        for event in report['recent_high_attention']:
            lines.append(f"  [{event['type']}] 评分{event['score']}: {event['content']}")
        
        lines.append("=" * 50)
        
        return "\n".join(lines)

    def get_topic_signals(self, lookback: int = 50) -> List[Dict]:
        """获取最近的话题信号（供外部系统使用）

        Returns:
            List[Dict]: 话题信号列表，每个包含:
                - type: topic_emerge | topic_grow | topic_high_attention | topic_fade
                - topic_id: 话题ID
                - topic_name: 话题名称
                - confidence: 信号置信度 (0-1)
                - keywords: 话题关键词
                - timestamp: 信号时间
        """
        signals = []
        recent_events = list(self.short_memory)[-max(1, lookback):]

        topic_stats: Dict[str, Dict] = {}
        now_ts = datetime.now().timestamp()

        for event in recent_events:
            if not event.topic_id:
                continue
            if event.topic_id not in topic_stats:
                topic = self.topics.get(event.topic_id)
                topic_stats[event.topic_id] = {
                    "name": topic.display_name if topic else event.topic_id,
                    "keywords": topic.keywords if topic else [],
                    "event_count": 0,
                    "total_attention": 0.0,
                    "last_ts": 0.0,
                }
            stats = topic_stats[event.topic_id]
            stats["event_count"] += 1
            stats["total_attention"] += event.attention_score
            event_ts = event.timestamp.timestamp() if isinstance(event.timestamp, datetime) else now_ts
            if event_ts > stats["last_ts"]:
                stats["last_ts"] = event_ts

        for topic_id, stats in topic_stats.items():
            if stats["event_count"] < 2:
                continue

            avg_attention = stats["total_attention"] / stats["event_count"]
            recent_count = stats["event_count"]

            if recent_count <= 2 and avg_attention < 0.4:
                signal_type = "topic_emerge"
                confidence = 0.3
            elif avg_attention >= 0.7 and recent_count >= 5:
                signal_type = "topic_high_attention"
                confidence = 0.8
            elif recent_count >= 4 and avg_attention >= 0.5:
                signal_type = "topic_grow"
                confidence = 0.6
            elif recent_count <= 2 and avg_attention < 0.3:
                signal_type = "topic_fade"
                confidence = 0.4
            else:
                continue

            signals.append({
                "type": signal_type,
                "topic_id": topic_id,
                "topic_name": stats["name"],
                "confidence": confidence,
                "keywords": stats["keywords"][:5],
                "event_count": recent_count,
                "avg_attention": round(avg_attention, 3),
                "timestamp": datetime.fromtimestamp(stats["last_ts"]).isoformat() if stats["last_ts"] else None,
            })

        signals.sort(key=lambda x: x["confidence"], reverse=True)
        return signals

    def get_market_sentiment_from_news(self) -> Tuple[str, float]:
        """从新闻中分析市场情绪（供外部系统使用）

        Returns:
            Tuple[str, float]: (情绪类型: bullish/neutral/fearful, 置信度 0-1)
        """
        recent_events = list(self.short_memory)[-100:]
        if not recent_events:
            return "neutral", 0.3

        bullish_count = 0
        fearful_count = 0
        total_attention = 0.0
        weighted_sentiment = 0.0

        sentiment_keywords = {
            "bullish": ["上涨", "利好", "突破", "看涨", "业绩增长", "订单", "中标", "超预期"],
            "fearful": ["下跌", "利空", "风险", "看跌", "业绩下滑", "亏损", "调查", "处罚"],
        }

        for event in recent_events:
            total_attention += event.attention_score
            content = event.content.lower()

            bullish_hits = sum(1 for kw in sentiment_keywords["bullish"] if kw.lower() in content)
            fearful_hits = sum(1 for kw in sentiment_keywords["fearful"] if kw.lower() in content)

            if bullish_hits > fearful_hits:
                bullish_count += 1
                weighted_sentiment += event.attention_score * 1
            elif fearful_hits > bullish_hits:
                fearful_count += 1
                weighted_sentiment -= event.attention_score * 1

        if total_attention == 0:
            return "neutral", 0.3

        net_sentiment = weighted_sentiment / total_attention
        total_hits = bullish_count + fearful_count
        hit_ratio = min(1.0, total_hits / max(1, len(recent_events) * 0.3))

        if net_sentiment > 0.3 and bullish_count > fearful_count:
            sentiment = "bullish"
            confidence = min(0.9, 0.5 + hit_ratio * 0.3 + net_sentiment * 0.2)
        elif net_sentiment < -0.3 or fearful_count > bullish_count:
            sentiment = "fearful"
            confidence = min(0.9, 0.5 + hit_ratio * 0.3 + abs(net_sentiment) * 0.2)
        else:
            sentiment = "neutral"
            confidence = 0.4

        return sentiment, round(confidence, 3)

    # ============================================================================
    # 持久化方法
    # ============================================================================
    
    PERSISTENCE_TABLE = "naja_news_radar_state"
    PERSISTENCE_KEY = "news_radar_main"
    PERSISTENCE_LOCK = threading.Lock()
    
    def save_state(self) -> dict:
        """保存雷达策略状态到数据库
        
        Returns:
            保存结果
        """
        if not NAJA_DB_AVAILABLE:
            return {"success": False, "error": "NB not available"}
        
        try:
            with self.PERSISTENCE_LOCK:
                db = NB(self.PERSISTENCE_TABLE)
                
                # 序列化状态
                state_data = self._serialize_state()
                
                # 保存到数据库
                db[self.PERSISTENCE_KEY] = state_data
                
                print(f"[NewsMind] 状态已保存: {len(self.short_memory)} 短期记忆, "
                      f"{len(self.mid_memory)} 中期记忆, {len(self.long_memory)} 长期记忆, "
                      f"{len(self.topics)} 主题")
                
                return {
                    "success": True,
                    "short_memory_count": len(self.short_memory),
                    "mid_memory_count": len(self.mid_memory),
                    "long_memory_count": len(self.long_memory),
                    "topics_count": len(self.topics),
                }
        except Exception as e:
            print(f"[NewsMind] 保存状态失败: {e}")
            return {"success": False, "error": str(e)}
    
    def load_state(self) -> dict:
        """从数据库加载雷达策略状态
        
        Returns:
            加载结果
        """
        if not NAJA_DB_AVAILABLE:
            return {"success": False, "error": "NB not available"}
        
        try:
            with self.PERSISTENCE_LOCK:
                db = NB(self.PERSISTENCE_TABLE)
                
                if self.PERSISTENCE_KEY not in db:
                    print("[NewsMind] 没有找到保存的状态")
                    return {"success": True, "loaded": False, "message": "No saved state found"}
                
                state_data = db.get(self.PERSISTENCE_KEY)
                if not isinstance(state_data, dict):
                    return {"success": False, "error": "Invalid state data format"}
                
                # 反序列化状态
                self._deserialize_state(state_data)
                
                print(f"[NewsMind] 状态已加载: {len(self.short_memory)} 短期记忆, "
                      f"{len(self.mid_memory)} 中期记忆, {len(self.long_memory)} 长期记忆, "
                      f"{len(self.topics)} 主题")
                
                return {
                    "success": True,
                    "loaded": True,
                    "short_memory_count": len(self.short_memory),
                    "mid_memory_count": len(self.mid_memory),
                    "long_memory_count": len(self.long_memory),
                    "topics_count": len(self.topics),
                }
        except Exception as e:
            print(f"[NewsMind] 加载状态失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _serialize_state(self) -> dict:
        """序列化状态为字典"""
        # 记忆部分委托给 MemoryManager
        memory_state = self.memory.serialize_state()

        # 序列化主题
        topics_data = {}
        for topic_id, topic in self.topics.items():
            topics_data[str(topic_id)] = {
                "id": topic.id,
                "center": topic.center,
                "events": list(topic.events)[-100:],
                "created_at": topic.created_at.isoformat(),
                "last_updated": topic.last_updated.isoformat(),
                "attention_sum": topic.attention_sum,
                "event_count": topic.event_count,
                "name": topic.name,
                "keywords": topic.keywords,
            }

        result = {
            "version": 1,
            "saved_at": datetime.now().isoformat(),
            "config": self.config,
            "stats": self.stats,
            "topic_counter": self.topic_counter,
            "topics": topics_data,
            "semantic_graph": self.semantic_graph,
        }
        result.update(memory_state)
        return result
    
    def _deserialize_state(self, data: dict):
        """从字典反序列化状态"""
        # 恢复配置
        self.config = data.get("config", {})
        self.short_term_size = self.config.get("short_term_size", 1000)
        self.topic_threshold = self.config.get("topic_threshold", 0.5)
        self.attention_threshold = self.config.get("attention_threshold", 0.6)
        self.max_topics = self.config.get("max_topics", 50)

        # 恢复统计信息
        default_stats = {
            "total_events": 0,
            "high_attention_events": 0,
            "topics_created": 0,
            "drifts_detected": 0,
            "filtered_events": 0,
        }
        saved_stats = data.get("stats", {})
        self.stats = {**default_stats, **saved_stats}
        self.topic_counter = data.get("topic_counter", 0)
        self.semantic_graph = data.get("semantic_graph", self.semantic_graph or {})

        # 记忆部分委托给 MemoryManager
        def _news_event_factory(e_data):
            event = NewsEvent(
                id=e_data["id"],
                timestamp=datetime.fromisoformat(e_data["timestamp"]),
                source=e_data["source"],
                event_type=e_data["event_type"],
                content=e_data["content"],
                vector=e_data.get("vector"),
                meta=e_data.get("meta", {}),
            )
            event.attention_score = e_data.get("attention_score", 0)
            event.topic_id = e_data.get("topic_id")
            return event

        self.memory.deserialize_state(data, event_factory=_news_event_factory)

        # 同步记忆属性
        self.short_memory = self.memory.short_memory
        self.mid_memory = self.memory.mid_memory
        self.long_memory = self.memory.long_memory
        self.short_term_half_life = self.memory.short_term_half_life
        self.mid_term_half_life = self.memory.mid_term_half_life
        self.topic_half_life = self.memory.topic_half_life
        self.reinforcement_shield = self.memory.reinforcement_shield
        self.mid_memory_threshold = self.memory.mid_memory_threshold
        self.long_memory_interval = self.memory.long_memory_interval
        self.last_long_memory_time = self.memory.last_long_memory_time

        # 恢复主题
        self.topics.clear()
        for topic_id_str, t_data in data.get("topics", {}).items():
            try:
                topic_id = int(topic_id_str)
                topic = Topic(
                    id=t_data["id"],
                    center=t_data["center"],
                    events=deque(maxlen=1000),
                    created_at=datetime.fromisoformat(t_data["created_at"]),
                    last_updated=datetime.fromisoformat(t_data["last_updated"]),
                )
                topic.attention_sum = t_data.get("attention_sum", 0)
                topic.event_count = t_data.get("event_count", 0)
                topic.name = t_data.get("name", "")
                topic.keywords = t_data.get("keywords", [])
                
                # 恢复主题内的事件
                for e_data in t_data.get("events", []):
                    if isinstance(e_data, dict) and "id" in e_data:
                        try:
                            event = NewsEvent(
                                id=e_data["id"],
                                timestamp=datetime.fromisoformat(e_data["timestamp"]) if isinstance(e_data["timestamp"], str) else e_data["timestamp"],
                                source=e_data.get("source", ""),
                                event_type=e_data.get("event_type", ""),
                                content=e_data.get("content", ""),
                            )
                            topic.events.append(event)
                        except:
                            pass
                
                self.topics[topic_id] = topic
            except Exception as e:
                print(f"[NewsMind] 恢复主题失败: {e}")
    
    def clear_saved_state(self) -> dict:
        """清除保存的状态"""
        if not NAJA_DB_AVAILABLE:
            return {"success": False, "error": "NB not available"}
        
        try:
            with self.PERSISTENCE_LOCK:
                db = NB(self.PERSISTENCE_TABLE)
                if self.PERSISTENCE_KEY in db:
                    del db[self.PERSISTENCE_KEY]
                print("[NewsMind] 已清除保存的状态")
                return {"success": True}
        except Exception as e:
            print(f"[NewsMind] 清除状态失败: {e}")
            return {"success": False, "error": str(e)}


# naja策略系统接口
class Strategy:
    """naja策略包装类"""

    def __init__(self, config: Dict = None):
        self.radar = NewsMindStrategy(config)
        self._save_interval = 300  # 默认5分钟保存一次
        self._save_thread = None
        self._stop_save_thread = threading.Event()
        # 启动时自动加载状态
        self._auto_load_on_init()
        # 启动定时保存线程
        self._start_auto_save()
    
    def _auto_load_on_init(self):
        """初始化时自动加载保存的状态"""
        result = self.radar.load_state()
        if result.get("success") and result.get("loaded"):
            print(f"[NewsMind] 策略恢复成功")
        elif not result.get("loaded"):
            print(f"[NewsMind] 没有找到保存的状态，使用新实例")
    
    def _start_auto_save(self):
        """启动定时保存线程"""
        if self._save_thread is not None and self._save_thread.is_alive():
            return
        
        self._stop_save_thread.clear()
        self._save_thread = threading.Thread(target=self._auto_save_loop, daemon=True)
        self._save_thread.start()
        print(f"[NewsMind] 定时保存已启动，间隔 {self._save_interval} 秒")
    
    def _auto_save_loop(self):
        """自动保存循环"""
        while not self._stop_save_thread.is_set():
            # 等待指定时间
            self._stop_save_thread.wait(self._save_interval)
            if self._stop_save_thread.is_set():
                break
            
            # 执行保存
            try:
                result = self.radar.save_state()
                if result.get("success"):
                    print(f"[NewsMind] 定时保存完成")
                else:
                    print(f"[NewsMind] 定时保存失败: {result.get('error')}")
            except Exception as e:
                print(f"[NewsMind] 定时保存异常: {e}")
    
    def _stop_auto_save(self):
        """停止定时保存线程"""
        if self._save_thread is not None:
            self._stop_save_thread.set()
            self._save_thread.join(timeout=5)
            print("[NewsMind] 定时保存已停止")
    
    def on_record(self, record: Dict) -> List[Dict]:
        """逐条处理"""
        return self.radar.process_record(record)
    
    def on_window(self, records: List[Dict]) -> List[Dict]:
        """窗口处理"""
        return self.radar.process_window(records)
    
    def get_report(self) -> Dict:
        """获取报告"""
        return self.radar.get_memory_report()
    
    def get_thought_report(self) -> str:
        """获取思想报告"""
        return self.radar.generate_thought_report()
    
    def save_state(self) -> dict:
        """保存状态（供外部调用）"""
        return self.radar.save_state()
    
    def load_state(self) -> dict:
        """加载状态（供外部调用）"""
        return self.radar.load_state()
    
    def clear_saved_state(self) -> dict:
        """清除保存的状态"""
        return self.radar.clear_saved_state()
    
    def on_stop(self):
        """策略停止时自动保存"""
        print("[NewsMind] 策略停止，自动保存状态...")
        self._stop_auto_save()
        return self.radar.save_state()

    def on_start(self):
        """策略启动时自动加载"""
        print("[NewsMind] 策略启动，自动加载状态...")
        self._start_auto_save()
        return self.radar.load_state()
