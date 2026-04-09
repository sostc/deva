"""
ManasManager - 末那识引擎管理器

管理 ManasEngine 的生命周期和状态

使用方式：
    manager = ManasManager(kernel)
    manager.set_enabled(True)

    # 在主循环中调用
    manas_output = manager.compute()
"""

import time
import logging
from typing import Optional

from .manas_engine import ManasEngine
from deva.naja.register import SR

log = logging.getLogger(__name__)


class ManasManager:
    """
    末那识引擎管理器

    管理 ManasEngine 的生命周期和状态

    使用方式：
        # 方式1: 独立模式（推荐）
        manager = ManasManager()
        manager.set_enabled(True)

        # 方式2: 包装 AttentionKernel 模式（已废弃）
        manager = ManasManager(kernel)
        manager.set_enabled(True)

        # 在主循环中调用
        manas_output = manager.compute()
    """

    def __init__(self, kernel=None):
        self.kernel = kernel
        self._manas_engine = None
        self._enabled = False
        self._last_compute_time = 0.0
        self._last_output: Optional[dict] = None

        if kernel is not None:
            self._enabled = False
        else:
            self._manas_engine = None
            self._enabled = False

    def set_enabled(self, enabled: bool):
        """
        设置是否启用末那识引擎

        Args:
            enabled: 是否启用
        """
        if enabled and not self._enabled:
            self._enabled = True
            if self.kernel is not None:
                self.kernel.set_manas_enabled(True)
            else:
                self._manas_engine = ManasEngine()
            log.info("[ManasManager] 末那识引擎已启用")
        elif not enabled:
            self._enabled = False
            if self.kernel is not None:
                self.kernel.set_manas_enabled(False)
            log.info("[ManasManager] 末那识引擎已关闭")

    def is_enabled(self) -> bool:
        """返回是否启用了末那识引擎"""
        return self._enabled

    def compute(self) -> Optional[dict]:
        """
        计算末那识输出

        Returns:
            ManasOutput dict 或 None（如果未启用）
        """
        if not self._enabled:
            return None

        current_time = time.time()
        if current_time - self._last_compute_time < 1.0 and self._last_output is not None:
            return self._last_output

        if self.kernel is not None:
            manas_engine = self.kernel.get_manas_engine()
        else:
            manas_engine = self._manas_engine

        if manas_engine is None:
            return None

        output = manas_engine.compute(
            session_manager=self._get_session_manager(),
            portfolio=self._get_portfolio(),
            scanner=self._get_scanner(),
            bandit_tracker=self._get_bandit_tracker(),
            macro_signal=self._get_macro_signal(),
        )

        self._last_output = output.to_dict()
        self._last_compute_time = current_time

        return self._last_output

    def get_state(self) -> dict:
        """获取末那识引擎状态"""
        kernel_manas_enabled = False
        if self.kernel is not None:
            kernel_manas_enabled = self.kernel.is_manas_enabled()
        return {
            "enabled": self._enabled,
            "kernel_manas_enabled": kernel_manas_enabled,
            "last_output": self._last_output,
        }

    def _get_session_manager(self):
        try:
            return SR('trading_clock')
        except ImportError:
            return None

    def _get_portfolio(self):
        try:
            return SR('virtual_portfolio')
        except ImportError:
            return None

    def _get_bandit_tracker(self):
        try:
            return SR('bandit_tracker')
        except ImportError:
            return None

    def _get_scanner(self):
        try:
            from deva.naja.radar.global_market_scanner import get_global_market_scanner
            return get_global_market_scanner()
        except ImportError:
            return None

    def _get_macro_signal(self) -> float:
        return 0.5


_global_manager: Optional[ManasManager] = None
_global_manager_initialized = False


def get_manas_manager() -> Optional[ManasManager]:
    """获取全局末那识管理器（自动启用）"""
    global _global_manager, _global_manager_initialized
    if _global_manager is None and not _global_manager_initialized:
        _global_manager_initialized = True
        try:
            from deva.naja.common.singleton_registry import SR
            _global_manager = SR('manas_manager')
            if _global_manager is not None and not _global_manager.is_enabled():
                _global_manager.set_enabled(True)
        except Exception:
            pass
    return _global_manager


def setup_manas_manager(kernel) -> ManasManager:
    """设置全局末那识管理器"""
    global _global_manager
    _global_manager = ManasManager(kernel)
    return _global_manager


def setup_manas_manager(kernel) -> ManasManager:
    """设置全局末那识管理器"""
    global _global_manager
    _global_manager = ManasManager(kernel)
    return _global_manager
