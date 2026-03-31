"""注意力系统 UI 卡片组件"""

from typing import Dict, Any


def render_attention_details_card(details: Dict[str, Any]) -> str:
    """渲染注意力计算详细数据（人类友好的算法展示）"""
    if not details or details.get('error'):
        return """
        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
            <div style="font-weight: 600; margin-bottom: 12px; color: #1e293b;">🧮 注意力计算详情</div>
            <div style="color: #64748b; text-align: center; padding: 20px;">暂无详细数据</div>
        </div>
        """

    total = details.get('total_stocks', 0)
    up_count = details.get('up_count', 0)
    down_count = details.get('down_count', 0)
    flat_count = details.get('flat_count', 0)
    up_ratio = details.get('up_ratio', 0)
    down_ratio = details.get('down_ratio', 0)
    flat_ratio = details.get('flat_ratio', 0)
    mean_abs_return = details.get('mean_abs_return', 0)
    volatility = details.get('volatility', 0)
    attention = details.get('attention', 0)
    activity = details.get('activity', 0)
    attention_level = details.get('attention_level', '未知')
    activity_level = details.get('activity_level', '未知')
    attention_formula = details.get('attention_formula', '')
    activity_formula = details.get('activity_formula', '')

    attention_color = "#dc2626" if attention >= 0.6 else ("#ca8a04" if attention >= 0.3 else "#16a34a")
    activity_color = "#dc2626" if activity >= 0.7 else ("#ca8a04" if activity >= 0.15 else "#16a34a")

    up_bar_width = max(int(up_ratio * 100), 2)
    down_bar_width = max(int(down_ratio * 100), 2)
    flat_bar_width = max(int(flat_ratio * 100), 2)

    html = f"""
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b; display: flex; align-items: center; gap: 8px;">
            🧮 注意力计算详情
            <span style="font-size: 11px; color: #64748b; font-weight: normal;">(算法解释)</span>
        </div>

        <div style="background: #f8fafc; border-radius: 8px; padding: 12px; margin-bottom: 16px;">
            <div style="font-size: 13px; font-weight: 600; color: #1e293b; margin-bottom: 8px;">
                📊 市场分布 ({total} 只股票)
            </div>
            <div style="display: flex; gap: 8px; margin-bottom: 8px;">
                <div style="flex: 1; text-align: center;">
                    <div style="background: #16a34a; height: 24px; border-radius: 4px; width: {up_bar_width}%; min-width: 4px;"></div>
                    <div style="font-size: 11px; color: #16a34a; font-weight: 600; margin-top: 4px;">上涨 {up_count}只</div>
                    <div style="font-size: 10px; color: #64748b;">{up_ratio:.1%}</div>
                </div>
                <div style="flex: 1; text-align: center;">
                    <div style="background: #dc2626; height: 24px; border-radius: 4px; width: {down_bar_width}%; min-width: 4px;"></div>
                    <div style="font-size: 11px; color: #dc2626; font-weight: 600; margin-top: 4px;">下跌 {down_count}只</div>
                    <div style="font-size: 10px; color: #64748b;">{down_ratio:.1%}</div>
                </div>
                <div style="flex: 1; text-align: center;">
                    <div style="background: #94a3b8; height: 24px; border-radius: 4px; width: {flat_bar_width}%; min-width: 4px;"></div>
                    <div style="font-size: 11px; color: #64748b; font-weight: 600; margin-top: 4px;">平盘 {flat_count}只</div>
                    <div style="font-size: 10px; color: #64748b;">{flat_ratio:.1%}</div>
                </div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px;">
            <div style="background: #fefce8; padding: 10px; border-radius: 6px;">
                <div style="font-size: 11px; color: #64748b;">📐 活跃度参数</div>
                <div style="font-size: 12px; color: #1e293b; margin-top: 4px;">
                    均值绝对值: <strong>{mean_abs_return:.4f}</strong><br>
                    波动率: <strong>{volatility:.4f}</strong>
                </div>
            </div>
            <div style="background: #f0f9ff; padding: 10px; border-radius: 6px;">
                <div style="font-size: 11px; color: #64748b;">📋 分类阈值</div>
                <div style="font-size: 12px; color: #1e293b; margin-top: 4px;">
                    上涨: &gt;0.1%<br>
                    下跌: &lt;-0.1%<br>
                    平盘: 其他
                </div>
            </div>
        </div>

        <div style="border-top: 1px solid #e2e8f0; padding-top: 12px;">
            <div style="font-size: 12px; font-weight: 600; color: #1e293b; margin-bottom: 8px;">
                🔍 计算公式解释
            </div>
            <div style="background: #f0fdf4; padding: 10px; border-radius: 6px; margin-bottom: 8px;">
                <div style="font-size: 11px; color: #16a34a; font-weight: 600; margin-bottom: 4px;">注意力 = {attention:.3f}</div>
                <div style="font-size: 11px; color: #64748b;">{attention_formula}</div>
            </div>
            <div style="background: #f0f9ff; padding: 10px; border-radius: 6px;">
                <div style="font-size: 11px; color: #0284c7; font-weight: 600; margin-bottom: 4px;">活跃度 = {activity:.3f}</div>
                <div style="font-size: 11px; color: #64748b;">{activity_formula}</div>
            </div>
        </div>
    </div>
    """

    return html


