"""策略模型持久化

提供策略模型的持久化机制:
- 模型状态保存和加载
- 模型版本管理
- 模型回滚
- 模型导出和导入

使用方式:
    from deva.naja.strategy.model_persist import (
        StrategyModelManager,
        get_model_manager,
        save_model,
        load_model,
    )
"""

from __future__ import annotations

import hashlib
import json
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from deva import NB


@dataclass
class ModelVersion:
    """模型版本"""

    version_id: str
    timestamp: float
    model_state: Any
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelInfo:
    """模型信息"""

    strategy_id: str
    strategy_type: str
    current_version: str
    created_at: float
    updated_at: float
    version_count: int = 0


class StrategyModelManager:
    """策略模型管理器

    负责:
    1. 模型状态的保存和加载
    2. 模型版本管理
    3. 模型状态持久化到数据库
    """

    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id
        self._db = NB("naja_strategy_models")
        self._current_version: Optional[ModelVersion] = None
        self._load_latest()

    def _load_latest(self) -> None:
        """加载最新版本"""
        key = f"latest_{self.strategy_id}"
        data = self._db.get(key)
        if data:
            self._current_version = ModelVersion(
                version_id=data.get("version_id", ""),
                timestamp=data.get("timestamp", 0),
                model_state=data.get("model_state"),
                metadata=data.get("metadata", {}),
            )

    def _generate_version_id(self, model_state: Any) -> str:
        """生成版本ID"""
        state_str = str(model_state)
        hash_obj = hashlib.md5(state_str.encode())
        timestamp = int(time.time())
        return f"v{timestamp}_{hash_obj.hexdigest()[:8]}"

    def save(
        self,
        model_state: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """保存模型状态

        Args:
            model_state: 模型状态 (可以是任意可序列化对象)
            metadata: 元数据

        Returns:
            str: 版本ID
        """
        version_id = self._generate_version_id(model_state)

        version = ModelVersion(
            version_id=version_id,
            timestamp=time.time(),
            model_state=model_state,
            metadata=metadata or {},
        )

        version_key = f"version_{self.strategy_id}_{version_id}"
        self._db[version_key] = {
            "version_id": version_id,
            "timestamp": version.timestamp,
            "model_state": model_state,
            "metadata": version.metadata,
        }

        versions_list_key = f"versions_{self.strategy_id}"
        versions = self._db.get(versions_list_key) or []
        versions.append(version_id)
        self._db[versions_list_key] = versions

        latest_key = f"latest_{self.strategy_id}"
        self._db[latest_key] = {
            "version_id": version_id,
            "timestamp": version.timestamp,
            "model_state": model_state,
            "metadata": version.metadata,
        }

        self._current_version = version

        return version_id

    def load(self, version_id: Optional[str] = None) -> Optional[Any]:
        """加载模型状态

        Args:
            version_id: 版本ID，None 表示加载最新版本

        Returns:
            Any: 模型状态，None 表示未找到
        """
        if version_id is None:
            if self._current_version:
                return self._current_version.model_state
            self._load_latest()
            if self._current_version:
                return self._current_version.model_state
            return None

        version_key = f"version_{self.strategy_id}_{version_id}"
        data = self._db.get(version_key)
        if data:
            return data.get("model_state")
        return None

    def get_versions(self) -> List[str]:
        """获取所有版本ID"""
        versions_list_key = f"versions_{self.strategy_id}"
        versions = self._db.get(versions_list_key) or []
        return versions

    def get_version_info(self, version_id: str) -> Optional[Dict]:
        """获取版本信息"""
        version_key = f"version_{self.strategy_id}_{version_id}"
        data = self._db.get(version_key)
        if data:
            return {
                "version_id": data.get("version_id"),
                "timestamp": data.get("timestamp"),
                "metadata": data.get("metadata", {}),
            }
        return None

    def delete_version(self, version_id: str) -> bool:
        """删除指定版本"""
        version_key = f"version_{self.strategy_id}_{version_id}"
        if self._db.get(version_key):
            del self._db[version_key]

            versions_list_key = f"versions_{self.strategy_id}"
            versions = self._db.get(versions_list_key) or []
            if version_id in versions:
                versions.remove(version_id)
                self._db[versions_list_key] = versions
            return True
        return False

    def rollback(self, version_id: str) -> bool:
        """回滚到指定版本

        Args:
            version_id: 目标版本ID

        Returns:
            bool: 是否成功
        """
        model_state = self.load(version_id)
        if model_state is None:
            return False

        self.save(model_state, metadata={"rollback_from": version_id})
        return True

    def export_model(self, version_id: Optional[str] = None) -> Optional[Dict]:
        """导出模型

        Args:
            version_id: 版本ID

        Returns:
            Dict: 导出的模型数据
        """
        model_state = self.load(version_id)
        if model_state is None:
            return None

        return {
            "strategy_id": self.strategy_id,
            "version_id": version_id or self._current_version.version_id,
            "timestamp": time.time(),
            "model_state": model_state,
        }

    def import_model(self, model_data: Dict) -> bool:
        """导入模型

        Args:
            model_data: 导出的模型数据

        Returns:
            bool: 是否成功
        """
        try:
            strategy_id = model_data.get("strategy_id")
            if strategy_id != self.strategy_id:
                return False

            model_state = model_data.get("model_state")
            metadata = model_data.get("metadata", {})

            self.save(model_state, metadata)
            return True

        except Exception:
            return False


_MODEL_MANAGERS: Dict[str, StrategyModelManager] = {}


def get_model_manager(strategy_id: str) -> StrategyModelManager:
    """获取策略模型管理器"""
    if strategy_id not in _MODEL_MANAGERS:
        _MODEL_MANAGERS[strategy_id] = StrategyModelManager(strategy_id)
    return _MODEL_MANAGERS[strategy_id]


def save_model(strategy_id: str, model_state: Any, metadata: Optional[Dict] = None) -> str:
    """保存模型状态的便捷函数"""
    manager = get_model_manager(strategy_id)
    return manager.save(model_state, metadata)


def load_model(strategy_id: str, version_id: Optional[str] = None) -> Optional[Any]:
    """加载模型状态的便捷函数"""
    manager = get_model_manager(strategy_id)
    return manager.load(version_id)


def export_model(strategy_id: str, version_id: Optional[str] = None) -> Optional[Dict]:
    """导出模型的便捷函数"""
    manager = get_model_manager(strategy_id)
    return manager.export_model(version_id)


def import_model(strategy_id: str, model_data: Dict) -> bool:
    """导入模型的便捷函数"""
    manager = get_model_manager(strategy_id)
    return manager.import_model(model_data)
