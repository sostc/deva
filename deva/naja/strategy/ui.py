"""策略管理 UI"""

import json

from pywebio.output import put_text, put_markdown, put_table, put_buttons, put_html, toast, popup, close_popup, put_code, put_collapse, put_row, use_scope, set_scope, clear
from pywebio.input import input_group, input, textarea, select, actions
from pywebio.session import run_async

from ..common.ui_style import apply_strategy_like_styles, render_empty_state, format_timestamp, render_status_badge, render_detail_section
from ..page_help import render_help_collapse

try:
    from ..strategy.handler_type import get_strategy_handler_type, StrategyHandlerType
    HANDLER_TYPE_AVAILABLE = True
except ImportError:
    HANDLER_TYPE_AVAILABLE = False


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

DEFAULT_DECLARATIVE_CONFIG = {
    "pipeline": [
        {"type": "feature", "name": "price_change"},
        {"type": "feature", "name": "volume_spike"},
    ],
    "model": {"type": "logistic_regression"},
    "params": {"learning_rate": 0.01},
    "logic": {"type": "threshold", "buy": 0.7, "sell": 0.3},
    "state_persist": True,
    "state_persist_interval": 300,
    "state_persist_every_n": 200,
}


def _render_strategy_help(ctx: dict):
    """渲染策略系统帮助说明"""
    render_help_collapse("strategy")


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
    elif stype == "legacy":
        label = "legacy"
    return f'<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:{bg};color:{color};">{label}</span>'


def _render_principle_section(ctx: dict, entry, principle: dict, color: str):
    """渲染原理解释部分（河流比喻）"""
    title = principle.get("title", "策略原理解释")
    core_concept = principle.get("core_concept", "")
    five_dimensions = principle.get("five_dimensions", {})
    learning_mechanism = principle.get("learning_mechanism", "")
    output_meaning = principle.get("output_meaning", "")

    # 生成五个维度的 HTML
    dimensions_html = ""
    dim_icons = {
        "向": "🌊",
        "速": "⚡",
        "弹": "💥",
        "深": "📏",
        "波": "🌀"
    }

    for dim_key, dim_data in five_dimensions.items():
        # 提取第一个字作为图标
        first_char = dim_key.split("_")[0] if "_" in dim_key else dim_key[0]
        icon = dim_icons.get(first_char, "📌")

        dimensions_html += f"""
        <div style="background:#f8f9fa;padding:15px;border-radius:8px;margin-bottom:12px;
                    border-left:3px solid {color};">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
                <span style="font-size:18px;">{icon}</span>
                <span style="font-weight:600;color:#333;font-size:14px;">{dim_key}</span>
            </div>
            <div style="margin-bottom:8px;">
                <span style="color:#666;font-size:12px;">📖 {dim_data.get('description', '')}</span>
            </div>
            <div style="margin-bottom:8px;">
                <span style="color:#666;font-size:12px;">⚙️ {dim_data.get('implementation', '')}</span>
            </div>
            <div style="margin-bottom:8px;">
                <div style="color:#888;font-size:11px;margin-bottom:4px;">📊 指标:</div>
                <div style="background:#fff;padding:8px;border-radius:4px;font-family:monospace;
                            font-size:11px;color:#555;">
                    {'<br>'.join(dim_data.get('metrics', []))}
                </div>
            </div>
            <div>
                <span style="color:#666;font-size:12px;">💭 {dim_data.get('interpretation', '')}</span>
            </div>
        </div>
        """

    # 学习机制和输出含义
    extra_html = ""
    if learning_mechanism or output_meaning:
        extra_html = f"""
        <div style="margin-top:15px;display:grid;grid-template-columns:1fr 1fr;gap:15px;">
            {'<div style="background:#e3f2fd;padding:12px;border-radius:8px;font-size:12px;color:#333;">'
             '<strong>🧠 学习机制:</strong><br>' + learning_mechanism + '</div>' if learning_mechanism else ''}
            {'<div style="background:#e8f5e9;padding:12px;border-radius:8px;font-size:12px;color:#333;">'
             '<strong>📤 输出含义:</strong><br>' + output_meaning + '</div>' if output_meaning else ''}
        </div>
        """

    ctx["put_html"](f"""
    <div style="background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);
                overflow:hidden;border:1px solid #eee;margin-bottom:15px;">
        <div style="background:linear-gradient(135deg,{color} 0%,{color}dd 100%);
                    padding:15px 20px;color:white;">
            <div style="display:flex;align-items:center;gap:12px;">
                <div style="font-size:24px;">🌊</div>
                <div>
                    <div style="font-size:16px;font-weight:600;">{title}</div>
                    <div style="font-size:12px;opacity:0.9;margin-top:3px;">{core_concept}</div>
                </div>
            </div>
        </div>
        <div style="padding:20px;">
            {dimensions_html}
            {extra_html}
        </div>
    </div>
    """)


def _render_strategy_diagram_section(ctx: dict, entry):
    """渲染策略详解图表部分"""
    diagram_info = getattr(entry._metadata, "diagram_info", {}) or {}

    if not diagram_info:
        return

    ctx["put_html"](render_detail_section("📊 策略详解"))

    icon = diagram_info.get("icon", "📊")
    color = diagram_info.get("color", "#667eea")
    description = diagram_info.get("description", "")
    formula = diagram_info.get("formula", "")
    logic = diagram_info.get("logic", [])
    output = diagram_info.get("output", "")
    principle = diagram_info.get("principle", {})

    # 生成流程步骤 HTML
    logic_html = "".join([
        f'<div style="padding:4px 0;color:#555;font-size:12px;display:flex;align-items:center;gap:6px;">'
        f'<span style="background:{color};color:white;width:18px;height:18px;border-radius:50%;'
        f'display:flex;align-items:center;justify-content:center;font-size:10px;">{i+1}</span>{step}</div>'
        for i, step in enumerate(logic)
    ])

    # 渲染原有的策略详解
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

    # 渲染河流比喻（如果有）
    river_metaphor = diagram_info.get("river_metaphor", {})
    if river_metaphor:
        _render_river_metaphor_section(ctx, river_metaphor, color)

    # 渲染记忆结构（如果有）
    memory_structure = diagram_info.get("memory_structure", {})
    if memory_structure:
        _render_memory_structure_section(ctx, memory_structure, color)

    # 渲染信号类型（如果有）
    signal_types = diagram_info.get("signal_types", [])
    if signal_types:
        _render_signal_types_section(ctx, signal_types, color)

    # 渲染原理解释（如果有）
    if principle:
        _render_principle_section(ctx, entry, principle, color)


async def render_strategy_admin(ctx: dict):
    """渲染策略管理面板"""
    set_scope("strategy_content")
    _render_strategy_content(ctx)


# 全局变量：当前选中的类别
_current_category = "全部"


def _get_all_categories(entries: list) -> list:
    """获取所有类别"""
    categories = set()
    for e in entries:
        cat = getattr(e._metadata, "category", "默认") or "默认"
        categories.add(cat)
    return sorted(list(categories))


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


