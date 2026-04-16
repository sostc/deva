"""
测试 RiskManager 模块的 Transformer 和上下文学习集成

验证风险管理器是否能够正确集成 Transformer 和上下文学习功能
"""

import sys
import os
import logging
from typing import Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deva.naja.risk.risk_manager import RiskManager, RiskMetrics

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)


def test_risk_manager_transformer_integration():
    """测试 RiskManager 的 Transformer 集成"""
    log.info("开始测试 RiskManager Transformer 集成")
    
    # 创建 RiskManager 实例
    risk_manager = RiskManager()
    
    # 启用 Transformer 和上下文学习
    risk_manager._transformer_enabled = True
    risk_manager._context_learning_enabled = True
    
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
        },
        "GOOGL": {
            "quantity": 20,
            "cost": 2800.0,
            "current_price": 2850.0
        }
    }
    
    # 模拟市场数据
    market_data = {
        "market_volatility": 1.8,
        "liquidity_score": 0.75,
        "total_assets": 100000.0
    }
    
    # 模拟市场状态
    market_state = {
        "trend_strength": 0.6,
        "market_breadth": 0.4
    }
    
    # 总资产
    total_assets = 100000.0
    
    # 日盈亏
    daily_pnl = 0.02
    
    # 评估风险
    risk_metrics = risk_manager.assess_risk(
        positions=positions,
        market_data=market_data,
        market_state=market_state,
        total_assets=total_assets,
        daily_pnl=daily_pnl
    )
    
    # 打印风险评估结果
    log.info(f"风险评估结果:")
    log.info(f"总敞口: {risk_metrics.total_exposure:.2f}")
    log.info(f"最大单票: {risk_metrics.max_single_position:.2%}")
    log.info(f"波动率得分: {risk_metrics.volatility_score:.2f}")
    log.info(f"流动性得分: {risk_metrics.liquidity_score:.2f}")
    log.info(f"综合风险得分: {risk_metrics.overall_risk_score:.2f}")
    log.info(f"风险等级: {risk_metrics.risk_level.value}")
    
    # 获取最近警报
    recent_alerts = risk_manager.get_recent_alerts()
    log.info(f"最近警报数量: {len(recent_alerts)}")
    for alert in recent_alerts:
        log.info(f"警报: {alert.description} - 等级: {alert.level.value}")
    
    # 获取警报摘要
    alert_summary = risk_manager.get_alert_summary()
    log.info(f"警报摘要: {alert_summary}")
    
    log.info("RiskManager Transformer 集成测试完成")


def test_risk_manager_without_transformer():
    """测试 RiskManager 禁用 Transformer 的情况"""
    log.info("开始测试 RiskManager 禁用 Transformer 的情况")
    
    # 创建 RiskManager 实例
    risk_manager = RiskManager()
    
    # 禁用 Transformer 和上下文学习
    risk_manager._transformer_enabled = False
    risk_manager._context_learning_enabled = False
    
    # 模拟持仓数据
    positions = {
        "AAPL": {
            "quantity": 100,
            "cost": 150.0,
            "current_price": 155.0
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
    
    # 总资产
    total_assets = 50000.0
    
    # 评估风险
    risk_metrics = risk_manager.assess_risk(
        positions=positions,
        market_data=market_data,
        market_state=market_state,
        total_assets=total_assets
    )
    
    # 打印风险评估结果
    log.info(f"风险评估结果 (禁用 Transformer):")
    log.info(f"综合风险得分: {risk_metrics.overall_risk_score:.2f}")
    log.info(f"风险等级: {risk_metrics.risk_level.value}")
    
    log.info("RiskManager 禁用 Transformer 测试完成")


def test_risk_manager_high_volatility():
    """测试高波动率情况下的风险评估"""
    log.info("开始测试高波动率情况下的风险评估")
    
    # 创建 RiskManager 实例
    risk_manager = RiskManager()
    
    # 启用 Transformer 和上下文学习
    risk_manager._transformer_enabled = True
    risk_manager._context_learning_enabled = True
    
    # 模拟持仓数据
    positions = {
        "TSLA": {
            "quantity": 50,
            "cost": 700.0,
            "current_price": 720.0
        }
    }
    
    # 模拟高波动率市场数据
    market_data = {
        "market_volatility": 2.8,  # 高波动率
        "liquidity_score": 0.6,
        "total_assets": 50000.0
    }
    
    # 模拟市场状态
    market_state = {
        "trend_strength": 0.9,  # 强趋势
        "market_breadth": 0.7  # 极端广度
    }
    
    # 总资产
    total_assets = 50000.0
    
    # 评估风险
    risk_metrics = risk_manager.assess_risk(
        positions=positions,
        market_data=market_data,
        market_state=market_state,
        total_assets=total_assets
    )
    
    # 打印风险评估结果
    log.info(f"高波动率风险评估结果:")
    log.info(f"综合风险得分: {risk_metrics.overall_risk_score:.2f}")
    log.info(f"风险等级: {risk_metrics.risk_level.value}")
    
    # 获取最近警报
    recent_alerts = risk_manager.get_recent_alerts()
    log.info(f"高波动率情况下的警报数量: {len(recent_alerts)}")
    for alert in recent_alerts:
        log.info(f"警报: {alert.description} - 等级: {alert.level.value}")
    
    log.info("高波动率风险评估测试完成")


if __name__ == "__main__":
    log.info("开始 RiskManager Transformer 集成测试")
    
    try:
        test_risk_manager_transformer_integration()
        print("\n" + "="*50 + "\n")
        test_risk_manager_without_transformer()
        print("\n" + "="*50 + "\n")
        test_risk_manager_high_volatility()
        log.info("所有测试完成")
    except Exception as e:
        log.error(f"测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
