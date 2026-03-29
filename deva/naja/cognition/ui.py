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
from ..common.ui_style import format_timestamp


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


def _get_data_sources():
    return [
        {"type": "market", "icon": "📡", "name": "市场事件", "color": "#f97316", "desc": "市场事件/叙事"},
        {"type": "attention", "icon": "👁️", "name": "注意力事件", "color": "#14b8a6", "desc": "市场关注度变化"},
        {"type": "news", "icon": "📰", "name": "新闻事件", "color": "#0ea5e9", "desc": "新闻/舆情信号"},
        {"type": "cross_signal", "icon": "🔄", "name": "共振信号", "color": "#8b5cf6", "desc": "新闻×注意力共振"},
        {"type": "attention_shift", "icon": "🔀", "name": "注意力转移", "color": "#f59e0b", "desc": "板块/个股变化"},
        {"type": "feedback_experiment", "icon": "📊", "name": "实验反馈", "color": "#22c55e", "desc": "策略有效性"},
        {"type": "sector_hotspot", "icon": "🔥", "name": "板块热点", "color": "#ef4444", "desc": "热点板块变化"},
        {"type": "llm_reflection", "icon": "🤖", "name": "LLM反思", "color": "#0ea5e9", "desc": "深度市场分析"},
    ]


def _calc_source_counts(recent_insights):
    source_counts = {}
    recent_by_source = {}
    for insight in recent_insights:
        src = insight.get('source', '')
        signal = insight.get('signal_type', '')
        theme = insight.get('theme', '')

        if src.startswith('llm_reflection') or signal == 'llm_reflection':
            key = 'llm_reflection'
        elif src == 'attention' or signal == 'attention_shift' or 'attention' in src:
            key = 'attention'
        elif src == 'cross_signal' or 'resonance' in str(signal):
            key = 'cross_signal'
        elif src.startswith('feedback') or signal.startswith('effective'):
            key = 'feedback_experiment'
        elif signal == 'sector_hotspot' or signal == 'sector_anomaly':
            key = 'sector_hotspot'
        elif signal.startswith('narrative_') or 'narrative' in str(signal) or '🌊' in theme:
            key = 'market'
        elif src == 'news' or signal == 'news_topic' or '📰' in theme:
            key = 'news'
        elif signal.startswith('topic_') or '📊' in theme:
            key = 'news'
        elif src == 'radar' or signal == 'radar' or src == 'market':
            key = 'market'
        else:
            key = src if src else 'other'
        source_counts[key] = source_counts.get(key, 0) + 1
        if key not in recent_by_source:
            recent_by_source[key] = []
        recent_by_source[key].append(insight)
    return source_counts, recent_by_source


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

        insight_pool = None
        try:
            from .insight import get_insight_pool
            insight_pool = get_insight_pool()
        except Exception:
            pass

        source_counts = {}
        recent_by_source = {}
        recent_insights = []
        if insight_pool:
            recent_insights = insight_pool.get_recent_insights(limit=100) or []
            source_counts, recent_by_source = _calc_source_counts(recent_insights)

        self._render_event_bus_flow(source_counts, recent_by_source, recent_insights)
        self._render_narrative_lifecycle()
        self._render_liquidity_structure()
        self._render_propagation_network()
        self._render_cross_signal_section()
        self._render_semantic_cold_start()
        self._render_insight_section()
        self._render_storage()
        self._render_control_panel()
        self._render_help()

        put_html('</div>')

    def _render_event_bus_flow(self, source_counts=None, recent_by_source=None, recent_insights=None):
        """渲染认知事件流 - 展示一切皆流的理念

        Args:
            source_counts: 各数据源的事件计数
            recent_by_source: 按数据源分组最近的洞察
            recent_insights: 最近的洞察列表
        """
        try:
            from .cognition_bus import cognition_bus, CognitionEventType, get_cognition_bus
            bus = get_cognition_bus()
            bus_len = len(bus) if hasattr(bus, '__len__') else 0
            cache_max = getattr(bus, 'cache_max_len', 1000)
            cache_age = getattr(bus, 'cache_max_age_seconds', 3600)
        except Exception:
            bus_len = 0
            cache_max = 1000
            cache_age = 3600

        if source_counts is None:
            source_counts = {}
        if recent_by_source is None:
            recent_by_source = {}

        event_type_colors = {
            "attention_snapshot": "#14b8a6",
            "news_signal": "#f97316",
            "resonance_detected": "#a855f7",
            "insight_generated": "#0ea5e9",
            "cognition_feedback": "#4ade80",
            "narrative_update": "#fb923c",
            "semantic_graph_update": "#60a5fa",
        }

        DATA_SOURCES = _get_data_sources()

        event_type_cards = ""
        for ds in DATA_SOURCES:
            color = ds["color"]
            count = source_counts.get(ds['type'], 0)
            bar_width = min(100, int(count / max(1, 50) * 100)) if count > 0 else 0

            event_type_cards += f"""
            <div style="display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: rgba(255,255,255,0.02); border-radius: 4px; margin-bottom: 4px; border-left: 3px solid {color};">
                <span style="font-size: 12px;">{ds['icon']}</span>
                <div style="flex: 1; min-width: 0;">
                    <div style="font-size: 10px; color: #cbd5e1;">{ds['name']}</div>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 10px; color: {color}; font-weight: 600;">{count}</span>
                </div>
            </div>
            """

        source_recent_items = ""
        for ds in DATA_SOURCES:
            insights = recent_by_source.get(ds['type'], [])[:2]
            if not insights:
                continue
            items = ""
            for item in insights:
                ts = format_timestamp(float(item.get('ts', 0)))
                theme = item.get('theme', '-')[:25]
                items += f"""
                <div style="display: flex; justify-content: space-between; font-size: 9px; color: #94a3b8; padding: 2px 0;">
                    <span style="color: {ds['color']};">{ts[-8:]}</span>
                    <span style="flex: 1; margin-left: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{theme}</span>
                </div>
                """
            source_recent_items += f"""
            <div style="background: rgba(255,255,255,0.02); border-radius: 4px; padding: 6px; margin-bottom: 6px;">
                <div style="font-size: 9px; color: {ds['color']}; font-weight: 600; margin-bottom: 4px;">{ds['icon']} {ds['name']}</div>
                {items}
            </div>
            """

        flow_items = """
        <div style="display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: rgba(20,184,166,0.1); border-radius: 4px; margin-bottom: 6px;">
            <span style="font-size: 12px;">📡</span>
            <span style="font-size: 10px; color: #14b8a6;">雷达</span>
            <span style="color: #475569;">→</span>
            <span style="font-size: 10px; color: #94a3b8;">事件入队</span>
        </div>
        <div style="display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: rgba(168,85,247,0.1); border-radius: 4px; margin-bottom: 6px;">
            <span style="font-size: 12px;">🔄</span>
            <span style="font-size: 10px; color: #a855f7;">跨信号</span>
            <span style="color: #475569;">→</span>
            <span style="font-size: 10px; color: #94a3b8;">共振检测</span>
        </div>
        <div style="display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: rgba(14,165,233,0.1); border-radius: 4px; margin-bottom: 6px;">
            <span style="font-size: 12px;">🤖</span>
            <span style="font-size: 10px; color: #0ea5e9;">LLM反思</span>
            <span style="color: #475569;">→</span>
            <span style="font-size: 10px; color: #94a3b8;">深度洞察</span>
        </div>
        <div style="display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: rgba(74,222,128,0.1); border-radius: 4px;">
            <span style="font-size: 12px;">📊</span>
            <span style="font-size: 10px; color: #4ade80;">反馈</span>
            <span style="color: #475569;">→</span>
            <span style="font-size: 10px; color: #94a3b8;">注意力调度</span>
        </div>
        """

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
                    🌊 认知事件流
                </div>
                <div style="font-size: 10px; color: #475569;">
                    缓冲: {bus_len}/{cache_max} | 生命周期: {cache_age}s
                </div>
            </div>
            <div style="font-size: 11px; color: #475569; margin-bottom: 12px;">
                一切皆流，无物永驻 — 事件驱动，实时处理
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;">
                <div>
                    <div style="font-size: 10px; font-weight: 600; color: #64748b; margin-bottom: 6px;">
                        📥 事件来源 ({len([k for k in source_counts if source_counts.get(k, 0) > 0])} 种活跃)
                    </div>
                    {event_type_cards}
                </div>
                <div>
                    <div style="font-size: 10px; font-weight: 600; color: #64748b; margin-bottom: 6px;">
                        🔄 处理流程
                    </div>
                    {flow_items}
                </div>
                <div>
                    <div style="font-size: 10px; font-weight: 600; color: #64748b; margin-bottom: 6px;">
                        📋 最近事件
                    </div>
                    {source_recent_items or '<div style="color: #64748b; font-size: 10px;">暂无数据</div>'}
                </div>
            </div>
        </div>
        """)

    def _render_semantic_cold_start(self):
        """渲染语义冷启动模块 - 完整展示语义图谱能力"""
        try:
            from .semantic_cold_start import SemanticColdStart
            cold_start = SemanticColdStart()
            graph = cold_start.get_graph()
            seeds = graph.get("seeds", [])
            nodes = graph.get("nodes", [])
            edges = graph.get("edges", [])
            decay = graph.get("industry_decay", [])
        except Exception:
            return

        node_count = len(nodes)
        edge_count = len(edges)
        seed_count = len(seeds)
        decay_count = len(decay)

        seed_tags = ""
        for seed in seeds[:10]:
            seed_tags += f'<span style="display: inline-block; padding: 2px 6px; background: rgba(96,165,250,0.15); color: #60a5fa; border-radius: 4px; font-size: 9px; margin: 2px;">{seed}</span>'
        if seeds:
            seed_tags += f'<span style="color: #64748b; font-size: 9px;">+{max(0, seed_count - 10)}</span>'

        level0_nodes = [n for n in nodes if n.get('level', 0) == 0]
        level1_nodes = [n for n in nodes if n.get('level', 0) == 1]
        level2_nodes = [n for n in nodes if n.get('level', 0) >= 2]

        top_level0 = sorted(level0_nodes, key=lambda x: x.get('weight', 0), reverse=True)[:4]
        top_level1 = sorted(level1_nodes, key=lambda x: x.get('weight', 0), reverse=True)[:4]
        top_level2 = sorted(level2_nodes, key=lambda x: x.get('weight', 0), reverse=True)[:4]

        def render_node_bar(node, color):
            term = node.get('term', '-')
            weight = float(node.get('weight', 0))
            confidence = float(node.get('confidence', 0))
            relation = node.get('relation', '')
            bar_width = min(100, int(weight * 100))
            return f"""
            <div style="margin-bottom: 6px;">
                <div style="display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; margin-bottom: 2px;">
                    <span style="color: {color};">{term[:15]}</span>
                    <span style="color: #a855f7;">{weight:.3f}</span>
                </div>
                <div style="height: 3px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden;">
                    <div style="width: {bar_width}%; height: 100%; background: linear-gradient(90deg, {color}, {color}aa);"></div>
                </div>
                <div style="font-size: 8px; color: #64748b;">{relation[:20]} | 置信 {confidence:.2f}</div>
            </div>
            """

        level0_bars = "".join([render_node_bar(n, "#f87171") for n in top_level0]) if top_level0 else '<div style="color: #64748b; font-size: 10px;">暂无</div>'
        level1_bars = "".join([render_node_bar(n, "#fb923c") for n in top_level1]) if top_level1 else '<div style="color: #64748b; font-size: 10px;">暂无</div>'
        level2_bars = "".join([render_node_bar(n, "#60a5fa") for n in top_level2]) if top_level2 else '<div style="color: #64748b; font-size: 10px;">暂无</div>'

        decay_items = ""
        top_decay = sorted(decay, key=lambda x: x.get('lambda', 0), reverse=True)[:5]
        for d in top_decay:
            term = d.get('term', '-')
            lam = float(d.get('lambda', 0))
            decay_items += f"""
            <div style="display: flex; justify-content: space-between; font-size: 9px; color: #94a3b8; padding: 2px 0;">
                <span>{term[:10]}</span>
                <span style="color: #4ade80;">λ={lam:.4f}</span>
            </div>
            """
        if not decay_items:
            decay_items = '<div style="color: #64748b; font-size: 9px;">暂无衰减配置</div>'

        edge_items = ""
        relation_types = {}
        for e in edges[:10]:
            src = e.get('src', '-')
            dst = e.get('dst', '-')
            rel = e.get('relation', 'related')
            w = float(e.get('weight', 0))
            relation_types[rel] = relation_types.get(rel, 0) + 1
            src_short = src[:8] if len(src) > 8 else src
            dst_short = dst[:8] if len(dst) > 8 else dst
            rel_short = rel[:10] if len(rel) > 10 else rel
            edge_items += f"""
            <div style="font-size: 9px; color: #94a3b8; padding: 2px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                <span style="color: #a855f7;">{src_short}</span> → <span style="color: #60a5fa;">{dst_short}</span>
                <span style="color: #64748b;">({rel_short})</span>
                <span style="color: #4ade80; float: right;">{w:.2f}</span>
            </div>
            """
        if not edge_items:
            edge_items = '<div style="color: #64748b; font-size: 9px;">暂无边关系</div>'

        relation_summary = ""
        for rel, cnt in sorted(relation_types.items(), key=lambda x: x[1], reverse=True)[:4]:
            relation_summary += f'<span style="display: inline-block; padding: 1px 4px; background: rgba(168,85,247,0.1); color: #a855f7; border-radius: 3px; font-size: 8px; margin: 2px;">{rel}({cnt})</span>'

        put_html(f"""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <div style="font-size: 13px; font-weight: 600; color: #a855f7;">
                    🔗 语义冷启动
                </div>
                <div style="font-size: 10px; color: #475569;">
                    种子: {seed_count} | 节点: {node_count} | 边: {edge_count} | 衰减: {decay_count}
                </div>
            </div>
            <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
                种子词 → 语义扩展 → 权重计算 → 图谱构建
            </div>

            <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 12px; margin-bottom: 12px;">
                <div style="background: rgba(96,165,250,0.08); border-radius: 8px; padding: 10px;">
                    <div style="font-size: 10px; color: #60a5fa; font-weight: 600; margin-bottom: 6px;">🎯 种子词</div>
                    <div style="margin-bottom: 10px;">{seed_tags or '<span style="color: #64748b; font-size: 10px;">暂无种子</span>'}</div>

                    <div style="font-size: 10px; color: #4ade80; font-weight: 600; margin-bottom: 6px;">📉 衰减配置 (Top5)</div>
                    <div>{decay_items}</div>
                </div>

                <div>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 10px;">
                        <div style="background: rgba(248,113,113,0.1); border: 1px solid rgba(248,113,113,0.2); padding: 8px; border-radius: 6px; text-align: center;">
                            <div style="font-size: 16px; font-weight: 700; color: #f87171;">{len(level0_nodes)}</div>
                            <div style="font-size: 9px; color: #64748b;">一级节点</div>
                        </div>
                        <div style="background: rgba(251,146,60,0.1); border: 1px solid rgba(251,146,60,0.2); padding: 8px; border-radius: 6px; text-align: center;">
                            <div style="font-size: 16px; font-weight: 700; color: #fb923c;">{len(level1_nodes)}</div>
                            <div style="font-size: 9px; color: #64748b;">二级节点</div>
                        </div>
                        <div style="background: rgba(96,165,250,0.1); border: 1px solid rgba(96,165,250,0.2); padding: 8px; border-radius: 6px; text-align: center;">
                            <div style="font-size: 16px; font-weight: 700; color: #60a5fa;">{len(level2_nodes)}</div>
                            <div style="font-size: 9px; color: #64748b;">深层节点</div>
                        </div>
                    </div>

                    {relation_summary if relation_summary else ''}
                </div>
            </div>

            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 10px;">
                <div style="background: rgba(248,113,113,0.08); border-radius: 6px; padding: 8px;">
                    <div style="font-size: 9px; color: #f87171; font-weight: 600; margin-bottom: 4px;">🔴 一级 (L0)</div>
                    {level0_bars}
                </div>
                <div style="background: rgba(251,146,60,0.08); border-radius: 6px; padding: 8px;">
                    <div style="font-size: 9px; color: #fb923c; font-weight: 600; margin-bottom: 4px;">🟠 二级 (L1)</div>
                    {level1_bars}
                </div>
                <div style="background: rgba(96,165,250,0.08); border-radius: 6px; padding: 8px;">
                    <div style="font-size: 9px; color: #60a5fa; font-weight: 600; margin-bottom: 4px;">🔵 深层 (L2+)</div>
                    {level2_bars}
                </div>
            </div>

            <div style="background: rgba(255,255,255,0.02); border-radius: 6px; padding: 8px;">
                <div style="font-size: 10px; color: #a855f7; font-weight: 600; margin-bottom: 4px;">🔗 边关系 (Top10)</div>
                <div>{edge_items}</div>
            </div>

            <div style="margin-top: 10px; padding: 8px; background: rgba(74,222,128,0.08); border-radius: 6px; border: 1px solid rgba(74,222,128,0.15);">
                <div style="font-size: 9px; color: #4ade80; font-weight: 600; margin-bottom: 4px;">💡 权重计算公式</div>
                <div style="font-size: 8px; color: #64748b; font-family: monospace;">
                    weight = 0.6 × historical_relevance + 0.4 × confidence
                </div>
            </div>
        </div>
        """)

    def _render_insight_section(self):
        """渲染洞察模块 - 展示思考层的逻辑和产物 - 深色主题风格"""
        from deva.naja.cognition.system_architecture import get_cognition_architecture_doc
        put_html(get_cognition_architecture_doc())

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
                    🔄 注意力转移监测
                </div>
            """)
            for item in attention_shift_insights[:5]:
                theme = item.get('theme', '-')
                summary_raw = item.get('summary', '')
                if isinstance(summary_raw, dict):
                    from .insight.engine import Insight
                    summary = Insight._format_dict_for_display(summary_raw, 120)
                elif isinstance(summary_raw, str) and summary_raw.startswith('{') and summary_raw.endswith('}'):
                    try:
                        import ast
                        parsed = ast.literal_eval(summary_raw)
                        if isinstance(parsed, dict):
                            from .insight.engine import Insight
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
                    from .insight.engine import Insight
                    summary = Insight._format_dict_for_display(summary_raw, 150)
                elif isinstance(summary_raw, str) and summary_raw.startswith('{') and summary_raw.endswith('}'):
                    try:
                        import ast
                        parsed = ast.literal_eval(summary_raw)
                        if isinstance(parsed, dict):
                            from .insight.engine import Insight
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
                sectors = ', '.join(str(s) for s in item.get('sectors', [])[:4]) or '-'
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
                    linked_sectors = payload.get('linked_sectors', [])[:2]

                    trend_icon = '📈' if trend > 0 else '📉' if trend < 0 else '➡️'
                    stage_color = '#4ade80' if stage == '高潮' else ('#a855f7' if stage == '扩散' else ('#fb923c' if stage == '消退' else '#60a5fa'))

                    kw_tags = ''.join([f'<span style="display: inline-block; padding: 1px 4px; background: rgba(255,255,255,0.08); color: #94a3b8; border-radius: 3px; font-size: 9px; margin-right: 2px;">{kw}</span>' for kw in keywords]) if keywords else ''
                    sector_tags = ''.join([f'<span style="display: inline-block; padding: 1px 4px; background: rgba(249,115,22,0.15); color: #fb923c; border-radius: 3px; font-size: 9px; margin-right: 2px;">{sec}</span>' for sec in linked_sectors]) if linked_sectors else ''

                    summary = f'<span style="color: {stage_color}; font-weight: 600;">叙事{narrative}进入</span><span style="padding: 1px 6px; background: {stage_color}; color: #0f172a; border-radius: 4px; font-size: 10px; font-weight: 600; margin: 0 4px;">{stage}</span>{trend_icon} 注意力{int(attention_score*100)}% {kw_tags} {sector_tags}'
                    summary = summary.replace('{', '{{').replace('}', '}}')
                    score_color = stage_color
                    is_html = True
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
                    is_html = True
                elif isinstance(summary_raw, dict):
                    from .insight.engine import Insight
                    summary = Insight._format_dict_for_display(summary_raw, 60)
                    summary = summary.replace('{', '{{').replace('}', '}}').replace('<', '&lt;').replace('>', '&gt;')
                    is_html = False
                elif isinstance(summary_raw, str) and summary_raw.startswith('{') and summary_raw.endswith('}'):
                    try:
                        import ast
                        parsed = ast.literal_eval(summary_raw)
                        if isinstance(parsed, dict):
                            from .insight.engine import Insight
                            summary = Insight._format_dict_for_display(parsed, 60)
                            summary = summary.replace('{', '{{').replace('}', '}}').replace('<', '&lt;').replace('>', '&gt;')
                        else:
                            summary = summary_raw[:60]
                            summary = summary.replace('<', '&lt;').replace('>', '&gt;')
                        is_html = False
                    except Exception:
                        summary = summary_raw[:60]
                        summary = summary.replace('<', '&lt;').replace('>', '&gt;')
                        is_html = False
                else:
                    summary = summary_raw[:60] if summary_raw else '-'
                    summary = summary.replace('<', '&lt;').replace('>', '&gt;')
                    is_html = False
                score = float(item.get('user_score', 0))
                ts = format_timestamp(float(item.get('ts', 0)))

                score_color = '#f87171' if score > 0.7 else ('#fb923c' if score > 0.5 else '#60a5fa')

                if signal_type == 'narrative_stage_change':
                    put_html(f"""
                    <div style="display: flex; align-items: center; gap: 10px; padding: 8px; background: rgba(255,255,255,0.02); border-radius: 6px; margin-bottom: 4px; border-left: 3px solid {stage_color};">
                        <div style="flex: 1; min-width: 0;">
                            <div style="font-size: 11px; font-weight: 600; color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">🌊 {theme}</div>
                            <div style="font-size: 11px; color: #94a3b8; margin-top: 4px;">{summary}</div>
                        </div>
                        <div style="font-size: 10px; color: #475569; flex-shrink: 0;">{ts[-8:]}</div>
                    </div>
                    """)
                else:
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
        def _format_insight_summary(insight: Dict) -> str:
            summary_raw = insight.get('summary', '')
            if isinstance(summary_raw, dict):
                from .insight.engine import Insight
                text = Insight._format_dict_for_display(summary_raw, 80)
            elif isinstance(summary_raw, str) and summary_raw.startswith('{') and summary_raw.endswith('}'):
                try:
                    import ast
                    parsed = ast.literal_eval(summary_raw)
                    if isinstance(parsed, dict):
                        from .insight.engine import Insight
                        text = Insight._format_dict_for_display(parsed, 80)
                    else:
                        text = summary_raw[:80]
                except Exception:
                    text = summary_raw[:80]
            else:
                text = summary_raw[:80] if summary_raw else '-'
            return text

        insight_lines = "".join(
            [f"<li>{_format_insight_summary(i)}</li>" for i in top_insights]
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
        """渲染控制面板 - 包含反思数据预览"""
        from .insight import get_llm_reflection_engine, get_insight_pool
        from ..attention.intelligence.feedback_report import get_feedback_report_generator

        llm_engine = get_llm_reflection_engine()
        pool = get_insight_pool()
        feedback_reporter = get_feedback_report_generator()

        stats = llm_engine.get_stats()
        pending_signals = stats.get('pending_signals', 0)
        interval = int(stats.get('interval_seconds', 3600))

        signals = pool.get_recent_insights(limit=100) if pool else []
        narratives_data = self.engine.get_memory_report().get('narratives', {}).get('summary', []) if self.engine else []
        narratives = []
        for n in narratives_data:
            narrative = n.get('narrative', '')
            if narrative:
                narratives.append({
                    'narrative': narrative,
                    'stage': n.get('stage', '萌芽'),
                    'trend': n.get('trend', 0),
                })

        feedback_summary = feedback_reporter.get_summary()
        feedback_signals = feedback_summary.get('signals_count', 0)
        feedback_bandit = feedback_summary.get('bandit_count', 0)
        feedback_records = feedback_summary.get('feedback_count', 0)
        is_collecting = feedback_summary.get('is_collecting', False)

        radar_signals = [s for s in signals if s.get('source') in ('market', 'radar', 'radar_news') or s.get('signal_type') in ('pattern', 'drift', 'anomaly', 'sector_anomaly', 'news_topic')]
        attention_signals = [s for s in signals if s.get('source') == 'attention' or s.get('signal_type') in ('global_attention_shift', 'market_activity_shift', 'sector_concentration_shift', 'sector_hotspot', 'symbol_attention_change', 'market_state_shift')]
        cross_signals = [s for s in signals if s.get('source') == 'cross_signal' or 'resonance' in str(s.get('signal_type', ''))]
        feedback_insights = [s for s in signals if s.get('source') == 'feedback_experiment' or s.get('signal_type') in ('experiment_feedback_summary', 'bandit_learning_analysis')]
        effectiveness_signals = [s for s in signals if s.get('source') == 'attention_effectiveness' or s.get('signal_type') in ('effective_pattern', 'ineffective_pattern')]
        llm_signals = [s for s in signals if s.get('source', '').startswith('llm_reflection') or s.get('signal_type') == 'llm_reflection']

        normal_signals = [s for s in signals if s not in radar_signals + attention_signals + cross_signals + feedback_insights + effectiveness_signals + llm_signals]

        def _render_source_section(title, icon, color, signals_list, max_show=4, max_len=18):
            if not signals_list:
                return f'<div style="margin-bottom: 8px;"><div style="font-size: 11px; color: {color}; margin-bottom: 4px;">{icon} {title} (0)</div><div style="color: #64748b; font-size: 10px;">暂无数据</div></div>'
            tags = ''.join([
                f'<span style="display: inline-block; padding: 2px 6px; background: rgba({color.replace("#", "").lower()}, 0.1); color: {color}; border-radius: 4px; font-size: 10px; margin: 2px;" title="{s.get("theme", "-")}">{s.get("theme", "-")[:max_len]}</span>'
                for s in signals_list[:max_show]
            ])
            count = len(signals_list)
            more = f' <span style="color: #64748b; font-size: 9px;">+{count - max_show}</span>' if count > max_show else ''
            return f'<div style="margin-bottom: 8px;"><div style="font-size: 11px; color: {color}; margin-bottom: 4px;">{icon} {title} ({count}){more}</div><div>{tags}</div></div>'

        def _render_signal_with_time(signals_list, title, icon, color, max_show=3):
            if not signals_list:
                return f'<div style="margin-bottom: 8px;"><div style="font-size: 11px; color: {color}; margin-bottom: 4px;">{icon} {title} (0)</div><div style="color: #64748b; font-size: 10px;">暂无数据</div></div>'
            items = []
            for s in signals_list[:max_show]:
                ts = s.get('ts', s.get('timestamp', 0))
                if ts:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(ts)
                    now = datetime.now()
                    diff = (now - dt).total_seconds()
                    if diff < 60:
                        time_str = "刚刚"
                    elif diff < 3600:
                        time_str = f"{int(diff // 60)}m"
                    elif diff < 86400:
                        time_str = f"{int(diff // 3600)}h"
                    else:
                        time_str = dt.strftime("%m-%d")
                else:
                    time_str = ""
                theme = s.get('theme', '-')[:15]
                score = s.get('system_attention', s.get('score', 0))
                items.append(f'<div style="display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; margin: 2px 0;"><span style="color: {color};">{time_str}</span><span style="flex: 1; margin-left: 6px;">{theme}</span><span>{score:.2f}</span></div>')
            count = len(signals_list)
            more = f'<div style="color: #64748b; font-size: 9px;">+{count - max_show} more</div>' if count > max_show else ''
            return f'<div style="margin-bottom: 8px;"><div style="font-size: 11px; color: {color}; margin-bottom: 4px;">{icon} {title} ({count})</div>{"".join(items)}{more}</div>'

        def _render_narrative_section(narratives_list, max_show=5):
            if not narratives_list:
                return f'<div style="margin-bottom: 8px;"><div style="font-size: 11px; color: #fb923c; margin-bottom: 4px;">🌊 叙事变化 (0)</div><div style="color: #64748b; font-size: 10px;">暂无叙事数据</div></div>'
            parts = []
            for n in narratives_list[:max_show]:
                narrative = n.get('narrative', '-')[:10]
                stage = n.get('stage', '萌芽')
                trend = n.get('trend', 0)
                ts = n.get('last_updated', 0)
                if ts:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(ts)
                    now = datetime.now()
                    diff = (now - dt).total_seconds()
                    if diff < 60:
                        time_str = "刚刚"
                    elif diff < 3600:
                        time_str = f"{int(diff // 60)}m"
                    elif diff < 86400:
                        time_str = f"{int(diff // 3600)}h"
                    else:
                        time_str = dt.strftime("%m-%d")
                else:
                    time_str = ""
                trend_icon = '📈' if trend > 0.3 else '📉' if trend < -0.3 else '➡️'
                color = '#4ade80' if stage == '高潮' else '#a855f7' if stage == '扩散' else '#94a3b8'
                parts.append(f'<div style="display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; margin: 2px 0;"><span style="color: #fb923c;">{time_str}</span><span style="color: {color};">{narrative}</span><span>{stage[:2]}{trend_icon}</span></div>')
            count = len(narratives_list)
            more = f'<div style="color: #64748b; font-size: 9px;">+{count - max_show} more</div>' if count > max_show else ''
            return f'<div style="margin-bottom: 8px;"><div style="font-size: 11px; color: #fb923c; margin-bottom: 4px;">🌊 叙事变化 ({count})</div>{"".join(parts)}{more}</div>'

        radar_section = _render_signal_with_time(radar_signals, "雷达事件", "📡", "#f59e0b")
        attention_section = _render_signal_with_time(attention_signals, "注意力事件", "👁️", "#0ea5e9")
        cross_section = _render_signal_with_time(cross_signals, "共振信号", "🔄", "#a855f7")
        feedback_section = _render_signal_with_time(feedback_insights, "实验反馈", "📊", "#4ade80")
        effectiveness_section = _render_signal_with_time(effectiveness_signals, "有效性分析", "✅", "#34d399")
        llm_section = _render_signal_with_time(llm_signals, "LLM反思", "🤖", "#60a5fa")
        narrative_section = _render_narrative_section(narratives)

        can_reflect = pending_signals >= 1
        reflect_btn_color = "success" if can_reflect else "secondary"

        self._put_html(f"""
        <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.08);">
            <div style="
                margin-bottom: 12px;
                background: rgba(255,255,255,0.03);
                border-radius: 12px;
                padding: 14px 18px;
                border: 1px solid rgba(255,255,255,0.08);
            ">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div style="font-size: 12px; font-weight: 600; color: #0ea5e9;">🤖 反思数据预览</div>
                    <div style="font-size: 10px; color: #64748b;">共 {pending_signals} 条洞察 | 每 {interval}s 触发</div>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px;">
                    <div style="background: rgba(245,158,11,0.08); border-radius: 8px; padding: 10px;">
                        {radar_section}
                        {attention_section}
                    </div>
                    <div style="background: rgba(168,85,247,0.08); border-radius: 8px; padding: 10px;">
                        {cross_section}
                        {effectiveness_section}
                    </div>
                    <div style="background: rgba(34,197,94,0.08); border-radius: 8px; padding: 10px;">
                        {feedback_section}
                        {llm_section}
                    </div>
                    <div style="background: rgba(249,115,22,0.08); border-radius: 8px; padding: 10px;">
                        {narrative_section}
                        <div style="margin-bottom: 8px;">
                            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">📈 常规洞察 ({len(normal_signals)})</div>
                            <div style="color: #64748b; font-size: 10px;">{' | '.join([s.get("theme", "-")[:12] for s in normal_signals[:3]]) or "暂无"}</div>
                        </div>
                    </div>
                </div>
            </div>
            <div style="display: flex; gap: 8px;">
        """)
        put_button("🔄 刷新", onclick=self._refresh_data, color="secondary", small=True)
        put_button(f"🧠 立即反思 ({pending_signals}条)", onclick=self._trigger_reflection, color=reflect_btn_color, small=True)
        put_button("📊 完整报告", onclick=self._generate_report, color="secondary", small=True)
        put_button("🧹 清空", onclick=self._clear_storage, color="secondary", small=True)
        put_html('</div></div>')

    def _trigger_reflection(self):
        """手动触发 LLM 反思"""
        from .insight import get_llm_reflection_engine

        try:
            engine = get_llm_reflection_engine()

            reflection_count = engine.get_stats().get('reflections_count', 0)
            pending_signals = engine.get_stats().get('pending_signals', 0)

            if pending_signals < 1:
                put_html("""
                <div style="margin: 16px 0; padding: 16px; background: rgba(249,115,22,0.1); border: 1px solid rgba(249,115,22,0.3); border-radius: 8px;">
                    <div style="color: #fb923c; font-weight: 600; margin-bottom: 8px;">⚠️ 反思条件不足</div>
                    <div style="color: #94a3b8; font-size: 12px;">
                        当前洞察池中只有 <b style="color: #fb923c;">{}</b> 条洞察，需要至少 <b style="color: #14b8a6;">1</b> 条才能触发 LLM 反思。
                    </div>
                    <div style="color: #64748b; font-size: 11px; margin-top: 8px;">
                        提示：请先运行实验模式产生反馈数据，或等待系统积累更多洞察。
                    </div>
                </div>
                """.format(pending_signals))
                return

            result = engine.trigger_now()
            if result:
                put_html("""
                <div style="margin: 16px 0; padding: 16px; background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.3); border-radius: 8px;">
                    <div style="color: #4ade80; font-weight: 600; margin-bottom: 8px;">✅ LLM 反思已生成</div>
                    <div style="color: #94a3b8; font-size: 12px;">
                        主题：<b style="color: #e2e8f0;">{}</b>
                    </div>
                    <div style="color: #64748b; font-size: 11px; margin-top: 8px;">
                        反思已添加到洞察池，页面刷新后将显示在「🤖 LLM 反思」区域。
                    </div>
                </div>
                """.format(result.theme))
            else:
                put_html("""
                <div style="margin: 16px 0; padding: 16px; background: rgba(249,115,22,0.1); border: 1px solid rgba(249,115,22,0.3); border-radius: 8px;">
                    <div style="color: #fb923c; font-weight: 600;">⚠️ 反思生成失败</div>
                    <div style="color: #94a3b8; font-size: 12px; margin-top: 8px;">
                        请检查 LLM 配置是否正确，或稍后重试。
                    </div>
                </div>
                """)

        except Exception as e:
            import traceback
            error_detail = str(e)
            log_msg = traceback.format_exc()
            put_html(f"""
            <div style="margin: 16px 0; padding: 16px; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 8px;">
                <div style="color: #f87171; font-weight: 600;">❌ 触发反思时出错</div>
                <div style="color: #94a3b8; font-size: 12px; margin-top: 8px;">
                    错误信息：<b style="color: #fb923c;">{error_detail}</b>
                </div>
            </div>
            """)

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
                evt_ts = format_timestamp(float(evt.get('timestamp', 0)))
                evt_attention = float(evt.get('attention_score', 0))
                evt_trend = float(evt.get('trend', 0))
                evt_keywords = evt.get('keywords', [])[:2]
                evt_sectors = evt.get('linked_sectors', [])[:2]

                if 'stage_change' in evt_type:
                    evt_color = '#4ade80' if evt_stage == '高潮' else ('#a855f7' if evt_stage == '扩散' else ('#fb923c' if evt_stage == '消退' else '#60a5fa'))
                    evt_icon = '🔄'
                    trend_icon = '📈' if evt_trend > 0 else '📉' if evt_trend < 0 else '➡️'
                    kw_str = ' '.join([f'<span style="padding: 1px 4px; background: rgba(255,255,255,0.08); color: #94a3b8; border-radius: 3px; font-size: 9px; margin-right: 2px;">{kw}</span>' for kw in evt_keywords]) if evt_keywords else ''
                    sector_str = ' '.join([f'<span style="padding: 1px 4px; background: rgba(249,115,22,0.15); color: #fb923c; border-radius: 3px; font-size: 9px; margin-right: 2px;">{s}</span>' for s in evt_sectors]) if evt_sectors else ''
                    evt_desc = f'<span style="color: {evt_color}; font-weight: 600;">{evt_nar}</span> → <span style="padding: 1px 6px; background: {evt_color}; color: #0f172a; border-radius: 4px; font-size: 10px; font-weight: 600;">{evt_stage}</span> {trend_icon} {int(evt_attention*100)}%'
                    if kw_str or sector_str:
                        evt_desc += f'<br><span style="margin-top: 4px; display: inline-block;">{kw_str} {sector_str}</span>'
                else:
                    evt_color = '#60a5fa'
                    evt_icon = '🔥'
                    evt_desc = f"{evt_nar} 飙升"
                put_html(f"""
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 0; font-size: 11px; border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <span><span style="color: {evt_color};">{evt_icon}</span> {evt_desc}</span>
                    <span style="color: #475569; font-size: 10px;">{evt_ts[-8:]}</span>
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

    def _render_liquidity_structure(self):
        """渲染流动性结构面板 - 美林时钟四象限"""
        if not self.engine:
            return

        report = self.engine.get_memory_report()
        narratives_data = report.get('narratives', {})
        narrative_summary = narratives_data.get('summary', [])

        liquidity_quadrants = {
            "股票市场": {"icon": "📈", "color": "#4ade80", "desc": "资金风险偏好"},
            "债券市场": {"icon": "📊", "color": "#60a5fa", "desc": "资金避险"},
            "大宗商品": {"icon": "🛢️", "color": "#f97316", "desc": "通胀预期"},
            "现金与货币": {"icon": "💵", "color": "#a855f7", "desc": "资金观望"},
        }

        related_narratives = {
            "贵金属": {"quadrant": "大宗商品", "icon": "🥇", "color": "#f97316"},
            "全球宏观": {"quadrant": "股票市场", "icon": "🌍", "color": "#4ade80"},
            "外汇与美元": {"quadrant": "现金与货币", "icon": "💱", "color": "#a855f7"},
            "流动性紧张": {"quadrant": "现金与货币", "icon": "⚠️", "color": "#f87171"},
        }

        quadrants_data = []
        for name in liquidity_quadrants.keys():
            found = None
            for nar in narrative_summary:
                if nar.get('narrative') == name:
                    found = nar
                    break
            quadrants_data.append({
                "name": name,
                "data": found,
            })

        stage_colors = {
            '萌芽': '#60a5fa',
            '扩散': '#818cf8',
            '高潮': '#f87171',
            '消退': '#fb923c',
        }

        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="font-size: 13px; font-weight: 600; color: #a855f7; margin-bottom: 4px;">
                💰 流动性结构（美林时钟四象限）
            </div>
            <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
                基于叙事活跃度判断资金流向 | 热度: 萌芽 → 扩散 → 高潮 → 消退
            </div>
        """)

        for q in quadrants_data:
            name = q["name"]
            info = liquidity_quadrants.get(name, {})
            icon = info.get("icon", "📊")
            base_color = info.get("color", "#60a5fa")
            desc = info.get("desc", "")

            if q["data"]:
                stage = q["data"].get('stage', '萌芽')
                attention = float(q["data"].get('attention_score', 0))
                recent_count = int(q["data"].get('recent_count', 0))
                trend = float(q["data"].get('trend', 0))
                stage_color = stage_colors.get(stage, '#60a5fa')
                bar_width = min(100, int(attention * 100))
                trend_icon = '↑' if trend > 0 else ('↓' if trend < 0 else '→')
                trend_color = '#4ade80' if trend > 0 else ('#f87171' if trend < 0 else '#6b7280')
            else:
                stage = "无数据"
                attention = 0
                recent_count = 0
                trend = 0
                stage_color = '#475569'
                bar_width = 0
                trend_icon = '?'
                trend_color = '#6b7280'

            trend_str = f"{trend_icon} {abs(trend):.2f}" if isinstance(trend, float) else f"{trend_icon}"

            put_html(f"""
            <div style="background: rgba(255,255,255,0.02); border-radius: 10px; padding: 12px; margin-bottom: 10px; border-left: 3px solid {base_color};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 16px;">{icon}</span>
                        <div>
                            <div style="font-size: 13px; font-weight: 600; color: #cbd5e1;">{name}</div>
                            <div style="font-size: 10px; color: #64748b;">{desc}</div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="padding: 2px 8px; background: {stage_color}; color: #0f172a; border-radius: 4px; font-size: 10px; font-weight: 600;">{stage}</span>
                        <span style="font-size: 11px; color: {trend_color}; font-weight: 600;">{trend_str}</span>
                        <span style="font-size: 10px; color: #475569;">{recent_count}次</span>
                    </div>
                </div>
                <div style="display: flex; height: 6px; border-radius: 4px; overflow: hidden; gap: 2px;">
                    <div style="flex: {bar_width}; background: linear-gradient(90deg, {base_color}, {base_color}dd); border-radius: 4px 0 0 4px;"></div>
                    <div style="flex: {100 - bar_width}; background: rgba(255,255,255,0.1); border-radius: 0 4px 4px 0;"></div>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 6px;">
                    <span style="font-size: 10px; color: #475569;">关注度 <b style="color: {base_color};">{attention:.2f}</b></span>
                    <span style="font-size: 10px; color: #64748b;">{bar_width}%</span>
                </div>
            </div>
            """)

        active_quadrants = [q["name"] for q in quadrants_data if q["data"] and q["data"].get("stage") in ("高潮", "扩散")]
        active_related = []
        for nar_name, nar_info in related_narratives.items():
            for nar in narrative_summary:
                if nar.get('narrative') == nar_name:
                    active_related.append({
                        "name": nar_name,
                        "icon": nar_info.get("icon", "📊"),
                        "stage": nar.get("stage", "萌芽"),
                        "attention": nar.get("attention_score", 0),
                        "quadrant": nar_info.get("quadrant", ""),
                    })
                    break

        if active_related:
            put_html("""
            <div style="margin-top: 14px; padding-top: 14px; border-top: 1px solid rgba(255,255,255,0.08);">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 10px;">相关宏观叙事</div>
                <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                """)
            for rel in active_related:
                stage_color = stage_colors.get(rel["stage"], "#60a5fa")
                put_html(f"""
                <div style="display: flex; align-items: center; gap: 6px; padding: 6px 10px; background: rgba(255,255,255,0.03); border-radius: 6px; border: 1px solid {stage_color}30;">
                    <span>{rel["icon"]}</span>
                    <span style="font-size: 11px; color: #cbd5e1;">{rel["name"]}</span>
                    <span style="padding: 1px 6px; background: {stage_color}; color: #0f172a; border-radius: 3px; font-size: 9px; font-weight: 600;">{rel["stage"]}</span>
                </div>
                """)
            put_html("</div></div>")

        liquidity_conclusion = ""
        if active_quadrants:
            if len(active_quadrants) >= 2:
                liquidity_conclusion = f"资金同时偏好: {', '.join(active_quadrants[:2])}"
            else:
                liquidity_conclusion = f"资金集中于: {active_quadrants[0]}"
        elif active_related:
            quadrant_map = {"大宗商品": "商品", "股票市场": "股市", "现金与货币": "货币"}
            related_quadrants = list(set([r["quadrant"] for r in active_related]))
            if len(related_quadrants) >= 2:
                liquidity_conclusion = f"宏观信号显示: {', '.join([quadrant_map.get(q, q) for q in related_quadrants[:2]])}偏强"
            else:
                q = related_quadrants[0] if related_quadrants else "未知"
                liquidity_conclusion = f"宏观信号显示: {quadrant_map.get(q, q)}偏强"
        else:
            no_data_quadrants = [q["name"] for q in quadrants_data if not q["data"]]
            if len(no_data_quadrants) == 4:
                liquidity_conclusion = "美林时钟象限暂无数据，关注叙事生命周期"
            else:
                all_fading = all(q["data"].get("stage") in ("消退", "萌芽") for q in quadrants_data if q["data"])
                if all_fading:
                    liquidity_conclusion = "所有象限处于低活跃，资金观望"
                else:
                    liquidity_conclusion = "象限数据收集中..."

        if liquidity_conclusion:
            put_html(f"""
            <div style="
                margin-top: 14px;
                padding: 10px 14px;
                background: rgba(168,85,247,0.1);
                border-radius: 8px;
                border: 1px solid rgba(168,85,247,0.3);
            ">
                <div style="font-size: 11px; color: #a855f7; font-weight: 600;">💡 流动性结论</div>
                <div style="font-size: 12px; color: #cbd5e1; margin-top: 4px;">{liquidity_conclusion}</div>
            </div>
            """)

        put_html('</div>')

    def _render_propagation_network(self):
        """渲染全球流动性传播网络"""
        if not self.engine:
            return

        try:
            newsmind = getattr(self.engine, '_news_mind', None)
            if not newsmind:
                return
            propagation_engine = getattr(newsmind, 'propagation_engine', None)
            if not propagation_engine:
                return
        except Exception:
            return

        structure = propagation_engine.get_liquidity_structure()
        if "error" in structure:
            return

        active_markets = structure.get("active_markets", [])
        markets = structure.get("markets", {})
        edges = structure.get("edges", {})

        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="font-size: 13px; font-weight: 600; color: #10b981; margin-bottom: 4px;">
                🌐 全球流动性传播网络
            </div>
            <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
                节点变化 → 沿边传播 → 验证结果 → 动态调权
            </div>
        """)

        if not active_markets:
            put_html("""
            <div style="text-align: center; padding: 20px; color: #64748b; font-size: 12px;">
                暂无活跃市场变化，等待数据流入...
            </div>
            """)
        else:
            put_html(f"""
            <div style="margin-bottom: 14px;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 8px;">活跃市场 ({len(active_markets)})</div>
                <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                """)
            for market_id in active_markets[:8]:
                m_info = markets.get(market_id, {})
                m_name = m_info.get("name", market_id)
                level = m_info.get("attention_level", "unknown")
                score = m_info.get("attention_score", 0)

                level_colors = {
                    "critical": "#ef4444",
                    "high": "#f97316",
                    "medium": "#eab308",
                    "low": "#22c55e",
                    "dormant": "#64748b",
                }
                color = level_colors.get(level, "#64748b")

                put_html(f"""
                <div style="
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    padding: 4px 10px;
                    background: {color}20;
                    border: 1px solid {color}50;
                    border-radius: 6px;
                ">
                    <span style="width: 8px; height: 8px; border-radius: 50%; background: {color};"></span>
                    <span style="font-size: 11px; color: #cbd5e1;">{m_name}</span>
                    <span style="font-size: 10px; color: {color};">{score:.2f}</span>
                </div>
                """)
            put_html("</div></div>")

        if edges:
            put_html("""
            <div style="margin-bottom: 14px;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 8px;">活跃传播路径</div>
                <div style="display: flex; flex-direction: column; gap: 6px;">
                """)
            for edge_key, e_info in sorted(edges.items(), key=lambda x: -x[1].get("current_weight", 0))[:5]:
                from_m = e_info.get("from_market", "")
                to_m = e_info.get("to_market", "")
                weight = e_info.get("current_weight", 0)
                conf = e_info.get("confidence", 0)
                delay = e_info.get("delay_hours", 0)
                rate = e_info.get("propagation_rate", 0)

                weight_color = "#10b981" if weight > 0.7 else ("#eab308" if weight > 0.4 else "#64748b")

                put_html(f"""
                <div style="
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    padding: 6px 10px;
                    background: rgba(255,255,255,0.02);
                    border-radius: 6px;
                    font-size: 11px;
                ">
                    <span style="color: #10b981;">{from_m}</span>
                    <span style="color: #64748b;">→</span>
                    <span style="color: #f97316;">{to_m}</span>
                    <span style="color: #475569;">|</span>
                    <span style="color: {weight_color};">强度 {weight:.2f}</span>
                    <span style="color: #64748b;">置信 {conf:.0%}</span>
                    <span style="color: #64748b;">延迟 {delay:.0f}h</span>
                </div>
                """)
            put_html("</div></div>")

        resonance_signals = propagation_engine.get_resonance_signals()
        if resonance_signals:
            put_html("""
            <div>
                <div style="font-size: 11px; color: #64748b; margin-bottom: 8px;">共振信号</div>
                <div style="display: flex; flex-direction: column; gap: 4px;">
                """)
            for sig in resonance_signals[:3]:
                name = sig.get("name", "")
                change = sig.get("change", 0)
                attention = sig.get("attention_score", 0)
                change_color = "#10b981" if change > 0 else "#ef4444"

                put_html(f"""
                <div style="
                    display: flex;
                    justify-content: space-between;
                    padding: 4px 8px;
                    background: rgba(255,255,255,0.02);
                    border-radius: 4px;
                    font-size: 11px;
                ">
                    <span style="color: #cbd5e1;">{name}</span>
                    <span style="color: {change_color};">{change:+.2f}%</span>
                    <span style="color: #64748b;">注意力 {attention:.2f}</span>
                </div>
                """)
            put_html("</div></div>")

        put_html('</div>')

    def _render_cross_signal_section(self):
        """渲染跨信号分析器 - 三种共振检测展示"""
        try:
            from .cross_signal_analyzer import get_cross_signal_analyzer, ResonanceType, SignalSource
            analyzer = get_cross_signal_analyzer()
            if not analyzer:
                return
        except Exception:
            return

        stats = analyzer.get_stats()
        recent_resonances = analyzer.get_recent_resonances(n=8)
        high_resonance_sectors = analyzer.get_high_resonance_sectors(threshold=0.7, n=5)
        market_resonance_summary = analyzer.get_market_resonance_summary()

        news_buffer_size = stats.get('news_buffer_size', 0)
        attention_buffer_size = stats.get('attention_buffer_size', 0)
        market_buffer_size = stats.get('market_buffer_size', 0)
        resonance_history_size = stats.get('resonance_history_size', 0)
        market_resonance_history_size = stats.get('market_resonance_history_size', 0)
        recent_resonance_count = stats.get('recent_resonance_count', 0)
        recent_market_resonance_count = stats.get('recent_market_resonance_count', 0)
        llm_cooldown_remaining = stats.get('llm_cooldown_remaining', 0)

        should_trigger_llm = analyzer.should_trigger_llm()
        llm_ready = "🔥 就绪" if should_trigger_llm else f"💤 冷却 ({int(llm_cooldown_remaining)}s)"

        resonance_type_colors = {
            "temporal": "#60a5fa",
            "intensity": "#f97316",
            "narrative": "#a855f7",
            "correlation": "#14b8a6",
        }

        market_resonance_type_colors = {
            "intensity": "#f97316",
            "macro": "#a855f7",
            "cross_market": "#14b8a6",
        }

        put_html("""
        <div style="
            margin-bottom: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(255,255,255,0.08);
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <div style="font-size: 13px; font-weight: 600; color: #f97316;">
                    🔄 跨信号分析（共振检测）
                </div>
                <div style="font-size: 10px; color: #475569;">
                    LLM层: {llm_ready}
                </div>
            </div>
            <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
                新闻 × 注意力 / 新闻 × 宏观叙事 / 市场 × 市场 → 三层共振
            </div>
        """.format(llm_ready=llm_ready))

        put_html(f"""
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 14px;">
            <div style="background: rgba(249,115,22,0.1); border: 1px solid rgba(249,115,22,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
                <div style="font-size: 11px; color: #fb923c; font-weight: 600;">📰 新闻缓冲</div>
                <div style="font-size: 9px; color: #94a3b8;">{news_buffer_size} 条</div>
            </div>
            <div style="background: rgba(168,85,247,0.1); border: 1px solid rgba(168,85,247,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
                <div style="font-size: 11px; color: #a855f7; font-weight: 600;">👁️ 注意力缓冲</div>
                <div style="font-size: 9px; color: #94a3b8;">{attention_buffer_size} 条</div>
            </div>
            <div style="background: rgba(20,184,166,0.1); border: 1px solid rgba(20,184,166,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
                <div style="font-size: 11px; color: #14b8a6; font-weight: 600;">📊 市场缓冲</div>
                <div style="font-size: 9px; color: #94a3b8;">{market_buffer_size} 条</div>
            </div>
        </div>
        """)

        put_html(f"""
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 14px;">
            <div style="background: rgba(96,165,250,0.12); border: 1px solid rgba(96,165,250,0.25); padding: 10px 14px; border-radius: 8px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 2px;">⚡ 板块共振历史</div>
                <div style="font-size: 18px; font-weight: 700; color: #60a5fa;">{resonance_history_size}</div>
                <div style="font-size: 9px; color: #94a3b8;">近1分钟: {recent_resonance_count}</div>
            </div>
            <div style="background: rgba(249,115,22,0.12); border: 1px solid rgba(249,115,22,0.25); padding: 10px 14px; border-radius: 8px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 2px;">🌐 市场共振历史</div>
                <div style="font-size: 18px; font-weight: 700; color: #fb923c;">{market_resonance_history_size}</div>
                <div style="font-size: 9px; color: #94a3b8;">近1分钟: {recent_market_resonance_count}</div>
            </div>
        </div>
        """)

        put_html("""
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 14px;">
            <div style="background: rgba(96,165,250,0.1); border: 1px solid rgba(96,165,250,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
                <div style="font-size: 11px; color: #60a5fa; font-weight: 600;">板块共振</div>
                <div style="font-size: 10px; color: #94a3b8;">新闻 × 注意力</div>
                <div style="font-size: 9px; color: #64748b; margin-top: 2px;">AI/芯片/新能源</div>
            </div>
            <div style="background: rgba(168,85,247,0.1); border: 1px solid rgba(168,85,247,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
                <div style="font-size: 11px; color: #a855f7; font-weight: 600;">宏观共振</div>
                <div style="font-size: 10px; color: #94a3b8;">新闻 × 宏观叙事</div>
                <div style="font-size: 9px; color: #64748b; margin-top: 2px;">流动性/全球宏观</div>
            </div>
            <div style="background: rgba(20,184,166,0.1); border: 1px solid rgba(20,184,166,0.2); padding: 8px 12px; border-radius: 8px; text-align: center;">
                <div style="font-size: 11px; color: #14b8a6; font-weight: 600;">市场共振</div>
                <div style="font-size: 10px; color: #94a3b8;">市场 × 市场</div>
                <div style="font-size: 9px; color: #64748b; margin-top: 2px;">纳斯达克×标普</div>
            </div>
        </div>
        """)

        if high_resonance_sectors:
            sector_bars = ""
            for sector_id, avg_score in high_resonance_sectors[:5]:
                bar_width = min(100, int(avg_score * 100))
                score_color = '#f87171' if avg_score >= 0.85 else ('#fb923c' if avg_score >= 0.7 else '#60a5fa')
                sector_bars += f'''
                <div style="margin-bottom: 6px;">
                    <div style="display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8; margin-bottom: 2px;">
                        <span style="color: #cbd5e1;">{sector_id}</span>
                        <span style="color: {score_color}; font-weight: 600;">{avg_score:.2f}</span>
                    </div>
                    <div style="height: 4px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden;">
                        <div style="width: {bar_width}%; height: 100%; background: linear-gradient(90deg, {score_color}, {score_color}cc); border-radius: 2px;"></div>
                    </div>
                </div>
                '''

            put_html(f"""
            <div style="
                margin-bottom: 12px;
                background: rgba(255,255,255,0.02);
                border-radius: 8px;
                padding: 12px;
            ">
                <div style="font-size: 11px; font-weight: 600; color: #f97316; margin-bottom: 8px;">
                    🔥 高共振板块
                </div>
                {sector_bars}
            </div>
            """)

        if recent_resonances:
            resonance_items = ""
            for res in recent_resonances[-6:]:
                res_type_color = resonance_type_colors.get(res.resonance_type.value, '#60a5fa')
                sentiment_icon = "📈" if res.news_sentiment > 0.2 else "📉" if res.news_sentiment < -0.2 else "📊"
                attention_icon = "🔥" if res.attention_weight > 0.6 else "⚡" if res.attention_weight > 0.3 else "💤"
                ts_str = format_timestamp(res.timestamp) if res.timestamp else "-"

                resonance_items += f"""
                <div style="display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: rgba(255,255,255,0.02); border-radius: 6px; margin-bottom: 4px; border-left: 2px solid {res_type_color};">
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-size: 11px; font-weight: 600; color: #cbd5e1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{res.sector_name or res.sector_id}</div>
                        <div style="font-size: 9px; color: #64748b;">{sentiment_icon} {res.news_sentiment:+.2f} {attention_icon} {res.attention_weight:.2f}</div>
                    </div>
                    <div style="text-align: right; flex-shrink: 0;">
                        <div style="font-size: 11px; font-weight: 600; color: {res_type_color};">{res.resonance_score:.2f}</div>
                        <div style="font-size: 9px; color: #475569;">{ts_str[-8:]}</div>
                    </div>
                </div>
                """

            put_html(f"""
            <div style="
                background: rgba(255,255,255,0.02);
                border-radius: 8px;
                padding: 12px;
            ">
                <div style="font-size: 11px; font-weight: 600; color: #64748b; margin-bottom: 8px;">
                    📋 最近共振信号
                </div>
                {resonance_items}
            </div>
            """)

        resonance_list = market_resonance_summary.get('共振列表', [])
        if resonance_list:
            market_resonance_items = ""
            for res in resonance_list[:6]:
                res_type_color = market_resonance_type_colors.get('intensity', '#f97316')
                change_str = f"{res['market_change']:+.1f}%" if isinstance(res['market_change'], (int, float)) else res.get('market_change', 'N/A')
                market_resonance_items += f"""
                <div style="display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: rgba(255,255,255,0.02); border-radius: 6px; margin-bottom: 4px; border-left: 2px solid {res_type_color};">
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-size: 11px; font-weight: 600; color: #cbd5e1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{res['market_name'] or res['market_index']}</div>
                        <div style="font-size: 9px; color: #64748b;">{res['narrative']} {change_str}</div>
                    </div>
                    <div style="text-align: right; flex-shrink: 0;">
                        <div style="font-size: 11px; font-weight: 600; color: {res_type_color};">{res['resonance_score']:.2f}</div>
                        <div style="font-size: 9px; color: #475569;">{res.get('stage', 'N/A')}</div>
                    </div>
                </div>
                """

            put_html(f"""
            <div style="
                background: rgba(255,255,255,0.02);
                border-radius: 8px;
                padding: 12px;
            ">
                <div style="font-size: 11px; font-weight: 600; color: #f97316; margin-bottom: 8px;">
                    🌐 市场共振信号
                </div>
                {market_resonance_items}
            </div>
            """)

        put_html("</div>")

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
