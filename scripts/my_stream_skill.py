#!/usr/bin/env python
"""
我的流式 Skill - 数据分析处理

支持多阶段处理和动态澄清请求
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


class MyDataAnalysisSkill(StreamSkill):
    """
    我的数据分析 Skill

    功能：
    1. 加载和验证数据
    2. 数据清洗（处理缺失值、异常值）
    3. 数据转换
    4. 生成分析报告

    澄清请求点：
    - 数据质量检查时发现严重问题
    - 发现异常值需要处理策略
    - 选择数据分析算法
    - 报告格式和内容确认
    """

    def __init__(self, skill_id: str = "my_data_analysis"):
        super().__init__(skill_id)
        self.processing_config = {
            "batch_size": 100,
            "max_workers": 4,
            "timeout": 300
        }

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """
        执行数据分析流程

        Args:
            input_data: 包含 file_path, options 等配置
            context: 执行上下文
        """
        file_path = input_data.get("file_path", "data.csv")
        analysis_type = input_data.get("analysis_type", "general")

        print(f"\n🚀 [Skill] 开始数据分析: {file_path}")
        print(f"   分析类型: {analysis_type}")

        # =====================================================================
        # 阶段 1: 数据加载和验证
        # =====================================================================
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

        # 模拟数据验证结果
        validation_result = {
            "total_rows": 5000,
            "missing_rate": 0.08,  # 8% 缺失率
            "duplicate_rate": 0.03,  # 3% 重复率
            "format_issues": 12
        }

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={
                "progress": 15,
                "message": f"数据加载完成，共 {validation_result['total_rows']} 行",
                "validation": validation_result
            },
            stage="data_loading"
        )

        # 🔥 澄清请求 1: 数据质量确认
        if validation_result["missing_rate"] > 0.05 or validation_result["duplicate_rate"] > 0.02:
            print(f"\n⚠️  [Skill] 数据质量检查发现问题:")
            print(f"   - 缺失率: {validation_result['missing_rate']*100:.1f}%")
            print(f"   - 重复率: {validation_result['duplicate_rate']*100:.1f}%")
            print(f"   - 格式问题: {validation_result['format_issues']} 处")

            response = await self.request_clarification(
                question=f"数据质量检查发现问题（缺失率 {validation_result['missing_rate']*100:.1f}%、重复率 {validation_result['duplicate_rate']*100:.1f}%），是否继续处理？",
                options=[
                    "继续处理（自动修复问题）",
                    "仅处理完整数据（删除有问题的行）",
                    "停止并报告问题",
                    "忽略问题继续分析"
                ],
                timeout_seconds=60,
                urgency="high",
                context_data={"validation": validation_result}
            )

            print(f"✅ [Skill] 用户/AI 决策: {response.answer}")

            # 根据决策调整处理策略
            if "停止" in response.answer:
                yield SkillEvent(
                    event_type="failed",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={"error": "用户选择停止分析", "validation": validation_result},
                    stage="data_loading"
                )
                return
            elif "仅处理完整数据" in response.answer:
                self.processing_config["skip_invalid"] = True

        # 保存验证结果
        context.intermediate_results.append({"validation": validation_result})
        context.create_checkpoint("data_loading")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "data_loading", "rows": validation_result["total_rows"]},
            stage="data_loading"
        )

        # =====================================================================
        # 阶段 2: 数据清洗
        # =====================================================================
        context.current_stage = "data_cleaning"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "data_cleaning"},
            stage="data_cleaning"
        )

        # 模拟发现异常值
        outliers = {
            "extreme_values": 8,
            "duplicates": 150,
            "format_errors": 12
        }

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={
                "progress": 30,
                "message": f"发现数据问题: 极端值({outliers['extreme_values']}), 重复({outliers['duplicates']}), 格式错误({outliers['format_errors']})"
            },
            stage="data_cleaning"
        )

        # 🔥 澄清请求 2: 异常值处理策略
        if sum(outliers.values()) > 10:
            print(f"\n⚠️  [Skill] 发现较多数据问题，需要制定处理策略")

            response = await self.request_clarification(
                question=f"发现 {sum(outliers.values())} 处数据问题，请制定清洗策略优先级",
                options=[
                    "先处理极端值（对分析影响最大）",
                    "先处理重复数据（数量最多）",
                    "先修复格式错误（基础问题）",
                    "智能批量处理（系统自动决策）"
                ],
                timeout_seconds=60,
                urgency="normal",
                context_data={"outliers": outliers}
            )

            print(f"✅ [Skill] 清洗策略: {response.answer}")

            # 保存策略
            context.metadata["cleaning_strategy"] = response.answer

        # 模拟清洗过程（可暂停）
        cleaning_steps = ["处理缺失值", "处理异常值", "去重", "格式标准化"]
        for i, step in enumerate(cleaning_steps):
            # 检查是否被暂停
            await self._pause_event.wait()

            await asyncio.sleep(0.3)

            progress = 30 + (i + 1) * 10
            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"progress": progress, "message": f"清洗步骤: {step}"},
                stage="data_cleaning"
            )

            print(f"🧹 [Skill] 完成: {step}")

        # 保存清洗结果
        cleaned_rows = validation_result["total_rows"] - outliers["duplicates"]
        context.intermediate_results.append({"cleaned_rows": cleaned_rows})
        context.create_checkpoint("data_cleaning")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "data_cleaning", "cleaned_rows": cleaned_rows},
            stage="data_cleaning"
        )

        # =====================================================================
        # 阶段 3: 分析策略选择
        # =====================================================================
        context.current_stage = "analysis_strategy"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "analysis_strategy"},
            stage="analysis_strategy"
        )

        # 🔥 澄清请求 3: 选择分析算法
        print(f"\n🤔 [Skill] 需要选择分析算法")

        response = await self.request_clarification(
            question=f"基于数据特征（{cleaned_rows} 行，已清洗），选择哪种分析策略？",
            options=[
                "描述性统计（快速了解数据分布）",
                "相关性分析（发现变量关系）",
                "趋势分析（时间序列模式）",
                "聚类分析（发现数据分组）",
                "全面分析（包含以上所有）"
            ],
            timeout_seconds=60,
            urgency="normal",
            context_data={
                "rows": cleaned_rows,
                "analysis_type": analysis_type
            }
        )

        selected_strategy = response.answer
        print(f"✅ [Skill] 选择策略: {selected_strategy}")

        # 保存策略
        context.metadata["analysis_strategy"] = selected_strategy

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 70, "message": f"选择策略: {selected_strategy}"},
            stage="analysis_strategy"
        )

        context.create_checkpoint("analysis_strategy")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "analysis_strategy", "strategy": selected_strategy},
            stage="analysis_strategy"
        )

        # =====================================================================
        # 阶段 4: 执行分析
        # =====================================================================
        context.current_stage = "analysis_execution"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "analysis_execution", "strategy": selected_strategy},
            stage="analysis_execution"
        )

        # 模拟长时间分析（可暂停）
        analysis_steps = 5
        for i in range(analysis_steps):
            # 检查是否被暂停
            await self._pause_event.wait()

            await asyncio.sleep(0.4)

            progress = 70 + (i + 1) * 5
            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={
                    "progress": progress,
                    "message": f"{selected_strategy} 分析中... {i+1}/{analysis_steps}"
                },
                stage="analysis_execution"
            )

            print(f"📊 [Skill] 分析进度: {progress}%")

        # 保存分析结果
        analysis_result = {
            "strategy": selected_strategy,
            "rows_analyzed": cleaned_rows,
            "findings": [
                "发现 3 个关键趋势",
                "识别 2 个异常模式",
                "找到 5 个强相关变量"
            ]
        }
        context.intermediate_results.append({"analysis": analysis_result})
        context.create_checkpoint("analysis_execution")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "analysis_execution", "result": analysis_result},
            stage="analysis_execution"
        )

        # =====================================================================
        # 阶段 5: 报告生成
        # =====================================================================
        context.current_stage = "report_generation"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report_generation"},
            stage="report_generation"
        )

        # 🔥 澄清请求 4: 报告格式确认
        print(f"\n📝 [Skill] 准备生成报告")

        response = await self.request_clarification(
            question="分析即将完成，请选择报告格式",
            options=[
                "详细报告（包含所有图表和数据）",
                "摘要报告（关键发现和建议）",
                "技术报告（适合数据科学家）",
                "业务报告（适合管理层）"
            ],
            timeout_seconds=60,
            urgency="normal"
        )

        report_format = response.answer
        print(f"✅ [Skill] 报告格式: {report_format}")

        await asyncio.sleep(0.5)

        # 生成报告
        final_report = {
            "file": file_path,
            "format": report_format,
            "strategy": selected_strategy,
            "data_quality": {
                "original_rows": validation_result["total_rows"],
                "cleaned_rows": cleaned_rows,
                "quality_score": 85
            },
            "analysis_findings": analysis_result["findings"],
            "recommendations": [
                "建议关注识别出的异常模式",
                "可以考虑深入分析强相关变量",
                "数据收集流程可以优化以减少缺失值"
            ],
            "checkpoints": len(context.checkpoints),
            "ai_decisions": len(context.intermediate_results)
        }

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 100, "message": "报告生成完成", "report": final_report},
            stage="report_generation"
        )

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report_generation", "report": final_report},
            stage="report_generation"
        )

        print(f"\n✨ [Skill] 分析完成!")
        print(f"   使用策略: {selected_strategy}")
        print(f"   报告格式: {report_format}")
        print(f"   AI 决策次数: {len(context.intermediate_results)}")
        print(f"   检查点数量: {len(context.checkpoints)}")


# =============================================================================
# 使用示例
# =============================================================================

async def trae_ai_handler(request: ClarificationRequest) -> str:
    """
    TRAE AI 处理澄清请求

    这里你可以：
    1. 调用真实的 LLM API
    2. 询问用户输入
    3. 根据规则自动决策
    """
    print(f"\n" + "="*70)
    print("🧠 TRAE AI 正在分析...")
    print("="*70)
    print(f"❓ {request.question}")
    print(f"\n📋 选项:")
    for i, option in enumerate(request.options, 1):
        print(f"   {i}. {option}")

    # 模拟 AI 思考
    await asyncio.sleep(0.5)

    # 简单的决策逻辑（实际中可以调用 LLM）
    question = request.question

    if "数据质量" in question:
        choice = "继续处理（自动修复问题）"
    elif "清洗策略" in question:
        choice = "先处理极端值（对分析影响最大）"
    elif "分析策略" in question:
        choice = "全面分析（包含以上所有）"
    elif "报告格式" in question:
        choice = "详细报告（包含所有图表和数据）"
    else:
        choice = request.options[0] if request.options else "继续"

    print(f"\n✅ AI 决策: {choice}")
    print("="*70)

    return choice


async def main():
    """主函数"""
    print("\n" + "="*70)
    print("我的流式 Skill - 数据分析处理")
    print("="*70)

    # 注册 Skill
    engine = get_execution_engine()
    engine.register_skill("my_data_analysis", MyDataAnalysisSkill)
    print("\n✅ 已注册 Skill: my_data_analysis")

    # 创建 Agent 接口
    interface = AgentSkillInterface("my_agent")
    print("✅ 创建 Agent 接口")

    # 定义事件处理
    async def on_event(event: SkillEvent):
        if event.event_type == "stage_started":
            print(f"\n🚀 开始阶段: {event.data.get('stage')}")
        elif event.event_type == "stage_completed":
            print(f"✅ 完成阶段: {event.data.get('stage')}")
        elif event.event_type == "progress":
            progress = event.data.get('progress', 0)
            message = event.data.get('message', '')
            print(f"📊 进度: {progress}% - {message}")

    # 执行 Skill
    print("\n" + "-"*70)
    print("开始执行数据分析...")
    print("-"*70)

    try:
        async for event in interface.invoke_skill_stream(
            skill_id="my_data_analysis",
            input_data={
                "file_path": "sales_data_2024.csv",
                "analysis_type": "comprehensive"
            },
            on_event=on_event,
            on_clarification=trae_ai_handler
        ):
            if event.event_type == "completed":
                print("\n" + "-"*70)
                print("🎉 Skill 执行完成!")
                print("-"*70)

                result = event.data.get('context', {})
                print(f"\n📈 执行统计:")
                print(f"   检查点数量: {result.get('checkpoints_count', 0)}")
                print(f"   中间结果数: {result.get('intermediate_results_count', 0)}")

    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*70)
    print("示例完成!")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
