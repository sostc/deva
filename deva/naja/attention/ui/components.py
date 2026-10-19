"""Attention Kernel UI - 注意力系统仍在用的展示组件

❗这里**只放有调用方的面板**：决策计划（``render_decision_plan_panel``），
由 ``/awakening`` 页面消费。

新闻摘要（原 ``render_news_digest_panel``）已于 2026-10-19 **搬到独立页面**
``/news``（``deva/naja/news/page.py``），改用报告级呈现 —— 原来是 64 字截断的
紧凑列表，条目一多就读不了。这里不再保留旧面板，避免两份 UI 各自漂移。

早期那批「Kernel 可视化」面板（QueryState / MultiHead / Memory / Feedback /
注意力流转图 / 末那识状态）已全部退役 —— 详见下方注释。
"""

# ❗以下 8 个渲染函数已于 2026-10-15 退役并删除（原因见当日日志）：
#
#   render_kernel_dashboard / render_query_state_panel / render_multi_head_panel /
#   render_memory_panel / render_feedback_panel / render_kernel_live_view /
#   render_attention_flow_diagram / render_manas_engine_status
#
# 它们**全仓零调用方**（唯一在跑的注意力页面是 ``/awakening`` →
# ``dashboard.render_attention_monitor_page``，它只用 ``render_awakening_status`` /
# ``render_decision_plan_panel``）。
#
# ❗最该删的是 ``render_kernel_live_view`` —— 它**硬编码**了一份假的
# ``query_state``（``market_regime: {"type": "trend"}`` / ``risk_bias: 0.6`` /
# ``attention_focus: {"market": 0.8, "news": 0.5}``，且**根本没有**
# ``macro_liquidity_signal`` 键），再喂给 ``render_query_state_panel`` —— 于是
# 面板永远显示「TREND + 风险偏好 0.60 + 宏观流动性 0.50 中性」。
# 这些看着像「系统状态」的数全是字面量，跟真实决策链一点关系没有，
# 属于「页面显示错 = 系统状态错」的典型。
#
# 真要看 QueryState 走 ``GET /api/query/state``（``api_extensions.py``）。

# 行动档位 → （中文名, 颜色）。权威档位来自 manas（见 decision/plan.py）。
_ACTION_LABELS = {
    "hold": ("不动", "#64748b"),
    "act_minimally": ("轻仓试探", "#d97706"),
    "act_carefully": ("谨慎行动", "#ea580c"),
    "act_fully": ("全力行动", "#16a34a"),
}

# 方向 → （中文名, 颜色）。遵循中国市场惯例：买入红、卖出绿。
_SIDE_LABELS = {
    "buy": ("买入", "#dc2626"),
    "sell": ("卖出", "#16a34a"),
    "none": ("无方向", "#64748b"),
    "hold": ("持有", "#64748b"),
}


def _esc(value) -> str:
    """HTML 转义（面板里可能出现来自信号的自由文本）。"""
    from html import escape
    return escape(str(value if value is not None else ""))


def _render_plan_row(plan: dict) -> str:
    """渲染"最近决策"里的一行。"""
    action = str(plan.get("action_type", "hold"))
    action_text, action_color = _ACTION_LABELS.get(action, (action, "#64748b"))
    side = str(plan.get("side", "none"))
    side_text, side_color = _SIDE_LABELS.get(side, (side, "#64748b"))
    symbol = _esc(plan.get("symbol") or "-")
    size_hint = float(plan.get("size_hint") or 0.0)
    confidence = float(plan.get("confidence") or 0.0)
    approved = plan.get("approved")

    if approved is True:
        badge, badge_color = "已批准", "#16a34a"
    elif approved is False:
        badge, badge_color = "已否决", "#dc2626"
    else:
        badge, badge_color = "—", "#64748b"

    return f"""
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;
                padding: 6px 8px; border-radius: 6px; background: #f8fafc; margin-bottom: 4px;">
        <div style="display: flex; align-items: center; gap: 8px; min-width: 0;">
            <span style="font-size: 12px; font-weight: 600; color: #0f172a;">{symbol}</span>
            <span style="font-size: 11px; color: {side_color};">{side_text}</span>
            <span style="font-size: 11px; color: {action_color}; font-weight: 600;">{action_text}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 10px; white-space: nowrap;">
            <span style="font-size: 10px; color: #64748b;">仓位 {size_hint:.0%}</span>
            <span style="font-size: 10px; color: #64748b;">置信 {confidence:.2f}</span>
            <span style="font-size: 10px; color: {badge_color}; font-weight: 600;">{badge}</span>
        </div>
    </div>
    """


