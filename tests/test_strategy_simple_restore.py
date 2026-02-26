#!/usr/bin/env python
# coding: utf-8
"""
测试策略简单恢复功能
"""

from deva.admin_ui.strategy.strategy_unit import StrategyUnit, StrategyStatus
from deva.admin_ui.strategy.strategy_manager import get_manager
from deva import NB
import time
import os
import sys

# 测试策略处理器
def test_strategy_processor(data):
    """测试策略处理器"""
    print(f"[测试策略] 执行代码：处理数据 - {data}")
    return {"result": data, "processed": True}

def test_strategy_simple_restore():
    """测试策略简单恢复功能"""
    print("=== 测试策略简单恢复功能 ===")
    
    # 1. 获取策略管理器
    manager = get_manager()
    
    # 2. 准备测试策略
    test_strategy_name = f"测试简单恢复_{int(time.time())}"
    print(f"1. 准备测试策略: {test_strategy_name}")
    
    # 3. 清除现有测试策略
    for unit in list(manager._items.values()):
        if unit.name.startswith("测试简单恢复_"):
            unit.delete()
    
    # 4. 创建测试策略
    print("2. 创建测试策略...")
    strategy = StrategyUnit(
        name=test_strategy_name,
        description="测试简单恢复功能的策略",
        processor_func=test_strategy_processor
    )
    
    # 5. 注册策略
    result = manager.register(strategy)
    print(f"注册结果: {result}")
    
    # 6. 启动策略
    print("3. 启动策略...")
    start_result = strategy.start()
    print(f"启动结果: {start_result}")
    print(f"策略状态: {strategy.status}")
    
    # 7. 测试执行
    print("4. 测试策略执行...")
    test_data = {"test": "data", "value": 123}
    result = strategy.process(test_data)
    print(f"处理结果: {result}")
    print(f"处理计数: {strategy.state.processed_count}")
    
    # 8. 保存策略状态
    print("5. 保存策略状态...")
    save_result = strategy.save()
    print(f"保存结果: {save_result}")
    
    # 9. 检查数据库
    print("6. 检查数据库中的策略...")
    db = NB("strategy_units")
    saved_strategy = db.get(strategy._id)
    if saved_strategy:
        print(f"策略已保存到数据库")
        print(f"保存的状态: {saved_strategy.get('state', {})}")
        print(f"保存的处理器代码长度: {len(saved_strategy.get('processor_code', ''))}")
    else:
        print("策略未保存到数据库")
    
    # 10. 模拟系统重启
    print("\n7. 模拟系统重启...")
    print(f"重启前策略数量: {len(manager._items)}")
    
    # 清除所有策略
    manager._items.clear()
    print(f"清除后策略数量: {len(manager._items)}")
    
    # 11. 重新加载策略
    print("8. 重新加载策略...")
    load_count = manager.load_from_db()
    print(f"加载策略数量: {load_count}")
    
    # 12. 恢复运行状态
    print("9. 恢复运行状态...")
    restore_result = manager.restore_running_states()
    print(f"恢复结果: {restore_result}")
    
    # 13. 检查恢复后的策略
    print("10. 检查恢复后的策略...")
    print(f"恢复后策略数量: {len(manager._items)}")
    
    restored_strategy = None
    for unit in manager._items.values():
        if unit.name == test_strategy_name:
            restored_strategy = unit
            print(f"找到恢复的策略: {unit.name}")
            print(f"策略ID: {unit._id}")
            print(f"状态: {unit.status}")
            print(f"处理器函数: {unit._processor_func}")
            print(f"处理器代码长度: {len(unit._processor_code)}")
            print(f"处理计数: {unit.state.processed_count}")
            break
    
    # 14. 测试恢复后执行
    if restored_strategy:
        print("\n11. 测试恢复后策略执行...")
        test_data2 = {"test": "data2", "value": 456}
        print(f"输入数据: {test_data2}")
        result2 = restored_strategy.process(test_data2)
        print(f"处理结果: {result2}")
        print(f"处理计数: {restored_strategy.state.processed_count}")
        
        # 15. 验证状态
        print("\n12. 验证策略状态...")
        if restored_strategy.status == StrategyStatus.RUNNING:
            print("✅ 策略状态正确: RUNNING")
        else:
            print(f"❌ 策略状态错误: {restored_strategy.status}")
        
        if restored_strategy._processor_func:
            print("✅ 处理器函数已恢复")
        else:
            print("❌ 处理器函数未恢复")
        
        if restored_strategy.state.processed_count > 0:
            print("✅ 处理计数正确")
        else:
            print("❌ 处理计数错误")
        
        print("\n✅ 策略简单恢复测试完成！")
    else:
        print("\n❌ 策略未恢复！")

if __name__ == "__main__":
    test_strategy_simple_restore()
