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
    TRADING_CLOCK_STREAM,
    is_trading_time as is_trading_time_clock,
)

# 从统一关键词注册表导入
from deva.naja.cognition.keyword_registry import NEWS_TOPIC_KEYWORDS
from deva.naja.register import SR

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
    """新闻主题聚类（使用统一的关键词注册表）"""

    def __init__(self):
        self._topics: Dict[int, List[str]] = {}
        self._topic_keywords: Dict[int, List[str]] = {}
        self._topic_counter = 0

        # 从统一的关键词注册表导入（转换为 list 格式）
        self._keyword_topics = {
            kw: list(value) for kw, value in NEWS_TOPIC_KEYWORDS.items()
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

    持久化：
    - 短期记忆保存在 NB 表中，重启后可恢复
    """

    NEWS_TABLE = "naja_radar_news"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self._short_memory_size = int(cfg.get("short_memory_size", 100))
        self._short_memory: Deque[NewsItem] = deque(maxlen=self._short_memory_size)
        self._nb = None
        self._load_from_persistence()

    def _load_from_persistence(self):
        """从持久化存储加载新闻摘要"""
        try:
            from deva import NB
            self._nb = NB(self.NEWS_TABLE)

            saved_summary = self._nb.get("daily_summary", {})
            if saved_summary:
                _radar_news_log(f"[RadarNewsProcessor] 从持久化恢复新闻摘要: {saved_summary.get('count', 0)} 条")
        except Exception as e:
            _radar_news_log(f"[RadarNewsProcessor] 加载持久化失败: {e}")
            self._nb = None

    def _save_to_persistence(self):
        """保存新闻摘要到持久化存储（只保存状态，不保存实体）"""
        if not self._nb:
            return

        try:
            now = datetime.now()
            today = now.strftime('%Y-%m-%d')

            saved_summary = self._nb.get("daily_summary", {})
            existing_today = saved_summary.get(today, {})

            news_list = list(self._short_memory)
            today_news = [
                {"title": item.title, "source": item.source}
                for item in news_list
                if item.timestamp and item.timestamp.strftime('%Y-%m-%d') == today
            ]

            macro_keywords = ["地缘政治", "宏观经济", "美联储", "通胀", "加息", "降息", "战争", "制裁", "经济"]
            industry_keywords = ["财报", "业绩", "营收", "利润", "超预期", "不及预期"]

            macro_titles = [n["title"] for n in today_news if any(kw in n["title"] for kw in macro_keywords)]
            industry_titles = [n["title"] for n in today_news if any(kw in n["title"] for kw in industry_keywords)]

            summary = {
                "count": len(today_news),
                "macro_count": len(macro_titles),
                "macro_titles": macro_titles[-5:],
                "industry_count": len(industry_titles),
                "industry_titles": industry_titles[-5:],
                "last_updated": now.isoformat(),
            }

            saved_summary[today] = summary

            recent_days = sorted(saved_summary.keys())[-7:]
            trimmed_summary = {k: saved_summary[k] for k in recent_days}

            self._nb["daily_summary"] = trimmed_summary
        except Exception as e:
            _radar_news_log(f"[RadarNewsProcessor] 保存持久化失败: {e}")

    def process(self, news: NewsItem) -> List[Dict]:
        """
        处理单条新闻（极简流程）

        1. 存入短期记忆（供雷达面板显示）
        2. 发送到认知系统进行深度处理
        3. 持久化到 NB 存储
        """
        self._short_memory.append(news)
        self._send_to_cognition_simple(news)
        self._save_to_persistence()
        return []

    def _send_to_cognition_simple(self, news: NewsItem) -> None:
        """发送原始新闻到认知系统进行深度处理"""
        try:
            cognition = SR('cognition_engine')
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
        'call_auction': 60.0,
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
            self._fetch_count += 1
            _radar_news_log(f"获取新闻: {news.title[:50]}")

            self._publish_text_fetched(news)

            self.processor.process(news)

    def _publish_text_fetched(self, news: NewsItem):
        """
        将新闻发布到事件总线

        发布 TextFetchedEvent 供 Attention 系统进行重要性评分
        """
        try:
            from deva.naja.events.text_events import TextFetchedEvent
            from deva.naja.events import get_event_bus

            keywords = []
            topics = []
            sentiment = 0.5

            if hasattr(self.processor, 'extract_keywords'):
                try:
                    keywords = self.processor.extract_keywords(news.content)
                except Exception:
                    pass

            event = TextFetchedEvent(
                text=news.content,
                title=news.title,
                source="radar_news",
                url=news.url,
                timestamp=news.timestamp or time.time(),
                keywords=keywords,
                topics=topics,
                sentiment=sentiment,
            )

            event_bus = get_event_bus()
            event_bus.publish(event)

            _radar_news_log(f"发布 TextFetchedEvent: {news.title[:50]}")

        except ImportError as e:
            _radar_news_log(f"事件架构导入失败: {e}")
        except Exception as e:
            log.error(f"[Radar-News] 发布 TextFetchedEvent 失败: {e}")

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
                    f"重磅！{keyword}题材迎来重大利好",
                    f"突发：{keyword}行业传来重磅消息",
                    f"【{topic_name}】{keyword}概念持续火爆",
                    f"{keyword}产业链个股集体涨停",
                    f"机构密集调研{keyword}相关标的",
                    f"政策加码！{keyword}迎发展机遇",
                    f"{keyword}龙头业绩超预期增长",
                    f"资金大幅流入{keyword}题材",
                ]
            else:
                titles = [
                    f"{keyword}题材个股普跌",
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
