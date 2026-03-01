"""数据迁移脚本

将老版本 admin_ui 的数据迁移到新版本 naja。

老版本表 (v1):
- data_sources -> naja_datasources
- tasks -> naja_tasks
- strategy_units -> naja_strategies
- data_dictionary_entries -> naja_dictionary_entries
- data_dictionary_payloads -> naja_dictionary_payloads

V2 版本表:
- data_sources_v2 -> naja_datasources
- tasks_v2 -> naja_tasks
- strategies_v2 -> naja_strategies
- dictionary_entries_v2 -> naja_dictionary_entries
- dictionary_payloads_v2 -> naja_dictionary_payloads
"""

import hashlib
import json
import time
from typing import Any, Dict, List

from deva import NB


def migrate_datasources_v1(dry_run: bool = False) -> dict:
    """迁移老版本数据源 (data_sources)"""
    print("\n" + "=" * 60)
    print("📡 迁移数据源 (v1)")
    print("=" * 60)
    
    old_db = NB("data_sources")
    old_data_db = NB("data_source_latest_data")
    new_db = NB("naja_datasources")
    new_data_db = NB("naja_ds_latest_data")
    
    stats = {"total": 0, "migrated": 0, "skipped": 0, "errors": []}
    
    for key, data in list(old_db.items()):
        stats["total"] += 1
        
        try:
            if not isinstance(data, dict):
                stats["skipped"] += 1
                continue
            
            metadata = data.get("metadata", {})
            state = data.get("state", {})
            stats_data = data.get("stats", {})
            
            entry_id = metadata.get("id", key)
            if not entry_id:
                entry_id = key
            
            if new_db.get(entry_id):
                print(f"  ⏭️  跳过已存在: {metadata.get('name', entry_id)}")
                stats["skipped"] += 1
                continue
            
            func_code = ""
            if "data_func_code" in metadata:
                func_code = metadata.get("data_func_code", "")
            elif "code" in metadata:
                func_code = metadata.get("code", "")
            elif "fetch_code" in metadata:
                func_code = metadata.get("fetch_code", "")
            
            source_type = metadata.get("source_type", "custom")
            if hasattr(source_type, "value"):
                source_type = source_type.value
            
            new_data = {
                "metadata": {
                    "id": entry_id,
                    "name": metadata.get("name", "unnamed"),
                    "description": metadata.get("description", ""),
                    "tags": metadata.get("tags", []),
                    "interval": metadata.get("interval", 5.0),
                    "source_type": source_type,
                    "config": metadata.get("config", {}),
                    "created_at": metadata.get("created_at", time.time()),
                    "updated_at": metadata.get("updated_at", time.time()),
                },
                "state": {
                    "status": "stopped",
                    "start_time": state.get("start_time", 0),
                    "last_activity_ts": state.get("last_data_ts", 0),
                    "last_data_ts": state.get("last_data_ts", 0),
                    "error_count": state.get("error_count", 0),
                    "last_error": state.get("last_error", ""),
                    "total_emitted": stats_data.get("total_emitted", 0),
                },
                "func_code": func_code,
                "was_running": False,
            }
            
            if not dry_run:
                new_db[entry_id] = new_data
            
            old_latest = old_data_db.get(f"{entry_id}_latest_data")
            if old_latest is None:
                old_latest = old_data_db.get(entry_id)
            if old_latest is not None and not dry_run:
                new_data_db[entry_id] = old_latest
            
            print(f"  ✅ 迁移: {metadata.get('name', entry_id)}")
            stats["migrated"] += 1
            
        except Exception as e:
            stats["errors"].append(f"{key}: {str(e)}")
            print(f"  ❌ 错误: {key} - {str(e)}")
    
    return stats


