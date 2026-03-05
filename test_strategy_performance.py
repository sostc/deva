#!/usr/bin/env python3
"""
测试StrategyManager的list_all性能优化
"""

import time
import random
from deva.naja.strategy import get_strategy_manager
from deva.naja.strategy.result_store import get_result_store


def generate_test_strategies(count=100):
    """生成测试策略"""
    mgr = get_strategy_manager()
    created_strategies = []
    
    # 生成新策略
    for i in range(count):
        strategy_name = f"test_strategy_perf_{i}"
        func_code = """
def process(data):
    return {'signal_type': 'test', 'value': data.get('value', 0)}
"""
        
        result = mgr.create(
            name=strategy_name,
            func_code=func_code,
            bound_datasource_id="",
            description=f"Test strategy for performance testing {i}"
        )
        
        if result.get("success"):
            created_strategies.append(strategy_name)
        
        if i % 10 == 0:
            print(f"Created {i}/{count} strategies")
    
    print(f"Generated {len(created_strategies)} test strategies")
    return created_strategies


def generate_test_results(strategy_count=100, results_per_strategy=50):
    """为每个策略生成测试结果"""
    mgr = get_strategy_manager()
    store = get_result_store()
    
    entries = mgr.list_all()
    
    for i, entry in enumerate(entries):
        for j in range(results_per_strategy):
            store.save(
                strategy_id=entry.id,
                strategy_name=entry.name,
                success=True,
                input_data={'value': random.randint(1, 100)},
                output_data={'signal_type': 'test', 'value': random.randint(1, 100)},
                process_time_ms=random.uniform(1, 100)
            )
        
        if i % 10 == 0:
            print(f"Generated results for {i}/{strategy_count} strategies")
    
    print(f"Generated {results_per_strategy} results per strategy")


def test_list_all_performance():
    """测试list_all方法的性能"""
    mgr = get_strategy_manager()
    
    start_time = time.time()
    entries = mgr.list_all()
    end_time = time.time()
    
    print(f"list_all() took {end_time - start_time:.4f} seconds")
    print(f"Retrieved {len(entries)} strategies")


def test_list_all_dict_performance():
    """测试list_all_dict方法的性能"""
    mgr = get_strategy_manager()
    
    start_time = time.time()
    entries = mgr.list_all_dict()
    end_time = time.time()
    
    print(f"list_all_dict() took {end_time - start_time:.4f} seconds")
    print(f"Retrieved {len(entries)} strategy dicts")


def test_get_recent_performance():
    """测试get_recent方法的性能"""
    mgr = get_strategy_manager()
    store = get_result_store()
    
    entries = mgr.list_all()
    
    start_time = time.time()
    total_results = 0
    for entry in entries:
        results = store.get_recent(entry.id, limit=10)
        total_results += len(results)
    end_time = time.time()
    
    print(f"get_recent() for all strategies took {end_time - start_time:.4f} seconds")
    print(f"Retrieved {total_results} total results")


def cleanup_test_strategies():
    """清理测试策略"""
    mgr = get_strategy_manager()
    deleted_count = 0
    
    for entry in mgr.list_all():
        if entry.name.startswith("test_strategy_perf_"):
            mgr.delete(entry.id)
            deleted_count += 1
    
    if deleted_count > 0:
        print(f"Cleaned up {deleted_count} test strategies")


def main():
    """主测试函数"""
    print("Testing StrategyManager performance...")
    print("=" * 50)
    
    try:
        # 生成测试数据
        print("1. Generating test strategies...")
        generate_test_strategies(100)
        
        print("2. Generating test results...")
        generate_test_results(100, 50)
        
        print("3. Testing performance...")
        print("-" * 50)
        
        test_list_all_performance()
        test_list_all_dict_performance()
        test_get_recent_performance()
        
        print("=" * 50)
        print("Performance test completed!")
    finally:
        # 清理测试数据
        print("\n4. Cleaning up test data...")
        cleanup_test_strategies()
        print("Cleanup completed!")


if __name__ == "__main__":
    main()
