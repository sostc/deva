#!/usr/bin/env python3
"""更新策略数据库中的策略输出格式，支持 bandit"""

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deva import NB

def update_strategy_output():
    db = NB('naja_strategies')
    
    strategies_to_update = []
    
    for k in db.keys():
        data = db.get(k)
        if data and isinstance(data, dict):
            meta = data.get('metadata', {})
            name = meta.get('name', '')
            
            # 找出需要更新的策略
            if any(keyword in name for keyword in [
                '短期方向概率', 
                '订单流失衡', 
                '量价盘口异常',
                '微观结构波动',
                '交易行为痕迹'
            ]):
                strategies_to_update.append({
                    'key': k,
                    'name': name,
                    'func_code': data.get('func_code', '')
                })
    
    print(f"找到 {len(strategies_to_update)} 个需要更新的策略")
    
    for strategy in strategies_to_update:
        name = strategy['name']
        func_code = strategy['func_code']
        key = strategy['key']
        
        print(f"\n处理策略: {name}")
        
        # 查找 return 语句
        pattern = r'(return\s*\{[^}]*"signal":\s*"[^"]*"[^}]*\})'
        
        def add_bandit_fields(match):
            original = match.group(1)
            
            # 检查是否已经有 stock_code 字段
            if 'stock_code' in original:
                print(f"  - 已有 stock_code，跳过")
                return original
            
            # 在 return 语句中添加 bandit 字段
            # 需要找到 "signal": "xxx" 后面的位置插入
            new_return = original.rstrip()
            
            # 添加 bandit 相关字段
            # 我们需要在 return 语句中添加这些字段
            # 由于不知道具体的 picks 结构，我们使用占位符
            
            # 在 "signal": "xxx" 后面添加 bandit 字段
            if '"signal":' in original:
                # 找到 signal 字段的位置
                signal_match = re.search(r'("signal":\s*"[^"]*")', original)
                if signal_match:
                    insert_pos = signal_match.end()
                    
                    # 添加 bandit 字段
                    bandit_fields = ''',
        "signal_type": "BUY",
        "stock_code": signals[0].get("code") if signals else "",
        "stock_name": signals[0].get("name") if signals else "",
        "price": float(signals[0].get("price", 0)) if signals else 0,
        "confidence": float(signals[0].get("up_probability", 0.5)) if signals else 0.5'''
                    
                    new_return = original[:insert_pos] + bandit_fields + original[insert_pos:]
                    print(f"  - 已添加 bandit 字段")
                    return new_return
            
            print(f"  - 无法找到插入位置")
            return original
        
        # 尝试匹配并替换
        new_func_code = re.sub(pattern, add_bandit_fields, func_code, flags=re.DOTALL)
        
        if new_func_code != func_code:
            # 保存更新后的策略
            data = db.get(key)
            data['func_code'] = new_func_code
            db[key] = data
            print(f"  - 已保存更新")
        else:
            print(f"  - 未找到匹配的 return 语句")

    print("\n更新完成")

if __name__ == '__main__':
    update_strategy_output()
