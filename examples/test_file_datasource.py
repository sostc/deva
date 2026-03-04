#!/usr/bin/env python3
"""
文件监控数据源测试脚本

功能：
1. 创建测试日志文件
2. 创建文件监控数据源
3. 启动数据源
4. 模拟日志写入
5. 查看监控结果
"""

import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deva.naja.datasource import get_datasource_manager


LOG_DIR = "/tmp/deva_test_logs"
LOG_FILE = os.path.join(LOG_DIR, "test.log")
DS_NAME = "测试日志监控"


def setup():
    """创建测试环境"""
    os.makedirs(LOG_DIR, exist_ok=True)
    
    with open(LOG_FILE, "w") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 测试日志文件创建\n")
    
    print(f"✅ 测试环境已创建")
    print(f"   日志文件: {LOG_FILE}")


def create_datasource():
    """创建文件监控数据源"""
    mgr = get_datasource_manager()
    
    for entry in mgr.list_all():
        if entry.name == DS_NAME:
            print(f"⚠️  数据源已存在，删除旧数据源")
            mgr.delete(entry.id)
            break
    
    result = mgr.create(
        name=DS_NAME,
        source_type="file",
        config={
            "file_path": LOG_FILE,
            "poll_interval": 0.1,
            "delimiter": "\n",
            "read_mode": "tail",
        },
        func_code='''# 文件数据源处理函数
import time

def fetch_data(line):
    """
    处理文件中的一行数据
    """
    if line and line.strip():
        return {
            "content": line.strip(),
            "timestamp": time.time(),
            "length": len(line.strip()),
        }
    return None
''',
        description="监控测试日志文件变化",
    )
    
    if result.get("success"):
        print(f"✅ 数据源创建成功: {result['id']}")
        return result["id"]
    else:
        print(f"❌ 数据源创建失败: {result.get('error')}")
        return None


def start_datasource(ds_id):
    """启动数据源"""
    mgr = get_datasource_manager()
    entry = mgr.get(ds_id)
    
    if not entry:
        print(f"❌ 数据源不存在: {ds_id}")
        return None
    
    result = entry.start()
    if result.get("success"):
        print(f"✅ 数据源已启动")
        return entry
    else:
        print(f"❌ 启动失败: {result.get('error')}")
        return None


def write_logs(count=10, interval=0.5):
    """模拟写入日志"""
    print(f"\n📝 开始写入 {count} 条日志...")
    
    for i in range(count):
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 测试消息 {i+1}\n")
        print(f"   写入: 测试消息 {i+1}")
        time.sleep(interval)
    
    print(f"✅ 日志写入完成")


def check_status(entry):
    """检查数据源状态"""
    print(f"\n📊 数据源状态:")
    print(f"   运行状态: {entry.is_running}")
    print(f"   发送数据数: {entry.state.total_emitted}")
    print(f"   最后数据时间: {entry.state.last_data_ts}")
    
    if entry._latest_data:
        print(f"   最新数据: {entry._latest_data}")


def main():
    print("=" * 50)
    print("文件监控数据源测试")
    print("=" * 50)
    
    setup()
    
    ds_id = create_datasource()
    if not ds_id:
        return
    
    entry = start_datasource(ds_id)
    if not entry:
        return
    
    time.sleep(1)
    
    write_logs(count=10, interval=0.3)
    
    time.sleep(1)
    
    check_status(entry)
    
    print("\n" + "=" * 50)
    print("测试完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
