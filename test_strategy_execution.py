#!/usr/bin/env python3
"""
测试策略执行和结果存储
"""

import time
from deva.admin_ui.strategy.strategy_manager import get_manager


def test_strategy_execution():
    """测试策略执行和结果存储"""
    print("开始测试策略执行和结果存储...")
    
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
        name="测试策略执行",
        processor_code=test_code,
        description="用于测试策略执行和结果存储",
        tags=["test", "execution"]
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
    
    # 执行多次处理
    test_data = [1, 2, 3, 4, 5]
    print(f"测试数据: {test_data}")
    
    for i in range(3):
        result = unit.process(test_data)
        print(f"第{i+1}次处理结果: {result}")
        time.sleep(0.5)
    
    # 检查处理计数
    print(f"处理计数: {unit.state.processed_count}")
    
    # 测试查询执行历史
    print("\n测试查询执行历史")
    
    # 直接使用result_store查询
    from deva.admin_ui.strategy.result_store import get_result_store
    store = get_result_store()
    
    # 查询结果
    results = store.query(strategy_id=unit_id)
    print(f"查询到 {len(results)} 条执行结果")
    
    for i, r in enumerate(results):
        print(f"  {i+1}. 时间: {r.ts}, 成功: {r.success}, 耗时: {r.process_time_ms:.1f}ms")
        print(f"     输入: {r.input_preview}")
        print(f"     输出: {r.output_preview}")
    
    # 测试通过manager查询
    print("\n通过manager查询执行历史")
    manager_results = manager.query_results(unit_id=unit_id)
    print(f"查询到 {len(manager_results)} 条执行结果")
    
    for i, r in enumerate(manager_results):
        print(f"  {i+1}. 时间: {r.get('ts')}, 成功: {r.get('success')}, 耗时: {r.get('process_time_ms', 0):.1f}ms")
    
    # 测试时间范围查询
    print("\n测试时间范围查询")
    start_time = time.time() - 60  # 1分钟前
    time_results = manager.query_results(unit_id=unit_id, start_ts=start_time)
    print(f"时间范围内查询到 {len(time_results)} 条结果")
    
    # 清理测试策略
    delete_result = manager.delete(unit_id, force=True)
    if delete_result.get("success"):
        print("测试策略删除成功")
    else:
        print(f"测试策略删除失败: {delete_result.get('error')}")
    
    print("\n测试完成！")


if __name__ == "__main__":
    test_strategy_execution()
