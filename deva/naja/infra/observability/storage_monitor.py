"""存储性能监控模块

监控底层存储(DBStream/NB)的读写性能
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable

from .performance_monitor import record_component_execution, ComponentType


class StorageMonitor:
    """存储性能监控器
    
    包装 DBStream 的读写操作，记录性能指标
    """
    
    @staticmethod
    def monitor_operation(db_name: str, operation: str):
        """装饰器：监控存储操作性能
        
        Args:
            db_name: 数据库/表名称
            operation: 操作类型 (read/write/delete/query)
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                success = False
                error_msg = ""
                
                try:
                    result = func(*args, **kwargs)
                    success = True
                    return result
                except Exception as e:
                    error_msg = str(e)
                    raise
                finally:
                    execution_time_ms = (time.time() - start_time) * 1000
                    
                    # 记录性能指标
                    try:
                        record_component_execution(
                            component_id=f"{db_name}:{operation}",
                            component_name=f"{db_name}.{operation}",
                            component_type=ComponentType.STORAGE,
                            execution_time_ms=execution_time_ms,
                            success=success,
                            error=error_msg,
                        )
                    except Exception:
                        pass  # 性能监控不应影响主流程
            
            return wrapper
        return decorator


def patch_dbstream_for_monitoring():
    """为 DBStream 打补丁，添加性能监控
    
    在 DBStream 的关键方法上添加性能监控
    """
    try:
        from deva.core.store import DBStream
        
        original_getitem = DBStream.__getitem__
        original_setitem = DBStream.__setitem__
        original_delitem = DBStream.__delitem__
        
        def monitored_getitem(self, key):
            """监控读取操作"""
            start_time = time.time()
            success = False
            error_msg = ""
            
            try:
                result = original_getitem(self, key)
                success = True
                return result
            except KeyError:
                success = True  # KeyError 是正常的
                raise
            except Exception as e:
                error_msg = str(e)
                raise
            finally:
                execution_time_ms = (time.time() - start_time) * 1000
                try:
                    record_component_execution(
                        component_id=f"{self.name}:read",
                        component_name=f"{self.name}.read",
                        component_type=ComponentType.STORAGE,
                        execution_time_ms=execution_time_ms,
                        success=success,
                        error=error_msg,
                    )
                except Exception:
                    pass
        
        def monitored_setitem(self, key, value):
            """监控写入操作"""
            start_time = time.time()
            success = False
            error_msg = ""
            
            try:
                result = original_setitem(self, key, value)
                success = True
                return result
            except Exception as e:
                error_msg = str(e)
                raise
            finally:
                execution_time_ms = (time.time() - start_time) * 1000
                try:
                    record_component_execution(
                        component_id=f"{self.name}:write",
                        component_name=f"{self.name}.write",
                        component_type=ComponentType.STORAGE,
                        execution_time_ms=execution_time_ms,
                        success=success,
                        error=error_msg,
                    )
                except Exception:
                    pass
        
        def monitored_delitem(self, key):
            """监控删除操作"""
            start_time = time.time()
            success = False
            error_msg = ""
            
            try:
                result = original_delitem(self, key)
                success = True
                return result
            except Exception as e:
                error_msg = str(e)
                raise
            finally:
                execution_time_ms = (time.time() - start_time) * 1000
                try:
                    record_component_execution(
                        component_id=f"{self.name}:delete",
                        component_name=f"{self.name}.delete",
                        component_type=ComponentType.STORAGE,
                        execution_time_ms=execution_time_ms,
                        success=success,
                        error=error_msg,
                    )
                except Exception:
                    pass
        
        def monitored_get(self, key, default=None):
            """监控 get 操作"""
            start_time = time.time()
            success = False
            error_msg = ""
            
            try:
                result = self.db.get(key, default)
                success = True
                return result
            except Exception as e:
                error_msg = str(e)
                raise
            finally:
                execution_time_ms = (time.time() - start_time) * 1000
                try:
                    record_component_execution(
                        component_id=f"{self.name}:read",
                        component_name=f"{self.name}.read",
                        component_type=ComponentType.STORAGE,
                        execution_time_ms=execution_time_ms,
                        success=success,
                        error=error_msg,
                    )
                except Exception:
                    pass
        
        def monitored_keys(self):
            """监控 keys 操作"""
            start_time = time.time()
            success = False
            error_msg = ""
            
            try:
                result = self.db.keys()
                success = True
                return result
            except Exception as e:
                error_msg = str(e)
                raise
            finally:
                execution_time_ms = (time.time() - start_time) * 1000
                try:
                    record_component_execution(
                        component_id=f"{self.name}:query",
                        component_name=f"{self.name}.query",
                        component_type=ComponentType.STORAGE,
                        execution_time_ms=execution_time_ms,
                        success=success,
                        error=error_msg,
                    )
                except Exception:
                    pass
        
        def monitored_values(self):
            """监控 values 操作"""
            start_time = time.time()
            success = False
            error_msg = ""
            
            try:
                result = self.db.values()
                success = True
                return result
            except Exception as e:
                error_msg = str(e)
                raise
            finally:
                execution_time_ms = (time.time() - start_time) * 1000
                try:
                    record_component_execution(
                        component_id=f"{self.name}:query",
                        component_name=f"{self.name}.query",
                        component_type=ComponentType.STORAGE,
                        execution_time_ms=execution_time_ms,
                        success=success,
                        error=error_msg,
                    )
                except Exception:
                    pass
        
        DBStream.__getitem__ = monitored_getitem
        DBStream.__setitem__ = monitored_setitem
        DBStream.__delitem__ = monitored_delitem
        DBStream.get = monitored_get
        DBStream.keys = monitored_keys
        DBStream.values = monitored_values
        
        print("[StorageMonitor] DBStream 性能监控已启用")
        
    except Exception as e:
        print(f"[StorageMonitor] 启用存储性能监控失败: {e}")


def enable_storage_monitoring():
    """启用存储性能监控"""
    patch_dbstream_for_monitoring()
