#!/usr/bin/env python
"""
流式 Skill + TRAE AI 处理示例

这个示例展示如何让 TRAE 来处理 Skill 的澄清请求和决策
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
# 定义一个需要 AI 决策的 Skill
# =============================================================================

class AIDataAnalysisSkill(StreamSkill):
    """
    AI 数据分析 Skill
    
    这个 Skill 会在以下场景发起澄清请求，需要 TRAE 的 AI 来处理：
    1. 发现异常值时 - 询问如何处理
    2. 数据质量问题 - 询问是否继续
    3. 分析策略选择 - 询问使用哪种算法
    """

    def __init__(self, skill_id: str = "ai_data_analysis"):
        super().__init__(skill_id)

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行 AI 数据分析"""
        data_file = input_data.get("file", "data.csv")
        
        print(f"\n🤖 [Skill] 开始 AI 数据分析: {data_file}")
        
        # 阶段 1: 数据加载和验证
        context.current_stage = "validation"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "validation", "file": data_file},
            stage="validation"
        )
        
        await asyncio.sleep(0.5)
        
        # 模拟数据质量检查
        missing_rate = 0.15  # 15% 缺失率
        
        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 20, "message": f"数据验证完成，缺失率: {missing_rate*100:.1f}%"},
            stage="validation"
        )
        
        # 🔥 澄清请求 1: 数据质量问题
        if missing_rate > 0.1:
            print(f"\n🤖 [Skill] 数据缺失率较高 ({missing_rate*100:.1f}%)，需要 AI 决策")
            
            response = await self.request_clarification(
                question=f"数据缺失率为 {missing_rate*100:.1f}%，超过 10% 阈值。如何处理？",
                options=[
                    "删除缺失行（简单但可能丢失信息）",
                    "填充均值（保持数据量但可能失真）",
                    "使用插值（更智能但计算复杂）",
                    "停止分析（数据质量不足）"
                ],
                timeout_seconds=60,
                urgency="high",
                context_data={"missing_rate": missing_rate, "total_rows": 1000}
            )
            
            print(f"🤖 [Skill] AI 决策: {response.answer}")
            
            # 如果决定停止
            if "停止分析" in response.answer:
                yield SkillEvent(
                    event_type="failed",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={"error": "数据质量不足，AI 建议停止分析", "missing_rate": missing_rate},
                    stage="validation"
                )
                return
        
        context.create_checkpoint("validation")
        
        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "validation"},
            stage="validation"
        )
        
        # 阶段 2: 异常值检测
        context.current_stage = "outlier_detection"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "outlier_detection"},
            stage="outlier_detection"
        )
        
        await asyncio.sleep(0.5)
        
        # 模拟发现不同类型的异常值
        outliers = {
            "极端值": 3,
            "重复数据": 12,
            "格式错误": 5
        }
        
        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 40, "message": f"发现异常值: {outliers}"},
            stage="outlier_detection"
        )
        
        # 🔥 澄清请求 2: 异常值处理策略
        print(f"\n🤖 [Skill] 发现多种异常值，需要 AI 制定处理策略")
        
        response = await self.request_clarification(
            question=f"发现 {sum(outliers.values())} 处数据问题：极端值({outliers['极端值']}), 重复({outliers['重复数据']}), 格式错误({outliers['格式错误']})。请制定处理优先级策略。",
            options=[
                "先处理极端值（影响最大）",
                "先处理重复数据（数量最多）",
                "先处理格式错误（基础问题）",
                "批量处理所有问题"
            ],
            timeout_seconds=60,
            urgency="normal"
        )
        
        print(f"🤖 [Skill] AI 策略: {response.answer}")
        
        # 保存 AI 决策到上下文
        context.intermediate_results.append({
            "outliers": outliers,
            "strategy": response.answer
        })
        
        context.create_checkpoint("outlier_detection")
        
        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "outlier_detection", "strategy": response.answer},
            stage="outlier_detection"
        )
        
        # 阶段 3: 分析策略选择
        context.current_stage = "strategy_selection"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "strategy_selection"},
            stage="strategy_selection"
        )
        
        await asyncio.sleep(0.3)
        
        # 🔥 澄清请求 3: 分析算法选择
        print(f"\n🤖 [Skill] 需要选择分析算法")
        
        response = await self.request_clarification(
            question="基于数据特征（存在异常值、15%缺失率），选择哪种分析策略最合适？",
            options=[
                "稳健统计（对异常值不敏感）",
                "机器学习（自动学习模式）",
                "时间序列（考虑时序特征）",
                "探索性分析（全面了解数据）"
            ],
            timeout_seconds=60,
            urgency="normal"
        )
        
        print(f"🤖 [Skill] AI 选择算法: {response.answer}")
        
        selected_algorithm = response.answer
        
        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 60, "message": f"选择算法: {selected_algorithm}"},
            stage="strategy_selection"
        )
        
        context.create_checkpoint("strategy_selection")
        
        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "strategy_selection", "algorithm": selected_algorithm},
            stage="strategy_selection"
        )
        
        # 阶段 4: 执行分析（可暂停）
        context.current_stage = "analysis"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "analysis", "algorithm": selected_algorithm},
            stage="analysis"
        )
        
        # 模拟长时间分析
        for i in range(5):
            # 检查是否被暂停
            await self._pause_event.wait()
            
            await asyncio.sleep(0.3)
            
            progress = 60 + (i + 1) * 8
            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"progress": progress, "message": f"{selected_algorithm} 分析中... {i+1}/5"},
                stage="analysis"
            )
            
            print(f"🤖 [Skill] 分析进度: {progress}%")
        
        context.create_checkpoint("analysis")
        
        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "analysis"},
            stage="analysis"
        )
        
        # 阶段 5: 生成报告
        context.current_stage = "report"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report"},
            stage="report"
        )
        
        await asyncio.sleep(0.3)
        
        final_result = {
            "file": data_file,
            "algorithm": selected_algorithm,
            "data_quality": {
                "missing_rate": missing_rate,
                "outliers": outliers
            },
            "ai_decisions": len(context.intermediate_results),
            "checkpoints": len(context.checkpoints)
        }
        
        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 100, "message": "分析完成", "result": final_result},
            stage="report"
        )
        
        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report", "result": final_result},
            stage="report"
        )
        
        print(f"\n🤖 [Skill] 分析完成!")
        print(f"   使用算法: {selected_algorithm}")
        print(f"   AI 决策次数: {len(context.intermediate_results)}")
        print(f"   检查点数量: {len(context.checkpoints)}")


