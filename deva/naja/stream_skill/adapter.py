"""
传统 Skill 适配器

将传统（确定性）Skill 包装为流式 Skill，实现向后兼容
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Any, Optional, Callable

from .models import SkillContext, SkillEvent
from .stream_skill import StreamSkill


class LegacySkillAdapter(StreamSkill):
    """传统 Skill 适配器

    将传统 Skill（确定性执行）包装为流式 Skill，使其能够：
    1. 在流式执行引擎中运行
    2. 产生执行事件
    3. 支持基本的控制命令（取消）

    示例用法：
        # 传统 Skill 类
        class MyLegacySkill:
            def execute(self, input_data):
                # 执行逻辑
                return result

        # 包装为流式 Skill
        legacy_skill = MyLegacySkill()
        stream_skill = LegacySkillAdapter(legacy_skill, skill_id="my_skill")

        # 在流式引擎中执行
        async for event in stream_skill.start(input_data):
            print(event)
    """

    def __init__(
        self,
        legacy_skill: Any,
        skill_id: Optional[str] = None,
        emit_progress: bool = True
    ):
        """
        Args:
            legacy_skill: 传统 Skill 实例，必须有 execute 方法
            skill_id: Skill 标识符，如果不提供则使用 legacy_skill 的 id 或 name
            emit_progress: 是否发送进度事件
        """
        # 确定 skill_id
        skill_id = skill_id or getattr(legacy_skill, 'id', None) or getattr(legacy_skill, 'name', None) or 'legacy_skill'
        super().__init__(skill_id)

        self._legacy_skill = legacy_skill
        self._emit_progress = emit_progress
        self._cancelled = False

        # 验证 legacy_skill 有 execute 方法
        if not hasattr(legacy_skill, 'execute') or not callable(getattr(legacy_skill, 'execute')):
            raise ValueError(f"Legacy skill must have an 'execute' method: {legacy_skill}")

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行传统 Skill

        在后台线程中执行传统 Skill，并产生相应的事件
        """
        # 发送开始事件
        if self._emit_progress:
            yield SkillEvent(
                event_type="stage_started",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"stage": "legacy_execution", "message": "开始执行传统 Skill"},
                stage="legacy_execution"
            )

        try:
            # 在后台线程执行传统 Skill
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # 定义执行函数
            def run_legacy():
                return self._legacy_skill.execute(input_data)

            # 执行并等待结果
            if self._emit_progress:
                yield SkillEvent(
                    event_type="progress",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={"progress": 50, "message": "执行中..."},
                    stage="legacy_execution"
                )

            result = await loop.run_in_executor(None, run_legacy)

            # 检查是否被取消
            if self._cancelled:
                yield SkillEvent(
                    event_type="cancelled",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={"reason": "cancelled_during_execution"},
                    stage="legacy_execution"
                )
                return

            # 保存结果到上下文
            context.intermediate_results.append({"legacy_result": result})

            # 发送完成事件
            if self._emit_progress:
                yield SkillEvent(
                    event_type="stage_completed",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={
                        "stage": "legacy_execution",
                        "result": result,
                        "result_type": type(result).__name__
                    },
                    stage="legacy_execution"
                )

        except Exception as e:
            # 发送失败事件
            yield SkillEvent(
                event_type="failed",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "stage": "legacy_execution"
                },
                stage="legacy_execution"
            )

    def _handle_cancel(self, data: Any):
        """处理取消命令"""
        self._cancelled = True
        # 调用 legacy skill 的 cancel 方法（如果有）
        if hasattr(self._legacy_skill, 'cancel') and callable(getattr(self._legacy_skill, 'cancel')):
            try:
                self._legacy_skill.cancel()
            except Exception:
                pass
        return super()._handle_cancel(data)


