"""DataSource Manager - 单例管理器"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Any, Dict, List, Optional

from deva import NB, bus, log
from deva.core.namespace import NS

from ..infra.runtime.recoverable import (
    RecoverableUnit,
    UnitStatus,
    RecoveryManager,
    recovery_manager,
)
from ..infra.management.base_manager import CatalogManagerMixin, SingletonLazyManager
from .models import (
    DS_TABLE,
    DS_LATEST_DATA_TABLE,
    DataSourceMetadata,
    DataSourceState,
    _scheduler_manager,
)
from .entry import DataSourceEntry


def _require_initialized(method):
    """装饰器：确保方法调用前已初始化"""
    def wrapper(self, *args, **kwargs):
        self._ensure_initialized()
        return method(self, *args, **kwargs)
    return wrapper


class DataSourceManager(SingletonLazyManager, CatalogManagerMixin[DataSourceEntry]):
    """数据源管理器

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局唯一性：数据源系统是全局资源，只能有一个实例管理所有数据源的生命周期。
       如果存在多个实例，可能导致数据源状态不一致。

    2. 资源管理：DataSourceManager 持有数据源字典（_items）和数据库连接（NB），
       这些资源应该全局共享，而非重复创建。

    3. 生命周期：Manager 的生命周期与系统一致，随系统启动和关闭。

    4. 依赖注入支持：如需测试，可以注入 mock 对象。

    5. Manager 类本身不是资源，而是通往资源的入口点。真正的系统资源
       （如 NB 数据库连接）是单例的，而 Manager 类保持单例是为了方便
       访问这些资源。

    6. 初始化模式：使用延迟初始化模式，初始化时机由 bootstrap 控制，
       避免模块导入顺序导致的数据未加载问题。
    ================================================================================
    """

    def __init__(self):
        pass

    def _initialize_manager_state(self):
        self._items: Dict[str, DataSourceEntry] = {}
        self._items_lock = threading.Lock()
        self._loaded_prefer_files = False
        self.load_prefer_files()

    @_require_initialized
    def create(
        self,
        name: str,
        func_code: str = "",
        interval: float = None,
        description: str = "",
        tags: List[str] = None,
        source_type: str = "custom",
        config: dict = None,
        execution_mode: str = "timer",
        scheduler_trigger: str = "interval",
        cron_expr: str = "",
        run_at: str = "",
        event_source: str = "log",
        event_condition: str = "",
        event_condition_type: str = "contains",
    ) -> dict:
        from ..config import get_datasource_config

        import hashlib
        entry_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]

        # 使用配置默认值
        ds_config = get_datasource_config()
        if interval is None:
            interval = ds_config.get("default_interval", 5.0)

        if source_type == "custom" and func_code and "fetch_data" not in func_code:
            return {"success": False, "error": "代码必须包含 fetch_data 函数"}

        if source_type == "replay":
            if not config or not config.get("table_name"):
                return {"success": False, "error": "回放数据源必须指定表名"}
            # 对于replay类型，不需要函数代码
            func_code = ""

        metadata = DataSourceMetadata(
            id=entry_id,
            name=name,
            description=description,
            tags=tags or [],
            interval=interval,
            source_type=source_type,
            config=config or {},
            execution_mode=str(execution_mode or "timer").strip().lower(),
            scheduler_trigger=str(scheduler_trigger or "interval").strip().lower(),
            cron_expr=str(cron_expr or "").strip(),
            run_at=str(run_at or "").strip(),
            event_source=str(event_source or "log").strip().lower(),
            event_condition=str(event_condition or ""),
            event_condition_type=str(event_condition_type or "contains").strip().lower(),
        )

        entry = DataSourceEntry(metadata=metadata)
        entry._func_code = func_code

        if func_code:
            result = entry.compile_code()
            if not result["success"]:
                return {"success": False, "error": f"编译失败: {result['error']}"}

        with self._items_lock:
            if any(e.name == name for e in self._items.values()):
                return {"success": False, "error": f"数据源名称已存在: {name}"}
            self._items[entry_id] = entry

        entry.save()

        self._log("INFO", "DataSource created", id=entry_id, name=name, source_type=source_type)
        return {"success": True, "id": entry_id, "entry": entry.to_dict()}

    @_require_initialized
    def delete(self, entry_id: str) -> dict:
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}

        entry.stop()

        with self._items_lock:
            self._items.pop(entry_id, None)

        db = NB(DS_TABLE)
        if entry_id in db:
            del db[entry_id]

        self._log("INFO", "DataSource deleted", id=entry_id, name=entry.name)
        return {"success": True}

    def load_from_db(self) -> int:
        db = NB(DS_TABLE)
        count = 0

        with self._items_lock:
            self._items.clear()

            for entry_id, data in list(db.items()):
                if not isinstance(data, dict):
                    continue

                try:
                    entry = DataSourceEntry.from_dict(data)
                    if not entry.id:
                        continue

                    self._items[entry.id] = entry
                    count += 1

                except Exception as e:
                    self._log("ERROR", "Load entry failed", id=entry_id, error=str(e))

        return count

    def load_prefer_files(self) -> int:
        """优先从文件加载数据源配置，NB 数据作为兜底

        加载策略：
        1. 如果已加载过，直接返回
        2. 如果文件存在，优先使用文件配置
        3. 如果文件不存在但 NB 中有，则使用 NB 数据
        4. 合并去重，以文件配置优先

        Returns:
            加载的数据源数量
        """
        if getattr(self, '_loaded_prefer_files', False):
            return len(getattr(self, '_items', {}))

        if not hasattr(self, '_items') or self._items is None:
            self._items = {}
        if not hasattr(self, '_items_lock') or self._items_lock is None:
            self._items_lock = threading.Lock()

        from deva.naja.config.file_config import get_file_config_manager

        file_mgr = get_file_config_manager('datasource')
        file_names = set(file_mgr.list_names())

        db = NB(DS_TABLE)
        loaded_count = 0

        with self._items_lock:
            self._items.clear()

            for entry_id, data in list(db.items()):
                if not isinstance(data, dict):
                    continue

                try:
                    entry = DataSourceEntry.from_dict(data)
                    if not entry.id:
                        continue

                    name = entry.name
                    if name in file_names:
                        file_item = file_mgr.get(name)
                        if file_item and file_item.metadata.source == 'file':
                            existing_time = getattr(entry._metadata, 'updated_at', 0) or 0
                            file_time = file_item.metadata.updated_at or 0
                            if file_time >= existing_time:
                                file_entry = self._create_entry_from_file_config(file_item)
                                if file_entry:
                                    self._items[file_entry.id] = file_entry
                                    loaded_count += 1
                                    continue

                    self._items[entry.id] = entry
                    loaded_count += 1

                except Exception as e:
                    self._log("ERROR", "Load entry failed", id=entry_id, error=str(e))

            for name in file_names:
                file_item = file_mgr.get(name)
                if not file_item:
                    continue

                name_already_loaded = any(e.name == name for e in self._items.values())
                if name_already_loaded:
                    continue

                try:
                    file_entry = self._create_entry_from_file_config(file_item)
                    if file_entry:
                        self._items[file_entry.id] = file_entry
                        loaded_count += 1
                except Exception as e:
                    self._log("ERROR", f"Load from file failed: {name}", error=str(e))

        self._loaded_prefer_files = True
        return loaded_count

    def _create_entry_from_file_config(self, file_item) -> Optional['DataSourceEntry']:
        """从文件配置创建 DataSourceEntry"""
        from deva.naja.config.file_config import ConfigFileItem

        if not isinstance(file_item, ConfigFileItem):
            return None

        file_metadata = file_item.metadata
        file_config = file_item.config
        file_params = file_item.parameters

        metadata = DataSourceMetadata(
            id=file_metadata.id or file_item.name,
            name=file_item.name,
            description=file_metadata.description or '',
            tags=file_metadata.tags or [],
            source_type=file_config.get('source_type', 'timer'),
            config=file_config.get('config', {}),
            interval=file_params.get('interval_seconds', 5.0),
            execution_mode=file_config.get('execution_mode', 'timer'),
            scheduler_trigger=file_config.get('scheduler_trigger', 'interval'),
            cron_expr=file_config.get('cron_expr', ''),
            run_at=file_config.get('run_at', ''),
            event_source=file_config.get('event_source', 'log'),
            event_condition=file_config.get('event_condition', ''),
            event_condition_type=file_config.get('event_condition_type', 'contains'),
            created_at=file_metadata.created_at or time.time(),
            updated_at=file_metadata.updated_at or time.time(),
        )

        state = DataSourceState()
        entry = DataSourceEntry(metadata=metadata, state=state)

        if file_item.func_code:
            entry._func_code = file_item.func_code
            try:
                entry.compile_code()
            except Exception:
                pass

        return entry

    def restore_running_states(self) -> dict:
        restored_count = 0
        failed_count = 0
        results = []

        with self._items_lock:
            entries_to_check = list(self._items.values())

        for entry in entries_to_check:
            try:
                prep = entry.prepare_for_recovery()

                if not prep.get("can_recover"):
                    results.append({
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": False,
                        "reason": prep.get("reason"),
                    })
                    continue

                result = entry.start()

                if result.get("success"):
                    restored_count += 1
                    results.append({
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": True,
                    })
                else:
                    failed_count += 1
                    results.append({
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": False,
                        "error": result.get("error"),
                    })

            except Exception as e:
                failed_count += 1
                results.append({
                    "entry_id": entry.id,
                    "entry_name": entry.name,
                    "success": False,
                    "error": str(e),
                })

        return {
            "success": True,
            "restored_count": restored_count,
            "failed_count": failed_count,
            "results": results,
        }

    def get_all_recovery_info(self) -> List[dict]:
        self._ensure_initialized()
        info = []
        for entry in self._items.values():
            prep = entry.prepare_for_recovery()
            info.append({
                "id": entry.id,
                "name": entry.name,
                "was_running": entry.was_running,
                "can_recover": prep.get("can_recover"),
                "reason": prep.get("reason"),
            })
        return info

    def get_stats(self) -> dict:
        entries = self.list_all()
        running = sum(1 for e in entries if e.is_running)
        error = sum(1 for e in entries if e._state.error_count > 0)

        stats = {
            "total": len(entries),
            "running": running,
            "stopped": len(entries) - running,
            "error": error,
        }

        attention_stats = self.get_attention_stats()
        if attention_stats:
            stats["attention"] = attention_stats

        return stats

    def get_attention_stats(self) -> Optional[dict]:
        try:
            from deva.naja.market_hotspot.integration.market_hotspot_integration import get_market_hotspot_integration
            integration = get_market_hotspot_integration()
            if not getattr(integration, '_initialized_attention_system', False):
                return None
        except Exception:
            return None

        try:
            from deva.naja.market_hotspot.data.async_fetcher import get_data_fetcher
            fetcher = get_data_fetcher()
            if fetcher and hasattr(fetcher, 'get_stats'):
                return fetcher.get_stats()
        except ImportError:
            pass
        return None

    def start_all(self) -> dict:
        success = 0
        failed = 0
        skipped = 0

        for entry in self.list_all():
            if entry.is_running:
                skipped += 1
                continue

            result = entry.start()
            if result.get("success"):
                success += 1
            else:
                failed += 1

        return {"success": success, "failed": failed, "skipped": skipped}

    def stop_all(self) -> dict:
        success = 0
        failed = 0
        skipped = 0

        for entry in self.list_all():
            if not entry.is_running:
                skipped += 1
                continue

            result = entry.stop()
            if result.get("success"):
                success += 1
            else:
                failed += 1

        return {"success": success, "failed": failed, "skipped": skipped}
def get_datasource_manager() -> DataSourceManager:
    from deva.naja.register import SR
    return SR('datasource_manager')