def migrate_tasks_v1(dry_run: bool = False) -> dict:
    """迁移老版本任务 (tasks)"""
    print("\n" + "=" * 60)
    print("⏰ 迁移任务 (v1)")
    print("=" * 60)
    
    old_db = NB("tasks")
    new_db = NB("naja_tasks")
    
    stats = {"total": 0, "migrated": 0, "skipped": 0, "errors": []}
    
    for name, info in list(old_db.items()):
        stats["total"] += 1
        
        try:
            if not isinstance(info, dict):
                stats["skipped"] += 1
                continue
            
            task_id = hashlib.md5(f"legacy:{name}".encode()).hexdigest()[:12]
            
            if new_db.get(task_id):
                print(f"  ⏭️  跳过已存在: {name}")
                stats["skipped"] += 1
                continue
            
            task_type_raw = str(info.get("type", "interval")).strip().lower()
            task_type = "cron" if task_type_raw == "cron" else "interval"
            
            time_value = str(info.get("time", "60")).strip()
            interval_seconds = 60.0
            
            if task_type == "cron":
                if ":" in time_value:
                    try:
                        hour, minute = time_value.split(":", 1)
                        interval_seconds = int(hour) * 3600 + int(minute) * 60
                    except Exception:
                        pass
            else:
                try:
                    interval_seconds = float(time_value)
                except Exception:
                    pass
            
            job_code = str(info.get("job_code", "") or "")
            if job_code and "def execute" not in job_code and "async def execute" not in job_code:
                if "async def " in job_code:
                    import re
                    match = re.search(r'async def (\w+)', job_code)
                    if match:
                        func_name = match.group(1)
                        job_code += f"\n\nasync def execute(context=None):\n    return await {func_name}()\n"
            
            was_running = info.get("status") == "运行中"
            
            new_data = {
                "metadata": {
                    "id": task_id,
                    "name": name,
                    "description": str(info.get("description", "") or ""),
                    "tags": [],
                    "task_type": task_type,
                    "interval_seconds": interval_seconds,
                    "created_at": time.time(),
                    "updated_at": time.time(),
                },
                "state": {
                    "status": "stopped",
                    "start_time": 0,
                    "last_activity_ts": 0,
                    "error_count": 0,
                    "last_error": "",
                    "success_count": 0,
                    "failure_count": 0,
                    "last_run_time": 0,
                    "last_result": "",
                },
                "func_code": job_code,
                "was_running": False,
            }
            
            if not dry_run:
                new_db[task_id] = new_data
            
            print(f"  ✅ 迁移: {name}")
            stats["migrated"] += 1
            
        except Exception as e:
            stats["errors"].append(f"{name}: {str(e)}")
            print(f"  ❌ 错误: {name} - {str(e)}")
    
    return stats


