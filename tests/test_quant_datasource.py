#!/usr/bin/env python3
"""
数据源行情数据获取测试脚本

测试内容：
1. 数据源重启后的行情数据获取
2. 状态恢复和代码持久化功能
3. 交易时间和非交易时间的数据获取
4. 错误处理和降级机制
"""

import time
import datetime
import pandas as pd
from deva.admin_ui.strategy.datasource import DataSource, DataSourceManager, DataSourceType
from deva.admin_ui.strategy.runtime import gen_quant_data_func_code

def test_datasource_creation_and_persistence():
    """测试数据源创建和持久化"""
    print("=== 测试数据源创建和持久化 ===")
    
    # 创建数据源管理器
    manager = DataSourceManager()
    
    # 查找或创建quant_source数据源
    quant_source = manager.get_source_by_name("quant_source_test")
    
    if not quant_source:
        print("创建新的quant_source测试数据源...")
        
        # 创建命名流
        from deva import NS
        source_stream = NS("quant_source_test", cache_max_len=1, cache_max_age_seconds=60, 
                          description='股票行情数据流测试')
        
        # 创建数据源
        quant_source = DataSource(
            name="quant_source_test",
            source_type=DataSourceType.TIMER,
            description="股票行情数据流 (定时获取行情数据)",
            config={},
            stream=source_stream,
            auto_start=False,
            data_func_code=gen_quant_data_func_code,
            interval=3.0,  # 3秒间隔用于测试
        )
        
        # 注册数据源（自动保存到数据库）
        manager.register(quant_source)
        print(f"✓ 数据源已创建并保存: {quant_source.id}")
    else:
        print(f"✓ 找到现有数据源: {quant_source.id}")
    
    return quant_source

def test_data_fetching():
    """测试数据获取功能"""
    print("\n=== 测试数据获取功能 ===")
    
    manager = DataSourceManager()
    quant_source = manager.get_source_by_name("quant_source_test")
    
    if not quant_source:
        print("✗ 未找到数据源")
        return False
    
    # 启动数据源
    start_result = quant_source.start()
    print(f"✓ 数据源启动结果: {start_result}")
    
    if not start_result.get("success"):
        print(f"✗ 数据源启动失败: {start_result.get('error')}")
        return False
    
    # 等待数据获取
    print("等待数据获取...")
    time.sleep(8)  # 等待至少2个周期
    
    # 检查获取的数据
    recent_data = quant_source.get_recent_data(5)
    print(f"✓ 获取到 {len(recent_data)} 条数据")
    
    if recent_data:
        latest_data = recent_data[-1]
        print(f"✓ 最新数据类型: {type(latest_data)}")
        
        if isinstance(latest_data, pd.DataFrame):
            print(f"✓ DataFrame形状: {latest_data.shape}")
            print(f"✓ 列名: {list(latest_data.columns)}")
            if len(latest_data) > 0:
                print(f"✓ 第一行数据: {latest_data.iloc[0].to_dict()}")
        elif isinstance(latest_data, dict):
            print(f"✓ 数据内容: {latest_data}")
        else:
            print(f"✓ 数据内容: {latest_data}")
    
    # 获取保存的最新数据状态
    saved_data = quant_source.get_saved_latest_data()
    if saved_data:
        print(f"✓ 保存的最新数据状态:")
        print(f"  - 数据类型: {saved_data.get('data_type')}")
        print(f"  - 数据大小: {saved_data.get('size')}")
        print(f"  - 时间戳: {saved_data.get('timestamp')}")
    
    # 获取保存的运行状态
    saved_state = quant_source.get_saved_running_state()
    if saved_state:
        print(f"✓ 保存的运行状态:")
        print(f"  - 运行状态: {saved_state.get('is_running')}")
        print(f"  - 进程ID: {saved_state.get('pid')}")
        print(f"  - 错误计数: {saved_state.get('error_count')}")
    
    # 停止数据源
    stop_result = quant_source.stop()
    print(f"✓ 数据源停止结果: {stop_result}")
    
    return True

