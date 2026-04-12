"""默认代码模板和工具函数"""

from datetime import datetime
from typing import Optional


DEFAULT_DS_CODE = '''# 数据获取函数
# 必须定义 fetch_data() 函数，返回获取的数据
# 返回 None 表示本次无数据

def fetch_data():
    import time
    return {
        "timestamp": time.time(),
        "value": 42,
        "message": "Hello from data source"
    }
'''

DEFAULT_FILE_DS_CODE = '''# 文件数据源处理函数
# 参数: line - 文件中的一行内容（或自定义分隔符分割的内容）
# 返回: 处理后的数据，返回 None 则跳过

def fetch_data(line):
    """
    处理文件中的一行数据
    line: 文件中的一行内容
    返回处理后的数据，返回 None 则跳过该行
    """
    # 示例：直接返回行内容
    if line and line.strip():
        return {"content": line.strip()}
    return None
'''

DEFAULT_DIRECTORY_DS_CODE = '''# 目录监控数据源处理函数
# 参数: event - 目录事件对象
# 返回: 处理后的数据，返回 None 则跳过

def fetch_data(event):
    """
    处理目录变化事件
    event: {
        "event": "created" | "modified" | "deleted",
        "path": "文件完整路径",
        "file_info": {"path": ..., "name": ..., "size": ..., "mtime": ...},
        "old_info": {...}  # 仅 modified 事件有
    }
    返回处理后的数据，返回 None 则跳过该事件
    """
    import os
    from datetime import datetime
    
    event_type = event.get("event")
    file_info = event.get("file_info", {})
    
    return {
        "event_type": event_type,
        "file_path": event.get("path"),
        "file_name": file_info.get("name"),
        "file_size": file_info.get("size"),
        "timestamp": datetime.now().isoformat(),
    }
'''


def _fmt_ts_short(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")


def _humanize_cron(expr: str) -> str:
    """将 cron 表达式转换为人类可读描述（使用共享函数）"""
    from deva.naja.scheduler.ui import humanize_cron
    return humanize_cron(expr)


def _parse_hhmm(value: str) -> Optional[tuple]:
    raw = str(value or "").strip().replace("：", ":")
    parts = raw.split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except Exception:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour, minute


def _preview_next_runs(cron_expr: str, count: int = 5) -> list:
    try:
        from apscheduler.triggers.cron import CronTrigger
        import pytz
    except Exception:
        return []
    try:
        trigger = CronTrigger.from_crontab(str(cron_expr or "").strip(), timezone=pytz.timezone("Asia/Shanghai"))
        out = []
        now = datetime.now(pytz.timezone("Asia/Shanghai"))
        prev = None
        current = now
        for _ in range(max(1, count)):
            nxt = trigger.get_next_fire_time(prev, current)
            if not nxt:
                break
            out.append(nxt.strftime("%Y-%m-%d %H:%M:%S"))
            prev = nxt
            current = nxt
        return out
    except Exception:
        return []


def _get_replay_tables():
    """获取可用的回放表列表"""
    try:
        from deva import NB
        temp_db = NB('temp')
        tables = temp_db.tables
        replay_tables = []
        for table in tables:
            if table.startswith("ds_") or table.startswith("data_") or table.startswith("quant_") or "_stream" in table or "snapshot" in table:
                try:
                    db = NB(table)
                    count = len(list(db.keys()))
                    if count > 0:
                        replay_tables.append({"name": table, "count": count})
                except Exception:
                    pass
        return replay_tables
    except Exception:
        return []


def _get_source_type_options() -> list:
    """获取启用的数据源类型选项"""
    from deva.naja.config import get_enabled_datasource_types

    all_types = {
        "timer": {"label": "⏱️ 定时器 - 定时执行代码获取数据", "value": "timer"},
        "stream": {"label": "📡 命名流 - 从命名总线订阅数据", "value": "stream"},
        "http": {"label": "🌐 HTTP服务 - 通过HTTP接口获取数据", "value": "http"},
        "kafka": {"label": "📨 Kafka - 从Kafka消息队列消费数据", "value": "kafka"},
        "redis": {"label": "🗄️ Redis - 从Redis订阅或拉取数据", "value": "redis"},
        "tcp": {"label": "🔌 TCP端口 - 监听TCP端口接收数据", "value": "tcp"},
        "file": {"label": "📄 文件 - 监控文件变化读取数据", "value": "file"},
        "directory": {"label": "📂 目录 - 监控目录中文件变化", "value": "directory"},
        "custom": {"label": "⚙️ 自定义代码 - 执行自定义代码获取数据", "value": "custom"},
        "replay": {"label": "📼 数据回放 - 从历史数据表中回放数据", "value": "replay"},
    }

    enabled_types = get_enabled_datasource_types()
    return [all_types[t] for t in enabled_types if t in all_types]