def migrate_strategies_v1(dry_run: bool = False) -> dict:
    """迁移老版本策略 (strategy_units)"""
    print("\n" + "=" * 60)
    print("📊 迁移策略 (v1)")
    print("=" * 60)
    
    old_db = NB("strategy_units")
    old_results_db = NB("strategy_results")
    new_db = NB("naja_strategies")
    new_results_db = NB("naja_strategy_results")
    
    stats = {"total": 0, "migrated": 0, "skipped": 0, "errors": []}
    
    for key, data in list(old_db.items()):
        stats["total"] += 1
        
        try:
            if not isinstance(data, dict):
                stats["skipped"] += 1
                continue
            
            metadata = data.get("metadata", {})
            state = data.get("state", {})
            
            entry_id = metadata.get("id", key)
            if not entry_id:
                entry_id = key
            
            if new_db.get(entry_id):
                print(f"  ⏭️  跳过已存在: {metadata.get('name', entry_id)}")
                stats["skipped"] += 1
                continue
            
            processor_code = data.get("processor_code", "") or metadata.get("processor_code", "")
            func_code = processor_code
            
            if func_code and "def process" not in func_code:
                import re
                match = re.search(r'def (\w+)', func_code)
                if match:
                    func_name = match.group(1)
                    func_code = f"def process(data):\n    return {func_name}(data)\n\n" + func_code
            
            compute_mode = metadata.get("compute_mode", "record")
            window_size = metadata.get("window_size", 5)
            window_type = metadata.get("window_type", "sliding") or "sliding"
            window_interval = metadata.get("window_interval", "10s") or "10s"
            window_return_partial = metadata.get("window_return_partial", False)
            
            if window_type == "tumbling":
                compute_mode = "window"
                window_type = "sliding"
            
            new_data = {
                "metadata": {
                    "id": entry_id,
                    "name": metadata.get("name", "unnamed"),
                    "description": metadata.get("description", ""),
                    "tags": metadata.get("tags", []),
                    "bound_datasource_id": metadata.get("bound_datasource_id", ""),
                    "compute_mode": compute_mode,
                    "window_size": window_size,
                    "window_type": window_type,
                    "window_interval": window_interval,
                    "window_return_partial": window_return_partial,
                    "dictionary_profile_ids": metadata.get("dictionary_profile_ids", []),
                    "max_history_count": metadata.get("max_history_count", 100),
                    "created_at": metadata.get("created_at", time.time()),
                    "updated_at": metadata.get("updated_at", time.time()),
                },
                "state": {
                    "status": "stopped",
                    "start_time": state.get("start_time", 0),
                    "last_activity_ts": state.get("last_process_ts", 0),
                    "error_count": state.get("error_count", 0),
                    "last_error": state.get("last_error", ""),
                    "processed_count": state.get("processed_count", 0),
                    "output_count": state.get("output_count", 0),
                    "last_process_ts": state.get("last_process_ts", 0),
                },
                "func_code": func_code,
                "was_running": False,
            }
            
            if not dry_run:
                new_db[entry_id] = new_data
            
            for rkey, rdata in list(old_results_db.items()):
                if rkey.startswith(f"{entry_id}:") and not dry_run:
                    new_results_db[rkey] = rdata
            
            print(f"  ✅ 迁移: {metadata.get('name', entry_id)}")
            stats["migrated"] += 1
            
        except Exception as e:
            stats["errors"].append(f"{key}: {str(e)}")
            print(f"  ❌ 错误: {key} - {str(e)}")
    
    return stats


def migrate_dictionaries_v1(dry_run: bool = False) -> dict:
    """迁移老版本数据字典 (data_dictionary_entries)"""
    print("\n" + "=" * 60)
    print("📚 迁移数据字典 (v1)")
    print("=" * 60)
    
    old_entry_db = NB("data_dictionary_entries")
    old_payload_db = NB("data_dictionary_payloads")
    new_entry_db = NB("naja_dictionary_entries")
    new_payload_db = NB("naja_dictionary_payloads")
    
    stats = {"total": 0, "migrated": 0, "skipped": 0, "errors": []}
    
    for key, data in list(old_entry_db.items()):
        stats["total"] += 1
        
        try:
            if not isinstance(data, dict):
                stats["skipped"] += 1
                continue
            
            entry_id = data.get("id", key)
            if not entry_id:
                entry_id = key
            
            if new_entry_db.get(entry_id):
                print(f"  ⏭️  跳过已存在: {data.get('name', entry_id)}")
                stats["skipped"] += 1
                continue
            
            new_data = {
                "metadata": {
                    "id": entry_id,
                    "name": data.get("name", "unnamed"),
                    "description": data.get("description", ""),
                    "tags": [],
                    "dict_type": data.get("dict_type", "dimension"),
                    "schedule_type": data.get("schedule_type", "interval"),
                    "interval_seconds": data.get("interval_seconds", 300),
                    "daily_time": data.get("daily_time", "03:00"),
                    "created_at": data.get("created_at", time.time()),
                    "updated_at": data.get("updated_at", time.time()),
                },
                "state": {
                    "status": "stopped",
                    "start_time": 0,
                    "last_activity_ts": data.get("last_update_ts", 0),
                    "error_count": 0,
                    "last_error": data.get("last_error", ""),
                    "run_count": data.get("run_count", 0),
                    "last_update_ts": data.get("last_update_ts", 0),
                    "last_status": data.get("last_status", "never"),
                    "data_size_bytes": data.get("data_size_bytes", 0),
                    "payload_key": data.get("payload_key", ""),
                },
                "func_code": data.get("code", ""),
                "was_running": False,
            }
            
            if not dry_run:
                new_entry_db[entry_id] = new_data
            
            payload_key = data.get("payload_key", entry_id)
            old_payload = old_payload_db.get(payload_key)
            if old_payload is None:
                old_payload = old_payload_db.get(entry_id)
            if old_payload is not None and not dry_run:
                new_payload_db[entry_id] = old_payload
            
            print(f"  ✅ 迁移: {data.get('name', entry_id)}")
            stats["migrated"] += 1
            
        except Exception as e:
            stats["errors"].append(f"{key}: {str(e)}")
            print(f"  ❌ 错误: {key} - {str(e)}")
    
    return stats


