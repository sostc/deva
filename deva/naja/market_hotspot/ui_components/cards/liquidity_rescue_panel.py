"""流动性救援面板 - 展示恐慌分析和流动性危机监控状态"""

import logging

log = logging.getLogger(__name__)


def render_liquidity_rescue_panel() -> str:
    """渲染流动性救援面板

    数据源:
    - PanicAnalyzer.get_stats() → history_size, last_panic_score, last_liquidity_score, panic_trend
    - PanicAnalyzer.is_panic_peak() → bool
    - LiquidityRescueFilter.get_filter_stats() → total_checked, rescued_count, rescue_rate
    """
    try:
        from deva.naja.market_hotspot.filters.panic_analyzer import PanicAnalyzer
        from deva.naja.market_hotspot.filters.liquidity_rescue_filter import LiquidityRescueFilter

        # 获取 PanicAnalyzer 实例（通过 hotspot_system）
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration
        integration = get_market_hotspot_integration()
        if not integration or not integration.hotspot_system:
            return _render_empty("热点系统未初始化")

        hs = integration.hotspot_system
        panic_analyzer = getattr(hs, 'panic_analyzer', None)
        rescue_filter = getattr(hs, 'liquidity_rescue_filter', None)

        # 恐慌数据
        if panic_analyzer:
            panic_stats = panic_analyzer.get_stats()
            panic_score = panic_stats.get('last_panic_score', 0)
            liquidity_score = panic_stats.get('last_liquidity_score', 0)
            panic_trend = panic_stats.get('panic_trend', 'stable')
            history_size = panic_stats.get('history_size', 0)
            is_peak = panic_analyzer.is_panic_peak()
        else:
            panic_score = 0
            liquidity_score = 0
            panic_trend = 'stable'
            history_size = 0
            is_peak = False

        # 救援过滤数据
        if rescue_filter:
            filter_stats = rescue_filter.get_filter_stats()
            total_checked = filter_stats.get('total_checked', 0)
            rescued_count = filter_stats.get('rescued_count', 0)
            rescue_rate = filter_stats.get('rescue_rate', 0)
        else:
            total_checked = 0
            rescued_count = 0
            rescue_rate = 0

        # 恐慌等级颜色
        if panic_score >= 0.8:
            panic_color, panic_label = "#dc2626", "🔴 极度恐慌"
        elif panic_score >= 0.6:
            panic_color, panic_label = "#ea580c", "🟠 高度恐慌"
        elif panic_score >= 0.3:
            panic_color, panic_label = "#ca8a04", "🟡 轻度恐慌"
        else:
            panic_color, panic_label = "#16a34a", "🟢 平稳"

        # 趋势箭头
        trend_map = {'rising': ('↑', '#dc2626'), 'falling': ('↓', '#16a34a'), 'stable': ('→', '#64748b')}
        trend_arrow, trend_color = trend_map.get(panic_trend, ('→', '#64748b'))

        peak_badge = '<span style="background: #dc2626; color: white; padding: 1px 6px; border-radius: 4px; font-size: 8px; font-weight: 600; margin-left: 6px;">PEAK</span>' if is_peak else ''

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
            <div style="font-size: 13px; font-weight: 600; color: #f43f5e;">
                🛡️ 流动性救援 {peak_badge}
            </div>
            <div style="font-size: 9px; color: #64748b;">
                {panic_label}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 10px;">
            <div style="text-align: center; padding: 8px; background: rgba(244,63,94,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: {panic_color};">{panic_score:.2f}</div>
                <div style="font-size: 8px; color: #64748b;">恐慌指数</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(59,130,246,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #3b82f6;">{liquidity_score:.2f}</div>
                <div style="font-size: 8px; color: #64748b;">流动性</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(168,85,247,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: {trend_color};">{trend_arrow}</div>
                <div style="font-size: 8px; color: #64748b;">趋势</div>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(74,222,128,0.1); border-radius: 4px;">
                <div style="font-size: 14px; font-weight: 700; color: #4ade80;">{rescued_count}</div>
                <div style="font-size: 8px; color: #64748b;">已救援</div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
            <div style="padding: 6px; background: rgba(244,63,94,0.05); border-radius: 4px;">
                <div style="font-size: 8px; color: #f43f5e; margin-bottom: 2px;">📊 恐慌分析</div>
                <div style="font-size: 8px; color: #94a3b8;">历史数据: {history_size} 条</div>
            </div>
            <div style="padding: 6px; background: rgba(74,222,128,0.05); border-radius: 4px;">
                <div style="font-size: 8px; color: #4ade80; margin-bottom: 2px;">🛟 救援过滤</div>
                <div style="font-size: 8px; color: #94a3b8;">检查: {total_checked} | 率: {rescue_rate:.1f}%</div>
            </div>
        </div>

        <div style="padding: 4px; background: rgba(255,255,255,0.02); border-radius: 4px; margin-top: 8px;">
            <div style="height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden;">
                <div style="width: {min(100, panic_score * 100)}%; height: 100%; background: linear-gradient(90deg, #16a34a, #ca8a04, #dc2626);"></div>
            </div>
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
        <div style="font-size: 13px; font-weight: 600; color: #f43f5e; margin-bottom: 10px;">
            🛡️ 流动性救援
        </div>
        <div style="text-align: center; padding: 15px; color: #64748b; font-size: 11px;">
            {msg}
        </div>
    </div>
    """
