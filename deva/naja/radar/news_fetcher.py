"""
Radar News Fetcher - 雷达内置新闻获取器

功能:
1. 自己获取新闻（不依赖数据源系统）
2. 内置新闻舆情处理能力（主题聚类、记忆等）
3. 直接输出信号给认知系统
4. 根据交易时间自动启停
"""

import hashlib
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
            "芯片": [3, "半导体/芯片"],
            "半导体": [3, "半导体/芯片"],
            "华为": [4, "华为产业链"],
            "新能源": [5, "新能源"],
            "光伏": [6, "光伏"],
            "锂电池": [7, "锂电池/储能"],
            "储能": [7, "锂电池/储能"],
            "电动车": [8, "新能源汽车"],
            "汽车": [8, "新能源汽车"],
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
        return f"主题_{topic_id}"


class RadarNewsProcessor:
    """
    雷达新闻处理器

    内置处理能力：
    1. 主题聚类
    2. 短期记忆
    3. 注意力评分
    4. 信号生成
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}

        self._short_memory_size = int(cfg.get("short_memory_size", 100))
        self._mid_memory_size = int(cfg.get("mid_memory_size", 50))
        self._attention_threshold = float(cfg.get("attention_threshold", 0.6))

        self._topic_cluster = NewsTopicCluster()

        self._short_memory: Deque[NewsItem] = deque(maxlen=self._short_memory_size)
        self._mid_memory: Deque[NewsItem] = deque(maxlen=self._mid_memory_size)
        self._long_memory: List[NewsItem] = []

        self._topic_counts: Dict[int, int] = {}
        self._last_signal_time: float = 0
        self._signal_cooldown = float(cfg.get("signal_cooldown", 60))

        self._stats = {
            "total_processed": 0,
            "high_attention": 0,
            "signals_generated": 0,
            "topics_identified": 0,
        }

    def process(self, news: NewsItem) -> List[Dict]:
        """
        处理单条新闻

        Returns:
            信号列表
        """
        signals = []

        topic_id = self._topic_cluster.assign_topic(news.title, news.content)
        news.meta["topic_id"] = topic_id
        news.meta["topic_name"] = self._topic_cluster.get_topic_name(topic_id)

        self._short_memory.append(news)
        self._topic_counts[topic_id] = self._topic_counts.get(topic_id, 0) + 1

        attention_score = self._calc_attention_score(news, topic_id)
        news.meta["attention_score"] = attention_score

        if attention_score >= self._attention_threshold:
            self._mid_memory.append(news)
            self._stats["high_attention"] += 1

            if time.time() - self._last_signal_time >= self._signal_cooldown:
                signal = self._generate_signal(news, topic_id, attention_score)
                if signal:
                    signals.append(signal)
                    self._last_signal_time = time.time()
                    self._stats["signals_generated"] += 1

        self._stats["total_processed"] += 1
        self._stats["topics_identified"] = len(self._topic_counts)

        return signals

    def _calc_attention_score(self, news: NewsItem, topic_id: int) -> float:
        """计算注意力评分"""
        score = 0.5

        title_len = len(news.title)
        if title_len > 20:
            score += 0.1
        if title_len > 40:
            score += 0.1

        topic_count = self._topic_counts.get(topic_id, 0)
        if topic_count >= 3:
            score += 0.2
        if topic_count >= 5:
            score += 0.1

        keywords = ["突发", "紧急", "重磅", "暴跌", "暴涨", "警告", "违约", "危机"]
        for kw in keywords:
            if kw in news.title:
                score += 0.1
                break

        return min(1.0, score)

    def _generate_signal(self, news: NewsItem, topic_id: int, attention_score: float) -> Optional[Dict]:
        """生成信号"""
        topic_name = self._topic_cluster.get_topic_name(topic_id)

        return {
            "source": "radar_news",
            "signal_type": "news_topic",
            "score": attention_score,
            "content": f"[{topic_name}] {news.title}",
            "raw_data": {
                "news_id": news.id,
                "topic_id": topic_id,
                "topic_name": topic_name,
                "source": news.source,
            },
            "timestamp": news.timestamp.timestamp(),
            "metadata": {
                "attention_score": attention_score,
                "topic_count": self._topic_counts.get(topic_id, 0),
            },
        }

    def get_report(self) -> Dict:
        """获取处理报告"""
        recent_news = []
        for item in list(self._short_memory)[-5:]:
            recent_news.append({
                "id": item.id,
                "title": item.title,
                "source": item.source,
                "timestamp": item.timestamp.isoformat(),
                "attention_score": item.meta.get("attention_score", 0),
                "topic_name": item.meta.get("topic_name", ""),
            })

        return {
            "stats": self._stats.copy(),
            "short_memory_size": len(self._short_memory),
            "mid_memory_size": len(self._mid_memory),
            "recent_news": recent_news,
            "topics": {
                tid: {
                    "name": self._topic_cluster.get_topic_name(tid),
                    "count": count,
                }
                for tid, count in self._topic_counts.items()
            },
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
                if self._current_phase in ('trading', 'pre_market'):
                    self._tick()
                    time.sleep(self._fetch_interval)
                else:
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

        这里实现了两种模式：
        1. 模拟模式：返回模拟新闻（用于测试）
        2. 实盘模式：从真实来源获取新闻

        可以扩展支持：
        - 金十数据API
        - 东方财富API
        - RSS订阅
        - 自定义新闻源
        """
        try:
            news_list = self._fetch_from_source()

            if not news_list:
                news_list = self._generate_simulated_news()

            return news_list

        except Exception as e:
            log.debug(f"[Radar-News] 获取新闻失败: {e}")
            return []

    def _fetch_from_source(self) -> List[NewsItem]:
        """
        从真实来源获取新闻

        默认返回空列表，子类可覆盖实现真实获取
        """
        return []

    def _generate_simulated_news(self) -> List[NewsItem]:
        """生成模拟新闻（用于测试）"""
        import random

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


class RadarNewsFetcherV2(RadarNewsFetcher):
    """
    雷达新闻获取器 V2

    支持更丰富的新闻源
    """

    def _fetch_from_source(self) -> List[NewsItem]:
        """从真实来源获取新闻"""
        try:
            import requests

            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            }

            news_list = []

            try:
                response = requests.get(
                    "https://api.jin10.com/get_news_list",
                    headers=headers,
                    timeout=5,
                )
                if response.status_code == 200:
                    data = response.json()
                    for item in data.get("data", []):
                        news = NewsItem(
                            id=str(item.get("id", "")),
                            timestamp=datetime.fromtimestamp(item.get("time", 0) / 1000),
                            source="jin10",
                            title=item.get("title", ""),
                            content=item.get("content", ""),
                        )
                        news_list.append(news)
            except Exception:
                pass

            return news_list

        except ImportError:
            log.debug("[Radar-News-V2] requests库未安装，使用模拟数据")
            return []
        except Exception as e:
            log.debug(f"[Radar-News-V2] 获取新闻失败: {e}")
            return []
