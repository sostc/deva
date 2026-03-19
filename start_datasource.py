#!/usr/bin/env python3
"""
启动数据源以测试注意力系统
"""

import sys

def start_datasource(datasource_name="历史行情回放"):
    """启动指定的数据源"""
    print(f"正在启动数据源: {datasource_name}")
    
    try:
        from deva.naja.datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        
        # 查找数据源
        datasources = ds_mgr.list_all() if hasattr(ds_mgr, 'list_all') else []
        target_ds = None
        
        for ds in datasources:
            name = getattr(ds, 'name', '')
            if datasource_name in name:
                target_ds = ds
                break
        
        if target_ds is None:
            print(f"❌ 未找到数据源: {datasource_name}")
            print("可用的数据源:")
            for ds in datasources:
                print(f"  - {getattr(ds, 'name', 'Unknown')}")
            return False
        
        # 启动数据源
        print(f"✅ 找到数据源: {getattr(target_ds, 'name', '')}")
        
        if hasattr(target_ds, 'start'):
            target_ds.start()
            print(f"✅ 数据源已启动")
        elif hasattr(ds_mgr, 'start_datasource'):
            ds_mgr.start_datasource(getattr(target_ds, 'id', None))
            print(f"✅ 数据源已启动")
        else:
            print(f"⚠️ 无法启动数据源，请手动在 Web UI 中启动")
            print(f"   访问: http://localhost:8080/dsadmin")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="启动数据源")
    parser.add_argument("--name", "-n", default="历史行情回放", 
                        help="数据源名称 (默认: 历史行情回放)")
    
    args = parser.parse_args()
    
    success = start_datasource(args.name)
    sys.exit(0 if success else 1)
