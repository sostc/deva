"""美股市场热点 UI 组件

复用手游 UI 组件实现美股数据混合展示
"""

from typing import Dict, Any, List, Tuple
import logging

log = logging.getLogger(__name__)


def get_us_hotspot_data() -> Dict[str, Any]:
    """获取美股热点数据"""
    try:
        from deva.naja.market_hotspot.integration import get_market_hotspot_integration
        integration = get_market_hotspot_integration()
        log.debug(f"[US-UI] get_us_hotspot_data: integration={integration is not None}")

        if integration is None:
            log.warning("[US-UI] integration 为 None")
            return {}

        log.debug(f"[US-UI] integration._initialized={getattr(integration, '_initialized', 'N/A')}")
        log.debug(f"[US-UI] integration.hotspot_system={getattr(integration, 'hotspot_system', 'N/A')}")

        if integration.hotspot_system is None:
            log.warning("[US-UI] hotspot_system 为 None")
            return {}

        result = integration.hotspot_system.get_us_hotspot_state()
        sw = result.get('symbol_weights', {})
        log.debug(f"[US-UI] symbol_weights count={len(sw)}, top5={sorted(sw.items(), key=lambda x: x[1], reverse=True)[:5]}")
        return result
    except Exception as e:
        log.error(f"[US-UI] 获取美股热点数据失败: {e}")
        import traceback
        traceback.print_exc()
    return {}



def render_cross_market_predictions() -> str:
    """渲染跨市场预测面板 - 基于美股题材预测明日A股"""
    try:
        from deva.naja.knowledge.alaya.awakened_alaya import AwakenedAlaya
        alaya = AwakenedAlaya()
        if not hasattr(alaya, 'cross_market_memory') or not alaya.cross_market_memory:
            log.info("[CrossMarket] cross_market_memory 不存在")
            return ""

        us_data = get_us_hotspot_data()
        if not us_data:
            log.info("[CrossMarket] us_data 为空")
            return ""

        current_conditions = {}

        patterns = alaya.cross_market_memory.recall_applicable_patterns(
            target_market="a_stock",
            current_conditions=current_conditions
        )

        log.info(f"[CrossMarket] 召回 patterns 数量: {len(patterns) if patterns else 0}")

        if not patterns:
            return ""

        html = """<div style="background: linear-gradient(135deg, #fef3c7, #fde68a); border: 1px solid #f59e0b; border-radius: 12px; padding: 16px; margin-top: 16px;">
<div style="font-weight: 600; color: #92400e; margin-bottom: 12px; font-size: 14px;">🔮 跨市场预测 <span style="font-size: 11px; font-weight: normal; color: #a16207;">基于美股题材 → 预测明日A股</span></div>
<div style="display: flex; flex-direction: column; gap: 10px;">"""

        for i, pattern in enumerate(patterns[:5], 1):
            conditions = pattern.get("conditions", {})
            us_block = conditions.get("us_block", "未知")
            us_weight = conditions.get("us_weight", 0)
            prediction = pattern.get("prediction", "")

            a_blocks = []
            try:
                from deva.naja.knowledge.alaya.awakened_alaya import CrossMarketBlockMapper
                a_blocks = CrossMarketBlockMapper.get_a_stock_blocks(us_block)
            except Exception:
                pass

            if not a_blocks:
                a_blocks = [conditions.get("a_block", "A股相关题材")]

            block_tags = " ".join([f"<span style='background: #fef3c7; padding: 2px 6px; border-radius: 4px; font-size: 11px; color: #92400e;'>{s}</span>" for s in a_blocks[:3]])

            html += f"""<div style="background: rgba(255,255,255,0.7); border-radius: 8px; padding: 10px;">
<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
<span style="background: #f59e0b; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">TOP {i}</span>
<span style="font-weight: 600; color: #78350f; font-size: 13px;">🇺🇸 {us_block}</span>
<span style="color: #a16207; font-size: 11px;">权重 {us_weight:.2f}</span>
</div>
<div style="margin-bottom: 6px;">{block_tags}</div>
<div style="font-size: 11px; color: #a16207;">{prediction}</div>
</div>"""

        html += """</div></div>"""
        return html
    except Exception as e:
        log.debug(f"[CrossMarket] 渲染预测面板失败: {e}")
        return ""


