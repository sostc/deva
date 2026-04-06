"""
Narrative Web UI - 叙事追踪独立页面

展示叙事生命周期、供应链联动和历史叙事
"""

from typing import Dict, Any, List, Optional
import json

from ..tracker import get_narrative_tracker, NarrativeTracker
from ..supply_chain_linker import get_supply_chain_linker, NarrativeSupplyChainLinker
from .lifecycle import render_narrative_lifecycle
from .svg import render_narrative_svg

try:
    from deva.naja.cognition.ui import get_running_cognition_engine
except ImportError:
    get_running_cognition_engine = None


def _render_lifecycle_summary(tracker: NarrativeTracker) -> str:
    """渲染生命周期摘要"""
    try:
        active = tracker.get_active_narratives()
        if not active:
            return '<div style="color:#64748b;font-size:13px;">暂无活跃叙事</div>'

        html_parts = ['<div style="display:flex;flex-wrap:wrap;gap:8px;">']
        for item in active[:6]:
            name = item.get('narrative', '未知')
            stage = item.get('stage', '未知')
            score = item.get('attention_score', 0.5)

            stage_colors = {
                '萌芽': '#60a5fa',
                '扩散': '#818cf8',
                '高潮': '#f87171',
                '消退': '#fb923c',
            }
            color = stage_colors.get(stage, '#60a5fa')

            html_parts.append(f'''
            <div style="
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-left: 3px solid {color};
                border-radius: 8px;
                padding: 10px 14px;
                min-width: 140px;
            ">
                <div style="font-size:13px;font-weight:600;color:#f1f5f9;margin-bottom:4px;">{name}</div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <span style="
                        background: {color}22;
                        color: {color};
                        padding: 2px 8px;
                        border-radius: 4px;
                        font-size: 11px;
                    ">{stage}</span>
                    <span style="color:#94a3b8;font-size:11px;">{score:.1f}</span>
                </div>
            </div>
            ''')
        html_parts.append('</div>')
        return ''.join(html_parts)
    except Exception as e:
        return f'<div style="color:#ef4444;font-size:13px;">加载失败: {str(e)}</div>'


def _render_supply_chain_summary(linker: NarrativeSupplyChainLinker) -> str:
    """渲染供应链联动摘要"""
    try:
        impacts = linker.get_recent_impacts(limit=5)
        if not impacts:
            return '<div style="color:#64748b;font-size:13px;">暂无供应链联动</div>'

        html_parts = ['<div style="display:flex;flex-direction:column;gap:8px;">']
        for impact in impacts:
            symbol = impact.get('symbol', '')
            risk = impact.get('risk_level', 'LOW')
            change = impact.get('narrative_change', 0)

            risk_colors = {
                'HIGH': '#ef4444',
                'MEDIUM': '#f97316',
                'LOW': '#10b981'
            }
            color = risk_colors.get(risk, '#10b981')

            html_parts.append(f'''
            <div style="
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 6px;
                padding: 8px 12px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            ">
                <span style="font-weight:600;color:#f1f5f9;">{symbol}</span>
                <div style="display:flex;align-items:center;gap:8px;">
                    <span style="color:#94a3b8;font-size:11px;">变化 {change:+.1f}</span>
                    <span style="
                        background: {color}22;
                        color: {color};
                        padding: 2px 6px;
                        border-radius: 4px;
                        font-size: 10px;
                    ">{risk}</span>
                </div>
            </div>
            ''')
        html_parts.append('</div>')
        return ''.join(html_parts)
    except Exception as e:
        return f'<div style="color:#ef4444;font-size:13px;">加载失败: {str(e)}</div>'


