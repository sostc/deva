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

log = logging.getLogger(__name__)


class ManasManager:
    """
    末那识引擎管理器

    管理 ManasEngine 的生命周期和状态

    使用方式：
        # 方式1: 独立模式（推荐）
        manager = ManasManager()
        manager.set_enabled(True)

        # 在主循环中调用
        manas_output = manager.compute()
    """

    def __init__(self, kernel=None, trading_clock=None, virtual_portfolio=None, bandit_tracker=None):
        self.kernel = kernel
        self._trading_clock = trading_clock
        self._virtual_portfolio = virtual_portfolio
        self._bandit_tracker = bandit_tracker
        self._manas_engine = None
        self._enabled = False
        self._last_compute_time = 0.0
        self._last_output: Optional[dict] = None

    def set_trading_clock(self, trading_clock):
        """显式设置 TradingClock（依赖注入）"""
        self._trading_clock = trading_clock

    def set_virtual_portfolio(self, virtual_portfolio):
        """显式设置 VirtualPortfolio（依赖注入）"""
        self._virtual_portfolio = virtual_portfolio

    def set_bandit_tracker(self, bandit_tracker):
        """显式设置 BanditTracker（依赖注入）"""
        self._bandit_tracker = bandit_tracker

    def set_enabled(self, enabled: bool):
        """
        设置是否启用末那识引擎

        Args:
            enabled: 是否启用
        """
        if enabled and not self._enabled:
            self._enabled = True
            if self.kernel is not None:
                # 兼容 OSAttentionKernel（无 set_manas_enabled）和标准 AttentionKernel
                if hasattr(self.kernel, 'set_manas_enabled'):
                    self.kernel.set_manas_enabled(True)
                # OSAttentionKernel 内部已持有 ManasEngine，通过 get_manas_engine 获取
                if hasattr(self.kernel, 'get_manas_engine'):
                    self._manas_engine = self.kernel.get_manas_engine()
            else:
                self._manas_engine = ManasEngine(
                    session_manager=self._trading_clock,
                    portfolio=self._virtual_portfolio,
                    bandit_tracker=self._bandit_tracker
                )

            # 引擎就绪后再挂事件总线：ManasEngine 构造期不再自订阅，
            # 这里是离创建点最近的装配位置（幂等，重复调用无副作用）
            self._attach_event_bus()
            log.info("[ManasManager] 末那识引擎已启用")
        elif not enabled:
            self._enabled = False
            if self.kernel is not None and hasattr(self.kernel, 'set_manas_enabled'):
                self.kernel.set_manas_enabled(False)
            log.info("[ManasManager] 末那识引擎已关闭")

    def _attach_event_bus(self) -> bool:
        """把当前引擎挂到认知事件总线（幂等）

        ManasEngine 的事件订阅已按架构基准 §6.3 移出构造函数，因此启用引擎后
        必须显式挂载一次；否则 _cognitive_state 不会随认知事件更新，
        叙事风险 / 共振分数 / AI 算力趋势会一直停在默认值。
        """
        engine = self.get_manas_engine()
        if engine is None:
            log.warning("[ManasManager] 引擎未就绪，跳过事件订阅")
            return False
        if not hasattr(engine, "subscribe_cognitive_events"):
            log.warning("[ManasManager] 引擎不支持 subscribe_cognitive_events，跳过")
            return False
        return bool(engine.subscribe_cognitive_events())

    def is_enabled(self) -> bool:
        """返回是否启用了末那识引擎"""
        return self._enabled
    
    def get_manas_engine(self) -> Optional[ManasEngine]:
        """
        获取 ManasEngine 实例
        
        Returns:
            ManasEngine 实例或 None
        """
        if self.kernel is not None:
            if hasattr(self.kernel, 'get_manas_engine'):
                return self.kernel.get_manas_engine()
            return None
        return self._manas_engine

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
            if hasattr(self.kernel, 'is_manas_enabled'):
                kernel_manas_enabled = self.kernel.is_manas_enabled()
            elif hasattr(self.kernel, 'get_manas_engine'):
                kernel_manas_enabled = self.kernel.get_manas_engine() is not None
        return {
            "enabled": self._enabled,
            "kernel_manas_enabled": kernel_manas_enabled,
            "last_output": self._last_output,
        }

    def _get_session_manager(self):
        """获取交易时段管理器

        ManasEngine 侧该依赖名为 session_manager（构造参数与 compute() 参数同名），
        因此这里的取数方法必须叫 _get_session_manager，与 compute() 的调用点保持一致。
        """
        return self._trading_clock

    def _get_portfolio(self):
        """获取虚拟持仓"""
        return self._virtual_portfolio

    def _get_bandit_tracker(self):
        """获取 bandit tracker"""
        return self._bandit_tracker

    def _get_scanner(self):
        try:
            from deva.naja.radar.global_market_scanner import get_global_market_scanner
            return get_global_market_scanner()
        except ImportError:
            return None

    def _get_macro_signal(self) -> float:
        return 0.5


def get_manas_manager() -> Optional[ManasManager]:
    """获取全局末那识管理器"""
    # 从 AppContainer 获取
    from deva.naja.application import get_app_container
    container = get_app_container()
    if container is not None:
        return container.manas_manager
    return None
