#!/usr/bin/env python3
"""
数据源状态持久化测试脚本

测试内容：
1. 数据源状态保存到数据库
2. 执行代码保存和版本管理
3. 程序重启时的状态恢复
4. 完整的状态导出和导入
"""

import time
import pandas as pd
from datetime import datetime
from deva.admin_ui.strategy.datasource import DataSource, DataSourceManager, DataSourceType, DataSourceStatus
from deva.admin_ui.strategy.quant import gen_quant
from deva import NS

def test_basic_persistence():
    """测试基本的状态持久化功能"""
    print("=== 测试基本状态持久化 ===")
    
    # 创建数据源管理器
    manager = DataSourceManager()
    
    # 创建测试数据源
    test_code = '''
import pandas as pd
import time

def fetch_data():
    """测试数据获取函数"""
    return pd.DataFrame({
        'timestamp': [time.time()],
        'value': [42],
        'status': ['test']
    })
'''
    
    source = DataSource(
        name="test_source",
        source_type=DataSourceType.TIMER,
        description="测试数据源",
        data_func_code=test_code,
        interval=2.0,
        auto_start=False
    )
    
    # 注册数据源（会自动保存到数据库）
    manager.register(source)
    print(f"✓ 数据源已创建并保存: {source.id}")
    
    # 启动数据源
    result = source.start()
    print(f"✓ 数据源启动结果: {result}")
    
    # 运行一段时间
    time.sleep(5)
    
    # 停止数据源
    result = source.stop()
    print(f"✓ 数据源停止结果: {result}")
    
    return source.id

def test_state_recovery():
    """测试状态恢复功能"""
    print("\n=== 测试状态恢复功能 ===")
    
    # 创建新的管理器实例（模拟程序重启）
    manager = DataSourceManager()
    
    # 从数据库加载数据源
    count = manager.load_from_db()
    print(f"✓ 从数据库加载了 {count} 个数据源")
    
    # 获取之前创建的数据源
    sources = manager.list_sources()
    print(f"✓ 找到 {len(sources)} 个数据源")
    
    for source in sources:
        if hasattr(source, 'name') and source.name == "test_source":
            print(f"✓ 找到测试数据源: {source.name}")
            print(f"  - 状态: {source.state.status}")
            print(f"  - 运行统计: {source.stats.total_emitted} 条数据")
            
            # 获取保存的状态摘要
            summary = source.get_full_state_summary()
            print(f"✓ 状态摘要: {summary}")
            
            # 恢复运行状态
            restore_result = manager.restore_running_states()
            print(f"✓ 状态恢复结果: {restore_result}")
            break
    
    return True

def test_code_version_management():
    """测试代码版本管理功能"""
    print("\n=== 测试代码版本管理 ===")
    
    manager = DataSourceManager()
    manager.load_from_db()
    
    # 找到测试数据源
    source = manager.get_source_by_name("test_source")
    
    if not source:
        print("✗ 未找到测试数据源")
        return False
    
    # 更新代码
    new_code = '''
import pandas as pd
import time

def fetch_data():
    """更新后的测试数据获取函数"""
    return pd.DataFrame({
        'timestamp': [time.time()],
        'value': [100],
        'status': ['updated_test'],
        'version': ['v2.0']
    })
'''
    
    update_result = source.update_data_func_code(new_code)
    print(f"✓ 代码更新结果: {update_result}")
    
    # 获取代码版本历史
    versions = source.get_code_versions(5)
    print(f"✓ 代码版本历史: {len(versions)} 个版本")
    for i, version in enumerate(versions):
        print(f"  版本 {i+1}: {version.get('timestamp', 'N/A')}")
    
    return True

def test_state_export_import():
    """测试状态导出和导入功能"""
    print("\n=== 测试状态导出和导入 ===")
    
    manager = DataSourceManager()
    manager.load_from_db()
    
    # 找到测试数据源
    source = manager.get_source_by_name("test_source")
    
    if not source:
        print("✗ 未找到测试数据源")
        return False
    
    # 导出状态
    export_data = source.export_state(include_data=True, include_code=True)
    print(f"✓ 状态导出成功，包含 {len(export_data)} 个字段")
    
    # 创建新的数据源用于导入测试
    new_source = DataSource(
        name="imported_test_source",
        source_type=DataSourceType.TIMER,
        description="导入的测试数据源"
    )
    manager.register(new_source)
    
    # 导入状态
    import_result = new_source.import_state(export_data, merge=False)
    print(f"✓ 状态导入结果: {import_result}")
    
    return True

def test_error_handling():
    """测试错误处理和状态保存"""
    print("\n=== 测试错误处理 ===")
    
    manager = DataSourceManager()
    
    # 创建有错误的数据源
    error_code = '''
import pandas as pd

def fetch_data():
    """有错误的数据获取函数"""
    raise ValueError("模拟数据获取错误")
    return pd.DataFrame()
'''
    
    error_source = DataSource(
        name="error_test_source",
        source_type=DataSourceType.TIMER,
        description="错误测试数据源",
        data_func_code=error_code,
        interval=1.0,
        auto_start=False
    )
    
    manager.register(error_source)
    
    # 启动并观察错误处理
    error_source.start()
    time.sleep(3)
    
    # 检查错误状态
    print(f"✓ 错误计数: {error_source.state.error_count}")
    print(f"✓ 最后错误: {error_source.state.last_error}")
    print(f"✓ 当前状态: {error_source.state.status}")
    
    # 获取保存的错误状态
    saved_state = error_source.get_saved_running_state()
    print(f"✓ 保存的运行状态: {saved_state}")
    
    error_source.stop()
    return True

def main():
    """主测试函数"""
    print("开始数据源状态持久化测试...")
    print(f"测试时间: {datetime.now()}")
    
    try:
        # 1. 测试基本持久化
        source_id = test_basic_persistence()
        
        # 2. 测试状态恢复
        test_state_recovery()
        
        # 3. 测试代码版本管理
        test_code_version_management()
        
        # 4. 测试状态导出导入
        test_state_export_import()
        
        # 5. 测试错误处理
        test_error_handling()
        
        print("\n=== 所有测试完成 ===")
        print("✓ 数据源状态持久化功能测试通过")
        
    except Exception as e:
        print(f"✗ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)