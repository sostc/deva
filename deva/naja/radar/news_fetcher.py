"""
Radar News Fetcher - 感知系统/新闻抓取/舆情

别名/关键词: 新闻抓取、news_fetcher、舆情、sentiment

功能:
1. 自己获取新闻（不依赖数据源系统）
2. 内置新闻舆情处理能力（主题聚类、记忆等）
3. 直接输出信号给认知系统
4. 根据交易时间自动启停
"""

import hashlib
import json
import random
import threading
import time
import logging
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from .trading_clock import (
    get_trading_clock,
    TRADING_CLOCK_STREAM,
    is_trading_time as is_trading_time_clock,
)

try:
    import numpy as np
except ImportError:
    np = None

log = logging.getLogger(__name__)


def _radar_news_log(msg: str):
    """雷达新闻日志"""
    if os.environ.get("NAJA_RADAR_DEBUG") == "true":
        log.info(f"[Radar-News] {msg}")


def _extract_title_from_content(content: str, max_len: int = 60) -> str:
    """
    从金十数据content中提取有意义的标题

    金十数据格式通常是：
    【金十数据整理：XXX】实际内容<无关HTML>

    这个函数会：
    1. 去除HTML标签
    2. 跳过固定前缀（如【金十数据整理：...】）
    3. 提取实际有意义的内容作为标题
    """
    import re

    clean = re.sub(r'<[^>]+>', '', content).strip()

    patterns_to_skip = [
        r'^【金十数据整理[：：][^】]*】',
        r'^【今日要闻[：：][^】]*】',
        r'^【市场快讯[：：][^】]*】',
        r'^【财经日历[：：][^】]*】',
        r'^【操盘必读[：：][^】]*】',
        r'^【涨停复盘[：：][^】]*】',
        r'^【要闻[：：][^】]*】',
        r'^【金十数据整理】',
        r'^【今日要闻】',
        r'^【市场快讯】',
        r'^【财经日历】',
        r'^【操盘必读】',
        r'^【涨停复盘】',
        r'^【要闻】',
    ]
    for pattern in patterns_to_skip:
        clean = re.sub(pattern, '', clean).strip()

    prefixes_to_remove = ['国内新闻：', '国外新闻：', '市场新闻：', '快讯：', '最新：', '实时：']
    for prefix in prefixes_to_remove:
        if clean.startswith(prefix):
            clean = clean[len(prefix):].strip()

    if not clean:
        return content[:max_len] + ("..." if len(content) > max_len else "")

    sentences = re.split(r'[。！？\n]', clean)
    if sentences and sentences[0].strip():
        first = sentences[0].strip()
        if len(first) > max_len:
            return first[:max_len] + "..."
        return first

    if len(clean) > max_len:
        return clean[:max_len] + "..."
    return clean


@dataclass
class NewsItem:
    """新闻条目"""
    id: str
    timestamp: datetime
    source: str
    title: str
    content: str = ""
    url: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "meta": self.meta,
        }


