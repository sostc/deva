"""
Hotspot Mixin - 让 DataSource 具备热点感知能力

使用方法:
    class MyDataSource(DataSourceEntry, HotspotMixin):
        def fetch_data(self):
            all_symbols = self.get_all_symbols()

            symbols_to_fetch = self.get_symbols_by_hotspot(all_symbols)

            data = self.fetch_symbols(symbols_to_fetch)

            self.emit(data)
"""

import time
from typing import List, Set, Optional
from abc import ABC


class HotspotMixin(ABC):
    """
    热点系统混入类

    为 DataSource 添加热点调度能力
    """

    def __init__(self):
        self._hotspot_integration = None
        self._hotspot_enabled = True
        self._last_tier_update = 0
        self._tier_update_interval = 10

        self._high_symbols: Set[str] = set()
        self._medium_symbols: Set[str] = set()
        self._low_symbols: Set[str] = set()

    def _get_market_hotspot_integration(self):
        """懒加载热点集成"""
        if self._hotspot_integration is None:
            try:
                from ..market_hotspot.integration.market_hotspot_integration import get_market_hotspot_integration
                self._hotspot_integration = get_market_hotspot_integration()
            except Exception:
                self._hotspot_enabled = False
        return self._hotspot_integration

    def get_symbols_by_hotspot(
        self,
        all_symbols: List[str],
        min_weight: float = 0.0
    ) -> List[str]:
        """
        根据热点系统筛选股票

        Args:
            all_symbols: 全量股票列表
            min_weight: 最小权重阈值

        Returns:
            应该获取的股票列表
        """
        integration = self._get_market_hotspot_integration()

        if not self._hotspot_enabled or integration is None:
            return all_symbols

        if integration.hotspot_system is None:
            return all_symbols

        self._update_symbol_tiers(integration)

        return self._select_by_frequency()

    def _update_symbol_tiers(self, integration):
        """更新股票分层"""
        current_time = time.time()

        if current_time - self._last_tier_update < self._tier_update_interval:
            return

        control = integration.get_datasource_control()

        self._high_symbols = set(control.get('high_freq_symbols', []))
        self._medium_symbols = set(control.get('medium_freq_symbols', []))
        self._low_symbols = set(control.get('low_freq_symbols', []))

        self._last_tier_update = current_time

    def _select_by_frequency(self) -> List[str]:
        """
        根据频率选择股票

        高频：每次返回
        中频：每10秒返回
        低频：每60秒返回
        """
        result = list(self._high_symbols)

        current_second = int(time.time()) % 60

        if current_second % 10 == 0:
            result.extend(self._medium_symbols)

        if current_second == 0:
            result.extend(self._low_symbols)

        return result

    def should_fetch_symbol(self, symbol: str) -> bool:
        """判断是否应该获取某只股票"""
        integration = self._get_market_hotspot_integration()

        if not self._hotspot_enabled or integration is None:
            return True

        return integration.should_fetch_symbol(symbol)

    def get_hotspot_report(self) -> dict:
        """获取热点系统报告"""
        integration = self._get_market_hotspot_integration()

        if not self._hotspot_enabled or integration is None:
            return {'status': 'disabled'}

        return integration.get_hotspot_report()

    def get_high_hotspot_symbols(self, threshold: float = 2.0) -> List[str]:
        """获取高热点股票"""
        integration = self._get_market_hotspot_integration()

        if not self._hotspot_enabled or integration is None:
            return []

        return integration.get_high_hotspot_symbols(threshold)

    def enable_hotspot(self):
        """启用热点调度"""
        self._hotspot_enabled = True

    def disable_hotspot(self):
        """禁用热点调度"""
        self._hotspot_enabled = False