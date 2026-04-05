"""
板块噪音检测器 - Sector Noise Detector

注意力系统的噪音过滤基础设施，用于识别和过滤低价值的噪音板块。

噪音板块类型:
1. 系统分类板块 - 通达信分类系统产生的噪音（如"通达信88"、"行业板块"等）
2. 宽基指数板块 - 沪深指数、大盘、权重等
3. 概念风格板块 - 概念炒作、风格轮动等短期噪音
4. 地方区域板块 - 包含大量低流动性股票
5. 静态分类板块 - 昨日涨停、近日跌停等无预测价值的板块
"""

import logging
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
import re

log = logging.getLogger(__name__)


@dataclass
class BlockNoiseConfig:
    """板块噪音检测配置"""

    blacklist_patterns: List[str] = field(default_factory=lambda: [
        '通达信', '系统', 'ST', 'B股', '基金', '指数', '期权', '期货',
        '上证', '深证', '沪深', '大盘', '权重', '综合', '行业', '地域',
        '概念', '风格', '上证所', '深交所', '_sys', '_index', '884',
        '物业管理', '含B股', '地方版', '预预', '昨日', '近日',
    ])

    auto_blacklist_enabled: bool = True

    min_correlation_variance: float = 0.0001

    min_relation_quality: float = 0.1

    min_sector_attention: float = 0.01


class BlockNoiseDetector:
    """
    板块噪音检测器

    职责：
    1. 识别噪音板块（基于名称模式）
    2. 自动将低价值板块加入黑名单（基于统计特性）
    3. 提供统一的噪音检测接口

    噪音过滤是注意力系统的基础设施，确保注意力资源集中在真正值得关注的板块上。
    """

    _DEFAULT_CONFIG = BlockNoiseConfig()
    _instance: Optional['BlockNoiseDetector'] = None

    def __init__(self, config: Optional[BlockNoiseConfig] = None):
        self.config = config or self._DEFAULT_CONFIG

        self._blacklist: Set[str] = set()

        self._sector_stats: Dict[str, Dict] = {}

        self._auto_blacklist_cache: Set[str] = set()

    @classmethod
    def get_instance(cls) -> 'BlockNoiseDetector':
        """获取单例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """重置单例（用于测试）"""
        cls._instance = None

    def is_noise(self, sector_id: str, sector_name: str = None) -> bool:
        """
        判断板块是否为噪音

        Args:
            sector_id: 板块ID
            sector_name: 板块名称（可选，如果不提供则只检查ID）

        Returns:
            是否为噪音板块
        """
        if sector_id in self._blacklist:
            return True

        if sector_id in self._auto_blacklist_cache:
            return True

        display = sector_name if sector_name else sector_id

        for pattern in self.config.blacklist_patterns:
            if pattern in display or pattern in sector_id:
                return True

        return False

    def add_to_blacklist(self, sector_id: str, reason: str = ""):
        """手动添加板块到黑名单"""
        self._blacklist.add(sector_id)
        log.info(f"板块加入噪音黑名单: {sector_id} ({reason})")

    def remove_from_blacklist(self, sector_id: str):
        """从黑名单移除"""
        self._blacklist.discard(sector_id)
        self._auto_blacklist_cache.discard(sector_id)

    def get_blacklist(self) -> Set[str]:
        """获取当前黑名单"""
        return self._blacklist.copy()

    def get_all_noise_sectors(self) -> Set[str]:
        """获取所有噪音板块（包括自动黑名单）"""
        return self._blacklist | self._auto_blacklist_cache

    def update_sector_stats(
        self,
        sector_id: str,
        attention_score: float,
        correlation_variance: float = None,
        relation_quality: float = None
    ):
        """
        更新板块统计信息（用于自动噪音检测）

        Args:
            sector_id: 板块ID
            attention_score: 注意力分数
            correlation_variance: 相关性方差（越小表示越稳定=噪音）
            relation_quality: 关系质量分数（越小表示越孤立=噪音）
        """
        if sector_id in self._blacklist:
            return

        self._sector_stats[sector_id] = {
            'attention_score': attention_score,
            'correlation_variance': correlation_variance,
            'relation_quality': relation_quality,
        }

        if self.config.auto_blacklist_enabled:
            self._auto_check_and_blacklist(sector_id)

    def _auto_check_and_blacklist(self, sector_id: str):
        """自动检查并加入黑名单"""
        if sector_id in self._auto_blacklist_cache:
            return

        stats = self._sector_stats.get(sector_id, {})

        if stats.get('correlation_variance') is not None:
            if stats['correlation_variance'] < self.config.min_correlation_variance:
                self._auto_blacklist_cache.add(sector_id)
                log.debug(f"板块自动加入黑名单（低方差）: {sector_id}")
                return

        if stats.get('relation_quality') is not None:
            if stats['relation_quality'] < self.config.min_relation_quality:
                self._auto_blacklist_cache.add(sector_id)
                log.debug(f"板块自动加入黑名单（低关系质量）: {sector_id}")
                return

        if stats.get('attention_score', 0) < self.config.min_sector_attention:
            self._auto_blacklist_cache.add(sector_id)
            log.debug(f"板块自动加入黑名单（低注意力）: {sector_id}")

    def filter_noise_sectors(self, sectors: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
        """
        过滤噪音板块

        Args:
            sectors: [(sector_id, weight), ...] 板块列表

        Returns:
            过滤后的板块列表
        """
        return [(s, w) for s, w in sectors if not self.is_noise(s)]

    def get_valid_sectors(self, sectors: List[str]) -> List[str]:
        """
        获取有效板块列表

        Args:
            sectors: 板块ID列表

        Returns:
            有效板块列表
        """
        return [s for s in sectors if not self.is_noise(s)]

    def get_noise_report(self) -> Dict:
        """获取噪音检测报告"""
        return {
            'manual_blacklist_size': len(self._blacklist),
            'auto_blacklist_size': len(self._auto_blacklist_cache),
            'total_noise_size': len(self.get_all_noise_sectors()),
            'manual_blacklist': sorted(list(self._blacklist))[:20],
            'auto_blacklist': sorted(list(self._auto_blacklist_cache))[:20],
        }


def get_block_noise_detector() -> BlockNoiseDetector:
    """获取板块噪音检测器单例"""
    return BlockNoiseDetector.get_instance()


def is_block_noise(sector_id: str, sector_name: str = None) -> bool:
    """快捷函数：判断板块是否为噪音"""
    detector = get_block_noise_detector()
    return detector.is_noise(sector_id, sector_name)


def filter_noise_sectors(sectors: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
    """快捷函数：过滤噪音板块"""
    detector = get_block_noise_detector()
    return detector.filter_noise_sectors(sectors)