def get_us_market_summary() -> Dict[str, Any]:
    """获取美股市场摘要（包含涨跌统计）"""
    us_data = get_us_hotspot_data()
    log.debug(f"[US-UI] get_us_market_summary: us_data={us_data}")

    if not us_data:
        return {
            'stock_count': 0,
            'up_count': 0,
            'down_count': 0,
            'flat_count': 0,
            'up_ratio': 0,
            'global_hotspot': 0.5,
            'activity': 0.5,
        }

    block_hotspot = us_data.get('block_hotspot', {})
    symbol_changes = us_data.get('symbol_changes', {})

    total = len(symbol_changes)
    up_count = sum(1 for c in symbol_changes.values() if c is not None and c > 0)
    down_count = sum(1 for c in symbol_changes.values() if c is not None and c < 0)
    flat_count = total - up_count - down_count
    up_ratio = up_count / total if total > 0 else 0

    return {
        'stock_count': total,
        'up_count': up_count,
        'down_count': down_count,
        'flat_count': flat_count,
        'up_ratio': up_ratio,
        'global_hotspot': us_data.get('global_hotspot', 0.5),
        'activity': us_data.get('activity', 0.5),
        'block_count': len(block_hotspot),
    }


def render_us_market_summary() -> str:
    """渲染美股市场摘要（涨跌分布）"""
    summary = get_us_market_summary()

    if summary['stock_count'] == 0:
        from .common import get_market_phase_summary, get_ui_mode_context
        phase_summary = get_market_phase_summary()
        mode_ctx = get_ui_mode_context()
        us_info = phase_summary.get('us', {})
        phase_name = us_info.get('phase_name', '休市')
        next_phase = us_info.get('next_phase_name', '')
        next_time = us_info.get('next_change_time', '')
        next_hint = f" →{next_phase} {next_time}" if us_info.get('phase') == 'closed' and next_time else ""
        mode_label = mode_ctx.get('mode_label', '实盘模式')
        time_hint = mode_ctx.get('market_time_str', '') if mode_ctx.get('is_replay') else ""
        return f"""<div style="background: #1e3a5f; border-radius: 8px; padding: 16px; margin-top: 12px;">
<div style="color: #94a3b8; font-size: 12px;">🇺🇸 美股状态: {phase_name}{next_hint} | {mode_label} {time_hint}</div>
</div>"""

    global_hotspot = summary['global_hotspot']
    activity = summary['activity']
    up_count = summary['up_count']
    down_count = summary['down_count']
    flat_count = summary['flat_count']
    total = summary['stock_count']

    up_pct = up_count / total * 100 if total > 0 else 0
    down_pct = down_count / total * 100 if total > 0 else 0
    flat_pct = flat_count / total * 100 if total > 0 else 0

    hotspot_bar = global_hotspot * 100
    activity_bar = activity * 100

    html = f"""<div style="background: #1e3a5f; border-radius: 8px; padding: 16px; margin-top: 12px;">
<div style="display: flex; justify-content: space-between; margin-bottom: 12px;">
<div style="color: #f8fafc; font-size: 14px; font-weight: 600;">🇺🇸 美股涨跌分布</div>
<div style="color: #94a3b8; font-size: 11px;">{total} 只股票</div>
</div>
<div style="display: flex; gap: 4px; height: 24px; border-radius: 4px; overflow: hidden; margin-bottom: 12px;">
<div style="background: #22c55e; width: {up_pct}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 10px; font-weight: 600;" title="上涨 {up_count} 只">{up_pct:.0f}%</div>
<div style="background: #64748b; width: {flat_pct}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 10px; font-weight: 600;" title="平盘 {flat_count} 只">{flat_pct:.0f}%</div>
<div style="background: #ef4444; width: {down_pct}%; display: flex; align-items: center; justify-content: center; color: white; font-size: 10px; font-weight: 600;" title="下跌 {down_count} 只">{down_pct:.0f}%</div>
</div>
<div style="display: flex; justify-content: space-between; font-size: 11px;">
<div style="color: #94a3b8;">热点</div>
<div style="color: #94a3b8;">活跃度</div>
</div>
<div style="display: flex; gap: 8px; margin-top: 4px;">
<div style="flex: 1; background: #334155; height: 6px; border-radius: 3px; overflow: hidden;">
<div style="background: #22c55e; height: 100%; width: {hotspot_bar}%;"></div>
</div>
<div style="flex: 1; background: #334155; height: 6px; border-radius: 3px; overflow: hidden;">
<div style="background: #3b82f6; height: 100%; width: {activity_bar}%;"></div>
</div>
</div>
<div style="display: flex; justify-content: space-between; font-size: 10px; margin-top: 4px;">
<div style="color: #22c55e;">{global_hotspot:.3f}</div>
<div style="color: #3b82f6;">{activity:.3f}</div>
</div>
</div>"""

    return html
