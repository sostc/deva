"""重定价编排层：把「分类 → 实测 PE 带 → 三件套」串成一句人话。

分层职责（❗别把取数逻辑塞进这里，这里只做编排和判读）：
- ``pe_classifier``  决定这家公司是周期 / 成长 / 稳态
- ``pe_bands``       决定那三条带子从哪来（实测分布，不是常量）
- ``repricing``      算 priced_in / 不对称比 / 九宫格
- **本文件**        把三者接起来，并负责「算不出来时该说什么」

❗**「算不出来」是这里最主要的工作**。一条结论要能用，必须同时满足：
1. 真实 PE 采集到了（亏损股 / 源失败 → 不可用，绝不用 0 顶上）
2. 分类不是 ``UNKNOWN``（没分类就谈不上「它被按哪把尺子定价」）
3. 尺子本身有效（结构性带中值必须高于周期带中值）
任何一条不满足 → ``usable=False`` + ``reason`` 写清是哪条。
**空着比编一个数安全**：编出来的数不报错，而且看起来很像结论。
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Sequence

from .pe_bands import PeerPe, build_bands
from .pe_classifier import ClassificationResult, build_input_from_financials, classify
from .repricing import evaluate_repricing

log = logging.getLogger(__name__)

# 分类结果缓存（财报是年度数据，半小时足够）
CLASSIFY_TTL = 1800.0
# ❗PE 样本缓存：evaluate_all 会对每只票重算一遍尺子，若每只票都重新拉 36 次
#   行情，36 只就是 1296 次网络调用（实测 83.8s）。行情 5 分钟内足够新鲜。
PE_TTL = 300.0
# ❗预热并发度：SEC 要求 ≤10 req/s，8 条并发留余量。串行跑满池 36 只实测要
#   几分钟（单只 companyfacts ~3.5s），页面第一次打开根本等不起。
WARM_WORKERS = 8


class RepricingService:
    """重定价编排。

    ``industry_stocks`` 缺省用 ``industry_aggregator.DEFAULT_INDUSTRY_STOCKS``，
    即页面监控池 —— 保证「页面看到的池子」和「算尺子用的池子」是同一个。
    """

    def __init__(self, industry_stocks: Optional[Dict[str, List[str]]] = None,
                 phase_provider=None):
        from .industry_aggregator import DEFAULT_INDUSTRY_STOCKS
        self._industry_stocks: Dict[str, List[str]] = dict(
            industry_stocks or DEFAULT_INDUSTRY_STOCKS)
        self._phase_provider = phase_provider   # Optional[Callable[[str], str]]
        self._classify_cache: Dict[str, tuple] = {}   # code -> (ts, result)
        self._pe_cache: Dict[str, tuple] = {}         # code -> (ts, pe, source, note)
        #: ❗财报抓取状态 ``code -> (status, reason)``。没有它，页面只能把
        #: 「我们没取到」和「这家确实没有财报」都写成一句含糊的「分类未定」。
        self._fetch_status: Dict[str, tuple] = {}

    # ------------------------------------------------------------ 取数
    @property
    def all_codes(self) -> List[str]:
        seen, out = set(), []
        for codes in self._industry_stocks.values():
            for c in codes:
                if c not in seen:
                    seen.add(c)
                    out.append(c)
        return out

    def industries_of(self, code: str) -> List[str]:
        c = (code or "").upper()
        return [i for i, codes in self._industry_stocks.items()
                if c in {x.upper() for x in codes}]

    def _classify(self, code: str) -> Optional[ClassificationResult]:
        now = time.time()
        hit = self._classify_cache.get(code)
        if hit and (now - hit[0]) < CLASSIFY_TTL:
            return hit[1]
        try:
            from .financial_data_fetcher import get_financial_data_fetcher
            fins, status, why = get_financial_data_fetcher().fetch_detail(code)
        except Exception as e:  # noqa: BLE001
            log.warning("[RepricingService] %s 财报获取失败: %s", code, e)
            self._fetch_status[code] = ("error", f"{type(e).__name__}: {e}")
            self._classify_cache[code] = (now, None)
            return None
        self._fetch_status[code] = (status, why)
        if not fins:
            self._classify_cache[code] = (now, None)
            return None
        res = classify(build_input_from_financials(code, fins))
        self._classify_cache[code] = (now, res)
        return res

    def _pe(self, code: str):
        """返回 (pe: Optional[float], source: str, note: str)。

        ❗``pe_source`` 为空串表示**没采到** —— 那时 ``pe`` 一律是 ``None``，
        绝不用 ``pe_ratio`` 的数值（缺失时它是 0.0，会被读成「PE 0 = 白送」）。
        """
        now = time.time()
        hit = self._pe_cache.get(code)
        if hit and (now - hit[0]) < PE_TTL:
            return hit[1], hit[2], hit[3]
        try:
            from deva.naja.bandit.fundamental_data_fetcher import get_fundamental_data_fetcher
            fd = get_fundamental_data_fetcher().get_fundamental(code)
        except Exception as e:  # noqa: BLE001
            out = (None, "", f"行情源异常：{type(e).__name__}")
            self._pe_cache[code] = (now,) + out
            return out
        if fd is None:
            out = (None, "", "行情源无此标的")
            self._pe_cache[code] = (now,) + out
            return out
        src = getattr(fd, "pe_source", "") or ""
        if not src:
            note = getattr(fd, "pe_note", "") or "未采集到 PE"
            out = (None, "", note)
            self._pe_cache[code] = (now,) + out
            return out
        out = (float(getattr(fd, "pe_ratio", 0.0) or 0.0), src, "")
        self._pe_cache[code] = (now,) + out
        return out

    def _phase(self, industry_id: str) -> str:
        if self._phase_provider is None:
            return ""
        try:
            return self._phase_provider(industry_id) or ""
        except Exception:  # noqa: BLE001
            return ""

    # ------------------------------------------------------------ 尺子
    def build_peers(self) -> List[PeerPe]:
        """构造池子的实测 PE 样本（全池一把尺子，见 ``pe_bands`` docstring）。

        ❗一只票同时属于多个行业时**按 code 去重** —— 它不该因为被记在两个
        行业里就在分布里占两个位置。
        """
        peers: List[PeerPe] = []
        for code in self.all_codes:
            cls = self._classify(code)
            pe, _src, note = self._pe(code)
            peers.append(PeerPe(code=code, pe=pe,
                                regime=cls.regime.value if cls else "unknown",
                                note=note))
        return peers

    # ------------------------------------------------------------ 评估
    def fetch_status(self, code: str) -> tuple:
        """``(status, reason)`` —— ``ok`` / ``empty`` / ``error``。"""
        return self._fetch_status.get((code or "").upper(), ("unknown", "尚未抓取"))

    def warm(self, codes: Optional[Sequence[str]] = None) -> None:
        """并发预热：把全池的财报 + PE 灌进缓存。

        ❗不预热的话 ``evaluate_all`` 里每只票都要等别人的网络往返，实测全池
        冷启动 20 分钟级；而 UI 是在一次请求里同步等的。
        """
        todo = list(codes or self.all_codes)
        if not todo:
            return

        def _one(c: str) -> None:
            try:
                self._classify(c)
                self._pe(c)
            except Exception as e:  # noqa: BLE001
                log.warning("[RepricingService] 预热 %s 失败: %s", c, e)

        if len(todo) == 1:
            _one(todo[0])
            return
        workers = max(1, min(WARM_WORKERS, len(todo)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="repricing-warm") as ex:
            list(ex.map(_one, todo))

    def evaluate(self, code: str, industry_id: Optional[str] = None) -> Dict:
        """评估单只票的重定价定位。返回的 dict 直接供 UI/API 使用。"""
        c = (code or "").upper()
        inds = self.industries_of(c)
        target_industry = industry_id or (inds[0] if inds else None)

        out: Dict = {
            "code": c,
            "industry_id": target_industry or "",
            "industries": inds,
            "usable": False,
            "reason": "",
        }

        pe, pe_source, pe_note = self._pe(c)
        cls = self._classify(c)

        out["pe_now"] = pe
        out["pe_source"] = pe_source
        out["pe_note"] = pe_note
        if cls is not None:
            out.update({
                "regime": cls.regime.value,
                "regime_name": cls.regime.display_name,
                "confidence": cls.confidence,
                "sample_sufficiency": cls.sample_sufficiency,
                "evidence": list(cls.evidence),
                "counter_evidence": list(cls.counter_evidence),
                "missing_fields": list(cls.missing_fields),
                "excluded": dict(cls.excluded or {}),
                "classify_note": cls.note,
            })
        else:
            status, why = self.fetch_status(c)
            # ❗「报不出来」要分三种说，混成一句「财报不足或缺失」＝把故障和事实混淆
            if status == "error":
                note = f"财报抓取失败（{why or '未知原因'}）"
            elif status == "empty":
                note = f"无财报数据（{why or '该标的无年报'}）"
            else:
                note = "财报未取到，无法分类"
            out.update({
                "regime": "unknown",
                "regime_name": "未分类",
                "confidence": 0.0,
                "sample_sufficiency": 0.0,
                "evidence": [], "counter_evidence": [],
                "missing_fields": ["财报序列"],
                "excluded": {},
                "classify_note": note,
                "fetch_status": status,
                "fetch_reason": why,
            })

        # ---- 尺子：全池共享，且排除自己 ----
        bands = build_bands(self.build_peers(), exclude_code=c)
        out["bands"] = bands.to_dict()
        out["phase"] = self._phase(target_industry) if target_industry else ""

        # ---- 闸门：三条缺一不可 ----
        reasons: List[str] = []
        if pe is None:
            reasons.append(f"PE 未采集（{pe_note or '源无数据'}）")
        if out["regime"] == "unknown":
            status, why = self.fetch_status(c)
            if status == "error":
                reasons.append(f"财报抓取失败（{why or '未知原因'}）")
            elif status == "empty":
                reasons.append(f"无财报数据（{why or '该标的无年报'}）")
            else:
                reasons.append("分类未定（财报不足或缺失）")
        if not bands.is_valid():
            reasons.append(f"估值带不可用（{bands.note or '结构性带未高于周期带'}）")
        if reasons:
            out["reason"] = "；".join(reasons)
            out["priced_in"] = None
            out["priced_in_label"] = "不可用"
            out["asymmetry"] = None
            out["verdict"] = "数据不足，不做判断"
            out["entry_window"] = "不可用"
            return out

        rp = evaluate_repricing(c, pe, bands.cyclical, bands.structural,
                                phase=out["phase"], regime=out["regime"])
        out["usable"] = True
        out["priced_in"] = rp.priced_in
        out["priced_in_label"] = rp.priced_in_label
        out["asymmetry"] = rp.asymmetry
        out["upside_pct"] = rp.upside_pct
        out["downside_pct"] = rp.downside_pct
        out["entry_window"] = rp.entry_window
        out["verdict"] = rp.verdict
        out["note"] = rp.note
        if bands.note:
            out["bands"]["caveat"] = bands.note
        return out

    def evaluate_all(self, codes: Optional[Sequence[str]] = None) -> List[Dict]:
        """批量评估。❗每只票的尺子按它所属行业取，所以逐个算。

        ❗先并发预热全池：否则第一只票要串行等地 36 只票的网络往返（实测分钟级），
        后面的票虽然有缓存，但那第一只已经把页面卡死了。
        """
        targets = list(codes or self.all_codes)
        self.warm(targets)
        return [self.evaluate(c) for c in targets]


_service: Optional[RepricingService] = None


def get_repricing_service(phase_provider=None) -> RepricingService:
    """❗单例：池子是共享状态，多实例会各自缓存出不同的尺子。"""
    global _service
    if _service is None:
        _service = RepricingService(phase_provider=phase_provider)
    elif phase_provider is not None and _service._phase_provider is None:
        _service._phase_provider = phase_provider
    return _service
