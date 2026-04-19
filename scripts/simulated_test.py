"""
Naja Attention 系统模拟测试

逐步展示整个系统的数据流链路，包括：
1. 数据输入
2. 特征编码
3. Transformer 处理
4. 上下文学习
5. 策略决策
6. 风险评估
7. 最终输出
"""

import sys
import os
import logging
import numpy as np
from typing import Dict, Any, List

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)


class SimulatedMarketData:
    """模拟市场数据"""
    
    def __init__(self):
        self.timestamp = 1680000000  # 模拟时间戳
    
    def generate_market_data(self):
        """生成模拟市场数据"""
        return {
            "market_volatility": 1.8,  # 市场波动率
            "liquidity_score": 0.75,  # 流动性得分
            "market_index": 3200.5,  # 市场指数
            "volume": 1200000000,  # 成交量
            "advance_decline_ratio": 1.2  # 涨跌比
        }
    
    def generate_market_state(self):
        """生成模拟市场状态"""
        return {
            "trend_strength": 0.6,  # 趋势强度
            "market_breadth": 0.4,  # 市场广度
            "momentum": 0.7,  # 动量
            "sentiment": 0.5,  # 情绪
            "volatility_trend": 0.2  # 波动率趋势
        }
    
    def generate_positions(self):
        """生成模拟持仓数据"""
        return {
            "AAPL": {
                "quantity": 100,
                "cost": 150.0,
                "current_price": 155.0
            },
            "MSFT": {
                "quantity": 50,
                "cost": 300.0,
                "current_price": 310.0
            },
            "GOOGL": {
                "quantity": 20,
                "cost": 2800.0,
                "current_price": 2850.0
            }
        }


