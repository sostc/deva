"""
Liquidity Rescue Strategies - 流动性救市策略

检测流动性危机并发出救市信号
"""

import logging
from typing import Dict

from .base import AttentionStrategyBase, HotspotSignal

log = logging.getLogger(__name__)


class LiquidityCrisisTracker(AttentionStrategyBase):
    """
    流动性危机追踪

    监控市场活跃度，检测流动性危机
    """

    def __init__(
        self,
        market: str = 'US',
        crisis_threshold: float = 0.2
    ):
        super().__init__(
            strategy_id='liquidity_crisis_tracker',
            name='LiquidityCrisisTracker',
            market=market,
            min_global_hotspot=0.0,
            cooldown_period=300.0
        )

        self.crisis_threshold = crisis_threshold
        self.crisis_history = []

    def _process_hotspot_event(self, event):
        """处理热点事件，检测流动性危机"""
        global_hotspot = event.global_hotspot
        activity = event.activity

        if global_hotspot < self.crisis_threshold:
            signal = HotspotSignal(
                strategy_id=self.strategy_id,
                strategy_name=self.name,
                symbol='MARKET',
                signal_type='sell',
                confidence=1.0 - global_hotspot,
                score=1.0 - global_hotspot,
                reason=f'流动性危机: hotspot={global_hotspot:.3f}, activity={activity:.3f}',
                timestamp=event.timestamp,
                market=self.market,
                metadata={
                    'global_hotspot': global_hotspot,
                    'activity': activity
                }
            )
            self._emit_signal(signal)

            self.crisis_history.append({
                'timestamp': event.timestamp,
                'hotspot': global_hotspot
            })


class PanicPeakDetector(AttentionStrategyBase):
    """
    恐慌峰值检测

    检测市场恐慌峰值
    """

    def __init__(self, market: str = 'US'):
        super().__init__(
            strategy_id='panic_peak_detector',
            name='PanicPeakDetector',
            market=market,
            min_global_hotspot=0.0,
            cooldown_period=600.0
        )

        self.peak_history = []

    def _process_hotspot_event(self, event):
        """处理热点事件，检测恐慌峰值"""
        global_hotspot = event.global_hotspot

        if global_hotspot >= 0.8:
            self.peak_history.append({
                'timestamp': event.timestamp,
                'hotspot': global_hotspot
            })

            signal = HotspotSignal(
                strategy_id=self.strategy_id,
                strategy_name=self.name,
                symbol='MARKET',
                signal_type='watch',
                confidence=0.8,
                score=global_hotspot,
                reason=f'恐慌峰值: hotspot={global_hotspot:.3f}',
                timestamp=event.timestamp,
                market=self.market
            )
            self._emit_signal(signal)


class RecoveryConfirmationMonitor(AttentionStrategyBase):
    """
    恢复确认监控

    监控市场从危机中恢复
    """

    def __init__(self, market: str = 'US'):
        super().__init__(
            strategy_id='recovery_confirmation_monitor',
            name='RecoveryConfirmationMonitor',
            market=market,
            min_global_hotspot=0.0,
            cooldown_period=300.0
        )

        self.in_crisis = False
        self.recovery_count = 0

    def _process_hotspot_event(self, event):
        """处理热点事件，确认恢复"""
        global_hotspot = event.global_hotspot

        if global_hotspot < 0.3 and not self.in_crisis:
            self.in_crisis = True
            self.recovery_count = 0

        if self.in_crisis:
            if global_hotspot > 0.5:
                self.recovery_count += 1

            if self.recovery_count >= 3:
                signal = HotspotSignal(
                    strategy_id=self.strategy_id,
                    strategy_name=self.name,
                    symbol='MARKET',
                    signal_type='buy',
                    confidence=0.7,
                    score=global_hotspot,
                    reason=f'市场恢复确认: hotspot={global_hotspot:.3f}, count={self.recovery_count}',
                    timestamp=event.timestamp,
                    market=self.market
                )
                self._emit_signal(signal)
                self.in_crisis = False
