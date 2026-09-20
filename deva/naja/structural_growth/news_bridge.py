"""新闻桥接器 - 将文本事件匹配到观察池中的行业

职责：
- 维护行业关键词映射
- 将 TextFetchedEvent / TextFocusedEvent 匹配到对应行业
- 通过 IndustryDataAdapter 喂入观察池作为证据

匹配规则（单一真源）：
- 行业关键词来自 IndustryConfig.keywords
- 新闻文本命中关键词即匹配该行业
- 证据态度由 sentiment 决定：>0.6 支持，<0.4 反证，其余中性
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .observation_pool import ObservationPool
from .data_adapter import IndustryDataAdapter


@dataclass
class IndustryConfig:
    """行业配置：用于新闻匹配"""
    industry_id: str
    name: str
    keywords: List[str] = field(default_factory=list)
    companies: List[str] = field(default_factory=list)


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

    # ---- 事件处理 ----
    def on_text_event(self, text: str, title: str = "", source: str = "",
                      sentiment: float = 0.5, topics: List[str] = None,
                      timestamp: Optional[float] = None) -> List[str]:
        """处理一条文本事件，返回匹配到的行业 ID 列表"""
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

        for industry_id in matched_ids:
            self._adapter.feed_to_pool(industry_id, {
                "type": "news",
                "content": title or text[:100],
                "source": source,
                "dimension": "",  # 新闻不直接更新因子，只作证据
                "status": status,
                "confidence": 0.5,
                "timestamp": ts,
            })
        return matched_ids
