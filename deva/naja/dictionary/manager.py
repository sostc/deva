"""Dictionary Manager - 单例管理器"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from deva import NB

from ..common.recoverable import (
    RecoverableUnit,
    UnitStatus,
)
from .models import (
    DICT_ENTRY_TABLE,
    DICT_PAYLOAD_TABLE,
    DictionaryMetadata,
    DictionaryState,
)
from .entry import DictionaryEntry
from .helpers import (
    _normalize_source_mode,
    _task_type_from_refresh_config,
    _build_refresh_task_code,
)
from deva.naja.register import SR


class DictionaryManager:
    """字典管理器

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局唯一性：字典系统是全局资源，只能有一个实例管理所有字典的生命周期。
       如果存在多个实例，可能导致字典状态不一致。

    2. 资源管理：DictionaryManager 持有字典字典（_items）和数据库连接（NB），
       这些资源应该全局共享，而非重复创建。

    3. 生命周期：Manager 的生命周期与系统一致，随系统启动和关闭。

    4. 依赖注入支持：如需测试，可以注入 mock 对象。

    5. Manager 类本身不是资源，而是通往资源的入口点。真正的系统资源
       （如 NB 数据库连接）是单例的，而 Manager 类保持单例是为了方便
       访问这些资源。
    ================================================================================
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                    cls._instance._init_lock = threading.Lock()
        return cls._instance

    def __init__(self):
        pass

    def _ensure_initialized(self):
        if getattr(self, '_initialized', False):
            return
        with self._init_lock:
            if getattr(self, '_initialized', False):
                return
            self._items: Dict[str, DictionaryEntry] = {}
            self._items_lock = threading.Lock()
            self._file_config_mgr = None
            self.load_from_db()
            self._initialized = True

    @property
    def file_config_manager(self):
        """获取文件配置管理器（延迟加载）"""
        if self._file_config_mgr is None:
            from ..config.file_config import get_dict_file_config_manager
            self._file_config_mgr = get_dict_file_config_manager()
        return self._file_config_mgr

    def _sync_legacy_schedule_fields(self, entry: DictionaryEntry):
        mode = str(getattr(entry._metadata, "execution_mode", "timer") or "timer").strip().lower()
        trig = str(getattr(entry._metadata, "scheduler_trigger", "interval") or "interval").strip().lower()

        if mode == "scheduler" and trig == "cron" and getattr(entry._metadata, "cron_expr", ""):
            entry._metadata.schedule_type = "daily"
            entry._metadata.daily_time = getattr(entry._metadata, "daily_time", "03:00") or "03:00"
        else:
            entry._metadata.schedule_type = "interval"

    def _upsert_refresh_task(
        self,
        entry: DictionaryEntry,
        *,
        func_code: str,
        execution_mode: str,
        interval_seconds: int,
        scheduler_trigger: str,
        cron_expr: str,
        run_at: str,
        event_source: str,
        event_condition: str,
        event_condition_type: str,
    ) -> dict:

        task_mgr = SR('task_manager')
        wrapper_code = _build_refresh_task_code(entry.id, func_code)
        task_type = _task_type_from_refresh_config(execution_mode, scheduler_trigger)
        task_name = f"dict_refresh_{entry.name}_{entry.id}"

        existing_task_id = str(getattr(entry._metadata, "refresh_task_id", "") or "")
        existing_task = task_mgr.get(existing_task_id) if existing_task_id else None

        if existing_task:
            return existing_task.update_config(
                name=task_name,
                description=f"字典 {entry.name} 鲜活任务",
                task_type=task_type,
                execution_mode=execution_mode,
                interval_seconds=float(interval_seconds),
                scheduler_trigger=scheduler_trigger,
                cron_expr=cron_expr,
                run_at=run_at,
                event_source=event_source,
                event_condition=event_condition,
                event_condition_type=event_condition_type,
                func_code=wrapper_code,
            )

        create_result = task_mgr.create(
            name=task_name,
            func_code=wrapper_code,
            task_type=task_type,
            execution_mode=execution_mode,
            interval_seconds=float(interval_seconds),
            scheduler_trigger=scheduler_trigger,
            cron_expr=cron_expr,
            run_at=run_at,
            event_source=event_source,
            event_condition=event_condition,
            event_condition_type=event_condition_type,
            description=f"字典 {entry.name} 鲜活任务",
        )
        if create_result.get("success"):
            entry._metadata.refresh_task_id = create_result.get("id", "")
        return create_result

    def _remove_refresh_task(self, entry: DictionaryEntry):
        task_id = str(getattr(entry._metadata, "refresh_task_id", "") or "")
        if not task_id:
            return

        task_mgr = SR('task_manager')
        try:
            task_mgr.stop(task_id)
        except Exception:
            pass
        try:
            task_mgr.delete(task_id)
        except Exception:
            pass

    def create(
        self,
        name: str,
        func_code: str = "",
        schedule_type: str = "interval",
        interval_seconds: int = None,
        daily_time: str = None,
        description: str = "",
        tags: List[str] = None,
        dict_type: str = "dimension",
        source_mode: str = "",
        uploaded_data: Any = None,
        execution_mode: str = "timer",
        scheduler_trigger: str = "interval",
        cron_expr: str = "",
        run_at: str = "",
        event_source: str = "log",
        event_condition: str = "",
        event_condition_type: str = "contains",
    ) -> dict:
        from ..config import get_dictionary_config

        import hashlib

        entry_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]

        dict_config = get_dictionary_config()
        if interval_seconds is None:
            interval_seconds = int(dict_config.get("default_interval", 300))
        if daily_time is None:
            daily_time = str(dict_config.get("default_daily_time", "03:00"))

        if schedule_type == "daily" and not cron_expr:
            try:
                execution_mode = "scheduler"
                scheduler_trigger = "cron"
                cron_expr = _daily_time_to_cron(daily_time)
            except Exception:
                pass

        has_upload = uploaded_data is not None
        has_code = bool(str(func_code or "").strip())
        mode = _normalize_source_mode(source_mode, has_upload, has_code)

        if mode == "upload" and not has_upload:
            return {"success": False, "error": "上传模式需要提供初始数据"}
        if mode in {"task", "upload_and_task"} and not has_code:
            return {"success": False, "error": "鲜活任务模式需要提供 fetch_data 代码"}
        if has_code and "fetch_data" not in func_code:
            return {"success": False, "error": "代码必须包含 fetch_data 函数"}

        metadata = DictionaryMetadata(
            id=entry_id,
            name=name,
            description=description,
            tags=tags or [],
            dict_type=dict_type,
            schedule_type=schedule_type,
            interval_seconds=int(interval_seconds),
            daily_time=daily_time,
            source_mode=mode,
            refresh_enabled=(mode in {"task", "upload_and_task"}),
            execution_mode=execution_mode,
            scheduler_trigger=scheduler_trigger,
            cron_expr=cron_expr,
            run_at=run_at,
            event_source=event_source,
            event_condition=event_condition,
            event_condition_type=event_condition_type,
        )

        entry = DictionaryEntry(metadata=metadata)
        entry._func_code = func_code or ""

        if has_code:
            result = entry.compile_code()
            if not result["success"]:
                return {"success": False, "error": f"编译失败: {result['error']}"}

        with self._items_lock:
            if any(e.name == name for e in self._items.values()):
                return {"success": False, "error": f"字典名称已存在: {name}"}
            self._items[entry_id] = entry

        if has_upload:
            entry.apply_fresh_data(uploaded_data)

        if metadata.refresh_enabled:
            task_result = self._upsert_refresh_task(
                entry,
                func_code=func_code,
                execution_mode=execution_mode,
                interval_seconds=int(interval_seconds),
                scheduler_trigger=scheduler_trigger,
                cron_expr=cron_expr,
                run_at=run_at,
                event_source=event_source,
                event_condition=event_condition,
                event_condition_type=event_condition_type,
            )
            if not task_result.get("success"):
                with self._items_lock:
                    self._items.pop(entry_id, None)
                return {"success": False, "error": f"创建鲜活任务失败: {task_result.get('error')}"}

        self._sync_legacy_schedule_fields(entry)
        entry.save()

        self._log("INFO", "Dictionary created", id=entry_id, name=name, mode=mode)
        return {"success": True, "id": entry_id, "entry": entry.to_dict()}

    def update(
        self,
        entry_id: str,
        *,
        name: str = None,
        description: str = None,
        dict_type: str = None,
        source_mode: str = None,
        uploaded_data: Any = None,
        func_code: str = None,
        execution_mode: str = None,
        interval_seconds: int = None,
        scheduler_trigger: str = None,
        cron_expr: str = None,
        run_at: str = None,
        event_source: str = None,
        event_condition: str = None,
        event_condition_type: str = None,
    ) -> dict:
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}

        if name is not None:
            new_name = name.strip()
            if not new_name:
                return {"success": False, "error": "名称不能为空"}
            with self._items_lock:
                duplicated = any(e.id != entry.id and e.name == new_name for e in self._items.values())
            if duplicated:
                return {"success": False, "error": f"字典名称已存在: {new_name}"}
            entry._metadata.name = new_name

        if description is not None:
            entry._metadata.description = description
        if dict_type is not None:
            entry._metadata.dict_type = dict_type

        if uploaded_data is not None:
            entry.apply_fresh_data(uploaded_data)

        if func_code is not None:
            if func_code.strip() and "fetch_data" not in func_code:
                return {"success": False, "error": "代码必须包含 fetch_data 函数"}
            entry._func_code = func_code
            entry._compiled_func = None
            if func_code.strip():
                compile_result = entry.compile_code()
                if not compile_result.get("success"):
                    return {"success": False, "error": f"编译失败: {compile_result.get('error')}"}

        effective_mode = _normalize_source_mode(
            source_mode if source_mode is not None else entry._metadata.source_mode,
            uploaded_data is not None or entry.get_payload() is not None,
            bool((func_code if func_code is not None else entry.func_code or "").strip()),
        )

        entry._metadata.source_mode = effective_mode
        entry._metadata.refresh_enabled = effective_mode in {"task", "upload_and_task"}

        if execution_mode is not None:
            entry._metadata.execution_mode = execution_mode
        if interval_seconds is not None:
            entry._metadata.interval_seconds = max(5, int(interval_seconds))
        if scheduler_trigger is not None:
            entry._metadata.scheduler_trigger = scheduler_trigger
        if cron_expr is not None:
            entry._metadata.cron_expr = cron_expr
        if run_at is not None:
            entry._metadata.run_at = run_at
        if event_source is not None:
            entry._metadata.event_source = event_source
        if event_condition is not None:
            entry._metadata.event_condition = event_condition
        if event_condition_type is not None:
            entry._metadata.event_condition_type = event_condition_type

        if entry._metadata.refresh_enabled:
            code_for_task = (entry.func_code or "").strip()
            if not code_for_task:
                return {"success": False, "error": "鲜活任务模式需要 fetch_data 代码"}
            task_result = self._upsert_refresh_task(
                entry,
                func_code=code_for_task,
                execution_mode=entry._metadata.execution_mode,
                interval_seconds=int(entry._metadata.interval_seconds),
                scheduler_trigger=entry._metadata.scheduler_trigger,
                cron_expr=entry._metadata.cron_expr,
                run_at=entry._metadata.run_at,
                event_source=entry._metadata.event_source,
                event_condition=entry._metadata.event_condition,
                event_condition_type=entry._metadata.event_condition_type,
            )
            if not task_result.get("success"):
                return {"success": False, "error": f"更新鲜活任务失败: {task_result.get('error')}"}
        else:
            self._remove_refresh_task(entry)
            entry._metadata.refresh_task_id = ""

        self._sync_legacy_schedule_fields(entry)
        return entry.save()

    def get(self, entry_id: str) -> Optional[DictionaryEntry]:
        self._ensure_initialized()
        return self._items.get(entry_id)

    def get_by_name(self, name: str) -> Optional[DictionaryEntry]:
        self._ensure_initialized()
        for entry in self._items.values():
            if entry.name == name:
                return entry
        return None

    def list_all(self) -> List[DictionaryEntry]:
        self._ensure_initialized()
        return list(self._items.values())

    def list_all_dict(self) -> List[dict]:
        self._ensure_initialized()
        return [entry.to_dict() for entry in self._items.values()]

    def delete(self, entry_id: str) -> dict:
        self._ensure_initialized()
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}

        entry.stop()
        self._remove_refresh_task(entry)
        entry.clear_payload()

        with self._items_lock:
            self._items.pop(entry_id, None)

        db = NB(DICT_ENTRY_TABLE)
        if entry_id in db:
            del db[entry_id]

        self._log("INFO", "Dictionary deleted", id=entry_id, name=entry.name)
        return {"success": True}

    def start(self, entry_id: str) -> dict:
        self._ensure_initialized()
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}
        return entry.start()

    def stop(self, entry_id: str) -> dict:
        self._ensure_initialized()
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}
        return entry.stop()

    def run_once(self, entry_id: str) -> dict:
        self._ensure_initialized()
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}
        return entry.run_once()

    def run_once_async(self, entry_id: str) -> dict:
        """异步执行一次（不阻塞UI）"""
        self._ensure_initialized()
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}

        def _run_in_thread():
            try:
                entry.run_once()
            except Exception as e:
                self._log("ERROR", "Async run failed", id=entry_id, error=str(e))

        # 使用全局线程池而不是直接创建线程
        from ..common.thread_pool import get_thread_pool
        pool = get_thread_pool()
        future = pool.submit(_run_in_thread)
        if future is None:
            return {"success": False, "error": "线程池过载，无法提交任务"}

        self._log("INFO", "Dictionary refresh queued", id=entry_id)
        return {"success": True, "queued": True, "entry_id": entry_id}

    def load_from_db(self) -> int:
        db = NB(DICT_ENTRY_TABLE)
        count = 0

        with self._items_lock:
            self._items.clear()

            for entry_id, data in list(db.items()):
                if not isinstance(data, dict):
                    continue

                try:
                    entry = DictionaryEntry.from_dict(data)
                    if not entry.id:
                        continue

                    self._items[entry.id] = entry
                    count += 1

                except Exception as e:
                    self._log("ERROR", "Load entry failed", id=entry_id, error=str(e))

            self._deduplicate_by_name()

        return count

    def load_from_files(self) -> int:
        """从配置文件加载字典

        配置文件位于 config/dictionaries/ 目录
        每个字典一个 YAML 文件，包含 metadata 和 func_code
        """
        file_mgr = self.file_config_manager
        count = 0

        with self._items_lock:
            for config_meta in file_mgr.list_all():
                name = config_meta.name
                if not name:
                    continue

                try:
                    entry = self._create_entry_from_file_config(config_meta, file_mgr.get_func_code(name))
                    if entry:
                        self._items[entry.id] = entry
                        count += 1
                except Exception as e:
                    self._log("ERROR", f"Load from file failed: {name}", error=str(e))

        self._deduplicate_by_name()
        return count

    def _create_entry_from_file_config(self, config_meta, func_code: str) -> Optional[DictionaryEntry]:
        """从文件配置创建字典条目"""
        entry_id = config_meta.id or config_meta.name

        payload = None
        payload_table = NB(DICT_PAYLOAD_TABLE)
        if entry_id in payload_table:
            payload = payload_table.get(entry_id)

        metadata_dict = {
            'id': entry_id,
            'name': config_meta.name,
            'description': config_meta.description,
            'tags': config_meta.tags or [],
            'dict_type': config_meta.dict_type,
            'schedule_type': config_meta.schedule_type,
            'interval_seconds': config_meta.interval_seconds,
            'daily_time': config_meta.daily_time,
            'source_mode': config_meta.source_mode,
            'refresh_enabled': config_meta.refresh_enabled,
            'execution_mode': config_meta.execution_mode,
            'scheduler_trigger': config_meta.scheduler_trigger,
            'cron_expr': config_meta.cron_expr,
            'run_at': config_meta.run_at,
            'event_source': config_meta.event_source,
            'event_condition': config_meta.event_condition,
            'event_condition_type': config_meta.event_condition_type,
            'created_at': config_meta.created_at,
            'updated_at': config_meta.updated_at,
            'func_code': func_code,
        }

        entry = DictionaryEntry(
            id=entry_id,
            metadata=metadata_dict,
            payload=payload,
        )

        self._sync_legacy_schedule_fields(entry)
        return entry

    def export_to_file(self, entry_id: str) -> bool:
        """将字典导出到文件

        用于将 NB 中的字典迁移到文件
        """
        from ..config.file_config import FileConfigMetadata

        with self._items_lock:
            entry = self._items.get(entry_id)
            if not entry:
                return False

            file_mgr = self.file_config_manager
            config_meta = FileConfigMetadata(
                id=entry.id,
                name=entry.name,
                description=entry.description or '',
                tags=entry.tags or [],
                dict_type=entry.dict_type or 'dimension',
                schedule_type=getattr(entry._metadata, 'schedule_type', 'interval'),
                interval_seconds=getattr(entry._metadata, 'interval_seconds', 300),
                daily_time=getattr(entry._metadata, 'daily_time', '03:00'),
                source_mode=entry.source_mode or 'task',
                refresh_enabled=entry.refresh_enabled if entry.refresh_enabled is not None else True,
                execution_mode=getattr(entry._metadata, 'execution_mode', 'timer'),
                scheduler_trigger=getattr(entry._metadata, 'scheduler_trigger', 'interval'),
                cron_expr=getattr(entry._metadata, 'cron_expr', ''),
                run_at=getattr(entry._metadata, 'run_at', ''),
                event_source=getattr(entry._metadata, 'event_source', 'log'),
                event_condition=getattr(entry._metadata, 'event_condition', ''),
                event_condition_type=getattr(entry._metadata, 'event_condition_type', 'contains'),
                func_code_file='',
                created_at=entry.created_at or 0,
                updated_at=time.time(),
            )

            func_code = entry.metadata.get('func_code', '')
            return file_mgr.save(entry.name, config_meta, func_code)

    def save_to_file(self, entry_id: str) -> bool:
        """保存字典到文件（实时同步）"""
        return self.export_to_file(entry_id)

    def load_prefer_files(self) -> int:
        """优先从文件加载字典，NB 数据作为兜底

        加载策略：
        1. 先扫描 config/dictionaries/ 目录下的文件配置
        2. 如果文件存在，优先使用文件配置（包含 func_code，方便代码审查）
        3. 如果文件不存在但 NB 中有，则使用 NB 数据（向后兼容）
        4. 合并去重，保留最新的配置

        Returns:
            加载的字典数量
        """
        file_mgr = self.file_config_manager
        file_names = set(config.name for config in file_mgr.list_all())

        with self._items_lock:
            for name in file_names:
                config_meta = file_mgr.get(name)
                if not config_meta:
                    continue

                try:
                    existing = self._items.get(config_meta.id or config_meta.name)
                    should_overwrite = True

                    if existing:
                        existing_time = getattr(existing._metadata, 'updated_at', 0) or 0
                        file_time = config_meta.updated_at or 0
                        should_overwrite = file_time >= existing_time

                    if should_overwrite:
                        entry = self._create_entry_from_file_config(
                            config_meta,
                            file_mgr.get_func_code(name)
                        )
                        if entry:
                            self._items[entry.id] = entry
                            self._log("INFO", f"从文件加载字典: {name}")
                except Exception as e:
                    self._log("ERROR", f"从文件加载字典失败: {name}", error=str(e))

            self._deduplicate_by_name()

        return len(self._items)

    def _deduplicate_by_name(self) -> int:
        """删除名称重复的字典，保留最新创建的一个"""
        name_to_entries = {}
        for entry in list(self._items.values()):
            if entry.name not in name_to_entries:
                name_to_entries[entry.name] = []
            name_to_entries[entry.name].append(entry)

        removed_count = 0
        for name, entries in name_to_entries.items():
            if len(entries) > 1:
                entries.sort(key=lambda e: getattr(e._metadata, 'created_at', 0), reverse=True)
                for entry in entries[1:]:
                    self._log("WARNING", f"删除重复字典: {name} (ID: {entry.id})")
                    self.delete(entry.id)
                    removed_count += 1

        if removed_count > 0:
            self._log("INFO", f"删除了 {removed_count} 个重复字典")

        return removed_count

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
                    results.append(
                        {
                            "entry_id": entry.id,
                            "entry_name": entry.name,
                            "success": False,
                            "reason": prep.get("reason"),
                        }
                    )
                    continue

                result = entry.start()

                if result.get("success"):
                    restored_count += 1
                    results.append(
                        {
                            "entry_id": entry.id,
                            "entry_name": entry.name,
                            "success": True,
                        }
                    )
                else:
                    failed_count += 1
                    results.append(
                        {
                            "entry_id": entry.id,
                            "entry_name": entry.name,
                            "success": False,
                            "error": result.get("error"),
                        }
                    )

            except Exception as e:
                failed_count += 1
                results.append(
                    {
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": False,
                        "error": str(e),
                    }
                )

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
            info.append(
                {
                    "id": entry.id,
                    "name": entry.name,
                    "was_running": entry.was_running,
                    "can_recover": prep.get("can_recover"),
                    "reason": prep.get("reason"),
                }
            )
        return info

    def get_stats(self) -> dict:
        self._ensure_initialized()
        entries = self.list_all()
        running = sum(1 for e in entries if e.is_running)
        success = sum(1 for e in entries if e._state.last_status == "success")
        error = sum(1 for e in entries if e._state.last_status == "error")
        file_based = sum(1 for e in entries if self._is_file_based(e))

        return {
            "total": len(entries),
            "running": running,
            "success": success,
            "error": error,
            "file_based": file_based,
        }

    def _is_file_based(self, entry) -> bool:
        """检查字典是否来自文件配置"""
        if not hasattr(self, '_file_config_mgr') or self._file_config_mgr is None:
            return False
        file_mgr = self.file_config_manager
        return file_mgr.exists(entry.name)

    def _log(self, level: str, message: str, **extra):
        extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
        print(f"[DictionaryManager][{level}] {message} | {extra_str}")

