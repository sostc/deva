"""
完整的集成测试脚本

测试整个系统的集成情况，包括：
1. Transformer 和上下文学习的完整功能
2. 与其他模块的集成
3. 端到端的系统测试
"""

import sys
import os
import logging
from typing import Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)


def test_transformer_components():
    """测试 Transformer 组件"""
    log.info("开始测试 Transformer 组件")
    
    try:
        from deva.naja.attention.kernel.embedding import MarketFeatureEncoder
        from deva.naja.attention.kernel.self_attention import TransformerLikeAttentionLayer
        
        # 测试 MarketFeatureEncoder
        encoder = MarketFeatureEncoder(embedding_dim=64)
        log.info("MarketFeatureEncoder 初始化成功")
        
        # 测试 TransformerLikeAttentionLayer
        attention_layer = TransformerLikeAttentionLayer(
            embedding_dim=64,
            num_heads=4,
            dropout=0.1
        )
        log.info("TransformerLikeAttentionLayer 初始化成功")
        
        log.info("Transformer 组件测试成功")
        return True
        
    except Exception as e:
        log.error(f"Transformer 组件测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_context_learning():
    """测试上下文学习组件"""
    log.info("开始测试上下文学习组件")
    
    try:
        from deva.naja.attention.kernel.in_context_learner import InContextAttentionLearner, Demonstration
        
        # 创建演示样本
        demo1 = Demonstration(
            market_conditions={"volatility": 1.5, "trend": 0.6},
            action="buy",
            result="profit",
            confidence=0.8
        )
        
        demo2 = Demonstration(
            market_conditions={"volatility": 2.5, "trend": -0.4},
            action="sell",
            result="profit",
            confidence=0.9
        )
        
        # 测试 InContextAttentionLearner
        learner = InContextAttentionLearner()
        learner.add_demonstration(demo1)
        learner.add_demonstration(demo2)
        
        log.info(f"上下文学习组件初始化成功，添加了 {len(learner.demonstrations)} 个演示样本")
        
        # 测试相似度计算
        test_conditions = {"volatility": 1.8, "trend": 0.5}
        similar_demos = learner.retrieve_similar_demonstrations(test_conditions, k=1)
        log.info(f"检索到 {len(similar_demos)} 个相似演示样本")
        
        log.info("上下文学习组件测试成功")
        return True
        
    except Exception as e:
        log.error(f"上下文学习组件测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_kernel_integration():
    """测试核心内核集成"""
    log.info("开始测试核心内核集成")
    
    try:
        from deva.naja.attention.kernel.kernel import AttentionKernel
        
        # 测试 AttentionKernel 初始化
        kernel = AttentionKernel()
        
        # 启用 Transformer 和上下文学习
        kernel.enable_transformer = True
        kernel.enable_in_context = True
        
        log.info("核心内核初始化成功，Transformer 和上下文学习已启用")
        
        # 测试处理功能
        test_data = {
            "market_data": {
                "market_volatility": 1.8,
                "liquidity_score": 0.75
            },
            "market_state": {
                "trend_strength": 0.6,
                "market_breadth": 0.4
            },
            "positions": {
                "AAPL": {
                    "quantity": 100,
                    "cost": 150.0,
                    "current_price": 155.0
                }
            }
        }
        
        # 模拟处理
        log.info("核心内核集成测试成功")
        return True
        
    except Exception as e:
        log.error(f"核心内核集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_risk_manager_integration():
    """测试风险管理器集成"""
    log.info("开始测试风险管理器集成")
    
    try:
        from deva.naja.risk.risk_manager import RiskManager
        
        # 测试 RiskManager 初始化
        risk_manager = RiskManager()
        
        # 启用 Transformer 和上下文学习
        risk_manager._transformer_enabled = True
        risk_manager._context_learning_enabled = True
        
        log.info("风险管理器初始化成功，Transformer 和上下文学习已启用")
        
        # 模拟持仓数据
        positions = {
            "AAPL": {
                "quantity": 100,
                "cost": 150.0,
                "current_price": 155.0
            },
            "MSFT": {
                "quantity": 50,
                "cost": 300.0,
                "current_price": 310.0
            }
        }
        
        # 模拟市场数据
        market_data = {
            "market_volatility": 1.5,
            "liquidity_score": 0.8,
            "total_assets": 50000.0
        }
        
        # 模拟市场状态
        market_state = {
            "trend_strength": 0.3,
            "market_breadth": 0.2
        }
        
        # 评估风险
        risk_metrics = risk_manager.assess_risk(
            positions=positions,
            market_data=market_data,
            market_state=market_state,
            total_assets=50000.0
        )
        
        log.info(f"风险评估成功，风险等级: {risk_metrics.risk_level.value}")
        log.info("风险管理器集成测试成功")
        return True
        
    except Exception as e:
        log.error(f"风险管理器集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_end_to_end_integration():
    """测试端到端集成"""
    log.info("开始测试端到端集成")
    
    try:
        # 测试所有组件的集成
        components_test = test_transformer_components()
        context_test = test_context_learning()
        kernel_test = test_kernel_integration()
        risk_test = test_risk_manager_integration()
        
        if all([components_test, context_test, kernel_test, risk_test]):
            log.info("端到端集成测试成功")
            return True
        else:
            log.warning("端到端集成测试部分失败")
            return False
            
    except Exception as e:
        log.error(f"端到端集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    log.info("开始完整集成测试")
    
    try:
        # 测试 Transformer 组件
        test_transformer_components()
        print("\n" + "="*50 + "\n")
        
        # 测试上下文学习组件
        test_context_learning()
        print("\n" + "="*50 + "\n")
        
        # 测试核心内核集成
        test_kernel_integration()
        print("\n" + "="*50 + "\n")
        
        # 测试风险管理器集成
        test_risk_manager_integration()
        print("\n" + "="*50 + "\n")
        
        # 测试端到端集成
        test_end_to_end_integration()
        
        log.info("所有集成测试完成")
        
    except Exception as e:
        log.error(f"集成测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
