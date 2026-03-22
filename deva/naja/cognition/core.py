"""
新闻舆情雷达策略 - News Mind Radar Strategy

核心思想: 流式学习 + 分层记忆 + 周期性自我反思
作为naja策略系统的一个插件运行

输入: 绑定的数据源（tick、新闻、文本）
输出: 信号流（主题信号、注意力信号、趋势变化信号）
"""

import json
import time
import numpy as np
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import threading
import os

from .narrative_tracker import NarrativeTracker
from .semantic_cold_start import SemanticColdStart

# River流式学习库
try:
    from river import cluster
    from river import drift
    RIVER_AVAILABLE = True
except ImportError:
    RIVER_AVAILABLE = False
    print("[NewsRadar] Warning: river not installed, using fallback implementations")

# 持久化数据库
try:
    from deva import NB
    NAJA_DB_AVAILABLE = True
except ImportError:
    NAJA_DB_AVAILABLE = False
    print("[NewsRadar] Warning: NB not available, persistence disabled")


class SignalType(Enum):
    """信号类型"""
    TOPIC_EMERGE = "topic_emerge"       # 新主题出现
    TOPIC_GROW = "topic_grow"           # 主题增长
    TOPIC_FADE = "topic_fade"           # 主题消退
    HIGH_ATTENTION = "high_attention"   # 高注意力事件
    TREND_SHIFT = "trend_shift"         # 趋势转变
    DRIFT_DETECTED = "drift_detected"   # 检测到漂移


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
        import numpy as np
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
                content = f"{data.get('symbol', 'UNKNOWN')} 价格:{data.get('price', 0)} 成交量:{data.get('volume', 0)}"
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


STOCK_RELEVANT_PREFIXES = ["[新闻]", "[行情]", "[财经]"]
STOCK_RELEVANT_SOURCES = ["news", "tick", "jin10", "财经", "新闻", "金十", "行情"]


def _get_market_activity() -> float:
    """
    获取当前市场活跃度 (0.0 ~ 1.0)
    
    从 AttentionOrchestrator 获取 GlobalAttentionEngine 的 activity 值
    如果获取失败，返回 0.5（默认值）
    """
    try:
        from deva.naja.attention_orchestrator import AttentionOrchestrator
        orchestrator = AttentionOrchestrator()
        if hasattr(orchestrator, '_integration') and orchestrator._integration.attention_system:
            return orchestrator._integration.attention_system._last_activity
    except Exception:
        pass
    return 0.5  # 默认值

def _is_stock_relevant_topic(topic: "Topic") -> bool:
    """判断主题是否与股票相关"""
    name = topic.name if topic.name else ""

    for prefix in STOCK_RELEVANT_PREFIXES:
        if prefix in name:
            return True

    for source_keyword in STOCK_RELEVANT_SOURCES:
        if source_keyword in name:
            return True

    keywords = topic.keywords if topic.keywords else []
    stock_keywords = ["新能源", "半导体", "医药", "消费", "金融", "地产", "传媒", "军工", "AI", "芯片", "茅台", "宁德", "比亚迪"]
    for kw in keywords:
        if kw in stock_keywords:
            return True

    return False


@dataclass
class Topic:
    """主题结构"""
    id: int
    center: List[float]                    # 主题中心向量
    events: deque                           # 属于该主题的事件
    created_at: datetime
    last_updated: datetime
    attention_sum: float = 0.0             # 累计注意力
    event_count: int = 0
    name: str = ""                         # 主题名称（自动提取）
    keywords: List[str] = field(default_factory=list)  # 主题关键词
    
    def __post_init__(self):
        """初始化后自动命名"""
        if not self.name and self.events:
            self._auto_name()
    
    def _auto_name(self):
        """根据事件内容自动提取主题名称"""
        if not self.events:
            self.name = f"主题{self.id}"
            return

        # 获取数据源标识（强制在主题名称前加上数据源）
        first_event = self.events[0]
        source = getattr(first_event, 'source', 'unknown')

        # 使用数据源类型映射获取类型前缀
        ds_type = get_datasource_type(source)
        type_prefix_map = {
            'news': '[新闻]',
            'tick': '[行情]',
            'log': '[日志]',
            'file': '[文件]',
            'array': '[数组]',
            'text': '[文本]',
        }
        source_prefix = type_prefix_map.get(ds_type, f"[{source[:4]}]")

        # 收集所有事件的关键词
        all_keywords = []
        all_content = []

        for event in self.events:
            content = getattr(event, 'content', '')
            if content:
                all_content.append(content)
                content_lower = content.lower()

                # 提取公司名称
                companies = ["腾讯", "阿里", "字节", "华为", "比亚迪", "宁德时代", "茅台", "美团", "小米", "百度", "京东", "拼多多"]
                for company in companies:
                    if company in content:
                        all_keywords.append(company)

                # 提取行业关键词
                sectors = ["新能源", "半导体", "医药", "消费", "金融", "地产", "传媒", "军工", "AI", "芯片"]
                for sector in sectors:
                    if sector in content:
                        all_keywords.append(sector)

                # 提取日志级别和类型（针对日志数据源）
                if '日志' in source or 'log' in source.lower():
                    log_levels = ["ERROR", "WARN", "INFO", "DEBUG", "CRITICAL", "FATAL"]
                    for level in log_levels:
                        if level in content or level.lower() in content_lower:
                            all_keywords.append(level)

                    log_actions = ["启动", "停止", "失败", "成功", "超时", "重试", "连接", "断开", "创建", "删除"]
                    for action in log_actions:
                        if action in content:
                            all_keywords.append(action)

                # 提取文件操作
                if '文件' in source or 'file' in source.lower() or '目录' in source:
                    file_ops = ["创建", "修改", "删除", "下载", "上传", "移动", "复制"]
                    for op in file_ops:
                        if op in content:
                            all_keywords.append(op)

                    import re
                    file_exts = re.findall(r'\.([a-zA-Z0-9]+)', content)
                    for ext in file_exts[:3]:
                        all_keywords.append(f".{ext}")

        # 统计词频并生成主题名称
        from collections import Counter

        # 获取第一条内容用于提取主题
        first_content = all_content[0] if all_content else ''

        # 使用数据源类型映射来判断数据源类型
        ds_type = get_datasource_type(source)

        # 无意义名称模式
        meaningless_patterns = [
            "主题", "未命名", "未知", "无内容", "无标题",
            "array", "dict", "object", "none", "null"
        ]

        def is_meaningful_name(name: str) -> bool:
            """判断名称是否有意义"""
            if not name or len(name.strip()) < 2:
                return False
            name_lower = name.lower()
            for pattern in meaningless_patterns:
                if pattern.lower() in name_lower:
                    return False
            return True

        # 优先使用关键词生成名称
        if all_keywords:
            keyword_counts = Counter(all_keywords)
            top_keywords = [k for k, _ in keyword_counts.most_common(3)]
            keyword_name = "·".join(top_keywords)
            if is_meaningful_name(keyword_name):
                self.name = f"{source_prefix} {keyword_name}"
                self.keywords = top_keywords
                return

        # 针对不同数据源类型使用不同的主题提取策略
        extracted_name = ""
        if ds_type == 'news' and first_content:
            extracted_name = self._extract_news_topic(first_content)
        elif ds_type == 'tick' and first_content:
            extracted_name = self._extract_tick_topic(first_content)
        elif ds_type == 'log' and first_content:
            extracted_name = self._extract_log_topic(first_content)
        elif first_content:
            extracted_name = first_content[:20].strip()

        # 如果提取的名称无意义，尝试使用关键词
        if not is_meaningful_name(extracted_name):
            if all_keywords:
                keyword_counts = Counter(all_keywords)
                top_keywords = [k for k, _ in keyword_counts.most_common(3)]
                extracted_name = "·".join(top_keywords)

        # 最终检查
        if is_meaningful_name(extracted_name):
            self.name = f"{source_prefix} {extracted_name}"
        else:
            self.name = f"{source_prefix} 热点关注"
        self.keywords = [k for k, _ in Counter(all_keywords).most_common(5)] if all_keywords else []
    
    def _extract_news_topic(self, content: str) -> str:
        """从新闻内容中提取热点主题名称"""
        # 调试：打印接收到的内容
        print(f"[_extract_news_topic] 接收到的内容类型: {type(content)}, 内容: {content[:100] if content else 'None'}")
        
        if not content or not content.strip():
            return "未命名主题"
        
        # 清理内容
        content = content.strip()
        
        # 如果内容是字典的字符串表示，尝试提取其中的 title
        if content.startswith('{') and content.endswith('}'):
            try:
                import json
                import ast
                # 尝试解析为字典
                data = ast.literal_eval(content)
                if isinstance(data, dict):
                    title = data.get('title', '')
                    if title:
                        print(f"[_extract_news_topic] 从字典中提取到title: {title}")
                        return title[:25]
            except:
                pass
        
        # 尝试提取核心主题
        import re
        
        # 1. 提取引号内的内容
        quoted = re.findall(r'["""]([^"""]+)["""]', content)
        if quoted and quoted[0].strip():
            return quoted[0].strip()[:25]
        
        # 2. 提取书名号内的内容
        book_title = re.findall(r'《([^》]+)》', content)
        if book_title and book_title[0].strip():
            return book_title[0].strip()[:25]
        
        # 3. 提取冒号前的内容（通常是主体）
        if '：' in content or ':' in content:
            parts = re.split(r'[：:]', content)
            if parts and parts[0].strip():
                return parts[0].strip()[:25]
        
        # 4. 提取第一句话（以句号、感叹号、问号分隔）
        first_sentence = re.split(r'[。！？\n]', content)
        if first_sentence and first_sentence[0].strip():
            return first_sentence[0].strip()[:25]
        
        # 5. 提取前25个字符作为主题
        return content[:25].strip() if content else "未命名主题"
    
    def _extract_log_topic(self, content: str) -> str:
        """从日志内容中提取主题名称"""
        if not content or not content.strip():
            return "未命名日志"

        content = content.strip()

        # 如果内容是字典的字符串表示，尝试提取其中的 content
        if content.startswith('{') and content.endswith('}'):
            try:
                import ast
                data = ast.literal_eval(content)
                if isinstance(data, dict):
                    log_content = data.get('content', '')
                    if log_content:
                        return log_content[:20].strip()
            except:
                pass

        return content[:20].strip() if content else "未命名日志"

    def _extract_tick_topic(self, content: str) -> str:
        """从行情内容中提取主题名称"""
        if not content or not content.strip():
            return ""

        content = content.strip()

        # 尝试解析为字典提取 symbol 或 code
        if content.startswith('{') and content.endswith('}'):
            try:
                import ast
                data = ast.literal_eval(content)
                if isinstance(data, dict):
                    symbol = data.get('symbol', '') or data.get('code', '')
                    if symbol:
                        return f"行情 {symbol}"
            except:
                pass

        # 直接返回内容前15字符
        return content[:15].strip() if content else ""

    def update_name(self):
        """更新主题名称（当有新事件加入时）"""
        self._auto_name()
    
    @property
    def display_name(self) -> str:
        """显示名称"""
        return self.name if self.name else f"主题{self.id}"
    
    @property
    def avg_attention(self) -> float:
        """平均注意力"""
        if self.event_count == 0:
            return 0.0
        return self.attention_sum / self.event_count
    
    @property
    def growth_rate(self) -> float:
        """增长率（最近1小时 vs 之前）"""
        if self.event_count < 2:
            return 0.0
        
        one_hour_ago = datetime.now() - timedelta(hours=1)
        
        # 处理 timestamp 可能是 float 或 datetime 的情况
        recent = 0
        for e in self.events:
            if isinstance(e.timestamp, datetime):
                if e.timestamp > one_hour_ago:
                    recent += 1
            elif isinstance(e.timestamp, (int, float)):
                # float 时间戳与 datetime 比较需要转换
                from datetime import datetime as dt
                ts_datetime = dt.fromtimestamp(e.timestamp)
                if ts_datetime > one_hour_ago:
                    recent += 1
        
        older = self.event_count - recent
        
        if older == 0:
            return 1.0
        return (recent - older) / older


