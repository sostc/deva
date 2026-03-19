"""
流式 Skill 数据模型

定义 Skill 执行过程中使用的所有数据结构和枚举
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional
import time


class SkillState(Enum):
    """Skill 执行状态"""
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    CLARIFICATION_REQUESTED = "clarification_requested"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SkillEventType(Enum):
    """Skill 事件类型"""
    # 生命周期事件
    STARTED = "started"
    PROGRESS = "progress"
    STAGE_COMPLETED = "stage_completed"
    STAGE_STARTED = "stage_started"

    # 交互事件
    CLARIFICATION_REQUESTED = "clarification_requested"
    CLARIFICATION_RECEIVED = "clarification_received"

    # 控制事件
    PAUSED = "paused"
    RESUMED = "resumed"
    CANCELLED = "cancelled"
    PARAMS_UPDATED = "params_updated"

    # 检查点事件
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESTORED = "checkpoint_restored"

    # 完成事件
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SkillContext:
    """Skill 执行上下文 - 保持完整状态不丢失

    Attributes:
        skill_id: Skill 标识符
        execution_id: 本次执行的唯一标识
        start_time: 执行开始时间
        input_data: 输入数据
        current_stage: 当前执行阶段
        stage_progress: 各阶段进度信息
        intermediate_results: 中间结果列表
        metadata: 元数据，可用于动态参数传递
        checkpoints: 检查点列表
    """
    skill_id: str
    execution_id: str
    start_time: float
    input_data: Any
    current_stage: str = ""
    stage_progress: Dict[str, Any] = field(default_factory=dict)
    intermediate_results: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    checkpoints: List[dict] = field(default_factory=list)

    def create_checkpoint(self, stage: str) -> dict:
        """创建检查点

        Args:
            stage: 当前阶段名称

        Returns:
            检查点数据字典
        """
        checkpoint = {
            "execution_id": self.execution_id,
            "stage": stage,
            "stage_progress": dict(self.stage_progress),
            "intermediate_results": list(self.intermediate_results),
            "metadata": dict(self.metadata),
            "timestamp": time.time()
        }
        self.checkpoints.append(checkpoint)
        return checkpoint

    def restore_from_checkpoint(self, checkpoint: dict) -> None:
        """从检查点恢复状态

        Args:
            checkpoint: 检查点数据字典
        """
        self.current_stage = checkpoint["stage"]
        self.stage_progress = dict(checkpoint.get("stage_progress", {}))
        self.intermediate_results = list(checkpoint.get("intermediate_results", []))
        self.metadata = dict(checkpoint.get("metadata", {}))

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "skill_id": self.skill_id,
            "execution_id": self.execution_id,
            "start_time": self.start_time,
            "current_stage": self.current_stage,
            "stage_progress": self.stage_progress,
            "intermediate_results_count": len(self.intermediate_results),
            "metadata": self.metadata,
            "checkpoints_count": len(self.checkpoints),
        }


@dataclass
class SkillEvent:
    """Skill 事件

    Attributes:
        event_type: 事件类型
        timestamp: 事件发生时间
        execution_id: 执行会话 ID
        data: 事件数据
        stage: 当前阶段（可选）
    """
    event_type: str
    timestamp: float
    execution_id: str
    data: Any
    stage: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "execution_id": self.execution_id,
            "data": self.data,
            "stage": self.stage,
        }


@dataclass
class ControlMessage:
    """控制消息 - 用于动态注入指令

    Attributes:
        message_type: 消息类型 (pause, resume, update_params, cancel, clarification_response)
        data: 消息数据
        timestamp: 消息发送时间
    """
    message_type: str  # "pause", "resume", "update_params", "cancel", "clarification_response"
    data: Any
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "message_type": self.message_type,
            "data": self.data,
            "timestamp": self.timestamp,
        }


@dataclass
class ClarificationRequest:
    """澄清请求 - 当 Skill 遇到不确定性时发起

    Attributes:
        request_id: 请求唯一标识
        skill_id: Skill 标识符
        execution_id: 执行会话 ID
        question: 需要澄清的问题
        context: 当前执行上下文快照
        options: 可选答案列表
        timeout_seconds: 超时时间（秒）
        urgency: 紧急程度 (normal, high, critical)
    """
    request_id: str
    skill_id: str
    execution_id: str
    question: str
    context: dict
    options: Optional[List[str]] = None
    timeout_seconds: float = 60.0
    urgency: str = "normal"  # normal, high, critical

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "request_id": self.request_id,
            "skill_id": self.skill_id,
            "execution_id": self.execution_id,
            "question": self.question,
            "context": self.context,
            "options": self.options,
            "timeout_seconds": self.timeout_seconds,
            "urgency": self.urgency,
        }


@dataclass
class ClarificationResponse:
    """澄清响应

    Attributes:
        request_id: 对应的请求 ID
        answer: 回答内容
        metadata: 额外元数据
    """
    request_id: str
    answer: Any
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "request_id": self.request_id,
            "answer": self.answer,
            "metadata": self.metadata,
        }


@dataclass
class ExecutionStats:
    """执行统计信息"""
    execution_id: str
    skill_id: str
    start_time: float
    end_time: Optional[float] = None
    event_count: int = 0
    clarification_count: int = 0
    checkpoint_count: int = 0
    status: str = "running"

    @property
    def duration_seconds(self) -> float:
        """执行持续时间"""
        end = self.end_time or time.time()
        return end - self.start_time

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "execution_id": self.execution_id,
            "skill_id": self.skill_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "event_count": self.event_count,
            "clarification_count": self.clarification_count,
            "checkpoint_count": self.checkpoint_count,
            "status": self.status,
        }
