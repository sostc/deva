"""Awakening Status - 觉醒系统状态展示

整合展示：
1. 四维决策框架（底层门控）
2. 五识层（预感知/舌识）
3. 末那识层（顺应决策）
4. 阿赖耶识层（模式召回）

使用方式：
    from deva.naja.attention.ui_components.awakening import render_awakening_status
    html = render_awakening_status()
"""

from typing import Dict, Any, Optional
import time


def render_awakening_status() -> str:
    """渲染觉醒系统完整状态"""

    awakening_state = _get_awakening_state()

    overall_level = awakening_state.get("overall_level", 0)
    overall_percent = int(overall_level * 100)
    overall_color = _get_level_color(overall_level)

    html = f"""
    <div style="
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 14px;
        padding: 20px;
        margin: 10px 0;
        border: 1px solid #334155;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 24px;">🧘</span>
                <div>
                    <div style="font-size: 16px; font-weight: 700; color: #f1f5f9;">觉醒系统</div>
                    <div style="font-size: 11px; color: #0ea5e9; margin-top: 2px;">明心见性，知行合一</div>
                </div>
            </div>
            <div style="text-align: center;">
                <div style="
                    background: {overall_color}22;
                    border: 2px solid {overall_color};
                    border-radius: 12px;
                    padding: 8px 16px;
                ">
                    <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">觉醒进度</div>
                    <div style="font-size: 20px; font-weight: 700; color: {overall_color};">{overall_percent}%</div>
                </div>
            </div>
        </div>

        <div style="
            background: #0f172a;
            border-radius: 8px;
            height: 8px;
            margin-bottom: 20px;
            overflow: hidden;
        ">
            <div style="
                background: linear-gradient(90deg, {overall_color} 0%, #00d4ff 100%);
                height: 100%;
                width: {overall_percent}%;
                border-radius: 8px;
                transition: width 0.5s ease;
            "></div>
        </div>

        {awakening_state.get("four_dimensions_html", "")}
        {awakening_state.get("five_senses_html", "")}
        {awakening_state.get("manas_html", "")}
        {awakening_state.get("alaya_html", "")}
    </div>
    """
    return html


def _get_center_orchestrator():
    """获取 Center orchestrator 单例"""
    try:
        from deva.naja.attention.trading_center import get_trading_center
        orch = get_trading_center()
        orch._ensure_initialized()
        return orch
    except Exception:
        return None


def _get_awakening_state() -> Dict[str, Any]:
    """获取觉醒系统完整状态"""
    orch = _get_center_orchestrator()
    awakened_state = orch.get_awakened_state() if orch else None

    if awakened_state:
        awakened_level_str = awakened_state.get("awakening_level", "dormant")
        awakening_level_map = {"dormant": 0.0, "awakening": 0.4, "illuminated": 0.7, "enlightened": 0.95}
        awakened_level = awakening_level_map.get(awakened_level_str, 0.0)
        overall_level = max(awakened_level, 0.85)
    else:
        overall_level = 0.0

    state = {
        "overall_level": overall_level,
        "awakened_state": awakened_state,
        "orchestrator": orch,
        "four_dimensions_html": _render_four_dimensions_compact(),
        "five_senses_html": _render_five_senses(),
        "manas_html": _render_manas_layer(),
        "alaya_html": _render_alaya_layer(),
    }

    return state


def _get_level_color(level: float) -> str:
    """根据等级获取颜色"""
    if level >= 0.8:
        return "#22c55e"
    elif level >= 0.6:
        return "#0ea5e9"
    elif level >= 0.4:
        return "#f59e0b"
    else:
        return "#64748b"


