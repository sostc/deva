#!/usr/bin/env python3
"""
查看有df变量错误的策略代码
"""

from deva.naja.strategy import get_strategy_manager


def view_strategy_code(strategy_id, strategy_name):
    """
    查看策略代码
    """
    mgr = get_strategy_manager()
    mgr.load_from_db()
    
    entry = mgr.get(strategy_id)
    if not entry:
        print(f"Strategy with ID {strategy_id} not found.")
        return
    
    print(f"\n=== Strategy: {strategy_name} (ID: {strategy_id}) ===")
    print("\nCode:")
    print(entry._func_code)
    print("\n" + "="*80)


if __name__ == "__main__":
    # 有问题的策略列表
    error_strategies = [
        {"id": "7f964b5eca8f", "name": "sliding_window 测"},
        {"id": "8c0460c1c2f5", "name": "river_板块轮动图"},
        {"id": "bca643834222", "name": "river_板块热力图"},
        {"id": "124c2cd69d4c", "name": "quant_snapshot_5min_window"},
        {"id": "57ea083ef16a", "name": "测试下载目录监控"},
        {"id": "94ebeefcaed1", "name": "监控日志"}
    ]
    
    for strategy in error_strategies:
        view_strategy_code(strategy["id"], strategy["name"])
