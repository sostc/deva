"""
AttentionAware DataSource 使用示例

展示如何在现有 DataSource 中集成注意力调度
"""

import pandas as pd
import time
from typing import List

# 假设这是你的现有 DataSource
from . import DataSourceEntry
from .attention_mixin import AttentionMixin


class AttentionAwareDataSource(DataSourceEntry, AttentionMixin):
    """
    具备注意力感知能力的数据源示例
    
    特点：
    1. 全量数据只获取一次（低频）
    2. 根据注意力系统动态筛选高关注股票
    3. 高关注股票高频获取，其他低频获取
    """
    
    def __init__(self, name: str = "attention_aware_ds"):
        DataSourceEntry.__init__(self, name)
        AttentionMixin.__init__(self)
        
        self._all_symbols = []  # 全量股票列表
        self._base_interval = 60  # 基础间隔60秒
    
    def initialize(self, symbols: List[str]):
        """初始化股票列表"""
        self._all_symbols = symbols
    
    def fetch_data(self):
        """
        获取数据 - 使用注意力调度
        
        流程：
        1. 获取注意力系统推荐的股票列表
        2. 根据频率分层获取
        3. 发送数据
        """
        while self._running:
            try:
                # ========== 关键：使用注意力系统筛选 ==========
                symbols_to_fetch = self.get_symbols_by_attention(self._all_symbols)
                
                if not symbols_to_fetch:
                    # 如果没有股票需要获取，等待一下
                    time.sleep(1)
                    continue
                
                # 获取这些股票的数据
                data = self._fetch_symbols_data(symbols_to_fetch)
                
                if data is not None and len(data) > 0:
                    # 发送到流（注意力系统会自动拦截计算）
                    self._emit_data(data)
                    
                    # 记录日志
                    self._log_info(f"获取 {len(symbols_to_fetch)} 只股票数据，"
                                  f"高关注: {len(self._high_symbols)}, "
                                  f"中关注: {len(self._medium_symbols)}, "
                                  f"低关注: {len(self._low_symbols)}")
                
                # 动态调整间隔
                interval = self._calculate_interval()
                time.sleep(interval)
                
            except Exception as e:
                self._log_error(f"获取数据失败: {e}")
                time.sleep(5)
    
    def _fetch_symbols_data(self, symbols: List[str]) -> pd.DataFrame:
        """获取指定股票的数据（模拟）"""
        # 这里替换为实际的数据获取逻辑
        # 例如：调用API、查询数据库等
        
        data = []
        for symbol in symbols:
            # 模拟数据
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
        根据注意力状态动态计算间隔
        
        如果高关注股票多，缩短间隔
        如果市场平静，延长间隔
        """
        report = self.get_attention_report()
        global_attention = report.get('global_attention', 0)
        
        # 注意力高 -> 间隔短（更频繁）
        # 注意力低 -> 间隔长（节省资源）
        if global_attention > 0.7:
            return 1.0  # 1秒
        elif global_attention > 0.4:
            return 5.0  # 5秒
        else:
            return self._base_interval  # 60秒
    
    def _log_info(self, msg: str):
        """记录信息日志"""
        print(f"[INFO] {self.name}: {msg}")
    
    def _log_error(self, msg: str):
        """记录错误日志"""
        print(f"[ERROR] {self.name}: {msg}")


class SimpleAttentionDataSource(DataSourceEntry):
    """
    简单版本的注意力感知数据源
    
    不需要继承 AttentionMixin，直接调用集成模块
    """
    
    def __init__(self, name: str = "simple_attention_ds"):
        super().__init__(name)
        self._use_attention = True
    
    def fetch_data(self):
        """获取数据"""
        from ..attention.integration import get_attention_integration
        
        while self._running:
            try:
                integration = get_attention_integration()
                
                if self._use_attention and integration.attention_system is not None:
                    # 获取高注意力股票
                    symbols = integration.get_high_attention_symbols(threshold=1.5)
                    
                    if symbols:
                        # 只获取这些股票
                        data = self._fetch_data_for_symbols(symbols)
                        self._emit_data(data)
                        
                        print(f"[SimpleDS] 获取 {len(symbols)} 只高注意力股票")
                else:
                    # 注意力系统未启用，获取默认股票
                    data = self._fetch_default_data()
                    self._emit_data(data)
                
                # 根据频率决定间隔
                if integration.attention_system is not None:
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
        # 实际实现...
        return pd.DataFrame()
    
    def _fetch_default_data(self) -> pd.DataFrame:
        """获取默认数据"""
        # 实际实现...
        return pd.DataFrame()


# ========== 使用示例 ==========

def example_usage():
    """使用示例"""
    
    # 方式1：使用 AttentionMixin
    print("=" * 60)
    print("方式1：使用 AttentionMixin")
    print("=" * 60)
    
    ds1 = AttentionAwareDataSource("my_ds")
    ds1.initialize(['000001', '000002', '000003', '000004', '000005'])
    
    # 启用/禁用注意力调度
    ds1.enable_attention()
    # ds1.disable_attention()
    
    # 获取注意力报告
    report = ds1.get_attention_report()
    print(f"注意力报告: {report}")
    
    # 方式2：直接调用集成模块
    print("\n" + "=" * 60)
    print("方式2：直接调用集成模块")
    print("=" * 60)

    from ..attention.integration import get_attention_integration
    
    integration = get_attention_integration()
    
    # 获取高注意力股票
    high_attention = integration.get_high_attention_symbols(threshold=2.0)
    print(f"高注意力股票: {high_attention}")
    
    # 获取活跃板块
    active_sectors = integration.get_active_sectors(threshold=0.5)
    print(f"活跃板块: {active_sectors}")
    
    # 获取数据源控制指令
    control = integration.get_datasource_control()
    print(f"高频股票数: {len(control['high_freq_symbols'])}")
    print(f"中频股票数: {len(control['medium_freq_symbols'])}")
    print(f"低频股票数: {len(control['low_freq_symbols'])}")


if __name__ == "__main__":
    example_usage()
