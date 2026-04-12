# 兼容 shim - 实际实现已移至 attention/orchestration/trading_center.py
from .orchestration.trading_center import *  # noqa: F401,F403
from .orchestration.trading_center import TradingCenter, get_trading_center  # noqa: F401
