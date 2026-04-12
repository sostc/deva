"""
NewsEvent - 新闻事件数据结构

从 core.py 提取，包含：
- DATASOURCE_TYPE_MAP: 数据源类型映射表
- get_datasource_type: 根据数据源名称获取数据类型
- NewsEvent: 龙虾事件结构（dataclass）
"""

import time
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class SignalType(Enum):
    """Cognition 信号类型

    命名规范：
    - topic_: 话题相关信号
    - narrative_: 叙事相关信号
    """
    TOPIC_EMERGE = "topic_emerge"
    TOPIC_GROW = "topic_grow"
    TOPIC_FADE = "topic_fade"
    TOPIC_HIGH_ATTENTION = "topic_high_attention"
    TOPIC_TREND_SHIFT = "topic_trend_shift"
    NARRATIVE_DRIFT = "narrative_drift"

    @classmethod
    def get_all_signal_types(cls) -> List[str]:
        """获取所有信号类型"""
        return [s.value for s in cls]

    @classmethod
    def is_topic_signal(cls, signal_type: str) -> bool:
        """判断是否为话题信号"""
        return signal_type.startswith("topic_")

    @classmethod
    def is_narrative_signal(cls, signal_type: str) -> bool:
        """判断是否为叙事信号"""
        return signal_type.startswith("narrative_")


# 数据源类型映射表 - 根据数据源名称识别数据类型
DATASOURCE_TYPE_MAP = {
    # 新闻数据源
    "财经新闻模拟源": "news",
    "新闻": "news",
    "news": "news",
    "金十数据快讯": "news",
    "金十": "news",
    "jin10": "news",
    # 行情数据源
    "行情回放": "tick",
    "tick": "tick",
    "quant": "tick",
    "realtime_quant_5s": "tick",
    # 日志数据源
    "系统日志监控": "log",
    "日志": "log",
    "log": "log",
    # 文件/目录数据源
    "下载目录监控": "file",
    "文件": "file",
    "file": "file",
    "目录": "file",
}


def get_datasource_type(source_name: str) -> str:
    """
    根据数据源名称获取数据类型

    Args:
        source_name: 数据源名称

    Returns:
        数据类型: news/tick/log/file/text
    """
    if not source_name:
        return "text"

    # 精确匹配
    if source_name in DATASOURCE_TYPE_MAP:
        return DATASOURCE_TYPE_MAP[source_name]

    # 模糊匹配 - 检查数据源名称是否包含关键字
    source_lower = source_name.lower()
    for key, dtype in DATASOURCE_TYPE_MAP.items():
        if key.lower() in source_lower:
            return dtype

    # 默认类型
    return "text"


@dataclass
class NewsEvent:
    """龙虾事件结构"""
    id: str
    timestamp: datetime
    source: str                          # 数据源标识
    event_type: str                      # tick/news/text/thought
    content: str                         # 文本内容
    vector: Optional[List[float]] = None # 语义向量
    meta: Dict[str, Any] = field(default_factory=dict)
    attention_score: float = 0.0
    topic_id: Optional[int] = None

    @classmethod
    def from_datasource_record(cls, record) -> "NewsEvent":
        """从naja数据源记录创建事件"""
        import numpy as np

        # 处理 numpy 数组类型的数据
        if isinstance(record, np.ndarray):
            return cls(
                id=hashlib.md5(f"array_{time.time()}".encode()).hexdigest()[:16],
                timestamp=datetime.now(),
                source="numpy_array",
                event_type="array",
                content=f"数组数据 shape={record.shape}",
                meta={"array_data": record.tolist(), "shape": record.shape}
            )

        # 处理非字典类型
        if not isinstance(record, dict):
            return cls(
                id=hashlib.md5(f"raw_{time.time()}".encode()).hexdigest()[:16],
                timestamp=datetime.now(),
                source="unknown",
                event_type="text",
                content=str(record),
                meta={"raw_data": str(record)}
            )

        # 生成唯一ID
        # 优先使用 _datasource_name（多数据源模式），其次使用 source（单数据源模式）
        source = record.get('_datasource_name') or record.get('source', 'unknown')
        content = f"{record.get('timestamp')}|{source}|{str(record.get('data', ''))[:100]}"
        event_id = hashlib.md5(content.encode()).hexdigest()[:16]

        # 获取数据源类型
        ds_type = get_datasource_type(source)

        # 解析数据
        # 首先尝试从 record 中获取 data 字段
        raw_data = record.get('data', {})

        # 如果 record 本身包含 title（新闻数据格式），直接使用 record
        if isinstance(record, dict) and 'title' in record:
            raw_data = record

        # 处理不同类型的数据（numpy数组、字典、其他类型）
        if isinstance(raw_data, np.ndarray):
            # numpy数组转换为字典
            data = {"array_data": raw_data.tolist(), "shape": raw_data.shape}
            content = f"数组数据 shape={raw_data.shape}"
            event_type = 'array'
        elif isinstance(raw_data, dict):
            data = raw_data

            # 使用数据源类型映射来识别数据类型
            if ds_type == 'tick' or 'price' in str(data):
                event_type = 'tick'
                symbol = data.get('symbol', '')
                if symbol and symbol != 'UNKNOWN':
                    content = f"{symbol} 价格:{data.get('price', 0)} 成交量:{data.get('volume', 0)}"
                else:
                    content = f"行情 价格:{data.get('price', 0)} 成交量:{data.get('volume', 0)}"
            elif ds_type == 'news' or 'title' in data:
                # 新闻数据
                event_type = 'news'
                title = data.get('title', '')
                content_text = data.get('content', '')
                content = f"{title}\n{content_text}" if title else content_text
            elif ds_type == 'log':
                # 日志数据
                event_type = 'log'
                log_content = data.get('content', '')
                content = log_content if log_content else str(data)
            elif ds_type == 'file':
                # 文件/目录数据
                event_type = 'file'
                file_path = data.get('file_path', '') or data.get('path', '')
                event = data.get('event_type', '') or data.get('event', '')
                content = f"{event}: {file_path}" if event else (file_path if file_path else str(data))
            else:
                # 默认文本类型
                event_type = 'text'
                content = str(data)
        else:
            # 其他类型转为字符串
            data = {"raw_data": str(raw_data)}
            content = str(raw_data)
            event_type = ds_type if ds_type != 'text' else 'text'

        # 处理 timestamp 可能是 float 或 datetime 的情况
        ts = record.get('timestamp', datetime.now())
        if isinstance(ts, (int, float)):
            ts = datetime.fromtimestamp(ts)
        elif not isinstance(ts, datetime):
            ts = datetime.now()

        return cls(
            id=event_id,
            timestamp=ts,
            source=source,
            event_type=event_type,
            content=content,
            meta=data
        )
