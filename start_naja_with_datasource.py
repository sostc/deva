#!/usr/bin/env python3
"""
启动 naja 并自动启动历史行情回放数据源
"""

import subprocess
import time
import sys
import signal
import os

def start_naja():
    """启动 naja 并捕获日志"""
    print("=" * 70)
    print("启动 naja 并自动启动数据源")
    print("=" * 70)
    
    # 先停止现有的 naja
    print("\n1. 停止现有的 naja 进程...")
    subprocess.run(["pkill", "-f", "python -m deva.naja"], capture_output=True)
    time.sleep(2)
    
    # 启动 naja
    print("2. 启动 naja...")
    log_file = "/tmp/naja_attention.log"
    
    # 使用 nohup 让进程在后台运行
    cmd = f"cd /Users/spark/pycharmproject/deva && nohup python -m deva.naja --attention > {log_file} 2>&1 &"
    os.system(cmd)
    
    print(f"   naja 已在后台启动")
    print(f"   日志文件: {log_file}")
    
    # 等待 naja 启动
    print("\n3. 等待 naja 启动完成...")
    time.sleep(5)
    
    # 检查是否启动成功
    result = subprocess.run(
        ["ps", "aux"], 
        capture_output=True, 
        text=True
    )
    
    if "python -m deva.naja" not in result.stdout:
        print("❌ naja 启动失败")
        return False
    
    print("✅ naja 启动成功")
    
    # 启动数据源
    print("\n4. 启动历史行情回放数据源...")
    time.sleep(3)
    
    # 通过导入方式启动数据源
    try:
        from deva.naja.datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        datasources = ds_mgr.list_all() if hasattr(ds_mgr, 'list_all') else []
        
        for ds in datasources:
            name = getattr(ds, 'name', '')
            if '历史行情回放' in name:
                print(f"   找到数据源: {name}")
                if hasattr(ds, 'start'):
                    ds.start()
                    print(f"   ✅ 数据源已启动")
                    break
    except Exception as e:
        print(f"   ⚠️ 启动数据源时出错: {e}")
        print(f"   请手动在 Web UI 中启动")
    
    print("\n" + "=" * 70)
    print("启动完成！")
    print("=" * 70)
    print(f"\n查看日志: tail -f {log_file}")
    print(f"访问 UI: http://localhost:8080/attentionadmin")
    print(f"数据源管理: http://localhost:8080/dsadmin")
    
    return True

if __name__ == "__main__":
    success = start_naja()
    sys.exit(0 if success else 1)
