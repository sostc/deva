#!/usr/bin/env python3
"""
分析实时行情数据结构，了解字段特点
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import easyquotation
import pandas as pd

def analyze_tick_data():
    """分析实时行情数据结构"""
    print("📊 分析实时行情数据结构...")
    
    # 获取实时行情数据
    quotation_engine = easyquotation.use("sina")
    q1 = quotation_engine.market_snapshot(prefix=False)
    
    # 转换为DataFrame
    df = pd.DataFrame(q1).T
    
    print(f"\n📈 数据概览:")
    print(f"   总数据量: {len(df)} 条")
    print(f"   字段列表: {list(df.columns)}")
    
    # 查看前5条数据
    print("\n🔍 前5条数据:")
    print(df.head())
    
    # 分析name字段
    if 'name' in df.columns:
        print("\n📋 分析name字段:")
        print(f"   非空值数量: {df['name'].notna().sum()}")
        
        # 查找包含关键字的数据
        keywords = ['指数', 'ETF', 'LOF', '基金']
        for keyword in keywords:
            keyword_data = df[df['name'].str.contains(keyword, na=False)]
            print(f"   包含'{keyword}'的数量: {len(keyword_data)}")
            if len(keyword_data) > 0:
                print(f"   示例: {list(keyword_data['name'].head(3))}")
    
    # 分析code字段
    print("\n📋 分析code字段:")
    print(f"   非空值数量: {df.index.notna().sum()}")
    
    # 查找包含关键字的数据
    code_keywords = ['ETF', 'LOF']
    for keyword in code_keywords:
        keyword_data = df[df.index.str.contains(keyword, na=False)]
        print(f"   代码包含'{keyword}'的数量: {len(keyword_data)}")
        if len(keyword_data) > 0:
            print(f"   示例: {list(keyword_data.index.head(3))}")
    
    # 分析成交量字段
    if 'volume' in df.columns:
        print("\n📊 分析成交量字段:")
        print(f"   成交量为0的数量: {(df['volume'] == 0).sum()}")
        print(f"   成交量小于100的数量: {(df['volume'] < 100).sum()}")
        print(f"   成交量统计: {df['volume'].describe()}")
    
    # 分析价格字段
    if 'close' in df.columns and 'now' in df.columns:
        print("\n📊 分析价格字段:")
        print(f"   close为0的数量: {(df['close'] == 0).sum()}")
        print(f"   now为0的数量: {(df['now'] == 0).sum()}")
    
    # 分析st股票
    if 'name' in df.columns:
        print("\n📋 分析ST股票:")
        st_data = df[df['name'].str.contains('ST', na=False)]
        print(f"   ST股票数量: {len(st_data)}")
        if len(st_data) > 0:
            print(f"   示例: {list(st_data['name'].head(3))}")
    
    return df

if __name__ == '__main__':
    print("=" * 60)
    print("分析实时行情数据结构")
    print("=" * 60)
    
    df = analyze_tick_data()
    
    print("\n🎯 分析完成！")
    print("根据分析结果，将改进过滤逻辑")
