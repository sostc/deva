#!/usr/bin/env python3
"""修复微观结构波动异常策略"""

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deva import NB

db = NB('naja_strategies')

for k in db.keys():
    data = db.get(k)
    if data and isinstance(data, dict):
        meta = data.get('metadata', {})
        name = meta.get('name', '')
        
        if '微观结构波动异常' in name:
            func_code = data.get('func_code', '')
            
            # 查找 return {  "signal":
            pattern = r'(return\s*\{\s*)("signal":\s*"microstructure[^"]*"[^}]*\})'
            
            def add_fields(m):
                prefix = m.group(1)
                signal_part = m.group(2)
                
                bandit_fields = ''',
        "signal_type": "BUY",
        "stock_code": picks[0].get("code") if picks else "",
        "stock_name": picks[0].get("name") if picks else "",
        "price": float(picks[0].get("price", 0)) if picks else 0,
        "confidence": min(1.0, picks[0].get("micro_vol_anomaly_score", 0) / 10.0) if picks else 0.5'''
                
                return prefix + signal_part + bandit_fields
            
            new_func_code = re.sub(pattern, add_fields, func_code, flags=re.DOTALL)
            
            if new_func_code != func_code:
                data['func_code'] = new_func_code
                db[k] = data
                print(f'已更新 {name}')
            else:
                print(f'未找到匹配模式 {name}')
                match = re.search(r'return\s*\{.*\}', func_code, re.DOTALL)
                if match:
                    print(f'return 内容: {match.group()[:300]}')
            break
