"""单例管理器混入类

提供统一的单例初始化模式，确保：
1. 单例只被创建一次
2. 初始化只发生一次
3. 初始化时机可控（不依赖 __init__ 的调用时机）
"""

from __future__ import annotations

import threading
from typing import Optional, Callable, Any


class SingletonMixin:
    """单例混入类

    使用方式：
    class DataSourceManager(SingletonMixin):
        _instance = None
        _lock = threading.Lock()

        def __init__(self):
            # 不在这里做数据加载！
            self._items = {}
            self._initialized = False

        def _do_initialize(self):
            # 实际的初始化逻辑
            self._items = load_data()
            self._initialized = True
    """

    _instance: Optional[Any] = None
    _lock: threading.Lock = None
    _init_lock: threading.Lock = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return

        if getattr(self, '_init_lock', None) is None:
            self._init_lock = threading.Lock()

        with self._init_lock:
            if getattr(self, '_initialized', False):
                return

            self._do_initialize()
            self._initialized = True

    def _do_initialize(self):
        """子类实现实际的初始化逻辑"""
        raise NotImplementedError("子类必须实现 _do_initialize()")


class LazySingletonMixin:
    """延迟初始化单例混入类

    与 SingletonMixin 的区别：
    - SingletonMixin：在 __init__ 时自动初始化
    - LazySingletonMixin：第一次访问时才初始化

    使用方式：
    class DataSourceManager(LazySingletonMixin):
        _instance = None
        _lock = threading.Lock()

        def _do_initialize(self):
            self._items = load_data()
    """

    _instance: Optional[Any] = None
    _lock: threading.Lock = None

    def __new__(cls, *args, **kwargs):
        return cls._get_instance()

    @classmethod
    def _get_instance(cls):
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
        """确保已初始化（延迟初始化模式）"""
        if getattr(self, '_initialized', False):
            return

        with self._init_lock:
            if getattr(self, '_initialized', False):
                return
            self._do_initialize()
            self._initialized = True

    def _do_initialize(self):
        """子类实现实际的初始化逻辑"""
        raise NotImplementedError("子类必须实现 _do_initialize()")


def ensure_initialized(method):
    """装饰器：确保方法调用前已初始化

    使用方式：
    class DataSourceManager(LazySingletonMixin):
        @ensure_initialized
        def list_all(self):
            return list(self._items.values())
    """
    def wrapper(self, *args, **kwargs):
        self._ensure_initialized()
        return method(self, *args, **kwargs)
    return wrapper
