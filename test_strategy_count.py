#!/usr/bin/env python3
"""
测试策略处理计数逻辑
"""

import time
from deva.admin_ui.strategy.strategy_manager import get_manager


def test_process_count():
    """测试策略处理计数逻辑"""
    print("开始测试策略处理计数逻辑...")
    
    # 获取策略管理器
    manager = get_manager()
    
    # 创建一个测试策略
    test_code = '''
def process(data):
    """测试处理函数"""
    return data
'''
    
    # 创建策略
    create_result = manager.create_strategy(
        name="测试策略",
        processor_code=test_code,
        description="用于测试处理计数逻辑的策略",
        tags=["test", "count"]
    )
    
    if not create_result.get("success"):
        print(f"创建策略失败: {create_result.get('error')}")
        return
    
    unit_id = create_result.get("unit_id")
    print(f"创建策略成功，ID: {unit_id}")
    
    # 获取策略实例
    unit = manager.get_unit(unit_id)
    if not unit:
        print("获取策略实例失败")
        return
    
    # 记录初始计数
    initial_count = unit.state.processed_count
    print(f"初始处理计数: {initial_count}")
    
    # 启动策略
    start_result = manager.start(unit_id)
    if not start_result.get("success"):
        print(f"启动策略失败: {start_result.get('error')}")
        return
    print("策略启动成功")
    
    # 等待策略启动
    time.sleep(1)
    
    # 测试处理数据
    test_data = [1, 2, 3, 4, 5]
    print(f"测试数据: {test_data}")
    
    # 执行多次处理
    for i in range(5):
        result = unit.process(test_data)
        print(f"第{i+1}次处理结果: {result}")
        time.sleep(0.1)
    
    # 检查处理计数
    final_count = unit.state.processed_count
    expected_count = initial_count + 5
    print(f"最终处理计数: {final_count}")
    print(f"期望处理计数: {expected_count}")
    
    if final_count == expected_count:
        print("✅ 处理计数逻辑正常工作！")
    else:
        print("❌ 处理计数逻辑异常！")
    
    # 检查最后处理时间戳
    last_process_ts = unit.state.last_process_ts
    if last_process_ts > 0:
        print(f"最后处理时间戳: {last_process_ts} ({time.ctime(last_process_ts)})")
    else:
        print("❌ 最后处理时间戳异常！")
    
    # 停止策略
    stop_result = manager.stop(unit_id)
    if not stop_result.get("success"):
        print(f"停止策略失败: {stop_result.get('error')}")
    else:
        print("策略停止成功")
    
    # 再次检查计数（应该不变）
    after_stop_count = unit.state.processed_count
    print(f"停止后处理计数: {after_stop_count}")
    
    if after_stop_count == final_count:
        print("✅ 停止后计数保持不变，逻辑正常！")
    else:
        print("❌ 停止后计数异常变化！")
    
    # 清理测试策略
    delete_result = manager.delete(unit_id, force=True)
    if delete_result.get("success"):
        print("测试策略删除成功")
    else:
        print(f"测试策略删除失败: {delete_result.get('error')}")
    
    print("测试完成！")


if __name__ == "__main__":
    test_process_count()
