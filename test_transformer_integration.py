#!/usr/bin/env python3
"""
测试Transformer和上下文学习的集成

直接测试OSAttentionKernel的Transformer和上下文学习功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import time
from deva.naja.attention.kernel.embedding import MarketFeatureEncoder, EventEmbedding
from deva.naja.attention.kernel.self_attention import TransformerLikeAttentionLayer
from deva.naja.attention.kernel.in_context_learner import InContextAttentionLearner, Demonstration
from deva.naja.attention.kernel.event import AttentionEvent


def generate_test_events():
    """生成测试事件"""
    events = []
    
    # 模拟 AI 板块相关事件
    ai_events = [
        {
            "price_change": 5.2,
            "volume_spike": 2.1,
            "sentiment": 0.8,
            "block": "AI",
            "alpha": 0.7,
            "risk": 0.3,
            "confidence": 0.8,
            "symbol": "NVDA",
            "name": "英伟达"
        },
        {
            "price_change": 3.8,
            "volume_spike": 1.8,
            "sentiment": 0.7,
            "block": "AI",
            "alpha": 0.6,
            "risk": 0.4,
            "confidence": 0.7,
            "symbol": "AMD",
            "name": "超微半导体"
        },
        {
            "price_change": 4.5,
            "volume_spike": 2.5,
            "sentiment": 0.9,
            "block": "AI",
            "alpha": 0.8,
            "risk": 0.2,
            "confidence": 0.9,
            "symbol": "MSFT",
            "name": "微软"
        },
    ]
    
    # 模拟 新能源 板块相关事件
    energy_events = [
        {
            "price_change": -2.1,
            "volume_spike": 1.2,
            "sentiment": -0.3,
            "block": "新能源",
            "alpha": 0.3,
            "risk": 0.6,
            "confidence": 0.5,
            "symbol": "TSLA",
            "name": "特斯拉"
        },
        {
            "price_change": 1.2,
            "volume_spike": 1.0,
            "sentiment": 0.2,
            "block": "新能源",
            "alpha": 0.4,
            "risk": 0.5,
            "confidence": 0.6,
            "symbol": "BYD",
            "name": "比亚迪"
        },
    ]
    
    # 生成事件对象
    all_events = ai_events + energy_events
    for i, features in enumerate(all_events):
        event = AttentionEvent(
            source=f"market_{i}",
            data={
                "symbol": features["symbol"],
                "name": features["name"],
                "block": features["block"]
            },
            features=features,
            timestamp=time.time() - (len(all_events) - i) * 60
        )
        events.append(event)
    
    return events


def test_transformer_integration():
    """测试Transformer的集成"""
    print("=" * 80)
    print("测试 Transformer 自注意力集成")
    print("=" * 80)
    
    # 创建MarketFeatureEncoder实例
    encoder = MarketFeatureEncoder(embedding_dim=128)
    print("✓ 创建 MarketFeatureEncoder 实例成功")
    
    # 创建TransformerLikeAttentionLayer实例
    transformer = TransformerLikeAttentionLayer(
        d_model=128,
        num_heads=4,
        d_ff=512
    )
    print("✓ 创建 TransformerLikeAttentionLayer 实例成功")
    
    # 生成测试事件
    events = generate_test_events()
    print(f"✓ 生成了 {len(events)} 个测试事件")
    
    # 测试事件嵌入和自注意力
    print("\n测试事件嵌入和自注意力...")
    try:
        # 将事件转换为嵌入
        event_embeddings = []
        for i, e in enumerate(events):
            vec = encoder.encode(e.features, time_position=i)
            event_embeddings.append(EventEmbedding(
                vector=vec,
                features=e.features,
                timestamp=e.timestamp
            ))
        print("✓ 事件嵌入成功")
        
        # 通过自注意力层
        enhanced_embeddings, attn_matrix = transformer.forward(event_embeddings)
        print("✓ 自注意力处理成功")
        print(f"  - 注意力权重形状: {attn_matrix.shape}")
        
        # 显示注意力矩阵（简化版）
        print("\n注意力矩阵（头0，简化显示）:")
        if len(attn_matrix.shape) >= 4:
            head0_attn = attn_matrix[0, 0, :, :]
            symbols = [e.data.get("symbol") for e in events]
            
            # 打印表头
            header = "      "
            for sym in symbols:
                header += f"{sym:>6}"
            print(header)
            
            # 打印每行
            for i, row in enumerate(head0_attn):
                row_str = f"{symbols[i]:>6} "
                for val in row:
                    row_str += f"{val:.2f}  "
                print(row_str)
        
    except Exception as e:
        print(f"✗ Transformer 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 80)
    print("Transformer 集成测试完成！")
    print("=" * 80)
    return True


def test_in_context_learning():
    """测试上下文学习的集成"""
    print("\n" + "=" * 80)
    print("测试 上下文学习 集成")
    print("=" * 80)
    
    # 创建InContextAttentionLearner实例
    learner = InContextAttentionLearner(max_demonstrations=10)
    print("✓ 创建 InContextAttentionLearner 实例成功")
    
    # 添加历史示范样本
    print("\n添加历史示范样本...")
    
    # 示范 1: AI 板块上涨，成功案例
    demo1_events = [
        {"price_change": 5.0, "volume_spike": 2.0, "sentiment": 0.8, "block": "AI", "symbol": "NVDA"},
        {"price_change": 4.0, "volume_spike": 1.8, "sentiment": 0.7, "block": "AI", "symbol": "AMD"},
    ]
    demo1_decision = {"alpha": 0.8, "risk": 0.3, "confidence": 0.85}
    learner.add_demonstration(demo1_events, demo1_decision, outcome=0.15)
    print("  ✓ 添加示范 1: AI 板块上涨，成功 (盈利 15%)")
    
    # 示范 2: 新能源板块下跌，失败案例
    demo2_events = [
        {"price_change": -3.0, "volume_spike": 1.5, "sentiment": -0.5, "block": "新能源", "symbol": "TSLA"},
    ]
    demo2_decision = {"alpha": 0.4, "risk": 0.7, "confidence": 0.5}
    learner.add_demonstration(demo2_events, demo2_decision, outcome=-0.08)
    print("  ✓ 添加示范 2: 新能源板块下跌，失败 (亏损 8%)")
    
    # 生成当前事件
    current_events = [
        {"price_change": 4.8, "volume_spike": 2.2, "sentiment": 0.7, "block": "AI", "symbol": "NVDA"},
        {"price_change": 3.5, "volume_spike": 1.9, "sentiment": 0.6, "block": "AI", "symbol": "AMD"},
        {"price_change": -1.8, "volume_spike": 1.3, "sentiment": -0.2, "block": "新能源", "symbol": "TSLA"},
    ]
    print("\n生成当前事件...")
    
    # 测试上下文学习
    print("\n测试上下文学习...")
    try:
        # 模拟QueryState
        class MockQueryState:
            def __init__(self):
                self.features = {}
        
        Q = MockQueryState()
        adjusted_Q, adjustment_info = learner.adjust_query_with_demos(Q, current_events)
        print("✓ 上下文学习调整成功")
        print("\n上下文学习调整结果:")
        print(f"  相关示范数量: {adjustment_info.get('num_demos', 0)}")
        print(f"  历史成功率: {adjustment_info.get('historical_success', 0):.2f}")
        print(f"  Alpha 调整: {adjustment_info.get('avg_alpha_bias', 0):+.2f}")
        print(f"  Risk 调整: {adjustment_info.get('avg_risk_bias', 0):+.2f}")
        print(f"  Confidence 调整: {adjustment_info.get('avg_confidence_bias', 0):+.2f}")
        
    except Exception as e:
        print(f"✗ 上下文学习测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 80)
    print("上下文学习集成测试完成！")
    print("=" * 80)
    return True


def main():
    """主测试函数"""
    print("开始集成测试...")
    print("=" * 80)
    
    # 测试Transformer集成
    transformer_success = test_transformer_integration()
    
    # 测试上下文学习集成
    context_success = test_in_context_learning()
    
    print("\n" + "=" * 80)
    print("集成测试总结果:")
    print(f"Transformer 集成: {'成功' if transformer_success else '失败'}")
    print(f"上下文学习集成: {'成功' if context_success else '失败'}")
    print("=" * 80)
    
    return transformer_success and context_success


if __name__ == "__main__":
    main()
