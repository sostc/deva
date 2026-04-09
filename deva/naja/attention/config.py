"""
Naja Attention System Configuration - 注意力系统配置模块

支持通过配置文件或环境变量配置注意力系统

职责:
- MarketHotspotConfig: Naja注意力系统主配置
- NoiseFilterConfig: 噪音过滤配置
- load_config(): 配置加载入口
- get_intelligence_config(): 智能增强系统配置
"""

import os
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class NoiseFilterConfig:
    """噪音过滤配置"""
    enabled: bool = True
    min_amount: float = 1_000_000
    min_volume: float = 100_000
    min_price: float = 1.0
    max_price: float = 1000.0
    max_price_change_pct: float = 20.0
    flat_threshold: float = 0.5
    flat_consecutive_frames: int = 10
    wash_trading_volume_ratio: float = 3.0
    wash_trading_price_change_max: float = 0.5
    abnormal_volatility_threshold: float = 10.0
    filter_b_shares: bool = True
    filter_st: bool = False
    blacklist: list = field(default_factory=list)
    whitelist: list = field(default_factory=list)


@dataclass
class MarketHotspotConfig:
    """
    Naja 注意力系统配置

    可以通过以下方式配置：
    1. 环境变量 (前缀: NAJA_ATTENTION_)
    2. 配置文件 (naja_attention.yaml)
    3. 代码中直接设置
    """

    enabled: bool = True
    global_history_window: int = 20
    max_blocks: int = 5000
    block_decay_half_life: float = 300.0
    max_symbols: int = 5000
    low_interval: float = 60.0
    medium_interval: float = 10.0
    high_interval: float = 1.0
    river_history_window: int = 20
    pytorch_max_concurrent: int = 10
    pytorch_batch_size: int = 32
    noise_filter: NoiseFilterConfig = field(default_factory=NoiseFilterConfig)
    enable_monitoring: bool = True
    report_interval: float = 60.0
    debug_mode: bool = False
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "MarketHotspotConfig":
        """从环境变量加载配置"""
        config = cls()

        config.enabled = os.getenv("NAJA_ATTENTION_ENABLED", "true").lower() == "true"
        config.global_history_window = int(os.getenv("NAJA_ATTENTION_GLOBAL_WINDOW", "20"))
        config.max_blocks = int(os.getenv("NAJA_ATTENTION_MAX_BLOCKS", "5000"))
        config.max_symbols = int(os.getenv("NAJA_ATTENTION_MAX_SYMBOLS", "5000"))
        config.block_decay_half_life = float(
            os.getenv("NAJA_ATTENTION_BLOCK_DECAY_HALF_LIFE", "300.0")
        )

        config.low_interval = float(os.getenv("NAJA_ATTENTION_LOW_INTERVAL", "60.0"))
        config.medium_interval = float(os.getenv("NAJA_ATTENTION_MEDIUM_INTERVAL", "10.0"))
        config.high_interval = float(os.getenv("NAJA_ATTENTION_HIGH_INTERVAL", "1.0"))

        config.pytorch_max_concurrent = int(os.getenv("NAJA_ATTENTION_PYTORCH_CONCURRENT", "10"))
        config.report_interval = float(os.getenv("NAJA_ATTENTION_REPORT_INTERVAL", "60.0"))

        config.enable_monitoring = os.getenv("NAJA_ATTENTION_ENABLE_MONITORING", "true").lower() == "true"
        config.debug_mode = os.getenv("NAJA_ATTENTION_DEBUG", "false").lower() == "true"
        config.log_level = os.getenv("NAJA_ATTENTION_LOG_LEVEL", "INFO")

        nf = config.noise_filter
        nf.enabled = os.getenv("NAJA_NOISE_FILTER_ENABLED", "true").lower() == "true"
        nf.min_amount = float(os.getenv("NAJA_NOISE_MIN_AMOUNT", "1000000"))
        nf.min_volume = float(os.getenv("NAJA_NOISE_MIN_VOLUME", "100000"))
        nf.min_price = float(os.getenv("NAJA_NOISE_MIN_PRICE", "1.0"))
        nf.max_price = float(os.getenv("NAJA_NOISE_MAX_PRICE", "1000.0"))
        nf.filter_b_shares = os.getenv("NAJA_NOISE_FILTER_B_SHARES", "true").lower() == "true"
        nf.filter_st = os.getenv("NAJA_NOISE_FILTER_ST", "false").lower() == "true"

        return config

    def to_attention_system_config(self):
        """转换为 AttentionSystemConfig"""
        from deva.naja.market_hotspot.integration.market_hotspot_system import MarketHotspotSystemConfig as AttentionSystemConfig
        return AttentionSystemConfig(
            global_history_window=self.global_history_window,
            max_blocks=self.max_blocks,
            block_decay_half_life=self.block_decay_half_life,
            max_symbols=self.max_symbols,
            low_interval=self.low_interval,
            medium_interval=self.medium_interval,
            high_interval=self.high_interval,
            river_history_window=self.river_history_window,
            pytorch_max_concurrent=self.pytorch_max_concurrent
        )

    def __str__(self) -> str:
        return f"""MarketHotspotConfig(
    enabled={self.enabled},
    max_blocks={self.max_blocks},
    max_symbols={self.max_symbols},
    intervals=[{self.high_interval}s/{self.medium_interval}s/{self.low_interval}s],
    monitoring={self.enable_monitoring}
)"""


default_config = MarketHotspotConfig()


def load_config() -> MarketHotspotConfig:
    """
    加载配置

    优先级：环境变量 > 配置文件 > 默认值
    """
    config = MarketHotspotConfig.from_env()

    try:
        config_file = os.path.expanduser("~/.naja/attention_config.yaml")
        if os.path.exists(config_file):
            import yaml
            with open(config_file, 'r') as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    for key, value in file_config.items():
                        if key == 'noise_filter' and isinstance(value, dict):
                            for nf_key, nf_value in value.items():
                                if hasattr(config.noise_filter, nf_key):
                                    setattr(config.noise_filter, nf_key, nf_value)
                        elif hasattr(config, key):
                            setattr(config, key, value)
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"加载配置文件失败: {e}")

    return config


def get_intelligence_config() -> dict:
    """
    获取智能增强系统配置

    使用统一的 config 系统: deva.config

    默认启用:
    - enable_predictive: True (预测注意力)
    - enable_feedback: True (注意力反馈学习)
    - enable_budget: True (预算系统)
    - enable_strategy_learning: True (策略学习)
    """
    from deva import config

    intelligence_enabled = config.get('attention_intelligence.enabled', True)

    intelligence_config = {
        'enable_predictive': config.get('attention_intelligence.predictive', True),
        'enable_feedback': config.get('attention_intelligence.feedback', True),
        'enable_budget': config.get('attention_intelligence.budget', True),
        'enable_propagation': config.get('attention_intelligence.propagation', True),
        'enable_strategy_learning': config.get('attention_intelligence.strategy_learning', True),
    }

    if not intelligence_enabled:
        return {}

    has_any = any(intelligence_config.values())
    if not has_any:
        return {}

    return intelligence_config
