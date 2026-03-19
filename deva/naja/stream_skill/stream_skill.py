"""
流式 Skill 基类

提供有状态、可干预、支持澄清请求的 Skill 执行框架的核心实现
"""

from __future__ import annotations

import asyncio
import uuid
import time
from abc import ABC, abstractmethod
from typing import AsyncIterator, Any, Optional, Callable, List, Dict

from .models import (
    SkillState,
    SkillContext,
    SkillEvent,
    ControlMessage,
    ClarificationRequest,
    ClarificationResponse,
    ExecutionStats,
)


class StreamSkill(ABC):
    """流式 Skill 基类

    提供以下核心能力：
    1. 流式执行 - 通过 AsyncIterator 实时产生事件
    2. 状态管理 - 维护执行上下文和检查点
    3. 动态干预 - 支持暂停、恢复、参数更新
    4. 澄清请求 - 遇到不确定性时可发起请求并等待响应
    5. 事件订阅 - 支持外部订阅执行事件

    示例用法：
        class MySkill(StreamSkill):
            async def execute(self, input_data, context):
                # 阶段 1
                context.current_stage = "stage1"
                yield SkillEvent(...)

                # 可能需要澄清
                response = await self.request_clarification(
                    question="如何处理?",
                    options=["A", "B"]
                )

                # 继续执行
                yield SkillEvent(...)

        # 使用
        skill = MySkill("my_skill")
        async for event in skill.start(input_data):
            print(event)
    """

    def __init__(self, skill_id: str):
        self.skill_id = skill_id
        self._state = SkillState.CREATED
        self._context: Optional[SkillContext] = None
        self._control_queue: asyncio.Queue[ControlMessage] = asyncio.Queue()
        self._clarification_queue: asyncio.Queue[ClarificationResponse] = asyncio.Queue()
        self._event_subscribers: List[Callable[[SkillEvent], None]] = []
        self._current_task: Optional[asyncio.Task] = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 默认不暂停
        self._stats: Optional[ExecutionStats] = None

    @abstractmethod
    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """子类必须实现的具体执行逻辑

        Args:
            input_data: 输入数据
            context: 执行上下文

        Yields:
            SkillEvent: 执行事件
        """
        pass

    async def start(self, input_data: Any) -> AsyncIterator[SkillEvent]:
        """启动流式执行

        Args:
            input_data: 输入数据

        Yields:
            SkillEvent: 执行事件流
        """
        execution_id = str(uuid.uuid4())
        self._context = SkillContext(
            skill_id=self.skill_id,
            execution_id=execution_id,
            start_time=time.time(),
            input_data=input_data
        )
        self._stats = ExecutionStats(
            execution_id=execution_id,
            skill_id=self.skill_id,
            start_time=time.time()
        )
        self._state = SkillState.STARTING

        # 发送启动事件
        yield SkillEvent(
            event_type="started",
            timestamp=time.time(),
            execution_id=execution_id,
            data={"input": input_data, "skill_id": self.skill_id}
        )

        self._state = SkillState.RUNNING
        self._stats.status = "running"

        # 启动控制消息处理任务
        control_task = asyncio.create_task(self._process_control_messages())

        try:
            async for event in self.execute(input_data, self._context):
                # 等待暂停事件（如果被暂停）
                await self._pause_event.wait()

                # 检查状态
                if self._state == SkillState.CANCELLED:
                    break

                # 更新统计
                if self._stats:
                    self._stats.event_count += 1

                # 发送事件
                yield event

                # 广播给订阅者
                await self._broadcast_event(event)

        except Exception as e:
            self._state = SkillState.FAILED
            if self._stats:
                self._stats.status = "failed"
                self._stats.end_time = time.time()
            yield SkillEvent(
                event_type="failed",
                timestamp=time.time(),
                execution_id=execution_id,
                data={"error": str(e), "error_type": type(e).__name__}
            )
        finally:
            control_task.cancel()
            try:
                await control_task
            except asyncio.CancelledError:
                pass

            if self._state not in (SkillState.FAILED, SkillState.CANCELLED):
                self._state = SkillState.COMPLETED
                if self._stats:
                    self._stats.status = "completed"
                    self._stats.end_time = time.time()
                yield SkillEvent(
                    event_type="completed",
                    timestamp=time.time(),
                    execution_id=execution_id,
                    data={
                        "context": self._context.create_checkpoint("completed") if self._context else None,
                        "stats": self._stats.to_dict() if self._stats else None
                    }
                )

    async def _process_control_messages(self):
        """处理控制消息的后台任务"""
        while True:
            try:
                message = await asyncio.wait_for(
                    self._control_queue.get(),
                    timeout=1.0
                )

                if message.message_type == "pause":
                    await self._handle_pause(message.data)

                elif message.message_type == "resume":
                    await self._handle_resume(message.data)

                elif message.message_type == "update_params":
                    await self._handle_update_params(message.data)

                elif message.message_type == "cancel":
                    await self._handle_cancel(message.data)

                elif message.message_type == "clarification_response":
                    await self._clarification_queue.put(message.data)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                # 控制消息处理错误不应影响主流程
                await self._emit_event("error", {"message": f"Control message error: {e}"})

    async def _handle_pause(self, data: Any):
        """处理暂停"""
        self._state = SkillState.PAUSED
        self._pause_event.clear()
        await self._emit_event("paused", {"reason": data})

    async def _handle_resume(self, data: Any):
        """处理恢复"""
        self._state = SkillState.RUNNING
        self._pause_event.set()
        await self._emit_event("resumed", data)

    async def _handle_update_params(self, data: Any):
        """处理参数更新"""
        if self._context and isinstance(data, dict):
            old_metadata = dict(self._context.metadata)
            self._context.metadata.update(data)
            await self._emit_event("params_updated", {
                "updated_keys": list(data.keys()),
                "old_metadata": old_metadata,
                "new_metadata": self._context.metadata
            })

    async def _handle_cancel(self, data: Any):
        """处理取消"""
        self._state = SkillState.CANCELLED
        if self._current_task:
            self._current_task.cancel()
        await self._emit_event("cancelled", data)

    async def _emit_event(self, event_type: str, data: Any, stage: Optional[str] = None):
        """发送事件"""
        if self._context:
            event = SkillEvent(
                event_type=event_type,
                timestamp=time.time(),
                execution_id=self._context.execution_id,
                data=data,
                stage=stage or self._context.current_stage
            )
            await self._broadcast_event(event)

    async def _broadcast_event(self, event: SkillEvent):
        """广播事件给所有订阅者"""
        for subscriber in self._event_subscribers:
            try:
                # 支持同步和异步回调
                if asyncio.iscoroutinefunction(subscriber):
                    await subscriber(event)
                else:
                    subscriber(event)
            except Exception:
                # 订阅者错误不应影响主流程
                pass

    async def request_clarification(
        self,
        question: str,
        options: Optional[List[str]] = None,
        timeout_seconds: float = 60.0,
        urgency: str = "normal",
        context_data: Optional[Dict[str, Any]] = None
    ) -> ClarificationResponse:
        """发起澄清请求并等待响应

        当 Skill 遇到不确定性时调用此方法发起澄清请求。
        方法会阻塞直到收到响应或超时。

        Args:
            question: 需要澄清的问题
            options: 可选答案列表
            timeout_seconds: 超时时间（秒）
            urgency: 紧急程度 (normal, high, critical)
            context_data: 额外的上下文数据

        Returns:
            ClarificationResponse: 澄清响应

        Raises:
            RuntimeError: Skill 未启动或响应超时
        """
        if not self._context:
            raise RuntimeError("Skill not started")

        request = ClarificationRequest(
            request_id=str(uuid.uuid4()),
            skill_id=self.skill_id,
            execution_id=self._context.execution_id,
            question=question,
            context=context_data or self._context.create_checkpoint(self._context.current_stage),
            options=options,
            timeout_seconds=timeout_seconds,
            urgency=urgency
        )

        self._state = SkillState.CLARIFICATION_REQUESTED
        if self._stats:
            self._stats.clarification_count += 1

        # 发送澄清请求事件
        await self._emit_event("clarification_requested", {
            "request_id": request.request_id,
            "question": question,
            "options": options,
            "urgency": urgency,
            "timeout_seconds": timeout_seconds
        })

        try:
            # 等待响应
            response = await asyncio.wait_for(
                self._clarification_queue.get(),
                timeout=timeout_seconds
            )

            if response.request_id != request.request_id:
                raise RuntimeError(f"Response ID mismatch: expected {request.request_id}, got {response.request_id}")

            self._state = SkillState.RUNNING

            # 发送澄清接收事件
            await self._emit_event("clarification_received", {
                "request_id": request.request_id,
                "answer": response.answer,
                "metadata": response.metadata
            })

            return response

        except asyncio.TimeoutError:
            self._state = SkillState.FAILED
            if self._stats:
                self._stats.status = "failed"
                self._stats.end_time = time.time()
            raise RuntimeError(f"Clarification request timed out after {timeout_seconds}s")

    def inject_control_message(self, message: ControlMessage):
        """注入控制消息（由主 Agent 调用）

        Args:
            message: 控制消息
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._control_queue.put(message))
            else:
                loop.run_until_complete(self._control_queue.put(message))
        except RuntimeError:
            # 没有事件循环时创建新任务
            asyncio.run(self._control_queue.put(message))

    def subscribe_to_events(self, callback: Callable[[SkillEvent], None]):
        """订阅事件

        Args:
            callback: 事件回调函数，可以是同步或异步函数
        """
        if callback not in self._event_subscribers:
            self._event_subscribers.append(callback)

    def unsubscribe_from_events(self, callback: Callable[[SkillEvent], None]):
        """取消订阅

        Args:
            callback: 要取消的回调函数
        """
        if callback in self._event_subscribers:
            self._event_subscribers.remove(callback)

    def create_checkpoint(self, stage: Optional[str] = None) -> Optional[dict]:
        """创建检查点

        Args:
            stage: 阶段名称，默认使用当前阶段

        Returns:
            检查点数据，如果 Skill 未启动则返回 None
        """
        if self._context:
            checkpoint = self._context.create_checkpoint(stage or self._context.current_stage)
            if self._stats:
                self._stats.checkpoint_count += 1

            # 发送检查点创建事件
            asyncio.create_task(self._emit_event("checkpoint_created", {
                "stage": stage or self._context.current_stage,
                "checkpoint": checkpoint
            }))

            return checkpoint
        return None

    def restore_from_checkpoint(self, checkpoint: dict) -> bool:
        """从检查点恢复

        Args:
            checkpoint: 检查点数据

        Returns:
            是否成功恢复
        """
        if self._context:
            self._context.restore_from_checkpoint(checkpoint)

            # 发送检查点恢复事件
            asyncio.create_task(self._emit_event("checkpoint_restored", {
                "stage": checkpoint.get("stage"),
                "checkpoint": checkpoint
            }))

            return True
        return False

    @property
    def state(self) -> SkillState:
        """当前状态"""
        return self._state

    @property
    def context(self) -> Optional[SkillContext]:
        """执行上下文"""
        return self._context

    @property
    def stats(self) -> Optional[ExecutionStats]:
        """执行统计"""
        return self._stats

    def is_running(self) -> bool:
        """是否正在运行"""
        return self._state == SkillState.RUNNING

    def is_paused(self) -> bool:
        """是否已暂停"""
        return self._state == SkillState.PAUSED

    def is_waiting_clarification(self) -> bool:
        """是否正在等待澄清"""
        return self._state == SkillState.CLARIFICATION_REQUESTED