def migrate_datasources_v2(dry_run: bool = False) -> dict:
    """迁移 V2 版本数据源"""
    print("\n" + "=" * 60)
    print("📡 迁移数据源 (v2)")
    print("=" * 60)
    
    old_db = NB("data_sources_v2")
    new_db = NB("naja_datasources")
    new_data_db = NB("naja_ds_latest_data")
    old_data_db = NB("ds_v2_latest_data")
    
    stats = {"total": 0, "migrated": 0, "skipped": 0, "errors": []}
    
    for key, data in list(old_db.items()):
        stats["total"] += 1
        
        try:
            if not isinstance(data, dict):
                stats["skipped"] += 1
                continue
            
            metadata = data.get("metadata", {})
            state = data.get("state", {})
            func_code = data.get("func_code", "")
            
            entry_id = metadata.get("id", key)
            
            if new_db.get(entry_id):
                print(f"  ⏭️  跳过已存在: {metadata.get('name', entry_id)}")
                stats["skipped"] += 1
                continue
            
            new_data = {
                "metadata": {
                    "id": entry_id,
                    "name": metadata.get("name", "unnamed"),
                    "description": metadata.get("description", ""),
                    "tags": metadata.get("tags", []),
                    "interval": metadata.get("interval", 5.0),
                    "created_at": metadata.get("created_at", time.time()),
                    "updated_at": metadata.get("updated_at", time.time()),
                },
                "state": {
                    "status": state.get("status", "stopped"),
                    "start_time": state.get("start_time", 0),
                    "last_activity_ts": state.get("last_data_ts", 0),
                    "error_count": state.get("error_count", 0),
                    "last_error": state.get("last_error", ""),
                    "total_emitted": state.get("total_emitted", 0),
                },
                "func_code": func_code,
                "was_running": False,
            }
            
            if not dry_run:
                new_db[entry_id] = new_data
            
            old_latest = old_data_db.get(entry_id)
            if old_latest is not None and not dry_run:
                new_data_db[entry_id] = old_latest
            
            print(f"  ✅ 迁移: {metadata.get('name', entry_id)}")
            stats["migrated"] += 1
            
        except Exception as e:
            stats["errors"].append(f"{key}: {str(e)}")
            print(f"  ❌ 错误: {key} - {str(e)}")
    
    return stats


