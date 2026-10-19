"""每日新闻报告 —— 把「该看什么」落成一份可随时查看的产物。

数据流：
    已评分新闻（FocusedNewsStore，只含 deep 级）
        → NewsTriage（持仓优先相关度）
        → build_digest（纯 dict）
        → render_digest_html / render_digest_fragment / render_digest_text（呈现）
        → ~/.naja/news_digest/YYYY-MM-DD.html（可回看）

两种呈现外壳、一套正文：
    ``render_digest_html``      完整文档（归档文件、双击打开）
    ``render_digest_fragment``  ``<style>`` + 正文（``/news`` 页面内嵌，一次 put_html）

三条守约（与 decision 模块一致，本项目反复踩过的坑）：
  1. **不兜底合成**——没有新闻就 ``available=False`` + ``reason``，
     绝不伪造一份"看起来像"的报告。
  2. **降级要留痕**——焦点信息取不到时把原因带进报告，不静默当作"没命中"。
  3. **UI 只吃 dict**——``get_news_digest_summary()`` 返回纯 dict 副本。
"""

from __future__ import annotations

import html
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .dedup import format_dup_suffix
from .focus import NewsFocusState, build_focus_state, collapse_identifiers
from .triage import GROUP_LABELS, GROUP_ORDER, NewsTriage, TriageConfig

log = logging.getLogger(__name__)

DIGEST_DIR = Path.home() / ".naja" / "news_digest"
DEFAULT_WINDOW_HOURS = 24
DEFAULT_PER_GROUP_LIMIT = 8
# 扫描上限：先把最近的一批读进来，再按相关度挑（不是只取前 N 条）
DEFAULT_SCAN_LIMIT = 300


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


# ── 数据装配 ────────────────────────────────────────────────────────────


def build_digest(
    *,
    hours: int = DEFAULT_WINDOW_HOURS,
    per_group_limit: int = DEFAULT_PER_GROUP_LIMIT,
    scan_limit: int = DEFAULT_SCAN_LIMIT,
    items: Optional[Iterable[Dict[str, Any]]] = None,
    focus_state: Optional[NewsFocusState] = None,
) -> Dict[str, Any]:
    """生成一份新闻消化报告（纯 dict）。

    Args:
        items: 显式注入新闻列表（测试 / 验证用）；``None`` 则读
               ``FocusedNewsStore``（系统里**已评分**的新闻池）。
        focus_state: 显式注入焦点快照；``None`` 则实时构建。
    """
    generated_at = time.time()
    focus = focus_state if focus_state is not None else build_focus_state()

    if items is None:
        items, source_reason = _load_scored_news(hours=hours, limit=scan_limit)
    else:
        items = list(items)
        source_reason = None

    triage = NewsTriage(focus)
    analyzed = triage.analyze(items, per_group_limit=per_group_limit)

    scanned = analyzed["stats"]["scanned"]
    available = scanned > 0
    reason = None
    if not available:
        reason = source_reason or f"最近 {hours} 小时内没有已评分的新闻"

    return {
        "available": available,
        "reason": reason,
        "generated_at": generated_at,
        "generated_at_text": datetime.fromtimestamp(generated_at).strftime("%Y-%m-%d %H:%M:%S"),
        "window_hours": hours,
        "focus": focus.to_dict(),
        "groups": analyzed["groups"],
        "group_labels": analyzed["group_labels"],
        # 口径透明：把生效的档位区间一并带出去，UI 才能显示"凭什么这么排"
        "tier_config": analyzed["tier_config"],
        "stats": analyzed["stats"],
    }


def _load_scored_news(*, hours: int, limit: int) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """从 ``FocusedNewsStore`` 读已评分新闻；不可用时如实返回原因。"""
    try:
        from deva.naja.events.focused_news_store import get_focused_news_store

        store = get_focused_news_store()
        news = store.get_recent_news(hours=hours, limit=limit)
        return list(news), None
    except Exception as e:
        log.warning("[NewsDigest] 读取已评分新闻失败: %s", e)
        return [], f"新闻池不可用：{type(e).__name__}: {e}"


