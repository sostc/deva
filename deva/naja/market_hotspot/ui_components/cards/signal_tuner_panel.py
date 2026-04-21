"""信号调谐器面板 - 展示 SignalTuner 的自适应调参状态"""

import logging

log = logging.getLogger(__name__)


def render_signal_tuner_panel() -> str:
    """渲染信号调谐器面板

    数据源: SR('signal_tuner').get_stats()
    返回字段: daily_stats, today_buy_signals, target_daily_signals,
              current_params, recent_adjustments, value_performances
    """
    try:
        from deva.naja.register import SR
        tuner = SR('signal_tuner')
        if not tuner:
            return _render_empty("信号调谐器未注册")

        stats = tuner.get_stats()
        if not stats:
            return _render_empty("暂无调谐数据")

        daily = stats.get('daily_stats', {})
        today_signals = stats.get('today_buy_signals', 0)
        target_signals = stats.get('target_daily_signals', 5)
        params = stats.get('current_params', {})
        adjustments = stats.get('recent_adjustments', [])
        performances = stats.get('value_performances', {})

        # 信号达成率
        if target_signals > 0:
            achieve_rate = today_signals / target_signals * 100
        else:
            achieve_rate = 0

        if achieve_rate >= 80:
            rate_color, rate_emoji = "#16a34a", "🟢"
        elif achieve_rate >= 40:
            rate_color, rate_emoji = "#ca8a04", "🟡"
        else:
            rate_color, rate_emoji = "#dc2626", "🔴"

        # 参数展示
        param_items = ""
        key_params = [
            ('min_hotspot_score', '最小热点分', '#a855f7'),
            ('min_block_weight', '最小题材权重', '#3b82f6'),
            ('min_confidence', '最小置信度', '#0ea5e9'),
            ('cooldown_minutes', '冷却时间(分)', '#f59e0b'),
        ]
        for key, label, color in key_params:
            val = params.get(key, '-')
            if isinstance(val, float):
                val = f"{val:.3f}"
            param_items += f"""
            <div style="text-align: center; padding: 6px; background: rgba(255,255,255,0.05); border-radius: 4px;">
                <div style="font-size: 12px; font-weight: 700; color: {color};">{val}</div>
                <div style="font-size: 8px; color: #64748b;">{label}</div>
            </div>"""

        # 最近调整
        adj_items = ""
        for adj in adjustments[:3]:
            param_name = adj.get('param_name', adj.get('param', '?'))
            strategy_id = adj.get('strategy_id', '')
            direction = adj.get('direction', '')
            arrow = "↑" if direction == 'up' else "↓" if direction == 'down' else "•"
            adj_color = "#16a34a" if direction == 'up' else "#dc2626" if direction == 'down' else "#64748b"
            reason = adj.get('reason', '')[:20]
            adj_items += f"""
            <div style="display: flex; align-items: center; gap: 6px; padding: 3px 0; font-size: 9px;">
                <span style="color: {adj_color}; font-weight: 600;">{arrow}</span>
                <span style="color: #94a3b8;">{param_name}</span>
                <span style="color: #64748b;">{reason}</span>
            </div>"""

        if not adj_items:
            adj_items = '<div style="color: #64748b; font-size: 9px; padding: 4px 0;">暂无调整记录</div>'

    except Exception as e:
        return _render_empty(f"加载失败: {e}")

    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="font-size: 13px; font-weight: 600; color: #0ea5e9;">
                🎛️ 信号调谐器
            </div>
            <div style="font-size: 9px; color: #64748b;">
                {rate_emoji} 达成率 {achieve_rate:.0f}%
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 10px;">
            <div style="text-align: center; padding: 8px; background: rgba(14,165,233,0.1); border-radius: 4px;">
                <div style="font-size: 16px; font-weight: 700; color: #0ea5e9;">{today_signals}</div>
                <div style="font-size: 8px; color: #64748b;">今日信号</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(168,85,247,0.1); border-radius: 4px;">
                <div style="font-size: 16px; font-weight: 700; color: #a855f7;">{target_signals}</div>
                <div style="font-size: 8px; color: #64748b;">目标信号</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(74,222,128,0.1); border-radius: 4px;">
                <div style="font-size: 16px; font-weight: 700; color: {rate_color};">{achieve_rate:.0f}%</div>
                <div style="font-size: 8px; color: #64748b;">达成率</div>
            </div>
        </div>

        <div style="font-size: 8px; color: #64748b; margin-bottom: 4px;">📋 当前参数</div>
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; margin-bottom: 10px;">
            {param_items}
        </div>

        <div style="font-size: 8px; color: #64748b; margin-bottom: 4px;">🔧 最近调整</div>
        {adj_items}
    </div>
    """


def _render_empty(msg: str) -> str:
    return f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="font-size: 13px; font-weight: 600; color: #0ea5e9; margin-bottom: 10px;">
            🎛️ 信号调谐器
        </div>
        <div style="text-align: center; padding: 15px; color: #64748b; font-size: 11px;">
            {msg}
        </div>
    </div>
    """
