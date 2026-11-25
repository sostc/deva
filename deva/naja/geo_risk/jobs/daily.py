"""
日更任务：读库 → 事件归并 → 模型指标/评级 → 写日报

放置原则（报告 §6/§7）：
- 走 SchedulerManager 的 cron（7:30），不进 market_hotspot 的 2 秒 tick；
- 只有 ``NAJA_GEO_RISK_ENABLE`` 开启时才允许创建生产库/写生产报告；
- 评级变化只在这里算一次，推送交给 notifier（P5 告警模块）。
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from deva.core.bus import log
from deva.llm.errors import LLMError  # noqa: F401  (保留给调用方统一捕获)
from deva.naja.geo_risk.entities.resolver import EntityIndex
from deva.naja.geo_risk.events.dedupe import cluster_mentions
from deva.naja.geo_risk.events.models import Mention
from deva.naja.geo_risk.model.rating import GRADE_LABEL, credit_dimension, rate
from deva.naja.geo_risk.model.stress import apply_scenario

ENV_FLAG = "NAJA_GEO_RISK_ENABLE"
DEFAULT_REPORT_DIR = Path.home() / ".naja" / "reports" / "geo_risk"
SEVERE_SCENARIO = {"china_churn": 0.8, "rent_decline": 0.3, "refinance_bps": 300}


def is_enabled() -> bool:
    return os.getenv(ENV_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def _as_date(value: Optional[Any]) -> date:
    if value is None:
        return datetime.now().date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def _safe_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _resolve_db(db=None, db_path=None):
    if db is not None:
        return db
    if db_path is None and not is_enabled():
        raise RuntimeError(
            f"{ENV_FLAG} 未启用：拒绝创建生产库。测试请显式传 db 或 db_path。"
        )
    from deva.naja.geo_risk.store.db import get_db
    return get_db(db_path)


def _resolve_report_dir(report_dir, *, creating: bool) -> Path:
    if report_dir is None:
        if creating and not is_enabled():
            raise RuntimeError(
                f"{ENV_FLAG} 未启用：拒绝写生产报告目录。测试请显式传 report_dir。"
            )
        return DEFAULT_REPORT_DIR
    return Path(report_dir)


def _load_rows(db) -> tuple[list, list, list]:
    projects = [dict(r) for r in db.query("SELECT * FROM project")]
    entities = []
    for r in db.query("SELECT * FROM entity"):
        row = dict(r)
        row["aliases"] = _safe_json(row.get("aliases"), [])
        entities.append(row)
    evidence = [dict(r) for r in db.query(
        "SELECT * FROM evidence ORDER BY write_seq"
    )]
    return projects, entities, evidence


def _evidence_to_mention(row: Dict[str, Any], projects: Dict[str, Dict[str, Any]]) -> Mention:
    pid = row["subject_id"] if row["subject_type"] == "project" else ""
    project = projects.get(pid, {})
    fields = {}
    if project.get("capacity_mw") is not None:
        fields["capacity_mw"] = project["capacity_mw"]
    if project.get("gpu_count") is not None:
        fields["gpu_count"] = project["gpu_count"]
    quote = row.get("quote") or ""
    return Mention(
        mention_id=row["evidence_id"],
        title=quote[:60] or row.get("event_hint") or row["source"],
        source=row["source"],
        url=row["url"],
        published_at=row.get("published_at") or "",
        text=quote,
        project_id=pid,
        project_name=project.get("name", ""),
        country=project.get("country", ""),
        site=project.get("site", ""),
        operator_entity_id=project.get("operator_entity_id", ""),
        evidence_id=row["evidence_id"],
        fields=fields,
    )


def _clusters_by_project(entities: List[Dict], evidence: List[Dict],
                         projects: List[Dict]) -> Dict[str, Any]:
    project_map = {p["project_id"]: p for p in projects}
    mentions = [_evidence_to_mention(r, project_map) for r in evidence]
    index = EntityIndex(entities)
    clusters = cluster_mentions(mentions, index)
    return {c.project_id: c for c in clusters if c.project_id in project_map}


def _snapshot_for(project: Dict[str, Any], snapshots: Optional[Dict[str, Dict]],
                  db=None) -> Optional[Dict]:
    """模型输入优先级：显式 snapshots > DB series > project.customer_mix。

    ❗series 里只存真实抓到的字段；缺的字段保持缺失，让模型明确报「缺哪些」，
    绝不用 0 把「不知道」伪装成「知道」。
    """
    pid = project["project_id"]
    if snapshots and pid in snapshots:
        return snapshots[pid]

    snapshot: Dict[str, Any] = {}
    if db is not None:
        try:
            from deva.naja.geo_risk.model.stress import SNAPSHOT_KEYS
            latest = db.latest_series(pid)
            # 只有 stress.SNAPSHOT_KEYS 里的字段才是模型输入；识别类字段不算。
            for key in (*SNAPSHOT_KEYS, "dimensions"):
                if key not in latest:
                    continue
                raw = latest[key]["value"]
                if raw in (None, ""):
                    continue
                if key in ("gpu_models", "dimensions"):
                    snapshot[key] = _safe_json(raw, {})
                elif key in ("gpu_count",):
                    try:
                        snapshot[key] = int(float(raw))
                    except (TypeError, ValueError):
                        continue
                else:
                    try:
                        snapshot[key] = float(raw)
                    except (TypeError, ValueError):
                        continue
        except Exception as exc:  # noqa: BLE001 - 读不到就当没有，由报告报缺
            log.warning("[GeoRisk] 读取 %s 的 series 失败: %s", pid, exc)

    mix = _safe_json(project.get("customer_mix"), {})
    raw = mix.get("model_inputs") if isinstance(mix, dict) else None
    if isinstance(raw, dict):
        for k, v in raw.items():
            snapshot.setdefault(k, v)

    return snapshot or None


def _compute_metrics(project: Dict[str, Any], snapshot: Dict[str, Any],
                     previous_grade: Optional[str]) -> Dict[str, Any]:
    base = apply_scenario(snapshot, {})
    severe = apply_scenario(snapshot, SEVERE_SCENARIO)

    credit = credit_dimension(base["base"]["ltv"], base["base"]["dscr"])
    dims = snapshot.get("dimensions")
    rating = None
    rating_error = None
    if isinstance(dims, dict):
        merged = {k: dims.get(k) for k in ("policy", "utilization", "price")}
        if all(v is not None for v in merged.values()):
            merged["credit"] = credit["score"]
            rating = rate(merged, previous_grade)
        else:
            rating_error = "缺少 policy/utilization/price 维度"
    else:
        rating_error = "缺少 dimensions（政策/利用率/价格）"

    return {
        "base": base,
        "severe": severe,
        "credit": credit,
        "rating": rating,
        "rating_error": rating_error,
    }


_STATE_FILE = "state/ratings.json"


def _load_state(report_dir: Path) -> Dict[str, Any]:
    path = report_dir / _STATE_FILE
    if not path.exists():
        return {"version": 1, "projects": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "projects": {}}
    if not isinstance(data, dict) or not isinstance(data.get("projects"), dict):
        return {"version": 1, "projects": {}}
    return data


def _save_state(report_dir: Path, state: Dict[str, Any]) -> None:
    path = report_dir / _STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}{suffix}"
    return f"{value}{suffix}"


def _project_row(project: Dict[str, Any], cluster, metrics: Dict[str, Any]) -> Dict[str, Any]:
    rating = metrics.get("rating")
    latest = max(
        (m.published_at for m in cluster.mentions if m.published_at),
        default=None,
    ) if cluster else None
    return {
        "project_id": project["project_id"],
        "name": project.get("name") or project["project_id"],
        "country": project.get("country") or "—",
        "capacity_mw": project.get("capacity_mw"),
        "evidence_count": len(cluster.mentions) if cluster else 0,
        "latest": latest,
        "confidence": cluster.confidence if cluster else None,
        "grade": rating["grade"] if rating else None,
        "score": rating["score"] if rating else None,
        "ltv": metrics["base"]["base"]["ltv"] if metrics else None,
        "dscr": metrics["base"]["base"]["dscr"] if metrics else None,
        "severe_ltv": metrics["severe"]["stressed"]["ltv"] if metrics else None,
        "severe_dscr": metrics["severe"]["stressed"]["dscr"] if metrics else None,
        "rating_error": metrics.get("rating_error") if metrics else "无模型输入",
    }


def render_daily(as_of: date, stats: Dict[str, Any], rows: List[Dict[str, Any]],
                 transitions: List[Dict[str, Any]], warnings: List[str]) -> str:
    lines = [
        f"# 东南亚 AI 算力风险日报 {as_of.isoformat()}",
        "",
        "## 概览",
        f"- 项目 {stats['projects']} 个，实体 {stats['entities']} 个，证据 {stats['evidence']} 条",
        f"- 事件簇 {stats['clusters']} 个；已评级 {stats['rated']} 个，未评级 {stats['unrated']} 个",
        "",
        "## 项目与评级",
        "",
        "| 项目 | 国家 | 容量(MW) | 证据 | 最近证据 | 评级 | 分数 | LTV | DSCR | 压力 LTV | 压力 DSCR |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        grade = f"{GRADE_LABEL[row['grade']]}{row['grade']}" if row["grade"] else "未评级"
        lines.append(
            "| {name} | {country} | {cap} | {ev} | {latest} | {grade} | {score} | {ltv} | {dscr} | {sltv} | {sdscr} |".format(
                name=row["name"], country=row["country"], cap=_fmt(row["capacity_mw"]),
                ev=row["evidence_count"], latest=(row["latest"] or "—")[:10],
                grade=grade, score=_fmt(row["score"]), ltv=_fmt(row["ltv"]),
                dscr=_fmt(row["dscr"]), sltv=_fmt(row["severe_ltv"]),
                sdscr=_fmt(row["severe_dscr"]),
            )
        )

    lines += ["", "## 等级跃迁", ""]
    if transitions:
        for t in transitions:
            lines.append(
                f"- {t['name']}: {GRADE_LABEL.get(t['from'], t['from'])} → "
                f"{GRADE_LABEL.get(t['to'], t['to'])}（{t['direction']}，score={t['score']}）"
            )
    else:
        lines.append("- 无等级变化")

    unrated = [r for r in rows if not r["grade"]]
    if unrated:
        lines += ["", "## 未评级原因", ""]
        for r in unrated:
            lines.append(f"- {r['name']}: {r['rating_error']}")

    if warnings:
        lines += ["", "## 数据告警", ""]
        lines += [f"- {w}" for w in warnings]

    lines += ["", "---", "由 geo_risk 日更任务生成；评级规则见 model/rating.py。"]
    return "\n".join(lines) + "\n"


def run_daily(
    *,
    as_of: Optional[Any] = None,
    db=None,
    db_path=None,
    snapshots: Optional[Dict[str, Dict]] = None,
    report_dir=None,
    notifier: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """跑一次日更并返回摘要。报告文件路径在返回值的 ``path``。"""
    day = _as_date(as_of)
    database = _resolve_db(db, db_path)
    out_dir = _resolve_report_dir(report_dir, creating=True)

    projects, entities, evidence = _load_rows(database)
    clusters = _clusters_by_project(entities, evidence, projects)
    state = _load_state(out_dir)
    prev_projects = state.get("projects", {})

    rows: List[Dict[str, Any]] = []
    transitions: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for project in projects:
        pid = project["project_id"]
        cluster = clusters.get(pid)
        snapshot = _snapshot_for(project, snapshots, db=database)
        previous = prev_projects.get(pid, {}).get("grade")

        metrics: Optional[Dict[str, Any]] = None
        if snapshot:
            try:
                metrics = _compute_metrics(project, snapshot, previous)
            except (ValueError, KeyError, TypeError) as exc:
                warnings.append(f"{project.get('name', pid)} 模型输入无效: {exc}")
        row = _project_row(project, cluster, metrics or {})
        rows.append(row)

        if metrics and metrics.get("rating"):
            rating = metrics["rating"]
            transition = rating["transition"]
            if transition["changed"]:
                transitions.append({
                    "project_id": pid,
                    "name": row["name"],
                    "from": transition["previous"],
                    "to": rating["grade"],
                    "direction": transition["direction"],
                    "score": rating["score"],
                })
            hist = list(prev_projects.get(pid, {}).get("history") or [])
            entry = {"date": day.isoformat(), "grade": rating["grade"], "score": rating["score"]}
            if hist and hist[-1].get("date") == day.isoformat():
                hist[-1] = entry
            else:
                hist.append(entry)
            prev_projects[pid] = {
                "grade": rating["grade"],
                "score": rating["score"],
                "updated": day.isoformat(),
                "history": hist[-30:],
            }

    state = {"version": 1, "projects": prev_projects}

    stats = {
        "projects": len(projects),
        "entities": len(entities),
        "evidence": len(evidence),
        "clusters": len(clusters),
        "rated": sum(1 for r in rows if r["grade"]),
        "unrated": sum(1 for r in rows if not r["grade"]),
    }
    text = render_daily(day, stats, rows, transitions, warnings)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{day.isoformat()}.md"
    path.write_text(text, encoding="utf-8")
    _save_state(out_dir, state)

    if notifier:
        for t in transitions:
            notifier(t)

    return {
        "date": day.isoformat(),
        "path": str(path),
        "stats": stats,
        "transitions": transitions,
        "warnings": warnings,
    }
