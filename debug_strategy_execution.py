#!/usr/bin/env python3
"""
调试策略执行
"""

import time
from deva.naja.strategy import get_strategy_manager


def main():
    """主函数"""
    # 获取策略管理器
    st_mgr = get_strategy_manager()
    
    # 加载数据
    st_mgr.load_from_db()
    
    # 查找 river 策略
    river_strategies = [s for s in st_mgr.list_all() if 'river' in s.name.lower()]
    
    # 选择一个策略进行调试
    if river_strategies:
        strategy = river_strategies[0]
        print(f"调试策略: {strategy.name} (ID: {strategy.id})")
        print(f"当前状态: 运行中={strategy.is_running}")
        
        # 启动策略
        print("\n启动策略...")
        start_result = strategy.start()
        print(f"启动结果: {start_result}")
        print(f"启动后状态: 运行中={strategy.is_running}")
        
        # 等待一段时间
        print("\n等待 5 秒...")
        time.sleep(5)
        
        # 检查状态
        print(f"5秒后状态: 运行中={strategy.is_running}")
        
        # 检查最近的执行结果
        recent_results = strategy.get_recent_results(limit=5)
        print(f"\n最近执行结果: {len(recent_results)} 条")
        for i, result in enumerate(recent_results):
            print(f"  {i+1}. 时间: {result.get('timestamp')}, 成功: {result.get('success')}, 错误: {result.get('error')}")
        
        # 检查策略状态
        print(f"\n策略状态:")
        print(f"  处理计数: {strategy._state.processed_count}")
        print(f"  输出计数: {strategy._state.output_count}")
        print(f"  最后处理时间: {strategy._state.last_process_ts}")
        print(f"  错误计数: {len(strategy._state.errors)}")
        if strategy._state.errors:
            print(f"  最近错误: {strategy._state.errors[-1]}")


if __name__ == "__main__":
    main()
