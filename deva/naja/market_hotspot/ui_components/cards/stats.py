"""热点系统 UI - 统计与状态卡片"""

import logging
from typing import Dict, Any
from deva.naja.register import SR
from deva.naja.market_hotspot.ui_components.styles import (
    heat_level,
    GRADIENT_US_MARKET, GRADIENT_INFO, GRADIENT_PINK, GRADIENT_SUCCESS,
    GRADIENT_NEUTRAL_DARK, GRADIENT_NEUTRAL, GRADIENT_WARNING,
    GRADIENT_PURPLE, GRADIENT_DANGER,
)

log = logging.getLogger(__name__)

def render_frequency_distribution(freq_summary: Dict[str, int]) -> str:
    """渲染频率分布"""
    high = freq_summary.get('high_frequency', 0)
    medium = freq_summary.get('medium_frequency', 0)
    low = freq_summary.get('low_frequency', 0)
    total = high + medium + low or 1

    high_pct = high / total * 100
    medium_pct = medium / total * 100
    low_pct = low / total * 100

    return f"""
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">📊 频率分布</div>
        <div style="margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;"><span style="color: #dc2626; font-weight: 600;">🔴 高频</span><span>{high} 只 ({high_pct:.1f}%)</span></div>
            <div style="background: #fee2e2; height: 8px; border-radius: 4px; overflow: hidden;"><div style="background: #dc2626; height: 100%; width: {high_pct}%; transition: width 0.3s;"></div></div>
        </div>
        <div style="margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;"><span style="color: #ca8a04; font-weight: 600;">🟡 中频</span><span>{medium} 只 ({medium_pct:.1f}%)</span></div>
            <div style="background: #fef3c7; height: 8px; border-radius: 4px; overflow: hidden;"><div style="background: #ca8a04; height: 100%; width: {medium_pct}%; transition: width 0.3s;"></div></div>
        </div>
        <div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;"><span style="color: #16a34a; font-weight: 600;">🟢 低频</span><span>{low} 只 ({low_pct:.1f}%)</span></div>
            <div style="background: #dcfce7; height: 8px; border-radius: 4px; overflow: hidden;"><div style="background: #16a34a; height: 100%; width: {low_pct}%; transition: width 0.3s;"></div></div>
        </div>
    </div>
    """


def render_strategy_status(strategy_stats: Dict[str, Any]) -> str:
    """渲染策略状态"""
    if not strategy_stats:
        return "<div style='color: #64748b;'>暂无策略数据</div>"

    strategies = strategy_stats.get('strategy_stats', {})
    total_signals = strategy_stats.get('total_signals_generated', 0)

    html = f"""<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;"><div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">🎯 策略状态 <span style="color: #3b82f6; font-size: 14px;">(总信号: {total_signals})</span></div>"""

    for strategy_id, stats in strategies.items():
        status = "🟢" if stats.get('enabled') else "🔴"
        name = stats.get('name', strategy_id)
        exec_count = stats.get('execution_count', 0)
        signal_count = stats.get('signal_count', 0)
        skip_count = stats.get('skip_count', 0)
        priority = stats.get('priority', 5)

        if skip_count > 0:
            if priority < 5:
                skip_reason = "(市场冷清)"
            elif priority < 8:
                skip_reason = "(热点不足)"
            else:
                skip_reason = "(冷却中)"
        else:
            skip_reason = ""

        html += f"""<div style="display: flex; justify-content: space-between; align-items: center; padding: 12px; margin-bottom: 8px; background: #f8fafc; border-radius: 8px; border-left: 3px solid {'#22c55e' if stats.get('enabled') else '#ef4444'};"><div><div style="font-weight: 500;">{status} {name}</div><div style="font-size: 12px; color: #64748b; margin-top: 2px;">执行: {exec_count} | 信号: {signal_count} | 跳过: {skip_count} {skip_reason}</div></div><div style="font-size: 12px; color: #64748b;">优先级: {priority}</div></div>"""

    html += "</div>"
    return html


