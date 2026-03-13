#!/usr/bin/env python3
"""
检查 river 策略的执行状态
"""

from deva.naja.strategy import get_strategy_manager


def main():
    """主函数"""
    # 获取策略管理器
    st_mgr = get_strategy_manager()
    
    # 加载数据
    st_mgr.load_from_db()
    
    # 查找 river 策略
    river_strategies = [s for s in st_mgr.list_all() if 'river' in s.name.lower()]
    
    print(f"找到 {len(river_strategies)} 个 river 策略:")
    for s in river_strategies:
        print(f"  - {s.name} (ID: {s.id}, 运行中: {s.is_running})")
        
        # 检查策略的绑定数据源
        datasource_ids = getattr(s._metadata, 'bound_datasource_ids', [])
        if not datasource_ids:
            datasource_id = getattr(s._metadata, 'bound_datasource_id', '')
            if datasource_id:
                datasource_ids = [datasource_id]
        
        print(f"    绑定的数据源: {datasource_ids}")
        
        # 检查最近的执行结果
        recent_results = s.get_recent_results(limit=5)
        print(f"    最近执行结果: {len(recent_results)} 条")
        if recent_results:
            for i, result in enumerate(recent_results[:3]):
                print(f"      {i+1}. 时间: {result.get('timestamp')}, 成功: {result.get('success')}")


if __name__ == "__main__":
    main()
