"""数据源列表渲染、分类/视图切换、表格构建"""

from pywebio.output import set_scope
from pywebio.session import run_async

from deva.naja.infra.ui.ui_style import (
    apply_strategy_like_styles, render_empty_state, render_stats_cards,
    render_status_badge,
)
from .constants import _fmt_ts_short, _humanize_cron


# 全局变量：当前选中的类别和视图模式
_current_category = "全部"
_view_mode = "name"  # "name": 按名称分类, "consumer": 按消费分类


async def render_datasource_admin(ctx: dict):
    """渲染数据源管理面板"""
    set_scope("ds_content")
    _render_ds_content(ctx)


def _get_consumer_handler_types(ds_id: str) -> list:
    """获取消费该数据源的策略的handler_type列表"""
    try:
        from deva.naja.strategy import get_strategy_manager
        mgr = get_strategy_manager()
        handler_types = set()
        for s in mgr.list_all():
            bound_ds = getattr(s._metadata, "bound_datasource_id", "")
            if bound_ds == ds_id:
                ht = getattr(s._metadata, "handler_type", "unknown")
                if ht and ht != "unknown":
                    handler_types.add(ht)
        return sorted(list(handler_types))
    except Exception:
        return []


def _get_handler_type_label(ht: str) -> str:
    """获取handler_type的中文标签"""
    labels = {
        "radar": "📡 Radar雷达",
        "memory": "🧠 Memory记忆",
        "bandit": "🎰 Bandit交易",
        "llm": "🤖 LLM调节",
    }
    return labels.get(ht, ht)


def _categorize_datasource_by_consumer(entry) -> str:
    """根据数据源被哪些handler_type消费来分类"""
    handler_types = _get_consumer_handler_types(entry.id)
    if not handler_types:
        return "⚪ 未消费"
    if len(handler_types) == 1:
        return _get_handler_type_label(handler_types[0])
    return "🌐 多消费"


def _get_all_consumer_categories(entries: list) -> list:
    """获取所有消费类别"""
    categories = set()
    for e in entries:
        cat = _categorize_datasource_by_consumer(e)
        categories.add(cat)
    return sorted(list(categories))


def _categorize_datasource(entry) -> str:
    """根据数据源名称分类"""
    name = entry.name
    if name.startswith("产业链_L1_"):
        return "🔋 第1层-电力能源"
    elif name.startswith("产业链_L2_"):
        return "💻 第2层-芯片算力"
    elif name.startswith("产业链_L3_"):
        return "🏢 第3层-数据中心"
    elif name.startswith("产业链_L4_"):
        return "🤖 第4层-大模型平台"
    elif name.startswith("产业链_L5_"):
        return "🎯 第5层-AI应用"
    elif name.startswith("题材_"):
        return "📊 概念题材"
    elif name.startswith("realtime_tick_"):
        return "📈 市场分类"
    elif "news" in name.lower() or "新闻" in name or "财经" in name:
        return "📰 新闻资讯"
    elif "replay" in name.lower() or "回放" in name:
        return "📼 数据回放"
    else:
        return "📦 其他"


def _get_all_categories(entries: list) -> list:
    """获取所有类别（根据视图模式）"""
    if _view_mode == "consumer":
        return _get_all_consumer_categories(entries)
    categories = set()
    for e in entries:
        cat = _categorize_datasource(e)
        categories.add(cat)
    return sorted(list(categories))


