"""
流式 Skill 框架演示

展示如何使用流式 Skill 框架创建具有动态智能的 Skill
"""

import asyncio
import time
from typing import AsyncIterator, Any

from deva.naja.stream_skill import (
    StreamSkill,
    SkillContext,
    SkillEvent,
    ClarificationRequest,
    get_execution_engine,
    AgentSkillInterface,
)


class DataProcessingSkill(StreamSkill):
    """数据处理 Skill - 展示多阶段执行和澄清请求"""

    def __init__(self, skill_id: str = "data_processing"):
        super().__init__(skill_id)

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行数据处理流程"""
        data_file = input_data.get("file", "unknown.csv")

        # Stage 1: 数据加载
        context.current_stage = "loading"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "loading", "file": data_file},
            stage="loading"
        )

        # 模拟加载
        await asyncio.sleep(0.5)

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 25, "message": f"已加载 {data_file}"},
            stage="loading"
        )

        context.create_checkpoint("loading")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "loading"},
            stage="loading"
        )

        # Stage 2: 数据清洗（需要澄清）
        context.current_stage = "cleaning"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "cleaning"},
            stage="cleaning"
        )

        # 检测到异常值，发起澄清请求
        response = await self.request_clarification(
            question="检测到 5 个异常值，如何处理？",
            options=["删除", "保留", "替换为均值", "标记"],
            timeout_seconds=30,
            urgency="normal"
        )

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 50, "message": f"选择处理方式: {response.answer}"},
            stage="cleaning"
        )

        # 模拟处理
        await asyncio.sleep(0.3)
        context.create_checkpoint("cleaning")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "cleaning", "action": response.answer},
            stage="cleaning"
        )

        # Stage 3: 数据分析（可暂停）
        context.current_stage = "analysis"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "analysis"},
            stage="analysis"
        )

        # 长时间运行的分析
        for i in range(5):
            # 检查是否被暂停
            await self._pause_event.wait()

            await asyncio.sleep(0.2)

            progress = 50 + (i + 1) * 10
            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"progress": progress, "message": f"分析中... {i+1}/5"},
                stage="analysis"
            )

        context.create_checkpoint("analysis")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "analysis"},
            stage="analysis"
        )

        # Stage 4: 生成报告
        context.current_stage = "report"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report"},
            stage="report"
        )

        await asyncio.sleep(0.3)

        result = {
            "file": data_file,
            "records_processed": 1000,
            "anomalies_handled": 5,
            "checkpoints": len(context.checkpoints)
        }

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 100, "message": "处理完成", "result": result},
            stage="report"
        )

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report", "result": result},
            stage="report"
        )


async def demo_basic_usage():
    """演示基本用法"""
    print("\n" + "="*60)
    print("演示 1: 基本用法 - 流式执行 Skill")
    print("="*60)

    # 注册 Skill
    engine = get_execution_engine()
    engine.register_skill("data_processing", DataProcessingSkill)

    # 创建 Agent 接口
    interface = AgentSkillInterface("demo_agent")

    # 定义事件处理
    async def on_event(event: SkillEvent):
        if event.event_type == "progress":
            print(f"  📊 进度: {event.data.get('progress', 0)}% - {event.data.get('message', '')}")
        elif event.event_type == "stage_started":
            print(f"  🚀 开始阶段: {event.data.get('stage')}")
        elif event.event_type == "stage_completed":
            print(f"  ✅ 完成阶段: {event.data.get('stage')}")
        elif event.event_type == "clarification_requested":
            print(f"  ❓ 需要澄清: {event.data.get('question')}")

    # 定义澄清处理（自动选择）
    async def on_clarification(request: ClarificationRequest):
        choice = request.options[0] if request.options else "继续"
        print(f"  🤖 自动回答: {choice}")
        return choice

    # 执行 Skill
    print("\n开始执行数据处理...")
    async for event in interface.invoke_skill_stream(
        skill_id="data_processing",
        input_data={"file": "sales_data.csv"},
        on_event=on_event,
        on_clarification=on_clarification
    ):
        if event.event_type == "completed":
            print(f"\n  🎉 完成! 结果: {event.data.get('context', {})}")


async def demo_dynamic_intervention():
    """演示动态干预"""
    print("\n" + "="*60)
    print("演示 2: 动态干预 - 暂停、更新参数、恢复")
    print("="*60)

    engine = get_execution_engine()
    engine.register_skill("data_processing_2", DataProcessingSkill)

    interface = AgentSkillInterface("demo_agent_2")

    event_count = 0

    async def on_event(event: SkillEvent):
        nonlocal event_count
        event_count += 1

        if event.event_type == "progress":
            print(f"  📊 进度: {event.data.get('progress', 0)}% - {event.data.get('message', '')}")

    async def on_clarification(request: ClarificationRequest):
        choice = request.options[0] if request.options else "继续"
        print(f"  🤖 自动回答: {choice}")
        return choice

    # 启动执行
    print("\n启动数据处理...")

    async def run_skill():
        async for event in interface.invoke_skill_stream(
            skill_id="data_processing_2",
            input_data={"file": "market_data.csv"},
            on_event=on_event,
            on_clarification=on_clarification
        ):
            pass

    # 创建任务
    task = asyncio.create_task(run_skill())

    # 等待一段时间
    await asyncio.sleep(1.5)

    # 暂停
    print("\n  ⏸️  暂停执行...")
    await interface.pause_skill("data_processing_2")

    await asyncio.sleep(1)

    # 更新参数
    print("  📝 更新参数...")
    await interface.update_skill_params("data_processing_2", {"priority": "high", "batch_size": 500})

    await asyncio.sleep(0.5)

    # 恢复
    print("  ▶️  恢复执行...\n")
    await interface.resume_skill("data_processing_2")

    # 等待完成
    await task

    print(f"\n  ✅ 执行完成，共处理 {event_count} 个事件")


async def demo_batch_execution():
    """演示批量执行"""
    print("\n" + "="*60)
    print("演示 3: 批量执行 - 同时运行多个 Skill")
    print("="*60)

    engine = get_execution_engine()

    # 创建多个 Skill 实例
    class QuickSkill(StreamSkill):
        def __init__(self, skill_id: str, duration: float):
            super().__init__(skill_id)
            self.duration = duration

        async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
            name = input_data.get("name", "unknown")
            await asyncio.sleep(self.duration)

            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"message": f"Skill {name} 完成", "duration": self.duration}
            )

    # 注册多个 Skill
    engine.register_skill("quick_1", lambda: QuickSkill("quick_1", 0.3))
    engine.register_skill("quick_2", lambda: QuickSkill("quick_2", 0.5))
    engine.register_skill("quick_3", lambda: QuickSkill("quick_3", 0.2))

    # 批量执行
    from deva.naja.stream_skill.agent_interface import BatchSkillInterface

    batch = BatchSkillInterface("batch_agent")

    skill_configs = [
        {"skill_id": "quick_1", "input_data": {"name": "A"}},
        {"skill_id": "quick_2", "input_data": {"name": "B"}},
        {"skill_id": "quick_3", "input_data": {"name": "C"}},
    ]

    print("\n并行执行 3 个 Skill...")

    async def on_event(skill_id: str, event: SkillEvent):
        if event.event_type == "progress":
            print(f"  📦 {skill_id}: {event.data.get('message')}")

    results = await batch.execute_multiple(skill_configs, on_event)

    print("\n  批量执行结果:")
    for skill_id, result in results.items():
        status = "✅ 成功" if result.get("success") else "❌ 失败"
        print(f"    {skill_id}: {status}")


async def demo_engine_stats():
    """演示引擎统计"""
    print("\n" + "="*60)
    print("演示 4: 引擎统计信息")
    print("="*60)

    engine = get_execution_engine()

    stats = engine.get_engine_stats()

    print("\n引擎统计:")
    print(f"  📊 总会话数: {stats['total_sessions']}")
    print(f"  🔧 注册 Skill 数: {stats['registered_skills']}")
    print(f"  📬 事件总线大小: {stats['event_bus_size']}")
    print(f"  📈 状态分布: {stats['status_breakdown']}")

    # 列出所有会话
    sessions = engine.list_sessions()
    print(f"\n  活跃会话列表 ({len(sessions)} 个):")
    for session in sessions[-5:]:  # 只显示最后 5 个
        print(f"    - {session['session_id'][:8]}... ({session['skill_id']}) - {session['status']}")


async def main():
    """主函数"""
    print("\n" + "="*60)
    print("流式 Skill 框架演示")
    print("="*60)
    print("\n这个演示展示了流式 Skill 框架的核心功能:")
    print("1. 流式执行和事件通知")
    print("2. 澄清请求和响应")
    print("3. 动态干预（暂停、恢复、参数更新）")
    print("4. 批量执行")
    print("5. 引擎统计")

    try:
        await demo_basic_usage()
        await demo_dynamic_intervention()
        await demo_batch_execution()
        await demo_engine_stats()

        print("\n" + "="*60)
        print("演示完成!")
        print("="*60)

    except Exception as e:
        print(f"\n  ❌ 演示出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 运行演示
    asyncio.run(main())
