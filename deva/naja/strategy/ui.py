"""策略管理 UI"""

import json
from datetime import datetime

from pywebio.output import put_text, put_markdown, put_table, put_buttons, put_html, toast, popup, close_popup, put_code, put_collapse, put_row, use_scope, set_scope, clear
from pywebio.input import input_group, input, textarea, select, actions
from pywebio.session import run_async


DEFAULT_STRATEGY_CODE = '''# 策略处理函数
# 必须定义 process(data) 函数
# data 通常是 pandas DataFrame

def process(data):
    """
    策略执行主体函数
    
    参数:
        data: 输入数据 (通常为 pandas.DataFrame)
    
    返回:
        处理后的数据
    """
    import pandas as pd
    
    # 示例：直接返回原始数据
    return data
'''


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _render_status_badge(is_running: bool) -> str:
    if is_running:
        return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#e8f5e9;color:#2e7d32;">● 运行中</span>'
    return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#f5f5f5;color:#757575;">○ 已停止</span>'


def _render_detail_section(title: str) -> str:
    return f"""
    <div style="margin:20px 0 12px 0;padding-bottom:8px;border-bottom:2px solid #e0e0e0;">
        <span style="font-size:15px;font-weight:600;color:#333;">{title}</span>
    </div>
    """


def _render_strategy_diagram_section(ctx: dict, entry):
    """渲染策略详解图表部分"""
    diagram_info = getattr(entry._metadata, "diagram_info", {}) or {}

    if not diagram_info:
        return

    ctx["put_html"](_render_detail_section("📊 策略详解"))

    icon = diagram_info.get("icon", "📊")
    color = diagram_info.get("color", "#667eea")
    description = diagram_info.get("description", "")
    formula = diagram_info.get("formula", "")
    logic = diagram_info.get("logic", [])
    output = diagram_info.get("output", "")

    # 生成流程步骤 HTML
    logic_html = "".join([
        f'<div style="padding:4px 0;color:#555;font-size:12px;display:flex;align-items:center;gap:6px;">'
        f'<span style="background:{color};color:white;width:18px;height:18px;border-radius:50%;'
        f'display:flex;align-items:center;justify-content:center;font-size:10px;">{i+1}</span>{step}</div>'
        for i, step in enumerate(logic)
    ])

    ctx["put_html"](f"""
    <div style="background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);
                overflow:hidden;border:1px solid #eee;margin-bottom:15px;">
        <div style="background:linear-gradient(135deg,{color} 0%,{color}dd 100%);
                    padding:15px 20px;color:white;">
            <div style="display:flex;align-items:center;gap:12px;">
                <div style="font-size:28px;">{icon}</div>
                <div>
                    <div style="font-size:16px;font-weight:600;">{entry.name}</div>
                    <div style="font-size:12px;opacity:0.9;margin-top:3px;">{description}</div>
                </div>
            </div>
        </div>
        <div style="padding:20px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
                <div>
                    <div style="font-weight:600;color:#333;margin-bottom:10px;display:flex;align-items:center;gap:6px;">
                        <span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">公式</span>
                        计算逻辑
                    </div>
                    <div style="background:#f8f9fa;padding:12px;border-radius:8px;
                                font-family:monospace;font-size:12px;color:#555;border-left:3px solid {color};">
                        {formula}
                    </div>
                </div>
                <div>
                    <div style="font-weight:600;color:#333;margin-bottom:10px;display:flex;align-items:center;gap:6px;">
                        <span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">步骤</span>
                        处理流程
                    </div>
                    <div style="background:#f8f9fa;padding:12px;border-radius:8px;">
                        {logic_html}
                    </div>
                </div>
            </div>
            <div style="margin-top:15px;padding:12px;
                        background:linear-gradient(135deg,{color}11 0%,{color}22 100%);
                        border-radius:8px;border:1px dashed {color}44;">
                <div style="display:flex;align-items:center;gap:6px;color:#333;font-size:13px;">
                    <span style="font-size:16px;">📤</span>
                    <strong>输出：</strong>
                    <span style="color:#666;">{output}</span>
                </div>
            </div>
        </div>
    </div>
    """)


async def render_strategy_admin(ctx: dict):
    """渲染策略管理面板"""
    await ctx["init_naja_ui"]("策略管理")

    set_scope("strategy_content")
    _render_strategy_content(ctx)
    
    # 启动后台任务自动插入新信号
    run_async(_auto_insert_new_signals(ctx))


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
    
    await asyncio.sleep(3)  # 初始等待3秒
    
    while True:
        await asyncio.sleep(2)  # 每2秒检查一次新信号
        
        # 检查是否启用自动刷新
        if not is_auto_refresh_enabled():
            continue
        
        try:
            from . import get_strategy_manager
            from .result_store import get_result_store
            
            mgr = get_strategy_manager()
            store = get_result_store()
            entries = list(mgr.list_all())
            
            # 获取所有结果
            all_results = []
            for e in entries:
                results = store.get_recent(e.id, limit=5)
                all_results.extend(results)
            
            all_results.sort(key=lambda x: x.ts, reverse=True)
            
            # 找出新信号（未显示过的）
            global _shown_signal_ids
            new_signals = []
            for r in all_results:
                if r.id not in _shown_signal_ids and r.success:
                    new_signals.append(r)
                    _shown_signal_ids.add(r.id)
                    
                    # 限制缓存大小
                    if len(_shown_signal_ids) > 200:
                        # 移除最旧的一半
                        old_ids = list(_shown_signal_ids)[:100]
                        for oid in old_ids:
                            _shown_signal_ids.discard(oid)
            
            # 在顶部插入新信号
            for r in new_signals[:5]:  # 每次最多插入5条
                _insert_signal_item(ctx, r)
                
        except Exception:
            pass


def _insert_signal_item(ctx, result):
    """在信号流顶部插入单个信号"""
    import json
    
    icon, color, signal_label, importance = _get_signal_type(result)
    detail = _get_signal_detail(result)
    time_str = datetime.fromtimestamp(result.ts).strftime("%H:%M:%S")
    
    # 根据重要性设置样式
    if importance == 'critical':
        border_width = "4px"
        bg_style = f"background:linear-gradient(135deg,{color}11,{color}22);"
    elif importance == 'high':
        border_width = "3px"
        bg_style = f"background:linear-gradient(135deg,{color}08,{color}15);"
    else:
        border_width = "2px"
        bg_style = "background:#fff;"
    
    # 生成高亮信息
    highlights_str = " | ".join(detail['highlights'][:4]) if detail['highlights'] else ""
    
    # 生成展开后的详细内容
    expanded_content = _generate_expanded_content(result, detail)
    # 转义 JSON 字符串
    expanded_content_escaped = json.dumps(expanded_content)
    
    # 构建信号数据
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
    
    # 使用 JavaScript 在顶部插入
    insert_script = f"""
    <script>
    (function() {{
        // 检查自动刷新是否开启
        var autoRefreshCb = document.getElementById('auto_refresh_checkbox');
        if (autoRefreshCb && !autoRefreshCb.checked) {{
            return;  // 自动刷新已关闭，不插入新信号
        }}
        
        var container = document.getElementById('signal-stream-container');
        if (!container) return;
        
        var data = {json.dumps(signal_data)};
        
        var div = document.createElement('div');
        div.className = 'signal-item';
        div.setAttribute('data-importance', data.importance);
        div.style.cssText = 'display:flex;flex-direction:column;padding:0;margin:6px 0;' + data.bg_style + 'border-radius:10px;border-left:' + data.border_width + ' solid ' + data.color + ';box-shadow:0 2px 8px rgba(0,0,0,0.06);opacity:0;transform:translateY(-20px);transition:all 0.3s ease;cursor:pointer;';
        div.onclick = function() {{ toggleSignalExpand(this); }};
        
        div.innerHTML = '<div class="signal-header" style="display:flex;align-items:stretch;"><div style="display:flex;align-items:center;justify-content:center;padding:0 12px;"><div style="font-size:24px;">' + data.icon + '</div></div><div style="flex:1;padding:10px 12px 10px 0;min-width:0;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;"><div style="display:flex;align-items:center;gap:8px;"><span style="font-weight:600;color:#333;font-size:14px;">' + data.strategy_name + '</span><span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;background:' + data.color + '22;color:' + data.color + ';">' + data.signal_label + '</span></div><div style="display:flex;align-items:center;gap:6px;"><span style="font-size:11px;color:#999;white-space:nowrap;">' + data.time_str + '</span><span class="expand-icon" style="font-size:10px;color:#999;transition:transform 0.2s;">▼</span></div></div><div style="font-size:13px;color:#333;font-weight:500;margin-bottom:2px;">' + data.summary + '</div>' + (data.highlights ? '<div style="font-size:11px;color:#666;margin-top:4px;">' + data.highlights + '</div>' : '') + '</div></div><div class="signal-detail" style="display:none;padding:0 12px 12px 48px;">' + JSON.parse(data.expanded_content) + '</div>';
        
        // 检查当前筛选状态
        var filterCb = document.querySelector('.signal-filter[value="' + data.importance + '"]');
        if (filterCb && !filterCb.checked) {{
            div.classList.add('hidden');
        }}
        
        container.insertBefore(div, container.firstChild);
        
        // 触发动画
        setTimeout(function() {{
            div.style.opacity = '1';
            div.style.transform = 'translateY(0)';
        }}, 10);
        
        // 限制显示数量
        while (container.children.length > 20) {{
            container.removeChild(container.lastChild);
        }}
    }})();
    </script>
    """
    
    ctx["put_html"](insert_script, scope="signal_stream")


