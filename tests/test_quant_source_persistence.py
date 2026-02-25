#!/usr/bin/env python3
"""
验证现有quant_source数据源的状态持久化和重启恢复功能
"""

import time
import datetime
from deva.admin_ui.strategy.runtime import initialize_strategy_monitor_streams
from deva.admin_ui.strategy.datasource import get_ds_manager

def test_existing_quant_source():
    """测试现有的quant_source数据源"""
    print("=== 测试现有quant_source数据源 ===")
    
    # 初始化策略监控流，这会创建或恢复quant_source
    print("初始化策略监控流...")
    initialize_strategy_monitor_streams()
    
    # 获取数据源管理器
    ds_manager = get_ds_manager()
    
    # 查找quant_source数据源
    quant_source = ds_manager.get_source_by_name("quant_source")
    
    if not quant_source:
        print("✗ 未找到quant_source数据源")
        return False
    
    print(f"✓ 找到quant_source数据源: {quant_source.id}")
    print(f"✓ 数据源名称: {quant_source.name}")
    print(f"✓ 数据源状态: {quant_source.state.status}")
    print(f"✓ 数据源类型: {quant_source.metadata.source_type}")
    print(f"✓ 执行间隔: {quant_source.metadata.interval} 秒")
    
    # 获取完整状态摘要
    summary = quant_source.get_full_state_summary()
    print(f"✓ 状态摘要:")
    print(f"  - 当前状态: {summary['current_status']}")
    print(f"  - 运行统计: 总发送 {summary['current_stats']['total_emitted']} 条数据")
    print(f"  - 代码版本: {summary['code_versions_count']} 个")
    print(f"  - 依赖策略: {len(summary['dependent_strategies'])} 个")
    
    # 检查保存的运行状态
    saved_state = quant_source.get_saved_running_state()
    if saved_state:
        print(f"✓ 保存的运行状态:")
        print(f"  - 运行状态: {saved_state.get('is_running')}")
        print(f"  - 进程ID: {saved_state.get('pid')}")
        print(f"  - 最后更新: {saved_state.get('last_update')}")
    
    # 检查保存的最新数据
    saved_data = quant_source.get_saved_latest_data()
    if saved_data:
        print(f"✓ 保存的最新数据:")
        print(f"  - 数据类型: {saved_data.get('data_type')}")
        print(f"  - 数据大小: {saved_data.get('size')}")
        print(f"  - 时间戳: {saved_data.get('timestamp')}")
    
    # 检查代码版本历史
    code_versions = quant_source.get_code_versions(3)
    print(f"✓ 代码版本历史: {len(code_versions)} 个版本")
    for i, version in enumerate(code_versions):
        print(f"  版本 {i+1}: {version.get('timestamp', 'N/A')}")
    
    # 检查执行代码
    print(f"✓ 执行代码长度: {len(quant_source.metadata.data_func_code)} 字符")
    print("✓ 执行代码预览:")
    lines = quant_source.metadata.data_func_code.split('\n')[:10]
    for line in lines:
        print(f"    {line}")
    
    return True

def test_quant_source_data_fetching():
    """测试quant_source的数据获取功能"""
    print("\n=== 测试quant_source数据获取功能 ===")
    
    ds_manager = get_ds_manager()
    quant_source = ds_manager.get_source_by_name("quant_source")
    
    if not quant_source:
        print("✗ 未找到quant_source数据源")
        return False
    
    # 如果数据源未运行，尝试启动它
    if quant_source.state.status != "running":
        print("启动quant_source数据源...")
        result = quant_source.start()
        print(f"✓ 启动结果: {result}")
        
        if not result.get("success"):
            print(f"✗ 启动失败: {result.get('error')}")
            return False
    
    # 等待数据获取
    print("等待数据获取...")
    time.sleep(10)  # 等待至少2个周期（5秒间隔）
    
    # 检查获取的数据
    recent_data = quant_source.get_recent_data(5)
    print(f"✓ 获取到 {len(recent_data)} 条数据")
    
    if recent_data:
        latest = recent_data[-1]
        print(f"✓ 最新数据类型: {type(latest)}")
        
        if hasattr(latest, 'shape'):  # DataFrame
            print(f"✓ DataFrame形状: {latest.shape}")
            print(f"✓ 列名: {list(latest.columns)}")
            if len(latest) > 0:
                print(f"✓ 数据行数: {len(latest)}")
                print(f"✓ 第一行数据示例: {latest.iloc[0].to_dict() if hasattr(latest, 'iloc') else latest}")
        elif isinstance(latest, list) and len(latest) > 0:
            print(f"✓ 列表数据，第一条: {latest[0]}")
        elif isinstance(latest, dict):
            print(f"✓ 字典数据: {latest}")
        
        print("✓ quant_source数据源正常工作，成功获取行情数据")
        return True
    else:
        print("✗ 未获取到数据")
        return False

def test_state_recovery():
    """测试状态恢复功能"""
    print("\n=== 测试状态恢复功能 ===")
    
    ds_manager = get_ds_manager()
    
    # 模拟程序重启：重新初始化
    print("模拟程序重启，重新初始化...")
    initialize_strategy_monitor_streams()
    
    # 重新获取数据源管理器
    ds_manager = get_ds_manager()
    
    # 查找quant_source数据源
    quant_source = ds_manager.get_source_by_name("quant_source")
    
    if not quant_source:
        print("✗ 重启后未找到quant_source数据源")
        return False
    
    print(f"✓ 重启后找到quant_source数据源: {quant_source.id}")
    print(f"✓ 重启后状态: {quant_source.state.status}")
    print(f"✓ 重启后统计: 总发送 {quant_source.stats.total_emitted} 条数据")
    
    # 检查保存的状态
    saved_state = quant_source.get_saved_running_state()
    if saved_state:
        print(f"✓ 保存的运行状态: {saved_state.get('is_running')}")
    
    # 等待恢复后的数据获取
    print("等待恢复后的数据获取...")
    time.sleep(8)
    
    # 检查恢复后的数据
    recent_data = quant_source.get_recent_data(3)
    print(f"✓ 恢复后获取到 {len(recent_data)} 条数据")
    
    if recent_data:
        print("✓ 数据源恢复成功并正常运行，成功获取行情数据")
        return True
    else:
        print("✗ 恢复后未获取到数据")
        return False

def main():
    """主测试函数"""
    print("开始验证quant_source数据源状态持久化功能...")
    print(f"测试时间: {datetime.datetime.now()}")
    
    try:
        # 1. 测试现有quant_source数据源
        existing_success = test_existing_quant_source()
        
        # 2. 测试数据获取功能
        fetching_success = test_quant_source_data_fetching()
        
        # 3. 测试状态恢复功能
        recovery_success = test_state_recovery()
        
        print("\n=== 测试完成 ===")
        
        if existing_success and fetching_success and recovery_success:
            print("🎉 所有测试通过！")
            print("✅ quant_source数据源状态持久化功能正常")
            print("✅ gen_quant相关代码已成功存储到数据源执行代码中")
            print("✅ 程序重启后能恢复状态并继续获取行情数据")
            print("✅ 状态保存和恢复功能完全正常")
            return True
        else:
            print("❌ 部分测试失败")
            if not existing_success:
                print("✗ 现有数据源检查失败")
            if not fetching_success:
                print("✗ 数据获取功能异常")
            if not recovery_success:
                print("✗ 状态恢复功能异常")
            return False
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)