"""注意力系统 UI 时间线组件"""

from datetime import datetime
from typing import List, Dict, Any


def get_history_tracker():
    """获取历史追踪器"""
    try:
        from deva.naja.attention.history_tracker import get_history_tracker as _get
        return _get()
    except Exception:
        return None


def render_sector_trends() -> str:
    """渲染板块注意力变化曲线"""
    tracker = get_history_tracker()
    if not tracker or len(tracker.snapshots) < 2:
        return "<div style='color: #64748b; text-align: center; padding: 20px;'>数据不足，无法显示趋势</div>"

    recent_snapshots = list(tracker.snapshots)[-30:]

    html = """
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">
            📊 板块注意力变化曲线
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">最近30个时间点</span>
        </div>
    """

    all_sectors_with_weight = []
    for snapshot in recent_snapshots:
        for sector_id, weight in snapshot.sector_weights.items():
            all_sectors_with_weight.append((sector_id, weight))

    sector_weights_sum = {}
    for sector_id, weight in all_sectors_with_weight:
        sector_weights_sum[sector_id] = sector_weights_sum.get(sector_id, 0) + weight

    top5_sectors = sorted(sector_weights_sum.items(), key=lambda x: x[1], reverse=True)[:5]
    top5_sector_ids = [s[0] for s in top5_sectors]

    sector_colors = {
        'tech': '#3b82f6', 'finance': '#10b981', 'healthcare': '#f59e0b',
        'energy': '#ef4444', 'consumer': '#8b5cf6',
    }

    for sector_id in top5_sector_ids:
        sector_name = tracker.get_sector_name(sector_id)
        color = sector_colors.get(sector_id, '#64748b')

        sector_data = []
        for snapshot in recent_snapshots:
            weight = snapshot.sector_weights.get(sector_id, 0)
            time_str = datetime.fromtimestamp(snapshot.timestamp).strftime("%H:%M")
            sector_data.append((time_str, weight))

        if not sector_data:
            continue

        current_weight = sector_data[-1][1]
        prev_weight = sector_data[0][1] if len(sector_data) > 1 else current_weight
        change_pct = ((current_weight - prev_weight) / prev_weight * 100) if prev_weight > 0 else 0

        max_weight = max([w for _, w in sector_data]) if sector_data else 1
        trend_bars = ""
        for time_str, weight in sector_data:
            height_pct = (weight / max_weight * 100) if max_weight > 0 else 0
            trend_bars += f"""
                <div style="flex: 1; background: {color}; height: {height_pct}%; min-height: 2px; margin: 0 1px; border-radius: 1px; opacity: {0.4 + (height_pct / 200)};" title="{time_str}: {weight:.3f}"></div>
            """

        top_symbols = []
        if recent_snapshots:
            latest_snapshot = recent_snapshots[-1]
            sorted_symbols = sorted(latest_snapshot.symbol_weights.items(), key=lambda x: x[1], reverse=True)[:3]
            for symbol, weight in sorted_symbols:
                symbol_name = tracker.get_symbol_name(symbol)
                display = f"{symbol}" if symbol_name == symbol else f"{symbol} {symbol_name}"
                top_symbols.append(f"{display}({weight:.1f})")

        symbols_str = ", ".join(top_symbols) if top_symbols else "暂无数据"

        change_emoji = "📈" if change_pct > 0 else "📉" if change_pct < 0 else "➡️"
        change_color = "#16a34a" if change_pct > 0 else "#dc2626" if change_pct < 0 else "#64748b"

        html += f"""
        <div style="margin-bottom: 16px; padding: 12px; background: linear-gradient(135deg, #f8fafc, #f1f5f9); border-radius: 10px; border-left: 4px solid {color};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-weight: 600; color: #1e293b; font-size: 14px;">{sector_name}</span>
                    <span style="font-size: 11px; color: #64748b;">({sector_id})</span>
                </div>
                <div style="text-align: right;">
                    <span style="font-weight: 700; color: {color}; font-size: 16px;">{current_weight:.3f}</span>
                    <span style="font-size: 11px; color: {change_color}; margin-left: 4px;">{change_emoji} {change_pct:+.1f}%</span>
                </div>
            </div>
            <div style="display: flex; align-items: flex-end; height: 40px; margin: 8px 0; padding: 4px; background: rgba(255,255,255,0.5); border-radius: 4px;">
                {trend_bars}
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; margin-top: 2px;">
                <span>{sector_data[0][0]}</span>
                <span>{sector_data[len(sector_data)//2][0]}</span>
                <span>{sector_data[-1][0]}</span>
            </div>
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #e2e8f0;">
                <span style="font-size: 11px; color: #64748b;">热门个股: </span>
                <span style="font-size: 11px; color: #374151;">{symbols_str}</span>
            </div>
        </div>
        """

    html += "</div>"
    return html


