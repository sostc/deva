#!/usr/bin/env python3
"""
检查股票代码格式
"""

from deva.naja.market_hotspot.data.sina_parser import _get_cn_codes_from_registry
from deva.naja.dictionary.blocks import get_block_dictionary

# 获取股票代码列表
codes = _get_cn_codes_from_registry()
print(f"实盘获取器股票代码数量: {len(codes)}")
print(f"前10个股票代码: {codes[:10]}")

# 检查代码格式
if codes:
    sample_code = codes[0]
    print(f"\n实盘获取器样本代码格式: {sample_code}")
    print(f"代码长度: {len(sample_code)}")
    print(f"代码前缀: {sample_code[:2]}")

# 检查BlockDictionary中的股票代码格式
b = get_block_dictionary()
print(f"\nBlockDictionary中的股票数量: {len(b._cn_stock_to_blocks)}")
block_codes = list(b._cn_stock_to_blocks.keys())
print(f"前10个BlockDictionary股票代码: {block_codes[:10]}")

if block_codes:
    block_sample = block_codes[0]
    print(f"\nBlockDictionary样本代码格式: {block_sample}")
    print(f"代码长度: {len(block_sample)}")
    print(f"代码前缀: {block_sample[:2]}")