# 全局变量：当前选中的类别
_current_category = "全部"


def _get_all_categories(entries: list) -> list:
    """获取所有类别"""
    categories = set()
    for e in entries:
        cat = getattr(e._metadata, "category", "默认") or "默认"
        categories.add(cat)
    return sorted(list(categories))


def _render_strategy_content(ctx: dict):
    """渲染策略管理内容（支持局部刷新）"""
    from . import get_strategy_manager
    from .result_store import get_result_store
    from pywebio.output import clear

    global _current_category

    mgr = get_strategy_manager()
    store = get_result_store()

    entries = mgr.list_all()
    stats = mgr.get_stats()
    result_stats = store.get_stats()

    running_count = sum(1 for e in entries if e.is_running)
    error_count = sum(1 for e in entries if e._state.error_count > 0)

    clear("strategy_content")

    # 添加全局按钮样式
    ctx["put_html"]("""
    <style>
        /* 全局按钮样式 */
        .pywebio-btn {
            border-radius: 6px !important;
            font-size: 13px !important;
            font-weight: 500 !important;
            transition: all 0.2s ease !important;
            border: 1px solid transparent !important;
        }
        .pywebio-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        /* 主要按钮 - 淡蓝 */
        .btn-primary, .pywebio-btn-primary {
            background: #5c8dd6 !important;
            color: white !important;
            border-color: #4a7bc4 !important;
        }
        .btn-primary:hover {
            background: #4a7bc4 !important;
        }
        
        /* 成功按钮 - 淡绿 */
        .btn-success {
            background: #5cb85c !important;
            color: white !important;
            border-color: #4cae4c !important;
        }
        .btn-success:hover {
            background: #4cae4c !important;
        }
        
        /* 危险按钮 - 淡红 */
        .btn-danger {
            background: #d9534f !important;
            color: white !important;
            border-color: #c9302c !important;
        }
        .btn-danger:hover {
            background: #c9302c !important;
        }
        
        /* 警告按钮 - 淡橙 */
        .btn-warning {
            background: #f0ad4e !important;
            color: white !important;
            border-color: #ec971f !important;
        }
        .btn-warning:hover {
            background: #ec971f !important;
        }
        
        /* 信息按钮 - 淡青 */
        .btn-info {
            background: #5bc0de !important;
            color: white !important;
            border-color: #46b8da !important;
        }
        .btn-info:hover {
            background: #46b8da !important;
        }
        
        /* 默认按钮 - 浅灰 */
        .btn-default {
            background: #f8f9fa !important;
            color: #495057 !important;
            border-color: #dee2e6 !important;
        }
        .btn-default:hover {
            background: #e9ecef !important;
        }
        
        /* 按钮组样式 */
        .pywebio-btn-group {
            display: flex !important;
            flex-wrap: wrap !important;
            gap: 8px !important;
        }
        .pywebio-btn-group .pywebio-btn {
            margin: 0 !important;
        }
        
        /* 小按钮样式 */
        .pywebio-btn-sm {
            padding: 4px 12px !important;
            font-size: 12px !important;
        }
        
        /* 表格内按钮 */
        .pywebio-table .pywebio-btn {
            padding: 3px 10px !important;
            font-size: 12px !important;
        }
    </style>
    """, scope="strategy_content")

    ctx["put_html"](_render_strategy_stats_html(
        stats, running_count, error_count), scope="strategy_content")

    # 渲染类别 Tab
    categories = _get_all_categories(entries)
    _render_category_tabs(ctx, categories, entries, mgr)

    # 根据当前类别筛选策略
    if _current_category == "全部":
        filtered_entries = entries
    else:
        filtered_entries = [e for e in entries if getattr(e._metadata, "category", "默认") == _current_category]

    if filtered_entries:
        table_data = _build_table_data(ctx, filtered_entries, mgr)
        # 添加表格样式，限制行高
        ctx["put_html"]("""
        <style>
            .pywebio-table tbody tr { height: 48px; max-height: 48px; }
            .pywebio-table tbody td { vertical-align: middle; padding: 8px 12px; }
            .pywebio-table tbody td > div { max-height: 40px; overflow: hidden; }
        </style>
        """, scope="strategy_content")
        ctx["put_table"](table_data, header=["名称", "状态", "数据源", "简介",
                                             "最近数据", "操作"], scope="strategy_content")

        ctx["put_html"](
            '<div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">', scope="strategy_content")
        ctx["put_buttons"]([
            {"label": "➕ 创建策略", "value": "create", "color": "primary"},
            {"label": "▶️ 全部启动", "value": "start_all", "color": "success"},
            {"label": "⏹️ 全部停止", "value": "stop_all", "color": "danger"},
            {"label": "🔄 重载配置", "value": "reload_all", "color": "info"},
            {"label": "🔄 刷新结果", "value": "refresh_results", "color": "info"},
            {"label": "📜 执行历史", "value": "show_history", "color": "default"},
        ], onclick=lambda v, m=mgr, c=ctx: _handle_toolbar_action(v, m, c), group=True, scope="strategy_content")
        ctx["put_html"]('</div>', scope="strategy_content")
    else:
        ctx["put_html"](
            '<div style="padding:40px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无策略，点击下方按钮创建</div>', scope="strategy_content")
        ctx["put_buttons"]([{"label": "➕ 创建策略", "value": "create", "color": "primary"}],
                           onclick=lambda v, m=mgr, c=ctx: _create_strategy_dialog(m, c), scope="strategy_content")

    ctx["put_html"](
        "<hr style='margin:24px 0;border:none;border-top:1px solid #e0e0e0;'>", scope="strategy_content")

    ctx["put_html"](_render_result_stats_html(result_stats), scope="strategy_content")

    # 实时信号流 - 使用独立 scope 支持局部刷新
    with use_scope("signal_stream", clear=True):
        _render_signal_stream_content(ctx, entries, store)


