"""热点系统 UI 时间线组件"""

from datetime import datetime
from typing import List, Dict, Any

from deva.naja.market_hotspot.ui_components.common import get_history_tracker

def render_hotspot_timeline(time_window: int = 50) -> str:
    """渲染热点变迁时间线

    Args:
        time_window: 时间窗口大小,控制显示最近多少个时间点的题材变化
    """
    tracker = get_history_tracker()
    if not tracker or len(tracker.snapshots) < 2:
        return ""

    recent_snapshots = list(tracker.snapshots)[-time_window:]
    if len(recent_snapshots) < 2:
        return ""

    html = """
    <div style="background: linear-gradient(135deg, #fef3c7, #fef9c3); border: 1px solid #fcd34d; border-radius: 12px; padding: 16px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 12px; color: #92400e;">🕐 题材热度切换</div>
    """

    transfers = []
    prev_top_blocks = []

    for i, snapshot in enumerate(recent_snapshots):
        if not snapshot.block_weights:
            continue

        sorted_blocks = sorted(snapshot.block_weights.items(), key=lambda x: x[1], reverse=True)
        current_top3 = [s[0] for s in sorted_blocks[:3]]

        if prev_top_blocks:
            new_in_top3 = set(current_top3) - set(prev_top_blocks)
            for block_id in new_in_top3:
                block_weight = snapshot.block_weights[block_id]
                block_name = tracker.get_block_name(block_id) or block_id
                time_str = snapshot.market_time_str if hasattr(snapshot, 'market_time_str') and snapshot.market_time_str else datetime.fromtimestamp(snapshot.timestamp).strftime("%m-%d %H:%M:%S")

                prev_rank = None
                for j, (s, w) in enumerate(sorted(snapshot.block_weights.items(), key=lambda x: x[1], reverse=True)):
                    if s == block_id:
                        prev_rank = j + 1
                        break

                rank_change = ""
                if prev_rank and prev_rank > 3:
                    rank_change = f"↑升至第{prev_rank}名"
                elif prev_rank:
                    rank_change = f"↑第{prev_rank}名"

                transfers.append({
                    'time': time_str, 'block': block_name, 'block_id': block_id,
                    'weight': block_weight, 'action': 'rise', 'change': rank_change,
                    'timestamp': snapshot.timestamp
                })

        prev_top_blocks = current_top3

    if recent_snapshots:
        latest = recent_snapshots[-1]
        if latest.block_weights:
            ranked = sorted(latest.block_weights.items(), key=lambda x: x[1], reverse=True)
            medals = ["🥇", "🥈", "🥉"]
            html += """
            <div style="margin-bottom: 12px;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">当前排行榜:</div>
            """
            for rank, (block_id, weight) in enumerate(ranked[:5], 1):
                block_name = tracker.get_block_name(block_id) or block_id
                medal = medals[rank-1] if rank <= 3 else f"{rank}."
                color = "#dc2626" if rank == 1 else ("#ea580c" if rank == 2 else ("#ca8a04" if rank == 3 else "#64748b"))

                trend = ""
                trend_color = "#64748b"
                if len(recent_snapshots) >= 3:
                    prev_weight = snapshot.block_weights.get(block_id, weight)
                    for snp in recent_snapshots[-4:-1]:
                        if snp.block_weights and block_id in snp.block_weights:
                            prev_weight = snp.block_weights[block_id]
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
                    <span style="font-weight: 500; color: #1e293b; flex: 1;">{block_name}</span>
                    <span style="font-size: 12px; color: {trend_color};">{trend}</span>
                    <span style="font-weight: 600; color: {color};">{weight:.1f}</span>
                </div>
                """
            html += "</div>"

    if transfers:
        html += f"""
        <div style="border-top: 1px dashed #fcd34d; padding-top: 12px;">
            <div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">题材崛起记录 (共{len(transfers)}条):</div>
        """
        for transfer in transfers[-20:]:
            time_str = transfer['time']
            if len(time_str) <= 8:
                time_str = datetime.fromtimestamp(transfer.get('timestamp', time.time())).strftime("%m-%d %H:%M:%S")
            html += f"""
            <div style="display: flex; align-items: center; gap: 8px; padding: 4px 6px; background: white; border-radius: 4px; margin-bottom: 4px;">
                <span style="font-size: 10px; color: #64748b; min-width: 90px; font-family: monospace;">{time_str}</span>
                <span style="font-size: 12px; color: #16a34a; font-weight: 600;">↑</span>
                <span style="font-size: 12px; color: #1e293b;">{transfer['block']}</span>
                <span style="font-size: 10px; color: #16a34a;">{transfer['change']}</span>
            </div>
            """
        html += "</div>"
    else:
        html += f"""
        <div style="text-align: center; color: #64748b; padding: 10px; font-size: 12px;">
            近{time_window}个时间点内题材排名无明显变化
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


