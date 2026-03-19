"""
Naja Attention Scheduling System 配置模块

支持通过配置文件或环境变量配置注意力系统
"""

import os
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class NoiseFilterConfig:
    """噪音过滤配置"""
    # 主开关
    enabled: bool = True
    
    # 流动性阈值
    min_amount: float = 1_000_000      # 最小成交金额（元）
    min_volume: float = 100_000        # 最小成交量（股）
    min_price: float = 1.0             # 最小价格
    max_price: float = 1000.0          # 最大价格
    
    # 价格异常阈值
    max_price_change_pct: float = 20.0     # 最大价格变动%（跳变检测）
    flat_threshold: float = 0.5            # 横盘振幅阈值%
    flat_consecutive_frames: int = 10      # 连续横盘帧数
    
    # 交易行为阈值
    wash_trading_volume_ratio: float = 3.0     # 成交量突增倍数
    wash_trading_price_change_max: float = 0.5 # 对敲时最大价格变动%
    abnormal_volatility_threshold: float = 10.0 # 异常波动阈值%
    
    # 特殊股票过滤
    filter_b_shares: bool = True       # 过滤B股
    filter_st: bool = False            # 过滤ST股
    
    # 黑白名单
    blacklist: list = field(default_factory=list)
    whitelist: list = field(default_factory=list)


@dataclass
class NajaAttentionConfig:
    """
    Naja 注意力系统配置
    
    可以通过以下方式配置：
    1. 环境变量 (前缀: NAJA_ATTENTION_)
    2. 配置文件 (naja_attention.yaml)
    3. 代码中直接设置
    """
    
    # 主开关
    enabled: bool = True
    
    # 全局注意力配置
    global_history_window: int = 20
    
    # 板块注意力配置
    max_sectors: int = 100
    sector_decay_half_life: float = 300.0  # 秒
    
    # 权重池配置
    max_symbols: int = 5000
    
    # 频率调度配置
    low_interval: float = 60.0      # 低频间隔（秒）
    medium_interval: float = 10.0   # 中频间隔（秒）
    high_interval: float = 1.0      # 高频间隔（秒）
    
    # 双引擎配置
    river_history_window: int = 20
    pytorch_max_concurrent: int = 10
    pytorch_batch_size: int = 32
    
    # 噪音过滤配置
    noise_filter: NoiseFilterConfig = field(default_factory=NoiseFilterConfig)
    
    # 监控配置
    enable_monitoring: bool = True
    report_interval: float = 60.0   # 报告间隔（秒）
    
    # 调试配置
    debug_mode: bool = False
    log_level: str = "INFO"
    
    @classmethod
    def from_env(cls) -> "NajaAttentionConfig":
        """从环境变量加载配置"""
        config = cls()
        
        # 主开关
        config.enabled = os.getenv("NAJA_ATTENTION_ENABLED", "true").lower() == "true"
        
        # 数值配置
        config.global_history_window = int(os.getenv("NAJA_ATTENTION_GLOBAL_WINDOW", "20"))
        config.max_sectors = int(os.getenv("NAJA_ATTENTION_MAX_SECTORS", "100"))
        config.max_symbols = int(os.getenv("NAJA_ATTENTION_MAX_SYMBOLS", "5000"))
        
        config.low_interval = float(os.getenv("NAJA_ATTENTION_LOW_INTERVAL", "60.0"))
        config.medium_interval = float(os.getenv("NAJA_ATTENTION_MEDIUM_INTERVAL", "10.0"))
        config.high_interval = float(os.getenv("NAJA_ATTENTION_HIGH_INTERVAL", "1.0"))
        
        config.pytorch_max_concurrent = int(os.getenv("NAJA_ATTENTION_PYTORCH_CONCURRENT", "10"))
        config.report_interval = float(os.getenv("NAJA_ATTENTION_REPORT_INTERVAL", "60.0"))
        
        # 布尔配置
        config.enable_monitoring = os.getenv("NAJA_ATTENTION_ENABLE_MONITORING", "true").lower() == "true"
        config.debug_mode = os.getenv("NAJA_ATTENTION_DEBUG", "false").lower() == "true"
        
        # 字符串配置
        config.log_level = os.getenv("NAJA_ATTENTION_LOG_LEVEL", "INFO")
        
        # 噪音过滤配置
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
        from naja_attention_system import AttentionSystemConfig
        
        return AttentionSystemConfig(
            global_history_window=self.global_history_window,
            max_sectors=self.max_sectors,
            sector_decay_half_life=self.sector_decay_half_life,
            max_symbols=self.max_symbols,
            low_interval=self.low_interval,
            medium_interval=self.medium_interval,
            high_interval=self.high_interval,
            river_history_window=self.river_history_window,
            pytorch_max_concurrent=self.pytorch_max_concurrent
        )
    
    def __str__(self) -> str:
        return f"""NajaAttentionConfig(
    enabled={self.enabled},
    max_sectors={self.max_sectors},
    max_symbols={self.max_symbols},
    intervals=[{self.high_interval}s/{self.medium_interval}s/{self.low_interval}s],
    monitoring={self.enable_monitoring}
)"""


# 默认配置实例
default_config = NajaAttentionConfig()


def load_config() -> NajaAttentionConfig:
    """
    加载配置
    
    优先级：环境变量 > 配置文件 > 默认值
    """
    # 首先尝试从环境变量加载
    config = NajaAttentionConfig.from_env()
    
    # 然后尝试从配置文件加载（如果存在）
    try:
        config_file = os.path.expanduser("~/.naja/attention_config.yaml")
        if os.path.exists(config_file):
            import yaml
            with open(config_file, 'r') as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    # 处理顶层配置
                    for key, value in file_config.items():
                        if key == 'noise_filter' and isinstance(value, dict):
                            # 特殊处理噪音过滤配置
                            for nf_key, nf_value in value.items():
                                if hasattr(config.noise_filter, nf_key):
                                    setattr(config.noise_filter, nf_key, nf_value)
                        elif hasattr(config, key):
                            setattr(config, key, value)
    except Exception as e:
        logging.getLogger(__name__).debug(f"加载配置文件失败: {e}")
    
    return config