def render_market_state_panel() -> str:
    """渲染当前市场注意力状态面板"""
    from .common import get_history_tracker
    tracker = get_history_tracker()

    if not tracker:
        return """<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;"><div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">👁️ 当前市场注意力状态</div><div style="color: #64748b; text-align: center; padding: 20px;">历史追踪器未初始化</div></div>"""

    state_info = tracker.get_market_state_info()
    state = state_info.get('state', 'unknown')
    description = state_info.get('description', '等待数据...')
    global_attn = state_info.get('global_attention', 0)
    market_time = state_info.get('market_time', '')

    state_config = {
        'active': {'color': '#dc2626', 'bg': '#fef2f2', 'emoji': '🔥', 'label': '焦点集中'},
        'moderate': {'color': '#ca8a04', 'bg': '#fefce8', 'emoji': '⚡', 'label': '焦点较集中'},
        'quiet': {'color': '#0284c7', 'bg': '#f0f9ff', 'emoji': '👁️', 'label': '焦点分散'},
        'very_quiet': {'color': '#16a34a', 'bg': '#f0fdf4', 'emoji': '💤', 'label': '焦点涣散'},
        'unknown': {'color': '#64748b', 'bg': '#f8fafc', 'emoji': '❓', 'label': '未知状态'}
    }
    config = state_config.get(state, state_config['unknown'])

    hot_sectors = list(tracker.current_hot_sectors.items())[:5]
    hot_symbols = list(tracker.current_hot_symbols.items())[:10]
    time_display = f"📅 {market_time}" if market_time else "📅 等待行情数据..."

    html = f"""
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="font-weight: 600; color: #1e293b;">👁️ 当前市场注意力状态</div>
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="font-size: 12px; color: #64748b;">{time_display}</div>
                <div style="background: {config['bg']}; color: {config['color']}; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">{config['emoji']} {config['label']}</div>
            </div>
        </div>
        <div style="background: {config['bg']}; border-left: 4px solid {config['color']}; padding: 12px 16px; margin-bottom: 16px; border-radius: 0 8px 8px 0;">
            <div style="font-size: 13px; color: #1e293b; line-height: 1.5;"><strong>📊 {description}</strong></div>
            <div style="font-size: 12px; color: #64748b; margin-top: 6px;">全局注意力分数: <strong>{global_attn:.3f}</strong></div>
        </div>
    """

    if hot_sectors:
        html += """<div style="margin-bottom: 16px;"><div style="font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 8px;">📈 注意力集中板块 Top5</div><div style="display: flex; flex-wrap: wrap; gap: 8px;">"""
        for sector_id, weight in hot_sectors:
            sector_name = tracker.get_sector_name(sector_id)
            bar_width = min(weight * 20, 100)
            html += f"""<div style="background: #f1f5f9; border-radius: 8px; padding: 10px 14px; min-width: 140px;"><div style="font-size: 14px; font-weight: 600; color: #1e293b;">{sector_name}</div><div style="display: flex; align-items: center; gap: 8px; margin-top: 6px;"><div style="background: {config['color']}; height: 6px; border-radius: 3px; width: {bar_width}px; min-width: 6px;"></div><span style="font-size: 13px; font-weight: 600; color: #1e293b;">{weight:.2f}</span></div></div>"""
        html += "</div></div>"

    if hot_symbols:
        html += """<div><div style="font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 8px;">🔥 注意力集中个股 Top10</div><div style="display: flex; flex-wrap: wrap; gap: 6px;">"""
        for symbol, weight in hot_symbols:
            symbol_name = tracker.get_symbol_name(symbol) or symbol
            change = tracker.get_symbol_change(symbol)
            change_str = f"{change:+.2f}%" if change is not None else ""
            change_color = "#16a34a" if change and change > 0 else ("#dc2626" if change and change < 0 else "#64748b")
            html += f"""<div style="background: #fef3c7; border: 1px solid #fcd34d; border-radius: 6px; padding: 4px 8px; font-size: 11px; display: flex; align-items: center; gap: 4px; min-width: 0;"><span style="color: #92400e; font-weight: 600;">{symbol}</span><span style="color: #1e293b; max-width: 50px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{symbol_name}</span>{f'<span style="font-size: 10px; color: {change_color}; font-weight: 600;">{change_str}</span>' if change_str else ''}<span style="color: #92400e; font-weight: 600;">{weight:.1f}</span></div>"""
        html += "</div></div>"

    if not hot_sectors and not hot_symbols:
        html += """<div style="background: #f8fafc; border-radius: 8px; padding: 24px; text-align: center; color: #64748b;"><div style="font-size: 24px; margin-bottom: 8px;">📊</div><div>暂无注意力数据</div><div style="font-size: 12px; margin-top: 4px;">等待市场数据输入...</div></div>"""

    html += "</div>"
    return html


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
                skip_reason = "(注意力不足)"
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
            <div style="background: linear-gradient(135deg, #dbeafe, #bfdbfe); padding: 16px; border-radius: 8px;">
                <div style="font-weight: 600; color: #1e40af; margin-bottom: 8px;">🌊 轻量检测 <span style="font-size: 10px; color: #64748b; font-weight: normal;">(River)</span></div>
                <div style="font-size: 12px; color: #1e3a8a; line-height: 1.6;">
                    <div style="display: flex; justify-content: space-between;"><span>处理数据:</span><span style="font-weight: 600;">{processed:,}</span></div>
                    <div style="display: flex; justify-content: space-between;"><span>异常检测:</span><span style="font-weight: 600;">{anomalies:,}</span></div>
                    <div style="display: flex; justify-content: space-between;"><span>异常率:</span><span style="font-weight: 600;">{anomaly_ratio:.1f}%</span><span style="font-size: 10px; color: #64748b;">(正常10-20%)</span></div>
                    <div style="display: flex; justify-content: space-between;"><span>活跃股票:</span><span style="font-weight: 600;">{river_stats.get('active_symbols', 0)} 只</span></div>
                </div>
                <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #93c5fd; font-size: 11px; color: #3b82f6;">💡 快速检测价格/成交量异常波动</div>
            </div>
            <div style="background: linear-gradient(135deg, #fce7f3, #fbcfe8); padding: 16px; border-radius: 8px;">
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
        <div style="margin-top: 16px; padding: 12px; background: linear-gradient(135deg, #f0fdf4, #dcfce7); border-radius: 8px; border: 1px solid #86efac;">
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
        from deva.naja.attention import get_noise_filter
        noise_filter = get_noise_filter()
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
            <div style="background: linear-gradient(135deg, #f1f5f9, #e2e8f0); padding: 12px; border-radius: 8px; text-align: center;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">总处理</div>
                <div style="font-size: 20px; font-weight: 700; color: #1e293b;">{total:,}</div>
                <div style="font-size: 10px; color: #94a3b8;">条记录</div>
            </div>
            <div style="background: linear-gradient(135deg, {rate_bg}, #ffffff); padding: 12px; border-radius: 8px; text-align: center; border: 1px solid {rate_color}33;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">已过滤</div>
                <div style="font-size: 20px; font-weight: 700; color: {rate_color};">{filtered:,}</div>
                <div style="font-size: 10px; color: {rate_color};">{filter_rate}</div>
            </div>
            <div style="background: linear-gradient(135deg, #f1f5f9, #e2e8f0); padding: 12px; border-radius: 8px; text-align: center;">
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


