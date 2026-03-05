"""信号处理工具

提供信号类型判断和详细信息生成功能，用于策略看板和信号流的显示
"""

from datetime import datetime


def get_signal_type(result) -> tuple:
    """根据结果判断信号类型和重要性"""
    output_full = result.output_full
    if output_full is None or (hasattr(output_full, 'empty') and output_full.empty):
        output = {}
    else:
        output = output_full
    if isinstance(output, dict):
        signal_type = output.get('signal_type', '')
        
        if 'contrarian' in signal_type or '逆势' in result.strategy_name:
            importance = 'high'
            stocks = output.get('contrarian_stocks', [])
            if stocks and len(stocks) >= 3:
                importance = 'critical'
            return ('🔴', '#dc3545', '逆势信号', importance)
        
        elif 'limit' in signal_type or '涨跌停' in result.strategy_name:
            up = output.get('up_limit_count', 0)
            down = output.get('down_limit_count', 0)
            importance = 'high' if up > 5 or down > 5 else 'medium'
            return ('🚀', '#dc3545', '涨跌停', importance)
        
        elif 'breakthrough' in signal_type or '突破' in result.strategy_name:
            return ('💥', '#ffc107', '突破信号', 'high')
        
        elif signal_type == 'volume_breakout':
            signals = output.get('signals', [])
            importance = 'critical' if len(signals) >= 5 else 'high'
            return ('🚀', '#dc3545', '放量突破', importance)
        
        elif signal_type == 'block_leader':
            leaders = output.get('leaders', [])
            importance = 'high' if len(leaders) >= 3 else 'medium'
            return ('👑', '#fd7e14', '板块龙头', importance)
        
        elif signal_type == 'pullback_buy':
            signals = output.get('signals', [])
            importance = 'high' if len(signals) >= 3 else 'medium'
            return ('📉', '#17a2b8', '强势回调', importance)
        
        elif signal_type == 'limit_up_retry':
            signals = output.get('signals', [])
            importance = 'critical' if len(signals) >= 5 else 'high'
            return ('🎯', '#9c27b0', '涨停回马枪', importance)
        
        elif signal_type == 'morning_strong':
            signals = output.get('signals', [])
            importance = 'high' if len(signals) >= 5 else 'medium'
            return ('🌅', '#dc3545', '早盘强势', importance)
        
        elif 'anomaly' in signal_type or '异动' in result.strategy_name:
            signals = output.get('signals', [])
            importance = 'high' if len(signals) >= 3 else 'medium'
            return ('⚡', '#fd7e14', '异动信号', importance)
        
        elif 'block' in signal_type or '板块' in result.strategy_name:
            return ('📊', '#17a2b8', '板块信号', 'low')
        
        elif 'industry' in signal_type or '行业' in result.strategy_name:
            return ('🏭', '#6f42c1', '行业信号', 'low')
        
        elif 'hot' in signal_type or '热门' in result.strategy_name:
            return ('🔥', '#e83e8c', '热门信号', 'medium')
        
        else:
            return ('📈', '#28a745', '普通信号', 'low')
    
    return ('📄', '#6c757d', '数据', 'low')


