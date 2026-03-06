#!/usr/bin/env python3
"""
列出所有策略
"""

from deva.naja.strategy import get_strategy_manager


def list_strategies():
    """列出所有策略"""
    mgr = get_strategy_manager()
    
    mgr.load_from_db()
    
    entries = mgr.list_all()
    
    if not entries:
        print("No strategies found.")
        return
    
    print(f"Found {len(entries)} strategies:\n")
    
    for entry in entries:
        print(f"Strategy: {entry.name}")
        print(f"ID: {entry.id}")
        print(f"Code length: {len(entry._func_code)}")
        print("-" * 50)


if __name__ == "__main__":
    list_strategies()