def render_decision_plan_panel(summary: dict = None) -> str:
    """渲染「决策计划」面板——直接消费 ``DecisionPlan``（经 query service 的 dict）。

    这是决策层产物在 dashboard 的唯一入口：动什么 / 怎么动 / 动多大 / 为什么，
    全部读 ``DecisionPlan`` 字段，而不再从 manas 的散字段（manas_score /
    harmony_strength / should_act …）里"拼"一个决策出来。

    Args:
        summary: ``decision.query.get_decision_plan_summary()`` 的返回；为 ``None``
                 时自行取一次。
    """
    if summary is None:
        try:
            from deva.naja.decision import get_decision_plan_summary
            summary = get_decision_plan_summary(limit=10)
        except Exception as e:
            return (
                '<div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 10px; '
                'padding: 14px; margin: 10px 0; font-size: 12px; color: #b91c1c;">'
                f'🎯 决策计划面板不可用: {_esc(e)}</div>'
            )

    if not summary.get("available"):
        reason = summary.get("reason") or "尚未产生决策（等待策略信号）"
        return f"""
    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
                padding: 14px; margin: 10px 0;">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
            <span style="font-size: 18px;">🎯</span>
            <span style="font-size: 14px; font-weight: 600; color: #0f172a;">决策计划</span>
            <span style="font-size: 10px; color: #64748b; background: #e2e8f0; padding: 2px 6px;
                         border-radius: 4px;">DecisionPlan</span>
        </div>
        <div style="font-size: 12px; color: #64748b;">{_esc(reason)}</div>
    </div>
    """

    latest = summary.get("latest") or {}
    stats = summary.get("stats") or {}
    recent = summary.get("recent") or []

    persisted = bool(stats.get("persisted"))
    persisted_text = "已落盘" if persisted else "仅内存"
    persisted_color = "#16a34a" if persisted else "#d97706"

    action = str(latest.get("action_type", "hold"))
    action_text, action_color = _ACTION_LABELS.get(action, (action, "#64748b"))
    side = str(latest.get("side", "none"))
    side_text, side_color = _SIDE_LABELS.get(side, (side, "#64748b"))

    size_hint = float(latest.get("size_hint") or 0.0)
    confidence = float(latest.get("confidence") or 0.0)
    risk_temp = float(latest.get("risk_temperature") or 1.0)
    gate_reason = _esc(latest.get("gate_reason") or "（未记录）")
    reasons = latest.get("reasons") or []
    reasons_html = "".join(
        f'<div style="font-size: 11px; color: #334155; line-height: 1.5;">· {_esc(r)}</div>'
        for r in reasons[:6]
    ) or '<div style="font-size: 11px; color: #94a3b8;">（无附加理由）</div>'

    approved = latest.get("approved")
    if approved is True:
        approved_text, approved_color = "已批准", "#16a34a"
    elif approved is False:
        approved_text, approved_color = "已否决", "#dc2626"
    else:
        approved_text, approved_color = "—", "#64748b"

    recent_html = "".join(_render_plan_row(p) for p in recent[1:6]) or (
        '<div style="font-size: 11px; color: #94a3b8;">（暂无更早记录）</div>'
    )

    return f"""
    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px;
                padding: 14px; margin: 10px 0;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 18px;">🎯</span>
                <div>
                    <div style="font-size: 14px; font-weight: 600; color: #0f172a;">决策计划</div>
                    <div style="font-size: 11px; color: #64748b;">
                        决策层唯一产物 · 累计 {int(stats.get('total', 0))} 条
                        （可执行 {int(stats.get('actionable', 0))}）·
                        <span style="color: {persisted_color};">{persisted_text}</span>
                    </div>
                </div>
            </div>
            <div style="background: {approved_color}1a; border: 1px solid {approved_color};
                        border-radius: 12px; padding: 4px 10px; font-size: 12px;
                        font-weight: 600; color: {approved_color};">{approved_text}</div>
        </div>

        <div style="display: grid; grid-template-columns: 1.2fr 1fr 1fr 1fr; gap: 10px; margin-bottom: 12px;">
            <div style="background: #f8fafc; border-radius: 6px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">标的 / 方向</div>
                <div style="font-size: 15px; font-weight: 600; color: #0f172a;">
                    {_esc(latest.get('symbol') or '-')}
                    <span style="font-size: 12px; color: {side_color};">{side_text}</span>
                </div>
            </div>
            <div style="background: #f8fafc; border-radius: 6px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">行动档位</div>
                <div style="font-size: 15px; font-weight: 600; color: {action_color};">{action_text}</div>
            </div>
            <div style="background: #f8fafc; border-radius: 6px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">仓位乘子</div>
                <div style="font-size: 15px; font-weight: 600; color: #0f172a;">{size_hint:.0%}</div>
            </div>
            <div style="background: #f8fafc; border-radius: 6px; padding: 10px; text-align: center;">
                <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">置信 / 风险温度</div>
                <div style="font-size: 15px; font-weight: 600; color: #0f172a;">{confidence:.2f}
                    <span style="font-size: 11px; color: #64748b;">/ {risk_temp:.2f}</span>
                </div>
            </div>
        </div>

        <div style="background: #f8fafc; border-radius: 6px; padding: 10px; margin-bottom: 12px;">
            <div style="font-size: 11px; font-weight: 600; color: #0f172a; margin-bottom: 6px;">
                🚦 为什么这样动（行动门理由）
            </div>
            <div style="font-size: 11px; color: #334155; line-height: 1.5;">{gate_reason}</div>
        </div>

        <div style="background: #f8fafc; border-radius: 6px; padding: 10px; margin-bottom: 12px;">
            <div style="font-size: 11px; font-weight: 600; color: #0f172a; margin-bottom: 6px;">
                📝 决策理由（融合层留痕）
            </div>
            {reasons_html}
        </div>

        <div>
            <div style="font-size: 11px; font-weight: 600; color: #0f172a; margin-bottom: 6px;">
                🕘 最近决策
            </div>
            {recent_html}
        </div>
    </div>
    """


__all__ = [
    "render_decision_plan_panel",
]
