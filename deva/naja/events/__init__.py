"""
Naja 事件系统 - 双总线 + 桥梁架构

🚀 架构说明：
1. 认知总线 (CognitiveEventBus) - 处理认知层内部信号
2. 交易总线 (TradingEventBus) - 处理交易层信号  
3. 桥梁 (BusBridge) - 连接两个总线，按需通信

使用指南：
    # 场景1：只关心认知事件
    from deva.naja.events import get_cognitive_bus, CognitiveEventType
    bus = get_cognitive_bus()
    bus.publish_cognitive_event(source="NarrativeTracker", event_type=CognitiveEventType.NARRATIVE_UPDATE)

    # 场景2：只关心交易事件  
    from deva.naja.events import get_trading_bus, StrategySignalEvent
    bus = get_trading_bus()
    bus.publish(StrategySignalEvent(symbol="000001", direction="buy"))

    # 场景3：需要桥梁通信
    from deva.naja.events import get_bus_bridge
    bridge = get_bus_bridge()
    bridge.enable_bridge(True)

    # 场景4：简单选择（推荐新代码）
    from deva.naja.events import publish_event, subscribe_event
    publish_event(event)  # 自动选择总线
    subscribe_event(event_type, callback)  # 跨总线订阅
"""

import logging

log = logging.getLogger(__name__)

# ============== 总线实例 ==============

# 导入认知总线（保持原样）
from .cognitive_bus import (
    # 认知总线类
    NajaEventBus as CognitiveEventBus,
    EventSubscription,
    # 认知事件枚举
    CognitiveEventType,
    # 单例访问
    get_event_bus as get_cognitive_bus,
    reset_event_bus as reset_cognitive_bus,
)

# 导入交易总线
try:
    from .trading_bus import (
        TradingEventBus,
        get_trading_bus,
        reset_trading_bus,
    )
    TRADING_BUS_AVAILABLE = True
except ImportError:
    TRADING_BUS_AVAILABLE = False
    log.warning("交易总线不可用，部分功能受限")

# 导入桥梁
try:
    from .bus_bridge import (
        BusBridge,
        get_bus_bridge,
    )
    BRIDGE_AVAILABLE = True
except ImportError:
    BRIDGE_AVAILABLE = False

# ============== 事件定义（保持原样） ==============

# 文本事件
from .text_events import (
    TextFetchedEvent,
    TextFocusedEvent,
)

# 热点事件
from .hotspot_events import (
    HotspotComputedEvent,
    HotspotShiftEvent,
    MarketSnapshotEvent,
    SymbolUpdateEvent,
)

# 认知事件
from .cognitive_events import (
    CognitiveInsightEvent,
    NarrativeStateEvent,
    LiquiditySignalEvent,
    MerrillClockEvent,
)

# 交易事件
from .trading_events import (
    StrategySignalEvent,
    TradeDecisionEvent,
    SignalDirection,
    DecisionResult,
)
from .router import resolve_event_bus_type

# 认知事件 dataclass（可选）
try:
    from .cognition_events import (
        # 所有认知事件 dataclass
        NarrativeUpdateEvent,
        TimingNarrativeShiftEvent,
        ResonanceDetectedEvent,
        SupplyChainRiskEvent,
        RiskAlertEvent,
        GlobalMarketEvent,
        PortfolioSignalEvent,
        CognitionResetEvent,
        # 快捷创建函数
        create_narrative_update,
        create_risk_alert,
        # 映射
        EVENT_TYPE_MAP,
    )
    COGNITION_EVENTS_AVAILABLE = True
except ImportError:
    COGNITION_EVENTS_AVAILABLE = False

# ============== 简单选择器（推荐新代码使用） ==============

def publish_event(event) -> int:
    """
    智能发布事件（自动选择总线）
    
    根据事件类型选择：
    - 认知事件 dataclass → 认知总线
    - 交易事件 dataclass → 交易总线
    - 其他 → 尝试兼容处理
    
    Returns:
        分发到的订阅者数量
    """
    if event is None:
        return 0
    
    try:
        bus_type = resolve_event_bus_type(event)
    except ValueError:
        try:
            return get_cognitive_bus().publish(event)
        except Exception:
            if TRADING_BUS_AVAILABLE:
                return get_trading_bus().publish(event)
            return 0

    if bus_type == "trading":
        if not TRADING_BUS_AVAILABLE:
            raise RuntimeError("交易总线不可用，无法发布交易事件")
        from .trading_bus import get_trading_bus
        return get_trading_bus().publish(event)
    return get_cognitive_bus().publish(event)


