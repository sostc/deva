"""
V2 系统演示脚本

展示如何使用 v2 增强功能
"""

import numpy as np
import time
import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from naja_attention_system.v2 import (
    create_v2_system,
    V2Config,
    AttentionBudgetSystem,
    BudgetConfig,
    PredictiveAttentionEngine,
    AttentionFeedbackLoop,
    AttentionPropagation,
    StrategyLearning
)


def demo_predictive_attention():
    """演示预测注意力"""
    print("\n" + "="*60)
    print("Module 7: Predictive Attention Engine 演示")
    print("="*60)
    
    engine = PredictiveAttentionEngine(alpha=0.7, beta=0.3)
    
    symbols = np.array(['000001', '000002', '000003', '000004', '000005'])
    current_attention = {
        '000001': 0.5, '000002': 0.7, '000003': 0.3, '000004': 0.8, '000005': 0.4
    }
    returns = np.array([2.5, -1.2, 0.8, 5.0, -0.5])
    volumes = np.array([1000000, 800000, 500000, 2000000, 600000])
    timestamps = np.array([time.time()] * 5)
    
    results = engine.batch_predict(
        symbols=symbols,
        current_attention=current_attention,
        returns=returns,
        volumes=volumes,
        timestamps=timestamps
    )
    
    print("\n预测结果:")
    for symbol, (pred_score, final_att) in results.items():
        print(f"  {symbol}: prediction={pred_score:.3f}, final_attention={final_att:.3f}")
    
    top_k = engine.get_predictions_top_k(k=3)
    print(f"\n预测分数最高 Top-3: {top_k}")


def demo_budget_system():
    """演示预算系统"""
    print("\n" + "="*60)
    print("Module 9: Attention Budget System 演示")
    print("="*60)
    
    budget_config = BudgetConfig(
        max_tier1_symbols=20,
        max_tier2_symbols=100,
        total_budget=50.0
    )
    
    system = AttentionBudgetSystem(budget_config)
    
    symbol_scores = {
        f'symbol_{i}': np.random.random() * 3
        for i in range(200)
    }
    
    allocation = system.allocate(symbol_scores)
    
    print(f"\n预算分配结果:")
    print(f"  Tier1 (高频): {len(allocation.tier1_symbols)} symbols, 成本: {allocation.tier1_total_cost:.2f}")
    print(f"  Tier2 (中频): {len(allocation.tier2_symbols)} symbols, 成本: {allocation.tier2_total_cost:.2f}")
    print(f"  Tier3 (低频): {len(allocation.tier3_symbols)} symbols, 成本: {allocation.tier3_total_cost:.2f}")
    print(f"  总成本: {allocation.total_cost:.2f} / {system.config.total_budget}")
    print(f"  预算利用率: {allocation.budget_utilization:.1%}")
    print(f"  拒绝 symbols: {len(allocation.rejected_symbols)}")
    
    print(f"\n高频 symbols (Tier1): {allocation.tier1_symbols[:5]}...")


def demo_propagation():
    """演示注意力传播"""
    print("\n" + "="*60)
    print("Module 10: Attention Propagation 演示")
    print("="*60)
    
    propagation = AttentionPropagation()
    
    sectors = ['新能源', '有色', '电池', '汽车', '科技']
    for s in sectors:
        propagation.register_sector(s)
    
    propagation.add_upstream_relation('新能源', '电池', 0.8)
    propagation.add_upstream_relation('有色', '电池', 0.6)
    propagation.add_upstream_relation('新能源', '汽车', 0.5)
    
    sector_attention = {
        '新能源': 0.9,
        '有色': 0.3,
        '电池': 0.4,
        '汽车': 0.2,
        '科技': 0.1
    }
    
    propagated = propagation.propagate(sector_attention)
    
    print("\n原始注意力:")
    for s, att in sector_attention.items():
        print(f"  {s}: {att:.2f}")
    
    print("\n传播后注意力:")
    for s, att in propagated.items():
        change = att - sector_attention[s]
        print(f"  {s}: {att:.2f} ({change:+.2f})")
    
    relations = propagation.get_all_relations()
    print(f"\n板块关系数量: {len(relations)}")


