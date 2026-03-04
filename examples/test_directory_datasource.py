#!/usr/bin/env python3
"""
目录监控数据源测试脚本

功能：
1. 创建测试目录
2. 创建目录监控数据源
3. 启动数据源
4. 模拟文件操作（创建、修改、删除）
5. 验证监控结果
"""

import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deva.naja.datasource import get_datasource_manager


TEST_DIR = "/tmp/deva_test_directory_ds"
DS_NAME = "测试目录监控"


def setup():
    """创建测试环境"""
    os.makedirs(TEST_DIR, exist_ok=True)
    
    print(f"✅ 测试环境已创建")
    print(f"   测试目录: {TEST_DIR}")


def create_datasource():
    """创建目录监控数据源"""
    mgr = get_datasource_manager()
    
    for entry in mgr.list_all():
        if entry.name == DS_NAME:
            print(f"⚠️  数据源已存在，删除旧数据源")
            mgr.delete(entry.id)
            break
    
    result = mgr.create(
        name=DS_NAME,
        source_type="directory",
        config={
            "directory_path": TEST_DIR,
            "poll_interval": 0.5,
            "file_pattern": "*.txt",
            "recursive": False,
            "watch_events": ["created", "modified", "deleted"],
        },
        func_code='''import time
import os

def fetch_data(event):
    """
    处理目录变化事件
    """
    event_type = event.get("event")
    file_info = event.get("file_info", {})
    file_path = event.get("path", "")
    
    return {
        "event_type": event_type,
        "file_name": file_info.get("name", ""),
        "file_path": file_path,
        "file_size": file_info.get("size", 0),
        "timestamp": time.time(),
    }
''',
        description="测试目录监控数据源",
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


def test_file_operations(entry):
    """测试文件操作"""
    print(f"\n📝 开始测试文件操作...")
    
    results = {
        "created": [],
        "modified": [],
        "deleted": [],
    }
    
    test_file = os.path.join(TEST_DIR, "test.txt")
    
    print(f"\n1. 测试文件创建...")
    with open(test_file, "w") as f:
        f.write("Hello World")
    time.sleep(1)
    
    print(f"2. 测试文件修改...")
    with open(test_file, "a") as f:
        f.write("\nNew Line")
    time.sleep(1)
    
    print(f"3. 测试文件删除...")
    os.remove(test_file)
    time.sleep(1)
    
    print(f"\n📊 测试结果:")
    print(f"   运行状态: {entry.is_running}")
    print(f"   发送数据数: {entry.state.total_emitted}")
    
    if entry.state.total_emitted >= 3:
        print(f"   ✅ 测试通过！捕获了 {entry.state.total_emitted} 个事件")
    else:
        print(f"   ❌ 测试失败！预期至少 3 个事件，实际捕获 {entry.state.total_emitted} 个")
    
    if entry._latest_data:
        print(f"   最新数据: {entry._latest_data}")
    
    return entry.state.total_emitted >= 3


def test_recursive():
    """测试递归扫描"""
    print(f"\n" + "=" * 50)
    print("测试递归扫描子目录")
    print("=" * 50)
    
    sub_dir = os.path.join(TEST_DIR, "subdir")
    os.makedirs(sub_dir, exist_ok=True)
    
    mgr = get_datasource_manager()
    
    result = mgr.create(
        name="测试递归目录监控",
        source_type="directory",
        config={
            "directory_path": TEST_DIR,
            "poll_interval": 0.5,
            "file_pattern": "*.log",
            "recursive": True,
            "watch_events": ["created"],
        },
        func_code='''import time

def fetch_data(event):
    return {
        "event_type": event.get("event"),
        "file_name": event.get("file_info", {}).get("name", ""),
        "timestamp": time.time(),
    }
''',
        description="测试递归目录监控",
    )
    
    if not result.get("success"):
        print(f"❌ 创建失败")
        return False
    
    entry = mgr.get(result["id"])
    entry.start()
    time.sleep(1)
    
    print(f"✅ 递归监控已启动")
    
    print(f"\n在子目录创建文件...")
    sub_file = os.path.join(sub_dir, "test.log")
    with open(sub_file, "w") as f:
        f.write("test")
    time.sleep(1)
    
    print(f"在主目录创建文件...")
    main_file = os.path.join(TEST_DIR, "main.log")
    with open(main_file, "w") as f:
        f.write("test")
    time.sleep(1)
    
    success = entry.state.total_emitted >= 2
    
    print(f"\n📊 递归测试结果:")
    print(f"   发送数据数: {entry.state.total_emitted}")
    if success:
        print(f"   ✅ 递归扫描测试通过！")
    else:
        print(f"   ❌ 递归扫描测试失败！")
    
    mgr.delete(result["id"])
    os.remove(sub_file)
    os.remove(main_file)
    
    return success


def test_file_pattern():
    """测试文件匹配模式"""
    print(f"\n" + "=" * 50)
    print("测试文件匹配模式")
    print("=" * 50)
    
    mgr = get_datasource_manager()
    
    result = mgr.create(
        name="测试文件匹配",
        source_type="directory",
        config={
            "directory_path": TEST_DIR,
            "poll_interval": 0.5,
            "file_pattern": "*.csv",
            "recursive": False,
            "watch_events": ["created"],
        },
        func_code='''import time

def fetch_data(event):
    return {
        "event_type": event.get("event"),
        "file_name": event.get("file_info", {}).get("name", ""),
        "timestamp": time.time(),
    }
''',
        description="测试文件匹配模式",
    )
    
    if not result.get("success"):
        print(f"❌ 创建失败")
        return False
    
    entry = mgr.get(result["id"])
    entry.start()
    time.sleep(1)
    
    print(f"✅ 文件匹配监控已启动 (模式: *.csv)")
    
    print(f"\n创建匹配的文件...")
    csv_file = os.path.join(TEST_DIR, "test.csv")
    with open(csv_file, "w") as f:
        f.write("a,b,c")
    time.sleep(1)
    
    print(f"创建不匹配的文件...")
    txt_file = os.path.join(TEST_DIR, "ignore.txt")
    with open(txt_file, "w") as f:
        f.write("ignore")
    time.sleep(1)
    
    success = entry.state.total_emitted == 1
    
    print(f"\n📊 文件匹配测试结果:")
    print(f"   发送数据数: {entry.state.total_emitted}")
    if success:
        print(f"   ✅ 文件匹配测试通过！只捕获了 .csv 文件")
    else:
        print(f"   ❌ 文件匹配测试失败！预期 1 个事件")
    
    mgr.delete(result["id"])
    os.remove(csv_file)
    os.remove(txt_file)
    
    return success


def cleanup():
    """清理测试环境"""
    import shutil
    
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    
    mgr = get_datasource_manager()
    for entry in mgr.list_all():
        if "测试" in entry.name and "目录" in entry.name:
            mgr.delete(entry.id)
    
    print(f"\n🧹 测试环境已清理")


def main():
    print("=" * 50)
    print("目录监控数据源测试")
    print("=" * 50)
    
    setup()
    
    ds_id = create_datasource()
    if not ds_id:
        return
    
    entry = start_datasource(ds_id)
    if not entry:
        return
    
    time.sleep(1)
    
    test1 = test_file_operations(entry)
    test2 = test_recursive()
    test3 = test_file_pattern()
    
    cleanup()
    
    print("\n" + "=" * 50)
    print("测试总结")
    print("=" * 50)
    print(f"   文件操作测试: {'✅ 通过' if test1 else '❌ 失败'}")
    print(f"   递归扫描测试: {'✅ 通过' if test2 else '❌ 失败'}")
    print(f"   文件匹配测试: {'✅ 通过' if test3 else '❌ 失败'}")
    
    all_passed = test1 and test2 and test3
    print(f"\n   总体结果: {'✅ 全部通过' if all_passed else '❌ 部分失败'}")
    print("=" * 50)


if __name__ == "__main__":
    main()
