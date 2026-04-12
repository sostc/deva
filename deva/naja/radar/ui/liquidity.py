"""Radar UI — 跨市场流动性预测面板 + 通知历史"""

from pywebio.output import put_html


def render_liquidity_prediction_panel(engine):
    """渲染跨市场流动性预测面板"""
    try:
        from deva.naja.radar.global_market_scanner import get_global_market_scanner
        scanner = get_global_market_scanner()
        status = scanner.get_liquidity_status()
    except Exception:
        status = {"predictions": {}, "verifications": {}, "resonance": None, "topic_predictions": {}}

    # 获取通知历史
    try:
        from deva.naja.cognition.liquidity import get_notifier
        notifier = get_notifier()
        notifications = notifier.get_recent_notifications(limit=5)
        notifier_stats = notifier.get_stats()
    except Exception:
        notifications = []
        notifier_stats = {"total_sent": 0, "total_failed": 0, "history_count": 0}

    predictions = status.get("predictions", {})
    verifications = status.get("verifications", {})
    resonance = status.get("resonance", None)
    topic_predictions = status.get("topic_predictions", {})

    prediction_html = _build_prediction_html(predictions)
    verification_html = _build_verification_html(verifications)
    resonance_html = _build_resonance_html(resonance)
    topic_html = _build_topic_html(topic_predictions)
    notification_html = _render_notifications(notifications)

    put_html(f"""
    <div style="
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px;
        padding: 15px;
        margin-top: 15px;
        border: 1px solid rgba(99, 102, 241, 0.3);
    ">
        <h4 style="margin: 0 0 15px 0; color: #818cf8;">
            🌊 流动性预测体系
        </h4>
        <div style="font-size: 11px; color: #64748b; margin-bottom: 12px;">
            基于行情+舆论共振检测，主题扩散预测，预判错误时自动解除限制
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
            <div>
                <div style="font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 8px;">
                    📊 预测
                </div>
                {prediction_html}
            </div>
            <div>
                <div style="font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 8px;">
                    🔍 验证
                </div>
                {verification_html}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 15px;">
            <div>
                <div style="font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 8px;">
                    ⚡ 共振检测
                </div>
                {resonance_html}
            </div>
            <div>
                <div style="font-size: 12px; font-weight: 600; color: #94a3b8; margin-bottom: 8px;">
                    🔥 主题扩散
                </div>
                {topic_html}
            </div>
        </div>

        <div style="margin-top: 15px; padding: 12px; background: rgba(99, 102, 241, 0.1); border-radius: 8px; border: 1px solid rgba(99, 102, 241, 0.2);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <div style="font-size: 12px; font-weight: 600; color: #818cf8;">🔔 通知历史</div>
                <div style="font-size: 10px; color: #64748b;">
                    已发送：{notifier_stats.get('total_sent', 0)} | 失败：{notifier_stats.get('total_failed', 0)}
                </div>
            </div>
            {notification_html}
        </div>

        <div style="margin-top: 12px; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 8px;">
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">规则说明:</div>
            <div style="font-size: 10px; color: #64748b;">
                • 共振：行情 + 舆论同向=高权重 (1.0), 背离=低权重 (0.3)<br/>
                • 主题扩散：热度>3 触发，传染概率×热度因子<br/>
                • 信号 &lt; 0.4: 紧张调整 | &gt; 0.7: 宽松调整<br/>
                • 预判错误或预测过期：自动解除限制
            </div>
        </div>
    </div>
    """)


# ---------------------------------------------------------------------------
# 子面板构建函数
# ---------------------------------------------------------------------------

_MARKET_DISPLAY = {
    "china_a": "A股",
    "hk": "港股",
    "us": "美股",
    "futures": "期货",
}


def _build_prediction_html(predictions: dict) -> str:
    if not predictions:
        return '<span style="color: #64748b; font-size: 12px;">暂无流动性预测</span>'

    html = ""
    for market, pred in predictions.items():
        signal = pred.get("signal", 0.5)
        confidence = pred.get("confidence", 0)
        sources = pred.get("source_signals", [])
        is_valid = pred.get("is_valid", False)

        if signal < 0.4:
            status_label = "🔴 紧张"
            bar_color = "#f87171"
        elif signal > 0.7:
            status_label = "🟢 宽松"
            bar_color = "#4ade80"
        else:
            status_label = "🟡 中性"
            bar_color = "#fbbf24"

        market_display = _MARKET_DISPLAY.get(market, market)
        source_text = ", ".join(sources) if sources else "无"
        validity_icon = "✅" if is_valid else "⏰"

        html += f"""
        <div style="
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 8px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-weight: 600; color: #e2e8f0;">{market_display}</span>
                <span style="font-size: 12px;">{status_label}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 10px;">
                <div style="flex: 1; background: #334155; border-radius: 4px; height: 8px;">
                    <div style="background: {bar_color}; border-radius: 4px; height: 8px; width: {signal * 100}%;"></div>
                </div>
                <span style="font-size: 11px; color: #94a3b8; min-width: 40px;">{signal:.2f}</span>
            </div>
            <div style="margin-top: 6px; font-size: 10px; color: #64748b;">
                信号源: {source_text} | 置信度: {confidence:.0%} | {validity_icon}
            </div>
        </div>
        """
    return html


