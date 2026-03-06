#!/usr/bin/env python3
"""
查看指定策略的完整代码
"""

from deva import NB

# 策略表名
STRATEGY_TABLE = "naja_strategies"


def view_strategy(strategy_id):
    """查看指定策略的完整代码"""
    print(f"查看策略 {strategy_id} 的完整代码...")
    print("=" * 80)
    
    # 连接到策略数据库
    db = NB(STRATEGY_TABLE)
    
    # 获取策略数据
    strategy_data = db.get(strategy_id)
    
    if strategy_data and isinstance(strategy_data, dict):
        metadata = strategy_data.get('metadata', {})
        strategy_name = metadata.get('name', '未知策略')
        func_code = strategy_data.get('func_code', '')
        
        print(f"策略ID: {strategy_id}")
        print(f"策略名称: {strategy_name}")
        print("\n执行代码:")
        print("-" * 80)
        print(func_code)
        print("-" * 80)
    else:
        print(f"策略 {strategy_id} 不存在")


if __name__ == "__main__":
    # 查看之前发现的包含admin_ui的策略
    view_strategy("32c7943b4f85")
