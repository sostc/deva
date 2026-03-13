#!/usr/bin/env python3
"""
测试过滤逻辑，查看过滤后真正有效的股票数据量
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import easyquotation
import pandas as pd

def test_filter_effect():
    """测试过滤逻辑的效果"""
    print("📊 测试过滤逻辑效果...")
    
    # 获取实时行情数据
    quotation_engine = easyquotation.use("sina")
    q1 = quotation_engine.market_snapshot(prefix=False)
    
    # 转换为DataFrame
    df = pd.DataFrame(q1).T
    
    print(f"\n📈 原始数据概览:")
    print(f"   总数据量: {len(df)} 条")
    
    # 应用过滤逻辑
    print("\n🔍 应用过滤逻辑...")
    
    # 1. 过滤掉 close 为 0 的股票
    close_zero = len(df[df["close"] == 0])
    df = df[(True ^ df["close"].isin([0]))]
    print(f"   过滤close为0的数据: {close_zero} 条")
    
    # 2. 过滤掉 now 为 0 的股票
    now_zero = len(df[df["now"] == 0])
    df = df[(True ^ df["now"].isin([0]))]
    print(f"   过滤now为0的数据: {now_zero} 条")
    
    # 3. 过滤掉指数代码（以000、399、688开头）
    index_codes = len(df[df.index.str.match('^000|^399|^688')])
    df = df[~df.index.str.match('^000')]
    df = df[~df.index.str.match('^399')]
    df = df[~df.index.str.match('^688')]
    print(f"   过滤指数代码: {index_codes} 条")
    
    # 4. 过滤掉name字段中包含特定关键字的产品
    if 'name' in df.columns:
        keywords = ['指数', 'ETF', 'LOF', '基金']
        keyword_count = 0
        for keyword in keywords:
            keyword_data = df[df['name'].str.contains(keyword, na=False, regex=False)]
            keyword_count += len(keyword_data)
            df = df[~df['name'].str.contains(keyword, na=False, regex=False)]
        print(f"   过滤包含关键字的产品: {keyword_count} 条")
    
    # 5. 过滤掉僵尸票（成交量小于 100 手）
    zombie_stocks = len(df[df.get('volume', 0) <= 100])
    df = df[df.get('volume', 0) > 100]
    print(f"   过滤僵尸票: {zombie_stocks} 条")
    
    # 6. 过滤掉退市票和ST股票（name字段包含特定后缀）
    if 'name' in df.columns:
        st_count = 0
        delisted_patterns = ['退', 'ST', '*ST']
        for pattern in delisted_patterns:
            st_data = df[df['name'].str.contains(pattern, na=False, regex=False)]
            st_count += len(st_data)
            df = df[~df['name'].str.contains(pattern, na=False, regex=False)]
        print(f"   过滤ST和退市票: {st_count} 条")
    
    print(f"\n✅ 过滤完成!")
    print(f"   剩余有效数据: {len(df)} 条")
    
    # 查看过滤后的数据示例
    if len(df) > 0:
        print("\n📋 过滤后的数据示例:")
        print(df.head())
    
    return len(df)

if __name__ == '__main__':
    print("=" * 60)
    print("测试过滤逻辑效果")
    print("=" * 60)
    
    valid_count = test_filter_effect()
    
    print(f"\n🎯 测试完成！")
    print(f"过滤后真正有效的股票数据: {valid_count} 条")
