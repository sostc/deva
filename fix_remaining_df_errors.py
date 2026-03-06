#!/usr/bin/env python3
"""
修复剩余的df变量错误
"""

from deva.naja.strategy import get_strategy_manager


def fix_remaining_df_errors():
    """
    修复剩余的df变量错误
    """
    mgr = get_strategy_manager()
    mgr.load_from_db()
    
    # 需要修复的策略列表
    strategies_to_fix = [
        {"id": "8c0460c1c2f5", "name": "river_板块轮动图"},
        {"id": "bca643834222", "name": "river_板块热力图"}
    ]
    
    fixed_count = 0
    failed_count = 0
    
    print(f"Fixing {len(strategies_to_fix)} strategies with df variable errors...")
    
    for strategy in strategies_to_fix:
        entry = mgr.get(strategy["id"])
        if not entry:
            print(f"Strategy {strategy['name']} (ID: {strategy['id']}) not found, skipped.")
            failed_count += 1
            continue
        
        print(f"\nFixing strategy: {strategy['name']} (ID: {strategy['id']})")
        
        # 获取原始代码
        code = entry._func_code
        
        # 将df变量替换为data
        new_code = code.replace("isinstance(df, pd.DataFrame)", "isinstance(data, pd.DataFrame)")
        new_code = new_code.replace("if not df.empty:", "if not data.empty:")
        new_code = new_code.replace("df = df.copy()", "data = data.copy()")
        new_code = new_code.replace("for idx, row in df.iterrows():", "for idx, row in data.iterrows():")
        new_code = new_code.replace("df = df[valid_mask]", "data = data[valid_mask]")
        new_code = new_code.replace("if df.empty:", "if data.empty:")
        
        # 更新策略代码
        result = entry.update_config(func_code=new_code)
        if result.get('success'):
            print(f"✓ Fixed successfully")
            fixed_count += 1
        else:
            print(f"✗ Fix failed: {result.get('error')}")
            failed_count += 1
    
    print(f"\nSummary: Fixed {fixed_count} strategies, failed {failed_count}")


if __name__ == "__main__":
    fix_remaining_df_errors()
