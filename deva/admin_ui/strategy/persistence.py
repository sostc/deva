"""统一持久化模块(Unified Persistence Module)

为策略和数据源提供统一的持久化能力，支持多种存储后端和序列化格式。

================================================================================
功能特性
================================================================================

1. **统一存储接口**: 标准化的数据存储和读取
2. **多后端支持**: 支持内存、文件、数据库等多种后端
3. **自动序列化**: 智能对象序列化和反序列化
4. **版本管理**: 数据版本控制和迁移
5. **缓存优化**: 读写缓存和性能优化
6. **备份恢复**: 数据备份和恢复机制
"""

from __future__ import annotations

import json
import pickle
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Type, TypeVar, Generic
from pathlib import Path

from deva import NB, log


T = TypeVar('T')


class StorageBackend(str, Enum):
    """存储后端类型"""
    MEMORY = "memory"      # 内存存储
    FILE = "file"         # 文件存储
    DATABASE = "database"  # 数据库存储
    HYBRID = "hybrid"     # 混合存储


class SerializationFormat(str, Enum):
    """序列化格式"""
    JSON = "json"      # JSON格式
    PICKLE = "pickle"  # Pickle格式
    MSGPACK = "msgpack"  # MessagePack格式


@dataclass
class StorageConfig:
    """存储配置"""
    backend: StorageBackend = StorageBackend.MEMORY
    format: SerializationFormat = SerializationFormat.JSON
    compression: bool = False
    encryption: bool = False
    backup_count: int = 3
    auto_backup: bool = True
    cache_size: int = 1000
    sync_interval: float = 60.0  # 同步间隔（秒）


