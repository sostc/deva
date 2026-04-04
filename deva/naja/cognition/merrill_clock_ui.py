"""
美林时钟 Web UI

展示当前经济周期状态、资产配置建议和历史数据
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
import json

from deva.naja.cognition.merrill_clock_engine import (
    get_merrill_clock_engine,
    MerrillClockPhase,
    PhaseSignal,
)
from deva.naja.cognition.merrill_clock_to_manas import (
    get_merrill_macro_signal,
    get_merrill_phase_display,
)

try:
    from deva.naja.cognition.ui import get_running_cognition_engine
except ImportError:
    get_running_cognition_engine = None


def _get_narrative_summary() -> List[Dict[str, Any]]:
    """获取叙事总结数据"""
    if not get_running_cognition_engine:
        return []
    try:
        engine = get_running_cognition_engine()
        if not engine:
            return []
        report = engine.get_memory_report()
        return report.get('narratives', {}).get('summary', [])
    except Exception:
        return []


# 四象限配置
QUADRANT_CONFIG = {
    MerrillClockPhase.RECOVERY: {
        "emoji": "🌱",
        "name": "复苏",
        "color": "#10b981",
        "bg": "#d1fae5",
        "border": "#6ee7b7",
        "description": "经济回升，通胀温和偏低",
        "stocks": "★★★★★",
        "bonds": "★★★☆☆",
        "commodities": "★★☆☆☆",
        "cash": "★★☆☆☆",
        "policy": "宽松货币政策，财政刺激",
    },
    MerrillClockPhase.OVERHEAT: {
        "emoji": "🔥",
        "name": "过热",
        "color": "#ef4444",
        "bg": "#fee2e2",
        "border": "#fca5a5",
        "description": "经济增长强劲，通胀上升压力",
        "stocks": "★★★☆☆",
        "bonds": "★★☆☆☆",
        "commodities": "★★★★★",
        "cash": "★★☆☆☆",
        "policy": "紧缩货币政策，收紧流动性",
    },
    MerrillClockPhase.STAGFLATION: {
        "emoji": "⚠️",
        "name": "滞胀",
        "color": "#f97316",
        "bg": "#ffedd5",
        "border": "#fdba74",
        "description": "增长放缓，通胀居高不下",
        "stocks": "★★☆☆☆",
        "bonds": "★★☆☆☆",
        "commodities": "★★★☆☆",
        "cash": "★★★★★",
        "policy": "两难境地，优先抗通胀",
    },
    MerrillClockPhase.RECESSION: {
        "emoji": "🥶",
        "name": "衰退",
        "color": "#6366f1",
        "bg": "#e0e7ff",
        "border": "#a5b4fc",
        "description": "经济收缩，通胀下行",
        "stocks": "★★☆☆☆",
        "bonds": "★★★★★",
        "commodities": "★★☆☆☆",
        "cash": "★★★☆☆",
        "policy": "宽松货币政策，财政兜底",
    },
}


def _get_phase_position(phase: MerrillClockPhase) -> tuple:
    """获取阶段在四象限图中的位置 (row, col)"""
    positions = {
        MerrillClockPhase.RECOVERY: (0, 0),      # 左上
        MerrillClockPhase.OVERHEAT: (0, 1),      # 右上
        MerrillClockPhase.STAGFLATION: (1, 1),   # 右下
        MerrillClockPhase.RECESSION: (1, 0),    # 左下
    }
    return positions.get(phase, (0, 0))


def _render_star_rating(rating: str) -> str:
    """渲染星级评分"""
    return f'<span style="font-size:14px;letter-spacing:-2px;">{rating}</span>'


def _render_quadrant_html(phase: MerrillClockPhase, config: Dict) -> str:
    """渲染单个象限"""
    is_active = True  # 未来可以判断历史中的阶段
    border_color = config["border"] if is_active else "#e5e7eb"
    opacity = "1.0" if is_active else "0.4"

    return f"""
    <div style="
        background: {config['bg']};
        border: 2px solid {border_color};
        border-radius: 16px;
        padding: 16px;
        opacity: {opacity};
        transition: all 0.3s;
    ">
        <div style="font-size: 28px; margin-bottom: 8px;">{config['emoji']}</div>
        <div style="font-size: 16px; font-weight: 700; color: {config['color']}; margin-bottom: 4px;">
            {config['name']}
        </div>
        <div style="font-size: 11px; color: #64748b; margin-bottom: 8px;">
            {config['description']}
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 11px;">
            <div>股票 {_render_star_rating(config['stocks'])}</div>
            <div>债券 {_render_star_rating(config['bonds'])}</div>
            <div>商品 {_render_star_rating(config['commodities'])}</div>
            <div>现金 {_render_star_rating(config['cash'])}</div>
        </div>
    </div>
    """


def _build_quadrant_map_html(current_phase: MerrillClockPhase) -> str:
    """构建美林时钟四象限图"""
    config = QUADRANT_CONFIG

    quadrants_html = ""
    positions = [
        [MerrillClockPhase.RECOVERY, MerrillClockPhase.OVERHEAT],
        [MerrillClockPhase.RECESSION, MerrillClockPhase.STAGFLATION],
    ]

    for row in positions:
        for phase in row:
            quadrants_html += _render_quadrant_html(phase, config[phase])

    arrow_style = ""
    if current_phase == MerrillClockPhase.RECOVERY:
        arrow = "→"
    elif current_phase == MerrillClockPhase.OVERHEAT:
        arrow = "↓"
    elif current_phase == MerrillClockPhase.STAGFLATION:
        arrow = "←"
    else:
        arrow = "↑"

    return f"""
    <div style="margin: 20px 0;">
        <div style="text-align: center; font-size: 12px; color: #64748b; margin-bottom: 12px;">
            增长 ↓ / ↑ 通胀 ← / →
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; max-width: 600px; margin: 0 auto;">
            {quadrants_html}
        </div>
        <div style="text-align: center; margin-top: 12px;">
            <span style="
                display: inline-block;
                background: linear-gradient(135deg, #fbbf24, #f97316);
                color: white;
                padding: 6px 16px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
            ">
                当前阶段: {QUADRANT_CONFIG[current_phase]['emoji']} {QUADRANT_CONFIG[current_phase]['name']}
            </span>
        </div>
    </div>
    """


def _build_data_summary_html(signal: PhaseSignal) -> str:
    """构建经济数据摘要"""
    summary = signal.data_summary or {}

    items = []
    for key, label in [
        ("GDP", "GDP同比"),
        ("PCE", "核心PCE"),
        ("PMI", "PMI"),
        ("非农", "非农就业"),
        ("失业率", "失业率"),
    ]:
        value = summary.get(key)
        if value is not None:
            items.append(f"<div><span style='color:#64748b;font-size:12px;'>{label}</span><br/><span style='font-weight:600;font-size:14px;'>{value}</span></div>")

    if not items:
        items.append("<div style='color:#94a3b8;font-size:12px;'>暂无数据</div>")

    return f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 12px; margin: 16px 0;">
        {''.join(items)}
    </div>
    """


def _build_asset_ranking_html(ranking: List[str]) -> str:
    """构建资产配置排名"""
    emoji_map = {
        "商品": "📦",
        "股票": "📈",
        "债券": "📉",
        "现金": "💵",
    }

    bars = ""
    for i, asset in enumerate(ranking):
        emoji = emoji_map.get(asset, "📊")
        width = 100 - i * 20
        bars += f"""
        <div style="margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                <span style="font-weight: 600; font-size: 13px;">{emoji} {asset}</span>
                <span style="font-size: 11px; color: #64748b;">{'最优' if i == 0 else f'第{i+1}'}</span>
            </div>
            <div style="background: #e2e8f0; border-radius: 4px; height: 8px; overflow: hidden;">
                <div style="
                    background: linear-gradient(90deg, #10b981, #34d399);
                    height: 100%;
                    width: {width}%;
                    border-radius: 4px;
                    transition: width 0.5s;
                "></div>
            </div>
        </div>
        """

    return bars


LIQUIDITY_QUADRANTS = {
    "股票市场": {"icon": "📈", "color": "#4ade80", "desc": "资金风险偏好"},
    "债券市场": {"icon": "📊", "color": "#60a5fa", "desc": "资金避险"},
    "大宗商品": {"icon": "🛢️", "color": "#f97316", "desc": "通胀预期"},
    "现金与货币": {"icon": "💵", "color": "#a855f7", "desc": "资金观望"},
}

STAGE_COLORS = {
    '萌芽': '#60a5fa',
    '扩散': '#818cf8',
    '高潮': '#f87171',
    '消退': '#fb923c',
}


def _build_liquidity_overlay_html(ctx: dict, narrative_summary: List[Dict], current_phase: MerrillClockPhase) -> None:
    """构建可折叠的叙事热度叠加层 - 挂在美林时钟框架上"""
    if not narrative_summary:
        return

    quadrants_data = []
    for name, info in LIQUIDITY_QUADRANTS.items():
        found = None
        for nar in narrative_summary:
            if nar.get('narrative') == name:
                found = nar
                break
        quadrants_data.append({
            "name": name,
            "info": info,
            "data": found,
        })

    quadrant_items_html = ""
    for q in quadrants_data:
        name = q["name"]
        info = q["info"]
        icon = info["icon"]
        base_color = info["color"]

        if q["data"]:
            stage = q["data"].get('stage', '萌芽')
            attention = float(q["data"].get('attention_score', 0))
            recent_count = int(q["data"].get('recent_count', 0))
            trend = float(q["data"].get('trend', 0))
            stage_color = STAGE_COLORS.get(stage, '#60a5fa')
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

        quadrant_items_html += f"""
        <div style="background: rgba(255,255,255,0.5); border-radius: 10px; padding: 10px 12px; margin-bottom: 8px; border-left: 3px solid {base_color};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 14px;">{icon}</span>
                    <span style="font-size: 12px; font-weight: 600; color: #374151;">{name}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="padding: 2px 6px; background: {stage_color}; color: #0f172a; border-radius: 4px; font-size: 9px; font-weight: 600;">{stage}</span>
                    <span style="font-size: 10px; color: {trend_color}; font-weight: 600;">{trend_str}</span>
                    <span style="font-size: 9px; color: #6b7280;">{recent_count}次</span>
                </div>
            </div>
            <div style="display: flex; height: 5px; border-radius: 3px; overflow: hidden; gap: 2px;">
                <div style="flex: {bar_width}; background: linear-gradient(90deg, {base_color}, {base_color}cc); border-radius: 3px 0 0 3px;"></div>
                <div style="flex: {100 - bar_width}; background: #e5e7eb; border-radius: 0 3px 3px 0;"></div>
            </div>
            <div style="display: flex; justify-content: space-between; margin-top: 4px;">
                <span style="font-size: 9px; color: #6b7280;">关注度 <b style="color: {base_color};">{attention:.2f}</b></span>
                <span style="font-size: 9px; color: #9ca3af;">{bar_width}%</span>
            </div>
        </div>
        """

    active_quadrants = [q["name"] for q in quadrants_data if q["data"] and q["data"].get("stage") in ("高潮", "扩散")]
    liquidity_conclusion = ""
    if active_quadrants:
        if len(active_quadrants) >= 2:
            liquidity_conclusion = f"资金同时偏好: {', '.join(active_quadrants[:2])}"
        else:
            liquidity_conclusion = f"资金集中于: {active_quadrants[0]}"
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

    ctx["put_html"](f"""
    <div style="
        background: linear-gradient(135deg, #faf5ff 0%, #fff 100%);
        border: 1px solid #e9d5ff;
        border-radius: 16px;
        padding: 16px;
        margin: 20px 0;
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; cursor: pointer; margin-bottom: 0;"
             onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'; this.querySelector('.arrow').textContent = this.nextElementSibling.style.display === 'none' ? '▶' : '▼';">
            <div>
                <div style="font-size: 14px; font-weight: 700; color: #7c3aed; margin-bottom: 2px;">
                    📰 新闻热度叠加层
                </div>
                <div style="font-size: 11px; color: #6b7280;">
                    热度: 萌芽 → 扩散 → 高潮 → 消退 | 资金流向实时反映新闻焦点
                </div>
            </div>
            <div style="font-size: 12px; color: #7c3aed;">
                <span class="arrow" style="font-size: 10px;">▼</span> 展开/收起
            </div>
        </div>
        <div style="margin-top: 12px;">
            {quadrant_items_html}
            <div style="
                margin-top: 12px;
                padding: 10px 12px;
                background: rgba(168,85,247,0.1);
                border-radius: 8px;
                border: 1px solid rgba(168,85,247,0.2);
            ">
                <div style="font-size: 10px; color: #7c3aed; font-weight: 600;">💡 流动性结论</div>
                <div style="font-size: 12px; color: #4b5563; margin-top: 4px;">{liquidity_conclusion}</div>
            </div>
        </div>
    </div>
    """)


async def render_merrill_clock_page(ctx: dict):
    """渲染美林时钟主页面"""
    try:
        clock = get_merrill_clock_engine()
        signal = clock.get_current_signal()
        history = clock.get_history(limit=5)
        summary = clock.get_summary()
    except Exception as e:
        ctx["put_html"](f"""
        <div style="padding: 24px; text-align: center; color: #ef4444;">
            <div style="font-size: 48px; margin-bottom: 12px;">❌</div>
            <div style="font-size: 14px;">加载美林时钟失败: {str(e)}</div>
        </div>
        """)
        return

    # 页面头部
    ctx["put_html"]("""
    <div style="margin: 24px 0;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
            <span style="font-size: 28px;">🕐</span>
            <h1 style="font-size: 22px; font-weight: 700; color: #1e293b; margin: 0;">
                美林时钟 · 经济周期
            </h1>
        </div>
        <div style="font-size: 13px; color: #64748b;">
            基于 FRED 真实经济数据的周期性判断，驱动 Manas 宏观信号
        </div>
    </div>
    """)

    if not signal:
        ctx["put_html"]("""
        <div style="
            background: linear-gradient(135deg, #fef3c7, #fde68a);
            border: 1px solid #fcd34d;
            border-radius: 16px;
            padding: 32px;
            text-align: center;
            margin: 20px 0;
        ">
            <div style="font-size: 48px; margin-bottom: 12px;">🌙</div>
            <div style="font-size: 16px; font-weight: 600; color: #92400e; margin-bottom: 8px;">
                暂无经济数据
            </div>
            <div style="font-size: 13px; color: #a16207;">
                经济数据每日凌晨 4:30 自动更新，或手动触发更新任务
            </div>
        </div>
        """)
        return

    # 当前阶段卡片
    phase_config = QUADRANT_CONFIG.get(signal.phase, {})
    phase_name = get_merrill_phase_display(signal.phase)
    macro_signal = get_merrill_macro_signal(phase=signal.phase, confidence=signal.confidence)

    # 信号强度条
    signal_bar_width = int(signal.confidence * 100)
    signal_bar_color = "#10b981" if signal.confidence > 0.6 else "#f97316" if signal.confidence > 0.4 else "#ef4444"

    ctx["put_html"](f"""
    <div style="
        background: linear-gradient(135deg, {phase_config.get('bg', '#f1f5f9')} 0%, #fff 100%);
        border: 2px solid {phase_config.get('border', '#e5e7eb')};
        border-radius: 20px;
        padding: 24px;
        margin: 20px 0;
    ">
        <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px;">
            <div style="font-size: 48px;">{phase_config.get('emoji', '❓')}</div>
            <div>
                <div style="font-size: 28px; font-weight: 800; color: {phase_config.get('color', '#1e293b')};">
                    {phase_name}
                </div>
                <div style="font-size: 13px; color: #64748b; margin-top: 2px;">
                    {phase_config.get('description', '')}
                </div>
            </div>
        </div>

        <!-- 信号质量条 -->
        <div style="margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                <span style="font-size: 12px; color: #64748b;">置信度</span>
                <span style="font-size: 12px; font-weight: 600; color: {signal_bar_color};">
                    {signal.confidence:.0%}
                </span>
            </div>
            <div style="background: #e2e8f0; border-radius: 6px; height: 10px; overflow: hidden;">
                <div style="
                    background: linear-gradient(90deg, {signal_bar_color}, {'#34d399' if signal.confidence > 0.6 else '#fb923c'});
                    height: 100%;
                    width: {signal_bar_width}%;
                    border-radius: 6px;
                "></div>
            </div>
        </div>

        <!-- 核心指标 -->
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px;">
            <div style="text-align: center; padding: 12px; background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">增长评分</div>
                <div style="font-size: 20px; font-weight: 700; color: {'#10b981' if signal.growth_score > 0 else '#ef4444'};">
                    {signal.growth_score:+.2f}
                </div>
            </div>
            <div style="text-align: center; padding: 12px; background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">通胀评分</div>
                <div style="font-size: 20px; font-weight: 700; color: {'#ef4444' if signal.inflation_score > 0 else '#10b981'};">
                    {signal.inflation_score:+.2f}
                </div>
            </div>
            <div style="text-align: center; padding: 12px; background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">Manas信号</div>
                <div style="font-size: 20px; font-weight: 700; color: {'#10b981' if macro_signal > 0.5 else '#ef4444'};">
                    {macro_signal:.2f}
                </div>
            </div>
            <div style="text-align: center; padding: 12px; background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">数据更新</div>
                <div style="font-size: 14px; font-weight: 700; color: #64748b;">
                    {datetime.fromtimestamp(signal.timestamp).strftime('%m-%d %H:%M') if signal.timestamp else '未知'}
                </div>
            </div>
        </div>

        <!-- 政策建议 -->
        <div style="background: white; border-radius: 12px; padding: 12px 16px; margin-bottom: 12px;">
            <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">货币政策</div>
            <div style="font-size: 13px; font-weight: 500; color: #1e293b;">
                {phase_config.get('policy', '暂无建议')}
            </div>
        </div>
    </div>
    """)

    # 四象限图
    ctx["put_html"](f"""
    <div style="
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 20px;
        margin: 20px 0;
    ">
        <div style="font-size: 15px; font-weight: 700; color: #1e293b; margin-bottom: 16px;">
            📊 美林时钟四象限
        </div>
        {_build_quadrant_map_html(signal.phase)}
    </div>
    """)

    # 新闻热度叠加层 - 可折叠
    narrative_summary = _get_narrative_summary()
    if narrative_summary:
        _build_liquidity_overlay_html(ctx, narrative_summary, signal.phase)

    # 资产配置
    if signal.asset_ranking:
        ctx["put_html"](f"""
        <div style="
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 20px;
            margin: 20px 0;
        ">
            <div style="font-size: 15px; font-weight: 700; color: #1e293b; margin-bottom: 16px;">
                💼 资产配置建议
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                <div>
                    {_build_asset_ranking_html(signal.asset_ranking)}
                </div>
                <div>
                    <div style="font-size: 13px; font-weight: 600; color: #1e293b; margin-bottom: 8px;">
                        超配方向
                    </div>
                    <div style="font-size: 12px; color: #64748b;">
                        {''.join([f'<div style="margin-bottom: 4px;">• {item}</div>' for item in (signal.overweight or [])]) or '<div style="color:#94a3b8;">暂无</div>'}
                    </div>
                    <div style="font-size: 13px; font-weight: 600; color: #1e293b; margin: 12px 0 8px;">
                        低配方向
                    </div>
                    <div style="font-size: 12px; color: #64748b;">
                        {''.join([f'<div style="margin-bottom: 4px;">• {item}</div>' for item in (signal.underweight or [])]) or '<div style="color:#94a3b8;">暂无</div>'}
                    </div>
                </div>
            </div>
            <div style="margin-top: 12px; padding: 12px; background: #f8fafc; border-radius: 8px;">
                <div style="font-size: 12px; color: #64748b; margin-bottom: 4px;">判断理由</div>
                <div style="font-size: 13px; color: #1e293b;">{signal.reason or '暂无'}</div>
            </div>
        </div>
        """)

    # 经济数据
    if signal.data_summary:
        ctx["put_html"](f"""
        <div style="
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 20px;
            margin: 20px 0;
        ">
            <div style="font-size: 15px; font-weight: 700; color: #1e293b; margin-bottom: 16px;">
                📈 经济数据摘要
            </div>
            {_build_data_summary_html(signal)}
        </div>
        """)

    # 历史记录
    if history and len(history) > 1:
        history_items = []
        for h in reversed(history):
            h_config = QUADRANT_CONFIG.get(h.phase, {})
            history_items.append(f"""
            <div style="display: flex; align-items: center; padding: 8px 0; border-bottom: 1px solid #f1f5f9;">
                <span style="font-size: 18px; margin-right: 8px;">{h_config.get('emoji', '❓')}</span>
                <span style="font-weight: 600; color: {h_config.get('color', '#64748b')}; margin-right: 8px;">
                    {h.phase.value}
                </span>
                <span style="font-size: 11px; color: #94a3b8;">
                    {datetime.fromtimestamp(h.timestamp).strftime('%m-%d %H:%M')}
                </span>
            </div>
            """)

        ctx["put_html"](f"""
        <div style="
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 20px;
            margin: 20px 0;
        ">
            <div style="font-size: 15px; font-weight: 700; color: #1e293b; margin-bottom: 8px;">
                📜 历史周期
            </div>
            {''.join(history_items)}
        </div>
        """)
