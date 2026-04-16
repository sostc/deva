"""StrategyManager - 策略管理器（单例）+ get_strategy_manager()"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Dict, List, Optional

from deva import NB

from ..infra.runtime.thread_pool import get_thread_pool
from .output_controller import get_output_controller
from .models import (
    STRATEGY_TABLE,
    STRATEGY_EXPERIMENT_TABLE,
    STRATEGY_EXPERIMENT_ACTIVE_KEY,
    StrategyMetadata,
    StrategyState,
)
from .entry import StrategyEntry

class StrategyManager:
    """策略管理器

    ================================================================================
    单例模式说明：为什么使用单例
    ================================================================================
    1. 全局唯一性：策略系统是全局资源，只能有一个实例管理所有策略的生命周期。
       如果存在多个实例，可能导致策略状态不一致。

    2. 资源管理：StrategyManager 持有策略字典（_items）和数据库连接（NB），
       这些资源应该全局共享，而非重复创建。

    3. 生命周期：Manager 的生命周期与系统一致，随系统启动和关闭。

    4. 依赖注入支持：如需测试，可以设置 _datasource_manager/_result_store
       等属性来注入 mock 对象。

    5. Manager 类本身不是资源，而是通往资源的入口点。真正的系统资源
       （如 ResultStore 管理的数据库连接）是单例的，而 Manager 类
       保持单例是为了方便访问这些资源。
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
            self._items: Dict[str, StrategyEntry] = {}
            self._items_lock = threading.Lock()
            self._experiment_lock = threading.Lock()
            self._experiment_session: Optional[Dict[str, Any]] = None
            self.load_prefer_files()
            self._initialized = True

    def health_check(self):
        """健康检查"""
        self._ensure_initialized()
        from ..infra.observability.manager_health import ManagerHealthReport

        items = list(self._items.values())
        running = sum(1 for i in items if i.is_running)
        errors = sum(1 for i in items if i._state.error_count > 0)

        return ManagerHealthReport(
            component="StrategyManager",
            healthy=errors == 0,
            timestamp=time.time(),
            item_count=len(items),
            running_count=running,
            error_count=errors,
        )

    def _normalize_categories(self, categories: List[str]) -> List[str]:
        normalized: List[str] = []
        for cat in categories or []:
            cat_name = str(cat or "").strip()
            if not cat_name:
                continue
            if cat_name not in normalized:
                normalized.append(cat_name)
        return normalized

    def _list_by_categories(self, categories: List[str]) -> List[StrategyEntry]:
        category_set = set(self._normalize_categories(categories))
        if not category_set:
            return []
        return [
            entry for entry in self.list_all()
            if str(getattr(entry._metadata, "category", "默认") or "默认") in category_set
        ]

    def _save_experiment_session(self):
        try:
            db = NB(STRATEGY_EXPERIMENT_TABLE)
            if self._experiment_session is None:
                if STRATEGY_EXPERIMENT_ACTIVE_KEY in db:
                    del db[STRATEGY_EXPERIMENT_ACTIVE_KEY]
                return
            db[STRATEGY_EXPERIMENT_ACTIVE_KEY] = self._experiment_session
        except Exception as e:
            self._log("ERROR", "Save experiment session failed", error=str(e))

    def _load_experiment_session(self):
        try:
            db = NB(STRATEGY_EXPERIMENT_TABLE)
            data = db.get(STRATEGY_EXPERIMENT_ACTIVE_KEY)
            if not isinstance(data, dict):
                self._experiment_session = None
                return

            snapshot = data.get("snapshot", {}) or {}
            normalized_snapshot = {}
            for entry_id, snap in snapshot.items():
                if entry_id not in self._items:
                    continue
                if not isinstance(snap, dict):
                    continue
                
                # 获取当前策略的配置作为默认值（兼容旧snapshot）
                entry = self._items[entry_id]
                output_ctrl = get_output_controller()
                output_cfg = output_ctrl.get_config(entry_id)
                
                normalized_snapshot[entry_id] = {
                    "entry_id": entry_id,
                    "name": snap.get("name", self._items[entry_id].name),
                    "category": snap.get("category", getattr(self._items[entry_id]._metadata, "category", "默认")),
                    "pre_experiment_bound_datasource_id": snap.get(
                        "pre_experiment_bound_datasource_id",
                        snap.get("bound_datasource_id", ""),
                    ) or "",
                    "pre_experiment_was_running": bool(
                        snap.get("pre_experiment_was_running", snap.get("was_running", False))
                    ),
                    # 输出配置快照（兼容旧snapshot：使用当前配置作为默认值）
                    "pre_experiment_output_config": snap.get("pre_experiment_output_config") or {
                        "signal": output_cfg.signal,
                        "radar": output_cfg.radar,
                        "memory": output_cfg.memory,
                        "bandit": output_cfg.bandit,
                        "radar_tags": list(output_cfg.radar_tags or []),
                        "memory_tags": list(output_cfg.memory_tags or []),
                    },
                    # 策略参数快照
                    "pre_experiment_strategy_params": snap.get("pre_experiment_strategy_params") or dict(getattr(entry._metadata, "strategy_params", {}) or {}),
                    "pre_experiment_strategy_config": snap.get("pre_experiment_strategy_config") or dict(getattr(entry._metadata, "strategy_config", {}) or {}),
                    # 窗口配置快照
                    "pre_experiment_window_size": snap.get("pre_experiment_window_size") or getattr(entry._metadata, "window_size", 5),
                    "pre_experiment_window_type": snap.get("pre_experiment_window_type") or getattr(entry._metadata, "window_type", "sliding"),
                    "pre_experiment_window_interval": snap.get("pre_experiment_window_interval") or getattr(entry._metadata, "window_interval", "10s"),
                    "pre_experiment_compute_mode": snap.get("pre_experiment_compute_mode") or getattr(entry._metadata, "compute_mode", "record"),
                    # 字典配置快照
                    "pre_experiment_dictionary_profile_ids": snap.get("pre_experiment_dictionary_profile_ids") or list(getattr(entry._metadata, "dictionary_profile_ids", []) or []),
                    # 历史记录配置快照
                    "pre_experiment_max_history_count": snap.get("pre_experiment_max_history_count") or getattr(entry._metadata, "max_history_count", 100),
                    # 兼容旧字段
                    "bound_datasource_id": snap.get("bound_datasource_id", "") or "",
                    "was_running": bool(snap.get("was_running", False)),
                }

            if not normalized_snapshot:
                self._experiment_session = None
                if STRATEGY_EXPERIMENT_ACTIVE_KEY in db:
                    del db[STRATEGY_EXPERIMENT_ACTIVE_KEY]
                return

            self._experiment_session = {
                "active": bool(data.get("active", True)),
                "started_at": float(data.get("started_at", time.time())),
                "datasource_id": str(data.get("datasource_id", "") or ""),
                "datasource_name": str(data.get("datasource_name", "") or ""),
                "categories": self._normalize_categories(data.get("categories", [])),
                "target_count": int(data.get("target_count", len(normalized_snapshot))),
                "snapshot": normalized_snapshot,
            }
            self._save_experiment_session()
        except Exception as e:
            self._experiment_session = None
            self._log("ERROR", "Load experiment session failed", error=str(e))
    
    def create(
        self,
        name: str,
        func_code: str,
        bound_datasource_id: str = "",
        bound_datasource_ids: List[str] = None,
        description: str = "",
        compute_mode: str = "record",
        window_size: int = None,
        window_type: str = "sliding",
        window_interval: str = None,
        window_return_partial: bool = False,
        max_history_count: int = None,
        dictionary_profile_ids: List[str] = None,
        tags: List[str] = None,
        category: str = "默认",
        strategy_type: str = "legacy",
        strategy_params: Dict[str, Any] = None,
        strategy_config: Dict[str, Any] = None,
        handler_type: str = "unknown",
    ) -> dict:
        from ..config import get_strategy_config

        import hashlib
        entry_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:12]

        # 使用配置默认值
        strategy_config = get_strategy_config()
        if window_size is None:
            window_size = strategy_config.get("default_window_size", 5)
        if max_history_count is None:
            max_history_count = strategy_config.get("single_history_count", 30)
        if window_interval is None:
            window_interval = strategy_config.get("default_window_interval", "10s")

        normalized_type = str(strategy_type or "legacy").strip().lower()
        if normalized_type == "legacy":
            if "process" not in func_code:
                return {"success": False, "error": "代码必须包含 process 函数"}
        elif not func_code:
            func_code = "def process(data, context=None):\n    return None\n"

        # 处理多数据源绑定
        if bound_datasource_ids is None:
            bound_datasource_ids = [bound_datasource_id] if bound_datasource_id else []
        elif bound_datasource_id and bound_datasource_id not in bound_datasource_ids:
            # 如果提供了单数据源但不在列表中，添加到列表
            bound_datasource_ids = [bound_datasource_id] + list(bound_datasource_ids)

        metadata = StrategyMetadata(
            id=entry_id,
            name=name,
            description=description,
            tags=tags or [],
            bound_datasource_id=bound_datasource_ids[0] if bound_datasource_ids else "",  # 兼容单数据源
            bound_datasource_ids=bound_datasource_ids,
            compute_mode=compute_mode,
            window_size=window_size,
            window_type=window_type,
            window_interval=window_interval,
            window_return_partial=window_return_partial,
            dictionary_profile_ids=dictionary_profile_ids or [],
            max_history_count=max_history_count,
            category=category or "默认",
            strategy_type=normalized_type or "legacy",
            strategy_params=strategy_params or {},
            strategy_config=strategy_config or {},
            handler_type=handler_type or "unknown",
        )
        
        entry = StrategyEntry(metadata=metadata)
        entry._func_code = func_code
        
        result = entry.compile_code()
        if not result["success"]:
            return {"success": False, "error": f"编译失败: {result['error']}"}
        
        with self._items_lock:
            if any(e.name == name for e in self._items.values()):
                return {"success": False, "error": f"策略名称已存在: {name}"}
            self._items[entry_id] = entry
        
        entry.save()
        
        self._log("INFO", "Strategy created", id=entry_id, name=name)
        return {"success": True, "id": entry_id, "entry": entry.to_dict()}
    
    def get(self, entry_id: str) -> Optional[StrategyEntry]:
        self._ensure_initialized()
        return self._items.get(entry_id)

    def get_by_name(self, name: str) -> Optional[StrategyEntry]:
        self._ensure_initialized()
        for entry in self._items.values():
            if entry.name == name:
                return entry
        return None

    def list_all(self) -> List[StrategyEntry]:
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
        
        db = NB(STRATEGY_TABLE)
        if entry_id in db:
            del db[entry_id]
        
        self._log("INFO", "Strategy deleted", id=entry_id, name=entry.name)
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

    def get_experiment_info(self) -> dict:
        self._ensure_initialized()
        with self._experiment_lock:
            session = self._experiment_session
            if not session:
                return {"active": False}
            info = dict(session)
            info.pop("snapshot", None)
            return info

    def start_experiment(self, categories: List[str], datasource_id: str, include_attention: bool = True) -> dict:
        normalized_categories = self._normalize_categories(categories)
        datasource_id = str(datasource_id or "").strip()

        if not normalized_categories and not include_attention:
            return {"success": False, "error": "请至少选择一个策略类别或启用注意力策略"}
        if not datasource_id:
            return {"success": False, "error": "请先选择实验数据源"}

        from ..radar.trading_clock import is_trading_time as is_trading_time_clock
        if is_trading_time_clock():
            return {"success": False, "error": "当前处于交易时间，实验模式需要在非交易时间启动（请在收盘后或周末操作）"}

        with self._experiment_lock:
            if self._experiment_session is not None:
                return {"success": False, "error": "实验模式已开启，请先关闭"}

            from ..datasource import get_datasource_manager
            ds_mgr = get_datasource_manager()
            ds_entry = ds_mgr.get(datasource_id)
            if ds_entry is None:
                return {"success": False, "error": "实验数据源不存在"}

            # 开启实验时确保实验数据源处于运行中（如“回放行情”）
            datasource_started = False
            datasource_start_error = ""
            if not ds_entry.is_running:
                ds_start_result = ds_entry.start()
                if not ds_start_result.get("success"):
                    datasource_start_error = ds_start_result.get("error", "unknown error")
                    return {"success": False, "error": f"实验数据源启动失败: {datasource_start_error}"}
                datasource_started = True

            target_entries = self._list_by_categories(normalized_categories)
            # 允许只运行注意力策略（不选择其他策略类别）
            if not target_entries and not include_attention:
                return {"success": False, "error": "所选类别下没有策略"}

            snapshot: Dict[str, Dict[str, Any]] = {}
            failed_switch = []
            started = 0
            failed_start = []

            for entry in target_entries:
                # 获取输出配置
                output_ctrl = get_output_controller()
                output_cfg = output_ctrl.get_config(entry.id)
                
                snapshot[entry.id] = {
                    "entry_id": entry.id,
                    "name": entry.name,
                    "category": getattr(entry._metadata, "category", "默认") or "默认",
                    # 实验前快照（关闭实验时用于恢复）
                    "pre_experiment_bound_datasource_id": getattr(entry._metadata, "bound_datasource_id", "") or "",
                    "pre_experiment_was_running": bool(entry.is_running),
                    # 输出配置快照
                    "pre_experiment_output_config": {
                        "signal": output_cfg.signal,
                        "radar": output_cfg.radar,
                        "memory": output_cfg.memory,
                        "bandit": output_cfg.bandit,
                        "radar_tags": list(output_cfg.radar_tags or []),
                        "memory_tags": list(output_cfg.memory_tags or []),
                    },
                    # 策略参数快照
                    "pre_experiment_strategy_params": dict(getattr(entry._metadata, "strategy_params", {}) or {}),
                    "pre_experiment_strategy_config": dict(getattr(entry._metadata, "strategy_config", {}) or {}),
                    # 窗口配置快照
                    "pre_experiment_window_size": getattr(entry._metadata, "window_size", 5),
                    "pre_experiment_window_type": getattr(entry._metadata, "window_type", "sliding"),
                    "pre_experiment_window_interval": getattr(entry._metadata, "window_interval", "10s"),
                    "pre_experiment_compute_mode": getattr(entry._metadata, "compute_mode", "record"),
                    # 字典配置快照
                    "pre_experiment_dictionary_profile_ids": list(getattr(entry._metadata, "dictionary_profile_ids", []) or []),
                    # 历史记录配置快照
                    "pre_experiment_max_history_count": getattr(entry._metadata, "max_history_count", 100),
                    # 兼容旧字段
                    "bound_datasource_id": getattr(entry._metadata, "bound_datasource_id", "") or "",
                    "was_running": bool(entry.is_running),
                }

                switch_result = entry.update_config(bound_datasource_id=datasource_id)
                if not switch_result.get("success"):
                    failed_switch.append({
                        "entry_id": entry.id,
                        "name": entry.name,
                        "error": switch_result.get("error", "unknown error"),
                    })
                    continue

                if not entry.is_running:
                    start_result = entry.start()
                    if start_result.get("success"):
                        started += 1
                    else:
                        failed_start.append({
                            "entry_id": entry.id,
                            "name": entry.name,
                            "error": start_result.get("error", "unknown error"),
                        })

            switched_ok = len(target_entries) - len(failed_switch)
            # 允许只运行注意力策略（原有策略数为0但注意力策略已启动）
            if switched_ok <= 0 and not include_attention:
                return {
                    "success": False,
                    "error": "未能切换任何策略到实验数据源",
                    "categories": normalized_categories,
                    "target_count": len(target_entries),
                    "failed_switch": failed_switch,
                    "failed_start": failed_start,
                }

            self._experiment_session = {
                "active": True,
                "started_at": time.time(),
                "datasource_id": datasource_id,
                "datasource_name": ds_entry.name,
                "categories": normalized_categories,
                "target_count": len(target_entries),
                "snapshot": snapshot,
            }
            self._save_experiment_session()
            
            # 启动注意力策略的实验模式（如果用户选择包含）
            attention_started = False
            if include_attention:
                try:
                    from deva.naja.market_hotspot.strategies import get_strategy_manager
                    attention_manager = get_strategy_manager()
                    attention_result = attention_manager.start_experiment(datasource_id)
                    if attention_result.get("success"):
                        print(f"✅ 注意力策略实验模式已启动: {datasource_id}")
                        attention_started = True
                    else:
                        print(f"⚠️ 注意力策略实验模式启动失败: {attention_result.get('error')}")
                except Exception as e:
                    print(f"⚠️ 启动注意力策略实验模式失败: {e}")
            
            # 保存实验会话时记录是否包含注意力策略
            self._experiment_session["include_attention"] = include_attention

            return {
                "success": True,
                "active": True,
                "datasource_id": datasource_id,
                "datasource_name": ds_entry.name,
                "categories": normalized_categories,
                "target_count": len(target_entries),
                "switched_count": switched_ok,
                "started_count": started,
                "datasource_started": datasource_started,
                "failed_switch": failed_switch,
                "failed_start": failed_start,
                "include_attention": include_attention,
                "attention_started": attention_started,
            }

    def stop_experiment(self) -> dict:
        with self._experiment_lock:
            session = self._experiment_session
            if not session:
                return {"success": False, "error": "实验模式未开启"}

            snapshot = session.get("snapshot", {}) or {}
            restored_bind = 0
            restored_run = 0
            restored_output = 0
            restored_params = 0
            restored_window = 0
            failed = []

            for entry_id, snap in snapshot.items():
                entry = self.get(entry_id)
                if entry is None:
                    failed.append({
                        "entry_id": entry_id,
                        "name": snap.get("name", ""),
                        "error": "策略不存在",
                    })
                    continue

                prev_ds_id = snap.get(
                    "pre_experiment_bound_datasource_id",
                    snap.get("bound_datasource_id", ""),
                ) or ""
                prev_running = bool(
                    snap.get("pre_experiment_was_running", snap.get("was_running", False))
                )

                # 1. 恢复输出配置
                output_config = snap.get("pre_experiment_output_config")
                if output_config:
                    try:
                        output_ctrl = get_output_controller()
                        from .output_controller import OutputConfig
                        new_output_cfg = OutputConfig(
                            strategy_id=entry_id,
                            signal=output_config.get("signal", True),
                            radar=output_config.get("radar", True),
                            memory=output_config.get("memory", True),
                            bandit=output_config.get("bandit", False),
                            radar_tags=output_config.get("radar_tags", []),
                            memory_tags=output_config.get("memory_tags", []),
                        )
                        output_ctrl.set_config(new_output_cfg)
                        restored_output += 1
                    except Exception as e:
                        failed.append({
                            "entry_id": entry_id,
                            "name": snap.get("name", ""),
                            "error": f"恢复输出配置失败: {str(e)}",
                        })
                        continue

                # 2. 恢复策略参数和策略配置
                strategy_params = snap.get("pre_experiment_strategy_params")
                strategy_config = snap.get("pre_experiment_strategy_config")
                if strategy_params is not None or strategy_config is not None:
                    try:
                        update_result = entry.update_config(
                            strategy_params=strategy_params,
                            strategy_config=strategy_config,
                        )
                        if update_result.get("success"):
                            restored_params += 1
                        else:
                            failed.append({
                                "entry_id": entry_id,
                                "name": entry.name,
                                "error": f"恢复策略参数失败: {update_result.get('error', 'unknown error')}",
                            })
                            continue
                    except Exception as e:
                        failed.append({
                            "entry_id": entry_id,
                            "name": snap.get("name", ""),
                            "error": f"恢复策略参数失败: {str(e)}",
                        })
                        continue

                # 3. 恢复窗口配置和计算模式
                window_size = snap.get("pre_experiment_window_size")
                window_type = snap.get("pre_experiment_window_type")
                window_interval = snap.get("pre_experiment_window_interval")
                compute_mode = snap.get("pre_experiment_compute_mode")
                if window_size or window_type or window_interval or compute_mode:
                    try:
                        update_result = entry.update_config(
                            window_size=window_size,
                            window_type=window_type,
                            window_interval=window_interval,
                            compute_mode=compute_mode,
                        )
                        if update_result.get("success"):
                            restored_window += 1
                    except Exception:
                        pass

                # 4. 恢复字典配置
                dictionary_profile_ids = snap.get("pre_experiment_dictionary_profile_ids")
                if dictionary_profile_ids is not None:
                    try:
                        entry.update_config(dictionary_profile_ids=dictionary_profile_ids)
                    except Exception:
                        pass

                # 5. 恢复历史记录配置
                max_history_count = snap.get("pre_experiment_max_history_count")
                if max_history_count is not None:
                    try:
                        entry.update_config(max_history_count=max_history_count)
                    except Exception:
                        pass

                # 6. 恢复数据源绑定
                bind_result = entry.update_config(bound_datasource_id=prev_ds_id)
                if not bind_result.get("success"):
                    failed.append({
                        "entry_id": entry.id,
                        "name": entry.name,
                        "error": f"恢复数据源失败: {bind_result.get('error', 'unknown error')}",
                    })
                    continue
                restored_bind += 1

                # 7. 恢复运行状态
                state_result = {"success": True}
                if prev_running and not entry.is_running:
                    state_result = entry.start()
                elif not prev_running and entry.is_running:
                    state_result = entry.stop()

                if state_result.get("success"):
                    restored_run += 1
                else:
                    failed.append({
                        "entry_id": entry.id,
                        "name": entry.name,
                        "error": f"恢复运行状态失败: {state_result.get('error', 'unknown error')}",
                    })

            # 停止注意力策略的实验模式（如果启动时包含）
            include_attention = session.get("include_attention", True)
            if include_attention:
                try:
                    from deva.naja.market_hotspot.strategies import get_strategy_manager
                    attention_manager = get_strategy_manager()
                    attention_result = attention_manager.stop_experiment()
                    if attention_result.get("success"):
                        print(f"✅ 注意力策略实验模式已停止")
                    else:
                        print(f"⚠️ 注意力策略实验模式停止失败: {attention_result.get('error')}")
                except Exception as e:
                    print(f"⚠️ 停止注意力策略实验模式失败: {e}")

                try:
                    from deva.naja.market_hotspot.integration import get_mode_manager
                    mode_manager = get_mode_manager()
                    if mode_manager.is_lab_mode():
                        mode_manager.exit_lab_mode()
                        print(f"✅ 注意力模式管理器已退出实验模式，恢复正常交易")
                except Exception as e:
                    print(f"⚠️ 退出实验模式失败: {e}")

            if not failed:
                self._experiment_session = None
                self._save_experiment_session()
                return {
                    "success": True,
                    "active": False,
                    "restored_bind_count": restored_bind,
                    "restored_state_count": restored_run,
                    "restored_output_count": restored_output,
                    "restored_params_count": restored_params,
                    "restored_window_count": restored_window,
                    "failed": failed,
                }

            return {
                "success": False,
                "active": True,
                "error": "部分策略恢复失败，请修复后重试关闭实验模式",
                "restored_bind_count": restored_bind,
                "restored_state_count": restored_run,
                "restored_output_count": restored_output,
                "restored_params_count": restored_params,
                "restored_window_count": restored_window,
                "failed": failed,
            }
    
    def load_from_db(self) -> int:
        db = NB(STRATEGY_TABLE)
        count = 0
        
        with self._items_lock:
            self._items.clear()
            
            for entry_id, data in list(db.items()):
                if not isinstance(data, dict):
                    continue
                
                try:
                    entry = StrategyEntry.from_dict(data)
                    if not entry.id:
                        continue
                    
                    self._items[entry.id] = entry
                    count += 1
                    
                except Exception as e:
                    self._log("ERROR", "Load entry failed", id=entry_id, error=str(e))

        with self._experiment_lock:
            self._load_experiment_session()

        return count

    def load_prefer_files(self) -> int:
        """只从文件加载策略配置，不再从 NB 加载

        加载策略：
        1. 扫描 config/strategies/ 目录下的所有 YAML 文件
        2. 为每个文件创建 StrategyEntry
        3. 文件名作为策略名

        Returns:
            加载的策略数量
        """
        from deva.naja.config.file_config import get_file_config_manager

        file_mgr = get_file_config_manager('strategy')
        file_names = file_mgr.list_names()

        loaded_count = 0

        if not hasattr(self, '_items') or self._items is None:
            self._items = {}
        if not hasattr(self, '_items_lock') or self._items_lock is None:
            self._items_lock = threading.Lock()
        if not hasattr(self, '_experiment_lock') or self._experiment_lock is None:
            self._experiment_lock = threading.Lock()
        if not hasattr(self, '_experiment_session'):
            self._experiment_session = None

        with self._items_lock:
            self._items.clear()

            for name in file_names:
                file_item = file_mgr.get(name)
                if not file_item:
                    continue

                try:
                    file_entry = self._create_entry_from_file_config(file_item)
                    if file_entry:
                        self._items[file_entry.id] = file_entry
                        loaded_count += 1
                except Exception as e:
                    self._log("ERROR", f"Load from file failed: {name}", error=str(e))

        with self._experiment_lock:
            self._load_experiment_session()

        return loaded_count

    def _create_entry_from_file_config(self, file_item) -> Optional['StrategyEntry']:
        """从文件配置创建 StrategyEntry"""
        from deva.naja.config.file_config import ConfigFileItem

        if not isinstance(file_item, ConfigFileItem):
            return None

        file_metadata = file_item.metadata
        file_config = file_item.config
        file_params = file_item.parameters

        metadata = StrategyMetadata(
            id=file_metadata.id or file_item.name,
            name=file_item.name,
            description=file_metadata.description or '',
            tags=file_metadata.tags or [],
            category=file_metadata.category or '默认',
            bound_datasource_id=file_config.get('bound_datasource_id', ''),
            bound_datasource_ids=file_config.get('bound_datasource_ids', []),
            compute_mode=file_config.get('compute_mode', 'record'),
            window_size=file_params.get('window_size', 5),
            window_type=file_config.get('window_type', 'sliding'),
            window_interval=file_config.get('window_interval', '10s'),
            window_return_partial=file_config.get('window_return_partial', False),
            dictionary_profile_ids=file_config.get('dictionary_profile_ids', []),
            max_history_count=file_params.get('max_history_count', 100),
            strategy_type=file_config.get('strategy_type', 'legacy'),
            handler_type=file_config.get('handler_type', 'unknown'),
            version=1,
            created_at=file_metadata.created_at or time.time(),
            updated_at=file_metadata.updated_at or time.time(),
        )

        state = StrategyState()
        entry = StrategyEntry(metadata=metadata, state=state)

        if file_item.func_code:
            entry._func_code = file_item.func_code
            try:
                entry.compile_code()
            except Exception:
                pass

        return entry

    def reload_entry(self, entry_id: str) -> dict:
        """热重载单个策略（从数据库重新加载配置和代码）
        
        Args:
            entry_id: 策略ID
            
        Returns:
            重载结果
        """
        db = NB(STRATEGY_TABLE)
        data = db.get(entry_id)
        
        if not data or not isinstance(data, dict):
            return {"success": False, "error": "策略不存在"}
        
        try:
            # 获取当前运行状态
            current_entry = self._items.get(entry_id)
            was_running = current_entry and current_entry.is_running
            
            # 先停止旧的策略
            if current_entry and current_entry.is_running:
                current_entry.stop()
                self._log("INFO", "Stopped old strategy before reload", id=entry_id)
            
            # 从数据库加载新数据
            new_entry = StrategyEntry.from_dict(data)
            
            with self._items_lock:
                self._items[entry_id] = new_entry
            
            # 如果之前在运行，重新启动
            if was_running:
                new_entry.start()
            
            self._log("INFO", "Strategy reloaded", id=entry_id, name=new_entry.name, was_running=was_running)
            return {
                "success": True, 
                "entry": new_entry.to_dict(),
                "was_running": was_running,
                "restarted": was_running,
            }
            
        except Exception as e:
            self._log("ERROR", "Reload entry failed", id=entry_id, error=str(e))
            return {"success": False, "error": str(e)}
    
    def reload_all(self) -> dict:
        """热重载所有策略（从数据库重新加载）
        
        Returns:
            重载结果统计
        """
        db = NB(STRATEGY_TABLE)
        reloaded = 0
        failed = 0
        results = []
        
        for entry_id, data in list(db.items()):
            if not isinstance(data, dict):
                continue
            
            result = self.reload_entry(entry_id)
            if result.get("success"):
                reloaded += 1
            else:
                failed += 1
            results.append({"id": entry_id, "result": result})
        
        self._log("INFO", "Reload all finished", reloaded=reloaded, failed=failed)
        return {
            "success": True,
            "reloaded": reloaded,
            "failed": failed,
            "results": results,
        }
    
    def restore_running_states(self) -> dict:
        restored_count = 0
        failed_count = 0
        results = []

        with self._items_lock:
            entries_to_check = list(self._items.values())

        if not entries_to_check:
            return {
                "success": True,
                "restored_count": 0,
                "failed_count": 0,
                "results": [],
            }

        from ..infra.runtime.thread_pool import get_thread_pool
        pool = get_thread_pool()
        futures = {}

        def restore_one(entry):
            try:
                prep = entry.prepare_for_recovery()

                if not prep.get("can_recover"):
                    return {
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": False,
                        "reason": prep.get("reason"),
                    }

                result = entry.start()

                if result.get("success"):
                    return {
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": True,
                    }
                else:
                    return {
                        "entry_id": entry.id,
                        "entry_name": entry.name,
                        "success": False,
                        "error": result.get("error"),
                    }

            except Exception as e:
                return {
                    "entry_id": entry.id,
                    "entry_name": entry.name,
                    "success": False,
                    "error": str(e),
                }

        for entry in entries_to_check:
            try:
                future = pool.submit(restore_one, entry)
                futures[future] = entry.id
            except RuntimeError:
                restore_one(entry)

        if futures:
            for future in futures:
                try:
                    result = future.result(timeout=30)
                    results.append(result)
                    if result.get("success"):
                        restored_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    entry_id = futures.get(future, "unknown")
                    results.append({
                        "entry_id": entry_id,
                        "success": False,
                        "error": str(e),
                    })
        else:
            for entry in entries_to_check:
                result = restore_one(entry)
                results.append(result)
                if result.get("success"):
                    restored_count += 1
                else:
                    failed_count += 1

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
        self._ensure_initialized()
        entries = self.list_all()
        running = sum(1 for e in entries if e.is_running)
        
        total_processed = sum(e._state.processed_count for e in entries)
        total_output = sum(e._state.output_count for e in entries)
        
        return {
            "total": len(entries),
            "running": running,
            "stopped": len(entries) - running,
            "total_processed": total_processed,
            "total_output": total_output,
        }
    
    def get_performance_stats(self) -> dict:
        """获取策略性能统计"""
        try:
            from deva.naja.infra.observability.performance_monitor import get_performance_monitor
            monitor = get_performance_monitor()
            return monitor.get_slow_strategies_summary()
        except Exception as e:
            return {"error": str(e)}
    
    def get_performance_report(self) -> str:
        """获取策略性能报告"""
        try:
            from deva.naja.infra.observability.performance_monitor import get_performance_monitor
            monitor = get_performance_monitor()
            return monitor.get_performance_report()
        except Exception as e:
            return f"获取性能报告失败: {e}"
    
    def _log(self, level: str, message: str, **extra):
        extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
        print(f"[StrategyManager][{level}] {message} | {extra_str}")


def get_strategy_manager() -> StrategyManager:
    from deva.naja.register import SR
    return SR('strategy_manager')

