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
from typing import Any, Dict, List, Optional, Tuple

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
        "ALAB",   # Astera Labs - AI 机架级连接/CXL/PCIe/交换芯片
        "MRVL",   # Marvell - 定制 AI 芯片 + 数据中心互连芯片
        "CRDO",   # Credo - 高速 SerDes/AEC 有源电缆/线性驱动
    ],
}


# 监控股票简介（单一真源）：ticker -> {name, description}
# 用于 UI 展示"监控股票"列表及点击查看公司介绍
STOCK_PROFILES: Dict[str, Dict[str, str]] = {
    # ---- AI 芯片 ----
    "NVDA": {"name": "英伟达 NVIDIA", "description": "全球 AI 算力龙头，GPU/AI 加速器（H100/H200/B200/GB200）主导数据中心训练与推理，CUDA 生态构筑护城河。"},
    "AMD":  {"name": "超威半导体 AMD", "description": "AI 加速器（MI300 系列）+ 通用 CPU（EPYC）双轮驱动，在 AI 训练与推理市场挑战英伟达。"},
    "AVGO": {"name": "博通 Broadcom", "description": "定制 AI 芯片（Google TPU 等）+ 网络芯片（Tomahawk/Jericho），受益于 AI 基础设施资本开支。"},
    "MRVL": {"name": "美满电子 Marvell", "description": "定制 AI 芯片（AWS Trainium 等）+ 数据中心互连芯片（6nm DSP/SerDes/交换），受益于超大规模云厂商 AI 投入与机架级互连升级。"},
    # ---- 晶圆代工 ----
    "TSM":  {"name": "台积电 TSMC", "description": "全球最大晶圆代工厂，3nm/2nm 制程垄断 AI 芯片制造，英伟达/AMD/博通核心代工厂。"},
    "INTC": {"name": "英特尔 Intel", "description": "IDM + 代工（Intel Foundry），18A 制程追赶，受益于美国本土芯片制造回流。"},
    # ---- 半导体设备 ----
    "ASML": {"name": "阿斯麦 ASML", "description": "全球唯一 EUV 光刻机供应商，先进制程制造的瓶颈环节，AI 芯片扩产直接受益。"},
    "AMAT": {"name": "应用材料 Applied Materials", "description": "半导体设备龙头，沉积/刻蚀/检测全流程覆盖，先进制程与 HBM 扩产受益。"},
    "LRCX": {"name": "拉姆研究 Lam Research", "description": "刻蚀设备龙头，3D NAND/HBM 与先进逻辑制程扩产核心供应商。"},
    "KLAC": {"name": "科磊 KLA", "description": "半导体检测/量测设备龙头，先进制程良率控制核心，AI 芯片复杂度提升驱动需求。"},
    "TER":  {"name": "泰瑞达 Teradyne", "description": "半导体测试设备龙头，AI 芯片与 HBM 复杂度提升驱动测试需求，亦布局工业自动化。"},
    # ---- 高带宽存储 ----
    "MU":   {"name": "美光科技 Micron", "description": "HBM3E 主力供应商之一，AI 算力扩张驱动 HBM 需求激增，DRAM 周期复苏。"},
    "WDC":  {"name": "西部数据 Western Digital", "description": "NAND Flash 与 HDD 存储厂商，AI 数据中心存储需求增长受益。"},
    # ---- 云计算/数据中心 ----
    "MSFT": {"name": "微软 Microsoft", "description": "Azure 云 + Copilot AI 应用，AI 资本开支与商业化双轮驱动，OpenAI 主要投资方。"},
    "GOOGL":{"name": "谷歌 Alphabet", "description": "GCP 云 + Gemini + TPU 自研芯片，AI 搜索与云业务双轮驱动。"},
    "AMZN": {"name": "亚马逊 Amazon", "description": "AWS 云 + Trainium/Inferentia 自研 AI 芯片，全球最大云厂商，AI 基础设施投入领跑。"},
    "EQIX": {"name": "Equinix", "description": "全球最大数据中心 REIT，AI 算力部署推动数据中心互联与机柜需求增长。"},
    # ---- AI 软件/应用 ----
    "PLTR": {"name": "Palantir", "description": "AI 数据平台龙头，AIP（AI 平台）驱动政企客户增长，AI 应用落地标杆。"},
    "SNOW": {"name": "Snowflake", "description": "数据云平台，AI 时代数据底座，与英伟达合作推进企业级 AI 应用。"},
    "CRM":  {"name": "Salesforce", "description": "企业级 CRM 龙头，Einstein AI 嵌入全产品线，AI 赋能 SaaS 提价与渗透。"},
    "MDB":  {"name": "MongoDB", "description": "AI 数据底座，向量数据库与开发者平台受益于生成式 AI 应用爆发。"},
    # ---- AI 电力/散热 ----
    "GE":   {"name": "通用电气 GE", "description": "GE Vernova 燃气轮机与电网业务，AI 数据中心电力需求爆发核心受益。"},
    "VST":  {"name": "Vistra", "description": "美国独立发电商，核电 + 天然气发电，AI 数据中心电力需求激增直接受益。"},
    "CEG":  {"name": "Constellation Energy", "description": "美国最大核电运营商，AI 数据中心对稳定清洁能源（核电）需求激增。"},
    "SMCI": {"name": "超微电脑 Super Micro", "description": "AI 服务器整机厂商，液冷散热与机柜级方案受益于 AI 算力部署。"},
    # ---- 储能 ----
    "TSLA": {"name": "特斯拉 Tesla", "description": "Megapack 储能 + 电动车，储能业务受益于 AI 数据中心与电网调峰需求。"},
    "ENPH": {"name": "Enphase", "description": "微型逆变器龙头，户用储能与智能能源管理，光伏 + 储能周期复苏受益。"},
    # ---- 网络安全 ----
    "PAN":  {"name": "Palo Alto Networks", "description": "网络安全龙头，平台化安全运营中心（SOC）+ AI 安全检测，受益于 AI 时代安全威胁升级。"},
    "CRWD": {"name": "CrowdStrike", "description": "端点安全龙头，Falcon 平台 + AI 威胁检测，云原生安全需求高增长。"},
    "FTNT": {"name": "Fortinet", "description": "防火墙与网络安全龙头，Secure Access 架构，AI 驱动的安全运营受益。"},
    "ZS":   {"name": "Zscaler", "description": "云安全（SASE/零信任）龙头，AI 与混合办公驱动云安全需求增长。"},
    # ---- 机器人/自动化 ----
    "ISRG": {"name": "直观医疗 Intuitive Surgical", "description": "手术机器人绝对龙头，达芬奇系统，医疗机器人渗透率提升受益。"},
    # ---- AI 网络 ----
    "ANET": {"name": "Arista Networks", "description": "数据中心交换机龙头，以太网 AI 集群互连方案，受益于 AI 集群网络带宽需求。"},
    "ALAB": {"name": "Astera Labs", "description": "AI 机架级连接芯片龙头，CXL/PCIe/Ethernet/NVLink 智能互连（Scorpio 交换芯片、Leo 智能内存控制器），2025 营收 +115%。"},
    "CRDO": {"name": "Credo Technology", "description": "高速连接芯片厂商，SerDes 收发器、AEC 有源电缆、线性驱动 DSP，服务 AI 数据中心机架级互连与 800G/1.6T 以太网升级。"},
}


