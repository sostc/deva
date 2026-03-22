"""
噪音管理系统 - Noise Manager

统一管理个股和板块的噪音过滤。

架构：
1. 个股噪音过滤 (StockNoiseFilter)
   - 基于流动性阈值（成交金额、成交量）
   - 基于特殊股票类型（B股、ST股）
   - 支持黑白名单

2. 板块噪音过滤 (SectorNoiseFilter)
   - 基于名称模式的黑名单
   - 基于统计特性的自动过滤

3. 统一接口 (NoiseManager)
   - 整合个股和板块噪音管理
   - 与 config 系统集成
   - 提供统一的过滤 API
"""

import logging
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, field
from deva import config

log = logging.getLogger(__name__)


@dataclass
class StockNoiseConfig:
    """个股噪音配置"""
    enabled: bool = True
    min_amount: float = 100_000
    min_volume: float = 10_000
    min_price: float = 0.1
    max_price: float = 5000.0
    filter_b_shares: bool = True
    filter_st: bool = False
    dynamic_threshold: bool = True
    dynamic_percentile: float = 5.0


@dataclass
class SectorNoiseConfig:
    """板块噪音配置"""
    enabled: bool = True
    blacklist_patterns: List[str] = field(default_factory=lambda: [
        '通达信', '系统', 'ST', 'B股', '基金', '指数', '期权', '期货',
        '上证', '深证', '沪深', '大盘', '权重', '综合', '行业', '地域',
        '概念', '风格', '上证所', '深交所', '_sys', '_index', '884',
        '物业管理', '含B股', '地方版', '预预', '昨日', '近日',
    ])
    auto_blacklist_enabled: bool = True
    min_attention_threshold: float = 0.01
    min_correlation_variance: float = 0.0001
    min_relation_quality: float = 0.1


class StockNoiseFilter:
    """个股噪音过滤器"""

    def __init__(self, stock_config: StockNoiseConfig = None):
        self._config = stock_config or StockNoiseConfig()
        self._blacklist: Set[str] = set()
        self._whitelist: Set[str] = set()
        self._load_from_config()

    def _load_from_config(self):
        """从配置加载黑白名单"""
        noise_config = config.get('noise_filter', {})
        if noise_config:
            self._config.enabled = noise_config.get('enabled', True)
            self._config.min_amount = noise_config.get('min_amount', 100_000)
            self._config.min_volume = noise_config.get('min_volume', 10_000)
            self._config.min_price = noise_config.get('min_price', 0.1)
            self._config.max_price = noise_config.get('max_price', 5000.0)
            self._config.filter_b_shares = noise_config.get('filter_b_shares', True)
            self._config.filter_st = noise_config.get('filter_st', False)
            self._blacklist = set(noise_config.get('blacklist', []))
            self._whitelist = set(noise_config.get('whitelist', []))

    def reload_config(self):
        """重新加载配置"""
        self._load_from_config()

    def is_noise(
        self,
        symbol: str,
        name: str = None,
        amount: float = None,
        volume: float = None,
        price: float = None
    ) -> bool:
        """
        判断个股是否为噪音

        Args:
            symbol: 股票代码
            name: 股票名称
            amount: 成交金额
            volume: 成交量
            price: 价格

        Returns:
            是否为噪音
        """
        if not self._config.enabled:
            return False

        if symbol in self._whitelist:
            return False

        if symbol in self._blacklist:
            return True

        if amount is not None and amount > 0 and amount < self._config.min_amount:
            return True

        if volume is not None and volume > 0 and volume < self._config.min_volume:
            return True

        if price is not None and price > 0:
            if price < self._config.min_price:
                return True
            if price > self._config.max_price:
                return True

        if name:
            if self._config.filter_b_shares:
                if name.endswith('B') or 'B股' in name:
                    return True
            if self._config.filter_st:
                if name.startswith('ST') or name.startswith('*ST'):
                    return True

        return False

    def add_to_blacklist(self, symbol: str):
        """添加到黑名单"""
        self._blacklist.add(symbol)
        self._save_blacklist()

    def add_to_whitelist(self, symbol: str):
        """添加到白名单"""
        self._whitelist.add(symbol)
        self._save_whitelist()

    def remove_from_blacklist(self, symbol: str):
        """从黑名单移除"""
        self._blacklist.discard(symbol)
        self._save_blacklist()

    def remove_from_whitelist(self, symbol: str):
        """从白名单移除"""
        self._whitelist.discard(symbol)
        self._save_whitelist()

    def _save_blacklist(self):
        """保存黑名单到配置"""
        noise_config = config.get('noise_filter', {})
        noise_config['blacklist'] = list(self._blacklist)
        config.set('noise_filter', 'blacklist', list(self._blacklist))

    def _save_whitelist(self):
        """保存白名单到配置"""
        config.set('noise_filter', 'whitelist', list(self._whitelist))

    def get_blacklist(self) -> Set[str]:
        return self._blacklist.copy()

    def get_whitelist(self) -> Set[str]:
        return self._whitelist.copy()

    def get_config(self) -> StockNoiseConfig:
        return self._config

    def get_stats(self) -> Dict[str, Any]:
        return {
            'enabled': self._config.enabled,
            'min_amount': self._config.min_amount,
            'min_volume': self._config.min_volume,
            'min_price': self._config.min_price,
            'max_price': self._config.max_price,
            'filter_b_shares': self._config.filter_b_shares,
            'filter_st': self._config.filter_st,
            'blacklist_size': len(self._blacklist),
            'whitelist_size': len(self._whitelist),
        }


