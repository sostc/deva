"""
geo_risk 生产采集编排：collect → extract → 实体解析 → evidence → series

为什么需要这一层
----------------
collectors/*.py 与 llm/extract.py 各自可单测，但此前**没有任何生产调用方**：
开 NAJA_GEO_RISK_ENABLE 也只会建空库，日更永远输出「0 项目」。本模块把
零散能力串成一个可被 cron / 手工调用、且结果可观测的编排单元。

边界（对应 notes/2026-11-23 §3.3 / §4）：
- 采集器全部按日更设计，不进 market_hotspot 的秒级 tick；
- 模型不在这里算，日更任务才算；这里只负责把「真实抓到的事实」落库；
- ❗只写真实抽取到的字段：缺就是缺，绝不把 None 填成 0 伪装成事实；
  财务模型输入（债务/租金/利用率）不由新闻抽取器产出，缺就让它缺。

产出统计（每次调用都返回）：
    fetched/parsed/extracted/stored/duplicates/unresolved/series/failed_sources
失败逐源记录，单源失败不拖垮整批；整批异常由 @probe 记到首页。
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from deva.core.bus import log
from deva.naja.geo_risk.collectors.base import RawItem
from deva.naja.geo_risk.collectors.ingest import persist_items
from deva.naja.geo_risk.entities.resolver import EntityIndex
from deva.naja.geo_risk.llm.extract import GeoRiskExtractor
from deva.naja.geo_risk.store.db import GeoRiskDB, get_db

# 采集器清单：(source_id, 无参 fetch 函数)。新增来源只加一行。
COLLECTORS = (
    ("federal_register", "deva.naja.geo_risk.collectors.federal_register", "fetch_documents"),
    ("bis", "deva.naja.geo_risk.collectors.bis", "fetch_documents"),
    ("media", "deva.naja.geo_risk.collectors.media", "fetch_all"),
)

#: 只有「抽取器真的报了值」才写 series； None / 空串一律跳过。
_SERIES_FIELDS = ("capacity_mw", "gpu_count")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _as_of_str(as_of: Optional[Any]) -> str:
    if as_of is None:
        return date.today().isoformat()
    if isinstance(as_of, (date, datetime)):
        return as_of.strftime("%Y-%m-%d")
    return str(as_of)[:10]


def _load_collector(module_path: str, func_name: str) -> Callable[..., List[RawItem]]:
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


def _run_one_collector(source_id: str, module_path: str, func_name: str) -> List[RawItem]:
    fn = _load_collector(module_path, func_name)
    result = fn()
    if result is None:
        return []
    if not isinstance(result, (list, tuple)):
        raise TypeError(f"{source_id} 返回的不是列表: {type(result).__name__}")
    return [r for r in result if isinstance(r, RawItem)]


def _project_id_for(item: RawItem, fields: Dict[str, Any], db: GeoRiskDB,
                    by_name: Dict[str, str]) -> Optional[str]:
    """把抽取结果关联到已知项目；不认识就返回 None，不凭空造项目。"""
    name = (fields.get("project_name") or "").strip().lower()
    if name and name in by_name:
        return by_name[name]
    text = f"{item.title} {item.body}".lower()
    for known_name, pid in by_name.items():
        if len(known_name) >= 8 and known_name in text:
            return pid
    return None


def run_pipeline(
    *,
    db=None,
    db_path=None,
    as_of: Optional[Any] = None,
    extractor: Optional[GeoRiskExtractor] = None,
    collectors: Optional[Sequence[tuple]] = None,
    max_items: int = 60,
) -> Dict[str, Any]:
    """跑一次采集编排，返回逐源统计。不抛异常给调用方（失败进 failed_sources）。

    Args:
        db/db_path: 传 db 用现成库；都不传时走生产默认路径（受开关保护）。
        max_items: 单次送入 LLM 的最大条数，控制成本；超出部分只采集不抽。
    """
    database = db if db is not None else get_db(db_path)
    sources = tuple(collectors) if collectors is not None else COLLECTORS
    extractor = extractor or GeoRiskExtractor()
    as_of_str = _as_of_str(as_of)
    stats: Dict[str, Any] = {
        "as_of": as_of_str,
        "fetched": 0,
        "extracted": 0,
        "stored": 0,
        "duplicates": 0,
        "unresolved": 0,
        "series": 0,
        "degraded": 0,
        "failed_sources": [],
    }

    # 先建实体索引与项目名索引（库为空时也能跑，只是全部 unresolved）
    index = EntityIndex.from_db(database)
    projects = [dict(r) for r in database.query("SELECT project_id, name FROM project")]
    by_name = {(p.get("name") or "").strip().lower(): p["project_id"] for p in projects}

    items: List[RawItem] = []
    for source_id, module_path, func_name in sources:
        try:
            got = _run_one_collector(source_id, module_path, func_name)
            items.extend(got)
            log.info("[GeoRisk] 采集 %s: %d 条", source_id, len(got))
        except Exception as exc:  # noqa: BLE001 - 单源失败不影响其它源
            msg = f"{source_id}: {type(exc).__name__}: {exc}"
            stats["failed_sources"].append(msg)
            log.warning("[GeoRisk] 采集失败 %s", msg)
    stats["fetched"] = len(items)

    if not items:
        return stats

    # 抽取：asyncio.run 一次跑完，避免每条都建 event loop
    async def _extract_all(batch: List[RawItem]):
        return await asyncio.gather(*[
            extractor.extract({
                "source": it.source, "url": it.url, "title": it.title,
                "text": it.body, "published_at": it.published_at,
            }) for it in batch
        ], return_exceptions=True)

    try:
        results = asyncio.run(_extract_all(items[:max_items]))
    except Exception as exc:  # noqa: BLE001
        stats["failed_sources"].append(f"extract: {type(exc).__name__}: {exc}")
        return stats

    enriched: List[RawItem] = []
    series_rows: List[Dict[str, Any]] = []
    for item, res in zip(items[:max_items], results):
        if isinstance(res, BaseException):
            stats["failed_sources"].append(f"extract:{item.source}: {type(res).__name__}")
            continue
        fields = res.get("fields") or {}
        stats["extracted"] += 1
        if res.get("degraded"):
            stats["degraded"] += 1

        # 只把真实抽到的识别字段补进 RawItem；没抽到就保持原样
        title = fields.get("project_name") or item.title
        item.title = str(title)[:200]
        enriched.append(item)

        pid = _project_id_for(item, fields, database, by_name)
        if pid is None:
            continue
        for metric in _SERIES_FIELDS:
            value = fields.get(metric)
            if value is None:
                continue  # ❗缺就是缺，绝不写 0
            series_rows.append({
                "series_id": f"{as_of_str}|{pid}|{metric}|{item.url}",
                "project_id": pid,
                "metric": metric,
                "as_of": as_of_str,
                "value": str(value),
                "source_id": item.source,
                "observed_at": _now_iso(),
                "quality": "llm" if res.get("source") == "llm" else "rule",
            })

    # 未进 LLM 的尾部条目仍然入库（不抽字段，但事实本身有价值）
    enriched.extend(items[max_items:])

    persist_stats = persist_items(database, enriched, index)
    stats["stored"] = persist_stats["stored"]
    stats["duplicates"] = persist_stats["duplicates"]
    stats["unresolved"] = persist_stats["unresolved"]

    if series_rows:
        database.add_series(series_rows).result()
        stats["series"] = len(series_rows)

    return stats


def run_pipeline_probe() -> Dict[str, Any]:
    """供 cron / 手工触发的入口：受生产开关保护，挂探针由 jobs 层负责。"""
    from deva.naja.geo_risk.jobs.daily import is_enabled

    if not is_enabled():
        return {"enabled": False, "reason": "NAJA_GEO_RISK_ENABLE 未启用"}
    return {"enabled": True, **run_pipeline()}
