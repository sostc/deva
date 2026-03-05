"""
信号流模块 UI

提供实时信号流的展示和管理功能
"""

from datetime import datetime
from pywebio.output import use_scope

# 存储已显示的信号 ID
_shown_signal_ids = set()

# 自动刷新控制
_auto_refresh_enabled = True


def set_auto_refresh(enabled: bool):
    """设置自动刷新状态"""
    global _auto_refresh_enabled
    _auto_refresh_enabled = enabled


def is_auto_refresh_enabled() -> bool:
    """获取自动刷新状态"""
    return _auto_refresh_enabled


async def _auto_insert_new_signals(ctx: dict):
    """自动插入新信号的后台任务"""
    import asyncio
    from pywebio.exceptions import SessionClosedException
    
    await asyncio.sleep(3)
    
    # 记录上次查询的时间戳，用于增量查询
    last_query_time = None
    
    while True:
        # 增加刷新间隔到5秒
        await asyncio.sleep(5)
        
        if not is_auto_refresh_enabled():
            continue
        
        try:
            from .stream import get_signal_stream
            
            signal_stream = get_signal_stream()
            all_results = signal_stream.get_recent(limit=30)  # 获取最近30条信号
            
            # 按时间戳排序
            all_results.sort(key=lambda x: x.ts, reverse=True)
            
            # 只处理新信号（时间戳大于上次查询时间）
            if last_query_time:
                all_results = [r for r in all_results if r.ts > last_query_time]
            
            # 更新上次查询时间
            if all_results:
                last_query_time = all_results[0].ts
            
            global _shown_signal_ids
            new_signals = []
            for r in all_results:
                if r.id not in _shown_signal_ids and r.success:
                    new_signals.append(r)
                    _shown_signal_ids.add(r.id)
                    
                    # 限制存储的信号ID数量，防止内存泄漏
                    if len(_shown_signal_ids) > 150:
                        old_ids = list(_shown_signal_ids)[:50]
                        for oid in old_ids:
                            _shown_signal_ids.discard(oid)
            
            # 每次最多处理3个新信号，避免一次性插入过多DOM元素
            for r in new_signals[:3]:
                _insert_signal_item(ctx, r)
                # 稍微延迟，避免DOM操作过于集中
                await asyncio.sleep(0.1)
                
        except SessionClosedException:
            # 会话已关闭，退出循环
            break
        except Exception as e:
            # 记录异常但不中断循环
            import traceback
            traceback.print_exc()
            await asyncio.sleep(1)


