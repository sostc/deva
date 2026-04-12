"""热点系统 UI 时间线组件"""

from datetime import datetime
from typing import List, Dict, Any

from deva.naja.market_hotspot.ui_components.common import get_history_tracker

def render_hotspot_changes(changes: List[Any]) -> str:
    """渲染热点变化记录"""
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
        if hasattr(change, 'block') and change.block:
            market_info_parts.append(f"[{change.block}]")
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


def render_hotspot_shift_report(report: Dict[str, Any]) -> str:
    """渲染热点转移报告"""
    from datetime import datetime

    html = """
    <div style="background: linear-gradient(135deg, #f0f9ff, #e0f2fe); border: 1px solid #7dd3fc; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="font-weight: 600; margin-bottom: 16px; color: #0369a1;">🔄 热点切换监测</div>
    """

    if not report.get('has_shift'):
        html += """
        <div style="color: #64748b; text-align: center; padding: 10px;">暂无热点切换<br><span style="font-size: 12px;">Top 3 题材和 Top 5 个股未发生变化</span></div>
        """
        html += "</div>"
        return html

    old_snapshot = report.get('old_snapshot')
    new_snapshot = report.get('new_snapshot')
    time_span = report.get('time_span', 0)

    old_time_str = ""
    new_time_str = ""
    if old_snapshot:
        old_ts = old_snapshot.get('timestamp', 0)
        old_time_str = datetime.fromtimestamp(old_ts).strftime('%m-%d %H:%M') if old_ts else ""
    if new_snapshot:
        new_ts = new_snapshot.get('timestamp', 0)
        new_time_str = datetime.fromtimestamp(new_ts).strftime('%m-%d %H:%M') if new_ts else ""

    time_display = ""
    if old_time_str and new_time_str:
        duration_str = f"{time_span/60:.1f}分钟" if time_span < 3600 else f"{time_span/3600:.1f}小时"
        time_display = f'<div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px; font-size: 11px;"><span style="background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 4px;">⏱️ {old_time_str}</span><span style="color: #64748b;">→</span><span style="background: #fef3c7; color: #92400e; padding: 2px 8px; border-radius: 4px;">⏱️ {new_time_str}</span><span style="color: #94a3b8;">({duration_str})</span></div>'

    html = f"""
    <div style="background: linear-gradient(135deg, #fef3c7, #fde68a); border: 1px solid #f59e0b; border-radius: 12px; padding: 20px; margin-top: 16px;">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
            <span style="font-size: 18px;">🚨</span>
            <span style="font-weight: 700; color: #92400e; font-size: 15px;">热点转移 detected</span>
        </div>
        {time_display}
    """

    if report.get('block_shift'):
        old_blocks = report.get('old_top_blocks', [])
        new_blocks = report.get('new_top_blocks', [])

        removed_blocks = [s for s in old_blocks if s[0] not in [ns[0] for ns in new_blocks]]
        added_blocks = [s for s in new_blocks if s[0] not in [os[0] for os in old_blocks]]
        kept_blocks = [s for s in new_blocks if s[0] in [os[0] for os in old_blocks]]

        html += """<div style="margin-bottom: 14px;">"""
        if removed_blocks:
            html += """<div style="font-weight: 500; color: #dc2626; margin-bottom: 6px;">📤 退出 Top3:</div>"""
            html += """<div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px;">"""
            for block_id, block_name, weight in removed_blocks:
                html += f"""<span style="background: #fee2e2; color: #dc2626; padding: 3px 10px; border-radius: 6px; font-size: 12px;">{block_name} <span style="opacity: 0.7;">{weight:.2f}</span></span>"""
            html += """</div>"""

        if added_blocks:
            html += """<div style="font-weight: 500; color: #16a34a; margin-bottom: 6px;">📥 新进入 Top3:</div>"""
            html += """<div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px;">"""
            for block_id, block_name, weight in added_blocks:
                html += f"""<span style="background: #dcfce7; color: #16a34a; padding: 3px 10px; border-radius: 6px; font-size: 12px;">{block_name} <span style="opacity: 0.7;">{weight:.2f}</span></span>"""
            html += """</div>"""

        if kept_blocks:
            html += """<div style="font-weight: 500; color: #475569; margin-bottom: 6px;">🔸 保持:</div>"""
            html += """<div style="display: flex; flex-wrap: wrap; gap: 6px;">"""
            for block_id, block_name, weight in kept_blocks:
                old_weight = next((w for s, n, w in old_blocks if s == block_id), 0)
                change = weight - old_weight
                change_str = f"+{change:.2f}" if change > 0 else f"{change:.2f}"
                change_color = "#16a34a" if change > 0 else "#dc2626"
                html += f"""<span style="background: #f1f5f9; color: #1e293b; padding: 3px 10px; border-radius: 6px; font-size: 12px;">{block_name} <span style="color: {change_color};">{change_str}</span></span>"""
            html += """</div>"""

        html += """</div>"""

    if report.get('symbol_shift'):
        old_symbols = report.get('old_top_symbols', [])
        new_symbols = report.get('new_top_symbols', [])

        removed_symbols = [s for s in old_symbols if s[0] not in [ns[0] for ns in new_symbols]]
        added_symbols = [s for s in new_symbols if s[0] not in [os[0] for os in old_symbols]]
        kept_symbols = [s for s in new_symbols if s[0] in [os[0] for os in old_symbols]]

        html += """<div style="margin-top: 8px;">"""
        if removed_symbols:
            html += """<div style="font-weight: 500; color: #dc2626; margin-bottom: 6px;">📤 退出 Top5 个股:</div>"""
            html += """<div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px;">"""
            for symbol, symbol_name, weight in removed_symbols:
                name_str = f"{symbol_name}" if symbol_name != symbol else ""
                html += f"""<span style="background: #fee2e2; color: #dc2626; padding: 2px 8px; border-radius: 4px; font-size: 11px;">{symbol}{name_str} <span style="opacity: 0.7;">{weight:.1f}</span></span>"""
            html += """</div>"""

        if added_symbols:
            html += """<div style="font-weight: 500; color: #16a34a; margin-bottom: 6px;">📥 新进入 Top5 个股:</div>"""
            html += """<div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px;">"""
            for symbol, symbol_name, weight in added_symbols:
                name_str = f"{symbol_name}" if symbol_name != symbol else ""
                html += f"""<span style="background: #dcfce7; color: #16a34a; padding: 2px 8px; border-radius: 4px; font-size: 11px;">{symbol}{name_str} <span style="opacity: 0.7;">{weight:.1f}</span></span>"""
            html += """</div>"""

        if kept_symbols:
            html += """<div style="font-weight: 500; color: #475569; margin-bottom: 6px;">🔸 保持:</div>"""
            html += """<div style="display: flex; flex-wrap: wrap; gap: 6px;">"""
            for symbol, symbol_name, weight in kept_symbols:
                old_weight = next((w for s, n, w in old_symbols if s == symbol), 0)
                change = weight - old_weight
                change_str = f"+{change:.1f}" if change > 0 else f"{change:.1f}"
                change_color = "#16a34a" if change > 0 else "#dc2626"
                name_str = f"{symbol_name}" if symbol_name != symbol else ""
                html += f"""<span style="background: #f1f5f9; color: #1e293b; padding: 2px 8px; border-radius: 4px; font-size: 11px;">{symbol}{name_str} <span style="color: {change_color};">{change_str}</span></span>"""
            html += """</div>"""

        html += """</div>"""

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
        block_id: str
        block_name: str
        event_type: str
        weight_change: float
        change_percent: float
        top_symbols: List[Dict] = field(default_factory=list)

    samples = [
        SampleEvent(0, "09:35", "tech", "科技题材", "new_hot", 0.15, 15.0, [
            {"symbol": "000063", "name": "中兴通讯", "change_pct": 9.8},
            {"symbol": "002415", "name": "海康威视", "change_pct": 7.2},
            {"symbol": "600570", "name": "恒生电子", "change_pct": 6.5},
        ]),
        SampleEvent(0, "09:42", "finance", "金融题材", "rise", 0.08, 8.5, [
            {"symbol": "600036", "name": "招商银行", "change_pct": 5.8},
            {"symbol": "000001", "name": "平安银行", "change_pct": 4.2},
        ]),
        SampleEvent(0, "09:48", "new_energy", "新能源", "rise", 0.06, 6.2, [
            {"symbol": "300750", "name": "宁德时代", "change_pct": 5.5},
            {"symbol": "002594", "name": "比亚迪", "change_pct": 4.8},
        ]),
        SampleEvent(0, "10:05", "tech", "科技题材", "rise", 0.12, 12.0, [
            {"symbol": "000938", "name": "中芯国际", "change_pct": 8.2},
        ]),
        SampleEvent(0, "10:15", "healthcare", "医药题材", "new_hot", 0.10, 10.0, [
            {"symbol": "600276", "name": "恒瑞医药", "change_pct": 7.8},
        ]),
        SampleEvent(0, "10:22", "consumer", "消费题材", "fall", -0.05, -5.5, [
            {"symbol": "600519", "name": "贵州茅台", "change_pct": -4.2},
        ]),
        SampleEvent(0, "10:35", "finance", "金融题材", "fall", -0.04, -4.2, [
            {"symbol": "601398", "name": "工商银行", "change_pct": -3.5},
        ]),
        SampleEvent(0, "10:48", "real_estate", "房地产", "cooled", -0.08, -8.0, [
            {"symbol": "000002", "name": "万科A", "change_pct": -6.5},
        ]),
        SampleEvent(0, "11:05", "tech", "科技题材", "rise", 0.09, 9.5, [
            {"symbol": "603019", "name": "中科曙光", "change_pct": 7.2},
        ]),
        SampleEvent(0, "11:18", "materials", "材料题材", "new_hot", 0.07, 7.2, [
            {"symbol": "600585", "name": "海螺水泥", "change_pct": 6.5},
        ]),
        SampleEvent(0, "13:05", "healthcare", "医药题材", "rise", 0.11, 11.5, [
            {"symbol": "300122", "name": "智飞生物", "change_pct": 8.5},
        ]),
        SampleEvent(0, "13:15", "energy", "能源题材", "fall", -0.06, -6.8, [
            {"symbol": "601857", "name": "中国石油", "change_pct": -5.5},
        ]),
        SampleEvent(0, "13:35", "tech", "科技题材", "fall", -0.07, -7.5, [
            {"symbol": "002371", "name": "北方华创", "change_pct": -6.2},
        ]),
        SampleEvent(0, "13:48", "finance", "金融题材", "rise", 0.13, 13.2, [
            {"symbol": "600030", "name": "中信证券", "change_pct": 9.5},
        ]),
        SampleEvent(0, "13:55", "new_energy", "新能源", "cooled", -0.09, -9.0, [
            {"symbol": "300750", "name": "宁德时代", "change_pct": -7.5},
        ]),
        SampleEvent(0, "14:08", "consumer", "消费题材", "rise", 0.05, 5.8, [
            {"symbol": "000333", "name": "美的集团", "change_pct": 4.8},
        ]),
        SampleEvent(0, "14:18", "healthcare", "医药题材", "fall", -0.08, -8.5, [
            {"symbol": "600276", "name": "恒瑞医药", "change_pct": -6.8},
        ]),
        SampleEvent(0, "14:35", "finance", "金融题材", "rise", 0.15, 15.5, [
            {"symbol": "601398", "name": "工商银行", "change_pct": 8.5},
        ]),
        SampleEvent(0, "14:42", "tech", "科技题材", "cooled", -0.12, -12.0, [
            {"symbol": "000063", "name": "中兴通讯", "change_pct": -8.5},
        ]),
        SampleEvent(0, "14:55", "materials", "材料题材", "rise", 0.08, 8.2, [
            {"symbol": "601899", "name": "紫金矿业", "change_pct": 7.5},
        ]),
    ]

    return samples