def get_stock_profile(ticker: str) -> Optional[Dict[str, str]]:
    """获取股票简介（名称 + 描述）"""
    return STOCK_PROFILES.get(ticker.upper())


@dataclass
class IndustryAggregate:
    """行业聚合后的基本面"""
    industry_id: str
    stock_count: int = 0
    revenue_yoy: Optional[float] = None       # 加权营收同比(%)
    net_profit_yoy: Optional[float] = None    # 加权净利同比(%)
    gross_margin: Optional[float] = None      # 加权毛利率(%)
    cashflow_margin: Optional[float] = None   # 加权现金流/营收(%)
    capex_growth: Optional[float] = None      # 加权资本开支同比(%) — 供给维度
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

    def _sync_companies(self, industry_id: str) -> None:
        """将监控股票列表同步到 IndustryState.companies"""
        tracked = self._pool.get(industry_id)
        if tracked is None:
            return
        stocks = self.get_stocks(industry_id)
        if stocks and tracked.state.companies != stocks:
            tracked.state.companies = list(stocks)

    # ---- 全部股票快照（用于集中展示与排序）----
    def get_all_stocks_snapshot(self) -> List[Dict[str, Any]]:
        """获取所有监控股票的最新一期财务+行情+简介快照。

        返回列表元素结构：
        {
            "industry_id": str,
            "ticker": str,
            "name": str,
            "description": str,
            "revenue": float, "revenue_yoy": float,
            "net_profit_yoy": float, "gross_margin": float,
            "market_cap": float, "pe_ratio": float, "pb_ratio": float,
            "change_pct": float,
        }
        """
        from deva.naja.bandit.fundamental_data_fetcher import get_fundamental_data_fetcher
        from .financial_data_fetcher import get_financial_data_fetcher

        fin_fetcher = get_financial_data_fetcher()
        fund_fetcher = get_fundamental_data_fetcher()

        results: List[Dict[str, Any]] = []
        seen: set = set()
        for industry_id, codes in self._industry_stocks.items():
            for code in codes:
                key = (industry_id, code)
                if key in seen:
                    continue
                seen.add(key)

                profile = get_stock_profile(code) or {}
                snapshot: Dict[str, Any] = {
                    "industry_id": industry_id,
                    "ticker": code,
                    "name": profile.get("name", code),
                    "description": profile.get("description", ""),
                    "revenue": 0.0,
                    "revenue_yoy": 0.0,
                    "net_profit_yoy": 0.0,
                    "gross_margin": 0.0,
                    "market_cap": 0.0,
                    "pe_ratio": 0.0,
                    "pb_ratio": 0.0,
                    "change_pct": 0.0,
                }

                # 最新一期财报
                try:
                    fins = fin_fetcher.fetch(code)
                    if fins:
                        latest = fins[0]
                        snapshot["revenue"] = float(latest.revenue or 0.0)
                        snapshot["revenue_yoy"] = float(latest.revenue_yoy or 0.0)
                        snapshot["net_profit_yoy"] = float(latest.net_profit_yoy or 0.0)
                        snapshot["gross_margin"] = float(latest.gross_margin or 0.0)
                except Exception:
                    pass

                # 行情数据
                try:
                    fd = fund_fetcher.get_fundamental(code)
                    if fd is not None:
                        snapshot["market_cap"] = float(getattr(fd, "market_cap", 0.0) or 0.0)
                        snapshot["pe_ratio"] = float(getattr(fd, "pe_ratio", 0.0) or 0.0)
                        snapshot["pb_ratio"] = float(getattr(fd, "pb_ratio", 0.0) or 0.0)
                        snapshot["change_pct"] = float(getattr(fd, "change_pct", 0.0) or 0.0)
                except Exception:
                    pass

                results.append(snapshot)

        return results

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
            capex_growth_list: List[Tuple[float, float]] = []
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
                # 供给维度：capex 同比增长率（用营收近似）
                if qi < len(fins) - 1 and fins[qi].capex > 0 and fins[qi + 1].capex > 0:
                    prev_capex = fins[qi + 1].capex  # 前一年
                    if prev_capex > 0:
                        capex_g = (fin.capex - prev_capex) / prev_capex * 100
                        capex_growth_list.append((weight, capex_g))

            results.append(IndustryAggregate(
                industry_id=industry_id,
                stock_count=valid_count,
                revenue_yoy=weighted(rev_yoy_list),
                net_profit_yoy=weighted(np_yoy_list),
                gross_margin=weighted(margin_list),
                cashflow_margin=weighted(cf_margin_list),
                capex_growth=weighted(capex_growth_list),
                pe_ratio=pe_ratio,
                pb_ratio=pb_ratio,
                market_cap=total_cap,
            ))

        return results

    def feed_to_pool(self, industry_id: str) -> Optional[IndustryAggregate]:
        """聚合全部季度数据并按时间顺序喂入观察池，返回最新一期结果"""
        quarters = self._aggregate_quarters(industry_id)
        if not quarters:
            # 即使无财报数据，也同步监控股票列表到状态卡
            self._sync_companies(industry_id)
            return None

        # 同步监控股票列表到 IndustryState.companies
        self._sync_companies(industry_id)

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

            # supply ← 资本开支同比（供给维度代理）
            # capex 增速低 = 供给扩张慢 = 可能形成瓶颈
            if agg.capex_growth is not None:
                self._adapter.feed_to_pool(industry_id, {
                    "type": "earnings",
                    "content": f"行业资本开支同比 {agg.capex_growth:.1f}%",
                    "dimension": "supply",
                    "value": agg.capex_growth,
                    "status": "supporting" if agg.capex_growth < 5 else "neutral",  # capex 低增长 → 供给受限 → 支持瓶颈假设
                    "confidence": 0.6,
                    "timestamp": ts,
                })

        return quarters[-1]  # 返回最新一期
