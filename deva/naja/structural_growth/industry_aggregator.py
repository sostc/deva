"""行业基本面聚合器

职责：
- 维护 industry_id -> stock_codes 映射
- 从 FundamentalDataFetcher 获取股价/PE/PB/市值（用于加权和估值）
- 从 FinancialDataFetcher 获取财报（营收同比、净利同比、毛利率、经营现金流）
- 按市值加权聚合到行业维度
- 通过 IndustryDataAdapter 喂入观察池

维度映射（单一真源）：
    营收同比(%)    → demand   因子
    毛利率(%)      → profit   因子
    经营现金流/营收 → cashflow 因子
    净利同比(%)    → profit   维度的证据（辅助）

聚合规则：
- 加权因子：优先市值，其次营收
- 数据缺失的个股跳过，不参与加权
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .observation_pool import ObservationPool
from .data_adapter import IndustryDataAdapter

log = logging.getLogger(__name__)


# 默认行业 -> 成分股映射（美股为主，兼顾 A 股龙头）
DEFAULT_INDUSTRY_STOCKS: Dict[str, List[str]] = {
    # ---- AI 芯片 ----
    "ai_chips": [
        "NVDA",   # 英伟达 - GPU/AI 加速器
        "AMD",    # 超威 - AI 加速器 + 通用 CPU
        "AVGO",   # 博通 - 定制 AI 芯片 + 网络芯片
        "MRVL",   # Marvell - 定制 AI 芯片
    ],
    # ---- 晶圆代工 ----
    "ai_foundry": [
        "TSM",    # 台积电 - 全球最大代工
        "INTC",   # 英特尔 - IDM + 代工
    ],
    # ---- 半导体设备 ----
    "semiconductor_equipment": [
        "ASML",   # ASML - 光刻机
        "AMAT",   # 应用材料
        "LRCX",   # 拉姆研究
        "KLAC",   # KLA Corp
        "TER",    # 泰瑞达 - 测试设备
    ],
    # ---- 高带宽存储（HBM）----
    "hbm": [
        "MU",     # 美光科技 - HBM3E
        "WDC",    # 西部数据 - 存储
    ],
    # ---- 云计算/数据中心 ----
    "cloud_infra": [
        "MSFT",   # 微软 - Azure
        "GOOGL",  # 谷歌 - GCP
        "AMZN",   # 亚马逊 - AWS
        "EQIX",   # Equinix - 数据中心 REIT
    ],
    # ---- AI 软件/应用 ----
    "ai_software": [
        "PLTR",   # Palantir - AI 数据平台
        "SNOW",   # Snowflake - 数据云
        "CRM",    # Salesforce - AI CRM
        "MDB",    # MongoDB - AI 数据底座
    ],
    # ---- AI 电力/散热 ----
    "ai_power": [
        "GE",     # GE Vernova - 燃气轮机/电网
        "VST",    # Vistra - 电力
        "CEG",    # Constellation - 核电
        "SMCI",   # 超微电脑 - AI 服务器
    ],
    # ---- 储能 ----
    "energy_storage": [
        "TSLA",   # 特斯拉 - 储能 + 电动车
        "ENPH",   # Enphase - 微型逆变器
    ],
    # ---- 网络安全 ----
    "cybersecurity": [
        "PAN",    # Palo Alto - 网络安全龙头
        "CRWD",   # CrowdStrike - 端点安全
        "FTNT",   # Fortinet - 防火墙
        "ZS",     # Zscaler - 云安全
    ],
    # ---- 机器人/自动化 ----
    "robotics": [
        "TSLA",   # 特斯拉 - Optimus
        "ISRG",   # 直观医疗 - 手术机器人
        "TER",    # 泰瑞达 - 自动化测试
    ],
    # ---- AI 网络 ----
    "ai_networking": [
        "ANET",   # Arista - 数据中心网络
        "AVGO",   # 博通 - 网络芯片
    ],
}


@dataclass
class IndustryAggregate:
    """行业聚合后的基本面"""
    industry_id: str
    stock_count: int = 0
    revenue_yoy: Optional[float] = None       # 加权营收同比(%)
    net_profit_yoy: Optional[float] = None    # 加权净利同比(%)
    gross_margin: Optional[float] = None      # 加权毛利率(%)
    cashflow_margin: Optional[float] = None   # 加权现金流/营收(%)
    pe_ratio: Optional[float] = None          # 市值加权 PE
    pb_ratio: Optional[float] = None          # 市值加权 PB
    market_cap: float = 0.0                   # 行业总市值


class IndustryAggregator:
    """行业基本面聚合器"""

    def __init__(self, pool: ObservationPool, adapter: Optional[IndustryDataAdapter] = None,
                 industry_stocks: Optional[Dict[str, List[str]]] = None):
        self._pool = pool
        self._adapter = adapter or IndustryDataAdapter(pool=pool)
        self._industry_stocks: Dict[str, List[str]] = dict(industry_stocks or DEFAULT_INDUSTRY_STOCKS)

    def set_stocks(self, industry_id: str, stock_codes: List[str]) -> None:
        """设置某行业的成分股"""
        self._industry_stocks[industry_id] = stock_codes

    def get_stocks(self, industry_id: str) -> List[str]:
        return self._industry_stocks.get(industry_id, [])

    # ---- 聚合 ----
    def aggregate(self, industry_id: str) -> IndustryAggregate:
        """聚合单个行业最新一期基本面数据"""
        quarters = self._aggregate_quarters(industry_id)
        if not quarters:
            return IndustryAggregate(industry_id=industry_id)
        return quarters[-1]  # 最新一期

    def _aggregate_quarters(self, industry_id: str) -> List[IndustryAggregate]:
        """聚合所有季度的数据，返回按时间排序的列表（旧→新）"""
        from deva.naja.bandit.fundamental_data_fetcher import get_fundamental_data_fetcher
        from .financial_data_fetcher import get_financial_data_fetcher

        codes = self._industry_stocks.get(industry_id, [])
        if not codes:
            return []

        fund_fetcher = get_fundamental_data_fetcher()
        fin_fetcher = get_financial_data_fetcher()

        # 收集所有股票的全部季度财报
        # stock_financials[code] = List[StockFinancial] (最新在前，需反转)
        stock_financials: Dict[str, List] = {}
        for code in codes:
            try:
                fins = fin_fetcher.fetch(code)
                if fins:
                    stock_financials[code] = fins  # 最新在前
            except Exception:
                pass

        if not stock_financials:
            return []

        # 对齐季度：以最长的为准
        max_quarters = max(len(fins) for fins in stock_financials.values())

        # 获取市值权重（只取一次，所有季度共用）
        weights: Dict[str, float] = {}
        total_cap = 0.0
        pe_values: List[Tuple[float, float]] = []
        pb_values: List[Tuple[float, float]] = []
        for code in stock_financials:
            try:
                fd = fund_fetcher.get_fundamental(code)
                if fd is not None:
                    cap = float(getattr(fd, "market_cap", 0.0) or 0.0)
                    if cap > 0:
                        weights[code] = cap
                        total_cap += cap
                        pe = float(getattr(fd, "pe_ratio", 0.0) or 0.0)
                        pb = float(getattr(fd, "pb_ratio", 0.0) or 0.0)
                        if pe > 0:
                            pe_values.append((cap, pe))
                        if pb > 0:
                            pb_values.append((cap, pb))
            except Exception:
                pass
            # 退化为营收权重
            if code not in weights and stock_financials[code]:
                rev = stock_financials[code][0].revenue
                if rev > 0:
                    weights[code] = rev

        def weighted(values: List[Tuple[float, float]]) -> Optional[float]:
            if not values:
                return None
            total_w = sum(w for w, _ in values)
            if total_w <= 0:
                return None
            return sum(w * v for w, v in values) / total_w

        pe_ratio = weighted(pe_values)
        pb_ratio = weighted(pb_values)

        # 按季度聚合（从最旧到最新）
        results: List[IndustryAggregate] = []
        for qi in range(max_quarters - 1, -1, -1):
            # qi 是从最新往回数的索引（0=最新, max-1=最旧）
            # 我们反转遍历：从最旧到最新
            rev_yoy_list: List[Tuple[float, float]] = []
            np_yoy_list: List[Tuple[float, float]] = []
            margin_list: List[Tuple[float, float]] = []
            cf_margin_list: List[Tuple[float, float]] = []
            valid_count = 0

            for code, fins in stock_financials.items():
                if qi >= len(fins):
                    continue
                fin = fins[qi]  # qi=0 是最新
                weight = weights.get(code, 0.0)
                if weight <= 0:
                    continue
                valid_count += 1
                if fin.revenue_yoy != 0:
                    rev_yoy_list.append((weight, fin.revenue_yoy))
                if fin.net_profit_yoy != 0:
                    np_yoy_list.append((weight, fin.net_profit_yoy))
                if fin.gross_margin > 0:
                    margin_list.append((weight, fin.gross_margin))
                if fin.revenue > 0 and fin.cashflow != 0:
                    cf_margin_list.append((weight, fin.cashflow / fin.revenue * 100))

            results.append(IndustryAggregate(
                industry_id=industry_id,
                stock_count=valid_count,
                revenue_yoy=weighted(rev_yoy_list),
                net_profit_yoy=weighted(np_yoy_list),
                gross_margin=weighted(margin_list),
                cashflow_margin=weighted(cf_margin_list),
                pe_ratio=pe_ratio,
                pb_ratio=pb_ratio,
                market_cap=total_cap,
            ))

        return results

    def feed_to_pool(self, industry_id: str) -> Optional[IndustryAggregate]:
        """聚合全部季度数据并按时间顺序喂入观察池，返回最新一期结果"""
        quarters = self._aggregate_quarters(industry_id)
        if not quarters:
            return None

        # 按时间顺序（旧→新）喂入每个季度的数据
        # 用偏移时间戳模拟季度间隔，使二阶导计算有意义
        import time as _time
        now = _time.time()
        quarter_seconds = 90 * 24 * 3600  # 90 天

        for i, agg in enumerate(quarters):
            # 时间戳从 (now - (len-1)*quarter_seconds) 到 now
            ts = now - (len(quarters) - 1 - i) * quarter_seconds

            # demand ← 营收同比
            if agg.revenue_yoy is not None:
                self._adapter.feed_to_pool(industry_id, {
                    "type": "earnings",
                    "content": f"行业营收同比 {agg.revenue_yoy:.1f}%",
                    "dimension": "demand",
                    "value": agg.revenue_yoy,
                    "status": "supporting" if agg.revenue_yoy > 0 else "refuting",
                    "confidence": 0.8,
                    "timestamp": ts,
                })

            # profit ← 毛利率
            if agg.gross_margin is not None:
                self._adapter.feed_to_pool(industry_id, {
                    "type": "earnings",
                    "content": f"行业毛利率 {agg.gross_margin:.1f}%",
                    "dimension": "profit",
                    "value": agg.gross_margin,
                    "status": "supporting" if agg.gross_margin > 20 else "neutral",
                    "confidence": 0.8,
                    "timestamp": ts,
                })

            # cashflow ← 现金流/营收
            if agg.cashflow_margin is not None:
                self._adapter.feed_to_pool(industry_id, {
                    "type": "earnings",
                    "content": f"行业现金流占营收 {agg.cashflow_margin:.1f}%",
                    "dimension": "cashflow",
                    "value": agg.cashflow_margin,
                    "status": "supporting" if agg.cashflow_margin > 10 else "neutral",
                    "confidence": 0.7,
                    "timestamp": ts,
                })

        return quarters[-1]  # 返回最新一期