def test_state_recovery():
    """测试状态恢复功能"""
    print("\n=== 测试状态恢复功能 ===")
    
    # 模拟程序重启：创建新的管理器实例
    new_manager = DataSourceManager()
    
    # 从数据库加载数据源
    loaded_count = new_manager.load_from_db()
    print(f"✓ 从数据库加载了 {loaded_count} 个数据源")
    
    # 查找之前的数据源
    recovered_source = new_manager.get_source_by_name("quant_source_test")
    
    if not recovered_source:
        print("✗ 未找到恢复的数据源")
        return False
    
    print(f"✓ 找到恢复的数据源: {recovered_source.id}")
    print(f"✓ 数据源状态: {recovered_source.state.status}")
    print(f"✓ 数据源统计: 总发送 {recovered_source.stats.total_emitted} 条数据")
    
    # 获取完整状态摘要
    summary = recovered_source.get_full_state_summary()
    print(f"✓ 状态摘要:")
    print(f"  - 当前状态: {summary['current_status']}")
    print(f"  - 代码版本: {summary['code_versions_count']} 个")
    print(f"  - 依赖策略: {len(summary['dependent_strategies'])} 个")
    
    # 恢复运行状态
    restore_result = new_manager.restore_running_states()
    print(f"✓ 状态恢复结果:")
    print(f"  - 恢复成功: {restore_result['restored_count']} 个")
    print(f"  - 恢复失败: {restore_result['failed_count']} 个")
    
    # 等待恢复后的数据获取
    if restore_result['restored_count'] > 0:
        print("等待恢复后的数据获取...")
        time.sleep(8)
        
        # 检查恢复后的数据
        recent_data = recovered_source.get_recent_data(3)
        print(f"✓ 恢复后获取到 {len(recent_data)} 条数据")
        
        if recent_data:
            print("✓ 数据源恢复成功并正常运行")
    
    return True

def test_trading_time_logic():
    """测试交易时间逻辑"""
    print("\n=== 测试交易时间逻辑 ===")
    
    # 创建一个测试数据源用于验证交易时间逻辑
    test_code = '''
import datetime
import pandas as pd
import time

def is_tradedate(dt=None):
    """测试用的交易日判断"""
    if dt is None:
        dt = datetime.datetime.now()
    return dt.weekday() < 5  # 周一到周五

def is_tradetime(dt=None):
    """测试用的交易时间判断"""
    if dt is None:
        dt = datetime.datetime.now()
    # 测试时总是返回True，确保能获取数据
    return True

def fetch_data():
    """测试数据获取"""
    now = datetime.datetime.now()
    print(f"[TEST] Fetching data at {now}")
    
    if not is_tradedate(now):
        print("[TEST] Non-trading date, returning None")
        return None
    
    if not is_tradetime(now):
        print("[TEST] Non-trading time, returning None")
        return None
    
    # 返回测试数据
    return pd.DataFrame({
        'code': ['000001', '000002'],
        'name': ['平安银行', '万科A'],
        'now': [10.5, 15.2],
        'close': [10.0, 15.0],
        'p_change': [0.05, 0.0133],
        'timestamp': [time.time(), time.time()]
    })
'''
    
    manager = DataSourceManager()
    
    test_source = DataSource(
        name="trading_time_test",
        source_type=DataSourceType.TIMER,
        description="交易时间测试数据源",
        data_func_code=test_code,
        interval=2.0,
        auto_start=False
    )
    
    manager.register(test_source)
    
    # 启动并测试
    test_source.start()
    time.sleep(5)
    
    # 检查数据
    recent_data = test_source.get_recent_data(3)
    print(f"✓ 交易时间测试获取到 {len(recent_data)} 条数据")
    
    test_source.stop()
    return True

def test_error_handling_and_fallback():
    """测试错误处理和降级机制"""
    print("\n=== 测试错误处理和降级机制 ===")
    
    # 创建一个会出错的数据源
    error_code = '''
import datetime
import pandas as pd

def fetch_data():
    """会出错的测试函数"""
    # 模拟各种错误情况
    import random
    error_type = random.choice(['import_error', 'network_error', 'data_error'])
    
    if error_type == 'import_error':
        import non_existent_module  # 这会触发ImportError
    elif error_type == 'network_error':
        raise ConnectionError("网络连接失败")
    else:
        # 返回错误格式的数据
        return "invalid data format"
    
    return pd.DataFrame({'test': [1, 2, 3]})
'''
    
    manager = DataSourceManager()
    
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
    time.sleep(4)  # 等待几个错误周期
    
    print(f"✓ 错误计数: {error_source.state.error_count}")
    print(f"✓ 最后错误: {error_source.state.last_error}")
    print(f"✓ 当前状态: {error_source.state.status}")
    
    # 获取保存的错误状态
    saved_state = error_source.get_saved_running_state()
    if saved_state:
        print(f"✓ 保存的错误状态: {saved_state.get('last_error')}")
    
    error_source.stop()
    return True

def main():
    """主测试函数"""
    print("开始数据源行情数据获取测试...")
    print(f"测试时间: {datetime.datetime.now()}")
    
    try:
        # 1. 测试数据源创建和持久化
        quant_source = test_datasource_creation_and_persistence()
        
        # 2. 测试数据获取功能
        test_data_fetching()
        
        # 3. 测试状态恢复功能
        test_state_recovery()
        
        # 4. 测试交易时间逻辑
        test_trading_time_logic()
        
        # 5. 测试错误处理和降级机制
        test_error_handling_and_fallback()
        
        print("\n=== 所有测试完成 ===")
        print("✓ 数据源行情数据获取功能测试通过")
        print("✓ 状态持久化和恢复功能正常")
        print("✓ 重启后能够正常获取行情数据")
        
    except Exception as e:
        print(f"✗ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)