class SectorNoiseFilter:
    """板块噪音过滤器"""

    def __init__(self, sector_config: SectorNoiseConfig = None):
        self._config = sector_config or SectorNoiseConfig()
        self._auto_blacklist: Set[str] = set()

    def is_noise(self, sector_id: str, sector_name: str = None) -> bool:
        """
        判断板块是否为噪音

        Args:
            sector_id: 板块ID
            sector_name: 板块名称

        Returns:
            是否为噪音
        """
        if not self._config.enabled:
            return False

        display = sector_name if sector_name else sector_id

        for pattern in self._config.blacklist_patterns:
            if pattern in display or pattern in sector_id:
                return True

        if sector_id in self._auto_blacklist:
            return True

        return False

    def add_to_auto_blacklist(self, sector_id: str, reason: str = ""):
        """添加到自动黑名单"""
        self._auto_blacklist.add(sector_id)
        log.debug(f"板块加入自动黑名单: {sector_id} ({reason})")

    def get_auto_blacklist(self) -> Set[str]:
        return self._auto_blacklist.copy()

    def get_all_noise_sectors(self) -> Set[str]:
        """获取所有噪音板块"""
        noise = set()
        for pattern in self._config.blacklist_patterns:
            noise.add(f"_pattern:{pattern}")
        return noise | self._auto_blacklist

    def get_config(self) -> SectorNoiseConfig:
        return self._config

    def get_stats(self) -> Dict[str, Any]:
        return {
            'enabled': self._config.enabled,
            'pattern_count': len(self._config.blacklist_patterns),
            'auto_blacklist_size': len(self._auto_blacklist),
        }


class NoiseManager:
    """
    统一噪音管理器

    整合个股和板块的噪音过滤，提供统一接口。
    """

    _instance: Optional['NoiseManager'] = None

    def __init__(self):
        self._stock_filter = StockNoiseFilter()
        self._sector_filter = SectorNoiseFilter()

    @classmethod
    def get_instance(cls) -> 'NoiseManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    @property
    def stock_filter(self) -> StockNoiseFilter:
        return self._stock_filter

    @property
    def sector_filter(self) -> SectorNoiseFilter:
        return self._sector_filter

    def is_stock_noise(
        self,
        symbol: str,
        name: str = None,
        amount: float = None,
        volume: float = None,
        price: float = None
    ) -> bool:
        """判断个股是否为噪音"""
        return self._stock_filter.is_noise(symbol, name, amount, volume, price)

    def is_sector_noise(self, sector_id: str, sector_name: str = None) -> bool:
        """判断板块是否为噪音"""
        return self._sector_filter.is_noise(sector_id, sector_name)

    def is_noise(
        self,
        item_type: str,
        item_id: str,
        item_name: str = None,
        **kwargs
    ) -> bool:
        """
        统一判断是否为噪音

        Args:
            item_type: 'stock' 或 'sector'
            item_id: 股票代码或板块ID
            item_name: 名称
            **kwargs: 其他参数（amount, volume, price 等）

        Returns:
            是否为噪音
        """
        if item_type == 'stock':
            return self.is_stock_noise(item_id, item_name, **kwargs)
        elif item_type == 'sector':
            return self.is_sector_noise(item_id, item_name)
        return False

    def reload_config(self):
        """重新加载配置"""
        self._stock_filter.reload_config()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'stock': self._stock_filter.get_stats(),
            'sector': self._sector_filter.get_stats(),
        }

    def get_full_report(self) -> Dict[str, Any]:
        """获取完整报告"""
        return {
            'stock_noise': {
                'blacklist': sorted(list(self._stock_filter.get_blacklist())),
                'whitelist': sorted(list(self._stock_filter.get_whitelist())),
                'config': {
                    'enabled': self._stock_filter._config.enabled,
                    'min_amount': self._stock_filter._config.min_amount,
                    'min_volume': self._stock_filter._config.min_volume,
                    'filter_b_shares': self._stock_filter._config.filter_b_shares,
                    'filter_st': self._stock_filter._config.filter_st,
                }
            },
            'sector_noise': {
                'patterns': self._sector_filter._config.blacklist_patterns,
                'auto_blacklist': sorted(list(self._sector_filter.get_auto_blacklist())),
                'config': {
                    'enabled': self._sector_filter._config.enabled,
                    'auto_blacklist': self._sector_filter._config.auto_blacklist_enabled,
                }
            }
        }


def get_noise_manager() -> NoiseManager:
    """获取噪音管理器单例"""
    return NoiseManager.get_instance()


def is_stock_noise(symbol: str, name: str = None, **kwargs) -> bool:
    """快捷函数：判断个股是否为噪音"""
    return get_noise_manager().is_stock_noise(symbol, name, **kwargs)


def is_sector_noise(sector_id: str, sector_name: str = None) -> bool:
    """快捷函数：判断板块是否为噪音"""
    return get_noise_manager().is_sector_noise(sector_id, sector_name)


def is_noise(item_type: str, item_id: str, item_name: str = None, **kwargs) -> bool:
    """快捷函数：统一判断是否为噪音"""
    return get_noise_manager().is_noise(item_type, item_id, item_name, **kwargs)
