"""
MemoryManager - 三层记忆管理

从 core.py 的 NewsMindStrategy 中提取，负责：
- 短期记忆（short_memory）：最近事件流，deque 实现
- 中期记忆（mid_memory）：高注意力事件归档
- 长期记忆（long_memory）：周期性总结
- 记忆衰减（指数衰减 + 强化保护）
- 记忆强化（reinforce_event）
- 长期记忆归档（周期性总结生成）
"""

import time
import math
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, List, Optional, Any, Callable


class MemoryManager:
    """
    三层记忆管理器

    管理短期/中期/长期记忆的存储、衰减、强化和归档。
    不涉及主题管理和信号生成——这些由 NewsMindStrategy 负责。

    使用方式：
        mm = MemoryManager(config)
        mm.append_short(event)
        mm.archive_to_mid(event_dict)
        mm.decay()
        mm.reinforce(event_id, reward)
    """

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}

        # ── 容量 ──
        self.short_term_size = config.get("short_term_size", 1000)

        # ── 三层记忆 ──
        self.short_memory: deque = deque(maxlen=self.short_term_size)
        self.mid_memory: deque = deque(maxlen=5000)
        self.long_memory: List[Dict] = []

        # ── 衰减参数 ──
        self.short_term_half_life = float(config.get("short_term_half_life", 300.0))
        self.mid_term_half_life = float(config.get("mid_term_half_life", 3600.0))
        self.topic_half_life = float(config.get("topic_half_life", 1800.0))
        self._last_decay_time: float = time.time()

        # ── 归档参数 ──
        self.mid_memory_threshold = config.get("mid_memory_threshold", 0.7)
        self.long_memory_interval = config.get("long_memory_interval", 24)  # 小时
        self.last_long_memory_time = datetime.now() - timedelta(hours=24)

        # ── 强化参数 ──
        self.reinforcement_shield = float(config.get("reinforcement_shield", 60.0))

        # ── 动态阈值缓存 ──
        self._cached_market_activity: float = 0.5
        self._last_activity_update: float = 0.0
        self._activity_cache_ttl: float = 5.0
        self._market_activity_fn: Optional[Callable[[], float]] = None

    # ------------------------------------------------------------------
    #  公共 API
    # ------------------------------------------------------------------

    def set_market_activity_fn(self, fn: Callable[[], float]):
        """注入市场活跃度查询函数（避免硬依赖 topic_manager）"""
        self._market_activity_fn = fn

    def append_short(self, event) -> None:
        """将事件追加到短期记忆"""
        self.short_memory.append(event)

    def archive_to_mid(self, event_dict: Dict) -> None:
        """将事件归档到中期记忆"""
        self.mid_memory.append(event_dict)

    def should_archive_to_mid(self, attention_score: float) -> bool:
        """判断事件是否应归档到中期记忆"""
        return attention_score >= self.get_dynamic_mid_threshold()

    def get_dynamic_mid_threshold(self) -> float:
        """
        获取动态中期记忆阈值

        根据市场活跃度动态调整：
        - 活跃（>0.6）：提高阈值，减少噪音
        - 平淡（<0.3）：降低阈值，保留更多信号
        """
        now = time.time()
        if self._market_activity_fn and now - self._last_activity_update > self._activity_cache_ttl:
            self._cached_market_activity = self._market_activity_fn()
            self._last_activity_update = now

        activity = self._cached_market_activity
        base = self.mid_memory_threshold

        if activity > 0.6:
            return min(0.85, base + 0.15)
        elif activity < 0.3:
            return max(0.5, base - 0.2)
        return base

    # ------------------------------------------------------------------
    #  衰减
    # ------------------------------------------------------------------

    @staticmethod
    def compute_freshness(timestamp, half_life: float) -> float:
        """
        计算时间戳的新鲜度权重

        使用指数衰减：weight = exp(-dt / half_life)
        """
        dt = time.time() - timestamp
        if isinstance(timestamp, datetime):
            dt = time.time() - timestamp.timestamp()
        return math.exp(-dt / half_life) if half_life > 0 else 1.0

    def decay(self, topics: Optional[Dict] = None) -> None:
        """
        惰性衰减记忆

        对所有三层记忆执行增量衰减。
        可选传入 topics dict 以同时衰减主题活跃度。
        """
        now = time.time()
        dt = now - self._last_decay_time
        if dt < 10:
            return

        self._last_decay_time = now

        # 短期记忆衰减
        for event in self.short_memory:
            if "timestamp" in event if isinstance(event, dict) else hasattr(event, "timestamp"):
                ts = event["timestamp"] if isinstance(event, dict) else event.timestamp
                freshness = self.compute_freshness(ts, self.short_term_half_life)
                shield_multiplier = 1.0
                last_reinforced = (event.get("last_reinforced") if isinstance(event, dict)
                                   else getattr(event, "last_reinforced", None))
                if last_reinforced:
                    time_since = now - last_reinforced
                    if time_since < self.reinforcement_shield:
                        shield_multiplier = 0.5
                    elif time_since < self.reinforcement_shield * 3:
                        shield_multiplier = 0.75
                score_attr = "attention_score"
                if isinstance(event, dict):
                    event[score_attr] *= freshness * shield_multiplier
                else:
                    event.attention_score *= freshness * shield_multiplier

        # 中期记忆衰减
        for event in self.mid_memory:
            if isinstance(event, dict) and "timestamp" in event:
                freshness = self.compute_freshness(event["timestamp"], self.mid_term_half_life)
                event["attention_score"] *= freshness

        # 主题衰减（可选）
        if topics:
            for topic in topics.values():
                if hasattr(topic, "last_updated") and topic.last_updated:
                    freshness = self.compute_freshness(topic.last_updated, self.topic_half_life)
                    topic.event_count *= freshness

    # ------------------------------------------------------------------
    #  强化
    # ------------------------------------------------------------------

    def reinforce(self, event_id: str, reward: float) -> None:
        """
        强化记忆事件

        Args:
            event_id: 事件 ID
            reward: 奖励值，正增强，负抑制
        """
        now = time.time()

        for event in self.short_memory:
            eid = event.get("id") if isinstance(event, dict) else getattr(event, "id", None)
            if eid == event_id:
                if isinstance(event, dict):
                    event["attention_score"] *= (1 + reward)
                    event["attention_score"] = max(0, min(1, event["attention_score"]))
                    event["last_reinforced"] = now
                    event["reinforce_count"] = event.get("reinforce_count", 0) + 1
                else:
                    event.attention_score *= (1 + reward)
                    event.attention_score = max(0, min(1, event.attention_score))
                    event.last_reinforced = now
                    event.reinforce_count = getattr(event, "reinforce_count", 0) + 1
                break

        for event in self.mid_memory:
            if isinstance(event, dict) and event.get("id") == event_id:
                event["attention_score"] *= (1 + reward)
                event["attention_score"] = max(0, min(1, event["attention_score"]))
                event["last_reinforced"] = now
                break

    # ------------------------------------------------------------------
    #  长期记忆归档
    # ------------------------------------------------------------------

    def update_long_memory(self, topics: Optional[Dict] = None) -> None:
        """
        检查并更新长期记忆（周期性总结）

        Args:
            topics: 当前主题库，用于生成总结中的主题统计
        """
        now = datetime.now()
        if (now - self.last_long_memory_time).total_seconds() < self.long_memory_interval * 3600:
            return

        summary = self._generate_summary(topics)
        self.long_memory.append({
            "timestamp": now.isoformat(),
            "summary": summary,
            "period_start": self.last_long_memory_time.isoformat(),
            "period_end": now.isoformat(),
        })
        if len(self.long_memory) > 30:
            self.long_memory = self.long_memory[-30:]
        self.last_long_memory_time = now

    def _generate_summary(self, topics: Optional[Dict] = None) -> Dict:
        """生成记忆总结"""
        period_start = self.last_long_memory_time
        period_events = [e for e in self.mid_memory if e["timestamp"] >= period_start]

        topic_stats: Dict[int, Dict] = {}
        for event in period_events:
            tid = event.get("topic_id")
            if tid:
                if tid not in topic_stats:
                    topic_name = f"主题{tid}"
                    if topics and tid in topics:
                        topic_name = topics[tid].display_name
                    topic_stats[tid] = {
                        "count": 0,
                        "total_attention": 0,
                        "topic_name": topic_name,
                    }
                topic_stats[tid]["count"] += 1
                topic_stats[tid]["total_attention"] += event["attention_score"]

        sorted_topics = sorted(
            topic_stats.items(),
            key=lambda x: x[1]["count"],
            reverse=True,
        )[:5]

        return {
            "total_events": len(period_events),
            "avg_attention": (
                sum(e["attention_score"] for e in period_events) / len(period_events)
                if period_events else 0
            ),
            "top_topics": [
                {
                    "id": tid,
                    "name": stats["topic_name"],
                    "event_count": stats["count"],
                    "avg_attention": round(
                        stats["total_attention"] / stats["count"], 3
                    ) if stats["count"] > 0 else 0,
                }
                for tid, stats in sorted_topics
            ],
            "event_types": self._count_by_key(period_events, "event_type"),
            "sources": self._count_by_key(period_events, "source"),
        }

    # ------------------------------------------------------------------
    #  数据查询
    # ------------------------------------------------------------------

    def get_short_term_data(self, limit: int = 10) -> List[Dict]:
        """获取短期记忆数据"""
        recent = list(self.short_memory)[-limit:]
        result = []
        for e in reversed(recent):
            if isinstance(e, dict):
                result.append(e)
            else:
                result.append({
                    "id": e.id,
                    "timestamp": e.timestamp.isoformat() if isinstance(e.timestamp, datetime) else str(e.timestamp),
                    "source": e.source,
                    "event_type": e.event_type,
                    "content": e.content[:50] + "..." if len(e.content) > 50 else e.content,
                    "attention_score": round(e.attention_score, 3),
                    "topic_id": e.topic_id,
                })
        return result

    def get_mid_term_data(self, limit: int = 10) -> List[Dict]:
        """获取中期记忆数据"""
        recent = list(self.mid_memory)[-limit:]
        return [
            {
                "id": e["id"],
                "timestamp": e["timestamp"].isoformat() if isinstance(e["timestamp"], datetime) else str(e["timestamp"]),
                "source": e["source"],
                "event_type": e["event_type"],
                "content": e["content"][:50] + "..." if len(e["content"]) > 50 else e["content"],
                "attention_score": round(e["attention_score"], 3),
                "topic_id": e.get("topic_id"),
            }
            for e in reversed(recent)
        ]

    def get_long_term_data(self, limit: int = 5) -> List[Dict]:
        """获取长期记忆数据"""
        recent = self.long_memory[-limit:]
        return [
            {
                "timestamp": s["timestamp"],
                "period_start": s["period_start"],
                "period_end": s["period_end"],
                "summary": s["summary"],
            }
            for s in reversed(recent)
        ]

    # ------------------------------------------------------------------
    #  序列化 / 反序列化
    # ------------------------------------------------------------------

    def serialize_state(self) -> Dict:
        """序列化记忆状态（供 NewsMindStrategy._serialize_state 调用）"""
        short_data = []
        for e in self.short_memory:
            if isinstance(e, dict):
                short_data.append(e)
            else:
                short_data.append({
                    "id": e.id,
                    "timestamp": e.timestamp.isoformat() if isinstance(e.timestamp, datetime) else str(e.timestamp),
                    "source": e.source,
                    "event_type": e.event_type,
                    "content": e.content,
                    "vector": e.vector,
                    "attention_score": e.attention_score,
                    "topic_id": e.topic_id,
                })

        mid_data = []
        for e in self.mid_memory:
            d = dict(e)
            if isinstance(d.get("timestamp"), datetime):
                d["timestamp"] = d["timestamp"].isoformat()
            mid_data.append(d)

        long_data = list(self.long_memory)

        return {
            "short_memory": short_data,
            "mid_memory": mid_data,
            "long_memory": long_data,
            "mid_memory_threshold": self.mid_memory_threshold,
            "long_memory_interval": self.long_memory_interval,
            "last_long_memory_time": self.last_long_memory_time.isoformat(),
            "short_term_half_life": self.short_term_half_life,
            "mid_term_half_life": self.mid_term_half_life,
            "topic_half_life": self.topic_half_life,
            "reinforcement_shield": self.reinforcement_shield,
        }

    def deserialize_state(self, data: Dict, event_factory=None) -> None:
        """
        反序列化记忆状态

        Args:
            data: 序列化数据
            event_factory: 可选，将 dict 转为 NewsEvent 的工厂函数
        """
        self.short_term_half_life = data.get("short_term_half_life", 300.0)
        self.mid_term_half_life = data.get("mid_term_half_life", 3600.0)
        self.topic_half_life = data.get("topic_half_life", 1800.0)
        self.reinforcement_shield = data.get("reinforcement_shield", 60.0)
        self.mid_memory_threshold = data.get("mid_memory_threshold", 0.7)
        self.long_memory_interval = data.get("long_memory_interval", 24)

        last_long_time_str = data.get("last_long_memory_time")
        if last_long_time_str:
            try:
                self.last_long_memory_time = datetime.fromisoformat(last_long_time_str)
            except Exception:
                self.last_long_memory_time = datetime.now() - timedelta(hours=24)

        # 恢复短期记忆
        self.short_memory.clear()
        for e_data in data.get("short_memory", []):
            if event_factory:
                try:
                    event = event_factory(e_data)
                    self.short_memory.append(event)
                except Exception:
                    pass
            else:
                self.short_memory.append(e_data)

        # 恢复中期记忆
        self.mid_memory.clear()
        for e_data in data.get("mid_memory", []):
            if isinstance(e_data.get("timestamp"), str):
                try:
                    e_data["timestamp"] = datetime.fromisoformat(e_data["timestamp"])
                except Exception:
                    pass
            self.mid_memory.append(e_data)

        # 恢复长期记忆
        self.long_memory = data.get("long_memory", [])

    # ------------------------------------------------------------------
    #  内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _count_by_key(events: List[Dict], key: str) -> Dict:
        """按 key 统计事件数量"""
        counts: Dict[str, int] = {}
        for e in events:
            val = e.get(key, "unknown")
            counts[val] = counts.get(val, 0) + 1
        return counts