def render_pytorch_patterns() -> str:
    """渲染 PyTorch 模式识别结果"""
    from .common import get_attention_integration

    try:
        integration = get_attention_integration()
        if not integration or not integration.attention_system:
            return ""

        dual_engine = integration.attention_system.dual_engine
        if not dual_engine or not dual_engine.pytorch:
            return ""

        pytorch = dual_engine.pytorch
        pattern_cache = pytorch._pattern_cache

        if not pattern_cache:
            return ""

        patterns = sorted(pattern_cache.values(), key=lambda x: x.timestamp, reverse=True)[:10]

        html = """<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;"><div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">🔍 PyTorch 模式识别结果 <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">深度学习异常检测</span></div>"""

        pattern_styles = {
            'breakout': ('🚀', '#dc2626', '突破'),
            'reversal': ('🔄', '#7c3aed', '反转'),
            'accumulation': ('📦', '#059669', '吸筹'),
            'distribution': ('📤', '#ea580c', '派发'),
            'volatility_expansion': ('⚡', '#f59e0b', '波动扩张'),
        }

        for pattern in patterns:
            emoji, color, label = pattern_styles.get(pattern.pattern_type, ('🔍', '#64748b', pattern.pattern_type))
            confidence = pattern.confidence
            bg_color = '#fef2f2' if confidence >= 0.8 else ('#fff7ed' if confidence >= 0.6 else '#f8fafc')
            border_color = '#fecaca' if confidence >= 0.8 else ('#fed7aa' if confidence >= 0.6 else '#e2e8f0')

            html += f"""<div style="padding: 12px; margin-bottom: 8px; background: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; border-left: 3px solid {color};"><div style="display: flex; justify-content: space-between; align-items: center;"><div style="display: flex; align-items: center; gap: 8px;"><span style="font-size: 18px;">{emoji}</span><div><div style="font-weight: 600; color: #1e293b;">{pattern.symbol}</div><div style="font-size: 11px; color: #64748b;">{label} | 得分: {pattern.pattern_score:.2f}</div></div></div><div style="text-align: right;"><div style="font-weight: 700; color: {color}; font-size: 14px;">{confidence:.1%}</div><div style="font-size: 10px; color: #94a3b8;">置信度</div></div></div></div>"""

        html += '</div>'
        return html
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"渲染 PyTorch 模式结果失败: {e}")
        return ""


