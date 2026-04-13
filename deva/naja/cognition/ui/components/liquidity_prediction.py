"""
Liquidity Prediction 组件 - 流动性预测闭环板块

展示 PredictionTracker 统计（活跃/确认/否认/取消）、
活跃预测列表（源市场→目标市场/方向/置信度/状态/验证时间）、预测准确率。
"""

import time


def render_liquidity_prediction(ui):
    try:
        from deva.naja.cognition.liquidity.liquidity_cognition import (
            get_liquidity_cognition, PredictionStatus
        )
        lc = get_liquidity_cognition()
        tracker = lc._prediction_tracker
    except Exception:
        return

    from pywebio.output import put_html

    # --- 获取数据 ---
    try:
        stats = tracker.get_stats()
        active_predictions = tracker.get_active_predictions()
        accuracy = tracker.get_prediction_rate()
    except Exception:
        return

    total_created = stats.get("total_created", 0)
    total_confirmed = stats.get("total_confirmed", 0)
    total_denied = stats.get("total_denied", 0)
    total_cancelled = stats.get("total_cancelled", 0)
    active_count = stats.get("active_count", 0)
    total_predictions = stats.get("total_predictions", 0)

    # --- 准确率颜色 ---
    accuracy_pct = int(accuracy * 100)
    if accuracy >= 0.7:
        acc_color = "#22c55e"
        acc_label = "优秀"
    elif accuracy >= 0.5:
        acc_color = "#f59e0b"
        acc_label = "一般"
    else:
        acc_color = "#ef4444"
        acc_label = "较差"

    # === 渲染 ===

    # 头部
    put_html(f"""
    <div style="
        margin-bottom: 12px;
        background: rgba(255,255,255,0.03);
        border-radius: 12px;
        padding: 14px 18px;
        border: 1px solid rgba(255,255,255,0.08);
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <div style="font-size: 13px; font-weight: 600; color: #3b82f6;">
                🔮 流动性预测闭环
            </div>
            <div style="font-size: 10px; color: #475569;">
                准确率: <span style="color: {acc_color}; font-weight: 600;">{accuracy_pct}%</span> ({acc_label})
            </div>
        </div>
        <div style="font-size: 11px; color: #475569; margin-bottom: 14px;">
            预测生成 → 跟踪验证 → 准确率反馈 → 模型校准
        </div>
    """)

    # 统计卡片
    status_cards = [
        ("⏳ 活跃", active_count, "#3b82f6"),
        ("✅ 确认", total_confirmed, "#22c55e"),
        ("❌ 否认", total_denied, "#ef4444"),
        ("🚫 取消", total_cancelled, "#94a3b8"),
    ]

    cards_html = ""
    for label, count, color in status_cards:
        cards_html += f"""
        <div style="background: rgba({_hex_to_rgb(color)},0.1); border: 1px solid rgba({_hex_to_rgb(color)},0.2); padding: 8px 10px; border-radius: 8px; text-align: center;">
            <div style="font-size: 16px; color: {color}; font-weight: 700;">{count}</div>
            <div style="font-size: 9px; color: #94a3b8;">{label}</div>
        </div>
        """

    put_html(f"""
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 14px;">
            {cards_html}
        </div>
    """)

    # 准确率进度条
    verified = total_confirmed + total_denied
    put_html(f"""
        <div style="
            background: rgba(59,130,246,0.06);
            border: 1px solid rgba(59,130,246,0.12);
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 14px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="font-size: 10px; color: #94a3b8;">📊 预测准确率</span>
                <span style="font-size: 10px; color: #64748b;">已验证 {verified} / 总计 {total_predictions}</span>
            </div>
            <div style="height: 8px; background: rgba(255,255,255,0.06); border-radius: 4px; overflow: hidden;">
                <div style="width: {accuracy_pct}%; height: 100%; background: {acc_color}; border-radius: 4px;"></div>
            </div>
        </div>
    """)

    # 活跃预测列表
    if active_predictions:
        now = time.time()
        rows_html = ""
        for pred in active_predictions[:8]:
            pd = pred.to_dict()
            from_m = pd.get("from_market", "?")
            to_m = pd.get("to_market", "?")
            direction = pd.get("direction", "?")
            prob = pd.get("probability", 0)
            verify_at = pd.get("verify_at", 0)

            # 方向徽章
            if direction == "up":
                dir_badge = '<span style="color: #ef4444; font-weight: 600;">↑ 流入</span>'
            elif direction == "down":
                dir_badge = '<span style="color: #22c55e; font-weight: 600;">↓ 流出</span>'
            else:
                dir_badge = f'<span style="color: #94a3b8;">{direction}</span>'

            # 验证倒计时
            if verify_at > 0:
                remaining = max(0, verify_at - now)
                if remaining > 3600:
                    time_str = f"{remaining / 3600:.1f}h"
                elif remaining > 60:
                    time_str = f"{int(remaining / 60)}m"
                else:
                    time_str = f"{int(remaining)}s"
                time_badge = f'<span style="color: #f59e0b; font-size: 9px;">⏱ {time_str}</span>'
            else:
                time_badge = '<span style="color: #64748b; font-size: 9px;">—</span>'

            # 置信度颜色
            prob_pct = int(prob * 100)
            if prob >= 0.7:
                prob_color = "#22c55e"
            elif prob >= 0.4:
                prob_color = "#f59e0b"
            else:
                prob_color = "#ef4444"

            rows_html += f"""
            <div style="display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 4px; padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.04); align-items: center;">
                <div style="font-size: 10px; color: #f1f5f9;">{from_m} → {to_m}</div>
                <div style="font-size: 10px;">{dir_badge}</div>
                <div style="font-size: 10px; color: {prob_color}; font-weight: 600;">{prob_pct}%</div>
                <div style="text-align: right;">{time_badge}</div>
            </div>
            """

        put_html(f"""
        <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px; font-weight: 500;">
            📋 活跃预测 <span style="font-size: 10px; color: #475569;">({len(active_predictions)} 个)</span>
        </div>
        <div style="
            background: rgba(59,130,246,0.04);
            border: 1px solid rgba(59,130,246,0.1);
            border-radius: 8px;
            padding: 8px 12px;
        ">
            <div style="display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 4px; padding-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.08);">
                <div style="font-size: 9px; color: #64748b;">路径</div>
                <div style="font-size: 9px; color: #64748b;">方向</div>
                <div style="font-size: 9px; color: #64748b;">置信度</div>
                <div style="font-size: 9px; color: #64748b; text-align: right;">验证</div>
            </div>
            {rows_html}
        </div>
        """)

    # 关闭容器
    put_html("</div>")


def _hex_to_rgb(hex_color: str) -> str:
    """将 #rrggbb 转为 r,g,b 字符串"""
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"
