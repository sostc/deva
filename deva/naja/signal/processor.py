"""信号处理模块

提供信号类型判断和详细信息生成功能，用于策略看板和信号流的显示

架构:
- parse_strategy_result(): 统一解析策略结果数据
- SIGNAL_REGISTRY: 信号类型注册表 (配置驱动)
- get_signal_type(): 使用注册表获取信号类型
- get_signal_detail(): 使用注册表获取信号详情
"""

import json
import re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, Callable


def parse_strategy_result(result) -> Dict[str, Any]:
    """统一解析策略结果
    
    解析顺序:
    1. 尝试从 output_full 获取
    2. 尝试解析 output_preview 的 JSON
    3. 使用正则提取关键字段
    
    Returns:
        标准化的 dict，包含:
        - signal_type: 信号类型字符串
        - raw: 原始解析数据
        - is_truncated: 是否为截断数据
        - strategy_name: 策略名称
    """
    output_full = result.output_full
    strategy_name = getattr(result, 'strategy_name', '')
    
    output = None
    is_truncated = False
    
    if output_full is None or (hasattr(output_full, 'empty') and output_full.empty):
        preview = result.output_preview or ""
        
        # 1. 尝试 JSON 解析
        try:
            output = json.loads(preview)
        except (json.JSONDecodeError, TypeError):
            output = None
        
        # 2. JSON 失败则正则提取
        if output is None or not output.get('signal_type'):
            signal_type_match = re.search(r'"signal_type"\s*:\s*"([^"]+)"', preview)
            signal_match = re.search(r'"signal"\s*:\s*"([^"]+)"', preview)
            signal_count_match = re.search(r'"signal_count"\s*:\s*(\d+)', preview)
            
            if signal_type_match or signal_match:
                is_truncated = True
                output = {
                    'signal_type': signal_type_match.group(1) if signal_type_match else signal_match.group(1),
                    'signal': signal_match.group(1) if signal_match else signal_type_match.group(1),
                    'signal_count': int(signal_count_match.group(1)) if signal_count_match else 0,
                }
                
                # 提取股票信息
                names = re.findall(r'"name"\s*:\s*"([^"]+)"', preview)
                codes = re.findall(r'"code"\s*:\s*"([^"]+)"', preview)
                if names:
                    output['extracted_names'] = names[:5]
                if codes:
                    output['extracted_codes'] = codes[:5]
    else:
        output = output_full
    
    if output is None:
        output = {}
    
    return {
        'signal_type': output.get('signal_type', output.get('signal', '')),
        'raw': output,
        'is_truncated': is_truncated,
        'strategy_name': strategy_name,
    }


# 信号类型注册表
# 格式: {
#     'signal_type': {
#         'icon': '图标',
#         'color': '#颜色',
#         'label': '显示名称',
#         'importance': 'critical|high|medium|low',
#         'detail_handler': 处理函数(可选)
#     }
# }
# 支持通配符: *pattern* 匹配任意字符