def _render_category_tabs(ctx: dict, categories: list, entries: list, mgr):
    """渲染类别 Tab"""
    global _current_category

    # 构建Tab按钮
    tab_buttons = [{"label": f"📋 全部 ({len(entries)})", "value": "全部"}]
    
    for cat in categories:
        count = len([e for e in entries if getattr(e._metadata, "category", "默认") == cat])
        tab_buttons.append({"label": f"📁 {cat} ({count})", "value": cat})

    # 渲染 Tab 样式
    ctx["put_html"]("""
    <style>
        .category-tabs { margin-bottom: 16px; }
        .category-tabs .pywebio-btn-group { display: flex; flex-wrap: wrap; gap: 8px; }
        .category-tabs button { 
            border-radius: 20px !important; 
            padding: 6px 16px !important;
            font-size: 13px !important;
            transition: all 0.2s ease;
        }
        .category-tabs button:hover { transform: translateY(-1px); }
        .category-tabs button.active { 
            background: linear-gradient(135deg, #667eea, #764ba2) !important;
            color: white !important;
        }
    </style>
    <div class="category-tabs">
    """, scope="strategy_content")

    ctx["put_buttons"](tab_buttons, onclick=lambda v, c=ctx, m=mgr: _switch_category(v, c, m), scope="strategy_content")
    
    ctx["put_html"]("</div>", scope="strategy_content")


def _switch_category(category: str, ctx: dict, mgr):
    """切换类别"""
    global _current_category
    _current_category = category
    _render_strategy_content(ctx)


def _render_strategy_stats_html(stats: dict, running_count: int, error_count: int) -> str:
    return f"""
    <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:24px;">
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#667eea,#764ba2);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(102,126,234,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">总策略数</div>
            <div style="font-size:32px;font-weight:700;">{stats['total']}</div>
        </div>
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#11998e,#38ef7d);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(17,153,142,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">运行中</div>
            <div style="font-size:32px;font-weight:700;">{running_count}</div>
        </div>
        <div style="flex:1;min-width:140px;background:linear-gradient(135deg,#ff416c,#ff4b2b);padding:20px;border-radius:12px;color:#fff;box-shadow:0 4px 12px rgba(255,65,108,0.3);">
            <div style="font-size:13px;opacity:0.9;margin-bottom:4px;">错误数</div>
            <div style="font-size:32px;font-weight:700;">{error_count}</div>
        </div>
    </div>
    """


def _render_result_stats_html(result_stats: dict) -> str:
    success_rate = result_stats.get('success_rate', 0)
    rate_color = '#28a745' if success_rate > 0.9 else '#ffc107' if success_rate > 0.7 else '#dc3545'

    return f"""
    <div style="margin:16px 0 12px 0;font-size:15px;font-weight:600;color:#333;">📊 执行结果监控</div>
    <div style="display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap;">
        <div style="flex:1;min-width:100px;background:#fff;padding:16px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            <div style="font-size:12px;color:#666;margin-bottom:4px;">总执行次数</div>
            <div style="font-size:24px;font-weight:700;color:#333;">{result_stats.get('total_results', 0)}</div>
        </div>
        <div style="flex:1;min-width:100px;background:#fff;padding:16px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            <div style="font-size:12px;color:#666;margin-bottom:4px;">成功次数</div>
            <div style="font-size:24px;font-weight:700;color:#28a745;">{result_stats.get('total_success', 0)}</div>
        </div>
        <div style="flex:1;min-width:100px;background:#fff;padding:16px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            <div style="font-size:12px;color:#666;margin-bottom:4px;">失败次数</div>
            <div style="font-size:24px;font-weight:700;color:#dc3545;">{result_stats.get('total_failed', 0)}</div>
        </div>
        <div style="flex:1;min-width:100px;background:#fff;padding:16px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            <div style="font-size:12px;color:#666;margin-bottom:4px;">平均耗时</div>
            <div style="font-size:24px;font-weight:700;color:#17a2b8;">{result_stats.get('avg_process_time_ms', 0):.1f}ms</div>
        </div>
        <div style="flex:1;min-width:100px;background:#fff;padding:16px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            <div style="font-size:12px;color:#666;margin-bottom:4px;">成功率</div>
            <div style="font-size:24px;font-weight:700;color:{rate_color};">{success_rate*100:.1f}%</div>
        </div>
    </div>
    """