def migrate_tasks_v2(dry_run: bool = False) -> dict:
    """迁移 V2 版本任务"""
    print("\n" + "=" * 60)
    print("⏰ 迁移任务 (v2)")
    print("=" * 60)
    
    old_db = NB("tasks_v2")
    new_db = NB("naja_tasks")
    new_history_db = NB("naja_task_history")
    old_history_db = NB("task_v2_history")
    
    stats = {"total": 0, "migrated": 0, "skipped": 0, "errors": []}
    
    for key, data in list(old_db.items()):
        stats["total"] += 1
        
        try:
            if not isinstance(data, dict):
                stats["skipped"] += 1
                continue
            
            metadata = data.get("metadata", {})
            state = data.get("state", {})
            func_code = data.get("func_code", "")
            
            entry_id = metadata.get("id", key)
            
            if new_db.get(entry_id):
                print(f"  ⏭️  跳过已存在: {metadata.get('name', entry_id)}")
                stats["skipped"] += 1
                continue
            
            new_data = {
                "metadata": {
                    "id": entry_id,
                    "name": metadata.get("name", "unnamed"),
                    "description": metadata.get("description", ""),
                    "tags": metadata.get("tags", []),
                    "task_type": metadata.get("task_type", "interval"),
                    "interval_seconds": metadata.get("interval_seconds", 60.0),
                    "created_at": metadata.get("created_at", time.time()),
                    "updated_at": metadata.get("updated_at", time.time()),
                },
                "state": {
                    "status": state.get("status", "stopped"),
                    "start_time": state.get("start_time", 0),
                    "last_activity_ts": state.get("last_run_time", 0),
                    "error_count": state.get("failure_count", 0),
                    "last_error": state.get("last_error", ""),
                    "success_count": state.get("success_count", 0),
                    "failure_count": state.get("failure_count", 0),
                    "last_run_time": state.get("last_run_time", 0),
                    "last_result": state.get("last_result", ""),
                },
                "func_code": func_code,
                "was_running": False,
            }
            
            if not dry_run:
                new_db[entry_id] = new_data
            
            for hkey, hdata in list(old_history_db.items()):
                if hkey.startswith(f"{entry_id}:") and not dry_run:
                    new_history_db[hkey] = hdata
            
            print(f"  ✅ 迁移: {metadata.get('name', entry_id)}")
            stats["migrated"] += 1
            
        except Exception as e:
            stats["errors"].append(f"{key}: {str(e)}")
            print(f"  ❌ 错误: {key} - {str(e)}")
    
    return stats


def migrate_strategies_v2(dry_run: bool = False) -> dict:
    """迁移 V2 版本策略"""
    print("\n" + "=" * 60)
    print("📊 迁移策略 (v2)")
    print("=" * 60)
    
    old_db = NB("strategies_v2")
    new_db = NB("naja_strategies")
    new_results_db = NB("naja_strategy_results")
    old_results_db = NB("strategy_v2_results")
    
    stats = {"total": 0, "migrated": 0, "skipped": 0, "errors": []}
    
    for key, data in list(old_db.items()):
        stats["total"] += 1
        
        try:
            if not isinstance(data, dict):
                stats["skipped"] += 1
                continue
            
            metadata = data.get("metadata", {})
            state = data.get("state", {})
            func_code = data.get("func_code", "")
            
            entry_id = metadata.get("id", key)
            
            if new_db.get(entry_id):
                print(f"  ⏭️  跳过已存在: {metadata.get('name', entry_id)}")
                stats["skipped"] += 1
                continue
            
            new_data = {
                "metadata": {
                    "id": entry_id,
                    "name": metadata.get("name", "unnamed"),
                    "description": metadata.get("description", ""),
                    "tags": metadata.get("tags", []),
                    "bound_datasource_id": metadata.get("bound_datasource_id", ""),
                    "compute_mode": metadata.get("compute_mode", "record"),
                    "window_size": metadata.get("window_size", 5),
                    "dictionary_profile_ids": metadata.get("dictionary_profile_ids", []),
                    "max_history_count": metadata.get("max_history_count", 100),
                    "created_at": metadata.get("created_at", time.time()),
                    "updated_at": metadata.get("updated_at", time.time()),
                },
                "state": {
                    "status": state.get("status", "stopped"),
                    "start_time": state.get("start_time", 0),
                    "last_activity_ts": state.get("last_process_ts", 0),
                    "error_count": state.get("error_count", 0),
                    "last_error": state.get("last_error", ""),
                    "processed_count": state.get("processed_count", 0),
                    "output_count": state.get("output_count", 0),
                    "last_process_ts": state.get("last_process_ts", 0),
                },
                "func_code": func_code,
                "was_running": False,
            }
            
            if not dry_run:
                new_db[entry_id] = new_data
            
            for rkey, rdata in list(old_results_db.items()):
                if rkey.startswith(f"{entry_id}:") and not dry_run:
                    new_results_db[rkey] = rdata
            
            print(f"  ✅ 迁移: {metadata.get('name', entry_id)}")
            stats["migrated"] += 1
            
        except Exception as e:
            stats["errors"].append(f"{key}: {str(e)}")
            print(f"  ❌ 错误: {key} - {str(e)}")
    
    return stats


