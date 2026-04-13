"""策略分配器面板 - 展示 StrategyAllocator 的动态分配状态"""

import logging

log = logging.getLogger(__name__)


def render_strategy_allocator_panel() -> str:
    """渲染策略分配器面板

    数据源: StrategyAllocator (非 SR 注册，通过 strategy_manager 获取)
    key method: get_allocation_summary()
    返回字段: active_count, by_scope, decision (alpha/temperature/courage)
    """
    try:
        from deva.naja.market_hotspot.strategies import get_strategy_manager
        manager = get_strategy_manager()
        if not manager:
            return _render_empty("策略管理器未初始化")

        allocator = getattr(manager, 'allocator', None)
        if not allocator:
            return _render_empty("策略分配器未启用")

        summary = allocator.get_allocation_summary()
        if not summary:
            return _render_empty("暂无分配数据")

        active_count = summary.get('active_count', 0)
        by_scope = summary.get('by_scope', {})
        decision = summary.get('decision', {})

        alpha = decision.get('alpha', 0)
        temperature = decision.get('temperature', 1.0)
        courage = decision.get('courage', 0.5)

        # alpha 颜色
        if alpha > 0.5:
            alpha_color = "#16a34a"
            alpha_label = "积极"
        elif alpha > 0:
            alpha_color = "#ca8a04"
            alpha_label = "中性"
        else:
            alpha_color = "#dc2626"
            alpha_label = "保守"

        # scope 分布
        scope_items = ""
        scope_colors = {'CN': '#dc2626', 'US': '#3b82f6', 'ALL': '#a855f7'}
        for scope, count in by_scope.items():
            color = scope_colors.get(scope, '#64748b')
            scope_items += f"""
            <div style="text-align: center; padding: 6px; background: rgba(255,255,255,0.05); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: {color};">{count}</div>
                <div style="font-size: 8px; color: #64748b;">{scope}</div>
            </div>"""

        if not scope_items:
            scope_items = '<div style="color: #64748b; font-size: 9px; grid-column: span 3; text-align: center;">暂无</div>'

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
            <div style="font-size: 13px; font-weight: 600; color: #8b5cf6;">
                🎲 策略分配器
            </div>
            <div style="font-size: 9px; color: #64748b;">
                活跃策略: {active_count}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 10px;">
            <div style="text-align: center; padding: 8px; background: rgba(139,92,246,0.1); border-radius: 4px;">
                <div style="font-size: 16px; font-weight: 700; color: {alpha_color};">{alpha:.2f}</div>
                <div style="font-size: 8px; color: #64748b;">Alpha ({alpha_label})</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(251,146,60,0.1); border-radius: 4px;">
                <div style="font-size: 16px; font-weight: 700; color: #fb923c;">{temperature:.2f}</div>
                <div style="font-size: 8px; color: #64748b;">Temperature</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(14,165,233,0.1); border-radius: 4px;">
                <div style="font-size: 16px; font-weight: 700; color: #0ea5e9;">{courage:.2f}</div>
                <div style="font-size: 8px; color: #64748b;">Courage</div>
            </div>
        </div>

        <div style="font-size: 8px; color: #64748b; margin-bottom: 4px;">📊 市场分布</div>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px;">
            {scope_items}
        </div>
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
        <div style="font-size: 13px; font-weight: 600; color: #8b5cf6; margin-bottom: 10px;">
            🎲 策略分配器
        </div>
        <div style="text-align: center; padding: 15px; color: #64748b; font-size: 11px;">
            {msg}
        </div>
    </div>
    """
