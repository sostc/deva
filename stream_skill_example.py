#!/usr/bin/env python
"""
流式 Skill 框架完整使用示例

详细演示如何使用流式 Skill 框架实现动态智能执行
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


# =============================================================================
# 示例 1: 基础流式 Skill
# =============================================================================

class SimpleAnalysisSkill(StreamSkill):
    """
    简单的数据分析 Skill

    展示基本的流式执行模式：
    - 多阶段执行
    - 进度报告
    - 事件通知
    """

    def __init__(self, skill_id: str = "simple_analysis"):
        super().__init__(skill_id)

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行分析流程"""
        data_file = input_data.get("file", "data.csv")

        print(f"\n[Skill] 开始分析文件: {data_file}")

        # 阶段 1: 数据加载
        context.current_stage = "loading"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "loading", "file": data_file},
            stage="loading"
        )

        # 模拟加载耗时
        await asyncio.sleep(0.5)

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 30, "message": f"已加载 {data_file}"},
            stage="loading"
        )

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "loading"},
            stage="loading"
        )

        # 阶段 2: 数据处理
        context.current_stage = "processing"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "processing"},
            stage="processing"
        )

        # 模拟处理（可暂停）
        for i in range(3):
            # 检查是否被暂停
            await self._pause_event.wait()

            await asyncio.sleep(0.3)

            progress = 30 + (i + 1) * 20
            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"progress": progress, "message": f"处理中... {i+1}/3"},
                stage="processing"
            )

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "processing"},
            stage="processing"
        )

        # 阶段 3: 生成报告
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
            "records": 1000,
            "anomalies": 5,
            "status": "success"
        }

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 100, "message": "分析完成", "result": result},
            stage="report"
        )

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report", "result": result},
            stage="report"
        )

        print(f"[Skill] 分析完成!")


# =============================================================================
# 示例 2: 带澄清请求的 Skill
# =============================================================================

class SmartDataCleaningSkill(StreamSkill):
    """
    智能数据清洗 Skill

    展示如何使用澄清请求：
    - 遇到不确定性时暂停执行
    - 向 Agent 发起澄清请求
    - 根据响应继续执行
    - 保持上下文不丢失
    """

    def __init__(self, skill_id: str = "smart_cleaning"):
        super().__init__(skill_id)

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行智能数据清洗"""
        data_file = input_data.get("file", "dirty_data.csv")

        print(f"\n[Skill] 开始清洗数据: {data_file}")

        # 阶段 1: 扫描数据
        context.current_stage = "scanning"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "scanning"},
            stage="scanning"
        )

        await asyncio.sleep(0.5)

        # 模拟发现异常值
        outliers = [15, 23, 45, 67, 89]

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 40, "message": f"发现 {len(outliers)} 个异常值"},
            stage="scanning"
        )

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "scanning", "outliers_count": len(outliers)},
            stage="scanning"
        )

        # 阶段 2: 处理异常值（需要澄清）
        context.current_stage = "handling_outliers"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "handling_outliers"},
            stage="handling_outliers"
        )

        print(f"[Skill] 检测到 {len(outliers)} 个异常值，发起澄清请求...")

        # 🔥 关键：发起澄清请求
        # 这里 Skill 会暂停执行，等待 Agent 的响应
        response = await self.request_clarification(
            question=f"检测到 {len(outliers)} 个异常值，如何处理？",
            options=["删除", "保留", "替换为均值", "标记但不删除"],
            timeout_seconds=60,  # 60秒超时
            urgency="normal"
        )

        print(f"[Skill] 收到澄清响应: {response.answer}")

        # 根据响应处理
        action = response.answer

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 70, "message": f"选择处理方式: {action}"},
            stage="handling_outliers"
        )

        # 模拟处理
        await asyncio.sleep(0.5)

        # 保存处理结果到上下文
        context.intermediate_results.append({
            "outliers_handled": len(outliers),
            "action": action
        })

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "handling_outliers", "action": action},
            stage="handling_outliers"
        )

        # 阶段 3: 完成清洗
        context.current_stage = "finalizing"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "finalizing"},
            stage="finalizing"
        )

        await asyncio.sleep(0.3)

        result = {
            "file": data_file,
            "outliers_found": len(outliers),
            "outliers_action": action,
            "records_cleaned": 1000 - len(outliers) if action == "删除" else 1000
        }

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 100, "message": "清洗完成", "result": result},
            stage="finalizing"
        )

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "finalizing", "result": result},
            stage="finalizing"
        )

        print(f"[Skill] 清洗完成! 处理方式: {action}")


# =============================================================================
# 示例 3: 可动态干预的 Skill
# =============================================================================

class LongRunningTaskSkill(StreamSkill):
    """
    长时间运行任务 Skill

    展示如何支持动态干预：
    - 暂停和恢复
    - 参数更新
    - 取消执行
    """

    def __init__(self, skill_id: str = "long_task"):
        super().__init__(skill_id)
        self.batch_size = 10  # 默认批次大小

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行长时间任务"""
        task_name = input_data.get("task", "unknown")
        total_items = input_data.get("total", 50)

        print(f"\n[Skill] 开始执行任务: {task_name} (共 {total_items} 项)")

        context.current_stage = "processing"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "processing", "task": task_name, "total": total_items},
            stage="processing"
        )

        processed = 0
        batch_num = 0

        while processed < total_items:
            # 🔥 关键：检查是否被暂停
            # 如果 Agent 调用了 pause_skill，这里会等待
            await self._pause_event.wait()

            # 检查是否被取消
            if self._state.value == "cancelled":
                print(f"[Skill] 任务被取消!")
                yield SkillEvent(
                    event_type="cancelled",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={"processed": processed, "reason": "cancelled_by_user"},
                    stage="processing"
                )
                return

            batch_num += 1
            current_batch = min(self.batch_size, total_items - processed)

            # 模拟处理批次
            await asyncio.sleep(0.2)

            processed += current_batch
            progress = int(processed / total_items * 100)

            # 🔥 关键：可以从上下文中读取动态更新的参数
            priority = context.metadata.get("priority", "normal")

            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={
                    "progress": progress,
                    "message": f"处理批次 #{batch_num} ({current_batch} 项)",
                    "processed": processed,
                    "batch_size": self.batch_size,
                    "priority": priority
                },
                stage="processing"
            )

            print(f"[Skill] 批次 #{batch_num} 完成 (进度: {progress}%, 优先级: {priority})")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "processing", "total_processed": processed},
            stage="processing"
        )

        print(f"[Skill] 任务完成! 共处理 {processed} 项")

    def _handle_update_params(self, data: Any):
        """处理参数更新"""
        super()._handle_update_params(data)

        # 🔥 关键：响应参数更新
        if isinstance(data, dict):
            if "batch_size" in data:
                self.batch_size = data["batch_size"]
                print(f"[Skill] 批次大小更新为: {self.batch_size}")