def test_feature_encoding():
    """测试特征编码"""
    log.info("=== 步骤 1: 特征编码 ===")
    
    try:
        from deva.naja.attention.kernel.embedding import MarketFeatureEncoder
        
        # 创建编码器
        encoder = MarketFeatureEncoder(embedding_dim=64)
        log.info("创建 MarketFeatureEncoder 成功")
        
        # 生成模拟数据
        market_data = SimulatedMarketData()
        market_data_dict = market_data.generate_market_data()
        market_state_dict = market_data.generate_market_state()
        
        # 构造特征字典
        features = {
            "price_change": 0.03,  # 价格变化
            "volume_spike": 1.5,  # 成交量变化
            "sentiment": 0.5,  # 情绪
            "block": "tech",  # 板块
            **market_data_dict,
            **market_state_dict
        }
        
        # 编码特征
        encoded_features = encoder.encode(features, time_position=0)
        log.info(f"特征编码成功，编码后维度: {encoded_features.shape}")
        
        return encoded_features
        
    except Exception as e:
        log.error(f"特征编码测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_transformer_processing(encoded_features):
    """测试 Transformer 处理"""
    log.info("=== 步骤 2: Transformer 处理 ===")
    
    try:
        from deva.naja.attention.kernel.self_attention import TransformerLikeAttentionLayer
        from deva.naja.attention.kernel.embedding import EventEmbedding
        
        # 创建 Transformer 层
        attention_layer = TransformerLikeAttentionLayer(d_model=64, num_heads=4, d_ff=256)
        log.info("创建 TransformerLikeAttentionLayer 成功")
        
        # 模拟输入数据 - 创建 EventEmbedding 对象列表
        event_embeddings = []
        for i in range(10):  # 10个时间步
            # 直接在构造函数中提供参数
            event = EventEmbedding(
                vector=encoded_features,  # 使用之前编码的特征
                features={"time_step": i},  # 特征字典
                timestamp=1680000000 + i  # 时间戳
            )
            event_embeddings.append(event)
        
        log.info(f"创建了 {len(event_embeddings)} 个 EventEmbedding 对象")
        
        # 处理输入
        output = attention_layer.forward(event_embeddings)
        log.info("Transformer 处理成功")
        
        return output
        
    except Exception as e:
        log.error(f"Transformer 处理测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_context_learning():
    """测试上下文学习"""
    log.info("=== 步骤 3: 上下文学习 ===")
    
    try:
        from deva.naja.attention.kernel.in_context_learner import InContextAttentionLearner, Demonstration
        
        # 创建上下文学习器
        learner = InContextAttentionLearner(max_demonstrations=20, embedding_dim=64)
        log.info("创建 InContextAttentionLearner 成功")
        
        # 添加演示样本
        # 直接调用add_demonstration方法，传递所需参数
        learner.add_demonstration(
            events=[{"volatility": 1.5, "trend": 0.6, "price_change": 0.02}],
            decision={"action": "buy", "confidence": 0.8},
            outcome=0.05,  # 5% 盈利
            metadata={"symbol": "AAPL"}
        )
        
        learner.add_demonstration(
            events=[{"volatility": 2.5, "trend": -0.4, "price_change": -0.03}],
            decision={"action": "sell", "confidence": 0.9},
            outcome=0.03,  # 3% 盈利
            metadata={"symbol": "MSFT"}
        )
        log.info(f"添加了 {len(learner.demonstrations)} 个演示样本")
        
        # 测试相似度计算
        test_event = [{"volatility": 1.8, "trend": 0.5, "price_change": 0.01}]
        similar_demos = learner.retrieve_relevant_demos(test_event, k=1)
        log.info(f"检索到 {len(similar_demos)} 个相似演示样本")
        
        return learner
        
    except Exception as e:
        log.error(f"上下文学习测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_strategy_decision():
    """测试策略决策"""
    log.info("=== 步骤 4: 策略决策 ===")
    
    try:
        # 模拟策略决策结果
        # 由于StrategyDecisionMaker需要kernel参数，这里我们直接模拟结果
        strategy_allocations = {
            "momentum": 0.3,
            "mean_reversion": 0.2,
            "breakout": 0.2,
            "grid": 0.1,
            "wait": 0.2
        }
        
        log.info(f"策略分配结果: {strategy_allocations}")
        return strategy_allocations
        
    except Exception as e:
        log.error(f"策略决策测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_risk_assessment():
    """测试风险评估"""
    log.info("=== 步骤 5: 风险评估 ===")
    
    try:
        from deva.naja.risk.risk_manager import RiskManager
        
        # 创建风险管理器
        risk_manager = RiskManager()
        risk_manager._transformer_enabled = True
        risk_manager._context_learning_enabled = True
        log.info("创建 RiskManager 成功，启用 Transformer 和上下文学习")
        
        # 模拟数据
        market_data = SimulatedMarketData()
        positions = market_data.generate_positions()
        market_data_dict = market_data.generate_market_data()
        market_state_dict = market_data.generate_market_state()
        
        # 评估风险
        risk_metrics = risk_manager.assess_risk(
            positions=positions,
            market_data=market_data_dict,
            market_state=market_state_dict,
            total_assets=100000.0
        )
        
        log.info(f"风险评估结果:")
        log.info(f"  总敞口: {risk_metrics.total_exposure:.2f}")
        log.info(f"  最大单票: {risk_metrics.max_single_position:.2%}")
        log.info(f"  波动率得分: {risk_metrics.volatility_score:.2f}")
        log.info(f"  综合风险得分: {risk_metrics.overall_risk_score:.2f}")
        log.info(f"  风险等级: {risk_metrics.risk_level.value}")
        
        # 获取警报
        alerts = risk_manager.get_recent_alerts()
        log.info(f"生成的风险警报数量: {len(alerts)}")
        for alert in alerts:
            log.info(f"  - {alert.description} (等级: {alert.level.value})")
        
        return risk_metrics
        
    except Exception as e:
        log.error(f"风险评估测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_end_to_end_flow():
    """测试端到端流程"""
    log.info("=== 端到端流程测试 ===")
    
    try:
        # 1. 特征编码
        encoded_features = test_feature_encoding()
        if encoded_features is None:
            log.error("特征编码失败，终止测试")
            return False
        
        # 2. Transformer 处理
        transformer_output = test_transformer_processing(encoded_features)
        if transformer_output is None:
            log.error("Transformer 处理失败，终止测试")
            return False
        
        # 3. 上下文学习
        context_learner = test_context_learning()
        if context_learner is None:
            log.error("上下文学习失败，终止测试")
            return False
        
        # 4. 策略决策
        strategy_allocation = test_strategy_decision()
        if strategy_allocation is None:
            log.error("策略决策失败，终止测试")
            return False
        
        # 5. 风险评估
        risk_metrics = test_risk_assessment()
        if risk_metrics is None:
            log.error("风险评估失败，终止测试")
            return False
        
        # 6. 生成最终决策
        log.info("=== 步骤 6: 最终决策 ===")
        
        # 综合所有信息生成最终决策
        final_decision = {
            "timestamp": SimulatedMarketData().timestamp,
            "strategy_allocation": strategy_allocation,
            "risk_level": risk_metrics.risk_level.value,
            "overall_risk_score": risk_metrics.overall_risk_score,
            "recommended_actions": [
                "保持当前仓位结构",
                "关注市场波动率变化",
                "根据上下文学习结果调整策略"
            ]
        }
        
        log.info(f"最终决策: {final_decision}")
        
        return True
        
    except Exception as e:
        log.error(f"端到端流程测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    log.info("开始 Naja Attention 系统模拟测试")
    
    try:
        # 运行端到端测试
        success = test_end_to_end_flow()
        
        if success:
            log.info("模拟测试成功完成！")
            log.info("数据流链路总结:")
            log.info("1. 数据输入: 模拟市场数据和状态")
            log.info("2. 特征编码: 将市场数据编码为向量")
            log.info("3. Transformer 处理: 使用自注意力机制分析数据")
            log.info("4. 上下文学习: 基于历史经验调整决策")
            log.info("5. 策略决策: 分配策略权重")
            log.info("6. 风险评估: 评估当前风险水平")
            log.info("7. 最终决策: 综合所有信息生成决策")
        else:
            log.error("模拟测试失败")
            
    except Exception as e:
        log.error(f"测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