def render_hot_sectors_and_stocks(hot_data: Dict[str, Any]) -> str:
    """渲染热门板块和股票"""
    sectors = hot_data.get("sectors", [])
    stocks = hot_data.get("stocks", [])

    if not sectors and not stocks:
        return ""

    from .common import get_history_tracker
    tracker = get_history_tracker()

    html = """<div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;"><div style="font-weight: 600; margin-bottom: 16px; color: #1e293b; font-size: 16px;">🔥 热门板块与股票 <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">实时注意力排名</span></div><div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">"""

    if sectors:
        html += """<div><div style="font-weight: 600; color: #7c3aed; margin-bottom: 12px; font-size: 14px;">📊 热门板块 Top 10</div>"""
        max_sector_weight = max([w for _, w in sectors[:10]]) if sectors else 1

        for i, (sector_id, weight) in enumerate(sectors[:10], 1):
            if weight > 0.7:
                color, status, bg_gradient = "#dc2626", "🔥 极高", "linear-gradient(90deg, #fee2e2, #fecaca)"
            elif weight > 0.5:
                color, status, bg_gradient = "#ea580c", "⚡ 高", "linear-gradient(90deg, #ffedd5, #fed7aa)"
            elif weight > 0.3:
                color, status, bg_gradient = "#ca8a04", "👁️ 中", "linear-gradient(90deg, #fef3c7, #fde68a)"
            else:
                color, status, bg_gradient = "#16a34a", "💤 低", "linear-gradient(90deg, #dcfce7, #bbf7d0)"

            sector_name = tracker.get_sector_name(sector_id) if tracker else sector_id
            display_name = sector_name if sector_name != sector_id else sector_id
            progress_width = (weight / max_sector_weight * 100) if max_sector_weight > 0 else 0

            html += f"""<div style="padding: 10px 12px; margin-bottom: 8px; background: {bg_gradient}; border-radius: 8px; border-left: 3px solid {color};"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;"><div style="display: flex; align-items: center; gap: 8px;"><span style="color: #64748b; font-weight: 600; min-width: 20px;">{i}.</span><span style="font-weight: 500; color: #1e293b;">{display_name}</span></div><div style="text-align: right;"><span style="color: {color}; font-weight: 700; font-size: 14px;">{weight:.3f}</span><span style="font-size: 10px; color: {color}; margin-left: 4px;">{status}</span></div></div><div style="background: rgba(255,255,255,0.5); height: 4px; border-radius: 2px; overflow: hidden;"><div style="background: {color}; height: 100%; width: {progress_width}%; border-radius: 2px;"></div></div></div>"""
        html += "</div>"

    if stocks:
        html += """<div><div style="font-weight: 600; color: #2563eb; margin-bottom: 12px; font-size: 14px;">📈 热门股票 Top 20</div><div style="display: flex; flex-wrap: wrap; gap: 6px;">"""
        for i, stock_item in enumerate(stocks[:20], 1):
            if isinstance(stock_item, dict):
                symbol = stock_item.get("symbol", "")
                weight = stock_item.get("weight", 0)
                symbol_name = stock_item.get("name", symbol)
                if symbol_name == symbol and not symbol.startswith(('sh', 'sz', 'bj', 'SH', 'SZ', 'BJ')):
                    pass
            else:
                symbol, weight = stock_item
                symbol_name = tracker.get_symbol_name(symbol) if tracker else symbol

            if weight > 5:
                color, bg_color, border_color = "#dc2626", "#fef2f2", "#fecaca"
            elif weight > 3:
                color, bg_color, border_color = "#ea580c", "#fff7ed", "#fed7aa"
            elif weight > 2:
                color, bg_color, border_color = "#ca8a04", "#fefce8", "#fef08a"
            else:
                color, bg_color, border_color = "#16a34a", "#f0fdf4", "#bbf7d0"

            symbol_change = tracker.get_symbol_change(symbol) if tracker else None
            change_str = f"{symbol_change:+.2f}%" if symbol_change is not None else ""
            change_color = "#16a34a" if symbol_change and symbol_change > 0 else ("#dc2626" if symbol_change and symbol_change < 0 else "#64748b")

            html += f"""<div style="background: {bg_color}; border: 1px solid {border_color}; border-radius: 6px; padding: 4px 8px; font-size: 11px; display: flex; align-items: center; gap: 4px; min-width: 0;"><span style="color: #64748b; font-weight: 600;">{i}.</span><span style="font-weight: 600; color: #1e293b; max-width: 60px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{symbol}</span>{f'<span style="color: #475569; max-width: 50px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{symbol_name}</span>' if symbol_name and symbol_name != symbol else ''}{f'<span style="font-size: 10px; color: {change_color}; font-weight: 600;">{change_str}</span>' if change_str else ''}<span style="color: {color}; font-weight: 600;">{weight:.1f}</span></div>"""
        html += "</div></div>"

    html += "</div></div>"
    return html