SIGNAL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # === 逆势/ contrarian ===
    'contrarian': {
        'icon': '🔴', 'color': '#dc3545', 'label': '逆势信号', 
        'importance': 'high', 'pattern': '*contrarian*'
    },
    'stock_contrarian': {
        'icon': '🔴', 'color': '#dc3545', 'label': '逆势选股',
        'importance': 'high'
    },
    'double_contrarian': {
        'icon': '🔴', 'color': '#dc3545', 'label': '双倍逆势',
        'importance': 'critical'
    },
    'strong_contrarian': {
        'icon': '🔴', 'color': '#dc3545', 'label': '强势逆势',
        'importance': 'high'
    },
    'industry_contrarian': {
        'icon': '🔴', 'color': '#dc3545', 'label': '行业逆势',
        'importance': 'high'
    },
    'block_contrarian': {
        'icon': '🔴', 'color': '#dc3545', 'label': '板块逆势',
        'importance': 'high'
    },
    
    # === 涨跌停 ===
    'limit': {
        'icon': '🚀', 'color': '#dc3545', 'label': '涨跌停',
        'importance': 'high', 'pattern': '*limit*'
    },
    'limit_up_retry': {
        'icon': '🎯', 'color': '#9c27b0', 'label': '涨停回马枪',
        'importance': 'high'
    },
    'morning_strong': {
        'icon': '🌅', 'color': '#dc3545', 'label': '早盘强势',
        'importance': 'high'
    },
    
    # === 突破 ===
    'breakthrough': {
        'icon': '💥', 'color': '#ffc107', 'label': '突破信号',
        'importance': 'high', 'pattern': '*breakthrough*'
    },
    'volume_breakout': {
        'icon': '🚀', 'color': '#dc3545', 'label': '放量突破',
        'importance': 'high'
    },
    
    # === 异动 ===
    'fast_anomaly': {
        'icon': '⚡', 'color': '#ff6600', 'label': '快速异动',
        'importance': 'high'
    },
    'anomaly': {
        'icon': '⚡', 'color': '#ff6600', 'label': '异动信号',
        'importance': 'high', 'pattern': '*anomaly*'
    },
    'block_anomaly': {
        'icon': '⚡', 'color': '#ff6600', 'label': '板块异动',
        'importance': 'high'
    },
    'industry_anomaly': {
        'icon': '⚡', 'color': '#ff6600', 'label': '行业异动',
        'importance': 'high'
    },
    'block_extreme': {
        'icon': '⚡', 'color': '#ff6600', 'label': '板块极端',
        'importance': 'high'
    },
    
    # === 回调/回踩 ===
    'pullback_buy': {
        'icon': '📉', 'color': '#17a2b8', 'label': '强势回调',
        'importance': 'medium'
    },
    
    # === 板块/行业 ===
    'block': {
        'icon': '📊', 'color': '#fd7e14', 'label': '板块信号',
        'importance': 'medium', 'pattern': '*block*'
    },
    'block_leader': {
        'icon': '👑', 'color': '#fd7e14', 'label': '板块龙头',
        'importance': 'high'
    },
    'block_rank': {
        'icon': '📈', 'color': '#fd7e14', 'label': '板块排行',
        'importance': 'medium'
    },
    'block_capital_flow': {
        'icon': '💰', 'color': '#fd7e14', 'label': '板块资金流',
        'importance': 'medium'
    },
    'block_rotation': {
        'icon': '🔄', 'color': '#fd7e14', 'label': '板块轮动',
        'importance': 'medium'
    },
    'hot_block_track': {
        'icon': '🔥', 'color': '#fd7e14', 'label': '热门板块追踪',
        'importance': 'medium'
    },
    
    # === 行业 ===
    'industry': {
        'icon': '🏭', 'color': '#6c757d', 'label': '行业信号',
        'importance': 'medium', 'pattern': '*industry*'
    },
    'industry_capital_flow': {
        'icon': '💰', 'color': '#6c757d', 'label': '行业资金流',
        'importance': 'medium'
    },
    'industry_rotation': {
        'icon': '🔄', 'color': '#6c757d', 'label': '行业轮动',
        'importance': 'medium'
    },
    
    # === 热门/热度 ===
    'hot': {
        'icon': '🔥', 'color': '#e83e8c', 'label': '热门信号',
        'importance': 'medium', 'pattern': '*hot*'
    },
    'turnover_rank': {
        'icon': '🔥', 'color': '#e83e8c', 'label': '换手排行',
        'importance': 'medium'
    },
    
    # === 市场气候/趋势 ===
    'trend_analysis': {
        'icon': '🌤️', 'color': '#20c997', 'label': '市场气候',
        'importance': 'low'
    },
    'market_strength': {
        'icon': '💪', 'color': '#20c997', 'label': '市场强度',
        'importance': 'low'
    },
    
    # === 监控类 ===
    'limit_monitor': {
        'icon': '👁️', 'color': '#6c757d', 'label': '涨跌停监控',
        'importance': 'low'
    },
}

# 信号类型缓存 (运行时)
_signal_cache: Dict[str, Dict[str, Any]] = {}


def _build_cache():
    """构建信号类型缓存，支持通配符匹配"""
    global _signal_cache
    
    # 添加特殊处理: river 策略
    _signal_cache['*river*'] = {
        'icon': '🌊', 'color': '#17a2b8', 'label': 'River信号', 
        'importance': 'medium', 'is_pattern': True
    }
    
    for signal_type, config in SIGNAL_REGISTRY.items():
        # 直接匹配
        _signal_cache[signal_type] = config
        
        # 处理 pattern 通配符
        pattern = config.get('pattern')
        if pattern:
            _signal_cache[pattern] = {**config, 'is_pattern': True}

_build_cache()


def _match_signal_type(signal_type: str) -> Dict[str, Any]:
    """匹配信号类型配置
    
    匹配优先级:
    1. 精确匹配
    2. 前缀匹配 (signal_type*)
    3. 通配符匹配 (*pattern*)
    """
    if signal_type in _signal_cache:
        return _signal_cache[signal_type]
    
    # 前缀匹配
    for key in _signal_cache:
        if key.endswith('*') and signal_type.startswith(key[:-1]):
            return _signal_cache[key]
    
    # 通配符匹配
    for key, config in _signal_cache.items():
        if config.get('is_pattern') and key.count('*') == 2:
            pattern = key.replace('*', '')
            if pattern in signal_type:
                return config
    
    # 默认配置
    return {
        'icon': '📌', 'color': '#6c757d', 'label': '普通信号',
        'importance': 'low'
    }


