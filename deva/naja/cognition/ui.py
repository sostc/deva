"""
认知系统 Web UI
风格与全局一致，紧凑布局，用户关注内容优先
"""

from datetime import datetime, timedelta
from typing import List, Dict
import math
import time

from pywebio.output import *
from pywebio.input import *
from pywebio.pin import *
from pywebio.session import run_js, set_env

from .engine import get_cognition_engine
from .core import AttentionScorer
from ..page_help import render_help_collapse


def _get_stock_display_info(code: str) -> str:
    """获取股票的显示信息：名称和板块"""
    try:
        from ..dictionary.stock.stock import Stock
        from ..dictionary.tongdaxin_blocks import get_stock_blocks
        name = Stock.get_name(code)
        blocks = get_stock_blocks(code)
        block_str = "|".join(blocks[:2]) if blocks else "-"
        return f"{name} ({block_str})" if blocks else name
    except Exception:
        return code


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def get_running_cognition_engine():
    """获取运行中的认知引擎实例（单例）"""
    try:
        return get_cognition_engine()
    except Exception as e:
        print(f"[CognitionUI] 获取认知引擎失败: {e}")
        return None


def create_nav_menu():
    """创建导航菜单 - 使用统一模块"""
    from ..common.ui_theme import get_nav_menu_js
    js_code = get_nav_menu_js()
    run_js(js_code)


def apply_global_styles():
    """应用全局样式 - 使用统一模块"""
    from ..common.ui_theme import get_global_styles
    from pywebio.output import put_html
    put_html(get_global_styles())


