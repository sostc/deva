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
    as_epoch_seconds,
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

        # 级联清理该数据源的最新数据缓存。
        # 否则每删掉一个数据源就留下一条孤儿缓存（单条约 0.5MB），实测累积到
        # 195 条 / 96MB —— 缓存只增不减，且 id 不存在后再也不会被读到。
        try:
            latest_db = NB(DS_LATEST_DATA_TABLE)
            if entry_id in latest_db:
                del latest_db[entry_id]
        except Exception:
            pass

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
        """优先从文件加载数据源配置，NB 提供运行状态。

        匹配一个文件条目与一条 NB 记录时，**先按 id、再按 name**。

        ❗以前只按「文件名 stem == entry.name」匹配，而文件的 stem 允许与
        ``metadata.name`` 不同：``OpenRouter_TOKEN_消耗.yaml`` 的 name 是
        「OpenRouter TOKEN 消耗监控」。结果是**同一条数据源在内存里变成两条**：
        一条是 NB 旧记录（在跑，抓取一直失败），一条是文件新条目（没状态、
        永远不会启动）。改 yaml、改代码都改不到在跑的那条 —— 修了半天没反应。

        另外文件名与 name 不一致时，旧代码把 ``name`` 也设成了文件名，
        UI 上就显示成 ``OpenRouter_TOKEN_消耗``，跟用户认的名字对不上。
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

        file_items = []
        file_by_id = {}
        file_by_name = {}
        for name in file_names:
            item = file_mgr.get(name)
            if not item:
                continue
            file_items.append(item)
            fid = getattr(item.metadata, 'id', '') or ''
            if fid:
                file_by_id[fid] = item
            file_by_name[getattr(item.metadata, 'name', '') or item.name] = item
            file_by_name[item.name] = item

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

                    file_item = file_by_id.get(entry.id) or file_by_name.get(entry.name)
                    matched_by_id = bool(file_by_id.get(entry.id))
                    if file_item and file_item.metadata.source == 'file':
                        existing_time = as_epoch_seconds(getattr(entry._metadata, 'updated_at', 0))
                        file_time = as_epoch_seconds(file_item.metadata.updated_at)
                        # id 命中 = 同一实体，配置必须听文件的（否则改了没反应）；
                        # 只按 name 命中时才用时间戳判断谁更新。
                        if matched_by_id or file_time >= existing_time:
                            file_entry = self._create_entry_from_file_config(file_item)
                            if file_entry:
                                # ❗文件只提供**配置**，运行状态属于运行时：
                                # 直接把文件条目塞进去会让 `_was_running` 恒 False，
                                # 那个数据源下次重启就不再自动恢复。
                                file_entry._state = entry._state
                                file_entry._was_running = entry._was_running
                                file_entry.id = entry.id  # 以 NB 的 id 为准，避免同实体换 id
                                self._items[file_entry.id] = file_entry
                                loaded_count += 1
                                continue

                    self._items[entry.id] = entry
                    loaded_count += 1

                except Exception as e:
                    self._log("ERROR", "Load entry failed", id=entry_id, error=str(e))

            for file_item in file_items:
                try:
                    file_entry = self._create_entry_from_file_config(file_item)
                    if not file_entry:
                        continue
                    if file_entry.id in self._items:
                        continue
                    if any(e.name == file_entry.name for e in self._items.values()):
                        continue
                    self._items[file_entry.id] = file_entry
                    loaded_count += 1
                except Exception as e:
                    self._log("ERROR", f"Load from file failed: {file_item.name}", error=str(e))

        self._loaded_prefer_files = True
        return loaded_count

    def _create_entry_from_file_config(self, file_item) -> Optional['DataSourceEntry']:
        """从文件配置创建 DataSourceEntry"""
        from deva.naja.config.file_config import ConfigFileItem

        if not isinstance(file_item, ConfigFileItem):
            return None

        file_metadata = file_item.metadata
        file_config = file_item.config or {}
        file_params = file_item.parameters or {}

        # ❗interval 有三个候选位置，取值优先级必须写清楚：
        #   ① ``config.config.interval`` —— UI 里「抓取间隔」的真身（金十=300s）
        #   ② ``parameters.interval_seconds`` —— 部分文件只写了这个
        #   ③ ``metadata.interval_seconds`` —— **最不可信**：它曾被写成 0.5
        # 老代码只读 ③（`file_params.get('interval_seconds', 5.0)` 实际读的是
        # parameters，但金十那份 parameters 里也是 0.5），于是 300 秒的数据源
        # 变成「每 0s」，2 秒发 4 个请求把金十打到限流，日志里 46 条
        # 「线程池过载」，最后停在 2026-04-09 再也没动过。
        _nested = file_config.get('config') or {}
        raw_interval = (
            _nested.get('interval')
            or file_params.get('interval_seconds')
            or getattr(file_metadata, 'interval_seconds', None)
            or 5.0
        )
        try:
            interval = float(raw_interval)
        except (TypeError, ValueError):
            interval = 5.0
        if interval <= 0:
            interval = 5.0

        metadata = DataSourceMetadata(
            id=file_metadata.id or file_item.name,
            # ❗name 以 metadata.name 为准，文件名只是兜底：两者可以不同
            # （`OpenRouter_TOKEN_消耗.yaml` 的名字是「OpenRouter TOKEN 消耗监控」），
            # 用文件名当显示名会让人认不出这是哪条数据源，也让合并匹配失效。
            name=getattr(file_metadata, 'name', '') or file_item.name,
            description=file_metadata.description or '',
            tags=file_metadata.tags or [],
            source_type=file_config.get('source_type', 'timer'),
            config=_nested,
            interval=interval,
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

        if interval < 1.0 and metadata.source_type == 'timer':
            # 亚秒级定时抓取几乎总是配置事故（真实场景里没人需要 0.5s 拉一次
            # 外部 HTTP）。不阻断加载，但必须喊出来——静默地按 0.5s 打外部接口
            # 只会以「线程池过载 / 被限流」的形式在几周后暴露。
            self._log(
                "WARNING",
                "数据源 interval 小于 1 秒，疑似配置错误",
                name=file_item.name,
                interval=interval,
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

    def reload_for_recovery(self) -> int:
        """恢复流程专用重载：强制重跑合并版 ``load_prefer_files()``。

        ``RecoveryManager.restore_all()`` 以前无条件调 ``load_from_db()``，
        而 ``load_from_db()`` 是「只用 NB、``_items.clear()`` 重建」——
        文件里有、NB 里没有的数据源会在恢复那一刻**凭空消失**。
        目前两边恰好都是 5 条才没暴露，但这是定时炸弹。
        """
        self._loaded_prefer_files = False
        return self.load_prefer_files()

    def restore_running_states(self) -> dict:
        restored_count = 0
        failed_count = 0
        # 「不该恢复」≠「恢复失败」：``_was_running`` 为 False / 已在运行
        # 的条目以前既不计数也不解释，于是「5 个条目只恢复 4 个」看不出第 5 个
        # 去哪了。单独计数后一眼能分辨「跳过」和「炸了」。
        skipped_count = 0
        results = []

        with self._items_lock:
            entries_to_check = list(self._items.values())

        for entry in entries_to_check:
            try:
                prep = entry.prepare_for_recovery()

                if not prep.get("can_recover"):
                    # ``fatal``（如 compile_failed）是真故障，不能算「跳过」
                    if prep.get("fatal"):
                        failed_count += 1
                        results.append({
                            "entry_id": entry.id,
                            "entry_name": entry.name,
                            "success": False,
                            "reason": prep.get("reason"),
                            "error": prep.get("error"),
                        })
                    else:
                        skipped_count += 1
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
            "skipped_count": skipped_count,
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

        # 与任务侧同口径：受影响条目数与最近失败时间，比累计 error_count 更能
        # 回答「现在有几个采集坏着」。
        last_error_ts = 0
        for e in entries:
            last_error_ts = max(last_error_ts, getattr(e._state, "last_error_ts", 0) or 0)

        stats = {
            "total": len(entries),
            "running": running,
            "stopped": len(entries) - running,
            "error": error,
            "last_error_ts": last_error_ts,
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
