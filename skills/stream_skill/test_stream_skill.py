"""
流式 Skill 测试

测试流式 Skill 框架的核心功能
"""

import asyncio
import pytest
from typing import AsyncIterator, Any

from .models import (
    SkillState,
    SkillContext,
    SkillEvent,
    ClarificationRequest,
)
from .stream_skill import StreamSkill
from .execution_engine import get_execution_engine
from .agent_interface import AgentSkillInterface


class TestSkill(StreamSkill):
    """测试用的 Skill"""

    def __init__(self):
        super().__init__("test_skill")

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行测试逻辑"""
        # 发送进度事件
        for i in range(5):
            yield SkillEvent(
                event_type="progress",
                timestamp=asyncio.get_event_loop().time(),
                execution_id=context.execution_id,
                data={"progress": (i + 1) * 20, "message": f"Step {i+1}"}
            )
            await asyncio.sleep(0.01)


class ClarificationTestSkill(StreamSkill):
    """测试澄清请求的 Skill"""

    def __init__(self):
        super().__init__("clarification_test")

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行测试逻辑"""
        # 发送进度
        yield SkillEvent(
            event_type="progress",
            timestamp=asyncio.get_event_loop().time(),
            execution_id=context.execution_id,
            data={"progress": 50, "message": "Before clarification"}
        )

        # 发起澄清请求
        response = await self.request_clarification(
            question="Test question?",
            options=["A", "B"],
            timeout_seconds=5
        )

        # 根据响应继续
        yield SkillEvent(
            event_type="progress",
            timestamp=asyncio.get_event_loop().time(),
            execution_id=context.execution_id,
            data={"progress": 100, "message": f"After clarification: {response.answer}"}
        )


class TestStreamSkill:
    """测试 StreamSkill 基类"""

    @pytest.mark.asyncio
    async def test_basic_execution(self):
        """测试基本执行"""
        skill = TestSkill()
        events = []

        async for event in skill.start({"test": "data"}):
            events.append(event)

        # 验证事件
        assert len(events) > 0
        assert events[0].event_type == "started"
        assert events[-1].event_type == "completed"

        # 验证状态
        assert skill.state == SkillState.COMPLETED

    @pytest.mark.asyncio
    async def test_pause_resume(self):
        """测试暂停和恢复"""
        skill = TestSkill()

        # 启动执行
        events = []
        async for event in skill.start({}):
            events.append(event)

            # 暂停
            if len(events) == 2:
                skill.inject_control_message(type('obj', (object,), {
                    'message_type': 'pause',
                    'data': {},
                    'timestamp': asyncio.get_event_loop().time()
                })())

            # 恢复
            if len(events) == 3:
                skill.inject_control_message(type('obj', (object,), {
                    'message_type': 'resume',
                    'data': {},
                    'timestamp': asyncio.get_event_loop().time()
                })())

        # 验证执行完成
        assert skill.state == SkillState.COMPLETED

    @pytest.mark.asyncio
    async def test_clarification(self):
        """测试澄清请求"""
        skill = ClarificationTestSkill()

        # 收集事件
        events = []
        clarification_requested = False

        async for event in skill.start({}):
            events.append(event)

            if event.event_type == "clarification_requested":
                clarification_requested = True
                # 发送澄清响应
                from .models import ClarificationResponse
                skill.inject_control_message(type('obj', (object,), {
                    'message_type': 'clarification_response',
                    'data': ClarificationResponse(
                        request_id=event.data["request_id"],
                        answer="A"
                    ),
                    'timestamp': asyncio.get_event_loop().time()
                })())

        # 验证澄清请求被触发
        assert clarification_requested
        assert skill.state == SkillState.COMPLETED


class TestExecutionEngine:
    """测试 SkillExecutionEngine"""

    @pytest.mark.asyncio
    async def test_register_and_execute(self):
        """测试注册和执行"""
        engine = get_execution_engine()
        engine.register_skill("test", TestSkill)

        # 执行 Skill
        session_id = await engine.execute("test", {"key": "value"})

        # 验证会话创建
        assert session_id is not None
        assert engine.get_session(session_id) is not None

        # 等待执行完成
        await asyncio.sleep(0.1)

        # 验证状态
        status = engine.get_session_status(session_id)
        assert status is not None

    @pytest.mark.asyncio
    async def test_inject_control(self):
        """测试控制注入"""
        engine = get_execution_engine()
        engine.register_skill("test_control", TestSkill)

        # 执行 Skill
        session_id = await engine.execute("test_control", {})

        # 注入控制
        result = await engine.inject_control(session_id, "pause", {})
        assert result

        result = await engine.inject_control(session_id, "resume", {})
        assert result

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        """测试列出会话"""
        engine = get_execution_engine()

        # 清理之前的会话
        await engine.cleanup_completed_sessions(max_age_seconds=0)

        engine.register_skill("test_list", TestSkill)

        # 创建多个会话
        session_ids = []
        for i in range(3):
            sid = await engine.execute("test_list", {"index": i})
            session_ids.append(sid)

        # 列出会话
        sessions = engine.list_sessions()
        assert len(sessions) >= 3


class TestAgentInterface:
    """测试 AgentSkillInterface"""

    @pytest.mark.asyncio
    async def test_invoke_skill_stream(self):
        """测试流式调用"""
        engine = get_execution_engine()
        engine.register_skill("test_agent", TestSkill)

        interface = AgentSkillInterface("test_agent")

        events = []
        async for event in interface.invoke_skill_stream(
            skill_id="test_agent",
            input_data={"test": "data"}
        ):
            events.append(event)

        # 验证事件流
        assert len(events) > 0
        assert events[0].event_type == "started"
        assert events[-1].event_type in ("completed", "failed")

    @pytest.mark.asyncio
    async def test_invoke_skill(self):
        """测试同步调用"""
        engine = get_execution_engine()
        engine.register_skill("test_sync", TestSkill)

        interface = AgentSkillInterface("test_sync")

        result = await interface.invoke_skill(
            skill_id="test_sync",
            input_data={}
        )

        # 验证结果
        assert "success" in result
        assert "events" in result

    @pytest.mark.asyncio
    async def test_dynamic_intervention(self):
        """测试动态干预"""
        engine = get_execution_engine()
        engine.register_skill("test_intervention", TestSkill)

        interface = AgentSkillInterface("test_intervention")

        # 启动执行
        task = asyncio.create_task(
            interface.invoke_skill("test_intervention", {})
        )

        # 等待一下
        await asyncio.sleep(0.05)

        # 暂停
        result = await interface.pause_skill("test_intervention")
        assert result

        # 恢复
        result = await interface.resume_skill("test_intervention")
        assert result

        # 等待完成
        await task


# 运行测试的辅助函数
def run_tests():
    """运行所有测试"""
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    run_tests()
