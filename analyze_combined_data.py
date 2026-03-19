#!/usr/bin/env python
"""
综合分析 Skill - 同时分析 infoharbor_block.dat 和行情回放数据源

功能：
1. 分析板块数据文件结构和内容
2. 分析行情回放数据源的 tick 数据
3. 交叉分析板块和行情数据
4. 生成综合分析报告
"""

import asyncio
import time
from typing import AsyncIterator, Any
from collections import defaultdict, Counter

from deva.naja.stream_skill import (
    StreamSkill,
    SkillContext,
    SkillEvent,
    ClarificationRequest,
    get_execution_engine,
    AgentSkillInterface,
)


class CombinedDataAnalysisSkill(StreamSkill):
    """
    综合数据分析 Skill
    
    同时分析：
    1. infoharbor_block.dat - 股票板块分类数据
    2. 行情回放数据源 - tick 级别行情数据
    
    输出：
    - 板块结构分析
    - 行情数据统计
    - 板块-行情交叉分析
    - 投资建议
    """

    def __init__(self, skill_id: str = "combined_data_analysis"):
        super().__init__(skill_id)

    async def execute(self, input_data: Any, context: SkillContext) -> AsyncIterator[SkillEvent]:
        """执行综合分析"""
        block_file = input_data.get("block_file", "")
        replay_datasource = input_data.get("replay_datasource", "行情回放")

        print(f"\n🚀 [Skill] 开始综合分析")
        print(f"   板块文件: {block_file}")
        print(f"   行情数据源: {replay_datasource}")

        # =====================================================================
        # 阶段 1: 加载板块数据
        # =====================================================================
        context.current_stage = "load_block_data"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "load_block_data", "file": block_file},
            stage="load_block_data"
        )

        # 读取板块文件
        try:
            with open(block_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            yield SkillEvent(
                event_type="failed",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"error": f"板块文件读取失败: {e}"},
                stage="load_block_data"
            )
            return

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
                    'stock_count': int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
                    'stocks': []
                }
            elif current_block and not line.startswith('#'):
                stocks = line.split(',')
                for stock in stocks:
                    if stock and not stock.startswith('#'):
                        current_block['stocks'].append(stock)
                        all_stocks.add(stock)

        if current_block:
            blocks.append(current_block)

        block_count = len(blocks)
        unique_stocks = len(all_stocks)

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={
                "progress": 20,
                "message": f"板块数据加载完成: {block_count} 个板块, {unique_stocks} 只独特股票"
            },
            stage="load_block_data"
        )

        context.intermediate_results.append({
            "blocks": blocks,
            "block_count": block_count,
            "unique_stocks": unique_stocks
        })
        context.create_checkpoint("load_block_data")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "load_block_data"},
            stage="load_block_data"
        )

        # =====================================================================
        # 阶段 2: 加载行情回放数据
        # =====================================================================
        context.current_stage = "load_replay_data"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "load_replay_data"},
            stage="load_replay_data"
        )

        try:
            from deva import NB
            import pandas as pd

            # 从 quant_snapshot_5min_window 表获取数据
            db = NB("quant_snapshot_5min_window")
            replay_data = list(db.items())

            if not replay_data:
                yield SkillEvent(
                    event_type="failed",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={"error": "行情回放数据源没有数据"},
                    stage="load_replay_data"
                )
                return

            # 解析行情数据
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
                combined_market_df = pd.concat(all_market_data, ignore_index=True)
                combined_market_df['timestamp'] = pd.to_datetime(combined_market_df['timestamp'])
                
                # 计算价格变化
                combined_market_df = combined_market_df.sort_values(['code', 'timestamp'])
                combined_market_df['price_change'] = combined_market_df.groupby('code')['price'].pct_change() * 100
                
                market_stock_count = len(combined_market_df['code'].unique())
                market_record_count = len(combined_market_df)

                yield SkillEvent(
                    event_type="progress",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={
                        "progress": 40,
                        "message": f"行情数据加载完成: {market_stock_count} 只股票, {market_record_count} 条记录"
                    },
                    stage="load_replay_data"
                )

                context.intermediate_results.append({
                    "market_data": combined_market_df,
                    "market_stock_count": market_stock_count,
                    "market_record_count": market_record_count
                })
            else:
                yield SkillEvent(
                    event_type="failed",
                    timestamp=time.time(),
                    execution_id=context.execution_id,
                    data={"error": "没有有效的行情数据"},
                    stage="load_replay_data"
                )
                return

        except Exception as e:
            yield SkillEvent(
                event_type="failed",
                timestamp=time.time(),
                execution_id=context.execution_id,
                data={"error": f"行情数据加载失败: {e}"},
                stage="load_replay_data"
            )
            return

        context.create_checkpoint("load_replay_data")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "load_replay_data"},
            stage="load_replay_data"
        )

        # =====================================================================
        # 阶段 3: 交叉分析
        # =====================================================================
        context.current_stage = "cross_analysis"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "cross_analysis"},
            stage="cross_analysis"
        )

        # 获取数据
        market_df = context.intermediate_results[-1]["market_data"]
        blocks = context.intermediate_results[0]["blocks"]

        # 分析每个板块的表现
        block_performance = []
        
        for block in blocks:
            block_stocks = set(block['stocks'])
            
            # 找到在行情数据中的股票
            block_market_data = market_df[market_df['code'].isin(block_stocks)]
            
            if not block_market_data.empty:
                # 计算板块平均涨跌幅
                avg_change = block_market_data['price_change'].mean()
                
                # 计算板块总成交量
                total_volume = block_market_data['volume'].sum()
                
                # 找出板块内表现最好的股票
                best_stock = block_market_data.loc[block_market_data['price_change'].idxmax()]
                
                block_performance.append({
                    'block_name': block['name'],
                    'stock_count': len(block_stocks),
                    'matched_stocks': len(block_market_data['code'].unique()),
                    'avg_change': avg_change,
                    'total_volume': total_volume,
                    'best_stock': {
                        'code': best_stock['code'],
                        'name': best_stock['name'],
                        'change': best_stock['price_change']
                    }
                })

        # 按涨跌幅排序
        block_performance.sort(key=lambda x: x['avg_change'], reverse=True)

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={
                "progress": 60,
                "message": f"交叉分析完成，分析了 {len(block_performance)} 个板块的表现"
            },
            stage="cross_analysis"
        )

        context.intermediate_results.append({
            "block_performance": block_performance,
            "top_performers": block_performance[:5],
            "bottom_performers": block_performance[-5:]
        })
        context.create_checkpoint("cross_analysis")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "cross_analysis"},
            stage="cross_analysis"
        )

        # =====================================================================
        # 阶段 4: 生成洞察和建议
        # =====================================================================
        context.current_stage = "generate_insights"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "generate_insights"},
            stage="generate_insights"
        )

        # 分析市场趋势
        market_df = context.intermediate_results[1]["market_data"]
        
        # 计算整体市场指标
        total_volume = market_df['volume'].sum()
        avg_price = market_df['price'].mean()
        price_volatility = market_df['price_change'].std()
        
        # 识别热点板块（成交量大且涨幅高的板块）
        hot_blocks = [b for b in block_performance 
                      if b['total_volume'] > total_volume / len(block_performance) 
                      and b['avg_change'] > 0]

        # 识别冷门板块（成交量小且跌幅大的板块）
        cold_blocks = [b for b in block_performance 
                       if b['total_volume'] < total_volume / len(block_performance) 
                       and b['avg_change'] < 0]

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={
                "progress": 80,
                "message": f"生成洞察: 发现 {len(hot_blocks)} 个热点板块, {len(cold_blocks)} 个冷门板块"
            },
            stage="generate_insights"
        )

        context.intermediate_results.append({
            "market_summary": {
                "total_volume": total_volume,
                "avg_price": avg_price,
                "price_volatility": price_volatility
            },
            "hot_blocks": hot_blocks,
            "cold_blocks": cold_blocks
        })
        context.create_checkpoint("generate_insights")

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "generate_insights"},
            stage="generate_insights"
        )

        # =====================================================================
        # 阶段 5: 生成综合报告
        # =====================================================================
        context.current_stage = "generate_report"
        yield SkillEvent(
            event_type="stage_started",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "generate_report"},
            stage="generate_report"
        )

        # 生成最终报告
        report = {
            "data_summary": {
                "block_data": {
                    "total_blocks": block_count,
                    "unique_stocks": unique_stocks
                },
                "market_data": {
                    "total_stocks": context.intermediate_results[1]["market_stock_count"],
                    "total_records": context.intermediate_results[1]["market_record_count"],
                    "avg_price": round(avg_price, 2),
                    "price_volatility": round(price_volatility, 2)
                }
            },
            "top_performing_blocks": [
                {
                    "name": b['block_name'],
                    "avg_change": round(b['avg_change'], 2),
                    "matched_stocks": b['matched_stocks'],
                    "best_stock": b['best_stock']
                }
                for b in block_performance[:10]
            ],
            "hot_sectors": [
                {
                    "name": b['block_name'],
                    "avg_change": round(b['avg_change'], 2),
                    "total_volume": int(b['total_volume'])
                }
                for b in hot_blocks[:5]
            ],
            "investment_suggestions": [
                f"关注涨幅前3的板块: {', '.join([b['block_name'] for b in block_performance[:3]])}",
                f"热点板块有 {len(hot_blocks)} 个，建议重点关注",
                f"市场整体波动率为 {price_volatility:.2f}%，{'波动较大' if price_volatility > 2 else '相对稳定'}"
            ]
        }

        yield SkillEvent(
            event_type="progress",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"progress": 100, "message": "报告生成完成", "report": report},
            stage="generate_report"
        )

        yield SkillEvent(
            event_type="stage_completed",
            timestamp=time.time(),
            execution_id=context.execution_id,
            data={"stage": "generate_report", "report": report},
            stage="generate_report"
        )

        print(f"\n✨ [Skill] 综合分析完成!")
        print(f"   分析了 {block_count} 个板块")
        print(f"   分析了 {context.intermediate_results[1]['market_stock_count']} 只股票的行情")
        print(f"   识别了 {len(hot_blocks)} 个热点板块")


