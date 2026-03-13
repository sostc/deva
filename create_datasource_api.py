#!/usr/bin/env python3
"""
通过 API 动态创建数据源（无需重启 naja）
"""

import requests
import json

# API 基础 URL
BASE_URL = "http://localhost:8080/api"

# 数据源配置
datasource_config = {
    "name": "API时间戳数据源",
    "description": "通过API动态创建的时间戳数据源，每2秒生成一个时间戳",
    "source_type": "timer",
    "interval": 2.0,
    "execution_mode": "timer",
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
    "tags": ["timer", "timestamp", "api"]
}

def create_datasource():
    """创建数据源"""
    url = f"{BASE_URL}/datasources"
    
    try:
        response = requests.post(url, json=datasource_config, timeout=10)
        result = response.json()
        
        print("=" * 60)
        print("创建结果:")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        if result.get('success'):
            ds_id = result.get('id')
            print(f"\n✅ 数据源创建成功！")
            print(f"数据源ID: {ds_id}")
            
            # 启动数据源
            start_result = start_datasource(ds_id)
            return result
        else:
            print(f"\n❌ 创建失败: {result.get('error')}")
            return result
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return None

def start_datasource(ds_id):
    """启动数据源"""
    url = f"{BASE_URL}/datasources/{ds_id}/start"
    
    try:
        response = requests.post(url, timeout=10)
        result = response.json()
        
        print("\n" + "=" * 60)
        print("启动结果:")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        if result.get('success'):
            print(f"\n✅ 数据源启动成功！")
            print(f"现在每2秒会生成一个时间戳")
        else:
            print(f"\n❌ 启动失败: {result.get('error')}")
        
        return result
        
    except Exception as e:
        print(f"❌ 启动请求失败: {e}")
        return None

def list_datasources():
    """列出所有数据源"""
    url = f"{BASE_URL}/datasources"
    
    try:
        response = requests.get(url, timeout=10)
        result = response.json()
        
        print("\n" + "=" * 60)
        print("当前所有数据源:")
        print("=" * 60)
        
        if result.get('success'):
            datasources = result.get('datasources', [])
            for ds in datasources:
                print(f"ID: {ds.get('id')}")
                print(f"  名称: {ds.get('name')}")
                print(f"  类型: {ds.get('source_type')}")
                print(f"  状态: {ds.get('status')}")
                print()
        
        return result
        
    except Exception as e:
        print(f"❌ 列表请求失败: {e}")
        return None

if __name__ == '__main__':
    print("通过 API 动态创建数据源")
    print("=" * 60)
    
    # 创建数据源
    result = create_datasource()
    
    # 列出所有数据源
    list_datasources()
