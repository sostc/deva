"""
/georisk 页面：风险等级、跃迁、证据覆盖与周报入口

只读渲染：未启用不建库；已启用但库不存在时显示空状态。
"""

from __future__ import annotations

import html
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from pywebio.output import put_html

from deva.naja.geo_risk.alerts import get_alert_center
from deva.naja.geo_risk.jobs.daily import (
    DEFAULT_REPORT_DIR,
    _load_state,
    is_enabled,
)
from deva.naja.geo_risk.model.rating import GRADE_LABEL
from deva.naja.geo_risk.store.db import DEFAULT_DB_PATH

_GRADE_STYLE = {
    "green": ("#e7f7ec", "#1a7f37"),
    "yellow": ("#fff8e1", "#9a6700"),
    "orange": ("#fff0e1", "#c05621"),
    "red": ("#fdecec", "#c53030"),
}


def _read_projects(db_path: Path) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT p.project_id, p.name, p.country, p.capacity_mw,
                   (SELECT COUNT(*) FROM evidence e
                     WHERE e.subject_type = 'project' AND e.subject_id = p.project_id) AS evidence_count
            FROM project p ORDER BY p.country, p.name
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "project_id": r[0], "name": r[1], "country": r[2] or "—",
            "capacity_mw": r[3], "evidence_count": r[4],
        }
        for r in rows
    ]


def load_view(
    *,
    report_dir: Optional[Path] = None,
    db_path: Optional[Path] = None,
    alert_limit: int = 10,
) -> Dict[str, Any]:
    report_path = Path(report_dir) if report_dir else DEFAULT_REPORT_DIR
    database = Path(db_path) if db_path else DEFAULT_DB_PATH
    enabled = is_enabled()
    state = _load_state(report_path)

    projects = _read_projects(database) if database.exists() else []
    grades = state.get("projects", {}) if isinstance(state.get("projects"), dict) else {}

    for project in projects:
        item = grades.get(project["project_id"], {})
        project["grade"] = item.get("grade")
        project["score"] = item.get("score")
        project["updated"] = item.get("updated")

    reports = sorted(report_path.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True) \
        if report_path.exists() else []

    return {
        "enabled": enabled,
        "db_exists": database.exists(),
        "db_path": str(database),
        "report_dir": str(report_path),
        "projects": projects,
        "alerts": get_alert_center().get_latest(alert_limit),
        "latest_report": reports[0].name if reports else None,
        "report_count": len(reports),
    }


def _fmt_score(value: Any) -> str:
    return "" if value is None else f"{float(value):.2f}"


def _grade_badge(grade: Optional[str]) -> str:
    if not grade:
        return '<span class="badge muted">未评级</span>'
    bg, fg = _GRADE_STYLE.get(grade, ("#eee", "#555"))
    label = GRADE_LABEL.get(grade, grade)
    return f'<span class="badge" style="background:{bg};color:{fg}">{label} · {grade}</span>'