class AsyncLegacySkillAdapter(StreamSkill):
    """异步传统 Skill 适配器

    用于包装已经是异步的传统 Skill
    """

    def __init__(
        self,
        legacy_skill: Any,
        skill_id: Optional[str] = None,
        emit_progress: bool = True
    ):
        skill_id = skill_id or getattr(legacy_skill, 'id', None) or getattr(legacy_skill, 'name', None) or 'async_legacy_skill'
        super().__init__(skill_id)

        self._legacy_skill = legacy_skill
        self._emit_progress = emit_progress
        self._cancelled = False

        # 验证 legacy_skill 有 execute 或 execute_async 方法
        has_execute = hasattr(legacy_skill, 'execute') and callable(getattr(legacy_skill, 'execute'))
        has_async_execute = hasattr(legacy_skill, 'execute_async') and callable(getattr(legacy_skill, 'execute_async'))

        if not (has_execute or has_async_execute):
            raise ValueError(f"Legacy skill must have an 'execute' or 'execute_async' method: {legacy_skill}")

        self._use_async = has_async_execute

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行异步传统 Skill"""
        if self._emit_progress:
            yield SkillEvent(
                event_type="stage_started",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"stage": "async_legacy_execution", "message": "开始执行异步传统 Skill"},
                stage="async_legacy_execution"
            )

        try:
            if self._emit_progress:
                yield SkillEvent(
                    event_type="progress",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={"progress": 50, "message": "执行中..."},
                    stage="async_legacy_execution"
                )

            # 调用适当的执行方法
            if self._use_async:
                result = await self._legacy_skill.execute_async(input_data)
            else:
                result = self._legacy_skill.execute(input_data)

            # 检查结果是否是协程
            if asyncio.iscoroutine(result):
                result = await result

            # 检查是否被取消
            if self._cancelled:
                yield SkillEvent(
                    event_type="cancelled",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={"reason": "cancelled_during_execution"},
                    stage="async_legacy_execution"
                )
                return

            # 保存结果
            context.intermediate_results.append({"legacy_result": result})

            if self._emit_progress:
                yield SkillEvent(
                    event_type="stage_completed",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={
                        "stage": "async_legacy_execution",
                        "result": result,
                        "result_type": type(result).__name__
                    },
                    stage="async_legacy_execution"
                )

        except Exception as e:
            yield SkillEvent(
                event_type="failed",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "stage": "async_legacy_execution"
                },
                stage="async_legacy_execution"
            )

    def _handle_cancel(self, data: Any):
        """处理取消命令"""
        self._cancelled = True
        if hasattr(self._legacy_skill, 'cancel') and callable(getattr(self._legacy_skill, 'cancel')):
            try:
                cancel_result = self._legacy_skill.cancel()
                if asyncio.iscoroutine(cancel_result):
                    asyncio.create_task(cancel_result)
            except Exception:
                pass
        return super()._handle_cancel(data)


def adapt_legacy_skill(
    legacy_skill: Any,
    skill_id: Optional[str] = None,
    is_async: bool = False,
    emit_progress: bool = True
) -> StreamSkill:
    """适配传统 Skill 为流式 Skill

    这是一个便捷函数，自动选择合适的适配器

    Args:
        legacy_skill: 传统 Skill 实例
        skill_id: Skill 标识符
        is_async: 是否是异步 Skill
        emit_progress: 是否发送进度事件

    Returns:
        流式 Skill 实例
    """
    if is_async:
        return AsyncLegacySkillAdapter(legacy_skill, skill_id, emit_progress)
    else:
        return LegacySkillAdapter(legacy_skill, skill_id, emit_progress)


class SkillRegistry:
    """Skill 注册表

    管理传统 Skill 和流式 Skill 的注册
    """

    def __init__(self):
        self._skills: dict[str, Any] = {}
        self._adapters: dict[str, StreamSkill] = {}

    def register(self, skill_id: str, skill: Any, is_async: bool = False) -> None:
        """注册 Skill

        Args:
            skill_id: Skill 标识符
            skill: Skill 实例（传统或流式）
            is_async: 是否是异步 Skill
        """
        self._skills[skill_id] = skill

        # 如果是传统 Skill，创建适配器
        if not isinstance(skill, StreamSkill):
            self._adapters[skill_id] = adapt_legacy_skill(skill, skill_id, is_async)
        else:
            self._adapters[skill_id] = skill

    def get(self, skill_id: str) -> Optional[Any]:
        """获取原始 Skill"""
        return self._skills.get(skill_id)

    def get_stream_skill(self, skill_id: str) -> Optional[StreamSkill]:
        """获取流式 Skill（自动适配）"""
        return self._adapters.get(skill_id)

    def unregister(self, skill_id: str) -> bool:
        """注销 Skill"""
        if skill_id in self._skills:
            del self._skills[skill_id]
            del self._adapters[skill_id]
            return True
        return False

    def list_skills(self) -> list[str]:
        """列出所有已注册的 Skill"""
        return list(self._skills.keys())
