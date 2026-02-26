#!/usr/bin/env python
# coding: utf-8
"""
测试策略状态持久化和恢复功能
"""

from deva.admin_ui.strategy.strategy_unit import StrategyUnit, StrategyStatus
from deva.admin_ui.strategy.strategy_manager import get_manager
import time
import os
import sys

# 测试策略处理器函数
def test_strategy_processor(data):
    """测试策略处理器"""
    print(f"[测试策略] 处理数据: {data}")
    return {"processed": data, "timestamp": time.time()}

def test_strategy_persistence():
    """测试策略状态持久化和恢复"""
    print("=== 测试策略状态持久化和恢复 ===")
    
    # 获取策略管理器
    manager = get_manager()
    
    # 清除现有测试策略
    for unit in list(manager._items.values()):
        if unit.name == "测试策略":
            unit.delete()
    
    # 创建测试策略
    print("1. 创建测试策略...")
    strategy = StrategyUnit(
        name="测试策略",
        description="测试状态持久化的策略",
        processor_func=test_strategy_processor
    )
    
    # 注册策略
    result = manager.register(strategy)
    print(f"注册结果: {result}")
    
    # 启动策略
    print("2. 启动测试策略...")
    start_result = strategy.start()
    print(f"启动结果: {start_result}")
    print(f"策略状态: {strategy.status}")
    
    # 模拟处理数据
    print("3. 模拟处理数据...")
    test_data = {"test": "data", "value": 123}
    result = strategy.process(test_data)
    print(f"处理结果: {result}")
    print(f"处理计数: {strategy.state.processed_count}")
    
    # 保存策略状态
    print("4. 保存策略状态...")
    save_result = strategy.save()
    print(f"保存结果: {save_result}")
    
    # 模拟系统重启 - 清除管理器中的策略
    print("5. 模拟系统重启...")
    manager._items.clear()
    
    # 重新加载策略
    print("6. 重新加载策略...")
    load_count = manager.load_from_db()
    print(f"加载策略数量: {load_count}")
    
    # 恢复运行状态
    print("7. 恢复运行状态...")
    restore_result = manager.restore_running_states()
    print(f"恢复结果: {restore_result}")
    
    # 验证策略状态
    print("8. 验证策略状态...")
    restored_strategy = manager.get_unit_by_name("测试策略")
    if restored_strategy:
        print(f"找到恢复的策略: {restored_strategy.name}")
        print(f"策略状态: {restored_strategy.status}")
        print(f"处理计数: {restored_strategy.state.processed_count}")
        
        # 再次处理数据验证功能
        print("9. 验证策略功能...")
        test_data2 = {"test": "data2", "value": 456}
        result2 = restored_strategy.process(test_data2)
        print(f"处理结果: {result2}")
        print(f"处理计数: {restored_strategy.state.processed_count}")
        
        print("\n✅ 测试策略状态持久化和恢复成功！")
    else:
        print("❌ 未能找到恢复的策略")

if __name__ == "__main__":
    test_strategy_persistence()
