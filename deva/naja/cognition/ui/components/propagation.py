"""
Propagation 组件
"""


def render_propagation(ui):
    from pywebio.output import put_html

    # --- 获取数据 ---
    has_data = False
    propagation_engine = None
    structure = None
    resonance_signals = None
    pred_stats = None
    active_preds = None

    try:
        newsmind = getattr(ui.engine, '_news_mind', None)
        if newsmind:
            propagation_engine = getattr(newsmind, 'propagation_engine', None)
    except Exception:
        pass

    if propagation_engine:
        try:
            structure = propagation_engine.get_liquidity_structure()
            if "error" not in structure:
                active_markets = structure.get("active_markets", [])
                has_data = len(active_markets) > 0

            resonance_signals = propagation_engine.get_resonance_signals()
            if resonance_signals and len(resonance_signals) > 0:
                has_data = True
        except Exception:
            pass

    # 尝试获取预测数据
    try:
        if ui.engine:
            pred_stats = ui.engine.get_liquidity_stats()
            active_preds = ui.engine.get_liquidity_predictions()
            if pred_stats:
                active_cnt = pred_stats.get("active_count", 0)
                confirmed_cnt = pred_stats.get("total_confirmed", 0)
                if active_cnt > 0 or confirmed_cnt > 0:
                    has_data = True
    except Exception:
        pass

    # --- 头部始终显示 ---
    active_markets_count = 0
    edges_count = 0
    if structure and "error" not in structure:
        active_markets_count = len(structure.get("active_markets", []))
        edges_count = len(structure.get("edges", {}))

    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <div style="font-size: 13px; font-weight: 600; color: #10b981;">
                🌐 全球流动性传播网络
            </div>
            <div style="font-size: 10px; color: #64748b;">
                {active_markets_count} 个活跃市场 · {edges_count} 条传播路径
            </div>
        </div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
            节点变化 → 沿边传播 → 验证结果 → 动态调权
        </div>
    """)

    # --- 无数据状态 ---
    if not propagation_engine:
        put_html("""
        <div style="text-align: center; padding: 24px 16px;">
            <div style="font-size: 32px; margin-bottom: 12px;">🌐</div>
            <div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">传播引擎未就绪</div>
            <div style="font-size: 10px; color: #475569;">等待系统初始化，将在此展示全球流动性传播网络和共振信号</div>
        </div>
        """)
        put_html('</div>')
        return

    if not has_data:
        put_html("""
        <div style="text-align: center; padding: 24px 16px;">
            <div style="font-size: 32px; margin-bottom: 12px;">⏳</div>
            <div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">暂无活跃市场变化</div>
            <div style="font-size: 10px; color: #475569;">系统正在监控全球市场流动性，检测到异动将立即展示</div>
        </div>
        """)
        put_html('</div>')
        return

    # --- 有数据时渲染内容 ---
    active_markets = structure.get("active_markets", [])
    markets = structure.get("markets", {})
    edges = structure.get("edges", {})

    if active_markets:
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

    if resonance_signals:
        put_html("""
        <div style="margin-bottom: 14px;">
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

    # === 预测闭环区域 ===
    if pred_stats:
        import time as _time

        active_cnt = pred_stats.get("active_count", 0)
        confirmed_cnt = pred_stats.get("total_confirmed", 0)
        denied_cnt = pred_stats.get("total_denied", 0)
        cancelled_cnt = pred_stats.get("total_cancelled", 0)
        pred_rate = pred_stats.get("prediction_rate", 0.5)

        rate_pct = int(pred_rate * 100)
        rate_color = "#22c55e" if pred_rate >= 0.7 else ("#f59e0b" if pred_rate >= 0.5 else "#ef4444")

        put_html(f"""
        <div style="padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.06);">
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 8px; font-weight: 500;">
                🔮 预测闭环 <span style="font-size: 10px; color: #475569;">准确率 <span style="color: {rate_color}; font-weight: 600;">{rate_pct}%</span></span>
            </div>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 10px;">
                <div style="background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.2); padding: 5px 8px; border-radius: 6px; text-align: center;">
                    <div style="font-size: 14px; color: #3b82f6; font-weight: 700;">{active_cnt}</div>
                    <div style="font-size: 8px; color: #94a3b8;">⏳ 活跃</div>
                </div>
                <div style="background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.2); padding: 5px 8px; border-radius: 6px; text-align: center;">
                    <div style="font-size: 14px; color: #22c55e; font-weight: 700;">{confirmed_cnt}</div>
                    <div style="font-size: 8px; color: #94a3b8;">✅ 确认</div>
                </div>
                <div style="background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.2); padding: 5px 8px; border-radius: 6px; text-align: center;">
                    <div style="font-size: 14px; color: #ef4444; font-weight: 700;">{denied_cnt}</div>
                    <div style="font-size: 8px; color: #94a3b8;">❌ 否认</div>
                </div>
                <div style="background: rgba(148,163,184,0.1); border: 1px solid rgba(148,163,184,0.2); padding: 5px 8px; border-radius: 6px; text-align: center;">
                    <div style="font-size: 14px; color: #94a3b8; font-weight: 700;">{cancelled_cnt}</div>
                    <div style="font-size: 8px; color: #94a3b8;">🚫 取消</div>
                </div>
            </div>
        """)

        if active_preds:
            now = _time.time()
            for pd in active_preds[:5]:
                from_m = pd.get("from_market", "?")
                to_m = pd.get("to_market", "?")
                direction = pd.get("direction", "?")
                prob = pd.get("probability", 0)
                verify_at = pd.get("verify_at", 0)

                dir_icon = "🔴 流入" if direction == "up" else ("🟢 流出" if direction == "down" else direction)
                prob_pct = int(prob * 100)

                remaining = max(0, verify_at - now) if verify_at > 0 else 0
                if remaining > 3600:
                    time_str = f"{remaining / 3600:.1f}h"
                elif remaining > 60:
                    time_str = f"{int(remaining / 60)}m"
                else:
                    time_str = f"{int(remaining)}s"

                put_html(f"""
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 3px 0; font-size: 10px; border-bottom: 1px solid rgba(255,255,255,0.04);">
                    <span style="color: #f1f5f9;">{from_m} → {to_m}</span>
                    <span style="color: #94a3b8;">{dir_icon}</span>
                    <span style="color: #f59e0b;">{prob_pct}%</span>
                    <span style="color: #64748b;">⏱ {time_str}</span>
                </div>
                """)

        put_html("</div>")

    put_html('</div>')
