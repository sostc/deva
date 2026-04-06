"""
Merrill Clock Module - 美林时钟系统

优雅的四象限经济周期判断引擎，为ManasEngine提供宏观经济信号。

📊 核心功能：
- 经济周期阶段判断（复苏/过热/滞胀/衰退）
- 宏观经济信号生成（0-1，用于ManasEngine）
- 资产配置建议（股票/商品/现金/债券）
- 实时经济数据获取与处理

🔄 工作流：
宏观经济数据 → 时钟引擎判断 → 适配器转换 → ManasEngine决策
"""

from .engine import (
    initialize_merrill_clock,
    get_merrill_clock_engine,
    MerrillClockPhase,
    EconomicData,
    PhaseSignal,
    MerrillClockEngine,
)

from .adapter import (
    get_merrill_macro_signal,
    get_merrill_phase_display,
)

from .ui.web_ui import render_merrill_clock_page

initialize = initialize_merrill_clock
get_engine = get_merrill_clock_engine
get_macro_signal = get_merrill_macro_signal

__all__ = [
    "initialize",
    "initialize_merrill_clock",
    "get_engine",
    "get_merrill_clock_engine",
    "MerrillClockPhase",
    "EconomicData",
    "PhaseSignal",
    "MerrillClockEngine",
    "get_macro_signal",
    "get_merrill_macro_signal",
    "get_merrill_phase_display",
    "render_merrill_clock_page",
]