def get_news_digest_summary(
    *,
    hours: int = DEFAULT_WINDOW_HOURS,
    per_group_limit: int = DEFAULT_PER_GROUP_LIMIT,
) -> Dict[str, Any]:
    """[公开] dashboard / UI 用的报告数据（纯 dict）。

    这是 UI 侧的**唯一入口**——UI 不深入 ``NewsTriage`` / ``NewsFocusState``
    这些核心对象，只吃 dict。
    """
    try:
        return build_digest(hours=hours, per_group_limit=per_group_limit)
    except Exception as e:  # pragma: no cover - 防御
        log.warning("[NewsDigest] 生成报告失败: %s", e)
        return {
            "available": False,
            "reason": f"报告生成失败：{type(e).__name__}: {e}",
            "generated_at": time.time(),
            "generated_at_text": "",
            "window_hours": hours,
            "focus": {},
            "groups": {g: [] for g in GROUP_ORDER},
            "group_labels": dict(GROUP_LABELS),
            "tier_config": TriageConfig().to_dict(),
            "stats": {"scanned": 0, "deduped": 0, "shown": 0,
                      "holding": 0, "theme": 0, "macro": 0, "pierced": 0,
                      "merged": 0, "merged_by_rule": {}},
        }


# ── 呈现：纯文本（iMessage / 控制台）────────────────────────────────────


def render_digest_text(digest: Dict[str, Any]) -> str:
    """渲染成适合推送到手机的纯文本。"""
    if not digest.get("available"):
        return f"📰 今日新闻消化\n{_esc(digest.get('reason') or '暂无内容')}"

    stats = digest.get("stats") or {}
    focus = digest.get("focus") or {}
    groups = digest.get("groups") or {}
    labels = digest.get("group_labels") or GROUP_LABELS

    lines: List[str] = [
        f"📰 今日新闻消化 · {digest.get('generated_at_text', '')}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"扫描 {stats.get('scanned', 0)} 条"
        + (f" → 合并 {stats['merged']} 条重复" if stats.get("merged") else "")
        + f" → 精选 {stats.get('shown', 0)} 条"
        f"（持仓 {stats.get('holding', 0)} / 叙事 {stats.get('theme', 0)}"
        f" / 外部 {stats.get('macro', 0)}）",
    ]
    if stats.get("pierced"):
        lines.append(f"⚠️ 其中 {stats['pierced']} 条外部风险穿透（重大负面宏观，未被挡掉）")

    # 持仓与自选分行：两者不是一回事，合并显示会让"我的钱"被"在看的票"稀释
    for key, label in (("holdings", "持仓"), ("watchlist", "自选")):
        # 展示用 *_labels（优先中文名）；否则会列成"baba、阿里巴巴、nvda、英伟达"
        values = list(collapse_identifiers(
            focus.get(f"{key}_labels") or focus.get(key) or []
        ))
        if values:
            lines.append(f"{label}：{'、'.join(values[:8])}")

    for group in GROUP_ORDER:
        rows = groups.get(group) or []
        if not rows:
            continue
        lines.append("")
        lines.append(f"【{labels.get(group, group)}】")
        for i, row in enumerate(rows, 1):
            hits = (row.get("holding_hits") or []) + (row.get("watchlist_hits") or [])
            if row.get("pierced"):
                tag = " ⚠️风险穿透"
            elif hits:
                tag = f" ⭐{'/'.join(str(h) for h in hits)}"
            else:
                tag = ""
            lines.append(
                f"  {i}. [{row.get('relevance', 0):.2f}] {row.get('title', '')}"
                f"{format_dup_suffix(row.get('dup_count'))}{tag}"
            )

    degraded = focus.get("degraded") or []
    if degraded:
        lines.append("")
        lines.append(f"⚠️ 焦点信息降级 {len(degraded)} 处：{'；'.join(str(d) for d in degraded)}")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("🦐 虾丸自动生成")
    return "\n".join(lines)


# ── 呈现：自包含 HTML（报告文件）────────────────────────────────────────


