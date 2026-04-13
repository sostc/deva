"""
Token Monitor 组件 - TOKEN 消耗监控板块

展示 OpenRouter 每周 TOKEN 消耗趋势、累计增长率、
异常告警级别、AI 算力趋势方向。
"""


def render_token_monitor(ui):
    try:
        from deva.naja.cognition.openrouter_monitor import (
            get_openrouter_trend, get_ai_compute_trend
        )
    except Exception:
        return

    from pywebio.output import put_html

    # --- 获取数据 ---
    try:
        or_trend = get_openrouter_trend()
        ai_trend = get_ai_compute_trend()
    except Exception:
        or_trend = None
        ai_trend = None

    if not or_trend and not ai_trend:
        return

    # === 渲染 ===

    # 告警级别
    alert_level = (or_trend or {}).get("alert_level", "normal")
    alert_config = {
        "normal": ("正常", "#22c55e", "🟢"),
        "warning": ("警告", "#f59e0b", "🟡"),
        "critical": ("严重", "#ef4444", "🔴"),
    }
    alert_label, alert_color, alert_icon = alert_config.get(
        alert_level, ("未知", "#94a3b8", "⚪")
    )

    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <div style="font-size: 13px; font-weight: 600; color: #f59e0b;">
                🔥 TOKEN 消耗监控
            </div>
            <div style="font-size: 10px; color: #475569;">
                告警: <span style="color: {alert_color};">{alert_icon} {alert_label}</span>
            </div>
        </div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
            OpenRouter 周消耗 × AI 算力趋势 → 行业基本面信号
        </div>
    """)

    # OpenRouter 趋势
    if or_trend:
        latest_total_fmt = or_trend.get("latest_total_formatted", "N/A")
        latest_change = or_trend.get("latest_change", 0)
        recent_avg_change = or_trend.get("recent_avg_change", 0)
        data_weeks = or_trend.get("data_weeks", 0)
        direction = or_trend.get("direction", "stable")
        strength = or_trend.get("strength", 0)
        is_anomaly = or_trend.get("is_anomaly", False)
        is_incomplete = or_trend.get("is_incomplete_week", False)

        # 方向图标
        dir_config = {
            "rising": ("📈 上升", "#ef4444"),
            "falling": ("📉 下降", "#22c55e"),
            "stable": ("➡️ 稳定", "#f59e0b"),
        }
        dir_label, dir_color = dir_config.get(direction, ("❓ 未知", "#94a3b8"))

        # 变化率颜色
        change_pct = f"{latest_change:+.1f}%"
        change_color = "#ef4444" if latest_change > 0 else ("#22c55e" if latest_change < 0 else "#94a3b8")

        incomplete_badge = ' <span style="font-size: 8px; color: #f59e0b; background: rgba(245,158,11,0.15); padding: 1px 4px; border-radius: 3px;">本周未完</span>' if is_incomplete else ""
        anomaly_badge = ' <span style="font-size: 8px; color: #ef4444; background: rgba(239,68,68,0.15); padding: 1px 4px; border-radius: 3px;">⚠️ 异常</span>' if is_anomaly else ""

        put_html(f"""
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px; font-weight: 500;">
            📡 OpenRouter 周消耗{incomplete_badge}{anomaly_badge}
        </div>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px;">
            <div style="background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.15); padding: 8px 10px; border-radius: 8px; text-align: center;">
                <div style="font-size: 15px; color: #f59e0b; font-weight: 700;">{latest_total_fmt}</div>
                <div style="font-size: 9px; color: #94a3b8;">最新周消耗</div>
            </div>
            <div style="background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.15); padding: 8px 10px; border-radius: 8px; text-align: center;">
                <div style="font-size: 15px; color: {change_color}; font-weight: 700;">{change_pct}</div>
                <div style="font-size: 9px; color: #94a3b8;">周环比</div>
            </div>
            <div style="background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.15); padding: 8px 10px; border-radius: 8px; text-align: center;">
                <div style="font-size: 15px; color: {dir_color}; font-weight: 700;">{dir_label}</div>
                <div style="font-size: 9px; color: #94a3b8;">趋势方向</div>
            </div>
        </div>
        """)

        # 趋势强度条
        strength_pct = min(int(abs(strength) * 100), 100)
        put_html(f"""
        <div style="
            background: rgba(245,158,11,0.06);
            border: 1px solid rgba(245,158,11,0.1);
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 12px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="font-size: 10px; color: #94a3b8;">趋势强度</span>
                <span style="font-size: 10px; color: #64748b;">数据周数: {data_weeks} | 近期均变: {recent_avg_change:+.1f}%</span>
            </div>
            <div style="height: 6px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden;">
                <div style="width: {strength_pct}%; height: 100%; background: {dir_color}; border-radius: 3px;"></div>
            </div>
        </div>
        """)

        # 建议
        recommendation = or_trend.get("recommendation", "")
        if recommendation:
            put_html(f"""
            <div style="
                background: rgba(245,158,11,0.04);
                border-left: 3px solid rgba(245,158,11,0.3);
                padding: 6px 10px;
                margin-bottom: 12px;
                border-radius: 0 6px 6px 0;
            ">
                <div style="font-size: 10px; color: #f59e0b;">💡 {recommendation}</div>
            </div>
            """)

    # AI 算力趋势
    if ai_trend:
        cumulative_growth = ai_trend.get("cumulative_growth", 0)
        weekly_growth_rate = ai_trend.get("weekly_growth_rate", 0)
        total_tokens = ai_trend.get("total_tokens", 0)
        trend_dir = ai_trend.get("trend_direction", "stable")
        base_strength = ai_trend.get("base_strength", 0)
        ai_alert = ai_trend.get("alert_level", "normal")
        is_abnormal = ai_trend.get("is_abnormal", False)
        ai_message = ai_trend.get("message", "")

        # 格式化
        from deva.naja.cognition.openrouter_monitor import format_tokens
        total_fmt = format_tokens(total_tokens) if total_tokens else "N/A"

        trend_config = {
            "rising": ("📈 上升", "#ef4444"),
            "falling": ("📉 下降", "#22c55e"),
            "stable": ("➡️ 稳定", "#f59e0b"),
        }
        trend_label, trend_color = trend_config.get(trend_dir, ("❓", "#94a3b8"))

        abnormal_badge = ' <span style="font-size: 8px; color: #ef4444; background: rgba(239,68,68,0.15); padding: 1px 4px; border-radius: 3px;">⚠️ 异常</span>' if is_abnormal else ""

        put_html(f"""
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px; font-weight: 500;">
            🖥️ AI 算力趋势{abnormal_badge}
        </div>
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 10px;">
            <div style="background: rgba(168,85,247,0.08); border: 1px solid rgba(168,85,247,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                <div style="font-size: 13px; color: #a855f7; font-weight: 700;">{total_fmt}</div>
                <div style="font-size: 9px; color: #94a3b8;">总消耗</div>
            </div>
            <div style="background: rgba(168,85,247,0.08); border: 1px solid rgba(168,85,247,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                <div style="font-size: 13px; color: #a855f7; font-weight: 700;">{cumulative_growth:+.1f}%</div>
                <div style="font-size: 9px; color: #94a3b8;">累计增长</div>
            </div>
            <div style="background: rgba(168,85,247,0.08); border: 1px solid rgba(168,85,247,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                <div style="font-size: 13px; color: {trend_color}; font-weight: 700;">{trend_label}</div>
                <div style="font-size: 9px; color: #94a3b8;">趋势</div>
            </div>
            <div style="background: rgba(168,85,247,0.08); border: 1px solid rgba(168,85,247,0.15); padding: 6px 8px; border-radius: 6px; text-align: center;">
                <div style="font-size: 13px; color: #a855f7; font-weight: 700;">{base_strength:.2f}</div>
                <div style="font-size: 9px; color: #94a3b8;">基础强度</div>
            </div>
        </div>
        """)

        if ai_message:
            put_html(f"""
            <div style="
                background: rgba(168,85,247,0.04);
                border-left: 3px solid rgba(168,85,247,0.3);
                padding: 6px 10px;
                border-radius: 0 6px 6px 0;
            ">
                <div style="font-size: 10px; color: #a855f7;">🖥️ {ai_message}</div>
            </div>
            """)

    # 关闭容器
    put_html("</div>")