def get_signal_detail(result) -> dict:
    """获取信号详细信息"""
    output_full = result.output_full
    if output_full is None or (hasattr(output_full, 'empty') and output_full.empty):
        output = {}
    else:
        output = output_full
    detail = {
        'summary': '',
        'highlights': [],
        'extra_info': ''
    }
    
    if not isinstance(output, dict):
        detail['summary'] = result.output_preview[:80]
        return detail
    
    signal_type = output.get('signal_type', '')
    
    if signal_type == 'market_strength':
        strength = output.get('strength', 0)
        up_count = output.get('up_count', 0)
        down_count = output.get('down_count', 0)
        limit_up = output.get('limit_up_count', 0)
        detail['summary'] = f"市场强度: {strength:.1f}%"
        detail['highlights'] = [f"📈 上涨: {up_count}", f"📉 下跌: {down_count}", f"🚀 涨停: {limit_up}"]
    
    elif signal_type == 'limit_monitor':
        up = output.get('limit_up_count', 0) or output.get('up_limit_count', 0)
        down = output.get('limit_down_count', 0) or output.get('down_limit_count', 0)
        up_stocks = output.get('limit_up_stocks', []) or output.get('up_limit', [])
        down_stocks = output.get('limit_down_stocks', []) or output.get('down_limit', [])
        detail['summary'] = f"涨停 {up} | 跌停 {down}"
        if up_stocks:
            names = [s.get('name', '')[:4] for s in up_stocks[:3]]
            detail['highlights'] = [f"🔴 {name}" for name in names]
        if down_stocks:
            names = [s.get('name', '')[:4] for s in down_stocks[:2]]
            detail['highlights'].extend([f"🟢 {name}" for name in names])
    
    elif signal_type == 'block_rank':
        top_up = output.get('top10_up', [])
        top_down = output.get('top10_down', [])
        if top_up:
            t = top_up[0]
            detail['summary'] = f"领涨: {t.get('block', '')} +{t.get('avg_p_change', 0):.2f}%"
            detail['highlights'] = [f"📈 {b.get('block', '')} +{b.get('avg_p_change', 0):.2f}%" for b in top_up[:3]]
        if top_down:
            detail['highlights'].extend([f"📉 {b.get('block', '')} {b.get('avg_p_change', 0):.2f}%" for b in top_down[:2]])
    
    elif signal_type == 'block_anomaly':
        signals = output.get('signals', [])
        if signals:
            s = signals[0]
            direction = '📈' if s.get('direction') == 'up' else '📉'
            detail['summary'] = f"{s.get('block', '')} {direction} {s.get('change', 0):+.2f}%"
            detail['highlights'] = [f"变化: {s.get('change', 0):+.2f}%", f"当前: {s.get('avg_p_change', 0):.2f}%", f"股票数: {s.get('stock_count', 0)}"]
    
    elif signal_type == 'stock_contrarian':
        stocks = output.get('contrarian_stocks', [])
        market_strength = output.get('market_strength', 0)
        if stocks:
            s = stocks[0]
            detail['summary'] = f"逆势: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [f"成交额: {s.get('turnover_yi', 0):.2f}亿", f"逆势度: {s.get('contrarian_degree', 0):.2f}%"]
            detail['extra_info'] = f"市场强度: {market_strength:.1f}%"
        if len(stocks) > 1:
            detail['highlights'].append(f"共 {len(stocks)} 只逆势股")
    
    elif signal_type == 'double_contrarian':
        stocks = output.get('double_contrarian', [])
        if stocks:
            s = stocks[0]
            detail['summary'] = f"双重逆势: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [f"板块: {s.get('block', '')}", f"板块涨幅: {s.get('block_avg_p', 0):.2f}%", f"双重逆势度: {s.get('double_contrarian_degree', 0):.2f}%"]
    
    elif signal_type == 'fast_anomaly':
        stocks = output.get('anomaly_stocks', [])
        if stocks:
            s = stocks[0]
            detail['summary'] = f"异动: {s.get('name', '')} 得分 {s.get('score', 0):.0f}"
            detail['highlights'] = [f"涨幅: {s.get('p_change', 0):.2f}%", f"量比: {s.get('volume_ratio', 0):.2f}", f"速度: {s.get('speed', 0):.2f}%"]
    
    elif signal_type == 'strong_contrarian':
        stocks = output.get('breakthrough_stocks', [])
        if stocks:
            s = stocks[0]
            detail['summary'] = f"突破: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [f"加速: +{s.get('acceleration', 0):.2f}%", f"成交额: {s.get('turnover_yi', 0):.2f}亿"]
    
    elif signal_type == 'block_capital_flow':
        inflow = output.get('top_inflow', [])
        outflow = output.get('top_outflow', [])
        if inflow:
            t = inflow[0]
            detail['summary'] = f"资金流入: {t.get('block', '')} {t.get('turnover_yi', 0):.2f}亿"
            detail['highlights'] = [f"💰 {b.get('block', '')} {b.get('turnover_yi', 0):.2f}亿" for b in inflow[:3]]
    
    elif 'industry' in signal_type:
        if signal_type == 'industry_rank':
            top_up = output.get('top10_up', [])
            if top_up:
                t = top_up[0]
                detail['summary'] = f"领涨行业: {t.get('industry', '')} +{t.get('avg_p_change', 0):.2f}%"
                detail['highlights'] = [f"📈 {b.get('industry', '')} +{b.get('avg_p_change', 0):.2f}%" for b in top_up[:3]]
        elif signal_type == 'industry_contrarian':
            industries = output.get('contrarian_industries', [])
            if industries:
                t = industries[0]
                detail['summary'] = f"逆势行业: {t.get('industry', '')} +{t.get('avg_p_change', 0):.2f}%"
                detail['highlights'] = [f"逆势度: {t.get('contrarian_degree', 0):.2f}%"]
        elif signal_type == 'industry_capital_flow':
            inflow = output.get('top_inflow', [])
            if inflow:
                t = inflow[0]
                detail['summary'] = f"行业资金流入: {t.get('industry', '')} {t.get('turnover_yi', 0):.2f}亿"
                detail['highlights'] = [f"💰 {b.get('industry', '')} {b.get('turnover_yi', 0):.2f}亿" for b in inflow[:3]]
        elif signal_type == 'industry_anomaly':
            signals = output.get('signals', [])
            if signals:
                s = signals[0]
                detail['summary'] = f"行业异动: {s.get('industry', '')} {s.get('change', 0):+.2f}%"
                detail['highlights'] = [f"变化: {s.get('change', 0):+.2f}%"]
        elif signal_type == 'industry_rotation':
            strong = output.get('strong_industries', [])
            rotation = output.get('rotation_signals', [])
            if strong:
                detail['summary'] = f"强势行业: {strong[0] if strong else ''}"
            if rotation:
                detail['highlights'] = rotation[:3]
    
    elif signal_type == 'block_contrarian':
        blocks = output.get('contrarian_blocks', [])
        if blocks:
            t = blocks[0]
            detail['summary'] = f"逆势板块: {t.get('block', '')} +{t.get('avg_p_change', 0):.2f}%"
            detail['highlights'] = [f"逆势度: {t.get('contrarian_degree', 0):.2f}%"]
    
    elif signal_type == 'block_rotation':
        strong = output.get('strong_blocks', [])
        rotation = output.get('rotation_signals', [])
        if strong:
            detail['summary'] = f"强势板块: {strong[0] if strong else ''}"
        if rotation:
            detail['highlights'] = rotation[:3]
    
    elif signal_type == 'hot_block_track':
        hot = output.get('hot_blocks', [])
        if hot:
            t = hot[0]
            detail['summary'] = f"热门板块: {t.get('block', '')} +{t.get('avg_p_change', 0):.2f}%"
            detail['highlights'] = [f"📈 {b.get('block', '')} +{b.get('avg_p_change', 0):.2f}%" for b in hot[:3]]
    
    elif signal_type == 'turnover_rank':
        total = output.get('total_turnover_yi', 0)
        hot = output.get('hot_stocks', [])
        concentration = output.get('concentration', 0)
        detail['summary'] = f"总成交额: {total:.1f}亿"
        if hot:
            detail['highlights'] = [f"🔥 {s.get('name', '')} {s.get('turnover_yi', 0):.1f}亿" for s in hot[:3]]
        detail['extra_info'] = f"集中度: {concentration:.1f}%"
    
    elif signal_type == 'trend_analysis':
        up = output.get('up_count', 0)
        down = output.get('down_count', 0)
        signals = output.get('signals', [])
        detail['summary'] = f"上涨趋势: {up} | 下跌趋势: {down}"
        if signals:
            detail['highlights'] = signals[:3]
    
    elif signal_type == 'volume_breakout':
        signals = output.get('signals', [])
        count = output.get('signal_count', 0)
        if signals:
            s = signals[0]
            detail['summary'] = f"🚀 放量突破: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [f"成交额: {s.get('turnover_yi', 0):.2f}亿", f"评分: {s.get('score', 0):.1f}"]
            if len(signals) > 1:
                detail['highlights'].append(f"共 {count} 只突破股")
    
    elif signal_type == 'block_leader':
        leaders = output.get('leaders', [])
        if leaders:
            s = leaders[0]
            detail['summary'] = f"👑 龙头: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [f"板块: {s.get('block', '')}", f"板块涨幅: +{s.get('block_avg', 0):.2f}%"]
            if len(leaders) > 1:
                detail['highlights'].append(f"共 {len(leaders)} 个龙头")
    
    elif signal_type == 'pullback_buy':
        signals = output.get('signals', [])
        count = output.get('signal_count', 0)
        if signals:
            s = signals[0]
            detail['summary'] = f"📉 回调: {s.get('name', '')} {s.get('p_change', 0):.2f}%"
            detail['highlights'] = [f"5日涨幅: +{s.get('change_5d', 0):.2f}%", f"成交额: {s.get('turnover_yi', 0):.2f}亿"]
            if len(signals) > 1:
                detail['highlights'].append(f"共 {count} 只回调股")
    
    elif signal_type == 'limit_up_retry':
        signals = output.get('signals', [])
        count = output.get('signal_count', 0)
        if signals:
            s = signals[0]
            detail['summary'] = f"🎯 回马枪: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [f"成交额: {s.get('turnover_yi', 0):.2f}亿", f"涨停次数: {s.get('limit_up_count', 0)}"]
            if len(signals) > 1:
                detail['highlights'].append(f"共 {count} 只回马枪")
    
    elif signal_type == 'morning_strong':
        signals = output.get('signals', [])
        count = output.get('signal_count', 0)
        current_time = output.get('current_time', '')
        if signals:
            s = signals[0]
            detail['summary'] = f"🌅 早盘强势: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [f"开盘涨幅: +{s.get('open_change', 0):.2f}%", f"评分: {s.get('score', 0):.1f}"]
            if len(signals) > 1:
                detail['highlights'].append(f"共 {count} 只强势股")
            detail['extra_info'] = f"时间: {current_time}"
    
    elif signal_type == 'block_extreme':
        top10 = output.get('top10', [])
        bottom10 = output.get('bottom10', [])
        if top10:
            t = top10[0]
            detail['summary'] = f"📈 领涨板块: {t.get('block', '')} +{t.get('avg_p_change', 0):.2f}%"
            detail['highlights'] = [f"📈 {b.get('block', '')} +{b.get('avg_p_change', 0):.2f}%" for b in top10[:3]]
        if bottom10:
            detail['highlights'].extend([f"📉 {b.get('block', '')} {b.get('avg_p_change', 0):.2f}%" for b in bottom10[:2]])
    
    if not detail['summary']:
        detail['summary'] = result.output_preview[:60]
    
    return detail


