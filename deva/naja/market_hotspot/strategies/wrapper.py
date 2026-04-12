"""热点策略包装器 - 将热点策略接入策略管理系统

实现 StrategyEntry 接口，代理到 HotspotStrategyManager
保持热点策略的核心竞争力（热点感知、动态调度）
"""

import time
from typing import Any, Callable, Dict, List, Optional

from deva.naja.strategy import StrategyEntry, StrategyMetadata, StrategyState
from deva.naja.infra.runtime.recoverable import UnitStatus
from .base import HotspotStrategyBase, Signal
from .strategy_manager import get_hotspot_manager, HotspotStrategyManager


HOTSPOT_STRATEGY_DIAGRAM_INFO = {
    "global_sentinel": {
        "icon": "🌐",
        "color": "#3b82f6",
        "description": "全局市场状态监控，实时感知整体市场热点水平",
        "formula": "global_hotspot = Σ(symbol_weights) / n",
        "logic": [
            "接收全市场行情数据流",
            "计算全市场热点加权总和",
            "判断市场整体活跃度等级",
            "输出市场状态信号（冷/暖/热）"
        ],
        "output": "global_hotspot: 0.0-1.0, activity_level: cold/warm/hot, market_state",
        "principle": {
            "core_mechanism": "通过加权求和计算全市场热点水平，将市场状态分为冷/暖/热三个等级。",
            "key_insights": [
                "市场热点是稀缺资源，集中于少数股票时往往意味着结构性机会",
                "冷市状态适合布局，热门市场需要注意回调风险",
                "热点转移往往先于价格变动"
            ],
            "when_to_use": "需要判断整体市场情绪和状态时使用，如仓位管理、入场时机选择等。"
        }
    },
    "block_rotation_hunter": {
        "icon": "🎯",
        "color": "#8b5cf6",
        "description": "题材轮动捕捉，追踪热点在题材间的转移",
        "formula": "block_momentum = Δ(hotspot_weight) / Δt",
        "logic": [
            "监测各题材热点权重变化",
            "计算题材间轮动速度",
            "识别正在崛起/衰退的题材",
            "输出题材轮动信号"
        ],
        "output": "rising_blocks: [...], falling_blocks: [...], rotation_speed",
        "principle": {
            "core_mechanism": "追踪热点在题材间的流动方向和速度，识别正在崛起或衰退的题材。",
            "key_insights": [
                "资金总是从老热点流向新热点，轮动是市场的主题",
                "强势题材的回调往往是二次入场机会",
                "题材轮动速度反映了市场热点的切换频率"
            ],
            "when_to_use": "需要捕捉题材轮动机会、优化行业配置时使用。"
        }
    },
    "momentum_surge_tracker": {
        "icon": "⚡",
        "color": "#f59e0b",
        "description": "动量突破追踪，捕捉强势股票的加速信号",
        "formula": "momentum_score = price_change * volume_ratio * hotspot_weight",
        "logic": [
            "筛选高热点股票池",
            "计算价格动量与成交量爆发",
            "多维度打分排序",
            "输出动量突破信号"
        ],
        "output": "momentum_stocks: [{symbol, score, change}], breakout_signals",
        "principle": {
            "core_mechanism": "结合价格动量、成交量爆发和热点权重，捕捉趋势加速的股票。",
            "key_insights": [
                "趋势一旦形成会持续，动量指标帮助确认趋势强度",
                "高成交量配合价格突破是最强的买入信号",
                "注意假突破，需要结合市场整体环境判断"
            ],
            "when_to_use": "需要追涨强势股、捕捉趋势加速行情时使用。"
        }
    },
    "anomaly_pattern_sniper": {
        "icon": "🎯",
        "color": "#ef4444",
        "description": "异常模式狙击，识别并追踪价格/成交量异常",
        "formula": "anomaly_score = |price_deviation| + |volume_deviation|",
        "logic": [
            "建立正常价格/成交量基线",
            "检测偏离基线的异常模式",
            "结合热点权重综合评分",
            "输出异常狙击信号"
        ],
        "output": "anomaly_stocks: [{symbol, anomaly_score, pattern_type}]",
        "principle": {
            "core_mechanism": "通过统计方法识别价格和成交量的异常偏离，捕捉可能存在操纵或特殊事件的股票。",
            "key_insights": [
                "异常往往意味着机会或风险，需要深入分析原因",
                "大单异动可能是机构行为的信号",
                "价格异常突破需要成交量确认"
            ],
            "when_to_use": "需要发现潜在主力动向、识别事件驱动机会时使用。"
        }
    },
    "smart_money_flow_detector": {
        "icon": "💰",
        "color": "#10b981",
        "description": "聪明资金流向检测，追踪大单动向",
        "formula": "smart_flow = net_buy_volume * order_size_weight * hotspot",
        "logic": [
            "分解订单流为大单/小单",
            "计算净买入方向与强度",
            "结合个股热点权重",
            "输出聪明资金信号"
        ],
        "output": "smart_flow_signals: [{symbol, direction, strength, confidence}]",
        "principle": {
            "core_mechanism": "通过追踪大单净流向，识别机构资金的布局方向，为散户提供跟随信号。",
            "key_insights": [
                "大单买入通常代表机构认可，是积极信号",
                "持续的大单流入表明主力正在吸筹",
                "需要结合股价位置综合判断，避免被高位出货"
            ],
            "when_to_use": "需要跟随机构资金、寻找主力布局标的时候使用。"
        }
    }
}


