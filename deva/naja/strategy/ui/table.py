"""策略列表表格渲染与分类切换"""

from datetime import datetime

from pywebio.output import put_html

from deva.naja.register import SR
from deva.naja.infra.ui.ui_style import render_status_badge


def _get_render_strategy_content():
    """延迟导入避免循环引用"""
    from . import _render_strategy_content
    return _render_strategy_content


# 全局状态：当前选中的类别和视图模式（由 _switch_category/_switch_view_mode 修改）
_current_category = "全部"
_view_mode = "category"  # "category": 按category分类, "handler": 按handler_type分类

try:
    from deva.naja.strategy.handler_type import get_strategy_handler_type, StrategyHandlerType
    HANDLER_TYPE_AVAILABLE = True
except ImportError:
    HANDLER_TYPE_AVAILABLE = False


def _render_type_badge(strategy_type: str) -> str:
    stype = str(strategy_type or "legacy").lower()
    color = "#64748b"
    bg = "#f1f5f9"
    label = stype
    if stype == "declarative":
        color = "#0ea5e9"
        bg = "#e0f2fe"
        label = "declarative"
    elif stype == "river":
        color = "#10b981"
        bg = "#dcfce7"
        label = "river"
    elif stype == "plugin":
        color = "#8b5cf6"
        bg = "#ede9fe"
        label = "plugin"
    elif stype == "attention":
        color = "#f59e0b"
        bg = "#fef3c7"
        label = "attention"
    elif stype == "legacy":
        label = "legacy"
    return f'<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:{bg};color:{color};">{label}</span>'


def _get_handler_type_label(ht: str) -> str:
    """获取handler_type的中文标签"""
    labels = {
        "radar": "📡 Radar雷达",
        "memory": "🧠 Memory记忆",
        "bandit": "🎰 Bandit交易",
        "llm": "🤖 LLM调节",
        "attention": "👁️ Attention注意",
    }
    return labels.get(ht, ht)


def _categorize_strategy_by_handler(entry) -> str:
    """根据策略的handler_type来分类"""
    ht = getattr(entry._metadata, "handler_type", "unknown") or "unknown"
    if ht == "unknown":
        return "⚪ 未分类"
    return _get_handler_type_label(ht)


def _get_all_handler_categories(entries: list) -> list:
    """获取所有handler类别"""
    categories = set()
    for e in entries:
        cat = _categorize_strategy_by_handler(e)
        categories.add(cat)
    return sorted(list(categories))


def _get_all_categories(entries: list) -> list:
    """获取所有类别（根据视图模式）"""
    if _view_mode == "handler":
        return _get_all_handler_categories(entries)
    categories = set()
    for e in entries:
        cat = getattr(e._metadata, "category", "默认") or "默认"
        categories.add(cat)
    return sorted(list(categories))


def _get_strategy_func_code_file(entry) -> str:
    """获取策略的代码文件路径"""
    func_code_file = getattr(entry._metadata, "func_code_file", "") or ""
    if not func_code_file:
        try:
            from deva.naja.config.file_config import get_file_config_manager
            file_mgr = get_file_config_manager("strategy")
            item = file_mgr.get(entry.name)
            if item:
                func_code_file = item.func_code_file or ""
        except Exception:
            pass
    return func_code_file


def _resolve_datasource_name(datasource_id: str) -> str:
    if not datasource_id:
        return "-"
    try:
        from deva.naja.datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        ds = ds_mgr.get(datasource_id)
        if ds:
            return ds.name
    except Exception:
        pass
    return datasource_id


def _render_category_tabs(ctx: dict, categories: list, entries: list, mgr):
    """渲染类别 Tab"""
    global _current_category, _view_mode

    tab_buttons = [{"label": f"📋 全部 ({len(entries)})", "value": "全部"}]

    for cat in categories:
        if _view_mode == "handler":
            count = len([e for e in entries if _categorize_strategy_by_handler(e) == cat])
        else:
            count = len([e for e in entries if getattr(e._metadata, "category", "默认") == cat])
        icon = "📡" if _view_mode == "handler" and "Radar" in cat else \
               "🧠" if _view_mode == "handler" and "Memory" in cat else \
               "🎰" if _view_mode == "handler" and "Bandit" in cat else \
               "🤖" if _view_mode == "handler" and "LLM" in cat else \
               "👁️" if _view_mode == "handler" and "Attention" in cat else \
               "⚪" if _view_mode == "handler" else "📁"
        tab_buttons.append({"label": f"{icon} {cat} ({count})", "value": cat})

    ctx["put_html"]('<div class="category-tabs">', scope="strategy_content")

    ctx["put_buttons"](tab_buttons, onclick=lambda v, c=ctx, m=mgr: _switch_category(v, c, m), scope="strategy_content")

    ctx["put_html"]("</div>", scope="strategy_content")

    view_mode_btns = [
        {"label": "📂 按类别", "value": "category", "color": "primary" if _view_mode == "category" else "secondary"},
        {"label": "📥 按消费", "value": "handler", "color": "primary" if _view_mode == "handler" else "secondary"},
    ]
    ctx["put_html"]('<div style="margin-top:8px;">', scope="strategy_content")
    ctx["put_buttons"](view_mode_btns, onclick=lambda v, c=ctx, m=mgr: _switch_view_mode(v, c, m), scope="strategy_content")
    ctx["put_html"]('</div>', scope="strategy_content")


