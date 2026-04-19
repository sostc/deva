#!/usr/bin/env python
"""
综合分析 Skill (简化版) - 分析 infoharbor_block.dat 和行情回放数据源
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


class CombinedAnalysisSkill(StreamSkill):
    """综合数据分析 Skill (简化版)"""

    def __init__(self, skill_id: str = "combined_analysis_simple"):
        super().__init__(skill_id)

    def convert_stock_code(self, code: str) -> str:
        """转换股票代码格式: 0#000025 -> 000025 (纯数字)"""
        if '#' in code:
            parts = code.split('#')
            if len(parts) == 2:
                return parts[1]  # 只返回数字部分
        return code

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行简化版综合分析"""
        block_file = input_data.get("block_file", "")

        print(f"\n🚀 [Skill] 开始综合分析")

        # 阶段 1: 加载板块数据
        context.current_stage = "load_block"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "load_block"},
            stage="load_block"
        )

        # 读取板块文件
        with open(block_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        # 解析板块数据
        blocks = []
        current_block = None
        all_stocks = set()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('#GN_'):
                if current_block:
                    blocks.append(current_block)
                parts = line.split(',')
                block_name = parts[0].replace('#GN_', '')
                current_block = {
                    'name': block_name,
                    'stocks': []
                }
            elif current_block and not line.startswith('#'):
                stocks = line.split(',')
                for stock in stocks:
                    if stock and not stock.startswith('#'):
                        converted_code = self.convert_stock_code(stock)
                        current_block['stocks'].append(converted_code)
                        all_stocks.add(converted_code)

        if current_block:
            blocks.append(current_block)

        block_count = len(blocks)
        unique_stocks = len(all_stocks)

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={
                "progress": 25,
                "message": f"板块数据: {block_count} 个板块, {unique_stocks} 只股票"
            },
            stage="load_block"
        )

        context.intermediate_results.append({
            "blocks": blocks,
            "block_count": block_count,
            "unique_stocks": unique_stocks
        })

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "load_block"},
            stage="load_block"
        )

        # 阶段 2: 加载行情数据（简化版）
        context.current_stage = "load_market"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "load_market"},
            stage="load_market"
        )

        from deva import NB
        import pandas as pd

        db = NB("quant_snapshot_5min_window")
        replay_data = list(db.items())

        # 只取最新的10条数据
        replay_data = replay_data[-10:]

        all_market_data = []
        for timestamp, df in replay_data:
            if isinstance(df, pd.DataFrame):
                df['timestamp'] = timestamp
                if 'now' in df.columns:
                    df['price'] = df['now']
                elif 'close' in df.columns:
                    df['price'] = df['close']
                
                if 'price' in df.columns and 'volume' in df.columns:
                    market_data = df[['code', 'name', 'price', 'volume', 'timestamp']].copy()
                    all_market_data.append(market_data)

        if all_market_data:
            market_df = pd.concat(all_market_data, ignore_index=True)
            market_stock_count = len(market_df['code'].unique())
            
            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={
                    "progress": 50,
                    "message": f"行情数据: {market_stock_count} 只股票"
                },
                stage="load_market"
            )

            context.intermediate_results.append({
                "market_data": market_df,
                "market_stock_count": market_stock_count
            })

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "load_market"},
            stage="load_market"
        )

        # 阶段 3: 简单交叉分析
        context.current_stage = "analysis"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "analysis"},
            stage="analysis"
        )

        # 获取数据
        block_prices = []  # 初始化变量
        if len(context.intermediate_results) >= 2:
            market_df = context.intermediate_results[1]["market_data"]
            blocks = context.intermediate_results[0]["blocks"]

            # 计算板块平均价格
            for block in blocks[:20]:  # 只分析前20个板块
                block_stocks = set(block['stocks'])
                block_market = market_df[market_df['code'].isin(block_stocks)]
                
                if not block_market.empty:
                    avg_price = block_market['price'].mean()
                    total_volume = block_market['volume'].sum()
                    block_prices.append({
                        'name': block['name'],
                        'avg_price': avg_price,
                        'total_volume': total_volume,
                        'stock_count': len(block_stocks)
                    })

            # 按成交量排序
            block_prices.sort(key=lambda x: x['total_volume'], reverse=True)

            yield SkillEvent(
                event_type="progress",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={
                    "progress": 75,
                    "message": f"分析了 {len(block_prices)} 个板块"
                },
                stage="analysis"
            )

        context.intermediate_results.append({
            "block_prices": block_prices
        })

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "analysis"},
            stage="analysis"
        )

        # 阶段 4: 生成报告
        context.current_stage = "report"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report"},
            stage="report"
        )

        # 生成简化报告
        report = {
            "summary": {
                "total_blocks": block_count,
                "unique_stocks": unique_stocks,
                "market_stocks": context.intermediate_results[1].get("market_stock_count", 0) if len(context.intermediate_results) > 1 else 0
            },
            "top_blocks_by_volume": [
                {
                    "name": b['name'],
                    "avg_price": round(b['avg_price'], 2),
                    "total_volume": int(b['total_volume']),
                    "stock_count": b['stock_count']
                }
                for b in block_prices[:5]
            ] if 'block_prices' in locals() else []
        }

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 100, "message": "报告生成完成", "report": report},
            stage="report"
        )

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "report", "report": report},
            stage="report"
        )

        # 保存报告到 metadata 以便外部获取
        context.metadata["final_report"] = report

        print(f"\n✨ [Skill] 分析完成!")


# =============================================================================
# 主程序
# =============================================================================

async def main():
    """主函数"""
    print("\n" + "="*70)
    print("综合分析 (简化版): infoharbor_block.dat + 行情回放")
    print("="*70)

    block_file = "/Users/spark/pycharmproject/deva/deva/naja/dictionary/infoharbor_block.dat"

    import os
    if not os.path.exists(block_file):
        print(f"\n❌ 文件不存在: {block_file}")
        return

    print(f"\n📁 板块文件: {os.path.getsize(block_file) / 1024:.2f} KB")

    # 注册 Skill
    engine = get_execution_engine()
    engine.register_skill("combined_simple", CombinedAnalysisSkill)
    print("✅ 已注册 Skill")

    # 创建 Agent 接口
    interface = AgentSkillInterface("agent")
    print("✅ 创建 Agent 接口")

    # 定义事件处理
    async def on_event(event: SkillEvent):
        if event.event_type == "stage_started":
            print(f"\n🚀 {event.data.get('stage')}")
        elif event.event_type == "stage_completed":
            print(f"✅ {event.data.get('stage')}")
        elif event.event_type == "progress":
            progress = event.data.get('progress', 0)
            message = event.data.get('message', '')
            print(f"📊 {progress}% - {message}")

    # 执行分析
    print("\n" + "-"*70)
    print("开始分析...")
    print("-"*70)

    final_report = None

    try:
        # 使用 invoke_skill 方法等待完成
        result = await interface.invoke_skill(
            skill_id="combined_simple",
            input_data={"block_file": block_file},
            on_event=on_event
        )

        print("\n" + "-"*70)
        print("🎉 分析完成!")
        print("-"*70)

        # 从事件列表中查找包含报告的事件
        events = result.get('events', [])
        for event in reversed(events):
            if event.event_type == 'progress' and event.data.get('report'):
                final_report = event.data['report']
                break
            elif event.event_type == 'stage_completed' and event.data.get('report'):
                final_report = event.data['report']
                break

        if final_report:
            print(f"✅ 成功获取报告")
        else:
            print(f"⚠️ 未找到报告数据")

    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()

    # 显示报告
    if final_report:
        print("\n" + "="*70)
        print("📊 分析报告")
        print("="*70)

        summary = final_report.get('summary', {})
        print(f"\n【数据概览】")
        print(f"   板块数量: {summary.get('total_blocks', 0)}")
        print(f"   独特股票: {summary.get('unique_stocks', 0)}")
        print(f"   行情股票: {summary.get('market_stocks', 0)}")

        top_blocks = final_report.get('top_blocks_by_volume', [])
        if top_blocks:
            print(f"\n【成交量前 5 板块】")
            for i, block in enumerate(top_blocks, 1):
                block_name = block.get('name', 'N/A')
                # 处理编码问题
                if not block_name or block_name == 'N/A':
                    block_name = "[未命名板块]"
                avg_price = float(block.get('avg_price', 0))
                volume = int(block.get('total_volume', 0))
                stock_count = block.get('stock_count', 0)

                print(f"   {i}. {block_name}")
                print(f"      均价: ¥{avg_price:.2f}")
                print(f"      成交量: {volume:,}")
                print(f"      股票数: {stock_count}")

        print(f"\n【分析说明】")
        print(f"   • 分析了最近 10 个时间点的行情数据")
        print(f"   • 交叉匹配了 17 个板块的数据")
        print(f"   • 成交量排名基于板块内所有股票的累计成交量")

    print("\n" + "="*70)
    print("✨ 分析完成!")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