def generate_expanded_content(result, detail: dict) -> str:
    """生成展开后的详细内容"""
    import json
    
    output_full = result.output_full
    if output_full is None or (hasattr(output_full, 'empty') and output_full.empty):
        output = {}
    else:
        output = output_full
    time_full = datetime.fromtimestamp(result.ts).strftime("%Y-%m-%d %H:%M:%S")
    
    parts = []
    
    parts.append(f"""
    <div style="background:#fff;padding:10px;border-radius:6px;margin-bottom:8px;">
        <div style="font-size:12px;color:#666;margin-bottom:6px;">📅 执行时间: {time_full}</div>
        <div style="font-size:12px;color:#666;">⏱️ 处理耗时: {result.process_time_ms:.1f}ms</div>
    </div>
    """)
    
    if isinstance(output, dict) and 'html' in output:
        parts.append(f"""
        <div style="background:#fff;padding:10px;border-radius:6px;">
            {output['html']}
        </div>
        """)
    else:
        if detail.get('highlights'):
            highlights_html = "<br>".join([f"• {h}" for h in detail['highlights']])
            parts.append(f"""
            <div style="background:#fff;padding:10px;border-radius:6px;margin-bottom:8px;">
                <div style="font-size:12px;font-weight:600;color:#333;margin-bottom:6px;">📊 关键指标</div>
                <div style="font-size:11px;color:#666;line-height:1.6;">{highlights_html}</div>
            </div>
            """)
        
        if output is not None:
            try:
                if hasattr(output, 'empty') and not output.empty:
                    output_str = str(output)
                elif isinstance(output, dict) and output:
                    output_str = json.dumps(output, ensure_ascii=False, indent=2)
                else:
                    output_str = str(output)
                
                if len(output_str) > 1000:
                    output_str = output_str[:1000] + "..."
                
                parts.append(f"""
                <div style="background:#f8f9fa;padding:10px;border-radius:6px;">
                    <div style="font-size:12px;font-weight:600;color:#333;margin-bottom:6px;">📋 完整数据</div>
                    <pre style="font-size:10px;color:#666;white-space:pre-wrap;word-break:break-all;margin:0;">{output_str}</pre>
                </div>
                """)
            except Exception:
                pass
    
    return "".join(parts) if parts else "<div style='color:#999;font-size:12px;'>暂无详细信息</div>"


