"""
信号流模块 UI

提供实时信号流的展示和管理功能
"""

from datetime import datetime
from pywebio.output import use_scope

# 从策略模块导入信号处理工具
from .processor import get_signal_type, get_signal_detail, generate_expanded_content

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
    import json
    expanded_content_json = json.dumps(expanded_content, ensure_ascii=False)
    
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
        'expanded_content': expanded_content_json,
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
    '''.format(data=json.dumps(signal_data, ensure_ascii=False))
    
    ctx["put_html"](insert_script, scope="signal_stream")





def _resolve_datasource_name(datasource_id: str) -> str:
    if not datasource_id:
        return "-"
    try:
        from ..datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        ds = ds_mgr.get(datasource_id)
        if ds:
            return ds.name
    except Exception:
        pass
    return datasource_id


def _render_experiment_status_html() -> str:
    try:
        from ..strategy import get_strategy_manager
        mgr = get_strategy_manager()
        exp_info = mgr.get_experiment_info()
    except Exception:
        exp_info = {"active": False}

    if not exp_info.get("active"):
        return ""

    categories_text = "、".join(exp_info.get("categories", []))
    ds_name = exp_info.get("datasource_name") or _resolve_datasource_name(exp_info.get("datasource_id", ""))
    target_count = int(exp_info.get("target_count", 0))
    return f"""
    <div style="margin:0 0 12px 0;padding:12px 14px;border-radius:10px;
                background:linear-gradient(135deg,#fff3cd,#ffe8a1);
                border:1px solid #f5d37a;color:#7a5a00;font-size:13px;">
        <strong>🧪 实验模式已开启</strong><br>
        类别：{categories_text or "-"} ｜ 数据源：{ds_name} ｜ 策略数：{target_count}
    </div>
    """


def _render_signal_stream_content(ctx, limit: int = 20):
    """渲染实时信号流内容"""
    from .stream import get_signal_stream
    
    signal_stream = get_signal_stream()
    all_results = signal_stream.get_recent(limit=limit)
    
    # 按时间戳排序
    all_results.sort(key=lambda x: x.ts, reverse=True)

    exp_status_html = _render_experiment_status_html()
    if exp_status_html:
        ctx["put_html"](exp_status_html)

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
            
        icon, color, signal_label, importance = get_signal_type(r)
        detail = get_signal_detail(r)
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
        expanded_content = generate_expanded_content(r, detail)

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
        .json-popup-overlay {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 10000;
            justify-content: center;
            align-items: center;
        }}
        .json-popup-overlay.active {{
            display: flex;
        }}
        .json-popup-content {{
            background: #fff;
            border-radius: 8px;
            max-width: 80%;
            max-height: 80%;
            display: flex;
            flex-direction: column;
            box-shadow: 0 4px 24px rgba(0,0,0,0.2);
        }}
        .json-popup-header {{
            padding: 12px 16px;
            border-bottom: 1px solid #e0e0e0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #f5f7fa;
            border-radius: 8px 8px 0 0;
        }}
        .json-popup-title {{
            font-weight: 600;
            color: #333;
            font-size: 14px;
        }}
        .json-popup-close {{
            background: none;
            border: none;
            font-size: 20px;
            cursor: pointer;
            color: #666;
            padding: 0;
            line-height: 1;
        }}
        .json-popup-close:hover {{
            color: #333;
        }}
        .json-popup-body {{
            padding: 16px;
            overflow: auto;
            flex: 1;
        }}
        .json-popup-body pre {{
            margin: 0;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 12px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-wrap: break-word;
            background: #282c34;
            color: #abb2bf;
            padding: 12px;
            border-radius: 4px;
        }}
    </style>
    <div id="json-popup-overlay" class="json-popup-overlay" onclick="closeJsonPopup(event)">
        <div class="json-popup-content" onclick="event.stopPropagation()">
            <div class="json-popup-header">
                <span class="json-popup-title">📄 完整 JSON 数据</span>
                <button class="json-popup-close" onclick="closeJsonPopup()">&times;</button>
            </div>
            <div class="json-popup-body">
                <pre id="json-popup-content"></pre>
            </div>
        </div>
    </div>
    <script>
    function showSignalJsonPopup(jsonStr) {{
        var overlay = document.getElementById('json-popup-overlay');
        var content = document.getElementById('json-popup-content');
        try {{
            var obj = JSON.parse(jsonStr.replace(/\\\\n/g, '\\n').replace(/\\\\'/g, \"'\"));
            content.textContent = JSON.stringify(obj, null, 2);
        }} catch(e) {{
            content.textContent = jsonStr.replace(/\\\\n/g, '\\n').replace(/\\\\'/g, \"'\");
        }}
        overlay.classList.add('active');
    }}
    
    function closeJsonPopup(event) {{
        if (event && event.target !== event.currentTarget) {{
            return;
        }}
        var overlay = document.getElementById('json-popup-overlay');
        overlay.classList.remove('active');
    }}
    
    document.addEventListener('keydown', function(e) {{
        if (e.key === 'Escape') {{
            closeJsonPopup();
        }}
    }});
    
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
