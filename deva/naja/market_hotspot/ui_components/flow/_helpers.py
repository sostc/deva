"""流式 UI 共享辅助函数"""

import logging
from typing import Dict, List, Any, Optional

log = logging.getLogger(__name__)

from deva.naja.infra.ui.ui_style import format_timestamp


def _fmt_ts(ts: float) -> str:
    """格式化时间戳（短格式：HH:MM:SS）"""
    return format_timestamp(ts, fmt="%H:%M:%S")


def _fmt_ts_full(ts: float) -> str:
    """格式化完整时间戳（微秒精度）"""
    if not ts:
        return "-"
    try:
        from datetime import datetime
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%H:%M:%S.%f")[:-3]
    except Exception:
        return str(ts)


def _safe_val(val, default="-"):
    """安全获取值"""
    if val is None:
        return default
    return val
