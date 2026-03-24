"""
注意力感知的策略基类和工具

为现有策略提供与注意力系统对接的能力
"""

import time
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod

try:
    import pandas as pd
except Exception:
    pd = None


class AttentionAwareMixin:
    """
    注意力感知混入类
    
    为策略添加注意力查询能力
    """
    
    def __init__(self):
        self._attention_integration = None
        self._use_attention = True
        self._last_attention_check = 0
        self._attention_cache_ttl = 5.0  # 5秒缓存
        self._cached_attention_state = {}
    
    def _get_attention_integration(self):
        """懒加载注意力集成"""
        if self._attention_integration is None:
            try:
                from ..attention.integration import get_attention_integration
                self._attention_integration = get_attention_integration()
            except Exception:
                self._use_attention = False
        return self._attention_integration
    
    def should_process_by_attention(self, symbol: str) -> bool:
        """
        根据注意力系统判断是否处理该股票
        
        Args:
            symbol: 股票代码
            
        Returns:
            是否应该处理
        """
        if not self._use_attention:
            return True
        
        integration = self._get_attention_integration()
        if integration is None or integration.attention_system is None:
            return True
        
        return integration.should_fetch_symbol(symbol)
    
    def get_symbol_attention_weight(self, symbol: str) -> float:
        """
        获取股票的注意力权重
        
        Args:
            symbol: 股票代码
            
        Returns:
            权重值 (0.0 - 5.0)
        """
        if not self._use_attention:
            return 1.0
        
        integration = self._get_attention_integration()
        if integration is None or integration.attention_system is None:
            return 1.0
        
        return integration.attention_system.weight_pool.get_symbol_weight(symbol)
    
    def get_global_attention(self) -> float:
        """获取全局注意力分数"""
        if not self._use_attention:
            return 0.5
        
        integration = self._get_attention_integration()
        if integration is None or integration.attention_system is None:
            return 0.5
        
        # 使用缓存
        current_time = time.time()
        if current_time - self._last_attention_check < self._attention_cache_ttl:
            return self._cached_attention_state.get('global', 0.5)
        
        report = integration.get_attention_report()
        global_attention = report.get('global_attention', 0.5)
        
        self._cached_attention_state['global'] = global_attention
        self._last_attention_check = current_time
        
        return global_attention
    
    def get_sector_attention(self, sector_id: str) -> float:
        """获取板块注意力分数"""
        if not self._use_attention:
            return 0.5
        
        integration = self._get_attention_integration()
        if integration is None or integration.attention_system is None:
            return 0.5
        
        return integration.attention_system.sector_attention.get_sector_attention(sector_id)
    
    def filter_by_attention(self, df: pd.DataFrame, 
                           min_weight: float = 1.0,
                           code_column: str = 'code') -> pd.DataFrame:
        """
        根据注意力权重筛选DataFrame
        
        Args:
            df: 输入数据
            min_weight: 最小权重阈值
            code_column: 股票代码列名
            
        Returns:
            筛选后的DataFrame
        """
        if not self._use_attention or df is None or df.empty:
            return df
        
        integration = self._get_attention_integration()
        if integration is None or integration.attention_system is None:
            return df
        
        # 获取高权重股票
        high_attention = integration.get_high_attention_symbols(threshold=min_weight)
        
        if not high_attention:
            return df
        
        # 筛选
        return df[df[code_column].isin(high_attention)]
    
    def adjust_params_by_attention(self, 
                                   base_threshold: float,
                                   base_position: float) -> tuple:
        """
        根据全局注意力调整策略参数
        
        Args:
            base_threshold: 基础阈值
            base_position: 基础仓位
            
        Returns:
            (adjusted_threshold, adjusted_position)
        """
        global_attention = self.get_global_attention()
        
        # 注意力高 -> 阈值降低（更容易触发），仓位增加
        # 注意力低 -> 阈值提高（更难触发），仓位降低
        threshold_factor = 1.0 - (global_attention - 0.5) * 0.4  # 0.8 - 1.2
        position_factor = 0.5 + global_attention * 0.5  # 0.5 - 1.0
        
        adjusted_threshold = base_threshold * threshold_factor
        adjusted_position = base_position * position_factor
        
        return adjusted_threshold, adjusted_position
    
    def get_active_sectors(self, threshold: float = 0.3) -> List[str]:
        """获取活跃板块列表"""
        if not self._use_attention:
            return []
        
        integration = self._get_attention_integration()
        if integration is None:
            return []
        
        return integration.get_active_sectors(threshold)
    
    def enable_attention(self):
        """启用注意力过滤"""
        self._use_attention = True
    
    def disable_attention(self):
        """禁用注意力过滤"""
        self._use_attention = False


