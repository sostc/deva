"""StrategyManager - 策略管理器（单例）+ get_strategy_manager()"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from ..infra.management.base_manager import CatalogManagerMixin, SingletonLazyManager
from ..infra.runtime.recoverable import as_epoch_seconds
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


logger = logging.getLogger(__name__)


def _get_nb():
    """延迟加载 NB 避免循环导入"""
    from deva import NB
    return NB


def _as_ts(value) -> float:
    """时间戳归一（date / datetime / 数字 / 字符串 → epoch 秒）。见中央实现。"""
    return as_epoch_seconds(value)


class StrategyManager(SingletonLazyManager, CatalogManagerMixin[StrategyEntry]):
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

    def __init__(self):
        pass

    def _initialize_manager_state(self):
        self._items: Dict[str, StrategyEntry] = {}
        # ❗外部体系（热点策略等）挂进来的条目单独存放，不进 _items。
        # 原因：``load_prefer_files()`` / ``load_from_db()`` 都会 ``_items.clear()``
        # 再重灌文件/NB 条目 —— 外部条目混在 _items 里会被一次重载**静默抹掉**，
        # 表现为「首页策略数忽大忽小」。分开放 + list_all() 合并，重载就伤不到它。
        self._external_items: Dict[str, StrategyEntry] = {}
        self._items_lock = threading.Lock()
        self._experiment_lock = threading.Lock()
        self._experiment_session: Optional[Dict[str, Any]] = None
        self._last_load_report: Dict[str, Any] = {}
        self.load_prefer_files()

    def attach_external_entry(self, entry) -> bool:
        """挂接一个**外部体系**的策略条目（如热点策略包装器）。

        与 ``create()`` 的区别：不写 NB、不参与 ``reload_all()`` / 启停恢复，
        因为它的生命周期由它自己的体系管（热点策略由 HotspotStrategyManager 管）。
        这里只解决「让它在策略列表与统计里被看见」。

        ❗失败必须返回 False 并留痕，调用方**不许** ``except: pass`` 吞掉 ——
        热点策略曾因汇入代码里一个不存在的 import 名字 + 静默 except，
        14 个在跑的策略从首页消失了整整一天且日志零痕迹。
        """
        self._ensure_initialized()
        entry_id = str(getattr(entry, "id", "") or "")
        if not entry_id:
            logger.warning("[StrategyManager] 挂接外部策略失败：条目缺 id")
            return False
        try:
            with self._items_lock:
                # 文件/NB 条目优先：同名时以 _items 为准，外部只补空缺
                if entry_id in self._items:
                    return True
                self._external_items[entry_id] = entry
            return True
        except Exception as e:
            logger.warning("[StrategyManager] 挂接外部策略 %s 失败（%s: %s）",
                           entry_id, type(e).__name__, e)
            return False

    def detach_external_entry(self, entry_id: str) -> bool:
        """摘掉一个外部挂接条目。"""
        self._ensure_initialized()
        try:
            with self._items_lock:
                return self._external_items.pop(entry_id, None) is not None
        except Exception:
            return False

    def list_external(self) -> List[StrategyEntry]:
        """只看外部挂接进来的条目（热点策略等）。"""
        self._ensure_initialized()
        try:
            with self._items_lock:
                return list(self._external_items.values())
        except Exception:
            return []

    def list_all(self) -> List[StrategyEntry]:
        """文件/NB 条目 + 外部挂接条目（按 id 去重，前者优先）。

        ❗重载（``load_prefer_files`` / ``load_from_db``）只会清 ``_items``，
        外部条目在 ``_external_items`` 里不受影响，所以首页策略数不会因重载跳变。
        """
        self._ensure_initialized()
        try:
            with self._items_lock:
                merged = {e.id: e for e in self._external_items.values()}
                merged.update({e.id: e for e in self._items.values()})
                return list(merged.values())
        except Exception:
            return list(self._items.values())

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
            db = _get_nb()(STRATEGY_EXPERIMENT_TABLE)
            if self._experiment_session is None:
                if STRATEGY_EXPERIMENT_ACTIVE_KEY in db:
                    del db[STRATEGY_EXPERIMENT_ACTIVE_KEY]
                return
            db[STRATEGY_EXPERIMENT_ACTIVE_KEY] = self._experiment_session
        except Exception as e:
            self._log("ERROR", "Save experiment session failed", error=str(e))

    def _load_experiment_session(self):
        try:
            db = _get_nb()(STRATEGY_EXPERIMENT_TABLE)
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
    
    def delete(self, entry_id: str) -> dict:
        self._ensure_initialized()
        entry = self.get(entry_id)
        if not entry:
            return {"success": False, "error": "Entry not found"}
        
        entry.stop()
        
        with self._items_lock:
            self._items.pop(entry_id, None)
        
        db = _get_nb()(STRATEGY_TABLE)
        if entry_id in db:
            del db[entry_id]
        
        self._log("INFO", "Strategy deleted", id=entry_id, name=entry.name)
        return {"success": True}
    
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
        db = _get_nb()(STRATEGY_TABLE)
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
        """加载策略：NB 条目作基线（带运行状态），文件配置按 ``updated_at`` 覆盖。

        ❗这里原来是「只用文件」：``self._items.clear()`` 后只塞文件条目，
        而 ``_create_entry_from_file_config`` 里 ``StrategyState()`` 是全新构造的
        —— ``_was_running`` 恒为 False。后果是双重的：

        1. 重启后**一个策略都不会自动恢复**（``should_restore()`` 只看
           ``_was_running``，不看文件里的 ``enabled``）；
        2. 恢复流程再走 ``load_from_db()``，把内存里 14 条文件策略换成 NB 里
           3 条历史残留，**另外 11 条静默消失**，UI 上「策略」只剩 3 个。

        数据源那边早就用「DB 基线 + 文件较新则覆盖」的写法，状态才留得住。
        策略现在对齐：文件只提供**配置**，运行状态一律从 NB 继承，
        文件比 NB 旧的条目直接保留 NB 版本（否则每次重启都清一次 ``was_running``）。
        """
        from deva.naja.config.file_config import get_file_config_manager

        file_mgr = get_file_config_manager('strategy')
        file_names = file_mgr.list_names()

        loaded_count = 0
        overridden = 0
        inherited_state = 0
        failed = []

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

            # ① DB 基线：只有这里带着 was_running / state
            try:
                db = _get_nb()(STRATEGY_TABLE)
                for entry_id, data in list(db.items()):
                    if not isinstance(data, dict):
                        continue
                    try:
                        entry = StrategyEntry.from_dict(data)
                        if not entry.id:
                            continue
                        self._items[entry.id] = entry
                        loaded_count += 1
                    except Exception as e:
                        failed.append(("db", entry_id, str(e)))
                        self._log("ERROR", "Load entry failed", id=entry_id, error=str(e))
            except Exception as e:
                self._log("ERROR", "Load strategy db baseline failed", error=str(e))

            # ② 文件覆盖：配置以文件为准，状态从基线继承
            for name in file_names:
                file_item = file_mgr.get(name)
                if not file_item:
                    continue

                try:
                    file_entry = self._create_entry_from_file_config(file_item)
                    if not file_entry:
                        continue

                    existing = self._items.get(file_entry.id)
                    if existing is not None:
                        file_time = _as_ts(getattr(file_item.metadata, 'updated_at', 0))
                        db_time = _as_ts(getattr(existing._metadata, 'updated_at', 0))
                        if file_time and db_time and file_time < db_time:
                            # NB 更新：保留 NB 条目（它带着运行状态）
                            continue
                        # 文件更新：用文件配置，但**不许丢掉运行状态**
                        file_entry._state = existing._state
                        file_entry._was_running = existing._was_running
                        inherited_state += 1
                        overridden += 1
                    else:
                        loaded_count += 1

                    self._items[file_entry.id] = file_entry
                except Exception as e:
                    failed.append(("file", name, str(e)))
                    self._log("ERROR", f"Load from file failed: {name}", error=str(e))

        with self._experiment_lock:
            self._load_experiment_session()

        self._last_load_report = {
            "total": len(self._items),
            "from_db": loaded_count,
            "from_file_overridden": overridden,
            "state_inherited": inherited_state,
            "failed": failed,
        }
        if failed:
            # ❗加载失败不许静默：以前这里只有 _log，UI 上看不出「少了一个策略」
            self._log(
                "ERROR",
                f"策略加载: {len(self._items)} 条，{len(failed)} 条失败",
                failed=[f"{k}:{n}" for k, n, _ in failed],
            )
        return len(self._items)

    def reload_for_recovery(self) -> int:
        """恢复流程专用重载：等价于 ``load_prefer_files()``。

        ``RecoveryManager.restore_all()`` 以前无条件调 ``load_from_db()``，
        对策略来说是把文件配置整体换成 NB 残留（14 → 3）。有了这个方法，
        恢复前的重载与启动时的加载走同一条路径，不再出现两套真相。
        """
        return self.load_prefer_files()

    def _create_entry_from_file_config(self, file_item) -> Optional['StrategyEntry']:
        """从文件配置创建 StrategyEntry"""
        from deva.naja.config.file_config import ConfigFileItem

        if not isinstance(file_item, ConfigFileItem):
            return None

        file_metadata = file_item.metadata
        file_config = file_item.config or {}
        file_params = file_item.parameters or {}

        def _pick(key: str, default=None):
            """config 段优先，metadata 段兜底，parameters 段最后。

            ❗yaml 里 ``bound_datasource_id`` / ``window_*`` / ``handler_type``
            / ``strategy_type`` 实际都写在 **metadata** 段（UI 导出格式），
            而老代码只读 ``config`` 段 → 这些字段全部退回默认值：
            策略看着「已绑定数据源」，其实 ``bound_datasource_id`` 是空串，
            启动后拿不到任何数据；``strategy_type`` 也退回 ``legacy``。
            读不到就是读不到，但**静默变成默认值**比报错难查得多。
            """
            if key in file_config and file_config[key] not in (None, ''):
                return file_config[key]
            val = getattr(file_metadata, key, None)
            if val not in (None, ''):
                return val
            if key in file_params and file_params[key] not in (None, ''):
                return file_params[key]
            return default

        metadata = StrategyMetadata(
            id=file_metadata.id or file_item.name,
            # ❗name 以 metadata.name 为准（文件名只是兜底）。文件名与 name
            # 不一致时（`OpenRouter_TOKEN_趋势分析.yaml` vs 「OpenRouter TOKEN 趋势分析」），
            # 用文件名当显示名既认不出，也让「按 name 合并」失效 → 同一条策略变两条。
            name=getattr(file_metadata, 'name', '') or file_item.name,
            description=file_metadata.description or '',
            tags=file_metadata.tags or [],
            category=file_metadata.category or '默认',
            bound_datasource_id=_pick('bound_datasource_id', '') or '',
            bound_datasource_ids=_pick('bound_datasource_ids', []) or [],
            compute_mode=_pick('compute_mode', 'record'),
            window_size=_pick('window_size', 5),
            window_type=_pick('window_type', 'sliding'),
            window_interval=_pick('window_interval', '10s'),
            window_return_partial=_pick('window_return_partial', False),
            dictionary_profile_ids=_pick('dictionary_profile_ids', []) or [],
            max_history_count=_pick('max_history_count', 100),
            strategy_type=_pick('strategy_type', 'legacy'),
            handler_type=_pick('handler_type', 'unknown'),
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
        db = _get_nb()(STRATEGY_TABLE)
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
        db = _get_nb()(STRATEGY_TABLE)
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
        # 「本来就不该恢复」不是失败：``_was_running`` 为 False 的条目
        # ``should_restore()`` 返回 (False, "")，以前会被计进 failed_count，
        # 于是日志天天报「strategy 恢复失败 2 个」，而那两个策略只是从没被启动过。
        # 失败摘要会撒谎，比没有摘要更毒。
        skipped_count = 0
        results = []

        with self._items_lock:
            entries_to_check = list(self._items.values())

        if not entries_to_check:
            return {
                "success": True,
                "restored_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "results": [],
            }

        from ..infra.runtime.thread_pool import get_thread_pool
        pool = get_thread_pool()
        futures = {}

        def restore_one(entry):
            try:
                prep = entry.prepare_for_recovery()

                if not prep.get("can_recover"):
                    if prep.get("fatal"):
                        # 编译不过/构建不出运行时是真故障，带上 error 让上层计入 failed
                        return {
                            "entry_id": entry.id,
                            "entry_name": entry.name,
                            "success": False,
                            "reason": prep.get("reason"),
                            "error": prep.get("error") or prep.get("reason"),
                        }
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
                    elif "error" in result:
                        failed_count += 1
                    else:
                        skipped_count += 1
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
                elif "error" in result:
                    failed_count += 1
                else:
                    skipped_count += 1

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
    
def get_strategy_manager() -> StrategyManager:
    from deva.naja.register import SR
    return SR('strategy_manager')