# =============================================================================
# TRAE AI 处理函数
# =============================================================================

async def tra_ai_handler(request: ClarificationRequest) -> str:
    """
    TRAE AI 处理澄清请求
    
    这个函数会调用 TRAE 的 AI 来分析和决策
    """
    print(f"\n" + "="*70)
    print("🧠 TRAE AI 正在分析澄清请求...")
    print("="*70)
    print(f"\n❓ 问题: {request.question}")
    print(f"\n📋 选项:")
    for i, option in enumerate(request.options, 1):
        print(f"   {i}. {option}")
    
    if request.context:
        print(f"\n📊 上下文信息:")
        for key, value in request.context.items():
            print(f"   - {key}: {value}")
    
    print(f"\n⏱️  超时时间: {request.timeout_seconds}秒")
    print(f"⚡ 紧急程度: {request.urgency}")
    
    # 模拟 AI 思考过程
    print(f"\n🤔 AI 思考中...")
    await asyncio.sleep(1)
    
    # 这里可以集成真实的 LLM 调用
    # 例如调用 OpenAI、Claude 等
    
    # 模拟 AI 决策逻辑
    question_lower = request.question.lower()
    
    if "缺失" in question_lower or "missing" in question_lower:
        # 数据缺失问题 - 选择智能填充
        choice = "使用插值（更智能但计算复杂）"
    elif "异常值" in question_lower or "outlier" in question_lower:
        # 异常值问题 - 选择先处理影响最大的
        choice = "先处理极端值（影响最大）"
    elif "算法" in question_lower or "algorithm" in question_lower:
        # 算法选择 - 根据数据质量选择
        if request.context and request.context.get("missing_rate", 0) > 0.1:
            choice = "稳健统计（对异常值不敏感）"
        else:
            choice = "机器学习（自动学习模式）"
    else:
        # 默认选择第一个
        choice = request.options[0] if request.options else "继续"
    
    print(f"\n✅ AI 决策: {choice}")
    print(f"\n💡 决策理由:")
    
    if "插值" in choice:
        print("   - 数据缺失率较高，需要智能填充")
        print("   - 插值能更好地保持数据趋势")
        print("   - 虽然计算复杂但结果更准确")
    elif "极端值" in choice:
        print("   - 极端值对分析结果影响最大")
        print("   - 优先处理能显著提升数据质量")
        print("   - 其他问题可以在后续处理")
    elif "稳健统计" in choice:
        print("   - 数据存在较多异常值")
        print("   - 稳健统计对异常值不敏感")
        print("   - 适合当前数据质量状况")
    
    print("="*70)
    
    return choice


# =============================================================================
# 主程序
# =============================================================================

async def main():
    """主函数"""
    print("\n" + "="*70)
    print("流式 Skill + TRAE AI 智能处理示例")
    print("="*70)
    print("""
这个示例展示了：
1. Skill 在执行过程中遇到不确定性时发起澄清请求
2. TRAE 的 AI 分析请求并做出决策
3. Skill 根据 AI 决策继续执行
4. 整个过程支持暂停、恢复、动态干预

特点：
- 🤖 Skill 不再是黑盒执行
- 🧠 AI 参与决策过程
- 🔄 可交互、可干预
- 💾 上下文保持不丢失
""")
    
    # 注册 Skill
    engine = get_execution_engine()
    engine.register_skill("ai_data_analysis", AIDataAnalysisSkill)
    print("\n✅ 已注册 Skill: ai_data_analysis")
    
    # 创建 Agent 接口
    interface = AgentSkillInterface("trae_agent")
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
    print("开始执行 AI 数据分析...")
    print("-"*70)
    
    try:
        async for event in interface.invoke_skill_stream(
            skill_id="ai_data_analysis",
            input_data={"file": "sales_data_2024.csv"},
            on_event=on_event,
            on_clarification=tra_ai_handler  # 使用 TRAE AI 处理澄清
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