def render_attention_timeline(time_window: int = 50) -> str:
    """渲染注意力转移时间线

    Args:
        time_window: 时间窗口大小，控制显示最近多少个时间点的板块变化
    """
    tracker = get_history_tracker()
    if not tracker or len(tracker.snapshots) < 2:
        return ""

    recent_snapshots = list(tracker.snapshots)[-time_window:]
    if len(recent_snapshots) < 2:
        return ""

    html = """
    <div style="background: linear-gradient(135deg, #fef3c7, #fef9c3); border: 1px solid #fcd34d; border-radius: 12px; padding: 16px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 12px; color: #92400e;">🕐 板块注意力转移</div>
    """

    transfers = []
    prev_top_sectors = []

    for i, snapshot in enumerate(recent_snapshots):
        if not snapshot.sector_weights:
            continue

        sorted_sectors = sorted(snapshot.sector_weights.items(), key=lambda x: x[1], reverse=True)
        current_top3 = [s[0] for s in sorted_sectors[:3]]

        if prev_top_sectors:
            new_in_top3 = set(current_top3) - set(prev_top_sectors)
            for sector_id in new_in_top3:
                sector_weight = snapshot.sector_weights[sector_id]
                sector_name = tracker.get_sector_name(sector_id) or sector_id
                time_str = snapshot.market_time_str if hasattr(snapshot, 'market_time_str') and snapshot.market_time_str else datetime.fromtimestamp(snapshot.timestamp).strftime("%m-%d %H:%M:%S")

                prev_rank = None
                for j, (s, w) in enumerate(sorted(snapshot.sector_weights.items(), key=lambda x: x[1], reverse=True)):
                    if s == sector_id:
                        prev_rank = j + 1
                        break

                rank_change = ""
                if prev_rank and prev_rank > 3:
                    rank_change = f"↑升至第{prev_rank}名"
                elif prev_rank:
                    rank_change = f"↑第{prev_rank}名"

                transfers.append({
                    'time': time_str, 'sector': sector_name, 'sector_id': sector_id,
                    'weight': sector_weight, 'action': 'rise', 'change': rank_change,
                    'timestamp': snapshot.timestamp
                })

        prev_top_sectors = current_top3

    if recent_snapshots:
        latest = recent_snapshots[-1]
        if latest.sector_weights:
            ranked = sorted(latest.sector_weights.items(), key=lambda x: x[1], reverse=True)
            medals = ["🥇", "🥈", "🥉"]
            html += """
            <div style="margin-bottom: 12px;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">当前排行榜:</div>
            """
            for rank, (sector_id, weight) in enumerate(ranked[:5], 1):
                sector_name = tracker.get_sector_name(sector_id) or sector_id
                medal = medals[rank-1] if rank <= 3 else f"{rank}."
                color = "#dc2626" if rank == 1 else ("#ea580c" if rank == 2 else ("#ca8a04" if rank == 3 else "#64748b"))

                trend = ""
                trend_color = "#64748b"
                if len(recent_snapshots) >= 3:
                    prev_weight = snapshot.sector_weights.get(sector_id, weight)
                    for snp in recent_snapshots[-4:-1]:
                        if snp.sector_weights and sector_id in snp.sector_weights:
                            prev_weight = snp.sector_weights[sector_id]
                            break
                    if weight > prev_weight * 1.1:
                        trend = "📈"
                        trend_color = "#16a34a"
                    elif weight < prev_weight * 0.9:
                        trend = "📉"
                        trend_color = "#dc2626"

                html += f"""
                <div style="display: flex; align-items: center; gap: 8px; padding: 4px 0; border-bottom: 1px solid #fef9c3;">
                    <span style="font-size: 12px; color: {color}; min-width: 24px;">{medal}</span>
                    <span style="font-weight: 500; color: #1e293b; flex: 1;">{sector_name}</span>
                    <span style="font-size: 12px; color: {trend_color};">{trend}</span>
                    <span style="font-weight: 600; color: {color};">{weight:.1f}</span>
                </div>
                """
            html += "</div>"

    if transfers:
        html += f"""
        <div style="border-top: 1px dashed #fcd34d; padding-top: 12px;">
            <div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">板块崛起记录 (共{len(transfers)}条):</div>
        """
        for transfer in transfers[-20:]:
            time_str = transfer['time']
            if len(time_str) <= 8:
                time_str = datetime.fromtimestamp(transfer.get('timestamp', time.time())).strftime("%m-%d %H:%M:%S")
            html += f"""
            <div style="display: flex; align-items: center; gap: 8px; padding: 4px 6px; background: white; border-radius: 4px; margin-bottom: 4px;">
                <span style="font-size: 10px; color: #64748b; min-width: 90px; font-family: monospace;">{time_str}</span>
                <span style="font-size: 12px; color: #16a34a; font-weight: 600;">↑</span>
                <span style="font-size: 12px; color: #1e293b;">{transfer['sector']}</span>
                <span style="font-size: 10px; color: #16a34a;">{transfer['change']}</span>
            </div>
            """
        html += "</div>"
    else:
        html += f"""
        <div style="text-align: center; color: #64748b; padding: 10px; font-size: 12px;">
            近{time_window}个时间点内板块排名无明显变化
        </div>
        """

    html += "</div>"
    return html