class NewsTopicCluster:
    """新闻主题聚类"""

    def __init__(self):
        self._topics: Dict[int, List[str]] = {}
        self._topic_keywords: Dict[int, List[str]] = {}
        self._topic_counter = 0

        self._keyword_topics = {
            "ai": [1, "AI/人工智能"],
            "人工智能": [1, "AI/人工智能"],
            "chatgpt": [2, "ChatGPT/大模型"],
            "gpt": [2, "ChatGPT/大模型"],
            "大模型": [2, "ChatGPT/大模型"],
            "deepseek": [2, "ChatGPT/大模型"],
            "芯片": [3, "半导体/芯片"],
            "半导体": [3, "半导体/芯片"],
            "华为": [4, "华为产业链"],
            "新能源": [5, "新能源"],
            "光伏": [6, "光伏"],
            "锂电池": [7, "锂电池/储能"],
            "储能": [7, "锂电池/储能"],
            "电动车": [8, "新能源汽车"],
            "汽车": [8, "新能源汽车"],
            "特斯拉": [8, "新能源汽车"],
            "苹果": [9, "苹果产业链"],
            "iphone": [9, "苹果产业链"],
            "数据": [10, "大数据/云计算"],
            "云计算": [10, "大数据/云计算"],
            "银行": [11, "金融/银行"],
            "保险": [12, "金融/保险"],
            "券商": [13, "金融/券商"],
            "美股": [14, "美股"],
            "港股": [15, "港股"],
            "A股": [16, "A股"],
            "加息": [17, "宏观/美联储"],
            "美联储": [17, "宏观/美联储"],
            "通胀": [18, "宏观/通胀"],
            "战争": [19, "地缘政治"],
            "制裁": [19, "地缘政治"],
            "地震": [20, "自然灾害"],
            "灾难": [20, "自然灾害"],
            "暴雨": [20, "自然灾害"],
            "洪水": [20, "自然灾害"],
            "干旱": [20, "自然灾害"],
            "火山": [20, "自然灾害"],
            "疫情": [21, "公共卫生"],
            "病毒": [21, "公共卫生"],
            "流感": [21, "公共卫生"],
            "经济": [22, "宏观经济"],
            "增长": [22, "宏观经济"],
            "衰退": [22, "宏观经济"],
            "贸易": [23, "国际贸易"],
            "关税": [23, "国际贸易"],
            "出口": [23, "国际贸易"],
            "进口": [23, "国际贸易"],
            "原油": [24, "大宗商品/原油"],
            "黄金": [25, "大宗商品/黄金"],
            "白银": [25, "大宗商品/黄金"],
            "美元": [26, "外汇/美元"],
            "人民币": [27, "外汇/人民币"],
            "欧元": [28, "外汇/欧元"],
            "英伟达": [3, "半导体/芯片"],
            "英特": [3, "半导体/芯片"],
            "AMD": [3, "半导体/芯片"],
            "阿里": [29, "互联网/电商"],
            "腾讯": [29, "互联网/电商"],
            "京东": [29, "互联网/电商"],
            "字节": [30, "互联网/短视频"],
            "抖音": [30, "互联网/短视频"],
            "快手": [30, "互联网/短视频"],
            "百度": [31, "互联网/搜索"],
            "微软": [32, "科技/软件"],
            "谷歌": [32, "科技/软件"],
            "亚马逊": [33, "电商/云服务"],
            "Meta": [34, "社交媒体"],
            "Facebook": [34, "社交媒体"],
            "推特": [34, "社交媒体"],
            "马斯克": [35, "人物/商业领袖"],
            "贝索斯": [35, "人物/商业领袖"],
            "普京": [36, "人物/政治"],
            "拜登": [36, "人物/政治"],
            "特朗普": [36, "人物/政治"],
            "OPEC": [37, "原油/能源"],
            "沙特": [37, "原油/能源"],
            "俄罗斯": [38, "地缘政治"],
            "乌克兰": [38, "地缘政治"],
            "中东": [39, "地缘政治"],
            "朝鲜": [39, "地缘政治"],
            "韩国": [40, "地缘政治"],
            "日本": [41, "宏观经济"],
            "印度": [41, "宏观经济"],
            "英国": [42, "宏观经济"],
            "德国": [42, "宏观经济"],
            "法国": [42, "宏观经济"],
            "大选": [43, "政治事件"],
            "选举": [43, "政治事件"],
            "峰会": [44, "政治事件"],
            "G20": [44, "政治事件"],
            "WTO": [45, "国际贸易"],
            "IMF": [46, "国际组织"],
            "世界银行": [46, "国际组织"],
            "财报": [47, "企业业绩"],
            "业绩": [47, "企业业绩"],
            "营收": [47, "企业业绩"],
            "利润": [47, "企业业绩"],
            "亏损": [47, "企业业绩"],
            "裁员": [48, "企业动态"],
            "收购": [49, "企业动态"],
            "并购": [49, "企业动态"],
            "上市": [50, "企业动态"],
            "IPO": [50, "企业动态"],
            "房地产": [51, "房地产"],
            "房价": [51, "房地产"],
            "地产": [51, "房地产"],
            "建筑": [51, "房地产"],
            "水泥": [51, "房地产"],
            "钢铁": [52, "原材料"],
            "铜": [52, "原材料"],
            "铝": [52, "原材料"],
            "煤炭": [53, "能源"],
            "电力": [54, "公用事业"],
            "电网": [54, "公用事业"],
            "5G": [55, "通信技术"],
            "6G": [55, "通信技术"],
            "元宇宙": [56, "新技术"],
            "区块链": [57, "新技术"],
            "web3": [57, "新技术"],
            "NFT": [57, "新技术"],
            "量子": [58, "新技术"],
            "生物": [59, "生物医药"],
            "医药": [59, "生物医药"],
            "疫苗": [59, "生物医药"],
            "茅台": [60, "消费/白酒"],
            "白酒": [60, "消费/白酒"],
            "食品": [61, "消费/食品"],
            "饮料": [61, "消费/食品"],
            "纺织": [62, "制造业"],
            "服装": [62, "制造业"],
            "家电": [63, "制造业"],
            "美的": [63, "制造业"],
            "格力": [63, "制造业"],
            "石化": [64, "化工"],
            "化工": [64, "化工"],
            "农药": [64, "化工"],
            "化肥": [65, "农业"],
            "农业": [65, "农业"],
            "养殖": [65, "农业"],
            "渔业": [65, "农业"],
            "木材": [66, "原材料"],
            "造纸": [66, "原材料"],
            "印刷": [66, "原材料"],
            "环保": [67, "环保"],
            "碳中和": [67, "环保"],
            " ESG ": [67, "环保"],
            "绿色": [67, "环保"],
            "可再生能源": [68, "新能源"],
            "氢能": [68, "新能源"],
            "风能": [68, "新能源"],
            "核电": [69, "能源"],
            "水利": [70, "基建"],
            "铁路": [71, "交通基建"],
            "公路": [71, "交通基建"],
            "航空": [72, "交通运输"],
            "机场": [72, "交通运输"],
            "港口": [72, "交通运输"],
            "物流": [73, "交通运输"],
            "快递": [73, "交通运输"],
            "教育": [74, "服务业"],
            "旅游": [75, "服务业"],
            "酒店": [75, "服务业"],
            "餐饮": [75, "服务业"],
            "电影": [76, "文娱"],
            "游戏": [76, "文娱"],
            "体育": [77, "文娱"],
            "足球": [77, "文娱"],
            "篮球": [77, "文娱"],
            "奥运": [77, "文娱"],
        }

    def assign_topic(self, title: str, content: str = "") -> int:
        """根据关键词分配主题"""
        text = (title + " " + content).lower()

        for keyword, (topic_id, topic_name) in self._keyword_topics.items():
            if keyword in text:
                if topic_id not in self._topics:
                    self._topics[topic_id] = []
                    self._topic_keywords[topic_id] = []
                if title not in self._topics[topic_id]:
                    self._topics[topic_id].append(title)
                return topic_id

        self._topic_counter += 1
        self._topics[self._topic_counter] = [title]
        return self._topic_counter

    def get_topic_name(self, topic_id: int) -> str:
        """获取主题名称"""
        for keyword, (tid, name) in self._keyword_topics.items():
            if tid == topic_id:
                return name
        topic_titles = self._topics.get(topic_id, [])
        if topic_titles:
            first_title = topic_titles[0]
            if len(first_title) > 15:
                return first_title[:15] + "..."
            return first_title
        return f"主题_{topic_id}"


