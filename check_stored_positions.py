#!/usr/bin/env python3
"""查看数据库中已同步的富途持仓数据"""

import sys
import os
from deva import NB

def check_positions():
    print("=== 检查富途持仓数据 ===")
    
    # 检查统一持仓表
    nb = NB("naja_bandit_positions")
    print("\n--- 统一持仓表 ---")
    accounts_data = nb.get("accounts", {})
    print(f"账户数据键: {list(accounts_data.keys())}")
    
    for acc_name, acc_data in accounts_data.items():
        print(f"\n账户: {acc_name}")
        print(f"  账户类型: {acc_data.get('account_type', 'unknown')}")
        print(f"  净资产: {acc_data.get('equity', 0)}")
        positions = acc_data.get('positions', {})
        print(f"  持仓数量: {len(positions)}")
        
        for pos_id, pos in positions.items():
            print(f"\n  持仓ID: {pos_id}")
            print(f"    股票代码: {pos.get('stock_code')}")
            print(f"    股票名称: {pos.get('stock_name')}")
            print(f"    数量: {pos.get('quantity')}")
            print(f"    入场价: {pos.get('entry_price')}")
            print(f"    现价: {pos.get('current_price')}")
            print(f"    完整数据: {pos}")
    
    # 检查富途账户表
    print("\n--- 富途账户表 ---")
    nb_futu = NB("naja_bandit_futu_accounts")
    print(f"富途账户数据: {dict(nb_futu)}")
    
    return 0

if __name__ == "__main__":
    sys.exit(check_positions())
