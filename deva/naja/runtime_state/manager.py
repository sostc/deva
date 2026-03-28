"""运行时状态管理器 (RuntimeStateManager)

统一管理系统中所有需要持久化的运行时状态。

主要功能：
1. 注册所有有状态的组件
2. 按优先级顺序加载/保存状态
3. 追踪每个组件的持久化状态
4. 提供 UI 查看和手动控制

使用方式：
    from deva.naja.runtime_state import RuntimeStateManager, StatefulComponent

    # 组件实现 StatefulComponent 接口
    class MyComponent(StatefulComponent):
        @property
        def persistence_id(self) -> str:
            return "my_component"

        @property
        def persistence_table(self) -> str:
            return "naja_my_state"

        @property
        def persistence_priority(self) -> int:
            return 50

        def load_state(self) -> bool:
            ...

        def save_state(self) -> bool:
            ...

    # 注册到管理器
    manager = RuntimeStateManager()
    manager.register(my_component)

    # 启动时加载
    manager.load_all()

    # 关闭时保存
    manager.save_all()
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class StateStatus(Enum):
    """状态持久化状态"""
    UNKNOWN = "unknown"
    SAVED = "saved"
    LOADED = "loaded"
    MODIFIED = "modified"
    ERROR = "error"
    NOT_REGISTERED = "not_registered"


@dataclass
class ComponentStateInfo:
    """组件状态信息"""
    persistence_id: str
    component_type: str
    component_name: str
    table_name: str
    priority: int
    status: StateStatus = StateStatus.UNKNOWN
    last_save_ts: float = 0
    last_load_ts: float = 0
    last_error: str = ""
    record_count: int = 0
    data_size_kb: float = 0

    @property
    def last_save_time(self) -> str:
        if not self.last_save_ts:
            return "从未保存"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.last_save_ts))

    @property
    def last_load_time(self) -> str:
        if not self.last_load_ts:
            return "从未加载"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.last_load_ts))

    def to_dict(self) -> dict:
        return {
            "persistence_id": self.persistence_id,
            "component_type": self.component_type,
            "component_name": self.component_name,
            "table_name": self.table_name,
            "priority": self.priority,
            "status": self.status.value,
            "last_save_time": self.last_save_time,
            "last_load_time": self.last_load_time,
            "last_error": self.last_error,
            "record_count": self.record_count,
            "data_size_kb": self.data_size_kb,
        }


class StatefulComponent:
    """需要持久化的组件接口"""

    @property
    def persistence_id(self) -> str:
        """唯一标识符"""
        raise NotImplementedError

    @property
    def persistence_table(self) -> str:
        """数据存储的表名"""
        raise NotImplementedError

    @property
    def persistence_priority(self) -> int:
        """优先级，越小越先加载/保存"""
        return 50

    @property
    def persistence_type(self) -> str:
        """组件类型"""
        return self.__class__.__name__

    @property
    def persistence_name(self) -> str:
        """显示名称"""
        return getattr(self, 'name', self.persistence_id)

    def load_state(self) -> bool:
        """加载状态，返回是否成功"""
        raise NotImplementedError

    def save_state(self) -> bool:
        """保存状态，返回是否成功"""
        raise NotImplementedError

    def verify_state(self) -> bool:
        """验证状态完整性"""
        return True


class RuntimeStateManager:
    """运行时状态管理器 - 单例"""

    _instance: Optional['RuntimeStateManager'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._components: Dict[str, StatefulComponent] = {}
        self._state_info: Dict[str, ComponentStateInfo] = {}
        self._lock = threading.RLock()
        self._initialized = True

        logger.info("[RuntimeStateManager] 初始化完成")

    def register(self, component: StatefulComponent) -> bool:
        """注册一个需要持久化的组件

        Args:
            component: 实现 StatefulComponent 接口的组件

        Returns:
            是否注册成功
        """
        pid = component.persistence_id

        with self._lock:
            if pid in self._components:
                logger.warning(f"[RuntimeStateManager] 组件 {pid} 已存在，将被覆盖")

            self._components[pid] = component
            self._state_info[pid] = ComponentStateInfo(
                persistence_id=pid,
                component_type=component.persistence_type,
                component_name=component.persistence_name,
                table_name=component.persistence_table,
                priority=component.persistence_priority,
            )

            logger.info(f"[RuntimeStateManager] 注册: {pid} (priority={component.persistence_priority})")
            return True

    def unregister(self, persistence_id: str) -> bool:
        """取消注册"""
        with self._lock:
            if persistence_id in self._components:
                del self._components[persistence_id]
                del self._state_info[persistence_id]
                logger.info(f"[RuntimeStateManager] 取消注册: {persistence_id}")
                return True
            return False

    def get(self, persistence_id: str) -> Optional[StatefulComponent]:
        """获取已注册的组件"""
        with self._lock:
            return self._components.get(persistence_id)

    def list_all(self) -> List[ComponentStateInfo]:
        """列出所有已注册组件的状态信息"""
        with self._lock:
            return sorted(
                list(self._state_info.values()),
                key=lambda x: x.priority
            )

    def load_all(self, dry_run: bool = False) -> Dict[str, Any]:
        """加载所有组件状态

        Args:
            dry_run: 如果为 True，只返回会做什么但不实际执行

        Returns:
            加载结果汇总
        """
        results = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "details": []
        }

        with self._lock:
            components = sorted(
                self._components.values(),
                key=lambda x: x.persistence_priority
            )
            results["total"] = len(components)

        if dry_run:
            logger.info(f"[RuntimeStateManager] 预演模式：需要加载 {len(components)} 个组件")
            for comp in components:
                results["details"].append({
                    "id": comp.persistence_id,
                    "name": comp.persistence_name,
                    "priority": comp.persistence_priority,
                    "action": "load",
                    "dry_run": True
                })
            return results

        for comp in components:
            pid = comp.persistence_id
            info = self._state_info.get(pid)

            try:
                if comp.verify_state():
                    success = comp.load_state()
                    if success:
                        info.status = StateStatus.LOADED
                        info.last_load_ts = time.time()
                        info.last_error = ""
                        results["success"] += 1
                    else:
                        info.status = StateStatus.ERROR
                        info.last_error = "load_state() 返回 False"
                        results["failed"] += 1
                else:
                    info.status = StateStatus.ERROR
                    info.last_error = "状态验证失败"
                    results["skipped"] += 1

                results["details"].append({
                    "id": pid,
                    "name": comp.persistence_name,
                    "status": info.status.value,
                    "error": info.last_error
                })

            except Exception as e:
                info.status = StateStatus.ERROR
                info.last_error = str(e)
                results["failed"] += 1
                logger.error(f"[RuntimeStateManager] 加载失败: {pid} - {e}")

        logger.info(f"[RuntimeStateManager] 加载完成: {results['success']}/{results['total']} 成功, {results['failed']} 失败")
        return results

    def save_all(self, dry_run: bool = False) -> Dict[str, Any]:
        """保存所有组件状态

        Args:
            dry_run: 如果为 True，只返回会做什么但不实际执行

        Returns:
            保存结果汇总
        """
        results = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "details": []
        }

        with self._lock:
            components = sorted(
                self._components.values(),
                key=lambda x: x.persistence_priority,
                reverse=True
            )
            results["total"] = len(components)

        if dry_run:
            logger.info(f"[RuntimeStateManager] 预演模式：需要保存 {len(components)} 个组件")
            for comp in components:
                results["details"].append({
                    "id": comp.persistence_id,
                    "name": comp.persistence_name,
                    "priority": comp.persistence_priority,
                    "action": "save",
                    "dry_run": True
                })
            return results

        for comp in components:
            pid = comp.persistence_id
            info = self._state_info.get(pid)

            try:
                success = comp.save_state()
                if success:
                    info.status = StateStatus.SAVED
                    info.last_save_ts = time.time()
                    info.last_error = ""
                    results["success"] += 1
                else:
                    info.status = StateStatus.ERROR
                    info.last_error = "save_state() 返回 False"
                    results["failed"] += 1

                results["details"].append({
                    "id": pid,
                    "name": comp.persistence_name,
                    "status": info.status.value,
                    "error": info.last_error
                })

            except Exception as e:
                info.status = StateStatus.ERROR
                info.last_error = str(e)
                results["failed"] += 1
                logger.error(f"[RuntimeStateManager] 保存失败: {pid} - {e}")

        logger.info(f"[RuntimeStateManager] 保存完成: {results['success']}/{results['total']} 成功, {results['failed']} 失败")
        return results

    def load_one(self, persistence_id: str) -> bool:
        """加载单个组件状态"""
        comp = self.get(persistence_id)
        if not comp:
            logger.warning(f"[RuntimeStateManager] 组件不存在: {persistence_id}")
            return False

        info = self._state_info.get(persistence_id)
        try:
            success = comp.load_state()
            if success:
                info.status = StateStatus.LOADED
                info.last_load_ts = time.time()
                info.last_error = ""
            return success
        except Exception as e:
            info.status = StateStatus.ERROR
            info.last_error = str(e)
            logger.error(f"[RuntimeStateManager] 加载失败: {persistence_id} - {e}")
            return False

    def save_one(self, persistence_id: str) -> bool:
        """保存单个组件状态"""
        comp = self.get(persistence_id)
        if not comp:
            logger.warning(f"[RuntimeStateManager] 组件不存在: {persistence_id}")
            return False

        info = self._state_info.get(persistence_id)
        try:
            success = comp.save_state()
            if success:
                info.status = StateStatus.SAVED
                info.last_save_ts = time.time()
                info.last_error = ""
            return success
        except Exception as e:
            info.status = StateStatus.ERROR
            info.last_error = str(e)
            logger.error(f"[RuntimeStateManager] 保存失败: {persistence_id} - {e}")
            return False

    def get_status(self, persistence_id: str) -> Optional[ComponentStateInfo]:
        """获取组件状态信息"""
        with self._lock:
            return self._state_info.get(persistence_id)

    def reset(self):
        """重置管理器（清空所有注册）"""
        with self._lock:
            self._components.clear()
            self._state_info.clear()
        logger.info("[RuntimeStateManager] 已重置")


def get_runtime_state_manager() -> RuntimeStateManager:
    """获取运行时状态管理器单例"""
    return RuntimeStateManager()


def register_stateful_component(component: StatefulComponent) -> bool:
    """快捷函数：注册有状态的组件"""
    return get_runtime_state_manager().register(component)


def load_all_state() -> Dict[str, Any]:
    """快捷函数：加载所有状态"""
    return get_runtime_state_manager().load_all()


def save_all_state() -> Dict[str, Any]:
    """快捷函数：保存所有状态"""
    return get_runtime_state_manager().save_all()