def migrate_dictionaries_v2(dry_run: bool = False) -> dict:
    """迁移 V2 版本数据字典"""
    print("\n" + "=" * 60)
    print("📚 迁移数据字典 (v2)")
    print("=" * 60)
    
    old_entry_db = NB("dictionary_entries_v2")
    old_payload_db = NB("dictionary_payloads_v2")
    new_entry_db = NB("naja_dictionary_entries")
    new_payload_db = NB("naja_dictionary_payloads")
    
    stats = {"total": 0, "migrated": 0, "skipped": 0, "errors": []}
    
    for key, data in list(old_entry_db.items()):
        stats["total"] += 1
        
        try:
            if not isinstance(data, dict):
                stats["skipped"] += 1
                continue
            
            metadata = data.get("metadata", {})
            state = data.get("state", {})
            func_code = data.get("func_code", "")
            
            entry_id = metadata.get("id", key)
            
            if new_entry_db.get(entry_id):
                print(f"  ⏭️  跳过已存在: {metadata.get('name', entry_id)}")
                stats["skipped"] += 1
                continue
            
            new_data = {
                "metadata": {
                    "id": entry_id,
                    "name": metadata.get("name", "unnamed"),
                    "description": metadata.get("description", ""),
                    "tags": metadata.get("tags", []),
                    "schedule_type": metadata.get("schedule_type", "interval"),
                    "interval_seconds": metadata.get("interval_seconds", 300),
                    "daily_time": metadata.get("daily_time", "03:00"),
                    "created_at": metadata.get("created_at", time.time()),
                    "updated_at": metadata.get("updated_at", time.time()),
                },
                "state": {
                    "status": state.get("status", "stopped"),
                    "start_time": state.get("start_time", 0),
                    "last_activity_ts": state.get("last_update_ts", 0),
                    "error_count": state.get("error_count", 0),
                    "last_error": state.get("last_error", ""),
                    "run_count": 0,
                    "last_update_ts": state.get("last_update_ts", 0),
                    "last_status": state.get("last_status", "never"),
                    "data_size_bytes": state.get("data_size_bytes", 0),
                    "payload_key": state.get("payload_key", ""),
                },
                "func_code": func_code,
                "was_running": False,
            }
            
            if not dry_run:
                new_entry_db[entry_id] = new_data
            
            payload_key = state.get("payload_key", entry_id)
            old_payload = old_payload_db.get(payload_key)
            if old_payload is not None and not dry_run:
                new_payload_db[entry_id] = old_payload
            
            print(f"  ✅ 迁移: {metadata.get('name', entry_id)}")
            stats["migrated"] += 1
            
        except Exception as e:
            stats["errors"].append(f"{key}: {str(e)}")
            print(f"  ❌ 错误: {key} - {str(e)}")
    
    return stats


