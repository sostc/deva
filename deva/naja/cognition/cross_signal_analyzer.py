# ── 转发 shim ──────────────────────────────────────────
# 此文件已迁移到 cognition/analysis/cross_signal_analyzer.py
# 保留此 shim 以兼容外部 from deva.naja.cognition.cross_signal_analyzer import ...
from .analysis.cross_signal_analyzer import *  # noqa: F401,F403
from .analysis.cross_signal_analyzer import (  # noqa: F401
    CrossSignalAnalyzer,
    ResonanceSignal,
    ResonanceType,
    SignalSource,
    NewsSignal,
    AttentionSnapshot,
    CognitionFeedback,
    get_cross_signal_analyzer,
)
