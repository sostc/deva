"""Insight 组件 —— 洞察（思考层）

2026-10-19 重排：这一块原本占整页 36%（3,369px），是三件事叠出来的——

1. 卡片最顶上直接铺 `system_architecture` 的 1,228px 静态说明文档，把运行时
   洞察推到 2,400px 以下 → 改成默认收起的折叠块；
2. 5 条 LLM 反思全部展开、每条约 300px 长文 → 只展开最新 1 条，其余折叠成一行；
3. Top 洞察 5 条 + 最近洞察 8 条都全量铺开 → 分页式折叠（展示 3 条，其余收起）。

另外移除了「输入雷达信号 + 热点事件 → LLM反思 → …」这类设计说明行，
运行时页面只显示运行时信息；静态说明统一去 /cognition_glossary 或折叠块里看。
"""

import ast
import html

from pywebio.output import put_html

from deva.naja.infra.ui.ui_style import format_timestamp

from .layout import card, fold


def _get_insight_engine():
    """获取 InsightEngine（AppContainer 优先，SR fallback 仅开发用）"""
    from deva.naja.application.container import get_app_container
    container = get_app_container()
    if container is not None:
        ie = getattr(container, 'insight_engine', None)
        if ie is not None:
            return ie
    from deva.naja.register import SR
    return SR('insight_engine')


def _get_insight_pool():
    """获取 InsightPool（AppContainer 优先，SR fallback 仅开发用）"""
    from deva.naja.application.container import get_app_container
    container = get_app_container()
    if container is not None:
        ip = getattr(container, 'insight_pool', None)
        if ip is not None:
            return ip
    from deva.naja.register import SR
    return SR('insight_pool')


def _get_stock_display_info(code: str) -> str:
    """股票代码 → 可读展示名（失败时回落原始代码）"""
    try:
        from ....dictionary.stocks import get_stock_name
        name = get_stock_name(code)
        if name:
            return f"{name}({code})"
    except Exception:
        pass
    return str(code)


def _plain_summary(raw, limit: int) -> str:
    """把 summary（dict / dict 字符串 / 纯文本）压成一段可安全插入 HTML 的纯文本。"""
    text = ""
    if isinstance(raw, dict):
        try:
            from ....cognition.insight.engine import Insight
            text = Insight._format_dict_for_display(raw, limit)
        except Exception:
            text = str(raw)
    elif isinstance(raw, str) and raw.startswith('{') and raw.endswith('}'):
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, dict):
                from ....cognition.insight.engine import Insight
                text = Insight._format_dict_for_display(parsed, limit)
            else:
                text = raw
        except Exception:
            text = raw
    else:
        text = str(raw or '')

    text = text or '-'
    if len(text) > limit:
        text = text[:limit] + '…'
    return html.escape(text)


def _narrative_label(item) -> str:
    """叙事条目可能是 str，也可能是 {'narrative','stage','trend',...} 字典。

    直接 f-string 一个 dict 会把整段 repr 打上屏（`{'narrative': '外汇与美元',
    'stage': '高潮', ...}`），这里统一收敛成 `名称·阶段`。
    """
    if isinstance(item, dict):
        name = (item.get('narrative') or item.get('name')
                or item.get('theme') or item.get('label') or '')
        stage = item.get('stage') or ''
        name = str(name).strip()
        if not name:
            return ''
        return f"{name}·{stage}" if stage else name
    return str(item)


def _first_clause(label: str) -> str:
    """取首个分句（到第一个逗号/句号为止）。

    用来判断「是不是在讲同一件事」：LLM 重述同一局面时，往往**首句同义改写、
    后面整段换掉**，首句才是稳定的语义锚点。
    """
    for sep in ("，", ",", "。", "；", ";"):
        pos = label.find(sep)
        if pos > 0:
            return label[:pos]
    return label


