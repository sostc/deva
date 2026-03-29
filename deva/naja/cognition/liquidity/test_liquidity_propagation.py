"""
Liquidity Propagation System - Complete Integration Test

测试完整的数据流:
1. GlobalMarketAPI 获取市场数据
2. PropagationEngine 更新市场并执行传播
3. LiquidityCognition 处理 Radar 事件
4. NarrativeTracker 叙事追踪
5. UI 输出渲染

用法:
    python -m deva.naja.cognition.liquidity.test_liquidity_propagation
"""

import asyncio
import time
import sys
from typing import Dict, Any


def print_section(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_subsection(title: str):
    print(f"\n## {title}")


async def test_global_market_api():
    """测试 1: GlobalMarketAPI 获取市场数据"""
    print_section("测试 1: GlobalMarketAPI 获取市场数据")

    from deva.naja.attention.data.global_market_futures import GlobalMarketAPI, MARKET_ID_TO_CODE

    api = GlobalMarketAPI()

    print_subsection("支持的期货市场")
    futures_codes = ["hf_NQ", "hf_ES", "hf_YM", "hf_GC", "hf_SI", "hf_CL", "hf_NG"]
    for code in futures_codes:
        market_id = MARKET_ID_TO_CODE.get(code, code)
        print(f"  {code} -> {market_id}")

    print_subsection("获取实时数据...")
    data = await api.fetch_all()

    if not data:
        print("  ❌ 未获取到数据")
        return None

    print(f"  ✅ 获取到 {len(data)} 个市场数据:\n")
    for code, md in data.items():
        pct = md.change_pct
        sign = "+" if pct >= 0 else ""
        status = "📈" if pct > 0 else "📉" if pct < 0 else "➡️"
        print(f"  {status} {md.name:15} ({md.market_id:12}): ${md.current:>10} ({sign}{pct:.2f}%)")

    return data


def test_propagation_engine_market_id_map():
    """测试 2: PropagationEngine 的 MARKET_ID_MAP"""
    print_section("测试 2: PropagationEngine MARKET_ID_MAP")

    from deva.naja.cognition.liquidity.propagation_engine import MARKET_ID_MAP

    print_subsection("市场 ID 映射表")
    print(f"  {'来源ID':15} -> {'目标ID':15}")
    print(f"  {'-'*15}    {'-'*15}")
    for source, target in sorted(MARKET_ID_MAP.items()):
        print(f"  {source:15} -> {target:15}")

    return MARKET_ID_MAP


def test_propagation_engine_updates(market_data: Dict[str, Any]):
    """测试 3: PropagationEngine 市场更新和传播"""
    print_section("测试 3: PropagationEngine 市场更新和传播")

    from deva.naja.cognition.liquidity.propagation_engine import PropagationEngine, MARKET_ID_MAP

    engine = PropagationEngine()
    engine.initialize()

    print_subsection("初始化状态")
    info = engine.get_info()
    print(f"  节点数: {info['nodes_count']}")
    print(f"  边数: {info['edges_count']}")

    print_subsection("更新市场数据...")
    updated_count = 0
    for code, md in market_data.items():
        if hasattr(md, 'current') and md.current > 0:
            mapped_id = MARKET_ID_MAP.get(md.market_id, md.market_id)
            if mapped_id in engine._nodes:
                state = engine.update_market(
                    market_id=mapped_id,
                    price=md.current,
                    volume=getattr(md, 'volume', 0),
                    narrative_score=abs(md.change_pct) / 10.0,
                )
                updated_count += 1
                pct = md.change_pct
                sign = "+" if pct >= 0 else ""
                print(f"  ✅ {mapped_id:12}: ${md.current} ({sign}{pct:.2f}%)")

    print(f"\n  总计更新了 {updated_count} 个市场节点")

    print_subsection("查看活跃市场 (>0.3)")
    active = engine.get_active_markets(threshold=0.3)
    print(f"  活跃市场: {active if active else '无'}")

    print_subsection("查看传播链 (以 nasdaq 为例)")
    chains = engine.get_propagation_chains("nasdaq")
    for i, chain in enumerate(chains[:3]):
        print(f"  链 {i+1}: {' → '.join(chain)}")

    print_subsection("查看共振信号 (>0.5)")
    signals = engine.get_resonance_signals()
    for sig in signals[:5]:
        print(f"  {sig['market_id']:12}: change={sig['change']:.2f}, volatility={sig['volatility']:.3f}")

    print_subsection("流动性结构摘要")
    structure = engine.get_liquidity_structure()
    print(f"  活跃市场数: {len(structure['active_markets'])}")
    print(f"  叙事状态数: {len(structure['narrative_states'])}")
    print(f"  有活动的边数: {len(structure['edges'])}")

    return engine


def test_liquidity_cognition_events():
    """测试 4: LiquidityCognition 处理 Radar 事件"""
    print_section("测试 4: LiquidityCognition 处理 Radar 事件")

    from deva.naja.cognition.liquidity.liquidity_cognition import LiquidityCognition

    cognition = LiquidityCognition()

    print_subsection("模拟 Radar 事件")

    test_events = [
        {
            "market_id": "nasdaq100",
            "current": 18500.0,
            "change_pct": -2.5,
            "volume": 5000000,
            "is_abnormal": True,
            "name": "纳斯达克100",
        },
        {
            "market_id": "sp500",
            "current": 4800.0,
            "change_pct": -1.8,
            "volume": 3000000,
            "is_abnormal": False,
            "name": "标普500",
        },
        {
            "market_id": "gold",
            "current": 2050.0,
            "change_pct": 1.2,
            "volume": 100000,
            "is_abnormal": False,
            "name": "黄金",
        },
        {
            "market_id": "vix",
            "current": 25.0,
            "change_pct": 15.0,
            "volume": 0,
            "is_abnormal": True,
            "name": "VIX恐慌指数",
        },
    ]

    for event in test_events:
        insight = cognition.ingest_global_market_event(event)
        if insight:
            print(f"  ✅ {insight.source_market:12}: {insight.narrative}")
            print(f"     严重度: {insight.severity:.2f}, 传播概率: {insight.propagation_probability:.2f}")
            if insight.target_markets:
                print(f"     目标市场: {', '.join(insight.target_markets)}")
        else:
            print(f"  ❌ {event['market_id']}: 处理失败")

    print_subsection("市场状态摘要")
    summary = cognition.get_summary()
    print(f"  总追踪市场数: {summary['total_markets']}")
    print(f"  异常市场数: {len(summary['abnormal_markets'])}")
    print(f"  严重市场数: {len(summary['severe_markets'])}")
    print(f"  全球情绪: {summary['global_sentiment']}")

    print_subsection("LiquidityCognition 统计")
    stats = cognition.get_stats()
    print(f"  接收事件数: {stats['events_received']}")
    print(f"  触发的传播数: {stats['propagations_triggered']}")
    print(f"  生成的洞察数: {stats['insights_generated']}")

    return cognition


def test_narrative_tracker():
    """测试 5: NarrativeTracker 叙事追踪"""
    print_section("测试 5: NarrativeTracker 叙事追踪 (简化版)")

    from deva.naja.cognition.narrative_tracker import NarrativeTracker

    tracker = NarrativeTracker()

    print_subsection("叙事生命周期阶段")
    print("  阶段: 萌芽 → 扩散 → 高潮 → 消退")
    print("\n  注意: NarrativeTracker 需要正确格式的事件输入")
    print("  以下关键词已配置在 DEFAULT_NARRATIVE_KEYWORDS:")

    keywords_sample = {
        "贵金属": ["黄金", "白银"],
        "全球宏观": ["美股", "纳斯达克", "全球市场"],
        "流动性紧张": ["流动性", "VIX"],
        "债券市场": ["美债", "国债收益率"],
    }

    for category, kws in keywords_sample.items():
        print(f"    {category}: {', '.join(kws)}")

    return tracker


def test_cross_signal_analyzer():
    """测试 6: CrossSignalAnalyzer 跨信号分析"""
    print_section("测试 6: CrossSignalAnalyzer 跨信号分析")

    from deva.naja.cognition.cross_signal_analyzer import CrossSignalAnalyzer, MarketSnapshot

    analyzer = CrossSignalAnalyzer()

    print_subsection("注入市场快照")
    snapshots = [
        MarketSnapshot(
            market_index="nasdaq",
            market_name="纳斯达克",
            price_change=-2.5,
            volume_ratio=1.2,
            volatility=0.8,
            activity=0.9,
        ),
        MarketSnapshot(
            market_index="sp500",
            market_name="标普500",
            price_change=-1.8,
            volume_ratio=1.0,
            volatility=0.6,
            activity=0.7,
        ),
        MarketSnapshot(
            market_index="vix",
            market_name="VIX恐慌指数",
            price_change=15.0,
            volume_ratio=1.5,
            volatility=1.5,
            activity=1.0,
        ),
    ]

    for snapshot in snapshots:
        analyzer.ingest_market_snapshot(snapshot)
        print(f"  ✅ {snapshot.market_index:12}: change={snapshot.price_change:+.1f}%, vol={snapshot.volatility:.2f}")

    print_subsection("市场共振检测")
    resonance_summary = analyzer.get_market_resonance_summary()
    if resonance_summary:
        print(f"  市场快照数: {resonance_summary.get('snapshot_count', 0)}")
        print(f"  共振市场: {resonance_summary.get('resonance_markets', [])}")
    else:
        print("  暂无市场共振数据")

    return analyzer


def test_ui_render():
    """测试 7: UI 渲染输出"""
    print_section("测试 7: UI 渲染输出")

    try:
        from deva.naja.cognition.ui import CognitionUI

        print_subsection("CognitionUI 初始化")
        ui = CognitionUI()
        print("  ✅ UI 创建成功")

        print_subsection("LiquidityStructure 面板")
        structure_rendered = ui._render_liquidity_structure()
        if structure_rendered and len(structure_rendered) > 100:
            print("  ✅ 流动性结构面板渲染成功")
            print(f"\n{structure_rendered[:300]}...")
        else:
            print("  ⚠️ 流动性结构面板为空或太短")

        print_subsection("PropagationNetwork 面板")
        network_rendered = ui._render_propagation_network()
        if network_rendered and len(network_rendered) > 100:
            print("  ✅ 传播网络面板渲染成功")
        else:
            print("  ⚠️ 传播网络面板为空或太短")

    except Exception as e:
        print(f"  ❌ UI 测试失败: {e}")
        import traceback
        traceback.print_exc()


async def test_complete_flow_with_data(market_data):
    """使用已有市场数据运行完整流程"""
    print_section("完整数据流测试")

    from deva.naja.cognition.liquidity.propagation_engine import PropagationEngine, MARKET_ID_MAP

    print_subsection("步骤 1: 初始化 PropagationEngine")
    engine = PropagationEngine()
    engine.initialize()

    print_subsection("步骤 2: 同步市场数据")
    sync_count = engine.sync_from_global_market_api(market_data)
    print(f"  ✅ 同步了 {sync_count} 个市场")

    print_subsection("步骤 3: 通过 LiquidityCognition 处理事件")
    from deva.naja.cognition.liquidity.liquidity_cognition import LiquidityCognition

    cognition = LiquidityCognition()

    for code, md in list(market_data.items())[:8]:
        if hasattr(md, 'current') and md.current > 0:
            event = {
                "market_id": md.market_id,
                "current": md.current,
                "change_pct": md.change_pct,
                "volume": getattr(md, 'volume', 0),
                "is_abnormal": abs(md.change_pct) > 2.0,
                "name": md.name,
            }
            insight = cognition.ingest_global_market_event(event)
            if insight:
                print(f"  ✅ {insight.source_market:12}: {insight.narrative}")

    print_subsection("步骤 4: 验证传播结果")
    structure = engine.get_liquidity_structure()
    print(f"  活跃市场: {len(structure['active_markets'])}")
    print(f"  叙事状态: {len(structure['narrative_states'])}")

    cognition_summary = cognition.get_summary()
    print(f"  LiquidityCognition 全球情绪: {cognition_summary['global_sentiment']}")
    print(f"  异常市场数: {len(cognition_summary['abnormal_markets'])}")
    print(f"  严重市场数: {len(cognition_summary['severe_markets'])}")

    print_subsection("✅ 完整流程测试成功!")


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "#" * 70)
    print("#" + " " * 68 + "#")
    print("#    Liquidity Propagation System - 完整集成测试                #")
    print("#" + " " * 68 + "#")
    print("#" * 70)

    try:
        market_data = await test_global_market_api()
        test_propagation_engine_market_id_map()

        if market_data:
            test_propagation_engine_updates(market_data)
            await test_complete_flow_with_data(market_data)

        test_liquidity_cognition_events()
        test_narrative_tracker()
        test_cross_signal_analyzer()
        test_ui_render()

        print("\n" + "=" * 70)
        print("  ✅ 所有测试完成!")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_all_tests())