def get_signal_type(result) -> Tuple[str, str, str, str]:
    """获取信号类型
    
    Returns:
        (icon, color, label, importance)
    """
    parsed = parse_strategy_result(result)
    signal_type = parsed['signal_type']
    
    config = _match_signal_type(signal_type)
    
    return (
        config.get('icon', '📌'),
        config.get('color', '#6c757d'),
        config.get('label', '普通信号'),
        config.get('importance', 'low')
    )


def get_signal_detail(result) -> Dict[str, Any]:
    """获取信号详细信息
    
    Returns:
        {
            'summary': str,      # 摘要描述
            'highlights': list,  # 关键亮点列表
            'extra_info': str    # 额外信息
        }
    """
    parsed = parse_strategy_result(result)
    signal_type = parsed['signal_type']
    raw = parsed['raw']
    is_truncated = parsed['is_truncated']
    
    detail = {
        'summary': '',
        'highlights': [],
        'extra_info': ''
    }
    
    if not isinstance(raw, dict):
        preview = result.output_preview if hasattr(result, 'output_preview') else ''
        detail['summary'] = preview[:80] if preview else '无数据'
        return detail
    
    signals = raw.get('signals', [])
    signal_count = raw.get('signal_count', len(signals) if signals else 0)
    
    # 通用字段提取
    extracted_names = raw.get('extracted_names', [])
    extracted_codes = raw.get('extracted_codes', [])
    
    # 根据信号类型生成详情
    if signal_type in ['fast_anomaly', 'block_anomaly', 'industry_anomaly', 'anomaly']:
        detail['summary'] = _handle_anomaly_signal(raw, signal_count, is_truncated, extracted_names, extracted_codes)
        
    elif signal_type == 'volume_breakout':
        detail['summary'] = _handle_volume_breakout(raw, signal_count, is_truncated, extracted_names, extracted_codes)
        
    elif signal_type == 'trend_analysis' or signal_type == 'market_strength':
        detail['summary'] = _handle_trend_signal(raw, signal_count)
        
    elif 'contrarian' in signal_type:
        detail['summary'] = _handle_contrarian_signal(raw, signal_count)
        
    elif 'limit' in signal_type:
        detail['summary'] = _handle_limit_signal(raw)
        
    elif 'block' in signal_type or 'industry' in signal_type:
        detail['summary'] = _handle_block_signal(raw, signal_count, signals)
        
    elif is_truncated and extracted_names:
        # 截断数据的通用处理
        name = extracted_names[0]
        code = extracted_codes[0] if extracted_codes else ''
        detail['summary'] = f"{name}({code}) - {signal_count} 个信号"
        if len(extracted_names) > 1:
            detail['highlights'] = [f"{n}({c})" for n, c in zip(extracted_names[1:], extracted_codes[1:])]
    else:
        # 默认处理
        detail['summary'] = f"{signal_type} - {signal_count} 个信号"
        if signals and isinstance(signals[0], dict):
            s = signals[0]
            name = s.get('name', '')
            code = s.get('code', '')
            if name:
                detail['summary'] = f"{name}({code})"
    
    return detail


def _handle_anomaly_signal(raw: dict, signal_count: int, is_truncated: bool, 
                           names: list, codes: list) -> str:
    """处理异动类信号"""
    if is_truncated and names:
        name = names[0]
        code = codes[0] if codes else ''
        summary = f"⚡ 异动信号: {name}({code})"
        if signal_count > 1:
            summary += f" 等{signal_count}只"
        return summary
    
    signals = raw.get('signals', [])
    if signals and isinstance(signals[0], dict):
        s = signals[0]
        name = s.get('name', '')
        code = s.get('code', '')
        p_change = s.get('p_change', 0)
        score = s.get('score', 0)
        
        summary = f"⚡ 异动: {name}({code}) 涨跌幅 {p_change:+.2f}%"
        if score:
            summary += f" 评分 {score:.0f}"
    else:
        summary = f"⚡ 异动信号: {signal_count} 个"
    
    return summary


def _handle_volume_breakout(raw: dict, signal_count: int, is_truncated: bool,
                            names: list, codes: list) -> str:
    """处理放量突破信号"""
    if is_truncated and names:
        name = names[0]
        code = codes[0] if codes else ''
        return f"🚀 放量突破: {name}({code})"
    
    signals = raw.get('signals', [])
    if signals and isinstance(signals[0], dict):
        s = signals[0]
        name = s.get('name', '')
        code = s.get('code', '')
        prob_up = s.get('prob_up', 0)
        
        summary = f"🚀 放量突破: {name}({code})"
        if prob_up:
            summary += f" 上攻概率 {prob_up*100:.1f}%"
    else:
        summary = f"🚀 放量突破: {signal_count} 个信号"
    
    return summary