def render_recent_signals(signals: List[Any], limit: int = 10) -> str:
    """渲染最近信号"""
    if not signals:
        return "<div style='color: #64748b; text-align: center; padding: 20px;'>暂无信号</div>"

    html = """
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">📡 最近信号</div>
    """

    for signal in list(signals)[-limit:]:
        emoji = "🚀" if signal.signal_type == 'buy' else "💨" if signal.signal_type == 'sell' else "👀"
        color = "#16a34a" if signal.signal_type == 'buy' else "#dc2626" if signal.signal_type == 'sell' else "#64748b"

        html += f"""
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; margin-bottom: 6px; background: #f8fafc; border-radius: 6px; font-size: 13px;">
            <div>
                <span style="color: {color}; font-weight: 600;">{emoji} {signal.symbol}</span>
                <span style="color: #64748b; margin-left: 8px;">{signal.strategy_name}</span>
            </div>
            <div style="text-align: right;">
                <div style="color: {color}; font-weight: 600;">{signal.signal_type.upper()}</div>
                <div style="font-size: 11px; color: #94a3b8;">置信度: {signal.confidence:.2f}</div>
            </div>
        </div>
        """

    html += "</div>"
    return html


def render_sector_hotspot_timeline(threshold: str = "high") -> str:
    """渲染板块热点切换时间线"""
    tracker = get_history_tracker()
    if not tracker:
        return """
        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
            <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">🔥 板块热点切换时间线</div>
            <div style="color: #64748b; text-align: center; padding: 40px 20px;">历史追踪器未初始化</div>
        </div>
        """

    threshold_config = {
        'low': {'events': tracker.sector_hotspot_events_low, 'pct': 3, 'label': '低敏感度', 'color': '#16a34a'},
        'high': {'events': tracker.sector_hotspot_events_high, 'pct': 10, 'label': '高敏感度', 'color': '#dc2626'},
    }

    config = threshold_config.get(threshold, threshold_config['high'])
    all_events = config['events']
    valid_events = [e for e in all_events if tracker.is_sector_valid(getattr(e, 'sector_id', ''))]
    pct = config['pct']
    label = config['label']
    header_color = config['color']

    if not valid_events:
        return f"""
        <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
            <div style="font-weight: 600; margin-bottom: 16px; color: {header_color};">🔥 {label} ({pct}%阈值)</div>
            <div style="color: #64748b; text-align: center; padding: 40px 20px;">暂无有效板块变化事件（噪声板块已被过滤）</div>
        </div>
        """

    html = f"""
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: {header_color};">
            🔥 {label} ({pct}%阈值)
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">共{len(valid_events)}个有效事件</span>
        </div>
    """

    event_styles = {
        'new_hot': ('🔥', '#dc2626', '新热点'),
        'cooled': ('❄️', '#3b82f6', '热点消退'),
        'rise': ('📈', '#16a34a', '大幅拉升'),
        'fall': ('📉', '#f59e0b', '明显回调'),
    }

    recent_events = list(valid_events)[-15:]
    current_date = None

    for event in reversed(recent_events):
        event_date = getattr(event, 'market_date', '') or datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d")
        if event_date != current_date:
            current_date = event_date
            html += f"""
            <div style="margin: 12px 0 8px 0; padding: 4px 0; border-bottom: 1px dashed #e2e8f0; font-size: 12px; color: #94a3b8; font-weight: 500;">📅 {event_date}</div>
            """

        emoji, color, label_text = event_styles.get(event.event_type, ('•', '#64748b', event.event_type))

        bg_colors = {'new_hot': '#fef2f2', 'cooled': '#eff6ff', 'rise': '#f0fdf4', 'fall': '#fffbeb'}
        bg_color = bg_colors.get(event.event_type, '#f8fafc')

        change_sign = '+' if event.change_percent > 0 else ''

        html += f"""
        <div style="padding: 12px; margin-bottom: 10px; background: {bg_color}; border-radius: 8px; border-left: 3px solid {color};">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                        <span style="font-size: 11px; color: #64748b; font-family: monospace; min-width: 50px;">{event.market_time}</span>
                        <span style="font-size: 18px;">{emoji}</span>
                        <span style="font-weight: 600; color: #1e293b;">{event.sector_name}</span>
                        <span style="font-size: 10px; color: {color}; background: rgba(255,255,255,0.6); padding: 2px 8px; border-radius: 4px;">{label_text}</span>
                    </div>
                    <div style="font-size: 12px; color: #64748b; margin-left: 58px; line-height: 1.5;">
                        权重: {event.weight_change:+.3f} ({change_sign}{event.change_percent:.1f}%)
                    </div>
                </div>
            </div>
        """

        if event.top_symbols:
            html += """
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #e2e8f0;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">板块内个股:</div>
                <div style="display: flex; flex-direction: column; gap: 4px;">
            """
            for s in event.top_symbols[:3]:
                s_emoji = '📈' if s['change_pct'] > 0 else '📉'
                s_color = '#16a34a' if s['change_pct'] > 0 else '#dc2626'
                s_sign = '+' if s['change_pct'] > 0 else ''
                html += f"""
                    <div style="font-size: 11px; display: flex; justify-content: space-between; align-items: center; padding: 4px 8px; background: rgba(255,255,255,0.5); border-radius: 4px;">
                        <span>{s_emoji} <strong>{s['symbol']}</strong> {s['name']}</span>
                        <span style="color: {s_color}; font-weight: 600;">{s['old']:.2f} → {s['new']:.2f} ({s_sign}{s['change_pct']:.1f}%)</span>
                    </div>
                """
            html += "</div></div>"

        html += "</div>"

    html += "</div>"
    return html


