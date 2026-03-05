#!/usr/bin/env python3
"""
清理测试策略
"""

from deva.naja.strategy import get_strategy_manager


def cleanup_test_strategies():
    """清理所有测试策略"""
    mgr = get_strategy_manager()
    
    entries = mgr.list_all()
    deleted_count = 0
    
    for entry in entries:
        if entry.name.startswith("test_strategy_"):
            mgr.delete(entry.id)
            deleted_count += 1
            print(f"Deleted test strategy: {entry.name} (ID: {entry.id})")
    
    print(f"\nCleanup completed. Deleted {deleted_count} test strategies.")


if __name__ == "__main__":
    cleanup_test_strategies()