def generate_signal_html(result) -> str:
    """生成信号的HTML表示"""
    import json
    
    icon, color, signal_label, importance = get_signal_type(result)
    detail = get_signal_detail(result)
    time_str = datetime.fromtimestamp(result.ts).strftime("%H:%M:%S")
    
    if importance == 'critical':
        border_width = "4px"
        bg_style = f"background:linear-gradient(135deg,{color}11,{color}22);"
    elif importance == 'high':
        border_width = "3px"
        bg_style = f"background:linear-gradient(135deg,{color}08,{color}15);"
    else:
        border_width = "2px"
        bg_style = "background:#fff;"
    
    highlights_str = " | ".join(str(h) for h in detail['highlights'][:4]) if detail['highlights'] else ""
    expanded_content = generate_expanded_content(result, detail)
    expanded_content_escaped = json.dumps(expanded_content)
    
    signal_data = {
        'icon': icon,
        'color': color,
        'signal_label': signal_label,
        'strategy_name': result.strategy_name[:14],
        'time_str': time_str,
        'summary': detail['summary'],
        'highlights': highlights_str,
        'border_width': border_width,
        'bg_style': bg_style,
        'expanded_content': expanded_content_escaped,
        'importance': importance,
    }
    
    html = f"""
    <div class="signal-item" data-importance="{importance}" data-result-id="{result.id}" onclick="toggleSignalExpand(this)" style="display:flex;flex-direction:column;padding:0;margin:6px 0;{bg_style}
                    border-radius:10px;border-left:{border_width} solid {color};
                    box-shadow:0 2px 8px rgba(0,0,0,0.06);cursor:pointer;transition:all 0.2s ease;">
        <div class="signal-header" style="display:flex;align-items:stretch;">
            <div style="display:flex;align-items:center;justify-content:center;padding:0 12px;">
                <div style="font-size:24px;">{icon}</div>
            </div>
            <div style="flex:1;padding:10px 12px 10px 0;min-width:0;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span style="font-weight:600;color:#333;font-size:14px;">{result.strategy_name[:14]}</span>
                        <span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;
                                    background:{color}22;color:{color};">{signal_label}</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:6px;">
                        <span style="font-size:11px;color:#999;white-space:nowrap;">{time_str}</span>
                        <span class="expand-icon" style="font-size:10px;color:#999;transition:transform 0.2s;">▼</span>
                    </div>
                </div>
                <div style="font-size:13px;color:#333;font-weight:500;margin-bottom:2px;">
                    {detail['summary']}
                </div>
                {f"<div style='font-size:11px;color:#666;margin-top:4px;'>{highlights_str}</div>" if highlights_str else ""}
            </div>
        </div>
        <div class="signal-detail" style="display:none;padding:0 12px 12px 48px;">
            {expanded_content}
        </div>
    </div>
    """
    
    return html
