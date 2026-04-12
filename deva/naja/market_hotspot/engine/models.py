"""
引擎数据模型

双引擎系统的公共枚举和数据类。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict


class AnomalyLevel(Enum):
    """异常等级"""
    NORMAL = 0
    WEAK = 1      # 弱异常
    STRONG = 2    # 强异常


@dataclass
class AnomalySignal:
    """异常信号"""
    symbol: str
    anomaly_score: float
    anomaly_level: AnomalyLevel
    features: Dict[str, float]
    timestamp: float


@dataclass
class PatternSignal:
    """模式识别信号"""
    symbol: str
    pattern_score: float
    pattern_type: str
    confidence: float
    timestamp: float