def _get_signal_type(result) -> tuple:
    """根据结果判断信号类型和重要性"""
    output = result.output_full or {}
    if isinstance(output, dict):
        signal_type = output.get('signal_type', '')
        
        # 高重要性信号 - 红色
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
        
        # === 选股策略 - 高重要性 ===
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
        
        # 中等重要性信号 - 橙色
        elif 'anomaly' in signal_type or '异动' in result.strategy_name:
            signals = output.get('signals', [])
            importance = 'high' if len(signals) >= 3 else 'medium'
            return ('⚡', '#fd7e14', '异动信号', importance)
        
        # 普通信号 - 蓝色/紫色
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
    
    # 市场强度
    if signal_type == 'market_strength':
        strength = output.get('strength', 0)
        status = output.get('status', '')
        up_count = output.get('up_count', 0)
        down_count = output.get('down_count', 0)
        limit_up = output.get('limit_up_count', 0)
        
        detail['summary'] = f"市场强度: {strength:.1f}%"
        detail['highlights'] = [
            f"📈 上涨: {up_count}",
            f"📉 下跌: {down_count}",
            f"🚀 涨停: {limit_up}"
        ]
        detail['extra_info'] = f"状态: {status}"
    
    # 涨跌停监控
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
    
    # 板块涨跌幅排行
    elif signal_type == 'block_rank':
        top_up = output.get('top10_up', [])
        top_down = output.get('top10_down', [])
        
        if top_up:
            t = top_up[0]
            detail['summary'] = f"领涨: {t.get('block', '')} +{t.get('avg_p_change', 0):.2f}%"
            detail['highlights'] = [f"📈 {b.get('block', '')} +{b.get('avg_p_change', 0):.2f}%" for b in top_up[:3]]
        if top_down:
            detail['highlights'].extend([f"📉 {b.get('block', '')} {b.get('avg_p_change', 0):.2f}%" for b in top_down[:2]])
    
    # 板块异动
    elif signal_type == 'block_anomaly':
        signals = output.get('signals', [])
        if signals:
            s = signals[0]
            direction = '📈' if s.get('direction') == 'up' else '📉'
            detail['summary'] = f"{s.get('block', '')} {direction} {s.get('change', 0):+.2f}%"
            detail['highlights'] = [
                f"变化: {s.get('change', 0):+.2f}%",
                f"当前: {s.get('avg_p_change', 0):.2f}%",
                f"股票数: {s.get('stock_count', 0)}"
            ]
    
    # 个股逆势上涨
    elif signal_type == 'stock_contrarian':
        stocks = output.get('contrarian_stocks', [])
        market_strength = output.get('market_strength', 0)
        
        if stocks:
            s = stocks[0]
            detail['summary'] = f"逆势: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [
                f"成交额: {s.get('turnover_yi', 0):.2f}亿",
                f"逆势度: {s.get('contrarian_degree', 0):.2f}%"
            ]
            detail['extra_info'] = f"市场强度: {market_strength:.1f}%"
        
        if len(stocks) > 1:
            detail['highlights'].append(f"共 {len(stocks)} 只逆势股")
    
    # 板块个股双重逆势
    elif signal_type == 'double_contrarian':
        stocks = output.get('double_contrarian', [])
        if stocks:
            s = stocks[0]
            detail['summary'] = f"双重逆势: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [
                f"板块: {s.get('block', '')}",
                f"板块涨幅: {s.get('block_avg_p', 0):.2f}%",
                f"双重逆势度: {s.get('double_contrarian_degree', 0):.2f}%"
            ]
    
    # 快速异动
    elif signal_type == 'fast_anomaly':
        stocks = output.get('anomaly_stocks', [])
        if stocks:
            s = stocks[0]
            detail['summary'] = f"异动: {s.get('name', '')} 得分 {s.get('score', 0):.0f}"
            detail['highlights'] = [
                f"涨幅: {s.get('p_change', 0):.2f}%",
                f"量比: {s.get('volume_ratio', 0):.2f}",
                f"速度: {s.get('speed', 0):.2f}%"
            ]
    
    # 强势股逆势突破
    elif signal_type == 'strong_contrarian':
        stocks = output.get('breakthrough_stocks', [])
        if stocks:
            s = stocks[0]
            detail['summary'] = f"突破: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [
                f"加速: +{s.get('acceleration', 0):.2f}%",
                f"成交额: {s.get('turnover_yi', 0):.2f}亿"
            ]
    
    # 板块资金流向
    elif signal_type == 'block_capital_flow':
        inflow = output.get('top_inflow', [])
        outflow = output.get('top_outflow', [])
        
        if inflow:
            t = inflow[0]
            detail['summary'] = f"资金流入: {t.get('block', '')} {t.get('turnover_yi', 0):.2f}亿"
            detail['highlights'] = [f"💰 {b.get('block', '')} {b.get('turnover_yi', 0):.2f}亿" for b in inflow[:3]]
    
    # 行业相关
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
    
    # 板块逆势上涨
    elif signal_type == 'block_contrarian':
        blocks = output.get('contrarian_blocks', [])
        if blocks:
            t = blocks[0]
            detail['summary'] = f"逆势板块: {t.get('block', '')} +{t.get('avg_p_change', 0):.2f}%"
            detail['highlights'] = [f"逆势度: {t.get('contrarian_degree', 0):.2f}%"]
    
    # 板块轮动分析
    elif signal_type == 'block_rotation':
        strong = output.get('strong_blocks', [])
        rotation = output.get('rotation_signals', [])
        if strong:
            detail['summary'] = f"强势板块: {strong[0] if strong else ''}"
        if rotation:
            detail['highlights'] = rotation[:3]
    
    # 热门板块追踪
    elif signal_type == 'hot_block_track':
        hot = output.get('hot_blocks', [])
        if hot:
            t = hot[0]
            detail['summary'] = f"热门板块: {t.get('block', '')} +{t.get('avg_p_change', 0):.2f}%"
            detail['highlights'] = [f"📈 {b.get('block', '')} +{b.get('avg_p_change', 0):.2f}%" for b in hot[:3]]
    
    # 成交额排行
    elif signal_type == 'turnover_rank':
        total = output.get('total_turnover_yi', 0)
        hot = output.get('hot_stocks', [])
        concentration = output.get('concentration', 0)
        detail['summary'] = f"总成交额: {total:.1f}亿"
        if hot:
            detail['highlights'] = [f"🔥 {s.get('name', '')} {s.get('turnover_yi', 0):.1f}亿" for s in hot[:3]]
        detail['extra_info'] = f"集中度: {concentration:.1f}%"
    
    # 趋势分析
    elif signal_type == 'trend_analysis':
        up = output.get('up_count', 0)
        down = output.get('down_count', 0)
        signals = output.get('signals', [])
        detail['summary'] = f"上涨趋势: {up} | 下跌趋势: {down}"
        if signals:
            detail['highlights'] = signals[:3]
    
    # === 选股策略 ===
    
    # 放量突破策略
    elif signal_type == 'volume_breakout':
        signals = output.get('signals', [])
        count = output.get('signal_count', 0)
        if signals:
            s = signals[0]
            detail['summary'] = f"🚀 放量突破: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [
                f"成交额: {s.get('turnover_yi', 0):.2f}亿",
                f"评分: {s.get('score', 0):.1f}"
            ]
            if len(signals) > 1:
                detail['highlights'].append(f"共 {count} 只突破股")
    
    # 板块龙头策略
    elif signal_type == 'block_leader':
        leaders = output.get('leaders', [])
        if leaders:
            s = leaders[0]
            detail['summary'] = f"👑 龙头: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [
                f"板块: {s.get('block', '')}",
                f"板块涨幅: +{s.get('block_avg', 0):.2f}%"
            ]
            if len(leaders) > 1:
                detail['highlights'].append(f"共 {len(leaders)} 个龙头")
    
    # 强势回调策略
    elif signal_type == 'pullback_buy':
        signals = output.get('signals', [])
        count = output.get('signal_count', 0)
        if signals:
            s = signals[0]
            detail['summary'] = f"📉 回调: {s.get('name', '')} {s.get('p_change', 0):.2f}%"
            detail['highlights'] = [
                f"5日涨幅: +{s.get('change_5d', 0):.2f}%",
                f"成交额: {s.get('turnover_yi', 0):.2f}亿"
            ]
            if len(signals) > 1:
                detail['highlights'].append(f"共 {count} 只回调股")
    
    # 涨停回马枪策略
    elif signal_type == 'limit_up_retry':
        signals = output.get('signals', [])
        count = output.get('signal_count', 0)
        if signals:
            s = signals[0]
            detail['summary'] = f"🎯 回马枪: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [
                f"成交额: {s.get('turnover_yi', 0):.2f}亿",
                f"涨停次数: {s.get('limit_up_count', 0)}"
            ]
            if len(signals) > 1:
                detail['highlights'].append(f"共 {count} 只回马枪")
    
    # 早盘强势策略
    elif signal_type == 'morning_strong':
        signals = output.get('signals', [])
        count = output.get('signal_count', 0)
        current_time = output.get('current_time', '')
        if signals:
            s = signals[0]
            detail['summary'] = f"🌅 早盘强势: {s.get('name', '')} +{s.get('p_change', 0):.2f}%"
            detail['highlights'] = [
                f"开盘涨幅: +{s.get('open_change', 0):.2f}%",
                f"评分: {s.get('score', 0):.1f}"
            ]
            if len(signals) > 1:
                detail['highlights'].append(f"共 {count} 只强势股")
            detail['extra_info'] = f"时间: {current_time}"
    
    # 板块极值
    elif signal_type == 'block_extreme':
        top10 = output.get('top10', [])
        bottom10 = output.get('bottom10', [])
        if top10:
            t = top10[0]
            detail['summary'] = f"📈 领涨板块: {t.get('block', '')} +{t.get('avg_p_change', 0):.2f}%"
            detail['highlights'] = [f"📈 {b.get('block', '')} +{b.get('avg_p_change', 0):.2f}%" for b in top10[:3]]
        if bottom10:
            detail['highlights'].extend([f"📉 {b.get('block', '')} {b.get('avg_p_change', 0):.2f}%" for b in bottom10[:2]])
    
    # 默认
    if not detail['summary']:
        detail['summary'] = result.output_preview[:60]
    
    return detail


