#!/usr/bin/env python3
"""
查看策略代码
"""

from deva.naja.strategy import get_strategy_manager


def view_strategy_code(strategy_id):
    """查看策略代码"""
    mgr = get_strategy_manager()
    mgr.load_from_db()
    
    entry = mgr.get(strategy_id)
    if not entry:
        print(f"Strategy with ID {strategy_id} not found.")
        return
    
    print(f"Strategy: {entry.name}")
    print(f"ID: {entry.id}")
    print("\nCode:")
    print(entry._func_code)


if __name__ == "__main__":
    # 查看第一个策略的代码
    mgr = get_strategy_manager()
    mgr.load_from_db()
    entries = mgr.list_all()
    if entries:
        view_strategy_code(entries[0].id)
    else:
        print("No strategies found.")
