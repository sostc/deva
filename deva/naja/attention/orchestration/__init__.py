"""
attention/orchestration/ - 协调层

包含交易中枢、认知协调、信号执行、状态查询。

❗本包**没有**「流动性管理」——`liquidity_manager.LiquidityManager` 已于
2026-10-15 退役（详见当日日志）：它自称「宏观流动性」，量纲却是**带符号 −1~1**，
与 `QueryState.macro_liquidity_signal` 的 **0~1** 不是同一个数；且它三个
`apply_liquidity_to_*` 的目标方法全仓根本不存在、两个 `update_*` 零调用方。
宏观流动性只有 `attention/kernel/macro_liquidity.py` 一处口径，别在这里再建。
"""

from .trading_center import TradingCenter, get_trading_center
from .cognition_orchestrator import CognitionOrchestrator
from .signal_executor import SignalExecutor
from .state_querier import StateQuerier

__all__ = [
    "TradingCenter",
    "get_trading_center",
    "CognitionOrchestrator",
    "SignalExecutor",
    "StateQuerier",
]
