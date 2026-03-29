"""
FourDimensions 智能触发器

根据条件自动启用/禁用四维决策框架

触发条件：
1. 资金不足自动启用（cash_ratio < 0.2）
2. 市场极端自动启用（liquidity_signal < 0.3 或 > 0.8）
3. 非交易时段自动启用（保守模式）
4. 手动模式（默认）

关闭条件：
1. 所有条件恢复正常后保持关闭
2. 手动切换
"""

import time
import logging
from typing import Optional
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class TriggerConfig:
    """触发器配置"""
    auto_enable_low_cash: bool = True
    auto_enable_extreme_market: bool = True
    auto_enable_off_hours: bool = False
    low_cash_threshold: float = 0.2
    extreme_low_signal: float = 0.3
    extreme_high_signal: float = 0.8
    check_interval: float = 5.0


class FourDimensionsTrigger:
    """
    四维决策框架智能触发器

    自动检测条件，决定是否启用四维

    使用方式：
        trigger = FourDimensionsTrigger()
        trigger.start()

        # 或手动控制
        trigger.set_auto_mode(False)
        trigger.set_enabled(True)
    """

    def __init__(self, config: Optional[TriggerConfig] = None):
        self.config = config or TriggerConfig()
        self._enabled = False
        self._auto_mode = True
        self._last_check = 0
        self._trigger_reason: Optional[str] = None
        self._last_trigger_state = False

    def should_enable(self) -> bool:
        """
        判断是否应该启用四维

        Returns:
            (should_enable, reason)
        """
        from .four_dimensions import FourDimensions

        fd = FourDimensions()

        fd.update(
            session_manager=self._get_session_manager(),
            portfolio=self._get_portfolio(),
            strategy_manager=self._get_strategy_manager(),
            scanner=self._get_scanner(),
            macro_signal=0.5
        )

        if self.config.auto_enable_low_cash and fd.capital.cash_ratio < self.config.low_cash_threshold:
            self._trigger_reason = f"资金不足 (cash_ratio={fd.capital.cash_ratio:.2%})"
            return True

        if self.config.auto_enable_extreme_market:
            signal = fd.market.liquidity_signal
            if signal < self.config.extreme_low_signal:
                self._trigger_reason = f"市场极度恐慌 (signal={signal:.2f})"
                return True
            if signal > self.config.extreme_high_signal:
                self._trigger_reason = f"市场极度贪婪 (signal={signal:.2f})"
                return True

        if self.config.auto_enable_off_hours and not fd.time.is_trading_open:
            if fd.time.market_status != "unknown":
                self._trigger_reason = f"非交易时段 (status={fd.time.market_status})"
                return True

        self._trigger_reason = None
        return False

    def update(self) -> bool:
        """
        更新触发器状态

        Returns:
            当前是否应该启用四维
        """
        if not self._auto_mode:
            return self._enabled

        current_time = time.time()
        if current_time - self._last_check < self.config.check_interval:
            return self._last_trigger_state

        self._last_check = current_time
        self._last_trigger_state = self.should_enable()
        return self._last_trigger_state

    def get_status(self) -> dict:
        """获取触发器状态"""
        return {
            "enabled": self._enabled,
            "auto_mode": self._auto_mode,
            "should_enable": self._last_trigger_state,
            "trigger_reason": self._trigger_reason,
        }

    def set_enabled(self, enabled: bool):
        """手动设置启用状态"""
        self._enabled = enabled
        self._auto_mode = False

    def set_auto_mode(self, auto: bool):
        """设置自动模式"""
        self._auto_mode = auto

    def is_auto_mode(self) -> bool:
        """是否是自动模式"""
        return self._auto_mode

    def _get_session_manager(self):
        try:
            from deva.naja.radar.trading_clock import get_trading_clock
            return get_trading_clock()
        except ImportError:
            return None

    def _get_portfolio(self):
        try:
            from deva.naja.bandit import get_virtual_portfolio
            return get_virtual_portfolio()
        except ImportError:
            return None

    def _get_strategy_manager(self):
        try:
            from deva.naja.attention.strategies import get_strategy_manager
            return get_strategy_manager()
        except ImportError:
            return None

    def _get_scanner(self):
        try:
            from deva.naja.radar.global_market_scanner import get_global_market_scanner
            return get_global_market_scanner()
        except ImportError:
            return None


class FourDimensionsManager:
    """
    四维决策框架管理器

    包装 AttentionKernel，自动管理四维的启用/禁用

    使用方式：
        manager = FourDimensionsManager(kernel)
        manager.start()

        # 在主循环中调用
        manager.update()  # 自动检查并更新四维状态
    """

    def __init__(self, kernel, trigger_config: Optional[TriggerConfig] = None):
        from .four_dimensions import FourDimensions
        self.kernel = kernel
        self.trigger = FourDimensionsTrigger(trigger_config)
        self._last_log_time = 0

    def update(self):
        """更新四维状态"""
        should_enable = self.trigger.update()
        current_state = self.kernel.is_four_dimensions_enabled()

        if should_enable != current_state:
            self.kernel.set_four_dimensions_enabled(should_enable)

            status = self.trigger.get_status()
            if should_enable:
                log.info(f"[FourDimensionsManager] 启用四维: {status['trigger_reason']}")
            else:
                log.info("[FourDimensionsManager] 关闭四维")

        if should_enable and time.time() - self._last_log_time > 60:
            status = self.trigger.get_status()
            log.info(f"[FourDimensionsManager] 四维状态: {status}")
            self._last_log_time = time.time()

    def set_enabled(self, enabled: bool):
        """手动启用/禁用"""
        self.trigger.set_enabled(enabled)
        self.kernel.set_four_dimensions_enabled(enabled)

    def set_auto_mode(self, auto: bool):
        """设置自动模式"""
        self.trigger.set_auto_mode(auto)

    def get_status(self) -> dict:
        """获取状态"""
        return {
            "kernel_fd_enabled": self.kernel.is_four_dimensions_enabled(),
            "trigger": self.trigger.get_status(),
        }


_global_manager: Optional[FourDimensionsManager] = None


def get_four_dimensions_manager() -> Optional[FourDimensionsManager]:
    """获取全局四维管理器"""
    return _global_manager


def setup_four_dimensions_manager(kernel, config: Optional[TriggerConfig] = None) -> FourDimensionsManager:
    """设置全局四维管理器"""
    global _global_manager
    _global_manager = FourDimensionsManager(kernel, config)
    return _global_manager
