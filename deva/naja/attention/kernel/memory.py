"""
AttentionMemory - 持久注意力记忆

提供事件级记忆存储、时间衰减和强化学习支持
"""

import time
import math


class AttentionMemory:
    """
    持久注意力记忆

    属性:
        store: 记忆存储列表
        decay_rate: 衰减率（秒），默认 300（5分钟半衰期）
    """

    def __init__(self, decay_rate=300):
        """
        初始化注意力记忆

        Args:
            decay_rate: 衰减半衰期（秒）
        """
        self.store = []
        self.decay_rate = decay_rate

    def update(self, event, score):
        """
        记录一次 attention

        Args:
            event: AttentionEvent
            score: 注意力分数
        """
        self.store.append({
            "event": event,
            "score": score,
            "time": time.time()
        })

    def decay(self):
        """
        时间衰减：所有记忆的 score 按指数衰减
        """
        now = time.time()
        for item in self.store:
            dt = now - item["time"]
            item["score"] *= math.exp(-dt / self.decay_rate)

    def keep_hot(self, event):
        """
        维持事件热度

        Args:
            event: AttentionEvent
        """
        for item in self.store:
            if item["event"] == event:
                item["score"] *= 1.5
                break

    def transfer(self, from_event, to_event):
        """
        注意力转移

        Args:
            from_event: 原事件
            to_event: 目标事件
        """
        for item in self.store:
            if item["event"] == from_event:
                item["event"] = to_event
                item["time"] = time.time()
                break

    def get_focus(self, top_k=10, min_score=0.01):
        """
        获取当前最高注意力的 K 个事件

        Args:
            top_k: 返回数量
            min_score: 最低分数阈值

        Returns:
            按 score 降序的事件列表
        """
        self.decay()
        self.store.sort(key=lambda x: x["score"], reverse=True)
        return [x for x in self.store[:top_k] if x["score"] > min_score]

    def reinforce(self, event, reward):
        """
        强化学习反馈

        Args:
            event: AttentionEvent
            reward: 奖励值，正增强，负抑制
        """
        for item in self.store:
            if item["event"] == event:
                item["score"] *= (1 + reward)
                break