#!/usr/bin/env python3
"""
检查naja策略数据库中哪些策略的执行函数包含admin_ui
"""

from deva import NB

# 策略表名
STRATEGY_TABLE = "naja_strategies"


def check_strategies_with_admin_ui():
    """检查策略执行函数是否包含admin_ui"""
    print("开始检查策略...")
    print("=" * 80)
    
    # 连接到策略数据库
    db = NB(STRATEGY_TABLE)
    
    # 统计信息
    total_strategies = 0
    strategies_with_admin_ui = []
    
    # 遍历所有策略
    for strategy_id, strategy_data in db.items():
        total_strategies += 1
        
        # 提取策略名称和执行代码
        if isinstance(strategy_data, dict):
            metadata = strategy_data.get('metadata', {})
            strategy_name = metadata.get('name', '未知策略')
            func_code = strategy_data.get('func_code', '')
            
            # 检查是否包含admin_ui
            if 'admin_ui' in func_code:
                strategies_with_admin_ui.append({
                    'id': strategy_id,
                    'name': strategy_name,
                    'code_snippets': []
                })
                
                # 提取包含admin_ui的代码行
                lines = func_code.split('\n')
                for i, line in enumerate(lines):
                    if 'admin_ui' in line:
                        strategies_with_admin_ui[-1]['code_snippets'].append({
                            'line': i + 1,
                            'content': line.strip()
                        })
    
    # 输出结果
    print(f"总策略数: {total_strategies}")
    print(f"包含admin_ui的策略数: {len(strategies_with_admin_ui)}")
    print("=" * 80)
    
    if strategies_with_admin_ui:
        print("包含admin_ui的策略:")
        print("-" * 80)
        
        for strategy in strategies_with_admin_ui:
            print(f"策略ID: {strategy['id']}")
            print(f"策略名称: {strategy['name']}")
            print("包含admin_ui的代码行:")
            for snippet in strategy['code_snippets']:
                print(f"  第{snippet['line']}行: {snippet['content']}")
            print("-" * 80)
    else:
        print("没有发现包含admin_ui的策略")
    
    print("检查完成！")


if __name__ == "__main__":
    check_strategies_with_admin_ui()
