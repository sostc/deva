#!/usr/bin/env python3
"""
不重启 naja 动态创建和启动数据源
通过直接操作数据库和发送启动命令
"""

import sys
sys.path.insert(0, '/Users/spark/pycharmproject/deva')

import hashlib
import time
import json
from deva import NB, NW

def generate_datasource_id(name: str) -> str:
    """生成数据源唯一ID"""
    return hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]

def create_datasource_direct():
    """直接创建数据源到数据库"""
    
    # 数据源配置
    name = "实时时间戳数据源"
    datasource_id = generate_datasource_id(name)
    
    # 检查名称是否已存在
    db = NB('naja_datasources')
    for existing_id, existing_data in db.items():
        if isinstance(existing_data, dict):
            existing_name = existing_data.get('metadata', {}).get('name', '')
            if existing_name == name:
                print(f"数据源 '{name}' 已存在，ID: {existing_id}")
                return existing_id
    
    # 构建数据源记录
    datasource_record = {
        "metadata": {
            "id": datasource_id,
            "name": name,
            "description": "实时创建的时间戳数据源，每2秒生成一个时间戳",
            "tags": ["timer", "timestamp", "live"],
            "source_type": "timer",
            "config": {
                "interval": 2.0,
                "data_schema": {
                    "type": "timestamp",
                    "description": "时间戳数据",
                    "fields": [
                        {"name": "id", "type": "string", "description": "数据ID", "required": True},
                        {"name": "timestamp", "type": "float", "description": "当前时间戳", "required": True},
                        {"name": "datetime", "type": "string", "description": "格式化时间", "required": True}
                    ],
                    "example": {
                        "id": "ts_1773170000",
                        "timestamp": 1773170000.0,
                        "datetime": "2026-03-11 04:00:00"
                    }
                }
            },
            "interval": 2.0,
            "execution_mode": "timer",
            "scheduler_trigger": "interval",
            "cron_expr": "",
            "run_at": "",
            "event_source": "log",
            "event_condition": "",
            "event_condition_type": "contains",
            "created_at": time.time(),
            "updated_at": time.time(),
        },
        "state": {
            "status": "stopped",
            "start_time": 0,
            "last_activity_ts": 0,
            "error_count": 0,
            "last_error": "",
            "last_error_ts": 0,
            "run_count": 0,
            "last_data_ts": 0,
            "total_emitted": 0,
            "pid": 0,
        },
        "func_code": """def fetch_data():
    import time
    from datetime import datetime
    
    ts = time.time()
    dt = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    
    return {
        'id': f'ts_{int(ts)}',
        'timestamp': ts,
        'datetime': dt
    }
""",
        "was_running": False
    }
    
    # 保存到数据库
    db[datasource_id] = datasource_record
    
    print("=" * 60)
    print("✅ 数据源创建成功！")
    print("=" * 60)
    print(f"数据源ID: {datasource_id}")
    print(f"名称: {name}")
    print(f"类型: timer")
    print(f"间隔: 2秒")
    
    return datasource_id

def send_start_command(ds_id: str):
    """通过 NS 发送启动命令给 naja"""
    try:
        # 使用 NW 发送命令到 naja
        nw = NW('naja_command')
        command = {
            "action": "start_datasource",
            "datasource_id": ds_id,
            "timestamp": time.time()
        }
        nw.send(command)
        
        print(f"\n📤 已发送启动命令到 naja")
        print(f"数据源ID: {ds_id}")
        
    except Exception as e:
        print(f"\n⚠️ 发送命令失败: {e}")
        print("请手动在 naja Web 界面中启动数据源")

def verify_datasource(ds_id: str):
    """验证数据源是否创建成功"""
    db = NB('naja_datasources')
    ds_data = db.get(ds_id)
    
    if ds_data:
        print("\n" + "=" * 60)
        print("验证结果:")
        print("=" * 60)
        metadata = ds_data.get('metadata', {})
        state = ds_data.get('state', {})
        
        print(f"✅ 数据源存在于数据库中")
        print(f"  名称: {metadata.get('name')}")
        print(f"  类型: {metadata.get('source_type')}")
        print(f"  状态: {state.get('status')}")
        print(f"  代码长度: {len(ds_data.get('func_code', ''))} 字符")
        
        return True
    else:
        print(f"\n❌ 数据源 {ds_id} 不存在")
        return False

def list_all_datasources():
    """列出所有数据源"""
    db = NB('naja_datasources')
    
    print("\n" + "=" * 60)
    print("当前所有数据源:")
    print("=" * 60)
    
    count = 0
    for ds_id, ds_data in db.items():
        if isinstance(ds_data, dict):
            metadata = ds_data.get('metadata', {})
            state = ds_data.get('state', {})
            name = metadata.get('name', '未命名')
            source_type = metadata.get('source_type', 'unknown')
            status = state.get('status', 'unknown')
            
            print(f"\n{count + 1}. {name}")
            print(f"   ID: {ds_id}")
            print(f"   类型: {source_type}")
            print(f"   状态: {status}")
            
            count += 1
    
    print(f"\n总计: {count} 个数据源")

if __name__ == '__main__':
    print("不重启 naja 动态创建数据源")
    print("=" * 60)
    
    # 创建数据源
    ds_id = create_datasource_direct()
    
    # 验证
    verify_datasource(ds_id)
    
    # 列出所有数据源
    list_all_datasources()
    
    print("\n" + "=" * 60)
    print("说明:")
    print("=" * 60)
    print("数据源已保存到数据库，naja 会自动加载它")
    print("你可以：")
    print("1. 刷新 naja Web 界面查看新数据源")
    print("2. 在 Web 界面中点击'启动'按钮启动它")
    print("3. 或者等待 naja 自动恢复运行状态（如果 was_running 为 true）")