def _render_signal_stream_content(ctx, entries, store, limit: int = 20):
    """渲染实时信号流内容（用于局部刷新）"""
    all_results = []
    for e in entries:
        results = store.get_recent(e.id, limit=10)
        all_results.extend(results)

    all_results.sort(key=lambda x: x.ts, reverse=True)
    all_results = all_results[:limit]

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
        
        # 根据重要性设置样式
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
        
        # 生成高亮信息
        highlights_str = " | ".join(detail['highlights'][:4]) if detail['highlights'] else ""
        
        # 生成展开后的详细内容
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
        
        // 收起其他展开的项
        document.querySelectorAll('.signal-item.expanded').forEach(function(item) {{
            if (item !== el) {{
                item.classList.remove('expanded');
                item.querySelector('.signal-detail').style.display = 'none';
            }}
        }});
        
        // 切换当前项
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
        // 纯前端控制，不需要后端处理
        // 复选框状态已经自动更新，插入新信号时会检查这个状态
    }}
    </script>
    <div id="signal-stream-container" style="max-height:500px;overflow-y:auto;padding:4px;background:#f5f7fa;border-radius:12px;">
        {''.join(signals_html)}
    </div>
    """
    ctx["put_html"](signals_container)
    
    # 初始化已显示的信号 ID
    global _shown_signal_ids
    for r in all_results:
        _shown_signal_ids.add(r.id)


def _generate_expanded_content(result, detail: dict) -> str:
    """生成展开后的详细内容"""
    import json
    
    output = result.output_full or {}
    time_full = datetime.fromtimestamp(result.ts).strftime("%Y-%m-%d %H:%M:%S")
    
    parts = []
    
    # 基本信息
    parts.append(f"""
    <div style="background:#fff;padding:10px;border-radius:6px;margin-bottom:8px;">
        <div style="font-size:12px;color:#666;margin-bottom:6px;">📅 执行时间: {time_full}</div>
        <div style="font-size:12px;color:#666;">⏱️ 处理耗时: {result.process_time_ms:.1f}ms</div>
    </div>
    """)
    
    # 如果有 HTML 输出，直接显示
    if isinstance(output, dict) and 'html' in output:
        parts.append(f"""
        <div style="background:#fff;padding:10px;border-radius:6px;">
            {output['html']}
        </div>
        """)
    else:
        # 显示详细信息
        if detail.get('highlights'):
            highlights_html = "<br>".join([f"• {h}" for h in detail['highlights']])
            parts.append(f"""
            <div style="background:#fff;padding:10px;border-radius:6px;margin-bottom:8px;">
                <div style="font-size:12px;font-weight:600;color:#333;margin-bottom:6px;">📊 关键指标</div>
                <div style="font-size:11px;color:#666;line-height:1.6;">{highlights_html}</div>
            </div>
            """)
        
        # 显示完整输出（JSON格式）
        if output:
            try:
                if isinstance(output, dict):
                    output_str = json.dumps(output, ensure_ascii=False, indent=2)
                else:
                    output_str = str(output)
                
                # 限制长度
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


def register_signal_callback(result_id: str, callback):
    """注册信号点击回调"""
    global _signal_click_callbacks
    _signal_click_callbacks[result_id] = callback


def handle_signal_click(result_id: str, ctx: dict):
    """处理信号点击"""
    _show_result_detail_by_id(ctx, result_id)


def _build_table_data(ctx: dict, entries: list, mgr) -> list:
    table_data = []
    for e in entries:
        status_html = _render_status_badge(e.is_running)

        bound_ds_id = getattr(e._metadata, "bound_datasource_id", "")
        bound_ds_name = bound_ds_id
        if bound_ds_id:
            from ..datasource import get_datasource_manager
            ds_mgr = get_datasource_manager()
            ds = ds_mgr.get(bound_ds_id)
            if ds:
                bound_ds_name = ds.name
                bound_ds = ctx["put_buttons"]([
                    {"label": bound_ds_name[:20], "value": bound_ds_id}
                ], onclick=lambda v, c=ctx: _show_ds_detail_from_strategy(c, v), small=True)
            else:
                bound_ds = bound_ds_id[:12]
        else:
            bound_ds = "-"

        description = getattr(e._metadata, "description", "") or ""
        # 限制简介最多两行，约40个字符
        summary_preview = description[:40] + "..." if len(description) > 40 else description if description else "-"

        processed_count = e._state.processed_count
        last_process_ts = e._state.last_process_ts

        if last_process_ts > 0:
            try:
                last_process_time = datetime.fromtimestamp(
                    last_process_ts).strftime("%m-%d %H:%M:%S")
                recent_data = f"执行 {processed_count} 次<br>最后: {last_process_time}"
            except Exception:
                recent_data = f"执行 {processed_count} 次"
        else:
            recent_data = f"执行 {processed_count} 次"

        toggle_label = "停止" if e.is_running else "启动"
        toggle_color = "danger" if e.is_running else "success"

        actions = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{e.id}", "color": "info"},
            {"label": "编辑", "value": f"edit_{e.id}", "color": "primary"},
            {"label": toggle_label, "value": f"toggle_{e.id}", "color": toggle_color},
            {"label": "删除", "value": f"delete_{e.id}", "color": "danger"},
        ], onclick=lambda v, m=mgr, c=ctx: _handle_strategy_action(v, m, c))

        table_data.append([
            ctx["put_html"](f"<strong style='display:inline-block;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>{e.name}</strong>"),
            ctx["put_html"](status_html),
            bound_ds,
            ctx["put_html"](f'<span style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:12px;color:#666;max-width:200px;line-height:1.4;">{summary_preview}</span>'),
            ctx["put_html"](f'<span style="font-size:12px;color:#666;white-space:nowrap;">{recent_data}</span>'),
            actions,
        ])

    return table_data


def _render_recent_results(ctx, entries, store, limit: int = 10):
    """渲染最近执行结果表格"""
    all_results = []
    for e in entries:
        results = store.get_recent(e.id, limit=5)
        all_results.extend(results)

    all_results.sort(key=lambda x: x.ts, reverse=True)
    all_results = all_results[:limit]

    if not all_results:
        ctx["put_html"](
            '<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无执行结果</div>')
        return

    table_data = [["时间", "策略名称", "状态", "耗时", "输出预览", "操作"]]

    for r in all_results:
        status_html = '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;background:#e8f5e9;color:#2e7d32;">✅ 成功</span>' if r.success else '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;background:#ffebee;color:#c62828;">❌ 失败</span>'
        output_preview = r.output_preview[:60] + \
            "..." if len(r.output_preview) > 60 else r.output_preview
        if not r.success and r.error:
            output_preview = f"错误: {r.error[:50]}..."

        actions = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{r.id}", "color": "info"},
        ], onclick=lambda v, rid=r.id: _show_result_detail_by_id(ctx, rid))

        table_data.append([
            r.ts_readable[:16] if hasattr(r, 'ts_readable') else datetime.fromtimestamp(
                r.ts).strftime("%m-%d %H:%M:%S"),
            r.strategy_name[:15],
            ctx["put_html"](status_html),
            f"{r.process_time_ms:.1f}ms",
            output_preview,
            actions,
        ])

    ctx["put_table"](table_data)


def _show_ds_detail_from_strategy(ctx, ds_id: str):
    """从策略页面显示数据源详情"""
    from ..datasource import get_datasource_manager
    from ..datasource.ui import _show_ds_detail
    mgr = get_datasource_manager()
    run_async(_show_ds_detail(ctx, mgr, ds_id))


def _start_all_strategies(ctx, mgr):
    """启动所有策略"""
    count = 0
    for e in mgr.list_all():
        if not e.is_running:
            mgr.start(e.id)
            count += 1
    ctx["toast"](f"已启动 {count} 个策略", color="success")
    _render_strategy_content(ctx)


def _stop_all_strategies(ctx, mgr):
    """停止所有策略"""
    count = 0
    for e in mgr.list_all():
        if e.is_running:
            mgr.stop(e.id)
            count += 1
    ctx["toast"](f"已停止 {count} 个策略", color="warning")
    _render_strategy_content(ctx)


def _reload_all_strategies(ctx, mgr):
    """热重载所有策略"""
    result = mgr.reload_all()
    reloaded = result.get("reloaded", 0)
    failed = result.get("failed", 0)

    if failed > 0:
        ctx["toast"](f"重载完成: {reloaded} 成功, {failed} 失败", color="warning")
    else:
        ctx["toast"](f"已重载 {reloaded} 个策略", color="success")

    _render_strategy_content(ctx)


def _refresh_results(ctx, mgr):
    """刷新执行结果"""
    _render_strategy_content(ctx)
    ctx["toast"]("结果已刷新", color="success")


async def _show_history_dialog(ctx, mgr):
    """显示执行历史对话框"""
    from .result_store import get_result_store

    store = get_result_store()
    entries = mgr.list_all()

    strategy_options = [
        {"label": "全部策略", "value": ""},
    ] + [
        {"label": e.name, "value": e.id}
        for e in entries
    ]

    form = await ctx["input_group"]("📜 查询执行历史", [
        ctx["select"]("策略", name="strategy_id", options=strategy_options, value=""),
        ctx["input"]("时间范围(分钟)", name="minutes", type="number", value=60, placeholder="查询最近N分钟"),
        ctx["checkbox"]("仅成功", name="success_only", options=[
                        {"label": "仅显示成功", "value": "success_only", "selected": False}]),
        ctx["input"]("限制条数", name="limit", type="number", value=100),
        ctx["actions"]("操作", [
            {"label": "查询", "value": "query"},
            {"label": "取消", "value": "cancel"},
        ], name="action"),
    ])

    if not form or form.get("action") == "cancel":
        return

    import time as time_module
    start_ts = time_module.time() - form["minutes"] * 60

    results = store.query(
        strategy_id=form["strategy_id"] or None,
        start_ts=start_ts,
        success_only="success_only" in form.get("success_only", []),
        limit=form["limit"],
    )

    with ctx["popup"]("📜 执行历史查询结果", size="large", closable=True):
        ctx["put_markdown"](f"### 📜 执行历史查询结果")
        ctx["put_markdown"](f"**查询条件:** 时间范围: {form['minutes']}分钟, 限制条数: {form['limit']}")
        ctx["put_markdown"](f"**查询结果:** 共找到 {len(results)} 条记录")

        if not results:
            ctx["put_html"](
                "<div style='padding:20px;background:#f8d7da;border-radius:4px;color:#721c24;'>未找到符合条件的记录</div>")
            return

        table_data = [["时间", "策略", "状态", "耗时", "预览", "操作"]]
        for r in results:
            status = "✅" if r.success else "❌"
            preview = (r.output_preview or r.error or "")[:50]
            from datetime import datetime
            ts_readable = datetime.fromtimestamp(r.ts).strftime(
                "%Y-%m-%d %H:%M:%S") if r.ts else ""
            table_data.append([
                ts_readable[:16],
                r.strategy_name[:15] if r.strategy_name else "",
                status,
                f"{r.process_time_ms:.1f}ms",
                preview[:50] + "..." if len(preview) >= 50 else preview,
                ctx["put_button"]("详情", onclick=lambda rid=r.id,
                                  c=ctx: _show_result_detail_by_id(c, rid), small=True),
            ])

        ctx["put_table"](table_data)


def _handle_toolbar_action(action: str, mgr, ctx: dict):
    """处理工具栏按钮操作"""
    if action == "create":
        _create_strategy_dialog(mgr, ctx)
    elif action == "start_all":
        _start_all_strategies(ctx, mgr)
    elif action == "stop_all":
        _stop_all_strategies(ctx, mgr)
    elif action == "reload_all":
        _reload_all_strategies(ctx, mgr)
    elif action == "refresh_results":
        _refresh_results(ctx, mgr)
    elif action == "toggle_auto_refresh":
        enabled = ctx.get("data", {}).get("enabled", "true") == "true"
        set_auto_refresh(enabled)
        ctx["toast"](f"自动刷新已{'开启' if enabled else '关闭'}", color="success")
    elif action == "show_history":
        run_async(_show_history_dialog(ctx, mgr))


def _show_result_detail_by_id(ctx, result_id: str):
    """根据结果ID显示结果详情"""
    from .result_store import get_result_store
    store = get_result_store()
    result = store.get_by_id(result_id)

    if not result:
        ctx["toast"]("结果不存在", color="error")
        return

    with ctx["popup"](f"执行结果详情", size="large", closable=True):
        ctx["put_html"](_render_detail_section("基本信息"))
        info_table = [
            ["结果ID", result.id],
            ["策略名称", result.strategy_name],
            ["执行时间", datetime.fromtimestamp(result.ts).strftime("%Y-%m-%d %H:%M:%S")],
            ["状态", "✅ 成功" if result.success else "❌ 失败"],
            ["处理耗时", f"{result.process_time_ms:.2f}ms"],
        ]
        if result.error:
            info_table.append(["错误信息", result.error])
        ctx["put_table"](info_table)

        ctx["put_html"](_render_detail_section("输入数据预览"))
        ctx["put_code"](result.input_preview, language="text")

        if result.success and result.output_full is not None:
            ctx["put_html"](_render_detail_section("输出结果"))
            output_data = result.output_full
            if isinstance(output_data, dict):
                if "html" in output_data:
                    ctx["put_html"](output_data["html"])
                else:
                    ctx["put_code"](json.dumps(output_data, ensure_ascii=False,
                                               indent=2), language="json")
            elif isinstance(output_data, str):
                if output_data.startswith("<"):
                    ctx["put_html"](output_data)
                else:
                    ctx["put_code"](output_data[:2000], language="text")
            elif isinstance(output_data, list):
                ctx["put_code"](json.dumps(output_data[:20],
                                           ensure_ascii=False, indent=2), language="json")
            else:
                ctx["put_code"](str(output_data)[:2000], language="text")

        # 删除按钮
        ctx["put_html"]("<div style='margin-top:20px;'>")
        ctx["put_buttons"]([
            {"label": "🗑️ 删除此结果", "value": result_id, "color": "danger"},
        ], onclick=lambda v, c=ctx, s=store: _delete_result(c, s, v))
        ctx["put_html"]("</div>")


def _delete_result(ctx, store, result_id: str):
    """删除执行结果"""
    from pywebio.output import clear
    
    try:
        store.delete(result_id)
        ctx["toast"]("删除成功", color="success")
        ctx["close_popup"]()
    except Exception as e:
        ctx["toast"](f"删除失败: {e}", color="error")


def _handle_result_action(ctx, entry, result_id: str, action: str):
    """处理结果操作（详情/删除）"""
    if action.startswith("result_"):
        _show_result_detail(ctx, entry, result_id)
    elif action.startswith("delete_"):
        _delete_result_with_confirm(ctx, entry, result_id)


def _delete_result_with_confirm(ctx, entry, result_id: str):
    """删除执行结果（带确认）"""
    from .result_store import get_result_store
    from . import get_strategy_manager
    from pywebio.output import clear, use_scope
    
    store = get_result_store()
    
    try:
        store.delete(result_id)
        ctx["toast"]("删除成功", color="success")
        ctx["close_popup"]()
        
        # 刷新信号流
        mgr = get_strategy_manager()
        entries = list(mgr.list_all())
        with use_scope("signal_stream", clear=True):
            _render_signal_stream_content(ctx, entries, store)
    except Exception as e:
        ctx["toast"](f"删除失败: {e}", color="error")


def _handle_strategy_action(action: str, mgr, ctx: dict):
    """处理策略操作"""
    parts = action.split("_")
    action_type = parts[0]
    entry_id = "_".join(parts[1:])

    if action_type == "detail":
        run_async(_show_strategy_detail(ctx, mgr, entry_id))
        return
    elif action_type == "edit":
        run_async(_edit_strategy_dialog(ctx, mgr, entry_id))
        return
    elif action_type == "toggle":
        entry = mgr.get(entry_id)
        if entry and entry.is_running:
            mgr.stop(entry_id)
            ctx["toast"]("已停止", color="warning")
        else:
            mgr.start(entry_id)
            ctx["toast"]("已启动", color="success")
    elif action_type == "delete":
        mgr.delete(entry_id)
        ctx["toast"]("已删除", color="error")

    _render_strategy_content(ctx)


async def _show_strategy_detail(ctx: dict, mgr, entry_id: str):
    """显示策略详情"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("策略不存在", color="error")
        return

    with ctx["popup"](f"策略详情: {entry.name}", size="large", closable=True):
        ctx["put_html"](_render_detail_section("📊 基本信息"))

        ctx["put_table"]([
            ["ID", entry.id],
            ["名称", entry.name],
            ["描述", getattr(entry._metadata, "description", "") or "-"],
            ["状态", "运行中" if entry.is_running else "已停止"],
            ["计算模式", getattr(entry._metadata, "compute_mode", "record")],
            ["窗口大小", getattr(entry._metadata, "window_size", 5)],
            ["绑定数据源", getattr(entry._metadata, "bound_datasource_id", "") or "-"],
            ["历史保留", getattr(entry._metadata, "max_history_count", 100)],
            ["创建时间", _fmt_ts(entry._metadata.created_at)],
            ["更新时间", _fmt_ts(entry._metadata.updated_at)],
        ], header=["字段", "值"])

        dict_ids = getattr(entry._metadata, "dictionary_profile_ids", [])
        if dict_ids:
            ctx["put_html"]("<p><strong>数据字典:</strong> " + ", ".join(dict_ids) + "</p>")

        # 策略详解图表
        _render_strategy_diagram_section(ctx, entry)

        ctx["put_html"](_render_detail_section("📈 执行统计"))

        ctx["put_table"]([
            ["处理次数", entry._state.processed_count],
            ["输出次数", entry._state.output_count],
            ["错误次数", entry._state.error_count],
            ["最后错误", entry._state.last_error or "-"],
            ["最后处理", _fmt_ts(entry._state.last_process_ts)],
        ], header=["字段", "值"])

        ctx["put_html"](_render_detail_section("📜 历史执行结果"))

        try:
            recent_results = entry.get_recent_results(limit=10)
            if recent_results:
                result_table = [["时间", "状态", "耗时", "输出预览", "操作"]]
                for r in recent_results:
                    status_html = '<span style="color:#28a745;">✅</span>' if r.get(
                        "success") else '<span style="color:#dc3545;">❌</span>'
                    output_preview = r.get("output_preview", "")[:50]
                    if not r.get("success") and r.get("error"):
                        output_preview = f"错误: {r.get('error', '')[:40]}"

                    actions = ctx["put_buttons"]([
                        {"label": "详情", "value": f"result_{r.get('id', '')}", "color": "info"},
                        {"label": "删除", "value": f"delete_{r.get('id', '')}", "color": "danger"},
                    ], onclick=lambda v, rid=r.get("id", ""), e=entry: _handle_result_action(ctx, e, rid, v))

                    result_table.append([
                        r.get("ts_readable", "")[:16],
                        ctx["put_html"](status_html),
                        f"{r.get('process_time_ms', 0):.1f}ms",
                        output_preview[:50] +
                        "..." if len(output_preview) > 50 else output_preview,
                        actions,
                    ])
                ctx["put_table"](result_table)

                result_stats = entry.get_result_stats()
                ctx["put_html"](f"""
                <div style="margin-top:10px;padding:10px;background:#f5f5f5;border-radius:4px;">
                    <strong>执行统计:</strong> 
                    总计 {result_stats.get('results_count', 0)} 次 | 
                    成功率 {result_stats.get('success_rate', 0)*100:.1f}% | 
                    平均耗时 {result_stats.get('avg_process_time_ms', 0):.2f}ms
                </div>
                """)

                trend_data = entry.get_result_trend(interval_minutes=5, limit=20)
                if trend_data.get("timestamps"):
                    ctx["put_html"]("<p style='margin-top:15px;'><strong>执行趋势:</strong></p>")
                    timestamps = trend_data["timestamps"][::-1]
                    success_counts = trend_data["success_counts"][::-1]
                    failed_counts = trend_data["failed_counts"][::-1]
                    process_counts = trend_data["process_counts"][::-1]

                    max_count = max(process_counts) if process_counts else 1
                    chart_html = '<div style="display:flex;gap:2px;align-items:flex-end;height:60px;margin-top:10px;">'
                    for i, ts in enumerate(timestamps):
                        total = process_counts[i] if i < len(process_counts) else 0
                        success = success_counts[i] if i < len(success_counts) else 0
                        failed = failed_counts[i] if i < len(failed_counts) else 0

                        total_height = int((total / max_count) * 50) if max_count > 0 else 0
                        success_height = int((success / max_count) * 50) if max_count > 0 else 0
                        failed_height = int((failed / max_count) * 50) if max_count > 0 else 0

                        chart_html += f'''
                        <div style="display:flex;flex-direction:column;align-items:center;width:30px;">
                            <div style="display:flex;flex-direction:column-reverse;height:50px;width:20px;background:#f0f0f0;border-radius:2px;">
                                <div style="height:{success_height}px;background:#28a745;border-radius:2px;"></div>
                                <div style="height:{failed_height}px;background:#dc3545;border-radius:2px;"></div>
                            </div>
                            <div style="font-size:8px;color:#666;margin-top:2px;">{ts}</div>
                        </div>
                        '''
                    chart_html += '</div>'
                    chart_html += '<div style="margin-top:5px;font-size:11px;color:#666;"><span style="color:#28a745;">■</span> 成功 <span style="color:#dc3545;">■</span> 失败</div>'
                    ctx["put_html"](chart_html)
            else:
                ctx["put_html"](
                    '<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无执行结果</div>')
        except Exception as e:
            ctx["put_text"](f"获取历史结果失败: {str(e)}")

        ctx["put_html"](_render_detail_section("💻 处理代码"))

        if entry.func_code:
            ctx["put_code"](entry.func_code, language="python")
        else:
            ctx["put_text"]("暂无代码")

        export_json = json.dumps(entry.to_dict(), ensure_ascii=False, indent=2)
        ctx["put_html"](_render_detail_section("📤 导出策略配置"))
        ctx["put_collapse"]("点击展开/收起配置", [
            ctx["put_code"](export_json, language="json")
        ])


