"""
Skill 执行引擎

管理所有流式 Skill 的执行，提供会话管理、事件总线、状态持久化等功能
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, Type

from .models import (
    SkillEvent,
    ControlMessage,
    ClarificationResponse,
    ExecutionStats,
)
from .stream_skill import StreamSkill


@dataclass
class ExecutionSession:
    """执行会话

    Attributes:
        session_id: 会话唯一标识
        skill_id: Skill 标识符
        skill_instance: Skill 实例
        start_time: 开始时间
        status: 会话状态
        events: 事件列表
        stats: 执行统计
    """
    session_id: str
    skill_id: str
    skill_instance: StreamSkill
    start_time: float
    status: str = "running"
    events: List[SkillEvent] = field(default_factory=list)
    stats: Optional[ExecutionStats] = None


class SkillExecutionEngine:
    """Skill 执行引擎

    单例模式，管理所有流式 Skill 的执行生命周期。
    提供会话管理、事件总线、控制注入等功能。

    示例用法：
        engine = get_execution_engine()

        # 注册 Skill
        engine.register_skill("my_skill", MySkillClass)

        # 执行 Skill
        session_id = await engine.execute("my_skill", input_data)

        # 注入控制
        await engine.inject_control(session_id, "pause", {})

        # 获取状态
        status = engine.get_session_status(session_id)
    """

    _instance: Optional[SkillExecutionEngine] = None
    _lock = asyncio.Lock()

    def __new__(cls) -> SkillExecutionEngine:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._sessions: Dict[str, ExecutionSession] = {}
        self._skill_registry: Dict[str, Type[StreamSkill]] = {}
        self._event_bus: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._global_subscribers: List[Callable[[Dict[str, Any]], None]] = []
        self._session_lock = asyncio.Lock()
        self._initialized = True

        # 启动事件总线处理任务
        asyncio.create_task(self._process_event_bus())

    def register_skill(self, skill_id: str, skill_class: Type[StreamSkill]) -> None:
        """注册 Skill 类型

        Args:
            skill_id: Skill 标识符
            skill_class: Skill 类，必须是 StreamSkill 的子类

        Raises:
            ValueError: 如果 skill_class 不是 StreamSkill 的子类
        """
        if not issubclass(skill_class, StreamSkill):
            raise ValueError(f"Skill class must be a subclass of StreamSkill: {skill_class}")
        self._skill_registry[skill_id] = skill_class

    def unregister_skill(self, skill_id: str) -> bool:
        """注销 Skill 类型

        Args:
            skill_id: Skill 标识符

        Returns:
            是否成功注销
        """
        if skill_id in self._skill_registry:
            del self._skill_registry[skill_id]
            return True
        return False

    async def execute(
        self,
        skill_id: str,
        input_data: Any,
        session_id: Optional[str] = None
    ) -> str:
        """执行 Skill

        Args:
            skill_id: Skill 标识符
            input_data: 输入数据
            session_id: 可选的会话 ID，如果不提供则自动生成

        Returns:
            会话 ID

        Raises:
            ValueError: 如果 Skill 未注册
        """
        if skill_id not in self._skill_registry:
            raise ValueError(f"Unknown skill: {skill_id}")

        # 创建会话
        session_id = session_id or f"session_{int(time.time() * 1000)}_{id(asyncio.current_task())}"
        skill_class = self._skill_registry[skill_id]
        skill_instance = skill_class(skill_id)

        session = ExecutionSession(
            session_id=session_id,
            skill_id=skill_id,
            skill_instance=skill_instance,
            start_time=time.time()
        )

        async with self._session_lock:
            self._sessions[session_id] = session

        # 订阅事件
        def on_event(event: SkillEvent):
            session.events.append(event)
            # 广播到事件总线
            asyncio.create_task(self._event_bus.put({
                "type": "skill_event",
                "session_id": session_id,
                "skill_id": skill_id,
                "event": event,
                "timestamp": time.time()
            }))

        skill_instance.subscribe_to_events(on_event)

        # 启动执行
        async def run_skill():
            try:
                async for event in skill_instance.start(input_data):
                    pass  # 事件通过订阅者处理
            except Exception as e:
                # 执行异常处理
                await self._event_bus.put({
                    "type": "execution_error",
                    "session_id": session_id,
                    "skill_id": skill_id,
                    "error": str(e),
                    "timestamp": time.time()
                })
            finally:
                # 更新会话状态
                async with self._session_lock:
                    if session_id in self._sessions:
                        session.status = skill_instance.state.value
                        session.stats = skill_instance.stats

        asyncio.create_task(run_skill())

        # 发送会话创建事件
        await self._event_bus.put({
            "type": "session_created",
            "session_id": session_id,
            "skill_id": skill_id,
            "timestamp": time.time()
        })

        return session_id

    async def inject_control(
        self,
        session_id: str,
        message_type: str,
        data: Any
    ) -> bool:
        """向执行会话注入控制消息

        Args:
            session_id: 会话 ID
            message_type: 消息类型 (pause, resume, update_params, cancel)
            data: 消息数据

        Returns:
            是否成功注入
        """
        async with self._session_lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

        message = ControlMessage(
            message_type=message_type,
            data=data
        )
        session.skill_instance.inject_control_message(message)

        # 发送控制注入事件
        await self._event_bus.put({
            "type": "control_injected",
            "session_id": session_id,
            "message_type": message_type,
            "timestamp": time.time()
        })

        return True

    async def request_clarification_response(
        self,
        session_id: str,
        request_id: str,
        answer: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """响应澄清请求

        Args:
            session_id: 会话 ID
            request_id: 请求 ID
            answer: 回答内容
            metadata: 额外元数据

        Returns:
            是否成功发送响应
        """
        async with self._session_lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

        response = ClarificationResponse(
            request_id=request_id,
            answer=answer,
            metadata=metadata or {}
        )
        message = ControlMessage(
            message_type="clarification_response",
            data=response
        )
        session.skill_instance.inject_control_message(message)

        return True

    def get_session(self, session_id: str) -> Optional[ExecutionSession]:
        """获取执行会话

        Args:
            session_id: 会话 ID

        Returns:
            执行会话，如果不存在则返回 None
        """
        return self._sessions.get(session_id)

    def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话状态

        Args:
            session_id: 会话 ID

        Returns:
            状态字典，如果不存在则返回 None
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        skill_instance = session.skill_instance
        context = skill_instance.context

        return {
            "session_id": session_id,
            "skill_id": session.skill_id,
            "status": session.status,
            "start_time": session.start_time,
            "event_count": len(session.events),
            "current_state": skill_instance.state.value,
            "current_stage": context.current_stage if context else None,
            "stats": session.stats.to_dict() if session.stats else None,
            "latest_events": [e.to_dict() for e in session.events[-5:]]
        }

    def get_session_events(
        self,
        session_id: str,
        since_index: int = 0
    ) -> List[SkillEvent]:
        """获取会话事件

        Args:
            session_id: 会话 ID
            since_index: 起始索引

        Returns:
            事件列表
        """
        session = self._sessions.get(session_id)
        if not session:
            return []
        return session.events[since_index:]

    def list_sessions(
        self,
        skill_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """列出会话

        Args:
            skill_id: 可选的 Skill ID 过滤
            status: 可选的状态过滤

        Returns:
            会话信息列表
        """
        result = []
        for session_id, session in self._sessions.items():
            if skill_id and session.skill_id != skill_id:
                continue
            if status and session.status != status:
                continue

            result.append({
                "session_id": session_id,
                "skill_id": session.skill_id,
                "status": session.status,
                "start_time": session.start_time,
                "event_count": len(session.events)
            })
        return result

    async def terminate_session(self, session_id: str) -> bool:
        """终止会话

        Args:
            session_id: 会话 ID

        Returns:
            是否成功终止
        """
        async with self._session_lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

        # 发送取消命令
        await self.inject_control(session_id, "cancel", {"reason": "terminated_by_engine"})

        # 从会话列表中移除
        async with self._session_lock:
            if session_id in self._sessions:
                del self._sessions[session_id]

        # 发送会话终止事件
        await self._event_bus.put({
            "type": "session_terminated",
            "session_id": session_id,
            "timestamp": time.time()
        })

        return True

    async def cleanup_completed_sessions(self, max_age_seconds: float = 3600) -> int:
        """清理已完成的会话

        Args:
            max_age_seconds: 最大保留时间（秒）

        Returns:
            清理的会话数量
        """
        now = time.time()
        to_remove = []

        async with self._session_lock:
            for session_id, session in self._sessions.items():
                if session.status in ("completed", "failed", "cancelled"):
                    if now - session.start_time > max_age_seconds:
                        to_remove.append(session_id)

            for session_id in to_remove:
                del self._sessions[session_id]

        return len(to_remove)

    def subscribe_to_events(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """订阅全局事件

        Args:
            callback: 事件回调函数
        """
        if callback not in self._global_subscribers:
            self._global_subscribers.append(callback)

    def unsubscribe_from_events(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """取消订阅全局事件

        Args:
            callback: 要取消的回调函数
        """
        if callback in self._global_subscribers:
            self._global_subscribers.remove(callback)

    async def _process_event_bus(self):
        """处理事件总线的后台任务"""
        while True:
            try:
                event_data = await self._event_bus.get()

                # 广播给全局订阅者
                for subscriber in self._global_subscribers:
                    try:
                        if asyncio.iscoroutinefunction(subscriber):
                            await subscriber(event_data)
                        else:
                            subscriber(event_data)
                    except Exception:
                        # 订阅者错误不应影响总线
                        pass

            except asyncio.CancelledError:
                break
            except Exception:
                # 总线错误不应导致崩溃
                pass

    def get_registered_skills(self) -> List[str]:
        """获取已注册的 Skill 列表

        Returns:
            Skill ID 列表
        """
        return list(self._skill_registry.keys())

    def get_engine_stats(self) -> Dict[str, Any]:
        """获取引擎统计信息

        Returns:
            统计信息字典
        """
        status_counts: Dict[str, int] = {}
        for session in self._sessions.values():
            status = session.status
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_sessions": len(self._sessions),
            "registered_skills": len(self._skill_registry),
            "status_breakdown": status_counts,
            "event_bus_size": self._event_bus.qsize(),
        }


def get_execution_engine() -> SkillExecutionEngine:
    """获取 SkillExecutionEngine 单例

    Returns:
        SkillExecutionEngine 实例
    """
    return SkillExecutionEngine()
