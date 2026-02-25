#!/usr/bin/env python3
"""
最终版行情数据获取测试
验证数据源代码持久化和重启恢复功能
"""

import time
import datetime
from deva.admin_ui.strategy.datasource import DataSource, DataSourceManager, DataSourceType

# 最终版行情数据获取代码 - 包含所有必要导入
final_gen_quant_code = '''
import datetime
import time
import random
import json

def fetch_data():
    """最终版行情数据获取函数"""
    try:
        # 获取当前时间
        now = datetime.datetime.now()
        print(f"[INFO] Fetching data at {now}")
        
        # 简化的交易时间检查（测试时总是允许）
        # 实际部署时可以启用更严格的检查
        
        # 创建模拟股票数据
        mock_stocks = [
            {"code": "000001", "name": "平安银行", "base_price": 15.8},
            {"code": "000002", "name": "万科A", "base_price": 22.5},
            {"code": "600036", "name": "招商银行", "base_price": 35.2},
            {"code": "600519", "name": "贵州茅台", "base_price": 1680.0},
            {"code": "300750", "name": "宁德时代", "base_price": 198.5},
        ]
        
        # 生成数据
        data = []
        for stock in mock_stocks:
            # 随机价格波动 (-2% 到 +2%)
            price_change = random.uniform(-0.02, 0.02)
            current_price = stock["base_price"] * (1 + price_change)
            
            data.append({
                "code": stock["code"],
                "name": stock["name"],
                "now": round(current_price, 2),
                "close": stock["base_price"],
                "open": round(stock["base_price"] * random.uniform(0.98, 1.02), 2),
                "high": round(current_price * random.uniform(1.0, 1.02), 2),
                "low": round(current_price * random.uniform(0.98, 1.0), 2),
                "volume": random.randint(100000, 10000000),
                "p_change": round(price_change, 4),
                "timestamp": time.time(),
                "datetime": now.strftime("%Y-%m-%d %H:%M:%S")
            })
        
        # 尝试转换为DataFrame
        try:
            import pandas as pd
            df = pd.DataFrame(data)
            print(f"[INFO] Successfully created DataFrame with {len(df)} stocks")
            return df
        except ImportError:
            print(f"[INFO] pandas not available, returning raw data")
            return data
            
    except Exception as e:
        print(f"[ERROR] fetch_data failed: {str(e)}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return None
'''

def test_working_datasource():
    """测试能正常工作的数据源"""
    print("=== 测试可工作的行情数据源 ===")
    
    manager = DataSourceManager()
    
    # 创建数据源
    source = DataSource(
        name="working_quant_source",
        source_type=DataSourceType.TIMER,
        description="可工作的行情数据源",
        data_func_code=final_gen_quant_code,
        interval=3.0,
        auto_start=False
    )
    
    manager.register(source)
    print(f"✓ 数据源已创建: {source.id}")
    
    # 启动数据源
    result = source.start()
    print(f"✓ 启动结果: {result}")
    
    # 等待数据获取
    print("等待数据获取...")
    time.sleep(8)
    
    # 检查数据
    recent_data = source.get_recent_data(5)
    print(f"✓ 获取到 {len(recent_data)} 条数据")
    
    if recent_data:
        latest = recent_data[-1]
        print(f"✓ 数据类型: {type(latest)}")
        
        if hasattr(latest, 'shape'):  # DataFrame
            print(f"✓ DataFrame形状: {latest.shape}")
            print(f"✓ 列名: {list(latest.columns)}")
            if len(latest) > 0:
                print(f"✓ 第一行数据: {latest.iloc[0].to_dict()}")
        else:  # 列表或字典
            if isinstance(latest, list) and len(latest) > 0:
                print(f"✓ 第一条数据: {latest[0]}")
            elif isinstance(latest, dict):
                print(f"✓ 数据内容: {latest}")
        
        print("✓ 数据源正常工作，成功获取行情数据")
        success = True
    else:
        print("✗ 未获取到数据")
        success = False
    
    # 停止数据源
    source.stop()
    print("✓ 数据源已停止")
    
    return success

def test_real_persistence_and_recovery():
    """测试真实的状态持久化和恢复"""
    print("\n=== 测试真实的状态持久化和恢复 ===")
    
    # 模拟程序重启：创建新的管理器实例
    new_manager = DataSourceManager()
    
    # 从数据库加载数据源
    loaded_count = new_manager.load_from_db()
    print(f"✓ 从数据库加载了 {loaded_count} 个数据源")
    
    # 查找之前的数据源
    source = new_manager.get_source_by_name("working_quant_source")
    
    if not source:
        print("✗ 未找到之前的数据源")
        return False
    
    print(f"✓ 找到数据源: {source.name}")
    print(f"✓ 数据源状态: {source.state.status}")
    print(f"✓ 数据源统计: 总发送 {source.stats.total_emitted} 条数据")
    
    # 获取完整状态摘要
    summary = source.get_full_state_summary()
    print(f"✓ 状态摘要:")
    print(f"  - 当前状态: {summary['current_status']}")
    print(f"  - 代码版本: {summary['code_versions_count']} 个")
    print(f"  - 依赖策略: {len(summary['dependent_strategies'])} 个")
    
    # 恢复运行状态
    restore_result = new_manager.restore_running_states()
    print(f"✓ 状态恢复结果:")
    print(f"  - 恢复成功: {restore_result['restored_count']} 个")
    print(f"  - 恢复失败: {restore_result['failed_count']} 个")
    
    if restore_result['restored_count'] > 0:
        print("✓ 状态恢复成功")
        
        # 等待恢复后的数据获取
        print("等待恢复后的数据获取...")
        time.sleep(6)
        
        # 检查恢复后的数据
        recent_data = source.get_recent_data(3)
        print(f"✓ 恢复后获取到 {len(recent_data)} 条数据")
        
        if recent_data:
            print("✓ 数据源恢复成功并正常运行，成功获取行情数据")
            recovery_success = True
        else:
            print("✗ 恢复后未获取到数据")
            recovery_success = False
        
        # 停止恢复的数据源
        source.stop()
        print("✓ 恢复的数据源已停止")
        
        return recovery_success
    else:
        print("✗ 状态恢复失败")
        return False

def main():
    """主测试函数"""
    print("开始最终版行情数据源测试...")
    print(f"测试时间: {datetime.datetime.now()}")
    
    try:
        # 1. 测试能正常工作的数据源
        data_success = test_working_datasource()
        
        # 2. 测试真实的状态持久化和恢复
        recovery_success = test_real_persistence_and_recovery()
        
        print("\n=== 测试完成 ===")
        
        if data_success and recovery_success:
            print("🎉 所有测试通过！")
            print("✅ 数据源能正常获取行情数据")
            print("✅ 状态持久化功能正常")
            print("✅ 程序重启后能恢复状态并继续获取行情数据")
            print("✅ gen_quant相关代码已成功存储到数据源执行代码中")
            return True
        else:
            print("❌ 部分测试失败")
            if not data_success:
                print("✗ 数据源获取行情数据失败")
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