def _render_ds_content(ctx: dict):
    """渲染数据源内容（支持局部刷新，使用Tab分类）"""
    from deva.naja.datasource import get_datasource_manager
    from pywebio.output import clear

    global _current_category

    mgr = get_datasource_manager()
    entries = mgr.list_all()
    stats = mgr.get_stats()

    clear("ds_content")
    apply_strategy_like_styles(ctx, scope="ds_content", include_compact_table=True, include_category_tabs=True)

    ctx["put_html"](_render_stats_html(stats), scope="ds_content")

    # 渲染类别 Tab
    categories = _get_all_categories(entries)
    _render_category_tabs(ctx, categories, entries, mgr)

    # 根据当前类别筛选数据源
    if _current_category == "全部":
        filtered_entries = entries
    else:
        if _view_mode == "consumer":
            filtered_entries = [e for e in entries if _categorize_datasource_by_consumer(e) == _current_category]
        else:
            filtered_entries = [e for e in entries if _categorize_datasource(e) == _current_category]

    if filtered_entries:
        table_data = _build_table_data(ctx, filtered_entries, mgr)
        ctx["put_table"](table_data, header=["名称", "来源", "类型", "状态", "简介", "最近数据", "操作"], scope="ds_content")
    else:
        ctx["put_html"](render_empty_state("暂无数据源，点击下方按钮创建"), scope="ds_content")

    ctx["put_html"](_render_toolbar_html(), scope="ds_content")
    ctx["put_buttons"]([
        {"label": "➕ 创建数据源", "value": "create", "color": "primary"},
        {"label": "▶ 全部启动", "value": "start_all", "color": "success"},
        {"label": "⏹ 全部停止", "value": "stop_all", "color": "danger"},
        {"label": "📁 导出全部", "value": "export_all", "color": "info"},
    ], onclick=lambda v, m=mgr, c=ctx: _handle_toolbar_action(v, m, c), group=True, scope="ds_content")
    ctx["put_html"]('</div>', scope="ds_content")


def _render_category_tabs(ctx: dict, categories: list, entries: list, mgr):
    """渲染类别 Tab"""
    global _current_category

    tab_buttons = []
    tab_buttons.append({"label": f"全部 ({len(entries)})", "value": "全部", "color": "primary" if _current_category == "全部" else "light"})

    for cat in categories:
        if _view_mode == "consumer":
            count = len([e for e in entries if _categorize_datasource_by_consumer(e) == cat])
        else:
            count = len([e for e in entries if _categorize_datasource(e) == cat])
        tab_buttons.append({
            "label": f"{cat} ({count})",
            "value": cat,
            "color": "primary" if _current_category == cat else "light"
        })

    ctx["put_html"]('<div class="category-tabs">', scope="ds_content")
    ctx["put_buttons"](tab_buttons, onclick=lambda v, c=ctx, m=mgr: _switch_category(v, c, m), scope="ds_content")
    ctx["put_html"]('</div>', scope="ds_content")

    view_mode_btns = [
        {"label": "📛 按名称", "value": "name", "color": "primary" if _view_mode == "name" else "secondary"},
        {"label": "📥 按消费", "value": "consumer", "color": "primary" if _view_mode == "consumer" else "secondary"},
    ]
    ctx["put_html"]('<div style="margin-top:8px;">', scope="ds_content")
    ctx["put_buttons"](view_mode_btns, onclick=lambda v, c=ctx, m=mgr: _switch_view_mode(v, c, m), scope="ds_content")
    ctx["put_html"]('</div>', scope="ds_content")


def _switch_category(category: str, ctx: dict, mgr):
    """切换类别"""
    global _current_category
    _current_category = category
    _render_ds_content(ctx)


def _switch_view_mode(mode: str, ctx: dict, mgr):
    """切换视图模式"""
    global _view_mode, _current_category
    _view_mode = mode
    _current_category = "全部"
    _render_ds_content(ctx)


def _render_stats_html(stats: dict) -> str:
    cards = [
        {"label": "总数据源", "value": stats["total"], "gradient": "linear-gradient(135deg,#667eea,#764ba2)", "shadow": "rgba(102,126,234,0.3)"},
        {"label": "运行中", "value": stats["running"], "gradient": "linear-gradient(135deg,#11998e,#38ef7d)", "shadow": "rgba(17,153,142,0.3)"},
        {"label": "已停止", "value": stats["stopped"], "gradient": "linear-gradient(135deg,#636363,#a2abba)", "shadow": "rgba(99,99,99,0.3)"},
        {"label": "错误数", "value": stats["error"], "gradient": "linear-gradient(135deg,#ff416c,#ff4b2b)", "shadow": "rgba(255,65,108,0.3)"},
    ]

    attention = stats.get("attention")
    if attention:
        active_label = "运行中" if attention.get("active") else "已停止"
        active_color = "linear-gradient(135deg,#11998e,#38ef7d)" if attention.get("active") else "linear-gradient(135deg,#636363,#a2abba)"
        cards.append({
            "label": "注意力获取",
            "value": active_label,
            "gradient": active_color,
            "shadow": "rgba(17,153,142,0.3)" if attention.get("active") else "rgba(99,99,99,0.3)",
        })
        cards.append({
            "label": "获取次数",
            "value": attention.get("fetch_count", 0),
            "gradient": "linear-gradient(135deg,#f093fb,#f5576c)",
            "shadow": "rgba(240,147,251,0.3)",
        })
        cards.append({
            "label": "高频档位",
            "value": attention.get("high_count", 0),
            "gradient": "linear-gradient(135deg,#4facfe,#00f2fe)",
            "shadow": "rgba(79,172,254,0.3)",
        })
    else:
        cards.append({
            "label": "注意力获取",
            "value": "未启动",
            "gradient": "linear-gradient(135deg,#e0e0e0,#9e9e9e)",
            "shadow": "rgba(158,158,158,0.3)",
        })
        cards.append({
            "label": "获取次数",
            "value": "-",
            "gradient": "linear-gradient(135deg,#e0e0e0,#9e9e9e)",
            "shadow": "rgba(158,158,158,0.3)",
        })
        cards.append({
            "label": "高频档位",
            "value": "-",
            "gradient": "linear-gradient(135deg,#e0e0e0,#9e9e9e)",
            "shadow": "rgba(158,158,158,0.3)",
        })

    return render_stats_cards(cards)


