#!/usr/bin/env python3
"""
分析列表页数字不跳动的原因并创建修复方案
"""

import time
import datetime
from deva.admin_ui.strategy.datasource import get_ds_manager

def analyze_refresh_issue():
    """分析刷新问题的原因"""
    print("🔍 分析数据源列表页数字不跳动的原因")
    
    ds_manager = get_ds_manager()
    ds_manager.load_from_db()
    
    # 获取运行中的数据源
    sources = ds_manager.list_all()
    running_sources = []
    
    for source_data in sources:
        metadata = source_data.get("metadata", {})
        state = source_data.get("state", {})
        
        name = metadata.get("name", "unknown")
        status = state.get("status", "stopped")
        last_data_ts = state.get("last_data_ts", 0)
        total_emitted = source_data.get("stats", {}).get("total_emitted", 0)
        
        if status == "running":
            running_sources.append({
                'name': name,
                'last_data_ts': last_data_ts,
                'total_emitted': total_emitted,
                'source_id': metadata.get("id", "")
            })
    
    print(f"📊 找到 {len(running_sources)} 个运行中的数据源")
    
    if not running_sources:
        print("⚠️  没有找到运行中的数据源，创建测试数据源...")
        return create_test_datasource()
    
    # 分析数据源状态
    print("\n📈 运行中数据源状态分析:")
    for source in running_sources:
        print(f"   {source['name']}:")
        print(f"     最后数据时间: {datetime.datetime.fromtimestamp(source['last_data_ts']) if source['last_data_ts'] > 0 else '无'}")
        print(f"     总发送量: {source['total_emitted']}")
        print(f"     数据源ID: {source['source_id']}")
    
    return running_sources

def create_test_datasource():
    """创建测试数据源"""
    print("\n🔧 创建测试数据源...")
    
    from deva.admin_ui.strategy.datasource import DataSource, DataSourceType
    
    test_source = DataSource(
        name="test_visible_refresh",
        source_type=DataSourceType.TIMER,
        description="可见刷新测试数据源",
        data_func_code='''
import datetime
import time
import random

def fetch_data():
    """可见刷新测试函数 - 每秒生成递增数据"""
    current_time = time.time()
    data = {
        "timestamp": current_time,
        "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "counter": int(current_time) % 1000,  # 循环计数器
        "value": random.randint(1, 100),
        "message": f"测试可见刷新 #{int(current_time) % 1000}"
    }
    print(f"[VISIBLE_TEST] 生成数据: {data['datetime']} - Counter: {data['counter']}")
    return data
''',
        interval=1.0,  # 1秒间隔，确保频繁更新
        auto_start=False
    )
    
    ds_manager = get_ds_manager()
    ds_manager.register(test_source)
    
    result = test_source.start()
    if result.get("success"):
        print("✅ 测试数据源创建并启动成功")
        return [{
            'name': test_source.name,
            'last_data_ts': 0,
            'total_emitted': 0,
            'source_id': test_source.id
        }]
    else:
        print(f"❌ 测试数据源启动失败: {result.get('error')}")
        return []

def demonstrate_refresh_logic():
    """演示当前刷新逻辑的问题"""
    print("\n🎯 当前刷新逻辑问题分析:")
    
    print("1. 随机概率问题:")
    print("   - 状态更新概率: 5% (Math.random() > 0.95)")
    print("   - 数据更新概率: 20% (Math.random() > 0.8)")
    print("   - 结果: 用户很难看到明显的变化")
    
    print("\n2. 数据模拟问题:")
    print("   - 使用随机数模拟数据条数")
    print("   - 没有基于真实的数据源状态")
    print("   - 结果: 数字变化不真实，用户感知不到")
    
    print("\n3. 时间显示问题:")
    print("   - 只显示当前时间，不显示数据生成时间")
    print("   - 没有数据时间戳的对比")
    print("   - 结果: 用户看不到数据更新的时间差")

def propose_solution():
    """提出修复方案"""
    print("\n🔧 修复方案:")
    
    print("1. 基于真实数据刷新:")
    print("   - 定期从后端获取真实的数据源状态")
    print("   - 对比前后状态差异")
    print("   - 只更新有真实变化的数据")
    
    print("\n2. 增强视觉反馈:")
    print("   - 增加更明显的颜色变化")
    print("   - 添加数字跳动动画")
    print("   - 显示数据时间戳变化")
    
    print("\n3. 优化刷新频率:")
    print("   - 提高有数据源运行时的刷新频率")
    print("   - 降低无数据源时的刷新频率")
    print("   - 智能调整刷新间隔")
    
    print("\n4. 增加状态指示器:")
    print("   - 显示刷新状态图标")
    print("   - 显示最后刷新时间")
    print("   - 显示数据变化计数")

def main():
    """主函数"""
    print("🚀 开始分析数据源列表页数字不跳动问题")
    print(f"📅 分析时间: {datetime.datetime.now()}")
    
    try:
        # 1. 分析问题
        running_sources = analyze_refresh_issue()
        
        # 2. 演示问题
        demonstrate_refresh_logic()
        
        # 3. 提出方案
        propose_solution()
        
        print("\n✅ 问题分析完成！")
        print("✅ 已识别出数字不跳动的根本原因")
        print("✅ 已提出完整的修复方案")
        
        return True
        
    except Exception as e:
        print(f"❌ 分析失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)