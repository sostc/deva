"""
噪音过滤器 - Noise Filter

过滤低流动性、低成交金额的噪音股票
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Set, Callable
from dataclasses import dataclass, field
import time
import logging

log = logging.getLogger(__name__)


@dataclass
class NoiseFilterConfig:
    """噪音过滤器配置"""
    
    # 成交金额阈值（元）- 低于此值视为噪音
    min_amount: float = 1_000_000  # 默认100万
    
    # 成交量阈值（股）- 低于此值视为噪音
    min_volume: float = 100_000  # 默认10万股
    
    # 价格阈值（元）- 低于此值可能是低价股噪音
    min_price: float = 1.0  # 默认1元
    
    # 黑名单 - 已知的问题股票
    blacklist: Set[str] = field(default_factory=set)
    
    # 白名单 - 即使不满足条件也不过滤
    whitelist: Set[str] = field(default_factory=set)
    
    # 是否启用动态阈值
    dynamic_threshold: bool = True
    
    # 动态阈值百分比（市场中位数的百分比）
    dynamic_percentile: float = 5.0  # 低于5%分位数的视为噪音
    
    # B股特殊处理（如南玻Ｂ）
    filter_b_shares: bool = True
    
    # ST股票处理
    filter_st: bool = False  # 默认不过滤ST，因为可能有特殊机会
    
    # 过滤统计窗口
    stats_window: int = 100


class NoiseFilter:
    """
    噪音过滤器
    
    职责：
    1. 根据成交金额、成交量过滤低流动性股票
    2. 维护黑名单/白名单
    3. 提供动态阈值调整
    4. 统计过滤效果
    """
    
    def __init__(self, config: Optional[NoiseFilterConfig] = None):
        self.config = config or NoiseFilterConfig()
        
        # 统计
        self._filtered_count = 0
        self._total_count = 0
        self._filtered_symbols: Dict[str, int] = {}  # symbol -> count
        self._amount_history: List[float] = []  # 用于动态阈值
        
        # 缓存
        self._last_filter_time = 0.0
        self._filter_cache: Dict[str, bool] = {}  # symbol -> is_noise
        self._cache_ttl = 5.0  # 缓存5秒
        
        log.info(f"噪音过滤器初始化: min_amount={self.config.min_amount:,.0f}, min_volume={self.config.min_volume:,.0f}")
    
    def filter_dataframe(
        self, 
        df: pd.DataFrame,
        symbol_col: str = 'code',
        amount_col: Optional[str] = 'amount',
        volume_col: Optional[str] = 'volume',
        price_col: Optional[str] = 'now',
        name_col: Optional[str] = 'name'
    ) -> pd.DataFrame:
        """
        过滤DataFrame中的噪音股票
        
        Args:
            df: 输入数据
            symbol_col: 股票代码列名
            amount_col: 成交金额列名
            volume_col: 成交量列名
            price_col: 价格列名
            name_col: 股票名称列名
            
        Returns:
            过滤后的DataFrame
        """
        if df.empty:
            return df
        
        self._total_count += len(df)

        # 获取股票代码的正确方式（可能是列，也可能是索引名）
        def get_symbols(df, col):
            if col in df.columns:
                return df[col].astype(str)
            elif col == df.index.name:
                return df.index.astype(str)
            else:
                return pd.Series([''] * len(df), index=df.index)

        # 构建mask
        mask = pd.Series([True] * len(df), index=df.index)

        # 1. 黑名单过滤
        if self.config.blacklist:
            symbols = get_symbols(df, symbol_col)
            blacklist_mask = ~symbols.isin(self.config.blacklist)
            mask &= blacklist_mask

        # 2. 白名单保护
        whitelist_symbols = set()
        if self.config.whitelist:
            symbols = get_symbols(df, symbol_col)
            whitelist_mask = symbols.isin(self.config.whitelist)
            whitelist_symbols = set(df.loc[whitelist_mask, symbol_col].astype(str).tolist() if symbol_col in df.columns else df.loc[whitelist_mask].index.astype(str).tolist())
        
        # 3. 成交金额过滤（只过滤大于0且低于阈值的）
        if amount_col and amount_col in df.columns:
            amount_threshold = self._get_amount_threshold(df[amount_col])
            symbols = get_symbols(df, symbol_col)
            amount_mask = (df[amount_col] == 0) | (df[amount_col] >= amount_threshold) | symbols.isin(whitelist_symbols)
            mask &= amount_mask

            # 记录被过滤的
            filtered_by_amount = df[~amount_mask & ~symbols.isin(whitelist_symbols)]
            for _, row in filtered_by_amount.iterrows():
                symbol = get_symbols(df, symbol_col).loc[row.name] if symbol_col not in df.columns else str(row[symbol_col])
                self._filtered_symbols[symbol] = self._filtered_symbols.get(symbol, 0) + 1

        # 4. 成交量过滤（只过滤大于0且低于阈值的）
        if volume_col and volume_col in df.columns:
            symbols = get_symbols(df, symbol_col)
            volume_mask = (df[volume_col] == 0) | (df[volume_col] >= self.config.min_volume) | symbols.isin(whitelist_symbols)
            mask &= volume_mask

            filtered_by_volume = df[~volume_mask & ~symbols.isin(whitelist_symbols)]
            for _, row in filtered_by_volume.iterrows():
                symbol = get_symbols(df, symbol_col).loc[row.name] if symbol_col not in df.columns else str(row[symbol_col])
                self._filtered_symbols[symbol] = self._filtered_symbols.get(symbol, 0) + 1

        # 5. 价格过滤
        if price_col and price_col in df.columns:
            symbols = get_symbols(df, symbol_col)
            price_mask = (df[price_col] >= self.config.min_price) | symbols.isin(whitelist_symbols)
            mask &= price_mask

        # 6. B股过滤
        if self.config.filter_b_shares and name_col and name_col in df.columns:
            symbols = get_symbols(df, symbol_col)
            b_share_mask = ~(
                df[name_col].astype(str).str.endswith('B') |
                df[name_col].astype(str).str.contains('B股', regex=False, na=False)
            )
            mask &= b_share_mask

            filtered_b = df[~b_share_mask & ~symbols.isin(whitelist_symbols)]
            for _, row in filtered_b.iterrows():
                symbol = get_symbols(df, symbol_col).loc[row.name] if symbol_col not in df.columns else str(row[symbol_col])
                name = str(row.get(name_col, ''))
                log.debug(f"过滤B股: {symbol} {name}")

        # 7. ST股票过滤
        if self.config.filter_st and name_col and name_col in df.columns:
            st_mask = ~df[name_col].astype(str).str.contains(r'^ST|\\*ST', regex=True, na=False)
            mask &= st_mask
        
        filtered_df = df[mask].copy()
        filtered_count = len(df) - len(filtered_df)
        self._filtered_count += filtered_count
        
        if filtered_count > 0:
            log.debug(f"噪音过滤: 原始{len(df)}条 -> 过滤后{len(filtered_df)}条 (过滤{filtered_count}条)")
        
        return filtered_df
    
    def filter_arrays(
        self,
        symbols: np.ndarray,
        amounts: Optional[np.ndarray] = None,
        volumes: Optional[np.ndarray] = None,
        prices: Optional[np.ndarray] = None,
        names: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        过滤数组格式的数据
        
        Args:
            symbols: 股票代码数组
            amounts: 成交金额数组
            volumes: 成交量数组
            prices: 价格数组
            names: 股票名称数组
            
        Returns:
            有效数据的索引数组
        """
        n = len(symbols)
        self._total_count += n
        
        # 默认全部有效
        valid_mask = np.ones(n, dtype=bool)
        
        # 1. 黑名单
        if self.config.blacklist:
            blacklist_mask = ~np.isin(symbols.astype(str), list(self.config.blacklist))
            valid_mask &= blacklist_mask
        
        # 2. 白名单
        whitelist_indices = set()
        if self.config.whitelist:
            whitelist_mask = np.isin(symbols.astype(str), list(self.config.whitelist))
            whitelist_indices = set(np.where(whitelist_mask)[0])
        
        # 3. 成交金额
        if amounts is not None:
            if self.config.dynamic_threshold and len(amounts) > 0:
                threshold = np.percentile(amounts, self.config.dynamic_percentile)
                threshold = max(threshold, self.config.min_amount)
            else:
                threshold = self.config.min_amount
            
            amount_mask = (amounts >= threshold)
            for i in whitelist_indices:
                amount_mask[i] = True
            valid_mask &= amount_mask
        
        # 4. 成交量
        if volumes is not None:
            volume_mask = (volumes >= self.config.min_volume)
            for i in whitelist_indices:
                volume_mask[i] = True
            valid_mask &= volume_mask
        
        # 5. 价格
        if prices is not None:
            price_mask = (prices >= self.config.min_price)
            for i in whitelist_indices:
                price_mask[i] = True
            valid_mask &= price_mask
        
        # 6. B股
        if self.config.filter_b_shares and names is not None:
            import re
            b_pattern = re.compile(r'[ＢB]$')
            b_mask = ~np.array([bool(b_pattern.search(str(n))) for n in names])
            valid_mask &= b_mask
        
        filtered_count = n - np.sum(valid_mask)
        self._filtered_count += filtered_count
        
        return np.where(valid_mask)[0]
    
    def is_noise(self, symbol: str, amount: float = 0, volume: float = 0, price: float = 0) -> bool:
        """
        判断单个股票是否为噪音
        
        Args:
            symbol: 股票代码
            amount: 成交金额
            volume: 成交量
            price: 价格
            
        Returns:
            是否为噪音
        """
        # 检查缓存
        current_time = time.time()
        if current_time - self._last_filter_time < self._cache_ttl:
            if symbol in self._filter_cache:
                return self._filter_cache[symbol]
        else:
            self._filter_cache.clear()
            self._last_filter_time = current_time
        
        # 白名单
        if symbol in self.config.whitelist:
            self._filter_cache[symbol] = False
            return False
        
        # 黑名单
        if symbol in self.config.blacklist:
            self._filter_cache[symbol] = True
            return True
        
        # 金额检查
        if amount > 0 and amount < self.config.min_amount:
            self._filter_cache[symbol] = True
            return True
        
        # 成交量检查
        if volume > 0 and volume < self.config.min_volume:
            self._filter_cache[symbol] = True
            return True
        
        # 价格检查
        if price > 0 and price < self.config.min_price:
            self._filter_cache[symbol] = True
            return True
        
        self._filter_cache[symbol] = False
        return False
    
    def _get_amount_threshold(self, amounts: pd.Series) -> float:
        """获取成交金额阈值"""
        if not self.config.dynamic_threshold:
            return self.config.min_amount
        
        # 更新历史
        self._amount_history.extend(amounts.tolist())
        if len(self._amount_history) > self.config.stats_window:
            self._amount_history = self._amount_history[-self.config.stats_window:]
        
        # 计算动态阈值
        if len(self._amount_history) >= 10:
            dynamic_threshold = np.percentile(self._amount_history, self.config.dynamic_percentile)
            return max(dynamic_threshold, self.config.min_amount)
        
        return self.config.min_amount
    
    def add_to_blacklist(self, symbol: str, reason: str = ""):
        """添加到黑名单"""
        self.config.blacklist.add(symbol)
        log.info(f"添加 {symbol} 到黑名单: {reason}")
    
    def add_to_whitelist(self, symbol: str, reason: str = ""):
        """添加到白名单"""
        self.config.whitelist.add(symbol)
        log.info(f"添加 {symbol} 到白名单: {reason}")
    
    def remove_from_blacklist(self, symbol: str):
        """从黑名单移除"""
        self.config.blacklist.discard(symbol)
    
    def remove_from_whitelist(self, symbol: str):
        """从白名单移除"""
        self.config.whitelist.discard(symbol)
    
    def get_stats(self) -> Dict:
        """获取过滤统计"""
        total = max(self._total_count, 1)
        filter_rate = self._filtered_count / total * 100
        
        # 最常过滤的股票
        top_filtered = sorted(
            self._filtered_symbols.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            'total_processed': self._total_count,
            'total_filtered': self._filtered_count,
            'filter_rate': f"{filter_rate:.2f}%",
            'blacklist_size': len(self.config.blacklist),
            'whitelist_size': len(self.config.whitelist),
            'top_filtered_symbols': top_filtered,
            'config': {
                'min_amount': self.config.min_amount,
                'min_volume': self.config.min_volume,
                'min_price': self.config.min_price,
                'dynamic_threshold': self.config.dynamic_threshold
            }
        }
    
    def reset_stats(self):
        """重置统计"""
        self._filtered_count = 0
        self._total_count = 0
        self._filtered_symbols.clear()
        self._amount_history.clear()


# 全局实例
_noise_filter: Optional[NoiseFilter] = None


def get_noise_filter(config: Optional[NoiseFilterConfig] = None) -> NoiseFilter:
    """获取噪音过滤器单例"""
    global _noise_filter
    if _noise_filter is None:
        _noise_filter = NoiseFilter(config)
    return _noise_filter


def reset_noise_filter():
    """重置噪音过滤器"""
    global _noise_filter
    _noise_filter = None
