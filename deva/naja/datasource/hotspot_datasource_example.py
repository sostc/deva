"""
HotspotAware DataSource 使用示例

展示如何在现有 DataSource 中集成热点调度
"""

import pandas as pd
import time
from typing import List

from . import DataSourceEntry
from .hotspot_mixin import HotspotMixin


class HotspotAwareDataSource(DataSourceEntry, HotspotMixin):
    """
    具备热点感知能力的数据源示例

    特点：
    1. 全量数据只获取一次（低频）
    2. 根据热点系统动态筛选高关注股票
    3. 高关注股票高频获取，其他低频获取
    """

    def __init__(self, name: str = "hotspot_aware_ds"):
        DataSourceEntry.__init__(self, name)
        HotspotMixin.__init__(self)

        self._all_symbols = []
        self._base_interval = 60

    def initialize(self, symbols: List[str]):
        """初始化股票列表"""
        self._all_symbols = symbols

    def fetch_data(self):
        """
        获取数据 - 使用热点调度

        流程：
        1. 获取热点系统推荐的股票列表
        2. 根据频率分层获取
        3. 发送数据
        """
        while self._running:
            try:
                symbols_to_fetch = self.get_symbols_by_hotspot(self._all_symbols)

                if not symbols_to_fetch:
                    time.sleep(1)
                    continue

                data = self._fetch_symbols_data(symbols_to_fetch)

                if data is not None and len(data) > 0:
                    self._emit_data(data)

                    self._log_info(f"获取 {len(symbols_to_fetch)} 只股票数据，"
                                  f"高关注: {len(self._high_symbols)}, "
                                  f"中关注: {len(self._medium_symbols)}, "
                                  f"低关注: {len(self._low_symbols)}")

                interval = self._calculate_interval()
                time.sleep(interval)

            except Exception as e:
                self._log_error(f"获取数据失败: {e}")
                time.sleep(5)

    def _fetch_symbols_data(self, symbols: List[str]) -> pd.DataFrame:
        """获取指定股票的数据（模拟）"""
        data = []
        for symbol in symbols:
            data.append({
                'code': symbol,
                'now': 100.0 + hash(symbol) % 50,
                'change_pct': (hash(symbol) % 10) - 5,
                'volume': 1000000 + hash(symbol) % 5000000,
                'timestamp': time.time()
            })

        return pd.DataFrame(data)

    def _calculate_interval(self) -> float:
        """
        根据热点状态动态计算间隔

        如果高关注股票多，缩短间隔
        如果市场平静，延长间隔
        """
        report = self.get_hotspot_report()
        global_hotspot = report.get('global_hotspot', 0)

        if global_hotspot > 0.7:
            return 1.0
        elif global_hotspot > 0.4:
            return 5.0
        else:
            return self._base_interval

    def _log_info(self, msg: str):
        """记录信息日志"""
        print(f"[INFO] {self.name}: {msg}")

    def _log_error(self, msg: str):
        """记录错误日志"""
        print(f"[ERROR] {self.name}: {msg}")


class SimpleHotspotDataSource(DataSourceEntry):
    """
    简单版本的热点感知数据源

    不需要继承 HotspotMixin，直接调用集成模块
    """

    def __init__(self, name: str = "simple_hotspot_ds"):
        super().__init__(name)
        self._use_hotspot = True

    def fetch_data(self):
        """获取数据"""
        from ..market_hotspot.integration.market_hotspot_integration import get_market_hotspot_integration

        while self._running:
            try:
                integration = get_market_hotspot_integration()

                if self._use_hotspot and integration.hotspot_system is not None:
                    symbols = integration.get_high_hotspot_symbols(threshold=1.5)

                    if symbols:
                        data = self._fetch_data_for_symbols(symbols)
                        self._emit_data(data)

                        print(f"[SimpleDS] 获取 {len(symbols)} 只高热点股票")
                else:
                    data = self._fetch_default_data()
                    self._emit_data(data)

                if integration.hotspot_system is not None:
                    control = integration.get_datasource_control()
                    interval = control['intervals']['high']
                else:
                    interval = 60

                time.sleep(interval)

            except Exception as e:
                print(f"[SimpleDS] 错误: {e}")
                time.sleep(5)

    def _fetch_data_for_symbols(self, symbols: List[str]) -> pd.DataFrame:
        """获取指定股票数据"""
        return pd.DataFrame()

    def _fetch_default_data(self) -> pd.DataFrame:
        """获取默认数据"""
        return pd.DataFrame()


def example_usage():
    """使用示例"""

    print("=" * 60)
    print("方式1：使用 HotspotMixin")
    print("=" * 60)

    ds1 = HotspotAwareDataSource("my_ds")
    ds1.initialize(['000001', '000002', '000003', '000004', '000005'])

    ds1.enable_hotspot()

    report = ds1.get_hotspot_report()
    print(f"热点报告: {report}")

    print("\n" + "=" * 60)
    print("方式2：直接调用集成模块")
    print("=" * 60)

    from ..market_hotspot.integration.market_hotspot_integration import get_market_hotspot_integration

    integration = get_market_hotspot_integration()

    high_hotspot = integration.get_high_hotspot_symbols(threshold=2.0)
    print(f"高热点股票: {high_hotspot}")

    active_blocks = integration.get_active_blocks(threshold=0.5)
    print(f"活跃题材: {active_blocks}")

    control = integration.get_datasource_control()
    print(f"高频股票数: {len(control['high_freq_symbols'])}")
    print(f"中频股票数: {len(control['medium_freq_symbols'])}")
    print(f"低频股票数: {len(control['low_freq_symbols'])}")


if __name__ == "__main__":
    example_usage()