class HotspotStrategyWrapper(StrategyEntry):
    """
    热点策略包装器

    将 HotspotStrategyBase 包装成 StrategyEntry 接口，
    使其可以接入策略管理系统进行统一管理。
    """

    def __init__(
        self,
        strategy: HotspotStrategyBase,
        manager: Optional[HotspotStrategyManager] = None
    ):
        self._hotspot_strategy = strategy
        self._hotspot_manager = manager

        diagram_info = HOTSPOT_STRATEGY_DIAGRAM_INFO.get(strategy.strategy_id, {})

        metadata = StrategyMetadata(
            id=strategy.strategy_id,
            name=strategy.name,
            description=f"热点策略: {strategy.name} (scope={strategy.scope})",
            strategy_type="hotspot",
            handler_type="hotspot",
            category="热点策略",
            diagram_info=diagram_info,
        )
        metadata.tags = ["hotspot", strategy.scope, "auto-managed"]
        metadata.source = "hotspot"

        state = StrategyState()
        if strategy.is_active:
            state.status = UnitStatus.RUNNING.value

        super().__init__(metadata=metadata, state=state)

        self._func_code = ""
        self._compiled_func = None

    def _get_hotspot_manager(self) -> HotspotStrategyManager:
        if self._hotspot_manager is None:
            self._hotspot_manager = get_hotspot_manager()
        return self._hotspot_manager

    def _get_func_name(self) -> str:
        return "process"

    def _do_compile(self, code: str) -> Callable:
        def noop_process(data, context=None):
            return None
        return noop_process

    def save(self) -> dict:
        return {"success": True, "message": "热点策略由 HotspotStrategyManager 管理"}

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["hotspot_scope"] = self._hotspot_strategy.scope
        data["hotspot_strategy_id"] = self._hotspot_strategy.strategy_id
        data["is_active"] = self._hotspot_strategy.is_active
        data["execution_count"] = self._hotspot_strategy.execution_count
        data["skip_count"] = self._hotspot_strategy.skip_count
        data["signal_count"] = len(self._hotspot_strategy.signals)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "HotspotStrategyWrapper":
        raise NotImplementedError("HotspotStrategyWrapper 不能从 dict 重建")

    def get_hotspot_stats(self) -> Dict[str, Any]:
        """获取热点策略特有统计"""
        return self._hotspot_strategy.get_stats()

    def get_recent_signals(self, n: int = 50) -> List[Signal]:
        """获取最近的信号"""
        signals = list(self._hotspot_strategy.signals)
        return signals[-n:] if len(signals) > n else signals

    @property
    def is_hotspot_active(self) -> bool:
        return self._hotspot_strategy.is_active

    @property
    def scope(self) -> str:
        return self._hotspot_strategy.scope

    def start(self) -> dict:
        try:
            self._hotspot_strategy.activate()
            self._state.status = UnitStatus.RUNNING.value
            self._state.start_time = time.time()
            return {"success": True, "message": f"热点策略 {self.name} 已启动"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def stop(self) -> dict:
        try:
            self._hotspot_strategy.deactivate()
            self._state.status = UnitStatus.STOPPED.value
            return {"success": True, "message": f"热点策略 {self.name} 已停止"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _do_start(self, func: Callable) -> dict:
        return self.start()

    def _do_stop(self) -> dict:
        return self.stop()


def wrap_hotspot_strategy(
    strategy: HotspotStrategyBase,
    manager: Optional[HotspotStrategyManager] = None
) -> HotspotStrategyWrapper:
    """
    将热点策略包装成 StrategyEntry 接口

    Args:
        strategy: 热点策略实例
        manager: 热点策略管理器（可选）

    Returns:
        HotspotStrategyWrapper 包装实例
    """
    return HotspotStrategyWrapper(strategy, manager)


def register_hotspot_strategies_to_manager(
    strategy_mgr: "StrategyManager",
    hotspot_mgr: Optional[HotspotStrategyManager] = None
) -> List[HotspotStrategyWrapper]:
    """
    将所有热点策略注册到策略管理系统

    Args:
        strategy_mgr: 策略管理系统管理器
        hotspot_mgr: 热点策略管理器（可选，默认获取全局实例）

    Returns:
        注册成功的包装器列表
    """
    if hotspot_mgr is None:
        hotspot_mgr = get_hotspot_manager()

    wrapped_strategies = []

    for strategy_id, strategy in hotspot_mgr.strategies.items():
        wrapper = wrap_hotspot_strategy(strategy, hotspot_mgr)

        config = hotspot_mgr.configs.get(strategy_id)
        if config:
            wrapper._state.status = UnitStatus.RUNNING.value if config.enabled else UnitStatus.STOPPED.value

        try:
            strategy_mgr._items[strategy_id] = wrapper
            wrapped_strategies.append(wrapper)
        except Exception:
            pass

    return wrapped_strategies