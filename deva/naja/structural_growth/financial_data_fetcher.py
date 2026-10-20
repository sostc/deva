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

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from deva.naja.infra.observability.fleet_registry import KIND_DATASOURCE, probe

log = logging.getLogger(__name__)

_EASTMONEY_URL = "https://datacenter.eastmoney.com/securities/api/data/get"
_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://emweb.securities.eastmoney.com/",
}
_SEC_HEADERS = {"User-Agent": "Naja Research Agent naja@example.com"}

# SEC EDGAR CIK 映射缓存
_cik_cache: Dict[str, int] = {}

# ------------------------------------------------------------------ 磁盘缓存
# ❗财报是**年度数据**，但原来只缓存在内存里：服务一重启缓存就空，页面第一次打
#   开要重新把整个池子的 companyfacts 拉一遍（实测 36 只 ~22 分钟，**页面直接
#   打不开**）。所以落盘。项目里同样的坑已经踩过一次（``_fundamental_cache``
#   零落盘 →「重启后第一次慢」没法靠内存缓存解决）。
_CACHE_DIR = Path.home() / ".naja" / "cache" / "structural_growth" / "financials"
# 有效数据 / 确无财报 / 抓取失败 三档 TTL。❗「抓取失败」也要缓存（负缓存），
# 否则每只失败的票每次进页面都会再同步重试一遍网络 —— 这是项目里踩过的坑：
# 「缓存只覆盖成功路径＝失败路径变成每请求一次的同步网络调用」。
OK_TTL = 86400.0        # 财报按年更新，一天足够
EMPTY_TTL = 21600.0     # 确实没有财报（ETF/基金/未上市）：6 小时确认一次
ERROR_TTL = 900.0       # 抓取失败：15 分钟后重试

# 抓取状态
ST_OK = "ok"
ST_EMPTY = "empty"
ST_ERROR = "error"


def _cache_path(code: str) -> Path:
    safe = "".join(ch for ch in (code or "").upper() if ch.isalnum() or ch in "._-")
    return _CACHE_DIR / f"{safe or 'unknown'}.json"