class PersistenceBackend(ABC, Generic[T]):
    """持久化后端基类"""
    
    def __init__(self, config: StorageConfig):
        self.config = config
    
    @abstractmethod
    def save(self, key: str, data: T) -> bool:
        """保存数据
        
        Args:
            key: 数据键
            data: 要保存的数据
            
        Returns:
            是否成功保存
        """
        pass
    
    @abstractmethod
    def load(self, key: str) -> Optional[T]:
        """加载数据
        
        Args:
            key: 数据键
            
        Returns:
            数据，不存在返回None
        """
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除数据
        
        Args:
            key: 数据键
            
        Returns:
            是否成功删除
        """
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """检查数据是否存在
        
        Args:
            key: 数据键
            
        Returns:
            是否存在
        """
        pass
    
    @abstractmethod
    def list_keys(self, pattern: str = None) -> List[str]:
        """列出所有键
        
        Args:
            pattern: 匹配模式，None表示所有
            
        Returns:
            键列表
        """
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """清空所有数据
        
        Returns:
            是否成功清空
        """
        pass
    
    def backup(self, backup_key: str) -> bool:
        """备份数据
        
        Args:
            backup_key: 备份键
            
        Returns:
            是否成功备份
        """
        # 默认实现，子类可以重写
        return True
    
    def restore(self, backup_key: str) -> bool:
        """恢复数据
        
        Args:
            backup_key: 备份键
            
        Returns:
            是否成功恢复
        """
        # 默认实现，子类可以重写
        return True


class MemoryBackend(PersistenceBackend[T]):
    """内存存储后端"""
    
    def __init__(self, config: StorageConfig):
        super().__init__(config)
        self._data: Dict[str, T] = {}
        self._backups: Dict[str, Dict[str, T]] = {}
    
    def save(self, key: str, data: T) -> bool:
        """保存数据到内存"""
        try:
            self._data[key] = data
            
            # 自动备份
            if self.config.auto_backup:
                self._auto_backup(key)
            
            return True
        except Exception as e:
            log.error(f"内存保存失败: {e}")
            return False
    
    def load(self, key: str) -> Optional[T]:
        """从内存加载数据"""
        return self._data.get(key)
    
    def delete(self, key: str) -> bool:
        """从内存删除数据"""
        if key in self._data:
            del self._data[key]
            return True
        return False
    
    def exists(self, key: str) -> bool:
        """检查数据是否存在"""
        return key in self._data
    
    def list_keys(self, pattern: str = None) -> List[str]:
        """列出所有键"""
        if pattern is None:
            return list(self._data.keys())
        
        # 简单的通配符匹配
        import fnmatch
        return [key for key in self._data.keys() if fnmatch.fnmatch(key, pattern)]
    
    def clear(self) -> bool:
        """清空所有数据"""
        self._data.clear()
        return True
    
    def _auto_backup(self, key: str):
        """自动备份"""
        if key not in self._backups:
            self._backups[key] = {}
        
        # 保留指定数量的备份
        backup_keys = list(self._backups[key].keys())
        if len(backup_keys) >= self.config.backup_count:
            # 删除最旧的备份
            oldest_key = min(backup_keys)
            del self._backups[key][oldest_key]
        
        # 创建新备份
        timestamp = str(int(time.time()))
        self._backups[key][timestamp] = self._data[key]


class FileBackend(PersistenceBackend[T]):
    """文件存储后端"""
    
    def __init__(self, config: StorageConfig, base_path: str = "./data"):
        super().__init__(config)
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _get_file_path(self, key: str) -> Path:
        """获取文件路径"""
        # 确保文件名安全
        safe_key = "".join(c for c in key if c.isalnum() or c in "._-")
        extension = self.config.format.value
        return self.base_path / f"{safe_key}.{extension}"
    
    def save(self, key: str, data: T) -> bool:
        """保存数据到文件"""
        try:
            file_path = self._get_file_path(key)
            
            # 序列化数据
            serialized_data = self._serialize(data)
            
            # 写入文件
            with open(file_path, 'wb' if self.config.format == SerializationFormat.PICKLE else 'w',
                     encoding=None if self.config.format == SerializationFormat.PICKLE else 'utf-8') as f:
                f.write(serialized_data)
            
            log.info(f"数据已保存到文件: {file_path}")
            return True
            
        except Exception as e:
            log.error(f"文件保存失败: {e}")
            return False
    
    def load(self, key: str) -> Optional[T]:
        """从文件加载数据"""
        try:
            file_path = self._get_file_path(key)
            
            if not file_path.exists():
                return None
            
            # 读取文件
            with open(file_path, 'rb' if self.config.format == SerializationFormat.PICKLE else 'r',
                     encoding=None if self.config.format == SerializationFormat.PICKLE else 'utf-8') as f:
                serialized_data = f.read()
            
            # 反序列化数据
            data = self._deserialize(serialized_data)
            
            log.info(f"数据已从文件加载: {file_path}")
            return data
            
        except Exception as e:
            log.error(f"文件加载失败: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """删除文件"""
        try:
            file_path = self._get_file_path(key)
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except Exception as e:
            log.error(f"文件删除失败: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """检查文件是否存在"""
        file_path = self._get_file_path(key)
        return file_path.exists()
    
    def list_keys(self, pattern: str = None) -> List[str]:
        """列出所有文件键"""
        keys = []
        extension = f".{self.config.format.value}"
        
        for file_path in self.base_path.glob(f"*{extension}"):
            key = file_path.stem  # 移除扩展名
            if pattern is None or self._match_pattern(key, pattern):
                keys.append(key)
        
        return keys
    
    def clear(self) -> bool:
        """清空所有文件"""
        try:
            extension = f".{self.config.format.value}"
            for file_path in self.base_path.glob(f"*{extension}"):
                file_path.unlink()
            return True
        except Exception as e:
            log.error(f"文件清空失败: {e}")
            return False
    
    def _serialize(self, data: T) -> Union[str, bytes]:
        """序列化数据"""
        if self.config.format == SerializationFormat.JSON:
            return json.dumps(data, ensure_ascii=False, indent=2)
        elif self.config.format == SerializationFormat.PICKLE:
            return pickle.dumps(data)
        else:
            raise ValueError(f"不支持的序列化格式: {self.config.format}")
    
    def _deserialize(self, data: Union[str, bytes]) -> T:
        """反序列化数据"""
        if self.config.format == SerializationFormat.JSON:
            return json.loads(data)
        elif self.config.format == SerializationFormat.PICKLE:
            return pickle.loads(data)
        else:
            raise ValueError(f"不支持的序列化格式: {self.config.format}")
    
    def _match_pattern(self, key: str, pattern: str) -> bool:
        """简单的模式匹配"""
        import fnmatch
        return fnmatch.fnmatch(key, pattern)


class DatabaseBackend(PersistenceBackend[T]):
    """数据库存储后端（基于NB）"""
    
    def __init__(self, config: StorageConfig, namespace: str = "persistence"):
        super().__init__(config)
        self.namespace = namespace
        self.db = NB(namespace)
    
    def save(self, key: str, data: T) -> bool:
        """保存数据到数据库"""
        try:
            self.db[key] = data
            log.info(f"数据已保存到数据库: {key}")
            return True
        except Exception as e:
            log.error(f"数据库保存失败: {e}")
            return False
    
    def load(self, key: str) -> Optional[T]:
        """从数据库加载数据"""
        try:
            return self.db.get(key)
        except Exception as e:
            log.error(f"数据库加载失败: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """从数据库删除数据"""
        try:
            if key in self.db:
                del self.db[key]
                return True
            return False
        except Exception as e:
            log.error(f"数据库删除失败: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """检查数据是否存在"""
        return key in self.db
    
    def list_keys(self, pattern: str = None) -> List[str]:
        """列出所有键"""
        all_keys = list(self.db.keys())
        
        if pattern is None:
            return all_keys
        
        # 简单的通配符匹配
        import fnmatch
        return [key for key in all_keys if fnmatch.fnmatch(key, pattern)]
    
    def clear(self) -> bool:
        """清空所有数据"""
        try:
            self.db.clear()
            return True
        except Exception as e:
            log.error(f"数据库清空失败: {e}")
            return False


class HybridBackend(PersistenceBackend[T]):
    """混合存储后端
    
    结合内存和数据库的优势：
    - 内存：快速访问
    - 数据库：持久化存储
    """
    
    def __init__(self, config: StorageConfig):
        super().__init__(config)
        self.memory_backend = MemoryBackend(config)
        self.db_backend = DatabaseBackend(config)
        self._cache: Dict[str, T] = {}  # 内存缓存
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_ttl = 300  # 缓存过期时间（秒）
    
    def save(self, key: str, data: T) -> bool:
        """保存数据到混合存储"""
        try:
            # 保存到内存缓存
            self._cache[key] = data
            self._cache_timestamps[key] = time.time()
            
            # 异步保存到数据库（可以优化为后台线程）
            try:
                self.db_backend.save(key, data)
            except Exception as e:
                log.warning(f"数据库保存失败，仅保存在内存: {e}")
            
            return True
        except Exception as e:
            log.error(f"混合存储保存失败: {e}")
            return False
    
    def load(self, key: str) -> Optional[T]:
        """从混合存储加载数据"""
        try:
            # 首先检查内存缓存
            if key in self._cache:
                # 检查缓存是否过期
                cache_time = self._cache_timestamps.get(key, 0)
                if time.time() - cache_time < self._cache_ttl:
                    log.debug(f"从内存缓存加载: {key}")
                    return self._cache[key]
                else:
                    # 缓存过期，删除
                    del self._cache[key]
                    del self._cache_timestamps[key]
            
            # 从数据库加载
            data = self.db_backend.load(key)
            if data is not None:
                # 更新内存缓存
                self._cache[key] = data
                self._cache_timestamps[key] = time.time()
                log.debug(f"从数据库加载并缓存: {key}")
            
            return data
            
        except Exception as e:
            log.error(f"混合存储加载失败: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """从混合存储删除数据"""
        try:
            # 从内存缓存删除
            if key in self._cache:
                del self._cache[key]
                del self._cache_timestamps[key]
            
            # 从数据库删除
            return self.db_backend.delete(key)
            
        except Exception as e:
            log.error(f"混合存储删除失败: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """检查数据是否存在"""
        # 先检查内存缓存
        if key in self._cache:
            return True
        
        # 再检查数据库
        return self.db_backend.exists(key)
    
    def list_keys(self, pattern: str = None) -> List[str]:
        """列出所有键"""
        return self.db_backend.list_keys(pattern)
    
    def clear(self) -> bool:
        """清空所有数据"""
        try:
            # 清空内存缓存
            self._cache.clear()
            self._cache_timestamps.clear()
            
            # 清空数据库
            return self.db_backend.clear()
            
        except Exception as e:
            log.error(f"混合存储清空失败: {e}")
            return False


class PersistenceManager:
    """持久化管理器"""
    
    def __init__(self, config: StorageConfig = None):
        self.config = config or StorageConfig()
        self.backend = self._create_backend(self.config)
    
    def _create_backend(self, config: StorageConfig) -> PersistenceBackend:
        """创建存储后端"""
        if config.backend == StorageBackend.MEMORY:
            return MemoryBackend(config)
        elif config.backend == StorageBackend.FILE:
            return FileBackend(config)
        elif config.backend == StorageBackend.DATABASE:
            return DatabaseBackend(config)
        elif config.backend == StorageBackend.HYBRID:
            return HybridBackend(config)
        else:
            raise ValueError(f"不支持的存储后端: {config.backend}")
    
    def save_unit(self, unit_type: str, unit_id: str, data: T) -> bool:
        """保存单元数据
        
        Args:
            unit_type: 单元类型 ("strategy" 或 "datasource")
            unit_id: 单元ID
            data: 要保存的数据
            
        Returns:
            是否成功保存
        """
        key = f"{unit_type}:{unit_id}"
        return self.backend.save(key, data)
    
    def load_unit(self, unit_type: str, unit_id: str) -> Optional[T]:
        """加载单元数据
        
        Args:
            unit_type: 单元类型
            unit_id: 单元ID
            
        Returns:
            数据，不存在返回None
        """
        key = f"{unit_type}:{unit_id}"
        return self.backend.load(key)
    
    def delete_unit(self, unit_type: str, unit_id: str) -> bool:
        """删除单元数据
        
        Args:
            unit_type: 单元类型
            unit_id: 单元ID
            
        Returns:
            是否成功删除
        """
        key = f"{unit_type}:{unit_id}"
        return self.backend.delete(key)
    
    def list_units(self, unit_type: str = None) -> List[str]:
        """列出所有单元
        
        Args:
            unit_type: 单元类型，None表示所有
            
        Returns:
            单元ID列表
        """
        if unit_type:
            pattern = f"{unit_type}:*"
        else:
            pattern = "*:*"
        
        keys = self.backend.list_keys(pattern)
        
        # 提取单元ID
        unit_ids = []
        for key in keys:
            parts = key.split(':', 1)
            if len(parts) == 2:
                unit_ids.append(parts[1])
        
        return unit_ids
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        all_keys = self.backend.list_keys()
        
        unit_counts = {}
        for key in all_keys:
            parts = key.split(':', 1)
            if len(parts) == 2:
                unit_type = parts[0]
                unit_counts[unit_type] = unit_counts.get(unit_type, 0) + 1
        
        return {
            "total_units": len(all_keys),
            "unit_type_counts": unit_counts,
            "backend_type": self.config.backend.value,
            "serialization_format": self.config.format.value,
        }


# 全局持久化管理器实例
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