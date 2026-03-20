#!/usr/bin/env python3
"""
检查运行中的 Naja 实例状态
"""

import os
import sys

# 设置环境变量
os.environ["NAJA_ATTENTION_ENABLED"] = "true"

def check_status():
    print("=" * 60)
    print("Naja 状态检查")
    print("=" * 60)
    
    # 1. 检查注意力集成
    print("\n1. 检查注意力集成...")
    try:
        from deva.naja.attention_integration import get_attention_integration
        integration = get_attention_integration()
        print(f"   集成实例: {integration}")
        print(f"   注意力系统: {integration.attention_system}")
        
        if integration.attention_system:
            print("   ✅ 注意力系统已初始化")
            report = integration.get_attention_report()
            print(f"   状态: {report}")
        else:
            print("   ❌ 注意力系统未初始化")
    except Exception as e:
        print(f"   ❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    # 2. 检查调度中心
    print("\n2. 检查调度中心...")
    try:
        from deva.naja.attention_orchestrator import get_orchestrator
        orchestrator = get_orchestrator()
        print(f"   调度中心: {orchestrator}")
        print(f"   处理帧数: {orchestrator._processed_frames}")
        print(f"   注册数据源: {list(orchestrator._datasources.keys())}")
    except Exception as e:
        print(f"   ❌ 错误: {e}")
    
    # 3. 检查历史追踪器
    print("\n3. 检查历史追踪器...")
    try:
        from deva.naja.attention.history_tracker import get_history_tracker
        tracker = get_history_tracker()
        summary = tracker.get_summary()
        print(f"   追踪器: {tracker}")
        print(f"   快照数: {summary['snapshot_count']}")
        print(f"   变化数: {summary['change_count']}")
    except Exception as e:
        print(f"   ❌ 错误: {e}")
    
    # 4. 检查策略管理器
    print("\n4. 检查策略管理器...")
    try:
        from naja_attention_strategies import get_strategy_manager
        manager = get_strategy_manager()
        stats = manager.get_all_stats()
        print(f"   管理器: {manager}")
        print(f"   运行中: {stats['is_running']}")
        print(f"   策略数: {stats['total_strategies']}")
    except Exception as e:
        print(f"   ❌ 错误: {e}")
    
    # 5. 尝试手动初始化注意力系统
    print("\n5. 尝试手动初始化注意力系统...")
    try:
        from deva.naja.attention_config import load_config
        from deva.naja.attention_integration import initialize_attention_system
        
        config = load_config()
        print(f"   配置 enabled: {config.enabled}")
        
        if config.enabled:
            attention_system = initialize_attention_system(config)
            print(f"   ✅ 注意力系统初始化成功: {attention_system}")
        else:
            print("   ⚠️ 注意力系统被禁用")
    except Exception as e:
        print(f"   ❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    check_status()
