#!/usr/bin/env python
"""
测试脚本：模拟热点策略信号，测试完整交易链路

信号流程：
StrategySignal → SignalDispatcher → SignalListener → AdaptiveCycle
            → TradingCenter.process_strategy_signal()
            → (批准) → VirtualPortfolio.open_position()
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')


def init_system():
    """初始化系统单例"""
    print("🔧 初始化系统单例...")

    from deva.naja.register import register_all_singletons
    register_all_singletons()
    print("✅ 系统单例注册完成")

    from deva.naja.register import SR

    from deva.naja.attention.trading_center import TradingCenter
    _ = TradingCenter()
    print("✅ TradingCenter 初始化完成")

    return SR


def create_test_signal():
    """创建测试信号"""
    import time
    from deva.naja.bandit.signal_listener import DetectedSignal

    signal = DetectedSignal(
        signal_id=f"test_signal_{int(time.time())}",
        stock_code="NVDA",
        stock_name="英伟达",
        signal_type="buy",
        price=450.0,
        confidence=0.75,
        timestamp=time.time(),
        strategy_id="us_momentum_surge_tracker",
        strategy_name="US Momentum Surge Tracker",
        raw_data={
            "block": "AI",
            "momentum": 0.85,
            "volume_ratio": 2.5,
        }
    )
    return signal


def test_signal_to_trading_center():
    """测试信号直接到 TradingCenter"""
    print("\n" + "="*60)
    print("测试 1: 信号直接到 TradingCenter")
    print("="*60)

    from deva.naja.attention.trading_center import get_trading_center

    tc = get_trading_center()
    if tc is None:
        print("❌ TradingCenter 不可用")
        return False

    import time
    signal_dict = {
        'strategy_id': 'us_momentum_surge_tracker',
        'strategy_name': 'US Momentum Surge Tracker',
        'stock_code': 'NVDA',
        'stock_name': '英伟达',
        'signal_type': 'buy',
        'price': 450.0,
        'confidence': 0.75,
        'timestamp': time.time(),
    }

    print(f"\n📤 发送信号到 TradingCenter:")
    print(f"   股票: {signal_dict['stock_code']} {signal_dict['stock_name']}")
    print(f"   价格: ${signal_dict['price']}")
    print(f"   置信度: {signal_dict['confidence']}")

    decision = tc.process_strategy_signal(signal_dict)

    if decision is None:
        print("❌ TradingCenter 返回 None")
        return False

    print(f"\n📥 TradingCenter 决策结果:")
    print(f"   批准: {decision.get('approved')}")
    print(f"   行动: {decision.get('action_type')}")
    print(f"   置信度: {decision.get('final_confidence', 0):.3f}")
    print(f"   和谐度: {decision.get('harmony_strength', 0):.3f}")
    print(f"   Manas: {decision.get('manas_score', 0):.3f}")
    print(f"   时机: {decision.get('timing_score', 0):.3f}")
    print(f"   格局: {decision.get('regime_score', 0):.3f}")
    print(f"   觉醒: {decision.get('awakening_level', 'unknown')}")

    if decision.get('reasoning'):
        print(f"\n   决策理由:")
        for r in decision.get('reasoning', []):
            print(f"     - {r}")

    return decision.get('approved', False)


def test_full_pipeline():
    """测试完整链路"""
    print("\n" + "="*60)
    print("测试 2: 完整链路 (SignalListener → AdaptiveCycle → TradingCenter)")
    print("="*60)

    from deva.naja.register import SR

    cycle = SR('adaptive_cycle')

    if cycle is None:
        print("❌ AdaptiveCycle 不可用")
        return False

    signal = create_test_signal()

    print(f"\n📤 模拟信号:")
    print(f"   股票: {signal.stock_code} {signal.stock_name}")
    print(f"   价格: ${signal.price}")
    print(f"   置信度: {signal.confidence}")
    print(f"   策略: {signal.strategy_id}")

    print(f"\n🔄 调用 AdaptiveCycle._on_new_signal()...")

    cycle._on_new_signal(signal)

    positions = cycle._portfolio.get_positions_by_stock(signal.stock_code)
    if positions:
        print(f"\n✅ 持仓创建成功!")
        if isinstance(positions, list):
            for pos in positions:
                print(f"   股票: {pos.stock_code} {pos.stock_name}")
                print(f"   价格: ${pos.price}")
                print(f"   数量: {pos.quantity}")
                print(f"   金额: ${pos.amount}")
        else:
            for pos_id, pos in positions.items():
                print(f"   持仓ID: {pos_id}")
                print(f"   股票: {pos.stock_code} {pos.stock_name}")
                print(f"   价格: ${pos.price}")
                print(f"   数量: {pos.quantity}")
                print(f"   金额: ${pos.amount}")
        return True
    else:
        print(f"\n⚠️  未找到持仓（可能被否决或还在处理中）")
        return False


def test_signal_stream():
    """测试信号流"""
    print("\n" + "="*60)
    print("测试 3: 信号到 SignalStream")
    print("="*60)

    from deva.naja.signal.stream import get_signal_stream
    from deva.naja.strategy.result_store import StrategyResult
    import time

    stream = get_signal_stream()

    result = StrategyResult(
        id=f"test_signal_{int(time.time())}",
        strategy_id="us_momentum_surge_tracker",
        strategy_name="US Momentum Surge Tracker",
        ts=time.time(),
        success=True,
        input_preview="NVDA momentum test",
        output_preview="BUY NVDA @ 450.0",
        output_full={
            "signal_type": "buy",
            "stock_code": "NVDA",
            "stock_name": "英伟达",
            "price": 450.0,
            "confidence": 0.75,
            "block": "AI",
        },
        process_time_ms=10.5,
        metadata={"test": True},
    )

    print(f"\n📤 发送信号到 SignalStream...")
    stream.update(result)

    recent = stream.get_recent(limit=5)
    print(f"   SignalStream 中的信号数: {len(recent)}")

    for r in recent[:3]:
        print(f"   - {r.strategy_name}: {r.output_preview[:50]}...")

    return len(recent) > 0


def main():
    print("\n" + "="*60)
    print("🧪 热点策略信号链路测试")
    print("="*60)

    init_system()
    results = {}

    try:
        results['trading_center'] = test_signal_to_trading_center()
    except Exception as e:
        print(f"❌ TradingCenter 测试失败: {e}")
        import traceback
        traceback.print_exc()
        results['trading_center'] = False

    try:
        results['signal_stream'] = test_signal_stream()
    except Exception as e:
        print(f"❌ SignalStream 测试失败: {e}")
        import traceback
        traceback.print_exc()
        results['signal_stream'] = False

    try:
        results['full_pipeline'] = test_full_pipeline()
    except Exception as e:
        print(f"❌ 完整链路测试失败: {e}")
        import traceback
        traceback.print_exc()
        results['full_pipeline'] = False

    print("\n" + "="*60)
    print("📊 测试结果汇总")
    print("="*60)
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {test_name}: {status}")

    all_passed = all(results.values())
    print(f"\n总体结果: {'✅ 全部通过' if all_passed else '❌ 存在问题'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
