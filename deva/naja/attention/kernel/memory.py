"""
AttentionMemory - 持久注意力记忆

提供事件级记忆存储、时间衰减和强化学习支持

衰减机制设计：
1. 惰性衰减：只在 get_focus() 时衰减
2. 增量衰减：每次衰减只计算自上次衰减以来的时间差
3. 分层衰减：根据注意力等级决定衰减速度
4. 强化保护：被强化后的记忆有临时保护窗口

持久化：
- 支持 save_state() / load_state() 持久化到 NB 数据库
"""

import time
import math
from enum import Enum
from typing import Dict, Any, Optional, List

try:
    from deva import NB
    NB_AVAILABLE = True
except ImportError:
    NB_AVAILABLE = False


class AttentionLevel(Enum):
    """注意力等级，决定衰减速度"""
    HIGH = "high"      # score > 0.8, 衰减最慢
    MEDIUM = "medium"  # 0.4 < score <= 0.8, 正常衰减
    LOW = "low"        # score <= 0.4, 衰减最快


class AttentionMemory:
    """
    持久注意力记忆

    属性:
        store: 记忆存储列表
        base_decay_rate: 基准衰减半衰期（秒），默认 300（5分钟）
        reinforcement_shield: 强化保护时间（秒），默认 60
        cleanup_threshold: 清理阈值，低于此分数的记忆被删除
    """

    def __init__(
        self,
        base_decay_rate: float = 300.0,
        reinforcement_shield: float = 60.0,
        cleanup_threshold: float = 0.01
    ):
        """
        初始化注意力记忆

        Args:
            base_decay_rate: 基准衰减半衰期（秒），默认 300（5分钟）
            reinforcement_shield: 强化保护时间（秒），默认 60
            cleanup_threshold: 清理阈值，默认 0.01
        """
        self.store: List[Dict[str, Any]] = []
        self.base_decay_rate = base_decay_rate
        self.reinforcement_shield = reinforcement_shield
        self.cleanup_threshold = cleanup_threshold
        self._last_decay_time: float = time.time()

    def _get_attention_level(self, score: float) -> AttentionLevel:
        """根据分数判断注意力等级"""
        if score > 0.8:
            return AttentionLevel.HIGH
        elif score > 0.4:
            return AttentionLevel.MEDIUM
        else:
            return AttentionLevel.LOW

    def _compute_decay_rate(self, item: Dict[str, Any]) -> float:
        """
        根据记忆属性计算衰减率

        衰减率由以下因素决定：
        1. 注意力等级：高等级衰减更慢
        2. 强化保护：被强化后的记忆有临时保护
        """
        score = item["score"]
        level = self._get_attention_level(score)

        # 1. 根据注意力等级确定基础衰减倍数
        if level == AttentionLevel.HIGH:
            level_multiplier = 2.0  # 高注意力记忆衰减更慢
        elif level == AttentionLevel.MEDIUM:
            level_multiplier = 1.0  # 正常衰减
        else:
            level_multiplier = 0.5  # 低注意力记忆衰减更快

        # 2. 检查强化保护
        shield_multiplier = 1.0
        if "last_reinforced" in item:
            time_since_reinforce = time.time() - item["last_reinforced"]
            if time_since_reinforce < self.reinforcement_shield:
                shield_multiplier = 0.5  # 保护期内衰减减半
            elif time_since_reinforce < self.reinforcement_shield * 3:
                shield_multiplier = 0.75  # 保护期后衰减略微减慢

        # 3. 计算最终衰减率
        return self.base_decay_rate * level_multiplier * shield_multiplier

    def update(
        self,
        event=None,
        score: float = None,
        symbol: str = None,
        alignment: float = None,
        reason: str = None
    ):
        """
        记录一次 attention

        Args:
            event: AttentionEvent 对象 (kernel.py 调用方式)
            score: 注意力分数 (kernel.py 调用方式)
            symbol: 股票代码 (attention_os.py 调用方式)
            alignment: 对齐分数 (attention_os 调用方式)
            reason: 决策原因 (attention_os 调用方式)
        """
        effective_score = score if score is not None else (alignment if alignment is not None else 0.5)
        attention_level = self._get_attention_level(effective_score)

        if symbol is not None:
            self.store.append({
                "symbol": symbol,
                "alignment": alignment,
                "reason": reason,
                "score": effective_score,
                "level": attention_level.value,
                "time": time.time(),
                "last_decay_time": time.time(),
                "reinforce_count": 0,
            })
        else:
            self.store.append({
                "event": event,
                "score": effective_score,
                "level": attention_level.value,
                "time": time.time(),
                "last_decay_time": time.time(),
                "reinforce_count": 0,
            })

    def _lazy_decay(self):
        """
        惰性衰减：只衰减自上次衰减以来的时间差

        使用增量衰减策略，避免累积时间一次性衰减的问题
        """
        now = time.time()

        for item in self.store:
            dt = now - item["last_decay_time"]
            if dt <= 0:
                continue

            decay_rate = self._compute_decay_rate(item)
            item["score"] *= math.exp(-dt / decay_rate)
            item["last_decay_time"] = now

        self._last_decay_time = now

    def _cleanup_low_score(self):
        """清理低分记忆，避免 store 无限增长"""
        original_len = len(self.store)
        self.store = [item for item in self.store if item["score"] > self.cleanup_threshold]
        removed = original_len - len(self.store)
        return removed

    def decay(self):
        """
        显式衰减调用（保持兼容性）

        对于需要主动触发衰减的场景，但推荐使用惰性衰减
        """
        self._lazy_decay()

    def keep_hot(self, event):
        """
        维持事件热度

        Args:
            event: AttentionEvent
        """
        for item in self.store:
            if item.get("event") == event:
                item["score"] = min(1.0, item["score"] * 1.5)
                item["level"] = self._get_attention_level(item["score"]).value
                item["last_reinforced"] = time.time()
                item["reinforce_count"] = item.get("reinforce_count", 0) + 1
                break

    def transfer(self, from_event, to_event):
        """
        注意力转移

        Args:
            from_event: 原事件
            to_event: 目标事件
        """
        for item in self.store:
            if item.get("event") == from_event:
                item["event"] = to_event
                item["time"] = time.time()
                item["last_decay_time"] = time.time()
                break

    def reinforce(self, event, reward: float):
        """
        强化学习反馈

        Args:
            event: AttentionEvent
            reward: 奖励值，正增强，负抑制
        """
        for item in self.store:
            if item.get("event") == event:
                item["score"] *= (1 + reward)
                item["score"] = max(0.0, min(1.0, item["score"]))
                item["level"] = self._get_attention_level(item["score"]).value
                item["last_reinforced"] = time.time()
                item["reinforce_count"] = item.get("reinforce_count", 0) + 1
                break

    def get_focus(
        self,
        top_k: int = 10,
        min_score: float = 0.01
    ) -> List[Dict[str, Any]]:
        """
        获取当前最高注意力的 K 个事件

        Args:
            top_k: 返回数量
            min_score: 最低分数阈值

        Returns:
            按 score 降序的事件列表
        """
        self._lazy_decay()
        removed = self._cleanup_low_score()

        self.store.sort(key=lambda x: x["score"], reverse=True)
        return [x for x in self.store[:top_k] if x["score"] > min_score]

    def get_stats(self) -> Dict[str, Any]:
        """
        获取记忆统计信息

        Returns:
            包含各种统计信息的字典
        """
        if not self.store:
            return {
                "total": 0,
                "level_distribution": {"high": 0, "medium": 0, "low": 0},
                "avg_score": 0.0,
                "avg_reinforce_count": 0.0,
            }

        level_counts = {"high": 0, "medium": 0, "low": 0}
        total_score = 0.0
        total_reinforce = 0

        for item in self.store:
            level = item.get("level", "medium")
            if level in level_counts:
                level_counts[level] += 1
            total_score += item.get("score", 0)
            total_reinforce += item.get("reinforce_count", 0)

        return {
            "total": len(self.store),
            "level_distribution": level_counts,
            "avg_score": total_score / len(self.store),
            "avg_reinforce_count": total_reinforce / len(self.store),
            "decay_rate": self.base_decay_rate,
        }

    def get_memory_age_stats(self) -> Dict[str, Any]:
        """获取记忆年龄统计"""
        now = time.time()
        ages = []
        for item in self.store:
            ages.append(now - item.get("time", now))

        if not ages:
            return {"min": 0, "max": 0, "avg": 0}

        return {
            "min": min(ages),
            "max": max(ages),
            "avg": sum(ages) / len(ages),
        }

    PERSISTENCE_TABLE = "naja_attention_memory"
    PERSISTENCE_KEY = "attention_memory"

    def save_state(self) -> Dict[str, Any]:
        """保存记忆状态到数据库"""
        if not NB_AVAILABLE:
            return {"success": False, "error": "NB not available"}

        try:
            state_data = {
                "store": self.store,
                "base_decay_rate": self.base_decay_rate,
                "reinforcement_shield": self.reinforcement_shield,
                "cleanup_threshold": self.cleanup_threshold,
                "_last_decay_time": self._last_decay_time,
                "saved_at": time.time(),
            }
            db = NB(self.PERSISTENCE_TABLE)
            db[self.PERSISTENCE_KEY] = state_data
            return {
                "success": True,
                "memory_count": len(self.store),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def load_state(self) -> Dict[str, Any]:
        """从数据库加载记忆状态"""
        if not NB_AVAILABLE:
            return {"success": False, "error": "NB not available"}

        try:
            db = NB(self.PERSISTENCE_TABLE)
            if self.PERSISTENCE_KEY not in db:
                return {"success": True, "loaded": False, "message": "No saved state"}

            state_data = db.get(self.PERSISTENCE_KEY)
            self.store = state_data.get("store", [])
            self.base_decay_rate = state_data.get("base_decay_rate", 300.0)
            self.reinforcement_shield = state_data.get("reinforcement_shield", 60.0)
            self.cleanup_threshold = state_data.get("cleanup_threshold", 0.01)
            self._last_decay_time = state_data.get("_last_decay_time", time.time())

            return {
                "success": True,
                "loaded": True,
                "memory_count": len(self.store),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
