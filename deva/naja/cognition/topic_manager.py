# ── 转发 shim ──────────────────────────────────────────
# 此文件已迁移到 cognition/semantic/topic_manager.py
# 保留此 shim 以兼容外部 from deva.naja.cognition.topic_manager import ...
from .semantic.topic_manager import *  # noqa: F401,F403
from .semantic.topic_manager import Topic, STOCK_RELEVANT_PREFIXES, STOCK_RELEVANT_SOURCES  # noqa: F401
