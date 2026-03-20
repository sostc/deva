"""
注意力调度系统 UI V2 - 优化版

设计原则：
1. 重要信息前置 - 一眼看到关键变化
2. 减少重复 - 合并相似模块
3. 紧凑布局 - 减少空白和冗余
4. 可折叠 - 次要信息默认收起
"""

import time
import json
from datetime import datetime
from typing import Dict, List, Any
import pandas as pd
from pywebio.output import *
from pywebio.input import input_group, input, select, actions
from pywebio import session, pin
from pywebio.session import run_js
import threading

from deva.naja.page_help import render_help_collapse

# 自动刷新控制
_auto_refresh_enabled = True
_refresh_interval = 2


def set_auto_refresh(enabled: bool):
    global _auto_refresh_enabled
    _auto_refresh_enabled = enabled


def _get_attention_integration():
    """获取注意力系统集成"""
    try:
        from ..attention_integration import get_attention_integration
        return get_attention_integration()
    except Exception:
        return None


def _get_strategy_manager():
    """获取策略管理器"""
    try:
        from deva.naja.attention.strategies import get_strategy_manager
        return get_strategy_manager()
    except Exception:
        return None


def _get_history_tracker():
    """获取历史追踪器"""
    try:
        from .history_tracker import get_history_tracker
        return get_history_tracker()
    except Exception:
        return None


def _get_attention_report() -> Dict[str, Any]:
    """获取注意力系统报告"""
    integration = _get_attention_integration()
    if integration:
        try:
            return integration.get_attention_report()
        except Exception:
            pass
    return {}


def _get_strategy_stats() -> Dict[str, Any]:
    """获取策略统计"""
    manager = _get_strategy_manager()
    if manager:
        try:
            return manager.get_all_stats()
        except Exception:
            pass
    return {}


def _get_experiment_info():
    """获取实验模式信息"""
    try:
        manager = _get_strategy_manager()
        if manager:
            return manager.get_experiment_info()
    except Exception:
        pass
    return {"active": False}


def _is_attention_initialized():
    """检查注意力系统是否已初始化"""
    integration = _get_attention_integration()
    if integration is None:
        return False
    return integration.attention_system is not None


# ==================== 核心摘要卡片 ====================