def _compact_themes(items, limit: int = 4, ratio: float = 0.72, width: int = 34):
    """把「主题长句」压缩成可读的短标签。

    `insight_engine.get_attention_hints()` 的 narratives 取的是 `item['theme']`，
    而 theme 是 LLM 生成的一整句（如「美林时钟过热维持但流动性信号持续缺失，
    AI叙事再创新高强化芯片与外汇叙事高位分化，商品>债券>美元>股票结构暂维持…」）。
    它只按**全等**去重，于是同一叙事的多个快照会全部留下，上屏就是 4 行几乎
    一样的句子，占掉 190px 却零信息增量。

    ❗**前缀折叠不够用**（第一版就是按前 12 字判同，实测漏掉一半）：
    LLM 重述同一局面时会**同义换词**，比如

        「美林时钟过热**延续**但流动性信号持续缺失，…」
        「美林时钟过热**持续**但流动性信号**仍**缺失，…」

    只差第 7 个字，前 12 字键不同 → 两条都留下。改成对**首句**算字符相似度，
    超过 ``ratio`` 就判同一件事（保留最长的一条）。选首句而不是整句，是因为
    同一叙事的后半段会被整段换掉（AI叙事高位强化 → AI绝对主导但边际减速）。

    折叠是展示层处理，不改数据源 —— 上游仍是完整句子，别处要用还能拿到。
    """
    from difflib import SequenceMatcher

    kept: list = []          # [(首句, 完整标签)]
    for raw in items or []:
        label = _narrative_label(raw).strip()
        if not label:
            continue
        head = _first_clause(label)
        dup_at = None
        for i, (kept_head, _kept_label) in enumerate(kept):
            if SequenceMatcher(None, head, kept_head).ratio() >= ratio:
                dup_at = i
                break
        if dup_at is None:
            kept.append((head, label))
        elif len(label) > len(kept[dup_at][1]):
            kept[dup_at] = (kept[dup_at][0], label)   # 留信息最全的那条

    out = []
    for _head, label in kept[:limit]:
        out.append(label if len(label) <= width else label[:width] + '…')
    return out


def _symbol_label(item) -> str:
    """标的条目可能是 str / {'symbol'|'code'|'name': ...} / (code, score) 元组。"""
    if isinstance(item, dict):
        for key in ('symbol', 'code', 'name', 'stock'):
            if item.get(key):
                return str(item[key])
        return ''
    if isinstance(item, (tuple, list)) and item:
        return str(item[0])
    return str(item)


def _tile(label: str, value: str, sub: str, color: str) -> str:
    sub_html = f'<div style="font-size: 11px; color: #64748b; margin-top: 3px;">{sub}</div>' if sub else ""
    return f"""
    <div style="background: {color}14; border: 1px solid {color}33; padding: 11px 16px; border-radius: 10px;">
        <div style="font-size: 11px; color: #64748b; margin-bottom: 3px;">{label}</div>
        <div style="font-size: 22px; font-weight: 700; color: {color}; line-height: 1.2;">{value}</div>
        {sub_html}
    </div>
    """


def _reflection_block(refl) -> str:
    """一条 LLM 反思的完整展示块。"""
    theme = html.escape(str(refl.get('theme', '-')))
    summary = _plain_summary(refl.get('summary', ''), 400)
    narratives = refl.get('narratives', []) or []
    symbols = refl.get('symbols', [])[:6]
    confidence = float(refl.get('confidence', 0.5))
    actionability = float(refl.get('actionability', 0.5))
    novelty = float(refl.get('novelty', 0.5))
    liquidity = html.escape(str(refl.get('liquidity_structure', '')))
    ts = format_timestamp(float(refl.get('ts', 0)))

    nar_tags = "".join(
        f'<span class="cog-pill" style="background: rgba(249,115,22,.15); color: #fb923c;">{html.escape(_narrative_label(n))}</span> '
        for n in narratives[:4] if _narrative_label(n)
    )
    sym_tags = "".join(
        f'<span class="cog-pill" style="background: rgba(20,184,166,.15); color: #2dd4bf;">{html.escape(_symbol_label(s))}</span> '
        for s in symbols if _symbol_label(s)
    )
    liq_tag = (
        f'<span class="cog-pill" style="background: rgba(16,185,129,.15); color: #10b981;">💰 {liquidity}</span>'
        if liquidity else ""
    )

    tail_rows = ""
    if nar_tags or sym_tags or liq_tag:
        tail_rows = f'<div style="margin-top: 8px; line-height: 2;">{liq_tag} {nar_tags} {sym_tags}</div>'

    return f"""
    <div style="background: rgba(255,255,255,.02); border-radius: 8px; padding: 12px 14px;
                border-left: 3px solid #0ea5e9;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; gap: 10px; margin-bottom: 6px;">
            <div style="font-size: 13px; font-weight: 600; color: #e2e8f0;">{theme}</div>
            <div style="font-size: 11px; color: #475569; white-space: nowrap;">{ts}</div>
        </div>
        <div style="font-size: 12px; color: #94a3b8; line-height: 1.6;">{summary}</div>
        {tail_rows}
        <div style="display: flex; gap: 12px; margin-top: 8px; font-size: 11px; color: #64748b;">
            <span>置信 <b style="color: #60a5fa;">{confidence:.2f}</b></span>
            <span>可行动 <b style="color: #fb923c;">{actionability:.2f}</b></span>
            <span>新颖度 <b style="color: #4ade80;">{novelty:.2f}</b></span>
        </div>
    </div>
    """


