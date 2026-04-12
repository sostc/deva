# ── 转发 shim ──────────────────────────────────────────
# 此文件已迁移到 cognition/semantic/news_event.py
# 保留此 shim 以兼容外部 from deva.naja.cognition.news_event import ...
from .semantic.news_event import *  # noqa: F401,F403
from .semantic.news_event import NewsEvent, SignalType, DATASOURCE_TYPE_MAP, get_datasource_type  # noqa: F401
