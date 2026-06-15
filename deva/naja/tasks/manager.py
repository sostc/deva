"""TaskManager - 任务管理器（单例）"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from deva import NB

from ..scheduler import normalize_execution_mode
from .models import TASK_TABLE, TaskMetadata, TaskState
from .entry import TaskEntry


class TaskManager:
    """任务管理器

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局唯一性：任务系统是全局资源，只能有一个实例管理所有任务的生命周期。
       如果存在多个实例，可能导致任务状态不一致。

    2. 资源管理：TaskManager 持有任务字典（_items）和数据库连接（NB），
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
            self._items: Dict[str, TaskEntry] = {}
            self._items_lock = threading.Lock()
            self.load_prefer_files()
            self._initialized = True

    def create(
        self,
        name: str,
        func_code: str,
        task_type: str = "interval",
        execution_mode: str = None,
        interval_seconds: float = 60.0,
        scheduler_trigger: str = "interval",
        cron_expr: str = "",
        run_at: str = "",
        event_source: str = "log",
        event_condition: str = "",
        event_condition_type: str = "contains",
        description: str = "",
        tags: List[str] = None,
    ) -> dict:
        from ..config import get_task_config

        entry_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]

        task_config = get_task_config()
        if interval_seconds is None:
            interval_seconds = task_config.get("default_interval", 60)

        if "execute" not in func_code:
            return {"success": False, "error": "代码必须包含 execute 函数"}

        mode = normalize_execution_mode(execution_mode, task_type)
        metadata = TaskMetadata(
            id=entry_id,
            name=name,
            description=description,
            tags=tags or [],
            task_type=task_type,
            execution_mode=mode,
            interval_seconds=interval_seconds,
            scheduler_trigger=(scheduler_trigger or "interval").strip().lower(),
            cron_expr=(cron_expr or "").strip(),
            run_at=(run_at or "").strip(),
            event_source=(event_source or "log").strip().lower(),
            event_condition=event_condition or "",
            event_condition_type=(event_condition_type or "contains").strip().lower(),
        )

        if task_type == "once" and not metadata.run_at:
            metadata.scheduler_trigger = "date"
            metadata.run_at = (datetime.now() + timedelta(seconds=1)).isoformat(timespec="seconds")

        entry = TaskEntry(metadata=metadata)
        entry._func_code = func_code

        result = entry.compile_code()
        if not result["success"]:
            return {"success": False, "error": f"编译失败: {result['error']}"}

        with self._items_lock:
            if any(e.name == name for e in self._items.values()):
                return {"success": False, "error": f"任务名称已存在: {name}"}
            self._items[entry_id] = entry

        entry.save()

        self._log("INFO", "Task created", id=entry_id, name=name, mode=mode)
        return {"success": True, "id": entry_id, "entry": entry.to_dict()}

    def get(self, entry_id: str) -> Optional[TaskEntry]:
        self._ensure_initialized()
        return self._items.get(entry_id)

    def get_by_name(self, name: str) -> Optional[TaskEntry]:
        self._ensure_initialized()
        for entry in self._items.values():
            if entry.name == name:
                return entry
        return None

    def list_all(self) -> List[TaskEntry]:
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

        with self._items_lock:
            self._items.pop(entry_id, None)

        db = NB(TASK_TABLE)
        if entry_id in db:
            del db[entry_id]

        self._log("INFO", "Task deleted", id=entry_id, name=entry.name)
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

        t = threading.Thread(
            target=_run_in_thread,
            daemon=True,
            name=f"task_run_once_{entry_id}",
        )
        t.start()
        return {"success": True, "message": "已提交执行任务"}

    def load_from_db(self) -> int:
        db = NB(TASK_TABLE)
        count = 0

        if not hasattr(self, '_items') or self._items is None:
            self._items = {}
        if not hasattr(self, '_items_lock') or self._items_lock is None:
            self._items_lock = threading.Lock()

        with self._items_lock:
            self._items.clear()

            for entry_id, data in list(db.items()):
                if not isinstance(data, dict):
                    continue

                try:
                    entry = TaskEntry.from_dict(data)
                    if not entry.id:
                        continue

                    self._items[entry.id] = entry
                    count += 1

                except Exception as e:
                    self._log("ERROR", "Load entry failed", id=entry_id, error=str(e))

        return count

    def load_prefer_files(self) -> int:
        """优先从文件加载任务配置，NB 数据作为兜底

        加载策略：
        1. 先扫描 config/tasks/ 目录下的文件配置
        2. 如果文件存在，优先使用文件配置
        3. 如果文件不存在但 NB 中有，则使用 NB 数据
        4. 合并去重，以文件配置优先

        Returns:
            加载的任务数量
        """
        from deva.naja.config.file_config import get_file_config_manager

        file_mgr = get_file_config_manager('task')
        file_names = set(file_mgr.list_names())

        db = NB(TASK_TABLE)
        loaded_count = 0

        if not hasattr(self, '_items') or self._items is None:
            self._items = {}
        if not hasattr(self, '_items_lock') or self._items_lock is None:
            self._items_lock = threading.Lock()

        with self._items_lock:
            self._items.clear()

            for entry_id, data in list(db.items()):
                if not isinstance(data, dict):
                    continue

                try:
                    entry = TaskEntry.from_dict(data)
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
                                    # 保留 NB 中的运行状态（last_run_time、success_count 等）
                                    file_entry._state = entry._state
                                    # 有 YAML 定义且非 manual：自动启用
                                    _cfg = file_item.config
                                    _is_manual = _cfg.get('execution_mode') == 'manual' or _cfg.get('task_type') == 'manual'
                                    file_entry._was_running = not _is_manual
                                    self._items[file_entry.id] = file_entry
                                    loaded_count += 1
                                    continue

                    # NB 中没有 YAML 覆盖的旧任务：如果曾经成功运行过且非 manual，保持运行状态
                    _task_type = getattr(entry._metadata, 'task_type', '') or ''
                    if not entry._was_running and 'manual' not in _task_type:
                        _last_run = getattr(entry._state, 'last_run_time', 0) if hasattr(entry._state, 'last_run_time') else getattr(entry._state, 'get', lambda k, d=0: entry._state.get(k, d)) if hasattr(entry._state, '__iter__') else 0
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
                        # YAML only 新任务：非 manual 模式默认启用（was_running=True）
                        exec_mode = file_config.get('execution_mode', '') if 'file_config' in dir() else ''
                        try:
                            _cfg = file_item.config
                            if _cfg.get('execution_mode') != 'manual' and _cfg.get('task_type') != 'manual':
                                file_entry._was_running = True
                        except Exception:
                            pass
                        self._items[file_entry.id] = file_entry
                        loaded_count += 1
                except Exception as e:
                    self._log("ERROR", f"Load from file failed: {name}", error=str(e))

        return loaded_count

    def _create_entry_from_file_config(self, file_item) -> Optional[TaskEntry]:
        """从文件配置创建 TaskEntry

        字段读取策略：优先从 config 读取，metadata 作为兜底（兼容旧格式）
        """
        from deva.naja.config.file_config import ConfigFileItem, TaskConfigMetadata

        if not isinstance(file_item, ConfigFileItem):
            return None

        file_metadata = file_item.metadata
        file_config = file_item.config

        def _get(key: str, default=None):
            """优先从 config 读，其次从 metadata 读"""
            v = file_config.get(key)
            if v is not None and v != '':
                return v
            v = getattr(file_metadata, key, None)
            if v is not None and v != '':
                return v
            return default

        execution_mode = normalize_execution_mode(
            _get('execution_mode', ''),
            _get('task_type', 'timer')
        )

        scheduler_trigger = _get('scheduler_trigger', 'interval')
        if scheduler_trigger == 'interval' and _get('cron_expr', ''):
            scheduler_trigger = 'cron'

        metadata = TaskMetadata(
            id=file_metadata.id or file_item.name,
            name=file_item.name,
            description=file_metadata.description or '',
            tags=file_metadata.tags or [],
            task_type=_get('task_type', 'timer'),
            execution_mode=execution_mode,
            interval_seconds=float(_get('interval_seconds', 60.0)),
            scheduler_trigger=scheduler_trigger,
            cron_expr=_get('cron_expr', ''),
            run_at=_get('run_at', ''),
            event_source=_get('event_source', 'log'),
            event_condition=_get('event_condition', ''),
            event_condition_type=_get('event_condition_type', 'contains'),
            created_at=file_metadata.created_at or time.time(),
            updated_at=file_metadata.updated_at or time.time(),
        )

        state = TaskState()
        entry = TaskEntry(metadata=metadata, state=state)

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

        # 先检查并补执行错过的 cron 任务
        catchup_results = self._catchup_missed_cron_tasks()
        results.extend(catchup_results.get("results", []))

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

    def _catchup_missed_cron_tasks(self, days_back: int = 3) -> dict:
        """检查并补执行最近几天内未执行的 cron 任务

        遍历所有 cron 类型的任务，检查最近 days_back 天是否有执行记录。
        如果最近 days_back 天都没有执行过，则立即补执行一次。

        同时检查今天是否执行过，如果今天的任务还没执行且已到执行时间，立即补执行。

        Args:
            days_back: 回溯检查的天数，默认3天
        """
        self._ensure_initialized()
        results = []
        catchup_count = 0
        skip_count = 0

        try:
            from apscheduler.triggers.cron import CronTrigger
            import pytz
        except Exception:
            return {"success": True, "catchup_count": 0, "skip_count": 0, "results": [], "reason": "apscheduler 未安装"}

        tz = pytz.timezone("Asia/Shanghai")
        now = datetime.now(tz)
        today_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=tz)

        with self._items_lock:
            entries = list(self._items.values())

        for entry in entries:
            try:
                mode = getattr(entry._metadata, "execution_mode", "")
                trigger = getattr(entry._metadata, "scheduler_trigger", "interval")
                cron_expr = getattr(entry._metadata, "cron_expr", "")
                last_run = entry._state.last_run_time

                if mode != "scheduler" or trigger != "cron" or not cron_expr:
                    continue

                ct = CronTrigger.from_crontab(cron_expr, timezone=tz)

                last_run_dt = None
                if last_run and last_run > 0:
                    last_run_dt = datetime.fromtimestamp(last_run, tz=tz)

                last_run_date = last_run_dt.date() if last_run_dt else None

                if last_run_dt is None:
                    self._log("INFO", "补执行: 从未执行过", id=entry.id, name=entry.name, cron=cron_expr)
                    entry.run_once()
                    catchup_count += 1
                    results.append({"entry_id": entry.id, "entry_name": entry.name, "success": True, "catchup": True, "reason": "从未执行"})
                    continue

                days_since_run = (now.date() - last_run_date).days

                if last_run_date == now.date():
                    self._log("INFO", "今日已执行，跳过", id=entry.id, name=entry.name)
                    skip_count += 1
                    continue

                today_fire_time = None
                check_today = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=tz)
                for _ in range(10):
                    next_fire = ct.get_next_fire_time(None, check_today)
                    if next_fire and next_fire.date() == now.date():
                        today_fire_time = next_fire
                        break
                    if next_fire and next_fire.date() > now.date():
                        break
                    check_today = next_fire + timedelta(minutes=1) if next_fire else check_today + timedelta(days=1)

                if today_fire_time and now >= today_fire_time and now - today_fire_time < timedelta(hours=12):
                    self._log("INFO", f"补执行: 今天任务未执行({today_fire_time.strftime('%H:%M')})", id=entry.id, name=entry.name)
                    entry.run_once()
                    catchup_count += 1
                    results.append({"entry_id": entry.id, "entry_name": entry.name, "success": True, "catchup": True, "reason": f"今日未执行({today_fire_time.strftime('%H:%M')})"})
                    continue

                if days_since_run > days_back:
                    self._log("INFO", f"补执行: 已{days_since_run}天未执行(超过{days_back}天)", id=entry.id, name=entry.name, last_run=last_run_dt.strftime("%Y-%m-%d"))
                    entry.run_once()
                    catchup_count += 1
                    results.append({"entry_id": entry.id, "entry_name": entry.name, "success": True, "catchup": True, "reason": f"已{days_since_run}天未执行"})
                    continue

                check_dt = last_run_dt + timedelta(minutes=1)
                missed = False
                for _ in range(1000):
                    next_fire = ct.get_next_fire_time(None, check_dt)
                    if not next_fire or next_fire > now:
                        break
                    if next_fire > last_run_dt:
                        missed = True
                        break
                    check_dt = next_fire + timedelta(minutes=1)

                if missed:
                    self._log("INFO", "补执行: 错过执行时间", id=entry.id, name=entry.name, last_run=last_run_dt.strftime("%Y-%m-%d %H:%M"))
                    entry.run_once()
                    catchup_count += 1
                    results.append({"entry_id": entry.id, "entry_name": entry.name, "success": True, "catchup": True})
                else:
                    skip_count += 1

            except Exception as e:
                skip_count += 1
                results.append({"entry_id": entry.id, "entry_name": entry.name, "success": False, "error": str(e)})

        return {"success": True, "catchup_count": catchup_count, "skip_count": skip_count, "results": results}

    def get_stats(self) -> dict:
        self._ensure_initialized()
        entries = self.list_all()
        running = sum(1 for e in entries if e.is_running)

        total_success = sum(e._state.success_count for e in entries)
        total_failure = sum(e._state.failure_count for e in entries)

        return {
            "total": len(entries),
            "running": running,
            "stopped": len(entries) - running,
            "total_success": total_success,
            "total_failure": total_failure,
        }

    def _log(self, level: str, message: str, **extra):
        extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
        print(f"[TaskManager][{level}] {message} | {extra_str}")
