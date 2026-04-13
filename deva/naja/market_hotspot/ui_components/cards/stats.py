"""热点系统 UI - 统计与状态卡片（去重版，仅保留 render_frequency_distribution）"""

import logging
from typing import Dict

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

