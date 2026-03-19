"""
噪音过滤配置文件

用于配置低流动性股票的过滤规则
"""

from dataclasses import dataclass, field
from typing import Set, Dict, Any
import json
import os

# 默认配置文件路径
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.naja/noise_filter_config.json")


@dataclass
class NoiseFilterUserConfig:
    """用户可配置的噪音过滤设置"""
    
    # 最小成交金额（元）- 低于此值视为噪音
    min_amount: float = 1_000_000  # 100万
    
    # 最小成交量（股）- 低于此值视为噪音
    min_volume: float = 100_000  # 10万股
    
    # 最小价格（元）
    min_price: float = 1.0
    
    # 是否启用动态阈值
    dynamic_threshold: bool = True
    
    # 动态阈值百分比（低于市场中位数X%视为噪音）
    dynamic_percentile: float = 5.0
    
    # 是否过滤B股
    filter_b_shares: bool = True
    
    # 是否过滤ST股票
    filter_st: bool = False
    
    # 黑名单 - 强制过滤的股票代码
    blacklist: Set[str] = field(default_factory=set)
    
    # 白名单 - 保护不被过滤的股票代码
    whitelist: Set[str] = field(default_factory=set)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'min_amount': self.min_amount,
            'min_volume': self.min_volume,
            'min_price': self.min_price,
            'dynamic_threshold': self.dynamic_threshold,
            'dynamic_percentile': self.dynamic_percentile,
            'filter_b_shares': self.filter_b_shares,
            'filter_st': self.filter_st,
            'blacklist': list(self.blacklist),
            'whitelist': list(self.whitelist),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NoiseFilterUserConfig':
        """从字典创建"""
        return cls(
            min_amount=data.get('min_amount', 1_000_000),
            min_volume=data.get('min_volume', 100_000),
            min_price=data.get('min_price', 1.0),
            dynamic_threshold=data.get('dynamic_threshold', True),
            dynamic_percentile=data.get('dynamic_percentile', 5.0),
            filter_b_shares=data.get('filter_b_shares', True),
            filter_st=data.get('filter_st', False),
            blacklist=set(data.get('blacklist', [])),
            whitelist=set(data.get('whitelist', [])),
        )


def load_noise_filter_config(config_path: str = None) -> NoiseFilterUserConfig:
    """
    加载噪音过滤配置
    
    Args:
        config_path: 配置文件路径，默认使用 ~/.naja/noise_filter_config.json
        
    Returns:
        噪音过滤配置对象
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return NoiseFilterUserConfig.from_dict(data)
        except Exception as e:
            print(f"加载噪音过滤配置失败: {e}，使用默认配置")
    
    return NoiseFilterUserConfig()


def save_noise_filter_config(config: NoiseFilterUserConfig, config_path: str = None):
    """
    保存噪音过滤配置
    
    Args:
        config: 噪音过滤配置对象
        config_path: 配置文件路径
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH
    
    # 确保目录存在
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存噪音过滤配置失败: {e}")


# 预定义的常见低流动性股票黑名单（可根据需要扩展）
DEFAULT_BLACKLIST = {
    # B股示例（南玻Ｂ等）
    # '200012',  # 南玻Ｂ
    # '200413',  # 东旭Ｂ
    # 添加更多已知的低流动性股票...
}


def get_default_noise_filter_config() -> NoiseFilterUserConfig:
    """获取默认噪音过滤配置"""
    config = NoiseFilterUserConfig()
    config.blacklist.update(DEFAULT_BLACKLIST)
    return config