def render_multi_threshold_timeline() -> str:
    """渲染多阈值板块热点切换时间线"""
    html = """
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 20px; color: #1e293b; font-size: 16px;">
            🔥 板块热点切换时间线
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">双阈值对比</span>
        </div>

        <div style="display: flex; gap: 16px; margin-bottom: 20px; padding: 12px 16px; background: linear-gradient(135deg, #f8fafc, #f1f5f9); border-radius: 8px; font-size: 12px;">
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="width: 12px; height: 12px; background: #16a34a; border-radius: 3px;"></span>
                <span><strong>低阈值 (3%)</strong>: 捕捉细微变化，事件较多</span>
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="width: 12px; height: 12px; background: #dc2626; border-radius: 3px;"></span>
                <span><strong>高阈值 (10%)</strong>: 重大变化，事件较少</span>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
    """

    for threshold in ['low', 'high']:
        html += f'<div style="min-width: 0;">{render_single_threshold_column(threshold)}</div>'

    html += "</div></div>"
    return html


def render_single_threshold_column(threshold: str) -> str:
    """渲染单个阈值的紧凑时间线列"""
    tracker = get_history_tracker()
    if not tracker:
        return "<div style='color: #64748b; text-align: center;'>未初始化</div>"

    threshold_config = {
        'low': {'events': tracker.sector_hotspot_events_low, 'pct': 3, 'label': '低敏感度', 'color': '#16a34a', 'bg': '#f0fdf4'},
        'high': {'events': tracker.sector_hotspot_events_high, 'pct': 10, 'label': '高敏感度', 'color': '#dc2626', 'bg': '#fef2f2'},
    }

    config = threshold_config.get(threshold, threshold_config.get('high'))
    all_events = config['events']
    valid_events = [e for e in all_events if tracker.is_sector_valid(getattr(e, 'sector_id', ''))]
    events = list(valid_events)[-20:]
    pct = config['pct']
    label = config['label']
    color = config['color']
    bg = config['bg']

    if not valid_events:
        return f"""
        <div style="background: {bg}; border: 1px solid {color}33; border-radius: 8px; padding: 16px; text-align: center;">
            <div style="font-weight: 600; color: {color}; margin-bottom: 8px;">{label} ({pct}%)</div>
            <div style="font-size: 12px; color: #64748b;">暂无有效事件</div>
        </div>
        """

    html = f"""
    <div style="background: {bg}; border: 1px solid {color}33; border-radius: 8px; padding: 12px;">
        <div style="font-weight: 600; color: {color}; margin-bottom: 12px; font-size: 13px;">
            {label} ({pct}%) <span style="font-weight: normal; color: #64748b;">· {len(events)}个</span>
        </div>
    """

    event_styles = {
        'new_hot': ('🔥', '#dc2626'),
        'cooled': ('❄️', '#3b82f6'),
        'rise': ('📈', '#16a34a'),
        'fall': ('📉', '#f59e0b'),
    }

    current_date = None

    for event in reversed(events):
        full_time = datetime.fromtimestamp(event.timestamp).strftime("%m-%d %H:%M:%S")
        event_date = full_time.split(' ')[0]
        if event_date != current_date:
            current_date = event_date
            html += f'<div style="font-size: 10px; color: #94a3b8; margin: 8px 0 4px 0; padding-top: 4px; border-top: 1px dashed #e2e8f0;">{event_date}</div>'

        emoji, evt_color = event_styles.get(event.event_type, ('•', '#64748b'))
        change_sign = '+' if event.change_percent > 0 else ''

        html += f"""
        <div style="padding: 8px; margin-bottom: 6px; background: white; border-radius: 6px; border-left: 2px solid {evt_color}; font-size: 11px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                <span style="color: #64748b; font-family: monospace; font-size: 10px;">{full_time}</span>
                <span>{emoji}</span>
            </div>
            <div style="font-weight: 500; color: #1e293b; margin-bottom: 2px;">{event.sector_name}</div>
            <div style="color: {evt_color}; font-size: 10px;">{change_sign}{event.change_percent:.1f}%</div>
        </div>
        """

    html += "</div>"
    return html