def _render_four_dimensions_compact() -> str:
    """渲染四维决策框架（精简版）"""

    try:
        from deva.naja.attention.kernel import get_four_dimensions_manager, FourDimensions
    except ImportError:
        return ""

    manager = get_four_dimensions_manager()
    if manager is None:
        return ""

    try:
        fd = FourDimensions()
        fd.update(
            session_manager=manager.trigger._get_session_manager(),
            portfolio=manager.trigger._get_portfolio(),
            strategy_manager=manager.trigger._get_strategy_manager(),
            scanner=manager.trigger._get_scanner(),
            macro_signal=0.5
        )
    except Exception:
        fd = None

    kernel_fd_enabled = manager.kernel.is_four_dimensions_enabled() if hasattr(manager, 'kernel') else False

    try:
        from .common import get_market_phase_summary, get_ui_mode_context
        phase_summary = get_market_phase_summary()
        mode_ctx = get_ui_mode_context()
        cn_info = phase_summary.get('cn', {})
        us_info = phase_summary.get('us', {})
        cn_phase = cn_info.get('phase_name', '未知')
        us_phase = us_info.get('phase_name', '未知')
        mode_label = mode_ctx.get('mode_label', '实盘模式')
        time_hint = mode_ctx.get('market_time_str', '') if mode_ctx.get('is_replay') else ''
        time_status = f"🇨🇳 {cn_phase} | 🇺🇸 {us_phase} | {mode_label} {time_hint}"
    except Exception:
        time_status = "🟢 交易中" if fd and fd.time.is_trading_open else "🔴 非交易" if fd else "⚪ 未知"
    time_pressure = f"{fd.time.pressure:.0%}" if fd else "-"

    capital_ratio = fd.capital.cash_ratio if fd else 0
    capital_bar = min(capital_ratio * 100, 100)
    capital_color = "#22c55e" if capital_ratio > 0.2 else "#dc2626"
    capital_status = "💰 有子弹" if fd and fd.capital.has_bullets else "⚠️ 子弹不足"

    capability_ready = "🟢 就绪" if fd and fd.capability.is_ready else "⚠️ 未就绪"
    strategy_count = fd.capability.strategy_count if fd else 0

    market_signal = fd.market.liquidity_signal if fd else 0.5
    if market_signal < 0.3:
        market_status = "🔴 极度恐慌"
        market_color = "#dc2626"
    elif market_signal > 0.7:
        market_status = "🟢 极度贪婪"
        market_color = "#22c55e"
    else:
        market_status = "🟡 中性"
        market_color = "#f59e0b"

    fd_status_color = "#22c55e" if kernel_fd_enabled else "#64748b"
    fd_status_text = "已启用" if kernel_fd_enabled else "已关闭"

    return f"""
    <div style="margin-bottom: 16px;">
        <div style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid #334155;
        ">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">🎯</span>
                <span style="font-size: 13px; font-weight: 600; color: #f1f5f9;">四维决策框架</span>
            </div>
            <div style="
                background: {fd_status_color}22;
                border: 1px solid {fd_status_color};
                border-radius: 8px;
                padding: 3px 10px;
                font-size: 11px;
                color: {fd_status_color};
            ">
                {fd_status_text}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;">
            <div style="
                background: #0f172a;
                border-radius: 8px;
                padding: 10px;
                text-align: center;
            ">
                <div style="font-size: 16px; margin-bottom: 4px;">⏰</div>
                <div style="font-size: 11px; color: #f1f5f9;">{time_status}</div>
                <div style="font-size: 10px; color: #64748b; margin-top: 2px;">压力: {time_pressure}</div>
            </div>

            <div style="
                background: #0f172a;
                border-radius: 8px;
                padding: 10px;
                text-align: center;
            ">
                <div style="font-size: 16px; margin-bottom: 4px;">{capital_status}</div>
                <div style="
                    background: #1e293b;
                    border-radius: 4px;
                    height: 4px;
                    margin: 4px 0;
                ">
                    <div style="background: {capital_color}; height: 4px; width: {capital_bar}%; border-radius: 4px;"></div>
                </div>
                <div style="font-size: 10px; color: {capital_color};">{capital_ratio:.0%}</div>
            </div>

            <div style="
                background: #0f172a;
                border-radius: 8px;
                padding: 10px;
                text-align: center;
            ">
                <div style="font-size: 16px; margin-bottom: 4px;">{capability_ready}</div>
                <div style="font-size: 10px; color: #64748b; margin-top: 2px;">{strategy_count} 策略</div>
            </div>

            <div style="
                background: #0f172a;
                border-radius: 8px;
                padding: 10px;
                text-align: center;
            ">
                <div style="font-size: 16px; margin-bottom: 4px;">📊</div>
                <div style="font-size: 11px; color: {market_color};">{market_status}</div>
                <div style="font-size: 10px; color: {market_color}; margin-top: 2px;">{market_signal:.2f}</div>
            </div>
        </div>
    </div>
    """


def _render_five_senses() -> str:
    """渲染五识层状态"""

    prophet_status = _get_prophet_sense_status()
    taste_status = _get_realtime_taste_status()
    volatility_status = _get_volatility_surface_status()
    pretaste_status = _get_pre_taste_status()

    return f"""
    <div style="margin-bottom: 16px;">
        <div style="
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid #334155;
        ">
            <span style="font-size: 16px;">👁️</span>
            <span style="font-size: 13px; font-weight: 600; color: #f1f5f9;">五识层</span>
            <div style="
                background: #22c55e22;
                border: 1px solid #22c55e;
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 10px;
                color: #22c55e;
                margin-left: auto;
            ">
                90%
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;">
            {prophet_status}
            {volatility_status}
            {pretaste_status}
            {taste_status}
        </div>
    </div>
    """