def demo_feedback_loop():
    """演示反馈循环"""
    print("\n" + "="*60)
    print("Module 8: Attention Feedback Loop 演示")
    print("="*60)
    
    feedback = AttentionFeedbackLoop()
    
    for i in range(20):
        feedback.record_outcome(
            strategy_id='momentum_tracker',
            symbol='000001',
            sector_id='新能源',
            attention_before=0.6 + np.random.random() * 0.2,
            attention_after=0.7,
            prediction_score=0.6,
            action='buy',
            pnl=np.random.random() * 0.2 - 0.05,
            holding_period=30,
            market_state='high_attention_high_volatility'
        )
    
    for i in range(20):
        feedback.record_outcome(
            strategy_id='sector_hunter',
            symbol='000002',
            sector_id='有色',
            attention_before=0.4 + np.random.random() * 0.2,
            attention_after=0.5,
            prediction_score=0.5,
            action='buy',
            pnl=np.random.random() * 0.1 - 0.08,
            holding_period=20,
            market_state='moderate_attention_low_pattern'
        )
    
    summary = feedback.get_summary()
    print(f"\n反馈摘要:")
    print(f"  总 outcomes: {summary['total_outcomes']}")
    print(f"  观察到的模式: {summary['patterns_observed']}")
    print(f"  有效模式: {summary['effective_patterns']}")
    print(f"  无效模式: {summary['ineffective_patterns']}")
    
    adjustment = feedback.get_attention_adjustment(
        symbol='000001',
        attention=0.7,
        prediction_score=0.6,
        market_state='high_attention_high_volatility'
    )
    print(f"\n注意力调整建议: {adjustment:.2f}")


def demo_strategy_learning():
    """演示策略学习"""
    print("\n" + "="*60)
    print("Module 11: Strategy Learning 演示")
    print("="*60)
    
    learning = StrategyLearning()
    
    strategies = ['momentum_tracker', 'sector_hunter', 'anomaly_sniper', 'smart_money_detector']
    
    for episode in range(50):
        global_att = 0.5 + np.random.random() * 0.3
        sector_att = {'新能源': 0.6, '有色': 0.4, '电池': 0.7}
        
        selection = learning.select_strategies(
            global_attention=global_att,
            sector_attention=sector_att,
            available_strategies=strategies,
            top_k=2
        )
        
        pnl = np.random.random() * 0.15 - 0.05
        learning.record_outcome(
            strategy_id=selection.selected_strategies[0],
            pnl=pnl,
            holding_time=30
        )
    
    summary = learning.get_selection_summary()
    print(f"\n策略选择摘要:")
    print(f"  当前市场状态: {summary['current_state']}")
    print(f"  最后选择: {summary['last_selection']['selected']}")
    print(f"  选择置信度: {summary['last_selection']['confidence']:.2f}")
    
    stats = learning.get_learning_stats()
    if stats:
        print(f"\n学习统计:")
        print(f"  学习策略数: {stats.get('total_strategies_learned', 0)}")
        print(f"  最高奖励策略: {stats.get('most_rewards', 'N/A')}")
        print(f"  最高置信度策略: {stats.get('highest_confidence', 'N/A')}")


def demo_v2_integration():
    """演示 v2 集成系统"""
    print("\n" + "="*60)
    print("V2 Enhanced Attention System 集成演示")
    print("="*60)
    
    system = create_v2_system(
        enable_predictive=True,
        enable_feedback=True,
        enable_budget=True,
        enable_propagation=False,
        enable_strategy_learning=False
    )
    
    symbols = np.array([f'{i:06d}' for i in range(1, 101)])
    returns = np.random.randn(100) * 2
    volumes = np.random.rand(100) * 1000000 + 500000
    prices = np.random.rand(100) * 100 + 10
    sector_ids = np.array([f'sector_{i % 10}' for i in range(100)])
    timestamp = time.time()
    
    result = system.process_snapshot(
        symbols=symbols,
        returns=returns,
        volumes=volumes,
        prices=prices,
        sector_ids=sector_ids,
        timestamp=timestamp
    )
    
    print(f"\n处理完成!")
    print(f"  延迟: {result['latency_ms']:.2f} ms")
    print(f"  V2 启用模块: {result['v2_enabled']}")
    
    if 'budget_allocation' in result:
        budget = result['budget_allocation']
        print(f"\n预算分配:")
        print(f"  高频: {len(budget['tier1'])} symbols")
        print(f"  中频: {len(budget['tier2'])} symbols")
        print(f"  低频: {len(budget['tier3'])} symbols")
        print(f"  利用率: {budget['utilization']:.1%}")
    
    if 'prediction_scores' in result:
        pred_scores = result['prediction_scores']
        top_preds = sorted(pred_scores.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"\n预测分数 Top-5:")
        for symbol, score in top_preds:
            print(f"  {symbol}: {score:.3f}")
    
    v2_summary = system.get_v2_summary()
    print(f"\nV2 系统摘要:")
    print(f"  {v2_summary}")


def main():
    print("\n" + "#"*60)
    print("# Naja Attention System v2.0 演示")
    print("#"*60)
    
    demo_predictive_attention()
    demo_budget_system()
    demo_propagation()
    demo_feedback_loop()
    demo_strategy_learning()
    demo_v2_integration()
    
    print("\n" + "#"*60)
    print("# 演示完成!")
    print("#"*60 + "\n")


if __name__ == '__main__':
    main()