def render_attention_changes(changes: List[Any]) -> str:
    """渲染注意力变化记录"""
    html = """
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">
            📈 个股重大变化记录
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">基于行情数据时间</span>
        </div>
    """

    if not changes:
        html += """
        <div style="color: #64748b; text-align: center; padding: 20px;">暂无变化记录<br><span style="font-size: 12px;">等待数据更新...</span></div>
        <div style="color: #64748b; text-align: center; padding: 20px;">暂无变化记录<br><span style="font-size: 12px;">等待数据更新...</span></div>
        """
        html += "</div>"
        return html

    type_icons = {
        'new_hot': ('🔥', '#dc2626', '新热门'),
        'cooled': ('❄️', '#3b82f6', '冷却'),
        'strengthen': ('📈', '#16a34a', '加强'),
        'weaken': ('📉', '#f59e0b', '减弱')
    }

    current_date = None

    for change in list(changes)[-20:]:
        icon, color, label = type_icons.get(change.change_type, ('•', '#64748b', '变化'))

        change_time = datetime.fromtimestamp(change.timestamp)
        time_str = change_time.strftime("%H:%M:%S")
        date_str = change_time.strftime("%m-%d")

        if date_str != current_date:
            current_date = date_str
            html += f"""
            <div style="margin: 12px 0 8px 0; padding: 4px 0; border-bottom: 1px dashed #e2e8f0; font-size: 12px; color: #94a3b8; font-weight: 500;">📅 {date_str}</div>
            """

        bg_color = {'new_hot': '#fef2f2', 'cooled': '#eff6ff', 'strengthen': '#f0fdf4', 'weaken': '#fffbeb'}.get(change.change_type, '#f8fafc')

        market_info_parts = []
        if hasattr(change, 'price') and change.price > 0:
            market_info_parts.append(f"¥{change.price:.2f}")
        if hasattr(change, 'price_change') and change.price_change != 0:
            market_info_parts.append(f"{change.price_change:+.2f}%")
        if hasattr(change, 'sector') and change.sector:
            market_info_parts.append(f"[{change.sector}]")
        market_info_str = " | ".join(market_info_parts) if market_info_parts else ""

        volume_str = ""
        if hasattr(change, 'volume') and change.volume > 0:
            vol = change.volume
            if vol >= 1e8:
                volume_str = f"量: {vol/1e8:.1f}亿"
            elif vol >= 1e4:
                volume_str = f"量: {vol/1e4:.1f}万"
            else:
                volume_str = f"量: {vol:.0f}"

        html += f"""
        <div style="padding: 10px 12px; margin-bottom: 6px; background: {bg_color}; border-radius: 8px; border-left: 3px solid {color}; font-size: 13px;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                        <span style="font-size: 11px; color: #64748b; font-family: monospace;">{time_str}</span>
                        <span style="font-size: 16px;">{icon}</span>
                        <span style="font-weight: 600; color: #1e293b;">{change.item_name or change.item_id}</span>
                        <span style="font-size: 10px; color: {color}; background: rgba(255,255,255,0.6); padding: 1px 6px; border-radius: 4px;">{label}</span>
                    </div>
                    <div style="font-size: 11px; color: #64748b; margin-left: 46px;">
                        权重: {change.old_weight:.2f} → {change.new_weight:.2f} ({change.change_percent:+.1f}%)
                        {f' | {market_info_str}' if market_info_str else ''}
                        {f' | {volume_str}' if volume_str else ''}
                    </div>
                </div>
            </div>
        </div>
        """

    html += "</div>"
    return html


