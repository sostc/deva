#!/usr/bin/env python3
"""
查看修复失败的策略代码
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
    # 修复失败的策略列表
    failed_strategies = [
        {"id": "8c0460c1c2f5", "name": "river_板块轮动图"},
        {"id": "bca643834222", "name": "river_板块热力图"}
    ]
    
    for strategy in failed_strategies:
        view_strategy_code(strategy["id"], strategy["name"])
