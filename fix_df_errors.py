#!/usr/bin/env python3
"""
修复策略代码中的df变量错误
"""

from deva.naja.strategy import get_strategy_manager


def fix_df_errors():
    """
    修复策略代码中的df变量错误
    """
    mgr = get_strategy_manager()
    mgr.load_from_db()
    
    # 有问题的策略列表
    error_strategies = [
        {"id": "7f964b5eca8f", "name": "sliding_window 测"},
        {"id": "8c0460c1c2f5", "name": "river_板块轮动图"},
        {"id": "bca643834222", "name": "river_板块热力图"},
        {"id": "124c2cd69d4c", "name": "quant_snapshot_5min_window"},
        {"id": "57ea083ef16a", "name": "测试下载目录监控"},
        {"id": "94ebeefcaed1", "name": "监控日志"}
    ]
    
    fixed_count = 0
    failed_count = 0
    
    print(f"Fixing {len(error_strategies)} strategies with df variable errors...")
    
    for strategy in error_strategies:
        entry = mgr.get(strategy["id"])
        if not entry:
            print(f"Strategy {strategy['name']} (ID: {strategy['id']}) not found, skipped.")
            failed_count += 1
            continue
        
        print(f"\nFixing strategy: {strategy['name']} (ID: {strategy['id']})")
        
        # 获取原始代码
        code = entry._func_code
        
        # 找到重复的过滤逻辑并移除
        # 第一次过滤逻辑是正确的（使用data变量）
        # 第二次过滤逻辑是错误的（使用df变量）
        
        # 找到第一次过滤逻辑的结束位置
        first_filter_end = code.find("# 处理字典类型的输入（单条数据）")
        if first_filter_end != -1:
            # 找到第一次过滤逻辑的完整结束
            first_filter_end = code.find("\n\n", first_filter_end)
            if first_filter_end != -1:
                # 找到第二次过滤逻辑的开始位置
                second_filter_start = code.find("# 过滤非个股数据", first_filter_end)
                if second_filter_start != -1:
                    # 找到第二次过滤逻辑的结束位置
                    second_filter_end = code.find("\n\n", second_filter_start)
                    if second_filter_end != -1:
                        # 移除第二次过滤逻辑
                        new_code = code[:first_filter_end] + code[second_filter_end:]
                        
                        # 更新策略代码
                        result = entry.update_config(func_code=new_code)
                        if result.get('success'):
                            print(f"✓ Fixed successfully")
                            fixed_count += 1
                        else:
                            print(f"✗ Fix failed: {result.get('error')}")
                            failed_count += 1
                    else:
                        print(f"✗ Could not find end of second filter logic")
                        failed_count += 1
                else:
                    print(f"✗ Could not find second filter logic")
                    failed_count += 1
            else:
                print(f"✗ Could not find end of first filter logic")
                failed_count += 1
        else:
            print(f"✗ Could not find first filter logic")
            failed_count += 1
    
    print(f"\nSummary: Fixed {fixed_count} strategies, failed {failed_count}")


if __name__ == "__main__":
    fix_df_errors()
