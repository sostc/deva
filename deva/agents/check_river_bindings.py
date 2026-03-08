#!/usr/bin/env python3
"""检查所有 River 策略的绑定情况"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from deva.naja.strategy import get_strategy_manager
from deva.naja.datasource import get_datasource_manager

def check_all_river_strategies():
    """检查所有 River 策略"""
    print("=" * 80)
    print("【检查所有 River 策略绑定情况】")
    print("=" * 80)
    
    # 加载数据源
    ds_mgr = get_datasource_manager()
    ds_mgr.load_from_db()
    
    # 加载策略
    strategy_mgr = get_strategy_manager()
    strategy_mgr.load_from_db()
    
    # 获取行情回放数据源
    replay_ds = None
    for ds in ds_mgr.list_all():
        if "回放" in getattr(ds, "name", ""):
            replay_ds = ds
            break
    
    print(f"\n行情回放数据源：{replay_ds.name if replay_ds else '未找到'} (ID: {replay_ds.id if replay_ds else 'N/A'})")
    print("")
    
    # 获取所有 River 策略
    river_strategies = [s for s in strategy_mgr.list_all() if 'river' in s.name.lower()]
    
    print(f"找到 {len(river_strategies)} 个 River 策略：\n")
    
    bound_count = 0
    not_bound_count = 0
    
    for strategy in river_strategies:
        datasource_id = getattr(strategy._metadata, 'bound_datasource_id', '')
        
        # 获取数据源名称
        datasource_name = "未绑定"
        if datasource_id:
            ds = ds_mgr.get(datasource_id)
            if ds:
                datasource_name = ds.name
                if datasource_id == (replay_ds.id if replay_ds else None):
                    bound_count += 1
                    status = "✓"
                else:
                    not_bound_count += 1
                    status = "✗"
            else:
                datasource_name = f"未找到 (ID: {datasource_id})"
                not_bound_count += 1
                status = "✗"
        else:
            not_bound_count += 1
            status = "✗"
        
        print(f"{status} {strategy.name}")
        print(f"  绑定数据源：{datasource_name} (ID: {datasource_id})")
        print(f"  数据库中的原始绑定：{getattr(strategy._metadata, 'bound_datasource_id', 'N/A')}")
        print("")
    
    print("=" * 80)
    print(f"统计：{bound_count}/{len(river_strategies)} 个策略绑定到行情回放")
    print(f"      {not_bound_count}/{len(river_strategies)} 个策略未绑定到行情回放")
    print("=" * 80)

if __name__ == "__main__":
    try:
        check_all_river_strategies()
    except Exception as e:
        print(f"检查失败：{e}")
        import traceback
        traceback.print_exc()
