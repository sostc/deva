#!/usr/bin/env python3
"""
通过 HTTP API 启动数据源

这个脚本通过 naja 的 Web API 启动数据源，
确保在运行中的 naja 进程中启动
"""

import requests
import sys
import time

def start_datasource_via_api(datasource_name="历史行情回放"):
    """通过 API 启动数据源"""
    base_url = "http://localhost:8080"
    
    print(f"正在通过 API 启动数据源: {datasource_name}")
    print(f"API 地址: {base_url}")
    
    try:
        # 首先获取数据源列表
        response = requests.get(f"{base_url}/api/datasources", timeout=5)
        if response.status_code != 200:
            print(f"❌ 无法获取数据源列表: {response.status_code}")
            return False
        
        datasources = response.json()
        target_id = None
        
        for ds in datasources:
            if datasource_name in ds.get('name', ''):
                target_id = ds.get('id')
                print(f"✅ 找到数据源: {ds.get('name')} (ID: {target_id})")
                break
        
        if not target_id:
            print(f"❌ 未找到数据源: {datasource_name}")
            return False
        
        # 启动数据源
        response = requests.post(f"{base_url}/api/datasource/{target_id}/start", timeout=10)
        if response.status_code == 200:
            print(f"✅ 数据源启动成功")
            return True
        else:
            print(f"❌ 启动失败: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ 无法连接到 naja (http://localhost:8080)")
        print(f"   请确保 naja 正在运行")
        return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="通过 API 启动数据源")
    parser.add_argument("--name", "-n", default="历史行情回放", 
                        help="数据源名称 (默认: 历史行情回放)")
    
    args = parser.parse_args()
    
    success = start_datasource_via_api(args.name)
    sys.exit(0 if success else 1)