def render_attention_shift_report(report: Dict[str, Any]) -> str:
    """渲染注意力转移报告"""
    html = """
    <div style="background: linear-gradient(135deg, #f0f9ff, #e0f2fe); border: 1px solid #7dd3fc; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: #0369a1;">🔄 注意力转移监测</div>
    """

    if not report.get('has_shift'):
        html += """
        <div style="color: #64748b; text-align: center; padding: 10px;">暂无注意力转移<br><span style="font-size: 12px;">Top 3板块和Top 5股票未发生变化</span></div>
        """
        html += "</div>"
        return html

    html = """
    <div style="background: linear-gradient(135deg, #fef3c7, #fde68a); border: 1px solid #f59e0b; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: #92400e;">🔄 注意力转移 detected</div>
    """

    if report.get('sector_shift'):
        html += """
        <div style="margin-bottom: 16px;">
            <div style="font-weight: 500; color: #78350f; margin-bottom: 8px;">板块转移:</div>
            <div style="display: flex; justify-content: space-between; font-size: 12px;">
                <div style="flex: 1;">
                    <div style="color: #9ca3af; margin-bottom: 4px;">之前 Top 3:</div>
        """
        for sector_id, sector_name, weight in report.get('old_top_sectors', []):
            html += f"<div>• {sector_name} ({weight:.3f})</div>"

        html += """
                </div>
                <div style="flex: 1;">
                    <div style="color: #9ca3af; margin-bottom: 4px;">现在 Top 3:</div>
        """
        for sector_id, sector_name, weight in report.get('new_top_sectors', []):
            html += f"<div>• {sector_name} ({weight:.3f})</div>"

        html += "</div></div></div>"

    if report.get('symbol_shift'):
        html += """
        <div>
            <div style="font-weight: 500; color: #78350f; margin-bottom: 8px;">个股转移:</div>
            <div style="display: flex; justify-content: space-between; font-size: 12px;">
                <div style="flex: 1;">
                    <div style="color: #9ca3af; margin-bottom: 4px;">之前 Top 5:</div>
        """
        for symbol, symbol_name, weight in report.get('old_top_symbols', []):
            name_str = f" {symbol_name}" if symbol_name != symbol else ""
            html += f"<div>• {symbol}{name_str} ({weight:.2f})</div>"

        html += """
                </div>
                <div style="flex: 1;">
                    <div style="color: #9ca3af; margin-bottom: 4px;">现在 Top 5:</div>
        """
        for symbol, symbol_name, weight in report.get('new_top_symbols', []):
            name_str = f" {symbol_name}" if symbol_name != symbol else ""
            html += f"<div>• {symbol}{name_str} ({weight:.2f})</div>"

        html += "</div></div></div>"

    html += "</div>"
    return html


def _get_sample_events() -> list:
    """生成样例事件数据，用于展示效果"""
    from dataclasses import dataclass, field
    from typing import List, Dict

    @dataclass
    class SampleEvent:
        timestamp: float
        market_time: str
        sector_id: str
        sector_name: str
        event_type: str
        weight_change: float
        change_percent: float
        top_symbols: List[Dict] = field(default_factory=list)

    samples = [
        SampleEvent(0, "09:35", "tech", "科技板块", "new_hot", 0.15, 15.0, [
            {"symbol": "000063", "name": "中兴通讯", "change_pct": 9.8},
            {"symbol": "002415", "name": "海康威视", "change_pct": 7.2},
            {"symbol": "600570", "name": "恒生电子", "change_pct": 6.5},
        ]),
        SampleEvent(0, "09:42", "finance", "金融板块", "rise", 0.08, 8.5, [
            {"symbol": "600036", "name": "招商银行", "change_pct": 5.8},
            {"symbol": "000001", "name": "平安银行", "change_pct": 4.2},
        ]),
        SampleEvent(0, "09:48", "new_energy", "新能源", "rise", 0.06, 6.2, [
            {"symbol": "300750", "name": "宁德时代", "change_pct": 5.5},
            {"symbol": "002594", "name": "比亚迪", "change_pct": 4.8},
        ]),
        SampleEvent(0, "10:05", "tech", "科技板块", "rise", 0.12, 12.0, [
            {"symbol": "000938", "name": "中芯国际", "change_pct": 8.2},
        ]),
        SampleEvent(0, "10:15", "healthcare", "医药板块", "new_hot", 0.10, 10.0, [
            {"symbol": "600276", "name": "恒瑞医药", "change_pct": 7.8},
        ]),
        SampleEvent(0, "10:22", "consumer", "消费板块", "fall", -0.05, -5.5, [
            {"symbol": "600519", "name": "贵州茅台", "change_pct": -4.2},
        ]),
        SampleEvent(0, "10:35", "finance", "金融板块", "fall", -0.04, -4.2, [
            {"symbol": "601398", "name": "工商银行", "change_pct": -3.5},
        ]),
        SampleEvent(0, "10:48", "real_estate", "房地产", "cooled", -0.08, -8.0, [
            {"symbol": "000002", "name": "万科A", "change_pct": -6.5},
        ]),
        SampleEvent(0, "11:05", "tech", "科技板块", "rise", 0.09, 9.5, [
            {"symbol": "603019", "name": "中科曙光", "change_pct": 7.2},
        ]),
        SampleEvent(0, "11:18", "materials", "材料板块", "new_hot", 0.07, 7.2, [
            {"symbol": "600585", "name": "海螺水泥", "change_pct": 6.5},
        ]),
        SampleEvent(0, "13:05", "healthcare", "医药板块", "rise", 0.11, 11.5, [
            {"symbol": "300122", "name": "智飞生物", "change_pct": 8.5},
        ]),
        SampleEvent(0, "13:15", "energy", "能源板块", "fall", -0.06, -6.8, [
            {"symbol": "601857", "name": "中国石油", "change_pct": -5.5},
        ]),
        SampleEvent(0, "13:35", "tech", "科技板块", "fall", -0.07, -7.5, [
            {"symbol": "002371", "name": "北方华创", "change_pct": -6.2},
        ]),
        SampleEvent(0, "13:48", "finance", "金融板块", "rise", 0.13, 13.2, [
            {"symbol": "600030", "name": "中信证券", "change_pct": 9.5},
        ]),
        SampleEvent(0, "13:55", "new_energy", "新能源", "cooled", -0.09, -9.0, [
            {"symbol": "300750", "name": "宁德时代", "change_pct": -7.5},
        ]),
        SampleEvent(0, "14:08", "consumer", "消费板块", "rise", 0.05, 5.8, [
            {"symbol": "000333", "name": "美的集团", "change_pct": 4.8},
        ]),
        SampleEvent(0, "14:18", "healthcare", "医药板块", "fall", -0.08, -8.5, [
            {"symbol": "600276", "name": "恒瑞医药", "change_pct": -6.8},
        ]),
        SampleEvent(0, "14:35", "finance", "金融板块", "rise", 0.15, 15.5, [
            {"symbol": "601398", "name": "工商银行", "change_pct": 8.5},
        ]),
        SampleEvent(0, "14:42", "tech", "科技板块", "cooled", -0.12, -12.0, [
            {"symbol": "000063", "name": "中兴通讯", "change_pct": -8.5},
        ]),
        SampleEvent(0, "14:55", "materials", "材料板块", "rise", 0.08, 8.2, [
            {"symbol": "601899", "name": "紫金矿业", "change_pct": 7.5},
        ]),
    ]

    return samples


