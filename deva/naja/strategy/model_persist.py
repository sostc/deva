"""策略模型持久化

提供策略模型的持久化机制:
- 模型状态保存和加载
- 模型版本管理
- 模型回滚
- 模型导出和导入
- River 在线学习模型序列化支持

使用方式:
    from deva.naja.strategy.model_persist import (
        StrategyModelManager,
        get_model_manager,
        save_model,
        load_model,
    )
    # River 模型持久化
    from deva.naja.strategy.model_persist import (
        serialize_river_model,
        deserialize_river_model,
        RiverStatePersistMixin,
    )
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from deva import NB

log = logging.getLogger(__name__)


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


# ============================================================================
# River 模型序列化工具
# ============================================================================

def serialize_river_model(model) -> str:
    """序列化 River 模型为 base64 字符串

    支持:
    - anomaly.HalfSpaceTrees
    - cluster.KMeans
    - drift.ADWIN
    - stats 系列
    - compose.Pipeline
    - linear_model 系列

    Args:
        model: River 模型实例

    Returns:
        str: base64 编码的序列化字符串，None 表示序列化失败
    """
    try:
        pickled = pickle.dumps(model)
        return base64.b64encode(pickled).decode('ascii')
    except Exception as e:
        log.error(f"[serialize_river_model] 序列化失败: {e}")
        return None


def deserialize_river_model(serialized: str):
    """反序列化 River 模型

    Args:
        serialized: base64 编码的序列化字符串

    Returns:
        River 模型实例，None 表示反序列化失败
    """
    try:
        pickled = base64.b64decode(serialized.encode('ascii'))
        return pickle.loads(pickled)
    except Exception as e:
        log.error(f"[deserialize_river_model] 反序列化失败: {e}")
        return None


# ============================================================================
# River 状态持久化 Mixin
# ============================================================================

class RiverStatePersistMixin:
    """River 状态持久化混入类

    为策略提供统一的 River 模型持久化能力。
    混入此类后，策略可以自动保存和恢复 River 模型状态。

    使用方式:
        class MyStrategy(RiverStatePersistMixin):
            MODEL_STATE_KEY = "my_strategy_model"  # 必须定义

            def __init__(self):
                self._model = anomaly.HalfSpaceTrees(...)
                self.try_load_state()  # 启动时恢复

            def on_data(self, data):
                self._model.learn_one(features)
                self.try_save_state()  # 处理后保存

    子类必须定义:
        MODEL_STATE_KEY: str  # 持久化存储的 key
    """

    MODEL_STATE_KEY: str = ""

    def _get_persist_db(self):
        """获取持久化存储（NB）"""
        if not hasattr(self, '_persist_db') or self._persist_db is None:
            self._persist_db = NB("naja_river_model_states")
        return self._persist_db

    def try_save_state(self) -> bool:
        """保存 River 模型状态

        Returns:
            bool: 是否保存成功
        """
        if not self.MODEL_STATE_KEY:
            log.warning(f"[RiverStatePersistMixin] {self.__class__.__name__} 未定义 MODEL_STATE_KEY")
            return False

        try:
            state = self._extract_model_state()
            if state is None:
                return False

            serialized = serialize_river_model(state)
            if serialized is None:
                return False

            db = self._get_persist_db()
            db[self.MODEL_STATE_KEY] = {
                "serialized": serialized,
                "timestamp": time.time(),
                "class": self.__class__.__name__,
            }
            return True

        except Exception as e:
            log.error(f"[RiverStatePersistMixin] 保存状态失败 {self.__class__.__name__}: {e}")
            return False

    def try_load_state(self) -> bool:
        """加载 River 模型状态

        Returns:
            bool: 是否加载成功
        """
        if not self.MODEL_STATE_KEY:
            return False

        try:
            db = self._get_persist_db()
            data = db.get(self.MODEL_STATE_KEY)
            if not data or "serialized" not in data:
                return False

            state = deserialize_river_model(data["serialized"])
            if state is None:
                return False

            self._restore_model_state(state)
            log.info(f"[RiverStatePersistMixin] {self.__class__.__name__} 已恢复状态 "
                     f"(保存时间: {time.strftime('%Y-%m-%d %H:%M', time.localtime(data.get('timestamp', 0)))})")
            return True

        except Exception as e:
            log.error(f"[RiverStatePersistMixin] 加载状态失败 {self.__class__.__name__}: {e}")
            return False

    def _extract_model_state(self) -> Any:
        """提取模型状态（子类必须实现）

        Returns:
            需要序列化的模型状态对象
        """
        raise NotImplementedError("子类必须实现 _extract_model_state()")

    def _restore_model_state(self, state: Any) -> None:
        """恢复模型状态（子类必须实现）

        Args:
            state: 从持久化存储中恢复的模型状态
        """
        raise NotImplementedError("子类必须实现 _restore_model_state()")
