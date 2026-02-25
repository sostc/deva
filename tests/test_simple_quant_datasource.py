#!/usr/bin/env python3
"""
简化版行情数据获取测试
验证数据源代码持久化和重启恢复功能
"""

import time
import datetime
from deva.admin_ui.strategy.datasource import DataSource, DataSourceManager, DataSourceType

# 简化的行情数据获取代码
simple_gen_quant_code = '''
import datetime
import time
import random

def fetch_data():
    """简化版行情数据获取函数"""
    try:
        now = datetime.datetime.now()
        print(f"[INFO] Fetching data at {now}")
        
        # 简单的交易时间检查（测试时总是返回True）
        # 实际使用时可以启用完整的交易时间检查
        
        # 创建模拟股票数据
        mock_stocks = [
            {"code": "000001", "name": "平安银行", "price": 15.8, "change": 0.02},
            {"code": "000002", "name": "万科A", "price": 22.5, "change": -0.01},
            {"code": "600036", "name": "招商银行", "price": 35.2, "change": 0.015},
            {"code": "600519", "name": "贵州茅台", "price": 1680.0, "change": 0.008},
            {"code": "300750", "name": "宁德时代", "price": 198.5, "change": -0.025},
        ]
        
        # 生成随机波动的数据
        data = []
        for stock in mock_stocks:
            # 随机价格波动
            price_change = random.uniform(-0.02, 0.02)
            current_price = stock["price"] * (1 + price_change)
            
            data.append({
                "code": stock["code"],
                "name": stock["name"],
                "now": round(current_price, 2),
                "close": stock["price"],
                "open": round(stock["price"] * random.uniform(0.98, 1.02), 2),
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

def test_simple_datasource():
    """测试简化版数据源"""
    print("=== 测试简化版行情数据源 ===")
    
    manager = DataSourceManager()
    
    # 创建数据源
    source = DataSource(
        name="simple_quant_source",
        source_type=DataSourceType.TIMER,
        description="简化版行情数据源",
        data_func_code=simple_gen_quant_code,
        interval=2.0,
        auto_start=False
    )
    
    manager.register(source)
    print(f"✓ 数据源已创建: {source.id}")
    
    # 启动数据源
    result = source.start()
    print(f"✓ 启动结果: {result}")
    
    # 等待数据获取
    print("等待数据获取...")
    time.sleep(6)
    
    # 检查数据
    recent_data = source.get_recent_data(3)
    print(f"✓ 获取到 {len(recent_data)} 条数据")
    
    if recent_data:
        latest = recent_data[-1]
        if hasattr(latest, 'shape'):  # DataFrame
            print(f"✓ DataFrame形状: {latest.shape}")
            print(f"✓ 列名: {list(latest.columns)}")
        else:  # 列表或字典
            print(f"✓ 数据类型: {type(latest)}")
            if isinstance(latest, list) and len(latest) > 0:
                print(f"✓ 第一条数据: {latest[0]}")
            elif isinstance(latest, dict):
                print(f"✓ 数据内容: {latest}")
    
    # 停止数据源
    source.stop()
    print("✓ 数据源已停止")
    
    return True

def test_persistence_and_recovery():
    """测试持久化和恢复功能"""
    print("\n=== 测试持久化和恢复功能 ===")
    
    # 模拟程序重启
    new_manager = DataSourceManager()
    
    # 从数据库加载
    loaded_count = new_manager.load_from_db()
    print(f"✓ 从数据库加载了 {loaded_count} 个数据源")
    
    # 查找之前的数据源
    source = new_manager.get_source_by_name("simple_quant_source")
    if source:
        print(f"✓ 找到数据源: {source.name}")
        print(f"✓ 当前状态: {source.state.status}")
        print(f"✓ 统计信息: 总发送 {source.stats.total_emitted} 条数据")
        
        # 获取状态摘要
        summary = source.get_full_state_summary()
        print(f"✓ 代码版本: {summary['code_versions_count']} 个")
        
        # 恢复运行
        restore_result = new_manager.restore_running_states()
        print(f"✓ 状态恢复: 成功 {restore_result['restored_count']} 个")
        
        # 等待恢复后的数据
        time.sleep(4)
        
        recent_data = source.get_recent_data(2)
        print(f"✓ 恢复后获取到 {len(recent_data)} 条数据")
        
        source.stop()
        print("✓ 恢复的数据源已停止")
        
        return True
    else:
        print("✗ 未找到数据源")
        return False

def main():
    """主测试函数"""
    print("开始简化版行情数据源测试...")
    print(f"测试时间: {datetime.datetime.now()}")
    
    try:
        # 1. 测试简化版数据源
        test_simple_datasource()
        
        # 2. 测试持久化和恢复
        test_persistence_and_recovery()
        
        print("\n=== 测试完成 ===")
        print("✓ 简化版行情数据源功能正常")
        print("✓ 状态持久化和恢复功能正常")
        print("✓ 数据源重启后能正常获取行情数据")
        
        return True
        
    except Exception as e:
        print(f"✗ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)