def render_sector_trading_timeline() -> str:
    """板块炒作时间轴 - 展示每天各板块随时间的涨跌变化"""
    tracker = get_history_tracker()

    today = datetime.now().strftime("%m-%d")
    today_events = []
    has_real_data = False

    if tracker and tracker.sector_hotspot_events_medium:
        all_events = list(tracker.sector_hotspot_events_medium)

        for event in all_events:
            event_date = datetime.fromtimestamp(event.timestamp).strftime("%m-%d")
            if event_date == today:
                today_events.append(event)

        if today_events:
            has_real_data = True
        else:
            today_events = all_events[-15:]

        today_events.sort(key=lambda x: x.timestamp)

    using_sample_data = not has_real_data and not today_events
    if using_sample_data:
        today_events = _get_sample_events()

    html = f"""
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="font-weight: 600; color: #1e293b; font-size: 14px;">
                📈 板块炒作时间轴
                <span style="font-size: 11px; color: #64748b; font-weight: normal; margin-left: 8px;">今日板块起落</span>
            </div>
            <div style="font-size: 11px; color: #94a3b8;">{len(today_events)}个事件</div>
        </div>
        {"" if has_real_data else """
        <div style="margin-bottom: 12px; padding: 8px 12px; background: linear-gradient(135deg, #fef3c7, #fde68a); border: 1px solid #f59e0b; border-radius: 6px; font-size: 12px; color: #92400e;">
            <strong>⚠️ 样例数据展示</strong> - 当前暂无实时数据，以下为示例效果。
        </div>
        """}
        <div style="margin-bottom: 12px; padding: 8px 12px; background: #f0f9ff; border-radius: 6px; font-size: 11px; color: #0369a1; line-height: 1.5;">
            <strong>📊 事件说明:</strong> 🔥新热点 | ❄️热点消退 | 📈拉升 | 📉回调
        </div>
    """

    time_periods = [
        ("09:30", "10:00", "早盘开盘", "#dc2626"),
        ("10:00", "10:30", "早盘活跃", "#ea580c"),
        ("10:30", "11:00", "早盘震荡", "#ca8a04"),
        ("11:00", "11:30", "早盘收尾", "#ca8a04"),
        ("13:00", "13:30", "午后开盘", "#3b82f6"),
        ("13:30", "14:00", "午后活跃", "#2563eb"),
        ("14:00", "14:30", "午后震荡", "#1d4ed8"),
        ("14:30", "15:00", "尾盘决战", "#7c3aed"),
    ]

    event_styles = {
        'new_hot': ('🔥', '#dc2626', '新热点'),
        'cooled': ('❄️', '#3b82f6', '热点消退'),
        'rise': ('📈', '#16a34a', '拉升'),
        'fall': ('📉', '#f59e0b', '回调'),
    }

    period_events = {i: [] for i in range(len(time_periods))}

    for event in today_events:
        try:
            if hasattr(event, 'market_time') and event.market_time:
                time_str = event.market_time
            else:
                time_str = datetime.fromtimestamp(event.timestamp).strftime("%H:%M")

            hour, minute = map(int, time_str.split(':'))
            time_val = hour * 100 + minute

            for i, (start, end, label, color) in enumerate(time_periods):
                start_h, start_m = map(int, start.split(':'))
                end_h, end_m = map(int, end.split(':'))
                start_val = start_h * 100 + start_m
                end_val = end_h * 100 + end_m

                if start_val <= time_val < end_val:
                    period_events[i].append((time_str, event))
                    break
        except:
            continue

    for i, (start, end, label, period_color) in enumerate(time_periods):
        events_in_period = period_events[i]
        has_events = len(events_in_period) > 0

        if has_events:
            header_bg = f"linear-gradient(135deg, {period_color}15, {period_color}08)"
            header_border = period_color
            event_count_text = f"{len(events_in_period)}个事件"
        else:
            header_bg = "#f8fafc"
            header_border = "#e2e8f0"
            event_count_text = "暂无数据"

        html += f"""
        <div style="margin-bottom: 16px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px; padding: 6px 10px; background: {header_bg}; border-left: 3px solid {header_border}; border-radius: 0 6px 6px 0;">
                <span style="font-weight: 600; color: {period_color if has_events else '#94a3b8'}; font-size: 12px;">{label}</span>
                <span style="color: #94a3b8; font-size: 11px;">{start}-{end}</span>
                <span style="margin-left: auto; color: {'#64748b' if has_events else '#94a3b8'}; font-size: 11px;">{event_count_text}</span>
            </div>
            <div style="padding-left: 16px; border-left: 2px dashed #e2e8f0; margin-left: 6px;">
        """

        if has_events:
            for time_str, event in events_in_period:
                emoji, evt_color, evt_label = event_styles.get(event.event_type, ('•', '#64748b', '变化'))
                change_sign = '+' if event.change_percent > 0 else ''

                if abs(event.change_percent) >= 10:
                    bg_color = '#fef2f2' if event.change_percent > 0 else '#eff6ff'
                    border_color = '#dc2626' if event.change_percent > 0 else '#3b82f6'
                elif abs(event.change_percent) >= 5:
                    bg_color = '#fff7ed' if event.change_percent > 0 else '#f0f9ff'
                    border_color = '#ea580c' if event.change_percent > 0 else '#0ea5e9'
                else:
                    bg_color = '#f8fafc'
                    border_color = evt_color

                top_symbols = getattr(event, 'top_symbols', [])[:3]

                html += f"""
                <div style="display: flex; align-items: flex-start; gap: 8px; padding: 8px 10px; margin-bottom: 6px; background: {bg_color}; border-radius: 6px; border-left: 3px solid {border_color}; font-size: 12px;">
                    <div style="min-width: 40px;">
                        <span style="color: #94a3b8; font-family: monospace; font-size: 11px;">{time_str}</span>
                    </div>
                    <div style="flex: 1;">
                        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                            <span style="font-size: 14px;">{emoji}</span>
                            <span style="font-weight: 500; color: #1e293b;">{event.sector_name}</span>
                            <span style="font-size: 10px; color: {evt_color};">{evt_label}</span>
                            <span style="color: {border_color}; font-weight: 600; font-size: 13px; margin-left: auto;">{change_sign}{event.change_percent:.1f}%</span>
                        </div>
                        {f'''<div style="display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; padding-top: 6px; border-top: 1px dashed {border_color}40;">
                            <span style="font-size: 10px; color: #64748b;">领涨/领跌:</span>
                            {''.join([f"<span style='font-size: 10px; padding: 2px 6px; background: {'#fef2f2' if s.get('change_pct', 0) > 0 else '#eff6ff'}; color: {'#dc2626' if s.get('change_pct', 0) > 0 else '#3b82f6'}; border-radius: 4px; white-space: nowrap;'>{s.get('symbol', '')} {s.get('name', '')[:4]} {s.get('change_pct', 0):+.1f}%</span>" for s in top_symbols])}
                        </div>''' if top_symbols else ''}
                    </div>
                </div>
                """
        else:
            html += """
            <div style="padding: 12px 10px; margin-bottom: 6px; background: #f8fafc; border-radius: 6px; border-left: 3px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center;">等待数据...</div>
            """

        html += "</div></div>"

    html += '</div>'
    return html
