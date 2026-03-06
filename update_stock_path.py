#!/usr/bin/env python3
"""
更新策略代码中的Stock导入路径
"""

from deva import NB

# 策略表名
STRATEGY_TABLE = "naja_strategies"


def update_stock_import_path():
    """更新所有策略中的Stock导入路径"""
    print("开始更新策略中的Stock导入路径...")
    print("=" * 80)
    
    # 连接到策略数据库
    db = NB(STRATEGY_TABLE)
    
    # 统计信息
    total_strategies = 0
    updated_strategies = 0
    
    # 遍历所有策略
    for strategy_id, strategy_data in db.items():
        total_strategies += 1
        
        # 提取策略名称和执行代码
        if isinstance(strategy_data, dict):
            metadata = strategy_data.get('metadata', {})
            strategy_name = metadata.get('name', '未知策略')
            func_code = strategy_data.get('func_code', '')
            
            # 检查是否需要更新
            if 'from deva.admin_ui.stock.stock import Stock' in func_code:
                # 更新导入路径
                updated_code = func_code.replace(
                    'from deva.admin_ui.stock.stock import Stock',
                    'from deva.naja.dictionary.stock.stock import Stock'
                )
                
                # 保存更新后的代码
                strategy_data['func_code'] = updated_code
                db[strategy_id] = strategy_data
                
                updated_strategies += 1
                print(f"已更新策略: {strategy_name} (ID: {strategy_id})")
    
    # 输出结果
    print("=" * 80)
    print(f"总策略数: {total_strategies}")
    print(f"已更新策略数: {updated_strategies}")
    print("=" * 80)
    
    if updated_strategies > 0:
        print("更新成功！")
    else:
        print("没有需要更新的策略。")


if __name__ == "__main__":
    update_stock_import_path()