def _render_strategy_content(ctx: dict):
    """渲染策略管理内容（支持局部刷新）"""
    import time as time_module
    _perf_start = time_module.time()
    
    from . import get_strategy_manager
    from .result_store import get_result_store
    from pywebio.output import clear

    global _current_category

    _t0 = time_module.time()
    mgr = get_strategy_manager()
    _t1 = time_module.time()

    store = get_result_store()
    _t2 = time_module.time()

    _t3 = time_module.time()
    entries = mgr.list_all()
    _t4 = time_module.time()

    stats = mgr.get_stats()
    _t5 = time_module.time()

    result_stats = store.get_stats()
    _t6 = time_module.time()

    running_count = sum(1 for e in entries if e.is_running)
    error_count = sum(1 for e in entries if e._state.error_count > 0)

    clear("strategy_content")
    _t7 = time_module.time()

    apply_strategy_like_styles(ctx, scope="strategy_content", include_compact_table=True, include_category_tabs=True)
    _t8 = time_module.time()

    ctx["put_html"](_render_strategy_stats_html(
        stats, running_count, error_count), scope="strategy_content")

    exp_info = mgr.get_experiment_info()
    if exp_info.get("active"):
        categories_text = "、".join(exp_info.get("categories", []))
        ds_name = exp_info.get("datasource_name") or _resolve_datasource_name(exp_info.get("datasource_id", ""))
        target_count = int(exp_info.get("target_count", 0))
        ctx["put_html"](f"""
        <div style="margin-bottom:14px;padding:12px 14px;border-radius:10px;
                    background:linear-gradient(135deg,#fff3cd,#ffe8a1);
                    border:1px solid #f5d37a;color:#7a5a00;font-size:13px;">
            <strong>🧪 实验模式已开启</strong><br>
            类别：{categories_text or "-"} ｜ 数据源：{ds_name} ｜ 策略数：{target_count}
        </div>
        """, scope="strategy_content")

    # 渲染类别 Tab
    categories = _get_all_categories(entries)
    _render_category_tabs(ctx, categories, entries, mgr)
    _t9 = time_module.time()

    # 根据当前类别筛选策略
    if _current_category == "全部":
        filtered_entries = entries
    else:
        filtered_entries = [e for e in entries if getattr(e._metadata, "category", "默认") == _current_category]

    if filtered_entries:
        _t10 = time_module.time()
        table_data = _build_table_data(ctx, filtered_entries, mgr)
        _t11 = time_module.time()

        ctx["put_table"](table_data, header=["名称", "来源", "类型", "状态", "数据源", "简介",
                                             "最近数据", "操作"], scope="strategy_content")

        ctx["put_html"](
            '<div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">', scope="strategy_content")
        toolbar_buttons = [
            {"label": "➕ 创建策略", "value": "create", "color": "primary"},
            {"label": "▶️ 全部启动", "value": "start_all", "color": "success"},
            {"label": "⏹️ 全部停止", "value": "stop_all", "color": "danger"},
            {"label": "🔄 重载配置", "value": "reload_all", "color": "info"},
            {"label": "🔄 刷新结果", "value": "refresh_results", "color": "info"},
            {"label": "📜 执行历史", "value": "show_history", "color": "default"},
        ]
        if exp_info.get("active"):
            toolbar_buttons.append({"label": "🧪 关闭实验模式", "value": "close_experiment", "color": "danger"})
        else:
            toolbar_buttons.append({"label": "🧪 开启实验模式", "value": "open_experiment", "color": "warning"})

        ctx["put_buttons"](toolbar_buttons, onclick=lambda v, m=mgr, c=ctx: _handle_toolbar_action(v, m, c), group=True, scope="strategy_content")
        ctx["put_html"]('</div>', scope="strategy_content")
    else:
        ctx["put_html"](render_empty_state("暂无策略，点击下方按钮创建"), scope="strategy_content")
        ctx["put_buttons"]([{"label": "➕ 创建策略", "value": "create", "color": "primary"}],
                           onclick=lambda v, m=mgr, c=ctx: _create_strategy_dialog(m, c), scope="strategy_content")

    ctx["put_buttons"]([{"label": "📁 导出全部到文件", "value": "export_all", "color": "info"}],
                       onclick=lambda v, m=mgr, c=ctx: _export_all_strategies_to_file(m, c), scope="strategy_content")

    ctx["put_html"](
        "<hr style='margin:24px 0;border:none;border-top:1px solid #e0e0e0;'>", scope="strategy_content")

    ctx["put_html"](_render_result_stats_html(result_stats), scope="strategy_content")

    _render_strategy_help(ctx)

    _t12 = time_module.time()
    total_time_ms = (_t12-_perf_start)*1000

    # 记录 Web 请求性能
    try:
        from ..performance import record_web_request
        record_web_request(
            request_path="/naja/strategy",
            execution_time_ms=total_time_ms,
            success=True,
        )
    except Exception:
        pass


def _render_category_tabs(ctx: dict, categories: list, entries: list, mgr):
    """渲染类别 Tab"""
    global _current_category

    # 构建Tab按钮
    tab_buttons = [{"label": f"📋 全部 ({len(entries)})", "value": "全部"}]
    
    for cat in categories:
        count = len([e for e in entries if getattr(e._metadata, "category", "默认") == cat])
        tab_buttons.append({"label": f"📁 {cat} ({count})", "value": cat})

    ctx["put_html"]('<div class="category-tabs">', scope="strategy_content")

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
            from ..datasource import get_datasource_manager
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
        if source == 'file':
            source_html = '<span style="background:#e8f5e9;color:#2e7d32;padding:2px 8px;border-radius:4px;font-size:11px;">📁 文件</span>'
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


def _export_all_strategies_to_file(mgr, ctx: dict):
    """导出所有策略到文件配置"""
    from deva.naja.config.file_config import get_file_config_manager

    file_mgr = get_file_config_manager('strategy')
    count = 0

    for entry in mgr.list_all():
        if not entry or not entry.name:
            continue

        try:
            from deva.naja.config.file_config import ConfigFileItem, StrategyConfigMetadata

            meta = entry._metadata
            config_meta = StrategyConfigMetadata(
                id=entry.id,
                name=entry.name,
                description=meta.description or '',
                tags=meta.tags or [],
                category=meta.category or '默认',
                created_at=getattr(meta, 'created_at', 0),
                updated_at=time_module.time(),
                enabled=getattr(meta, 'enabled', True),
                source='file',
                bound_datasource_id=getattr(meta, 'bound_datasource_id', ''),
                bound_datasource_ids=getattr(meta, 'bound_datasource_ids', []),
                compute_mode=getattr(meta, 'compute_mode', 'record'),
                window_size=getattr(meta, 'window_size', 5),
                window_type=getattr(meta, 'window_type', 'sliding'),
                window_interval=getattr(meta, 'window_interval', '10s'),
                window_return_partial=getattr(meta, 'window_return_partial', False),
                dictionary_profile_ids=getattr(meta, 'dictionary_profile_ids', []),
                max_history_count=getattr(meta, 'max_history_count', 100),
                strategy_type=getattr(meta, 'strategy_type', 'legacy'),
                handler_type=getattr(meta, 'handler_type', 'unknown'),
            )

            parameters = {
                'window_size': getattr(meta, 'window_size', 5),
                'max_history_count': getattr(meta, 'max_history_count', 100),
                'enabled': getattr(meta, 'enabled', True),
            }

            config = {
                'compute_mode': getattr(meta, 'compute_mode', 'record'),
                'window_type': getattr(meta, 'window_type', 'sliding'),
                'strategy_type': getattr(meta, 'strategy_type', 'legacy'),
                'handler_type': getattr(meta, 'handler_type', 'unknown'),
            }

            item = ConfigFileItem(
                name=entry.name,
                config_type='strategy',
                metadata=config_meta,
                parameters=parameters,
                config=config,
                func_code=entry._func_code or '',
            )

            if file_mgr.save(item):
                count += 1
        except Exception as e:
            print(f"Export strategy failed: {entry.name}, error: {e}")

    ctx["toast"](f"已导出 {count} 个策略到文件", color="success")


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
        ], onclick=lambda v, rid=r.id: _show_result_detail_by_id(ctx, rid), small=True)

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
    try:
        result = mgr.reload_all()
        reloaded = result.get("reloaded", 0)
        failed = result.get("failed", 0)

        if failed > 0:
            ctx["toast"](f"重载完成: {reloaded} 成功, {failed} 失败", color="warning")
        else:
            ctx["toast"](f"已重载 {reloaded} 个策略", color="success")
    except Exception as e:
        ctx["toast"](f"重载过程中出现错误: {str(e)}", color="error")
    finally:
        # 无论重载是否成功，都刷新策略列表页
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
    elif action == "open_experiment":
        run_async(_open_experiment_dialog(ctx, mgr))
    elif action == "close_experiment":
        _close_experiment_mode(ctx, mgr)


