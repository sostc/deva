"""
美林时钟系统集成测试

测试完整的美林时钟工作流：
1. 获取经济数据
2. 更新美林时钟
3. 查询流动性结构（整合周期判断）
4. 生成 Markdown 报告
"""

import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def test_merrill_clock_integration():
    """美林时钟集成测试"""
    print("=" * 80)
    print("美林时钟系统集成测试")
    print("=" * 80)
    
    # ========== 步骤 1: 获取经济数据 ==========
    print("\n【步骤 1】获取经济数据...")
    from deva.naja.cognition.economic_data_fetcher import EconomicDataFetcher
    import asyncio
    
    fetcher = EconomicDataFetcher(use_mock=True)
    
    data = asyncio.run(fetcher.fetch_latest_data())
    asyncio.run(fetcher.close())
    
    print(f"✓ 数据获取成功")
    print(f"  GDP 增速：{data.gdp_growth:.1f}%" if data.gdp_growth else "  GDP: 无数据")
    print(f"  PMI: {data.pmi:.1f}" if data.pmi else "  PMI: 无数据")
    print(f"  CPI: {data.cpi_yoy:.1f}%" if data.cpi_yoy else "  CPI: 无数据")
    print(f"  核心 PCE: {data.core_pce_yoy:.1f}%" if data.core_pce_yoy else "  核心 PCE: 无数据")
    
    # ========== 步骤 2: 更新美林时钟 ==========
    print("\n【步骤 2】更新美林时钟周期判断...")
    from deva.naja.cognition.merrill_clock_engine import get_merrill_clock_engine
    
    clock_engine = get_merrill_clock_engine()
    signal = clock_engine.on_economic_data(data)
    
    if signal:
        print(f"✓ 周期阶段：{signal.phase.value}")
        print(f"  置信度：{signal.confidence:.0%}")
        print(f"  增长评分：{signal.growth_score:+.2f}")
        print(f"  通胀评分：{signal.inflation_score:+.2f}")
        print(f"  资产排序：{' > '.join(signal.asset_ranking)}")
    else:
        print("✗ 数据不足，无法判断")
        return
    
    # ========== 步骤 3: 查询流动性结构（整合周期判断） ==========
    print("\n【步骤 3】查询流动性结构（整合周期判断）...")
    from deva.naja.cognition.narrative_tracker import NarrativeTracker
    
    tracker = NarrativeTracker()
    liquidity_structure = tracker.get_liquidity_structure()
    
    print(f"✓ 流动性结构:")
    print(f"  短期：{liquidity_structure.get('short_term', 'N/A')}")
    print(f"  长期：{liquidity_structure.get('long_term', 'N/A')}")
    print(f"  综合：{liquidity_structure.get('conclusion', 'N/A')}")
    
    # ========== 步骤 4: 生成 Markdown 报告 ==========
    print("\n【步骤 4】生成 Markdown 报告...")
    from deva.naja.cognition.ui_merrill_clock import get_merrill_clock_markdown
    
    # 重新获取引擎（确保使用同一实例）
    clock_engine = get_merrill_clock_engine()
    
    markdown_report = get_merrill_clock_markdown()
    
    print("✓ Markdown 报告生成成功")
    print("\n" + "=" * 80)
    print(markdown_report)
    print("=" * 80)
    
    # ========== 步骤 5: 测试天道民心评分 ==========
    print("\n【步骤 5】测试天道民心评分...")
    tiandao_minxin = tracker.get_tiandao_minxin_summary()
    
    print(f"✓ 天道民心评分:")
    print(f"  天道评分：{tiandao_minxin.get('tiandao_score', 0):.0%}")
    print(f"  民心评分：{tiandao_minxin.get('minxin_score', 0):.0%}")
    print(f"  推荐行动：{tiandao_minxin.get('recommendation', 'N/A')}")
    print(f"  理由：{tiandao_minxin.get('reason', 'N/A')}")
    
    print("\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)
    
    return {
        "economic_data": data,
        "clock_signal": signal,
        "liquidity_structure": liquidity_structure,
        "tiandao_minxin": tiandao_minxin,
    }


if __name__ == "__main__":
    test_merrill_clock_integration()