def _insert_signal_item(ctx, result):
    """在信号流顶部插入单个信号"""
    import json
    
    icon, color, signal_label, importance = _get_signal_type(result)
    detail = _get_signal_detail(result)
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
    
    expanded_content = _generate_expanded_content(result, detail)
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
    
    # 构建JavaScript代码，注意转义大括号
    insert_script = '''
    <script>
    (function() {{
        var autoRefreshCb = document.getElementById('auto_refresh_checkbox');
        if (autoRefreshCb && !autoRefreshCb.checked) {{
            return;
        }}
        
        var container = document.getElementById('signal-stream-container');
        if (!container) return;
        
        var data = {data};
        
        // 使用文档片段减少重排
        var fragment = document.createDocumentFragment();
        
        var div = document.createElement('div');
        div.className = 'signal-item';
        div.setAttribute('data-importance', data.importance);
        div.style.cssText = 'display:flex;flex-direction:column;padding:0;margin:6px 0;' + data.bg_style + 'border-radius:10px;border-left:' + data.border_width + ' solid ' + data.color + ';box-shadow:0 2px 8px rgba(0,0,0,0.06);opacity:0;transform:translateY(-20px);transition:all 0.3s ease;cursor:pointer;';
        div.onclick = function() {{ toggleSignalExpand(this); }};
        
        div.innerHTML = '<div class="signal-header" style="display:flex;align-items:stretch;"><div style="display:flex;align-items:center;justify-content:center;padding:0 12px;"><div style="font-size:24px;">' + data.icon + '</div></div><div style="flex:1;padding:10px 12px 10px 0;min-width:0;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;"><div style="display:flex;align-items:center;gap:8px;"><span style="font-weight:600;color:#333;font-size:14px;">' + data.strategy_name + '</span><span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;background:' + data.color + '22;color:' + data.color + ';">' + data.signal_label + '</span></div><div style="display:flex;align-items:center;gap:6px;"><span style="font-size:11px;color:#999;white-space:nowrap;">' + data.time_str + '</span><span class="expand-icon" style="font-size:10px;color:#999;transition:transform 0.2s;">▼</span></div></div><div style="font-size:13px;color:#333;font-weight:500;margin-bottom:2px;">' + data.summary + '</div>' + (data.highlights ? '<div style="font-size:11px;color:#666;margin-top:4px;">' + data.highlights + '</div>' : '') + '</div></div><div class="signal-detail" style="display:none;padding:0 12px 12px 48px;">' + JSON.parse(data.expanded_content) + '</div>';
        
        var filterCb = document.querySelector('.signal-filter[value="' + data.importance + '"]');
        if (filterCb && !filterCb.checked) {{
            div.classList.add('hidden');
        }}
        
        fragment.appendChild(div);
        container.insertBefore(fragment, container.firstChild);
        
        setTimeout(function() {{
            div.style.opacity = '1';
            div.style.transform = 'translateY(0)';
        }}, 10);
        
        // 限制容器中的信号数量，避免过多DOM元素
        while (container.children.length > 15) {{
            var lastChild = container.lastChild;
            if (lastChild) {{
                container.removeChild(lastChild);
            }}
        }}
    }})();
    </script>
    '''.format(data=json.dumps(signal_data))
    
    ctx["put_html"](insert_script, scope="signal_stream")


def _get_signal_type(result) -> tuple:
    """根据结果判断信号类型和重要性"""
    output = result.output_full or {}
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


def _get_signal_detail(result) -> dict:
    """获取信号详细信息"""
    output = result.output_full or {}
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


def _generate_expanded_content(result, detail: dict) -> str:
    """生成展开后的详细内容"""
    import json
    
    output = result.output_full or {}
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
        
        if output:
            try:
                if isinstance(output, dict):
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


