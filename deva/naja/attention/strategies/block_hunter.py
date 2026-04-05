"""
Block Rotation Hunter Strategy

Tracks block attention weight momentum to detect capital rotation between blocks
"""

import time
import numpy as np
from typing import Dict, List, Optional, Any
from collections import deque

from .base import AttentionStrategyBase, Signal


def _get_noise_detector():
    try:
        from deva.naja.attention.processing.block_noise_detector import get_block_noise_detector
        return get_block_noise_detector()
    except ImportError:
        return None


class BlockRotationHunter(AttentionStrategyBase):
    """
    Block Rotation Hunter Strategy

    Core Logic:
    1. Monitor block attention weight changes
    2. Flag "capital inflow" when block weight rises rapidly
    3. Flag "capital outflow" when block weight declines
    4. Capture rotation inflection points

    Only executes during active block attention periods
    """

    def __init__(
        self,
        momentum_threshold: float = 0.15,
        rotation_threshold: float = 0.3,
        min_block_attention: float = 0.4,
        history_window: int = 20,
        cooldown_period: float = 300.0
    ):
        super().__init__(
            strategy_id="block_rotation_hunter",
            name="Block Rotation Hunter",
            scope='block',
            min_global_attention=0.3,
            cooldown_period=cooldown_period
        )

        self.momentum_threshold = momentum_threshold
        self.rotation_threshold = rotation_threshold
        self.min_block_attention = min_block_attention
        self.history_window = history_window

        self.block_history: Dict[str, deque] = {}
        self.block_momentum: Dict[str, float] = {}
        self.block_signals: Dict[str, str] = {}

        self.current_hot_blocks: List[str] = []
        self.last_rotation_time: float = 0.0

    def _on_signal(self, signal: Signal):
        print(f"📊 [{signal.strategy_name}] {signal.signal_type.upper()} | "
              f"Block: {signal.symbol} | Confidence: {signal.confidence:.2f} | "
              f"Reason: {signal.reason}")

    def _update_block_history(self, block_weights: Dict[str, float]):
        current_time = self._get_market_time()

        for block_id, weight in block_weights.items():
            if block_id not in self.block_history:
                self.block_history[block_id] = deque(maxlen=self.history_window)

            self.block_history[block_id].append({
                'time': current_time,
                'weight': weight
            })

    def _calculate_block_momentum(self, block_id: str) -> float:
        if block_id not in self.block_history:
            return 0.0

        history = list(self.block_history[block_id])
        if len(history) < 5:
            return 0.0

        recent = np.mean([h['weight'] for h in history[-3:]])
        previous = np.mean([h['weight'] for h in history[:min(5, len(history))]])

        if previous == 0:
            return 0.0

        momentum = (recent - previous) / previous
        return momentum

    def _detect_rotation(self, block_weights: Dict[str, float]) -> List[Signal]:
        signals = []
        current_time = self._get_market_time()
        noise_detector = _get_noise_detector()

        for block_id, weight in block_weights.items():
            if noise_detector and noise_detector.is_block_noise(block_id):
                continue

            if weight < self.min_block_attention:
                continue

            momentum = self._calculate_block_momentum(block_id)
            self.block_momentum[block_id] = momentum

            if momentum > self.momentum_threshold:
                if self._is_rotation_target(block_id, block_weights):
                    if self.can_emit_signal(block_id):
                        signal = Signal(
                            strategy_name=self.name,
                            symbol=block_id,
                            signal_type='watch',
                            confidence=min(abs(momentum) * 2, 1.0),
                            score=momentum,
                            reason=f"Block rotation inflow, momentum: {momentum:.3f}, weight: {weight:.3f}",
                            timestamp=current_time,
                            metadata={
                                'momentum': momentum,
                                'weight': weight,
                                'rotation_type': 'inflow'
                            }
                        )
                        self.emit_signal(signal)
                        signals.append(signal)
                        self.block_signals[block_id] = 'watching_inflow'

            elif momentum < -self.momentum_threshold:
                if self.can_emit_signal(f"{block_id}_out"):
                    signal = Signal(
                        strategy_name=self.name,
                        symbol=block_id,
                        signal_type='watch',
                        confidence=min(abs(momentum) * 2, 1.0),
                        score=momentum,
                        reason=f"Block rotation outflow, momentum: {momentum:.3f}, weight: {weight:.3f}",
                        timestamp=current_time,
                        metadata={
                            'momentum': momentum,
                            'weight': weight,
                            'rotation_type': 'outflow'
                        }
                    )
                    self.emit_signal(signal)
                    signals.append(signal)
                    self.block_signals[block_id] = 'watching_outflow'

        return signals

    def _is_rotation_target(self, target_block: str, block_weights: Dict[str, float]) -> bool:
        outflow_blocks = [
            b for b, momentum in self.block_momentum.items()
            if momentum < -self.momentum_threshold * 0.5 and b != target_block
        ]

        return len(outflow_blocks) > 0

    def _identify_hot_blocks(self, block_weights: Dict[str, float]) -> List[str]:
        hot_blocks = []
        noise_detector = _get_noise_detector()

        for block_id, weight in block_weights.items():
            if noise_detector and noise_detector.is_block_noise(block_id):
                continue

            momentum = self.block_momentum.get(block_id, 0.0)

            if weight > self.min_block_attention and momentum > 0:
                hot_blocks.append({
                    'block': block_id,
                    'weight': weight,
                    'momentum': momentum,
                    'score': weight * (1 + momentum)
                })

        hot_blocks.sort(key=lambda x: x['score'], reverse=True)

        return [h['block'] for h in hot_blocks[:5]]

    def analyze(self, data, context: Dict[str, Any]) -> List[Signal]:
        signals = []
        current_time = self._get_market_time()

        block_weights = context.get('block_weights', {})

        if not block_weights:
            integration = self._get_attention_system()
            if integration and integration.attention_system:
                block_weights = integration.attention_system.block_attention.get_all_weights()

        if not block_weights:
            return signals

        self._update_block_history(block_weights)
        rotation_signals = self._detect_rotation(block_weights)
        signals.extend(rotation_signals)
        self.current_hot_blocks = self._identify_hot_blocks(block_weights)

        if rotation_signals:
            self.last_rotation_time = current_time

        return signals

    def get_block_analysis(self) -> Dict[str, Any]:
        return {
            'hot_blocks': self.current_hot_blocks,
            'block_momentum': self.block_momentum.copy(),
            'block_signals': self.block_signals.copy(),
            'last_rotation_time': self.last_rotation_time,
            'history_length': {b: len(h) for b, h in self.block_history.items()}
        }