def render_digest_html(digest: Dict[str, Any]) -> str:
    """渲染成自包含 HTML 报告（可双击打开、可归档）。"""
    title, body = _render_body_parts(digest)
    return _html_shell(title, body)


def _render_body_parts(
    digest: Dict[str, Any], *, include_title: bool = True
) -> tuple[str, str]:
    """返回 ``(标题, 正文片段)``。

    ``include_title=False`` 供内嵌页面用：页面自己有 ``<h2>``，正文再带一个
    ``<h1>`` 就成了双标题。
    """
    title = f"今日新闻消化 · {digest.get('generated_at_text', '')}"

    if not digest.get("available"):
        body = (
            '<div class="empty">'
            f'<div class="empty-title">暂无可以消化的新闻</div>'
            f'<div class="empty-reason">{_esc(digest.get("reason") or "")}</div>'
            "</div>"
        )
        return title, body

    stats = digest.get("stats") or {}
    focus = digest.get("focus") or {}
    groups = digest.get("groups") or {}
    labels = digest.get("group_labels") or GROUP_LABELS

    holdings = list(collapse_identifiers(
        focus.get("holdings_labels") or focus.get("holdings") or []
    ))
    watchlist = list(collapse_identifiers(
        focus.get("watchlist_labels") or focus.get("watchlist") or []
    ))
    narratives = [str(x) for x in (focus.get("narratives") or [])]
    themes = [str(t.get("name", "")) for t in (focus.get("themes") or []) if isinstance(t, dict)]

    # 持仓与自选**分开展示**：自己的钱 vs 在看的票，合并会稀释前者
    focus_chips = ""
    if holdings:
        focus_chips += _chips("持仓", holdings, "#1d4ed8")
    if watchlist:
        focus_chips += _chips("自选", watchlist, "#0891b2")
    if narratives:
        focus_chips += _chips("关注叙事", narratives, "#7c3aed")
    if themes:
        focus_chips += _chips("关注主题", themes, "#0f766e")

    degraded = focus.get("degraded") or []
    degraded_html = ""
    if degraded:
        items_html = "".join(f"<li>{_esc(d)}</li>" for d in degraded)
        degraded_html = (
            '<div class="degraded">'
            '<div class="degraded-title">⚠️ 焦点信息有降级（如实记录，未静默）</div>'
            f'<ul>{items_html}</ul>'
            "</div>"
        )

    sections = ""
    for group in GROUP_ORDER:
        rows = groups.get(group) or []
        if not rows:
            continue
        cards = "".join(_render_row_html(row, group) for row in rows)
        sections += (
            f'<section class="group">'
            f'<h2>{_esc(labels.get(group, group))}'
            f'<span class="count">{len(rows)}</span></h2>'
            f'<div class="cards">{cards}</div>'
            f"</section>"
        )

    tiers = (digest.get("tier_config") or {}).get("bands") or {}
    tier_line = ""
    if tiers:
        bits = " &gt; ".join(
            f'{label} {tiers[key]["floor"]:.2f}–{tiers[key]["ceiling"]:.2f}'
            for key, label in (("holding", "持仓"), ("theme", "叙事"),
                               ("watchlist", "自选"), ("macro", "外部"))
            if key in tiers
        )
        tier_line = (
            '<div class="tierline">排序口径（区间严格不重叠，持仓数学上必然优先）：'
            f"{bits}</div>"
        )

    pierced = int(stats.get("pierced", 0))
    summary = (
        '<div class="stats">'
        f'<div class="stat"><div class="stat-v">{stats.get("scanned", 0)}</div>'
        f'<div class="stat-k">扫描</div></div>'
        f'<div class="stat"><div class="stat-v">{stats.get("holding", 0)}</div>'
        f'<div class="stat-k">持仓</div></div>'
        f'<div class="stat"><div class="stat-v">{stats.get("theme", 0)}</div>'
        f'<div class="stat-k">关注叙事</div></div>'
        f'<div class="stat"><div class="stat-v">{stats.get("macro", 0)}</div>'
        f'<div class="stat-k">外部要闻</div></div>'
        + (
            f'<div class="stat stat-warn"><div class="stat-v">{pierced}</div>'
            f'<div class="stat-k">风险穿透</div></div>'
            if pierced else ""
        )
        + "</div>"
    )

    merged = int(stats.get("merged", 0) or 0)
    header = (
        '<div class="head">'
        + (f'<h1>{_esc(title)}</h1>' if include_title else "")
        + f'<div class="sub">窗口 {digest.get("window_hours", 24)} 小时 · '
        f'去重后 {stats.get("deduped", 0)} 条'
        + (f'（合并 {merged} 条重复）' if merged else "")
        + f' · 精选 {stats.get("shown", 0)} 条 · {_esc(digest.get("generated_at_text", ""))}'
        "</div>"
        "</div>"
    )

    body = header + summary + tier_line
    if focus_chips:
        body += f'<div class="focus">{focus_chips}</div>'
    body += degraded_html
    body += sections or '<div class="empty"><div class="empty-title">没有命中任何关注项</div></div>'

    return title, body


