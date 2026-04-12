"""
TopicManager - 主题管理

从 core.py 提取，包含：
- Topic: 主题数据结构（dataclass）
- STOCK_RELEVANT_PREFIXES / STOCK_RELEVANT_SOURCES: 股票相关判定常量
- _is_stock_relevant_topic: 判断主题是否与股票相关
- _get_market_activity: 获取当前市场活跃度
"""

import re
from datetime import datetime, timedelta
from collections import deque, Counter
from typing import Dict, List
from dataclasses import dataclass, field

from .news_event import get_datasource_type


STOCK_RELEVANT_PREFIXES = ["[新闻]", "[行情]", "[财经]"]
STOCK_RELEVANT_SOURCES = ["news", "tick", "jin10", "财经", "新闻", "金十", "行情"]


def _get_market_activity() -> float:
    """
    获取当前市场活跃度 (0.0 ~ 1.0)

    从 AttentionOS 获取 harmony 值作为活跃度
    如果获取失败，返回 0.5（默认值）
    """
    try:
        from deva.naja.attention.trading_center import get_trading_center
        tc = get_trading_center()
        harmony = tc.get_harmony()
        return harmony.get("harmony_strength", 0.5)
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
                blocks = ["新能源", "半导体", "医药", "消费", "金融", "地产", "传媒", "军工", "AI", "芯片"]
                for block in blocks:
                    if block in content:
                        all_keywords.append(block)

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

                    file_exts = re.findall(r'\.([a-zA-Z0-9]+)', content)
                    for ext in file_exts[:3]:
                        all_keywords.append(f".{ext}")

        # 统计词频并生成主题名称

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