class RadarNewsProcessor:
    """
    雷达新闻处理器（极简版）

    只负责：
    1. 新闻存储（供雷达面板显示）
    2. 将原始新闻发送给认知系统（NewsMind 处理）

    所有深度处理（主题分类、注意力评分、叙事追踪等）由认知系统完成
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self._short_memory_size = int(cfg.get("short_memory_size", 100))
        self._short_memory: Deque[NewsItem] = deque(maxlen=self._short_memory_size)

    def process(self, news: NewsItem) -> List[Dict]:
        """
        处理单条新闻（极简流程）

        1. 存入短期记忆（供雷达面板显示）
        2. 发送到认知系统进行深度处理
        """
        self._short_memory.append(news)
        self._send_to_cognition_simple(news)
        return []

    def _send_to_cognition_simple(self, news: NewsItem) -> None:
        """发送原始新闻到认知系统进行深度处理"""
        try:
            from deva.naja.cognition import get_cognition_engine
            cognition = get_cognition_engine()
            record = {
                "timestamp": news.timestamp.timestamp(),
                "source": "radar_news",
                "type": "news",
                "title": news.title,
                "content": news.content,
            }
            signals = cognition.process_record(record)
            if signals:
                self._send_signals_to_insight(signals)
        except ImportError:
            pass
        except Exception as e:
            _radar_news_log(f"发送认知引擎失败: {e}")

    def _send_signals_to_insight(self, signals: List[Dict]) -> None:
        """发送认知信号到洞察池和CrossSignalAnalyzer"""
        try:
            from deva.naja.cognition.insight import emit_to_insight_pool
            from deva.naja.cognition.cross_signal_analyzer import get_cross_signal_analyzer
            analyzer = get_cross_signal_analyzer()

            for signal in signals:
                emit_to_insight_pool(signal)
                analyzer.ingest_news_from_signal(signal)
        except ImportError:
            pass
        except Exception as e:
            _radar_news_log(f"发送洞察池失败: {e}")

    def get_report(self) -> Dict:
        """获取处理报告"""
        recent_news = []
        for item in list(self._short_memory)[-5:]:
            recent_news.append({
                "id": item.id,
                "title": item.title,
                "source": item.source,
                "timestamp": item.timestamp.isoformat(),
            })

        return {
            "short_memory_size": len(self._short_memory),
            "recent_news": recent_news,
        }


class RadarNewsFetcher:
    """
    雷达内置新闻获取器

    完全独立于数据源系统，自己获取和处理新闻

    事件驱动：
    - 订阅 TRADING_CLOCK_STREAM 信号（正常模式）
    - 收到 phase_change 信号时调整获取间隔
    - 交易时间间隔小，非交易时间间隔大

    强制模式（force_trading_mode=True）：
    - 不订阅交易时钟
    - 持续全速运行，不受交易时间限制
    """

    PHASE_INTERVALS = {
        'trading': 60.0,
        'pre_market': 60.0,
        'lunch': 300.0,
        'post_market': 300.0,
        'closed': 300.0,
    }

    def __init__(
        self,
        processor: Optional[RadarNewsProcessor] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.processor = processor or RadarNewsProcessor(config)
        self.config = config or {}

        self._running = False
        self._fetch_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._fetch_interval = float(self.config.get("fetch_interval", 60))
        self._base_interval = self._fetch_interval
        self._target_interval = self._fetch_interval
        self._force_trading = self.config.get("force_trading_mode", False)
        self._is_trading_day = False
        self._last_trading_check = 0.0

        self._fetch_count = 0
        self._error_count = 0

        self._on_signal_callback: Optional[callable] = None

        self._llm_interval_override: Optional[float] = None
        self._last_interval_adjustment = 0.0

        self._pre_market_minutes = int(self.config.get("pre_market_minutes", 30))
        self._post_market_minutes = int(self.config.get("post_market_minutes", 30))

        self._performance_adjustment = 0.0
        self._last_perf_check = 0.0

        self._current_phase: str = 'closed' if not self._force_trading else 'trading'

    def _on_trading_clock_signal(self, signal: Dict[str, Any]):
        """处理交易时钟信号"""
        signal_type = signal.get('type')
        phase = signal.get('phase')

        if signal_type == 'current_state':
            self._current_phase = phase
            new_interval = self._get_interval_for_phase(phase)
            if new_interval != self._fetch_interval:
                self._fetch_interval = new_interval
                _radar_news_log(f"当前时段 {phase}，调整获取间隔: {self._fetch_interval}s")

        elif signal_type == 'phase_change':
            old_phase = signal.get('previous_phase', 'unknown')
            new_phase = phase
            self._current_phase = new_phase
            new_interval = self._get_interval_for_phase(new_phase)

            if new_interval != self._fetch_interval:
                old_interval = self._fetch_interval
                self._fetch_interval = new_interval
                log.info(f"[Radar-News] 时段变化 {old_phase} -> {new_phase}，"
                        f"调整获取间隔: {old_interval:.0f}s -> {self._fetch_interval:.0f}s")

    def _get_interval_for_phase(self, phase: str) -> float:
        """根据时段获取对应间隔"""
        if self._force_trading:
            return self._base_interval
        return self.PHASE_INTERVALS.get(phase, 300.0)

    def start(self):
        """启动获取器"""
        if self._running:
            log.warning("[Radar-News] 获取器已在运行中")
            return

        self._running = True
        self._stop_event.clear()

        if not self._force_trading:
            TRADING_CLOCK_STREAM.sink(self._on_trading_clock_signal)
        else:
            log.info("[Radar-News] 强制交易模式，跳过交易时钟订阅")

        self._fetch_thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._fetch_thread.start()

        log.info(f"[Radar-News] 已启动, 获取间隔: {self._fetch_interval}s")

    def stop(self):
        """停止获取器"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._fetch_thread:
            self._fetch_thread.join(timeout=5.0)

        log.info("[Radar-News] 已停止")

    def set_signal_callback(self, callback: callable):
        """设置信号回调"""
        self._on_signal_callback = callback

    def adjust_interval(self, interval: float, reason: str = ""):
        """
        动态调整获取间隔

        Args:
            interval: 新的获取间隔（秒）
            reason: 调整原因
        """
        old_interval = self._fetch_interval
        self._fetch_interval = max(1.0, min(interval, 300.0))

        if abs(old_interval - self._fetch_interval) > 0.5:
            _radar_news_log(f"获取间隔调整: {old_interval:.1f}s -> {self._fetch_interval:.1f}s ({reason})")

    def set_interval(self, interval: float):
        """
        外部接口设置获取间隔（供 speed_mode 等外部调用）

        Args:
            interval: 新的获取间隔（秒），会在 1-300 秒之间 clamped
        """
        old_interval = self._fetch_interval
        self._fetch_interval = max(1.0, min(interval, 300.0))
        self._base_interval = self._fetch_interval
        if abs(old_interval - self._fetch_interval) > 0.5:
            log.info(f"[Radar-News] 外部设置获取间隔: {old_interval:.1f}s -> {self._fetch_interval:.1f}s")

    def set_interval_from_llm(self, interval: float, reason: str = ""):
        """
        LLM调用设置获取间隔

        Args:
            interval: LLM建议的获取间隔（秒）
            reason: LLM给出的原因
        """
        self._llm_interval_override = max(1.0, min(interval, 300.0))
        self._last_interval_adjustment = time.time()
        _radar_news_log(f"LLM建议调整获取间隔: {self._fetch_interval:.1f}s -> {self._llm_interval_override:.1f}s ({reason})")

    def get_interval_recommendation(self) -> Dict[str, Any]:
        """
        获取当前间隔推荐值（供LLM参考）

        Returns:
            包含当前状态和建议的字典
        """
        stats = self.get_stats()
        processor_stats = stats.get('processor_stats', {}).get('stats', {})

        signal_rate = processor_stats.get('signals_generated', 0) / max(1, self._fetch_count)

        recommendation = {
            "current_interval": self._fetch_interval,
            "llm_override": self._llm_interval_override,
            "base_interval": self._base_interval,
            "signal_rate": signal_rate,
            "total_fetched": self._fetch_count,
            "total_signals": processor_stats.get('signals_generated', 0),
            "current_phase": self._current_phase,
            "suggested_interval": self._base_interval,
            "suggestion_reason": "",
        }

        if signal_rate > 0.5:
            recommendation["suggested_interval"] = self._base_interval * 0.5
            recommendation["suggestion_reason"] = "高信号频率，加快获取"
        elif signal_rate > 0.3:
            recommendation["suggested_interval"] = self._base_interval * 0.75
            recommendation["suggestion_reason"] = "中等信号频率，适当加快"
        elif signal_rate < 0.1 and self._fetch_count > 10:
            recommendation["suggested_interval"] = self._base_interval * 1.5
            recommendation["suggestion_reason"] = "低信号频率，降低获取频率"

        return recommendation

    def _fetch_loop(self):
        """获取循环 - 持续运行，根据交易时段调整间隔"""
        log.info("[Radar-News] 获取循环开始")

        while self._running and not self._stop_event.is_set():
            try:
                self._tick()
                time.sleep(self._fetch_interval)
            except Exception as e:
                self._error_count += 1
                log.error(f"[Radar-News] 获取异常: {e}")
                time.sleep(5)

        log.info("[Radar-News] 获取循环结束")

    def _is_trading_time(self) -> bool:
        """判断是否在交易时间内"""
        if self._force_trading:
            return True
        return is_trading_time_clock()

    def _get_trading_phase(self) -> str:
        """
        获取当前交易时段

        Returns:
            "closed": 收盘/休市
            "pre_market": 盘前
            "trading": 交易中
            "lunch": 午间休市
        """
        if self._force_trading:
            return "trading"
        return self._current_phase

    def _get_interval_multiplier(self) -> float:
        """
        根据交易时段获取间隔倍数

        Returns:
            间隔倍数
        """
        phase = self._get_trading_phase()

        if phase == "trading":
            return 1.0
        elif phase == "pre_market":
            return 0.8
        elif phase == "post_market":
            return 1.2
        elif phase == "lunch":
            return 1.5
        else:
            return 2.0

    def _auto_adjust_by_performance(self):
        """根据性能自动调节频率"""
        current_time = time.time()

        if current_time - self._last_perf_check < 60:
            return

        self._last_perf_check = current_time

        stats = self.get_stats()
        processor_stats = stats.get('processor_stats', {}).get('stats', {})

        signal_rate = processor_stats.get('signals_generated', 0) / max(1, self._fetch_count)

        adjustment = 0.0
        reason = ""

        if signal_rate > 0.5:
            adjustment = -0.2
            reason = "高信号频率"
        elif signal_rate > 0.3:
            adjustment = -0.1
            reason = "中等信号频率"
        elif signal_rate < 0.1 and self._fetch_count > 10:
            adjustment = 0.3
            reason = "低信号频率"

        phase_mult = self._get_interval_multiplier()

        if adjustment != 0.0:
            new_interval = self._base_interval * (1 + adjustment) * phase_mult
            self.adjust_interval(new_interval, f"{reason}, {self._get_trading_phase()}")

    def _tick(self):
        """一次tick"""
        self._auto_adjust_by_performance()

        news_list = self._fetch_news()

        for news in news_list:
            signals = self.processor.process(news)

            for signal in signals:
                self._fetch_count += 1
                _radar_news_log(f"产生信号: {signal.get('content', '')[:50]}")

                if self._on_signal_callback:
                    try:
                        self._on_signal_callback(signal)
                    except Exception as e:
                        log.error(f"[Radar-News] 信号回调异常: {e}")

    def _fetch_news(self) -> List[NewsItem]:
        """
        获取新闻

        优先从真实来源获取，失败时返回模拟数据
        """
        try:
            news_list = self._fetch_from_source()
            if news_list:
                return news_list

            _radar_news_log("真实数据获取失败，使用模拟数据")
            return self._generate_simulated_news()

        except Exception as e:
            log.debug(f"[Radar-News] 获取新闻失败: {e}")
            return []

    def _fetch_from_source(self) -> List[NewsItem]:
        """
        从真实来源获取新闻（金十数据API）

        Returns:
            新闻列表
        """
        try:
            import requests
        except ImportError:
            log.debug("[Radar-News] requests库未安装，无法获取真实数据")
            return []

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            }

            response = requests.get(
                "https://www.jin10.com/flash_newest.js",
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Referer": "https://www.jin10.com/",
                },
                timeout=5,
            )
            if response.status_code == 200:
                text = response.text.strip()
                prefix = "var newest ="
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()
                if text.endswith(";"):
                    text = text[:-1].strip()
                data = json.loads(text)
                news_list = []
                for item in data:
                    inner = item.get("data", {})
                    content = inner.get("content", "").strip()
                    if not content:
                        continue
                    title = _extract_title_from_content(content)
                    time_str = item.get("time", "")
                    try:
                        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                        ts = dt.timestamp()
                    except Exception:
                        ts = time.time()
                    news = NewsItem(
                        id=str(item.get("id", "")),
                        timestamp=datetime.fromtimestamp(ts),
                        source="jin10",
                        title=title,
                        content=content,
                    )
                    news_list.append(news)
                if news_list:
                    _radar_news_log(f"从金十API获取到 {len(news_list)} 条新闻")
                return news_list
            return []

        except Exception as e:
            log.debug(f"[Radar-News] 获取金十数据失败: {e}")
            return []

    def _generate_simulated_news(self) -> List[NewsItem]:
        """生成模拟新闻（用于测试）"""
        topics = [
            ("AI", ["ChatGPT", "人工智能", "大模型", "AI应用", "AIGC"]),
            ("芯片", ["半导体", "芯片国产替代", "光刻机", "集成电路"]),
            ("新能源", ["锂电池", "光伏", "储能", "新能源汽车", "充电桩"]),
            ("宏观", ["美联储", "加息", "通胀", "GDP", "CPI"]),
            ("金融", ["银行", "券商", "保险", "基金"]),
            ("产业", ["华为", "苹果", "特斯拉", "比亚迪"]),
            ("地缘", ["中美关系", "俄乌", "中东", "制裁"]),
            ("A股", ["上证指数", "创业板", "科创板", "北交所"]),
        ]

        news_list = []
        num_news = random.randint(3, 8)

        for _ in range(num_news):
            topic_name, keywords = random.choice(topics)
            keyword = random.choice(keywords)

            if random.random() > 0.5:
                titles = [
                    f"重磅！{keyword}板块迎来重大利好",
                    f"突发：{keyword}行业传来重磅消息",
                    f"【{topic_name}】{keyword}概念持续火爆",
                    f"{keyword}产业链个股集体涨停",
                    f"机构密集调研{keyword}相关标的",
                    f"政策加码！{keyword}迎发展机遇",
                    f"{keyword}龙头业绩超预期增长",
                    f"资金大幅流入{keyword}板块",
                ]
            else:
                titles = [
                    f"{keyword}板块个股普跌",
                    f"解析{keyword}行业最新动态",
                    f"{keyword}产业链追踪报告",
                    f"专家解读{keyword}发展趋势",
                    f"{keyword}市场行情分析",
                ]

            title = random.choice(titles)

            news = NewsItem(
                id=hashlib.md5(f"{title}{time.time()}".encode()).hexdigest()[:16],
                timestamp=datetime.now(),
                source="RadarNewsSimulator",
                title=title,
                content=f"详细报道：{keyword}相关事件持续发酵，市场关注度显著提升。",
            )
            news_list.append(news)

        return news_list

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "running": self._running,
            "is_trading": self._is_trading_time(),
            "trading_phase": self._get_trading_phase(),
            "fetch_interval": self._fetch_interval,
            "llm_override": self._llm_interval_override,
            "base_interval": self._base_interval,
            "fetch_count": self._fetch_count,
            "error_count": self._error_count,
            "processor_stats": self.processor.get_report(),
        }