def _render_signal_stream_content(ctx, limit: int = 20):
    """渲染实时信号流内容"""
    from .stream import get_signal_stream
    
    signal_stream = get_signal_stream()
    all_results = signal_stream.get_recent(limit=limit)
    
    # 按时间戳排序
    all_results.sort(key=lambda x: x.ts, reverse=True)

    ctx["put_html"]("""
    <div style="margin:16px 0 12px 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
        <div style="font-size:15px;font-weight:600;color:#333;">🔥 实时信号流</div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
            <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                <input type="checkbox" class="signal-filter" value="critical" checked onchange="filterSignals()" style="cursor:pointer;">
                <span style="padding:2px 6px;background:#dc354522;color:#dc3545;border-radius:4px;">🔴 重要</span>
            </label>
            <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                <input type="checkbox" class="signal-filter" value="high" checked onchange="filterSignals()" style="cursor:pointer;">
                <span style="padding:2px 6px;background:#fd7e1422;color:#fd7e14;border-radius:4px;">🟠 关注</span>
            </label>
            <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                <input type="checkbox" class="signal-filter" value="medium" checked onchange="filterSignals()" style="cursor:pointer;">
                <span style="padding:2px 6px;background:#ffc10722;color:#ffc107;border-radius:4px;">🟡 中等</span>
            </label>
            <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                <input type="checkbox" class="signal-filter" value="low" checked onchange="filterSignals()" style="cursor:pointer;">
                <span style="padding:2px 6px;background:#17a2b822;color:#17a2b8;border-radius:4px;">🔵 普通</span>
            </label>
            <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;margin-left:12px;">
                <input type="checkbox" id="auto_refresh_checkbox" checked onchange="toggleAutoRefresh(this.checked)" style="cursor:pointer;">
                <span style="font-size:11px;color:#666;">🔄 自动刷新</span>
            </label>
        </div>
    </div>
    """)

    if not all_results:
        ctx["put_html"](
            '<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无信号</div>')
        return

    signals_html = []
    for r in all_results:
        if not r.success:
            continue
            
        icon, color, signal_label, importance = _get_signal_type(r)
        detail = _get_signal_detail(r)
        time_str = datetime.fromtimestamp(r.ts).strftime("%H:%M:%S")
        
        if importance == 'critical':
            border_width = "4px"
            bg_style = f"background:linear-gradient(135deg,{color}11,{color}22);"
        elif importance == 'high':
            border_width = "3px"
            bg_style = f"background:linear-gradient(135deg,{color}08,{color}15);"
        elif importance == 'medium':
            border_width = "2px"
            bg_style = f"background:linear-gradient(135deg,{color}05,{color}10);"
        else:
            border_width = "2px"
            bg_style = "background:#fff;"
        
        highlights_str = " | ".join(str(h) for h in detail['highlights'][:4]) if detail['highlights'] else ""
        expanded_content = _generate_expanded_content(r, detail)

        signals_html.append(f"""
        <div class="signal-item" data-importance="{importance}" data-result-id="{r.id}" onclick="toggleSignalExpand(this)" style="display:flex;flex-direction:column;padding:0;margin:6px 0;{bg_style}
                        border-radius:10px;border-left:{border_width} solid {color};
                        box-shadow:0 2px 8px rgba(0,0,0,0.06);cursor:pointer;transition:all 0.2s ease;">
            <div class="signal-header" style="display:flex;align-items:stretch;">
                <div style="display:flex;align-items:center;justify-content:center;padding:0 12px;">
                    <div style="font-size:24px;">{icon}</div>
                </div>
                <div style="flex:1;padding:10px 12px 10px 0;min-width:0;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <span style="font-weight:600;color:#333;font-size:14px;">{r.strategy_name[:14]}</span>
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
        """)

    signals_container = f"""
    <style>
        .signal-item:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,0.12) !important; }}
        .signal-item.expanded .expand-icon {{ transform: rotate(180deg); }}
        .signal-detail {{ animation: fadeIn 0.2s ease; }}
        .signal-item.hidden {{ display: none !important; }}
        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}
    </style>
    <script>
    function toggleSignalExpand(el) {{
        var detail = el.querySelector('.signal-detail');
        var isExpanded = detail.style.display !== 'none';
        
        document.querySelectorAll('.signal-item.expanded').forEach(function(item) {{
            if (item !== el) {{
                item.classList.remove('expanded');
                item.querySelector('.signal-detail').style.display = 'none';
            }}
        }});
        
        if (isExpanded) {{
            detail.style.display = 'none';
            el.classList.remove('expanded');
        }} else {{
            detail.style.display = 'block';
            el.classList.add('expanded');
        }}
    }}
    
    function filterSignals() {{
        var checkboxes = document.querySelectorAll('.signal-filter');
        var selected = {{}};
        
        checkboxes.forEach(function(cb) {{
            selected[cb.value] = cb.checked;
        }});
        
        var items = document.querySelectorAll('.signal-item');
        items.forEach(function(item) {{
            var importance = item.getAttribute('data-importance');
            if (selected[importance]) {{
                item.classList.remove('hidden');
            }} else {{
                item.classList.add('hidden');
            }}
        }});
    }}
    
    function toggleAutoRefresh(enabled) {{
        pywebio.run_async(function() {{
            pywebio.call('set_auto_refresh', [enabled]);
        }});
    }}
    </script>
    <div id="signal-stream-container" style="padding:4px;background:#f5f7fa;border-radius:12px;">
        {''.join(signals_html)}
    </div>
    """
    ctx["put_html"](signals_container)
    
    global _shown_signal_ids
    for r in all_results:
        _shown_signal_ids.add(r.id)


async def render_signal_page(ctx: dict):
    """渲染信号流页面"""
    from pywebio.session import run_async
    
    with use_scope("signal_stream", clear=True):
        _render_signal_stream_content(ctx, limit=20)
    
    run_async(_auto_insert_new_signals(ctx))