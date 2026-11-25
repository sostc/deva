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
import re
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
from deva.naja.cognition.semantic.keyword_registry import NEWS_TOPIC_KEYWORDS
from deva.naja.register import SR
from deva.naja.infra.observability.fleet_registry import KIND_DATASOURCE, probe

try:
    import numpy as np
except ImportError:
    np = None

log = logging.getLogger(__name__)


def _radar_news_log(msg: str):
    """雷达新闻日志"""
    if os.environ.get("NAJA_RADAR_DEBUG") == "true":
        log.info(f"[Radar-News] {msg}")


# ── 舆情分类 ─────────────────────────────────────────────
# 归属「宏观」的主题名（NEWS_TOPIC_KEYWORDS 里的 topic_name），其余主题都算行业
MACRO_TOPICS = frozenset({
    "宏观/美联储", "宏观/通胀", "宏观经济", "地缘政治", "国际贸易",
    "自然灾害", "公共卫生", "外汇/美元", "外汇/人民币", "外汇/欧元",
    "人物/政治", "政治事件", "国际组织", "大宗商品/原油", "大宗商品/黄金",
})

# 公司层面主题优先于宏观：「财报超预期、营收增长30%」会同时命中
# 企业业绩和宏观经济（"增长"挂在宏观经济下），若按宏观优先处理，
# 全部公司新闻都会被吃进宏观桶，行业热点永远空着。
COMPANY_TOPICS = frozenset({"企业业绩", "企业动态"})

# 注册表没覆盖但日报需要的补充词（降息/降准、财报类在注册表里没有或不够）
EXTRA_MACRO_KEYWORDS = (
    "降息", "降准", "贴现率", "国债", "非农", "cpi", "ppi", "gdp",
    "财政", "赤字", "债务上限", "政府停摆", "地缘", "冲突", "谈判",
    "外交", "外长", "会晤", "磋商", "封锁", "禁运", "反制", "峰会",
    # 注册表的地缘政治词只有国名（乌克兰/俄罗斯…），军事事件命中不了，
    # 「胡塞武装发射弹道导弹瞄准亚丁机场」会只因「机场」被判成交通运输行业。
    "导弹", "空袭", "停火", "武装", "国防部", "军事", "战事", "袭击",
)
EXTRA_INDUSTRY_KEYWORDS = (
    "财报", "业绩", "营收", "利润", "毛利率", "净利润", "预增", "预亏",
    "超预期", "不及预期", "订单", "产能", "销量", "出货量", "中标",
    "涨价", "提价", "降价", "裁员", "上市", "并购", "回购", "分红",
)

# 注册表里少数关键词过于宽泛，直接子串匹配会把无关新闻全吃进来：
# 「数据」能命中金十**每一条**标题末尾的「金十数据X月X日讯」，
# 结果「大数据/云计算」主题几乎覆盖全部新闻、行业桶被彻底污染。
# 共享注册表认知系统也在用，不动它，这里换成更具体的词。
WEAK_KEYWORD_OVERRIDES = {
    "数据": ("大数据", "数据中心", "数据要素", "数据资产", "算力", "数据库"),
    "增长": ("经济增长", "gdp增长", "增长放缓", "增长预期", "同比增长"),
}

# 金十标题里的媒体署名：署名之前是新闻本身，之后通常是正文摘要或播报模板
_MEDIA_SIGN_RE = re.compile(r"金十(?:数据|期货|图示|数据整理|快讯|早餐|午评)")


def _clean_title_for_classify(title: str) -> str:
    """剥掉标题里的媒体署名，只留新闻本身

    「【宁波建工：中标价11.58亿元】金十数据10月21日讯，宁波建工公告…」
    → 「【宁波建工：中标价11.58亿元】」
    """
    text = (title or "").strip()
    head = _MEDIA_SIGN_RE.split(text, maxsplit=1)[0].strip()
    # 去掉切完残留的悬空标点
    head = re.sub(r"[\s，,。；;：:、\-—]+$", "", head).strip()
    # 署名就在开头时（「【金十期货图示】金十期货APP独家整理…」）会切出一个「【」，
    # 整条新闻内容被切没了 —— 这种情况退回原文。
    if len(re.findall(r"[\u4e00-\u9fff]", head)) < 2:
        return text
    return head or text


def _cjk_ratio(text: str) -> float:
    """汉字占「汉字+英文字母」的比例"""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    total = len(re.findall(r"[\u4e00-\u9fffA-Za-z]", text or ""))
    return cjk / total if total else 0.0