def render_dual_engine_status(dual_summary: Dict[str, Any]) -> str:
    """渲染双引擎状态"""
    if not dual_summary:
        return ""

    river_stats = dual_summary.get('river_stats', {})
    pytorch_stats = dual_summary.get('pytorch_stats', {})
    trigger_count = dual_summary.get('trigger_count', 0)

    processed = river_stats.get('processed_count', 0)
    anomalies = river_stats.get('anomaly_count', 0)
    anomaly_ratio = (anomalies / max(processed, 1)) * 100

    queue_size = pytorch_stats.get('pending_queue_size', 0)
    inference_count = pytorch_stats.get('inference_count', 0)

    if queue_size > 10000 and inference_count == 0:
        queue_status, queue_color = "⚠️ 严重积压", "#dc2626"
    elif queue_size > 1000:
        queue_status, queue_color = "⏳ 队列积压", "#f59e0b"
    else:
        queue_status, queue_color = "✅ 正常", "#16a34a"

    return f"""
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">⚙️ 双引擎状态 <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">轻量筛选 → 深度分析</span></div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
            <div style="background: {GRADIENT_INFO}; padding: 16px; border-radius: 8px;">
                <div style="font-weight: 600; color: #1e40af; margin-bottom: 8px;">🌊 轻量检测 <span style="font-size: 10px; color: #64748b; font-weight: normal;">(River)</span></div>
                <div style="font-size: 12px; color: #1e3a8a; line-height: 1.6;">
                    <div style="display: flex; justify-content: space-between;"><span>处理数据:</span><span style="font-weight: 600;">{processed:,}</span></div>
                    <div style="display: flex; justify-content: space-between;"><span>异动检测:</span><span style="font-weight: 600;">{anomalies:,}</span></div>
                    <div style="display: flex; justify-content: space-between;"><span>异常率:</span><span style="font-weight: 600;">{anomaly_ratio:.1f}%</span><span style="font-size: 10px; color: #64748b;">(正常10-20%)</span></div>
                    <div style="display: flex; justify-content: space-between;"><span>活跃股票:</span><span style="font-weight: 600;">{river_stats.get('active_symbols', 0)} 只</span></div>
                </div>
                <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #93c5fd; font-size: 11px; color: #3b82f6;">💡 快速检测价格/成交量异常波动</div>
            </div>
            <div style="background: {GRADIENT_PINK}; padding: 16px; border-radius: 8px;">
                <div style="font-weight: 600; color: #9d174d; margin-bottom: 8px;">🔥 深度分析 <span style="font-size: 10px; color: #64748b; font-weight: normal;">(PyTorch)</span></div>
                <div style="font-size: 12px; color: #831843; line-height: 1.6;">
                    <div style="display: flex; justify-content: space-between;"><span>深度推理:</span><span style="font-weight: 600;">{inference_count:,}</span></div>
                    <div style="display: flex; justify-content: space-between;"><span>待处理队列:</span><span style="font-weight: 600; color: {queue_color};">{queue_size:,}</span></div>
                    <div style="display: flex; justify-content: space-between;"><span>队列状态:</span><span style="font-weight: 600; color: {queue_color};">{queue_status}</span></div>
                    <div style="display: flex; justify-content: space-between;"><span>处理中:</span><span style="font-weight: 600;">{pytorch_stats.get('processing_count', 0)}</span></div>
                </div>
                <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #f9a8d4; font-size: 11px; color: #db2777;">💡 深度学习模型分析严重异常</div>
            </div>
        </div>
        <div style="margin-top: 16px; padding: 12px; background: {GRADIENT_SUCCESS}; border-radius: 8px; border: 1px solid #86efac;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div><span style="font-weight: 600; color: #166534;">🔗 双引擎触发次数:</span><span style="font-size: 18px; font-weight: 700; color: #15803d; margin-left: 8px;">{trigger_count}</span></div>
                <div style="font-size: 11px; color: #22c55e; text-align: right;">River检测到严重异常 → 触发PyTorch深度分析</div>
            </div>
        </div>
        <div style="margin-top: 12px; padding: 12px; background: #f8fafc; border-radius: 6px; font-size: 11px; color: #64748b; line-height: 1.5;">
            <strong>📊 数据解读:</strong><br>• <strong>异常率</strong>: 价格/成交量超出正常统计范围的数据占比（正常约10-20%）<br>• <strong>队列积压</strong>: River检测到异常但PyTorch未触发<br>• <strong>触发机制</strong>: 只有当异常达到严重程度时，才会触发PyTorch深度推理
        </div>
    </div>
    """