def _show_result_detail(ctx: dict, entry, result_id: str):
    """显示执行结果详情"""
    from .result_store import get_result_store
    store = get_result_store()
    result = store.get_by_id(result_id)

    if not result:
        ctx["toast"]("结果不存在", color="error")
        return

    with ctx["popup"](f"执行结果详情", size="large", closable=True):
        ctx["put_html"](_render_detail_section("基本信息"))
        info_table = [
            ["结果ID", result.id],
            ["策略名称", result.strategy_name],
            ["执行时间", datetime.fromtimestamp(result.ts).strftime("%Y-%m-%d %H:%M:%S")],
            ["状态", "✅ 成功" if result.success else "❌ 失败"],
            ["处理耗时", f"{result.process_time_ms:.2f}ms"],
        ]
        if result.error:
            info_table.append(["错误信息", result.error])
        ctx["put_table"](info_table)

        ctx["put_html"](_render_detail_section("输入数据预览"))
        ctx["put_code"](result.input_preview, language="text")

        if result.success and result.output_full is not None:
            ctx["put_html"](_render_detail_section("输出结果"))
            output_data = result.output_full
            if isinstance(output_data, dict):
                if "html" in output_data:
                    ctx["put_html"](output_data["html"])
                else:
                    ctx["put_code"](json.dumps(output_data, ensure_ascii=False,
                                               indent=2), language="json")
            elif isinstance(output_data, str):
                if output_data.startswith("<"):
                    ctx["put_html"](output_data)
                else:
                    ctx["put_code"](output_data[:2000], language="text")
            elif isinstance(output_data, list):
                ctx["put_code"](json.dumps(output_data[:20],
                                           ensure_ascii=False, indent=2), language="json")
            else:
                ctx["put_code"](str(output_data)[:2000], language="text")


