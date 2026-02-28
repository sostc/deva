#!/usr/bin/env python3
"""
测试策略执行结果存储和查询
"""

import time
from deva.admin_ui.strategy.result_store import get_result_store


def test_result_store():
    """测试结果存储功能"""
    print("开始测试结果存储功能...")
    
    # 获取结果存储实例
    store = get_result_store()
    
    # 测试保存结果
    print("\n1. 测试保存结果")
    
    # 保存一些测试数据
    test_strategy_id = "test_strategy_123"
    test_strategy_name = "测试策略"
    
    for i in range(5):
        success = i % 2 == 0  # 交替成功和失败
        result = store.save(
            strategy_id=test_strategy_id,
            strategy_name=test_strategy_name,
            success=success,
            input_data=f"输入数据 {i}",
            output_data=f"输出数据 {i}" if success else None,
            process_time_ms=100 + i * 10,
            error=f"错误信息 {i}" if not success else "",
            persist=True
        )
        print(f"保存结果 {i+1}: ID={result.id}, 成功={result.success}")
        time.sleep(0.1)  # 确保时间戳不同
    
    # 测试获取最近结果
    print("\n2. 测试获取最近结果")
    recent_results = store.get_recent(test_strategy_id, limit=3)
    print(f"最近 {len(recent_results)} 条结果:")
    for i, r in enumerate(recent_results):
        print(f"  {i+1}. ID={r.id}, 成功={r.success}, 时间={r.ts}")
    
    # 测试查询功能
    print("\n3. 测试查询功能")
    
    # 查询所有结果
    all_results = store.query(strategy_id=test_strategy_id)
    print(f"查询到 {len(all_results)} 条结果")
    for i, r in enumerate(all_results):
        print(f"  {i+1}. ID={r.id}, 成功={r.success}, 时间={r.ts}")
    
    # 测试时间范围查询
    print("\n4. 测试时间范围查询")
    start_time = time.time() - 60  # 1分钟前
    time_results = store.query(strategy_id=test_strategy_id, start_ts=start_time)
    print(f"时间范围内查询到 {len(time_results)} 条结果")
    
    # 测试成功过滤
    print("\n5. 测试成功过滤")
    success_results = store.query(strategy_id=test_strategy_id, success_only=True)
    print(f"成功的结果: {len(success_results)} 条")
    
    # 测试获取统计信息
    print("\n6. 测试获取统计信息")
    stats = store.get_stats(strategy_id=test_strategy_id)
    print("统计信息:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # 测试导出功能
    print("\n7. 测试导出功能")
    export_data = store.export_results(strategy_id=test_strategy_id, format="json")
    print(f"导出的JSON数据长度: {len(export_data)} 字符")
    
    # 清理测试数据
    print("\n8. 清理测试数据")
    store.clear_db(strategy_id=test_strategy_id)
    store.clear_cache(strategy_id=test_strategy_id)
    
    # 验证清理
    after_clear = store.query(strategy_id=test_strategy_id)
    print(f"清理后查询到 {len(after_clear)} 条结果")
    
    print("\n测试完成！")


if __name__ == "__main__":
    test_result_store()