def render_key_metrics_summary(report: Dict, strategy_stats: Dict) -> str:
    """核心指标摘要 - 放在最顶部"""
    from .common import get_history_tracker

    global_attention = report.get('global_attention', 0)
    processed = report.get('processed_snapshots', 0)

    tracker = get_history_tracker()
    hotspot_count = len(tracker.sector_hotspot_events_medium) if tracker else 0

    signal_count = strategy_stats.get('total_signals_generated', 0)

    if global_attention >= 0.7:
        ga_color = "#dc2626"
        ga_emoji = "🔥"
        ga_text = "极高"
    elif global_attention >= 0.5:
        ga_color = "#ea580c"
        ga_emoji = "⚡"
        ga_text = "高"
    elif global_attention >= 0.3:
        ga_color = "#ca8a04"
        ga_emoji = "👁️"
        ga_text = "中"
    else:
        ga_color = "#16a34a"
        ga_emoji = "💤"
        ga_text = "低"

    return f"""
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px;">
        <div style="background: linear-gradient(135deg, {ga_color}15, {ga_color}08); border: 2px solid {ga_color}; border-radius: 12px; padding: 16px; text-align: center;">
            <div style="font-size: 28px; margin-bottom: 4px;">{ga_emoji}</div>
            <div style="font-size: 32px; font-weight: bold; color: {ga_color};">{global_attention:.2f}</div>
            <div style="font-size: 11px; color: #64748b;">全局注意力 · {ga_text}</div>
        </div>
        <div style="background: linear-gradient(135deg, #fef3c7, #fde68a); border: 2px solid #f59e0b; border-radius: 12px; padding: 16px; text-align: center;">
            <div style="font-size: 28px; margin-bottom: 4px;">🔥</div>
            <div style="font-size: 32px; font-weight: bold; color: #b45309;">{hotspot_count}</div>
            <div style="font-size: 11px; color: #64748b;">热点事件</div>
        </div>
        <div style="background: linear-gradient(135deg, #dbeafe, #bfdbfe); border: 2px solid #3b82f6; border-radius: 12px; padding: 16px; text-align: center;">
            <div style="font-size: 28px; margin-bottom: 4px;">📡</div>
            <div style="font-size: 32px; font-weight: bold; color: #1d4ed8;">{signal_count}</div>
            <div style="font-size: 11px; color: #64748b;">交易信号</div>
        </div>
        <div style="background: linear-gradient(135deg, #f3e8ff, #e9d5ff); border: 2px solid #8b5cf6; border-radius: 12px; padding: 16px; text-align: center;">
            <div style="font-size: 28px; margin-bottom: 4px;">📊</div>
            <div style="font-size: 32px; font-weight: bold; color: #6d28d9;">{processed//1000}k</div>
            <div style="font-size: 11px; color: #64748b;">处理数据</div>
        </div>
    </div>
    """


