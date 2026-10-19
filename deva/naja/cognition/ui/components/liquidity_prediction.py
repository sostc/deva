"""Liquidity Prediction 组件 —— 流动性预测闭环

展示 PredictionTracker 统计（活跃/确认/否认/取消）、
活跃预测列表（源市场→目标市场/方向/置信度/验证时间）、预测准确率。

2026-10-19 重排：空态压成一行；删掉「预测生成 → 跟踪验证 → 准确率反馈 →
模型校准」这类模块说明行。
"""

import html
import time

from pywebio.output import put_html

from .layout import card, report_empty


def _fmt_remaining(seconds: float) -> str:
    if seconds > 3600:
        return f"{seconds / 3600:.1f}h"
    if seconds > 60:
        return f"{int(seconds / 60)}m"
    return f"{int(seconds)}s"


def render_liquidity_prediction(ui):
    stats = None
    active_predictions = None

    try:
        if ui.engine:
            stats = ui.engine.get_liquidity_stats()
            active_predictions = ui.engine.get_liquidity_predictions()
    except Exception:
        pass

    has_data = False
    if stats:
        has_data = (stats.get("total_created", 0) > 0 or stats.get("active_count", 0) > 0)

    accuracy_pct = 50
    acc_color = "#94a3b8"
    acc_label = "等待数据"
    if stats:
        accuracy = stats.get("prediction_rate", 0.5)
        accuracy_pct = int(accuracy * 100)
        if accuracy >= 0.7:
            acc_color, acc_label = "#22c55e", "优秀"
        elif accuracy >= 0.5:
            acc_color, acc_label = "#f59e0b", "一般"
        else:
            acc_color, acc_label = "#ef4444", "较差"

    meta = f'准确率 <b style="color: {acc_color};">{accuracy_pct}%</b> · {acc_label}'

    if not stats:
        report_empty("🔮", "流动性预测闭环", "预测引擎未就绪", "等待系统初始化")
        return

    if not has_data:
        report_empty("🔮", "流动性预测闭环", "暂无预测数据", "系统正在学习市场模式")
        return

    total_confirmed = stats.get("total_confirmed", 0)
    total_denied = stats.get("total_denied", 0)
    total_cancelled = stats.get("total_cancelled", 0)
    active_count = stats.get("active_count", 0)
    total_predictions = stats.get("total_predictions", 0)

    tiles = "".join(
        f'<div style="background: {color}14; border: 1px solid {color}2e; padding: 7px 10px;'
        f'border-radius: 8px; text-align: center;">'
        f'<div style="font-size: 17px; color: {color}; font-weight: 700;">{value}</div>'
        f'<div style="font-size: 11px; color: #94a3b8;">{label}</div></div>'
        for label, value, color in (
            ("⏳ 活跃", active_count, "#3b82f6"),
            ("✅ 确认", total_confirmed, "#22c55e"),
            ("❌ 否认", total_denied, "#ef4444"),
            ("🚫 取消", total_cancelled, "#94a3b8"),
        )
    )

    verified = total_confirmed + total_denied
    body = f"""
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;">{tiles}</div>
    <div style="margin-top: 10px; background: rgba(59,130,246,.06); border: 1px solid rgba(59,130,246,.12);
                border-radius: 8px; padding: 8px 12px;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px;">
            <span style="font-size: 11px; color: #94a3b8;">📊 预测准确率</span>
            <span style="font-size: 11px; color: #64748b;">已验证 {verified} / 总计 {total_predictions}</span>
        </div>
        <div style="height: 8px; background: rgba(255,255,255,.06); border-radius: 4px; overflow: hidden;">
            <div style="width: {accuracy_pct}%; height: 100%; background: {acc_color}; border-radius: 4px;"></div>
        </div>
    </div>
    """

    if active_predictions:
        now = time.time()
        rows = ""
        for pd in active_predictions[:8]:
            direction = pd.get("direction", "?")
            if direction == "up":
                dir_badge = '<span style="color: #ef4444; font-weight: 600;">↑ 流入</span>'
            elif direction == "down":
                dir_badge = '<span style="color: #22c55e; font-weight: 600;">↓ 流出</span>'
            else:
                dir_badge = f'<span style="color: #94a3b8;">{html.escape(str(direction))}</span>'

            prob = pd.get("probability", 0)
            prob_pct = int(prob * 100)
            prob_color = "#22c55e" if prob >= 0.7 else ("#f59e0b" if prob >= 0.4 else "#ef4444")

            verify_at = pd.get("verify_at", 0)
            remain = _fmt_remaining(max(0, verify_at - now)) if verify_at > 0 else "—"

            rows += f"""
            <div style="display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 6px; padding: 5px 0;
                        border-bottom: 1px solid rgba(255,255,255,.04); align-items: center; font-size: 11px;">
                <div style="color: #e2e8f0;">{html.escape(str(pd.get("from_market", "?")))} → {html.escape(str(pd.get("to_market", "?")))}</div>
                <div>{dir_badge}</div>
                <div style="color: {prob_color}; font-weight: 600;">{prob_pct}%</div>
                <div style="text-align: right; color: #f59e0b;">⏱ {remain}</div>
            </div>
            """

        body += f"""
        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.06);">
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px;">
                📋 活跃预测 <span style="color: #475569;">({len(active_predictions)} 个)</span>
            </div>
            <div style="background: rgba(59,130,246,.04); border: 1px solid rgba(59,130,246,.1);
                        border-radius: 8px; padding: 6px 12px;">
                <div style="display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 6px; padding-bottom: 4px;
                            border-bottom: 1px solid rgba(255,255,255,.08); font-size: 11px; color: #64748b;">
                    <div>路径</div><div>方向</div><div>置信度</div><div style="text-align: right;">验证</div>
                </div>
                {rows}
            </div>
        </div>
        """

    put_html(card(title="流动性预测闭环", icon="🔮", meta=meta, body=body))