class AttentionScorer:
    """注意力评分器"""
    
    KEYWORDS = {
        "high": ["突破", "暴涨", "暴跌", "涨停", "跌停", "重大", "紧急", "突发",
                "AI", "人工智能", "算力", "芯片", "GPU", "英伟达", "OpenAI",
                "政策", "监管", "改革", "创新", "革命"],
        "medium": ["上涨", "下跌", "增长", "下降", "利好", "利空",
                   "技术", "产品", "发布", "合作", "收购", "并购"],
    }
    
    def __init__(self, history_size: int = 1000):
        self.history = deque(maxlen=history_size)
        self.recent_events = deque(maxlen=100)
    
    def score(self, event: NewsEvent) -> float:
        """计算注意力评分"""
        scores = {
            "novelty": self._novelty_score(event),
            "sentiment": self._sentiment_score(event),
            "market": self._market_score(event),
            "keywords": self._keyword_score(event),
            "velocity": self._velocity_score(event),
            "importance": self._importance_score(event),  # 新增：数据源标记的重要性
        }
        
        weights = {
            "novelty": 0.20,
            "sentiment": 0.12,
            "market": 0.20,
            "keywords": 0.15,
            "velocity": 0.13,
            "importance": 0.20,  # 数据源标记的重要性权重
        }
        
        total = sum(scores[k] * weights[k] for k in scores)
        
        self.history.append(event)
        self.recent_events.append({
            "time": event.timestamp,
            "type": event.event_type,
        })
        
        return min(1.0, max(0.0, total))

    def peek_score(self, event: NewsEvent) -> float:
        """计算注意力评分（不写入历史，用于预筛选）"""
        scores = {
            "novelty": self._novelty_score(event),
            "sentiment": self._sentiment_score(event),
            "market": self._market_score(event),
            "keywords": self._keyword_score(event),
            "velocity": self._velocity_score(event),
            "importance": self._importance_score(event),
        }
        weights = {
            "novelty": 0.20,
            "sentiment": 0.12,
            "market": 0.20,
            "keywords": 0.15,
            "velocity": 0.13,
            "importance": 0.20,
        }
        total = sum(scores[k] * weights[k] for k in scores)
        return min(1.0, max(0.0, total))
    
    def _importance_score(self, event: NewsEvent) -> float:
        """数据源标记的重要性评分
        
        如果数据源标记了 importance="high"，则直接给高分
        """
        # 从 meta 中获取 importance
        importance = event.meta.get('importance', '')
        
        if isinstance(importance, str):
            importance = importance.lower()
            if importance == 'high':
                return 1.0
            elif importance == 'medium':
                return 0.6
            elif importance == 'normal':
                return 0.3
        
        # 也检查 meta 中的其他可能字段
        if event.meta.get('important'):
            return 0.9
        
        return 0.0
    
    def _novelty_score(self, event: NewsEvent) -> float:
        """新颖度评分"""
        if not self.history or event.vector is None:
            return 0.5
        
        similarities = []
        for hist in self.history:
            if hist.vector is not None:
                sim = self._cosine_similarity(event.vector, hist.vector)
                similarities.append(sim)
        
        if not similarities:
            return 0.5
        
        return 1.0 - np.mean(similarities)
    
    def _sentiment_score(self, event: NewsEvent) -> float:
        """情绪强度评分"""
        text = event.content.lower()
        score = 0.0
        
        strong_words = ["暴涨", "涨停", "突破", "重大利好", "暴跌", "跌停", "崩盘", "危机"]
        for word in strong_words:
            if word in text:
                score += 0.3
        
        score += min(0.2, text.count("!") * 0.05)
        return min(1.0, score)
    
    def _market_score(self, event: NewsEvent) -> float:
        """市场波动评分"""
        if event.event_type != "tick":
            return 0.0
        
        meta = event.meta
        score = 0.0
        
        change_pct = meta.get("change_pct", 0)
        if abs(change_pct) > 10:
            score += 0.5
        elif abs(change_pct) > 5:
            score += 0.3
        elif abs(change_pct) > 2:
            score += 0.1
        
        return min(1.0, score)
    
    def _keyword_score(self, event: NewsEvent) -> float:
        """关键词评分"""
        text = event.content.lower()
        score = 0.0
        
        for keyword in self.KEYWORDS["high"]:
            if keyword.lower() in text:
                score += 0.25
        
        for keyword in self.KEYWORDS["medium"]:
            if keyword.lower() in text:
                score += 0.1
        
        return min(1.0, score)
    
    def _velocity_score(self, event: NewsEvent) -> float:
        """传播速度评分"""
        if not self.recent_events:
            return 0.0
        
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_count = sum(
            1 for e in self.recent_events
            if e["time"] > one_hour_ago and e["type"] == event.event_type
        )
        
        if recent_count > 20:
            return 1.0
        elif recent_count > 10:
            return 0.7
        elif recent_count > 5:
            return 0.4
        return 0.1
    
    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """余弦相似度"""
        v1, v2 = np.array(v1), np.array(v2)
        norm = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norm == 0:
            return 0.0
        return float(np.dot(v1, v2) / norm)


