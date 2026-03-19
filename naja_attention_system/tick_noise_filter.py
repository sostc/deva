"""
Tick级别噪音过滤器

基于5秒tick数据的噪音过滤，支持：
1. 基础流动性过滤（金额、成交量）
2. 价格异常过滤（横盘、跳变、极端价格）
3. 交易行为过滤（对敲、异常波动）
4. 特殊股票过滤（B股、ST股）
5. 跨天跨周末数据特殊处理
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import logging
from collections import deque
from datetime import datetime

from .market_time_utils import MarketTimeUtils, get_market_utils

log = logging.getLogger(__name__)


class TickNoiseType(Enum):
    """Tick级别噪音类型"""
    # 流动性噪音
    LOW_AMOUNT = "low_amount"                 # 低成交金额
    LOW_VOLUME = "low_volume"                 # 低成交量
    
    # 价格异常
    EXTREME_PRICE = "extreme_price"           # 极端价格
    PRICE_JUMP = "price_jump"                 # 价格跳变
    LONG_FLAT = "long_flat"                   # 长期横盘
    
    # 交易行为
    WASH_TRADING = "wash_trading"             # 对敲交易
    ABNORMAL_VOLATILITY = "abnormal_vol"      # 异常波动
    
    # 特殊股票
    B_SHARE = "b_share"                       # B股
    ST_STOCK = "st_stock"                     # ST股
    
    # 数据质量
    DATA_MISSING = "data_missing"             # 数据缺失


@dataclass
class TickNoiseFilterConfig:
    """Tick噪音过滤器配置"""
    
    # ===== 1. 流动性阈值 =====
    min_amount: float = 1_000_000            # 最小成交金额（元）
    min_volume: float = 100_000              # 最小成交量（股）
    
    # ===== 2. 价格异常阈值 =====
    min_price: float = 1.0                   # 最小价格
    max_price: float = 1000.0                # 最大价格
    max_price_change_pct: float = 20.0       # 最大价格变动%（跳变检测）
    
    # 时间跨度相关配置
    normal_time_interval: float = 5.0        # 正常时间间隔（秒），默认5秒
    max_time_gap: float = 300.0              # 最大允许时间间隔（秒），超过视为不连续数据
    time_gap_adjustment: bool = True         # 是否根据时间跨度调整阈值
    
    # 横盘检测
    flat_threshold: float = 0.5              # 横盘振幅阈值%
    flat_consecutive_frames: int = 10        # 连续横盘帧数（5秒*10=50秒）
    
    # ===== 3. 交易行为阈值 =====
    wash_trading_volume_ratio: float = 3.0   # 成交量突增倍数
    wash_trading_price_change_max: float = 0.5  # 对敲时最大价格变动%
    abnormal_volatility_threshold: float = 10.0  # 异常波动阈值%
    
    # ===== 4. 特殊股票 =====
    filter_b_shares: bool = True             # 过滤B股
    filter_st: bool = False                  # 过滤ST股
    
    # ===== 5. 黑白名单 =====
    blacklist: Set[str] = field(default_factory=set)
    whitelist: Set[str] = field(default_factory=set)
    
    # ===== 6. 历史窗口 =====
    history_window: int = 20                 # 历史数据保存帧数


@dataclass
class TickNoiseReport:
    """Tick噪音检测报告"""
    symbol: str
    name: str
    is_noise: bool
    noise_types: List[TickNoiseType]
    details: Dict[str, any]
    timestamp: float


class TickNoiseFilter:
    """
    Tick级别噪音过滤器
    
    专为5秒tick数据设计，维护每只股票的历史状态
    """
    
    def __init__(self, config: Optional[TickNoiseFilterConfig] = None):
        self.config = config or TickNoiseFilterConfig()
        
        # 历史数据缓存 - 每只股票独立维护
        self._price_history: Dict[str, deque] = {}      # symbol -> deque of (price, timestamp)
        self._volume_history: Dict[str, deque] = {}     # symbol -> deque of (volume, timestamp)
        self._amplitude_history: Dict[str, deque] = {}  # symbol -> deque of (amplitude, timestamp)
        self._last_price: Dict[str, float] = {}         # symbol -> last_price
        
        # 统计
        self._stats: Dict[TickNoiseType, int] = {t: 0 for t in TickNoiseType}
        self._total_checked = 0
        self._total_filtered = 0
        self._symbol_noise_count: Dict[str, Dict[TickNoiseType, int]] = {}
        
        # 缓存
        self._cache: Dict[str, Tuple[bool, List[TickNoiseType], float]] = {}
        self._cache_ttl = 5.0
        
        log.info(f"Tick噪音过滤器初始化: min_amount={self.config.min_amount:,.0f}, min_volume={self.config.min_volume:,.0f}")
    
    def analyze_tick(
        self,
        symbol: str,
        name: str = "",
        now: float = 0,
        close: float = 0,
        volume: float = 0,
        amount: float = 0,
        high: float = 0,
        low: float = 0,
        open_price: float = 0,
        timestamp: float = None
    ) -> TickNoiseReport:
        """
        分析单只股票的tick数据
        
        支持不连续数据（时间跨度大）的智能处理
        
        Returns:
            TickNoiseReport: 噪音检测报告
        """
        if timestamp is None:
            timestamp = time.time()
        
        self._total_checked += 1
        
        # 检查缓存
        cache_key = f"{symbol}_{int(timestamp / self._cache_ttl)}"
        if cache_key in self._cache:
            cached_result, cached_types, _ = self._cache[cache_key]
            return TickNoiseReport(
                symbol=symbol,
                name=name,
                is_noise=cached_result,
                noise_types=cached_types,
                details={},
                timestamp=timestamp
            )
        
        noise_types = []
        details = {}
        
        # ===== 0. 计算时间跨度并识别市场时段 =====
        time_gap = 0
        last_timestamp = None
        gap_type = 'intraday'
        market_utils = get_market_utils()
        
        if symbol in self._price_history and self._price_history[symbol]:
            last_timestamp = self._price_history[symbol][-1][1]
            time_gap = timestamp - last_timestamp
            
            # 使用市场时间工具分析时间跨度
            try:
                dt1 = datetime.fromtimestamp(last_timestamp)
                dt2 = datetime.fromtimestamp(timestamp)
                _, gap_type = market_utils.calculate_trading_time_gap(dt1, dt2)
            except:
                gap_type = 'intraday'
        
        # 判断数据是否连续（考虑跨天跨周末）
        is_continuous = gap_type == 'intraday' and time_gap <= self.config.max_time_gap
        should_reset = gap_type in ['overnight', 'weekend', 'holiday']
        
        details['time_gap'] = time_gap
        details['is_continuous'] = is_continuous
        details['gap_type'] = gap_type
        details['should_reset_history'] = should_reset
        
        # 如果是跨天/跨周末/节假日，记录日志
        if should_reset:
            log.debug(f"[{symbol}] 检测到{gap_type}数据，时间跨度: {market_utils.format_time_gap(time_gap)}")
        
        # ===== 1. 基础流动性检查（不受时间跨度影响） =====
        # 注意：金额为0或成交量为0是正常的（如停牌、集合竞价前），不视为噪音
        # 只过滤有交易但金额/成交量过低的股票
        if amount > 0 and amount < self.config.min_amount:
            noise_types.append(TickNoiseType.LOW_AMOUNT)
            details['amount'] = amount
        
        if volume > 0 and volume < self.config.min_volume:
            if TickNoiseType.LOW_VOLUME not in noise_types:
                noise_types.append(TickNoiseType.LOW_VOLUME)
            details['volume'] = volume
        
        # ===== 2. 价格异常检查（考虑时间跨度） =====
        if now > 0:
            # 极端价格（不受时间影响）
            if now < self.config.min_price or now > self.config.max_price:
                noise_types.append(TickNoiseType.EXTREME_PRICE)
                details['price'] = now
            
            # 价格跳变检测（考虑时间跨度和市场时段）
            if symbol in self._last_price and last_timestamp:
                last_price = self._last_price[symbol]
                if last_price > 0:
                    price_change_pct = abs(now - last_price) / last_price * 100
                    
                    # 使用市场时间工具获取调整后的阈值
                    adjusted_threshold = market_utils.get_adjusted_threshold(
                        self.config.max_price_change_pct,
                        gap_type,
                        time_gap
                    )
                    
                    details['adjusted_threshold'] = adjusted_threshold
                    details['original_threshold'] = self.config.max_price_change_pct
                    details['gap_type'] = gap_type
                    
                    if price_change_pct > adjusted_threshold:
                        noise_types.append(TickNoiseType.PRICE_JUMP)
                        details['price_change_pct'] = price_change_pct
                        details['last_price'] = last_price
                        details['threshold_type'] = f'adjusted_{gap_type}'
                    else:
                        # 记录正常的价格变化（用于调试）
                        if gap_type != 'intraday':
                            details['price_change_normal'] = price_change_pct
                            details['note'] = f'{gap_type}价格变化正常'
            
            # 保存当前价格和时间戳
            self._last_price[symbol] = now
            
            # 更新价格历史
            self._update_history(self._price_history, symbol, now, timestamp)
        
        # ===== 3. 振幅检测（横盘）- 跨天/跨周末时重置历史 =====
        if should_reset:
            # 跨天/跨周末/节假日，重置历史数据
            if symbol in self._amplitude_history:
                self._amplitude_history[symbol].clear()
            details['flat_detection_reset'] = f'{gap_type}数据，重置历史'
        elif is_continuous and high > 0 and low > 0 and open_price > 0.001:  # 避免除以极小值
            try:
                amplitude = (high - low) / open_price * 100
                # 检查振幅是否合理（防止异常值）
                if 0 <= amplitude <= 100:  # 振幅应该在0-100%之间
                    self._update_history(self._amplitude_history, symbol, amplitude, timestamp)
            except (OverflowError, ValueError) as e:
                log.debug(f"[{symbol}] 振幅计算异常: {e}, high={high}, low={low}, open={open_price}")
            
            # 检测长期横盘
            if len(self._amplitude_history.get(symbol, [])) >= self.config.flat_consecutive_frames:
                recent_amplitudes = list(self._amplitude_history[symbol])[-self.config.flat_consecutive_frames:]
                avg_amplitude = np.mean(recent_amplitudes)
                if avg_amplitude < self.config.flat_threshold:
                    noise_types.append(TickNoiseType.LONG_FLAT)
                    details['avg_amplitude'] = avg_amplitude
                    details['flat_frames'] = self.config.flat_consecutive_frames
        elif not is_continuous:
            # 数据不连续，重置振幅历史
            if symbol in self._amplitude_history:
                self._amplitude_history[symbol].clear()
            details['flat_detection_skipped'] = True
        
        # ===== 4. 对敲交易检测 - 跨天/跨周末时重置历史 =====
        if should_reset:
            # 跨天/跨周末/节假日，重置成交量历史
            if symbol in self._volume_history:
                self._volume_history[symbol].clear()
            details['wash_trading_detection_reset'] = f'{gap_type}数据，重置历史'
        elif is_continuous and volume > 0 and now > 0:
            self._update_history(self._volume_history, symbol, volume, timestamp)
            
            if len(self._volume_history.get(symbol, [])) >= 5:
                # 计算平均成交量（最近5帧）
                recent_volumes = [v for v, _ in list(self._volume_history[symbol])[-5:]]
                avg_volume = np.mean(recent_volumes)
                
                if avg_volume > 0:
                    volume_ratio = volume / avg_volume
                    
                    # 获取价格变动
                    price_change_pct = 0
                    if symbol in self._price_history and len(self._price_history[symbol]) >= 2:
                        prices = [p for p, _ in list(self._price_history[symbol])[-2:]]
                        if len(prices) >= 2 and prices[0] > 0:
                            price_change_pct = abs(prices[1] - prices[0]) / prices[0] * 100
                    
                    # 成交量突增但价格几乎不变 -> 对敲
                    if (volume_ratio > self.config.wash_trading_volume_ratio and 
                        price_change_pct < self.config.wash_trading_price_change_max):
                        noise_types.append(TickNoiseType.WASH_TRADING)
                        details['volume_ratio'] = volume_ratio
                        details['price_change_pct'] = price_change_pct
        elif not is_continuous:
            # 数据不连续，重置成交量历史
            if symbol in self._volume_history:
                self._volume_history[symbol].clear()
            details['wash_trading_detection_skipped'] = True
        
        # ===== 5. 异常波动检测（考虑市场时段） =====
        if now > 0 and close > 0:
            p_change = (now - close) / close * 100
            
            # 使用市场时间工具获取调整后的波动阈值
            adjusted_vol_threshold = market_utils.get_adjusted_threshold(
                self.config.abnormal_volatility_threshold,
                gap_type,
                time_gap
            )
            
            if abs(p_change) > adjusted_vol_threshold:
                noise_types.append(TickNoiseType.ABNORMAL_VOLATILITY)
                details['p_change'] = p_change
                details['vol_threshold_type'] = f'adjusted_{gap_type}'
            elif gap_type != 'intraday':
                # 记录正常的波动（用于调试）
                details['volatility_normal'] = p_change
                details['vol_threshold'] = adjusted_vol_threshold
        
        # ===== 6. 特殊股票检测 =====
        if self.config.filter_b_shares and name:
            import re
            if re.search(r'[ＢB]$', name):
                noise_types.append(TickNoiseType.B_SHARE)
        
        if self.config.filter_st and name:
            import re
            if re.match(r'^(ST|\*ST)', name):
                noise_types.append(TickNoiseType.ST_STOCK)
        
        # ===== 7. 数据缺失检测 =====
        # 注意：只检测关键字段（价格），成交量和金额可能为0（如停牌期间）
        if now == 0:
            noise_types.append(TickNoiseType.DATA_MISSING)
            details['missing'] = ['price']
        # volume 和 amount 为0是正常的（如集合竞价前、停牌期间）
        # 不将其视为噪音
        
        # ===== 8. 黑白名单检查 =====
        if symbol in self.config.blacklist:
            noise_types.append(TickNoiseType.LOW_AMOUNT)  # 使用通用类型
            details['in_blacklist'] = True
        
        if symbol in self.config.whitelist:
            noise_types = []
            details['in_whitelist'] = True
        
        # 更新统计
        is_noise = len(noise_types) > 0
        if is_noise:
            self._total_filtered += 1
            if symbol not in self._symbol_noise_count:
                self._symbol_noise_count[symbol] = {}
            for t in noise_types:
                self._stats[t] = self._stats.get(t, 0) + 1
                self._symbol_noise_count[symbol][t] = self._symbol_noise_count[symbol].get(t, 0) + 1
        
        # 缓存结果
        self._cache[cache_key] = (is_noise, noise_types, timestamp)
        
        return TickNoiseReport(
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
        close_col: str = 'close',
        volume_col: str = 'volume',
        amount_col: str = 'amount',
        high_col: str = 'high',
        low_col: str = 'low',
        open_col: str = 'open'
    ) -> Tuple[pd.DataFrame, List[TickNoiseReport]]:
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
            
            report = self.analyze_tick(
                symbol=symbol,
                name=name,
                now=float(row.get(price_col, 0) or 0),
                close=float(row.get(close_col, 0) or 0),
                volume=float(row.get(volume_col, 0) or 0),
                amount=float(row.get(amount_col, 0) or 0),
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
            log.info(f"[Tick噪音过滤] 原始{len(df)}条 -> 过滤后{len(filtered_df)}条 (过滤{filtered_count}条)")
        
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
            [(t.value, c) for t, c in self._stats.items() if c > 0],
            key=lambda x: x[1],
            reverse=True
        )
        
        # 最常过滤的股票
        top_symbols = sorted(
            [(s, sum(c.values())) for s, c in self._symbol_noise_count.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        # 每种类型的top股票
        top_by_type = {}
        for noise_type in TickNoiseType:
            type_symbols = [
                (s, c.get(noise_type, 0))
                for s, c in self._symbol_noise_count.items()
            ]
            type_symbols = [(s, c) for s, c in type_symbols if c > 0]
            type_symbols = sorted(type_symbols, key=lambda x: x[1], reverse=True)[:5]
            if type_symbols:
                top_by_type[noise_type.value] = type_symbols
        
        return {
            'total_checked': self._total_checked,
            'total_filtered': self._total_filtered,
            'filter_rate': f"{filter_rate:.2f}%",
            'by_type': sorted_stats,
            'top_noise_symbols': top_symbols,
            'top_by_type': top_by_type
        }
    
    def get_symbol_history(self, symbol: str) -> Dict:
        """获取某只股票的历史数据（用于调试）"""
        return {
            'price_history': list(self._price_history.get(symbol, [])),
            'volume_history': list(self._volume_history.get(symbol, [])),
            'amplitude_history': list(self._amplitude_history.get(symbol, [])),
            'last_price': self._last_price.get(symbol),
            'noise_count': self._symbol_noise_count.get(symbol, {})
        }
    
    def reset(self):
        """重置过滤器状态"""
        self._price_history.clear()
        self._volume_history.clear()
        self._amplitude_history.clear()
        self._last_price.clear()
        self._stats = {t: 0 for t in TickNoiseType}
        self._total_checked = 0
        self._total_filtered = 0
        self._symbol_noise_count.clear()
        self._cache.clear()


# 全局实例
_tick_noise_filter: Optional[TickNoiseFilter] = None


def get_tick_noise_filter(config: Optional[TickNoiseFilterConfig] = None) -> TickNoiseFilter:
    """获取Tick噪音过滤器单例"""
    global _tick_noise_filter
    if _tick_noise_filter is None:
        _tick_noise_filter = TickNoiseFilter(config)
    return _tick_noise_filter


def reset_tick_noise_filter():
    """重置Tick噪音过滤器"""
    global _tick_noise_filter
    _tick_noise_filter = None
