"""数据字典 V2 自动恢复功能测试

测试场景:
1. 创建数据字典条目并启动
2. 模拟系统重启 (重新加载)
3. 验证自动恢复

"""

import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deva.admin_ui.dictionary.dictionary_v2 import (
    DictionaryManager,
    get_dictionary_manager,
    DICT_ENTRY_TABLE,
    DICT_PAYLOAD_TABLE,
)
from deva.admin_ui.common.recoverable import recovery_manager
from deva import NB


def clear_test_data():
    """清理测试数据"""
    entry_db = NB(DICT_ENTRY_TABLE)
    payload_db = NB(DICT_PAYLOAD_TABLE)
    
    keys_to_delete = list(entry_db.keys())
    for k in keys_to_delete:
        del entry_db[k]
    
    keys_to_delete = list(payload_db.keys())
    for k in keys_to_delete:
        del payload_db[k]
    
    print("测试数据已清理")


def test_basic_create_and_run():
    """测试基本创建和运行"""
    print("\n" + "=" * 60)
    print("测试1: 基本创建和运行")
    print("=" * 60)
    
    manager = get_dictionary_manager()
    
    func_code = '''
def fetch_data():
    import time
    return {
        "timestamp": time.time(),
        "message": "Hello from dictionary!",
        "data": [1, 2, 3, 4, 5]
    }
'''
    
    result = manager.create(
        name="test_dict_1",
        func_code=func_code,
        description="测试数据字典",
        schedule_type="interval",
        interval_seconds=10,
        enabled=False,
    )
    
    if not result["success"]:
        print(f"创建失败: {result.get('error')}")
        return None
    
    entry_id = result["id"]
    print(f"创建成功: id={entry_id}")
    
    entry = manager.get(entry_id)
    print(f"编译状态: compiled={entry.compiled_func is not None}")
    
    print("执行一次...")
    run_result = entry.run_once()
    print(f"执行结果: {run_result}")
    
    payload = entry.get_payload()
    print(f"获取数据: {payload}")
    
    return entry_id


def test_start_and_auto_recovery(entry_id: str):
    """测试启动和自动恢复"""
    print("\n" + "=" * 60)
    print("测试2: 启动和自动恢复")
    print("=" * 60)
    
    manager = get_dictionary_manager()
    entry = manager.get(entry_id)
    
    if not entry:
        print(f"条目不存在: {entry_id}")
        return
    
    print(f"启动前状态: status={entry.status}, was_running={entry.was_running}")
    
    print("启动条目...")
    start_result = entry.start()
    print(f"启动结果: {start_result}")
    
    time.sleep(1)
    
    print(f"启动后状态: status={entry.status}, was_running={entry.was_running}")
    
    print("\n模拟系统重启...")
    print("创建新的管理器实例...")
    
    from deva.admin_ui.dictionary.dictionary_v2 import DictionaryManager
    new_manager = DictionaryManager()
    
    print("从数据库加载...")
    count = new_manager.load_from_db()
    print(f"加载了 {count} 个条目")
    
    new_entry = new_manager.get(entry_id)
    if new_entry:
        print(f"加载后状态: status={new_entry.status}, was_running={new_entry.was_running}")
    
    print("\n恢复运行状态...")
    restore_result = new_manager.restore_running_states()
    print(f"恢复结果: {restore_result}")
    
    if new_entry:
        print(f"恢复后状态: status={new_entry.status}, was_running={new_entry.was_running}")
    
    print("\n停止条目...")
    stop_result = new_entry.stop()
    print(f"停止结果: {stop_result}")
    print(f"停止后状态: status={new_entry.status}, was_running={new_entry.was_running}")


def test_recovery_manager_integration():
    """测试 RecoveryManager 集成"""
    print("\n" + "=" * 60)
    print("测试3: RecoveryManager 集成")
    print("=" * 60)
    
    manager = get_dictionary_manager()
    
    func_code = '''
def fetch_data():
    import time
    return {"ts": time.time(), "value": 42}
'''
    
    result = manager.create(
        name="test_dict_2",
        func_code=func_code,
        schedule_type="interval",
        interval_seconds=60,
        enabled=True,
    )
    
    if result["success"]:
        entry_id = result["id"]
        print(f"创建并启动: id={entry_id}")
        
        entry = manager.get(entry_id)
        print(f"状态: status={entry.status}, was_running={entry.was_running}")
        
        time.sleep(1)
        
        print("\n获取恢复信息...")
        recovery_info = recovery_manager.get_recovery_info()
        print(f"恢复信息: {recovery_info}")
        
        entry.stop()


def test_daily_schedule():
    """测试每日定时调度"""
    print("\n" + "=" * 60)
    print("测试4: 每日定时调度")
    print("=" * 60)
    
    manager = get_dictionary_manager()
    
    func_code = '''
def fetch_data():
    import datetime
    return {"time": str(datetime.datetime.now())}
'''
    
    result = manager.create(
        name="test_daily_dict",
        func_code=func_code,
        schedule_type="daily",
        daily_time="03:00",
        enabled=False,
    )
    
    if result["success"]:
        entry_id = result["id"]
        entry = manager.get(entry_id)
        
        wait_seconds = entry._calculate_wait_seconds()
        print(f"下次执行等待时间: {wait_seconds:.0f} 秒 ({wait_seconds/3600:.2f} 小时)")
        
        manager.delete(entry_id)
        print("已删除测试条目")


def main():
    print("=" * 60)
    print("数据字典 V2 自动恢复功能测试")
    print("=" * 60)
    
    clear_test_data()
    
    try:
        entry_id = test_basic_create_and_run()
        
        if entry_id:
            test_start_and_auto_recovery(entry_id)
        
        test_recovery_manager_integration()
        
        test_daily_schedule()
        
    finally:
        print("\n" + "=" * 60)
        print("清理测试数据...")
        clear_test_data()
        print("测试完成")
        print("=" * 60)


if __name__ == "__main__":
    main()
