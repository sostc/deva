# ── 转发 shim ──────────────────────────────────────────
# 此文件已迁移到 cognition/semantic/attention_scorer.py
# 保留此 shim 以兼容外部 from deva.naja.cognition.attention_scorer import ...
from .semantic.attention_scorer import *  # noqa: F401,F403
from .semantic.attention_scorer import AttentionScorer  # noqa: F401