def run_migration(dry_run: bool = False, v1_only: bool = False, v2_only: bool = False):
    """执行完整迁移"""
    print("=" * 60)
    print("🚀 开始数据迁移")
    print("=" * 60)
    print(f"模式: {'预览模式 (不写入数据)' if dry_run else '正式迁移'}")
    
    results = {}
    
    if not v2_only:
        results["datasources_v1"] = migrate_datasources_v1(dry_run)
        results["tasks_v1"] = migrate_tasks_v1(dry_run)
        results["strategies_v1"] = migrate_strategies_v1(dry_run)
        results["dictionaries_v1"] = migrate_dictionaries_v1(dry_run)
    
    if not v1_only:
        results["datasources_v2"] = migrate_datasources_v2(dry_run)
        results["tasks_v2"] = migrate_tasks_v2(dry_run)
        results["strategies_v2"] = migrate_strategies_v2(dry_run)
        results["dictionaries_v2"] = migrate_dictionaries_v2(dry_run)
    
    print("\n" + "=" * 60)
    print("📊 迁移统计")
    print("=" * 60)
    
    total_migrated = 0
    total_skipped = 0
    total_errors = 0
    
    for module, stats in results.items():
        print(f"\n{module}:")
        print(f"  总数: {stats['total']}")
        print(f"  迁移: {stats['migrated']}")
        print(f"  跳过: {stats['skipped']}")
        if stats['errors']:
            print(f"  错误: {len(stats['errors'])}")
            for err in stats['errors']:
                print(f"    - {err}")
        
        total_migrated += stats['migrated']
        total_skipped += stats['skipped']
        total_errors += len(stats['errors'])
    
    print("\n" + "-" * 40)
    print(f"总计迁移: {total_migrated}")
    print(f"总计跳过: {total_skipped}")
    print(f"总计错误: {total_errors}")
    
    return results


def update_datasource_types():
    """更新现有数据源的类型字段"""
    print("\n" + "=" * 60)
    print("📡 更新数据源类型字段")
    print("=" * 60)
    
    old_db = NB("data_sources")
    new_db = NB("naja_datasources")
    
    updated = 0
    skipped = 0
    
    for key, new_data in list(new_db.items()):
        if not isinstance(new_data, dict):
            continue
        
        metadata = new_data.get("metadata", {})
        current_type = metadata.get("source_type", "")
        
        old_data = old_db.get(key)
        if not old_data:
            print(f"  ⏭️  跳过 (无旧数据): {metadata.get('name', key)}")
            skipped += 1
            continue
        
        old_metadata = old_data.get("metadata", {})
        old_source_type = old_metadata.get("source_type", "custom")
        
        if hasattr(old_source_type, "value"):
            old_source_type = old_source_type.value
        
        if current_type == old_source_type:
            print(f"  ⏭️  跳过 (类型相同): {metadata.get('name', key)} = {old_source_type}")
            skipped += 1
            continue
        
        metadata["source_type"] = old_source_type
        metadata["config"] = old_metadata.get("config", {})
        
        new_db[key] = new_data
        print(f"  ✅ 更新: {metadata.get('name', key)} -> {old_source_type}")
        updated += 1
    
    print(f"\n更新完成: {updated} 个, 跳过: {skipped} 个")


def update_dictionary_types():
    """更新现有数据字典的类型字段"""
    print("\n" + "=" * 60)
    print("📚 更新数据字典类型字段")
    print("=" * 60)
    
    old_db = NB("data_dictionary_entries")
    new_db = NB("naja_dictionary_entries")
    
    updated = 0
    skipped = 0
    
    for key, new_data in list(new_db.items()):
        if not isinstance(new_data, dict):
            continue
        
        metadata = new_data.get("metadata", {})
        current_type = metadata.get("dict_type", "")
        
        old_data = old_db.get(key)
        if not old_data:
            print(f"  ⏭️  跳过 (无旧数据): {metadata.get('name', key)}")
            skipped += 1
            continue
        
        old_dict_type = old_data.get("dict_type", "dimension")
        
        if current_type == old_dict_type:
            print(f"  ⏭️  跳过 (类型相同): {metadata.get('name', key)} = {old_dict_type}")
            skipped += 1
            continue
        
        metadata["dict_type"] = old_dict_type
        new_db[key] = new_data
        print(f"  ✅ 更新: {metadata.get('name', key)} -> {old_dict_type}")
        updated += 1
    
    print(f"\n更新完成: {updated} 个, 跳过: {skipped} 个")


