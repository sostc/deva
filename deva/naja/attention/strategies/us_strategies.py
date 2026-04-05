"""
US Market Attention Strategies

美股专用策略：复用 A 股策略逻辑，但使用美股注意力状态与数据过滤。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

try:
    import pandas as pd
except Exception:
    pd = None

from .global_sentinel import GlobalMarketSentinel
from .block_hunter import BlockRotationHunter
from .momentum_tracker import MomentumSurgeTracker
from .anomaly_sniper import AnomalyPatternSniper
from .smart_money_detector import SmartMoneyFlowDetector


class USAttentionMixin:
    """为美股策略提供 US 注意力上下文与过滤能力。"""

    def _get_us_state(self) -> Dict[str, Any]:
        try:
            from deva.naja.attention.integration import get_attention_integration
            integration = get_attention_integration()
            if integration and integration.attention_system:
                return integration.attention_system.get_us_attention_state()
        except Exception:
            pass
        return {
            'global_attention': 0.5,
            'activity': 0.5,
            'block_attention': {},
            'symbol_weights': {},
        }

    def get_global_attention(self) -> float:
        state = self._get_us_state()
        return state.get('global_attention', 0.5)

    def get_symbol_weight(self, symbol: str) -> float:
        state = self._get_us_state()
        return state.get('symbol_weights', {}).get(symbol, 0.0)

    def get_active_blocks(self, threshold: float = 0.3) -> List[str]:
        state = self._get_us_state()
        block_weights = state.get('block_attention', {})
        return [s for s, w in block_weights.items() if w >= threshold]

    def filter_by_attention(self, df: 'pd.DataFrame', min_weight: Optional[float] = None):
        if pd is None or df is None or df.empty:
            return df

        if 'market' in df.columns:
            market_mask = df['market'].astype(str).str.upper() == 'US'
            df = df[market_mask]
            if df.empty:
                return df

        min_weight = min_weight or getattr(self, 'min_symbol_weight', 0.0)
        state = self._get_us_state()
        symbol_weights = state.get('symbol_weights', {})
        if not symbol_weights:
            return df

        high_attention = [s for s, w in symbol_weights.items() if w >= min_weight]
        if not high_attention:
            return df

        code_column = 'code' if 'code' in df.columns else df.index.name
        if code_column == 'code':
            return df[df['code'].isin(high_attention)]
        return df[df.index.isin(high_attention)]

    def should_execute(
        self,
        global_attention: Optional[float] = None,
        activity: Optional[float] = None,
        market_timestamp: Optional[float] = None
    ) -> bool:
        """
        美股策略执行门槛：放宽活跃度阈值
        """
        current_time = market_timestamp if market_timestamp is not None else time.time()

        if global_attention is None or activity is None:
            state = self._get_us_state()
            if global_attention is None:
                global_attention = state.get('global_attention', 0.5)
            if activity is None:
                activity = state.get('activity', 0.5)

        # 美股数据稀疏时降低活跃度门槛
        if activity < 0.05:
            self.skip_count += 1
            return False

        if current_time - self.last_execution_time < self._get_dynamic_interval(global_attention):
            return False

        return True

    def process(self, data: 'pd.DataFrame', context: Optional[Dict[str, Any]] = None):
        if pd is None or data is None or data.empty:
            return []

        if 'market' in data.columns:
            market_mask = data['market'].astype(str).str.upper() == 'US'
            data = data[market_mask]
            if data.empty:
                return []
        else:
            if not context or str(context.get('market', '')).upper() != 'US':
                return []

        if context is None:
            state = self._get_us_state()
            now_ts = time.time()
            context = {
                'timestamp': now_ts,
                'global_attention': state.get('global_attention', 0.5),
                'activity': state.get('activity', 0.5),
                'block_weights': state.get('block_attention', {}),
                'symbol_weights': state.get('symbol_weights', {}),
                'market': 'US',
            }
        else:
            context = dict(context)
            context.setdefault('market', 'US')
            if 'global_attention' not in context or 'activity' not in context:
                state = self._get_us_state()
                context.setdefault('global_attention', state.get('global_attention', 0.5))
                context.setdefault('activity', state.get('activity', 0.5))
                context.setdefault('block_weights', state.get('block_attention', {}))
                context.setdefault('symbol_weights', state.get('symbol_weights', {}))
            context.setdefault('timestamp', time.time())

        return super().process(data, context)


class USGlobalMarketSentinel(USAttentionMixin, GlobalMarketSentinel):
    """美股全局市场监控策略"""

    def __init__(self):
        super().__init__(
            strategy_id="us_global_sentinel",
            volatility_threshold=2.5,
            panic_threshold=4.0,
            history_window=20,
        )
        self.name = "US Global Market Sentinel"
        self.market_scope = "US"


class USBlockRotationHunter(USAttentionMixin, BlockRotationHunter):
    """US Block Rotation Hunter"""

    def __init__(self):
        super().__init__()
        self.strategy_id = "us_block_rotation_hunter"
        self.name = "US Block Rotation Hunter"
        self.min_global_attention = 0.25
        self.market_scope = "US"


class USMomentumSurgeTracker(USAttentionMixin, MomentumSurgeTracker):
    """美股动量突破追踪"""

    def __init__(self):
        super().__init__(
            price_threshold=0.008,
            volume_threshold=1.3,
            combined_threshold=0.25,
            min_symbol_weight=0.0002,
            cooldown_period=45.0,
        )
        self.strategy_id = "us_momentum_surge_tracker"
        self.name = "US Momentum Surge Tracker"
        self.min_global_attention = 0.3
        self.market_scope = "US"


class USAnomalyPatternSniper(USAttentionMixin, AnomalyPatternSniper):
    """美股异常模式狙击"""

    def __init__(self):
        super().__init__(
            min_symbol_weight=0.00025,
            cooldown_period=90.0,
        )
        self.strategy_id = "us_anomaly_pattern_sniper"
        self.name = "US Anomaly Pattern Sniper"
        self.min_global_attention = 0.45
        self.market_scope = "US"


class USSmartMoneyFlowDetector(USAttentionMixin, SmartMoneyFlowDetector):
    """美股聪明资金流向检测"""

    def __init__(self):
        super().__init__(
            large_order_threshold=500000,
            smart_money_imbalance_threshold=0.55,
            accumulation_threshold=0.65,
            distribution_threshold=-0.65,
            min_symbol_weight=0.0003,
            cooldown_period=180.0,
        )
        self.strategy_id = "us_smart_money_flow_detector"
        self.name = "US Smart Money Flow Detector"
        self.min_global_attention = 0.28
        self.market_scope = "US"