def _render_row_html(row: Dict[str, Any], group: str) -> str:
    hits = list(row.get("holding_hits") or []) + list(row.get("watchlist_hits") or [])
    reasons = row.get("reasons") or []
    theme_hits = list(row.get("theme_hits") or []) + list(row.get("narrative_hits") or [])

    rel = float(row.get("relevance") or 0.0)
    bar = int(round(rel * 100))
    bar_color = {"holding": "#1d4ed8", "theme": "#7c3aed"}.get(group, "#94a3b8")
    if row.get("pierced"):
        bar_color = "#dc2626"

    tag_html = "".join(
        f'<span class="tag tag-star">{_esc(h)}</span>' for h in hits
    ) + "".join(f'<span class="tag tag-theme">{_esc(t)}</span>' for t in theme_hits)
    if row.get("pierced"):
        tag_html = '<span class="tag tag-pierce">⚠️ 风险穿透</span>' + tag_html

    url = row.get("url") or ""
    title_html = (
        f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(row.get("title", ""))}</a>'
        if url
        else _esc(row.get("title", ""))
    )
    # 同一事件被折叠了几条：只显示条数，不显示语言/来源（呈现口径）
    dup_html = (
        f'<span class="dup">{_esc(format_dup_suffix(row.get("dup_count")).strip())}</span>'
        if int(row.get("dup_count") or 1) > 1
        else ""
    )

    return (
        '<div class="card">'
        f'<div class="card-top"><div class="card-title">{title_html}{dup_html}</div>'
        f'<div class="card-rel" title="相关度">{rel:.2f}</div></div>'
        f'<div class="bar"><i style="width:{bar}%;background:{bar_color}"></i></div>'
        f'<div class="meta">{_esc(row.get("datetime", ""))} · {_esc(row.get("source", ""))}'
        f' · 基础分 {float(row.get("base_importance") or 0):.2f}</div>'
        + (f'<div class="tags">{tag_html}</div>' if tag_html else "")
        + (
            '<div class="reasons">'
            + "".join(f"<span>· {_esc(r)}</span>" for r in reasons)
            + "</div>"
            if reasons
            else ""
        )
        + "</div>"
    )


def _chips(label: str, values: List[str], color: str) -> str:
    inner = "".join(
        f'<span class="chip" style="border-color:{color};color:{color}">{_esc(v)}</span>'
        for v in values[:12]
    )
    return f'<div class="chip-row"><span class="chip-label">{_esc(label)}</span>{inner}</div>'


_FOOT = "Naja · 新闻消化器 · 数据源：已评分新闻池（deep 级）"