def _render_toolbar_html() -> str:
    return '<div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">'


def _build_table_data(ctx: dict, entries: list, mgr) -> list:
    from .detail import _show_ds_detail
    from .actions import _handle_ds_action

    table_data = []
    for e in entries:
        status_html = render_status_badge(e.is_running)
        type_label = _get_type_label(e)
        desc_short = _get_description_short(e)
        recent_data_info = _get_recent_data_info(e)
        toggle_color = "danger" if e.is_running else "success"

        source = getattr(e._metadata, 'source', 'nb') if hasattr(e, '_metadata') else 'nb'
        if source == 'file':
            source_html = '<span style="background:#e8f5e9;color:#2e7d32;padding:2px 8px;border-radius:4px;font-size:11px;">📁 文件</span>'
        else:
            source_html = '<span style="background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:4px;font-size:11px;">💾 NB</span>'

        action_btns = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{e.id}", "color": "info"},
            {"label": "编辑", "value": f"edit_{e.id}", "color": "primary"},
            {"label": "停止" if e.is_running else "启动", "value": f"toggle_{e.id}", "color": toggle_color},
            {"label": "删除", "value": f"delete_{e.id}", "color": "danger"},
        ], onclick=lambda v, m=mgr, c=ctx: _handle_ds_action(v, m, c))

        table_data.append([
            ctx["put_html"](f'<div style="max-width:200px;white-space:normal;word-break:break-word;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;"><strong>{e.name}</strong></div>'),
            ctx["put_html"](source_html),
            ctx["put_html"](type_label),
            ctx["put_html"](status_html),
            ctx["put_html"](f'<div style="color:#666;font-size:12px;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;" title="{getattr(e._metadata, "description", "") or ""}">{desc_short}</div>'),
            ctx["put_html"](f'<span style="color:#666;font-size:12px;">{recent_data_info}</span>'),
            action_btns,
        ])
    return table_data