def render_noise_filter_status() -> str:
    """渲染噪音过滤状态"""
    try:
        hotspot_system = SR('hotspot_system')
        noise_filter = hotspot_system.noise_filter
        stats = noise_filter.get_stats()

        total = stats.get('total_processed', 0)
        filtered = stats.get('total_filtered', 0)
        filter_rate = stats.get('filter_rate', '0.00%')
        config = stats.get('config', {})
        top_filtered = stats.get('top_filtered_symbols', [])
        blacklist_size = stats.get('blacklist_size', 0)
        whitelist_size = stats.get('whitelist_size', 0)

        rate_value = float(filter_rate.replace('%', ''))
        rate_color = '#dc2626' if rate_value > 30 else ('#f59e0b' if rate_value > 10 else '#16a34a')
        rate_bg = '#fef2f2' if rate_value > 30 else ('#fffbeb' if rate_value > 10 else '#f0fdf4')

        html = f"""
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">🔇 噪音过滤状态 <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">低流动性股票过滤</span></div>
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-bottom: 16px;">
            <div style="background: {GRADIENT_NEUTRAL_DARK}; padding: 12px; border-radius: 8px; text-align: center;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">总处理</div>
                <div style="font-size: 20px; font-weight: 700; color: #1e293b;">{total:,}</div>
                <div style="font-size: 10px; color: #94a3b8;">条记录</div>
            </div>
            <div style="background: linear-gradient(135deg, {rate_bg}, #ffffff); padding: 12px; border-radius: 8px; text-align: center; border: 1px solid {rate_color}33;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">已过滤</div>
                <div style="font-size: 20px; font-weight: 700; color: {rate_color};">{filtered:,}</div>
                <div style="font-size: 10px; color: {rate_color};">{filter_rate}</div>
            </div>
            <div style="background: {GRADIENT_NEUTRAL_DARK}; padding: 12px; border-radius: 8px; text-align: center;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">黑白名单</div>
                <div style="font-size: 16px; font-weight: 600; color: #1e293b;"><span style="color: #dc2626;">⚫ {blacklist_size}</span><span style="color: #94a3b8; margin: 0 4px;">|</span><span style="color: #16a34a;">⚪ {whitelist_size}</span></div>
                <div style="font-size: 10px; color: #94a3b8;">黑名单 | 白名单</div>
            </div>
        </div>
        <div style="background: #f8fafc; padding: 12px; border-radius: 8px; margin-bottom: 12px;">
            <div style="font-size: 12px; font-weight: 600; color: #1e293b; margin-bottom: 8px;">📋 过滤阈值配置</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; font-size: 11px;">
                <div style="text-align: center; padding: 8px; background: white; border-radius: 6px;"><div style="color: #64748b;">最小金额</div><div style="font-weight: 600; color: #1e293b;">{config.get('min_amount', 1000000):,.0f}</div></div>
                <div style="text-align: center; padding: 8px; background: white; border-radius: 6px;"><div style="color: #64748b;">最小成交量</div><div style="font-weight: 600; color: #1e293b;">{config.get('min_volume', 100000):,.0f}</div></div>
                <div style="text-align: center; padding: 8px; background: white; border-radius: 6px;"><div style="color: #64748b;">动态阈值</div><div style="font-weight: 600; color: #1e293b;">{'✅ 启用' if config.get('dynamic_threshold') else '❌ 禁用'}</div></div>
            </div>
        </div>
        {''.join([f'<span style="font-size: 11px; padding: 4px 8px; background: #fee2e2; color: #dc2626; border-radius: 4px;">{sym}: {cnt}次</span>' for sym, cnt in top_filtered[:5]]) if top_filtered else ''}
        <div style="margin-top: 12px; padding: 10px; background: #f0f9ff; border-radius: 6px; font-size: 11px; color: #0369a1; line-height: 1.5;">
            <strong>💡 过滤规则:</strong><br>• 成交金额低于阈值的股票会被过滤（如南玻Ｂ等低流动性B股）<br>• B股默认会被过滤（名称以"Ｂ"或"B"结尾）<br>• 黑名单中的股票会被强制过滤，白名单中的股票会被保护
        </div>
    </div>
        """
        return html
    except Exception as e:
        return f"""<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;"><div style="font-weight: 600; margin-bottom: 8px; color: #1e293b;">🔇 噪音过滤状态</div><div style="color: #64748b; font-size: 13px;">加载失败: {e}</div></div>"""

