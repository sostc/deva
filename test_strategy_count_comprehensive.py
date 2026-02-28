#!/usr/bin/env python3
"""
全面测试策略处理计数逻辑
"""

import time
from deva.admin_ui.strategy.strategy_manager import get_manager


def test_restart_count():
    """测试策略重启后的计数恢复"""
    print("\n=== 测试策略重启后的计数恢复 ===")
    
    manager = get_manager()
    
    test_code = '''
def process(data):
    """测试处理函数"""
    return data
'''
    
    # 创建策略
    create_result = manager.create_strategy(
        name="重启测试策略",
        processor_code=test_code,
        description="用于测试重启后计数恢复的策略",
        tags=["test", "restart"]
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
    
    # 启动策略
    manager.start(unit_id)
    print("策略启动成功")
    
    # 执行处理
    test_data = [1, 2, 3]
    for i in range(3):
        unit.process(test_data)
        time.sleep(0.1)
    
    first_count = unit.state.processed_count
    print(f"第一次运行后计数: {first_count}")
    
    # 停止策略
    manager.stop(unit_id)
    print("策略停止成功")
    
    # 重新启动策略
    manager.start(unit_id)
    print("策略重新启动成功")
    
    # 再次执行处理
    for i in range(2):
        unit.process(test_data)
        time.sleep(0.1)
    
    final_count = unit.state.processed_count
    expected_count = first_count + 2
    print(f"最终计数: {final_count}")
    print(f"期望计数: {expected_count}")
    
    if final_count == expected_count:
        print("✅ 策略重启后计数正确恢复！")
    else:
        print("❌ 策略重启后计数异常！")
    
    # 清理
    manager.delete(unit_id, force=True)
    print("测试策略删除成功")


def test_error_count():
    """测试错误情况下的计数行为"""
    print("\n=== 测试错误情况下的计数行为 ===")
    
    manager = get_manager()
    
    # 创建会抛出异常的策略
    error_code = '''
def process(data):
    """测试错误处理函数"""
    if data == "error":
        raise Exception("测试错误")
    return data
'''
    
    create_result = manager.create_strategy(
        name="错误测试策略",
        processor_code=error_code,
        description="用于测试错误情况下的计数行为",
        tags=["test", "error"]
    )
    
    if not create_result.get("success"):
        print(f"创建策略失败: {create_result.get('error')}")
        return
    
    unit_id = create_result.get("unit_id")
    unit = manager.get_unit(unit_id)
    
    # 启动策略
    manager.start(unit_id)
    
    # 执行正常处理
    unit.process("normal")
    normal_count = unit.state.processed_count
    print(f"正常处理后计数: {normal_count}")
    
    # 执行错误处理
    try:
        unit.process("error")
    except Exception:
        pass
    
    error_count = unit.state.processed_count
    print(f"错误处理后计数: {error_count}")
    
    if error_count == normal_count:
        print("✅ 错误情况下计数不变，逻辑正确！")
    else:
        print("❌ 错误情况下计数异常变化！")
    
    # 清理
    manager.delete(unit_id, force=True)
    print("测试策略删除成功")


def test_long_running_count():
    """测试长时间运行的计数累积"""
    print("\n=== 测试长时间运行的计数累积 ===")
    
    manager = get_manager()
    
    test_code = '''
def process(data):
    """测试处理函数"""
    return data
'''
    
    create_result = manager.create_strategy(
        name="长运行测试策略",
        processor_code=test_code,
        description="用于测试长时间运行的计数累积",
        tags=["test", "long"]
    )
    
    if not create_result.get("success"):
        print(f"创建策略失败: {create_result.get('error')}")
        return
    
    unit_id = create_result.get("unit_id")
    unit = manager.get_unit(unit_id)
    
    # 启动策略
    manager.start(unit_id)
    
    # 执行多次处理
    test_data = [1]
    total_processes = 100
    
    start_time = time.time()
    for i in range(total_processes):
        unit.process(test_data)
        if (i + 1) % 20 == 0:
            current_count = unit.state.processed_count
            print(f"已处理 {i+1} 次，当前计数: {current_count}")
    end_time = time.time()
    
    final_count = unit.state.processed_count
    print(f"\n总处理次数: {total_processes}")
    print(f"最终计数: {final_count}")
    print(f"处理时间: {end_time - start_time:.2f} 秒")
    
    if final_count == total_processes:
        print("✅ 长时间运行计数累积正确！")
    else:
        print("❌ 长时间运行计数累积异常！")
    
    # 清理
    manager.delete(unit_id, force=True)
    print("测试策略删除成功")


def main():
    """运行所有测试"""
    print("开始全面测试策略处理计数逻辑...")
    
    test_restart_count()
    test_error_count()
    test_long_running_count()
    
    print("\n所有测试完成！")


if __name__ == "__main__":
    main()
