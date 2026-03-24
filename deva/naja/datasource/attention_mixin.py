"""
Attention Mixin - 让 DataSource 具备注意力感知能力

使用方法:
    class MyDataSource(DataSourceEntry, AttentionMixin):
        def fetch_data(self):
            # 获取全量数据
            all_symbols = self.get_all_symbols()
            
            # 使用注意力系统筛选
            symbols_to_fetch = self.get_symbols_by_attention(all_symbols)
            
            # 只获取高注意力股票（节省资源）
            data = self.fetch_symbols(symbols_to_fetch)
            
            self.emit(data)
"""

import time
from typing import List, Set, Optional
from abc import ABC


class AttentionMixin(ABC):
    """
    注意力系统混入类
    
    为 DataSource 添加注意力调度能力
    """
    
    def __init__(self):
        self._attention_integration = None
        self._attention_enabled = True
        self._last_tier_update = 0
        self._tier_update_interval = 10  # 每10秒更新一次分层
        
        # 股票分层缓存
        self._high_symbols: Set[str] = set()
        self._medium_symbols: Set[str] = set()
        self._low_symbols: Set[str] = set()
    
    def _get_attention_integration(self):
        """懒加载注意力集成"""
        if self._attention_integration is None:
            try:
                from ..attention.integration import get_attention_integration
                self._attention_integration = get_attention_integration()
            except Exception:
                self._attention_enabled = False
        return self._attention_integration
    
    def get_symbols_by_attention(
        self, 
        all_symbols: List[str],
        min_weight: float = 0.0
    ) -> List[str]:
        """
        根据注意力系统筛选股票
        
        Args:
            all_symbols: 全量股票列表
            min_weight: 最小权重阈值
            
        Returns:
            应该获取的股票列表
        """
        integration = self._get_attention_integration()
        
        if not self._attention_enabled or integration is None:
            return all_symbols
        
        if integration.attention_system is None:
            return all_symbols
        
        # 更新分层
        self._update_symbol_tiers(integration)
        
        # 根据频率返回不同分层
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
        
        # 中频：每10秒（0, 10, 20, 30, 40, 50）
        if current_second % 10 == 0:
            result.extend(self._medium_symbols)
        
        # 低频：每60秒（只在0秒）
        if current_second == 0:
            result.extend(self._low_symbols)
        
        return result
    
    def should_fetch_symbol(self, symbol: str) -> bool:
        """判断是否应该获取某只股票"""
        integration = self._get_attention_integration()
        
        if not self._attention_enabled or integration is None:
            return True
        
        return integration.should_fetch_symbol(symbol)
    
    def get_attention_report(self) -> dict:
        """获取注意力系统报告"""
        integration = self._get_attention_integration()
        
        if not self._attention_enabled or integration is None:
            return {'status': 'disabled'}
        
        return integration.get_attention_report()
    
    def get_high_attention_symbols(self, threshold: float = 2.0) -> List[str]:
        """获取高注意力股票"""
        integration = self._get_attention_integration()
        
        if not self._attention_enabled or integration is None:
            return []
        
        return integration.get_high_attention_symbols(threshold)
    
    def enable_attention(self):
        """启用注意力调度"""
        self._attention_enabled = True
    
    def disable_attention(self):
        """禁用注意力调度"""
        self._attention_enabled = False