#: 报告的全部样式。**每条规则都挂在 ``.nj-digest`` 下**——同一份 CSS 既用于
#: 归档文件（整页），也用于 ``/news`` 页面内嵌（PyWebIO 片段）。不作用域化的话，
#: 内嵌时 ``body{padding:28px}``、``*{box-sizing}`` 会污染站点其它页面。
_NJ_CSS = """
.nj-digest{max-width:880px;margin:0 auto;color:#0f172a;line-height:1.5;
  font-family:-apple-system,"PingFang SC","Helvetica Neue",sans-serif}
.nj-digest *{box-sizing:border-box}
.nj-digest .head h1{font-size:20px;font-weight:600;margin:0 0 6px}
.nj-digest .head .sub{font-size:12px;color:#64748b}
.nj-digest .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(88px,1fr));
  gap:10px;margin:18px 0}
.nj-digest .stat{background:#fff;border:1px solid #e2e8f0;border-radius:10px;
  padding:12px;text-align:center}
.nj-digest .stat-v{font-size:20px;font-weight:600}
.nj-digest .stat-k{font-size:11px;color:#64748b;margin-top:2px}
.nj-digest .stat-warn{border-color:#fecaca;background:#fef2f2}
.nj-digest .stat-warn .stat-v{color:#b91c1c}
.nj-digest .tierline{font-size:11px;color:#64748b;background:#f8fafc;border:1px solid #e2e8f0;
  border-radius:8px;padding:8px 12px;margin:-8px 0 14px}
.nj-digest .focus{background:#fff;border:1px solid #e2e8f0;border-radius:10px;
  padding:12px;margin-bottom:14px}
.nj-digest .chip-row{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:4px 0}
.nj-digest .chip-label{font-size:11px;color:#64748b;min-width:70px}
.nj-digest .chip{font-size:11px;border:1px solid;border-radius:10px;padding:1px 8px;
  background:#fff}
.nj-digest .degraded{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;
  padding:12px;margin-bottom:14px;font-size:12px;color:#92400e}
.nj-digest .degraded-title{font-weight:600;margin-bottom:4px}
.nj-digest .degraded ul{margin:0;padding-left:18px}
.nj-digest .group{margin-top:22px}
.nj-digest .group h2{font-size:14px;font-weight:600;margin:0 0 10px;display:flex;
  align-items:center;gap:8px}
.nj-digest .group h2 .count{font-size:11px;color:#64748b;background:#e2e8f0;
  border-radius:8px;padding:1px 7px;font-weight:400}
.nj-digest .cards{display:flex;flex-direction:column;gap:10px}
.nj-digest .card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;
  padding:12px 14px}
.nj-digest .card-top{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.nj-digest .card-title{font-size:13px;font-weight:500;line-height:1.5}
.nj-digest .card-title a{color:#0f172a;text-decoration:none}
.nj-digest .card-title a:hover{text-decoration:underline}
.nj-digest .dup{font-size:10px;color:#64748b;background:#f1f5f9;border-radius:6px;
  padding:0 5px;margin-left:6px}
.nj-digest .card-rel{font-size:13px;font-weight:600;color:#334155;flex:none}
.nj-digest .bar{height:3px;background:#f1f5f9;border-radius:2px;margin:8px 0 6px;
  overflow:hidden}
.nj-digest .bar i{display:block;height:100%;border-radius:2px}
.nj-digest .meta{font-size:11px;color:#94a3b8}
.nj-digest .tags{margin-top:6px;display:flex;flex-wrap:wrap;gap:5px}
.nj-digest .tag{font-size:10px;border-radius:8px;padding:1px 7px;background:#f1f5f9;
  color:#475569}
.nj-digest .tag-star{background:#dbeafe;color:#1d4ed8}
.nj-digest .tag-theme{background:#ede9fe;color:#6d28d9}
.nj-digest .tag-pierce{background:#fee2e2;color:#b91c1c;font-weight:600}
.nj-digest .reasons{margin-top:6px;display:flex;flex-direction:column;gap:2px}
.nj-digest .reasons span{font-size:11px;color:#64748b}
.nj-digest .empty{background:#fff;border:1px solid #e2e8f0;border-radius:10px;
  padding:28px;text-align:center}
.nj-digest .empty-title{font-size:14px;font-weight:500;color:#334155}
.nj-digest .empty-reason{font-size:12px;color:#94a3b8;margin-top:6px}
.nj-digest .foot{margin-top:26px;font-size:11px;color:#94a3b8;text-align:center}
/* 内嵌模式（/news）：报告是「浅灰纸 + 白卡片」的两层设计，站点正文是白底。
   不铺纸底的话，卡片和白背景同色、只剩 1px 描边，整页糊成一片，
   分组标题与卡片的分界也没了（第一版漏了这层，实测才看出来）。 */
.nj-digest-embed{background:#f1f5f9;border-radius:14px;padding:22px 20px 26px}
"""


