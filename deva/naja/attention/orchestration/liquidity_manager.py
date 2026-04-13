"""
LiquidityManager - 流动性管理模块

职责：
- 组合状态更新
- 宏观流动性更新
- 流动性应用到各系统

从 AttentionOrchestrator 拆分出来
"""

import logging
import threading
from typing import Dict, Any

log = logging.getLogger(__name__)


class LiquidityManager:
    """
    流动性管理器

    负责：
    - 更新组合状态
    - 宏观流动性监测
    - 流动性信号应用到注意力、策略预算、频率
    """

    _instance = None

    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # double-checked locking
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        with self.__class__._lock:
            if getattr(self, '_initialized', False):
                return
            self._ensure_initialized()

    def _ensure_initialized(self):
        """初始化"""
        self._portfolio_state = {
            "total_value": 0.0,
            "cash": 0.0,
            "position_value": 0.0,
            "daily_pnl": 0.0,
        }
        self._macro_liquidity_signal = 0.0
        self._liquidity_history = []
        self._initialized = True
        log.info("LiquidityManager 初始化完成")

    def update_portfolio_state(self):
        """更新组合状态"""
        try:
            from deva.naja.radar.global_market_scanner import get_global_market_scanner
            scanner = get_global_market_scanner()
            if scanner:
                market_data = scanner.get_snapshot()
                if market_data:
                    self._portfolio_state["total_value"] = market_data.get("total_value", 0)
                    self._portfolio_state["cash"] = market_data.get("cash", 0)
                    self._portfolio_state["position_value"] = market_data.get("position_value", 0)
                    self._portfolio_state["daily_pnl"] = market_data.get("daily_pnl", 0)
                    log.debug(f"[Liquidity] 组合状态更新: {self._portfolio_state}")
        except Exception as e:
            log.debug(f"[Liquidity] 更新组合状态失败: {e}")

    def update_macro_liquidity_from_scanner(self):
        """从 Scanner 更新宏观流动性"""
        try:
            from deva.naja.radar.global_market_scanner import get_global_market_scanner
            scanner = get_global_market_scanner()
            if scanner:
                snapshot = scanner.get_snapshot()
                if snapshot:
                    market_state = snapshot.get("market_state", {})
                    global_attention = market_state.get("global_attention", 0.5)

                    if global_attention > 0.7:
                        self._macro_liquidity_signal = 1.0
                    elif global_attention > 0.5:
                        self._macro_liquidity_signal = 0.5
                    elif global_attention < 0.3:
                        self._macro_liquidity_signal = -1.0
                    else:
                        self._macro_liquidity_signal = 0.0

                    self._liquidity_history.append(self._macro_liquidity_signal)
                    if len(self._liquidity_history) > 100:
                        self._liquidity_history = self._liquidity_history[-100:]

                    log.debug(f"[Liquidity] 宏观流动性信号: {self._macro_liquidity_signal}")
        except Exception as e:
            log.debug(f"[Liquidity] 更新宏观流动性失败: {e}")

    def apply_liquidity_to_block_attention(self, liquidity_signal: float):
        """应用流动性到题材注意力"""
        try:
            if abs(liquidity_signal) < 0.3:
                return

            from deva.naja.cognition.semantic.keyword_registry import KeywordRegistry
            registry = KeywordRegistry()

            if liquidity_signal > 0:
                registry.apply_liquidity_bonus("bullish_blocks", liquidity_signal * 0.2)
            else:
                registry.apply_liquidity_penalty("bearish_blocks", abs(liquidity_signal) * 0.2)

            log.debug(f"[Liquidity] 应用流动性到题材注意力: {liquidity_signal}")
        except Exception as e:
            log.debug(f"[Liquidity] 应用流动性到题材注意力失败: {e}")

    def apply_liquidity_to_strategy_budget(self, liquidity_signal: float):
        """应用流动性到策略预算"""
        try:
            if abs(liquidity_signal) < 0.3:
                return

            from deva.naja.market_hotspot.strategies import get_strategy_manager
            mgr = get_strategy_manager()
            if mgr:
                if liquidity_signal > 0:
                    mgr.apply_budget_multiplier("high_liquidity", 1.2)
                else:
                    mgr.apply_budget_multiplier("low_liquidity", 0.8)

            log.debug(f"[Liquidity] 应用流动性到策略预算: {liquidity_signal}")
        except Exception as e:
            log.debug(f"[Liquidity] 应用流动性到策略预算失败: {e}")

    def apply_liquidity_to_frequency(self, liquidity_signal: float):
        """应用流动性到交易频率"""
        try:
            from deva.naja.risk import PositionSizer
            sizer = PositionSizer()
            if sizer:
                if liquidity_signal < -0.5:
                    sizer.apply_frequency_limit("low_liquidity", max_trades=3)
                elif liquidity_signal > 0.5:
                    sizer.apply_frequency_limit("high_liquidity", max_trades=10)

            log.debug(f"[Liquidity] 应用流动性到频率: {liquidity_signal}")
        except Exception as e:
            log.debug(f"[Liquidity] 应用流动性到频率失败: {e}")

    def get_liquidity_signal(self) -> float:
        """获取当前流动性信号"""
        return self._macro_liquidity_signal

    def get_portfolio_state(self) -> Dict[str, Any]:
        """获取组合状态"""
        return self._portfolio_state


def get_liquidity_manager() -> LiquidityManager:
    """获取 LiquidityManager 单例

    直接委托给 LiquidityManager() 构造函数，
    由 __new__ + threading.Lock 保证线程安全的单例。
    """
    return LiquidityManager()