def _switch_category(category: str, ctx: dict, mgr):
    """切换类别"""
    global _current_category
    _current_category = category
    _get_render_strategy_content()(ctx)


def _switch_view_mode(mode: str, ctx: dict, mgr):
    """切换视图模式"""
    global _view_mode, _current_category
    _view_mode = mode
    _current_category = "全部"
    _get_render_strategy_content()(ctx)


def _build_table_data(ctx: dict, entries: list, mgr) -> list:
    import time as time_module
    _table_start = time_module.time()
    
    table_data = []
    for idx, e in enumerate(entries):
        _entry_start = time_module.time()
        
        status_html = render_status_badge(e.is_running)
        type_html = _render_type_badge(getattr(e._metadata, "strategy_type", "legacy"))
        
        handler_type = getattr(e._metadata, "handler_type", "unknown")
        if HANDLER_TYPE_AVAILABLE and handler_type != "unknown":
            handler_info = {
                "radar": {"icon": "📡", "color": "#ef4444", "bg": "rgba(239,68,68,0.1)"},
                "memory": {"icon": "🧠", "color": "#8b5cf6", "bg": "rgba(139,92,246,0.1)"},
                "bandit": {"icon": "🎰", "color": "#f59e0b", "bg": "rgba(245,158,11,0.1)"},
                "llm": {"icon": "🤖", "color": "#10b981", "bg": "rgba(16,185,129,0.1)"},
                "attention": {"icon": "👁️", "color": "#f59e0b", "bg": "rgba(245,158,11,0.1)"},
            }.get(handler_type, {"icon": "❓", "color": "#6b7280", "bg": "rgba(107,114,128,0.1)"})
            
            handler_html = f'''<span style="display:inline-flex;align-items:center;gap:2px;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:500;background:{handler_info['bg']};color:{handler_info['color']};margin-left:4px;">
                {handler_info['icon']} {handler_type}
            </span>'''
            type_html = type_html.replace('</span>', f'{handler_html}</span>')

        # 获取多数据源绑定列表
        bound_datasource_ids = getattr(e._metadata, "bound_datasource_ids", [])
        if not bound_datasource_ids:
            # 兼容旧版本单数据源
            bound_ds_id = getattr(e._metadata, "bound_datasource_id", "")
            if bound_ds_id:
                bound_datasource_ids = [bound_ds_id]

        # 构建数据源按钮列表（使用透明/浅色样式）
        if bound_datasource_ids:
            from deva.naja.datasource import get_datasource_manager
            ds_mgr = get_datasource_manager()
            ds_buttons_html = '<div style="display:flex;flex-wrap:wrap;gap:4px;">'
            for ds_id in bound_datasource_ids:
                ds = ds_mgr.get(ds_id)
                ds_name = ds.name[:10] if ds else ds_id[:8]
                ds_buttons_html += f'''<button onclick="showDsDetail('{ds_id}')" 
                    style="padding:2px 8px;font-size:11px;border:1px solid #e0e0e0;
                    background:#f5f5f5;color:#666;border-radius:4px;cursor:pointer;
                    transition:all 0.2s;"
                    onmouseover="this.style.background='#e8e8e8';this.style.borderColor='#d0d0d0';"
                    onmouseout="this.style.background='#f5f5f5';this.style.borderColor='#e0e0e0';"
                    >{ds_name}</button>'''
            ds_buttons_html += '</div>'
            ds_buttons_html += '''<script>
                function showDsDetail(dsId) {
                    // 触发数据源详情查看
                    window.parent.postMessage({type: 'show_datasource_detail', dsId: dsId}, '*');
                }
            </script>'''
            bound_ds = ctx["put_html"](ds_buttons_html)
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

        source = getattr(e._metadata, 'source', 'nb') if hasattr(e, '_metadata') else 'nb'
        internal_to_cognition = getattr(e._metadata, 'internal_to_cognition', False)
        if internal_to_cognition:
            source_html = '<span style="background:#f3e5f5;color:#7b1fa2;padding:2px 8px;border-radius:4px;font-size:11px;">🧠 认知系统</span>'
        elif source == 'file':
            source_html = '<span style="background:#e8f5e9;color:#2e7d32;padding:2px 8px;border-radius:4px;font-size:11px;">📁 文件</span>'
        elif source == 'attention':
            source_html = '<span style="background:#fef3c7;color:#f59e0b;padding:2px 8px;border-radius:4px;font-size:11px;">👁️ 注意力</span>'
        else:
            source_html = '<span style="background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:4px;font-size:11px;">💾 NB</span>'

        actions = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{e.id}", "color": "info"},
            {"label": "编辑", "value": f"edit_{e.id}", "color": "primary"},
            {"label": toggle_label, "value": f"toggle_{e.id}", "color": toggle_color},
            {"label": "看板", "value": f"board_{e.id}", "color": "warning"},
        ], onclick=lambda v, m=mgr, c=ctx: _handle_strategy_action(v, m, c), small=True, group=True)

        table_data.append([
            ctx["put_html"](f"<strong style='display:inline-block;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>{e.name}</strong>"),
            ctx["put_html"](source_html),
            ctx["put_html"](type_html),
            ctx["put_html"](status_html),
            bound_ds,
            ctx["put_html"](f'<span style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:12px;color:#666;max-width:200px;line-height:1.4;">{summary_preview}</span>'),
            ctx["put_html"](f'<span style="font-size:12px;color:#666;white-space:nowrap;">{recent_data}</span>'),
            actions,
        ])

    _table_end = time_module.time()

    return table_data
