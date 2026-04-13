"""
事件总线持久化配置

在系统启动时调用，为关键交易事件配置 NB 持久化
"""

import logging
log = logging.getLogger(__name__)

# 关键交易事件类型（需要持久化）
PERSISTENT_EVENT_TYPES = [
    # 热点策略信号
    'StrategySignalEvent',
    
    # 交易决策
    'TradeDecisionEvent',
    
    # 热点计算
    'HotspotComputedEvent',
    'HotspotShiftEvent',
    
    # 市场快照（高频，可选持久化）
    # 'MarketSnapshotEvent',  # 频率太高，暂时不持久化
    
    # 文本事件（用于 NLP 分析）
    # 'TextFetchedEvent',      # 频率高，暂时不持久化
    # 'TextFocusedEvent',     # 频率高，暂时不持久化
]

# 认知事件类型（部分需要持久化）
PERSISTENT_COGNITIVE_EVENT_TYPES = [
    # 关键认知信号
    'BLOCK_NARRATIVE_UPDATE',
    'TIMING_NARRATIVE_UPDATE',
    'MARKET_NARRATIVE_UPDATE',
    'RESONANCE_SIGNAL',
    'RISK_SIGNAL',
    'MACRO_SIGNAL',
    
    # 叙事变化
    'NARRATIVE_BOOST',
    'NARRATIVE_DECAY',
    'TIMING_NARRATIVE_SHIFT',
    'MARKET_NARRATIVE_SHIFT',
    
    # 供应链
    'NARRATIVE_SUPPLY_LINK',
    'NARRATIVE_SUPPLY_BREAK',
    
    # 清仓信号
    'RESONANCE_BREAK',
    'RISK_CLEAR',
    'LIQUIDITY_DRAIN',
]

def configure_event_bus_persistence(bus):
    """
    为事件总线配置持久化
    
    Args:
        bus: StreamBackedEventBus 实例
    """
    log.info("⚙️ 配置事件总线持久化...")
    
    # 配置 dataclass 事件持久化
    for event_type in PERSISTENT_EVENT_TYPES:
        try:
            bus.configure_persistence(event_type, persistent=True)
        except Exception as e:
            log.warning(f"配置事件持久化失败 {event_type}: {e}")
    
    # 注：认知事件目前走单独的通道，没有集成到 StreamBackedEventBus 的 NB 持久化
    # 如有需要，可为 CognitiveEvent 类型也配置 NB 持久化
    
    log.info(f"✅ 已配置 {len(PERSISTENT_EVENT_TYPES)} 种事件类型的持久化")


def create_persistence_monitor(bus):
    """
    创建持久化监控器，定期打印统计
    
    Args:
        bus: StreamBackedEventBus 实例
    
    Returns:
        监控线程（可选启动）
    """
    import threading
    import time
    
    def monitor_thread():
        log.info("📊 持久化监控器启动")
        while True:
            try:
                stats = bus.get_stats()
                # 统计每种事件的发布和持久化数量
                publish_stats = {k:v for k,v in stats.items() if k.startswith('publish_')}
                persist_stats = {k:v for k,v in stats.items() if k.startswith('persist_')}
                
                log.info(f"📈 事件统计 - 发布: {sum(publish_stats.values())}, 持久化: {sum(persist_stats.values())}")
                
                # 如有差异，可能是配置或写入失败
                for event_type in PERSISTENT_EVENT_TYPES:
                    pub_key = f'publish_{event_type}'
                    per_key = f'persist_{event_type}'
                    if stats.get(pub_key, 0) > stats.get(per_key, 0):
                        log.warning(f"⚠️ {event_type} 持久化缺失: 发布{stats.get(pub_key,0)} vs 持久化{stats.get(per_key,0)}")
                
            except Exception as e:
                log.error(f"监控异常: {e}")
            
            time.sleep(60)  # 每分钟检查一次
    
    return threading.Thread(target=monitor_thread, daemon=True, name="PersistenceMonitor")