# =============================================================================
# 使用示例
# =============================================================================

async def example_1_basic_usage():
    """示例 1: 基础用法"""
    print("\n" + "="*70)
    print("示例 1: 基础用法 - 流式执行 Skill")
    print("="*70)
    print("""
说明:
  这个示例展示了最基本的流式 Skill 使用方法。
  Skill 会按阶段执行，并通过事件流实时报告进度。
""")

    # 1. 获取执行引擎（单例）
    engine = get_execution_engine()

    # 2. 注册 Skill
    engine.register_skill("simple_analysis", SimpleAnalysisSkill)
    print("[Agent] 已注册 Skill: simple_analysis")

    # 3. 创建 Agent 接口
    interface = AgentSkillInterface("demo_agent")
    print("[Agent] 创建 Agent 接口")

    # 4. 定义事件处理回调
    async def on_event(event: SkillEvent):
        """处理 Skill 发送的事件"""
        if event.event_type == "stage_started":
            print(f"[Agent] 🚀 开始阶段: {event.data.get('stage')}")
        elif event.event_type == "stage_completed":
            print(f"[Agent] ✅ 完成阶段: {event.data.get('stage')}")
        elif event.event_type == "progress":
            progress = event.data.get('progress', 0)
            message = event.data.get('message', '')
            print(f"[Agent] 📊 进度: {progress}% - {message}")

    # 5. 流式调用 Skill
    print("\n[Agent] 开始执行 Skill...")
    print("-" * 70)

    async for event in interface.invoke_skill_stream(
        skill_id="simple_analysis",
        input_data={"file": "sales_data.csv"},
        on_event=on_event
    ):
        # 可以在这里处理事件，或者依赖 on_event 回调
        if event.event_type == "completed":
            print("-" * 70)
            print(f"[Agent] 🎉 Skill 执行完成!")
            print(f"[Agent] 最终结果: {event.data.get('context', {})}")