def build_html(view: Dict[str, Any]) -> str:
    if not view["enabled"]:
        banner = (
            '<div class="banner warn">未启用：设置 <code>NAJA_GEO_RISK_ENABLE=1</code> '
            "并重启 naja 后才会注册日更/周报。</div>"
        )
    elif not view["db_exists"]:
        banner = (
            '<div class="banner info">已启用，但库尚未创建。首轮采集或日更运行后'
            f"<br><span class=\"path\">{html.escape(view['db_path'])}</span></div>"
        )
    else:
        banner = (
            f'<div class="banner info">库：<span class="path">{html.escape(view["db_path"])}</span>'
            f'<br>报告目录：<span class="path">{html.escape(view["report_dir"])}</span>'
            f'（{view["report_count"]} 份，最近 {html.escape(view["latest_report"] or "—")}）</div>'
        )

    cards = f"""
    <div class="cards">
      <div class="card"><div class="num">{len(view['projects'])}</div><div class="label">项目</div></div>
      <div class="card"><div class="num">{sum(1 for p in view['projects'] if p.get('grade'))}</div><div class="label">已评级</div></div>
      <div class="card"><div class="num">{len(view['alerts'])}</div><div class="label">近期跃迁</div></div>
    </div>
    """

    rows = "".join(
        "<tr>"
        f"<td>{html.escape(p['name'] or p['project_id'])}</td>"
        f"<td>{html.escape(p['country'])}</td>"
        f"<td>{'' if p['capacity_mw'] is None else p['capacity_mw']}</td>"
        f"<td>{p['evidence_count']}</td>"
        f"<td>{_fmt_score(p['score'])}</td>"
        f"<td>{_grade_badge(p.get('grade'))}</td>"
        f"<td class='muted'>{html.escape(p.get('updated') or '—')}</td>"
        "</tr>"
        for p in view["projects"]
    )
    table = (
        '<table><thead><tr><th>项目</th><th>国家</th><th>容量(MW)</th><th>证据</th>'
        '<th>分数</th><th>评级</th><th>更新</th></tr></thead><tbody>'
        f"{rows}</tbody></table>"
        if view["projects"] else
        '<div class="empty">暂无项目。启用后先运行采集与日更。</div>'
    )

    alerts = "".join(
        "<li>"
        f"<b>{html.escape(str(a.get('name') or a.get('project_id') or '—'))}</b> "
        f"{html.escape(str(a.get('from')))} → {html.escape(str(a.get('to')))}"
        f'<span class="muted">（{html.escape(str(a.get("direction") or ""))}）</span>'
        "</li>"
        for a in view["alerts"]
    )
    alert_html = f"<ul class=\"alerts\">{alerts}</ul>" if alerts else '<div class="empty">暂无等级跃迁</div>'

    return f"""
    <style>
      .geo-wrap {{ font-family: -apple-system, "PingFang SC", sans-serif; color:#1f2328; }}
      .geo-wrap h1 {{ font-size:22px; margin:0 0 14px; }}
      .banner {{ padding:10px 14px; border-radius:8px; margin-bottom:14px; line-height:1.7;
                background:#eff6ff; border:1px solid #bfdbfe; }}
      .banner.warn {{ background:#fff7ed; border-color:#fed7aa; }}
      .path {{ font-family: ui-monospace, SFMono-Regular, monospace; font-size:12px; color:#57606a; }}
      .cards {{ display:flex; gap:12px; margin:14px 0 18px; }}
      .card {{ flex:1; border:1px solid #e5e7eb; border-radius:10px; padding:12px 14px; background:#fff; }}
      .card .num {{ font-size:26px; font-weight:600; }}
      .card .label {{ color:#6b7280; font-size:12px; margin-top:2px; }}
      table {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid #e5e7eb; border-radius:10px; overflow:hidden; }}
      th, td {{ padding:9px 10px; border-bottom:1px solid #eef0f2; text-align:left; font-size:13px; }}
      th {{ background:#f8fafc; color:#57606a; font-weight:600; }}
      .badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; }}
      .badge.muted {{ background:#f1f3f5; color:#6b7280; }}
      .muted {{ color:#6b7280; }}
      .alerts {{ margin:0; padding-left:18px; line-height:1.9; }}
      .empty {{ color:#6b7280; padding:12px 0; }}
      h2 {{ font-size:16px; margin:22px 0 10px; }}
    </style>
    <div class="geo-wrap">
      <h1>东南亚 AI 算力风险监控</h1>
      {banner}
      {cards}
      <h2>项目评级</h2>
      {table}
      <h2>等级跃迁（仅变化时推送）</h2>
      {alert_html}
      <p class="muted" style="margin-top:18px">评级规则：政策 35% / 利用率 25% / 价格 20% / 信用 20%，
      信用分由 LTV 与 DSCR 折算；压力情景含中国客户流失、租赁价下跌、再融资上行。</p>
    </div>
    """


async def render_geo_risk(ctx: dict):
    await ctx["init_naja_ui"]("东南亚算力风险")
    put_html(build_html(load_view()))
