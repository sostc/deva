"""
双通道架构梳理与测试

架构说明:
========

通道1: 新闻数据 (NarrativeTracker)
----------------------------------
新闻事件 (NewsEvent)
    ↓ .content / .meta.title
NarrativeTracker.ingest_event()
    ↓ 检测叙事关键词
    ↓ 更新叙事生命周期 (萌芽→扩散→高潮→消退)
    ↓ 产出 narrative_events
    ↓ emit_to_insight_pool()
    ↓
PropagationEngine.update_narrative_state()
    ↓ 关联到市场节点
    ↓


通道2: 市场数据 (LiquidityCognition)
------------------------------------
GlobalMarketScanner (Radar)
    ↓ MarketAlert
Radar._on_global_market_alert()
    ↓ RadarEvent
LiquidityCognition.ingest_global_market_event()
    ↓ MARKET_ID_MAP 映射
    ↓ PropagationEngine.update_market()
    ↓ 产出 GlobalMarketInsight
    ↓ emit_to_insight_pool()


共振分析: CrossSignalAnalyzer
----------------------------------
ingest_news() + ingest_market_snapshot()
    ↓
detect_resonance() → ResonanceSignal
    ↓
should_trigger_llm() → 是否需要深度分析


关键类:
- NewsEvent: 新闻事件 (.content, .meta)
- NarrativeTracker: 叙事追踪 (检测关键词, 更新生命周期)
- LiquidityCognition: 市场事件处理 (映射, 更新)
- PropagationEngine: 传播网络 (节点+边)
- CrossSignalAnalyzer: 共振分析 (新闻+市场)
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class MockNewsEvent:
    """模拟新闻事件"""
    content: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    attention_score: float = 0.5
    timestamp: float = field(default_factory=time.time)
    source: str = "test"


async def test_news_flow():
    """测试新闻数据流"""
    print("\n" + "=" * 70)
    print("  通道1: 新闻数据流测试")
    print("=" * 70)

    from deva.naja.cognition.narrative import NarrativeTracker

    tracker = NarrativeTracker()

    print("\n## 步骤1: 创建新闻事件")

    news_events = [
        MockNewsEvent(
            content="美股暴跌引发市场恐慌",
            meta={"title": "美股暴跌引发市场恐慌", "block": "全球宏观"},
            attention_score=0.9,
        ),
        MockNewsEvent(
            content="黄金价格突破2050美元，避险资金流入贵金属板块",
            meta={"title": "黄金创历史新高", "block": "贵金属"},
            attention_score=0.7,
        ),
        MockNewsEvent(
            content="原油价格波动加剧，地缘政治影响大宗商品市场",
            meta={"title": "原油市场分析", "block": "大宗商品"},
            attention_score=0.6,
        ),
    ]

    for i, event in enumerate(news_events):
        print(f"\n  新闻事件 {i+1}:")
        print(f"    内容: {event.content[:40]}...")
        print(f"    元数据: {event.meta}")

        # 关键: NarrativeTracker 需要 .content 属性
        results = tracker.ingest_event(event)

        if results:
            for r in results:
                print(f"    ✅ 检测到叙事: {r.get('narrative', 'N/A')}")
                print(f"       阶段: {r.get('stage', 'N/A')}")
                print(f"       注意力: {r.get('attention_score', 0):.2f}")
        else:
            print(f"    ⚠️ 未检测到叙事")

    print("\n## 步骤2: 获取叙事摘要")
    summary = tracker.get_summary(limit=10)
    print(f"  活跃叙事数: {len(summary)}")
    for item in summary[:5]:
        print(f"  - {item.get('narrative', 'N/A'):15}: attention={item.get('attention_score', 0):.2f}, stage={item.get('stage', 'N/A')}")

    print("\n## 步骤3: 获取流动性结构")
    liquidity = tracker.get_liquidity_structure()
    if liquidity:
        print(f"  主叙事: {liquidity.get('primary_liquidity_narrative', 'N/A')}")
        quadrants = liquidity.get('quadrants', {})
        for q, info in quadrants.items():
            print(f"  {q}: stage={info.get('stage', 'N/A')}, attention={info.get('attention_score', 0):.2f}")
    else:
        print("  无流动性结构数据")

    return tracker


async def test_market_flow():
    """测试市场数据流"""
    print("\n" + "=" * 70)
    print("  通道2: 市场数据流测试")
    print("=" * 70)

    from deva.naja.attention.data.global_market_futures import GlobalMarketAPI
    from deva.naja.cognition.liquidity.liquidity_cognition import LiquidityCognition
    from deva.naja.cognition.liquidity.propagation_engine import MARKET_ID_MAP

    print("\n## 步骤1: 获取市场数据")
    api = GlobalMarketAPI()
    data = await api.fetch_all()
    print(f"  获取到 {len(data)} 个市场")

    print("\n## 步骤2: 通过 LiquidityCognition 处理")
    cognition = LiquidityCognition()

    for code, md in list(data.items())[:8]:
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

    print("\n## 步骤3: 市场状态摘要")
    summary = cognition.get_summary()
    print(f"  全球情绪: {summary.get('global_sentiment', 'N/A')}")
    print(f"  异常市场: {len(summary.get('abnormal_markets', []))}")
    print(f"  严重市场: {len(summary.get('severe_markets', []))}")

    return cognition


async def test_resonance_flow():
    """测试共振分析"""
    print("\n" + "=" * 70)
    print("  共振分析测试")
    print("=" * 70)

    from deva.naja.cognition.cross_signal_analyzer import (
        CrossSignalAnalyzer, NewsSignal, MarketSnapshot
    )

    analyzer = CrossSignalAnalyzer()

    print("\n## 步骤1: 注入新闻信号")

    attention_mock = {
        "sp500": 0.8, "nasdaq": 0.9, "vix": 0.7, "gold": 0.5,
        "us_equity": 0.7, "a_share": 0.3
    }
    symbol_weights_mock = {
        "sp500": 0.8, "SP500": 0.8, "nasdaq": 0.9, "NASDAQ": 0.9,
        "vix": 0.7, "^VIX": 0.7, "gold": 0.5, "GC": 0.5,
        "us_equity": 0.7
    }
    sector_names_mock = {
        "sp500": "标普500", "nasdaq": "纳斯达克", "vix": "恐慌指数",
        "gold": "黄金", "us_equity": "美股"
    }

    class MockAttentionSnapshot:
        def __init__(self):
            self.timestamp = time.time()
            self.sector_weights = attention_mock
            self.symbol_weights = symbol_weights_mock
            self.sector_names = sector_names_mock
            self.high_attention_symbols = {"sp500", "nasdaq", "vix"}
            self.active_sectors = {"sp500", "nasdaq", "vix"}
            self.global_attention = 0.7
            self.activity = 0.6

    analyzer._attention_buffer.append(MockAttentionSnapshot())
    print(f"  ✅ 注入了模拟注意力快照")

    news_signals = [
        NewsSignal(
            source="test",
            signal_type="narrative",
            themes=["流动性紧张", "全球宏观"],
            sentiment=-0.8,
            content="美股暴跌流动性紧张",
            score=0.9,
        ),
        NewsSignal(
            source="test",
            signal_type="narrative",
            themes=["贵金属", "避险"],
            sentiment=0.6,
            content="黄金价格上涨避险情绪",
            score=0.7,
        ),
    ]

    for signal in news_signals:
        result = analyzer.ingest_news(signal)
        if result:
            print(f"  ✅ 新闻共振: {result.resonance_type}, 强度: {result.strength:.2f}")
        else:
            print(f"  ⚠️ 新闻未触发共振")

    print("\n## 步骤2: 注入市场快照")
    market_snapshots = [
        MarketSnapshot(
            market_index="nasdaq",
            market_name="纳斯达克",
            price_change=-2.5,
            volatility=0.8,
            activity=0.9,
        ),
        MarketSnapshot(
            market_index="vix",
            market_name="VIX恐慌指数",
            price_change=15.0,
            volatility=1.5,
            activity=1.0,
        ),
        MarketSnapshot(
            market_index="gold",
            market_name="黄金",
            price_change=1.2,
            volatility=0.3,
            activity=0.6,
        ),
    ]

    for snapshot in market_snapshots:
        analyzer.ingest_market_snapshot(snapshot)
        print(f"  ✅ 市场快照: {snapshot.market_index} change={snapshot.price_change:+.1f}%")

    print("\n## 步骤3: 共振摘要")
    summary = analyzer.get_market_resonance_summary()
    print(f"  市场快照数: {summary.get('共振列表', [])}")
    resonance_list = summary.get('共振列表', [])
    diagnosis = summary.get('诊断', {})
    print(f"  诊断原因: {diagnosis.get('reason', 'N/A')}")
    print(f"  置信度: {diagnosis.get('confidence', 0)}")

    if resonance_list:
        print(f"\n  ✅ 检测到 {len(resonance_list)} 个市场共振!")
        for r in resonance_list[:3]:
            print(f"     {r['market_index']} + {r['narrative']}: score={r['resonance_score']:.2f}")

    return analyzer


async def main():
    print("\n" + "#" * 70)
    print("#" + " " * 68 + "#")
    print("#    双通道架构测试 - 新闻数据 vs 市场数据                 #")
    print("#" + " " * 68 + "#")
    print("#" * 70)

    await test_news_flow()
    await test_market_flow()
    await test_resonance_flow()

    print("\n" + "=" * 70)
    print("  ✅ 双通道测试完成!")
    print("=" * 70)
    print("""
架构总结:
========

通道1 (新闻): NewsEvent → NarrativeTracker → 叙事生命周期
                ↓
             PropagationEngine (update_narrative_state)

通道2 (市场): GlobalMarketScanner → LiquidityCognition → PropagationEngine
                ↓
             MarketSnapshot → CrossSignalAnalyzer

共振检测: CrossSignalAnalyzer 同时接收新闻信号和市场快照
         分析两者是否共振 (时间、强度、叙事、相关性)
""")


if __name__ == "__main__":
    asyncio.run(main())