async def _edit_strategy_dialog(ctx: dict, mgr, entry_id: str):
    """编辑策略对话框"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("策略不存在", color="error")
        return

    from ..datasource import get_datasource_manager
    from ..dictionary import get_dictionary_manager

    ds_mgr = get_datasource_manager()
    dict_mgr = get_dictionary_manager()

    source_options = [{"label": "无", "value": ""}]
    for ds in ds_mgr.list_all():
        source_options.append({"label": ds.name, "value": ds.id})

    dict_options = []
    for d in dict_mgr.list_all():
        dict_options.append({"label": d.name, "value": d.id})

    # 获取现有类别
    entries = mgr.list_all()
    existing_categories = _get_all_categories(entries)
    current_category = getattr(entry._metadata, "category", "默认") or "默认"
    category_options = [{"label": "默认", "value": "默认"}]
    for cat in existing_categories:
        if cat != "默认":
            category_options.append({"label": cat, "value": cat})
    category_options.append({"label": "+ 新建类别...", "value": "__new__"})

    with ctx["popup"](f"编辑策略: {entry.name}", size="large", closable=True):
        compute_mode = getattr(entry._metadata, "compute_mode", "record")
        window_type = getattr(entry._metadata, "window_type", "sliding")
        window_return_partial = getattr(entry._metadata, "window_return_partial", False)
        bound_datasource_id = getattr(entry._metadata, "bound_datasource_id", "")
        dictionary_profile_ids = getattr(entry._metadata, "dictionary_profile_ids", [])

        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("名称", name="name", required=True, value=entry.name),
            ctx["textarea"]("描述", name="description", rows=2,
                            value=getattr(entry._metadata, "description", "") or ""),
            ctx["select"]("类别", name="category_select", options=category_options, value=current_category),
            ctx["input"]("新类别名称", name="category_new", placeholder="输入新类别名称（如选择新建类别）"),
            ctx["select"]("绑定数据源", name="datasource_id", options=source_options,
                          value=bound_datasource_id),
            ctx["select"]("字典配置", name="dictionary_profile_ids", options=dict_options,
                          multiple=True, value=dictionary_profile_ids),
            ctx["select"]("计算模式", name="compute_mode", options=[
                {"label": "逐条处理", "value": "record"},
                {"label": "窗口处理", "value": "window"},
            ], value=compute_mode),
            ctx["select"]("窗口类型", name="window_type", options=[
                {"label": "滑动窗口", "value": "sliding"},
                {"label": "定时窗口", "value": "timed"},
            ], value=window_type),
            ctx["input"]("窗口大小", name="window_size", type="number",
                         value=getattr(entry._metadata, "window_size", 5)),
            ctx["input"]("定时窗口间隔", name="window_interval",
                         value=getattr(entry._metadata, "window_interval", "10s"),
                         placeholder="如 5s / 1min / 1h"),
            ctx["select"]("窗口未满是否输出", name="window_return_partial", options=[
                {"label": "否", "value": "false"},
                {"label": "是", "value": "true"},
            ], value="true" if window_return_partial else "false"),
            ctx["input"]("历史保留条数", name="max_history_count", type="number",
                         value=getattr(entry._metadata, "max_history_count", 100)),
            ctx["textarea"]("代码", name="code",
                            value=entry.func_code or DEFAULT_STRATEGY_CODE,
                            rows=14,
                            code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])

        if form and form.get("action") == "save":
            form_window_return_partial = str(
                form.get("window_return_partial", "false")).lower() in ("true", "1", "yes")

            # 处理类别
            category = form.get("category_select", "默认")
            if category == "__new__" and form.get("category_new"):
                category = form.get("category_new").strip()
            elif category == "__new__":
                category = current_category

            result = entry.update_config(
                name=form["name"].strip(),
                description=form.get("description", "").strip(),
                bound_datasource_id=form.get("datasource_id", ""),
                dictionary_profile_ids=form.get("dictionary_profile_ids", []),
                compute_mode=form.get("compute_mode"),
                window_type=form.get("window_type"),
                window_size=int(form.get("window_size", 5)),
                window_interval=form.get("window_interval", "10s"),
                window_return_partial=form_window_return_partial,
                max_history_count=int(form.get("max_history_count", 100)),
                func_code=form.get("code"),
                category=category,
            )

            if result.get("success"):
                ctx["toast"]("保存成功", color="success")
                ctx["close_popup"]()
                _render_strategy_content(ctx)
            else:
                ctx["toast"](f"保存失败: {result.get('error')}", color="error")


def _create_strategy_dialog(mgr, ctx: dict):
    """创建策略对话框"""
    run_async(_create_strategy_dialog_async(mgr, ctx))


async def _create_strategy_dialog_async(mgr, ctx: dict):
    """创建策略对话框（异步）"""
    from ..datasource import get_datasource_manager
    from ..dictionary import get_dictionary_manager

    ds_mgr = get_datasource_manager()
    dict_mgr = get_dictionary_manager()

    source_options = [{"label": "无", "value": ""}]
    for ds in ds_mgr.list_all():
        source_options.append({"label": ds.name, "value": ds.id})

    dict_options = []
    for d in dict_mgr.list_all():
        dict_options.append({"label": d.name, "value": d.id})

    # 获取现有类别
    entries = mgr.list_all()
    existing_categories = _get_all_categories(entries)
    category_options = [{"label": "默认", "value": "默认"}]
    for cat in existing_categories:
        if cat != "默认":
            category_options.append({"label": cat, "value": cat})
    category_options.append({"label": "+ 新建类别...", "value": "__new__"})

    with ctx["popup"]("创建策略", size="large", closable=True):
        ctx["put_markdown"]("### 创建策略")
        ctx["put_html"]("<p style='color:#666;font-size:13px;'>处理数据流中的数据</p>")

        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("名称", name="name", required=True, placeholder="输入策略名称"),
            ctx["textarea"]("描述", name="description", rows=2, placeholder="策略描述（可选）"),
            ctx["select"]("类别", name="category_select", options=category_options, value="默认"),
            ctx["input"]("新类别名称", name="category_new", placeholder="输入新类别名称（如选择新建类别）"),
            ctx["select"]("绑定数据源", name="datasource_id", options=source_options, value=""),
            ctx["select"]("字典配置", name="dictionary_profile_ids",
                          options=dict_options, multiple=True, value=[]),
            ctx["select"]("计算模式", name="compute_mode", options=[
                {"label": "逐条处理", "value": "record"},
                {"label": "窗口处理", "value": "window"},
            ], value="record"),
            ctx["select"]("窗口类型", name="window_type", options=[
                {"label": "滑动窗口", "value": "sliding"},
                {"label": "定时窗口", "value": "timed"},
            ], value="sliding"),
            ctx["input"]("窗口大小", name="window_size", type="number", value=5),
            ctx["input"]("定时窗口间隔", name="window_interval", value="10s", placeholder="如 5s / 1min"),
            ctx["select"]("窗口未满是否输出", name="window_return_partial", options=[
                {"label": "否", "value": "false"},
                {"label": "是", "value": "true"},
            ], value="false"),
            ctx["input"]("历史保留条数", name="max_history_count", type="number", value=100),
            ctx["textarea"]("代码", name="code",
                            value=DEFAULT_STRATEGY_CODE,
                            rows=14,
                            code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])

        if form and form.get("action") == "create":
            window_return_partial = str(
                form.get("window_return_partial", "false")).lower() in ("true", "1", "yes")

            # 处理类别
            category = form.get("category_select", "默认")
            if category == "__new__" and form.get("category_new"):
                category = form.get("category_new").strip()
            elif category == "__new__":
                category = "默认"

            result = mgr.create(
                name=form["name"].strip(),
                func_code=form.get("code", ""),
                description=form.get("description", "").strip(),
                bound_datasource_id=form.get("datasource_id", ""),
                dictionary_profile_ids=form.get("dictionary_profile_ids", []),
                compute_mode=form.get("compute_mode", "record"),
                window_type=form.get("window_type", "sliding"),
                window_size=int(form.get("window_size", 5)),
                window_interval=form.get("window_interval", "10s"),
                window_return_partial=window_return_partial,
                max_history_count=int(form.get("max_history_count", 100)),
                category=category,
            )

            if result.get("success"):
                ctx["toast"]("创建成功", color="success")
                ctx["close_popup"]()
                _render_strategy_content(ctx)
            else:
                ctx["toast"](f"创建失败: {result.get('error')}", color="error")
