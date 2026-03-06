#!/usr/bin/env python3
"""
批量更新策略代码，添加股票过滤逻辑
"""

from deva.naja.strategy import get_strategy_manager


def add_stock_filter(code):
    """
    向策略代码添加股票过滤逻辑
    """
    # 检查代码是否已经包含过滤逻辑
    if "is_valid_stock" in code:
        return code, False
    
    # 过滤函数
    filter_function = '''
import pandas as pd

def is_valid_stock(code, name):
    """
    Check if it's a valid stock
    Filter out:
    1. Indexes
    2. Delisted companies (name ends with '退')
    3. Non-stock data in A-shares (funds, bonds, warrants, etc.)
    """
    # Filter indexes (name contains keywords)
    if name and any(keyword in name for keyword in ['指数', 'ETF', 'LOF', '基金', '债券', '权证', '优先股', '存托凭证', '资产支持证券']):
        return False
    
    # Filter delisted companies (name ends with '退')
    if name and name.endswith('退'):
        return False
    
    # Filter non-stock codes
    code_str = str(code)
    
    # 基金类
    fund_prefixes = ['15', '16', '51', '58', '159', '50', '511']
    for prefix in fund_prefixes:
        if code_str.startswith(prefix):
            return False
    
    # 债券类
    bond_prefixes = ['01', '10', '12', '11', '14']
    for prefix in bond_prefixes:
        if code_str.startswith(prefix):
            return False
    
    # 权证类
    warrant_prefixes = ['580']
    for prefix in warrant_prefixes:
        if code_str.startswith(prefix):
            return False
    
    # B股
    b_stock_prefixes = ['200', '900']
    for prefix in b_stock_prefixes:
        if code_str.startswith(prefix):
            return False
    
    # 特殊代码
    special_codes = ['000001', '399001', '880001', '888888', '999999']
    if code_str in special_codes:
        return False
    
    # 测试代码
    if code_str.startswith('888'):
        return False
    
    return True

'''
    
    # 在process函数开始处添加过滤逻辑
    if "def process(" in code:
        # 找到process函数的开始位置
        process_start = code.find("def process(")
        # 找到process函数的第一行代码
        first_line_end = code.find("\n", process_start)
        # 找到函数体的开始位置
        body_start = code.find("\n", first_line_end + 1)
        
        # 构建新的代码
        new_code = code[:body_start + 1]
        new_code += """
    # 过滤非个股数据
    if isinstance(data, pd.DataFrame):
        # 确保索引是股票代码
        if not data.empty:
            # 复制DataFrame以避免修改原始数据
            data = data.copy()
            # 应用过滤逻辑
            valid_mask = []
            for idx, row in data.iterrows():
                code = idx
                name = row.get('name', '')
                valid_mask.append(is_valid_stock(code, name))
            # 过滤掉无效股票
            data = data[valid_mask]
            # 如果过滤后没有数据，返回None
            if data.empty:
                return None
    # 处理字典类型的输入（单条数据）
    elif isinstance(data, dict):
        # 检查是否为股票数据
        symbol = data.get('symbol', data.get('code', data.get('ts_code', '')))
        name = data.get('name', '')
        if symbol:
            if not is_valid_stock(symbol, name):
                return None

"""
        new_code += code[body_start + 1:]
        
        # 将过滤函数添加到代码开头
        new_code = filter_function + new_code
        return new_code, True
    
    return code, False


def update_all_strategies():
    """
    更新所有策略，添加股票过滤逻辑
    """
    mgr = get_strategy_manager()
    mgr.load_from_db()
    
    entries = mgr.list_all()
    updated_count = 0
    skipped_count = 0
    
    print(f"Found {len(entries)} strategies to process")
    
    for entry in entries:
        print(f"\nProcessing strategy: {entry.name} (ID: {entry.id})")
        
        # 获取原始代码
        original_code = entry._func_code
        
        # 添加过滤逻辑
        new_code, updated = add_stock_filter(original_code)
        
        if updated:
            # 更新策略代码
            result = entry.update_config(func_code=new_code)
            if result.get('success'):
                print(f"✓ Updated successfully")
                updated_count += 1
            else:
                print(f"✗ Update failed: {result.get('error')}")
                skipped_count += 1
        else:
            print(f"✓ Already has filter logic, skipped")
            skipped_count += 1
    
    print(f"\nSummary: Updated {updated_count} strategies, skipped {skipped_count}")


if __name__ == "__main__":
    update_all_strategies()
