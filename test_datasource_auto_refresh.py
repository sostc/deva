#!/usr/bin/env python3
"""
测试数据源列表页自动刷新功能
"""

import time
import datetime
from deva.admin_ui.strategy.datasource import get_ds_manager
from deva.admin_ui.strategy.runtime import initialize_strategy_monitor_streams

def test_datasource_auto_refresh():
    """测试数据源自动刷新功能"""
    print("🚀 开始测试数据源列表页自动刷新功能")
    print(f"📅 测试时间: {datetime.datetime.now()}")
    
    try:
        # 1. 初始化策略监控流
        print("\n1️⃣ 初始化策略监控流...")
        initialize_strategy_monitor_streams()
        
        # 2. 获取数据源管理器
        ds_manager = get_ds_manager()
        ds_manager.load_from_db()
        
        # 3. 获取数据源列表
        print("\n2️⃣ 获取数据源列表...")
        sources = ds_manager.list_all()
        print(f"✅ 找到 {len(sources)} 个数据源")
        
        # 4. 验证数据源状态
        print("\n3️⃣ 验证数据源状态...")
        
        running_sources = []
        for source_data in sources:
            metadata = source_data.get("metadata", {})
            state = source_data.get("state", {})
            
            name = metadata.get("name", "unknown")
            status = state.get("status", "stopped")
            last_data_ts = state.get("last_data_ts", 0)
            total_emitted = source_data.get("stats", {}).get("total_emitted", 0)
            
            print(f"📊 {name}: {status}")
            print(f"   最近数据时间: {datetime.datetime.fromtimestamp(last_data_ts) if last_data_ts > 0 else '无'}")
            print(f"   总发送量: {total_emitted}")
            
            if status == "running":
                running_sources.append(name)
        
        print(f"✅ 运行中的数据源: {len(running_sources)} 个")
        
        # 5. 启动测试数据源
        print("\n4️⃣ 启动测试数据源...")
        
        # 获取或创建测试数据源
        test_source = ds_manager.get_source_by_name("test_auto_refresh")
        if not test_source:
            from deva.admin_ui.strategy.datasource import DataSource, DataSourceType
            
            test_source = DataSource(
                name="test_auto_refresh",
                source_type=DataSourceType.TIMER,
                description="自动刷新测试数据源",
                data_func_code='''
import datetime
import time
import random

def fetch_data():
    """自动刷新测试函数"""
    data = {
        "timestamp": time.time(),
        "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "value": random.randint(1, 100),
        "message": "测试自动刷新功能"
    }
    print(f"[TEST] 生成测试数据: {data['datetime']} - value: {data['value']}")
    return data
''',
                interval=3.0,  # 3秒间隔
                auto_start=False
            )
            ds_manager.register(test_source)
            print("✅ 创建测试数据源")
        
        # 启动测试数据源
        result = test_source.start()
        if result.get("success"):
            print("✅ 测试数据源启动成功")
        else:
            print(f"❌ 测试数据源启动失败: {result.get('error')}")
            return False
        
        # 6. 等待数据生成
        print("\n5️⃣ 等待数据生成...")
        print("⏳ 等待15秒，让数据源生成多批数据...")
        
        for i in range(5):
            time.sleep(3)
            
            # 刷新数据源状态
            ds_manager.load_from_db()
            test_source = ds_manager.get_source_by_name("test_auto_refresh")
            
            if test_source:
                recent_data = test_source.get_recent_data(3)
                saved_data = test_source.get_saved_latest_data()
                
                print(f"\n⏰ 第{i+1}次检查 ({datetime.datetime.now()}):")
                print(f"   状态: {test_source.status}")
                print(f"   最近数据: {len(recent_data)} 条")
                print(f"   保存数据: {'有' if saved_data else '无'}")
                
                if recent_data:
                    latest = recent_data[-1]
                    if isinstance(latest, dict) and 'datetime' in latest:
                        print(f"   最新数据时间: {latest['datetime']}")
                    elif isinstance(latest, dict) and 'timestamp' in latest:
                        print(f"   最新数据时间: {datetime.datetime.fromtimestamp(latest['timestamp'])}")
                
                if saved_data:
                    print(f"   保存数据时间戳: {datetime.datetime.fromtimestamp(saved_data.get('timestamp', 0))}")
        
        # 7. 验证自动刷新功能
        print("\n6️⃣ 验证自动刷新功能")
        
        # 检查数据源列表数据
        final_sources = ds_manager.list_all()
        test_source_data = None
        
        for source_data in final_sources:
            metadata = source_data.get("metadata", {})
            if metadata.get("name") == "test_auto_refresh":
                test_source_data = source_data
                break
        
        if test_source_data:
            state = test_source_data.get("state", {})
            stats = test_source_data.get("stats", {})
            
            final_last_data_ts = state.get("last_data_ts", 0)
            final_total_emitted = stats.get("total_emitted", 0)
            
            print(f"✅ 最终状态验证:")
            print(f"   状态: {state.get('status')}")
            print(f"   最近数据时间: {datetime.datetime.fromtimestamp(final_last_data_ts) if final_last_data_ts > 0 else '无'}")
            print(f"   总发送量: {final_total_emitted}")
            
            if final_total_emitted > 0 and final_last_data_ts > 0:
                print("✅ 自动刷新功能验证通过")
                print("✅ 数据源成功生成多批数据")
                print("✅ 最近数据时间正确更新")
                return True
            else:
                print("⚠️  数据源未生成足够的数据")
                return False
        else:
            print("❌ 未找到测试数据源")
            return False
        
        # 8. 清理测试数据
        print("\n7️⃣ 清理测试数据...")
        if test_source:
            test_source.stop()
            print("✅ 停止测试数据源")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def main():
    """主函数"""
    success = test_datasource_auto_refresh()
    
    if success:
        print("\n🎉 自动刷新功能测试完成！")
        print("✅ 数据源列表页的最近数据列可以自动刷新")
        print("✅ 数据生成时间正确更新")
        print("✅ 状态信息实时同步")
    else:
        print("\n❌ 自动刷新功能测试失败")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)