def render_live_hotspots() -> str:
    """实时热点 - 最重要的信息"""
    from .common import get_history_tracker

    tracker = get_history_tracker()
    if not tracker:
        return ""

    hot_sectors = list(tracker.current_hot_sectors.items())[:5]
    hot_symbols = list(tracker.current_hot_symbols.items())[:8]

    if not hot_sectors and not hot_symbols:
        return ""

    html = """
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-bottom: 16px;">
        <div style="font-weight: 600; margin-bottom: 12px; color: #1e293b; font-size: 14px;">🔥 实时热点</div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
    """

    if hot_sectors:
        html += '<div><div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">热门板块</div>'
        for i, (sector_id, weight) in enumerate(hot_sectors, 1):
            sector_name = tracker.get_sector_name(sector_id) if tracker else sector_id
            color = "#dc2626" if weight > 0.7 else "#ea580c" if weight > 0.5 else "#ca8a04"
            html += f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; margin-bottom: 4px; background: #f8fafc; border-radius: 6px; font-size: 12px;">
                <span><span style="color: #94a3b8; margin-right: 6px;">{i}.</span>{sector_name}</span>
                <span style="color: {color}; font-weight: 600;">{weight:.2f}</span>
            </div>
            """
        html += '</div>'

    if hot_symbols:
        html += '<div><div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">热门个股</div>'
        for i, (symbol, weight) in enumerate(hot_symbols, 1):
            symbol_name = tracker.get_symbol_name(symbol) if tracker else symbol
            color = "#dc2626" if weight > 5 else "#ea580c" if weight > 3 else "#ca8a04"
            html += f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; margin-bottom: 4px; background: #f8fafc; border-radius: 6px; font-size: 12px;">
                <span><span style="color: #94a3b8; margin-right: 6px;">{i}.</span>{symbol} {symbol_name if symbol_name != symbol else ''}</span>
                <span style="color: {color}; font-weight: 600;">{weight:.1f}</span>
            </div>
            """
        html += '</div>'

    html += '</div></div>'
    return html


