#!/usr/bin/env python3
"""
测试行情回放数据源启动流程
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from deva.naja.datasource import get_datasource_manager
from deva.naja.strategy import get_strategy_manager

def test_datasource_startup():
    """测试数据源启动"""
    print("=" * 80)
    print("【测试行情回放数据源启动流程】")
    print("=" * 80)
    
    # 1. 加载数据源
    print("\n【步骤 1】加载数据源...")
    ds_mgr = get_datasource_manager()
    ds_mgr.load_from_db()
    
    # 2. 查找行情回放数据源
    print("\n【步骤 2】查找行情回放数据源...")
    replay_ds = None
    for ds in ds_mgr.list_all():
        ds_name = getattr(ds, "name", "")
        print(f"  - 数据源：{ds_name} (ID: {ds.id}, 状态：{'运行中' if ds.is_running else '已停止'})")
        if "回放" in ds_name or "replay" in ds_name.lower():
            replay_ds = ds
    
    if not replay_ds:
        print("  ✗ 未找到行情回放数据源")
        return False
    
    print(f"  ✓ 找到行情回放数据源：{replay_ds.name} (ID: {replay_ds.id})")
    
    # 3. 启动数据源
    print("\n【步骤 3】启动数据源...")
    if replay_ds.is_running:
        print(f"  ✓ 数据源已在运行中")
    else:
        start_result = replay_ds.start()
        if start_result.get('success'):
            print(f"  ✓ 数据源启动成功")
        else:
            print(f"  ✗ 数据源启动失败：{start_result.get('error', '')}")
            return False
    
    # 4. 验证数据源状态
    print("\n【步骤 4】验证数据源状态...")
    time.sleep(2)  # 等待启动
    
    # 重新获取数据源对象（可能需要刷新）
    replay_ds_refreshed = ds_mgr.get(replay_ds.id)
    if replay_ds_refreshed:
        print(f"  数据源状态：{'✓ 运行中' if replay_ds_refreshed.is_running else '✗ 已停止'}")
    else:
        print(f"  ✗ 无法获取数据源状态")
    
    # 5. 检查策略绑定
    print("\n【步骤 5】检查策略绑定...")
    strategy_mgr = get_strategy_manager()
    strategy_mgr.load_from_db()
    
    river_strategies = [s for s in strategy_mgr.list_all() if 'river' in s.name.lower()]
    print(f"  找到 {len(river_strategies)} 个 River 策略")
    
    for strategy in river_strategies[:3]:
        datasource_id = getattr(strategy._metadata, 'bound_datasource_id', '')
        print(f"  - {strategy.name}: 绑定数据源 ID={datasource_id}")
    
    print("\n" + "=" * 80)
    print("✓ 测试完成")
    print("=" * 80)
    
    return True

if __name__ == "__main__":
    try:
        test_datasource_startup()
    except Exception as e:
        print(f"测试失败：{e}")
        import traceback
        traceback.print_exc()