async def _open_experiment_dialog(ctx, mgr):
    """开启实验模式"""
    from ..datasource import get_datasource_manager

    entries = mgr.list_all()
    categories = _get_all_categories(entries)

    if not categories:
        ctx["toast"]("没有可用策略类别", color="warning")
        return

    ds_mgr = get_datasource_manager()
    ds_entries = ds_mgr.list_all()
    if not ds_entries:
        ctx["toast"]("没有可用数据源", color="warning")
        return

    default_categories = ["实验"] if "实验" in categories else []
    category_options = []
    for cat in categories:
        count = len([e for e in entries if getattr(e._metadata, "category", "默认") == cat])
        category_options.append({
            "label": f"{cat} ({count})",
            "value": cat,
            "selected": cat in default_categories,
        })

    ds_options = [{"label": ds.name, "value": ds.id} for ds in ds_entries]
    replay_ds = next((
        ds for ds in ds_entries
        if "回放" in ((getattr(ds, "name", "") or "").strip())
    ), None)
    default_ds_id = replay_ds.id if replay_ds else ds_entries[0].id

    form = await ctx["input_group"]("🧪 开启策略实验模式", [
        ctx["checkbox"]("策略类别（可逐项选择）", name="categories", options=category_options, value=default_categories),
        ctx["select"]("实验数据源", name="datasource_id", options=ds_options, value=default_ds_id),
        ctx["checkbox"]("包含注意力策略", name="include_attention", options=[
            {"label": "👁️ 同时运行注意力策略系统（5个策略）", "value": True, "selected": True}
        ], value=[True]),
        ctx["actions"]("操作", [
            {"label": "开启并启动策略", "value": "start"},
            {"label": "取消", "value": "cancel"},
        ], name="action"),
    ])

    if not form or form.get("action") == "cancel":
        return

    categories_selected = form.get("categories", []) or []
    datasource_id = form.get("datasource_id", "")
    include_attention = bool(form.get("include_attention", [True]))
    result = mgr.start_experiment(categories=categories_selected, datasource_id=datasource_id, include_attention=include_attention)

    if result.get("success"):
        if result.get("datasource_started"):
            ds_name = result.get("datasource_name", "实验数据源")
            ctx["toast"](f"已自动启动数据源：{ds_name}", color="info")
        failed_switch = len(result.get("failed_switch", []))
        failed_start = len(result.get("failed_start", []))
        
        # 构建成功消息
        msg_parts = []
        if result.get("target_count", 0) > 0:
            msg_parts.append(f"原有策略 {result['target_count']} 个")
        if result.get("include_attention"):
            msg_parts.append(f"注意力策略 5 个")
        
        msg = "实验模式已开启"
        if msg_parts:
            msg += "：" + "、".join(msg_parts)
        
        if failed_switch or failed_start:
            ctx["toast"](f"{msg}，切换失败 {failed_switch} 个，启动失败 {failed_start} 个", color="warning")
        else:
            ctx["toast"](msg, color="success")
        _render_strategy_content(ctx)
        return

    ctx["toast"](f"开启失败: {result.get('error', 'unknown error')}", color="error")


def _close_experiment_mode(ctx, mgr):
    """关闭实验模式并恢复策略配置"""
    result = mgr.stop_experiment()
    if result.get("success"):
        # 构建详细的恢复信息
        restored_bind = result.get("restored_bind_count", 0)
        restored_state = result.get("restored_state_count", 0)
        restored_output = result.get("restored_output_count", 0)
        restored_params = result.get("restored_params_count", 0)
        restored_window = result.get("restored_window_count", 0)
        
        detail_parts = []
        if restored_output > 0:
            detail_parts.append(f"输出配置({restored_output})")
        if restored_params > 0:
            detail_parts.append(f"策略参数({restored_params})")
        if restored_window > 0:
            detail_parts.append(f"窗口配置({restored_window})")
        
        detail_str = "、" + "、".join(detail_parts) if detail_parts else ""
        ctx["toast"](f"实验模式已关闭，策略已恢复：数据源绑定({restored_bind})、运行状态({restored_state}){detail_str}", color="success")
    else:
        ctx["toast"](f"关闭失败: {result.get('error', 'unknown error')}", color="error")
    _render_strategy_content(ctx)


def _show_result_detail_by_id(ctx, result_id: str):
    """根据结果ID显示结果详情"""
    from .result_store import get_result_store
    store = get_result_store()
    result = store.get_by_id(result_id)

    if not result:
        ctx["toast"]("结果不存在", color="error")
        return

    with ctx["popup"](f"执行结果详情", size="large", closable=True):
        ctx["put_html"](render_detail_section("基本信息"))
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

        ctx["put_html"](render_detail_section("输入数据预览"))
        ctx["put_code"](result.input_preview, language="text")

        if result.success and result.output_full is not None:
            ctx["put_html"](render_detail_section("输出结果"))
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


# 存储已显示的策略结果 ID
_shown_strategy_result_ids = {}

# 自动刷新控制
_strategy_board_auto_refresh = True


def _set_strategy_board_auto_refresh(enabled: bool):
    """设置策略看板自动刷新状态"""
    global _strategy_board_auto_refresh
    _strategy_board_auto_refresh = enabled


def _is_strategy_board_auto_refresh_enabled() -> bool:
    """获取策略看板自动刷新状态"""
    return _strategy_board_auto_refresh


async def _auto_refresh_strategy_board(ctx: dict, strategy_id: str, strategy_name: str):
    """策略看板自动刷新后台任务"""
    import asyncio
    from pywebio.exceptions import SessionClosedException
    from .result_store import get_result_store
    from datetime import datetime
    
    await asyncio.sleep(3)
    
    # 记录上次查询的时间戳，用于增量查询
    last_query_time = None
    
    try:
        while True:
            # 增加刷新间隔到5秒
            await asyncio.sleep(5)
            
            if not _is_strategy_board_auto_refresh_enabled():
                continue
            
            try:
                # 检查会话是否已关闭
                if not ctx.get('session'):
                    break
                    
                # 尝试获取会话状态
                if hasattr(ctx.get('session'), 'closed') and ctx['session'].closed:
                    break
                    
                store = get_result_store()
                # 只查询最新的一条结果
                all_results = store.query(strategy_id=strategy_id, limit=1)
                
                # 按时间戳排序
                all_results.sort(key=lambda x: x.ts, reverse=True)
                
                # 只处理新结果（时间戳大于上次查询时间）
                if last_query_time and all_results:
                    if all_results[0].ts <= last_query_time:
                        # 没有新结果，只更新刷新时间
                        update_time_script = '''
                        <script>
                        (function() {
                            var now = new Date();
                            var timeStr = now.toLocaleString('zh-CN');
                            var element = document.getElementById('last-refresh-time');
                            if (element) {
                                element.textContent = '上次刷新: ' + timeStr;
                            }
                        })();
                        </script>
                        '''
                        try:
                            ctx["put_html"](update_time_script, scope="strategy_board")
                        except Exception:
                            # 会话已关闭，退出循环
                            break
                        continue
                
                # 更新上次查询时间
                if all_results:
                    last_query_time = all_results[0].ts
                
                global _shown_strategy_result_ids
                if strategy_id not in _shown_strategy_result_ids:
                    _shown_strategy_result_ids[strategy_id] = set()
                
                shown_ids = _shown_strategy_result_ids[strategy_id]
                new_results = []
                for r in all_results:
                    if r.id not in shown_ids and r.success:
                        new_results.append(r)
                        shown_ids.add(r.id)
                        
                        # 限制存储的结果ID数量，防止内存泄漏
                        if len(shown_ids) > 100:
                            old_ids = list(shown_ids)[:50]
                            for oid in old_ids:
                                shown_ids.discard(oid)
                
                # 处理新结果
                for r in new_results:
                    # 使用信号处理器生成详细内容
                    from ..signal.processor import get_signal_type, get_signal_detail, generate_expanded_content
                    icon, color, signal_label, importance = get_signal_type(r)
                    signal_detail = get_signal_detail(r)
                    expanded_content = generate_expanded_content(r, signal_detail)
                    
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
                    
                    # 构建更新脚本
                    update_script = f'''
                    <script>
                    (function() {{
                        var container = document.getElementById('strategy-board-container');
                        if (!container) return;
                        
                        // 更新刷新时间
                        var now = new Date();
                        var timeStr = now.toLocaleString('zh-CN');
                        var timeElement = document.getElementById('last-refresh-time');
                        if (timeElement) {{
                            timeElement.textContent = '上次刷新: ' + timeStr;
                        }}
                        
                        // 更新卡片内容
                        container.innerHTML = `
                            <div class="strategy-board-item" style="display:flex;flex-direction:column;padding:12px;margin:6px 0;{bg_style}
                                        border-radius:10px;border-left:{border_width} solid {color};
                                        box-shadow:0 2px 8px rgba(0,0,0,0.06);transition:all 0.2s ease;">
                                <div class="board-item-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                                    <div style="display:flex;align-items:center;gap:8px;">
                                        <span style="font-weight:600;color:#333;font-size:14px;">{r.strategy_name}</span>
                                        <span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;
                                                    background:{color}22;color:{color};">{signal_label}</span>
                                        <span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;
                                                    background:{'#dc354522' if importance == 'critical' else '#fd7e1422' if importance == 'high' else '#ffc10722' if importance == 'medium' else '#17a2b822'};
                                                    color:{'#dc3545' if importance == 'critical' else '#fd7e14' if importance == 'high' else '#ffc107' if importance == 'medium' else '#17a2b8'};
                                                {'重要' if importance == 'critical' else '关注' if importance == 'high' else '中等' if importance == 'medium' else '普通'}
                                        </span>
                                    </div>
                                    <div style="display:flex;align-items:center;gap:6px;">
                                        <span style="font-size:11px;color:#999;white-space:nowrap;">{time_str}</span>
                                    </div>
                                </div>
                                <div style="font-size:13px;color:#333;font-weight:500;margin-bottom:8px;">
                                    {signal_detail['summary']}
                                </div>
                                {'<div style="font-size:11px;color:#666;margin-bottom:8px;">'+ ' | '.join(signal_detail['highlights'][:4]) +'</div>' if signal_detail['highlights'] else ''}
                                <div class="board-item-detail" style="display:block;padding:8px 0 4px 0;">
                                    {expanded_content}
                                </div>
                            </div>
                        `;
                    }})();
                    </script>
                    '''
                    
                    try:
                        ctx["put_html"](update_script, scope="strategy_board")
                        # 稍微延迟，避免DOM操作过于集中
                        await asyncio.sleep(0.1)
                    except Exception:
                        # 会话已关闭，退出循环
                        break
                    
            except SessionClosedException:
                # 会话已关闭，退出循环
                break
            except Exception as e:
                # 记录异常但不中断循环
                import traceback
                traceback.print_exc()
                await asyncio.sleep(1)
    finally:
        # 清理资源
        if strategy_id in _shown_strategy_result_ids:
            del _shown_strategy_result_ids[strategy_id]





