#!/usr/bin/env python3
"""
中期集成测试

验证Transformer和上下文学习在协调层和UI层的集成
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
from deva.naja.attention.orchestration.cognition_orchestrator import get_cognition_orchestrator
from deva.naja.attention.orchestration.trading_center import get_trading_center
from deva.naja.attention.ui.dashboard import get_attention_monitor_data


def test_cognition_orchestrator_integration():
    """测试CognitionOrchestrator的集成"""
    print("=" * 80)
    print("测试 CognitionOrchestrator 集成")
    print("=" * 80)
    
    try:
        # 获取CognitionOrchestrator实例
        orchestrator = get_cognition_orchestrator()
        print("✓ 获取 CognitionOrchestrator 实例成功")
        
        # 获取认知上下文
        context = orchestrator._get_cognition_context()
        print("✓ 获取认知上下文成功")
        
        # 检查上下文学习信息是否存在
        if "in_context_learning" in context:
            print("✓ 上下文学习信息已集成到认知上下文")
            print(f"  - 启用状态: {context['in_context_learning'].get('enabled', False)}")
            print(f"  - 示范统计: {context['in_context_learning'].get('demo_statistics', {})}")
        else:
            print("✗ 上下文学习信息未集成到认知上下文")
        
        return True
        
    except Exception as e:
        print(f"✗ CognitionOrchestrator 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_trading_center_integration():
    """测试TradingCenter的集成"""
    print("\n" + "=" * 80)
    print("测试 TradingCenter 集成")
    print("=" * 80)
    
    try:
        # 获取TradingCenter实例
        trading_center = get_trading_center()
        print("✓ 获取 TradingCenter 实例成功")
        
        # 测试快速决策
        market_state = {
            "symbol_weights": {
                "NVDA": 0.8,
                "AMD": 0.7,
                "MSFT": 0.9
            },
            "block_hotspot": {
                "AI": 0.9
            }
        }
        
        result = trading_center.make_decision(market_state)
        print("✓ 快速决策测试成功")
        print(f"  - 行动类型: {result.action_type}")
        print(f"  - 和谐强度: {result.harmony_strength:.4f}")
        print(f"  - 融合置信度: {result.fused_confidence:.4f}")
        
        return True
        
    except Exception as e:
        print(f"✗ TradingCenter 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_dashboard_integration():
    """测试Dashboard的集成"""
    print("\n" + "=" * 80)
    print("测试 Dashboard 集成")
    print("=" * 80)
    
    try:
        # 获取监控数据
        data = get_attention_monitor_data()
        print("✓ 获取监控数据成功")
        
        # 检查Transformer自注意力信息是否存在
        if "transformer_attention" in data:
            print("✓ Transformer自注意力信息已集成到Dashboard")
            print(f"  - 启用状态: {data['transformer_attention'].get('enabled', False)}")
            print(f"  - 可用状态: {data['transformer_attention'].get('available', False)}")
            print(f"  - 配置: {data['transformer_attention'].get('config', {})}")
        else:
            print("✗ Transformer自注意力信息未集成到Dashboard")
        
        # 检查上下文学习信息是否存在
        if "in_context_learning" in data:
            print("✓ 上下文学习信息已集成到Dashboard")
            print(f"  - 启用状态: {data['in_context_learning'].get('enabled', False)}")
            print(f"  - 可用状态: {data['in_context_learning'].get('available', False)}")
            print(f"  - 示范统计: {data['in_context_learning'].get('demo_statistics', {})}")
        else:
            print("✗ 上下文学习信息未集成到Dashboard")
        
        return True
        
    except Exception as e:
        print(f"✗ Dashboard 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("开始中期集成测试...")
    print("=" * 80)
    
    # 测试CognitionOrchestrator集成
    cog_success = test_cognition_orchestrator_integration()
    
    # 测试TradingCenter集成
    tc_success = test_trading_center_integration()
    
    # 测试Dashboard集成
    dash_success = test_dashboard_integration()
    
    print("\n" + "=" * 80)
    print("中期集成测试总结果:")
    print(f"CognitionOrchestrator 集成: {'成功' if cog_success else '失败'}")
    print(f"TradingCenter 集成: {'成功' if tc_success else '失败'}")
    print(f"Dashboard 集成: {'成功' if dash_success else '失败'}")
    print("=" * 80)
    
    return cog_success and tc_success and dash_success


if __name__ == "__main__":
    main()