def _build_verification_html(verifications: dict) -> str:
    if not verifications:
        return '<span style="color: #64748b; font-size: 12px;">等待验证数据...</span>'

    html = ""
    for market, ver in verifications.items():
        expected = ver.get("expected", 0.5)
        count = ver.get("verification_count", 0)
        verified = ver.get("verified", False)
        should_relax = ver.get("should_relax", False)

        status_icon = "✅" if verified else ("🔄" if count >= 5 else "⏳")
        relax_text = "解除限制" if should_relax else "保持限制"
        market_display = _MARKET_DISPLAY.get(market, market)

        html += f"""
        <div style="
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 8px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; color: #e2e8f0;">{market_display} 验证</span>
                <span style="font-size: 12px;">{status_icon} {relax_text}</span>
            </div>
            <div style="margin-top: 6px; font-size: 11px; color: #64748b;">
                预期: {expected:.2f} | 验证次数: {count}/5
            </div>
        </div>
        """
    return html


def _build_resonance_html(resonance) -> str:
    if not resonance:
        return '<span style="color: #64748b; font-size: 12px;">暂无共振数据</span>'

    level = resonance.get("level", "none")
    m_signal = resonance.get("market_signal", 0)
    n_signal = resonance.get("narrative_signal", 0)
    alignment = resonance.get("alignment", 0)
    weight = resonance.get("weight", 0)

    level_icons = {
        "high": ("🔴", "#f87171", "高共振"),
        "medium": ("🟡", "#fbbf24", "中共振"),
        "low": ("🔵", "#60a5fa", "低共振"),
        "divergent": ("⚠️", "#9333ea", "背离"),
        "none": ("⚪", "#94a3b8", "无信号"),
    }
    icon, color, label = level_icons.get(level, ("⚪", "#94a3b8", "未知"))

    return f"""
    <div style="
        background: rgba(255,255,255,0.05);
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 8px;
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-weight: 600; color: #e2e8f0;">信号共振</span>
            <span style="font-size: 12px;">{icon} {label}</span>
        </div>
        <div style="display: flex; gap: 15px; font-size: 11px; color: #94a3b8;">
            <span>行情: <b style="color: #f87171;">{m_signal:+.2f}</b></span>
            <span>舆论: <b style="color: #60a5fa;">{n_signal:+.2f}</b></span>
            <span>对齐: <b style="color: {color};">{alignment:.0%}</b></span>
        </div>
        <div style="margin-top: 6px; font-size: 10px; color: #64748b;">
            权重: {weight:.1f} | 最终信号: {m_signal * weight:+.2f}
        </div>
    </div>
    """


def _build_topic_html(topic_predictions: dict) -> str:
    if not topic_predictions:
        return '<span style="color: #64748b; font-size: 12px;">暂无主题扩散</span>'

    html = ""
    for topic, pred in topic_predictions.items():
        heat = pred.get("heat_score", 0)
        prob = pred.get("spread_probability", 0)
        block_list = pred.get("target_blocks", [])

        heat_bar = min(heat / 10 * 100, 100)
        heat_color = "#f87171" if heat > 5 else ("#fbbf24" if heat > 3 else "#4ade80")

        html += f"""
        <div style="
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 8px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-weight: 600; color: #e2e8f0;">{topic}</span>
                <span style="font-size: 12px; color: {heat_color};">🔥 {heat:.1f}</span>
            </div>
            <div style="background: #334155; border-radius: 4px; height: 6px; margin-bottom: 6px;">
                <div style="background: {heat_color}; border-radius: 4px; height: 6px; width: {heat_bar}%;"></div>
            </div>
            <div style="font-size: 10px; color: #64748b;">
                传染概率: {prob:.0%} | 目标: {', '.join(block_list[:2]) if block_list else '无'}
            </div>
        </div>
        """
    return html


def _render_notifications(notifications: list) -> str:
    """渲染通知历史"""
    if not notifications:
        return '<div style="font-size: 11px; color: #64748b; padding: 8px 0;">暂无通知记录</div>'

    html = '<div style="display: flex; flex-direction: column; gap: 6px;">'

    for n in notifications:
        time_str = n.get('time_str', '')
        n_type = n.get('type', '')
        severity = n.get('severity', '')
        title = n.get('title', '')
        sent = n.get('sent', False)

        # 类型图标
        type_icons = {
            "prediction_created": ("🔔", "#f59e0b"),
            "prediction_confirmed": ("✅", "#22c55e"),
            "prediction_denied": ("❌", "#ef4444"),
            "resonance_detected": ("⚡", "#8b5cf6"),
            "signal_change": ("📊", "#3b82f6"),
        }
        icon, color = type_icons.get(n_type, ("📌", "#64748b"))

        # 严重程度标记
        severity_color = {
            "high": "#ef4444",
            "medium": "#f59e0b",
            "low": "#22c55e",
        }.get(severity, "#64748b")

        sent_icon = "✓" if sent else "✗"
        sent_color = "#22c55e" if sent else "#ef4444"

        # 截断标题
        short_title = title[:50] + "..." if len(title) > 50 else title

        html += f'''
        <div style="
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 8px;
            background: rgba(255,255,255,0.03);
            border-radius: 6px;
            border-left: 3px solid {severity_color};
        ">
            <span style="font-size: 14px;">{icon}</span>
            <div style="flex: 1; min-width: 0;">
                <div style="font-size: 10px; color: {color}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                    {short_title}
                </div>
                <div style="font-size: 9px; color: #64748b;">
                    {time_str} | {severity}
                </div>
            </div>
            <div style="font-size: 10px; color: {sent_color}; min-width: 20px;">
                {sent_icon}
            </div>
        </div>
        '''

    html += '</div>'
    return html
