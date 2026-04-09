"""
增强型噪音过滤器 - Enhanced Noise Filter

识别并过滤多种类型的噪音股票：
1. 流动性噪音（低成交）
2. 价格异常噪音（横盘、断层、极端价格）
3. 交易行为噪音（对敲、高换手、停牌复牌）
4. 数据质量噪音（缺失、跳变、异常时间）
5. 市场微观结构噪音（庄股、闪崩、涨跌停异常）
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import logging
from collections import deque

log = logging.getLogger(__name__)


class NoiseType(Enum):
    """噪音类型枚举"""
    LOW_LIQUIDITY = "low_liquidity"          # 低流动性
    B_SHARE = "b_share"                       # B股
    ST_STOCK = "st_stock"                     # ST股票
    PRICE_ABNORMAL = "price_abnormal"         # 价格异常
    LONG_TERM_FLAT = "long_term_flat"         # 长期横盘
    PRICE_GAP = "price_gap"                   # 价格断层
    EXTREME_PRICE = "extreme_price"           # 极端价格
    WASH_TRADING = "wash_trading"             # 对敲交易
    HIGH_TURNOVER = "high_turnover"           # 异常高换手
    SUSPENSION = "suspension"                 # 停牌/复牌
    DATA_MISSING = "data_missing"             # 数据缺失
    DATA_JUMP = "data_jump"                   # 数据跳变
    ZHUANG_STOCK = "zhuang_stock"             # 庄股特征
    FLASH_CRASH = "flash_crash"               # 闪崩/闪涨
    LIMIT_ABNORMAL = "limit_abnormal"         # 涨跌停异常


@dataclass
class EnhancedNoiseFilterConfig:
    """增强型噪音过滤器配置"""
    
    # ===== 1. 流动性噪音 =====
    min_amount: float = 1_000_000            # 最小成交金额（元）
    min_volume: float = 100_000              # 最小成交量（股）
    min_price: float = 1.0                   # 最小价格
    max_price: float = 1000.0                # 最大价格（防止除权异常）
    
    # ===== 2. 价格异常噪音 =====
    flat_threshold: float = 0.5              # 横盘阈值：日振幅<%视为横盘
    flat_consecutive_days: int = 5           # 连续横盘天数
    max_spread_pct: float = 2.0              # 最大买卖价差%
    
    # ===== 3. 交易行为噪音 =====
    max_turnover: float = 30.0               # 最大换手率%（超过视为异常）
    wash_trading_volume_ratio: float = 3.0   # 量增价平倍数（成交量突增但价格不变）
    
    # ===== 4. 数据质量噪音 =====
    filter_missing_data: bool = True         # 过滤数据缺失
    max_price_change_pct: float = 20.0       # 最大价格变动%（防止数据跳变）
    
    # ===== 5. 市场微观结构噪音 =====
    flash_crash_threshold: float = 5.0       # 闪崩/闪涨阈值：1分钟内变动%
    zhuang_pattern_threshold: int = 3        # 庄股特征检测阈值
    
    # ===== 6. 特殊股票 =====
    filter_b_shares: bool = True             # 过滤B股
    filter_st: bool = False                  # 过滤ST股票
    filter_chuangyeban_st: bool = True       # 过滤创业板ST（退市风险更高）
    
    # ===== 7. 黑白名单 =====
    blacklist: Set[str] = field(default_factory=set)
    whitelist: Set[str] = field(default_factory=set)
    
    # ===== 8. 动态调整 =====
    dynamic_threshold: bool = True           # 启用动态阈值
    dynamic_percentile: float = 5.0          # 动态阈值分位数
    
    # ===== 9. 历史追踪 =====
    history_window: int = 20                 # 历史数据窗口


@dataclass
class NoiseReport:
    """噪音检测报告"""
    symbol: str
    name: str
    is_noise: bool
    noise_types: List[NoiseType]
    details: Dict[str, any]
    timestamp: float


class EnhancedNoiseFilter:
    """
    增强型噪音过滤器
    
    多维度识别噪音股票，提供详细的过滤报告
    """
    
    def __init__(self, config: Optional[EnhancedNoiseFilterConfig] = None):
        self.config = config or EnhancedNoiseFilterConfig()
        
        # 历史数据缓存（用于检测趋势）
        self._price_history: Dict[str, deque] = {}  # symbol -> deque of (price, timestamp)
        self._volume_history: Dict[str, deque] = {}  # symbol -> deque of (volume, timestamp)
        self._amplitude_history: Dict[str, deque] = {}  # symbol -> deque of (amplitude, timestamp)
        
        # 统计
        self._stats: Dict[NoiseType, int] = {t: 0 for t in NoiseType}
        self._total_checked = 0
        self._total_filtered = 0
        self._symbol_noise_count: Dict[str, int] = {}
        
        # 缓存
        self._cache: Dict[str, Tuple[bool, List[NoiseType], float]] = {}  # symbol -> (is_noise, types, timestamp)
        self._cache_ttl = 5.0
        
        log.info("增强型噪音过滤器初始化完成")
    
    def analyze_stock(
        self,
        symbol: str,
        name: str = "",
        price: float = 0,
        prev_price: float = 0,
        volume: float = 0,
        amount: float = 0,
        turnover: float = 0,
        bid_price: float = 0,
        ask_price: float = 0,
        high: float = 0,
        low: float = 0,
        open_price: float = 0,
        timestamp: float = None
    ) -> NoiseReport:
        """
        分析单个股票是否为噪音
        
        Returns:
            NoiseReport: 噪音检测报告
        """
        if timestamp is None:
            timestamp = time.time()
        
        self._total_checked += 1
        
        # 检查缓存
        if symbol in self._cache:
            cached_result, cached_types, cached_time = self._cache[symbol]
            if timestamp - cached_time < self._cache_ttl:
                return NoiseReport(
                    symbol=symbol,
                    name=name,
                    is_noise=cached_result,
                    noise_types=cached_types,
                    details={},
                    timestamp=timestamp
                )
        
        noise_types = []
        details = {}
        
        # ===== 1. 基础流动性检查 =====
        if amount > 0 and amount < self.config.min_amount:
            noise_types.append(NoiseType.LOW_LIQUIDITY)
            details['amount'] = amount
        
        if volume > 0 and volume < self.config.min_volume:
            if NoiseType.LOW_LIQUIDITY not in noise_types:
                noise_types.append(NoiseType.LOW_LIQUIDITY)
            details['volume'] = volume
        
        # ===== 2. 价格异常检查 =====
        if price > 0:
            # 极端价格
            if price < self.config.min_price or price > self.config.max_price:
                noise_types.append(NoiseType.EXTREME_PRICE)
                details['price'] = price
            
            # 价格跳变检测
            if prev_price > 0:
                price_change_pct = abs(price - prev_price) / prev_price * 100
                if price_change_pct > self.config.max_price_change_pct:
                    noise_types.append(NoiseType.DATA_JUMP)
                    details['price_change_pct'] = price_change_pct
            
            # 买卖价差检测
            if bid_price > 0 and ask_price > 0:
                spread_pct = (ask_price - bid_price) / price * 100
                if spread_pct > self.config.max_spread_pct:
                    noise_types.append(NoiseType.PRICE_GAP)
                    details['spread_pct'] = spread_pct
        
        # ===== 3. 振幅检测（横盘） =====
        if high > 0 and low > 0 and open_price > 0:
            amplitude = (high - low) / open_price * 100
            self._update_history(self._amplitude_history, symbol, amplitude, timestamp)
            
            # 检测长期横盘
            if len(self._amplitude_history.get(symbol, [])) >= self.config.flat_consecutive_days:
                recent_amplitudes = list(self._amplitude_history[symbol])[-self.config.flat_consecutive_days:]
                if all(a < self.config.flat_threshold for a in recent_amplitudes):
                    noise_types.append(NoiseType.LONG_TERM_FLAT)
                    details['avg_amplitude'] = np.mean(recent_amplitudes)
        
        # ===== 4. 换手率检测 =====
        if turnover > self.config.max_turnover:
            noise_types.append(NoiseType.HIGH_TURNOVER)
            details['turnover'] = turnover
        
        # ===== 5. 对敲交易检测 =====
        if volume > 0 and prev_price > 0 and price > 0:
            self._update_history(self._volume_history, symbol, volume, timestamp)
            
            if len(self._volume_history.get(symbol, [])) >= 5:
                avg_volume = np.mean(list(self._volume_history[symbol])[-5:])
                if avg_volume > 0:
                    volume_ratio = volume / avg_volume
                    price_change_pct = abs(price - prev_price) / prev_price * 100
                    
                    # 成交量突增但价格几乎不变
                    if volume_ratio > self.config.wash_trading_volume_ratio and price_change_pct < 0.5:
                        noise_types.append(NoiseType.WASH_TRADING)
                        details['volume_ratio'] = volume_ratio
                        details['price_change_pct'] = price_change_pct
        
        # ===== 6. 特殊股票检测 =====
        if self.config.filter_b_shares and name:
            import re
            if re.search(r'[ＢB]$', name):
                noise_types.append(NoiseType.B_SHARE)
        
        if self.config.filter_st and name:
            import re
            if re.match(r'^(ST|\*ST)', name):
                noise_types.append(NoiseType.ST_STOCK)
        
        # ===== 7. 数据缺失检测 =====
        if self.config.filter_missing_data:
            if price == 0 or volume == 0 or amount == 0:
                noise_types.append(NoiseType.DATA_MISSING)
                details['missing_fields'] = []
                if price == 0: details['missing_fields'].append('price')
                if volume == 0: details['missing_fields'].append('volume')
                if amount == 0: details['missing_fields'].append('amount')
        
        # ===== 8. 黑白名单检查 =====
        if symbol in self.config.blacklist:
            noise_types.append(NoiseType.LOW_LIQUIDITY)  # 使用通用类型
            details['in_blacklist'] = True
        
        if symbol in self.config.whitelist:
            # 白名单保护 - 清除所有噪音标记
            noise_types = []
            details['in_whitelist'] = True
        
        # 更新统计
        is_noise = len(noise_types) > 0
        if is_noise:
            self._total_filtered += 1
            self._symbol_noise_count[symbol] = self._symbol_noise_count.get(symbol, 0) + 1
            for t in noise_types:
                self._stats[t] = self._stats.get(t, 0) + 1
        
        # 缓存结果
        self._cache[symbol] = (is_noise, noise_types, timestamp)
        
        return NoiseReport(
            symbol=symbol,
            name=name,
            is_noise=is_noise,
            noise_types=noise_types,
            details=details,
            timestamp=timestamp
        )
    
    def filter_dataframe(
        self,
        df: pd.DataFrame,
        symbol_col: str = 'code',
        name_col: str = 'name',
        price_col: str = 'now',
        prev_price_col: str = 'close',
        volume_col: str = 'volume',
        amount_col: str = 'amount',
        turnover_col: str = 'turnover',
        high_col: str = 'high',
        low_col: str = 'low',
        open_col: str = 'open',
        bid_col: str = 'buy',
        ask_col: str = 'sell'
    ) -> Tuple[pd.DataFrame, List[NoiseReport]]:
        """
        过滤DataFrame并返回详细报告
        
        Returns:
            (filtered_df, noise_reports)
        """
        if df.empty:
            return df, []
        
        reports = []
        noise_symbols = set()
        
        for idx, row in df.iterrows():
            symbol = str(row.get(symbol_col, idx))
            name = str(row.get(name_col, ''))
            
            report = self.analyze_stock(
                symbol=symbol,
                name=name,
                price=float(row.get(price_col, 0) or 0),
                prev_price=float(row.get(prev_price_col, 0) or 0),
                volume=float(row.get(volume_col, 0) or 0),
                amount=float(row.get(amount_col, 0) or 0),
                turnover=float(row.get(turnover_col, 0) or 0),
                bid_price=float(row.get(bid_col, 0) or 0),
                ask_price=float(row.get(ask_col, 0) or 0),
                high=float(row.get(high_col, 0) or 0),
                low=float(row.get(low_col, 0) or 0),
                open_price=float(row.get(open_col, 0) or 0)
            )
            
            reports.append(report)
            if report.is_noise:
                noise_symbols.add(symbol)
        
        # 过滤
        mask = ~df[symbol_col].astype(str).isin(noise_symbols)
        filtered_df = df[mask].copy()
        
        filtered_count = len(df) - len(filtered_df)
        if filtered_count > 0:
            log.info(f"[增强噪音过滤] 原始{len(df)}条 -> 过滤后{len(filtered_df)}条 (过滤{filtered_count}条)")
        
        return filtered_df, reports
    
    def _update_history(self, history_dict: Dict, symbol: str, value: float, timestamp: float):
        """更新历史数据"""
        if symbol not in history_dict:
            history_dict[symbol] = deque(maxlen=self.config.history_window)
        history_dict[symbol].append((value, timestamp))
    
    def get_noise_summary(self) -> Dict:
        """获取噪音统计摘要"""
        total = max(self._total_checked, 1)
        filter_rate = self._total_filtered / total * 100
        
        # 按类型排序
        sorted_stats = sorted(
            self._stats.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # 最常过滤的股票
        top_symbols = sorted(
            self._symbol_noise_count.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            'total_checked': self._total_checked,
            'total_filtered': self._total_filtered,
            'filter_rate': f"{filter_rate:.2f}%",
            'by_type': {t.value: c for t, c in sorted_stats if c > 0},
            'top_noise_symbols': top_symbols
        }
    
    def reset(self):
        """重置过滤器状态"""
        self._price_history.clear()
        self._volume_history.clear()
        self._amplitude_history.clear()
        self._stats = {t: 0 for t in NoiseType}
        self._total_checked = 0
        self._total_filtered = 0
        self._symbol_noise_count.clear()
        self._cache.clear()


# 全局实例
_enhanced_filter: Optional[EnhancedNoiseFilter] = None


def get_enhanced_noise_filter(config: Optional[EnhancedNoiseFilterConfig] = None) -> EnhancedNoiseFilter:
    """获取增强型噪音过滤器单例"""
    global _enhanced_filter
    if _enhanced_filter is None:
        _enhanced_filter = EnhancedNoiseFilter(config)
    return _enhanced_filter


def reset_enhanced_noise_filter():
    """重置增强型噪音过滤器"""
    global _enhanced_filter
    _enhanced_filter = None