def _html_shell(title: str, body: str) -> str:
    """完整 HTML 文档（归档文件 / 双击打开）。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>
 body{{margin:0;padding:28px 20px 60px;background:#f1f5f9}}
{_NJ_CSS}
</style></head><body><div class="nj-digest">{body}
<div class="foot">{_FOOT}</div>
</div></body></html>"""


def render_digest_fragment(digest: Dict[str, Any]) -> str:
    """渲染成**可内嵌片段**（``/news`` 页面用）。

    样式与正文拼成**一个字符串一次性**交给 ``put_html``：PyWebIO 把每次调用当
    独立 DOM 片段插入，拆成两次调用会让 ``<style>`` 与内容分家（本仓踩过，
    ``news/ui.py`` 头部有记）。
    """
    _title, body = _render_body_parts(digest, include_title=False)
    return (
        f"<style>{_NJ_CSS}</style>"
        + f'<div class="nj-digest nj-digest-embed">{body}</div>'
    )


# ── 落盘 + 定时任务入口 ─────────────────────────────────────────────────


def write_daily_digest(
    digest: Optional[Dict[str, Any]] = None,
    *,
    out_dir: Optional[Path] = None,
) -> Path:
    """把报告写成 ``<out_dir>/YYYY-MM-DD.html``，另存一份最新快照 json。"""
    digest = digest if digest is not None else build_digest()
    directory = Path(out_dir) if out_dir is not None else DIGEST_DIR
    directory.mkdir(parents=True, exist_ok=True)

    day = datetime.fromtimestamp(digest.get("generated_at") or time.time()).strftime("%Y-%m-%d")
    html_path = directory / f"{day}.html"
    html_path.write_text(render_digest_html(digest), encoding="utf-8")

    try:
        (directory / f"{day}.json").write_text(
            json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (directory / "latest.json").write_text(
            json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:  # pragma: no cover - 防御
        log.warning("[NewsDigest] 报告 JSON 落盘失败: %s", e)

    return html_path


def run_daily_digest(*, push: bool = False, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """定时任务入口：生成 + 落盘（可选推送到手机）。失败不抛，返回 dict。"""
    try:
        digest = build_digest()
        path = write_daily_digest(digest, out_dir=out_dir)
        stats = digest.get("stats") or {}

        result: Dict[str, Any] = {
            "success": True,
            "available": digest.get("available"),
            "report_path": str(path),
            "scanned": stats.get("scanned", 0),
            "shown": stats.get("shown", 0),
            "holding": stats.get("holding", 0),
        }

        if push and digest.get("available"):
            result["pushed"] = _push_via_imessage(render_digest_text(digest))

        log.info(
            "[NewsDigest] 日报已生成：扫描 %s → 精选 %s（持仓 %s）→ %s",
            result["scanned"], result["shown"], result["holding"], path,
        )
        return result
    except Exception as e:
        log.error("[NewsDigest] 日报生成失败: %s", e)
        return {"success": False, "error": str(e)}


def _push_via_imessage(text: str) -> bool:
    """复用 ai_daily_report 的推送方式（尽力而为，失败只记日志）。"""
    phone = os.environ.get("NAJA_NEWS_DIGEST_PHONE", "+86XXXXXXXXXXX")
    try:
        import subprocess

        escaped = text.replace('"', '\\"')
        cmd = [
            "osascript", "-e",
            'tell application "Messages" to send '
            f'"{escaped}" to buddy "{phone}"',
        ]
        subprocess.run(cmd, capture_output=True, timeout=15)
        return True
    except Exception as e:
        log.warning("[NewsDigest] iMessage 推送失败: %s", e)
        return False


__all__ = [
    "build_digest",
    "get_news_digest_summary",
    "render_digest_text",
    "render_digest_html",
    "render_digest_fragment",
    "write_daily_digest",
    "run_daily_digest",
    "DIGEST_DIR",
]
