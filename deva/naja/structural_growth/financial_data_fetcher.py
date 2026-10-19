"""财报数据获取器

职责：
- A 股：从东方财富 datacenter API 获取财报主要财务指标
- 美股：从 SEC EDGAR API 获取真实 XBRL 财报数据，失败时回退到已知值
- 输出统一的 StockFinancial 数据结构
- 带缓存（避免频繁请求），单例模式

字段映射（单一真源）：
    A 股:
        营收           → TOTALOPERATEREVE
        营收同比(%)    → TOTALOPERATEREVETZ
        归母净利       → PARENTNETPROFIT
        净利同比(%)    → PARENTNETPROFITTZ
        毛利率(%)      → XSMLL
        经营性现金流   → NETCASH_OPERATE_PK
    美股:
        营收           → us-gaap:Revenues (SEC EDGAR)
        净利           → us-gaap:NetIncomeLoss
        毛利率(%)      → GrossProfit / Revenues * 100
        经营性现金流   → us-gaap:NetCashProvidedByUsedInOperatingActivities
        资本开支       → us-gaap:PaymentsToAcquirePropertyPlantAndEquipment
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_EASTMONEY_URL = "https://datacenter.eastmoney.com/securities/api/data/get"
_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://emweb.securities.eastmoney.com/",
}
_SEC_HEADERS = {"User-Agent": "Naja Research Agent naja@example.com"}

# SEC EDGAR CIK 映射缓存
_cik_cache: Dict[str, int] = {}


def _get_cik(symbol: str) -> Optional[int]:
    """从 SEC EDGAR 获取股票代码 → CIK 映射"""
    if symbol in _cik_cache:
        return _cik_cache[symbol]
    try:
        import requests
        resp = requests.get("https://www.sec.gov/files/company_tickers.json",
                            headers=_SEC_HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        for v in resp.json().values():
            if v.get("ticker", "").upper() == symbol.upper():
                _cik_cache[symbol.upper()] = v["cik_str"]
                return v["cik_str"]
    except Exception:
        pass
    return None


@dataclass
class StockFinancial:
    """单只股票的单期财报"""
    stock_code: str
    report_date: str              # 报告期 YYYY-MM-DD（美股为财年标签，如 2026）
    revenue: float = 0.0          # 营业总收入(元)
    revenue_yoy: float = 0.0      # 营收同比(%)
    net_profit: float = 0.0       # 归母净利润(元)
    net_profit_yoy: float = 0.0   # 净利同比(%)
    gross_margin: float = 0.0     # 销售毛利率(%)
    cashflow: float = 0.0         # 经营性现金流(元)
    capex: float = 0.0           # 资本开支(元) — 供给维度代理
    timestamp: float = 0.0
    #: 数据来源：``eastmoney`` / ``sec`` / ``none``。**没有 fallback 这一档** ——
    #: 拿不到就是拿不到，绝不用估算值填空（见 2026-10-19 的硬编码事故）。
    source: str = ""
    #: 财年/报告期的真实截止日 YYYY-MM-DD（美股是财年末，不等于自然年）
    period_end: str = ""
    #: 本期的缺失字段名。``None ≠ 0``：毛利率缺失的银行股不能被当成 "0% 毛利"，
    #: 同比缺失的首年也不能被当成 "零增长"。
    missing: List[str] = field(default_factory=list)
    # ---- 估值所需的时点字段（A 股来自东财同一接口，美股由 SEC 另行取）----
    #: 基本每股收益（A 股为**年初至今累计值**，美股为单季/全年值）
    eps: Optional[float] = None
    #: 每股净资产
    bps: Optional[float] = None
    #: 归母净资产（元）——算 ROE 的分母
    equity: Optional[float] = None
    #: 公告日 YYYY-MM-DD。**时点估值必须用它**，不能用报告期末
    notice_date: str = ""
    #: 报告类型：一季报/中报/三季报/年报（A 股累计口径的判定依据）
    report_type: str = ""

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def is_valid(self) -> bool:
        """至少有一个核心指标非零才算有效"""
        return any([self.revenue > 0, self.net_profit != 0,
                    self.gross_margin > 0, self.cashflow != 0])


def _is_us_stock(stock_code: str) -> bool:
    """判断是否为美股代码（字母开头）"""
    return stock_code[:1].isalpha()


def _secucode(stock_code: str) -> str:
    """A 股代码 → 东方财富 SECUCODE（600xxx.SH / 000xxx.SZ）"""
    code = stock_code.strip()
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    return f"{code}.SZ"


class FinancialDataFetcher:
    """财报数据获取器（A 股 + 美股）"""

    def __init__(self, cache_ttl: float = 86400.0):
        self._cache: Dict[str, List[StockFinancial]] = {}
        self._cache_ts: Dict[str, float] = {}
        self._cache_ttl = cache_ttl

    def _is_cached(self, stock_code: str) -> bool:
        ts = self._cache_ts.get(stock_code, 0)
        return stock_code in self._cache and (time.time() - ts) < self._cache_ttl

    def fetch(self, stock_code: str, force_refresh: bool = False) -> List[StockFinancial]:
        """获取某只股票最近 4 期财报

        自动判断 A 股 / 美股，路由到对应获取方法。
        """
        if not force_refresh and self._is_cached(stock_code):
            return self._cache[stock_code]

        if _is_us_stock(stock_code):
            results = self._fetch_us(stock_code)
        else:
            results = self._fetch_a(stock_code)

        self._cache[stock_code] = results
        self._cache_ts[stock_code] = time.time()
        return results

    def _fetch_a(self, stock_code: str) -> List[StockFinancial]:
        """A 股：从东方财富获取财报"""
        try:
            import requests
            params = {
                "type": "RPT_F10_FINANCE_MAINFINADATA",
                "sty": "ALL",
                "filter": f'(SECUCODE="{_secucode(stock_code)}")',
                "p": 1,
                "ps": 12,
                "sr": "-1",
                "st": "REPORT_DATE",
            }
            resp = requests.get(_EASTMONEY_URL, params=params, headers=_HEADERS, timeout=10)
            data = resp.json()
        except Exception as e:
            log.warning(f"[FinancialDataFetcher] A股 {stock_code} 财报失败: {e}")
            return []

        items = ((data or {}).get("result") or {}).get("data") or []
        if not items:
            # ETF / 基金 / 未上市代码会走到这里。不是错误，是「这类标的没有企业财报」，
            # 返回空列表比抛 AttributeError 或编造数字都诚实。
            log.info(f"[FinancialDataFetcher] {stock_code} 无财报数据（可能是 ETF/基金）")
            return []

        results: List[StockFinancial] = []
        for it in items:
            report_date = (it.get("REPORT_DATE") or "")[:10]

            def _num(key: str) -> Tuple[float, bool]:
                raw = it.get(key)
                if raw in (None, "", "-"):
                    return 0.0, True
                try:
                    return float(raw), False
                except (TypeError, ValueError):
                    return 0.0, True

            revenue, m_rev = _num("TOTALOPERATEREVE")
            rev_yoy, m_rev_yoy = _num("TOTALOPERATEREVETZ")
            net_profit, m_np = _num("PARENTNETPROFIT")
            np_yoy, m_np_yoy = _num("PARENTNETPROFITTZ")
            margin, m_margin = _num("XSMLL")
            cashflow, m_cf = _num("NETCASH_OPERATE_PK")

            def _opt(key: str) -> Optional[float]:
                """估值字段专用：缺失返回 None 而不是 0（0 是「真的没赚钱/没净资产」）。"""
                raw = it.get(key)
                if raw in (None, "", "-"):
                    return None
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    return None

            eps = _opt("EPSJB")
            bps = _opt("BPS")
            equity = _opt("TOTAL_EQUITY_PK")
            notice_date = (it.get("NOTICE_DATE") or "")[:10]
            report_type = (it.get("REPORT_TYPE") or "").strip()

            missing = []
            if m_rev:
                missing.append("revenue")
            if m_rev_yoy:
                missing.append("revenue_yoy")
            if m_np:
                missing.append("net_profit")
            if m_np_yoy:
                missing.append("net_profit_yoy")
            if m_margin:
                # 银行/保险没有毛利率这个概念，缺失是**结构性**的，不是数据坏了
                missing.append("gross_margin")
            if m_cf:
                missing.append("cashflow")
            missing.append("capex")  # 东财该接口不提供资本开支

            results.append(StockFinancial(
                stock_code=stock_code,
                report_date=report_date,
                period_end=report_date,
                revenue=revenue,
                revenue_yoy=rev_yoy,
                net_profit=net_profit,
                net_profit_yoy=np_yoy,
                gross_margin=margin,
                cashflow=cashflow,
                source="eastmoney",
                missing=missing,
                eps=eps,
                bps=bps,
                equity=equity,
                notice_date=notice_date,
                report_type=report_type,
            ))

        results.sort(key=lambda x: x.report_date, reverse=True)
        return results

    def _fetch_us(self, stock_code: str) -> List[StockFinancial]:
        """美股：只认 SEC EDGAR 的真实 XBRL；拿不到就返回空。

        ❗ 2026-10-19 删除了 ``_fetch_us_fallback``：它会用一张硬编码字典
        （MU/WDC/ENPH…）乘以一批「加速趋势」系数，生成 4 期看起来很像真的
        序列。这类数据进入打分后无法与真数据区分，等于给风控喂假账。
        按项目既有铁律：``None ≠ 0``，拿不到就承认拿不到。
        """
        symbol = stock_code.upper()
        try:
            results = self._fetch_us_sec(symbol)
            if results:
                return results
            log.warning(f"[FinancialDataFetcher] SEC 无 {symbol} 财报数据，返回空")
        except Exception as e:
            log.warning(f"[FinancialDataFetcher] SEC EDGAR {symbol} 失败: {e}")
        return []

    def _fetch_us_sec(self, symbol: str) -> List[StockFinancial]:
        """从 SEC EDGAR API 获取真实财报数据"""
        import requests

        cik = _get_cik(symbol)
        if cik is None:
            return []

        cik_padded = str(cik).zfill(10)
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
        resp = requests.get(url, headers=_SEC_HEADERS, timeout=15)
        if resp.status_code != 200:
            return []

        facts = resp.json().get("facts", {}).get("us-gaap", {})
        if not facts:
            return []

        # 提取年度数据 (fp=FY)
        # ❗ 不能「取第一个非空的标签」：老标签（如 NVDA 的
        # PaymentsToAcquirePropertyPlantAndEquipment）只有 2010-2012 的数据，
        # 一旦被选中，最近四年的 capex 就全变成「缺失」。
        # 规则改为：多个候选标签里，取**覆盖年份最新**的那个。
        revenues: Dict[str, float] = {}
        revenue_tag = ""
        for tag in (
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
        ):
            cand = self._extract_annual(facts, tag)
            if cand and (not revenues or max(cand) > max(revenues)):
                revenues, revenue_tag = cand, tag

        year_ends = self._extract_year_end(facts, revenue_tag) if revenue_tag else {}
        net_income = self._extract_annual(facts, "NetIncomeLoss")
        gross_profit = self._extract_annual(facts, "GrossProfit")
        cashflow = self._extract_annual(facts, "NetCashProvidedByUsedInOperatingActivities")
        capex: Dict[str, float] = {}
        for tag in (
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
            "PaymentsToAcquirePPE",
            "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets",
        ):
            cand = self._extract_annual(facts, tag)
            if cand and (not capex or max(cand) > max(capex)):
                capex = cand

        if not revenues:
            return []

        years = sorted(revenues.keys())
        if len(years) < 2:
            return []

        results: List[StockFinancial] = []
        for year in years[-4:]:  # 最多取最近4年
            idx = years.index(year)
            prev_year = years[idx - 1] if idx > 0 else None

            rev = revenues.get(year, 0.0)
            prev_rev = revenues.get(prev_year, 0.0) if prev_year else 0.0
            rev_yoy = ((rev - prev_rev) / abs(prev_rev) * 100) if prev_rev else None

            ni = net_income.get(year, 0.0)
            prev_ni = net_income.get(prev_year, 0.0) if prev_year else 0.0
            ni_yoy = ((ni - prev_ni) / abs(prev_ni) * 100) if prev_ni else None

            missing: List[str] = []
            if rev_yoy is None:
                missing.append("revenue_yoy")
            if ni_yoy is None:
                missing.append("net_profit_yoy")
            if "NetIncomeLoss" not in facts:
                missing.append("net_profit")

            gp = gross_profit.get(year)
            if gp is None:
                missing.append("gross_margin")
                margin = 0.0
            else:
                margin = (gp / rev * 100) if rev else 0.0

            cx = capex.get(year)
            if cx is None:
                missing.append("capex")
                cx = 0.0

            results.append(StockFinancial(
                stock_code=symbol,
                report_date=year,
                period_end=year_ends.get(year, ""),
                revenue=rev,
                revenue_yoy=rev_yoy or 0.0,
                net_profit=ni,
                net_profit_yoy=ni_yoy or 0.0,
                gross_margin=margin,
                cashflow=cashflow.get(year, 0.0),
                capex=cx,
                source="sec",
                missing=missing,
            ))

        # 反转为最新在前
        results.sort(key=lambda x: x.report_date, reverse=True)
        return results

    def _extract_year_end(self, facts: Dict, tag: str) -> Dict[str, str]:
        """年度数据对应的真实期末日期 ``{year: YYYY-MM-DD}``。

        美股财年末不等于自然年（NVDA 的 FY2026 结束在 2026-01），
        只留一个年份会让「这条数据有多旧」无法判断。
        """
        if tag not in facts:
            return {}
        ends: Dict[str, str] = {}
        for r in facts[tag].get("units", {}).get("USD", []):
            if r.get("fp") == "FY":
                end_date = str(r.get("end") or "")
                if end_date:
                    ends[end_date[:4]] = end_date
        return ends

    def _extract_annual(self, facts: Dict, tag: str) -> Dict[str, float]:
        """从 XBRL facts 中提取年度数据 (fp=FY)，返回 {year: value}"""
        if tag not in facts:
            return {}
        units = facts[tag].get("units", {})
        usd = units.get("USD", [])
        annual = {}
        for r in usd:
            if r.get("fp") == "FY":
                end_date = r.get("end", "")
                year = end_date[:4] if end_date else ""
                if year:
                    annual[year] = float(r.get("val", 0))
        return annual

    def latest(self, stock_code: str, force_refresh: bool = False) -> Optional[StockFinancial]:
        """获取最新一期有效财报"""
        for fin in self.fetch(stock_code, force_refresh=force_refresh):
            if fin.is_valid:
                return fin
        return None


_financial_fetcher: Optional[FinancialDataFetcher] = None


def get_financial_data_fetcher() -> FinancialDataFetcher:
    """获取财报数据获取器（单例）"""
    global _financial_fetcher
    if _financial_fetcher is None:
        _financial_fetcher = FinancialDataFetcher()
    return _financial_fetcher