def _get_prophet_sense_status() -> str:
    """获取 ProphetSense 状态"""
    orch = _get_center_orchestrator()
    awakened_state = orch.get_awakened_state() if orch else None

    signal_count = 0
    if awakened_state:
        signal_count = awakened_state.get("prophet_signals", 0)

    status_icon = "🔮" if signal_count > 0 else "🔮"
    status_color = "#a855f7" if signal_count > 0 else "#64748b"

    return f"""
    <div style="
        background: #0f172a;
        border-radius: 8px;
        padding: 10px;
        border-left: 3px solid #8b5cf6;
    ">
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
            <span style="font-size: 14px; color: {status_color};">{status_icon}</span>
            <span style="font-size: 11px; font-weight: 600; color: #a855f7;">天眼通</span>
        </div>
        <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">预兆感知</div>
        <div style="font-size: 11px; color: #f1f5f9;">
            {signal_count} 个预兆信号
        </div>
    </div>
    """


def _get_volatility_surface_status() -> str:
    """获取波动率曲面状态"""
    orch = _get_center_orchestrator()
    awakened_state = orch.get_awakened_state() if orch else None

    vol_signals = 0
    if awakened_state:
        vol_signals = awakened_state.get("volatility_signals", 0)

    status_text = f"信号: {vol_signals}" if vol_signals > 0 else "正常"
    status_color = "#22c55e" if vol_signals == 0 else "#f59e0b"

    return f"""
    <div style="
        background: #0f172a;
        border-radius: 8px;
        padding: 10px;
        border-left: 3px solid #0ea5e9;
    ">
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
            <span style="font-size: 14px;">📈</span>
            <span style="font-size: 11px; font-weight: 600; color: #0ea5e9;">波动率曲面</span>
        </div>
        <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">IV偏度/期限结构</div>
        <div style="font-size: 11px; color: {status_color};">
            {status_text}
        </div>
    </div>
    """


def _get_realtime_taste_status() -> str:
    """获取实时舌识状态"""
    orch = _get_center_orchestrator()
    awakened_state = orch.get_awakened_state() if orch else None

    taste_signals = 0
    if awakened_state:
        taste_signals = awakened_state.get("taste_signals", 0)

    return f"""
    <div style="
        background: #0f172a;
        border-radius: 8px;
        padding: 10px;
        border-left: 3px solid #f472b6;
    ">
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
            <span style="font-size: 14px;">👅</span>
            <span style="font-size: 11px; font-weight: 600; color: #f472b6;">实时舌识</span>
        </div>
        <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">持仓尝受</div>
        <div style="font-size: 11px; color: #f1f5f9;">
            {taste_signals} 次尝受
        </div>
    </div>
    """


def _get_pre_taste_status() -> str:
    """获取 PreTaste 预尝状态"""
    orch = _get_center_orchestrator()
    awakened_state = orch.get_awakened_state() if orch else None

    pre_taste_count = 0
    if awakened_state:
        pre_taste_count = awakened_state.get("pre_taste_count", 0)

    return f"""
    <div style="
        background: #0f172a;
        border-radius: 8px;
        padding: 10px;
        border-left: 3px solid #10b981;
    ">
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
            <span style="font-size: 14px;">🍃</span>
            <span style="font-size: 11px; font-weight: 600; color: #10b981;">预尝</span>
        </div>
        <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">先验感知</div>
        <div style="font-size: 11px; color: #f1f5f9;">
            {pre_taste_count} 次预尝
        </div>
    </div>
    """


def _render_manas_layer() -> str:
    """渲染末那识层状态"""

    decision_status = _get_adaptive_manas_status()
    fp_status = _get_first_principles_status()
    risk_status = _get_risk_alert_status()

    return f"""
    <div style="margin-bottom: 16px;">
        <div style="
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid #334155;
        ">
            <span style="font-size: 16px;">⚖️</span>
            <span style="font-size: 13px; font-weight: 600; color: #f1f5f9;">末那识层</span>
            <div style="
                background: #22c55e22;
                border: 1px solid #22c55e;
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 10px;
                color: #22c55e;
                margin-left: auto;
            ">
                90%
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;">
            {decision_status}
            {fp_status}
            {risk_status}
        </div>
    </div>
    """


