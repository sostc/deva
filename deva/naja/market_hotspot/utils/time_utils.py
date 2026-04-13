"""时间格式化工具模块

提供跨层共享的时间处理函数，不依赖任何特定层次的模块。
"""

import pytz
from datetime import datetime


def format_next_time(raw_time: str) -> str:
    """格式化下一次交易时间（用于显示）

    将美东时间或北京时间的时间戳格式化为 HH:MM 或 次日HH:MM 格式

    Parameters
    ----------
    raw_time : str
        ISO 格式的时间字符串，如 '2026-04-13T09:30:00-04:00'

    Returns
    -------
    str
        格式化后的时间，如 '09:30' 或 '次日09:30'
    """
    if not raw_time:
        return ""
    try:
        local_tz = pytz.timezone("Asia/Shanghai")

        raw_time_clean = raw_time.replace('Z', '+00:00')
        dt = datetime.fromisoformat(raw_time_clean)

        if dt.tzinfo is not None:
            utc_offset = dt.utcoffset()
            if utc_offset is not None:
                offset_hours = utc_offset.total_seconds() / 3600
                if -6 <= offset_hours <= -4:
                    dt_local = dt.astimezone(local_tz)
                elif 7 <= offset_hours <= 9:
                    dt_local = dt.astimezone(local_tz)
                else:
                    dt_local = dt.astimezone(local_tz)
            else:
                dt_local = dt.astimezone(local_tz)
        else:
            dt_local = local_tz.localize(dt)

        now_local = datetime.now(local_tz)
        if dt_local.date() != now_local.date():
            return dt_local.strftime("次日%H:%M")
        return dt_local.strftime("%H:%M")
    except Exception:
        if "T" in raw_time:
            return raw_time.split("T")[1][:5]
        return raw_time


def _format_next_time(raw_time: str) -> str:
    """兼容性别名，建议使用 format_next_time"""
    return format_next_time(raw_time)
