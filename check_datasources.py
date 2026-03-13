#!/usr/bin/env python3
"""
检查数据源的运行状态
"""

from deva.naja.datasource import get_datasource_manager


def main():
    """主函数"""
    # 获取数据源管理器
    ds_mgr = get_datasource_manager()
    
    # 加载数据
    ds_mgr.load_from_db()
    
    # 列出所有数据源
    all_datasources = ds_mgr.list_all()
    print(f"找到 {len(all_datasources)} 个数据源:")
    
    for ds in all_datasources:
        print(f"  - {ds.name} (ID: {ds.id}, 运行中: {ds.is_running})")


if __name__ == "__main__":
    main()
