#!/usr/bin/env python3
"""
启动 river 策略和行情回放数据源
"""

import time
from deva.naja.datasource import get_datasource_manager
from deva.naja.strategy import get_strategy_manager


def main():
    """主函数"""
    print("=" * 80)
    print("启动 River 策略和行情回放数据源")
    print("=" * 80)
    
    # 获取管理器
    print("获取数据源管理器...")
    ds_mgr = get_datasource_manager()
    print("获取策略管理器...")
    st_mgr = get_strategy_manager()
    
    # 加载数据
    print("加载数据源数据...")
    ds_mgr.load_from_db()
    print("加载策略数据...")
    st_mgr.load_from_db()
    
    # 列出所有数据源
    all_ds = ds_mgr.list_all()
    print(f"\n所有数据源 ({len(all_ds)}):")
    for ds in all_ds:
        print(f"  - {ds.name} (ID: {ds.id}, 运行中: {ds.is_running})")
    
    # 启动行情回放数据源
    print("\n1. 启动行情回放数据源...")
    replay_ds = None
    for ds in all_ds:
        if '回放' in ds.name or 'replay' in ds.name.lower():
            replay_ds = ds
            break
    
    if replay_ds:
        print(f"   找到数据源: {replay_ds.name} (ID: {replay_ds.id})")
        start_result = replay_ds.start()
        print(f"   启动结果: {start_result}")
        if start_result.get('success'):
            print("   ✅ 行情回放数据源已启动")
        else:
            print(f"   ❌ 行情回放数据源启动失败: {start_result.get('error', '未知错误')}")
    else:
        print("   ⚠️  未找到行情回放数据源")
    
    # 启动 river 策略
    print("\n2. 启动 River 策略...")
    river_strategies = [s for s in st_mgr.list_all() if 'river' in s.name.lower()]
    print(f"   找到 {len(river_strategies)} 个 river 策略")
    
    started_count = 0
    failed_count = 0
    
    for strategy in river_strategies:
        print(f"   - {strategy.name} (ID: {strategy.id})")
        print(f"     绑定的数据源: {getattr(strategy._metadata, 'bound_datasource_ids', [])}")
        start_result = strategy.start()
        print(f"     启动结果: {start_result}")
        if start_result.get('success'):
            print(f"     ✅ 启动成功")
            started_count += 1
        else:
            print(f"     ❌ 启动失败: {start_result.get('error', '未知错误')}")
            failed_count += 1
        time.sleep(0.5)  # 避免并发启动导致的问题
    
    # 再次检查状态
    print("\n3. 检查启动后状态...")
    for strategy in river_strategies:
        print(f"   - {strategy.name}: 运行中={strategy.is_running}")
    
    # 打印结果
    print("\n" + "=" * 80)
    print("启动结果:")
    print(f"  总策略数: {len(river_strategies)}")
    print(f"  启动成功: {started_count}")
    print(f"  启动失败: {failed_count}")


if __name__ == "__main__":
    main()