"""
GlobalMarketSentinel - 全局市场风险监控

监控整体市场风险状态
"""

import logging
from typing import Dict

from .base import AttentionStrategyBase, HotspotSignal

log = logging.getLogger(__name__)


class GlobalMarketSentinel(AttentionStrategyBase):
    """
    全局市场风险监控策略

    监控整体市场热点，判断市场状态
    输出: Normal / Caution / Warning / Danger / Panic
    """

    def __init__(self, market: str = 'US'):
        super().__init__(
            strategy_id='global_market_sentinel',
            name='GlobalMarketSentinel',
            market=market,
            min_global_hotspot=0.0,
            cooldown_period=0.0
        )

        self.risk_level = 'Normal'
        self.risk_history = []

    def _process_hotspot_event(self, event):
        """处理热点事件，判断市场风险"""
        global_hotspot = event.global_hotspot
        activity = event.activity

        if global_hotspot >= 0.8:
            self.risk_level = 'Panic'
        elif global_hotspot >= 0.65:
            self.risk_level = 'Danger'
        elif global_hotspot >= 0.5:
            self.risk_level = 'Warning'
        elif global_hotspot >= 0.35:
            self.risk_level = 'Caution'
        else:
            self.risk_level = 'Normal'

        self.risk_history.append({
            'timestamp': event.timestamp,
            'global_hotspot': global_hotspot,
            'activity': activity,
            'risk_level': self.risk_level
        })

        if len(self.risk_history) > 100:
            self.risk_history.pop(0)

        log.debug(f"[GlobalMarketSentinel] risk={self.risk_level}, hotspot={global_hotspot:.3f}")

    def get_risk_level(self) -> str:
        """获取当前风险等级"""
        return self.risk_level

    def get_risk_summary(self) -> Dict:
        """获取风险摘要"""
        return {
            'risk_level': self.risk_level,
            'history_count': len(self.risk_history),
            'recent_hotspot': self.risk_history[-1]['global_hotspot'] if self.risk_history else 0.0
        }