def _reflection_rollup(refl) -> str:
    """折叠态的反思摘要：一行一个，主题 + 时间 + 结论首句。"""
    theme = html.escape(str(refl.get('theme', '-')))
    head = _plain_summary(refl.get('summary', ''), 56)
    ts = format_timestamp(float(refl.get('ts', 0)))
    return f"""
    <div style="display: flex; gap: 10px; align-items: baseline; padding: 5px 0;
                border-bottom: 1px solid rgba(255,255,255,.04);">
        <span style="font-size: 11px; color: #64748b; flex-shrink: 0;">{ts[-14:]}</span>
        <span style="font-size: 11px; color: #94a3b8; flex-shrink: 0;">{theme}</span>
        <span style="font-size: 11px; color: #475569; overflow: hidden; text-overflow: ellipsis;
                     white-space: nowrap;">{head}</span>
    </div>
    """


def _top_insight_block(item) -> str:
    theme = html.escape(str(item.get('theme', '-')))
    summary = _plain_summary(item.get('summary', ''), 150)
    score = float(item.get('user_score', 0))
    confidence = float(item.get('confidence', 0))
    actionability = float(item.get('actionability', 0))
    novelty = float(item.get('novelty', 0))
    system_attention = float(item.get('system_attention', 0))
    symbols = ', '.join(html.escape(_symbol_label(s)) for s in item.get('symbols', [])[:4] if _symbol_label(s)) or '-'
    blocks = ', '.join(html.escape(str(s)) for s in (item.get('blocks') or [])[:4]) or '-'
    ts = format_timestamp(float(item.get('ts', 0)))
    source = str(item.get('source', ''))
    signal_type = str(item.get('signal_type', ''))

    score_color = '#f87171' if score > 0.7 else ('#fb923c' if score > 0.5 else '#60a5fa')

    badge = ""
    if 'feedback_experiment' in source or signal_type == 'experiment_feedback_summary':
        badge = '<span class="cog-pill" style="background: rgba(34,197,94,.2); color: #4ade80;">📊 实验反馈</span>'
    elif 'llm_reflection' in source or signal_type == 'llm_reflection':
        badge = '<span class="cog-pill" style="background: rgba(14,165,233,.2); color: #0ea5e9;">🤖 LLM反思</span>'
    elif 'bandit_learning' in signal_type:
        badge = '<span class="cog-pill" style="background: rgba(168,85,247,.2); color: #a855f7;">🎯 Bandit</span>'

    return f"""
    <div style="background: rgba(255,255,255,.02); border-radius: 8px; padding: 10px 12px;
                margin-bottom: 6px; border-left: 3px solid {score_color};">
        <div style="display: flex; justify-content: space-between; align-items: baseline; gap: 10px;">
            <div style="font-size: 12px; font-weight: 600; color: #cbd5e1;">{theme} {badge}</div>
            <div style="font-size: 11px; color: #475569; white-space: nowrap;">{ts}</div>
        </div>
        <div style="font-size: 11px; color: #94a3b8; margin: 5px 0; line-height: 1.55;">{summary}</div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 5px;">标的 {symbols} · 题材 {blocks}</div>
        <div style="display: flex; flex-wrap: wrap; gap: 4px;">
            <span class="cog-pill" style="background: rgba(20,184,166,.15); color: #14b8a6;">分 <b>{score:.2f}</b></span>
            <span class="cog-pill" style="background: rgba(96,165,250,.15); color: #60a5fa;">热度 <b>{system_attention:.2f}</b></span>
            <span class="cog-pill" style="background: rgba(168,85,247,.15); color: #a855f7;">置信 <b>{confidence:.2f}</b></span>
            <span class="cog-pill" style="background: rgba(249,115,22,.15); color: #fb923c;">可行动 <b>{actionability:.2f}</b></span>
            <span class="cog-pill" style="background: rgba(34,197,94,.15); color: #4ade80;">新颖 <b>{novelty:.2f}</b></span>
        </div>
    </div>
    """


