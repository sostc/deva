#!/usr/bin/env python3
"""
启动注意力策略系统示例脚本

在 naja 环境中运行此脚本启动注意力策略
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

# 1. 首先启动注意力系统
from deva.naja.attention_integration import initialize_attention_system
from deva.naja.attention_orchestrator import initialize_orchestrator

print("="*60)
print("🚀 启动 Naja 注意力策略系统")
print("="*60)

# 初始化注意力系统
print("\n📊 初始化注意力系统...")
attention_system = initialize_attention_system()

# 初始化调度中心
print("📡 初始化调度中心...")
orchestrator = initialize_orchestrator()

# 2. 启动注意力策略
print("\n🎯 初始化注意力策略...")
try:
    from naja_attention_strategies import setup_attention_strategies
    manager = setup_attention_strategies()
    
    print("\n✅ 注意力策略系统启动完成!")
    print("-"*60)
    
    # 显示策略列表
    stats = manager.get_all_stats()
    print(f"\n📋 已加载策略 ({stats['active_strategies']}/{stats['total_strategies']}):")
    
    for strategy_id, strategy_stats in stats['strategy_stats'].items():
        status = "🟢" if strategy_stats['enabled'] else "🔴"
        print(f"   {status} {strategy_stats['name']} (优先级: {strategy_stats['priority']})")
    
    print("\n" + "="*60)
    print("💡 提示: 策略现在会自动处理市场数据")
    print("💡 使用 manager.get_all_stats() 查看运行状态")
    print("="*60)
    
except ImportError as e:
    print(f"\n❌ 导入失败: {e}")
    print("请确保 naja_attention_strategies 包已正确安装")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ 启动失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


# 保持运行
if __name__ == "__main__":
    print("\n按 Ctrl+C 停止...")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 停止策略系统...")
        manager.stop()
        print("✅ 已停止")