def _is_chinese_news(title: str) -> bool:
    """是否中文新闻（英文版一律丢弃）

    金十同一条快讯常同时推中英文两版、id 不同，去重拦不住，结果是
    标题中英混排、count 翻倍。实测 47 条里 21 条纯英文（汉字占比 0.00）、
    25 条纯中文（0.6+），0.3 是安全分界；「据匈牙利媒体Telex：…」这类
    中文夹英文名占 0.49，仍算中文。
    """
    return _cjk_ratio(_clean_title_for_classify(title)) >= 0.3


def _match_keyword(keyword: str, text: str) -> bool:
    """关键词匹配

    英文关键词必须整词匹配：`ai` 用子串匹配会命中 `Shanghai` / `said` /
    `again`，把大量无关新闻误判成 AI 主题。
    """
    kw = keyword.lower()
    if kw.isascii():
        return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", text) is not None
    return kw in text


def classify_news(title: str, content: str = "") -> Dict[str, Any]:
    """给新闻打主题标签并判定宏观/行业归属

    只按标题判定：金十的 content 是全文，常夹带「据数据显示」「拟上市」这类
    套话，用全文匹配会让一条「数字人民币全面升级」因为正文提到「上市」
    被归进企业动态，实测误判明显高于只看标题。

    Returns:
        {"topics": [主题名...], "macro": bool}
    """
    text = _clean_title_for_classify(title).lower()
    topics: List[str] = []

    for keyword, (_tid, topic_name) in NEWS_TOPIC_KEYWORDS.items():
        if topic_name in topics:
            continue
        narrowed = WEAK_KEYWORD_OVERRIDES.get(keyword)
        if narrowed is not None:
            if any(alt in text for alt in narrowed):
                topics.append(topic_name)
        elif _match_keyword(keyword, text):
            topics.append(topic_name)

    # 公司层面主题优先，避免"营收增长30%"被「增长→宏观经济」吃进宏观桶
    if any(t in COMPANY_TOPICS for t in topics):
        return {"topics": topics, "macro": False}

    is_macro = any(t in MACRO_TOPICS for t in topics)
    if not is_macro and any(k in text for k in EXTRA_MACRO_KEYWORDS):
        is_macro = True

    return {"topics": topics, "macro": is_macro}


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

    # 每日保留的宏观/行业标题条数上限（持久化累积，重启不丢）
    MAX_TITLES_PER_DAY = 20

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self._short_memory_size = int(cfg.get("short_memory_size", 100))
        self._short_memory: Deque[NewsItem] = deque(maxlen=self._short_memory_size)
        self._nb = None

        # 去重：金十 flash_newest 每次返回滚动窗口（同一批新闻会被反复抓到），
        # 不去重会让 count 每分钟把同一批重复计一遍、标题列表全是重复项。
        self._seen_ids: set = set()
        self._seen_date: str = datetime.now().strftime('%Y-%m-%d')

        # 当日中文新闻条数：英文版不入库，count 不能再拿 _seen_ids 的长度
        # （那里面中英文两版都算），单独计数并随 seen_ids 一起落库。
        self._cn_count: int = 0
        # 当日被丢弃的英文条数（去重后），用于观测金十中英文双发的实际比例
        self._dropped_non_cn: int = 0

        # 落库节流：原来每条新闻都触发一次「读全表→改→写回」，
        # 一分钟 49 条就是 49 次全表重写，且并发下会互相覆盖。
        self._persist_interval = float(cfg.get("persist_interval", 60))
        self._last_persist_ts = 0.0

        self._load_from_persistence()

    def _load_from_persistence(self):
        """从持久化存储加载新闻摘要与当日去重集合"""
        try:
            from deva import NB
            self._nb = NB(self.NEWS_TABLE)

            saved_summary = self._nb.get("daily_summary", {})
            if isinstance(saved_summary, dict) and saved_summary:
                today = datetime.now().strftime('%Y-%m-%d')
                today_data = saved_summary.get(today, {})
                _radar_news_log(
                    f"[RadarNewsProcessor] 从持久化恢复新闻摘要: {today_data.get('count', 0)} 条"
                )

            # 恢复当日已见 id：进程重启后 count 不会归零、也不会重复计数
            seen = self._nb.get("seen_ids", {})
            if isinstance(seen, dict) and seen.get("date") == self._seen_date:
                ids = seen.get("ids") or []
                if isinstance(ids, (list, tuple, set)):
                    self._seen_ids = {str(i) for i in ids}
                    _radar_news_log(f"[RadarNewsProcessor] 恢复当日去重集合: {len(self._seen_ids)} 条")
                try:
                    self._cn_count = int(seen.get("cn_count") or 0)
                except Exception:
                    self._cn_count = 0
                try:
                    self._dropped_non_cn = int(seen.get("dropped_non_cn") or 0)
                except Exception:
                    self._dropped_non_cn = 0
        except Exception as e:
            # 这里原来只写 debug 日志：NB 建不出来时整个持久化层直接失效却无人知晓
            log.warning(f"[Radar-News] 加载持久化失败，新闻摘要将无法落库: {e}")
            self._nb = None

    def _reset_if_new_day(self, today: str):
        """跨天时重置去重集合与中文计数"""
        if self._seen_date != today:
            _radar_news_log(f"[RadarNewsProcessor] 跨天重置去重集合: {self._seen_date} -> {today}")
            self._seen_date = today
            self._seen_ids = set()
            self._cn_count = 0
            self._dropped_non_cn = 0
            self._last_persist_ts = 0.0

    def _record_seen(self, news: NewsItem) -> bool:
        """记录已处理新闻 id，返回是否为新新闻（用于去重计数）

        中文计数只累加中文新闻：英文版虽仍进 _seen_ids（避免每轮重复处理），
        但不计入当日条数。
        """
        nid = str(getattr(news, "id", "") or "")
        if not nid:
            return True
        if nid in self._seen_ids:
            return False
        self._seen_ids.add(nid)
        if _is_chinese_news(getattr(news, "title", "") or ""):
            self._cn_count += 1
        return True

    def note_non_chinese(self, news: NewsItem) -> None:
        """记录被丢弃的英文新闻（按 id 去重，跨轮不重复计数）

        金十同一批英文快讯每分钟都会重新返回，不去重会让这个计数虚高。
        """
        nid = str(getattr(news, "id", "") or "")
        if nid:
            if nid in self._seen_ids:
                return
            self._seen_ids.add(nid)
        self._dropped_non_cn += 1

    def is_new(self, news: NewsItem) -> bool:
        """判断是否为本轮新新闻（只读，不改变状态）

        金十 flash_newest 是滚动窗口，同一批新闻会被反复抓到；
        抓取循环用它把重复项挡在认知引擎之外。
        """
        nid = str(getattr(news, "id", "") or "")
        if not nid:
            return True
        self._reset_if_new_day(datetime.now().strftime('%Y-%m-%d'))
        return nid not in self._seen_ids

    def _save_to_persistence(self, force: bool = False):
        """保存新闻摘要到持久化存储（只保存状态，不保存实体）

        Args:
            force: 忽略节流窗口立即落库（跨天、停止时使用）
        """
        # ❗必须用 `is None` 判断：DBStream 定义了 __len__，
        # 空表时 bool(...) 为 False，`if not self._nb` 会让「表空」被当成
        # 「对象不可用」直接 return —— 于是永远写不进第一条，表永远是空的。
        if self._nb is None:
            return

        now = datetime.now()
        if not force and self._last_persist_ts and (now.timestamp() - self._last_persist_ts) < self._persist_interval:
            return

        try:
            today = now.strftime('%Y-%m-%d')
            self._reset_if_new_day(today)

            saved_summary = self._nb.get("daily_summary", {})
            if not isinstance(saved_summary, dict):
                saved_summary = {}
            existing_today = saved_summary.get(today) or {}

            # 标题从 short_memory 取，但必须累加到已持久化的列表上：
            # short_memory 只有 100 条且重启清空，只用它会丢掉当天早先的标题。
            # 入库前先剥掉「金十数据X月X日讯」这类署名，日报直接拿这条标题展示。
            # 英文版一律不进桶：金十中英文双发会让标题中英混排、count 翻倍。
            news_list = list(self._short_memory)
            today_items = [
                item for item in news_list
                if item.timestamp and item.timestamp.strftime('%Y-%m-%d') == today
            ]
            cn_items = [item for item in today_items if _is_chinese_news(item.title)]
            today_news = [
                {"title": _clean_title_for_classify(item.title),
                 "content": item.content or "",
                 "source": item.source}
                for item in cn_items
            ]

            # 分类走统一关键词注册表（NEWS_TOPIC_KEYWORDS, ~80 个主题）。
            # 原来手写的 9 个 macro / 6 个 industry 关键词实测 49 条新闻只命中 1 条，
            # 舆情长期显示「暂无重要舆情」其实是分类器几乎不命中，不是真的没新闻。
            macro_titles: List[str] = []
            industry_titles: List[str] = []
            for n in today_news:
                title_l = n["title"].lower()
                info = classify_news(n["title"])
                if info["macro"]:
                    macro_titles.append(n["title"])
                elif info["topics"] or any(k in title_l for k in EXTRA_INDUSTRY_KEYWORDS):
                    industry_titles.append(n["title"])

            def _merge(old, new):
                merged = []
                for t in list(old or []) + list(new):
                    if t and t not in merged:
                        merged.append(t)
                return merged[-self.MAX_TITLES_PER_DAY:]

            merged_macro = _merge(existing_today.get("macro_titles"), macro_titles)
            merged_industry = _merge(existing_today.get("industry_titles"), industry_titles)

            summary = {
                # count = 当日去重后的**中文**新闻条数：重启后从持久化恢复，不会归零。
                # 不能用 len(_seen_ids) —— 那里面中英文两版都算，会比真实条数高。
                "count": self._cn_count,
                "dropped_non_cn": self._dropped_non_cn,
                "macro_count": len(merged_macro),
                "macro_titles": merged_macro,
                "industry_count": len(merged_industry),
                "industry_titles": merged_industry,
                "last_updated": now.isoformat(),
            }

            saved_summary[today] = summary

            recent_days = sorted(saved_summary.keys())[-7:]
            trimmed_summary = {k: saved_summary[k] for k in recent_days if isinstance(saved_summary.get(k), dict)}

            self._nb["daily_summary"] = trimmed_summary
            self._nb["seen_ids"] = {
                "date": self._seen_date,
                "ids": sorted(self._seen_ids),
                "cn_count": self._cn_count,
                "dropped_non_cn": self._dropped_non_cn,
            }
            self._last_persist_ts = now.timestamp()
        except Exception as e:
            # 落库失败必须能看见，否则日报会把「写入坏了」显示成「今天没新闻」
            log.warning(f"[Radar-News] 保存新闻摘要失败: {e}")

    def process(self, news: NewsItem) -> List[Dict]:
        """
        处理单条新闻（极简流程）

        1. 存入短期记忆（供雷达面板显示）
        2. 发送到认知系统进行深度处理
        3. 持久化到 NB 存储（按 persist_interval 节流）
        """
        self._short_memory.append(news)
        self._send_to_cognition_simple(news)
        self._record_seen(news)
        self._save_to_persistence(force=False)
        return []

    def flush(self):
        """立即落库（停止前调用，避免节流窗口内的最后一批新闻丢失）"""
        self._save_to_persistence(force=True)

    def _send_to_cognition_simple(self, news: NewsItem) -> None:
        """发送原始新闻到认知系统进行深度处理"""
        try:
            from deva.naja.application import get_app_container
            container = get_app_container()
            cognition = container.cognition_engine if container else None
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
            from deva.naja.cognition.analysis.cross_signal_analyzer import get_cross_signal_analyzer
            analyzer = get_cross_signal_analyzer()

            for signal in signals:
                emit_to_insight_pool(signal)
                analyzer.ingest_news_from_signal(signal)
        except ImportError:
            pass
        except Exception as e:
            _radar_news_log(f"发送洞察池失败: {e}")

    def get_report(self) -> Dict:
        """获取处理报告

        只列中文新闻：金十中英文双发，直接取末 5 条会有一半是英文。
        """
        recent_news = []
        for item in reversed(list(self._short_memory)):
            if not _is_chinese_news(getattr(item, "title", "") or ""):
                continue
            recent_news.append({
                "id": item.id,
                "title": item.title,
                "source": item.source,
                "timestamp": item.timestamp.isoformat(),
            })
            if len(recent_news) >= 5:
                break

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

        # 停止前强制落库，避免节流窗口内最后一批新闻丢失
        try:
            self.processor.flush()
        except Exception as e:
            log.warning(f"[Radar-News] 停止前落库失败: {e}")

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
            # 金十 flash_newest 返回的是滚动窗口，同一批新闻每分钟会被重复抓到。
            # 已在上一轮处理过的直接跳过，否则认知引擎 / 事件总线 / 摘要计数
            # 都会被同一批新闻反复灌一遍。
            if not self.processor.is_new(news):
                continue

            # 英文版直接丢弃：金十同一快讯常中英文双发（id 不同，去重拦不住），
            # 英文进事件总线/认知/摘要只会让标题中英混排、条数翻倍。
            if not _is_chinese_news(news.title):
                self.processor.note_non_chinese(news)
                _radar_news_log(f"跳过英文新闻: {(news.title or '')[:50]}")
                continue

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
                timestamp=news.timestamp.timestamp() if isinstance(news.timestamp, datetime) else (news.timestamp or time.time()),
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

    @probe(KIND_DATASOURCE, "ds:news_api", "新闻源抓取（金十数据）", cadence="定时轮询")
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