def _normalize_namespaces(raw_facts: Dict) -> Dict[str, dict]:
    """把多命名空间的 XBRL facts 合并成单一 tag 视图（``{"tag": {...}}``）。

    ❗**外国发行人壁**（2026-10-20 实测 TSM / ASML）：它们以 **20-F** 报送，
    XBRL 命名空间是 ``ifrs-full``，**根本不在 ``us-gaap`` 里**。原来只读
    ``facts["us-gaap"]`` → 这些票一期都取不到 → 下游显示「分类未定（财报不足
    或缺失）」，**分不清是「真没有」还是「我读不到」** —— 典型的静默失效。

    优先级：``us-gaap`` > ``ifrs-full`` > 其它命名空间，同名 tag 取高优先级。
    """
    order = ("us-gaap", "ifrs-full")
    rest = [ns for ns in (raw_facts or {}) if ns not in order]
    merged: Dict[str, dict] = {}
    for ns in list(reversed(rest)) + list(reversed(order)):
        for tag, body in ((raw_facts or {}).get(ns) or {}).items():
            merged[tag] = body       # 低优先级先写，高优先级后写覆盖
    return merged


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
    #: 币种（美股 SEC）。❗**绝对值不能跨币种比**，但本结构的用量全是比值
    #: （同比、毛利率、现金流/净利），同币种序列内部自洽，**可以放心用**。
    #: 默认 USD；ASML/SAP 报 EUR、NVO 报 DKK（2026-10-20 实测）。
    currency: str = "USD"

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

    def __init__(self, cache_ttl: float = OK_TTL, cache_dir: Optional[Path] = None):
        self._cache: Dict[str, List[StockFinancial]] = {}
        self._cache_ts: Dict[str, float] = {}
        self._cache_ttl = cache_ttl
        # ❗抓取状态：把「是因为没有财报，还是我们没取到」分开记。
        #   两者都表现为空列表，混在一起就是静默失效。
        self._status: Dict[str, Tuple[str, str]] = {}   # code -> (status, reason)
        self._cache_dir = Path(cache_dir) if cache_dir else _CACHE_DIR

    # ------------------------------------------------------------ 缓存层
    def _ttl_for(self, status: str) -> float:
        if status == ST_EMPTY:
            return EMPTY_TTL
        if status == ST_ERROR:
            return ERROR_TTL
        return self._cache_ttl

    def _memory_get(self, key: str) -> Optional[Tuple[List[StockFinancial], str, str]]:
        ts = self._cache_ts.get(key, 0)
        if key not in self._cache:
            return None
        status, reason = self._status.get(key, (ST_OK, ""))
        if (time.time() - ts) >= self._ttl_for(status):
            return None
        return self._cache.get(key) or [], status, reason

    def _memory_put(self, key: str, data: List[StockFinancial],
                    status: str, reason: str) -> None:
        self._cache[key] = data or []
        self._status[key] = (status, reason)
        self._cache_ts[key] = time.time()

    def _path_for(self, key: str) -> Path:
        if self._cache_dir is _CACHE_DIR:
            return _cache_path(key)
        safe = "".join(ch for ch in key if ch.isalnum() or ch in "._-")
        return self._cache_dir / f"{safe or 'unknown'}.json"

    def _disk_read(self, key: str) -> Optional[Tuple[List[StockFinancial], str, str]]:
        """读磁盘缓存。损坏的文件按未命中处理（不缓存解析异常）。"""
        path = self._path_for(key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        status = payload.get("status") or ST_OK
        if (time.time() - float(payload.get("ts", 0) or 0)) >= self._ttl_for(status):
            return None
        fields = {f for f in StockFinancial.__dataclass_fields__}
        rebuilt: List[StockFinancial] = []
        for item in payload.get("data") or []:
            try:
                rebuilt.append(StockFinancial(**{k: v for k, v in item.items() if k in fields}))
            except TypeError:
                continue      # 字段变了就丢这一期，不把整个票判死
        if (payload.get("data") and not rebuilt and status == ST_OK):
            return None       # 有效数据却全部反序列化失败 → 不认这份缓存
        return rebuilt, status, str(payload.get("reason") or "")

    def _disk_write(self, key: str, data: List[StockFinancial],
                    status: str, reason: str) -> None:
        path = self._path_for(key)
        payload = {
            "ts": time.time(), "code": key, "status": status, "reason": reason,
            "data": [asdict(x) for x in data or []],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)     # 原子替换：读到的一定是完整文件
        except OSError as e:
            log.debug("[FinancialDataFetcher] 磁盘缓存写入失败 %s: %s", key, e)

    def _is_cached(self, stock_code: str) -> bool:
        return self._memory_get(stock_code.upper()) is not None

    # ------------------------------------------------------------ 入口
    def status_of(self, stock_code: str) -> Tuple[str, str]:
        """上一次抓取的状态与原因（``ok`` / ``empty`` / ``error``）。

        ❗UI 必须用它区分「这类标的没有财报」和「我们没取到」——二者都是空列表，
        混在一起用户看到的就是一句含糊的「分类未定」。
        """
        return self._status.get((stock_code or "").upper(), (ST_ERROR, "尚未抓取"))

    def fetch_detail(self, stock_code: str,
                     force_refresh: bool = False) -> Tuple[List[StockFinancial], str, str]:
        """同 ``fetch``，但额外返回 ``(status, reason)``。"""
        key = (stock_code or "").upper()

        if not force_refresh:
            hit = self._memory_get(key)
            if hit is not None:
                return hit
            hit = self._disk_read(key)
            if hit is not None:
                self._memory_put(key, hit[0], hit[1], hit[2])
                return hit

        data, status, reason = self._fetch_source(key)
        self._disk_write(key, data, status, reason)
        self._memory_put(key, data, status, reason)
        return data or [], status, reason

    def fetch(self, stock_code: str, force_refresh: bool = False) -> List[StockFinancial]:
        """获取某只股票最近 4 期财报

        自动判断 A 股 / 美股，路由到对应获取方法。
        缓存顺序：**内存 → 磁盘 → 网络**。需要「为什么取不到」时用 ``fetch_detail``。
        """
        data, _status, _reason = self.fetch_detail(stock_code, force_refresh=force_refresh)
        return data

    def _fetch_source(self, code: str) -> Tuple[List[StockFinancial], str, str]:
        if _is_us_stock(code):
            return self._fetch_us(code)
        return self._fetch_a(code)

    @probe(KIND_DATASOURCE, "ds:eastmoney_fin", "A股财报（东方财富 datacenter）", cadence="按需/缓存")
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
            if resp.status_code != 200:
                return [], ST_ERROR, f"东财 HTTP {resp.status_code}"
            data = resp.json()
        except Exception as e:
            log.warning(f"[FinancialDataFetcher] A股 {stock_code} 财报失败: {e}")
            return [], ST_ERROR, f"{type(e).__name__}: {e}"

        items = ((data or {}).get("result") or {}).get("data") or []
        if not items:
            # ETF / 基金 / 未上市代码会走到这里。不是错误，是「这类标的没有企业财报」，
            # 返回空列表比抛 AttributeError 或编造数字都诚实。
            # ❗但必须和「抓取失败」区分开：两者的表象都是空列表。
            log.info(f"[FinancialDataFetcher] {stock_code} 无财报数据（可能是 ETF/基金）")
            return [], ST_EMPTY, "无财报数据（可能是 ETF/基金/未上市代码）"

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
        return results, ST_OK, ""

    def _fetch_us(self, stock_code: str) -> Tuple[List[StockFinancial], str, str]:
        """美股：只认 SEC EDGAR 的真实 XBRL；拿不到就坦白说为什么拿不到。

        ❗ 2026-10-19 删除了 ``_fetch_us_fallback``：它会用一张硬编码字典
        （MU/WDC/ENPH…）乘以一批「加速趋势」系数，生成 4 期看起来很像真的
        序列。这类数据进入打分后无法与真数据区分，等于给风控喂假账。
        按项目既有铁律：``None ≠ 0``，拿不到就承认拿不到。

        ❗返回三元组而不是裸列表：``empty``（确实没有）和 ``error``（没取到）
        都表现为空列表，不分开的话页面只能说一句含糊的「分类未定」。
        """
        symbol = stock_code.upper()
        try:
            results, status, reason = self._fetch_us_sec(symbol)
            if results:
                return results, ST_OK, ""
            if status:
                log.warning(f"[FinancialDataFetcher] SEC {symbol}: {reason}")
                return [], status, reason
            log.warning(f"[FinancialDataFetcher] SEC 无 {symbol} 财报数据，返回空")
            return [], ST_EMPTY, reason or "SEC 无该标的的年度财报"
        except Exception as e:
            log.warning(f"[FinancialDataFetcher] SEC EDGAR {symbol} 失败: {e}")
            return [], ST_ERROR, f"{type(e).__name__}: {e}"

    @probe(KIND_DATASOURCE, "ds:sec_edgar", "美股财报（SEC EDGAR XBRL）", cadence="按需/缓存")
    def _fetch_us_sec(self, symbol: str) -> Tuple[List[StockFinancial], str, str]:
        """从 SEC EDGAR API 获取真实财报数据"""
        import requests

        cik = _get_cik(symbol)
        if cik is None:
            return [], ST_ERROR, "SEC EDGAR 查不到该代码的 CIK"

        cik_padded = str(cik).zfill(10)
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
        resp = requests.get(url, headers=_SEC_HEADERS, timeout=15)
        if resp.status_code != 200:
            return [], ST_ERROR, f"SEC companyfacts HTTP {resp.status_code}"

        # ❗不能只读 ``us-gaap``：外国发行人（TSM/ASML…）以 20-F 报送，命名空间
        #   是 ``ifrs-full``。只读 us-gaap 会让这类票**静默地一期都取不到**。
        raw_facts = resp.json().get("facts", {}) or {}
        facts = _normalize_namespaces(raw_facts)
        if not facts:
            return [], ST_EMPTY, f"SEC 无可用财报命名空间（{sorted(raw_facts)[:3]}）"

        # 提取年度数据 (fp=FY)
        # ❗ 不能「取第一个非空的标签」：老标签（如 NVDA 的
        # PaymentsToAcquirePropertyPlantAndEquipment）只有 2010-2012 的数据，
        # 一旦被选中，最近四年的 capex 就全变成「缺失」。
        # 规则改为：多个候选标签里，取**覆盖年份最新**的那个。
        #   规则同上——多个候选里取「覆盖年份最新」的那个；IFRS 名称排在后面，
        #   同一家公司的 us-gaap 标签在较少年份被选中时也不会被顶掉。
        revenues: Dict[str, float] = {}
        revenue_tag = ""
        for tag in (
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            # ❗CRWD 报的是 **Including** 版本（2026-10-20 实测）：只认 Excluding
            #   会让它整票「无年度营收标签」→ 页面上只是含糊的「分类未定」。
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
            # ---- IFRS（20-F 报送的外国发行人）----
            "Revenue",
            "RevenueFromContractsWithCustomers",
            "RevenueFromSaleOfGoods",
        ):
            cand = self._extract_annual(facts, tag)
            # ❗排序键必须是 **(期数, 最新年份)**：只看最新年份的话，
            #   一个"[只有 1 期但年份更晚] 的杂标签（实测 SAP：ifrs-full:Revenue
            #   的 USD 单位只有 2017 一年）"会把覆盖 5 年的正主顶掉 → 整票只剩 1 期。
            if cand and ((len(cand), max(cand)) > (len(revenues), max(revenues) if revenues else "")):
                revenues, revenue_tag = cand, tag

        year_ends = self._extract_year_end(facts, revenue_tag) if revenue_tag else {}
        # ❗``NetIncomeLoss`` 在很多公司里是**稀疏标签**（实测 AVGO 只有 2024 和 2018
        #   两年），只认它会让整条净利序列断掉 —— AVGO 因此只剩 2 期有效同比，
        #   直接跌破分类所需的最少期数、变成"未分类"。``ProfitLoss``（含少数股东
        #   权益的净利）覆盖更全，作为按年兜底。
        net_income = self._extract_annual(facts, "NetIncomeLoss")
        net_income_alt: Dict[str, float] = {}
        for tag in ("ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"):
            for y, v in self._extract_annual(facts, tag).items():
                net_income_alt.setdefault(y, v)
        # ❗毛利标签各公司不统一（2026-10-20 实测）：
        #   AMZN 的 GrossProfit 只报过 **2009 年**（陈旧），近年报的是 CostOfGoodsAndServicesSold；
        #   GOOGL 根本没有 GrossProfit，只有 CostOfRevenue；NVDA 才有正常 GrossProfit。
        #   只认 GrossProfit 一个标签 → 7/33 只票毛利率恒为 0，而这个 0 会被下游当**真实
        #   毛利率**收进分类判据（极差 0、升降 0），把「没数据」读成「毛利率纹丝不动」。
        #   所以：GrossProfit 优先，缺则用 Revenue − Cost 反推，Cost 走多候选标签。
        gross_profit = self._extract_annual(facts, "GrossProfit")
        cost_by_year: Dict[str, float] = {}
        for tag in ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold",
                    "CostOfServices",
                    "CostOfGoodsAndServicesSoldExcludingDepreciationDepletionAndAmortization",
                    # ---- IFRS ----
                    "CostOfSales", "CostOfGoodsSoldExcludingDepreciationDepletionAndAmortization"):
            for y, v in self._extract_annual(facts, tag).items():
                cost_by_year.setdefault(y, v)

        cashflow = self._extract_annual(facts, "NetCashProvidedByUsedInOperatingActivities")
        if not cashflow:
            # IFRS 的名称不一样（实测 TSM/ASML）
            for tag in ("CashFlowsFromUsedInOperatingActivities",
                        "NetCashFromOperatingActivities"):
                cashflow = self._extract_annual(facts, tag)
                if cashflow:
                    break
        capex: Dict[str, float] = {}
        for tag in (
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
            "PaymentsToAcquirePPE",
            "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets",
            # ---- IFRS ----
            "PurchaseOfPropertyPlantAndEquipment",
        ):
            cand = self._extract_annual(facts, tag)
            if cand and ((len(cand), max(cand)) > (len(capex), max(capex) if capex else "")):
                capex = cand

        if not revenues:
            return [], ST_EMPTY, "SEC 无可用年度营收标签"

        years = sorted(revenues.keys())
        if len(years) < 2:
            return [], ST_EMPTY, f"SEC 年度营收只有 {len(years)} 期（分类至少需要 4 期）"
        # ❗绝对值金额是**这个币种**下的数（ASML/SAP=EUR、NVO=DKK），跨票不可直接比
        currency = self.currency_of(facts, revenue_tag) or "USD"


        results: List[StockFinancial] = []
        for year in years[-4:]:  # 最多取最近4年
            idx = years.index(year)
            prev_year = years[idx - 1] if idx > 0 else None

            rev = revenues.get(year, 0.0)
            prev_rev = revenues.get(prev_year, 0.0) if prev_year else 0.0
            rev_yoy = ((rev - prev_rev) / abs(prev_rev) * 100) if prev_rev else None

            # ❗原来写 ``net_income.get(year, 0.0)``：该年取不到就填 0，
            #   于是「净利 = 0」这个**假值**会顺着两条路污染下游：
            #   1) 净利同比 = (0 − 前值)/|前值| = **−100%**，伪造出一次「由盈转亏」
            #      （实测 AVGO 2025 就是这样被造出 −100% 的，它当年真实净利数百亿）
            #   2) 现金流/净利 的分母变 0，直接被跳过
            #   而且原来只在「整个 NetIncomeLoss 标签不存在」时才记 missing，
            #   单年缺失完全静默。改成按年判空。
            ni = net_income.get(year)
            if ni is None:
                ni = net_income_alt.get(year)
            prev_ni = net_income.get(prev_year) if prev_year else None
            if prev_ni is None and prev_year:
                prev_ni = net_income_alt.get(prev_year)
            ni_yoy = ((ni - prev_ni) / abs(prev_ni) * 100) if (ni is not None and prev_ni) else None

            missing: List[str] = []
            if rev_yoy is None:
                missing.append("revenue_yoy")
            if ni_yoy is None:
                missing.append("net_profit_yoy")
            if ni is None:
                missing.append("net_profit")
                ni = 0.0

            gp = gross_profit.get(year)
            cost = cost_by_year.get(year) if gp is None else None
            if gp is not None and rev:
                margin = gp / rev * 100
            elif cost is not None and rev:
                margin = (rev - cost) / rev * 100
            else:
                missing.append("gross_margin")
                margin = 0.0

            cx = capex.get(year)
            if cx is None:
                missing.append("capex")
                cx = 0.0

            cf = cashflow.get(year)
            # ❗现金流缺失原本**不记 missing**，直接填 0.0 —— 下游算「现金流/净利」
            # 会得到 0，被读成「利润质量极差」，而真相是「没这个数」。
            if cf is None:
                missing.append("cashflow")
                cf = 0.0

            results.append(StockFinancial(
                stock_code=symbol,
                report_date=year,
                period_end=year_ends.get(year, ""),
                revenue=rev,
                revenue_yoy=rev_yoy or 0.0,
                net_profit=ni,
                net_profit_yoy=ni_yoy or 0.0,
                gross_margin=margin,
                cashflow=cf,
                capex=cx,
                source="sec",
                missing=missing,
                currency=currency,
            ))

        # 反转为最新在前
        results.sort(key=lambda x: x.report_date, reverse=True)
        return results, ST_OK, ""

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

    def _annual_rows(self, facts: Dict, tag: str) -> Tuple[str, list]:
        """取年度（``fp=FY``）行，并挑出币种。

        ❗不能只认 USD：ASML / SAP 报 **EUR**、NVO 报 **DKK**（2026-10-20 实测），
        SAP 甚至在 USD 下只有 2017 一年 —— 只读 USD 会把这些票读成「只有 1 期」。
        挑法：USD 优先；没有 USD 就取 FY 行最多的那个币种。
        整条序列都取自同一币种，跨年同比仍然自洽。
        """
        body = facts.get(tag) or {}
        units = body.get("units", {}) or {}
        usd = [r for r in units.get("USD", []) if r.get("fp") == "FY"]
        if usd:
            return "USD", usd
        best_unit, best_rows = "", []
        for unit, rows in units.items():
            fy = [r for r in rows if r.get("fp") == "FY"]
            if len(fy) > len(best_rows):
                best_unit, best_rows = unit, fy
        return best_unit, best_rows

    def currency_of(self, facts: Dict, tag: str) -> str:
        return self._annual_rows(facts, tag)[0] or "USD"

    def _extract_annual(self, facts: Dict, tag: str) -> Dict[str, float]:
        """从 XBRL facts 中提取年度数据 (fp=FY)，返回 {year: value}"""
        if tag not in facts:
            return {}
        annual = {}
        for r in self._annual_rows(facts, tag)[1]:
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
