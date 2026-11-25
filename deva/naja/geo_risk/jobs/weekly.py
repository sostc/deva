"""
周报：近 7 天新增证据 + 等级变化 + 压力情景排序

只读状态文件与库，不写评级状态（状态由日更维护）；周一 09:00 由 cron 触发。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from deva.naja.geo_risk.jobs.daily import (
    _as_date,
    _clusters_by_project,
    _load_rows,
    _load_state,
    _project_row,
    _resolve_db,
    _resolve_report_dir,
    _snapshot_for,
    _compute_metrics,
)
from deva.naja.geo_risk.model.rating import GRADE_LABEL


def _parse_day(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _source_counts(evidence: List[Dict], start: date) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in evidence:
        day = _parse_day(row.get("retrieved_at")) or _parse_day(row.get("published_at"))
        if day is None or day < start:
            continue
        counts[row["source"]] = counts.get(row["source"], 0) + 1
    return counts


def _weekly_changes(projects: Dict[str, Dict], start: date, end: date) -> List[Dict[str, Any]]:
    changes = []
    for pid, item in projects.items():
        hist = [
            h for h in (item.get("history") or [])
            if start <= (datetime.fromisoformat(h["date"]).date()) <= end
        ]
        if len(hist) >= 2 and hist[0]["grade"] != hist[-1]["grade"]:
            changes.append({
                "project_id": pid,
                "from": hist[0]["grade"],
                "to": hist[-1]["grade"],
                "at": hist[-1]["date"],
            })
    return changes


def render_weekly(end: date, start: date, stats: Dict[str, Any],
                  rows: List[Dict[str, Any]], source_counts: Dict[str, int],
                  changes: List[Dict[str, Any]], warnings: List[str]) -> str:
    lines = [
        f"# 东南亚 AI 算力风险周报 {start.isoformat()} ~ {end.isoformat()}",
        "",
        "## 概览",
        f"- 本周新增证据 {stats['new_evidence']} 条；项目 {stats['projects']} 个，事件簇 {stats['clusters']} 个",
        f"- 已评级 {stats['rated']} 个，未评级 {stats['unrated']} 个",
        "",
        "## 来源分布（本周新增）",
        "",
    ]
    if source_counts:
        for source, count in sorted(source_counts.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"- {source}: {count}")
    else:
        lines.append("- 本周无新增证据")

    lines += ["", "## 等级变化", ""]
    if changes:
        for c in changes:
            name = next((r["name"] for r in rows if r["project_id"] == c["project_id"]),
                        c["project_id"])
            lines.append(
                f"- {name}: {GRADE_LABEL.get(c['from'], c['from'])} → "
                f"{GRADE_LABEL.get(c['to'], c['to'])}（{c['at']}）"
            )
    else:
        lines.append("- 无等级变化")

    lines += [
        "",
        "## 当前评级与压力情景",
        "",
        "| 项目 | 评级 | 分数 | LTV | DSCR | 压力 LTV | 压力 DSCR |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        grade = f"{GRADE_LABEL[row['grade']]}{row['grade']}" if row["grade"] else "未评级"
        lines.append(
            "| {name} | {grade} | {score} | {ltv} | {dscr} | {sltv} | {sdscr} |".format(
                name=row["name"], grade=grade,
                score="—" if row["score"] is None else f"{row['score']:.2f}",
                ltv="—" if row["ltv"] is None else f"{row['ltv']:.3f}",
                dscr="—" if row["dscr"] is None else f"{row['dscr']:.3f}",
                sltv="—" if row["severe_ltv"] is None else f"{row['severe_ltv']:.3f}",
                sdscr="—" if row["severe_dscr"] is None else f"{row['severe_dscr']:.3f}",
            )
        )

    stressed = [r for r in rows if r["severe_dscr"] is not None and r["severe_dscr"] < 1.0]
    if stressed:
        lines += ["", "## 压力情景跌破 DSCR 1.0", ""]
        for r in sorted(stressed, key=lambda x: x["severe_dscr"]):
            lines.append(f"- {r['name']}: 压力 DSCR {r['severe_dscr']:.3f}，压力 LTV {r['severe_ltv']:.3f}")

    if warnings:
        lines += ["", "## 数据告警", ""]
        lines += [f"- {w}" for w in warnings]

    lines += ["", "---", "由 geo_risk 周报任务生成。"]
    return "\n".join(lines) + "\n"


def run_weekly(
    *,
    as_of: Optional[Any] = None,
    days: int = 7,
    db=None,
    db_path=None,
    snapshots: Optional[Dict[str, Dict]] = None,
    report_dir=None,
    notifier: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    end = _as_date(as_of)
    start = end - timedelta(days=max(1, int(days)))
    database = _resolve_db(db, db_path)
    out_dir = _resolve_report_dir(report_dir, creating=True)

    projects, entities, evidence = _load_rows(database)
    clusters = _clusters_by_project(entities, evidence, projects)
    state = _load_state(out_dir)

    rows: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for project in projects:
        pid = project["project_id"]
        snapshot = _snapshot_for(project, snapshots)
        metrics: Dict[str, Any] = {}
        if snapshot:
            try:
                metrics = _compute_metrics(project, snapshot,
                                           state.get("projects", {}).get(pid, {}).get("grade"))
            except (ValueError, KeyError, TypeError) as exc:
                warnings.append(f"{project.get('name', pid)} 模型输入无效: {exc}")
        rows.append(_project_row(project, clusters.get(pid), metrics))

    source_counts = _source_counts(evidence, start)
    new_evidence = sum(source_counts.values())
    changes = _weekly_changes(state.get("projects", {}), start, end)

    stats = {
        "projects": len(projects),
        "clusters": len(clusters),
        "new_evidence": new_evidence,
        "rated": sum(1 for r in rows if r["grade"]),
        "unrated": sum(1 for r in rows if not r["grade"]),
    }
    text = render_weekly(end, start, stats, rows, source_counts, changes, warnings)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"weekly-{end.isoformat()}.md"
    path.write_text(text, encoding="utf-8")

    if notifier:
        for c in changes:
            notifier({**c, "kind": "weekly_change"})

    return {
        "date": end.isoformat(),
        "window": [start.isoformat(), end.isoformat()],
        "path": str(path),
        "stats": stats,
        "changes": changes,
        "warnings": warnings,
    }
