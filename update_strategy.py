#!/usr/bin/env python3
"""
更新策略代码，修复admin_ui导入路径
"""

from deva import NB

# 策略表名
STRATEGY_TABLE = "naja_strategies"


def update_strategy(strategy_id):
    """更新策略代码，修复admin_ui导入路径"""
    print(f"更新策略 {strategy_id}...")
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
        
        # 检查是否需要更新
        if 'from deva.admin_ui.strategy.data import Stock' in func_code:
            # 更新导入路径
            updated_code = func_code.replace(
                'from deva.admin_ui.strategy.data import Stock',
                'from deva.admin_ui.stock.stock import Stock'
            )
            
            # 保存更新后的代码
            strategy_data['func_code'] = updated_code
            db[strategy_id] = strategy_data
            
            print("\n已更新导入路径:")
            print("- 旧: from deva.admin_ui.strategy.data import Stock")
            print("- 新: from deva.admin_ui.stock.stock import Stock")
            print("\n更新成功！")
        else:
            print("\n策略代码中没有需要更新的导入路径。")
    else:
        print(f"策略 {strategy_id} 不存在")


if __name__ == "__main__":
    # 更新之前发现的包含admin_ui的策略
    update_strategy("32c7943b4f85")
