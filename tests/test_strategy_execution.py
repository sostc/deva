#!/usr/bin/env python
# coding: utf-8
"""
测试策略恢复后代码执行情况
"""

from deva.admin_ui.strategy.strategy_unit import StrategyUnit, StrategyStatus
from deva.admin_ui.strategy.strategy_manager import get_manager
from deva import NB, NS
import time
import os
import sys

# 测试策略处理器函数，包含日志输出
def test_strategy_execution(data):
    """测试策略处理器 - 验证代码执行"""
    print(f"[测试策略] 执行代码：处理数据 - {data}")
    print(f"[测试策略] 数据类型: {type(data)}")
    print(f"[测试策略] 数据内容: {data}")
    
    # 模拟复杂处理逻辑
    result = {
        "processed_data": data,
        "timestamp": time.time(),
        "processed_by": "test_strategy_execution",
        "status": "success"
    }
    
    print(f"[测试策略] 处理结果: {result}")
    return result

def test_strategy_execution_restore():
    """测试策略恢复后代码执行"""
    print("=== 测试策略恢复后代码执行 ===")
    
    # 获取策略管理器
    manager = get_manager()
    
    # 生成唯一的策略名称
    test_strategy_name = f"测试执行策略_{int(time.time())}"
    
    # 清除现有测试策略
    for unit in list(manager._items.values()):
        if unit.name.startswith("测试执行策略_"):
            unit.delete()
    
    # 创建测试策略
    print(f"1. 创建测试策略: {test_strategy_name}...")
    strategy = StrategyUnit(
        name=test_strategy_name,
        description="测试恢复后代码执行的策略",
        processor_func=test_strategy_execution
    )
    
    # 注册策略
    result = manager.register(strategy)
    print(f"注册结果: {result}")
    print(f"策略ID: {strategy._id}")
    
    # 启动策略
    print("2. 启动测试策略...")
    start_result = strategy.start()
    print(f"启动结果: {start_result}")
    print(f"策略状态: {strategy.status}")
    
    # 模拟处理数据，验证代码执行
    print("3. 测试代码执行...")
    test_data = {"test": "data", "value": 123, "timestamp": time.time()}
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
    print(f"保存的处理器代码长度: {len(saved_data.get('processor_code', ''))}")
    print(f"保存的状态: {saved_data.get('state', {})}")
    
    # 模拟系统重启 - 清除管理器中的策略
    print("6. 模拟系统重启...")
    manager._items.clear()
    print(f"重启后策略数量: {len(manager._items)}")
    
    # 重新加载策略
    print("7. 重新加载策略...")
    load_count = manager.load_from_db()
    print(f"加载策略数量: {load_count}")
    
    # 恢复运行状态
    print("8. 恢复运行状态...")
    restore_result = manager.restore_running_states()
    print(f"恢复结果: {restore_result}")
    
    # 验证策略状态
    print("9. 验证策略状态...")
    restored_strategy = None
    for unit_id, unit in manager._items.items():
        if unit.name == test_strategy_name:
            restored_strategy = unit
            print(f"找到恢复的策略: {unit.name}")
            print(f"策略状态: {unit.status}")
            print(f"处理器函数: {unit._processor_func}")
            print(f"处理计数: {unit.state.processed_count}")
            break
    
    if restored_strategy:
        # 测试恢复后代码执行
        print("10. 测试恢复后代码执行...")
        test_data2 = {"test": "data2", "value": 456, "timestamp": time.time()}
        print(f"输入数据: {test_data2}")
        result2 = restored_strategy.process(test_data2)
        print(f"处理结果: {result2}")
        print(f"处理计数: {restored_strategy.state.processed_count}")
        
        # 验证处理计数是否增加
        if restored_strategy.state.processed_count > 0:
            print("\n✅ 策略恢复后代码执行成功！")
        else:
            print("\n❌ 策略恢复后代码未执行！")
    else:
        print("\n❌ 未能找到恢复的策略")

if __name__ == "__main__":
    test_strategy_execution_restore()
