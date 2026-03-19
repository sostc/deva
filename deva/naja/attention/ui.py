"""注意力调度系统 UI

展示注意力系统的实时状态和变化
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
_refresh_interval = 2  # 刷新间隔（秒）


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
        from naja_attention_strategies import get_strategy_manager
        return get_strategy_manager()
    except Exception:
        return None


def _get_hot_sectors_and_stocks() -> Dict[str, Any]:
    """获取热门板块和股票"""
    integration = _get_attention_integration()
    if not integration:
        return {"sectors": [], "stocks": []}
    
    try:
        # 获取板块权重
        sector_weights = integration.attention_system.sector_attention.get_all_weights() if integration.attention_system else {}
        
        # 获取个股权重
        symbol_weights = integration.attention_system.weight_pool.get_all_weights() if integration.attention_system else {}
        
        # 排序获取热门板块
        hot_sectors = sorted(
            [(sector, weight) for sector, weight in sector_weights.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]  # Top 10
        
        # 排序获取热门股票
        hot_stocks = sorted(
            [(symbol, weight) for symbol, weight in symbol_weights.items()],
            key=lambda x: x[1],
            reverse=True
        )[:20]  # Top 20
        
        return {
            "sectors": hot_sectors,
            "stocks": hot_stocks
        }
    except Exception:
        return {"sectors": [], "stocks": []}


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


def _get_history_tracker():
    """获取历史追踪器"""
    try:
        from .history_tracker import get_history_tracker
        return get_history_tracker()
    except Exception:
        return None


def _get_attention_changes():
    """获取注意力变化记录"""
    tracker = _get_history_tracker()
    if tracker:
        try:
            return tracker.get_recent_changes(n=20)
        except Exception:
            pass
    return []


def _get_attention_shift_report():
    """获取注意力转移报告"""
    tracker = _get_history_tracker()
    if tracker:
        try:
            return tracker.get_attention_shift_report()
        except Exception:
            pass
    return {'has_shift': False}


def _register_stock_names(data: pd.DataFrame):
    """注册股票名称到历史追踪器"""
    tracker = _get_history_tracker()
    if tracker is None or data is None or data.empty:
        return
    
    try:
        # 从数据中注册股票名称
        if 'code' in data.columns and 'name' in data.columns:
            for _, row in data.iterrows():
                symbol = row['code']
                name = row.get('name', symbol)
                if symbol and name:
                    tracker.register_symbol_name(symbol, name)
    except Exception:
        pass


def _render_global_attention_card(global_attention: float) -> str:
    """渲染全局注意力卡片"""
    # 根据注意力水平设置颜色
    if global_attention >= 0.7:
        color = "#dc2626"  # 红色 - 高
        emoji = "🔥"
        level = "极高"
    elif global_attention >= 0.5:
        color = "#ea580c"  # 橙色 - 中高
        emoji = "⚡"
        level = "高"
    elif global_attention >= 0.3:
        color = "#ca8a04"  # 黄色 - 中
        emoji = "👁️"
        level = "中"
    else:
        color = "#16a34a"  # 绿色 - 低
        emoji = "💤"
        level = "低"
    
    return f"""
    <div style="
        background: linear-gradient(135deg, {color}22, {color}11);
        border: 2px solid {color};
        border-radius: 16px;
        padding: 24px;
        text-align: center;
        min-width: 200px;
    ">
        <div style="font-size: 48px; margin-bottom: 8px;">{emoji}</div>
        <div style="font-size: 42px; font-weight: bold; color: {color};">{global_attention:.3f}</div>
        <div style="font-size: 14px; color: #64748b; margin-top: 4px;">全局注意力</div>
        <div style="font-size: 12px; color: {color}; margin-top: 4px; font-weight: 600;">{level}</div>
    </div>
    """


def _render_frequency_distribution(freq_summary: Dict[str, int]) -> str:
    """渲染频率分布"""
    high = freq_summary.get('high_frequency', 0)
    medium = freq_summary.get('medium_frequency', 0)
    low = freq_summary.get('low_frequency', 0)
    total = high + medium + low
    
    if total == 0:
        total = 1
    
    high_pct = high / total * 100
    medium_pct = medium / total * 100
    low_pct = low / total * 100
    
    return f"""
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">📊 频率分布</div>
        
        <div style="margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                <span style="color: #dc2626; font-weight: 600;">🔴 高频</span>
                <span>{high} 只 ({high_pct:.1f}%)</span>
            </div>
            <div style="background: #fee2e2; height: 8px; border-radius: 4px; overflow: hidden;">
                <div style="background: #dc2626; height: 100%; width: {high_pct}%; transition: width 0.3s;"></div>
            </div>
        </div>
        
        <div style="margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                <span style="color: #ca8a04; font-weight: 600;">🟡 中频</span>
                <span>{medium} 只 ({medium_pct:.1f}%)</span>
            </div>
            <div style="background: #fef3c7; height: 8px; border-radius: 4px; overflow: hidden;">
                <div style="background: #ca8a04; height: 100%; width: {medium_pct}%; transition: width 0.3s;"></div>
            </div>
        </div>
        
        <div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                <span style="color: #16a34a; font-weight: 600;">🟢 低频</span>
                <span>{low} 只 ({low_pct:.1f}%)</span>
            </div>
            <div style="background: #dcfce7; height: 8px; border-radius: 4px; overflow: hidden;">
                <div style="background: #16a34a; height: 100%; width: {low_pct}%; transition: width 0.3s;"></div>
            </div>
        </div>
    </div>
    """


def _render_strategy_status(strategy_stats: Dict[str, Any]) -> str:
    """渲染策略状态"""
    if not strategy_stats:
        return "<div style='color: #64748b;'>暂无策略数据</div>"
    
    strategies = strategy_stats.get('strategy_stats', {})
    total_signals = strategy_stats.get('total_signals_generated', 0)
    
    html = f"""
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">
            🎯 策略状态 
            <span style="color: #3b82f6; font-size: 14px;">(总信号: {total_signals})</span>
        </div>
    """
    
    for strategy_id, stats in strategies.items():
        status = "🟢" if stats.get('enabled') else "🔴"
        name = stats.get('name', strategy_id)
        exec_count = stats.get('execution_count', 0)
        signal_count = stats.get('signal_count', 0)
        skip_count = stats.get('skip_count', 0)
        
        html += f"""
        <div style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px;
            margin-bottom: 8px;
            background: #f8fafc;
            border-radius: 8px;
            border-left: 3px solid {'#22c55e' if stats.get('enabled') else '#ef4444'};
        ">
            <div>
                <div style="font-weight: 500;">{status} {name}</div>
                <div style="font-size: 12px; color: #64748b; margin-top: 2px;">
                    执行: {exec_count} | 信号: {signal_count} | 跳过: {skip_count}
                </div>
            </div>
            <div style="font-size: 12px; color: #64748b;">
                优先级: {stats.get('priority', 5)}
            </div>
        </div>
        """
    
    html += "</div>"
    return html


def _render_dual_engine_status(dual_summary: Dict[str, Any]) -> str:
    """渲染双引擎状态 - 带说明"""
    if not dual_summary:
        return ""
    
    river_stats = dual_summary.get('river_stats', {})
    pytorch_stats = dual_summary.get('pytorch_stats', {})
    trigger_count = dual_summary.get('trigger_count', 0)
    
    # 计算异常率
    processed = river_stats.get('processed_count', 0)
    anomalies = river_stats.get('anomaly_count', 0)
    anomaly_ratio = (anomalies / max(processed, 1)) * 100
    
    # 队列状态判断
    queue_size = pytorch_stats.get('pending_queue_size', 0)
    inference_count = pytorch_stats.get('inference_count', 0)
    
    if queue_size > 10000 and inference_count == 0:
        queue_status = "⚠️ 严重积压"
        queue_color = "#dc2626"
    elif queue_size > 1000:
        queue_status = "⏳ 队列积压"
        queue_color = "#f59e0b"
    else:
        queue_status = "✅ 正常"
        queue_color = "#16a34a"
    
    return f"""
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">
            ⚙️ 双引擎状态
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">轻量筛选 → 深度分析</span>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
            <!-- River Engine -->
            <div style="
                background: linear-gradient(135deg, #dbeafe, #bfdbfe);
                padding: 16px;
                border-radius: 8px;
            ">
                <div style="font-weight: 600; color: #1e40af; margin-bottom: 8px;">🌊 River Engine</div>
                <div style="font-size: 12px; color: #1e3a8a; line-height: 1.6;">
                    <div style="display: flex; justify-content: space-between;">
                        <span>处理数据:</span>
                        <span style="font-weight: 600;">{processed:,}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>异常检测:</span>
                        <span style="font-weight: 600;">{anomalies:,}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>异常率:</span>
                        <span style="font-weight: 600;">{anomaly_ratio:.1f}%</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>活跃股票:</span>
                        <span style="font-weight: 600;">{river_stats.get('active_symbols', 0)} 只</span>
                    </div>
                </div>
                <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #93c5fd; font-size: 11px; color: #3b82f6;">
                    💡 快速检测价格/成交量异常波动
                </div>
            </div>
            
            <!-- PyTorch Engine -->
            <div style="
                background: linear-gradient(135deg, #fce7f3, #fbcfe8);
                padding: 16px;
                border-radius: 8px;
            ">
                <div style="font-weight: 600; color: #9d174d; margin-bottom: 8px;">🔥 PyTorch Engine</div>
                <div style="font-size: 12px; color: #831843; line-height: 1.6;">
                    <div style="display: flex; justify-content: space-between;">
                        <span>深度推理:</span>
                        <span style="font-weight: 600;">{inference_count:,}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>待处理队列:</span>
                        <span style="font-weight: 600; color: {queue_color};">{queue_size:,}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>队列状态:</span>
                        <span style="font-weight: 600; color: {queue_color};">{queue_status}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>处理中:</span>
                        <span style="font-weight: 600;">{pytorch_stats.get('processing_count', 0)}</span>
                    </div>
                </div>
                <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #f9a8d4; font-size: 11px; color: #db2777;">
                    💡 深度学习模型分析严重异常
                </div>
            </div>
        </div>
        
        <!-- 触发统计 -->
        <div style="
            margin-top: 16px; 
            padding: 12px;
            background: linear-gradient(135deg, #f0fdf4, #dcfce7);
            border-radius: 8px;
            border: 1px solid #86efac;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-weight: 600; color: #166534;">🔗 双引擎触发次数:</span>
                    <span style="font-size: 18px; font-weight: 700; color: #15803d; margin-left: 8px;">{trigger_count}</span>
                </div>
                <div style="font-size: 11px; color: #22c55e; text-align: right;">
                    River检测到严重异常 → 触发PyTorch深度分析
                </div>
            </div>
        </div>
        
        <!-- 说明文字 -->
        <div style="margin-top: 12px; padding: 12px; background: #f8fafc; border-radius: 6px; font-size: 11px; color: #64748b; line-height: 1.5;">
            <strong>📊 数据解读:</strong><br>
            • <strong>异常率</strong>: 价格/成交量超出正常统计范围的数据占比（正常约10-20%）<br>
            • <strong>队列积压</strong>: River检测到异常但PyTorch未触发，说明异常分数不够高或触发阈值过高<br>
            • <strong>触发机制</strong>: 只有当异常达到严重程度(分数&gt;阈值)时，才会触发PyTorch深度推理
        </div>
    </div>
    """


def _render_noise_filter_status() -> str:
    """渲染噪音过滤状态"""
    try:
        from naja_attention_system import get_noise_filter
        noise_filter = get_noise_filter()
        stats = noise_filter.get_stats()
        
        total = stats.get('total_processed', 0)
        filtered = stats.get('total_filtered', 0)
        filter_rate = stats.get('filter_rate', '0.00%')
        config = stats.get('config', {})
        top_filtered = stats.get('top_filtered_symbols', [])
        blacklist_size = stats.get('blacklist_size', 0)
        whitelist_size = stats.get('whitelist_size', 0)
        
        # 过滤率颜色
        rate_value = float(filter_rate.replace('%', ''))
        if rate_value > 30:
            rate_color = '#dc2626'
            rate_bg = '#fef2f2'
        elif rate_value > 10:
            rate_color = '#f59e0b'
            rate_bg = '#fffbeb'
        else:
            rate_color = '#16a34a'
            rate_bg = '#f0fdf4'
        
        html = f"""
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">
            🔇 噪音过滤状态
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">低流动性股票过滤</span>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-bottom: 16px;">
            <!-- 总处理 -->
            <div style="
                background: linear-gradient(135deg, #f1f5f9, #e2e8f0);
                padding: 12px;
                border-radius: 8px;
                text-align: center;
            ">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">总处理</div>
                <div style="font-size: 20px; font-weight: 700; color: #1e293b;">{total:,}</div>
                <div style="font-size: 10px; color: #94a3b8;">条记录</div>
            </div>
            
            <!-- 已过滤 -->
            <div style="
                background: linear-gradient(135deg, {rate_bg}, #ffffff);
                padding: 12px;
                border-radius: 8px;
                text-align: center;
                border: 1px solid {rate_color}33;
            ">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">已过滤</div>
                <div style="font-size: 20px; font-weight: 700; color: {rate_color};">{filtered:,}</div>
                <div style="font-size: 10px; color: {rate_color};">{filter_rate}</div>
            </div>
            
            <!-- 黑白名单 -->
            <div style="
                background: linear-gradient(135deg, #f1f5f9, #e2e8f0);
                padding: 12px;
                border-radius: 8px;
                text-align: center;
            ">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">黑白名单</div>
                <div style="font-size: 16px; font-weight: 600; color: #1e293b;">
                    <span style="color: #dc2626;">⚫ {blacklist_size}</span>
                    <span style="color: #94a3b8; margin: 0 4px;">|</span>
                    <span style="color: #16a34a;">⚪ {whitelist_size}</span>
                </div>
                <div style="font-size: 10px; color: #94a3b8;">黑名单 | 白名单</div>
            </div>
        </div>
        
        <!-- 阈值配置 -->
        <div style="
            background: #f8fafc;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 12px;
        ">
            <div style="font-size: 12px; font-weight: 600; color: #1e293b; margin-bottom: 8px;">📋 过滤阈值配置</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; font-size: 11px;">
                <div style="text-align: center; padding: 8px; background: white; border-radius: 6px;">
                    <div style="color: #64748b;">最小金额</div>
                    <div style="font-weight: 600; color: #1e293b;">{config.get('min_amount', 1000000):,.0f}</div>
                </div>
                <div style="text-align: center; padding: 8px; background: white; border-radius: 6px;">
                    <div style="color: #64748b;">最小成交量</div>
                    <div style="font-weight: 600; color: #1e293b;">{config.get('min_volume', 100000):,.0f}</div>
                </div>
                <div style="text-align: center; padding: 8px; background: white; border-radius: 6px;">
                    <div style="color: #64748b;">动态阈值</div>
                    <div style="font-weight: 600; color: #1e293b;">{'✅ 启用' if config.get('dynamic_threshold') else '❌ 禁用'}</div>
                </div>
            </div>
        </div>
        
        <!-- 最常过滤的股票 -->
        {f"""
        <div style="margin-top: 12px;">
            <div style="font-size: 12px; font-weight: 600; color: #1e293b; margin-bottom: 8px;">📊 最常过滤的股票</div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                {''.join([f'<span style="font-size: 11px; padding: 4px 8px; background: #fee2e2; color: #dc2626; border-radius: 4px;">{sym}: {cnt}次</span>' for sym, cnt in top_filtered[:5]])}
            </div>
        </div>
        """ if top_filtered else ""}
        
        <!-- 说明 -->
        <div style="margin-top: 12px; padding: 10px; background: #f0f9ff; border-radius: 6px; font-size: 11px; color: #0369a1; line-height: 1.5;">
            <strong>💡 过滤规则:</strong><br>
            • 成交金额低于阈值的股票会被过滤（如南玻Ｂ等低流动性B股）<br>
            • B股默认会被过滤（名称以"Ｂ"或"B"结尾）<br>
            • 黑名单中的股票会被强制过滤，白名单中的股票会被保护
        </div>
    </div>
        """
        
        return html
    except Exception as e:
        return f"""
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 8px; color: #1e293b;">🔇 噪音过滤状态</div>
        <div style="color: #64748b; font-size: 13px;">加载失败: {e}</div>
    </div>
        """


def _render_pytorch_patterns() -> str:
    """渲染 PyTorch 模式识别结果"""
    try:
        # 从 attention_integration 获取 dual_engine 的 pattern_cache
        integration = _get_attention_integration()
        if not integration or not integration.attention_system:
            return ""
        
        dual_engine = integration.attention_system.dual_engine
        if not dual_engine or not dual_engine.pytorch:
            return ""
        
        pytorch = dual_engine.pytorch
        pattern_cache = pytorch._pattern_cache
        
        if not pattern_cache:
            return ""
        
        # 获取最近的模式识别结果（按时间排序）
        patterns = sorted(pattern_cache.values(), key=lambda x: x.timestamp, reverse=True)[:10]
        
        html = """
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">
            🔍 PyTorch 模式识别结果
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">深度学习异常检测</span>
        </div>
        """
        
        # 模式类型图标和颜色
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
            
            # 根据置信度设置背景色
            if confidence >= 0.8:
                bg_color = '#fef2f2'
                border_color = '#fecaca'
            elif confidence >= 0.6:
                bg_color = '#fff7ed'
                border_color = '#fed7aa'
            else:
                bg_color = '#f8fafc'
                border_color = '#e2e8f0'
            
            html += f"""
        <div style="
            padding: 12px;
            margin-bottom: 8px;
            background: {bg_color};
            border: 1px solid {border_color};
            border-radius: 8px;
            border-left: 3px solid {color};
        ">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 18px;">{emoji}</span>
                    <div>
                        <div style="font-weight: 600; color: #1e293b;">{pattern.symbol}</div>
                        <div style="font-size: 11px; color: #64748b;">{label} | 得分: {pattern.pattern_score:.2f}</div>
                    </div>
                </div>
                <div style="text-align: right;">
                    <div style="font-weight: 700; color: {color}; font-size: 14px;">{confidence:.1%}</div>
                    <div style="font-size: 10px; color: #94a3b8;">置信度</div>
                </div>
            </div>
        </div>
        """
        
        html += '</div>'
        return html
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"渲染 PyTorch 模式结果失败: {e}")
        return ""


def _get_trend_indicator(current_weight: float, history: list) -> str:
    """获取趋势指示器"""
    if len(history) < 2:
        return "→"
    
    prev_weight = history[-2] if len(history) >= 2 else history[0]
    change = current_weight - prev_weight
    
    if change > 0.1:
        return "↗️"
    elif change < -0.1:
        return "↘️"
    else:
        return "→"


def _render_hot_sectors_and_stocks(hot_data: Dict[str, Any]) -> str:
    """渲染热门板块和股票 - 增强版"""
    sectors = hot_data.get("sectors", [])
    stocks = hot_data.get("stocks", [])
    
    if not sectors and not stocks:
        return ""
    
    # 获取历史追踪器以获取名称和趋势
    tracker = _get_history_tracker()
    
    html = """
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b; font-size: 16px;">
            🔥 热门板块与股票
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">实时注意力排名</span>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
    """
    
    # 热门板块
    if sectors:
        html += """
            <div>
                <div style="font-weight: 600; color: #7c3aed; margin-bottom: 12px; font-size: 14px; 
                            display: flex; justify-content: space-between; align-items: center;">
                    <span>📊 热门板块 Top 10</span>
                    <span style="font-size: 11px; color: #94a3b8; font-weight: normal;">注意力权重</span>
                </div>
        """
        
        # 计算最大权重用于进度条
        max_sector_weight = max([w for _, w in sectors[:10]]) if sectors else 1
        
        for i, (sector_id, weight) in enumerate(sectors[:10], 1):
            # 根据权重确定颜色和状态
            if weight > 0.7:
                color = "#dc2626"
                status = "🔥 极高"
                bg_gradient = "linear-gradient(90deg, #fee2e2, #fecaca)"
            elif weight > 0.5:
                color = "#ea580c"
                status = "⚡ 高"
                bg_gradient = "linear-gradient(90deg, #ffedd5, #fed7aa)"
            elif weight > 0.3:
                color = "#ca8a04"
                status = "👁️ 中"
                bg_gradient = "linear-gradient(90deg, #fef3c7, #fde68a)"
            else:
                color = "#16a34a"
                status = "💤 低"
                bg_gradient = "linear-gradient(90deg, #dcfce7, #bbf7d0)"
            
            # 获取板块名称
            sector_name = tracker.get_sector_name(sector_id) if tracker else sector_id
            display_name = sector_name if sector_name != sector_id else sector_id
            
            # 获取趋势
            trend = "→"
            if tracker:
                trend_data = tracker.get_sector_trend(sector_id, n=3)
                if len(trend_data) >= 2:
                    prev_weight = trend_data[-2]['weight']
                    change_pct = ((weight - prev_weight) / prev_weight * 100) if prev_weight > 0 else 0
                    if change_pct > 5:
                        trend = "📈"
                    elif change_pct < -5:
                        trend = "📉"
                    else:
                        trend = "➡️"
            
            # 进度条宽度
            progress_width = (weight / max_sector_weight * 100) if max_sector_weight > 0 else 0
            
            html += f"""
                <div style="
                    padding: 10px 12px;
                    margin-bottom: 8px;
                    background: {bg_gradient};
                    border-radius: 8px;
                    border-left: 3px solid {color};
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="color: #64748b; font-weight: 600; min-width: 20px;">{i}.</span>
                            <span style="font-weight: 500; color: #1e293b;" title="ID: {sector_id}">{display_name}</span>
                            <span style="font-size: 12px;">{trend}</span>
                        </div>
                        <div style="text-align: right;">
                            <span style="color: {color}; font-weight: 700; font-size: 14px;">{weight:.3f}</span>
                            <span style="font-size: 10px; color: {color}; margin-left: 4px;">{status}</span>
                        </div>
                    </div>
                    <div style="background: rgba(255,255,255,0.5); height: 4px; border-radius: 2px; overflow: hidden;">
                        <div style="background: {color}; height: 100%; width: {progress_width}%; border-radius: 2px; transition: width 0.3s;"></div>
                    </div>
                </div>
            """
        html += "</div>"
    
    # 热门股票
    if stocks:
        html += """
            <div>
                <div style="font-weight: 600; color: #2563eb; margin-bottom: 12px; font-size: 14px;
                            display: flex; justify-content: space-between; align-items: center;">
                    <span>📈 热门股票 Top 20</span>
                    <span style="font-size: 11px; color: #94a3b8; font-weight: normal;">注意力得分</span>
                </div>
                <div style="max-height: 500px; overflow-y: auto; padding-right: 4px;">
        """
        
        # 计算最大权重用于进度条
        max_stock_weight = max([w for _, w in stocks[:20]]) if stocks else 1
        
        for i, (symbol, weight) in enumerate(stocks[:20], 1):
            # 根据权重确定颜色和状态
            if weight > 5:
                color = "#dc2626"
                status = "🔥 爆发"
                bg_color = "#fef2f2"
                border_color = "#fecaca"
            elif weight > 3:
                color = "#ea580c"
                status = "⚡ 强势"
                bg_color = "#fff7ed"
                border_color = "#fed7aa"
            elif weight > 2:
                color = "#ca8a04"
                status = "📊 活跃"
                bg_color = "#fefce8"
                border_color = "#fef08a"
            else:
                color = "#16a34a"
                status = "💤 平稳"
                bg_color = "#f0fdf4"
                border_color = "#bbf7d0"
            
            # 获取股票名称
            symbol_name = tracker.get_symbol_name(symbol) if tracker else symbol
            display_name = symbol_name if symbol_name != symbol else ""
            
            # 获取趋势
            trend = "➡️"
            change_str = ""
            if tracker:
                trend_data = tracker.get_symbol_trend(symbol, n=3)
                if len(trend_data) >= 2:
                    prev_weight = trend_data[-2]['weight']
                    change = weight - prev_weight
                    change_pct = (change / prev_weight * 100) if prev_weight > 0 else 0
                    if change_pct > 10:
                        trend = "🚀"
                    elif change_pct > 5:
                        trend = "📈"
                    elif change_pct < -10:
                        trend = "📉"
                    elif change_pct < -5:
                        trend = "🔻"
                    
                    if abs(change_pct) > 1:
                        change_str = f"{change_pct:+.1f}%"
            
            # 进度条宽度
            progress_width = (weight / max_stock_weight * 100) if max_stock_weight > 0 else 0
            
            html += f"""
                <div style="
                    padding: 8px 10px;
                    margin-bottom: 6px;
                    background: {bg_color};
                    border: 1px solid {border_color};
                    border-radius: 8px;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <div style="display: flex; align-items: center; gap: 6px; flex: 1;">
                            <span style="color: #64748b; font-weight: 600; min-width: 18px; font-size: 12px;">{i}.</span>
                            <span style="font-weight: 600; color: #1e293b; font-size: 13px;">{symbol}</span>
                            {f'<span style="font-size: 11px; color: #64748b; flex: 1;">{display_name}</span>' if display_name else ''}
                            <span style="font-size: 11px;">{trend}</span>
                        </div>
                        <div style="text-align: right; margin-left: 8px;">
                            <span style="color: {color}; font-weight: 700; font-size: 13px;">{weight:.2f}</span>
                            {f'<span style="font-size: 9px; color: {color}; margin-left: 3px;">{change_str}</span>' if change_str else ''}
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <div style="background: rgba(255,255,255,0.6); height: 3px; border-radius: 2px; overflow: hidden; flex: 1;">
                            <div style="background: {color}; height: 100%; width: {progress_width}%; border-radius: 2px; transition: width 0.3s;"></div>
                        </div>
                        <span style="font-size: 9px; color: {color}; min-width: 35px; text-align: right;">{status}</span>
                    </div>
                </div>
            """
        html += "</div></div>"
    
    html += "</div></div>"
    return html


def _render_sector_trends() -> str:
    """渲染板块注意力变化曲线 - 主视图"""
    from datetime import datetime
    
    tracker = _get_history_tracker()
    if not tracker or len(tracker.snapshots) < 2:
        return "<div style='color: #64748b; text-align: center; padding: 20px;'>数据不足，无法显示趋势</div>"
    
    # 获取最近30个快照
    recent_snapshots = list(tracker.snapshots)[-30:]
    
    html = """
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">
            📊 板块注意力变化曲线
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">最近30个时间点</span>
        </div>
    """
    
    # 获取所有板块
    all_sectors = set()
    for snapshot in recent_snapshots:
        all_sectors.update(snapshot.sector_weights.keys())
    
    # 板块颜色配置
    sector_colors = {
        'tech': '#3b82f6',      # 蓝色
        'finance': '#10b981',   # 绿色
        'healthcare': '#f59e0b', # 橙色
        'energy': '#ef4444',    # 红色
        'consumer': '#8b5cf6',  # 紫色
    }
    
    # 为每个板块渲染趋势
    for sector_id in sorted(all_sectors):
        sector_name = tracker.get_sector_name(sector_id)
        color = sector_colors.get(sector_id, '#64748b')
        
        # 获取该板块的历史数据
        sector_data = []
        for snapshot in recent_snapshots:
            weight = snapshot.sector_weights.get(sector_id, 0)
            time_str = datetime.fromtimestamp(snapshot.timestamp).strftime("%H:%M")
            sector_data.append((time_str, weight))
        
        if not sector_data:
            continue
        
        # 计算当前值和变化
        current_weight = sector_data[-1][1]
        prev_weight = sector_data[0][1] if len(sector_data) > 1 else current_weight
        change_pct = ((current_weight - prev_weight) / prev_weight * 100) if prev_weight > 0 else 0
        
        # 生成趋势条
        max_weight = max([w for _, w in sector_data]) if sector_data else 1
        trend_bars = ""
        for time_str, weight in sector_data:
            height_pct = (weight / max_weight * 100) if max_weight > 0 else 0
            trend_bars += f"""
                <div style="
                    flex: 1;
                    background: {color};
                    height: {height_pct}%;
                    min-height: 2px;
                    margin: 0 1px;
                    border-radius: 1px;
                    opacity: {0.4 + (height_pct / 200)};
                " title="{time_str}: {weight:.3f}"></div>
            """
        
        # 获取该板块下的热门个股（Top 3）
        top_symbols = []
        if recent_snapshots:
            latest_snapshot = recent_snapshots[-1]
            # 这里简化处理，实际应该根据symbol_sector_map关联
            # 现在显示全局热门个股作为示例
            sorted_symbols = sorted(latest_snapshot.symbol_weights.items(), 
                                   key=lambda x: x[1], reverse=True)[:3]
            for symbol, weight in sorted_symbols:
                symbol_name = tracker.get_symbol_name(symbol)
                display = f"{symbol}" if symbol_name == symbol else f"{symbol} {symbol_name}"
                top_symbols.append(f"{display}({weight:.1f})")
        
        symbols_str = ", ".join(top_symbols) if top_symbols else "暂无数据"
        
        # 变化指示
        change_emoji = "📈" if change_pct > 0 else "📉" if change_pct < 0 else "➡️"
        change_color = "#16a34a" if change_pct > 0 else "#dc2626" if change_pct < 0 else "#64748b"
        
        html += f"""
        <div style="
            margin-bottom: 16px;
            padding: 12px;
            background: linear-gradient(135deg, #f8fafc, #f1f5f9);
            border-radius: 10px;
            border-left: 4px solid {color};
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-weight: 600; color: #1e293b; font-size: 14px;">{sector_name}</span>
                    <span style="font-size: 11px; color: #64748b;">({sector_id})</span>
                </div>
                <div style="text-align: right;">
                    <span style="font-weight: 700; color: {color}; font-size: 16px;">{current_weight:.3f}</span>
                    <span style="font-size: 11px; color: {change_color}; margin-left: 4px;">
                        {change_emoji} {change_pct:+.1f}%
                    </span>
                </div>
            </div>
            
            <!-- 趋势图 -->
            <div style="
                display: flex;
                align-items: flex-end;
                height: 40px;
                margin: 8px 0;
                padding: 4px;
                background: rgba(255,255,255,0.5);
                border-radius: 4px;
            ">
                {trend_bars}
            </div>
            
            <!-- 时间轴 -->
            <div style="display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; margin-top: 2px;">
                <span>{sector_data[0][0]}</span>
                <span>{sector_data[len(sector_data)//2][0]}</span>
                <span>{sector_data[-1][0]}</span>
            </div>
            
            <!-- 热门个股 -->
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #e2e8f0;">
                <span style="font-size: 11px; color: #64748b;">热门个股: </span>
                <span style="font-size: 11px; color: #374151;">{symbols_str}</span>
            </div>
        </div>
        """
    
    html += "</div>"
    return html


def _render_recent_signals(signals: List[Any], limit: int = 10) -> str:
    """渲染最近信号"""
    if not signals:
        return "<div style='color: #64748b; text-align: center; padding: 20px;'>暂无信号</div>"
    
    html = """
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">📡 最近信号</div>
    """
    
    for signal in list(signals)[-limit:]:
        emoji = "🚀" if signal.signal_type == 'buy' else "💨" if signal.signal_type == 'sell' else "👀"
        color = "#16a34a" if signal.signal_type == 'buy' else "#dc2626" if signal.signal_type == 'sell' else "#64748b"
        
        html += f"""
        <div style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            margin-bottom: 6px;
            background: #f8fafc;
            border-radius: 6px;
            font-size: 13px;
        ">
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


def _render_sector_hotspot_timeline(threshold: str = "medium") -> str:
    """渲染板块热点切换时间线 - 支持多阈值
    
    Args:
        threshold: 阈值级别 - 'low'(3%), 'medium'(5%), 'high'(10%)
    """
    from datetime import datetime
    
    tracker = _get_history_tracker()
    if not tracker:
        return """
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">
            🔥 板块热点切换时间线
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">多阈值事件记录</span>
        </div>
        <div style="color: #64748b; text-align: center; padding: 40px 20px;">
            <div style="font-size: 24px; margin-bottom: 8px;">📊</div>
            <div>历史追踪器未初始化</div>
        </div>
    </div>
    """
    
    # 根据阈值选择对应的事件队列
    threshold_config = {
        'low': {'events': tracker.sector_hotspot_events_low, 'pct': 3, 'label': '低敏感度', 'color': '#16a34a'},
        'medium': {'events': tracker.sector_hotspot_events_medium, 'pct': 5, 'label': '中敏感度', 'color': '#ca8a04'},
        'high': {'events': tracker.sector_hotspot_events_high, 'pct': 10, 'label': '高敏感度', 'color': '#dc2626'},
    }
    
    config = threshold_config.get(threshold, threshold_config['medium'])
    events = config['events']
    pct = config['pct']
    label = config['label']
    header_color = config['color']
    
    # 如果没有事件，显示空状态
    if not events:
        return f"""
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: {header_color};">
            🔥 {label} ({pct}%阈值)
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">暂无事件</span>
        </div>
        <div style="color: #64748b; text-align: center; padding: 40px 20px;">
            <div style="font-size: 24px; margin-bottom: 8px;">📊</div>
            <div>暂无板块变化事件</div>
            <div style="font-size: 12px; margin-top: 8px; color: #94a3b8;">
                当板块权重变化超过 ±{pct}% 时会自动记录<br>
                等待数据更新中...
            </div>
        </div>
    </div>
    """
    
    html = f"""
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: {header_color};">
            🔥 {label} ({pct}%阈值)
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">共{len(events)}个事件</span>
        </div>
    """
    
    # 事件类型图标和颜色
    event_styles = {
        'new_hot': ('🔥', '#dc2626', '新热点'),
        'cooled': ('❄️', '#3b82f6', '热点消退'),
        'rise': ('📈', '#16a34a', '大幅拉升'),
        'fall': ('📉', '#f59e0b', '明显回调'),
    }
    
    # 按时间倒序显示最近的事件
    recent_events = list(events)[-15:]
    current_date = None
    
    for event in reversed(recent_events):
        # 日期分隔
        event_date = datetime.fromtimestamp(event.timestamp).strftime("%m-%d")
        if event_date != current_date:
            current_date = event_date
            html += f"""
            <div style="
                margin: 12px 0 8px 0;
                padding: 4px 0;
                border-bottom: 1px dashed #e2e8f0;
                font-size: 12px;
                color: #94a3b8;
                font-weight: 500;
            ">
                📅 {event_date}
            </div>
            """
        
        emoji, color, label = event_styles.get(event.event_type, ('•', '#64748b', event.event_type))
        
        # 根据事件类型设置背景色
        bg_colors = {
            'new_hot': '#fef2f2',
            'cooled': '#eff6ff',
            'rise': '#f0fdf4',
            'fall': '#fffbeb',
        }
        bg_color = bg_colors.get(event.event_type, '#f8fafc')
        
        # 变化方向
        change_emoji = '📈' if event.change_percent > 0 else '📉'
        change_sign = '+' if event.change_percent > 0 else ''
        
        html += f"""
        <div style="
            padding: 12px;
            margin-bottom: 10px;
            background: {bg_color};
            border-radius: 8px;
            border-left: 3px solid {color};
        ">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                        <span style="font-size: 11px; color: #64748b; font-family: monospace; min-width: 50px;">{event.market_time}</span>
                        <span style="font-size: 18px;">{emoji}</span>
                        <span style="font-weight: 600; color: #1e293b;">{event.sector_name}</span>
                        <span style="font-size: 10px; color: {color}; background: rgba(255,255,255,0.6); padding: 2px 8px; border-radius: 4px;">{label}</span>
                    </div>
                    <div style="font-size: 12px; color: #64748b; margin-left: 58px; line-height: 1.5;">
                        权重: {event.weight_change:+.3f} ({change_sign}{event.change_percent:.1f}%)
                    </div>
                </div>
            </div>
        """
        
        # 添加领涨/领跌个股
        if event.top_symbols:
            html += """
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #e2e8f0;">
                <div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">板块内个股:</div>
                <div style="display: flex; flex-direction: column; gap: 4px;">
            """
            for s in event.top_symbols[:3]:  # 最多显示3个
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


def _render_multi_threshold_timeline() -> str:
    """渲染多阈值板块热点切换时间线 - 三栏并排展示"""
    html = """
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 20px; color: #1e293b; font-size: 16px;">
            🔥 板块热点切换时间线
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">多阈值对比分析</span>
        </div>
        
        <!-- 阈值说明 -->
        <div style="
            display: flex;
            gap: 16px;
            margin-bottom: 20px;
            padding: 12px 16px;
            background: linear-gradient(135deg, #f8fafc, #f1f5f9);
            border-radius: 8px;
            font-size: 12px;
        ">
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="width: 12px; height: 12px; background: #16a34a; border-radius: 3px;"></span>
                <span><strong>低阈值 (3%)</strong>: 捕捉细微变化，事件较多</span>
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="width: 12px; height: 12px; background: #ca8a04; border-radius: 3px;"></span>
                <span><strong>中阈值 (5%)</strong>: 平衡敏感度，推荐关注</span>
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
                <span style="width: 12px; height: 12px; background: #dc2626; border-radius: 3px;"></span>
                <span><strong>高阈值 (10%)</strong>: 重大变化，事件较少</span>
            </div>
        </div>
        
        <!-- 三栏时间线 -->
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px;">
    """
    
    # 三个阈值的时间线
    thresholds = ['low', 'medium', 'high']
    for threshold in thresholds:
        html += f"""
            <div style="min-width: 0;">
                {_render_single_threshold_column(threshold)}
            </div>
        """
    
    html += """
        </div>
    </div>
    """
    return html


def _render_single_threshold_column(threshold: str) -> str:
    """渲染单个阈值的紧凑时间线列"""
    from datetime import datetime
    
    tracker = _get_history_tracker()
    if not tracker:
        return "<div style='color: #64748b; text-align: center;'>未初始化</div>"
    
    # 配置
    threshold_config = {
        'low': {'events': tracker.sector_hotspot_events_low, 'pct': 3, 'label': '低敏感度', 'color': '#16a34a', 'bg': '#f0fdf4'},
        'medium': {'events': tracker.sector_hotspot_events_medium, 'pct': 5, 'label': '中敏感度', 'color': '#ca8a04', 'bg': '#fefce8'},
        'high': {'events': tracker.sector_hotspot_events_high, 'pct': 10, 'label': '高敏感度', 'color': '#dc2626', 'bg': '#fef2f2'},
    }
    
    config = threshold_config.get(threshold, threshold_config['medium'])
    events = list(config['events'])[-10:]  # 只显示最近10个
    pct = config['pct']
    label = config['label']
    color = config['color']
    bg = config['bg']
    
    if not events:
        return f"""
        <div style="
            background: {bg};
            border: 1px solid {color}33;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        ">
            <div style="font-weight: 600; color: {color}; margin-bottom: 8px;">{label} ({pct}%)</div>
            <div style="font-size: 12px; color: #64748b;">暂无事件</div>
        </div>
        """
    
    html = f"""
    <div style="
        background: {bg};
        border: 1px solid {color}33;
        border-radius: 8px;
        padding: 12px;
    ">
        <div style="font-weight: 600; color: {color}; margin-bottom: 12px; font-size: 13px;">
            {label} ({pct}%) <span style="font-weight: normal; color: #64748b;">· {len(events)}个</span>
        </div>
    """
    
    # 事件类型样式
    event_styles = {
        'new_hot': ('🔥', '#dc2626'),
        'cooled': ('❄️', '#3b82f6'),
        'rise': ('📈', '#16a34a'),
        'fall': ('📉', '#f59e0b'),
    }
    
    current_date = None
    
    for event in reversed(events):
        # 日期分隔
        event_date = datetime.fromtimestamp(event.timestamp).strftime("%m-%d")
        if event_date != current_date:
            current_date = event_date
            html += f'<div style="font-size: 10px; color: #94a3b8; margin: 8px 0 4px 0; padding-top: 4px; border-top: 1px dashed #e2e8f0;">{event_date}</div>'
        
        emoji, evt_color = event_styles.get(event.event_type, ('•', '#64748b'))
        change_sign = '+' if event.change_percent > 0 else ''
        
        html += f"""
        <div style="
            padding: 8px;
            margin-bottom: 6px;
            background: white;
            border-radius: 6px;
            border-left: 2px solid {evt_color};
            font-size: 11px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                <span style="color: #64748b; font-family: monospace; font-size: 10px;">{event.market_time}</span>
                <span>{emoji}</span>
            </div>
            <div style="font-weight: 500; color: #1e293b; margin-bottom: 2px;">{event.sector_name}</div>
            <div style="color: {evt_color}; font-size: 10px;">{change_sign}{event.change_percent:.1f}%</div>
        </div>
        """
    
    html += "</div>"
    return html


def _render_attention_changes(changes: List[Any]) -> str:
    """渲染注意力变化记录 - 带时间线"""
    from datetime import datetime
    
    html = """
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: #1e293b;">
            📈 个股重大变化记录
            <span style="font-size: 12px; color: #64748b; font-weight: normal; margin-left: 8px;">基于行情数据时间</span>
        </div>
    """
    
    if not changes:
        html += """
        <div style="color: #64748b; text-align: center; padding: 20px;">
            暂无变化记录<br>
            <span style="font-size: 12px;">等待数据更新...</span>
        </div>
        """
        html += "</div>"
        return html
    
    # 变化类型图标和颜色
    type_icons = {
        'new_hot': ('🔥', '#dc2626', '新热门'),
        'cooled': ('❄️', '#3b82f6', '冷却'),
        'strengthen': ('📈', '#16a34a', '加强'),
        'weaken': ('📉', '#f59e0b', '减弱')
    }
    
    # 按时间分组显示
    current_date = None
    
    for change in list(changes)[-20:]:  # 显示最近20条
        icon, color, label = type_icons.get(change.change_type, ('•', '#64748b', '变化'))
        
        # 格式化时间
        change_time = datetime.fromtimestamp(change.timestamp)
        time_str = change_time.strftime("%H:%M:%S")
        date_str = change_time.strftime("%m-%d")
        
        # 如果是新的一天，显示日期分隔
        if date_str != current_date:
            current_date = date_str
            html += f"""
            <div style="
                margin: 12px 0 8px 0;
                padding: 4px 0;
                border-bottom: 1px dashed #e2e8f0;
                font-size: 12px;
                color: #94a3b8;
                font-weight: 500;
            ">
                📅 {date_str}
            </div>
            """
        
        # 根据类型选择背景色
        bg_color = {
            'new_hot': '#fef2f2',
            'cooled': '#eff6ff',
            'strengthen': '#f0fdf4',
            'weaken': '#fffbeb'
        }.get(change.change_type, '#f8fafc')
        
        # 类型标签
        type_label = "板块" if change.item_type == 'sector' else "个股"
        
        html += f"""
        <div style="
            padding: 10px 12px;
            margin-bottom: 6px;
            background: {bg_color};
            border-radius: 8px;
            border-left: 3px solid {color};
            font-size: 13px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                        <span style="font-size: 11px; color: #64748b; font-family: monospace;">{time_str}</span>
                        <span style="font-size: 16px;">{icon}</span>
                        <span style="font-weight: 600; color: #1e293b;">{change.item_name or change.item_id}</span>
                        <span style="font-size: 10px; color: {color}; background: rgba(255,255,255,0.6); padding: 1px 6px; border-radius: 4px;">{label}</span>
                    </div>
                    <div style="font-size: 11px; color: #64748b; margin-left: 46px;">
                        {type_label} | {change.old_weight:.2f} → {change.new_weight:.2f} ({change.change_percent:+.1f}%)
                    </div>
                </div>
            </div>
        </div>
        """
    
    html += "</div>"
    return html


def _render_attention_shift_report(report: Dict[str, Any]) -> str:
    """渲染注意力转移报告"""
    html = """
    <div style="
        background: linear-gradient(135deg, #f0f9ff, #e0f2fe);
        border: 1px solid #7dd3fc;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: #0369a1;">🔄 注意力转移监测</div>
    """
    
    if not report.get('has_shift'):
        html += """
        <div style="color: #64748b; text-align: center; padding: 10px;">
            暂无注意力转移<br>
            <span style="font-size: 12px;">Top 3板块和Top 5股票未发生变化</span>
        </div>
        """
        html += "</div>"
        return html
    
    # 有转移时显示黄色背景
    html = """
    <div style="
        background: linear-gradient(135deg, #fef3c7, #fde68a);
        border: 1px solid #f59e0b;
        border-radius: 12px;
        padding: 20px;
        margin-top: 16px;
    ">
        <div style="font-weight: 600; margin-bottom: 16px; color: #92400e;">🔄 注意力转移 detected</div>
    """
    
    # 板块转移
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
    
    # 个股转移
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


def _initialize_attention_system():
    """初始化注意力系统"""
    try:
        from ..attention_config import load_config
        from ..attention_integration import initialize_attention_system
        
        config = load_config()
        if config.enabled:
            attention_system = initialize_attention_system(config)
            toast("✅ 注意力系统初始化成功！", color="success")
            # 刷新页面
            run_js("setTimeout(() => window.location.reload(), 1000)")
        else:
            toast("⚠️ 注意力系统被禁用", color="warning")
    except Exception as e:
        toast(f"❌ 初始化失败: {e}", color="error")


async def render_attention_admin(ctx: dict):
    """渲染注意力系统管理页面"""
    
    # 检查注意力系统是否已初始化
    attention_initialized = _is_attention_initialized()
    
    # 获取初始数据
    report = _get_attention_report()
    strategy_stats = _get_strategy_stats()
    experiment_info = _get_experiment_info()
    
    global_attention = report.get('global_attention', 0)
    freq_summary = report.get('frequency_summary', {})
    dual_summary = report.get('dual_engine_summary', {})
    processed = report.get('processed_snapshots', 0)
    avg_latency = report.get('avg_latency_ms', 0)
    
    with use_scope("attention_header"):
        put_html("<h2>👁️ 注意力调度系统</h2>")
        
        # 如果注意力系统未初始化，显示启动按钮
        if not attention_initialized:
            put_html("""
            <div style="margin-bottom:14px;padding:16px;border-radius:10px;
                        background:linear-gradient(135deg,#fef3c7,#fde68a);
                        border:1px solid #f59e0b;color:#92400e;font-size:14px;">
                <strong>⚠️ 注意力系统未启动</strong><br>
                当前 naja 启动时未启用注意力系统。点击下方按钮手动启动。
            </div>
            """)
            put_button("🚀 启动注意力系统", onclick=lambda: _initialize_attention_system(), color="warning")
            put_text("")
        
        # 实验模式横幅
        if experiment_info.get('active'):
            exp_ds = experiment_info.get('datasource_id', '未知')
            put_html(f"""
            <div style="margin-bottom:14px;padding:12px 14px;border-radius:10px;
                        background:linear-gradient(135deg,#dbeafe,#bfdbfe);
                        border:1px solid #93c5fd;color:#1e40af;font-size:13px;">
                <strong>🧪 实验模式运行中</strong><br>
                数据源: {exp_ds} | 策略数: {experiment_info.get('strategy_count', 0)}
            </div>
            """)
        
        try:
            render_help_collapse("attention")
        except Exception:
            pass
        
        # 控制按钮
        put_row([
            put_button("🔄 刷新", onclick=lambda: _do_refresh(), small=True),
            put_button("⏸️ 暂停刷新", onclick=lambda: _toggle_refresh(), small=True),
        ], size="auto")
        
        put_text("")
    
    # 主要指标卡片
    with use_scope("attention_metrics"):
        put_html(_render_global_attention_card(global_attention))
        
        put_row([
            put_column([
                put_html("<b>系统状态</b>"),
                put_text(f"状态: {'🟢 运行中' if report.get('status') == 'running' else '🔴 已停止'}"),
                put_text(f"处理快照: {processed}"),
                put_text(f"平均延迟: {avg_latency:.2f} ms"),
            ]),
            put_column([
                put_html("<b>策略概览</b>"),
                put_text(f"总策略: {strategy_stats.get('total_strategies', 0)}"),
                put_text(f"活跃策略: {strategy_stats.get('active_strategies', 0)}"),
                put_text(f"总信号: {strategy_stats.get('total_signals_generated', 0)}"),
            ]),
        ], size="1fr 1fr")
    
    put_text("")
    
    # 频率分布和策略状态
    with use_scope("attention_details"):
        put_row([
            put_html(_render_frequency_distribution(freq_summary)),
            put_html(_render_strategy_status(strategy_stats)),
        ], size="1fr 1fr")
    
    # 双引擎状态
    with use_scope("attention_dual_engine"):
        put_html(_render_dual_engine_status(dual_summary))
    
    # 噪音过滤状态
    with use_scope("attention_noise_filter"):
        put_html(_render_noise_filter_status())
    
    # 板块注意力变化曲线（主视图）
    with use_scope("attention_sector_trends"):
        put_html(_render_sector_trends())
    
    # 注意力转移报告
    with use_scope("attention_shift"):
        shift_report = _get_attention_shift_report()
        put_html(_render_attention_shift_report(shift_report))
    
    # 热门板块和股票
    with use_scope("attention_hot"):
        hot_data = _get_hot_sectors_and_stocks()
        put_html(_render_hot_sectors_and_stocks(hot_data))
    
    # 板块热点切换时间线（多阈值对比）
    with use_scope("attention_sector_hotspot"):
        put_html(_render_multi_threshold_timeline())
    
    # 注意力变化动态
    with use_scope("attention_changes"):
        changes = _get_attention_changes()
        put_html(_render_attention_changes(changes))
    
    # 最近信号
    with use_scope("attention_signals"):
        manager = _get_strategy_manager()
        if manager:
            signals = manager.get_recent_signals(n=20)
            put_html(_render_recent_signals(signals))
    
    # 诊断按钮和管理按钮
    put_html("<hr>")
    put_row([
        put_button("🔍 运行诊断", onclick=lambda: _run_diagnostic(), small=True),
        put_button("🔇 噪音过滤管理", onclick=lambda: _manage_noise_filter(), small=True, color="info"),
    ], size="auto")
    
    # 启动自动刷新
    if _auto_refresh_enabled:
        _start_auto_refresh()


def _run_diagnostic():
    """运行诊断"""
    from .diagnostic import render_attention_diagnostic
    render_attention_diagnostic()


def _manage_noise_filter():
    """管理噪音过滤黑白名单"""
    from pywebio.output import popup, put_html, put_buttons, put_row, put_column
    from pywebio.input import input_group, input, textarea
    from naja_attention_system import get_noise_filter
    
    noise_filter = get_noise_filter()
    
    def refresh_popup():
        """刷新弹窗内容"""
        blacklist = list(noise_filter.config.blacklist)
        whitelist = list(noise_filter.config.whitelist)
        
        html = f"""
        <div style="padding: 16px;">
            <div style="margin-bottom: 20px;">
                <div style="font-weight: 600; color: #dc2626; margin-bottom: 8px;">⚫ 黑名单 ({len(blacklist)})</div>
                <div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">强制过滤的股票</div>
                <div style="display: flex; flex-wrap: wrap; gap: 6px; max-height: 100px; overflow-y: auto;">
                    {''.join([f'<span style="font-size: 11px; padding: 4px 8px; background: #fee2e2; color: #dc2626; border-radius: 4px;">{s}</span>' for s in blacklist]) if blacklist else '<span style="color: #94a3b8;">暂无</span>'}
                </div>
            </div>
            
            <div style="margin-bottom: 20px;">
                <div style="font-weight: 600; color: #16a34a; margin-bottom: 8px;">⚪ 白名单 ({len(whitelist)})</div>
                <div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">保护不被过滤的股票</div>
                <div style="display: flex; flex-wrap: wrap; gap: 6px; max-height: 100px; overflow-y: auto;">
                    {''.join([f'<span style="font-size: 11px; padding: 4px 8px; background: #dcfce7; color: #16a34a; border-radius: 4px;">{s}</span>' for s in whitelist]) if whitelist else '<span style="color: #94a3b8;">暂无</span>'}
                </div>
            </div>
            
            <div style="background: #f8fafc; padding: 12px; border-radius: 8px; font-size: 12px; color: #64748b;">
                <strong>当前过滤配置:</strong><br>
                • 最小金额: {noise_filter.config.min_amount:,.0f} 元<br>
                • 最小成交量: {noise_filter.config.min_volume:,.0f} 股<br>
                • 动态阈值: {'启用' if noise_filter.config.dynamic_threshold else '禁用'}<br>
                • B股过滤: {'启用' if noise_filter.config.filter_b_shares else '禁用'}
            </div>
        </div>
        """
        return html
    
    def add_to_blacklist():
        """添加到黑名单"""
        symbol = input("输入股票代码", placeholder="如: 200012", required=True)
        if symbol:
            noise_filter.add_to_blacklist(symbol.strip(), "手动添加")
            toast(f"已添加 {symbol} 到黑名单", color="success")
            popup.close()
            _manage_noise_filter()  # 重新打开
    
    def add_to_whitelist():
        """添加到白名单"""
        symbol = input("输入股票代码", placeholder="如: 000001", required=True)
        if symbol:
            noise_filter.add_to_whitelist(symbol.strip(), "手动添加")
            toast(f"已添加 {symbol} 到白名单", color="success")
            popup.close()
            _manage_noise_filter()  # 重新打开
    
    def remove_from_blacklist():
        """从黑名单移除"""
        symbol = input("输入股票代码", placeholder="如: 200012", required=True)
        if symbol:
            noise_filter.remove_from_blacklist(symbol.strip())
            toast(f"已从黑名单移除 {symbol}", color="success")
            popup.close()
            _manage_noise_filter()
    
    def remove_from_whitelist():
        """从白名单移除"""
        symbol = input("输入股票代码", placeholder="如: 000001", required=True)
        if symbol:
            noise_filter.remove_from_whitelist(symbol.strip())
            toast(f"已从白名单移除 {symbol}", color="success")
            popup.close()
            _manage_noise_filter()
    
    def reset_stats():
        """重置统计"""
        noise_filter.reset_stats()
        toast("统计已重置", color="success")
        popup.close()
        _manage_noise_filter()
    
    with popup("🔇 噪音过滤管理"):
        put_html(refresh_popup())
        
        put_row([
            put_buttons([
                {'label': '⚫ 添加黑名单', 'value': 'add_black', 'color': 'danger'},
                {'label': '⚪ 添加白名单', 'value': 'add_white', 'color': 'success'},
            ], onclick=lambda v: add_to_blacklist() if v == 'add_black' else add_to_whitelist()),
        ])
        
        put_row([
            put_buttons([
                {'label': '移除黑名单', 'value': 'remove_black', 'color': 'secondary'},
                {'label': '移除白名单', 'value': 'remove_white', 'color': 'secondary'},
            ], onclick=lambda v: remove_from_blacklist() if v == 'remove_black' else remove_from_whitelist()),
        ])
        
        put_buttons([
            {'label': '🔄 重置统计', 'value': 'reset', 'color': 'warning'},
            {'label': '❌ 关闭', 'value': 'close', 'color': 'secondary'},
        ], onclick=lambda v: reset_stats() if v == 'reset' else popup.close())


def _do_refresh():
    """手动刷新"""
    toast("正在刷新...", color="info")
    run_js("window.location.reload()")


def _toggle_refresh():
    """切换自动刷新"""
    global _auto_refresh_enabled
    _auto_refresh_enabled = not _auto_refresh_enabled
    
    if _auto_refresh_enabled:
        toast("自动刷新已启用", color="success")
        _start_auto_refresh()
    else:
        toast("自动刷新已暂停", color="warning")


def _start_auto_refresh():
    """启动自动刷新"""
    if not _auto_refresh_enabled:
        return
    
    async def refresh_loop():
        while _auto_refresh_enabled:
            try:
                # 更新数据
                report = _get_attention_report()
                strategy_stats = _get_strategy_stats()
                
                # 更新全局注意力显示
                global_attention = report.get('global_attention', 0)
                
                # 这里可以添加更多动态更新逻辑
                # 由于 PyWebIO 的限制，简单页面刷新是最可靠的方式
                
                await session.sleep(_refresh_interval)
            except Exception:
                break
    
    # 启动后台刷新任务 - 需要调用函数获取协程对象
    session.run_async(refresh_loop())
