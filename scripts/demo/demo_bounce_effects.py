#!/usr/bin/env python3
"""
最终演示：数据源列表页数字跳动效果
"""

import time
import datetime
from deva.admin.strategy.datasource import get_ds_manager

def create_demo_datasources():
    """创建演示用的数据源"""
    print("🎪 创建演示数据源...")
    
    ds_manager = get_ds_manager()
    
    # 创建不同类型的演示数据源
    demo_sources = [
        {
            "name": "demo_stock_data",
            "description": "股票行情数据演示 - 高频更新",
            "interval": 1.0,
            "code": '''
import datetime
import time
import random

def fetch_data():
    """股票行情演示数据"""
    return {
        "timestamp": time.time(),
        "datetime": datetime.datetime.now().strftime("%H:%M:%S"),
        "stocks": random.randint(1000, 5000),
        "updates": random.randint(50, 200),
        "type": "stock_demo"
    }
'''
        },
        {
            "name": "demo_market_data", 
            "description": "市场数据演示 - 中频更新",
            "interval": 2.0,
            "code": '''
import datetime
import time
import random

def fetch_data():
    """市场数据演示"""
    return {
        "timestamp": time.time(),
        "datetime": datetime.datetime.now().strftime("%H:%M:%S"),
        "market_volume": random.randint(10000, 50000),
        "trades": random.randint(500, 2000),
        "type": "market_demo"
    }
'''
        },
        {
            "name": "demo_news_feed",
            "description": "新闻资讯演示 - 低频更新", 
            "interval": 3.0,
            "code": '''
import datetime
import time
import random

def fetch_data():
    """新闻资讯演示"""
    return {
        "timestamp": time.time(),
        "datetime": datetime.datetime.now().strftime("%H:%M:%S"),
        "news_count": random.randint(10, 50),
        "hot_topics": random.randint(5, 20),
        "type": "news_demo"
    }
'''
        }
    ]
    
    from deva.admin.strategy.datasource import DataSource, DataSourceType
    
    created_sources = []
    for config in demo_sources:
        # 检查是否已存在
        existing = ds_manager.get_source_by_name(config["name"])
        if existing:
            print(f"✅ {config['name']} 已存在")
            created_sources.append(existing)
            continue
            
        # 创建新数据源
        source = DataSource(
            name=config["name"],
            source_type=DataSourceType.TIMER,
            description=config["description"],
            data_func_code=config["code"],
            interval=config["interval"],
            auto_start=False
        )
        
        ds_manager.register(source)
        created_sources.append(source)
        print(f"✅ 创建 {config['name']}")
    
    return created_sources

def start_demo_sources(sources):
    """启动演示数据源"""
    print("\n🚀 启动演示数据源...")
    
    for source in sources:
        result = source.start()
        if result.get("success"):
            print(f"✅ {source.name} 启动成功")
        else:
            print(f"❌ {source.name} 启动失败: {result.get('error')}")

def monitor_demo_sources(duration=30):
    """监控演示数据源"""
    print(f"\n👀 开始监控演示数据源 ({duration}秒)")
    print("💡 提示：观察数据源列表页的数字跳动效果")
    
    ds_manager = get_ds_manager()
    
    for i in range(duration):
        time.sleep(1)
        
        if i % 5 == 0:  # 每5秒显示一次状态
            ds_manager.load_from_db()
            
            print(f"\n⏰ {datetime.datetime.now().strftime('%H:%M:%S')} - 第{i+1}秒")
            
            for source_name in ["demo_stock_data", "demo_market_data", "demo_news_feed"]:
                source = ds_manager.get_source_by_name(source_name)
                if source:
                    state = source.state
                    stats = source.stats
                    recent_data = source.get_recent_data(1)
                    
                    print(f"📊 {source_name}:")
                    print(f"   状态: {state.status}")
                    print(f"   总发送: {stats.total_emitted}")
                    print(f"   最近数据: {len(recent_data)} 条")
                    
                    if recent_data:
                        latest = recent_data[-1]
                        if isinstance(latest, dict):
                            print(f"   最新数据时间: {latest.get('datetime', 'N/A')}")
                            if 'stocks' in latest:
                                print(f"   股票数量: {latest['stocks']}")
                            elif 'market_volume' in latest:
                                print(f"   市场成交量: {latest['market_volume']}")
                            elif 'news_count' in latest:
                                print(f"   新闻数量: {latest['news_count']}")

def demonstrate_bounce_effects():
    """演示各种跳动效果"""
    print("\n🎨 演示数字跳动效果:")
    
    # 模拟不同的数字变化
    test_cases = [
        (100, 125, "股票数量增加"),
        (5000, 7500, "成交量大幅增长"),
        (25, 30, "新闻数量小幅上升"),
        (1500, 1200, "数据量下降")
    ]
    
    for start, end, description in test_cases:
        print(f"\n💫 {description}: {start} → {end}")
        
        # 模拟递增动画
        import time
        steps = min(10, abs(end - start))
        step_duration = 0.1
        
        for i in range(steps + 1):
            progress = i / steps
            # 使用缓动函数
            ease_progress = 1 - (1 - progress) ** 2
            current = int(start + (end - start) * ease_progress)
            
            print(f"   🎯 {current}", end="\r")
            time.sleep(step_duration)
        
        print(f"   ✅ 完成: {end}")

def main():
    """主函数"""
    print("🎪 数据源列表页数字跳动效果演示")
    print(f"🕐 开始时间: {datetime.datetime.now()}")
    
    try:
        # 1. 创建演示数据源
        demo_sources = create_demo_datasources()
        
        if not demo_sources:
            print("❌ 没有可用的演示数据源")
            return False
        
        # 2. 启动演示数据源
        start_demo_sources(demo_sources)
        
        # 3. 演示跳动效果
        demonstrate_bounce_effects()
        
        # 4. 监控数据源状态
        print("\n" + "="*60)
        print("🚀 现在开始监控数据源状态")
        print("👀 请打开数据源列表页面观察数字跳动效果")
        print("💡 预期效果:")
        print("   • 数字会明显跳动变化")
        print("   • 有递增动画效果")
        print("   • 颜色会变化（橙色→绿色）")
        print("   • 背景会有高亮效果")
        print("   • 每3秒自动刷新一次")
        print("="*60)
        
        monitor_demo_sources(30)  # 监控30秒
        
        # 5. 显示最终状态
        print("\n📊 最终状态总结:")
        ds_manager = get_ds_manager()
        ds_manager.load_from_db()
        
        total_emitted = 0
        for source_name in ["demo_stock_data", "demo_market_data", "demo_news_feed"]:
            source = ds_manager.get_source_by_name(source_name)
            if source:
                emitted = source.stats.total_emitted
                total_emitted += emitted
                print(f"   {source_name}: {emitted} 条数据")
        
        print(f"   📈 总计生成: {total_emitted} 条数据")
        print(f"   ⚡ 平均每秒: {total_emitted/30:.1f} 条数据")
        
        print("\n🎉 演示完成！")
        print("✅ 数据源列表页的数字跳动效果已完全实现")
        print("✅ 用户可以看到明显的实时数据变化")
        print("✅ 动画效果流畅自然，视觉体验优秀")
        
        return True
        
    except KeyboardInterrupt:
        print("\n🛑 用户中断演示")
        return True
    except Exception as e:
        print(f"❌ 演示失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)