async def _show_strategy_board(ctx: dict, mgr, entry_id: str):
    """显示策略看板"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("策略不存在", color="error")
        return

    from .result_store import get_result_store
    store = get_result_store()
    recent_results = store.query(strategy_id=entry_id, limit=1)
    
    # 按时间戳排序
    recent_results.sort(key=lambda x: x.ts, reverse=True)

    with ctx["popup"](f"{entry.name}看板", size="large", closable=True):
        apply_strategy_like_styles(ctx, scope=None, include_compact_table=False, include_category_tabs=False)
        
        # 渲染看板标题和控制栏
        ctx["put_html"]("""
        <div style="margin:16px 0 12px 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
            <div style="font-size:18px;font-weight:600;color:#333;">📈 策略实时结果</div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;">
                    <input type="checkbox" id="board_auto_refresh_checkbox" checked onchange="toggleBoardAutoRefresh(this.checked)" style="cursor:pointer;">
                    <span style="font-size:11px;color:#666;">🔄 自动刷新</span>
                </label>
                <div id="last-refresh-time" style="font-size:11px;color:#999;">上次刷新: -</div>
            </div>
        </div>
        """)
        
        if not recent_results:
            ctx["put_html"](
                '<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无执行结果</div>')
            return
        
        # 只显示最新的一条结果
        r = recent_results[0]
        if not r.success:
            ctx["put_html"](
                '<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无成功的执行结果</div>')
            return
            
        from datetime import datetime
        time_str = datetime.fromtimestamp(r.ts).strftime("%H:%M:%S")
        time_full = datetime.fromtimestamp(r.ts).strftime("%Y-%m-%d %H:%M:%S")
        
        # 使用信号处理器生成详细内容
        from ..signal.processor import get_signal_detail, generate_expanded_content
        detail = get_signal_detail(r)
        expanded_content = generate_expanded_content(r, detail)

        # 使用信号处理器获取信号类型和详细信息
        from ..signal.processor import get_signal_type, get_signal_detail
        icon, color, signal_label, importance = get_signal_type(r)
        signal_detail = get_signal_detail(r)
        
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
        
        # 渲染结果容器和脚本
        signal_highlights_html = '<div style="font-size:11px;color:#666;margin-bottom:8px;">'+ ' | '.join(signal_detail['highlights'][:4]) +'</div>' if signal_detail['highlights'] else ''
        board_container = f"""
        <style>
            .strategy-board-item:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,0.12) !important; }}
            .board-item-detail {{ animation: fadeIn 0.2s ease; }}
            @keyframes fadeIn {{
                from {{ opacity: 0; }}
                to {{ opacity: 1; }}
            }}
        </style>
        <script>
        function toggleBoardAutoRefresh(enabled) {{
            pywebio.run_async(function() {{
                pywebio.call('set_strategy_board_auto_refresh', [enabled]);
            }});
        }}
        
        function updateLastRefreshTime() {{
            var now = new Date();
            var timeStr = now.toLocaleString('zh-CN');
            var element = document.getElementById('last-refresh-time');
            if (element) {{
                element.textContent = '上次刷新: ' + timeStr;
            }}
        }}
        
        // 初始更新刷新时间
        updateLastRefreshTime();
        </script>
        <div id="strategy-board-container" style="padding:12px;background:#f5f7fa;border-radius:12px;">
            <div class="strategy-board-item" style="display:flex;flex-direction:column;padding:12px;margin:6px 0;{bg_style}
                        border-radius:10px;border-left:{border_width} solid {color};
                        box-shadow:0 2px 8px rgba(0,0,0,0.06);transition:all 0.2s ease;">
                <div class="board-item-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span style="font-weight:600;color:#333;font-size:14px;">{r.strategy_name}</span>
                        <span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;
                                    background:{color}22;color:{color};">{signal_label}</span>
                        <span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;
                                    background:{'#dc354522' if importance == 'critical' else '#fd7e1422' if importance == 'high' else '#ffc10722' if importance == 'medium' else '#17a2b822'};
                                    color:{'#dc3545' if importance == 'critical' else '#fd7e14' if importance == 'high' else '#ffc107' if importance == 'medium' else '#17a2b8'};">
                            {'重要' if importance == 'critical' else '关注' if importance == 'high' else '中等' if importance == 'medium' else '普通'}
                        </span>
                    </div>
                    <div style="display:flex;align-items:center;gap:6px;">
                        <span style="font-size:11px;color:#999;white-space:nowrap;">{time_str}</span>
                    </div>
                </div>
                <div style="font-size:13px;color:#333;font-weight:500;margin-bottom:8px;">
                    {signal_detail['summary']}
                </div>
                {signal_highlights_html}
                <div class="board-item-detail" style="display:block;padding:8px 0 4px 0;">
                    {expanded_content}
                </div>
            </div>
        </div>
        """
        
        from pywebio.output import use_scope
        with use_scope("strategy_board", clear=True):
            ctx["put_html"](board_container)
        
        # 初始化已显示的结果ID
        global _shown_strategy_result_ids
        _shown_strategy_result_ids[entry_id] = set()
        _shown_strategy_result_ids[entry_id].add(r.id)
        
        # 启动自动刷新任务
        from pywebio.session import run_async
        run_async(_auto_refresh_strategy_board(ctx, entry_id, entry.name))


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
    elif action_type == "board":
        run_async(_show_strategy_board(ctx, mgr, entry_id))
        return
    elif action_type == "delete":
        mgr.delete(entry_id)
        ctx["toast"]("已删除", color="error")
        ctx["close_popup"]()

    _render_strategy_content(ctx)


async def _show_strategy_detail(ctx: dict, mgr, entry_id: str):
    """显示策略详情"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("策略不存在", color="error")
        return

    # 获取多数据源绑定列表
    bound_datasource_ids = getattr(entry._metadata, "bound_datasource_ids", [])
    if not bound_datasource_ids:
        # 兼容旧版本单数据源
        bound_ds_id = getattr(entry._metadata, "bound_datasource_id", "")
        if bound_ds_id:
            bound_datasource_ids = [bound_ds_id]

    # 构建数据源名称列表
    if bound_datasource_ids:
        from ..datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        ds_names = []
        for ds_id in bound_datasource_ids:
            ds = ds_mgr.get(ds_id)
            if ds:
                ds_names.append(f"{ds.name} ({ds_id[:8]}...)")
            else:
                ds_names.append(ds_id[:12])
        bound_ds_display = "\n".join([f"• {name}" for name in ds_names]) if ds_names else "-"
    else:
        bound_ds_display = "-"

    with ctx["popup"](f"策略详情: {entry.name}", size="large", closable=True):
        # 计算 state_persist 状态
        state_persist = False
        try:
            cfg = getattr(entry._metadata, "strategy_config", {}) or {}
            state_persist = bool(cfg.get("state_persist", False))
        except Exception:
            state_persist = False
        
        strategy_type = getattr(entry._metadata, "strategy_type", "legacy") or "legacy"
        is_running = entry.is_running
        
        type_colors = {
            "legacy": {"bg": "#f1f5f9", "color": "#64748b"},
            "declarative": {"bg": "#e0f2fe", "color": "#0284c7"},
            "river": {"bg": "#dcfce7", "color": "#16a34a"},
            "plugin": {"bg": "#ede9fe", "color": "#7c3aed"},
        }
        type_style = type_colors.get(strategy_type, type_colors["legacy"])
        
        # 紧凑顶部栏
        ctx["put_html"](f"""
        <div style="margin-bottom:12px;padding:10px 14px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
            <div style="display:flex;align-items:center;gap:10px;">
                <span style="font-size:16px;font-weight:600;color:#1e293b;">{entry.name}</span>
                <span style="background:{type_style['bg']};color:{type_style['color']};padding:2px 6px;border-radius:4px;font-size:11px;font-weight:500;">{strategy_type.upper()}</span>
                <span style="font-size:11px;color:#64748b;">{getattr(entry._metadata, "compute_mode", "record")}</span>
            </div>
            <div style="display:flex;align-items:center;gap:10px;">
                <span style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;background:{"#dcfce7" if is_running else "#f3f4f6"};color:{"#22c55e" if is_running else "#9ca3af"};border-radius:12px;font-size:11px;font-weight:500;">
                    {"●" if is_running else "○"} {"运行中" if is_running else "已停止"}
                </span>
                <span style="font-size:11px;color:#64748b;">{entry._state.processed_count}次</span>
            </div>
        </div>
        """)
        
        # 紧凑二列布局：基本信息 + 执行统计
        ctx["put_html"]('<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">')
        
        # 左侧：关键信息
        ctx["put_html"](f"""
        <div style="background:#fff;padding:12px;border-radius:8px;border:1px solid #e5e7eb;font-size:11px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
                <div><span style="color:#64748b;">窗口:</span> <span style="color:#1e293b;">{getattr(entry._metadata, "window_size", 5)}</span></div>
                <div><span style="color:#64748b;">历史:</span> <span style="color:#1e293b;">{getattr(entry._metadata, "max_history_count", 100)}</span></div>
                <div><span style="color:#64748b;">持久化:</span> <span style="color:{"#22c55e" if state_persist else "#9ca3af"};">{"开" if state_persist else "关"}</span></div>
                <div><span style="color:#64748b;">输出:</span> <span style="color:#1e293b;">{entry._state.output_count}</span></div>
                <div><span style="color:#64748b;">错误:</span> <span style="color:{"#ef4444" if entry._state.error_count > 0 else "#1e293b"};">{entry._state.error_count}</span></div>
                <div><span style="color:#64748b;">最后:</span> <span style="color:#1e293b;">{format_timestamp(entry._state.last_process_ts) if entry._state.last_process_ts > 0 else "-"}</span></div>
            </div>
        </div>
        """)
        
        # 错误信息 + 最新正确信息并排显示
        try:
            recent_results = entry.get_recent_results(limit=2)
            has_error = entry._state.error_count > 0 and entry._state.last_error
            has_success = any(r.get("success") for r in recent_results if r.get("success"))
            
            if has_error or has_success:
                ctx["put_html"]('<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;">')
                
                # 错误信息 - 红色背景
                if has_error and entry._state.last_error:
                    ctx["put_html"](f'''
                    <div style="padding:8px;background:#fef2f2;border-radius:6px;border:1px solid #fecaca;">
                        <div style="font-size:10px;font-weight:600;color:#dc2626;margin-bottom:4px;">❌ 最新错误</div>
                        <div style="font-size:10px;color:#991b1b;">{entry._state.last_error or ""}</div>
                        <div style="font-size:9px;color:#f87171;margin-top:4px;">{format_timestamp(entry._state.last_error_ts) if entry._state.last_error_ts > 0 else ""}</div>
                    </div>
                    ''')
                
                # 最新正确信息 - 绿色背景
                success_result = next((r for r in recent_results if r.get("success")), None)
                if success_result:
                    ctx["put_html"](f'''
                    <div style="padding:8px;background:#f0fdf4;border-radius:6px;border:1px solid #bbf7d0;">
                        <div style="font-size:10px;font-weight:600;color:#16a34a;margin-bottom:4px;">✅ 最新成功</div>
                        <div style="font-size:10px;color:#166534;">{(success_result.get("output_preview") or "-")[:60]}</div>
                        <div style="font-size:9px;color:#4ade80;margin-top:4px;">{success_result.get("ts_readable", "")[:19] if success_result.get("ts_readable") else ""}</div>
                    </div>
                    ''')
                
                ctx["put_html"]('</div>')
        except Exception:
            pass
        
        # 右侧：数据源
        ctx["put_html"](f"""
        <div style="background:#fff;padding:12px;border-radius:8px;border:1px solid #e5e7eb;font-size:11px;">
            <div style="font-weight:600;color:#1e293b;margin-bottom:6px;">🔗 数据源</div>
            <div style="color:#64748b;line-height:1.6;">{bound_ds_display.replace(chr(10), '<br>').replace('• ', '• ') if bound_ds_display != '-' else '<span style="color:#9ca3af;">未绑定</span>'}</div>
        </div>
        """)
        ctx["put_html"]('</div>')
        
        dict_ids = getattr(entry._metadata, "dictionary_profile_ids", [])
        if dict_ids:
            ctx["put_html"](f'<div style="margin-bottom:12px;font-size:11px;"><span style="color:#64748b;">📖 字典:</span> <span style="color:#1e293b;">{", ".join(dict_ids)}</span></div>')

        # AI调节历史 - 提前到更前面
        try:
            llm_rows = _get_llm_adjustments(entry, limit=5)
            if llm_rows:
                ctx["put_html"]('<div style="margin-top:12px;">')
                ctx["put_collapse"](f"🤖 AI调节 ({len(llm_rows)}条)", [
                    ctx["put_table"](llm_rows, header=["时间", "摘要", "动作"])
                ])
                ctx["put_html"]('</div>')
        except Exception:
            pass

        # 策略详解 - 直接调用（内部已处理空数据情况）
        _render_strategy_diagram_section(ctx, entry)

        # 代码区块 - 折叠显示
        strategy_config = getattr(entry._metadata, "strategy_config", {}) or {}
        display_code = entry.func_code
        if not display_code and strategy_type in ("declarative", "river", "plugin"):
            logic_config = strategy_config.get("logic", {})
            display_code = logic_config.get("code", "")
        
        code_char_count = len(display_code) if display_code else 0
        ctx["put_collapse"](f"💻 代码 {f'({strategy_type.upper()})' if strategy_type != 'legacy' else ''} [{code_char_count}字符]", [
            ctx["put_code"](display_code[:2000], language="python") if display_code else ctx["put_html"]('<div style="color:#9ca3af;font-size:11px;">暂无代码</div>')
        ])

        # 配置折叠
        config = getattr(entry._metadata, "strategy_config", {}) or {}
        params = getattr(entry._metadata, "strategy_params", {}) or {}
        if params:
            config = dict(config)
            config["params"] = {**(config.get("params", {}) or {}), **params}
        
        if config:
            ctx["put_collapse"](f"🧩 配置 ({len(json.dumps(config))//512 + 1}KB)", [
                ctx["put_code"](json.dumps(config, ensure_ascii=False, indent=2), language="json")
            ])

        # 执行结果 - 紧凑
        try:
            recent_results = entry.get_recent_results(limit=5)
            if recent_results:
                ctx["put_html"]('<div style="margin-top:12px;">')
                ctx["put_html"]('<div style="font-size:12px;font-weight:600;color:#1e293b;margin-bottom:8px;">📜 最近结果</div>')
                result_table = [["时间", "状态", "耗时", "预览"]]
                for r in recent_results:
                    status = "✅" if r.get("success") else "❌"
                    preview = (r.get("output_preview", "") or r.get("error", ""))[:30]
                    result_table.append([
                        r.get("ts_readable", "")[:12] if r.get("ts_readable") else "-",
                        status,
                        f"{r.get('process_time_ms', 0):.0f}ms",
                        preview + "..." if len(preview) >= 30 else preview
                    ])
                ctx["put_table"](result_table)
                ctx["put_html"]('</div>')
        except Exception:
            pass

        # 操作按钮
        ctx["put_html"]("<div style='margin-top:16px;text-align:center;'>")
        ctx["put_buttons"]([
            {"label": "🗑️ 删除", "value": f"delete_{entry.id}", "color": "danger"},
        ], onclick=lambda v, m=mgr, c=ctx: _handle_strategy_action(v, m, c))
        ctx["put_html"]("</div>")


