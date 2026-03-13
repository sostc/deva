"""
事件统一结构 - 所有信息的标准化格式
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import hashlib


class EventType(Enum):
    """事件类型"""
    TICK = "tick"           # 行情数据
    NEWS = "news"           # 新闻
    TEXT = "text"           # 文本/笔记
    SIGNAL = "signal"       # 信号
    THOUGHT = "thought"     # 思想/思考
    SYSTEM = "system"       # 系统事件


@dataclass
class Event:
    """
    统一事件结构
    
    所有输入信息都转换为这个标准格式
    """
    # 基础字段
    time: datetime                          # 时间戳
    type: EventType                         # 事件类型
    source: str                             # 来源标识
    
    # 内容字段
    text: str                               # 文本内容
    vector: Optional[List[float]] = None    # 语义向量 (embedding)
    
    # 元数据
    meta: Dict[str, Any] = field(default_factory=dict)
    
    # 系统字段
    id: str = field(default="")            # 唯一ID (自动生成)
    attention_score: float = 0.0           # 注意力评分
    topic_id: Optional[int] = None         # 所属主题ID
    
    def __post_init__(self):
        """自动生成ID"""
        if not self.id:
            content = f"{self.time.isoformat()}|{self.type.value}|{self.text[:100]}"
            self.id = hashlib.md5(content.encode()).hexdigest()[:16]
    
    @classmethod
    def from_tick(cls, symbol: str, price: float, volume: float, 
                  timestamp: datetime, **kwargs) -> "Event":
        """从tick数据创建事件"""
        text = f"{symbol} 价格:{price} 成交量:{volume}"
        meta = {
            "symbol": symbol,
            "price": price,
            "volume": volume,
            "change_pct": kwargs.get("change_pct", 0),
        }
        meta.update(kwargs)
        
        return cls(
            time=timestamp,
            type=EventType.TICK,
            source=f"tick:{symbol}",
            text=text,
            meta=meta
        )
    
    @classmethod
    def from_news(cls, title: str, content: str, source: str,
                  timestamp: datetime, **kwargs) -> "Event":
        """从新闻创建事件"""
        text = f"{title}\n{content}"
        meta = {
            "title": title,
            "content": content,
            "news_source": source,
            "url": kwargs.get("url", ""),
        }
        meta.update(kwargs)
        
        return cls(
            time=timestamp,
            type=EventType.NEWS,
            source=f"news:{source}",
            text=text,
            meta=meta
        )
    
    @classmethod
    def from_text(cls, text: str, author: str = "user",
                  timestamp: Optional[datetime] = None, **kwargs) -> "Event":
        """从用户文本创建事件"""
        return cls(
            time=timestamp or datetime.now(),
            type=EventType.TEXT,
            source=f"user:{author}",
            text=text,
            meta=kwargs
        )
    
    @classmethod
    def from_thought(cls, thought: str, topic: str = "",
                     timestamp: Optional[datetime] = None, **kwargs) -> "Event":
        """从思想/思考创建事件"""
        meta = {"topic": topic}
        meta.update(kwargs)
        
        return cls(
            time=timestamp or datetime.now(),
            type=EventType.THOUGHT,
            source="thought",
            text=thought,
            meta=meta
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "time": self.time.isoformat(),
            "type": self.type.value,
            "source": self.source,
            "text": self.text,
            "vector": self.vector,
            "meta": self.meta,
            "attention_score": self.attention_score,
            "topic_id": self.topic_id,
        }
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)
    
    @property
    def is_high_attention(self) -> bool:
        """是否高注意力事件"""
        return self.attention_score >= 0.7
    
    def __repr__(self) -> str:
        return f"Event({self.type.value}, {self.source}, score={self.attention_score:.2f})"
