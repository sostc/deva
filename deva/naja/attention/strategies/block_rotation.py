"""
BlockRotationHunter - 题材轮动捕捉

捕捉资金在题材间的轮动
"""

import logging
from typing import Dict, List

from .base import AttentionStrategyBase, HotspotSignal

log = logging.getLogger(__name__)


class BlockRotationHunter(AttentionStrategyBase):
    """
    题材轮动捕捉策略

    监控题材热点变化，捕捉轮动信号
    """

    def __init__(self, market: str = 'US', min_hotspot_change: float = 0.2):
        super().__init__(
            strategy_id='block_rotation_hunter',
            name='BlockRotationHunter',
            market=market,
            min_global_hotspot=0.3,
            cooldown_period=300.0
        )

        self.min_hotspot_change = min_hotspot_change
        self.last_block_hotspot: Dict[str, float] = {}
        self.rotation_signals: List[Dict] = []

    def _process_hotspot_event(self, event):
        """处理热点事件，检测轮动"""
        current_blocks = event.block_hotspot

        if not self.last_block_hotspot:
            self.last_block_hotspot = current_blocks.copy()
            return

        rotations = self._detect_rotation(self.last_block_hotspot, current_blocks)

        for rotation in rotations:
            self.rotation_signals.append(rotation)
            log.info(f"[BlockRotationHunter] 轮动: {rotation}")

        self.last_block_hotspot = current_blocks.copy()

        if len(self.rotation_signals) > 50:
            self.rotation_signals = self.rotation_signals[-50:]

    def _detect_rotation(self, old: Dict[str, float], new: Dict[str, float]) -> List[Dict]:
        """检测题材轮动"""
        rotations = []
        all_blocks = set(old.keys()) | set(new.keys())

        for block in all_blocks:
            old_val = old.get(block, 0.0)
            new_val = new.get(block, 0.0)
            change = new_val - old_val

            if abs(change) >= self.min_hotspot_change:
                rotations.append({
                    'block': block,
                    'old_hotspot': old_val,
                    'new_hotspot': new_val,
                    'change': change,
                    'direction': 'inflow' if change > 0 else 'outflow'
                })

        return rotations

    def get_rotation_signals(self) -> List[Dict]:
        """获取轮动信号"""
        return self.rotation_signals[-10:]
