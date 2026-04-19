#!/usr/bin/env python
"""
用流式 Skill 分析 infoharbor_block.dat 文件

这个文件包含股票板块分类数据
"""

import asyncio
import time
from typing import AsyncIterator, Any
from collections import defaultdict

from deva.naja.stream_skill import (
    StreamSkill,
    SkillContext,
    SkillEvent,
    ClarificationRequest,
    get_execution_engine,
    AgentSkillInterface,
)


class InfoharborAnalysisSkill(StreamSkill):
    """
    Infoharbor 板块数据分析 Skill

    分析股票板块数据文件，包括：
    1. 板块数量和分布
    2. 股票代码统计
    3. 数据质量检查
    4. 板块分类分析
    """

    def __init__(self, skill_id: str = "infoharbor_analysis"):
        super().__init__(skill_id)

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行分析流程"""
        file_path = input_data.get("file_path", "")

        print(f"\n🚀 [Skill] 开始分析文件: {file_path}")

        # =====================================================================
        # 阶段 1: 文件加载和解析
        # =====================================================================
        context.current_stage = "file_loading"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "file_loading", "file": file_path},
            stage="file_loading"
        )

        # 读取文件
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            yield SkillEvent(
                event_type="failed",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"error": f"文件读取失败: {e}"},
                stage="file_loading"
            )
            return

        total_lines = len(lines)

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 20, "message": f"文件加载完成，共 {total_lines} 行"},
            stage="file_loading"
        )

        context.intermediate_results.append({"total_lines": total_lines})
        context.create_checkpoint("file_loading")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "file_loading", "lines": total_lines},
            stage="file_loading"
        )

        # =====================================================================
        # 阶段 2: 数据解析和结构分析
        # =====================================================================
        context.current_stage = "data_parsing"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "data_parsing"},
            stage="data_parsing"
        )

        # 解析数据
        blocks = []  # 板块信息
        current_block = None
        all_stocks = set()
        block_stock_count = defaultdict(int)

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # 检查是否是板块标题行（以 #GN_ 开头）
            if line.startswith('#GN_'):
                # 保存上一个板块
                if current_block:
                    blocks.append(current_block)

                # 解析板块标题
                parts = line.split(',')
                block_name = parts[0].replace('#GN_', '')
                current_block = {
                    'name': block_name,
                    'stock_count': int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
                    'stocks': []
                }
            elif current_block and not line.startswith('#'):
                # 解析股票代码
                stocks = line.split(',')
                for stock in stocks:
                    if stock and not stock.startswith('#'):
                        current_block['stocks'].append(stock)
                        all_stocks.add(stock)
                        block_stock_count[block_name] += 1

            # 每 1000 行报告一次进度
            if (i + 1) % 1000 == 0:
                progress = 20 + int((i + 1) / total_lines * 30)
                yield SkillEvent(
                    event_type="progress",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={"progress": progress, "message": f"解析中... {i+1}/{total_lines} 行"},
                    stage="data_parsing"
                )

        # 保存最后一个板块
        if current_block:
            blocks.append(current_block)

        total_blocks = len(blocks)
        total_stocks = len(all_stocks)

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={
                "progress": 50,
                "message": f"解析完成，发现 {total_blocks} 个板块，{total_stocks} 只独特股票"
            },
            stage="data_parsing"
        )

        context.intermediate_results.append({
            "blocks": blocks,
            "total_blocks": total_blocks,
            "total_stocks": total_stocks,
            "block_stock_count": dict(block_stock_count)
        })
        context.create_checkpoint("data_parsing")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "data_parsing", "blocks": total_blocks, "stocks": total_stocks},
            stage="data_parsing"
        )

        # =====================================================================
        # 阶段 3: 数据质量检查
        # =====================================================================
        context.current_stage = "quality_check"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "quality_check"},
            stage="quality_check"
        )

        # 检查数据质量
        quality_issues = []

        # 1. 检查空板块
        empty_blocks = [b for b in blocks if len(b['stocks']) == 0]
        if empty_blocks:
            quality_issues.append(f"发现 {len(empty_blocks)} 个空板块")

        # 2. 检查股票数量不匹配
        mismatch_blocks = []
        for block in blocks:
            declared = block['stock_count']
            actual = len(block['stocks'])
            if declared != actual:
                mismatch_blocks.append(f"{block['name']}: 声明{declared}, 实际{actual}")

        if mismatch_blocks:
            quality_issues.append(f"发现 {len(mismatch_blocks)} 个板块股票数量不匹配")

        # 3. 检查重复股票
        all_stock_list = []
        for block in blocks:
            all_stock_list.extend(block['stocks'])

        from collections import Counter
        stock_counter = Counter(all_stock_list)
        duplicates = {k: v for k, v in stock_counter.items() if v > 1}

        if duplicates:
            quality_issues.append(f"发现 {len(duplicates)} 只股票出现在多个板块")

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={
                "progress": 70,
                "message": f"质量检查完成，发现 {len(quality_issues)} 类问题",
                "issues": quality_issues
            },
            stage="quality_check"
        )

        # 🔥 澄清请求：数据质量问题
        if quality_issues:
            print(f"\n⚠️  [Skill] 发现数据质量问题:")
            for issue in quality_issues:
                print(f"   - {issue}")

            response = await self.request_clarification(
                question=f"数据质量检查发现 {len(quality_issues)} 类问题，是否继续分析？",
                options=[
                    "继续分析（忽略小问题）",
                    "仅分析完整板块（跳过问题板块）",
                    "显示详细问题后决定",
                    "停止分析"
                ],
                timeout_seconds=60,
                urgency="normal",
                context_data={"issues": quality_issues}
            )

            print(f"✅ [Skill] 决策: {response.answer}")

            if "停止" in response.answer:
                yield SkillEvent(
                    event_type="failed",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={"error": "用户选择停止分析", "issues": quality_issues},
                    stage="quality_check"
                )
                return

        context.intermediate_results.append({
            "quality_issues": quality_issues,
            "duplicate_stocks": len(duplicates),
            "empty_blocks": len(empty_blocks)
        })
        context.create_checkpoint("quality_check")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "quality_check", "issues": len(quality_issues)},
            stage="quality_check"
        )

        # =====================================================================
        # 阶段 4: 板块分析
        # =====================================================================
        context.current_stage = "block_analysis"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "block_analysis"},
            stage="block_analysis"
        )

        # 分析板块大小分布
        block_sizes = [len(b['stocks']) for b in blocks]
        avg_size = sum(block_sizes) / len(block_sizes) if block_sizes else 0
        max_size = max(block_sizes) if block_sizes else 0
        min_size = min(block_sizes) if block_sizes else 0

        # 找出最大和最小的板块
        largest_block = max(blocks, key=lambda x: len(x['stocks']))
        smallest_block = min(blocks, key=lambda x: len(x['stocks']))

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={
                "progress": 85,
                "message": f"板块分析完成，平均 {avg_size:.1f} 只股票/板块"
            },
            stage="block_analysis"
        )

        context.intermediate_results.append({
            "avg_block_size": avg_size,
            "max_block_size": max_size,
            "min_block_size": min_size,
            "largest_block": largest_block['name'],
            "smallest_block": smallest_block['name']
        })
        context.create_checkpoint("block_analysis")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "block_analysis"},
            stage="block_analysis"
        )

        # =====================================================================
        # 阶段 5: 生成报告
        # =====================================================================
        context.current_stage = "report_generation"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report_generation"},
            stage="report_generation"
        )

        # 生成分析报告
        report = {
            "file": file_path,
            "summary": {
                "total_lines": total_lines,
                "total_blocks": total_blocks,
                "total_unique_stocks": total_stocks,
                "total_stock_entries": len(all_stock_list)
            },
            "block_statistics": {
                "average_size": round(avg_size, 2),
                "max_size": max_size,
                "min_size": min_size,
                "largest_block": {
                    "name": largest_block['name'],
                    "count": len(largest_block['stocks'])
                },
                "smallest_block": {
                    "name": smallest_block['name'],
                    "count": len(smallest_block['stocks'])
                }
            },
            "data_quality": {
                "issues_found": len(quality_issues),
                "empty_blocks": len(empty_blocks),
                "duplicate_stocks": len(duplicates),
                "mismatch_blocks": len(mismatch_blocks)
            },
            "top_10_blocks": sorted(
                [{"name": b['name'], "count": len(b['stocks'])} for b in blocks],
                key=lambda x: x['count'],
                reverse=True
            )[:10]
        }

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 100, "message": "报告生成完成", "report": report},
            stage="report_generation"
        )

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report_generation", "report": report},
            stage="report_generation"
        )

        print(f"\n✨ [Skill] 分析完成!")
        print(f"   板块数量: {total_blocks}")
        print(f"   独特股票: {total_stocks}")
        print(f"   平均板块大小: {avg_size:.1f}")


# =============================================================================
# AI 处理函数
# =============================================================================

async def tra_ai_handler(request: ClarificationRequest) -> str:
    """TRAE AI 处理澄清请求"""
    print(f"\n" + "="*70)
    print("🧠 TRAE AI 正在分析数据质量问题...")
    print("="*70)
    print(f"❓ {request.question}")
    print(f"\n📋 选项:")
    for i, option in enumerate(request.options, 1):
        print(f"   {i}. {option}")

    # 简单的决策逻辑
    question = request.question

    if "数据质量" in question:
        # 数据质量问题 - 选择继续分析
        choice = "继续分析（忽略小问题）"
    else:
        choice = request.options[0] if request.options else "继续"

    print(f"\n✅ AI 决策: {choice}")
    print("="*70)

    return choice


# =============================================================================
# 主程序
# =============================================================================

async def main():
    """主函数"""
    print("\n" + "="*70)
    print("Infoharbor 板块数据分析")
    print("="*70)

    file_path = "/Users/spark/pycharmproject/deva/deva/naja/dictionary/infoharbor_block.dat"

    # 检查文件是否存在
    import os
    if not os.path.exists(file_path):
        print(f"\n❌ 文件不存在: {file_path}")
        return

    file_size = os.path.getsize(file_path)
    print(f"\n📁 文件信息:")
    print(f"   路径: {file_path}")
    print(f"   大小: {file_size / 1024:.2f} KB")

    # 注册 Skill
    engine = get_execution_engine()
    engine.register_skill("infoharbor_analysis", InfoharborAnalysisSkill)
    print("\n✅ 已注册 Skill: infoharbor_analysis")

    # 创建 Agent 接口
    interface = AgentSkillInterface("infoharbor_agent")
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

    # 执行分析
    print("\n" + "-"*70)
    print("开始分析...")
    print("-"*70)

    final_report = None

    try:
        async for event in interface.invoke_skill_stream(
            skill_id="infoharbor_analysis",
            input_data={"file_path": file_path},
            on_event=on_event,
            on_clarification=tra_ai_handler
        ):
            if event.event_type == "completed":
                print("\n" + "-"*70)
                print("🎉 分析完成!")
                print("-"*70)

                # 获取报告
                final_report = event.data.get('context', {}).get('intermediate_results', [{}])[-1].get('report')

    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()

    # 显示最终报告
    if final_report:
        print("\n" + "="*70)
        print("📊 分析报告")
        print("="*70)

        summary = final_report.get('summary', {})
        print(f"\n【数据概览】")
        print(f"   文件行数: {summary.get('total_lines', 0)}")
        print(f"   板块数量: {summary.get('total_blocks', 0)}")
        print(f"   独特股票: {summary.get('total_unique_stocks', 0)}")
        print(f"   股票条目: {summary.get('total_stock_entries', 0)}")

        stats = final_report.get('block_statistics', {})
        print(f"\n【板块统计】")
        print(f"   平均大小: {stats.get('average_size', 0)}")
        print(f"   最大板块: {stats.get('max_size', 0)} 只股票")
        print(f"   最小板块: {stats.get('min_size', 0)} 只股票")

        largest = stats.get('largest_block', {})
        print(f"   最大板块名称: {largest.get('name', 'N/A')} ({largest.get('count', 0)} 只)")

        quality = final_report.get('data_quality', {})
        print(f"\n【数据质量】")
        print(f"   问题数量: {quality.get('issues_found', 0)}")
        print(f"   空板块: {quality.get('empty_blocks', 0)}")
        print(f"   重复股票: {quality.get('duplicate_stocks', 0)}")

        top_blocks = final_report.get('top_10_blocks', [])
        print(f"\n【前 10 大板块】")
        for i, block in enumerate(top_blocks, 1):
            print(f"   {i}. {block.get('name', 'N/A')}: {block.get('count', 0)} 只股票")

    print("\n" + "="*70)
    print("分析完成!")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
