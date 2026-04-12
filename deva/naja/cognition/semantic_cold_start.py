# ── 转发 shim ──────────────────────────────────────────
# 此文件已迁移到 cognition/semantic/semantic_cold_start.py
# 保留此 shim 以兼容外部 from deva.naja.cognition.semantic_cold_start import ...
from .semantic.semantic_cold_start import *  # noqa: F401,F403
from .semantic.semantic_cold_start import SemanticColdStart  # noqa: F401
