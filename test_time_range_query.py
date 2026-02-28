#!/usr/bin/env python3
"""
测试时间范围查询功能
"""

import time
from deva.admin_ui.strategy.strategy_manager import get_manager


def test_time_range_query():
    """测试时间范围查询功能"""
    print("开始测试时间范围查询功能...")
    
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
        name="测试时间范围查询",
        processor_code=test_code,
        description="用于测试时间范围查询",
        tags=["test", "time"]
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
    start_result = manager.start(unit_id)
    if not start_result.get("success"):
        print(f"启动策略失败: {start_result.get('error')}")
        return
    print("策略启动成功")
    
    # 等待策略启动
    time.sleep(1)
    
    # 执行处理
    test_data = [1, 2, 3]
    print(f"测试数据: {test_data}")
    
    # 记录当前时间
    current_time = time.time()
    print(f"当前时间: {current_time}")
    
    # 执行多次处理
    for i in range(3):
        result = unit.process(test_data)
        print(f"第{i+1}次处理结果: {result}")
        time.sleep(0.5)
    
    # 测试不同时间范围的查询
    print("\n测试不同时间范围的查询")
    
    # 测试1: 1分钟内
    print("\n1. 测试1分钟内的查询")
    start_time_1min = time.time() - 60
    results_1min = manager.query_results(unit_id=unit_id, start_ts=start_time_1min)
    print(f"1分钟内查询到 {len(results_1min)} 条结果")
    
    # 测试2: 10秒内
    print("\n2. 测试10秒内的查询")
    start_time_10sec = time.time() - 10
    results_10sec = manager.query_results(unit_id=unit_id, start_ts=start_time_10sec)
    print(f"10秒内查询到 {len(results_10sec)} 条结果")
    
    # 测试3: 1小时内
    print("\n3. 测试1小时内的查询")
    start_time_1hour = time.time() - 3600
    results_1hour = manager.query_results(unit_id=unit_id, start_ts=start_time_1hour)
    print(f"1小时内查询到 {len(results_1hour)} 条结果")
    
    # 测试4: 全部结果
    print("\n4. 测试查询全部结果")
    results_all = manager.query_results(unit_id=unit_id)
    print(f"查询到 {len(results_all)} 条结果")
    
    # 打印结果详情
    print("\n结果详情:")
    for i, r in enumerate(results_all):
        print(f"  {i+1}. 时间戳: {r.get('ts')}, 可读时间: {r.get('ts_readable')}")
        print(f"     与当前时间的差值: {current_time - r.get('ts'):.2f} 秒")
    
    # 清理测试策略
    delete_result = manager.delete(unit_id, force=True)
    if delete_result.get("success"):
        print("测试策略删除成功")
    else:
        print(f"测试策略删除失败: {delete_result.get('error')}")
    
    print("\n测试完成！")


if __name__ == "__main__":
    test_time_range_query()
