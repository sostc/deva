#!/usr/bin/env python3
"""手动更新微观结构波动异常策略"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deva import NB

def update_micro_strategy():
    db = NB('naja_strategies')
    
    for k in db.keys():
        data = db.get(k)
        if data and isinstance(data, dict):
            meta = data.get('metadata', {})
            name = meta.get('name', '')
            
            if '微观结构波动' in name:
                print(f"找到策略: {name}")
                
                func_code = data.get('func_code', '')
                
                # 直接在 return 语句中添加 bandit 字段
                # 查找 return { 后面包含 "signal" 的那一行
                lines = func_code.split('\n')
                new_lines = []
                
                for i, line in enumerate(lines):
                    new_lines.append(line)
                    
                    # 找到 return { 后面几行
                    if '"signal":' in line and 'microstructure' in line.lower():
                        # 在 "signal": "xxx" 后面添加 bandit 字段
                        indent = ' ' * 8  # 保持缩进
                        bandit_fields = f'{indent}"signal_type": "BUY",\n{indent}"stock_code": picks[0].get("code") if picks else "",\n{indent}"stock_name": picks[0].get("name") if picks else "",\n{indent}"price": float(picks[0].get("price", 0)) if picks else 0,\n{indent}"confidence": min(1.0, picks[0].get("micro_vol_anomaly_score", 0) / 10.0) if picks else 0.5,'
                        
                        # 在下一行插入（当前行已经是 "signal": "xxx"）
                        new_lines.append(bandit_fields)
                        print(f"已添加 bandit 字段")
                
                new_func_code = '\n'.join(new_lines)
                
                if new_func_code != func_code:
                    data['func_code'] = new_func_code
                    db[k] = data
                    print(f"已保存更新")
                else:
                    print(f"未找到插入位置")
                
                break

if __name__ == '__main__':
    update_micro_strategy()
