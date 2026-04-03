"""
MerrillClockToManas - 美林时钟信号到 Manas 的适配层

功能：
1. 将美林时钟的周期信号转换为 Manas 能理解的宏观信号
2. 提供 get_merrill_macro_signal() 供 RegimeEngine 调用

美林时钟 → macro_signal 映射逻辑：
- 复苏：增长正向，通胀偏低 → 宏观偏松，macro_signal = 0.65
- 过热：增长正向，通胀偏高 → 宏观偏紧，macro_signal = 0.35
- 滞胀：增长负向，通胀偏高 → 宏观最紧，macro_signal = 0.25
- 衰退：增长负向，通胀偏低 → 宏观宽松，macro_signal = 0.60
"""

import logging
from typing import Optional

from .merrill_clock_engine import MerrillClockPhase

log = logging.getLogger(__name__)

# 美林时钟四阶段到 macro_signal 的映射
MERRILL_TO_MACRO = {
    MerrillClockPhase.RECOVERY: 0.65,     # 复苏：宽松
    MerrillClockPhase.OVERHEAT: 0.35,    # 过热：收紧
    MerrillClockPhase.STAGFLATION: 0.25, # 滞胀：最紧
    MerrillClockPhase.RECESSION: 0.60,    # 衰退：宽松
}


def get_merrill_macro_signal(
    growth_score: Optional[float] = None,
    inflation_score: Optional[float] = None,
    phase: Optional[MerrillClockPhase] = None,
    confidence: float = 1.0,
    base_macro: float = 0.5,
) -> float:
    """
    将美林时钟信号转换为 macro_signal
    
    Args:
        growth_score: 增长评分 [-1, 1]
        inflation_score: 通胀评分 [-1, 1]
        phase: 美林时钟阶段（优先使用）
        confidence: 置信度 [0, 1]
        base_macro: 基础宏观信号（无美林数据时使用）
    
    Returns:
        macro_signal [0, 1]，用于 Manas RegimeEngine
    """
    # 如果有阶段信息，直接查表
    if phase is not None:
        base_signal = MERRILL_TO_MACRO.get(phase, 0.5)
        # 根据置信度调整（置信度低时，向中性回归）
        adjusted = base_signal * confidence + 0.5 * (1 - confidence)
        return max(0.0, min(1.0, adjusted))
    
    # 如果没有阶段，但有评分数据
    if growth_score is not None and inflation_score is not None:
        # 增长正向 → 信号宽松（>0.5）
        # 通胀正向 → 信号收紧（<0.5）
        # 两者结合
        growth_signal = (growth_score + 1) / 2  # [-1,1] → [0,1]
        inflation_signal = (inflation_score + 1) / 2  # [-1,1] → [0,1]
        
        # 宏观信号：增长利好 - 通胀利空
        base_signal = (growth_signal * 0.6 + (1 - inflation_signal) * 0.4)
        
        adjusted = base_signal * confidence + 0.5 * (1 - confidence)
        return max(0.0, min(1.0, adjusted))
    
    return base_macro


def get_merrill_phase_display(phase: Optional[MerrillClockPhase]) -> str:
    """获取阶段的中文显示"""
    if phase is None:
        return "未知"
    phase_names = {
        MerrillClockPhase.RECOVERY: "复苏",
        MerrillClockPhase.OVERHEAT: "过热",
        MerrillClockPhase.STAGFLATION: "滞胀",
        MerrillClockPhase.RECESSION: "衰退",
    }
    return phase_names.get(phase, "未知")
