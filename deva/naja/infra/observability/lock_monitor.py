"""锁性能监控模块

提供通用的锁监控功能，可以：
1. 开启/关闭监控，不影响系统性能
2. 自动记录锁等待时间
3. 只在超过阈值时才记录，避免干扰系统执行
4. 支持从配置文件读取设置
"""

import threading
import time
from typing import Optional, Callable

from .performance_monitor import (
    record_lock_wait,
    get_performance_monitor,
    ComponentType,
)


class LockMonitor:
    """锁监控器
    
    使用方式:
        # 1. 从配置加载设置
        LockMonitor.load_from_config()
        
        # 2. 开启监控（默认关闭）
        LockMonitor.enable()
        
        # 3. 设置阈值（默认 100ms）
        LockMonitor.set_threshold(100)
        
        # 4. 使用监控包装锁
        lock = LockMonitor.wrap_lock(original_lock, "MyLock")
    """
    
    _enabled = False
    _threshold_ms = 100
    _callbacks: list = []
    _initialized = False
    
    @classmethod
    def load_from_config(cls):
        """从配置加载锁监控设置"""
        try:
            from ..config import get_config
            perf_config = get_config("performance") or {}
            cls._enabled = perf_config.get("lock_monitoring_enabled", False)
            cls._threshold_ms = perf_config.get("lock_monitoring_threshold_ms", 100)
            print(f"[LockMonitor] 从配置加载: enabled={cls._enabled}, threshold={cls._threshold_ms}ms")
        except Exception as e:
            print(f"[LockMonitor] 加载配置失败: {e}")
    
    @classmethod
    def save_to_config(cls):
        """保存锁监控设置到配置"""
        try:
            from ..config import get_config, set_config
            set_config("performance.lock_monitoring_enabled", cls._enabled)
            set_config("performance.lock_monitoring_threshold_ms", cls._threshold_ms)
            print(f"[LockMonitor] 已保存配置: enabled={cls._enabled}, threshold={cls._threshold_ms}ms")
        except Exception as e:
            print(f"[LockMonitor] 保存配置失败: {e}")
    
    @classmethod
    def enable(cls):
        """开启锁监控"""
        cls._enabled = True
        cls.save_to_config()
        print(f"[LockMonitor] 锁监控已开启，阈值: {cls._threshold_ms}ms")
    
    @classmethod
    def disable(cls):
        """关闭锁监控"""
        cls._enabled = False
        cls.save_to_config()
        print("[LockMonitor] 锁监控已关闭")
    
    @classmethod
    def is_enabled(cls) -> bool:
        """检查锁监控是否开启"""
        return cls._enabled
    
    @classmethod
    def set_threshold(cls, threshold_ms: int):
        """设置监控阈值（毫秒）
        
        只有等待时间超过这个阈值才会记录
        """
        cls._threshold_ms = threshold_ms
        cls.save_to_config()
        print(f"[LockMonitor] 阈值已设置为: {threshold_ms}ms")
    
    @classmethod
    def get_threshold(cls) -> int:
        """获取当前阈值"""
        return cls._threshold_ms
    
    @classmethod
    def wrap_lock(cls, lock: threading.Lock, lock_name: str):
        """包装锁，添加监控功能
        
        Args:
            lock: 原始锁对象
            lock_name: 锁名称（用于标识）
            
        Returns:
            包装后的锁对象
        """
        class MonitoredLock:
            """监控锁包装器"""
            
            def __init__(self, original_lock, name):
                self._original = original_lock
                self._name = name
            
            def acquire(self, blocking: bool = True, timeout: float = -1):
                """获取锁"""
                if not cls._enabled:
                    return self._original.acquire(blocking, timeout)
                
                wait_start = time.time()
                if timeout > 0:
                    result = self._original.acquire(blocking, timeout)
                else:
                    result = self._original.acquire(blocking)
                wait_time_ms = (time.time() - wait_start) * 1000
                
                if wait_time_ms > cls._threshold_ms:
                    record_lock_wait(
                        lock_name=self._name,
                        wait_time_ms=wait_time_ms,
                        operation="acquire",
                    )
                
                return result
            
            def release(self):
                """释放锁"""
                return self._original.release()
            
            @property
            def locked(self):
                """检查锁状态"""
                return self._original.locked()
            
            def __enter__(self):
                """上下文管理器入口"""
                self.acquire()
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                """上下文管理器退出"""
                self.release()
                return False
            
            def __repr__(self):
                return f"MonitoredLock({self._name})"
        
        return MonitoredLock(lock, lock_name)


class MonitoredLock:
    """可监控的锁类
    
    使用方式:
        # 方式1: 直接创建
        lock = MonitoredLock("MyLock")
        with lock:
            # 临界区代码
            pass
        
        # 方式2: 包装现有锁
        original_lock = threading.Lock()
        lock = MonitoredLock.wrap(original_lock, "MyLock")
    """
    
    def __init__(self, name: str = "unnamed", monitored: bool = True):
        self._lock = threading.RLock()
        self._name = name
        self._monitored = monitored and LockMonitor.is_enabled()
    
    @staticmethod
    def wrap(lock: threading.Lock, name: str, monitored: bool = True):
        """包装现有锁"""
        monitored_lock = MonitoredLock(name, monitored)
        monitored_lock._lock = lock
        return monitored_lock
    
    def acquire(self, blocking: bool = True, timeout: float = -1):
        """获取锁"""
        if not self._monitored:
            return self._lock.acquire(blocking, timeout)
        
        wait_start = time.time()
        if timeout > 0:
            result = self._lock.acquire(blocking, timeout)
        else:
            result = self._lock.acquire(blocking)
        wait_time_ms = (time.time() - wait_start) * 1000
        
        if wait_time_ms > LockMonitor.get_threshold():
            record_lock_wait(
                lock_name=self._name,
                wait_time_ms=wait_time_ms,
                operation="acquire",
            )
        
        return result
    
    def release(self):
        """释放锁"""
        return self._lock.release()
    
    @property
    def locked(self):
        """检查锁状态"""
        return self._lock.locked()
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
    
    def __repr__(self):
        return f"MonitoredLock({self._name})"


def enable_lock_monitoring(threshold_ms: int = 100):
    """便捷函数：开启锁监控"""
    LockMonitor.set_threshold(threshold_ms)
    LockMonitor.enable()


def disable_lock_monitoring():
    """便捷函数：关闭锁监控"""
    LockMonitor.disable()