class NewsMindStrategy:
    """
    新闻心智策略 - News Mind Strategy

    作为naja策略系统的插件运行，驱动认知流水线：
    信号 → 注意力 → 记忆 → 洞察
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """初始化策略"""
        self.config = config or {}
        
        # 配置参数
        self.short_term_size = self.config.get("short_term_size", 1000)
        self.topic_threshold = self.config.get("topic_threshold", 0.5)  # 降低阈值，让新主题更容易创建
        self.attention_threshold = self.config.get("attention_threshold", 0.6)
        self.max_topics = self.config.get("max_topics", 50)
        self.enable_attention_filter = bool(self.config.get("attention_filter_enabled", True))
        self.base_attention_gate = float(self.config.get("attention_gate_base", 0.35))
        self.target_rate_per_min = float(self.config.get("target_rate_per_min", 30))
        self.rate_window_seconds = int(self.config.get("rate_window_seconds", 300))
        self.max_batch_keep = int(self.config.get("max_batch_keep", 80))
        
        # 核心组件
        self.attention_scorer = AttentionScorer(history_size=self.short_term_size)
        
        # 记忆系统 - 三层记忆架构
        self.short_memory: deque = deque(maxlen=self.short_term_size)  # 短期记忆：最近事件
        self.mid_memory: deque = deque(maxlen=5000)                    # 中期记忆：重要事件归档
        self.long_memory: List[Dict] = []                              # 长期记忆：周期性总结
        self.topics: Dict[int, Topic] = {}                            # 主题库
        self.topic_counter = 0
        
        # 记忆归档阈值
        self.mid_memory_threshold = self.config.get("mid_memory_threshold", 0.7)   # 注意力评分超过此值进入中期记忆
        self.long_memory_interval = self.config.get("long_memory_interval", 24)    # 小时，生成长期记忆的时间间隔
        self.last_long_memory_time = datetime.now() - timedelta(hours=24)
        
        # River组件
        if RIVER_AVAILABLE:
            # 使用River的在线聚类
            self.clustering = cluster.DBSTREAM(
                clustering_threshold=self.topic_threshold,
                fading_factor=self.config.get("fading_factor", 0.05),
                cleanup_interval=self.config.get("cleanup_interval", 10),
                intersection_factor=self.config.get("intersection_factor", 0.5),
            )
            # 漂移检测
            self.drift_detector = drift.ADWIN()
        else:
            self.clustering = None
            self.drift_detector = None
        
        # 统计信息
        self.stats = {
            "total_events": 0,
            "high_attention_events": 0,
            "topics_created": 0,
            "drifts_detected": 0,
            "filtered_events": 0,
        }

        # 频率控制
        self._rate_buckets: Dict[str, deque] = {}

        # 叙事追踪器
        self.narrative_tracker = NarrativeTracker(self.config)
        self.narrative_events: deque = deque(maxlen=200)

        # 语义冷启动（种子词 -> 语义图谱）
        self.semantic_cold_start = SemanticColdStart(self.config)
        self.semantic_graph: Dict[str, Any] = dict(self.semantic_cold_start.graph)
        
        # 缓存的市场活跃度（避免频繁查询）
        self._cached_market_activity: float = 0.5
        self._last_activity_update: float = 0.0
        self._activity_cache_ttl: float = 5.0  # 5秒缓存
    
    def _get_dynamic_mid_memory_threshold(self) -> float:
        """
        获取动态中期记忆阈值
        
        根据市场活跃度动态调整阈值：
        - 市场活跃时（activity > 0.6）：提高阈值，减少噪音
        - 市场平淡时（activity < 0.3）：降低阈值，保留更多信号
        - 市场温和时：使用默认值
        """
        now = time.time()
        
        # 每5秒更新一次缓存的市场活跃度
        if now - self._last_activity_update > self._activity_cache_ttl:
            self._cached_market_activity = _get_market_activity()
            self._last_activity_update = now
        
        activity = self._cached_market_activity
        
        base_threshold = self.mid_memory_threshold
        
        if activity > 0.6:
            return min(0.85, base_threshold + 0.15)
        elif activity < 0.3:
            return max(0.5, base_threshold - 0.2)
        else:
            return base_threshold
    
    def process_record(self, record: Dict) -> List[Dict]:
        """
        处理单条记录（naja策略接口）
        

            record: 数据源记录（单个dict或包含data字段的dict）
            

            信号列表
        """
        # 检测是否是 numpy 数组
        # Defensive: ensure stats has required keys
        import numpy as np
        if isinstance(record, np.ndarray):
            import logging
            logging.warning(f"[NewsRadar] 收到 numpy 数组数据，已跳过: type={type(record)}, shape={getattr(record, 'shape', 'N/A')}")
            return []
        
        # 检测是否是批量数据（列表）
        if isinstance(record, list):
            return self.process_batch(record)
        
        # 检测是否是包装格式（包含data字段，data是列表）
        if isinstance(record, dict) and 'data' in record:
            data = record['data']
            if isinstance(data, list):
                return self.process_batch(data)
        
        # 单条数据处理
        signals = []
        
        # 1. 转换为龙虾事件
        event = NewsEvent.from_datasource_record(record)

        # 1.5 注意力门控（频率+重要性）
        if self.enable_attention_filter and not self._should_ingest_event(event):
            self.stats["filtered_events"] = self.stats.get("filtered_events", 0) + 1
            return []

        # 2. 语义编码（改进版：使用关键词特征向量 + 数据源特征 + 事件类型特征）
        event.attention_score = self.attention_scorer.score(event)
        
        # 4. 主题聚类
        topic_id = self._assign_topic(event)
        event.topic_id = topic_id

        # 4.5 叙事追踪（避免对叙事/雷达/注意力事件重复触发）
        narrative_signals = self._process_narratives(event)

        # 5. 存入短期记忆
        self.short_memory.append(event)
        self.stats["total_events"] += 1
        
        # 6. 归档到中期记忆（高注意力事件，使用动态阈值）
        dynamic_threshold = self._get_dynamic_mid_memory_threshold()
        if event.attention_score >= dynamic_threshold:
            self.mid_memory.append({
                "id": event.id,
                "timestamp": event.timestamp,
                "source": event.source,
                "event_type": event.event_type,
                "content": event.content,
                "attention_score": event.attention_score,
                "topic_id": event.topic_id,
            })
        
        # 7. 检查是否需要生成长期记忆
        self._update_long_memory()
        
        # 8. 生成信号
        signals.extend(self._generate_signals_for_event(event, topic_id))
        
        # 9. 漂移检测
        if self.drift_detector and event.vector:
            signals.extend(self._check_drift(event))
        
        signals.extend(narrative_signals)
        return signals
    
    def process_batch(self, records: List[Dict]) -> List[Dict]:
        """
        批量处理记录列表（支持一次性处理多条数据）
        
        Args:
            records: 数据源记录列表
            
        Returns:
            信号列表
        """
        all_signals = []
        
        if not records:
            return all_signals
        
        # 用于去重的已见内容集合
        seen_contents = set()
        
        # 检测 numpy 数组
        # Defensive: ensure stats has required keys (in case of loaded state without them)
        import numpy as np
        filtered_records = [r for r in records if not isinstance(r, np.ndarray)]
        removed_count = len(records) - len(filtered_records)
        if removed_count > 0:
            import logging
            logging.warning(f"[NewsMind] 批量数据中包含 {removed_count} 个 numpy 数组，已过滤")
        records = filtered_records
        
        # 逐条处理，但进行去重检测
        candidates = []
        for record in records:
            event = NewsEvent.from_datasource_record(record)
            
            # 简单去重：基于内容hash
            content_hash = hash(event.content[:100])
            if content_hash in seen_contents:
                continue
            seen_contents.add(content_hash)

            if self.enable_attention_filter and not self._should_ingest_event(event):
                self.stats["filtered_events"] = self.stats.get("filtered_events", 0) + 1
                continue

            # 预评分用于批量筛选
            event.attention_score = self.attention_scorer.peek_score(event)
            candidates.append(event)

        if len(candidates) > self.max_batch_keep:
            candidates.sort(key=lambda e: e.attention_score, reverse=True)
            candidates = candidates[: self.max_batch_keep]

        for event in candidates:
            # 语义编码
            event.vector = self._simple_embedding(event.content, event.source, event.event_type)
            
            # 注意力评分（批量模式下使用相同的scorer）
            event.attention_score = self.attention_scorer.score(event)
            
            # 主题聚类
            topic_id = self._assign_topic(event)
            event.topic_id = topic_id

            narrative_signals = self._process_narratives(event)
            
            # 存入短期记忆
            self.short_memory.append(event)
            self.stats["total_events"] += 1
            
            # 归档到中期记忆（使用动态阈值）
            dynamic_threshold = self._get_dynamic_mid_memory_threshold()
            if event.attention_score >= dynamic_threshold:
                self.mid_memory.append({
                    "id": event.id,
                    "timestamp": event.timestamp,
                    "source": event.source,
                    "event_type": event.event_type,
                    "content": event.content,
                    "attention_score": event.attention_score,
                    "topic_id": event.topic_id,
                })
            
            # 生成信号
            all_signals.extend(self._generate_signals_for_event(event, topic_id))
            all_signals.extend(narrative_signals)
            
            # 漂移检测
            if self.drift_detector and event.vector:
                all_signals.extend(self._check_drift(event))
        
        # 批量处理后检查是否需要生成长期记忆
        self._update_long_memory()
        
        # 批量处理完成后，如果累积数据足够，进行窗口分析
        if len(self.short_memory) >= 100:
            window_signals = self._analyze_window()
            all_signals.extend(window_signals)
        
        return all_signals

    def _should_ingest_event(self, event: NewsEvent) -> bool:
        """
        根据频率与注意力门控决定是否纳入记忆
        
        改进版：增加价值驱动豁免逻辑，确保高价值事件不被过滤
        """
        # ========== 价值驱动豁免逻辑 ==========
        
        # 1. 注意力/雷达事件直接放行
        if event.source.startswith("attention:") or event.source.startswith("radar:"):
            return True

        # 2. 高重要性直接放行
        importance = str(event.meta.get("importance", "")).lower()
        if importance == "high":
            return True

        # 3. 首次出现的话题（新主题）直接放行
        if self._is_first_appearance_topic(event):
            return True

        # 4. 重大关键词触发（政策、突发、革命性变化）直接放行
        if self._has_critical_keywords(event):
            return True

        # 5. 新数据源类型首次出现直接放行
        if self._is_new_event_type(event):
            return True
        
        # ========== 频率/评分门控逻辑 ==========
        
        # 计算当前频率
        bucket = self._rate_buckets.setdefault(event.event_type, deque())
        now_ts = time.time()
        cutoff = now_ts - self.rate_window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        bucket.append(now_ts)
        rate_per_min = len(bucket) / max(1.0, self.rate_window_seconds / 60.0)

        # 动态门槛：频率越高，门槛越高
        rate_factor = min(1.5, rate_per_min / max(1.0, self.target_rate_per_min))
        dynamic_gate = min(0.9, self.base_attention_gate + rate_factor * 0.25)

        # 预评分（不写历史）
        pre_score = self.attention_scorer.peek_score(event)
        if pre_score >= dynamic_gate:
            return True

        return False
    
    def _is_first_appearance_topic(self, event: NewsEvent) -> bool:
        """检测是否是首次出现的话题（新话题萌芽期）"""
        if not self.topics:
            return True
        
        if event.vector is None:
            return False
        
        for topic in self.topics.values():
            if topic.event_count <= 2:
                sim = self._cosine_similarity(event.vector, topic.center)
                if sim > self.topic_threshold * 0.8:
                    return False
        
        return True
    
    def _has_critical_keywords(self, event: NewsEvent) -> bool:
        """检测是否包含重大关键词（政策、突发等）"""
        CRITICAL_KEYWORDS = [
            "政策", "监管", "改革", "革命", "突破", "重大", "紧急", "突发",
            "制裁", "禁止", "限制", "放开", "降准", "加息", "缩表",
            "战争", "灾难", "黑天鹅", "灰犀牛",
            "OpenAI", "英伟达", "ChatGPT", "AI", "人工智能",
        ]
        
        content_lower = event.content.lower()
        for kw in CRITICAL_KEYWORDS:
            if kw in event.content or kw.lower() in content_lower:
                return True
        
        return False
    
    def _is_new_event_type(self, event: NewsEvent) -> bool:
        """检测是否是新的事件类型（数据源的首条消息）"""
        seen_types = set()
        for e in self.short_memory:
            seen_types.add((e.source, e.event_type))
        
        return (event.source, event.event_type) not in seen_types
    
    def _generate_signals_for_event(self, event: NewsEvent, topic_id: Optional[int]) -> List[Dict]:
        """为单个事件生成信号"""
        signals = []
        
        # 高注意力信号
        if event.attention_score >= self.attention_threshold:
            signals.append(self._create_signal(
                SignalType.HIGH_ATTENTION,
                event,
                f"高注意力事件: {event.content[:50]}...",
                {"attention_score": event.attention_score}
            ))
            self.stats["high_attention_events"] += 1
        
        # 主题相关信号
        if topic_id is not None and topic_id in self.topics:
            topic = self.topics[topic_id]
            topic_name = topic.display_name
            
            # 新主题信号
            if topic.event_count == 1:
                signals.append(self._create_signal(
                    SignalType.TOPIC_EMERGE,
                    event,
                    f"新主题出现: {topic_name}",
                    {"topic_id": topic_id, "topic_name": topic_name, "event_type": event.event_type}
                ))
            
            # 主题增长信号
            elif topic.growth_rate > 0.5:
                signals.append(self._create_signal(
                    SignalType.TOPIC_GROW,
                    event,
                    f"主题快速增长: {topic_name}",
                    {"topic_id": topic_id, "topic_name": topic_name, "growth_rate": topic.growth_rate}
                ))
        
        return signals
    
    def _check_drift(self, event: NewsEvent) -> List[Dict]:
        """检查漂移"""
        signals = []
        if self.drift_detector and event.vector:
            self.drift_detector.update(event.attention_score)
            if self.drift_detector.drift_detected:
                signals.append(self._create_signal(
                    SignalType.DRIFT_DETECTED,
                    event,
                    "检测到数据分布漂移",
                    {"drift_point": self.stats["total_events"]}
                ))
                self.stats["drifts_detected"] += 1
        return signals

    def _process_narratives(self, event: NewsEvent) -> List[Dict]:
        """叙事追踪与事件桥接"""
        if not self.narrative_tracker or not self.narrative_tracker.enabled:
            return []
        if event.source.startswith(("narrative:", "radar:", "attention:")):
            return []
        narrative_events = self.narrative_tracker.ingest_event(event)
        if narrative_events:
            self.narrative_events.extend(narrative_events)
            self._emit_narrative_events(narrative_events)
        return narrative_events

    def _emit_narrative_events(self, events: List[Dict[str, Any]]) -> None:
        try:
            from ..radar import get_radar_engine
        except Exception:
            return
        try:
            radar = get_radar_engine()
        except Exception:
            return
        for event in events:
            event_type = str(event.get("event_type", "narrative_event"))
            narrative = str(event.get("narrative", "unknown"))
            stage = str(event.get("stage", ""))
            score = float(event.get("attention_score", 0.0) or 0.0)
            message = (
                f"叙事{narrative}进入{stage}"
                if event_type == "narrative_stage_change"
                else f"叙事{narrative}注意力飙升"
            )
            payload = dict(event)
            payload["signal_type"] = "narrative"
            radar.ingest_attention_event(
                event_type=event_type,
                score=score,
                message=message,
                payload=payload,
                signal_type="narrative",
                strategy_id="narrative_tracker",
                strategy_name="Narrative Tracker",
            )

    def build_semantic_cold_start_prompt(self, seeds: Optional[List[str]] = None) -> str:
        """构建语义冷启动 prompt（给 LLM 使用）"""
        if not self.semantic_cold_start:
            return ""
        return self.semantic_cold_start.build_prompt(seeds)

    def apply_semantic_cold_start(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """应用 LLM 冷启动输出，更新语义图谱"""
        if not self.semantic_cold_start:
            return {}
        self.semantic_graph = self.semantic_cold_start.apply_graph_payload(payload)
        return self.semantic_graph
    
    def process_window(self, records: List[Dict]) -> List[Dict]:
        """
        处理窗口数据（naja策略接口）
        
        Args:
            records: 窗口内的记录列表
            
        Returns:
            信号列表
        """
        all_signals = []
        for record in records:
            signals = self.process_record(record)
            all_signals.extend(signals)
        
        # 窗口级别的分析
        if len(self.short_memory) >= 100:
            window_signals = self._analyze_window()
            all_signals.extend(window_signals)
        
        return all_signals
    
    def _simple_embedding(self, text: str, source: str = "unknown", event_type: str = "text") -> List[float]:
        """
        简化版语义编码 - 改进版
        
        使用关键词特征向量 + 数据源特征 + 事件类型特征
        数据源特征权重更高，确保不同数据源的数据形成不同主题
        """
        text_lower = text.lower()
        vector = []
        
        # 1. 数据源类型特征 (10维，高权重) - 让不同数据源的数据更容易区分
        # 使用 one-hot 编码，每个数据源有独立的维度
        source_onehot = {
            "行情回放":    [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "tick":        [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "quant":       [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "系统日志监控": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "日志":        [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "log":         [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "下载目录监控": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "文件":        [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "file":        [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "财经新闻":    [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "新闻":        [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "news":        [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }
        
        source_vec = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        matched = False
        for key, vec in source_onehot.items():
            if key in source:
                source_vec = vec
                matched = True
                break
        
        # 如果没有匹配到已知数据源，使用最后一个维度作为"其他"
        if not matched:
            source_vec = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        
        vector.extend(source_vec)
        
        # 2. 事件类型特征 (3维)
        type_features = {
            "tick": [1.0, 0.0, 0.0],
            "trade": [0.8, 0.2, 0.0],
            "array": [0.0, 1.0, 0.0],
            "text": [0.0, 0.0, 1.0],
            "dict": [0.3, 0.3, 0.4],
        }
        type_vec = type_features.get(event_type, [0.0, 0.0, 1.0])
        vector.extend(type_vec)
        
        # 3. 金融关键词特征 (5维) - 行情数据
        finance_keywords = ["price", "volume", "涨", "跌", "买", "卖"]
        for kw in finance_keywords:
            count = text_lower.count(kw.lower())
            vector.append(min(1.0, count * 0.3))
        
        # 4. 日志关键词特征 (3维) - 日志数据
        log_keywords = ["error", "warn", "info"]
        for kw in log_keywords:
            count = text_lower.count(kw.lower())
            vector.append(min(1.0, count * 0.3))
        
        # 5. 文件关键词特征 (3维) - 文件数据
        file_keywords = [".py", ".txt", ".csv"]
        for kw in file_keywords:
            count = text_lower.count(kw.lower())
            vector.append(min(1.0, count * 0.3))
        
        # 6. 文本统计特征 (3维)
        vector.append(min(1.0, len(text) / 1000))  # 长度
        vector.append(min(1.0, text.count("!") * 0.1))  # 感叹号
        vector.append(min(1.0, sum(c.isdigit() for c in text) / max(len(text), 1)))  # 数字比例
        
        return vector
    
    def _assign_topic(self, event: NewsEvent) -> Optional[int]:
        """分配主题"""
        if event.vector is None:
            return None
        
        # 使用River聚类
        if self.clustering:
            # River DBSTREAM 期望输入是字典格式，不是 numpy 数组
            vector_dict = {i: v for i, v in enumerate(event.vector)}
            self.clustering.learn_one(vector_dict)
            # DBSTREAM不直接返回标签，我们使用距离最近的主题
            topic_id = self._find_nearest_topic(event.vector)
        else:
            topic_id = self._find_nearest_topic(event.vector)
        
        # 创建新主题
        if topic_id is None or topic_id not in self.topics:
            if len(self.topics) < self.max_topics:
                self.topic_counter += 1
                topic_id = self.topic_counter
                self.topics[topic_id] = Topic(
                    id=topic_id,
                    center=event.vector.copy(),
                    events=deque(maxlen=1000),
                    created_at=datetime.now(),
                    last_updated=datetime.now(),
                )
                self.stats["topics_created"] += 1
        
        # 更新主题
        if topic_id in self.topics:
            topic = self.topics[topic_id]
            topic.events.append(event)
            topic.last_updated = datetime.now()
            topic.attention_sum += event.attention_score
            topic.event_count += 1
            
            # 更新主题中心（移动平均）
            alpha = 0.1
            topic.center = [
                (1 - alpha) * c + alpha * v
                for c, v in zip(topic.center, event.vector)
            ]
            
            # 更新主题名称
            topic.update_name()
        
        return topic_id
    
    def _find_nearest_topic(self, vector: List[float]) -> Optional[int]:
        """找到最近的现有主题"""
        if not self.topics:
            return None
        
        best_topic = None
        best_similarity = -1
        
        for topic_id, topic in self.topics.items():
            sim = self._cosine_similarity(vector, topic.center)
            if sim > best_similarity and sim > self.topic_threshold:
                best_similarity = sim
                best_topic = topic_id
        
        return best_topic
    
    def _analyze_window(self) -> List[Dict]:
        """分析窗口数据，生成高级信号"""
        signals = []
        
        # 检查主题消退
        one_hour_ago = datetime.now() - timedelta(hours=1)
        for topic_id, topic in self.topics.items():
            if topic.last_updated < one_hour_ago and topic.event_count > 10:
                topic_name = topic.display_name
                signals.append(self._create_signal(
                    SignalType.TOPIC_FADE,
                    None,
                    f"主题消退: {topic_name}",
                    {"topic_id": topic_id, "topic_name": topic_name, "last_active": topic.last_updated.isoformat()}
                ))
        
        return signals
    
    def _update_long_memory(self):
        """更新长期记忆 - 周期性总结"""
        now = datetime.now()
        if (now - self.last_long_memory_time).total_seconds() >= self.long_memory_interval * 3600:
            # 生成周期性总结
            summary = self._generate_memory_summary()
            self.long_memory.append({
                "timestamp": now.isoformat(),
                "summary": summary,
                "period_start": self.last_long_memory_time.isoformat(),
                "period_end": now.isoformat(),
            })
            # 只保留最近30天的长期记忆
            if len(self.long_memory) > 30:
                self.long_memory = self.long_memory[-30:]
            self.last_long_memory_time = now
    
    def _generate_memory_summary(self) -> Dict:
        """生成记忆总结"""
        # 统计周期内的数据
        period_start = self.last_long_memory_time
        period_events = [e for e in self.mid_memory if e["timestamp"] >= period_start]
        
        # 按主题统计
        topic_stats = {}
        for event in period_events:
            tid = event.get("topic_id")
            if tid:
                if tid not in topic_stats:
                    topic_stats[tid] = {
                        "count": 0,
                        "total_attention": 0,
                        "topic_name": self.topics.get(tid, Topic(id=tid, center=[], events=deque(), created_at=datetime.now(), last_updated=datetime.now())).display_name
                    }
                topic_stats[tid]["count"] += 1
                topic_stats[tid]["total_attention"] += event["attention_score"]
        
        # 排序获取热门主题
        sorted_topics = sorted(
            topic_stats.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )[:5]
        
        return {
            "total_events": len(period_events),
            "avg_attention": sum(e["attention_score"] for e in period_events) / len(period_events) if period_events else 0,
            "top_topics": [
                {
                    "id": tid,
                    "name": stats["topic_name"],
                    "event_count": stats["count"],
                    "avg_attention": round(stats["total_attention"] / stats["count"], 3) if stats["count"] > 0 else 0,
                }
                for tid, stats in sorted_topics
            ],
            "event_types": self._count_by_key(period_events, "event_type"),
            "sources": self._count_by_key(period_events, "source"),
        }
    
    def _count_by_key(self, events: List[Dict], key: str) -> Dict:
        """按key统计事件数量"""
        counts = {}
        for e in events:
            val = e.get(key, "unknown")
            counts[val] = counts.get(val, 0) + 1
        return counts
    
    def _create_signal(self, signal_type: SignalType, event: Optional[NewsEvent],
                       message: str, data: Dict) -> Dict:
        """创建信号"""
        return {
            "type": signal_type.value,
            "timestamp": datetime.now().isoformat(),
            "event_id": event.id if event else None,
            "message": message,
            "data": data,
            "priority": "high" if signal_type in [SignalType.HIGH_ATTENTION, SignalType.DRIFT_DETECTED] else "normal",
        }
    
    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """余弦相似度"""
        v1, v2 = np.array(v1), np.array(v2)
        norm = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norm == 0:
            return 0.0
        return float(np.dot(v1, v2) / norm)
    
    def get_memory_report(self) -> Dict:
        """获取记忆报告"""
        # 主题排序（按活跃度），过滤掉噪音主题
        sorted_topics = sorted(
            self.topics.values(),
            key=lambda t: t.event_count,
            reverse=True
        )
        # 只保留股票相关主题
        stock_topics = [t for t in sorted_topics if _is_stock_relevant_topic(t)]
        
        # 三层记忆统计
        short_term_data = self._get_short_term_memory_data()
        mid_term_data = self._get_mid_term_memory_data()
        long_term_data = self._get_long_term_memory_data()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "stats": self.stats,
            "memory_layers": {
                "short": {
                    "size": len(self.short_memory),
                    "capacity": self.short_term_size,
                    "description": "最近的事件流",
                    "data": short_term_data,
                },
                "mid": {
                    "size": len(self.mid_memory),
                    "capacity": 5000,
                    "threshold": self.mid_memory_threshold,
                    "description": "高注意力事件归档",
                    "data": mid_term_data,
                },
                "long": {
                    "size": len(self.long_memory),
                    "capacity": 30,
                    "interval_hours": self.long_memory_interval,
                    "description": "周期性总结",
                    "data": long_term_data,
                },
            },
            "active_topics": len(stock_topics),
            "top_topics": [
                {
                    "id": t.id,
                    "name": t.display_name,
                    "keywords": t.keywords,
                    "event_count": t.event_count,
                    "avg_attention": round(t.avg_attention, 3),
                    "growth_rate": round(t.growth_rate, 3),
                    "created_at": t.created_at.isoformat(),
                    "last_updated": t.last_updated.isoformat(),
                }
                for t in stock_topics[:10]
            ],
            "recent_high_attention": [
                {
                    "id": e.id,
                    "timestamp": e.timestamp.isoformat() if isinstance(e.timestamp, datetime) else str(e.timestamp),
                    "source": e.source,
                    "type": e.event_type,
                    "score": round(e.attention_score, 3),
                    "content": e.content[:100] + "..." if len(e.content) > 100 else e.content,
                }
                for e in list(self.short_memory)[-20:]
                if e.attention_score >= self.attention_threshold
            ][-5:],
            "user_focus": self._get_user_focus_events(limit=8),
            "narratives": self._get_narratives_report(),
            "semantic_graph": self.semantic_cold_start.get_summary(limit=10) if self.semantic_cold_start else {},
        }

    def _get_narratives_report(self) -> Dict[str, Any]:
        """从短期记忆动态计算叙事报告"""
        if not self.narrative_tracker:
            return {"summary": [], "graph": {"nodes": [], "edges": []}, "events": []}

        recent_events = list(self.short_memory)[-500:]
        if not recent_events:
            return {
                "summary": self.narrative_tracker.get_summary(limit=10),
                "graph": self.narrative_tracker.get_graph(),
                "events": list(self.narrative_events)[-10:],
            }

        keyword_hits: Dict[str, Dict[str, Any]] = {}
        cooccurrence: Dict[Tuple[str, str], int] = {}
        now_ts = datetime.now().timestamp()
        recent_window = 6 * 3600
        prev_window = 6 * 3600

        for event in recent_events:
            event_ts = getattr(event, "timestamp", None)
            if isinstance(event_ts, datetime):
                event_ts = event_ts.timestamp()
            elif not isinstance(event_ts, float):
                event_ts = now_ts

            if now_ts - event_ts > recent_window + prev_window:
                continue

            content = getattr(event, "content", "") or ""
            meta = getattr(event, "meta", {}) or {}
            for key in ("title", "topic", "sector", "industry", "theme", "summary"):
                val = meta.get(key)
                if val:
                    content += " " + str(val)

            for key in ("tags", "keywords", "narratives", "narrative"):
                val = meta.get(key)
                if isinstance(val, list):
                    content += " " + " ".join(str(v) for v in val)
                elif val:
                    content += " " + str(val)

            if not content:
                continue

            content_lower = content.lower()
            matched_narratives: List[str] = []

            for narrative, keywords in self.narrative_tracker._keywords.items():
                if narrative not in keyword_hits:
                    keyword_hits[narrative] = {
                        "name": narrative,
                        "recent_hits": 0,
                        "prev_hits": 0,
                        "attention_sum": 0.0,
                        "recent_ts": 0.0,
                        "last_keywords": [],
                    }

                hit_kws = []
                for kw in keywords:
                    if kw.lower() in content_lower if kw.isascii() else kw in content:
                        hit_kws.append(kw)

                if hit_kws:
                    matched_narratives.append(narrative)
                    event_age = now_ts - event_ts
                    if event_age <= recent_window:
                        keyword_hits[narrative]["recent_hits"] += 1
                        if event_ts > keyword_hits[narrative]["recent_ts"]:
                            keyword_hits[narrative]["recent_ts"] = event_ts
                            keyword_hits[narrative]["last_keywords"] = hit_kws
                    elif event_age <= recent_window + prev_window:
                        keyword_hits[narrative]["prev_hits"] += 1

                    att_score = float(getattr(event, "attention_score", 0.0))
                    keyword_hits[narrative]["attention_sum"] += att_score

            for i, nar1 in enumerate(matched_narratives):
                for nar2 in matched_narratives[i + 1:]:
                    key = tuple(sorted([nar1, nar2]))
                    cooccurrence[key] = cooccurrence.get(key, 0) + 1

        summary = []
        for narrative, data in keyword_hits.items():
            recent_count = data["recent_hits"]
            prev_count = data["prev_hits"]
            attention_avg = data["attention_sum"] / max(1, recent_count + prev_count)
            trend = (recent_count - prev_count) / max(1, prev_count)

            import math
            count_score = 1.0 - math.exp(-recent_count / max(self.narrative_tracker._count_scale, 1e-6))
            attention_score = 0.6 * count_score + 0.4 * attention_avg

            if recent_count <= self.narrative_tracker._fade_count and attention_score <= self.narrative_tracker._fade_score:
                stage = "消退"
            elif recent_count >= self.narrative_tracker._peak_count or attention_score >= self.narrative_tracker._peak_score:
                stage = "高潮"
            elif recent_count >= self.narrative_tracker._spread_count or trend >= self.narrative_tracker._trend_threshold or attention_score >= self.narrative_tracker._spread_score:
                stage = "扩散"
            else:
                stage = "萌芽"

            summary.append({
                "narrative": data["name"],
                "stage": stage,
                "attention_score": round(attention_score, 3),
                "recent_count": recent_count,
                "trend": round(trend, 3),
                "last_updated": data["recent_ts"],
                "keywords": data["last_keywords"][:5],
            })

        summary.sort(key=lambda x: x["attention_score"], reverse=True)

        tracker_summary = self.narrative_tracker.get_summary(limit=10)
        if not summary and tracker_summary:
            summary = tracker_summary

        graph = self.narrative_tracker.get_graph()
        if not graph.get("nodes") and summary:
            max_score = max(s["attention_score"] for s in summary) if summary else 1.0
            nodes = []
            for s in summary:
                nodes.append({
                    "id": s["narrative"],
                    "stage": s["stage"],
                    "attention_score": s["attention_score"],
                    "recent_count": s["recent_count"],
                })

            edges = []
            min_weight = 0.2
            for (src, tgt), weight in cooccurrence.items():
                norm_weight = min(1.0, weight / 10.0)
                if norm_weight >= min_weight:
                    edges.append({
                        "source": src,
                        "target": tgt,
                        "weight": round(norm_weight, 3),
                    })

            edges.sort(key=lambda e: e["weight"], reverse=True)
            graph = {"nodes": nodes, "edges": edges[:15]}

        return {
            "summary": summary[:10],
            "graph": graph,
            "events": list(self.narrative_events)[-10:],
        }

    def _get_user_focus_events(self, limit: int = 8) -> List[Dict[str, Any]]:
        """基于双注意力计算用户重点记忆"""
        events = list(self.short_memory)[-200:]
        if not events:
            return []

        scored = []
        now_ts = datetime.now().timestamp()
        for event in events:
            system_attention = float(getattr(event, "attention_score", 0.0))
            confidence = 0.4
            actionability = 0.3
            novelty = 0.5

            meta = getattr(event, "meta", {}) or {}
            importance = str(meta.get("importance", "")).lower()
            if importance == "high":
                confidence = 0.8
            elif importance == "medium":
                confidence = 0.6

            if event.event_type in {"tick"}:
                actionability = 0.6
            if meta.get("symbol") or meta.get("code"):
                actionability = max(actionability, 0.7)

            # 简单新颖度：用时间差近似
            ts = event.timestamp.timestamp() if isinstance(event.timestamp, datetime) else now_ts
            delta = max(0.0, now_ts - ts)
            novelty = min(1.0, delta / 3600.0)

            user_score = (
                0.4 * system_attention
                + 0.2 * confidence
                + 0.2 * actionability
                + 0.2 * novelty
            )

            theme = meta.get("topic") or meta.get("sector") or meta.get("industry") or event.event_type
            summary = event.content[:80] + ("..." if len(event.content) > 80 else "")

            scored.append(
                {
                    "id": event.id,
                    "timestamp": event.timestamp.isoformat() if isinstance(event.timestamp, datetime) else str(event.timestamp),
                    "theme": str(theme),
                    "summary": summary,
                    "user_score": round(user_score, 3),
                    "system_attention": round(system_attention, 3),
                }
            )

        scored.sort(key=lambda x: x["user_score"], reverse=True)
        return scored[: max(1, int(limit))]

    def get_attention_hints(self, lookback: int = 200) -> Dict[str, Any]:
        """
        从记忆中提取可用于注意力系统的提示（带权重版）。

        返回:
            {
                "symbols": {"SYMBOL": weight, ...},  # 权重 = 平均注意力 * 频率归一化
                "sectors": {"SECTOR": weight, ...},
            }
        """
        symbol_scores: Dict[str, List[float]] = {}
        sector_scores: Dict[str, List[float]] = {}

        recent_events = list(self.short_memory)[-max(1, int(lookback)):]
        for event in recent_events:
            meta = getattr(event, "meta", {}) or {}
            attention = getattr(event, "attention_score", 0.5)

            for key in ("symbol", "code", "ticker", "stock"):
                val = meta.get(key)
                if val:
                    symbol = str(val)
                    if symbol not in symbol_scores:
                        symbol_scores[symbol] = []
                    symbol_scores[symbol].append(attention)

            for key in ("sector", "industry", "sector_id"):
                val = meta.get(key)
                if val:
                    sector = str(val)
                    if sector not in sector_scores:
                        sector_scores[sector] = []
                    sector_scores[sector].append(attention)

        def compute_weight(scores: List[float]) -> float:
            if not scores:
                return 0.0
            avg_attention = sum(scores) / len(scores)
            frequency_factor = min(1.0, len(scores) / 10.0)
            return avg_attention * 0.7 + frequency_factor * 0.3

        symbols_weighted = {
            sym: compute_weight(scores)
            for sym, scores in symbol_scores.items()
        }
        sectors_weighted = {
            sec: compute_weight(scores)
            for sec, scores in sector_scores.items()
        }

        return {
            "symbols": symbols_weighted,
            "sectors": sectors_weighted,
        }
    
    def _get_short_term_memory_data(self) -> List[Dict]:
        """获取短期记忆数据（最近10条）"""
        recent_events = list(self.short_memory)[-10:]
        return [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat() if isinstance(e.timestamp, datetime) else str(e.timestamp),
                "source": e.source,
                "event_type": e.event_type,
                "content": e.content[:50] + "..." if len(e.content) > 50 else e.content,
                "attention_score": round(e.attention_score, 3),
                "topic_id": e.topic_id,
            }
            for e in reversed(recent_events)
        ]
    
    def _get_mid_term_memory_data(self) -> List[Dict]:
        """获取中期记忆数据（最近10条）"""
        recent_events = list(self.mid_memory)[-10:]
        return [
            {
                "id": e["id"],
                "timestamp": e["timestamp"].isoformat() if isinstance(e["timestamp"], datetime) else str(e["timestamp"]),
                "source": e["source"],
                "event_type": e["event_type"],
                "content": e["content"][:50] + "..." if len(e["content"]) > 50 else e["content"],
                "attention_score": round(e["attention_score"], 3),
                "topic_id": e.get("topic_id"),
            }
            for e in reversed(recent_events)
        ]
    
    def _get_long_term_memory_data(self) -> List[Dict]:
        """获取长期记忆数据（最近5个周期）"""
        recent_summaries = self.long_memory[-5:]
        return [
            {
                "timestamp": s["timestamp"],
                "period_start": s["period_start"],
                "period_end": s["period_end"],
                "summary": s["summary"],
            }
            for s in reversed(recent_summaries)
        ]
    
    def generate_thought_report(self) -> str:
        """生成思想报告"""
        report = self.get_memory_report()
        
        lines = [
            "=" * 50,
            "🦞 龙虾思想雷达报告",
            "=" * 50,
            f"生成时间: {report['timestamp']}",
            "",
            "📊 统计概览",
            f"  总事件数: {report['stats']['total_events']}",
            f"  高注意力事件: {report['stats']['high_attention_events']}",
            f"  主题数: {report['stats']['topics_created']}",
            f"  漂移检测: {report['stats']['drifts_detected']}",
            "",
            "🔥 热门主题 TOP 5",
        ]
        
        for i, topic in enumerate(report['top_topics'][:5], 1):
            topic_name = topic.get('name', f"主题{topic['id']}")
            keywords = topic.get('keywords', [])
            kw_str = f"[{', '.join(keywords)}]" if keywords else ""
            lines.append(f"  {i}. {topic_name} {kw_str}: {topic['event_count']}事件, "
                        f"注意力{topic['avg_attention']}, 增长率{topic['growth_rate']}")
        
        lines.extend([
            "",
            "⚡ 最近高注意力事件",
        ])
        
        for event in report['recent_high_attention']:
            lines.append(f"  [{event['type']}] 评分{event['score']}: {event['content']}")
        
        lines.append("=" * 50)
        
        return "\n".join(lines)
    
    # ============================================================================
    # 持久化方法
    # ============================================================================
    
    PERSISTENCE_TABLE = "naja_news_radar_state"
    PERSISTENCE_KEY = "news_radar_main"
    PERSISTENCE_LOCK = threading.Lock()
    
    def save_state(self) -> dict:
        """保存雷达策略状态到数据库
        
        Returns:
            保存结果
        """
        if not NAJA_DB_AVAILABLE:
            return {"success": False, "error": "NB not available"}
        
        try:
            with self.PERSISTENCE_LOCK:
                db = NB(self.PERSISTENCE_TABLE)
                
                # 序列化状态
                state_data = self._serialize_state()
                
                # 保存到数据库
                db[self.PERSISTENCE_KEY] = state_data
                
                print(f"[NewsRadar] 状态已保存: {len(self.short_memory)} 短期记忆, "
                      f"{len(self.mid_memory)} 中期记忆, {len(self.long_memory)} 长期记忆, "
                      f"{len(self.topics)} 主题")
                
                return {
                    "success": True,
                    "short_memory_count": len(self.short_memory),
                    "mid_memory_count": len(self.mid_memory),
                    "long_memory_count": len(self.long_memory),
                    "topics_count": len(self.topics),
                }
        except Exception as e:
            print(f"[NewsRadar] 保存状态失败: {e}")
            return {"success": False, "error": str(e)}
    
    def load_state(self) -> dict:
        """从数据库加载雷达策略状态
        
        Returns:
            加载结果
        """
        if not NAJA_DB_AVAILABLE:
            return {"success": False, "error": "NB not available"}
        
        try:
            with self.PERSISTENCE_LOCK:
                db = NB(self.PERSISTENCE_TABLE)
                
                if self.PERSISTENCE_KEY not in db:
                    print("[NewsRadar] 没有找到保存的状态")
                    return {"success": True, "loaded": False, "message": "No saved state found"}
                
                state_data = db.get(self.PERSISTENCE_KEY)
                if not isinstance(state_data, dict):
                    return {"success": False, "error": "Invalid state data format"}
                
                # 反序列化状态
                self._deserialize_state(state_data)
                
                print(f"[NewsRadar] 状态已加载: {len(self.short_memory)} 短期记忆, "
                      f"{len(self.mid_memory)} 中期记忆, {len(self.long_memory)} 长期记忆, "
                      f"{len(self.topics)} 主题")
                
                return {
                    "success": True,
                    "loaded": True,
                    "short_memory_count": len(self.short_memory),
                    "mid_memory_count": len(self.mid_memory),
                    "long_memory_count": len(self.long_memory),
                    "topics_count": len(self.topics),
                }
        except Exception as e:
            print(f"[NewsRadar] 加载状态失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _serialize_state(self) -> dict:
        """序列化状态为字典"""
        # 序列化短期记忆（只保存最近500条，避免数据过大）
        short_memory_data = []
        for e in list(self.short_memory)[-500:]:
            short_memory_data.append({
                "id": e.id,
                "timestamp": e.timestamp.isoformat() if isinstance(e.timestamp, datetime) else str(e.timestamp),
                "source": e.source,
                "event_type": e.event_type,
                "content": e.content,
                "vector": e.vector,
                "attention_score": e.attention_score,
                "topic_id": e.topic_id,
                "meta": e.meta,
            })
        
        # 序列化中期记忆
        mid_memory_data = []
        for e in list(self.mid_memory)[-1000:]:  # 最多保存1000条
            mid_memory_data.append({
                "id": e["id"],
                "timestamp": e["timestamp"].isoformat() if isinstance(e["timestamp"], datetime) else str(e["timestamp"]),
                "source": e["source"],
                "event_type": e["event_type"],
                "content": e["content"],
                "attention_score": e["attention_score"],
                "topic_id": e.get("topic_id"),
            })
        
        # 序列化长期记忆
        long_memory_data = self.long_memory[-30:]  # 最多保存30个周期
        
        # 序列化主题
        topics_data = {}
        for topic_id, topic in self.topics.items():
            topics_data[str(topic_id)] = {
                "id": topic.id,
                "center": topic.center,
                "events": list(topic.events)[-100:],  # 每个主题最多保存100个事件
                "created_at": topic.created_at.isoformat(),
                "last_updated": topic.last_updated.isoformat(),
                "attention_sum": topic.attention_sum,
                "event_count": topic.event_count,
                "name": topic.name,
                "keywords": topic.keywords,
            }
        
        return {
            "version": 1,
            "saved_at": datetime.now().isoformat(),
            "config": self.config,
            "stats": self.stats,
            "topic_counter": self.topic_counter,
            "short_memory": short_memory_data,
            "mid_memory": mid_memory_data,
            "long_memory": long_memory_data,
            "topics": topics_data,
            "mid_memory_threshold": self.mid_memory_threshold,
            "long_memory_interval": self.long_memory_interval,
            "last_long_memory_time": self.last_long_memory_time.isoformat(),
            "semantic_graph": self.semantic_graph,
        }
    
    def _deserialize_state(self, data: dict):
        """从字典反序列化状态"""
        # 恢复配置
        self.config = data.get("config", {})
        self.short_term_size = self.config.get("short_term_size", 1000)
        self.topic_threshold = self.config.get("topic_threshold", 0.5)
        self.attention_threshold = self.config.get("attention_threshold", 0.6)
        self.max_topics = self.config.get("max_topics", 50)
        
        # 恢复统计信息
        default_stats = {
            "total_events": 0,
            "high_attention_events": 0,
            "topics_created": 0,
            "drifts_detected": 0,
            "filtered_events": 0,
        }
        saved_stats = data.get("stats", {})
        self.stats = {**default_stats, **saved_stats}
        self.topic_counter = data.get("topic_counter", 0)
        self.mid_memory_threshold = data.get("mid_memory_threshold", 0.7)
        self.long_memory_interval = data.get("long_memory_interval", 24)
        self.semantic_graph = data.get("semantic_graph", self.semantic_graph or {})
        
        # 恢复长期记忆时间
        last_long_time_str = data.get("last_long_memory_time")
        if last_long_time_str:
            try:
                self.last_long_memory_time = datetime.fromisoformat(last_long_time_str)
            except:
                self.last_long_memory_time = datetime.now() - timedelta(hours=24)
        
        # 恢复短期记忆
        self.short_memory.clear()
        for e_data in data.get("short_memory", []):
            try:
                event = NewsEvent(
                    id=e_data["id"],
                    timestamp=datetime.fromisoformat(e_data["timestamp"]),
                    source=e_data["source"],
                    event_type=e_data["event_type"],
                    content=e_data["content"],
                    vector=e_data.get("vector"),
                    meta=e_data.get("meta", {}),
                )
                event.attention_score = e_data.get("attention_score", 0)
                event.topic_id = e_data.get("topic_id")
                self.short_memory.append(event)
            except Exception as e:
                print(f"[NewsRadar] 恢复短期记忆事件失败: {e}")
        
        # 恢复中期记忆
        self.mid_memory.clear()
        for e_data in data.get("mid_memory", []):
            try:
                ts = e_data["timestamp"]
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                self.mid_memory.append({
                    "id": e_data["id"],
                    "timestamp": ts,
                    "source": e_data["source"],
                    "event_type": e_data["event_type"],
                    "content": e_data["content"],
                    "attention_score": e_data["attention_score"],
                    "topic_id": e_data.get("topic_id"),
                })
            except Exception as e:
                print(f"[NewsRadar] 恢复中期记忆事件失败: {e}")
        
        # 恢复长期记忆
        self.long_memory = data.get("long_memory", [])
        
        # 恢复主题
        self.topics.clear()
        for topic_id_str, t_data in data.get("topics", {}).items():
            try:
                topic_id = int(topic_id_str)
                topic = Topic(
                    id=t_data["id"],
                    center=t_data["center"],
                    events=deque(maxlen=1000),
                    created_at=datetime.fromisoformat(t_data["created_at"]),
                    last_updated=datetime.fromisoformat(t_data["last_updated"]),
                )
                topic.attention_sum = t_data.get("attention_sum", 0)
                topic.event_count = t_data.get("event_count", 0)
                topic.name = t_data.get("name", "")
                topic.keywords = t_data.get("keywords", [])
                
                # 恢复主题内的事件
                for e_data in t_data.get("events", []):
                    if isinstance(e_data, dict) and "id" in e_data:
                        try:
                            event = NewsEvent(
                                id=e_data["id"],
                                timestamp=datetime.fromisoformat(e_data["timestamp"]) if isinstance(e_data["timestamp"], str) else e_data["timestamp"],
                                source=e_data.get("source", ""),
                                event_type=e_data.get("event_type", ""),
                                content=e_data.get("content", ""),
                            )
                            topic.events.append(event)
                        except:
                            pass
                
                self.topics[topic_id] = topic
            except Exception as e:
                print(f"[NewsRadar] 恢复主题失败: {e}")
    
    def clear_saved_state(self) -> dict:
        """清除保存的状态"""
        if not NAJA_DB_AVAILABLE:
            return {"success": False, "error": "NB not available"}
        
        try:
            with self.PERSISTENCE_LOCK:
                db = NB(self.PERSISTENCE_TABLE)
                if self.PERSISTENCE_KEY in db:
                    del db[self.PERSISTENCE_KEY]
                print("[NewsRadar] 已清除保存的状态")
                return {"success": True}
        except Exception as e:
            print(f"[NewsRadar] 清除状态失败: {e}")
            return {"success": False, "error": str(e)}


# naja策略系统接口
class Strategy:
    """naja策略包装类"""

    def __init__(self, config: Dict = None):
        self.radar = NewsMindStrategy(config)
        self._save_interval = 300  # 默认5分钟保存一次
        self._save_thread = None
        self._stop_save_thread = threading.Event()
        # 启动时自动加载状态
        self._auto_load_on_init()
        # 启动定时保存线程
        self._start_auto_save()
    
    def _auto_load_on_init(self):
        """初始化时自动加载保存的状态"""
        result = self.radar.load_state()
        if result.get("success") and result.get("loaded"):
            print(f"[NewsMindStrategy] 成功恢复之前的状态")
        elif not result.get("loaded"):
            print(f"[NewsRadarStrategy] 没有找到保存的状态，使用新实例")
    
    def _start_auto_save(self):
        """启动定时保存线程"""
        if self._save_thread is not None and self._save_thread.is_alive():
            return
        
        self._stop_save_thread.clear()
        self._save_thread = threading.Thread(target=self._auto_save_loop, daemon=True)
        self._save_thread.start()
        print(f"[NewsRadarStrategy] 定时保存已启动，间隔 {self._save_interval} 秒")
    
    def _auto_save_loop(self):
        """自动保存循环"""
        while not self._stop_save_thread.is_set():
            # 等待指定时间
            self._stop_save_thread.wait(self._save_interval)
            if self._stop_save_thread.is_set():
                break
            
            # 执行保存
            try:
                result = self.radar.save_state()
                if result.get("success"):
                    print(f"[NewsMindStrategy] 定时保存完成")
                else:
                    print(f"[NewsRadarStrategy] 定时保存失败: {result.get('error')}")
            except Exception as e:
                print(f"[NewsRadarStrategy] 定时保存异常: {e}")
    
    def _stop_auto_save(self):
        """停止定时保存线程"""
        if self._save_thread is not None:
            self._stop_save_thread.set()
            self._save_thread.join(timeout=5)
            print("[NewsRadarStrategy] 定时保存已停止")
    
    def on_record(self, record: Dict) -> List[Dict]:
        """逐条处理"""
        return self.radar.process_record(record)
    
    def on_window(self, records: List[Dict]) -> List[Dict]:
        """窗口处理"""
        return self.radar.process_window(records)
    
    def get_report(self) -> Dict:
        """获取报告"""
        return self.radar.get_memory_report()
    
    def get_thought_report(self) -> str:
        """获取思想报告"""
        return self.radar.generate_thought_report()
    
    def save_state(self) -> dict:
        """保存状态（供外部调用）"""
        return self.radar.save_state()
    
    def load_state(self) -> dict:
        """加载状态（供外部调用）"""
        return self.radar.load_state()
    
    def clear_saved_state(self) -> dict:
        """清除保存的状态"""
        return self.radar.clear_saved_state()
    
    def on_stop(self):
        """策略停止时自动保存"""
        print("[NewsRadarStrategy] 策略停止，自动保存状态...")
        self._stop_auto_save()
        return self.radar.save_state()

    def on_start(self):
        """策略启动时自动加载"""
        print("[NewsMindStrategy] 策略启动，自动加载状态...")
        self._start_auto_save()
        return self.radar.load_state()
