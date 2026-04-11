"""
热点感知的策略基类和工具

为现有策略提供与热点系统对接的能力
"""

import time
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod

try:
    import pandas as pd
except Exception:
    pd = None


class HotspotAwareMixin:
    """
    热点感知混入类

    为策略添加热点查询能力
    """

    def __init__(self):
        self._hotspot_integration = None
        self._use_hotspot = True
        self._last_hotspot_check = 0
        self._hotspot_cache_ttl = 5.0
        self._cached_hotspot_state = {}

    def _get_market_hotspot_integration(self):
        """懒加载热点集成"""
        if self._hotspot_integration is None:
            try:
                from ..market_hotspot.integration.market_hotspot_integration import get_market_hotspot_integration
                self._hotspot_integration = get_market_hotspot_integration()
            except Exception:
                self._use_hotspot = False
        return self._hotspot_integration

    def should_process_by_hotspot(self, symbol: str) -> bool:
        """
        根据热点系统判断是否处理该股票

        Args:
            symbol: 股票代码

        Returns:
            是否应该处理
        """
        if not self._use_hotspot:
            return True

        integration = self._get_market_hotspot_integration()
        if integration is None or integration.hotspot_system is None:
            return True

        return integration.should_fetch_symbol(symbol)

    def get_symbol_hotspot_weight(self, symbol: str) -> float:
        """
        获取股票的热点权重

        Args:
            symbol: 股票代码

        Returns:
            权重值 (0.0 - 5.0)
        """
        if not self._use_hotspot:
            return 1.0

        integration = self._get_market_hotspot_integration()
        if integration is None or integration.hotspot_system is None:
            return 1.0

        return integration.hotspot_system.weight_pool.get_symbol_weight(symbol)

    def get_global_hotspot(self) -> float:
        """获取全局热点分数"""
        if not self._use_hotspot:
            return 0.5

        integration = self._get_market_hotspot_integration()
        if integration is None or integration.hotspot_system is None:
            return 0.5

        current_time = time.time()
        if current_time - self._last_hotspot_check < self._hotspot_cache_ttl:
            return self._cached_hotspot_state.get('global', 0.5)

        report = integration.get_hotspot_report()
        global_hotspot = report.get('global_hotspot', 0.5)

        self._cached_hotspot_state['global'] = global_hotspot
        self._last_hotspot_check = current_time

        return global_hotspot

    def get_block_hotspot_weight(self, block_id: str) -> float:
        """获取题材热点分数"""
        if not self._use_hotspot:
            return 0.5

        integration = self._get_market_hotspot_integration()
        if integration is None or integration.hotspot_system is None:
            return 0.5

        return integration.hotspot_system.block_hotspot.get_block_hotspot(block_id)

    def filter_by_hotspot(self, df: pd.DataFrame,
                           min_weight: float = 1.0,
                           code_column: str = 'code') -> pd.DataFrame:
        """
        根据热点权重筛选DataFrame

        Args:
            df: 输入数据
            min_weight: 最小权重阈值
            code_column: 股票代码列名

        Returns:
            筛选后的DataFrame
        """
        if not self._use_hotspot or df is None or df.empty:
            return df

        integration = self._get_market_hotspot_integration()
        if integration is None or integration.hotspot_system is None:
            return df

        high_hotspot = integration.get_high_hotspot_symbols(threshold=min_weight)

        if not high_hotspot:
            return df

        return df[df[code_column].isin(high_hotspot)]

    def adjust_params_by_hotspot(self,
                                   base_threshold: float,
                                   base_position: float) -> tuple:
        """
        根据全局热点调整策略参数

        Args:
            base_threshold: 基础阈值
            base_position: 基础仓位

        Returns:
            (adjusted_threshold, adjusted_position)
        """
        global_hotspot = self.get_global_hotspot()

        threshold_factor = 1.0 - (global_hotspot - 0.5) * 0.4
        position_factor = 0.5 + global_hotspot * 0.5

        adjusted_threshold = base_threshold * threshold_factor
        adjusted_position = base_position * position_factor

        return adjusted_threshold, adjusted_position

    def get_active_blocks(self, threshold: float = 0.3) -> List[str]:
        """获取活跃题材列表"""
        if not self._use_hotspot:
            return []

        integration = self._get_market_hotspot_integration()
        if integration is None:
            return []

        return integration.get_active_blocks(threshold)

    def enable_hotspot(self):
        """启用热点过滤"""
        self._use_hotspot = True

    def disable_hotspot(self):
        """禁用热点过滤"""
        self._use_hotspot = False


