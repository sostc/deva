"""临时的持久化模块，替代已删除的 strategy.persistence"""

from typing import Dict, Any, Optional


class PersistenceManager:
    """临时的持久化管理器"""
    
    def __init__(self):
        self._storage: Dict[str, Dict[str, Any]] = {}
    
    def save_unit(self, unit_type: str, unit_id: str, data: dict) -> bool:
        """保存单元数据"""
        if unit_type not in self._storage:
            self._storage[unit_type] = {}
        self._storage[unit_type][unit_id] = data
        return True
    
    def load_unit(self, unit_type: str, unit_id: str) -> Optional[dict]:
        """加载单元数据"""
        if unit_type in self._storage:
            return self._storage[unit_type].get(unit_id)
        return None
    
    def delete_unit(self, unit_type: str, unit_id: str) -> bool:
        """删除单元数据"""
        if unit_type in self._storage:
            if unit_id in self._storage[unit_type]:
                del self._storage[unit_type][unit_id]
                return True
        return False
    
    def list_units(self, unit_type: str) -> list:
        """列出所有单元ID"""
        if unit_type in self._storage:
            return list(self._storage[unit_type].keys())
        return []


_global_persistence_manager: Optional[PersistenceManager] = None


def get_global_persistence_manager() -> PersistenceManager:
    """获取全局持久化管理器"""
    global _global_persistence_manager
    if _global_persistence_manager is None:
        _global_persistence_manager = PersistenceManager()
    return _global_persistence_manager


def set_global_persistence_manager(manager: PersistenceManager):
    """设置全局持久化管理器"""
    global _global_persistence_manager
    _global_persistence_manager = manager
