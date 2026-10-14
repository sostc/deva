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

    # 场景3：需要桥梁通信（认知 ↔ 交易）
    # ❗默认关闭，且**不要在业务代码里手动 enable**：
    #   由容器装配期读环境开关 `NAJA_BUS_BRIDGE=1` 统一启用
    #   （AppContainer 步骤 9b → events.bus_bridge.enable_bridge_from_env）。
    #   手动 enable_bridge(True) 会绕过装配期日志与守卫，造成「又一处开了没人知道」。
    #   背景与四层障碍见 events/bus_bridge.py 模块 docstring。

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
    TradeOutcomeEvent,
    SignalDirection,
    DecisionResult,
)
from .router import resolve_event_bus_type

# 认知事件 dataclass（可选）
#
# ❗这里的名单必须与 `cognition_events.py` 的**实际定义逐名对齐**。
# 历史事故（2026-10-15 审计）：清单里写了三个该模块并不存在的名字
# （`GlobalMarketEvent` / `create_risk_alert` / `EVENT_TYPE_MAP`）。
# `from X import (a, b, c)` 编译成逐名 IMPORT_FROM/STORE_NAME，
# **在第一个缺失名处抛 ImportError**，于是：
#   - 缺失名**之前**的名字侥幸已绑定（NarrativeUpdateEvent … RiskAlertEvent）；
#   - 缺失名**之后**的名字全部没有绑定
#     （PortfolioSignalEvent / CognitionResetEvent / create_narrative_update …）；
#   - `COGNITION_EVENTS_AVAILABLE` 变 False。
# 而所有消费方写的都是 `except ImportError: pass` → 整件事完全无声，
# 表现为「认知 dataclass 事件家族半个不存在」。现按实际定义列名，
# 并把失败从静默改成告警。
try:
    from .cognition_events import (
        # 所有认知事件 dataclass
        NarrativeUpdateEvent,
        TimingNarrativeShiftEvent,
        BlockNarrativeUpdateEvent,
        ResonanceDetectedEvent,
        SupplyChainRiskEvent,
        PortfolioSignalEvent,
        RiskAlertEvent,
        CognitionResetEvent,
        # 快捷创建函数
        create_narrative_update,
        create_timing_shift,
        create_resonance_detected,
        # 映射
        EVENT_TYPE_MAPPING,
    )
    # 兼容旧名：`__all__` 与历史引用用的是 EVENT_TYPE_MAP
    EVENT_TYPE_MAP = EVENT_TYPE_MAPPING
    COGNITION_EVENTS_AVAILABLE = True
except ImportError as _cog_evt_err:  # pragma: no cover - 仅在定义缺失时触发
    COGNITION_EVENTS_AVAILABLE = False
    log.warning(
        "[events] 认知事件 dataclass 导入失败，相关事件类型将不可用（"
        "请核对 events/__init__.py 的导入名单与 cognition_events.py 的实际定义）: %s",
        _cog_evt_err,
    )

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
        if TRADING_BUS_AVAILABLE and event_type in ['StrategySignalEvent', 'TradeDecisionEvent', 'TradeOutcomeEvent']:
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
    "TradeOutcomeEvent",
    "SignalDirection",
    "DecisionResult",
]

# 有条件导出的认知事件 dataclass
if COGNITION_EVENTS_AVAILABLE:
    __all__.extend([
        "NarrativeUpdateEvent",
        "TimingNarrativeShiftEvent",
        "BlockNarrativeUpdateEvent",
        "ResonanceDetectedEvent",
        "SupplyChainRiskEvent",
        "RiskAlertEvent",
        "PortfolioSignalEvent",
        "CognitionResetEvent",
        "create_narrative_update",
        "create_timing_shift",
        "create_resonance_detected",
        "EVENT_TYPE_MAP",
        "EVENT_TYPE_MAPPING",
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