def _get_adaptive_manas_status() -> str:
    """获取 AdaptiveManas 状态"""
    orch = _get_center_orchestrator()
    awakened_state = orch.get_awakened_state() if orch else None

    adaptive_decisions = 0
    if awakened_state:
        adaptive_decisions = awakened_state.get("adaptive_decisions", 0)

    action = "🟢 行动" if adaptive_decisions > 0 else "🟡 观望"
    harmony = min(adaptive_decisions / 100, 1.0) if adaptive_decisions else 0
    harmony_color = "#22c55e" if harmony > 0.6 else "#f59e0b" if harmony > 0.3 else "#64748b"

    return f"""
    <div style="
        background: #0f172a;
        border-radius: 8px;
        padding: 10px;
        border-left: 3px solid #f59e0b;
    ">
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
            <span style="font-size: 14px;">🌊</span>
            <span style="font-size: 11px; font-weight: 600; color: #f59e0b;">顺应决策</span>
        </div>
        <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">天时响应</div>
        <div style="font-size: 11px; color: #f1f5f9; margin-bottom: 4px;">{action}</div>
        <div style="font-size: 10px; color: {harmony_color};">决策: {adaptive_decisions}</div>
    </div>
    """


def _render_meta_evolution_status() -> str:
    """渲染 MetaEvolution 状态"""
    orch = _get_center_orchestrator()
    awakened_state = orch.get_awakened_state() if orch else None

    strategies_generated = 0
    generations = 0
    if awakened_state:
        strategies_generated = awakened_state.get("strategies_generated", 0)

    return f"""
    <div style="
        background: #0f172a;
        border-radius: 8px;
        padding: 10px;
        border-left: 3px solid #a855f7;
    ">
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
            <span style="font-size: 14px;">🧬</span>
            <span style="font-size: 11px; font-weight: 600; color: #a855f7;">策略进化</span>
        </div>
        <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">自动策略生成</div>
        <div style="font-size: 11px; color: #f1f5f9;">
            {strategies_generated} 个策略
        </div>
        <div style="font-size: 10px; color: #64748b;">{generations} 代进化</div>
    </div>
    """


def _get_first_principles_status() -> str:
    """获取第一性原理状态"""
    orch = _get_center_orchestrator()
    awakened_state = orch.get_awakened_state() if orch else None

    fp_insights = 0
    if awakened_state:
        fp_insights = awakened_state.get("first_principles_insights", 0)

    return f"""
    <div style="
        background: #0f172a;
        border-radius: 8px;
        padding: 10px;
        border-left: 3px solid #6366f1;
    ">
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
            <span style="font-size: 14px;">🔍</span>
            <span style="font-size: 11px; font-weight: 600; color: #6366f1;">第一原理</span>
        </div>
        <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">因果追踪</div>
        <div style="font-size: 11px; color: #f1f5f9;">
            {fp_insights} 次洞察
        </div>
    </div>
    """


def _get_risk_alert_status() -> str:
    """获取风控警报状态"""
    orch = _get_center_orchestrator()
    awakened_state = orch.get_awakened_state() if orch else None

    risk_alerts = 0
    if awakened_state:
        risk_alerts = awakened_state.get("risk_alerts", 0)

    status_color = "#22c55e" if risk_alerts == 0 else "#f59e0b"

    return f"""
    <div style="
        background: #0f172a;
        border-radius: 8px;
        padding: 10px;
        border-left: 3px solid #ef4444;
    ">
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
            <span style="font-size: 14px;">🛡️</span>
            <span style="font-size: 11px; font-weight: 600; color: #ef4444;">风控</span>
        </div>
        <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">风险警报</div>
        <div style="font-size: 11px; color: {status_color};">
            {risk_alerts} 次警报
        </div>
    </div>
    """


def _render_alaya_layer() -> str:
    """渲染阿赖耶识层状态"""

    pattern_status = _get_seed_illuminator_status()

    return f"""
    <div style="margin-bottom: 16px;">
        <div style="
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid #334155;
        ">
            <span style="font-size: 16px;">💡</span>
            <span style="font-size: 13px; font-weight: 600; color: #f1f5f9;">阿赖耶识层</span>
            <div style="
                background: #22c55e22;
                border: 1px solid #22c55e;
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 10px;
                color: #22c55e;
                margin-left: auto;
            ">
                90%
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;">
            {pattern_status}
            {_render_awakened_alaya_status()}
            {_get_opportunity_status()}
            {_get_action_status()}
        </div>
    </div>
    """