def render_collapsible_system_status(report: Dict, strategy_stats: Dict) -> str:
    """可折叠的系统状态详情"""
    freq_summary = report.get('frequency_summary', {})
    dual_summary = report.get('dual_engine_summary', {})

    high = freq_summary.get('high_frequency', 0)
    medium = freq_summary.get('medium_frequency', 0)
    low = freq_summary.get('low_frequency', 0)
    total = high + medium + low or 1

    river_stats = dual_summary.get('river_stats', {})
    pytorch_stats = dual_summary.get('pytorch_stats', {})

    return f"""
    <details style="margin-bottom: 16px;">
        <summary style="cursor: pointer; padding: 12px 16px; background: linear-gradient(135deg, #f8fafc, #f1f5f9); border: 1px solid #e2e8f0; border-radius: 8px; font-weight: 500; color: #1e293b; font-size: 13px; user-select: none;">
            ⚙️ 系统状态详情 (点击展开)
        </summary>
        <div style="padding: 16px; background: white; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 8px 8px;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; font-size: 12px;">
                <div>
                    <div style="font-weight: 600; margin-bottom: 8px; color: #374151;">频率分布</div>
                    <div style="display: flex; gap: 8px;">
                        <span style="padding: 4px 8px; background: #fee2e2; color: #dc2626; border-radius: 4px;">高频 {high}</span>
                        <span style="padding: 4px 8px; background: #fef3c7; color: #b45309; border-radius: 4px;">中频 {medium}</span>
                        <span style="padding: 4px 8px; background: #dcfce7; color: #16a34a; border-radius: 4px;">低频 {low}</span>
                    </div>
                </div>
                <div>
                    <div style="font-weight: 600; margin-bottom: 8px; color: #374151;">双引擎</div>
                    <div style="color: #64748b;">
                        River: {river_stats.get('processed_count', 0):,} |
                        PyTorch: {pytorch_stats.get('inference_count', 0):,}
                    </div>
                </div>
            </div>
        </div>
    </details>
    """


def render_compact_signals(limit: int = 5) -> str:
    """紧凑的最近信号"""
    from .common import get_strategy_manager

    manager = get_strategy_manager()
    if not manager:
        return ""

    signals = manager.get_recent_signals(n=limit)
    if not signals:
        return ""

    html = """
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="font-weight: 600; color: #1e293b; font-size: 14px;">📡 最近信号</div>
        </div>
    """

    for signal in signals:
        emoji = "🚀" if signal.signal_type == 'buy' else "💨" if signal.signal_type == 'sell' else "👀"
        color = "#16a34a" if signal.signal_type == 'buy' else "#dc2626" if signal.signal_type == 'sell' else "#64748b"

        html += f"""
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; margin-bottom: 6px; background: #f8fafc; border-radius: 6px; font-size: 12px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="color: {color};">{emoji}</span>
                <span style="font-weight: 500;">{signal.symbol}</span>
                <span style="color: #94a3b8;">{signal.strategy_name}</span>
            </div>
            <span style="color: {color}; font-weight: 600; text-transform: uppercase;">{signal.signal_type}</span>
        </div>
        """

    html += '</div>'
    return html


def render_compact_noise_filter() -> str:
    """简化的噪音过滤状态"""
    try:
        from deva.naja.attention import get_noise_filter
        noise_filter = get_noise_filter()
        stats = noise_filter.get_stats()

        total = stats.get('total_processed', 0)
        filtered = stats.get('total_filtered', 0)
        filter_rate = stats.get('filter_rate', '0.00%')

        return f"""
        <div style="display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: #f0f9ff; border-radius: 6px; font-size: 11px; color: #0369a1; margin-bottom: 16px;">
            <span>🔇</span>
            <span>噪音过滤: 已处理 {total:,} 条, 过滤 {filtered} 条 ({filter_rate})</span>
        </div>
        """
    except:
        return ""