class AttentionAwareStrategy:
    """
    注意力感知策略基类
    
    继承此类可以快速为策略添加注意力感知能力
    """
    
    def __init__(self):
        self.attention = AttentionAwareMixin()
    
    def pre_process(self, data: Any) -> Any:
        """
        预处理数据，应用注意力过滤
        
        Args:
            data: 输入数据
            
        Returns:
            过滤后的数据
        """
        if pd is not None and isinstance(data, pd.DataFrame):
            return self.attention.filter_by_attention(data)
        return data
    
    def should_process_symbol(self, symbol: str) -> bool:
        """判断是否应该处理某只股票"""
        return self.attention.should_process_by_attention(symbol)
    
    def get_adjusted_params(self, base_threshold: float, base_position: float) -> tuple:
        """获取根据注意力调整后的参数"""
        return self.attention.adjust_params_by_attention(base_threshold, base_position)


def create_attention_wrapper(strategy_class):
    """
    为现有策略类创建注意力感知包装器
    
    用法:
        @create_attention_wrapper
        class MyStrategy:
            def on_data(self, data):
                ...
    """
    class AttentionWrappedStrategy(strategy_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._attention_mixin = AttentionAwareMixin()
        
        def on_data(self, data):
            # 预处理：注意力过滤
            if pd is not None and isinstance(data, pd.DataFrame):
                data = self._attention_mixin.filter_by_attention(data)
                if data is None or data.empty:
                    return
            
            # 调用原策略逻辑
            super().on_data(data)
    
    return AttentionWrappedStrategy


# ========== 具体策略适配器 ==========

class RiverTickAnomalyHSTWithAttention:
    """
    带注意力感知的 RiverTickAnomalyHST 策略
    """
    
    def __init__(self, base_strategy, use_attention: bool = True):
        self.base_strategy = base_strategy
        self.attention = AttentionAwareMixin()
        if not use_attention:
            self.attention.disable_attention()
    
    def on_data(self, data: Any) -> None:
        """处理数据"""
        # 提取特征前，先进行注意力过滤
        if pd is not None and isinstance(data, pd.DataFrame):
            filtered_df = self.attention.filter_by_attention(data, min_weight=1.5)
            if filtered_df is None or filtered_df.empty:
                return
            data = filtered_df
        
        # 调用原策略
        self.base_strategy.on_data(data)
    
    def get_signal(self) -> Optional[Dict]:
        """获取信号"""
        signal = self.base_strategy.get_signal()
        
        if signal is None:
            return None
        
        # 根据全局注意力调整信号强度
        global_attention = self.attention.get_global_attention()
        if 'score' in signal:
            signal['score'] *= (0.5 + global_attention * 0.5)
        
        return signal


class BlockStockSelectorWithAttention:
    """
    带注意力感知的 BlockStockSelector 策略
    """
    
    def __init__(self, base_selector, use_attention: bool = True):
        self.base_selector = base_selector
        self.attention = AttentionAwareMixin()
        if not use_attention:
            self.attention.disable_attention()
    
    def on_data(self, data: Any) -> None:
        """处理数据"""
        # 只处理活跃板块的股票
        active_sectors = self.attention.get_active_sectors(threshold=0.4)
        
        if active_sectors and pd is not None and isinstance(data, pd.DataFrame):
            # 这里假设可以通过某种方式过滤板块
            # 实际实现需要根据具体数据结构
            pass
        
        # 调用原策略
        self.base_selector.on_data(data)
    
    def get_signal(self) -> Optional[Dict]:
        """获取信号"""
        signal = self.base_selector.get_signal()
        
        if signal is None:
            return None
        
        # 如果股票不在高注意力列表，降低信号强度
        if 'code' in signal:
            weight = self.attention.get_symbol_attention_weight(signal['code'])
            if weight < 1.0 and 'score' in signal:
                signal['score'] *= 0.5
        
        return signal
