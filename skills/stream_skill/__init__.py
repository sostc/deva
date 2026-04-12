"""
流式 Skill 执行架构

提供有状态、可干预、支持澄清请求的 Skill 执行框架
"""

from .models import (
    SkillState,
    SkillContext,
    SkillEvent,
    ControlMessage,
    ClarificationRequest,
    ClarificationResponse,
)
from .stream_skill import StreamSkill
from .execution_engine import SkillExecutionEngine, ExecutionSession, get_execution_engine
from .agent_interface import AgentSkillInterface
from .adapter import LegacySkillAdapter

__all__ = [
    # 数据模型
    "SkillState",
    "SkillContext",
    "SkillEvent",
    "ControlMessage",
    "ClarificationRequest",
    "ClarificationResponse",
    # 核心类
    "StreamSkill",
    "SkillExecutionEngine",
    "ExecutionSession",
    "AgentSkillInterface",
    "LegacySkillAdapter",
    # 工具函数
    "get_execution_engine",
]
