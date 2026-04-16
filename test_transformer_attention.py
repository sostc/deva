"""
测试类 Transformer 注意力系统

验证新增功能的测试脚本
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import time
from deva.naja.attention.kernel import (
    AttentionEvent,
    QueryState,
    Encoder,
    AttentionHead,
    MultiHeadAttention,
    AttentionKernel,
    get_default_heads,
    MarketFeatureEncoder,
    EventEmbedding,
    TransformerLikeAttentionLayer,
)


def create_test_events():
    """创建测试事件"""
    events = []
    
    # 模拟几个相关的市场事件
    test_features = [
        {
            "price_change": 5.2,
            "volume_spike": 2.1,
            "sentiment": 0.8,
            "block": "AI",
            "alpha": 0.7,
            "risk": 0.3,
            "confidence": 0.8,
            "symbol": "NVDA"
        },
        {
            "price_change": 3.8,
            "volume_spike": 1.8,
            "sentiment": 0.7,
            "block": "AI",
            "alpha": 0.6,
            "risk": 0.4,
            "confidence": 0.7,
            "symbol": "AMD"
        },
        {
            "price_change": -2.1,
            "volume_spike": 1.2,
            "sentiment": -0.3,
            "block": "能源",
            "alpha": 0.3,
            "risk": 0.6,
            "confidence": 0.5,
            "symbol": "XOM"
        },
        {
            "price_change": 4.5,
            "volume_spike": 2.5,
            "sentiment": 0.9,
            "block": "AI",
            "alpha": 0.8,
            "risk": 0.2,
            "confidence": 0.9,
            "symbol": "MSFT"
        }
    ]
    
    for i, features in enumerate(test_features):
        event = AttentionEvent(
            source=f"test_{i}",
            data={"symbol": features["symbol"]},
            features=features,
            timestamp=time.time() - (len(test_features) - i) * 60
        )
        events.append(event)
    
    return events


def test_market_feature_encoder():
    """测试市场特征编码器"""
    print("=" * 60)
    print("测试 1: 市场特征编码器 (MarketFeatureEncoder)")
    print("=" * 60)
    
    encoder = MarketFeatureEncoder(embedding_dim=128)
    
    test_features = {
        "price_change": 5.0,
        "volume_spike": 2.0,
        "sentiment": 0.8,
        "block": "AI"
    }
    
    embedding = encoder.encode(test_features, time_position=0)
    
    print(f"✓ 嵌入维度: {embedding.shape}")
    print(f"✓ 嵌入向量范数: {np.linalg.norm(embedding):.4f}")
    print("✓ 市场特征编码器测试通过\n")


def test_event_embedding_and_self_attention():
    """测试事件嵌入和自注意力"""
    print("=" * 60)
    print("测试 2: 事件嵌入和自注意力")
    print("=" * 60)
    
    # 创建编码器和自注意力层
    feature_encoder = MarketFeatureEncoder(embedding_dim=128)
    transformer_layer = TransformerLikeAttentionLayer(
        d_model=128,
        num_heads=4,
        d_ff=512
    )
    
    # 创建测试事件嵌入
    events = create_test_events()
    event_embeddings = []
    
    for i, event in enumerate(events):
        vec = feature_encoder.encode(event.features, time_position=i)
        event_embeddings.append(EventEmbedding(
            vector=vec,
            features=event.features,
            timestamp=event.timestamp
        ))
    
    print(f"✓ 创建了 {len(event_embeddings)} 个事件嵌入")
    
    # 通过自注意力层
    enhanced_embeddings, attn_weights = transformer_layer.forward(event_embeddings)
    
    print(f"✓ 自注意力处理完成")
    print(f"✓ 注意力权重形状: {attn_weights.shape}")
    
    # 检查事件特征中的增强信息
    for i, (orig, enhanced) in enumerate(zip(event_embeddings, enhanced_embeddings)):
        change = np.linalg.norm(enhanced.vector - orig.vector)
        print(f"  事件 {i} 变化量: {change:.4f}")
    
    print("✓ 事件嵌入和自注意力测试通过\n")


def test_attention_kernel_with_transformer():
    """测试启用 Transformer 的 AttentionKernel"""
    print("=" * 60)
    print("测试 3: 启用 Transformer 的 AttentionKernel")
    print("=" * 60)
    
    # 创建基础组件
    encoder = Encoder()
    heads = get_default_heads()
    multi_head = MultiHeadAttention(heads, output_mode="merge")
    
    # 创建启用 Transformer 的 AttentionKernel
    kernel = AttentionKernel(
        encoder=encoder,
        multi_head=multi_head,
        enable_manas=False,
        enable_transformer=True
    )
    
    print(f"✓ Transformer 启用状态: {kernel.is_transformer_enabled()}")
    
    # 创建测试事件
    events = create_test_events()
    Q = QueryState()
    
    # 处理事件
    print(f"✓ 开始处理 {len(events)} 个事件...")
    result = kernel.process(Q, events)
    
    print(f"✓ 处理完成!")
    print(f"✓ 结果 - Alpha: {result.get('alpha', 0):.4f}")
    print(f"✓ 结果 - Risk: {result.get('risk', 0):.4f}")
    print(f"✓ 结果 - Confidence: {result.get('confidence', 0):.4f}")
    
    # 关闭 Transformer 再测试一次
    print("\n--- 对比测试：关闭 Transformer ---")
    kernel.set_transformer_enabled(False)
    result_no_transformer = kernel.process(Q, events)
    
    print(f"✓ 无 Transformer - Alpha: {result_no_transformer.get('alpha', 0):.4f}")
    print(f"✓ 无 Transformer - Risk: {result_no_transformer.get('risk', 0):.4f}")
    print(f"✓ 无 Transformer - Confidence: {result_no_transformer.get('confidence', 0):.4f}")
    
    print("\n✓ AttentionKernel 测试通过\n")


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("Naja Attention 系统 - 类 Transformer 改进测试")
    print("="*60 + "\n")
    
    try:
        test_market_feature_encoder()
        test_event_embedding_and_self_attention()
        test_attention_kernel_with_transformer()
        
        print("="*60)
        print("✅ 所有测试通过!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