# =============================================================================
# AI 处理函数
# =============================================================================

async def tra_ai_handler(request: ClarificationRequest) -> str:
    """TRAE AI 处理澄清请求"""
    print(f"\n" + "="*70)
    print("🧠 TRAE AI 正在分析...")
    print("="*70)
    print(f"❓ {request.question}")
    print(f"\n📋 选项:")
    for i, option in enumerate(request.options, 1):
        print(f"   {i}. {option}")

    # 简单的决策逻辑
    question = request.question

    if "数据质量" in question:
        choice = "继续分析（忽略小问题）"
    elif "分析策略" in question:
        choice = "全面分析（包含以上所有）"
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
    print("综合分析: infoharbor_block.dat + 行情回放数据源")
    print("="*70)

    block_file = "/Users/spark/pycharmproject/deva/deva/naja/dictionary/infoharbor_block.dat"

    # 检查文件是否存在
    import os
    if not os.path.exists(block_file):
        print(f"\n❌ 文件不存在: {block_file}")
        return

    file_size = os.path.getsize(block_file)
    print(f"\n📁 板块文件信息:")
    print(f"   路径: {block_file}")
    print(f"   大小: {file_size / 1024:.2f} KB")

    # 注册 Skill
    engine = get_execution_engine()
    engine.register_skill("combined_analysis", CombinedDataAnalysisSkill)
    print("\n✅ 已注册 Skill: combined_analysis")

    # 创建 Agent 接口
    interface = AgentSkillInterface("combined_agent")
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
    print("开始综合分析...")
    print("-"*70)

    final_report = None

    try:
        async for event in interface.invoke_skill_stream(
            skill_id="combined_analysis",
            input_data={
                "block_file": block_file,
                "replay_datasource": "行情回放"
            },
            on_event=on_event,
            on_clarification=tra_ai_handler
        ):
            if event.event_type == "completed":
                print("\n" + "-"*70)
                print("🎉 综合分析完成!")
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
        print("📊 综合分析报告")
        print("="*70)

        summary = final_report.get('data_summary', {})
        block_summary = summary.get('block_data', {})
        market_summary = summary.get('market_data', {})

        print(f"\n【数据概览】")
        print(f"   板块数据:")
        print(f"     - 板块数量: {block_summary.get('total_blocks', 0)}")
        print(f"     - 独特股票: {block_summary.get('unique_stocks', 0)}")
        print(f"   行情数据:")
        print(f"     - 股票数量: {market_summary.get('total_stocks', 0)}")
        print(f"     - 记录数量: {market_summary.get('total_records', 0)}")
        print(f"     - 平均价格: {market_summary.get('avg_price', 0):.2f}")
        print(f"     - 价格波动: {market_summary.get('price_volatility', 0):.2f}%")

        top_blocks = final_report.get('top_performing_blocks', [])
        print(f"\n【涨幅前 10 板块】")
        for i, block in enumerate(top_blocks, 1):
            print(f"   {i}. {block.get('name', 'N/A')}: {block.get('avg_change', 0):.2f}%")
            best = block.get('best_stock', {})
            print(f"      最佳: {best.get('name', 'N/A')} ({best.get('change', 0):.2f}%)")

        hot_sectors = final_report.get('hot_sectors', [])
        print(f"\n【热点板块】")
        for i, sector in enumerate(hot_sectors, 1):
            print(f"   {i}. {sector.get('name', 'N/A')}: {sector.get('avg_change', 0):.2f}%")

        suggestions = final_report.get('investment_suggestions', [])
        print(f"\n【投资建议】")
        for suggestion in suggestions:
            print(f"   💡 {suggestion}")

    print("\n" + "="*70)
    print("分析完成!")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