async def render_narrative_page(ctx: dict):
    """渲染叙事追踪主页面"""

    tracker = get_narrative_tracker()
    linker = get_supply_chain_linker()

    ctx["put_html"]("""
    <div style="margin: 24px 0;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
            <span style="font-size: 28px;">📖</span>
            <h1 style="font-size: 22px; font-weight: 700; color: #1e293b; margin: 0;">
                叙事追踪 · 天-地框架
            </h1>
        </div>
        <div style="font-size: 13px; color: #64748b;">
            外部新闻叙事追踪 + 时机感知，驱动 Manas 交易决策
        </div>
    </div>
    """)

    ctx["put_html"]("""
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 20px 0;">
        <div style="
            background: linear-gradient(135deg, rgba(99,102,241,0.1), rgba(139,92,246,0.1));
            border: 1px solid rgba(139,92,246,0.2);
            border-radius: 16px;
            padding: 20px;
        ">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
                <span style="font-size:18px;">🌍</span>
                <span style="font-size:15px;font-weight:600;color:#a78bfa;">外部叙事</span>
            </div>
            <div style="color:#94a3b8;font-size:12px;margin-bottom:12px;">
                基于外部新闻和事件追踪市场叙事演化
            </div>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
                <a href="/narrative_lifecycle" style="
                    background: linear-gradient(135deg, #6366f1, #8b5cf6);
                    color: white;
                    padding: 8px 16px;
                    border-radius: 8px;
                    font-size: 12px;
                    text-decoration: none;
                    font-weight: 500;
                ">查看完整生命周期 →</a>
            </div>
        </div>

        <div style="
            background: linear-gradient(135deg, rgba(245,158,11,0.1), rgba(249,115,22,0.1));
            border: 1px solid rgba(249,115,22,0.2);
            border-radius: 16px;
            padding: 20px;
        ">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
                <span style="font-size:18px;">⏰</span>
                <span style="font-size:15px;font-weight:600;color:#f59e0b;">时机感知</span>
            </div>
            <div style="color:#94a3b8;font-size:12px;margin-bottom:12px;">
                叙事阶段判断和转换时机识别
            </div>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
                <span style="
                    background: rgba(245,158,11,0.2);
                    color: #f59e0b;
                    padding: 8px 16px;
                    border-radius: 8px;
                    font-size: 12px;
                ">阶段分析进行中</span>
            </div>
        </div>

        <div style="
            background: linear-gradient(135deg, rgba(16,185,129,0.1), rgba(6,182,212,0.1));
            border: 1px solid rgba(16,185,129,0.2);
            border-radius: 16px;
            padding: 20px;
        ">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
                <span style="font-size:18px;">⛓️</span>
                <span style="font-size:15px;font-weight:600;color:#10b981;">供应链联动</span>
            </div>
            <div style="color:#94a3b8;font-size:12px;margin-bottom:12px;">
                叙事变化对供应链股票的影响分析
            </div>
        </div>
    </div>
    """)

    if tracker:
        summary_html = _render_lifecycle_summary(tracker)
        ctx["put_html"](f"""
        <div style="
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 20px;
            margin: 16px 0;
        ">
            <div style="font-size:14px;font-weight:600;color:#a78bfa;margin-bottom:16px;">
                📊 活跃叙事 ({len(tracker.get_active_narratives()) if hasattr(tracker, 'get_active_narratives') else '?'})
            </div>
            {summary_html}
        </div>
        """)

    ctx["put_html"]("""
    <div style="margin-top: 24px; padding-top: 24px; border-top: 1px solid rgba(255,255,255,0.08);">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
            <span style="font-size: 16px;">📈</span>
            <span style="font-size: 14px; font-weight: 600; color: #f1f5f9;">数据来源</span>
        </div>
        <div style="color: #64748b; font-size: 12px;">
            外部叙事数据来自 NewsAPI 和财经新闻聚合 · 每日更新
        </div>
    </div>
    """)


async def render_narrative_lifecycle_page(ctx: dict):
    """渲染叙事生命周期详细页面"""
    tracker = get_narrative_tracker()

    ctx["put_html"]("""
    <div style="margin: 24px 0;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
            <a href="/narrative" style="
                color: #6366f1;
                text-decoration: none;
                font-size: 13px;
            ">← 叙事概览</a>
        </div>
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
            <span style="font-size: 28px;">🌍</span>
            <h1 style="font-size: 22px; font-weight: 700; color: #1e293b; margin: 0;">
                叙事生命周期
            </h1>
        </div>
        <div style="font-size: 13px; color: #64748b;">
            外部叙事追踪：萌芽 → 扩散 → 高潮 → 消退
        </div>
    </div>
    """)

    if not tracker:
        ctx["put_html"]("""
        <div style="
            background: rgba(245,158,11,0.1);
            border: 1px solid rgba(245,158,11,0.2);
            border-radius: 12px;
            padding: 32px;
            text-align: center;
        ">
            <div style="font-size: 48px; margin-bottom: 12px;">⏳</div>
            <div style="font-size: 14px; color: #f59e0b;">
                NarrativeTracker 初始化中，请稍后刷新页面
            </div>
        </div>
        """)
        return

    class _FakeUI:
        def __init__(self, ctx, engine):
            self.ctx = ctx
            self.engine = engine
        def put_html(self, html):
            self.ctx["put_html"](html)
        def _render_narrative_svg(self, nodes, edges):
            return render_narrative_svg(nodes, edges)

    from deva.naja.cognition.engine import get_cognition_engine
    fake_ui = _FakeUI(ctx, get_cognition_engine())
    render_narrative_lifecycle(fake_ui)
