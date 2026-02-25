#!/usr/bin/env python3
"""
测试数据源代码执行修复效果
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deva.admin_ui.strategy.datasource import DataSource, DataSourceType

def test_multi_function_code():
    """测试包含多个函数的数据源代码"""
    
    # 测试代码包含多个函数和导入
    test_code = '''
import pandas as pd
import numpy as np

def helper_function(data):
    """辅助函数：处理数据"""
    return data * 2

def another_helper(df):
    """另一个辅助函数：添加列"""
    df['processed'] = df['value'].apply(helper_function)
    return df

def fetch_data():
    """主数据获取函数"""
    # 创建测试数据
    data = {
        'code': ['000001', '000002', '000003'],
        'value': [10, 20, 30],
        'name': ['股票1', '股票2', '股票3']
    }
    
    # 使用pandas创建DataFrame
    df = pd.DataFrame(data)
    
    # 调用辅助函数处理数据
    result_df = another_helper(df)
    
    # 添加时间戳
    result_df['timestamp'] = time.time()
    
    return result_df
'''
    
    print("=== 测试多函数数据源代码 ===")
    
    # 创建数据源
    source = DataSource(
        name="test_multi_function",
        source_type=DataSourceType.TIMER,
        data_func_code=test_code,
        interval=1.0,
        auto_start=False
    )
    
    # 编译数据函数
    print("1. 编译数据函数...")
    data_func = source._compile_data_func()
    
    if data_func is None:
        print("❌ 数据函数编译失败")
        return False
    
    print("✅ 数据函数编译成功")
    
    # 执行数据函数
    print("2. 执行数据函数...")
    try:
        result = data_func()
        print(f"✅ 数据函数执行成功，返回数据类型: {type(result)}")
        
        if hasattr(result, 'shape'):
            print(f"   数据形状: {result.shape}")
            print(f"   数据预览:\n{result.head()}")
        else:
            print(f"   数据内容: {result}")
            
        return True
        
    except Exception as e:
        print(f"❌ 数据函数执行失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_import_error_code():
    """测试导入错误处理"""
    
    # 测试代码使用未导入的库
    test_code = '''
def fetch_data():
    # 使用pandas但没有导入
    df = pd.DataFrame({'test': [1, 2, 3]})
    return df
'''
    
    print("\n=== 测试导入错误处理 ===")
    
    # 创建数据源
    source = DataSource(
        name="test_import_error",
        source_type=DataSourceType.TIMER,
        data_func_code=test_code,
        interval=1.0,
        auto_start=False
    )
    
    # 编译数据函数
    print("1. 编译数据函数...")
    data_func = source._compile_data_func()
    
    if data_func is None:
        print("❌ 数据函数编译失败")
        return False
    
    print("✅ 数据函数编译成功")
    
    # 执行数据函数
    print("2. 执行数据函数...")
    try:
        result = data_func()
        print(f"✅ 数据函数执行成功，返回数据类型: {type(result)}")
        return True
        
    except Exception as e:
        print(f"❌ 数据函数执行失败: {str(e)}")
        return False

def test_complex_scenario():
    """测试复杂场景：多个函数、类、复杂逻辑"""
    
    test_code = '''
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class DataProcessor:
    """数据处理器类"""
    def __init__(self, factor=1.5):
        self.factor = factor
    
    def process(self, data):
        return data * self.factor

def generate_mock_data():
    """生成模拟数据"""
    codes = ['000001', '000002', '000003', '000004', '000005']
    prices = np.random.uniform(10, 100, len(codes))
    
    return pd.DataFrame({
        'code': codes,
        'price': prices,
        'volume': np.random.randint(1000, 100000, len(codes)),
        'change': np.random.uniform(-0.1, 0.1, len(codes))
    })

def add_technical_indicators(df):
    """添加技术指标"""
    df['ma5'] = df['price'].rolling(window=5, min_periods=1).mean()
    df['rsi'] = calculate_rsi(df['change'])
    return df

def calculate_rsi(changes, period=14):
    """计算RSI指标"""
    delta = pd.Series(changes)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)  # 填充NaN值

def fetch_data():
    """主数据获取函数"""
    # 生成基础数据
    df = generate_mock_data()
    
    # 创建数据处理器
    processor = DataProcessor(factor=1.2)
    
    # 处理价格数据
    df['processed_price'] = df['price'].apply(processor.process)
    
    # 添加技术指标
    df = add_technical_indicators(df)
    
    # 添加时间戳
    df['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return df
'''
    
    print("\n=== 测试复杂场景 ===")
    
    # 创建数据源
    source = DataSource(
        name="test_complex_scenario",
        source_type=DataSourceType.TIMER,
        data_func_code=test_code,
        interval=1.0,
        auto_start=False
    )
    
    # 编译数据函数
    print("1. 编译数据函数...")
    data_func = source._compile_data_func()
    
    if data_func is None:
        print("❌ 数据函数编译失败")
        return False
    
    print("✅ 数据函数编译成功")
    
    # 执行数据函数
    print("2. 执行数据函数...")
    try:
        result = data_func()
        print(f"✅ 数据函数执行成功")
        print(f"   返回数据类型: {type(result)}")
        
        if hasattr(result, 'shape'):
            print(f"   数据形状: {result.shape}")
            print(f"   列名: {list(result.columns)}")
            print(f"   数据预览:\n{result}")
            
        return True
        
    except Exception as e:
        print(f"❌ 数据函数执行失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("开始测试数据源代码执行修复效果...\n")
    
    # 运行测试
    results = []
    
    results.append(("多函数测试", test_multi_function_code()))
    results.append(("导入错误测试", test_import_error_code()))
    results.append(("复杂场景测试", test_complex_scenario()))
    
    # 总结结果
    print("\n" + "="*50)
    print("测试结果总结:")
    print("="*50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("🎉 所有测试都通过了！修复效果良好。")
    else:
        print("⚠️  部分测试失败，需要进一步优化。")