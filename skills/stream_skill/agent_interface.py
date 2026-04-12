"""
Agent-Skill 交互接口

提供 Agent 与流式 Skill 交互的高级接口，简化流式调用和动态干预
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional, Callable, Any, Dict, List

from .models import SkillEvent, ClarificationRequest
from .execution_engine import get_execution_engine


class AgentSkillInterface:
    """Agent 与 Skill 的交互接口

    提供简化的 API 用于：
    1. 流式调用 Skill
    2. 实时接收执行事件
    3. 自动处理澄清请求
    4. 动态干预执行（暂停、恢复、参数更新）

    示例用法：
        interface = AgentSkillInterface(agent_id="agent_001")

        # 定义事件处理
        async def on_event(event):
            print(f"进度: {event.data.get('progress', 0)}%")

        async def on_clarification(request):
            # 可以询问用户或调用 LLM
            return request.options[0] if request.options else "继续"

        # 流式调用
        async for event in interface.invoke_skill_stream(
            skill_id="data_analysis",
            input_data={"file": "data.csv"},
            on_event=on_event,
            on_clarification=on_clarification
        ):
            if event.event_type == "completed":
                print("完成!")

        # 动态干预
        await interface.pause_skill("data_analysis")
        await interface.update_skill_params("data_analysis", {"threshold": 0.8})
        await interface.resume_skill("data_analysis")
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._engine = get_execution_engine()
        self._active_sessions: Dict[str, str] = {}  # skill_id -> session_id
        self._event_callbacks: Dict[str, Callable] = {}  # skill_id -> callback

    async def invoke_skill_stream(
        self,
        skill_id: str,
        input_data: Any,
        on_event: Optional[Callable[[SkillEvent], Any]] = None,
        on_clarification: Optional[Callable[[ClarificationRequest], Any]] = None,
        auto_handle_clarification: bool = True
    ) -> AsyncIterator[SkillEvent]:
        """流式调用 Skill

        这是与 Skill 交互的主要方法。它会启动 Skill 执行并返回一个异步迭代器，
        可以实时接收执行事件。

        特性：
        1. 实时接收执行事件
        2. 自动处理澄清请求（如果提供 on_clarification）
        3. 支持动态干预（通过返回的 session_id）

        Args:
            skill_id: Skill 标识符
            input_data: 输入数据
            on_event: 可选的事件回调函数
            on_clarification: 可选的澄清处理函数
            auto_handle_clarification: 是否自动处理澄清请求

        Yields:
            SkillEvent: 执行事件

        Example:
            async for event in interface.invoke_skill_stream(
                skill_id="my_skill",
                input_data={"key": "value"}
            ):
                print(f"{event.event_type}: {event.data}")
        """
        session_id = await self._engine.execute(skill_id, input_data)
        self._active_sessions[skill_id] = session_id

        if on_event:
            self._event_callbacks[skill_id] = on_event

        last_event_index = 0
        pending_clarifications: Dict[str, asyncio.Future] = {}
        no_event_count = 0
        max_no_event_count = 200  # 最多等待 10 秒 (200 * 0.05)

        try:
            while True:
                # 获取新事件
                events = self._engine.get_session_events(session_id, last_event_index)

                if events:
                    no_event_count = 0
                    for event in events:
                        last_event_index += 1

                        # 处理澄清请求
                        if event.event_type == "clarification_requested" and auto_handle_clarification:
                            if on_clarification:
                                # 创建异步任务处理澄清
                                asyncio.create_task(
                                    self._handle_clarification_request(
                                        session_id,
                                        event,
                                        on_clarification
                                    )
                                )

                        # 回调通知
                        if on_event:
                            try:
                                if asyncio.iscoroutinefunction(on_event):
                                    await on_event(event)
                                else:
                                    on_event(event)
                            except Exception as e:
                                # 回调错误不应影响主流程
                                pass

                        yield event

                        # 检查是否完成
                        if event.event_type in ("completed", "failed", "cancelled"):
                            return
                else:
                    no_event_count += 1
                    if no_event_count > max_no_event_count:
                        # 超时退出
                        return

                # 短暂等待新事件
                await asyncio.sleep(0.05)

        finally:
            self._active_sessions.pop(skill_id, None)
            self._event_callbacks.pop(skill_id, None)

    async def _handle_clarification_request(
        self,
        session_id: str,
        event: SkillEvent,
        on_clarification: Callable[[ClarificationRequest], Any]
    ):
        """处理澄清请求"""
        try:
            request_data = event.data
            request = ClarificationRequest(
                request_id=request_data["request_id"],
                skill_id=event.execution_id,  # 这里用 execution_id 作为 skill_id
                execution_id=event.execution_id,
                question=request_data["question"],
                context={},
                options=request_data.get("options"),
                urgency=request_data.get("urgency", "normal"),
                timeout_seconds=request_data.get("timeout_seconds", 60.0)
            )

            # 调用处理函数
            if asyncio.iscoroutinefunction(on_clarification):
                answer = await on_clarification(request)
            else:
                answer = on_clarification(request)

            # 发送澄清响应
            await self._engine.request_clarification_response(
                session_id,
                request.request_id,
                answer
            )

        except Exception as e:
            # 澄清处理错误不应影响主流程
            pass

    async def invoke_skill(
        self,
        skill_id: str,
        input_data: Any,
        on_event: Optional[Callable[[SkillEvent], Any]] = None,
        on_clarification: Optional[Callable[[ClarificationRequest], Any]] = None
    ) -> Dict[str, Any]:
        """调用 Skill 并等待完成

        这是 invoke_skill_stream 的同步版本，会等待 Skill 执行完成并返回结果。

        Args:
            skill_id: Skill 标识符
            input_data: 输入数据
            on_event: 可选的事件回调函数
            on_clarification: 可选的澄清处理函数

        Returns:
            包含执行结果的字典
        """
        events = []
        final_result = None

        async for event in self.invoke_skill_stream(
            skill_id=skill_id,
            input_data=input_data,
            on_event=on_event,
            on_clarification=on_clarification
        ):
            events.append(event)

            if event.event_type in ("completed", "failed", "cancelled"):
                final_result = event
                break

        return {
            "success": final_result.event_type == "completed" if final_result else False,
            "events": events,
            "final_event": final_result.to_dict() if final_result else None,
            "session_id": self._active_sessions.get(skill_id)
        }

    async def pause_skill(self, skill_id: str) -> bool:
        """暂停 Skill 执行

        Args:
            skill_id: Skill 标识符

        Returns:
            是否成功暂停
        """
        session_id = self._active_sessions.get(skill_id)
        if session_id:
            return await self._engine.inject_control(session_id, "pause", {})
        return False

    async def resume_skill(self, skill_id: str) -> bool:
        """恢复 Skill 执行

        Args:
            skill_id: Skill 标识符

        Returns:
            是否成功恢复
        """
        session_id = self._active_sessions.get(skill_id)
        if session_id:
            return await self._engine.inject_control(session_id, "resume", {})
        return False

    async def update_skill_params(self, skill_id: str, params: Dict[str, Any]) -> bool:
        """动态更新 Skill 参数

        Args:
            skill_id: Skill 标识符
            params: 要更新的参数字典

        Returns:
            是否成功更新
        """
        session_id = self._active_sessions.get(skill_id)
        if session_id:
            return await self._engine.inject_control(session_id, "update_params", params)
        return False

    async def cancel_skill(self, skill_id: str) -> bool:
        """取消 Skill 执行

        Args:
            skill_id: Skill 标识符

        Returns:
            是否成功取消
        """
        session_id = self._active_sessions.get(skill_id)
        if session_id:
            return await self._engine.inject_control(session_id, "cancel", {})
        return False

    def get_active_session(self, skill_id: str) -> Optional[str]:
        """获取 Skill 的活跃会话 ID

        Args:
            skill_id: Skill 标识符

        Returns:
            会话 ID，如果没有活跃会话则返回 None
        """
        return self._active_sessions.get(skill_id)

    def list_active_sessions(self) -> Dict[str, str]:
        """列出所有活跃的会话

        Returns:
            skill_id -> session_id 的字典
        """
        return dict(self._active_sessions)

    async def wait_for_completion(
        self,
        skill_id: str,
        timeout: Optional[float] = None
    ) -> bool:
        """等待 Skill 执行完成

        Args:
            skill_id: Skill 标识符
            timeout: 超时时间（秒），None 表示无限等待

        Returns:
            是否在超时前完成
        """
        session_id = self._active_sessions.get(skill_id)
        if not session_id:
            return True  # 没有活跃会话，视为已完成

        start_time = asyncio.get_event_loop().time()

        while True:
            status = self._engine.get_session_status(session_id)
            if not status:
                return True

            if status["current_state"] in ("completed", "failed", "cancelled"):
                return True

            if timeout is not None:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    return False

            await asyncio.sleep(0.1)

    async def get_skill_status(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """获取 Skill 执行状态

        Args:
            skill_id: Skill 标识符

        Returns:
            状态字典，如果没有活跃会话则返回 None
        """
        session_id = self._active_sessions.get(skill_id)
        if session_id:
            return self._engine.get_session_status(session_id)
        return None

    def is_skill_active(self, skill_id: str) -> bool:
        """检查 Skill 是否处于活跃状态

        Args:
            skill_id: Skill 标识符

        Returns:
            是否有活跃会话
        """
        return skill_id in self._active_sessions


class BatchSkillInterface:
    """批量 Skill 调用接口

    用于同时管理多个 Skill 的执行
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._engine = get_execution_engine()
        self._interfaces: Dict[str, AgentSkillInterface] = {}

    async def execute_multiple(
        self,
        skill_configs: List[Dict[str, Any]],
        on_event: Optional[Callable[[str, SkillEvent], Any]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """并行执行多个 Skill

        Args:
            skill_configs: Skill 配置列表，每个配置包含 skill_id 和 input_data
            on_event: 可选的全局事件回调，接收 skill_id 和 event

        Returns:
            skill_id -> 执行结果的字典
        """
        tasks = []

        for config in skill_configs:
            skill_id = config["skill_id"]
            input_data = config.get("input_data", {})

            interface = AgentSkillInterface(f"{self.agent_id}_{skill_id}")
            self._interfaces[skill_id] = interface

            # 定义事件处理
            def make_event_handler(sid):
                async def handler(event):
                    if on_event:
                        await on_event(sid, event)
                return handler

            # 启动执行
            task = asyncio.create_task(
                interface.invoke_skill(
                    skill_id=skill_id,
                    input_data=input_data,
                    on_event=make_event_handler(skill_id)
                )
            )
            tasks.append((skill_id, task))

        # 等待所有执行完成
        results = {}
        for skill_id, task in tasks:
            try:
                result = await task
                results[skill_id] = result
            except Exception as e:
                results[skill_id] = {
                    "success": False,
                    "error": str(e)
                }

        return results

    async def pause_all(self) -> Dict[str, bool]:
        """暂停所有活跃的 Skill

        Returns:
            skill_id -> 是否成功暂停的字典
        """
        results = {}
        for skill_id, interface in self._interfaces.items():
            results[skill_id] = await interface.pause_skill(skill_id)
        return results

    async def resume_all(self) -> Dict[str, bool]:
        """恢复所有暂停的 Skill

        Returns:
            skill_id -> 是否成功恢复的字典
        """
        results = {}
        for skill_id, interface in self._interfaces.items():
            results[skill_id] = await interface.resume_skill(skill_id)
        return results

    async def cancel_all(self) -> Dict[str, bool]:
        """取消所有活跃的 Skill

        Returns:
            skill_id -> 是否成功取消的字典
        """
        results = {}
        for skill_id, interface in self._interfaces.items():
            results[skill_id] = await interface.cancel_skill(skill_id)
        return results
