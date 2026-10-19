"""基本面拉取服务：取数 → 落库 → 给出可消费的快照。

调用方只需要 ``snapshot(symbol)``：拿到的是「最新一期 + 数据多旧 + 缺什么」，
不需要知道数据来自东财还是 SEC，也不需要自己判空。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterable, List, Optional

from .store import FundamentalStore

log = logging.getLogger(__name__)

#: 季频数据，超过这个年龄就提示「该更新了」（不是错误）
STALE_AFTER_DAYS = 120


def _payload(row: Any) -> Dict[str, Any]:
    return {
        "symbol": getattr(row, "stock_code", ""),
        "period": getattr(row, "report_date", ""),
        "period_end": getattr(row, "period_end", "") or getattr(row, "report_date", ""),
        "revenue": getattr(row, "revenue", 0.0),
        "revenue_yoy": getattr(row, "revenue_yoy", 0.0),
        "net_profit": getattr(row, "net_profit", 0.0),
        "net_profit_yoy": getattr(row, "net_profit_yoy", 0.0),
        "gross_margin": getattr(row, "gross_margin", 0.0),
        "cashflow": getattr(row, "cashflow", 0.0),
        "capex": getattr(row, "capex", 0.0),
        "eps": getattr(row, "eps", None),
        "bps": getattr(row, "bps", None),
        "equity": getattr(row, "equity", None),
        "notice_date": getattr(row, "notice_date", ""),
        "report_type": getattr(row, "report_type", ""),
        "source": getattr(row, "source", "") or "unknown",
        "missing": list(getattr(row, "missing", []) or []),
    }


class FundamentalService:
    """财报取数与快照。单例由 :func:`get_fundamental_service` 管理。"""

    def __init__(self, store: Optional[FundamentalStore] = None, fetcher: Any = None):
        self.store = store or FundamentalStore()
        self._fetcher = fetcher

    @property
    def fetcher(self):
        if self._fetcher is None:
            from ..structural_growth.financial_data_fetcher import (
                get_financial_data_fetcher,
            )
            self._fetcher = get_financial_data_fetcher()
        return self._fetcher

    def refresh(self, symbols: Iterable[str], force: bool = True) -> Dict[str, Dict[str, Any]]:
        """拉取并落库，返回每只票的状态。失败不影响其他标的。"""
        out: Dict[str, Dict[str, Any]] = {}
        for raw in symbols:
            symbol = str(raw).strip()
            if not symbol:
                continue
            try:
                rows = self.fetcher.fetch(symbol, force_refresh=force) or []
            except Exception as e:  # noqa: BLE001 - 单只票失败不能拖垮整批
                log.warning("[Fundamental] %s 拉取失败: %s", symbol, e)
                out[symbol] = {"ok": False, "reason": f"{type(e).__name__}: {e}", "periods": 0}
                continue

            if not rows:
                out[symbol] = {
                    "ok": False,
                    "reason": "无财报数据（ETF/基金或数据源无覆盖）",
                    "periods": 0,
                }
                continue

            for row in rows:
                payload = _payload(row)
                self.store.upsert(symbol, payload["period"], payload)
            latest = _payload(rows[0])
            out[symbol] = {
                "ok": True,
                "periods": len(rows),
                "latest_period": latest["period"],
                "source": latest["source"],
                "missing": latest["missing"],
            }
        return out

    def snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """给决策侧用的快照：最新一期 + 新鲜度 + 是否可用。

        Returns:
            ``None`` 表示本地完全没有这只票的财报（例如 ETF）。调用方必须
            把它当成「无基本面」，而不是「中性」。
        """
        row = self.store.latest(symbol)
        if not row:
            return None
        age_days = None
        try:
            ts = row.get("_fetched_at")
            if ts:
                age_days = round((time.time() - float(ts)) / 86400.0, 1)
        except (TypeError, ValueError):
            age_days = None
        missing = list(row.get("missing") or [])
        return {
            **row,
            "age_days": age_days,
            "stale": bool(age_days is not None and age_days > STALE_AFTER_DAYS),
            "usable": bool(row.get("revenue") or row.get("net_profit")),
            "has_gross_margin": "gross_margin" not in missing,
            "has_capex": "capex" not in missing,
        }

    def warm_payload(self, symbol: str) -> Optional[Dict[str, Any]]:
        """把最近一次估值结果压成 QueryState 需要的那几个键（重启预热用）。"""
        cached = self.store.latest_evaluation(symbol)
        if not cached or not cached.get("ok"):
            return None
        val = cached.get("valuation") or {}
        fund = cached.get("fundamental") or {}
        return {
            "tier": cached.get("tier"),
            "total": cached.get("total"),
            "allows_dip": bool(cached.get("allows_dip")),
            "forward_scale": cached.get("forward_scale"),
            "pe": val.get("pe"),
            "pe_percentile": val.get("pe_percentile"),
            "pb": val.get("pb"),
            "pb_percentile": val.get("pb_percentile"),
            "roe": fund.get("roe"),
            "flags": (cached.get("score") or {}).get("flags") or [],
            "period_end": fund.get("period_end"),
            "basis": fund.get("basis"),
            "as_of": cached.get("as_of"),
            "_computed_at": cached.get("_computed_at"),
            "_warm": True,
        }

    def stats(self) -> Dict[str, Any]:
        return self.store.stats()

    # ------------------------------------------------------------ 估值与打分

    @staticmethod
    def _bare(symbol: str) -> str:
        """去掉 ``sh``/``sz``/``SH.`` 前缀：核心持仓里写的是 ``sh588200``，
        而东财接口要的是 ``588200``。带前缀直接查会静默返回空。"""
        import re

        return re.sub(r"^(sh|sz)\.?", "", str(symbol).strip(), flags=re.IGNORECASE)

    def _points(self, symbol: str, force: bool = False):
        """取时点基本面序列。A 股走东财累计差分，美股走 SEC 季度滚动。"""
        from ..structural_growth.financial_data_fetcher import _is_us_stock
        from . import points as points_mod

        if _is_us_stock(symbol):
            return points_mod.us_series(symbol)

        bare = self._bare(symbol)
        rows = []
        try:
            rows = self.fetcher.fetch(bare, force_refresh=force) or []
        except Exception as e:  # noqa: BLE001
            log.warning("[Fundamental] %s 财报拉取失败: %s", symbol, e)
        if rows:
            # 顺手落库：估值路径本身就在取财报，没有理由再跑一遍刷新
            for row in rows:
                try:
                    payload = _payload(row)
                    self.store.upsert(bare, payload["period"], payload)
                except Exception:
                    continue
        else:
            rows = self._rows_from_store(bare)
        return points_mod.a_share_series(rows) if rows else []

    def _rows_from_store(self, symbol: str) -> List[Any]:
        """离线兜底：把落库的 payload 还原成 ``StockFinancial``，字段缺失即为 None。"""
        from types import SimpleNamespace

        rows = []
        for item in self.store.history(symbol, limit=12):
            rows.append(
                SimpleNamespace(
                    stock_code=symbol,
                    report_date=item.get("period", ""),
                    period_end=item.get("period_end", ""),
                    revenue=item.get("revenue"),
                    revenue_yoy=item.get("revenue_yoy"),
                    net_profit=item.get("net_profit"),
                    net_profit_yoy=item.get("net_profit_yoy"),
                    gross_margin=item.get("gross_margin"),
                    cashflow=item.get("cashflow"),
                    capex=item.get("capex"),
                    eps=item.get("eps"),
                    bps=item.get("bps"),
                    equity=item.get("equity"),
                    notice_date=item.get("notice_date", ""),
                    report_type=item.get("report_type", ""),
                    missing=item.get("missing") or [],
                )
            )
        return rows

    @staticmethod
    def _yoy(points_list) -> tuple:
        """用 TTM 序列自算同比，避免依赖单期累计值的同比字段。"""
        if len(points_list) < 2:
            return None, None
        latest = points_list[-1]
        try:
            from datetime import date, timedelta

            target = (date.fromisoformat(latest.period_end) - timedelta(days=350)).isoformat()
        except (TypeError, ValueError):
            return None, None
        base = None
        for p in points_list:
            if p.period_end <= target:
                base = p
        if base is None:
            return None, None

        def _chg(cur, old):
            if cur is None or old in (None, 0):
                return None
            return (cur - old) / abs(old) * 100.0

        return (
            _chg(latest.revenue_ttm, base.revenue_ttm),
            _chg(latest.net_profit_ttm, base.net_profit_ttm),
        )

    def evaluate(self, symbol: str, force: bool = False) -> Dict[str, Any]:
        """一次性给出：估值分位 + 质量/风险打分 + 档位。

        结果按 (symbol, 当日) 落库，重启后当天不必重算（5 年日线 + SEC 全量
        companyfacts 都不便宜）。``force=True`` 强制重算。
        """
        from datetime import date

        from . import prices as prices_mod
        from . import score as score_mod
        from . import valuation as valuation_mod

        key = str(symbol).strip()
        today = date.today().isoformat()
        if not force:
            cached = self.store.get_evaluation(key, today)
            if cached:
                # 老缓存（本次改动之前写下的）没有 no_fundamental 字段。
                # 直接当 False 会让 ETF 走进「取数失败」分支，把 NA 标记删掉。
                cached.setdefault(
                    "no_fundamental",
                    not bool((cached.get("fundamental") or {}).get("period_end")),
                )
                return cached

        points_list = self._points(key, force=force)
        price_series = prices_mod.daily_closes(key, years=5)
        val = valuation_mod.build(key, price_series, points_list)
        rev_yoy, np_yoy = self._yoy(points_list)
        current = points_list[-1] if points_list else None
        sc = score_mod.score(key, current, val, rev_yoy=rev_yoy, np_yoy=np_yoy)

        out: Dict[str, Any] = {
            "symbol": key,
            "as_of": today,
            "tier": sc.tier,
            "total": round(sc.total, 1),
            "forward_scale": score_mod.TIER_SCALE.get(sc.tier, 0.0),
            "allows_dip": score_mod.allows_dip(sc.tier),
            "score": sc.to_dict(),
            "valuation": val.to_dict(),
            "fundamental": {
                "period_end": current.period_end if current else "",
                "as_of": current.as_of if current else "",
                "basis": current.basis if current else "",
                "source": current.source if current else "",
                "eps_ttm": current.eps_ttm if current else None,
                "bps": current.bps if current else None,
                "roe": None if not current or current.roe is None else round(current.roe, 2),
                "cash_conversion": (
                    None if not current or current.cash_conversion is None
                    else round(current.cash_conversion, 2)
                ),
                "net_profit_ttm": current.net_profit_ttm if current else None,
                "revenue_ttm": current.revenue_ttm if current else None,
                "revenue_yoy": None if rev_yoy is None else round(rev_yoy, 2),
                "net_profit_yoy": None if np_yoy is None else round(np_yoy, 2),
            },
            "ok": bool(current is not None and sc.tier != "NA"),
            # 区分两件完全不同的事：**这类标的没有企业财报**（ETF/基金） vs
            # **这次没取到**。前者是结构性的，不该按「数据缺失」打折。
            "no_fundamental": current is None,
        }
        try:
            self.store.put_evaluation(key, today, out)
        except Exception as e:  # pragma: no cover
            log.debug("[Fundamental] 估值缓存写入失败: %s", e)
        return out


_service: Optional[FundamentalService] = None


def get_fundamental_service() -> FundamentalService:
    global _service
    if _service is None:
        _service = FundamentalService()
    return _service