def publish_cognitive_event(event) -> int:
    return get_cognitive_bus().publish(event)


def publish_trading_event(event) -> int:
    if not TRADING_BUS_AVAILABLE:
        raise RuntimeError("交易总线不可用，无法发布交易事件")
    from .trading_bus import get_trading_bus
    return get_trading_bus().publish(event)


def subscribe_event(event_type: str, callback, bus_type: str = "auto", **kwargs):
    """
    智能订阅事件（跨总线）
    
    Args:
        event_type: 事件类型（dataclass 类名或 CognitiveEventType）
        callback: 回调函数
        bus_type: "cognitive", "trading", 或 "auto"（自动选择）
        **kwargs: 其他订阅参数
        
    Returns:
        订阅ID
    """
    if bus_type == "cognitive":
        return get_cognitive_bus().subscribe(event_type, callback, **kwargs)
    elif bus_type == "trading" and TRADING_BUS_AVAILABLE:
        from .trading_bus import get_trading_bus
        return get_trading_bus().subscribe(event_type, callback, **kwargs)
    else:
        if TRADING_BUS_AVAILABLE and event_type in ['StrategySignalEvent', 'TradeDecisionEvent']:
            try:
                from .trading_bus import get_trading_bus
                return get_trading_bus().subscribe(event_type, callback, **kwargs)
            except Exception:
                pass
        return get_cognitive_bus().subscribe(event_type, callback, **kwargs)


# ============== 兼容性包装 ==============

# 保持 get_event_bus 的兼容性（返回认知总线）
get_event_bus = get_cognitive_bus
reset_event_bus = reset_cognitive_bus

# 别名
NajaEventBus = CognitiveEventBus


# ============== 导出列表 ==============

__all__ = [
    # 架构说明
    "CognitiveEventBus",  # 认知总线
    "TradingEventBus",    # 交易总线
    "BusBridge",          # 桥梁
    
    # 单例获取
    "get_cognitive_bus",
    "get_trading_bus", 
    "get_bus_bridge",
    "reset_cognitive_bus",
    "reset_trading_bus",
    
    # 兼容性接口
    "get_event_bus",      # 兼容旧代码
    "reset_event_bus",    # 兼容旧代码
    "NajaEventBus",       # 别名
    
    # 订阅配置
    "EventSubscription",
    
    # 认知事件枚举
    "CognitiveEventType",
    
    # 简单选择器（推荐新代码使用）
    "publish_event",
    "publish_cognitive_event",
    "publish_trading_event",
    "subscribe_event",
    
    # 文本事件
    "TextFetchedEvent",
    "TextFocusedEvent",
    
    # 热点事件
    "HotspotComputedEvent",
    "HotspotShiftEvent",
    "MarketSnapshotEvent",
    "SymbolUpdateEvent",
    
    # 认知事件
    "CognitiveInsightEvent",
    "NarrativeStateEvent",
    "LiquiditySignalEvent",
    "MerrillClockEvent",
    
    # 交易事件
    "StrategySignalEvent",
    "TradeDecisionEvent",
    "SignalDirection",
    "DecisionResult",
]

# 有条件导出的认知事件 dataclass
if COGNITION_EVENTS_AVAILABLE:
    __all__.extend([
        "NarrativeUpdateEvent",
        "TimingNarrativeShiftEvent",
        "ResonanceDetectedEvent",
        "SupplyChainRiskEvent",
        "RiskAlertEvent",
        "GlobalMarketEvent",
        "PortfolioSignalEvent",
        "CognitionResetEvent",
        "create_narrative_update",
        "create_risk_alert",
        "EVENT_TYPE_MAP",
    ])

# 使用说明
__doc__ += f"""

📊 系统状态:
- 认知总线: ✅ 可用
- 交易总线: {'✅ 可用' if TRADING_BUS_AVAILABLE else '❌ 不可用'}
- 桥梁: {'✅ 可用' if BRIDGE_AVAILABLE else '❌ 不可用'}
- 认知事件dataclass: {'✅ 可用' if COGNITION_EVENTS_AVAILABLE else '❌ 不可用'}

🎯 使用建议:
1. 现有的认知模块 → 继续使用 get_cognitive_bus() 和 publish_cognitive_event()
2. 新的交易相关模块 → 使用 get_trading_bus() 和 StrategySignalEvent
3. 不确定的模块 → 使用 publish_event() 和 subscribe_event() 自动选择
4. 需要跨总线通信 → 启用桥梁 get_bus_bridge().enable_bridge(True)
"""
