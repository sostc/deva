#!/usr/bin/env python
# coding: utf-8
"""
测试不同函数名的策略恢复
"""

from deva.admin_ui.strategy.strategy_unit import StrategyUnit, StrategyStatus
from deva.admin_ui.strategy.strategy_manager import get_manager
from deva import NB
import time
import os
import sys

# 测试不同函数名的处理器
def custom_processor(data):
    """自定义处理器函数 - 使用不同的函数名"""
    print(f"[自定义处理器] 执行代码：处理数据 - {data}")
    return {"result": data, "processed_by": "custom_processor"}

def another_strategy(data):
    """另一个策略函数 - 使用不同的函数名"""
    print(f"[另一个策略] 执行代码：处理数据 - {data}")
    return {"result": data, "processed_by": "another_strategy"}

def test_strategy_function_names():
    """测试不同函数名的策略恢复"""
    print("=== 测试不同函数名的策略恢复 ===")
    
    # 获取策略管理器
    manager = get_manager()
    
    # 测试策略1：使用 custom_processor 函数名
    test_strategy_name1 = f"测试策略_custom_{int(time.time())}"
    print(f"\n1. 测试策略1: {test_strategy_name1} (函数名: custom_processor)")
    
    # 创建测试策略1
    strategy1 = StrategyUnit(
        name=test_strategy_name1,
        description="测试不同函数名的策略",
        processor_func=custom_processor
    )
    
    # 注册和启动
    result = manager.register(strategy1)
    print(f"注册结果: {result}")
    start_result = strategy1.start()
    print(f"启动结果: {start_result}")
    
    # 测试执行
    test_data1 = {"test": "data1", "value": 123}
    result1 = strategy1.process(test_data1)
    print(f"处理结果: {result1}")
    
    # 保存策略
    save_result1 = strategy1.save()
    print(f"保存结果: {save_result1}")
    
    # 测试策略2：使用 another_strategy 函数名
    test_strategy_name2 = f"测试策略_another_{int(time.time())}"
    print(f"\n2. 测试策略2: {test_strategy_name2} (函数名: another_strategy)")
    
    # 创建测试策略2
    strategy2 = StrategyUnit(
        name=test_strategy_name2,
        description="测试不同函数名的策略",
        processor_func=another_strategy
    )
    
    # 注册和启动
    result = manager.register(strategy2)
    print(f"注册结果: {result}")
    start_result = strategy2.start()
    print(f"启动结果: {start_result}")
    
    # 测试执行
    test_data2 = {"test": "data2", "value": 456}
    result2 = strategy2.process(test_data2)
    print(f"处理结果: {result2}")
    
    # 保存策略
    save_result2 = strategy2.save()
    print(f"保存结果: {save_result2}")
    
    # 模拟系统重启
    print("\n3. 模拟系统重启...")
    manager._items.clear()
    print(f"重启后策略数量: {len(manager._items)}")
    
    # 重新加载策略
    print("4. 重新加载策略...")
    load_count = manager.load_from_db()
    print(f"加载策略数量: {load_count}")
    
    # 恢复运行状态
    print("5. 恢复运行状态...")
    restore_result = manager.restore_running_states()
    print(f"恢复结果: {restore_result}")
    
    # 验证策略1
    print(f"\n6. 验证策略1: {test_strategy_name1}")
    restored_strategy1 = None
    for unit in manager._items.values():
        if unit.name == test_strategy_name1:
            restored_strategy1 = unit
            print(f"找到策略: {unit.name}")
            print(f"状态: {unit.status}")
            print(f"处理器函数: {unit._processor_func}")
            print(f"处理器代码: {unit._processor_code}")
            
            # 测试执行
            test_data3 = {"test": "data3", "value": 789}
            result3 = unit.process(test_data3)
            print(f"恢复后执行结果: {result3}")
            break
    
    # 验证策略2
    print(f"\n7. 验证策略2: {test_strategy_name2}")
    restored_strategy2 = None
    for unit in manager._items.values():
        if unit.name == test_strategy_name2:
            restored_strategy2 = unit
            print(f"找到策略: {unit.name}")
            print(f"状态: {unit.status}")
            print(f"处理器函数: {unit._processor_func}")
            print(f"处理器代码: {unit._processor_code}")
            
            # 测试执行
            test_data4 = {"test": "data4", "value": 987}
            result4 = unit.process(test_data4)
            print(f"恢复后执行结果: {result4}")
            break
    
    if restored_strategy1 and restored_strategy2:
        print("\n✅ 所有策略都成功恢复并执行！")
    else:
        print("\n❌ 部分策略恢复失败！")

if __name__ == "__main__":
    test_strategy_function_names()