def _get_type_label(entry) -> str:
    source_type = getattr(entry._metadata, "source_type", "custom")
    interval = getattr(entry._metadata, "interval", 5)

    type_config = {
        "timer": {
            "icon": "⏱️", "label": "定时器",
            "title": f"定时器：每 {interval:.0f} 秒执行一次",
            "bg_color": "#e3f2fd", "text_color": "#1565c0",
        },
        "stream": {
            "icon": "📡", "label": "命名流",
            "title": "命名流：从命名总线订阅数据",
            "bg_color": "#f3e5f5", "text_color": "#7b1fa2",
        },
        "http": {
            "icon": "🌐", "label": "HTTP服务",
            "title": "HTTP服务：通过HTTP接口获取数据",
            "bg_color": "#e8f5e9", "text_color": "#2e7d32",
        },
        "kafka": {
            "icon": "📨", "label": "Kafka",
            "title": "Kafka：从Kafka消息队列消费数据",
            "bg_color": "#fce4ec", "text_color": "#c2185b",
        },
        "redis": {
            "icon": "🗄️", "label": "Redis",
            "title": "Redis：从Redis订阅或拉取数据",
            "bg_color": "#e0f2f1", "text_color": "#00695c",
        },
        "tcp": {
            "icon": "🔌", "label": "TCP端口",
            "title": "TCP端口：监听TCP端口接收数据",
            "bg_color": "#fff8e1", "text_color": "#f57f17",
        },
        "file": {
            "icon": "📄", "label": "文件",
            "title": "文件：从文件读取数据",
            "bg_color": "#efebe9", "text_color": "#5d4037",
        },
        "directory": {
            "icon": "📂", "label": "目录",
            "title": "目录：监控目录中文件变化",
            "bg_color": "#e1f5fe", "text_color": "#0277bd",
        },
        "custom": {
            "icon": "⚙️", "label": "自定义",
            "title": "自定义：执行自定义代码获取数据",
            "bg_color": "#f5f5f5", "text_color": "#616161",
        },
        "replay": {
            "icon": "📼", "label": "回放",
            "title": "数据回放：从历史数据表中回放数据",
            "bg_color": "#fff3e0", "text_color": "#e65100",
        },
    }

    config = type_config.get(source_type, {
        "icon": "❓", "label": source_type, "title": source_type,
        "bg_color": "#f5f5f5", "text_color": "#616161",
    })

    icon = config["icon"]
    label = config["label"]
    title = config["title"]
    bg_color = config["bg_color"]
    text_color = config["text_color"]

    if source_type == "timer":
        mode = (getattr(entry._metadata, "execution_mode", "timer") or "timer").strip().lower()
        if mode == "scheduler":
            trig = (getattr(entry._metadata, "scheduler_trigger", "interval") or "interval").strip().lower()
            if trig == "cron":
                desc = _humanize_cron(getattr(entry._metadata, "cron_expr", ""))
            elif trig == "date":
                desc = "一次性计划"
            else:
                desc = f"间隔 {interval:.0f}s"
        elif mode == "event_trigger":
            desc = "事件触发"
        else:
            desc = f"每 {interval:.0f}s"
        return f'<span title="{title}" style="background:{bg_color};color:{text_color};padding:2px 8px;border-radius:4px;font-size:12px;cursor:help;">{icon} {label} ({desc})</span>'

    return f'<span title="{title}" style="background:{bg_color};color:{text_color};padding:2px 8px;border-radius:4px;font-size:12px;cursor:help;">{icon} {label}</span>'


def _get_description_short(entry) -> str:
    description = getattr(entry._metadata, "description", "") or ""
    return description[:30] + "..." if len(description) > 30 else description or "-"


def _get_recent_data_info(entry) -> str:
    last_data_ts = entry._state.last_data_ts
    total_emitted = entry._state.total_emitted
    if last_data_ts > 0:
        return f"{_fmt_ts_short(last_data_ts)} ({total_emitted}条)"
    return f"无数据 ({total_emitted}条)"


def _timer_trigger_text(entry) -> str:
    mode = (getattr(entry._metadata, "execution_mode", "timer") or "timer").strip().lower()
    interval = float(getattr(entry._metadata, "interval", 5) or 5)
    if mode == "timer":
        return f"Timer：每 {interval:.1f} 秒执行"
    if mode == "scheduler":
        trig = (getattr(entry._metadata, "scheduler_trigger", "interval") or "interval").strip().lower()
        if trig == "interval":
            return f"Scheduler/interval：每 {interval:.1f} 秒执行"
        if trig == "date":
            return f"Scheduler/date：{getattr(entry._metadata, 'run_at', '') or '-'}"
        return f"Scheduler/cron：{_humanize_cron(getattr(entry._metadata, 'cron_expr', '') or '')}"
    return f"EventTrigger：来源 {getattr(entry._metadata, 'event_source', 'log')} / 条件 {getattr(entry._metadata, 'event_condition', '') or '任意事件'}"


def _handle_toolbar_action(action: str, mgr, ctx: dict):
    """处理工具栏按钮操作"""
    from .actions import _start_all_ds, _stop_all_ds, _export_all_ds_to_file, _create_ds_dialog

    if action == "create":
        _create_ds_dialog(mgr, ctx)
    elif action == "start_all":
        _start_all_ds(mgr, ctx)
    elif action == "stop_all":
        _stop_all_ds(mgr, ctx)
    elif action == "export_all":
        _export_all_ds_to_file(mgr, ctx)