def _show_result_detail(ctx: dict, entry, result_id: str):
    """显示执行结果详情"""
    from .result_store import get_result_store
    store = get_result_store()
    result = store.get_by_id(result_id)

    if not result:
        ctx["toast"]("结果不存在", color="error")
        return

    with ctx["popup"](f"执行结果详情", size="large", closable=True):
        ctx["put_html"](render_detail_section("基本信息"))
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

        ctx["put_html"](render_detail_section("输入数据预览"))
        ctx["put_code"](result.input_preview, language="text")

        if result.success and result.output_full is not None:
            ctx["put_html"](render_detail_section("输出结果"))
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

    # 构建数据源选项（用于checkbox）
    source_options = []
    for ds in ds_mgr.list_all():
        source_options.append({"label": f"{ds.name} ({ds.id[:8]}...)", "value": ds.id})

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
        
        # 先获取输出目标配置（在 popup 里面，表单之前）
        from .output_controller import get_output_controller
        output_ctrl = get_output_controller()
        current_config = output_ctrl.get_config(entry_id)
        
        # 显示输出目标配置
        ctx["put_html"]("""
        <div style="margin-bottom:15px;padding:12px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;">
            <div style="font-weight:600;color:#334155;margin-bottom:10px;">📤 输出目标配置</div>
            <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:8px;">
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_signal" """ + ("checked" if current_config.signal else "") + """ style="width:16px;height:16px;">
                    <span style="font-size:13px;">💰 信号流</span>
                    <span style="font-size:11px;color:#64748b;">(存储)</span>
                </label>
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_radar" """ + ("checked" if current_config.radar else "") + """ style="width:16px;height:16px;">
                    <span style="font-size:13px;">📡 雷达</span>
                    <span style="font-size:11px;color:#f59e0b;">(技术)</span>
                </label>
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_memory" """ + ("checked" if current_config.memory else "") + """ style="width:16px;height:16px;">
                    <span style="font-size:13px;">🧠 记忆</span>
                    <span style="font-size:11px;color:#8b5cf6;">(叙事)</span>
                </label>
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_bandit" """ + ("checked" if current_config.bandit else "") + """ style="width:16px;height:16px;">
                    <span style="font-size:13px;">🎰 Bandit</span>
                    <span style="font-size:11px;color:#f43f5e;">(交易)</span>
                </label>
            </div>
            
            <!-- 输出结构规范说明 -->
            <div style="margin-top:12px;padding-top:12px;border-top:1px solid #e2e8f0;">
                <div style="font-size:11px;color:#64748b;margin-bottom:8px;">📋 输出结构规范（开启目标后需按此结构输出）</div>
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:10px;">
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #f5576c;">
                        <div style="font-weight:600;color:#f5576c;margin-bottom:4px;">💰 信号流</div>
                        <div style="color:#666;">输出所有结果</div>
                        <div style="color:#999;">任意格式均支持</div>
                    </div>
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #f59e0b;">
                        <div style="font-weight:600;color:#f59e0b;margin-bottom:4px;">📡 雷达</div>
                        <div style="color:#666;">signal_type, score</div>
                        <div style="color:#999;">例: fast_anomaly</div>
                    </div>
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #8b5cf6;">
                        <div style="font-weight:600;color:#8b5cf6;margin-bottom:4px;">🧠 记忆</div>
                        <div style="color:#666;">content 必需</div>
                        <div style="color:#999;">topic, sentiment</div>
                    </div>
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #f43f5e;grid-column:span 3;">
                        <div style="font-weight:600;color:#f43f5e;margin-bottom:4px;">🎰 Bandit</div>
                        <div style="color:#666;">signal_type(BUY/SELL), stock_code, price</div>
                        <div style="color:#999;">confidence, amount, reason 可选</div>
                    </div>
                </div>
            </div>
        </div>
        """)
        
        compute_mode = getattr(entry._metadata, "compute_mode", "record")
        window_type = getattr(entry._metadata, "window_type", "sliding")
        window_return_partial = getattr(entry._metadata, "window_return_partial", False)
        strategy_type = getattr(entry._metadata, "strategy_type", "legacy") or "legacy"
        strategy_config = getattr(entry._metadata, "strategy_config", {}) or {}
        strategy_params = getattr(entry._metadata, "strategy_params", {}) or {}
        config_json = json.dumps(strategy_config, ensure_ascii=False, indent=2) if strategy_config else json.dumps(DEFAULT_DECLARATIVE_CONFIG, ensure_ascii=False, indent=2)
        params_json = json.dumps(strategy_params, ensure_ascii=False, indent=2) if strategy_params else "{}"
        param_help = strategy_config.get("param_help", {}) if isinstance(strategy_config, dict) else {}
        # 支持多数据源绑定
        bound_datasource_ids = getattr(entry._metadata, "bound_datasource_ids", [])
        if not bound_datasource_ids:
            # 兼容旧版本单数据源
            bound_datasource_id = getattr(entry._metadata, "bound_datasource_id", "")
            if bound_datasource_id:
                bound_datasource_ids = [bound_datasource_id]
        dictionary_profile_ids = getattr(entry._metadata, "dictionary_profile_ids", [])

        if param_help:
            ctx["put_html"](
                "<div style='margin:0 0 8px 0; color:#64748b; font-size:12px;'>"
                "<div style='font-weight:600; color:#475569; margin-bottom:4px;'>参数说明</div>"
                + "".join([f"<div><code>{k}</code>：{v}</div>" for k, v in param_help.items()])
                + "</div>"
            )

        ctx["put_html"]("""
        <div style="margin:0 0 15px 0;padding:10px 12px;background:#f8fafc;border-radius:6px;border:1px solid #e2e8f0;font-size:12px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                <div><b style="color:#6366f1;">legacy</b> - 传统代码模式，编写 Python process 函数处理数据</div>
                <div><b style="color:#10b981;">river</b> - 使用 River 机器学习库，适合在线学习/预测场景</div>
                <div><b style="color:#f59e0b;">declarative</b> - 声明式配置，通过 pipeline/model/logic 定义处理流程</div>
                <div><b style="color:#ec4899;">plugin</b> - 插件模式，通过类路径加载自定义策略实现</div>
            </div>
        </div>
        """)

        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("名称", name="name", required=True, value=entry.name),
            ctx["textarea"]("描述", name="description", rows=2,
                            value=getattr(entry._metadata, "description", "") or ""),
            ctx["select"]("类别", name="category_select", options=category_options, value=current_category),
            ctx["input"]("新类别名称", name="category_new", placeholder="输入新类别名称（如选择新建类别）"),
            ctx["checkbox"]("绑定数据源", name="datasource_ids", options=source_options,
                            value=bound_datasource_ids),
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
            ctx["select"]("策略类型", name="strategy_type", options=[
                {"label": "legacy（代码）", "value": "legacy"},
                {"label": "river", "value": "river"},
                {"label": "declarative（声明式）", "value": "declarative"},
                {"label": "plugin", "value": "plugin"},
            ], value=strategy_type),
            ctx["textarea"]("结构化配置(JSON)", name="strategy_config_json",
                            value=config_json, rows=8,
                            code={"mode": "application/json", "theme": "darcula"}),
            ctx["textarea"]("可调参数(JSON)", name="strategy_params_json",
                            value=params_json, rows=6,
                            code={"mode": "application/json", "theme": "darcula"}),
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

            # 获取多数据源绑定列表
            datasource_ids = form.get("datasource_ids", [])
            # 兼容处理：如果是字符串（单选情况），转换为列表
            if isinstance(datasource_ids, str):
                datasource_ids = [datasource_ids] if datasource_ids else []

            stype = str(form.get("strategy_type") or "legacy").strip().lower()
            config_text = (form.get("strategy_config_json") or "").strip()
            params_text = (form.get("strategy_params_json") or "").strip()
            try:
                strategy_config = json.loads(config_text) if config_text else {}
            except Exception:
                ctx["toast"]("结构化配置 JSON 解析失败", color="error")
                return
            try:
                strategy_params = json.loads(params_text) if params_text else {}
            except Exception:
                ctx["toast"]("可调参数 JSON 解析失败", color="error")
                return

            if stype == "declarative" and not strategy_config:
                strategy_config = DEFAULT_DECLARATIVE_CONFIG.copy()

            if stype == "declarative":
                logic = dict(strategy_config.get("logic") or {})
                if form.get("code") and (not logic or str(logic.get("type", "")).lower() == "python"):
                    logic["type"] = "python"
                    logic["code"] = form.get("code")
                    strategy_config["logic"] = logic
            
            result = entry.update_config(
                name=form["name"].strip(),
                description=form.get("description", "").strip(),
                bound_datasource_id=datasource_ids[0] if datasource_ids else "",  # 兼容单数据源
                bound_datasource_ids=datasource_ids,  # 多数据源
                dictionary_profile_ids=form.get("dictionary_profile_ids", []),
                compute_mode=form.get("compute_mode"),
                window_type=form.get("window_type"),
                window_size=int(form.get("window_size", 5)),
                window_interval=form.get("window_interval", "10s"),
                window_return_partial=form_window_return_partial,
                max_history_count=int(form.get("max_history_count", 100)),
                func_code=form.get("code") if stype == "legacy" else "",
                category=category,
                strategy_type=stype,
                strategy_config=strategy_config,
                strategy_params=strategy_params,
            )

            # 保存输出目标配置
            try:
                from .output_controller import get_output_controller
                output_ctrl = get_output_controller()
                output_ctrl.update_targets(
                    entry_id,
                    signal=form.get("output_signal", True),
                    radar=form.get("output_radar", True),
                    memory=form.get("output_memory", True),
                    bandit=form.get("output_bandit", False),
                )
            except Exception as e:
                print(f"保存输出配置失败: {e}")

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

    # 构建数据源选项（用于checkbox）
    source_options = []
    for ds in ds_mgr.list_all():
        source_options.append({"label": f"{ds.name} ({ds.id[:8]}...)", "value": ds.id})

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
        ctx["put_html"]("""
        <div style="margin:0 0 15px 0;padding:10px 12px;background:#f8fafc;border-radius:6px;border:1px solid #e2e8f0;font-size:12px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                <div><b style="color:#6366f1;">legacy</b> - 传统代码模式，编写 Python process 函数处理数据</div>
                <div><b style="color:#10b981;">river</b> - 使用 River 机器学习库，适合在线学习/预测场景</div>
                <div><b style="color:#f59e0b;">declarative</b> - 声明式配置，通过 pipeline/model/logic 定义处理流程</div>
                <div><b style="color:#ec4899;">plugin</b> - 插件模式，通过类路径加载自定义策略实现</div>
            </div>
        </div>
        """)

        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("名称", name="name", required=True, placeholder="输入策略名称"),
            ctx["textarea"]("描述", name="description", rows=2, placeholder="策略描述（可选）"),
            ctx["select"]("类别", name="category_select", options=category_options, value="默认"),
            ctx["input"]("新类别名称", name="category_new", placeholder="输入新类别名称（如选择新建类别）"),
            ctx["checkbox"]("绑定数据源", name="datasource_ids", options=source_options, value=[]),
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
            ctx["select"]("策略类型", name="strategy_type", options=[
                {"label": "legacy（代码）", "value": "legacy"},
                {"label": "river", "value": "river"},
                {"label": "declarative（声明式）", "value": "declarative"},
                {"label": "plugin", "value": "plugin"},
            ], value="legacy"),
            ctx["textarea"]("结构化配置(JSON)", name="strategy_config_json",
                            value=json.dumps(DEFAULT_DECLARATIVE_CONFIG, ensure_ascii=False, indent=2),
                            rows=8, code={"mode": "application/json", "theme": "darcula"}),
            ctx["textarea"]("可调参数(JSON)", name="strategy_params_json",
                            value="{}", rows=6, code={"mode": "application/json", "theme": "darcula"}),
            ctx["textarea"]("代码", name="code",
                            value=DEFAULT_STRATEGY_CODE,
                            rows=14,
                            code={"mode": "python", "theme": "darcula"}),
        ])

        # 添加输出目标配置（创建时默认全部开启信号）
        ctx["put_html"]("""
        <div style="margin:15px 0;padding:12px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;">
            <div style="font-weight:600;color:#334155;margin-bottom:10px;">📤 输出目标配置</div>
            <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:8px;">
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_signal" checked style="width:16px;height:16px;">
                    <span style="font-size:13px;">📡 信号流</span>
                    <span style="font-size:11px;color:#64748b;">(存储)</span>
                </label>
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_radar" checked style="width:16px;height:16px;">
                    <span style="font-size:13px;">📡 雷达</span>
                    <span style="font-size:11px;color:#f59e0b;">(技术)</span>
                </label>
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_memory" checked style="width:16px;height:16px;">
                    <span style="font-size:13px;">🧠 记忆</span>
                    <span style="font-size:11px;color:#8b5cf6;">(叙事)</span>
                </label>
                <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
                    <input type="checkbox" name="output_bandit" style="width:16px;height:16px;">
                    <span style="font-size:13px;">🎰 Bandit</span>
                    <span style="font-size:11px;color:#f43f5e;">(交易)</span>
                </label>
            </div>
            <div style="font-size:11px;color:#94a3b8;">
                新策略默认开启信号流、雷达、记忆输出。Bandit 交易需要手动开启。
            </div>
            
            <!-- 输出结构规范说明 -->
            <div style="margin-top:12px;padding-top:12px;border-top:1px solid #e2e8f0;">
                <div style="font-size:11px;color:#64748b;margin-bottom:8px;">📋 输出结构规范</div>
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:10px;">
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #f5576c;">
                        <div style="font-weight:600;color:#f5576c;margin-bottom:4px;">💰 信号流</div>
                        <div style="color:#666;">输出所有结果</div>
                        <div style="color:#999;">任意格式均支持</div>
                    </div>
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #f59e0b;">
                        <div style="font-weight:600;color:#f59e0b;margin-bottom:4px;">📡 雷达</div>
                        <div style="color:#666;">signal_type, score</div>
                        <div style="color:#999;">例: fast_anomaly</div>
                    </div>
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #8b5cf6;">
                        <div style="font-weight:600;color:#8b5cf6;margin-bottom:4px;">🧠 记忆</div>
                        <div style="color:#666;">content 必需</div>
                        <div style="color:#999;">topic, sentiment</div>
                    </div>
                    <div style="background:#fff;padding:8px;border-radius:6px;border:1px solid #f43f5e;grid-column:span 3;">
                        <div style="font-weight:600;color:#f43f5e;margin-bottom:4px;">🎰 Bandit</div>
                        <div style="color:#666;">signal_type(BUY/SELL), stock_code, price</div>
                        <div style="color:#999;">confidence, amount, reason 可选</div>
                    </div>
                </div>
            </div>
        </div>
        """)

        form = await ctx["input_group"]("确认", [
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

            # 获取多数据源绑定列表
            datasource_ids = form.get("datasource_ids", [])
            # 兼容处理：如果是字符串（单选情况），转换为列表
            if isinstance(datasource_ids, str):
                datasource_ids = [datasource_ids] if datasource_ids else []

            stype = str(form.get("strategy_type") or "legacy").strip().lower()
            config_text = (form.get("strategy_config_json") or "").strip()
            params_text = (form.get("strategy_params_json") or "").strip()
            try:
                strategy_config = json.loads(config_text) if config_text else {}
            except Exception:
                ctx["toast"]("结构化配置 JSON 解析失败", color="error")
                return
            try:
                strategy_params = json.loads(params_text) if params_text else {}
            except Exception:
                ctx["toast"]("可调参数 JSON 解析失败", color="error")
                return

            if stype == "declarative" and not strategy_config:
                strategy_config = DEFAULT_DECLARATIVE_CONFIG.copy()

            if stype == "declarative":
                logic = dict(strategy_config.get("logic") or {})
                if form.get("code") and (not logic or str(logic.get("type", "")).lower() == "python"):
                    logic["type"] = "python"
                    logic["code"] = form.get("code")
                    strategy_config["logic"] = logic

            result = mgr.create(
                name=form["name"].strip(),
                func_code=form.get("code", "") if stype == "legacy" else "",
                description=form.get("description", "").strip(),
                bound_datasource_id=datasource_ids[0] if datasource_ids else "",  # 兼容单数据源
                bound_datasource_ids=datasource_ids,  # 多数据源
                dictionary_profile_ids=form.get("dictionary_profile_ids", []),
                compute_mode=form.get("compute_mode", "record"),
                window_type=form.get("window_type", "sliding"),
                window_size=int(form.get("window_size", 5)),
                window_interval=form.get("window_interval", "10s"),
                window_return_partial=window_return_partial,
                max_history_count=int(form.get("max_history_count", 100)),
                category=category,
                strategy_type=stype,
                strategy_config=strategy_config,
                strategy_params=strategy_params,
            )

            # 创建成功后设置默认输出目标配置
            if result.get("success"):
                try:
                    from .output_controller import get_output_controller
                    output_ctrl = get_output_controller()
                    # 新策略默认开启：信号流、雷达、记忆
                    strategy_id = result.get("strategy_id", "")
                    if strategy_id:
                        output_ctrl.update_targets(
                            strategy_id,
                            signal=True,
                            radar=True,
                            memory=True,
                            bandit=False
                        )
                except Exception:
                    pass

                ctx["toast"]("创建成功", color="success")
                ctx["close_popup"]()
                _render_strategy_content(ctx)
            else:
                ctx["toast"](f"创建失败: {result.get('error')}", color="error")


def _render_river_metaphor_section(ctx: dict, river_metaphor: dict, color: str):
    """渲染河流比喻部分"""
    title = river_metaphor.get("title", "�� 河流比喻")
    description = river_metaphor.get("description", "")
    elements = river_metaphor.get("elements", {})
    process = river_metaphor.get("process", [])
    
    # 生成元素 HTML
    elements_html = ""
    for key, value in elements.items():
        elements_html += f'''<div style="padding:8px 12px;background:#f8f9fa;border-radius:6px;margin-bottom:6px;"><span style="font-weight:600;color:{color};">{key}</span><span style="color:#666;margin-left:8px;">{value}</span></div>'''
    
    # 生成流程 HTML
    process_html = ""
    for step in process:
        process_html += f'''<div style="padding:6px 0;color:#555;font-size:13px;border-left:2px solid {color};padding-left:12px;margin-bottom:4px;">{step}</div>'''
    
    ctx["put_html"](f'''<div style="background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);overflow:hidden;border:1px solid #eee;margin-bottom:15px;"><div style="background:linear-gradient(135deg,{color} 0%,{color}dd 100%);padding:12px 20px;color:white;"><div style="font-size:16px;font-weight:600;">{title}</div><div style="font-size:12px;opacity:0.9;margin-top:4px;">{description}</div></div><div style="padding:20px;"><div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;"><div><div style="font-weight:600;color:#333;margin-bottom:10px;">🏞️ 河流元素</div><div style="background:#f8f9fa;padding:12px;border-radius:8px;">{elements_html}</div></div><div><div style="font-weight:600;color:#333;margin-bottom:10px;">🔄 处理流程</div><div style="background:#f8f9fa;padding:12px;border-radius:8px;">{process_html}</div></div></div></div></div>''')


def _get_llm_adjustments(entry, limit: int = 10):
    """获取与该策略相关的 LLM 调节历史"""
    try:
        from deva import NB
        db = NB("naja_llm_decisions")
        items = []
        for _, value in list(db.items()):
            if not isinstance(value, dict):
                continue
            actions = value.get("actions", []) or []
            matched_actions = []
            for action in actions:
                if not isinstance(action, dict):
                    continue
                target = str(action.get("strategy", "") or "")
                if target == entry.id or target == entry.name:
                    matched_actions.append(action)
            if matched_actions:
                items.append((value, matched_actions))

        items.sort(key=lambda x: float(x[0].get("timestamp", 0) or 0), reverse=True)
        rows = []
        for value, acts in items[:limit]:
            ts = format_timestamp(float(value.get("timestamp", 0) or 0))
            summary = value.get("summary", "") or "-"
            reason = value.get("reason", "") or "-"
            act_texts = []
            for a in acts:
                act_texts.append(f"{a.get('action', '')}({a.get('strategy', '')})")
            rows.append([ts, summary, "; ".join(act_texts), reason])
        return rows
    except Exception:
        return []


def _render_memory_structure_section(ctx: dict, memory_structure: dict, color: str):
    """渲染记忆结构部分"""
    # 生成记忆层级 HTML
    levels_html = ""
    level_colors = ["#e3f2fd", "#fff3e0", "#f3e5f5", "#e8f5e9"]
    for i, (key, value) in enumerate(memory_structure.items()):
        bg_color = level_colors[i % len(level_colors)]
        levels_html += f'''<div style="padding:10px 12px;background:{bg_color};border-radius:6px;margin-bottom:8px;border-left:3px solid {color};"><div style="font-weight:600;color:#333;">{key}</div><div style="color:#666;font-size:12px;margin-top:2px;">{value}</div></div>'''
    
    ctx["put_html"](f'''<div style="background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);overflow:hidden;border:1px solid #eee;margin-bottom:15px;"><div style="background:linear-gradient(135deg,{color} 0%,{color}dd 100%);padding:12px 20px;color:white;"><div style="font-size:16px;font-weight:600;">🧠 记忆结构</div><div style="font-size:12px;opacity:0.9;margin-top:4px;">分层记忆存储系统</div></div><div style="padding:20px;">{levels_html}</div></div>''')


def _render_signal_types_section(ctx: dict, signal_types: list, color: str):
    """渲染信号类型部分"""
    # 生成信号类型 HTML
    signals_html = ""
    signal_colors = ["#e8f5e9", "#fff3e0", "#ffebee", "#e3f2fd", "#f3e5f5", "#e0f2f1"]
    for i, signal in enumerate(signal_types):
        bg_color = signal_colors[i % len(signal_colors)]
        signals_html += f'''<div style="padding:8px 12px;background:{bg_color};border-radius:6px;margin-bottom:6px;font-size:13px;color:#333;">{signal}</div>'''
    
    ctx["put_html"](f'''<div style="background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);overflow:hidden;border:1px solid #eee;margin-bottom:15px;"><div style="background:linear-gradient(135deg,{color} 0%,{color}dd 100%);padding:12px 20px;color:white;"><div style="font-size:16px;font-weight:600;">📡 信号类型</div><div style="font-size:12px;opacity:0.9;margin-top:4px;">策略可能输出的信号</div></div><div style="padding:20px;">{signals_html}</div></div>''')
