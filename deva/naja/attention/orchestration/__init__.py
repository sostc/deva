"""
attention/orchestration/ - 协调层

包含交易中枢、认知协调、信号执行、状态查询、流动性管理。
"""

from .trading_center import TradingCenter, get_trading_center
from .cognition_orchestrator import CognitionOrchestrator
from .signal_executor import SignalExecutor
from .state_querier import StateQuerier
from .liquidity_manager import LiquidityManager

__all__ = [
    "TradingCenter",
    "get_trading_center",
    "CognitionOrchestrator",
    "SignalExecutor",
    "StateQuerier",
    "LiquidityManager",
]