def _render_key_metrics_summary(report: Dict, strategy_stats: Dict) -> str:
    """核心指标摘要 - 放在最顶部"""
    global_attention = report.get('global_attention', 0)
    processed = report.get('processed_snapshots', 0)
    
    # 获取热点数量
    tracker = _get_history_tracker()
    hotspot_count = len(tracker.sector_hotspot_events_medium) if tracker else 0
    
    # 获取信号数量
    signal_count = strategy_stats.get('total_signals_generated', 0)
    
    # 全局注意力颜色
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
    <div style="
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 16px;
    ">
        <!-- 全局注意力 -->
        <div style="
            background: linear-gradient(135deg, {ga_color}15, {ga_color}08);
            border: 2px solid {ga_color};
            border-radius: 12px;
            padding: 16px;
            text-align: center;
        ">
            <div style="font-size: 28px; margin-bottom: 4px;">{ga_emoji}</div>
            <div style="font-size: 32px; font-weight: bold; color: {ga_color};">{global_attention:.2f}</div>
            <div style="font-size: 11px; color: #64748b;">全局注意力 · {ga_text}</div>
        </div>
        
        <!-- 热点事件 -->
        <div style="
            background: linear-gradient(135deg, #fef3c7, #fde68a);
            border: 2px solid #f59e0b;
            border-radius: 12px;
            padding: 16px;
            text-align: center;
        ">
            <div style="font-size: 28px; margin-bottom: 4px;">🔥</div>
            <div style="font-size: 32px; font-weight: bold; color: #b45309;">{hotspot_count}</div>
            <div style="font-size: 11px; color: #64748b;">热点事件</div>
        </div>
        
        <!-- 交易信号 -->
        <div style="
            background: linear-gradient(135deg, #dbeafe, #bfdbfe);
            border: 2px solid #3b82f6;
            border-radius: 12px;
            padding: 16px;
            text-align: center;
        ">
            <div style="font-size: 28px; margin-bottom: 4px;">📡</div>
            <div style="font-size: 32px; font-weight: bold; color: #1d4ed8;">{signal_count}</div>
            <div style="font-size: 11px; color: #64748b;">交易信号</div>
        </div>
        
        <!-- 处理数据 -->
        <div style="
            background: linear-gradient(135deg, #f3e8ff, #e9d5ff);
            border: 2px solid #8b5cf6;
            border-radius: 12px;
            padding: 16px;
            text-align: center;
        ">
            <div style="font-size: 28px; margin-bottom: 4px;">📊</div>
            <div style="font-size: 32px; font-weight: bold; color: #6d28d9;">{processed//1000}k</div>
            <div style="font-size: 11px; color: #64748b;">处理数据</div>
        </div>
    </div>
    """


# ==================== 第一优先级：实时热点 ====================

def _render_live_hotspots() -> str:
    """实时热点 - 最重要的信息"""
    tracker = _get_history_tracker()
    if not tracker:
        return ""
    
    # 获取当前热点
    hot_sectors = list(tracker.current_hot_sectors.items())[:5]
    hot_symbols = list(tracker.current_hot_symbols.items())[:8]
    
    if not hot_sectors and not hot_symbols:
        return ""
    
    html = """
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 12px; color: #1e293b; font-size: 14px;">
            🔥 实时热点
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
    """
    
    # 热门板块
    if hot_sectors:
        html += '<div><div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">热门板块</div>'
        for i, (sector_id, weight) in enumerate(hot_sectors, 1):
            sector_name = tracker.get_sector_name(sector_id) if tracker else sector_id
            color = "#dc2626" if weight > 0.7 else "#ea580c" if weight > 0.5 else "#ca8a04"
            html += f"""
            <div style="
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 6px 10px;
                margin-bottom: 4px;
                background: #f8fafc;
                border-radius: 6px;
                font-size: 12px;
            ">
                <span><span style="color: #94a3b8; margin-right: 6px;">{i}.</span>{sector_name}</span>
                <span style="color: {color}; font-weight: 600;">{weight:.2f}</span>
            </div>
            """
        html += '</div>'
    
    # 热门个股
    if hot_symbols:
        html += '<div><div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">热门个股</div>'
        for i, (symbol, weight) in enumerate(hot_symbols, 1):
            symbol_name = tracker.get_symbol_name(symbol) if tracker else symbol
            color = "#dc2626" if weight > 5 else "#ea580c" if weight > 3 else "#ca8a04"
            html += f"""
            <div style="
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 6px 10px;
                margin-bottom: 4px;
                background: #f8fafc;
                border-radius: 6px;
                font-size: 12px;
            ">
                <span><span style="color: #94a3b8; margin-right: 6px;">{i}.</span>{symbol} {symbol_name if symbol_name != symbol else ''}</span>
                <span style="color: {color}; font-weight: 600;">{weight:.1f}</span>
            </div>
            """
        html += '</div>'
    
    html += '</div></div>'
    return html


# ==================== 第二优先级：板块炒作时间轴 ====================

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
    
    # 样例数据：模拟一天中不同时间段的板块变化，包含主导个股（带名称）
    samples = [
        # 早盘开盘
        SampleEvent(0, "09:35", "tech", "科技板块", "new_hot", 0.15, 15.0, [
            {"symbol": "000063", "name": "中兴通讯", "change_pct": 9.8},
            {"symbol": "002415", "name": "海康威视", "change_pct": 7.2},
            {"symbol": "600570", "name": "恒生电子", "change_pct": 6.5},
        ]),
        SampleEvent(0, "09:42", "finance", "金融板块", "rise", 0.08, 8.5, [
            {"symbol": "600036", "name": "招商银行", "change_pct": 5.8},
            {"symbol": "000001", "name": "平安银行", "change_pct": 4.2},
            {"symbol": "601318", "name": "中国平安", "change_pct": 3.9},
        ]),
        SampleEvent(0, "09:48", "new_energy", "新能源", "rise", 0.06, 6.2, [
            {"symbol": "300750", "name": "宁德时代", "change_pct": 5.5},
            {"symbol": "002594", "name": "比亚迪", "change_pct": 4.8},
        ]),
        
        # 早盘活跃
        SampleEvent(0, "10:05", "tech", "科技板块", "rise", 0.12, 12.0, [
            {"symbol": "000938", "name": "中芯国际", "change_pct": 8.2},
            {"symbol": "600498", "name": "烽火通信", "change_pct": 7.5},
            {"symbol": "002230", "name": "科大讯飞", "change_pct": 6.8},
        ]),
        SampleEvent(0, "10:15", "healthcare", "医药板块", "new_hot", 0.10, 10.0, [
            {"symbol": "600276", "name": "恒瑞医药", "change_pct": 7.8},
            {"symbol": "000538", "name": "云南白药", "change_pct": 6.5},
            {"symbol": "300003", "name": "乐普医疗", "change_pct": 5.9},
        ]),
        SampleEvent(0, "10:22", "consumer", "消费板块", "fall", -0.05, -5.5, [
            {"symbol": "600519", "name": "贵州茅台", "change_pct": -4.2},
            {"symbol": "000858", "name": "五粮液", "change_pct": -3.8},
        ]),
        
        # 早盘震荡
        SampleEvent(0, "10:35", "finance", "金融板块", "fall", -0.04, -4.2, [
            {"symbol": "601398", "name": "工商银行", "change_pct": -3.5},
            {"symbol": "601288", "name": "农业银行", "change_pct": -2.8},
        ]),
        SampleEvent(0, "10:48", "real_estate", "房地产", "cooled", -0.08, -8.0, [
            {"symbol": "000002", "name": "万科A", "change_pct": -6.5},
            {"symbol": "600048", "name": "保利地产", "change_pct": -5.8},
            {"symbol": "001979", "name": "招商蛇口", "change_pct": -4.9},
        ]),
        
        # 早盘收尾
        SampleEvent(0, "11:05", "tech", "科技板块", "rise", 0.09, 9.5, [
            {"symbol": "603019", "name": "中科曙光", "change_pct": 7.2},
            {"symbol": "000977", "name": "浪潮信息", "change_pct": 6.8},
        ]),
        SampleEvent(0, "11:18", "materials", "材料板块", "new_hot", 0.07, 7.2, [
            {"symbol": "600585", "name": "海螺水泥", "change_pct": 6.5},
            {"symbol": "000878", "name": "云南铜业", "change_pct": 5.8},
        ]),
        
        # 午后开盘
        SampleEvent(0, "13:05", "healthcare", "医药板块", "rise", 0.11, 11.5, [
            {"symbol": "300122", "name": "智飞生物", "change_pct": 8.5},
            {"symbol": "002007", "name": "华兰生物", "change_pct": 7.2},
            {"symbol": "600436", "name": "片仔癀", "change_pct": 6.8},
        ]),
        SampleEvent(0, "13:15", "energy", "能源板块", "fall", -0.06, -6.8, [
            {"symbol": "601857", "name": "中国石油", "change_pct": -5.5},
            {"symbol": "600028", "name": "中国石化", "change_pct": -4.8},
        ]),
        
        # 午后活跃
        SampleEvent(0, "13:35", "tech", "科技板块", "fall", -0.07, -7.5, [
            {"symbol": "002371", "name": "北方华创", "change_pct": -6.2},
            {"symbol": "300014", "name": "亿纬锂能", "change_pct": -5.5},
            {"symbol": "600703", "name": "三安光电", "change_pct": -4.8},
        ]),
        SampleEvent(0, "13:48", "finance", "金融板块", "rise", 0.13, 13.2, [
            {"symbol": "600030", "name": "中信证券", "change_pct": 9.5},
            {"symbol": "601688", "name": "华泰证券", "change_pct": 8.2},
            {"symbol": "300059", "name": "东方财富", "change_pct": 7.8},
        ]),
        SampleEvent(0, "13:55", "new_energy", "新能源", "cooled", -0.09, -9.0, [
            {"symbol": "300750", "name": "宁德时代", "change_pct": -7.5},
            {"symbol": "601012", "name": "隆基绿能", "change_pct": -6.8},
            {"symbol": "002459", "name": "晶澳科技", "change_pct": -5.9},
        ]),
        
        # 午后震荡
        SampleEvent(0, "14:08", "consumer", "消费板块", "rise", 0.05, 5.8, [
            {"symbol": "000333", "name": "美的集团", "change_pct": 4.8},
            {"symbol": "600887", "name": "伊利股份", "change_pct": 4.2},
        ]),
        SampleEvent(0, "14:18", "healthcare", "医药板块", "fall", -0.08, -8.5, [
            {"symbol": "600276", "name": "恒瑞医药", "change_pct": -6.8},
            {"symbol": "000538", "name": "云南白药", "change_pct": -5.5},
        ]),
        
        # 尾盘决战
        SampleEvent(0, "14:35", "finance", "金融板块", "rise", 0.15, 15.5, [
            {"symbol": "601398", "name": "工商银行", "change_pct": 8.5},
            {"symbol": "601288", "name": "农业银行", "change_pct": 7.8},
            {"symbol": "600036", "name": "招商银行", "change_pct": 7.2},
        ]),
        SampleEvent(0, "14:42", "tech", "科技板块", "cooled", -0.12, -12.0, [
            {"symbol": "000063", "name": "中兴通讯", "change_pct": -8.5},
            {"symbol": "002415", "name": "海康威视", "change_pct": -7.2},
            {"symbol": "600570", "name": "恒生电子", "change_pct": -6.5},
        ]),
        SampleEvent(0, "14:55", "materials", "材料板块", "rise", 0.08, 8.2, [
            {"symbol": "601899", "name": "紫金矿业", "change_pct": 7.5},
            {"symbol": "603993", "name": "洛阳钼业", "change_pct": 6.8},
        ]),
    ]
    
    return samples


def _render_sector_trading_timeline() -> str:
    """
    板块炒作时间轴 - 展示每天各板块随时间的涨跌变化
    类似: 9:30 科技启动 -> 10:00 金融拉升 -> 10:30 医药跳水
    """
    from datetime import datetime
    
    tracker = _get_history_tracker()
    
    # 获取今天的事件（按时间排序）
    today = datetime.now().strftime("%m-%d")
    today_events = []
    has_real_data = False
    
    if tracker and tracker.sector_hotspot_events_medium:
        all_events = list(tracker.sector_hotspot_events_medium)
        
        # 过滤今天的事件并按时间排序
        for event in all_events:
            event_date = datetime.fromtimestamp(event.timestamp).strftime("%m-%d")
            if event_date == today:
                today_events.append(event)
        
        if today_events:
            has_real_data = True
        else:
            # 如果没有今天的事件，显示最近的事件
            today_events = all_events[-15:]
        
        # 按时间排序
        today_events.sort(key=lambda x: x.timestamp)
    
    # 如果没有数据，使用样例数据
    using_sample_data = not has_real_data and not today_events
    if using_sample_data:
        today_events = _get_sample_events()
    
    html = """
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 16px;
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="font-weight: 600; color: #1e293b; font-size: 14px;">
                📈 板块炒作时间轴
                <span style="font-size: 11px; color: #64748b; font-weight: normal; margin-left: 8px;">
                    今日板块起落
                </span>
            </div>
            <div style="font-size: 11px; color: #94a3b8;">{}个事件</div>
        </div>
        
        <!-- 数据状态提示 -->
        {}
        
        <!-- 事件说明 -->
        <div style="
            margin-bottom: 12px;
            padding: 8px 12px;
            background: #f0f9ff;
            border-radius: 6px;
            font-size: 11px;
            color: #0369a1;
            line-height: 1.5;
        ">
            <strong>📊 事件说明:</strong><br>
            • <strong>新热点</strong> 🔥: 板块权重从0开始上升（出现概率: 约5-10次/天）<br>
            • <strong>热点消退</strong> ❄️: 板块权重降为0（出现概率: 约3-5次/天）<br>
            • <strong>拉升</strong> 📈: 板块权重上升≥5%（出现概率: 约20-30次/天）<br>
            • <strong>回调</strong> 📉: 板块权重下降≥5%（出现概率: 约15-25次/天）<br>
            <em>注: 实际频率取决于市场波动程度，以上为中高波动市场的估算值</em>
        </div>
    """.format(
        len(today_events),
        "" if has_real_data else """
        <div style="
            margin-bottom: 12px;
            padding: 8px 12px;
            background: linear-gradient(135deg, #fef3c7, #fde68a);
            border: 1px solid #f59e0b;
            border-radius: 6px;
            font-size: 12px;
            color: #92400e;
        ">
            <strong>⚠️ 样例数据展示</strong> - 当前暂无实时数据，以下为示例效果。启动数据源后将显示真实数据。
        </div>
        """
    )
    
    # 时间段定义
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
    
    # 事件类型样式
    event_styles = {
        'new_hot': ('🔥', '#dc2626', '新热点'),
        'cooled': ('❄️', '#3b82f6', '热点消退'),
        'rise': ('📈', '#16a34a', '拉升'),
        'fall': ('📉', '#f59e0b', '回调'),
    }
    
    # 按时间段分组事件
    period_events = {i: [] for i in range(len(time_periods))}
    
    for event in today_events:
        try:
            # 解析时间
            if hasattr(event, 'market_time') and event.market_time:
                time_str = event.market_time
            else:
                time_str = datetime.fromtimestamp(event.timestamp).strftime("%H:%M")
            
            hour, minute = map(int, time_str.split(':'))
            time_val = hour * 100 + minute
            
            # 找到对应的时间段
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
    
    # 渲染时间轴（始终显示所有时间段）
    for i, (start, end, label, period_color) in enumerate(time_periods):
        events_in_period = period_events[i]
        has_events = len(events_in_period) > 0
        
        # 根据是否有事件调整样式
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
            <!-- 时间段标签 -->
            <div style="
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 8px;
                padding: 6px 10px;
                background: {header_bg};
                border-left: 3px solid {header_border};
                border-radius: 0 6px 6px 0;
            ">
                <span style="font-weight: 600; color: {period_color if has_events else '#94a3b8'}; font-size: 12px;">{label}</span>
                <span style="color: #94a3b8; font-size: 11px;">{start}-{end}</span>
                <span style="margin-left: auto; color: {'#64748b' if has_events else '#94a3b8'}; font-size: 11px;">{event_count_text}</span>
            </div>
            
            <!-- 该时间段的事件 -->
            <div style="padding-left: 16px; border-left: 2px dashed #e2e8f0; margin-left: 6px;">
        """
        
        if has_events:
            for time_str, event in events_in_period:
                emoji, evt_color, evt_label = event_styles.get(event.event_type, ('•', '#64748b', '变化'))
                change_sign = '+' if event.change_percent > 0 else ''
                
                # 根据变化幅度调整背景色
                if abs(event.change_percent) >= 10:
                    bg_color = '#fef2f2' if event.change_percent > 0 else '#eff6ff'
                    border_color = '#dc2626' if event.change_percent > 0 else '#3b82f6'
                elif abs(event.change_percent) >= 5:
                    bg_color = '#fff7ed' if event.change_percent > 0 else '#f0f9ff'
                    border_color = '#ea580c' if event.change_percent > 0 else '#0ea5e9'
                else:
                    bg_color = '#f8fafc'
                    border_color = evt_color
                
                # 获取板块主导个股
                top_symbols = getattr(event, 'top_symbols', [])[:3]  # 最多显示3个
                
                html += f"""
                <div style="
                    display: flex;
                    align-items: flex-start;
                    gap: 8px;
                    padding: 8px 10px;
                    margin-bottom: 6px;
                    background: {bg_color};
                    border-radius: 6px;
                    border-left: 3px solid {border_color};
                    font-size: 12px;
                ">
                    <!-- 左侧：时间和板块信息 -->
                    <div style="min-width: 40px;">
                        <span style="color: #94a3b8; font-family: monospace; font-size: 11px;">{time_str}</span>
                    </div>
                    
                    <div style="flex: 1;">
                        <!-- 板块名称和事件类型 -->
                        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                            <span style="font-size: 14px;">{emoji}</span>
                            <span style="font-weight: 500; color: #1e293b;">{event.sector_name}</span>
                            <span style="font-size: 10px; color: {evt_color};">{evt_label}</span>
                            <span style="color: {border_color}; font-weight: 600; font-size: 13px; margin-left: auto;">
                                {change_sign}{event.change_percent:.1f}%
                            </span>
                        </div>
                        
                        <!-- 主导个股 -->
                        {f'''
                        <div style="
                            display: flex;
                            flex-wrap: wrap;
                            gap: 6px;
                            margin-top: 6px;
                            padding-top: 6px;
                            border-top: 1px dashed {border_color}40;
                        ">
                            <span style="font-size: 10px; color: #64748b;">领涨/领跌:</span>
                            {''.join([f"""
                            <span style="
                                font-size: 10px;
                                padding: 2px 6px;
                                background: {'#fef2f2' if s.get('change_pct', 0) > 0 else '#eff6ff'};
                                color: {'#dc2626' if s.get('change_pct', 0) > 0 else '#3b82f6'};
                                border-radius: 4px;
                                white-space: nowrap;
                            ">
                                {s.get('symbol', '')} {s.get('name', '')[:4]} {s.get('change_pct', 0):+.1f}%
                            </span>
                            """ for s in top_symbols])}
                        </div>
                        ''' if top_symbols else ''}
                    </div>
                </div>
                """
        else:
            # 无数据时的占位显示
            html += """
            <div style="
                padding: 12px 10px;
                margin-bottom: 6px;
                background: #f8fafc;
                border-radius: 6px;
                border-left: 3px solid #e2e8f0;
                font-size: 12px;
                color: #94a3b8;
                text-align: center;
            ">
                等待数据...
            </div>
            """
        
        html += "</div></div>"
    
    html += '</div>'
    return html


# ==================== 第三优先级：系统状态（可折叠） ====================

def _render_collapsible_system_status(report: Dict, strategy_stats: Dict) -> str:
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
        <summary style="
            cursor: pointer;
            padding: 12px 16px;
            background: linear-gradient(135deg, #f8fafc, #f1f5f9);
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            font-weight: 500;
            color: #1e293b;
            font-size: 13px;
            user-select: none;
        ">
            ⚙️ 系统状态详情 (点击展开)
        </summary>
        <div style="
            padding: 16px;
            background: white;
            border: 1px solid #e2e8f0;
            border-top: none;
            border-radius: 0 0 8px 8px;
        ">
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


# ==================== 第四优先级：最近信号（紧凑版） ====================

def _render_compact_signals(limit: int = 5) -> str:
    """紧凑的最近信号"""
    manager = _get_strategy_manager()
    if not manager:
        return ""
    
    signals = manager.get_recent_signals(n=limit)
    if not signals:
        return ""
    
    html = """
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 16px;
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <div style="font-weight: 600; color: #1e293b; font-size: 14px;">
                📡 最近信号
            </div>
        </div>
    """
    
    for signal in signals:
        emoji = "🚀" if signal.signal_type == 'buy' else "💨" if signal.signal_type == 'sell' else "👀"
        color = "#16a34a" if signal.signal_type == 'buy' else "#dc2626" if signal.signal_type == 'sell' else "#64748b"
        
        html += f"""
        <div style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 10px;
            margin-bottom: 6px;
            background: #f8fafc;
            border-radius: 6px;
            font-size: 12px;
        ">
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


# ==================== 第五优先级：噪音过滤（简化） ====================

def _render_compact_noise_filter() -> str:
    """简化的噪音过滤状态"""
    try:
        from deva.naja.attention import get_noise_filter
        noise_filter = get_noise_filter()
        stats = noise_filter.get_stats()
        
        total = stats.get('total_processed', 0)
        filtered = stats.get('total_filtered', 0)
        filter_rate = stats.get('filter_rate', '0.00%')
        
        return f"""
        <div style="
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 12px;
            background: #f0f9ff;
            border-radius: 6px;
            font-size: 11px;
            color: #0369a1;
            margin-bottom: 16px;
        ">
            <span>🔇</span>
            <span>噪音过滤: 已处理 {total:,} 条, 过滤 {filtered} 条 ({filter_rate})</span>
        </div>
        """
    except:
        return ""


# ==================== 主页面 ====================

async def render_attention_admin_v2(ctx: dict):
    """渲染优化版注意力系统页面"""
    
    attention_initialized = _is_attention_initialized()
    report = _get_attention_report()
    strategy_stats = _get_strategy_stats()
    experiment_info = _get_experiment_info()
    
    with use_scope("attention_header_v2"):
        put_html("<h3>👁️ 注意力监控</h3>")
        
        # 未初始化提示
        if not attention_initialized:
            put_html("""
            <div style="margin-bottom:14px;padding:12px;border-radius:8px;
                        background:linear-gradient(135deg,#fef3c7,#fde68a);
                        border:1px solid #f59e0b;color:#92400e;font-size:13px;">
                ⚠️ 注意力系统未启动
            </div>
            """)
            put_button("🚀 启动", onclick=lambda: _initialize_attention_system(), small=True, color="warning")
            put_text("")
        
        # 实验模式提示
        if experiment_info.get('active'):
            put_html(f"""
            <div style="margin-bottom:14px;padding:8px 12px;border-radius:6px;
                        background:linear-gradient(135deg,#dbeafe,#bfdbfe);
                        border:1px solid #93c5fd;color:#1e40af;font-size:12px;">
                🧪 实验模式: {experiment_info.get('datasource_id', '未知')}
            </div>
            """)
        
        # 控制按钮
        put_row([
            put_button("🔄 刷新", onclick=lambda: _do_refresh(), small=True),
            put_button("⏸️ 暂停", onclick=lambda: _toggle_refresh(), small=True),
            put_button("🔍 诊断", onclick=lambda: _run_diagnostic(), small=True),
        ], size="auto")
        
        put_text("")
    
    # ========== 第一优先级：核心摘要 ==========
    with use_scope("attention_summary"):
        put_html(_render_key_metrics_summary(report, strategy_stats))
    
    # ========== 第二优先级：实时热点 ==========
    with use_scope("attention_live"):
        put_html(_render_live_hotspots())
    
    # ========== 第三优先级：板块炒作时间轴 ==========
    with use_scope("attention_timeline"):
        put_html(_render_sector_trading_timeline())
    
    # ========== 第四优先级：最近信号 ==========
    with use_scope("attention_signals_compact"):
        put_html(_render_compact_signals(limit=5))
    
    # ========== 第五优先级：噪音过滤（简化行） ==========
    with use_scope("attention_noise"):
        put_html(_render_compact_noise_filter())
    
    # ========== 可折叠：系统详情 ==========
    with use_scope("attention_system_details"):
        put_html(_render_collapsible_system_status(report, strategy_stats))
    
    # 启动自动刷新
    if _auto_refresh_enabled:
        _start_auto_refresh()


def _do_refresh():
    """手动刷新"""
    toast("正在刷新...", color="info")
    run_js("window.location.reload()")


def _toggle_refresh():
    """切换自动刷新"""
    global _auto_refresh_enabled
    _auto_refresh_enabled = not _auto_refresh_enabled
    toast("自动刷新已" + ("启用" if _auto_refresh_enabled else "暂停"), 
          color="success" if _auto_refresh_enabled else "warning")


def _start_auto_refresh():
    """启动自动刷新"""
    if not _auto_refresh_enabled:
        return
    
    async def refresh_loop():
        while _auto_refresh_enabled:
            try:
                await session.sleep(_refresh_interval)
            except Exception:
                break
    
    session.run_async(refresh_loop())


def _run_diagnostic():
    """运行诊断"""
    from .diagnostic import render_attention_diagnostic
    render_attention_diagnostic()


def _initialize_attention_system():
    """初始化注意力系统"""
    try:
        from ..attention_config import load_config
        from ..attention_integration import initialize_attention_system
        
        config = load_config()
        if config.enabled:
            attention_system = initialize_attention_system(config)
            toast("✅ 注意力系统初始化成功！", color="success")
            run_js("setTimeout(() => window.location.reload(), 1000)")
        else:
            toast("⚠️ 注意力系统被禁用", color="warning")
    except Exception as e:
        toast(f"❌ 初始化失败: {e}", color="error")
