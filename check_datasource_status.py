#!/usr/bin/env python3
"""
检查数据源状态
"""

import time
from deva.naja.datasource import get_datasource_manager


def main():
    """主函数"""
    # 获取数据源管理器
    ds_mgr = get_datasource_manager()
    
    # 加载数据
    ds_mgr.load_from_db()
    
    # 查找行情回放数据源
    replay_ds = None
    for ds in ds_mgr.list_all():
        if '回放' in ds.name or 'replay' in ds.name.lower():
            replay_ds = ds
            break
    
    if replay_ds:
        print(f"检查数据源: {replay_ds.name} (ID: {replay_ds.id})")
        print(f"当前状态: 运行中={replay_ds.is_running}")
        
        # 启动数据源
        if not replay_ds.is_running:
            print("\n启动数据源...")
            start_result = replay_ds.start()
            print(f"启动结果: {start_result}")
            print(f"启动后状态: 运行中={replay_ds.is_running}")
        
        # 等待一段时间
        print("\n等待 5 秒...")
        time.sleep(5)
        
        # 检查状态
        print(f"5秒后状态: 运行中={replay_ds.is_running}")
        
        # 检查数据源的流
        print("\n检查数据源的流...")
        stream = replay_ds.get_stream()
        print(f"流对象: {stream}")
        
        # 尝试订阅流，看看是否有数据
        if stream:
            print("\n尝试订阅流，等待数据...")
            
            def on_data(data):
                print(f"收到数据: {data}")
            
            if hasattr(stream, "sink"):
                stream.sink(on_data)
            elif hasattr(stream, "subscribe"):
                stream.subscribe(on_data)
            
            # 等待一段时间
            print("等待 10 秒，接收数据...")
            time.sleep(10)


if __name__ == "__main__":
    main()