class CognitionUI:
    """认知系统 UI"""

    def __init__(self):
        self.engine = get_running_cognition_engine()

    def render(self):
        """渲染主页面"""
        set_env(title="Naja - 认知", output_animation=False)
        apply_global_styles()

        from ..common.ui_theme import get_nav_menu_js
        nav_js = get_nav_menu_js()
        switch_theme_js = """
            window.switchTheme = function(name) {
                document.cookie = 'naja-theme=' + name + '; path=/; max-age=31536000';
                document.body.style.opacity = '0';
                setTimeout(function() { location.reload(); }, 150);
            };
        """

        run_js("setTimeout(function(){" + nav_js + "}, 50);")
        run_js(switch_theme_js)

        put_html('<div class="container">')

        self._render_cognition_summary()
        self._render_narrative_lifecycle()
        self._render_insight_section()
        self._render_storage()
        self._render_control_panel()
        self._render_help()

        put_html('</div>')

    def _render_insight_section(self):
        """渲染洞察模块 - 展示思考层的逻辑和产物 - 深色主题风格"""
        from .insight import get_insight_engine, get_insight_pool, get_llm_reflection_engine

        insight_engine = get_insight_engine()
        insight_pool = get_insight_pool()
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
        last_reflection_str = _fmt_ts(last_reflection_ts) if last_reflection_ts > 0 else '从未'
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
        top_sectors = dict(sorted(attention_hints.get('sectors', {}).items(), key=lambda x: x[1], reverse=True)[:5])
        narratives = attention_hints.get('narratives', [])[:5]

        if top_symbols or top_sectors or narratives:
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

            if top_sectors:
                sector_bars = "".join([
                    f'<div style="margin-bottom: 8px;"><div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 2px;"><span>{sec}</span><span style="color: #a855f7; font-weight: 600;">{score:.2f}</span></div><div style="height: 4px; background: rgba(255,255,255,0.08); border-radius: 2px;"><div style="width: {min(100, int(score * 100))}%; height: 100%; background: linear-gradient(90deg, #a855f7, #c084fc); border-radius: 2px;"></div></div></div>'
                    for sec, score in top_sectors.items()
                ])
                put_html(f'<div style="background: rgba(255,255,255,0.02); padding: 10px; border-radius: 8px;"><div style="font-size: 11px; font-weight: 600; color: #a855f7; margin-bottom: 8px;">🏭 板块</div>{sector_bars}</div>')

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
                ts = _fmt_ts(float(refl.get('ts', 0)))

                narrative_tags = ''.join([
                    f'<span style="display: inline-block; padding: 2px 6px; background: rgba(249,115,22,0.15); color: #fb923c; border-radius: 4px; font-size: 9px; margin-right: 4px;">{n}</span>'
                    for n in narratives[:4]
                ]) if narratives else ''

                put_html(f"""
                <div style="background: rgba(255,255,255,0.03); border-radius: 8px; padding: 12px; margin-bottom: 8px; border-left: 3px solid #0ea5e9;">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 6px;">
                        <div style="font-size: 13px; font-weight: 600; color: #e2e8f0;">{theme}</div>
                        <div style="font-size: 10px; color: #475569;">{ts}</div>
                    </div>
                    <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px; line-height: 1.5;">{summary}</div>
                    {narrative_tags}
                    <div style="display: flex; gap: 8px; margin-top: 6px;">
                        <span style="font-size: 9px; color: #64748b;">置信 <b style="color: #60a5fa;">{confidence:.2f}</b></span>
                        <span style="font-size: 9px; color: #64748b;">可行动 <b style="color: #fb923c;">{actionability:.2f}</b></span>
                        <span style="font-size: 9px; color: #64748b;">新颖度 <b style="color: #4ade80;">{novelty:.2f}</b></span>
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
                summary = item.get('summary', '')
                score = float(item.get('user_score', 0))
                system_attention = float(item.get('system_attention', 0))
                confidence = float(item.get('confidence', 0))
                actionability = float(item.get('actionability', 0))
                novelty = float(item.get('novelty', 0))
                symbols = ', '.join(item.get('symbols', [])[:4]) or '-'
                sectors = ', '.join(item.get('sectors', [])[:4]) or '-'
                ts = _fmt_ts(float(item.get('ts', 0)))

                score_color = '#f87171' if score > 0.7 else ('#fb923c' if score > 0.5 else '#60a5fa')

                put_html(f"""
                <div style="background: rgba(255,255,255,0.02); border-radius: 8px; padding: 12px; margin-bottom: 8px; border-left: 3px solid {score_color};">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 6px;">
                        <div style="font-size: 13px; font-weight: 600; color: #cbd5e1;">{theme}</div>
                        <div style="font-size: 10px; color: #475569;">{ts}</div>
                    </div>
                    <div style="font-size: 12px; color: #94a3b8; margin-bottom: 6px; line-height: 1.4;">{summary}</div>
                    <div style="font-size: 10px; color: #475569; margin-bottom: 6px;">
                        标的: {symbols} | 板块: {sectors}
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
                summary = item.get('summary', '')[:60]
                score = float(item.get('user_score', 0))
                ts = _fmt_ts(float(item.get('ts', 0)))

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

    def _render_cognition_summary(self):
        """渲染认知中枢 - 酷炫深色风格头部"""
        from ..radar.engine import get_radar_engine
        from ..attention.ui_components.common import get_attention_report
        from .insight import get_insight_engine, get_insight_pool

        radar = get_radar_engine()
        radar_summary = radar.summarize(window_seconds=600) if radar else {}
        radar_events = radar_summary.get("event_count", 0)

        attention_report = get_attention_report() or {}
        global_attention = float(attention_report.get("global_attention", 0))
        activity = float(attention_report.get("activity", 0))

        insight_engine = get_insight_engine()
        insight_pool = get_insight_pool()
        insight_summary = insight_engine.get_summary() if insight_engine else {}
        insight_stats = insight_pool.get_stats() if insight_pool else {"total_insights": 0}

        memory_report = self.engine.get_memory_report() if self.engine else {}
        stats = memory_report.get('stats', {})
        total_events = stats.get('total_events', 0)
        filtered_events = stats.get('filtered_events', 0)
        memory_layers = memory_report.get('memory_layers', {})
        short_size = memory_layers.get('short', {}).get('size', 0)
        mid_size = memory_layers.get('mid', {}).get('size', 0)

        engine_status = "🟢 运行中" if self.engine else "🔴 已停止"
        attention_icon = "🔥" if global_attention >= 0.6 else ("📊" if global_attention >= 0.3 else "💤")
        attention_color = "#dc2626" if global_attention >= 0.6 else ("#ca8a04" if global_attention >= 0.3 else "#64748b")
        attention_level = "焦点集中" if global_attention >= 0.6 else ("温和" if global_attention >= 0.3 else "低迷")

        self._put_html(f"""
        <div style="
            margin-bottom: 12px;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            border-radius: 14px;
            padding: 16px 20px;
            box-shadow: 0 4px 20px rgba(15, 23, 42, 0.25), inset 0 1px 0 rgba(255,255,255,0.05);
            border: 1px solid #334155;
            position: relative;
            overflow: hidden;
        ">
            <div style="position: absolute; top: 0; right: 0; width: 200px; height: 100%; background: radial-gradient(ellipse at top right, #14b8a608 0%, transparent 60%); pointer-events: none;"></div>
            <div style="display: flex; justify-content: space-between; align-items: flex-start; position: relative;">
                <div>
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
                        <span style="font-size: 24px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));">🧠</span>
                        <div>
                            <div style="font-size: 16px; font-weight: 700; color: #f1f5f9;">认知中枢 <span style="font-size: 13px; font-weight: 400; color: #94a3b8;">认知层</span></div>
                            <div style="font-size: 11px; color: #14b8a6; margin-top: 2px;">理解语义、形成记忆、生成洞察</div>
                        </div>
                    </div>
                    <div style="font-size: 12px; color: #64748b; margin-top: 6px;">输入：雷达事件 + 新闻舆情 ｜ 输出：洞察建议 → 注意力调度</div>
                </div>
                <div style="display: flex; gap: 12px; text-align: center;">
                    <div style="background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">📡 雷达</div>
                        <div style="font-size: 18px; font-weight: 700; color: #f59e0b;">{radar_events}</div>
                        <div style="font-size: 10px; color: #94a3b8;">10分钟事件</div>
                    </div>
                    <div style="background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 80px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">👁️ 注意力</div>
                        <div style="font-size: 18px; font-weight: 700; color: {attention_color};">{attention_icon} {global_attention:.2f}</div>
                        <div style="font-size: 10px; color: {attention_color}; opacity: 0.8;">{attention_level}</div>
                    </div>
                    <div style="background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 100px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">💡 洞察</div>
                        <div style="font-size: 18px; font-weight: 700; color: #14b8a6;">{insight_stats.get('total_insights', 0)}</div>
                        <div style="font-size: 10px; color: #94a3b8;">活跃主题 {insight_stats.get('active_themes', 0)}</div>
                    </div>
                    <div style="background: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 10px; padding: 8px 14px; min-width: 100px;">
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">记忆</div>
                        <div style="font-size: 14px; font-weight: 700; color: #a855f7;">{short_size}/{memory_layers.get('short', {}).get('capacity', 0)}</div>
                        <div style="font-size: 10px; color: #94a3b8;">短/中期 {mid_size}</div>
                    </div>
                </div>
            </div>
            <div style="display: flex; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #334155;">
                <div style="flex: 1; padding: 6px 10px; background: rgba(245, 158, 11, 0.15); border-radius: 6px; text-align: center;">
                    <span style="font-size: 11px; color: #fcd34d;">📥 接收</span>
                    <span style="font-size: 12px; font-weight: 600; color: #f59e0b; margin-left: 4px;">{total_events + filtered_events}</span>
                </div>
                <div style="flex: 1; padding: 6px 10px; background: rgba(239, 68, 68, 0.15); border-radius: 6px; text-align: center;">
                    <span style="font-size: 11px; color: #fca5a5;">🚫 过滤</span>
                    <span style="font-size: 12px; font-weight: 600; color: #ef4444; margin-left: 4px;">{filtered_events}</span>
                </div>
                <div style="flex: 1; padding: 6px 10px; background: rgba(59, 130, 246, 0.15); border-radius: 6px; text-align: center;">
                    <span style="font-size: 11px; color: #93c5fd;">⚡ 短期</span>
                    <span style="font-size: 12px; font-weight: 600; color: #3b82f6; margin-left: 4px;">{short_size}</span>
                </div>
                <div style="flex: 1; padding: 6px 10px; background: rgba(16, 185, 129, 0.15); border-radius: 6px; text-align: center;">
                    <span style="font-size: 11px; color: #6ee7b7;">📦 中期</span>
                    <span style="font-size: 12px; font-weight: 600; color: #10b981; margin-left: 4px;">{mid_size}</span>
                </div>
            </div>
        </div>
        """)

        top_insights = (insight_pool.get_top_insights(limit=3) if insight_pool else []) or []
        recent_radar = (radar_summary.get("events", []) or [])[:3]

        if not top_insights and not recent_radar:
            self._put_html(render_empty_state("暂无认知数据，请确保雷达和洞察引擎正在运行"))
            return

        radar_lines = "".join(
            [f"<li>{e.get('message','-')[:80]}</li>" for e in recent_radar]
        ) or "<li>暂无雷达事件</li>"
        insight_lines = "".join(
            [f"<li>{i.get('summary','-')[:80]}</li>" for i in top_insights]
        ) or "<li>暂无洞察</li>"

        self._put_html(
            f"""
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin-bottom: 16px;">
                <div style="
                    background: rgba(255,255,255,0.03);
                    border-radius: 12px;
                    padding: 14px 18px;
                    border: 1px solid rgba(255,255,255,0.08);
                ">
                    <div style="font-size: 13px; font-weight: 600; color: #f59e0b; margin-bottom: 8px;">📡 雷达快照</div>
                    <div style="font-size: 11px; color: #475569; margin-bottom: 12px;">
                        最近 10 分钟雷达检测到的异常事件
                    </div>
                    <ol style="padding-left: 16px; margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.6;">{radar_lines}</ol>
                </div>
                <div style="
                    background: rgba(255,255,255,0.03);
                    border-radius: 12px;
                    padding: 14px 18px;
                    border: 1px solid rgba(255,255,255,0.08);
                ">
                    <div style="font-size: 13px; font-weight: 600; color: #14b8a6; margin-bottom: 8px;">💡 洞察摘要</div>
                    <ol style="padding-left: 16px; margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.6;">{insight_lines}</ol>
                </div>
            </div>
            """,
        )

    def _put_html(self, html: str):
        put_html(html)

    def _render_control_panel(self):
        """渲染控制面板 - 底部样式"""
        put_html('''
        <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.08); display: flex; gap: 8px;">
        ''')
        put_button("🔄 刷新", onclick=self._refresh_data, color="secondary", small=True)
        put_button("📊 完整报告", onclick=self._generate_report, color="secondary", small=True)
        put_button("🧹 清空", onclick=self._clear_storage, color="secondary", small=True)
        put_html('</div>')

    def _render_narrative_lifecycle(self):
        """渲染叙事生命周期可视化 - 深色主题风格"""
        if not self.engine:
            return

        report = self.engine.get_memory_report()
        narratives_data = report.get('narratives', {})
        narrative_summary = narratives_data.get('summary', [])
        narrative_graph = narratives_data.get('graph', {})
        narrative_events = narratives_data.get('events', [])

        if not narrative_summary:
            return

        stage_colors = {
            '萌芽': '#60a5fa',
            '扩散': '#818cf8',
            '高潮': '#f87171',
            '消退': '#fb923c',
        }
        stage_order = ['萌芽', '扩散', '高潮', '消退']

        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="font-size: 13px; font-weight: 600; color: #60a5fa; margin-bottom: 4px;">
                🌊 叙事生命周期
            </div>
            <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
                叙事阶段：萌芽 → 扩散 → 高潮 → 消退
            </div>

            <div style="border-left: 2px solid rgba(96,165,250,0.3); padding-left: 12px; margin-bottom: 14px;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                    <span style="color: #60a5fa;">📋</span> 叙事列表
                </div>
        """)
        for nar in narrative_summary[:5]:
            name = nar.get('narrative', '未知')
            stage = nar.get('stage', '萌芽')
            attention = float(nar.get('attention_score', 0))
            trend = float(nar.get('trend', 0))
            recent_count = int(nar.get('recent_count', 0))
            keywords = nar.get('keywords', [])[:3]
            stage_idx = stage_order.index(stage) if stage in stage_order else 0
            stage_color = stage_colors.get(stage, '#60a5fa')

            trend_icon = '↑' if trend > 0 else ('↓' if trend < 0 else '→')
            trend_color = '#4ade80' if trend > 0 else ('#f87171' if trend < 0 else '#6b7280')

            bar_width = min(100, int(attention * 100))

            kw_tags = ''.join([
                f'<span style="display: inline-block; padding: 2px 6px; background: rgba(255,255,255,0.08); color: #94a3b8; border-radius: 4px; font-size: 10px; margin-right: 4px;">{kw}</span>'
                for kw in keywords
            ]) if keywords else ''

            put_html(f"""
            <div style="background: rgba(255,255,255,0.02); border-radius: 10px; padding: 12px; margin-bottom: 10px; border-left: 3px solid {stage_color};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div style="font-size: 13px; font-weight: 600; color: #cbd5e1;">{name}</div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="padding: 2px 8px; background: {stage_color}; color: #0f172a; border-radius: 4px; font-size: 10px; font-weight: 600;">{stage}</span>
                        <span style="font-size: 11px; color: {trend_color}; font-weight: 600;">{trend_icon} {abs(trend):.2f}</span>
                        <span style="font-size: 10px; color: #475569;">{recent_count}次/6h</span>
                    </div>
                </div>
                <div style="margin-bottom: 8px;">
                    <div style="display: flex; height: 6px; border-radius: 4px; overflow: hidden; gap: 2px;">
                        <div style="flex: {bar_width}; background: linear-gradient(90deg, {stage_color}, {stage_color}dd); border-radius: 4px 0 0 4px;"></div>
                        <div style="flex: {100 - bar_width}; background: rgba(255,255,255,0.1); border-radius: 0 4px 4px 0;"></div>
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-size: 10px; color: #475569;">注意力 <b style="color: {stage_color};">{attention:.2f}</b></div>
                    {kw_tags}
                </div>
            </div>
            """)
        put_html('</div>')

        if narrative_events:
            put_html("""
            <div style="margin-top: 14px; padding-top: 14px; border-top: 1px solid rgba(255,255,255,0.08);">
                <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 10px;">
                    <div style="width: 8px; height: 8px; border-radius: 2px; background: linear-gradient(135deg, #4ade80, #6ee7b7);"></div>
                    <div style="font-size: 11px; font-weight: 600; color: #4ade80;">📍 子模块：最近阶段变化</div>
                </div>
                <div style="border-left: 2px solid rgba(74,222,128,0.3); padding-left: 12px;">
            """)
            recent_events = narrative_events[-5:] if len(narrative_events) > 5 else narrative_events
            for evt in reversed(recent_events):
                evt_type = evt.get('event_type', '')
                evt_nar = evt.get('narrative', '')
                evt_stage = evt.get('stage', '')
                evt_ts = _fmt_ts(float(evt.get('timestamp', 0)))
                evt_color = '#4ade80' if 'stage_change' in evt_type else '#60a5fa'
                evt_icon = '🔄' if 'stage_change' in evt_type else '🔥'
                if 'stage_change' in evt_type:
                    evt_desc = f"{evt_nar} → {evt_stage}"
                else:
                    evt_desc = f"{evt_nar} 飙升"
                put_html(f"""
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 0; font-size: 11px;">
                    <span><span style="color: {evt_color};">{evt_icon}</span> {evt_desc}</span>
                    <span style="color: #475569;">{evt_ts}</span>
                </div>
                """)
            put_html('</div></div>')

        if narrative_graph.get('nodes') and narrative_graph.get('edges'):
            nodes = narrative_graph.get('nodes', [])
            edges = narrative_graph.get('edges', [])
            svg_html = self._render_narrative_svg(nodes, edges)
            put_html(f"""
            <div style="margin-top: 14px; padding-top: 14px; border-top: 1px solid rgba(255,255,255,0.08);">
                <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 10px;">
                    <div style="width: 8px; height: 8px; border-radius: 2px; background: linear-gradient(135deg, #818cf8, #a78bfa);"></div>
                    <div style="font-size: 11px; font-weight: 600; color: #818cf8;">🔗 叙事关联图</div>
                </div>
                <div style="display: flex; justify-content: center; padding: 8px; background: rgba(255,255,255,0.02); border-radius: 8px;">
                    {svg_html}
                </div>
            </div>
            """)

        put_html('</div>')

    def _render_narrative_svg(self, nodes: List[Dict], edges: List[Dict]) -> str:
        if not nodes:
            return '<div style="color:#64748b;font-size:11px;">暂无叙事数据</div>'

        width = 380
        height = 260
        center_x = width // 2
        center_y = height // 2
        radius = 90

        stage_colors = {
            '萌芽': '#60a5fa',
            '扩散': '#818cf8',
            '高潮': '#f87171',
            '消退': '#fb923c',
        }

        node_count = len(nodes)
        if node_count == 1:
            positions = [(center_x, center_y)]
        elif node_count <= 4:
            positions = []
            for i in range(node_count):
                angle = (2 * math.pi * i / node_count) - math.pi / 2
                x = center_x + radius * 0.6 * math.cos(angle)
                y = center_y + radius * 0.6 * math.sin(angle)
                positions.append((x, y))
            positions.extend([(center_x, center_y)] * (4 - node_count))
        else:
            positions = []
            for i in range(node_count):
                angle = (2 * math.pi * i / node_count) - math.pi / 2
                x = center_x + radius * math.cos(angle)
                y = center_y + radius * math.sin(angle)
                positions.append((x, y))

        node_map = {}
        for i, node in enumerate(nodes):
            node_map[node['id']] = i

        svg_parts = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']

        svg_parts.append(f'''
        <defs>
            <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="3" result="blur"/>
                <feMerge>
                    <feMergeNode in="blur"/>
                    <feMergeNode in="SourceGraphic"/>
                </feMerge>
            </filter>
            <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
                <feDropShadow dx="0" dy="2" stdDeviation="2" flood-opacity="0.4"/>
            </filter>
        </defs>
        ''')

        svg_parts.append(f'<rect width="{width}" height="{height}" fill="rgba(15,23,42,0.3)" rx="8"/>')

        for edge in edges:
            src = edge.get('source', '')
            tgt = edge.get('target', '')
            weight = float(edge.get('weight', 0))
            if src not in node_map or tgt not in node_map:
                continue

            src_idx = node_map[src]
            tgt_idx = node_map[tgt]
            x1, y1 = positions[src_idx]
            x2, y2 = positions[tgt_idx]

            opacity = 0.3 + weight * 0.5
            stroke_width = max(1, weight * 3)
            color = '#a78bfa'

            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2

            if node_count <= 4:
                ctrl_x = mid_x
                ctrl_y = mid_y - 15
            else:
                dist = math.sqrt((x2-x1)**2 + (y2-y1)**2)
                offset = 20 * (1 - dist / (2 * radius))
                ctrl_x = mid_x + offset
                ctrl_y = mid_y - offset

            svg_parts.append(
                f'<path d="M {x1:.1f} {y1:.1f} Q {ctrl_x:.1f} {ctrl_y:.1f} {x2:.1f} {y2:.1f}" '
                f'stroke="{color}" stroke-width="{stroke_width:.1f}" fill="none" opacity="{opacity:.2f}" stroke-linecap="round"/>'
            )

        for i, node in enumerate(nodes):
            x, y = positions[i]
            stage = node.get('stage', '萌芽')
            attention = float(node.get('attention_score', 0))
            node_color = stage_colors.get(stage, '#60a5fa')
            node_size = 28 + attention * 12

            svg_parts.append(f'''
            <circle cx="{x:.1f}" cy="{y:.1f}" r="{node_size:.1f}"
                fill="{node_color}" opacity="0.85" filter="url(#shadow)"/>
            <circle cx="{x:.1f}" cy="{y:.1f}" r="{node_size * 0.6:.1f}"
                fill="rgba(255,255,255,0.15)"/>
            ''')

            font_size = 9 if len(node['id']) > 3 else 10
            svg_parts.append(f'''
            <text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" dominant-baseline="central"
                fill="#f1f5f9" font-size="{font_size}" font-weight="600" font-family="system-ui">
                {node['id']}
            </text>
            ''')

            stage_text_x = x + node_size + 4
            stage_text_y = y - 6
            svg_parts.append(f'''
            <text x="{stage_text_x:.1f}" y="{stage_text_y:.1f}"
                fill="#94a3b8" font-size="8" font-family="system-ui">
                {stage}
            </text>
            ''')

        svg_parts.append('</svg>')
        return ''.join(svg_parts)

    def _render_stats_overview(self):
        """渲染统计概览"""
        if not self.engine:
            put_html(render_empty_state("认知引擎未初始化"))
            return

        report = self.engine.get_memory_report()
        stats = report['stats']
        topics = report.get('top_topics', [])

        total_events = stats.get('total_events', 0)
        hot_events = stats.get('high_attention_events', 0)
        topic_count = len(topics)

        gradient = "linear-gradient(135deg,#667eea,#764ba2)"

        put_html(f"""
        <div style="display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px;">
            <div style="flex: 1; min-width: 140px; background: {gradient}; padding: 16px 20px; border-radius: 12px; color: #fff; box-shadow: 0 4px 12px rgba(102,126,234,0.3);">
                <div style="font-size: 12px; opacity: 0.9; margin-bottom: 4px;">📖 记忆总量</div>
                <div style="font-size: 28px; font-weight: 700;">{total_events}</div>
            </div>
            <div style="flex: 1; min-width: 140px; background: linear-gradient(135deg,#ef4444,#dc2626); padding: 16px 20px; border-radius: 12px; color: #fff; box-shadow: 0 4px 12px rgba(239,68,68,0.3);">
                <div style="font-size: 12px; opacity: 0.9; margin-bottom: 4px;">🔥 重要事件</div>
                <div style="font-size: 28px; font-weight: 700;">{hot_events}</div>
            </div>
            <div style="flex: 1; min-width: 140px; background: linear-gradient(135deg,#10b981,#059669); padding: 16px 20px; border-radius: 12px; color: #fff; box-shadow: 0 4px 12px rgba(16,185,129,0.3);">
                <div style="font-size: 12px; opacity: 0.9; margin-bottom: 4px;">📌 热点主题</div>
                <div style="font-size: 28px; font-weight: 700;">{topic_count}</div>
            </div>
        </div>
        """)

        self._render_pipeline()

    def _render_pipeline(self):
        """渲染记忆流水线 - 深色主题风格"""
        if not self.engine:
            return

        report = self.engine.get_memory_report()
        stats = report.get('stats', {})
        memory_layers = report.get('memory_layers', {})

        total_events = stats.get('total_events', 0)
        filtered_events = stats.get('filtered_events', 0)
        processed_events = stats.get('processed_events', 0)

        short_layer = memory_layers.get('short', {})
        mid_layer = memory_layers.get('mid', {})

        short_size = short_layer.get('size', 0)
        short_capacity = short_layer.get('capacity', 0)
        mid_size = mid_layer.get('size', 0)
        mid_capacity = mid_layer.get('capacity', 0)

        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="font-size: 13px; font-weight: 600; color: #a855f7; margin-bottom: 4px;">
                🔍 记忆流水线
            </div>
            <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
                雷达事件 → 过滤 → 短期记忆 → 中期沉淀 → 长期反思
            </div>

            <div style="display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 14px;">
                <div style="flex: 1; min-width: 100px; padding: 10px; background: rgba(255,255,255,0.02); border-radius: 8px; text-align: center;">
                    <div style="font-size: 20px; font-weight: 700; color: #60a5fa;">{total_events}</div>
                    <div style="font-size: 10px; color: #475569;">接收事件</div>
                </div>
                <div style="flex: 1; min-width: 100px; padding: 10px; background: rgba(255,255,255,0.02); border-radius: 8px; text-align: center;">
                    <div style="font-size: 20px; font-weight: 700; color: #f87171;">{filtered_events}</div>
                    <div style="font-size: 10px; color: #475569;">过滤掉</div>
                </div>
                <div style="flex: 1; min-width: 100px; padding: 10px; background: rgba(255,255,255,0.02); border-radius: 8px; text-align: center;">
                    <div style="font-size: 20px; font-weight: 700; color: #4ade80;">{processed_events}</div>
                    <div style="font-size: 10px; color: #475569;">处理成功</div>
                </div>
            </div>

            <div style="display: flex; gap: 12px;">
                <div style="flex: 1; padding: 10px; background: rgba(168,85,247,0.12); border: 1px solid rgba(168,85,247,0.25); border-radius: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-size: 11px; color: #a855f7; font-weight: 600;">短期</span>
                        <span style="font-size: 11px; color: #cbd5e1;">{short_size}/{short_capacity}</span>
                    </div>
                    <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                        <div style="width: {short_pct}%; height: 100%; background: linear-gradient(90deg, #a855f7, #c084fc); border-radius: 3px;"></div>
                    </div>
                    <div style="font-size: 10px; color: #475569; margin-top: 4px;">{short_size} 条事件</div>
                </div>
                <div style="flex: 1; padding: 10px; background: rgba(34,197,94,0.12); border: 1px solid rgba(34,197,94,0.25); border-radius: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-size: 11px; color: #4ade80; font-weight: 600;">中期</span>
                        <span style="font-size: 11px; color: #cbd5e1;">{mid_size}/{mid_capacity}</span>
                    </div>
                    <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                        <div style="width: {mid_pct}%; height: 100%; background: linear-gradient(90deg, #4ade80, #6ee7b7); border-radius: 3px;"></div>
                    </div>
                    <div style="font-size: 10px; color: #475569; margin-top: 4px;">{mid_size} 条沉淀</div>
                </div>
            </div>
        </div>
        """.format(
            total_events=total_events,
            filtered_events=filtered_events,
            processed_events=processed_events,
            short_size=short_size,
            short_capacity=short_capacity,
            short_pct=min(100, int(short_size / max(1, short_capacity) * 100)) if short_capacity else 0,
            mid_size=mid_size,
            mid_capacity=mid_capacity,
            mid_pct=min(100, int(mid_size / max(1, mid_capacity) * 100)) if mid_capacity else 0,
        ))

    def _render_hot_topics(self):
        """渲染热点主题 - 深色主题风格"""
        if not self.engine:
            return

        report = self.engine.get_memory_report()
        topics = report.get('top_topics', [])

        if not topics:
            return

        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="font-size: 13px; font-weight: 600; color: #f97316; margin-bottom: 4px;">
                📈 热点主题
            </div>
            <div style="font-size: 11px; color: #475569; margin-bottom: 12px;">
                基于事件频率和注意力得分计算的热点主题
            </div>
        """)

        put_html('<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px;">')
        for topic in topics[:6]:
            name = topic.get('name', '未命名')
            count = topic.get('event_count', 0)
            attention = topic.get('avg_attention', 0)
            growth = topic.get('growth_rate', 0)

            growth_icon = "📈" if growth > 0.2 else ("📉" if growth < -0.2 else "➡️")
            growth_color = "#4ade80" if growth > 0.2 else ("#f87171" if growth < -0.2 else "#6b7280")
            heat_level = "🔥🔥🔥" if attention > 0.7 else ("🔥🔥" if attention > 0.5 else "🔥")

            put_html(f'''
            <div style="background: rgba(255,255,255,0.03); border-radius: 8px; padding: 12px 14px; border: 1px solid rgba(255,255,255,0.08);">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 6px;">
                    <div style="font-size: 13px; font-weight: 600; color: #cbd5e1; flex: 1;">{name}</div>
                    <div style="font-size: 11px; color: #fb923c;">{heat_level}</div>
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 11px; color: #475569;">
                    <span>{count} 条</span>
                    <span style="color: {growth_color};">{growth_icon} {growth:+.0%}</span>
                </div>
            </div>
            ''')
        put_html('</div>')
        put_html('</div>')

    def _render_recent_events(self):
        """渲染最近重要事件 - 深色主题风格"""
        if not self.engine:
            return

        report = self.engine.get_memory_report()
        events = report.get('recent_high_attention', [])

        if not events:
            return

        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="font-size: 13px; font-weight: 600; color: #fbbf24; margin-bottom: 4px;">
                ⚡ 最近重要事件
            </div>
            <div style="font-size: 11px; color: #475569; margin-bottom: 12px;">
                高注意力得分的事件，按时间倒序排列
            </div>
        """)

        for event in events[:5]:
                timestamp_str = event.get('timestamp', '')
                if 'T' in timestamp_str:
                    try:
                        ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        timestamp_str = ts.strftime('%m-%d %H:%M')
                    except:
                        pass

                content = event.get('content', '')
                score = event.get('score', 0)
                bar_color = "#f87171" if score > 0.7 else ("#fb923c" if score > 0.5 else "#60a5fa")

                put_html(f'''
                <div style="display: flex; align-items: center; gap: 12px; padding: 10px 12px; background: rgba(255,255,255,0.02); border-radius: 8px; border-left: 3px solid {bar_color};">
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-size: 12px; color: #cbd5e1; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{content[:80]}</div>
                        <div style="font-size: 10px; color: #475569;">🕐 {timestamp_str}</div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;">
                        <div style="width: 50px; height: 5px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                            <div style="width: {int(score*100)}%; height: 100%; background: {bar_color}; border-radius: 3px;"></div>
                        </div>
                        <span style="font-size: 11px; color: #475569; min-width: 32px;">{score:.0%}</span>
                    </div>
                </div>
                ''')
        put_html('</div>')

    def _render_storage(self):
        """渲染存储"""
        if not self.engine:
            put_html(render_empty_state("认知引擎未初始化"))
            return

        report = self.engine.get_memory_report()
        memory_layers = report.get('memory_layers', {})

        short = memory_layers.get('short', {})
        mid = memory_layers.get('mid', {})

        short_size = short.get('size', 0)
        short_cap = short.get('capacity', 1000)
        mid_size = mid.get('size', 0)
        mid_cap = mid.get('capacity', 5000)

        short_pct = min(100, int(short_size / short_cap * 100)) if short_cap > 0 else 0
        mid_pct = min(100, int(mid_size / mid_cap * 100)) if mid_cap > 0 else 0

        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="font-size: 13px; font-weight: 600; color: #60a5fa; margin-bottom: 4px;">
                🧠 记忆存储
            </div>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 14px;">
                <div style="text-align: center; padding: 10px; background: rgba(96,165,250,0.12); border: 1px solid rgba(96,165,250,0.25); border-radius: 8px;">
                    <div style="font-size: 16px; margin-bottom: 2px;">⚡</div>
                    <div style="font-size: 11px; font-weight: 600; color: #60a5fa;">短期</div>
                    <div style="font-size: 18px; font-weight: 700; color: #93c5fd;">{short_size}</div>
                    <div style="font-size: 10px; color: #475569;">/ {short_cap}</div>
                </div>
                <div style="text-align: center; padding: 10px; background: rgba(251,191,36,0.12); border: 1px solid rgba(251,191,36,0.25); border-radius: 8px;">
                    <div style="font-size: 16px; margin-bottom: 2px;">📦</div>
                    <div style="font-size: 11px; font-weight: 600; color: #fbbf24;">中期</div>
                    <div style="font-size: 18px; font-weight: 700; color: #fcd34d;">{mid_size}</div>
                    <div style="font-size: 10px; color: #475569;">/ {mid_cap}</div>
                </div>
                <div style="text-align: center; padding: 10px; background: rgba(168,85,247,0.12); border: 1px solid rgba(168,85,247,0.25); border-radius: 8px;">
                    <div style="font-size: 16px; margin-bottom: 2px;">🧠</div>
                    <div style="font-size: 11px; font-weight: 600; color: #a855f7;">长期</div>
                    <div style="font-size: 18px; font-weight: 700; color: #c084fc;">总结</div>
                    <div style="font-size: 10px; color: #475569;">定期生成</div>
                </div>
            </div>
            <div style="margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; font-size: 11px; color: #475569; margin-bottom: 4px;">
                    <span>短期使用</span><span>{short_size}/{short_cap}</span>
                </div>
                <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                    <div style="width: {short_pct}%; height: 100%; background: linear-gradient(90deg,#60a5fa,#93c5fd); border-radius: 3px;"></div>
                </div>
            </div>
            <div>
                <div style="display: flex; justify-content: space-between; font-size: 11px; color: #475569; margin-bottom: 4px;">
                    <span>中期使用</span><span>{mid_size}/{mid_cap}</span>
                </div>
                <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                    <div style="width: {mid_pct}%; height: 100%; background: linear-gradient(90deg,#fbbf24,#fcd34d); border-radius: 3px;"></div>
                </div>
            </div>
        </div>
        """.format(
            short_size=short_size, short_cap=short_cap, short_pct=short_pct,
            mid_size=mid_size, mid_cap=mid_cap, mid_pct=mid_pct
        ))

    def _render_help(self):
        """渲染帮助说明"""
        render_help_collapse("cognition")

    def _refresh_data(self):
        """刷新数据"""
        run_js("setTimeout(function() { location.reload(); }, 200)")

    def _generate_report(self):
        """生成完整报告"""
        if not self.engine:
            toast("认知引擎未初始化", color="error")
            return
        report_text = self.engine.generate_thought_report()
        popup("认知报告", put_text(report_text))

    def _clear_storage(self):
        """清空存储"""
        if not self.engine:
            toast("认知引擎未初始化", color="error")
            return
        if hasattr(self.engine, 'short_memory'):
            self.engine.short_memory.clear()
        if hasattr(self.engine, 'mid_memory'):
            self.engine.mid_memory.clear()
        if hasattr(self.engine, 'long_memory'):
            self.engine.long_memory.clear()
        if hasattr(self.engine, 'topics'):
            self.engine.topics.clear()
        if hasattr(self.engine, 'attention_scorer'):
            self.engine.attention_scorer = AttentionScorer()
        toast("存储已清空", color="success")
        run_js("setTimeout(function() { location.reload(); }, 1000)")


def render_empty_state(message: str) -> str:
    """渲染空状态"""
    return f'<div style="padding: 24px; text-align: center; color: #94a3b8; font-size: 13px; background: #f8fafc; border-radius: 8px;">{message}</div>'


def main():
    """主入口"""
    ui = CognitionUI()
    ui.render()


if __name__ == "__main__":
    main()
