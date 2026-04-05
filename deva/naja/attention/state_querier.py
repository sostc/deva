"""
StateQuerier - 状态查询模块

职责：
- 状态查询
- 统计信息
- Lab状态

从 AttentionOrchestrator 拆分出来
"""

import logging
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)


class StateQuerier:
    """
    状态查询器

    负责：
    - 提供系统状态
    - 统计信息
    - Lab状态
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            import threading
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._init_lock = threading.Lock()
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        with self._init_lock:
            if getattr(self, '_initialized', False):
                return
            self._ensure_initialized()

    def _ensure_initialized(self):
        """初始化"""
        self._awakened_state = {
            "volatility_signals": 0,
            "awakening_level": "dormant",
            "illuminated_patterns": 0,
            "first_principles_insights": 0,
            "adaptive_decisions": 0,
        }
        self._initialized = True
        log.info("StateQuerier 初始化完成")

    def get_awakened_state(self) -> Dict[str, Any]:
        """获取觉醒状态"""
        return self._awakened_state

    def _get_volatility_surface_state(self) -> Dict[str, Any]:
        """获取波动率曲面状态"""
        try:
            from deva.naja.senses import VolatilitySurfaceSense
            surface = VolatilitySurfaceSense()
            if surface:
                return {
                    "regime": surface.get_regime(),
                    "volatility": surface.get_volatility(),
                }
        except Exception as e:
            log.debug(f"[StateQuerier] 获取波动率曲面状态失败: {e}")
        return {"regime": "normal", "volatility": 0.5}

    def _get_awakening_level(self) -> str:
        """获取觉醒级别"""
        return self._awakened_state.get("awakening_level", "dormant")

    def _check_contradiction(self) -> Dict[str, Any]:
        """检查矛盾"""
        return {
            "has_contradiction": False,
            "description": "",
            "severity": 0.0,
        }

    def _get_adaptive_factor(self) -> float:
        """获取自适应因子"""
        return 1.0

    def _apply_volatility_surface_check(self, data) -> Dict[str, Any]:
        """应用波动率曲面检查"""
        return {"passed": True, "warnings": []}

    def get_cached_market_time(self) -> str:
        """获取缓存的市场时间"""
        try:
            from deva.naja.radar.trading_clock import get_trading_clock
            clock = get_trading_clock()
            if clock:
                return clock.get_formatted_time()
        except Exception:
            pass
        return ""

    def get_lab_status(self) -> Dict[str, Any]:
        """获取 Lab 状态"""
        try:
            from deva.naja.attention.kernel import get_default_kernel
            kernel = get_default_kernel()
            if kernel:
                kernel_status = kernel.get_status()
            else:
                kernel_status = {}
        except Exception:
            kernel_status = {}

        return {
            "kernel": kernel_status,
            "awakening": self._awakened_state,
            "volatility_surface": self._get_volatility_surface_state(),
        }

    def get_attention_context(self) -> Dict[str, Any]:
        """获取注意力上下文"""
        return {
            "awakening_level": self._get_awakening_level(),
            "volatility_surface": self._get_volatility_surface_state(),
            "contradiction": self._check_contradiction(),
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "awakening": self._awakened_state,
            "volatility_surface": self._get_volatility_surface_state(),
        }

    def _get_block_weights(self) -> Dict[str, float]:
        """获取板块权重"""
        return {}

    def _get_symbol_weights(self) -> Dict[str, float]:
        """获取符号权重"""
        return {}

    def get_human_readable_status(self) -> str:
        """获取人类可读状态"""
        return f"Awakening: {self._get_awakening_level()}"

    def _get_decision_summary(self) -> Dict[str, Any]:
        """获取决策摘要"""
        return {
            "awakening_level": self._get_awakening_level(),
            "volatility": self._get_volatility_surface_state(),
            "contradiction": self._check_contradiction(),
        }


_state_querier: Optional['StateQuerier'] = None


def get_state_querier() -> StateQuerier:
    """获取 StateQuerier 单例"""
    global _state_querier
    if _state_querier is None:
        _state_querier = StateQuerier()
    return _state_querier
