"""
绑定行情回放数据源到龙虾思想雷达策略
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva.naja.strategy import get_strategy_manager
from deva.naja.datasource import get_datasource_manager


def bind_replay_datasource():
    """绑定行情回放数据源"""
    
    strategy_mgr = get_strategy_manager()
    datasource_mgr = get_datasource_manager()
    
    # 查找策略
    strategy = strategy_mgr.get_by_name("龙虾思想雷达")
    if not strategy:
        print("[ERROR] 策略 '龙虾思想雷达' 不存在")
        return False
    
    print(f"[INFO] 找到策略: {strategy.name} (ID: {strategy.id})")
    print(f"[INFO] 当前类别: {getattr(strategy._metadata, 'category', '默认')}")
    print(f"[INFO] 当前绑定数据源: {getattr(strategy._metadata, 'bound_datasource_id', '无')}")
    
    # 查找行情回放数据源
    print("\n[INFO] 查找可用的数据源...")
    replay_ds = None
    
    for ds in datasource_mgr.list_all():
        ds_name = ds.name.lower()
        ds_type = getattr(ds._metadata, 'source_type', 'unknown')
        print(f"  - {ds.name} (类型: {ds_type}, ID: {ds.id})")
        
        # 匹配行情回放数据源
        if any(keyword in ds_name for keyword in ['replay', '回放', '行情', 'market', 'tick']):
            replay_ds = ds
            print(f"    ✓ 匹配到行情回放数据源")
            break
    
    if not replay_ds:
        print("\n[WARN] 未找到行情回放数据源")
        print("[INFO] 可用的数据源类型:")
        for ds in datasource_mgr.list_all():
            print(f"  - {ds.name}: {getattr(ds._metadata, 'source_type', 'unknown')}")
        return False
    
    print(f"\n[INFO] 将绑定数据源: {replay_ds.name} (ID: {replay_ds.id})")
    
    # 停止策略
    if strategy.is_running:
        print("[INFO] 停止策略...")
        strategy.stop()
    
    # 绑定数据源
    strategy._metadata.bound_datasource_id = replay_ds.id
    strategy.save()
    print(f"[SUCCESS] 已绑定数据源: {replay_ds.name}")
    
    # 启动策略
    print("[INFO] 启动策略...")
    start_result = strategy.start()
    
    if start_result.get("success"):
        print(f"[SUCCESS] 策略已启动并绑定到行情回放数据源")
        print(f"\n策略状态:")
        print(f"  名称: {strategy.name}")
        print(f"  类别: {getattr(strategy._metadata, 'category', '默认')}")
        print(f"  绑定数据源: {replay_ds.name} (ID: {replay_ds.id})")
        print(f"  状态: {'运行中' if strategy.is_running else '已停止'}")
        return True
    else:
        print(f"[ERROR] 策略启动失败: {start_result.get('error', '未知错误')}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("🦞 龙虾思想雷达 - 数据源绑定工具")
    print("=" * 60)
    print()
    
    success = bind_replay_datasource()
    
    print()
    print("=" * 60)
    if success:
        print("✅ 绑定完成!")
        print("=" * 60)
        print()
        print("使用说明:")
        print("  1. 启动naja: python -m deva.naja")
        print("  2. 访问策略管理: http://localhost:8080/strategyadmin")
        print("  3. 在'记忆系统'类别下查看'龙虾思想雷达'策略")
        print("  4. 查看思想雷达: http://localhost:8080/lobster")
    else:
        print("❌ 绑定失败")
        print("=" * 60)
        print()
        print("建议:")
        print("  1. 先创建行情回放数据源")
        print("  2. 确保数据源正在运行")
        print("  3. 重新运行此脚本")


if __name__ == "__main__":
    main()
