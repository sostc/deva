"""策略分类标签系统

定义策略的处理类型，用于将策略路由到合适的处理模块：
- radar: 雷达专用策略（异常检测、漂移检测、模式识别）
- memory: 记忆系统策略（主题聚类、注意力评分）
- bandit: 交易策略（买卖信号、仓位管理）
- llm: LLM调节策略（参数优化、策略调优）
"""

from __future__ import annotations

from enum import Enum


class StrategyHandlerType(str, Enum):
    """策略处理器类型枚举"""
    RADAR = "radar"           # 雷达处理
    MEMORY = "memory"         # 记忆处理
    BANDIT = "bandit"         # 交易处理
    LLM = "llm"               # LLM调节
    UNKNOWN = "unknown"        # 未分类


STRATEGY_HANDLER_LABELS = {
    "radar": {
        "description": "雷达专用策略",
        "examples": ["异常检测", "漂移检测", "模式识别", "波动率爆发"],
        "handler_module": "deva.naja.radar",
    },
    "memory": {
        "description": "记忆系统策略",
        "examples": ["主题聚类", "注意力评分", "趋势反转"],
        "handler_module": "deva.naja.memory",
    },
    "bandit": {
        "description": "交易策略",
        "examples": ["动量趋势", "资金集中度", "买卖信号"],
        "handler_module": "deva.naja.bandit",
    },
    "llm": {
        "description": "LLM调节策略",
        "examples": ["参数优化", "策略调优"],
        "handler_module": "deva.naja.llm_controller",
    },
}


STRATEGY_TYPE_TO_HANDLER: Dict[str, StrategyHandlerType] = {
    "tick_anomaly_hst": StrategyHandlerType.RADAR,
    "tick_drift_adwin": StrategyHandlerType.RADAR,
    "tick_volatility_burst": StrategyHandlerType.RADAR,
    "tick_breadth_concentration": StrategyHandlerType.RADAR,
    "tick_regime_cluster": StrategyHandlerType.MEMORY,
    "tick_volume_price_spike": StrategyHandlerType.MEMORY,
    "tick_trend_reversal": StrategyHandlerType.MEMORY,
    "tick_momentum_trend": StrategyHandlerType.BANDIT,
    "tick_capital_concentration": StrategyHandlerType.BANDIT,
}


def get_strategy_handler_type(signal_type: str) -> StrategyHandlerType:
    """根据信号类型获取对应的处理器类型
    
    Args:
        signal_type: 信号类型 (如 tick_anomaly_hst)
        
    Returns:
        StrategyHandlerType: 处理器类型
    """
    return STRATEGY_TYPE_TO_HANDLER.get(signal_type, StrategyHandlerType.UNKNOWN)


__all__ = ["StrategyHandlerType", "get_strategy_handler_type"]
