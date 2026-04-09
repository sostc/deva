"""
Insight 组件
"""

import time
from ....common.ui_style import format_timestamp
from deva.naja.register import SR


def _get_stock_display_info(code: str) -> str:
    try:
        from ....dictionary.stock.stock import Stock
        from ....dictionary.tongdaxin_blocks import get_stock_blocks
        name = Stock.get_name(code)
        blocks = get_stock_blocks(code)
        block_str = ",".join(blocks[:2]) if blocks else ""
        return f"{name}({block_str})" if block_str else name
    except Exception:
        return code


def _get_data_sources():
    return [
        {"name": "金十数据", "type": "news", "icon": "📡"},
        {"name": "BlockAttention", "type": "market", "icon": "📊"},
        {"name": "CognitiveSignalBus", "type": "internal", "icon": "🧠"},
    ]


def _calc_source_counts(insights):
    source_counts = {}
    for i in insights:
        src = i.get('source', 'unknown')
        source_counts[src] = source_counts.get(src, 0) + 1
    return source_counts, len(source_counts)


def render_insight(ui):
    from deva.naja.cognition.system_architecture import get_cognition_architecture_doc
    from pywebio.output import put_html
    put_html(get_cognition_architecture_doc())

    from ....cognition.insight import get_llm_reflection_engine

    insight_engine = SR('insight_engine')
    insight_pool = SR('insight_pool')
    llm_reflection = get_llm_reflection_engine()
    llm_stats = llm_reflection.get_stats()
    recent_reflections = llm_reflection.get_recent_reflections(limit=5)

    if not insight_engine or not insight_pool:
        return

    pool_stats = insight_pool.get_stats()
    top_insights = insight_pool.get_top_insights(limit=5)
    recent_insights = insight_pool.get_recent_insights(limit=10)
    insight_summary = insight_engine.get_summary() if insight_engine else {}
    attention_hints = insight_engine.get_attention_hints() if insight_engine else {}

    last_reflection_ts = llm_stats.get('last_success_ts', 0)
    last_reflection_str = format_timestamp(last_reflection_ts) if last_reflection_ts > 0 else '从未'
    next_reflection_in = max(0, int(llm_stats['interval_seconds'] - (time.time() - llm_stats['last_run_ts']))) if llm_stats['last_run_ts'] > 0 else int(llm_stats['interval_seconds'])

    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <div style="font-size: 13px; font-weight: 600; color: #14b8a6;">
                💡 洞察（思考层）
            </div>
            <div style="font-size: 10px; color: #475569;">
                🤖 LLM反思: {llm_stats['reflections_count']}次 | 上次: {last_reflection_str}
            </div>
        </div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
            输入雷达信号 + 注意力事件 → LLM反思 → 洞察结论与建议
        </div>
    </div>
    """)

    put_html(f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 12px;">
        <div style="background: rgba(20, 184, 166, 0.15); border: 1px solid rgba(20, 184, 166, 0.3); padding: 14px 16px; border-radius: 10px;">
            <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">洞察总数</div>
            <div style="font-size: 24px; font-weight: 700; color: #14b8a6;">{pool_stats.get('total_insights', 0)}</div>
        </div>
        <div style="background: rgba(168, 85, 247, 0.12); border: 1px solid rgba(168, 85, 247, 0.25); padding: 14px 16px; border-radius: 10px;">
            <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">活跃主题</div>
            <div style="font-size: 24px; font-weight: 700; color: #a855f7;">{pool_stats.get('active_themes', 0)}</div>
            <div style="font-size: 10px; color: #64748b; margin-top: 4px;">平均分 <b style="color: #a855f7;">{pool_stats.get('avg_user_score', 0):.3f}</b></div>
        </div>
        <div style="background: rgba(14, 165, 233, 0.12); border: 1px solid rgba(14, 165, 233, 0.25); padding: 14px 16px; border-radius: 10px;">
            <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">LLM反思</div>
            <div style="font-size: 24px; font-weight: 700; color: #0ea5e9;">{llm_stats['reflections_count']}</div>
            <div style="font-size: 10px; color: #64748b; margin-top: 4px;">下次约 <b style="color: #0ea5e9;">{next_reflection_in}</b>s</div>
        </div>
    </div>
    """)

    top_symbols = dict(sorted(attention_hints.get('symbols', {}).items(), key=lambda x: x[1], reverse=True)[:5])
    top_blocks = dict(sorted(attention_hints.get('blocks', {}).items(), key=lambda x: x[1], reverse=True)[:5])
    narratives = attention_hints.get('narratives', [])[:5]

    if top_symbols or top_blocks or narratives:
        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="font-size: 12px; font-weight: 600; color: #64748b; margin-bottom: 10px;">
                🎯 注意力建议（基于洞察计算）
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;">
        """)

        if top_symbols:
            symbol_bars = "".join([
                f'<div style="margin-bottom: 8px;"><div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 2px;"><span>{_get_stock_display_info(sym)}</span><span style="color: #14b8a6; font-weight: 600;">{score:.2f}</span></div><div style="height: 4px; background: rgba(255,255,255,0.08); border-radius: 2px;"><div style="width: {min(100, int(score * 100))}%; height: 100%; background: linear-gradient(90deg, #14b8a6, #2dd4bf); border-radius: 2px;"></div></div></div>'
                for sym, score in top_symbols.items()
            ])
            put_html(f'<div style="background: rgba(255,255,255,0.02); padding: 10px; border-radius: 8px;"><div style="font-size: 11px; font-weight: 600; color: #14b8a6; margin-bottom: 8px;">📈 标的</div>{symbol_bars}</div>')

        if top_blocks:
            block_bars = "".join([
                f'<div style="margin-bottom: 8px;"><div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 2px;"><span>{sec}</span><span style="color: #a855f7; font-weight: 600;">{score:.2f}</span></div><div style="height: 4px; background: rgba(255,255,255,0.08); border-radius: 2px;"><div style="width: {min(100, int(score * 100))}%; height: 100%; background: linear-gradient(90deg, #a855f7, #c084fc); border-radius: 2px;"></div></div></div>'
                for sec, score in top_blocks.items()
            ])
            put_html(f'<div style="background: rgba(255,255,255,0.02); padding: 10px; border-radius: 8px;"><div style="font-size: 11px; font-weight: 600; color: #a855f7; margin-bottom: 8px;">🏭 板块</div>{block_bars}</div>')

        if narratives:
            narrative_tags = " ".join([f'<span style="display: inline-block; padding: 3px 8px; background: rgba(249,115,22,0.15); color: #fb923c; border-radius: 4px; font-size: 10px; margin: 2px;">{nar}</span>' for nar in narratives])
            put_html(f'<div style="background: rgba(255,255,255,0.02); padding: 10px; border-radius: 8px;"><div style="font-size: 11px; font-weight: 600; color: #fb923c; margin-bottom: 8px;">💭 叙事</div><div>{narrative_tags}</div></div>')

        put_html('</div></div>')

    if recent_reflections:
        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(14,165,233,0.08);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(14,165,233,0.2);
        ">
            <div style="font-size: 12px; font-weight: 600; color: #0ea5e9; margin-bottom: 10px;">
                🤖 LLM 反思（深度市场分析）
            </div>
        """)
        for refl in recent_reflections:
            theme = refl.get('theme', '-')
            summary = refl.get('summary', '')
            narratives = refl.get('narratives', [])
            symbols = refl.get('symbols', [])[:5]
            confidence = float(refl.get('confidence', 0.5))
            actionability = float(refl.get('actionability', 0.5))
            novelty = float(refl.get('novelty', 0.5))
            liquidity_structure = refl.get('liquidity_structure', '')
            ts = format_timestamp(float(refl.get('ts', 0)))

            narrative_tags = ''.join([
                f'<span style="display: inline-block; padding: 2px 6px; background: rgba(249,115,22,0.15); color: #fb923c; border-radius: 4px; font-size: 9px; margin-right: 4px;">{n}</span>'
                for n in narratives[:4]
            ]) if narratives else ''

            liquidity_badge = ''
            if liquidity_structure:
                liquidity_badge = f'<span style="display: inline-block; padding: 2px 8px; background: rgba(16,185,129,0.15); color: #10b981; border-radius: 4px; font-size: 9px; margin-right: 4px;">💰 {liquidity_structure}</span>'

            put_html(f"""
            <div style="background: rgba(255,255,255,0.03); border-radius: 8px; padding: 12px; margin-bottom: 8px; border-left: 3px solid #0ea5e9;">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 6px;">
                    <div style="font-size: 13px; font-weight: 600; color: #e2e8f0;">{theme}</div>
                    <div style="font-size: 10px; color: #475569;">{ts}</div>
                </div>
                <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px; line-height: 1.5;">{summary}</div>
                {liquidity_badge}
                {narrative_tags}
                <div style="display: flex; gap: 8px; margin-top: 6px;">
                    <span style="font-size: 9px; color: #64748b;">置信 <b style="color: #60a5fa;">{confidence:.2f}</b></span>
                    <span style="font-size: 9px; color: #64748b;">可行动 <b style="color: #fb923c;">{actionability:.2f}</b></span>
                    <span style="font-size: 9px; color: #64748b;">新颖度 <b style="color: #4ade80;">{novelty:.2f}</b></span>
                </div>
            </div>
            """)
        put_html('</div>')

    DATA_SOURCES = _get_data_sources()
    source_counts, _ = _calc_source_counts(recent_insights)

    attention_shift_insights = [i for i in recent_insights if i.get('signal_type') == 'attention_shift']
    if attention_shift_insights:
        put_html("""
        <div style="
            margin-bottom: 12px;
            background: linear-gradient(135deg, rgba(254,240,138,0.1), rgba(253,224,71,0.05));
            border: 1px solid rgba(245,158,11,0.3);
            border-radius: 12px;
            padding: 14px 18px;
        ">
            <div style="font-size: 12px; font-weight: 600; color: #f59e0b; margin-bottom: 10px;">
                🔄 热点切换监测
            </div>
        """)
        for item in attention_shift_insights[:5]:
            theme = item.get('theme', '-')
            summary_raw = item.get('summary', '')
            if isinstance(summary_raw, dict):
                from ....cognition.insight.engine import Insight
                summary = Insight._format_dict_for_display(summary_raw, 120)
            elif isinstance(summary_raw, str) and summary_raw.startswith('{') and summary_raw.endswith('}'):
                try:
                    import ast
                    parsed = ast.literal_eval(summary_raw)
                    if isinstance(parsed, dict):
                        from ....cognition.insight.engine import Insight
                        summary = Insight._format_dict_for_display(parsed, 120)
                    else:
                        summary = summary_raw[:120]
                except Exception:
                    summary = summary_raw[:120]
            else:
                summary = summary_raw[:120] if summary_raw else '-'
            summary = summary.replace('{', '{{').replace('}', '}}').replace('<', '&lt;').replace('>', '&gt;')

            payload = item.get('payload', {})
            removed_symbols = payload.get('removed_symbols', [])
            added_symbols = payload.get('added_symbols', [])
            duration = payload.get('duration', '')
            shift_type = payload.get('shift_type', '')

            ts = format_timestamp(float(item.get('ts', 0)))
            score = float(item.get('user_score', 0))

            removed_html = ''
            if removed_symbols:
                removed_list = [f"{s}({n})" for s, n in removed_symbols[:5]]
                removed_html = f'<div style="font-size: 10px; color: #dc2626; margin-bottom: 4px;">📤 退出: {" | ".join(removed_list)}</div>'

            added_html = ''
            if added_symbols:
                added_list = [f"{s}({n})" for s, n in added_symbols[:5]]
                added_html = f'<div style="font-size: 10px; color: #16a34a; margin-bottom: 4px;">📥 新进: {" | ".join(added_list)}</div>'

            put_html(f"""
            <div style="background: rgba(255,255,255,0.03); border-radius: 8px; padding: 12px; margin-bottom: 8px; border-left: 3px solid #f59e0b;">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 6px;">
                    <div style="font-size: 12px; font-weight: 600; color: #fbbf24;">{theme}</div>
                    <div style="font-size: 10px; color: #475569;">{ts}</div>
                </div>
                {removed_html}
                {added_html}
                <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">{summary}</div>
                <div style="display: flex; gap: 8px;">
                    <span style="font-size: 9px; color: #64748b;">类型: <b style="color: #fbbf24;">{shift_type}</b></span>
                    <span style="font-size: 9px; color: #64748b;">评分 <b style="color: #f59e0b;">{score:.2f}</b></span>
                </div>
            </div>
            """)
        put_html('</div>')

    if top_insights:
        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="font-size: 12px; font-weight: 600; color: #64748b; margin-bottom: 10px;">
                🏆 Top 洞察
            </div>
        """)
        for item in top_insights:
            theme = item.get('theme', '-')
            summary_raw = item.get('summary', '')
            if isinstance(summary_raw, dict):
                from ....cognition.insight.engine import Insight
                summary = Insight._format_dict_for_display(summary_raw, 150)
            elif isinstance(summary_raw, str) and summary_raw.startswith('{') and summary_raw.endswith('}'):
                try:
                    import ast
                    parsed = ast.literal_eval(summary_raw)
                    if isinstance(parsed, dict):
                        from ....cognition.insight.engine import Insight
                        summary = Insight._format_dict_for_display(parsed, 150)
                    else:
                        summary = summary_raw[:150] + ('…' if len(summary_raw) > 150 else '')
                except Exception:
                    summary = summary_raw[:150] + ('…' if len(summary_raw) > 150 else '')
            else:
                summary = summary_raw[:150] + ('…' if len(summary_raw) > 150 else '') if summary_raw else '-'
            summary = summary.replace('{', '{{').replace('}', '}}').replace('<', '&lt;').replace('>', '&gt;')
            score = float(item.get('user_score', 0))
            system_attention = float(item.get('system_attention', 0))
            confidence = float(item.get('confidence', 0))
            actionability = float(item.get('actionability', 0))
            novelty = float(item.get('novelty', 0))
            symbols = ', '.join(str(s) for s in item.get('symbols', [])[:4]) or '-'
            blocks = ', '.join(str(s) for s in (item.get('blocks') or item.get('blocks') or [])[:4]) or '-'
            ts = format_timestamp(float(item.get('ts', 0)))
            source = item.get('source', '')
            signal_type = item.get('signal_type', '')

            score_color = '#f87171' if score > 0.7 else ('#fb923c' if score > 0.5 else '#60a5fa')

            source_badge = ''
            if 'feedback_experiment' in source or signal_type == 'experiment_feedback_summary':
                source_badge = '<span style="padding: 2px 6px; border-radius: 4px; background: rgba(34,197,94,0.2); color: #4ade80; font-size: 9px; margin-left: 6px;">📊 实验反馈</span>'
            elif 'llm_reflection' in source or signal_type == 'llm_reflection':
                source_badge = '<span style="padding: 2px 6px; border-radius: 4px; background: rgba(14,165,233,0.2); color: #0ea5e9; font-size: 9px; margin-left: 6px;">🤖 LLM反思</span>'
            elif 'bandit_learning' in signal_type:
                source_badge = '<span style="padding: 2px 6px; border-radius: 4px; background: rgba(168,85,247,0.2); color: #a855f7; font-size: 9px; margin-left: 6px;">🎯 Bandit学习</span>'

            put_html(f"""
            <div style="background: rgba(255,255,255,0.02); border-radius: 8px; padding: 12px; margin-bottom: 8px; border-left: 3px solid {score_color};">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 6px;">
                    <div style="font-size: 13px; font-weight: 600; color: #cbd5e1;">{theme}{source_badge}</div>
                    <div style="font-size: 10px; color: #475569;">{ts}</div>
                </div>
                <div style="font-size: 12px; color: #94a3b8; margin-bottom: 6px; line-height: 1.4;">{summary}</div>
                <div style="font-size: 10px; color: #475569; margin-bottom: 6px;">
                    标的: {symbols} | 板块: {blocks}
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 4px;">
                    <span style="padding: 2px 6px; border-radius: 4px; background: rgba(20,184,166,0.15); color: #14b8a6; font-size: 10px;">用户分 <b>{score:.2f}</b></span>
                    <span style="padding: 2px 6px; border-radius: 4px; background: rgba(96,165,250,0.15); color: #60a5fa; font-size: 10px;">系统注意力 <b>{system_attention:.2f}</b></span>
                    <span style="padding: 2px 6px; border-radius: 4px; background: rgba(168,85,247,0.15); color: #a855f7; font-size: 10px;">置信度 <b>{confidence:.2f}</b></span>
                    <span style="padding: 2px 6px; border-radius: 4px; background: rgba(249,115,22,0.15); color: #fb923c; font-size: 10px;">可行动 <b>{actionability:.2f}</b></span>
                    <span style="padding: 2px 6px; border-radius: 4px; background: rgba(34,197,94,0.15); color: #4ade80; font-size: 10px;">新颖度 <b>{novelty:.2f}</b></span>
                </div>
            </div>
            """)
        put_html('</div>')

    if recent_insights:
        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="font-size: 12px; font-weight: 600; color: #64748b; margin-bottom: 10px;">
                📋 最近洞察
            </div>
        """)
        for item in recent_insights[:8]:
            theme = item.get('theme', '-')
            summary_raw = item.get('summary', '')
            signal_type = str(item.get('signal_type', item.get('event_type', '')))
            payload = item.get('payload', {})

            if signal_type == 'narrative_stage_change':
                narrative = payload.get('narrative')
                if not narrative:
                    narrative = theme.replace('🌊 叙事信号: ', '').replace('🌊 ', '') if '叙事信号' in theme or theme.startswith('🌊 ') else theme
                stage = payload.get('stage', '-')
                attention_score = float(payload.get('attention_score', 0))
                trend = float(payload.get('trend', 0))
                keywords = payload.get('keywords', [])[:3]
                linked_blocks = (payload.get('linked_blocks') or payload.get('linked_blocks') or [])[:2]

                trend_icon = '📈' if trend > 0 else '📉' if trend < 0 else '➡️'
                stage_color = '#4ade80' if stage == '高潮' else ('#a855f7' if stage == '扩散' else ('#fb923c' if stage == '消退' else '#60a5fa'))

                kw_tags = ''.join([f'<span style="display: inline-block; padding: 1px 4px; background: rgba(255,255,255,0.08); color: #94a3b8; border-radius: 3px; font-size: 9px; margin-right: 2px;">{kw}</span>' for kw in keywords]) if keywords else ''
                block_tags = ''.join([f'<span style="display: inline-block; padding: 1px 4px; background: rgba(249,115,22,0.15); color: #fb923c; border-radius: 3px; font-size: 9px; margin-right: 2px;">{blk}</span>' for blk in linked_blocks]) if linked_blocks else ''

                summary = f'<span style="color: {stage_color}; font-weight: 600;">叙事{narrative}进入</span><span style="padding: 1px 6px; background: {stage_color}; color: #0f172a; border-radius: 4px; font-size: 10px; font-weight: 600; margin: 0 4px;">{stage}</span>{trend_icon} 注意力{int(attention_score*100)}% {kw_tags} {block_tags}'
                summary = summary.replace('{', '{{').replace('}', '}}')
                score_color = stage_color
            elif signal_type.startswith('narrative_'):
                narrative = payload.get('narrative')
                if not narrative:
                    narrative = theme.replace('🌊 叙事信号: ', '').replace('🌊 ', '') if '叙事信号' in theme or theme.startswith('🌊 ') else theme
                attention_score = float(payload.get('attention_score', 0))
                keywords = payload.get('keywords', [])[:2]
                kw_tags = ''.join([f'<span style="display: inline-block; padding: 1px 4px; background: rgba(255,255,255,0.08); color: #94a3b8; border-radius: 3px; font-size: 9px; margin-right: 2px;">{kw}</span>' for kw in keywords]) if keywords else ''
                summary = f'🌊 {narrative} 注意力{int(attention_score*100)}% {kw_tags}'
                summary = summary.replace('{', '{{').replace('}', '}}')
                score_color = '#60a5fa'
            elif isinstance(summary_raw, dict):
                from ....cognition.insight.engine import Insight
                summary = Insight._format_dict_for_display(summary_raw, 60)
                summary = summary.replace('{', '{{').replace('}', '}}').replace('<', '&lt;').replace('>', '&gt;')
            elif isinstance(summary_raw, str) and summary_raw.startswith('{') and summary_raw.endswith('}'):
                try:
                    import ast
                    parsed = ast.literal_eval(summary_raw)
                    if isinstance(parsed, dict):
                        from ....cognition.insight.engine import Insight
                        summary = Insight._format_dict_for_display(parsed, 60)
                        summary = summary.replace('{', '{{').replace('}', '}}').replace('<', '&lt;').replace('>', '&gt;')
                    else:
                        summary = summary_raw[:60]
                        summary = summary.replace('<', '&lt;').replace('>', '&gt;')
                except Exception:
                    summary = summary_raw[:60]
                    summary = summary.replace('<', '&lt;').replace('>', '&gt;')
            else:
                summary = summary_raw[:60] if summary_raw else '-'
                summary = summary.replace('<', '&lt;').replace('>', '&gt;')
            score = float(item.get('user_score', 0))
            ts = format_timestamp(float(item.get('ts', 0)))

            score_color = '#f87171' if score > 0.7 else ('#fb923c' if score > 0.5 else '#60a5fa')

            put_html(f"""
            <div style="display: flex; align-items: center; gap: 10px; padding: 8px; background: rgba(255,255,255,0.02); border-radius: 6px; margin-bottom: 4px;">
                <div style="width: 6px; height: 6px; border-radius: 50%; background: {score_color}; flex-shrink: 0;"></div>
                <div style="flex: 1; min-width: 0;">
                    <div style="font-size: 11px; font-weight: 600; color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{theme}</div>
                    <div style="font-size: 10px; color: #475569; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{summary}</div>
                </div>
                <div style="font-size: 10px; color: #475569; flex-shrink: 0;">{ts}</div>
            </div>
            """)
        put_html('</div>')

    insight_logic = f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 12px; font-weight: 600; color: #64748b; margin-bottom: 8px;">
            🧩 认知层能力说明
        </div>
        <div style="font-size: 11px; color: #475569; line-height: 1.8;">
            <div style="margin-bottom: 6px;"><b style="color: #f59e0b;">📡 雷达层 → 认知层：</b>接收雷达事件（异常、漂移、模式检测）</div>
            <div style="margin-bottom: 6px;"><b style="color: #14b8a6;">📝 新闻舆情策略 → 认知层：</b>处理新闻语义 + 叙事追踪</div>
            <div style="margin-bottom: 6px;"><b style="color: #a855f7;">💾 记忆分层：</b>短期(1000条) → 中期(5000条, score≥0.6) → 长期反思(LLM反思)</div>
            <div style="margin-bottom: 6px;"><b style="color: #60a5fa;">🤖 LLM反思：</b>每{int(llm_stats['interval_seconds'])}秒触发一次，对近期信号进行深度总结</div>
            <div style="margin-bottom: 6px;"><b style="color: #fb923c;">👁️ 注意力建议：</b>基于信号计算标的/板块权重，反馈给注意力调度</div>
            <div><b style="color: #4ade80;">📊 评分体系：</b>user_score + system_attention + confidence + actionability + novelty</div>
        </div>
    </div>
    """
    put_html(insight_logic)
