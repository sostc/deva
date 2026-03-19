"""
流式 Skill 示例

展示如何使用流式 Skill 框架创建具有动态智能的 Skill
"""

import asyncio
import time
from typing import AsyncIterator, Any

from .models import SkillContext, SkillEvent, ClarificationRequest
from .stream_skill import StreamSkill


class DataAnalysisSkill(StreamSkill):
    """数据分析 Skill 示例

    展示如何在 Skill 中使用：
    1. 多阶段执行
    2. 进度报告
    3. 澄清请求
    4. 检查点创建
    """

    def __init__(self, skill_id: str = "data_analysis"):
        super().__init__(skill_id)

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行数据分析流程"""
        file_path = input_data.get("file", "unknown")

        # Stage 1: 数据加载
        context.current_stage = "data_loading"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "data_loading", "file": file_path},
            stage="data_loading"
        )

        # 模拟数据加载
        await asyncio.sleep(0.5)

        # 报告进度
        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 20, "message": "数据加载完成", "rows": 1000},
            stage="data_loading"
        )

        # 创建检查点
        context.create_checkpoint("data_loading")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "data_loading"},
            stage="data_loading"
        )

        # Stage 2: 数据清洗（可能需要澄清）
        context.current_stage = "data_cleaning"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "data_cleaning"},
            stage="data_cleaning"
        )

        # 模拟检测到异常值
        outliers = [10, 25, 30]  # 模拟异常值

        if outliers:
            # 发起澄清请求
            response = await self.request_clarification(
                question=f"检测到 {len(outliers)} 个异常值，如何处理？",
                options=["删除", "保留", "标记", "替换为均值"],
                timeout_seconds=30,
                urgency="normal"
            )

            # 根据响应处理
            action = response.answer
            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"progress": 40, "message": f"选择处理方式: {action}", "action": action},
                stage="data_cleaning"
            )

            # 模拟处理
            await asyncio.sleep(0.3)

        context.create_checkpoint("data_cleaning")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "data_cleaning"},
            stage="data_cleaning"
        )

        # Stage 3: 数据分析
        context.current_stage = "analysis"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "analysis"},
            stage="analysis"
        )

        # 模拟长时间运行的分析（可暂停）
        total_chunks = 5
        for i in range(total_chunks):
            # 检查是否被暂停
            await self._pause_event.wait()

            # 模拟分析
            await asyncio.sleep(0.2)

            progress = 50 + (i + 1) * 10
            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={
                    "progress": progress,
                    "message": f"分析进度: {i+1}/{total_chunks}",
                    "chunk": i + 1
                },
                stage="analysis"
            )

        # 保存分析结果
        context.intermediate_results.append({
            "analysis_result": {
                "mean": 42.0,
                "std": 5.5,
                "trend": "upward"
            }
        })

        context.create_checkpoint("analysis")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "analysis"},
            stage="analysis"
        )

        # Stage 4: 生成报告
        context.current_stage = "report_generation"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report_generation"},
            stage="report_generation"
        )

        await asyncio.sleep(0.3)

        final_result = {
            "file": file_path,
            "summary": "数据分析完成",
            "statistics": context.intermediate_results[-1]["analysis_result"],
            "checkpoints": len(context.checkpoints)
        }

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 100, "message": "报告生成完成", "result": final_result},
            stage="report_generation"
        )

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report_generation", "result": final_result},
            stage="report_generation"
        )


class SimpleTaskSkill(StreamSkill):
    """简单任务 Skill 示例

    展示最基本的流式 Skill 实现
    """

    def __init__(self, skill_id: str = "simple_task"):
        super().__init__(skill_id)

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行简单任务"""
        task_name = input_data.get("task", "unknown")

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"message": f"开始任务: {task_name}", "progress": 0}
        )

        # 模拟任务执行
        for i in range(10):
            await self._pause_event.wait()
            await asyncio.sleep(0.1)

            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"message": f"任务进度: {(i+1)*10}%", "progress": (i+1)*10}
            )

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"message": f"任务完成: {task_name}", "progress": 100, "result": "success"}
        )


class ClarificationDemoSkill(StreamSkill):
    """澄清请求演示 Skill

    展示如何在 Skill 中使用澄清请求
    """

    def __init__(self, skill_id: str = "clarification_demo"):
        super().__init__(skill_id)

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """演示澄清请求流程"""
        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"message": "开始演示澄清请求", "progress": 0}
        )

        # 第一个澄清请求
        response1 = await self.request_clarification(
            question="请选择数据处理方式",
            options=["平均值", "中位数", "最大值", "最小值"],
            timeout_seconds=60
        )

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={
                "message": f"选择的数据处理方式: {response1.answer}",
                "progress": 33,
                "choice": response1.answer
            }
        )

        # 第二个澄清请求（条件性）
        if response1.answer == "平均值":
            response2 = await self.request_clarification(
                question="是否排除异常值？",
                options=["是", "否"],
                timeout_seconds=30
            )

            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={
                    "message": f"排除异常值: {response2.answer}",
                    "progress": 66,
                    "exclude_outliers": response2.answer
                }
            )

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"message": "演示完成", "progress": 100}
        )


# 使用示例代码
async def demo_usage():
    """演示如何使用流式 Skill"""
    from .execution_engine import get_execution_engine
    from .agent_interface import AgentSkillInterface

    # 注册 Skill
    engine = get_execution_engine()
    engine.register_skill("data_analysis", DataAnalysisSkill)
    engine.register_skill("simple_task", SimpleTaskSkill)
    engine.register_skill("clarification_demo", ClarificationDemoSkill)

    # 创建 Agent 接口
    interface = AgentSkillInterface("demo_agent")

    # 定义事件处理
    async def on_event(event: SkillEvent):
        if event.event_type == "progress":
            print(f"  进度: {event.data.get('progress', 0)}% - {event.data.get('message', '')}")
        elif event.event_type == "clarification_requested":
            print(f"  [需要澄清] {event.data.get('question')}")

    # 定义澄清处理（自动选择第一个选项）
    async def on_clarification(request: ClarificationRequest):
        print(f"  [自动回答] 选择: {request.options[0] if request.options else '继续'}")
        return request.options[0] if request.options else "继续"

    # 执行 Skill
    print("\n=== 执行数据分析 Skill ===")
    async for event in interface.invoke_skill_stream(
        skill_id="data_analysis",
        input_data={"file": "sales_data.csv"},
        on_event=on_event,
        on_clarification=on_clarification
    ):
        if event.event_type == "completed":
            print(f"  完成! 结果: {event.data}")

    # 演示动态干预
    print("\n=== 演示动态干预 ===")

    # 启动一个长时间运行的 Skill
    task = asyncio.create_task(
        interface.invoke_skill(
            skill_id="simple_task",
            input_data={"task": "long_running_task"},
            on_event=on_event
        )
    )

    # 等待一会儿
    await asyncio.sleep(0.3)

    # 暂停
    print("  [干预] 暂停任务")
    await interface.pause_skill("simple_task")

    await asyncio.sleep(0.5)

    # 恢复
    print("  [干预] 恢复任务")
    await interface.resume_skill("simple_task")

    # 等待完成
    result = await task
    print(f"  最终结果: {result['success']}")


if __name__ == "__main__":
    # 运行演示
    asyncio.run(demo_usage())
