"""
Data Processing - 数据预处理

噪音过滤层：
- NoiseFilter: 个股级噪音过滤（主力，广泛使用）
- BlockNoiseDetector: 题材级噪音检测（主力，有自动黑名单统计）
- NoiseManager: 统一噪音管理接口（轻量封装，UI 层使用）

已清理：
- enhanced_noise_filter.py (死代码，已删除)
- tick_filter.py (死代码，已删除)
- market_time_utils.py (死代码，已删除)
- BlockNoiseConfig 重复定义 bug 已修复（以 block_noise_detector 中的为准）
"""

from .noise_filter import NoiseFilter, NoiseFilterConfig, get_noise_filter
from .block_noise_detector import (
    BlockNoiseDetector,
    BlockNoiseConfig,
    get_block_noise_detector,
    is_block_noise,
    filter_noise_blocks,
)
from .noise_manager import (
    NoiseManager,
    StockNoiseFilter,
    BlockNoiseFilter,
    StockNoiseConfig,
    get_noise_manager,
    is_stock_noise,
    is_block_noise as is_block_noise_manager,
    is_noise,
)

__all__ = [
    # 主力噪音过滤
    "NoiseFilter",
    "NoiseFilterConfig",
    "get_noise_filter",
    # 题材噪音检测
    "BlockNoiseDetector",
    "BlockNoiseConfig",  # 来自 block_noise_detector（权威定义）
    "get_block_noise_detector",
    "is_block_noise",
    "filter_noise_blocks",
    # 统一噪音管理
    "NoiseManager",
    "StockNoiseFilter",
    "BlockNoiseFilter",
    "StockNoiseConfig",
    "get_noise_manager",
    "is_stock_noise",
    "is_block_noise_manager",
    "is_noise",
]
