"""
龙虾思想雷达 v1 - 实时记忆系统
Lobster Mind Radar - Real-time Memory System

核心思想: 流式学习 + 分层记忆 + 周期性自我反思
技术核心: River (流数据处理)
"""

__version__ = "1.0.0"
__author__ = "Lobster AI"

from .core.event import Event, EventType
from .core.radar import LobsterRadar
from .memory.short_memory import ShortMemory
from .memory.mid_memory import MidMemory
from .memory.long_memory import LongMemory

__all__ = [
    "Event",
    "EventType", 
    "LobsterRadar",
    "ShortMemory",
    "MidMemory",
    "LongMemory",
]