def _recent_insight_row(item) -> str:
    theme = html.escape(str(item.get('theme', '-')))
    summary = _plain_summary(item.get('summary', ''), 60)
    score = float(item.get('user_score', 0))
    ts = format_timestamp(float(item.get('ts', 0)))
    dot = '#f87171' if score > 0.7 else ('#fb923c' if score > 0.5 else '#60a5fa')
    return f"""
    <div style="display: flex; align-items: center; gap: 10px; padding: 6px 8px;
                background: rgba(255,255,255,.02); border-radius: 6px; margin-bottom: 4px;">
        <span style="width: 6px; height: 6px; border-radius: 50%; background: {dot}; flex-shrink: 0;"></span>
        <div style="flex: 1; min-width: 0;">
            <div style="font-size: 11px; font-weight: 600; color: #94a3b8; overflow: hidden;
                        text-overflow: ellipsis; white-space: nowrap;">{theme}</div>
            <div style="font-size: 11px; color: #475569; overflow: hidden;
                        text-overflow: ellipsis; white-space: nowrap;">{summary}</div>
        </div>
        <div style="font-size: 11px; color: #475569; flex-shrink: 0;">{ts[-8:]}</div>
    </div>
    """


def render_insight(ui):
    from deva.naja.cognition.ui.system_architecture import get_cognition_architecture_doc

    from ....cognition.insight import get_llm_reflection_engine

    insight_engine = _get_insight_engine()
    insight_pool = _get_insight_pool()
    llm_reflection = get_llm_reflection_engine()
    llm_stats = llm_reflection.get_stats()
    recent_reflections = llm_reflection.get_recent_reflections(limit=5)

    if not insight_engine or not insight_pool:
        return

    pool_stats = insight_pool.get_stats()
    top_insights = insight_pool.get_top_insights(limit=5) or []
    recent_insights = insight_pool.get_recent_insights(limit=10) or []
    attention_hints = insight_engine.get_attention_hints() if insight_engine else {}

    last_reflection_ts = llm_stats.get('last_success_ts', 0)
    last_reflection_str = format_timestamp(last_reflection_ts) if last_reflection_ts > 0 else '从未'

    tiles = "".join([
        _tile("洞察总数", str(pool_stats.get('total_insights', 0)), "", "#14b8a6"),
        _tile("活跃主题", str(pool_stats.get('active_themes', 0)),
              f"平均分 {pool_stats.get('avg_user_score', 0):.3f}", "#a855f7"),
        _tile("LLM 反思", str(llm_stats['reflections_count']), f"上次 {last_reflection_str}", "#0ea5e9"),
    ])

    sections = []
    sections.append(f'<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;">{tiles}</div>')

    # ── 热点建议（只保留有数据时的紧凑三列）──
    top_symbols = dict(sorted(attention_hints.get('symbols', {}).items(), key=lambda x: x[1], reverse=True)[:5])
    top_blocks = dict(sorted(attention_hints.get('blocks', {}).items(), key=lambda x: x[1], reverse=True)[:5])
    narratives = attention_hints.get('narratives', [])[:5]

    if top_symbols or top_blocks or narratives:
        def _bars(data, color, fmt):
            return "".join([
                f"""
                <div style="margin-bottom: 6px;">
                    <div style="display: flex; justify-content: space-between; font-size: 11px;
                                color: #64748b; margin-bottom: 2px;">
                        <span>{fmt(k)}</span><span style="color: {color}; font-weight: 600;">{v:.2f}</span>
                    </div>
                    <div style="height: 3px; background: rgba(255,255,255,.08); border-radius: 2px;">
                        <div style="width: {min(100, int(v * 100))}%; height: 100%;
                                    background: {color}; border-radius: 2px;"></div>
                    </div>
                </div>
                """
                for k, v in data.items()
            ])

        cols = []
        if top_symbols:
            cols.append(f'<div><div style="font-size: 11px; color: #14b8a6; font-weight: 600; margin-bottom: 6px;">📈 标的</div>{_bars(top_symbols, "#14b8a6", lambda k: html.escape(_get_stock_display_info(k)))}</div>')
        if top_blocks:
            cols.append(f'<div><div style="font-size: 11px; color: #a855f7; font-weight: 600; margin-bottom: 6px;">🏭 题材</div>{_bars(top_blocks, "#a855f7", html.escape)}</div>')
        if narratives:
            labels = _compact_themes(narratives)
            tags = " ".join(
                f'<span class="cog-pill" style="background: rgba(249,115,22,.15); color: #fb923c;">{html.escape(lab)}</span>'
                for lab in labels
            )
            cols.append(f'<div><div style="font-size: 11px; color: #fb923c; font-weight: 600; margin-bottom: 6px;">💭 叙事</div><div style="line-height: 2;">{tags}</div></div>')

        sections.append(f"""
        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.06);">
            <div style="font-size: 11px; color: #64748b; font-weight: 600; margin-bottom: 8px;">🎯 热点建议（基于洞察计算）</div>
            <div style="display: grid; grid-template-columns: repeat({len(cols)}, 1fr); gap: 16px;">{"".join(cols)}</div>
        </div>
        """)

    # ── LLM 反思：最新 1 条展开，其余折叠 ──
    if recent_reflections:
        latest = recent_reflections[0]
        rest = recent_reflections[1:]
        block = (
            '<div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.06);">'
            '<div style="font-size: 11px; color: #0ea5e9; font-weight: 600; margin-bottom: 8px;">🤖 LLM 深度反思</div>'
            + _reflection_block(latest)
            + '</div>'
        )
        if rest:
            block += fold(
                f"更早的 {len(rest)} 条反思",
                "".join(_reflection_rollup(r) for r in rest),
                meta="按时间倒序",
            )
        sections.append(block)

    # ── Top 洞察：展示 3 条，其余折叠 ──
    if top_insights:
        shown = top_insights[:1]
        rest = top_insights[1:]
        block = (
            '<div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.06);">'
            '<div style="font-size: 11px; color: #64748b; font-weight: 600; margin-bottom: 8px;">🏆 Top 洞察</div>'
            + "".join(_top_insight_block(i) for i in shown)
            + '</div>'
        )
        if rest:
            block += fold(f"其余 {len(rest)} 条 Top 洞察",
                          "".join(_top_insight_block(i) for i in rest))
        sections.append(block)

    # ── 最近洞察：整体折叠 ──
    if recent_insights:
        sections.append(fold(
            f"最近洞察 · {len(recent_insights)} 条",
            "".join(_recent_insight_row(i) for i in recent_insights[:8]),
            meta="按时间倒序",
        ))

    # ── 静态说明：默认收起 ──
    sections.append(fold(
        "🏗️ 认知层工作原理（静态说明）",
        get_cognition_architecture_doc(),
        meta="不随运行变化",
    ))

    sections.append(fold(
        "🧩 认知层能力说明",
        f"""
        <div style="font-size: 11px; color: #64748b; line-height: 1.9;">
            <div><b style="color: #f59e0b;">📡 雷达层 → 认知层：</b>接收雷达事件（异常、漂移、模式检测）</div>
            <div><b style="color: #14b8a6;">📝 新闻舆情策略 → 认知层：</b>处理新闻语义 + 叙事追踪</div>
            <div><b style="color: #a855f7;">💾 记忆分层：</b>短期(1000条) → 中期(5000条, score≥0.6) → 长期反思</div>
            <div><b style="color: #60a5fa;">🤖 LLM反思：</b>每 {int(llm_stats['interval_seconds'])} 秒触发一次</div>
            <div><b style="color: #fb923c;">👁️ 热点建议：</b>基于信号计算标的/题材权重，反馈给注意力调度</div>
            <div><b style="color: #4ade80;">📊 评分体系：</b>user_score + system_attention + confidence + actionability + novelty</div>
        </div>
        """,
    ))

    put_html(card(
        title="洞察（思考层）",
        icon="💡",
        meta=f"LLM 反思 <b>{llm_stats['reflections_count']}</b> 次 · 上次 <b>{last_reflection_str}</b>",
        body="".join(sections),
    ))