async def example_2_clarification():
    """示例 2: 澄清请求"""
    print("\n" + "="*70)
    print("示例 2: 澄清请求 - Skill 遇到不确定性时主动询问")
    print("="*70)
    print("""
说明:
  这个示例展示了 Skill 如何在遇到不确定性时发起澄清请求。
  Skill 会暂停执行，等待 Agent 的响应，然后继续执行。
  整个过程上下文保持不丢失。
""")

    engine = get_execution_engine()
    engine.register_skill("smart_cleaning", SmartDataCleaningSkill)
    print("[Agent] 已注册 Skill: smart_cleaning")

    interface = AgentSkillInterface("demo_agent_2")

    # 定义澄清处理函数
    async def on_clarification(request: ClarificationRequest):
        """
        处理 Skill 的澄清请求

        这里可以:
        1. 询问用户
        2. 调用 LLM 自动决策
        3. 根据策略自动选择
        """
        print(f"\n[Agent] ❓ 收到澄清请求:")
        print(f"[Agent]    问题: {request.question}")
        print(f"[Agent]    选项: {request.options}")

        # 模拟决策（实际中可以询问用户或调用 LLM）
        choice = request.options[0] if request.options else "继续"
        print(f"[Agent] 🤖 自动选择: {choice}")

        return choice

    async def on_event(event: SkillEvent):
        if event.event_type == "clarification_requested":
            print(f"[Agent] 📤 发送澄清请求...")
        elif event.event_type == "progress":
            progress = event.data.get('progress', 0)
            message = event.data.get('message', '')
            print(f"[Agent] 📊 进度: {progress}% - {message}")

    print("\n[Agent] 开始执行 Skill（会自动发起澄清请求）...")
    print("-" * 70)

    async for event in interface.invoke_skill_stream(
        skill_id="smart_cleaning",
        input_data={"file": "customer_data.csv"},
        on_event=on_event,
        on_clarification=on_clarification
    ):
        if event.event_type == "completed":
            print("-" * 70)
            print(f"[Agent] 🎉 Skill 执行完成!")


async def example_3_dynamic_intervention():
    """示例 3: 动态干预"""
    print("\n" + "="*70)
    print("示例 3: 动态干预 - 暂停、更新参数、恢复")
    print("="*70)
    print("""
说明:
  这个示例展示了 Agent 如何动态干预 Skill 的执行：
  1. 暂停 Skill 执行
  2. 更新执行参数
  3. 恢复 Skill 执行
  4. 观察参数变化的效果
""")

    engine = get_execution_engine()
    engine.register_skill("long_task", LongRunningTaskSkill)
    print("[Agent] 已注册 Skill: long_task")

    interface = AgentSkillInterface("demo_agent_3")

    async def on_event(event: SkillEvent):
        if event.event_type == "progress":
            progress = event.data.get('progress', 0)
            message = event.data.get('message', '')
            priority = event.data.get('priority', 'normal')
            batch_size = event.data.get('batch_size', 10)
            print(f"[Agent] 📊 进度: {progress}% | 批次: {batch_size} | 优先级: {priority} | {message}")

    print("\n[Agent] 启动长时间运行任务...")
    print("-" * 70)

    # 启动 Skill 执行（非阻塞）
    skill_task = asyncio.create_task(
        interface.invoke_skill(
            skill_id="long_task",
            input_data={"task": "data_migration", "total": 30},
            on_event=on_event
        )
    )

    # 等待 Skill 执行一段时间
    await asyncio.sleep(1.2)

    # 🔥 动态干预 1: 暂停
    print("\n" + "-" * 70)
    print("[Agent] ⏸️  暂停执行...")
    await interface.pause_skill("long_task")
    await asyncio.sleep(1)

    # 🔥 动态干预 2: 更新参数
    print("[Agent] 📝 更新参数: batch_size=20, priority=high")
    await interface.update_skill_params("long_task", {
        "batch_size": 20,
        "priority": "high"
    })
    await asyncio.sleep(0.5)

    # 🔥 动态干预 3: 恢复
    print("[Agent] ▶️  恢复执行...")
    print("-" * 70 + "\n")
    await interface.resume_skill("long_task")

    # 等待完成
    result = await skill_task

    print("-" * 70)
    print(f"[Agent] ✅ 任务完成!")
    print(f"[Agent] 执行结果: {'成功' if result['success'] else '失败'}")


async def main():
    """主函数"""
    print("\n" + "="*70)
    print("流式 Skill 框架使用示例")
    print("="*70)
    print("""
本示例演示流式 Skill 框架的三个核心特性:

1. 基础用法 - 流式执行和事件通知
2. 澄清请求 - Skill 主动询问，保持上下文
3. 动态干预 - Agent 实时控制 Skill 执行

每个示例都会详细展示代码实现和运行机制。
""")

    try:
        # 运行示例
        await example_1_basic_usage()
        await example_2_clarification()
        await example_3_dynamic_intervention()

        print("\n" + "="*70)
        print("所有示例执行完成!")
        print("="*70)
        print("""
总结:
  ✅ 流式执行 - 实时获取执行进度
  ✅ 澄清请求 - Skill 主动询问，上下文保持
  ✅ 动态干预 - 随时暂停、恢复、更新参数

你可以基于这个框架:
  1. 创建自己的流式 Skill
  2. 集成到现有系统
  3. 实现更复杂的交互逻辑
""")

    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