class HotspotAwareStrategy:
    """
    热点感知策略基类

    继承此类可以快速为策略添加热点感知能力
    """

    def __init__(self):
        self.hotspot = HotspotAwareMixin()

    def pre_process(self, data: Any) -> Any:
        """
        预处理数据，应用热点过滤

        Args:
            data: 输入数据

        Returns:
            过滤后的数据
        """
        if pd is not None and isinstance(data, pd.DataFrame):
            return self.hotspot.filter_by_hotspot(data)
        return data

    def should_process_symbol(self, symbol: str) -> bool:
        """判断是否应该处理某只股票"""
        return self.hotspot.should_process_by_hotspot(symbol)

    def get_adjusted_params(self, base_threshold: float, base_position: float) -> tuple:
        """获取根据热点调整后的参数"""
        return self.hotspot.adjust_params_by_hotspot(base_threshold, base_position)


def create_hotspot_wrapper(strategy_class):
    """
    为现有策略类创建热点感知包装器

    用法:
        @create_hotspot_wrapper
        class MyStrategy:
            def on_data(self, data):
                ...
    """
    class HotspotWrappedStrategy(strategy_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._hotspot_mixin = HotspotAwareMixin()

        def on_data(self, data):
            if pd is not None and isinstance(data, pd.DataFrame):
                data = self._hotspot_mixin.filter_by_hotspot(data)
                if data is None or data.empty:
                    return

            super().on_data(data)

    return HotspotWrappedStrategy


class RiverTickAnomalyHSTWithHotspot:
    """
    带热点感知的 RiverTickAnomalyHST 策略
    """

    def __init__(self, base_strategy, use_hotspot: bool = True):
        self.base_strategy = base_strategy
        self.hotspot = HotspotAwareMixin()
        if not use_hotspot:
            self.hotspot.disable_hotspot()

    def on_data(self, data: Any) -> None:
        """处理数据"""
        if pd is not None and isinstance(data, pd.DataFrame):
            filtered_df = self.hotspot.filter_by_hotspot(data, min_weight=1.5)
            if filtered_df is None or filtered_df.empty:
                return
            data = filtered_df

        self.base_strategy.on_data(data)

    def get_signal(self) -> Optional[Dict]:
        """获取信号"""
        signal = self.base_strategy.get_signal()

        if signal is None:
            return None

        global_hotspot = self.hotspot.get_global_hotspot()
        if 'score' in signal:
            signal['score'] *= (0.5 + global_hotspot * 0.5)

        return signal


class BlockStockSelectorWithHotspot:
    """
    带热点感知的 BlockStockSelector 策略
    """

    def __init__(self, base_selector, use_hotspot: bool = True):
        self.base_selector = base_selector
        self.hotspot = HotspotAwareMixin()
        if not use_hotspot:
            self.hotspot.disable_hotspot()

    def on_data(self, data: Any) -> None:
        """处理数据"""
        active_blocks = self.hotspot.get_active_blocks(threshold=0.4)

        if active_blocks and pd is not None and isinstance(data, pd.DataFrame):
            pass

        self.base_selector.on_data(data)

    def get_signal(self) -> Optional[Dict]:
        """获取信号"""
        signal = self.base_selector.get_signal()

        if signal is None:
            return None

        if 'code' in signal:
            weight = self.hotspot.get_symbol_hotspot_weight(signal['code'])
            if weight < 1.0 and 'score' in signal:
                signal['score'] *= 0.5

        return signal