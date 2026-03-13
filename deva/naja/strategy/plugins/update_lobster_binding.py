"""
直接更新数据库，绑定行情回放到龙虾思想雷达策略
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

from deva import NB


def update_strategy_binding():
    """更新策略绑定"""
    
    # 打开策略表
    db = NB('naja_strategies')
    
    print("[INFO] 查找龙虾思想雷达策略...")
    
    # 查找策略
    strategy_key = None
    strategy_data = None
    
    for key, value in db.items():
        if isinstance(value, dict) and value.get('metadata', {}).get('name') == '龙虾思想雷达':
            strategy_key = key
            strategy_data = value
            print(f"[INFO] 找到策略: {key}")
            break
    
    if not strategy_key:
        print("[ERROR] 策略 '龙虾思想雷达' 不存在")
        return False
    
    # 查找行情回放数据源
    ds_db = NB('naja_datasources')
    replay_ds_id = None
    replay_ds_name = None
    
    print("\n[INFO] 查找行情回放数据源...")
    for key, value in ds_db.items():
        if isinstance(value, dict):
            ds_name = value.get('metadata', {}).get('name', '').lower()
            ds_type = value.get('metadata', {}).get('source_type', '')
            print(f"  - {value.get('metadata', {}).get('name')} (类型: {ds_type})")
            
            if any(keyword in ds_name for keyword in ['replay', '回放', '行情', 'market']):
                replay_ds_id = key
                replay_ds_name = value.get('metadata', {}).get('name')
                print(f"    ✓ 匹配到行情回放数据源: {replay_ds_name}")
                break
    
    if not replay_ds_id:
        print("\n[WARN] 未找到行情回放数据源")
        print("[INFO] 请先在naja中创建行情回放数据源")
        return False
    
    # 更新策略绑定
    print(f"\n[INFO] 绑定数据源: {replay_ds_name} (ID: {replay_ds_id})")
    
    strategy_data['metadata']['bound_datasource_id'] = replay_ds_id
    strategy_data['updated_at'] = __import__('time').time()
    
    # 保存回数据库
    db[strategy_key] = strategy_data
    
    print(f"[SUCCESS] 策略绑定已更新")
    print(f"\n策略信息:")
    print(f"  名称: {strategy_data['metadata']['name']}")
    print(f"  类别: {strategy_data['metadata'].get('category', '默认')}")
    print(f"  绑定数据源: {replay_ds_name} (ID: {replay_ds_id})")
    print(f"  状态: {strategy_data['state'].get('status', 'unknown')}")
    
    return True


def main():
    """主函数"""
    print("=" * 60)
    print("🦞 龙虾思想雷达 - 数据源绑定工具")
    print("=" * 60)
    print()
    
    success = update_strategy_binding()
    
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
        print()
        print("注意: 绑定后需要重启naja才能生效")
    else:
        print("❌ 绑定失败")
        print("=" * 60)


if __name__ == "__main__":
    main()