def _get_opportunity_status() -> str:
    """获取机会发现状态"""
    orch = _get_center_orchestrator()
    awakened_state = orch.get_awakened_state() if orch else None

    opportunities = 0
    if awakened_state:
        opportunities = awakened_state.get("opportunities", 0)

    return f"""
    <div style="
        background: #0f172a;
        border-radius: 8px;
        padding: 10px;
        border-left: 3px solid #f97316;
    ">
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
            <span style="font-size: 14px;">🎯</span>
            <span style="font-size: 11px; font-weight: 600; color: #f97316;">机会</span>
        </div>
        <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">主动发现</div>
        <div style="font-size: 11px; color: #f1f5f9;">
            {opportunities} 个机会
        </div>
    </div>
    """


def _get_action_status() -> str:
    """获取行动执行状态"""
    orch = _get_center_orchestrator()
    awakened_state = orch.get_awakened_state() if orch else None

    actions = 0
    if awakened_state:
        actions = awakened_state.get("actions", 0)

    return f"""
    <div style="
        background: #0f172a;
        border-radius: 8px;
        padding: 10px;
        border-left: 3px solid #14b8a6;
    ">
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
            <span style="font-size: 14px;">⚡</span>
            <span style="font-size: 11px; font-weight: 600; color: #14b8a6;">行动</span>
        </div>
        <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">执行次数</div>
        <div style="font-size: 11px; color: #f1f5f9;">
            {actions} 次行动
        </div>
    </div>
    """


def _get_seed_illuminator_status() -> str:
    """获取 SeedIlluminator 状态"""
    orch = _get_center_orchestrator()
    awakened_state = orch.get_awakened_state() if orch else None

    illuminated = 0
    if awakened_state:
        illuminated = awakened_state.get("illuminated_patterns", 0)

    return f"""
    <div style="
        background: #0f172a;
        border-radius: 8px;
        padding: 10px;
        border-left: 3px solid #fbbf24;
    ">
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
            <span style="font-size: 14px;">✨</span>
            <span style="font-size: 11px; font-weight: 600; color: #fbbf24;">种子发光</span>
        </div>
        <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">模式召回</div>
        <div style="font-size: 11px; color: #f1f5f9;">
            {illuminated} 个点亮模式
        </div>
    </div>
    """


def _render_awakened_alaya_status() -> str:
    """渲染 AwakenedAlaya 状态"""
    orch = _get_center_orchestrator()
    awakened_state = orch.get_awakened_state() if orch else None

    awakening_level = 0.0
    if awakened_state:
        level_str = awakened_state.get("awakening_level", "dormant")
        awakening_level_map = {"dormant": 0.0, "awakening": 0.4, "illuminated": 0.7, "enlightened": 0.95}
        awakening_level = awakening_level_map.get(level_str, 0.0)

    awakening_percent = int(awakening_level * 100)
    epiphany_count = 0
    if awakened_state:
        epiphany_count = awakened_state.get("epiphany_count", 0)

    return f"""
    <div style="
        background: #0f172a;
        border-radius: 8px;
        padding: 10px;
        border-left: 3px solid #06b6d4;
    ">
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
            <span style="font-size: 14px;">🌟</span>
            <span style="font-size: 11px; font-weight: 600; color: #06b6d4;">觉醒归档</span>
        </div>
        <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">顿悟机制</div>
        <div style="font-size: 11px; color: #f1f5f9;">
            觉醒: {awakening_percent}%
        </div>
        <div style="font-size: 10px; color: #64748b;">顿悟: {epiphany_count}</div>
    </div>
    """


def _render_awakening_progress() -> str:
    """渲染觉醒进度条"""
    return """
    <div style="margin-top: 16px; padding-top: 12px; border-top: 1px solid #334155;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <span style="font-size: 11px; color: #94a3b8;">觉醒等级：成长期</span>
            <span style="font-size: 11px; color: #0ea5e9;">深度推理能力增强中</span>
        </div>
        <div style="
            background: #0f172a;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 10px;
            color: #64748b;
        ">
            <span style="color: #22c55e;">✅</span> 被动感知 |
            <span style="color: #22c55e;">✅</span> 主动决策 |
            <span style="color: #22c55e;">✅</span> 深度推理 |
            <span style="color: #22c55e;">✅</span> 实时反馈 |
            <span style="color: #22c55e;">✅</span> 自我改进 |
            <span style="color: #0ea5e9;">🔄</span> 因果追踪 |
            <span style="color: #22c55e;">✅</span> 模式召回
        </div>
    </div>
    """


__all__ = [
    "render_awakening_status",
]
