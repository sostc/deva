"""新闻桥接器 - 将文本事件匹配到观察池中的行业

职责：
- 维护行业关键词映射
- 将 TextFetchedEvent / TextFocusedEvent 匹配到对应行业
- 从新闻文本中提取库存/价格定量信号，喂入对应维度
- 通过 IndustryDataAdapter 喂入观察池作为证据 + 因子数据

匹配规则（单一真源）：
- 行业关键词来自 IndustryConfig.keywords
- 新闻文本命中关键词即匹配该行业
- 证据态度由 sentiment 决定：>0.6 支持，<0.4 反证，其余中性
- 库存/价格数值由正则 + 方向词提取，补充 inventory/price 维度
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .observation_pool import ObservationPool
from .data_adapter import IndustryDataAdapter


@dataclass
class IndustryConfig:
    """行业配置：用于新闻匹配"""
    industry_id: str
    name: str
    keywords: List[str] = field(default_factory=list)
    companies: List[str] = field(default_factory=list)


# ---- 库存维度提取规则 ----
# 分离匹配：维度词 + 方向词（不要求连续出现）
# (维度词, 方向词列表, 方向, 默认值)
_INVENTORY_DIM_KEYWORDS = ["库存", "inventory", "存货"]
_INVENTORY_PATTERNS: List[Tuple[List[str], str, float]] = [
    # 方向词列表, 方向标识, 默认值
    (["高企", "积压", "堆积", "上升", "增加", "buildup", "excess", "accumulation"], "high", 30.0),
    (["周转天数", "days", "周转"], "days", 0.0),
    (["去库存", "去化", "下降", "减少", "降低", "destocking", "decline", "drop", "decreasing"], "down", -15.0),
    (["补库存", "补货", "备货", "restocking", "replenishment", "restock"], "restock", -10.0),
]

# ---- 价格维度提取规则 ----
# (方向词列表, 方向, 默认值)
_PRICE_DIM_KEYWORDS = ["价格", "现货价", "合约价", "报价", "售价", "price", "pricing"]
_PRICE_PATTERNS: List[Tuple[List[str], str, float]] = [
    (["涨价", "上涨", "上调", "提价", "飙升", "跳涨", "hike", "increase", "surge", "走高"], "up", 10.0),
    (["降价", "下跌", "下调", "drop", "cut", "decrease", "走低"], "down", -10.0),
    (["持平", "稳定", "flat", "stable", "unchanged"], "flat", 0.0),
]

# 百分比提取正则
_RE_PCT = re.compile(r'([\d.]+)\s*(?:%|percent|百分点|個百分點)', re.IGNORECASE)
# 天数提取正则
_RE_DAYS = re.compile(r'(\d+)\s*(?:天|days?)', re.IGNORECASE)


def _extract_pct(text: str, anchor: str = "") -> Optional[float]:
    """从文本中提取百分比数值

    如果提供 anchor（关键词），优先提取关键词附近的百分比（向后搜索 30 字符）
    """
    if anchor:
        idx = text.lower().find(anchor.lower())
        if idx >= 0:
            window = text[idx:idx + len(anchor) + 30]
            m = _RE_PCT.search(window)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    pass
            # 也向前搜索
            start = max(0, idx - 20)
            window_before = text[start:idx + len(anchor)]
            m = _RE_PCT.search(window_before)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    pass
    # 回退：提取第一个百分比
    m = _RE_PCT.search(text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _extract_days(text: str) -> Optional[float]:
    """从文本中提取天数"""
    m = _RE_DAYS.search(text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


class NewsBridge:
    """新闻到行业的桥接器"""

    def __init__(self, pool: ObservationPool, adapter: Optional[IndustryDataAdapter] = None,
                 industry_configs: Optional[List[IndustryConfig]] = None):
        self._pool = pool
        self._adapter = adapter or IndustryDataAdapter(pool=pool)
        self._configs: Dict[str, IndustryConfig] = {}
        if industry_configs:
            for cfg in industry_configs:
                self._configs[cfg.industry_id] = cfg

    # ---- 配置管理 ----
    def register_industry(self, config: IndustryConfig) -> None:
        """注册行业关键词配置"""
        self._configs[config.industry_id] = config

    def get_config(self, industry_id: str) -> Optional[IndustryConfig]:
        return self._configs.get(industry_id)

    # ---- 匹配 ----
    def match_industries(self, text: str, title: str = "") -> List[str]:
        """根据文本匹配相关行业 ID"""
        content = (title + " " + text).lower()
        matched = []
        for industry_id, cfg in self._configs.items():
            for kw in cfg.keywords:
                if kw.lower() in content:
                    matched.append(industry_id)
                    break
        return matched

    # ---- 数值信号提取 ----
    def _extract_inventory_signal(self, text: str) -> Optional[Tuple[float, str]]:
        """从新闻文本提取库存信号

        使用分离匹配：文本必须包含维度词(库存/inventory) + 方向词(下降/高企等)
        Returns: (value, status) 或 None
        """
        text_lower = text.lower()

        # 先检查是否包含库存维度词
        has_dim = any(d.lower() in text_lower for d in _INVENTORY_DIM_KEYWORDS)
        if not has_dim:
            return None

        # 再匹配方向词
        for keywords, direction, default_val in _INVENTORY_PATTERNS:
            for kw in keywords:
                if kw.lower() in text_lower:
                    if direction == "days":
                        days = _extract_days(text)
                        if days is not None:
                            return (-days, "supporting")
                        return (default_val, "supporting")
                    elif direction == "down":
                        pct = _extract_pct(text, anchor=kw)
                        val = -abs(pct) if pct is not None else default_val
                        return (val, "supporting")
                    elif direction == "high":
                        # 库存高企/积压：用默认值，不提取百分比（避免误提取附近的价格数据）
                        return (default_val, "refuting")
                    elif direction == "restock":
                        pct = _extract_pct(text, anchor=kw)
                        val = -abs(pct) * 0.5 if pct is not None else default_val
                        return (val, "supporting")
        return None

    def _extract_price_signal(self, text: str) -> Optional[Tuple[float, str]]:
        """从新闻文本提取产品价格信号

        使用分离匹配：文本必须包含价格维度词 + 方向词
        Returns: (value, status) 或 None
        """
        text_lower = text.lower()

        # 先检查是否包含价格维度词
        has_dim = any(d.lower() in text_lower for d in _PRICE_DIM_KEYWORDS)
        if not has_dim:
            # 如果没有价格维度词，但方向词很明确(涨价/降价)，也接受
            for keywords, direction, _ in _PRICE_PATTERNS:
                for kw in keywords:
                    if kw.lower() in text_lower:
                        has_dim = True
                        break
                if has_dim:
                    break
            if not has_dim:
                return None

        for keywords, direction, default_val in _PRICE_PATTERNS:
            for kw in keywords:
                if kw.lower() in text_lower:
                    pct = _extract_pct(text, anchor=kw)
                    if direction == "up":
                        val = abs(pct) if pct is not None else default_val
                        return (val, "supporting")
                    elif direction == "down":
                        val = -abs(pct) if pct is not None else default_val
                        return (val, "refuting")
                    elif direction == "flat":
                        return (0.0, "neutral")
        return None

    # ---- 事件处理 ----
    def on_text_event(self, text: str, title: str = "", source: str = "",
                      sentiment: float = 0.5, topics: List[str] = None,
                      timestamp: Optional[float] = None) -> List[str]:
        """处理一条文本事件，返回匹配到的行业 ID 列表

        - 匹配行业后，尝试从文本提取库存/价格数值信号
        - 如果提取到数值，同时更新对应因子维度（使二阶导可计算）
        - 无论是否提取到数值，都添加新闻证据
        """
        ts = timestamp or time.time()
        matched_ids = self.match_industries(text, title)
        if not matched_ids:
            return []

        # 由 sentiment 决定证据态度
        if sentiment > 0.6:
            status = "supporting"
        elif sentiment < 0.4:
            status = "refuting"
        else:
            status = "neutral"

        full_text = title + " " + text

        # 提取库存信号
        inv_signal = self._extract_inventory_signal(full_text)
        # 提取价格信号
        price_signal = self._extract_price_signal(full_text)

        for industry_id in matched_ids:
            # 1. 添加新闻证据（无数值）
            self._adapter.feed_to_pool(industry_id, {
                "type": "news",
                "content": title or text[:100],
                "source": source,
                "dimension": "",
                "status": status,
                "confidence": 0.5,
                "timestamp": ts,
            })

            # 2. 如果提取到库存数值，喂入 inventory 维度
            if inv_signal is not None:
                inv_val, inv_status = inv_signal
                self._adapter.feed_to_pool(industry_id, {
                    "type": "news",
                    "content": f"[库存信号] {title or text[:80]}",
                    "source": source,
                    "dimension": "inventory",
                    "value": inv_val,
                    "status": inv_status,
                    "confidence": 0.6,
                    "timestamp": ts,
                })

            # 3. 如果提取到价格数值，喂入 price 维度
            if price_signal is not None:
                price_val, price_status = price_signal
                self._adapter.feed_to_pool(industry_id, {
                    "type": "news",
                    "content": f"[价格信号] {title or text[:80]}",
                    "source": source,
                    "dimension": "price",
                    "value": price_val,
                    "status": price_status,
                    "confidence": 0.6,
                    "timestamp": ts,
                })

        return matched_ids
