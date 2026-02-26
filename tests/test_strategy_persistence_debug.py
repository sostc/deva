#!/usr/bin/env python
# coding: utf-8
"""
调试策略状态持久化和恢复功能
"""

from deva.admin_ui.strategy.strategy_unit import StrategyUnit, StrategyStatus
from deva.admin_ui.strategy.strategy_manager import get_manager
from deva import NB
import time
import os
import sys

# 测试策略处理器函数
def test_strategy_processor(data):
    """测试策略处理器"""
    print(f"[测试策略] 处理数据: {data}")
    return {"processed": data, "timestamp": time.time()}

def test_strategy_persistence_debug():
    """调试策略状态持久化和恢复"""
    print("=== 调试策略状态持久化和恢复 ===")
    
    # 获取策略管理器
    manager = get_manager()
    
    # 生成唯一的策略名称
    test_strategy_name = f"测试策略_{int(time.time())}"
    
    # 清除现有测试策略
    for unit in list(manager._items.values()):
        if unit.name.startswith("测试策略_"):
            unit.delete()
    
    # 创建测试策略
    print(f"1. 创建测试策略: {test_strategy_name}...")
    strategy = StrategyUnit(
        name=test_strategy_name,
        description="测试状态持久化的策略",
        processor_func=test_strategy_processor
    )
    
    # 注册策略
    result = manager.register(strategy)
    print(f"注册结果: {result}")
    print(f"策略ID: {strategy._id}")
    print(f"处理器代码: {strategy._processor_code}")
    
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
    
    # 检查数据库中的数据
    print("5. 检查数据库中的数据...")
    db = NB("strategy_units")
    saved_data = db.get(strategy._id)
    print(f"数据库中保存的数据: {list(saved_data.keys())}")
    print(f"保存的metadata: {saved_data.get('metadata', {})}")
    print(f"保存的状态: {saved_data.get('state', {})}")
    print(f"保存的处理器代码: {saved_data.get('processor_code', '')}")
    
    # 模拟系统重启 - 清除管理器中的策略
    print("6. 模拟系统重启...")
    manager._items.clear()
    
    # 重新加载策略
    print("7. 重新加载策略...")
    load_count = manager.load_from_db()
    print(f"加载策略数量: {load_count}")
    
    # 检查加载的策略
    print("8. 检查加载的策略...")
    loaded_strategy = None
    for unit_id, unit in manager._items.items():
        if unit.name == test_strategy_name:
            print(f"找到测试策略: {unit.name}")
            print(f"策略ID: {unit._id}")
            print(f"状态: {unit.state.status}")
            print(f"_was_running: {getattr(unit, '_was_running', False)}")
            print(f"处理器函数: {unit._processor_func}")
            print(f"处理器代码: {unit._processor_code}")
            print(f"处理计数: {unit.state.processed_count}")
            loaded_strategy = unit
    
    # 恢复运行状态
    print("9. 恢复运行状态...")
    restore_result = manager.restore_running_states()
    print(f"恢复结果: {restore_result}")
    
    # 再次检查策略
    print("10. 再次检查策略...")
    for unit_id, unit in manager._items.items():
        if unit.name == test_strategy_name:
            print(f"找到测试策略: {unit.name}")
            print(f"状态: {unit.state.status}")
            print(f"处理器函数: {unit._processor_func}")
            print(f"处理计数: {unit.state.processed_count}")
            
            # 尝试手动设置处理器
            print("11. 尝试手动设置处理器...")
            try:
                if unit._processor_code:
                    unit.set_processor_from_code(unit._processor_code, func_name="test_strategy_processor")
                    print("手动设置处理器成功")
                    print(f"处理器函数: {unit._processor_func}")
                    
                    # 测试处理数据
                    test_data2 = {"test": "data2", "value": 456}
                    result2 = unit.process(test_data2)
                    print(f"处理结果: {result2}")
                    print(f"处理计数: {unit.state.processed_count}")
            except Exception as e:
                print(f"手动设置处理器失败: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    test_strategy_persistence_debug()