def _handle_trend_signal(raw: dict, signal_count: int) -> str:
    """处理市场气候/趋势信号"""
    up_count = raw.get('up_count', 0)
    down_count = raw.get('down_count', 0)
    
    return f"🌤️ 市场气候: {signal_count} 个信号 (上涨{up_count}/下跌{down_count})"


def _handle_contrarian_signal(raw: dict, signal_count: int) -> str:
    """处理逆势信号"""
    stocks = raw.get('contrarian_stocks', raw.get('stocks', []))
    
    if stocks:
        first = stocks[0] if isinstance(stocks[0], str) else stocks[0].get('name', '')
        summary = f"🔴 逆势信号: {first}"
        if len(stocks) > 1:
            summary += f" 等{len(stocks)}只"
    else:
        summary = f"🔴 逆势信号: {signal_count} 个"
    
    return summary


def _handle_limit_signal(raw: dict) -> str:
    """处理涨跌停信号"""
    up_count = raw.get('up_limit_count', 0)
    down_count = raw.get('down_limit_count', 0)
    
    if up_count and down_count:
        return f"🚀 涨跌停: 涨停{up_count} / 跌停{down_count}"
    elif up_count:
        return f"🚀 涨停: {up_count} 只"
    else:
        return f"🔻 跌停: {down_count} 只"


def _handle_block_signal(raw: dict, signal_count: int, signals: list) -> str:
    """处理板块/行业信号"""
    if signals and isinstance(signals[0], dict):
        block = signals[0].get('blockname', signals[0].get('industry', ''))
        if block:
            return f"📊 {block}: {signal_count} 个信号"
    
    return f"📊 板块信号: {signal_count} 个"


def generate_expanded_content(result, detail: dict) -> str:
    """生成展开的详细内容 HTML"""
    output_full = getattr(result, 'output_full', None)
    
    if output_full is not None and isinstance(output_full, dict):
        raw = output_full
    else:
        parsed = parse_strategy_result(result)
        raw = parsed['raw']
    
    if not isinstance(raw, dict):
        return "<pre>" + json.dumps(raw, ensure_ascii=False, indent=2) + "</pre>"
    
    html_content = raw.get('html', '')
    
    if html_content:
        return html_content
    else:
        html = '<div style="font-size:12px;">'
        
        signals = raw.get('signals', [])
        if signals and isinstance(signals[0], dict):
            html += '<table style="width:100%;border-collapse:collapse;">'
            html += '<tr style="background:#f8f9fa;"><th style="padding:4px;border:1px solid #dee2e6;">股票</th>'
            html += '<th style="padding:4px;border:1px solid #dee2e6;">代码</th>'
            html += '<th style="padding:4px;border:1px solid #dee2e6;">涨跌幅</th>'
            html += '<th style="padding:4px;border:1px solid #dee2e6;">评分</th></tr>'
            
            for s in signals:
                name = s.get('name', '-')
                code = s.get('code', '-')
                p_change = s.get('p_change', 0)
                score = s.get('score', 0)
                
                html += '<tr><td style="padding:4px;border:1px solid #dee2e6;">' + str(name) + '</td>'
                html += '<td style="padding:4px;border:1px solid #dee2e6;">' + str(code) + '</td>'
                html += '<td style="padding:4px;border:1px solid #dee2e6;">' + ('%+.2f' % p_change) + '%</td>'
                html += '<td style="padding:4px;border:1px solid #dee2e6;">%d</td></tr>' % score
            
            html += '</table>'
        
        return html + '</div>'


def generate_signal_html(result) -> str:
    """生成信号卡片 HTML (保留兼容性)"""
    icon, color, label, importance = get_signal_type(result)
    
    importance_styles = {
        'critical': 'border: 2px solid #dc3545;',
        'high': 'border: 2px solid #ffc107;',
        'medium': 'border: 1px solid #17a2b8;',
        'low': 'border: 1px solid #dee2e6;',
    }
    
    bg_styles = {
        'critical': 'background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);',
        'high': 'background: linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%);',
        'medium': 'background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);',
        'low': 'background: #f8f9fa;',
    }
    
    border_width = '2px' if importance in ['critical', 'high'] else '1px'
    
    return {
        'importance': importance,
        'border_width': border_width,
        'bg_style': bg_styles.get(importance, bg_styles['low']),
        'importance_style': importance_styles.get(importance, importance_styles['low']),
    }