def update_datasource_codes():
    """更新现有数据源的代码字段"""
    print("\n" + "=" * 60)
    print("📡 更新数据源代码字段")
    print("=" * 60)
    
    old_db = NB("data_sources")
    new_db = NB("naja_datasources")
    
    updated = 0
    skipped = 0
    
    for key, new_data in list(new_db.items()):
        if not isinstance(new_data, dict):
            continue
        
        metadata = new_data.get("metadata", {})
        current_code = new_data.get("func_code", "")
        
        old_data = old_db.get(key)
        if not old_data:
            print(f"  ⏭️  跳过 (无旧数据): {metadata.get('name', key)}")
            skipped += 1
            continue
        
        old_metadata = old_data.get("metadata", {})
        old_code = old_metadata.get("data_func_code", "") or old_metadata.get("code", "") or old_metadata.get("fetch_code", "")
        
        if current_code == old_code:
            print(f"  ⏭️  跳过 (代码相同): {metadata.get('name', key)}")
            skipped += 1
            continue
        
        new_data["func_code"] = old_code
        new_db[key] = new_data
        print(f"  ✅ 更新: {metadata.get('name', key)} -> {len(old_code)} bytes")
        updated += 1
    
    print(f"\n更新完成: {updated} 个, 跳过: {skipped} 个")


def update_strategy_window_fields():
    """更新现有策略的窗口类型字段"""
    print("\n" + "=" * 60)
    print("📊 更新策略窗口类型字段")
    print("=" * 60)
    
    old_db = NB("strategy_units")
    new_db = NB("naja_strategies")
    
    updated = 0
    skipped = 0
    
    for key, new_data in list(new_db.items()):
        if not isinstance(new_data, dict):
            continue
        
        metadata = new_data.get("metadata", {})
        current_window_type = metadata.get("window_type")
        
        if current_window_type and current_window_type != "None":
            print(f"  ⏭️  跳过 (已有类型): {metadata.get('name', key)} -> {current_window_type}")
            skipped += 1
            continue
        
        old_data = old_db.get(key)
        if not old_data:
            print(f"  ⏭️  跳过 (无旧数据): {metadata.get('name', key)}")
            skipped += 1
            continue
        
        old_metadata = old_data.get("metadata", {})
        old_window_type = old_metadata.get("window_type", "sliding") or "sliding"
        old_window_interval = old_metadata.get("window_interval", "10s") or "10s"
        old_window_return_partial = old_metadata.get("window_return_partial", False)
        old_compute_mode = old_metadata.get("compute_mode", "record")
        old_window_size = old_metadata.get("window_size", 5)
        
        if old_window_type == "tumbling":
            old_window_type = "sliding"
            old_compute_mode = "window"
        
        metadata["window_type"] = old_window_type
        metadata["window_interval"] = old_window_interval
        metadata["window_return_partial"] = old_window_return_partial
        if not metadata.get("compute_mode"):
            metadata["compute_mode"] = old_compute_mode
        if not metadata.get("window_size"):
            metadata["window_size"] = old_window_size
        
        new_db[key] = new_data
        print(f"  ✅ 更新: {metadata.get('name', key)} -> window_type={old_window_type}, compute_mode={metadata.get('compute_mode')}")
        updated += 1
    
    print(f"\n更新完成: {updated} 个, 跳过: {skipped} 个")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="数据迁移脚本")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不写入数据")
    parser.add_argument("--v1-only", action="store_true", help="只迁移 v1 版本数据")
    parser.add_argument("--v2-only", action="store_true", help="只迁移 v2 版本数据")
    parser.add_argument("--update-types", action="store_true", help="更新数据源类型字段")
    parser.add_argument("--update-dict-types", action="store_true", help="更新数据字典类型字段")
    parser.add_argument("--update-codes", action="store_true", help="更新数据源代码字段")
    parser.add_argument("--update-strategy-window", action="store_true", help="更新策略窗口类型字段")
    args = parser.parse_args()
    
    if args.update_types:
        update_datasource_types()
    elif args.update_dict_types:
        update_dictionary_types()
    elif args.update_codes:
        update_datasource_codes()
    elif args.update_strategy_window:
        update_strategy_window_fields()
    else:
        run_migration(dry_run=args.dry_run, v1_only=args.v1_only, v2_only=args.v2_only)
