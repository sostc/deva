"""
Naja Attention 系统 - 借鉴 Transformer 和大模型技术演示

这个文件演示了如何使用新增的功能：
1. 事件嵌入和位置编码
2. 事件自注意力机制
3. 上下文学习（In-Context Learning）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import time
from deva.naja.attention import (
    AttentionEvent,
    QueryState,
    Encoder,
    AttentionHead,
    MultiHeadAttention,
    AttentionKernel,
    get_default_heads,
    # 新增功能
    MarketFeatureEncoder,
    EventEmbedding,
    TransformerLikeAttentionLayer,
    InContextAttentionLearner,
    Demonstration,
)


def demo_1_event_embedding():
    """演示 1: 事件嵌入和位置编码"""
    print("\n" + "="*60)
    print("演示 1: 事件嵌入和位置编码")
    print("="*60)
    
    encoder = MarketFeatureEncoder(embedding_dim=64)
    
    # 创建几个测试事件特征
    test_events = [
        {
            "price_change": 5.2,
            "volume_spike": 2.1,
            "sentiment": 0.8,
            "block": "AI",
            "symbol": "NVDA"
        },
        {
            "price_change": 3.8,
            "volume_spike": 1.8,
            "sentiment": 0.7,
            "block": "AI",
            "symbol": "AMD"
        },
        {
            "price_change": -2.1,
            "volume_spike": 1.2,
            "sentiment": -0.3,
            "block": "能源",
            "symbol": "XOM"
        }
    ]
    
    print("\n创建事件嵌入（带位置编码）:")
    for i, features in enumerate(test_events):
        embedding = encoder.encode(features, time_position=i)
        print(f"  事件 {i} ({features['symbol']}):")
        print(f"    - 嵌入维度: {embedding.shape}")
        print(f"    - 向量范数: {np.linalg.norm(embedding):.4f}")
        print(f"    - 前5个值: {embedding[:5]}")
    
    print("\n✓ 事件嵌入演示完成")


def demo_2_self_attention():
    """演示 2: 事件自注意力机制"""
    print("\n" + "="*60)
    print("演示 2: 事件自注意力机制")
    print("="*60)
    
    # 创建编码器和自注意力层
    feature_encoder = MarketFeatureEncoder(embedding_dim=64)
    transformer_layer = TransformerLikeAttentionLayer(
        d_model=64,
        num_heads=4,
        d_ff=256
    )
    
    # 创建测试事件
    test_events = [
        {
            "price_change": 5.2,
            "volume_spike": 2.1,
            "sentiment": 0.8,
            "block": "AI",
            "symbol": "NVDA"
        },
        {
            "price_change": 3.8,
            "volume_spike": 1.8,
            "sentiment": 0.7,
            "block": "AI",
            "symbol": "AMD"
        },
        {
            "price_change": -2.1,
            "volume_spike": 1.2,
            "sentiment": -0.3,
            "block": "能源",
            "symbol": "XOM"
        },
        {
            "price_change": 4.5,
            "volume_spike": 2.5,
            "sentiment": 0.9,
            "block": "AI",
            "symbol": "MSFT"
        }
    ]
    
    # 创建事件嵌入
    event_embeddings = []
    for i, features in enumerate(test_events):
        vec = feature_encoder.encode(features, time_position=i)
        event_embeddings.append(EventEmbedding(
            vector=vec,
            features=features,
            timestamp=time.time()
        ))
    
    print(f"\n✓ 创建了 {len(event_embeddings)} 个事件嵌入")
    
    # 通过自注意力层
    print("\n正在通过自注意力层...")
    enhanced_embeddings, attn_weights = transformer_layer.forward(event_embeddings)
    
    print(f"\n✓ 自注意力处理完成!")
    print(f"  - 注意力权重形状: {attn_weights.shape}")
    
    # 显示事件变化
    print("\n事件嵌入变化量:")
    for i, (orig, enhanced) in enumerate(zip(event_embeddings, enhanced_embeddings)):
        change = np.linalg.norm(enhanced.vector - orig.vector)
        symbol = orig.features.get("symbol", "N/A")
        print(f"  {i} [{symbol}]: 变化量 = {change:.4f}")
    
    # 显示注意力矩阵（简化版）
    print("\n注意力矩阵（头0，简化显示）:")
    if len(attn_weights.shape) >= 4:
        head0_attn = attn_weights[0, 0, :, :]
        for i in range(len(head0_attn)):
            row_str = "  ["
            for j in range(len(head0_attn[i])):
                row_str += f"{head0_attn[i, j]:.2f} "
            row_str += "]"
            print(row_str)
    
    print("\n✓ 自注意力演示完成")


def demo_3_in_context_learning():
    """演示 3: 上下文学习（In-Context Learning）"""
    print("\n" + "="*60)
    print("演示 3: 上下文学习（In-Context Learning）")
    print("="*60)
    
    learner = InContextAttentionLearner(max_demonstrations=10)
    
    # 添加一些历史示范样本
    print("\n添加历史示范样本...")
    
    # 示范 1: AI 板块上涨，成功案例
    demo1_events = [
        {"price_change": 5.0, "volume_spike": 2.0, "sentiment": 0.8, "block": "AI", "symbol": "NVDA"},
        {"price_change": 4.0, "volume_spike": 1.8, "sentiment": 0.7, "block": "AI", "symbol": "AMD"},
    ]
    demo1_decision = {"alpha": 0.8, "risk": 0.3, "confidence": 0.85}
    learner.add_demonstration(demo1_events, demo1_decision, outcome=0.15)
    print("  ✓ 添加示范 1: AI 板块上涨，成功 (盈利 15%)")
    
    # 示范 2: 能源板块下跌，失败案例
    demo2_events = [
        {"price_change": -3.0, "volume_spike": 1.5, "sentiment": -0.5, "block": "能源", "symbol": "XOM"},
    ]
    demo2_decision = {"alpha": 0.4, "risk": 0.7, "confidence": 0.5}
    learner.add_demonstration(demo2_events, demo2_decision, outcome=-0.08)
    print("  ✓ 添加示范 2: 能源板块下跌，失败 (亏损 8%)")
    
    # 示范 3: 另一个 AI 成功案例
    demo3_events = [
        {"price_change": 6.0, "volume_spike": 2.2, "sentiment": 0.9, "block": "AI", "symbol": "MSFT"},
    ]
    demo3_decision = {"alpha": 0.9, "risk": 0.25, "confidence": 0.9}
    learner.add_demonstration(demo3_events, demo3_decision, outcome=0.22)
    print("  ✓ 添加示范 3: AI 另一成功案例 (盈利 22%)")
    
    # 显示统计信息
    stats = learner.get_demo_statistics()
    print(f"\n示范样本统计:")
    print(f"  - 总数: {stats['total']}")
    print(f"  - 成功: {stats['successful']}")
    print(f"  - 平均结果: {stats['avg_outcome']:.2%}")
    print(f"  - 最好结果: {stats['best_outcome']:.2%}")
    print(f"  - 最差结果: {stats['worst_outcome']:.2%}")
    
    # 测试检索相关示范
    print("\n测试检索相关示范...")
    current_events = [
        {"price_change": 4.5, "volume_spike": 2.0, "sentiment": 0.85, "block": "AI", "symbol": "NVDA"},
    ]
    
    relevant_demos = learner.retrieve_relevant_demos(current_events, k=2)
    print(f"  找到 {len(relevant_demos)} 个相关示范")
    for i, demo in enumerate(relevant_demos):
        print(f"    {i+1}. 结果: {demo.outcome:.2%}, 符号: {[e.get('symbol','N/A') for e in demo.events]}")
    
    # 测试调整 Query
    print("\n测试使用示范调整 Query...")
    Q = QueryState()
    Q.features = {}
    
    adjusted_Q, adjustment_info = learner.adjust_query_with_demos(Q, current_events)
    
    if adjustment_info:
        print(f"  调整信息:")
        for key, value in adjustment_info.items():
            print(f"    - {key}: {value}")
    
    print("\n✓ 上下文学习演示完成")


def demo_4_full_pipeline():
    """演示 4: 完整的集成管道"""
    print("\n" + "="*60)
    print("演示 4: 完整的集成管道")
    print("="*60)
    
    # 创建完整的 AttentionKernel，启用所有新功能
    encoder = Encoder()
    heads = get_default_heads()
    multi_head = MultiHeadAttention(heads, output_mode="merge")
    
    kernel = AttentionKernel(
        encoder=encoder,
        multi_head=multi_head,
        enable_manas=False,
        enable_transformer=True,  # 启用 Transformer
        enable_in_context=True    # 启用上下文学习
    )
    
    print("\n✓ AttentionKernel 创建完成")
    print(f"  - Transformer 启用: {kernel.is_transformer_enabled()}")
    print(f"  - 上下文学习启用: {kernel.is_in_context_enabled()}")
    
    # 添加上下文学习示范
    print("\n添加上下文学习示范...")
    learner = kernel.get_in_context_learner()
    
    demo_events = [
        {"price_change": 5.0, "volume_spike": 2.0, "sentiment": 0.8, "block": "AI", "symbol": "NVDA"},
    ]
    demo_decision = {"alpha": 0.8, "risk": 0.3, "confidence": 0.85}
    learner.add_demonstration(demo_events, demo_decision, outcome=0.15)
    
    # 创建测试事件
    print("\n创建测试事件...")
    test_events = []
    for i in range(4):
        features = {
            "price_change": [5.2, 3.8, -2.1, 4.5][i],
            "volume_spike": [2.1, 1.8, 1.2, 2.5][i],
            "sentiment": [0.8, 0.7, -0.3, 0.9][i],
            "block": ["AI", "AI", "能源", "AI"][i],
            "alpha": [0.7, 0.6, 0.3, 0.8][i],
            "risk": [0.3, 0.4, 0.6, 0.2][i],
            "confidence": [0.8, 0.7, 0.5, 0.9][i],
        }
        event = AttentionEvent(
            source=f"demo_{i}",
            data={"symbol": ["NVDA", "AMD", "XOM", "MSFT"][i]},
            features=features,
            timestamp=time.time()
        )
        test_events.append(event)
    
    print(f"✓ 创建了 {len(test_events)} 个测试事件")
    
    # 处理事件
    print("\n开始处理事件...")
    Q = QueryState()
    result = kernel.process(Q, test_events)
    
    print("\n✓ 处理完成!")
    print(f"\n最终结果:")
    print(f"  - Alpha: {result.get('alpha', 0):.4f}")
    print(f"  - Risk: {result.get('risk', 0):.4f}")
    print(f"  - Confidence: {result.get('confidence', 0):.4f}")
    
    if "_in_context" in result:
        print(f"\n上下文学习信息:")
        for key, value in result["_in_context"].items():
            print(f"  - {key}: {value}")
    
    print("\n✓ 完整管道演示完成")


def main():
    """运行所有演示"""
    print("\n" + "="*60)
    print("Naja Attention 系统 - 借鉴 Transformer 和大模型技术演示")
    print("="*60)
    
    try:
        demo_1_event_embedding()
        demo_2_self_attention()
        demo_3_in_context_learning()
        demo_4_full_pipeline()
        
        print("\n" + "="*60)
        print("✅ 所有演示完成!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
