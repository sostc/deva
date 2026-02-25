#!/usr/bin/env python3
"""
测试导入语句在数据库加载时的执行情况
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deva.admin_ui.strategy.datasource import DataSource, DataSourceType

def test_import_execution():
    """测试导入语句的有效执行"""
    
    # 测试代码包含各种导入语句
    test_code = '''
# 测试各种导入方式
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
import json
import random
import math

# 测试自定义模块导入（如果存在）
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

def fetch_data():
    """测试导入是否有效"""
    print(f"pandas version: {pd.__version__}")
    print(f"numpy version: {np.__version__}")
    print(f"HAS_REQUESTS: {HAS_REQUESTS}")
    
    # 使用导入的库创建数据
    data = {
        'code': ['000001', '000002', '000003'],
        'price': np.array([10.5, 20.3, 15.7]),
        'timestamp': datetime.now().isoformat(),
        'random_val': random.randint(1, 100),
        'sqrt_price': [math.sqrt(p) for p in [10.5, 20.3, 15.7]]
    }
    
    df = pd.DataFrame(data)
    
    # 使用typing
    result: Dict[str, List] = {
        'data': df.to_dict('records'),
        'import_test': {
            'pandas': True,
            'numpy': True,
            'datetime': True,
            'random': True,
            'math': True,
            'json': True
        }
    }
    
    return result
'''
    
    print("=== 测试导入语句执行 ===")
    
    # 创建数据源
    source = DataSource(
        name="test_import_execution",
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
        print(f"返回结果: {result}")
        return True
        
    except Exception as e:
        print(f"❌ 数据函数执行失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_import_from_database():
    """测试从数据库加载后的导入执行情况"""
    
    test_code = '''
import pandas as pd
import numpy as np

def helper_function():
    """辅助函数使用导入的库"""
    return np.array([1, 2, 3]) * 2

def fetch_data():
    """主函数"""
    # 使用导入的库
    data = helper_function()
    df = pd.DataFrame({'values': data, 'doubled': data * 2})
    return df
'''
    
    print("\n=== 测试数据库加载后的导入执行 ===")
    
    # 创建数据源
    source = DataSource(
        name="test_db_import",
        source_type=DataSourceType.TIMER,
        data_func_code=test_code,
        interval=1.0,
        auto_start=False
    )
    
    # 保存到数据库
    print("1. 保存到数据库...")
    source.save()
    
    # 从数据库加载
    print("2. 从数据库加载...")
    loaded_source = DataSource.load(source.id)
    
    if loaded_source is None:
        print("❌ 从数据库加载失败")
        return False
    
    print("✅ 从数据库加载成功")
    
    # 编译加载后的数据函数
    print("3. 编译加载后的数据函数...")
    data_func = loaded_source._compile_data_func()
    
    if data_func is None:
        print("❌ 加载后的数据函数编译失败")
        return False
    
    print("✅ 加载后的数据函数编译成功")
    
    # 执行加载后的数据函数
    print("4. 执行加载后的数据函数...")
    try:
        result = data_func()
        print(f"✅ 加载后的数据函数执行成功")
        print(f"返回数据类型: {type(result)}")
        if hasattr(result, 'shape'):
            print(f"数据形状: {result.shape}")
            print(f"数据预览:\n{result}")
        return True
        
    except Exception as e:
        print(f"❌ 加载后的数据函数执行失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("开始测试导入语句执行情况...\n")
    
    # 运行测试
    results = []
    
    results.append(("导入执行测试", test_import_execution()))
    results.append(("数据库加载导入测试", test_import_from_database()))
    
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
        print("🎉 所有导入测试都通过了！")
    else:
        print("⚠️  部分测试失败，需要进一步优化。")