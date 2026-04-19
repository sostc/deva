"""
Naja Attention 系统 - 真实世界演示案例

这个文件模拟真实的市场数据，演示整个注意力系统的工作流程：
1. 模拟市场事件数据
2. 展示 Transformer 自注意力的效果
3. 展示上下文学习的效果
4. 展示完整的决策流程
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
    MultiHeadAttention,
    AttentionKernel,
    get_default_heads,
    InContextAttentionLearner,
    MarketFeatureEncoder,
    TransformerLikeAttentionLayer,
    EventEmbedding,
)


def generate_market_events():
    """生成模拟市场事件"""
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
        {
            "price_change": 2.9,
            "volume_spike": 1.5,
            "sentiment": 0.6,
            "block": "AI",
            "alpha": 0.5,
            "risk": 0.5,
            "confidence": 0.6,
            "symbol": "GOOG",
            "name": "谷歌"
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


def run_demo():
    """运行完整演示"""
    print("\n" + "="*80)
    print("Naja Attention 系统 - 真实世界演示案例")
    print("="*80)
    
    # 1. 生成模拟市场事件
    print("\n📊 步骤 1: 生成模拟市场事件")
    print("-" * 60)
    events = generate_market_events()
    print(f"✓ 生成了 {len(events)} 个市场事件")
    
    # 显示事件摘要
    print("\n事件摘要:")
    for i, event in enumerate(events):
        symbol = event.data.get("symbol")
        name = event.data.get("name")
        block = event.data.get("block")
        price_change = event.features.get("price_change")
        sentiment = event.features.get("sentiment")
        
        print(f"  {i+1}. {name} ({symbol}) - {block}")
        print(f"     价格变化: {price_change:+.1f}%  情绪: {sentiment:.1f}")
    
    # 2. 演示事件嵌入和位置编码
    print("\n🔄 步骤 2: 事件嵌入和位置编码")
    print("-" * 60)
    encoder = MarketFeatureEncoder(embedding_dim=64)
    
    print("\n事件嵌入结果:")
    for i, event in enumerate(events[:3]):  # 只显示前3个
        embedding = encoder.encode(event.features, time_position=i)
        print(f"  {event.data['symbol']}:")
        print(f"    嵌入维度: {embedding.shape}")
        print(f"    向量范数: {np.linalg.norm(embedding):.4f}")
    
    # 3. 演示自注意力机制
    print("\n🧠 步骤 3: 自注意力机制")
    print("-" * 60)
    
    # 创建事件嵌入
    event_embeddings = []
    for i, event in enumerate(events):
        vec = encoder.encode(event.features, time_position=i)
        event_embeddings.append(EventEmbedding(
            vector=vec,
            features=event.features,
            timestamp=event.timestamp
        ))
    
    # 使用自注意力层
    transformer = TransformerLikeAttentionLayer(
        d_model=64,
        num_heads=4,
        d_ff=256
    )
    
    print("\n正在通过自注意力层...")
    enhanced_embeddings, attn_weights = transformer.forward(event_embeddings)
    
    print(f"\n✓ 自注意力处理完成!")
    print(f"  - 注意力权重形状: {attn_weights.shape}")
    
    # 显示注意力矩阵（简化版）
    print("\n注意力矩阵（头0，简化显示）:")
    if len(attn_weights.shape) >= 4:
        head0_attn = attn_weights[0, 0, :, :]
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
    
    # 4. 演示上下文学习
    print("\n📚 步骤 4: 上下文学习")
    print("-" * 60)
    
    learner = InContextAttentionLearner(max_demonstrations=10)
    
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
    
    # 5. 上下文学习效果演示
    print("\n🚀 步骤 5: 上下文学习效果演示")
    print("-" * 60)
    
    # 模拟当前事件
    current_events = [event.features for event in events]
    
    # 调整查询
    Q = QueryState()
    adjusted_Q, adjustment_info = learner.adjust_query_with_demos(Q, current_events)
    
    print("\n上下文学习调整结果:")
    print(f"  相关示范数量: {adjustment_info.get('num_demos', 0)}")
    print(f"  历史成功率: {adjustment_info.get('historical_success', 0):.2f}")
    print(f"  Alpha 调整: {adjustment_info.get('avg_alpha_bias', 0):+.2f}")
    print(f"  Risk 调整: {adjustment_info.get('avg_risk_bias', 0):+.2f}")
    print(f"  Confidence 调整: {adjustment_info.get('avg_confidence_bias', 0):+.2f}")
    
    # 6. 模拟决策过程
    print("\n📋 步骤 6: 模拟决策过程")
    print("-" * 60)
    
    # 基于增强的嵌入和上下文学习进行决策
    print("\n基于 Transformer 自注意力和上下文学习的决策:")
    print("  1. 事件通过自注意力层，发现事件间关系")
    print("  2. 上下文学习从历史案例中获取经验")
    print("  3. 综合考虑当前市场情况和历史经验")
    
    # 模拟最终决策
    final_decision = {
        "alpha": 0.75 + adjustment_info.get('avg_alpha_bias', 0),
        "risk": 0.35 + adjustment_info.get('avg_risk_bias', 0),
        "confidence": 0.8 + adjustment_info.get('avg_confidence_bias', 0)
    }
    
    print("\n最终决策:")
    print(f"  Alpha: {final_decision['alpha']:.4f}")
    print(f"  Risk: {final_decision['risk']:.4f}")
    print(f"  Confidence: {final_decision['confidence']:.4f}")
    
    # 7. 总结
    print("\n✅ 演示完成!")
    print("=" * 80)
    print("\n📝 总结:")
    print("1. 事件嵌入和位置编码: 将市场事件转换为向量表示")
    print("2. 自注意力机制: 让事件之间互相关注，发现事件间的关系")
    print("3. 上下文学习: 从历史案例中学习，调整当前决策")
    print("4. 决策过程: 综合考虑当前市场情况和历史经验")
    print("\n💡 优势:")
    print("- 模块化: 各组件可单独使用")
    print("- 智能增强: 利用 Transformer 和大模型技术提升决策质量")
    print("- 可解释: 保持决策逻辑的可解释性")
    print("- 灵活集成: 可以根据需要集成到现有系统")
    print("\n" + "=" * 80)


def main():
    """主函数"""
    try:
        run_demo()
    except Exception as e:
        print(f"\n❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
