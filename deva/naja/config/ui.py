"""Naja 配置管理 UI"""

from pywebio.output import put_text, put_markdown, put_table, put_buttons, put_html, toast, popup, close_popup, put_row
from pywebio.input import input_group, input, select, NUMBER, PASSWORD, textarea
from pywebio.session import run_async
from pywebio import pin

from ..common.ui_style import apply_strategy_like_styles, render_stats_cards
from . import (
    get_config,
    set_config,
    set_category_config,
    get_datasource_config,
    get_strategy_config,
    get_task_config,
    get_dictionary_config,
    get_auth_config,
    get_performance_config,
    ensure_auth_secret,
    reset_to_default,
    DEFAULT_CONFIG,
)


def render_config_page(ctx: dict):
    """渲染配置管理页面"""
    apply_strategy_like_styles(ctx)
    ctx["put_html"](
        '<div style="margin:0 0 14px 0;">'
        '<div style="font-size:24px;font-weight:700;color:#2c3e50;">⚙️ Naja 配置管理</div>'
        '<div style="font-size:13px;color:#6c757d;margin-top:6px;">管理数据源、策略、任务、字典四个模块的配置参数，配置存储在 NB(\'naja_config\') 命名空间中。</div>'
        '</div>'
    )
    
    ctx["put_html"]('<div style="margin:16px 0;">')
    ctx["put_buttons"]([
        {"label": "🔐 认证配置", "value": "auth", "color": "warning"},
        {"label": "📡 数据源配置", "value": "datasource", "color": "info"},
        {"label": "📈 策略配置", "value": "strategy", "color": "primary"},
        {"label": "⏰ 任务配置", "value": "task", "color": "success"},
        {"label": "📚 字典配置", "value": "dictionary", "color": "default"},
        {"label": "🧠 记忆配置", "value": "memory", "color": "primary"},
        {"label": "🧭 雷达配置", "value": "radar", "color": "info"},
        {"label": "🤖 LLM调节", "value": "llm", "color": "warning"},
        {"label": "⚡ 性能监控", "value": "performance", "color": "danger"},
    ], onclick=lambda v: run_async(_show_config_dialog(ctx, v)), group=True)
    ctx["put_html"]('</div>')
    
    _render_config_summary(ctx)


def _render_config_summary(ctx: dict):
    """渲染配置摘要"""
    ctx["put_html"]('<div style="margin:8px 0 10px 0;font-size:18px;font-weight:600;color:#333;">📊 当前配置摘要</div>')
    
    config_data = [
        ["类别", "关键配置", "当前值"],
    ]
    
    ds_config = get_datasource_config()
    config_data.append([
        "📡 数据源",
        f"默认间隔: {ds_config.get('default_interval', 5)}s\n超时: {ds_config.get('timeout', 30)}s",
        f"重试次数: {ds_config.get('max_retries', 3)}"
    ])
    
    strategy_config = get_strategy_config()
    config_data.append([
        "📈 策略",
        f"单条历史: {strategy_config.get('single_history_count', 30)}\n总历史: {strategy_config.get('total_history_count', 500)}",
        f"默认窗口: {strategy_config.get('default_window_size', 5)}"
    ])
    
    task_config = get_task_config()
    config_data.append([
        "⏰ 任务",
        f"默认间隔: {task_config.get('default_interval', 60)}s\n最大并发: {task_config.get('max_concurrent', 10)}",
        f"重试次数: {task_config.get('retry_count', 3)}"
    ])
    
    dict_config = get_dictionary_config()
    config_data.append([
        "📚 字典",
        f"默认间隔: {dict_config.get('default_interval', 300)}s\n每日时间: {dict_config.get('default_daily_time', '03:00')}",
        f"缓存大小: {dict_config.get('max_cache_size', 10000)}"
    ])
    
    auth_config = get_auth_config()
    config_data.append([
        "🔐 认证",
        f"用户名: {auth_config.get('username', '未设置')}",
        f"开发模式: {'启用' if auth_config.get('dev_mode', False) else '禁用'}"
    ])
    
    perf_config = get_config("performance") or {}
    lock_enabled = perf_config.get("lock_monitoring_enabled", False)
    web_enabled = perf_config.get("web_request_monitoring_enabled", True)
    storage_enabled = perf_config.get("storage_monitoring_enabled", False)
    config_data.append([
        "⚡ 性能监控",
        f"锁监控: {'启用' if lock_enabled else '禁用'}\nWeb请求: {'启用' if web_enabled else '禁用'}",
        f"存储监控: {'启用' if storage_enabled else '禁用'}\n阈值: {perf_config.get('lock_monitoring_threshold_ms', 100)}ms"
    ])

    memory_config = get_config("memory") or {}
    config_data.append([
        "🧠 记忆",
        f"自动保存: {'启用' if memory_config.get('auto_save_enabled', True) else '禁用'}\n自动加载: {'启用' if memory_config.get('auto_load_on_start', True) else '禁用'}",
        f"保存间隔: {memory_config.get('auto_save_interval', 300)}s"
    ])

    radar_config = get_config("radar") or {}
    config_data.append([
        "🧭 雷达",
        f"事件保留: {radar_config.get('event_retention_days', 7)} 天",
        f"清理间隔: {radar_config.get('cleanup_interval_seconds', 600)}s"
    ])

    llm_config = get_config("llm") or {}
    config_data.append([
        "🤖 LLM调节",
        f"自动调节: {'启用' if llm_config.get('auto_adjust_enabled', True) else '禁用'}\n最小间隔: {llm_config.get('min_interval_seconds', 300)}s",
        f"调节间隔: {llm_config.get('auto_adjust_interval_seconds', 900)}s"
    ])

    ctx["put_html"](render_stats_cards([
        {"label": "配置模块", "value": 8, "gradient": "linear-gradient(135deg,#667eea,#764ba2)", "shadow": "rgba(102,126,234,0.3)"},
        {"label": "启用开发模式", "value": 1 if auth_config.get('dev_mode', False) else 0, "gradient": "linear-gradient(135deg,#f0ad4e,#ec971f)", "shadow": "rgba(240,173,78,0.3)"},
        {"label": "默认策略窗口", "value": strategy_config.get('default_window_size', 5), "gradient": "linear-gradient(135deg,#11998e,#38ef7d)", "shadow": "rgba(17,153,142,0.3)"},
    ]))
    
    ctx["put_table"](config_data)


async def _show_config_dialog(ctx: dict, category: str):
    """显示配置对话框"""
    config = get_config(category)
    defaults = DEFAULT_CONFIG.get(category, {})
    
    category_names = {
        "auth": "认证",
        "datasource": "数据源",
        "strategy": "策略",
        "task": "任务",
        "dictionary": "字典",
        "memory": "记忆",
        "radar": "雷达",
        "llm": "LLM调节",
        "performance": "性能监控",
    }
    
    with ctx["popup"](f"⚙️ {category_names.get(category, category)}配置", size="large", closable=True):
        ctx["put_markdown"](f"### {category_names.get(category, category)}配置")
        
        if category == "auth":
            await _render_auth_config(ctx, config, defaults)
        elif category == "datasource":
            await _render_datasource_config(ctx, config, defaults)
        elif category == "strategy":
            await _render_strategy_config(ctx, config, defaults)
        elif category == "task":
            await _render_task_config(ctx, config, defaults)
        elif category == "dictionary":
            await _render_dictionary_config(ctx, config, defaults)
        elif category == "performance":
            await _render_performance_config(ctx, config, defaults)
        elif category == "memory":
            await _render_memory_config(ctx, config, defaults)
        elif category == "radar":
            await _render_radar_config(ctx, config, defaults)
        elif category == "llm":
            await _render_llm_config(ctx, config, defaults)


def _split_list(value: str) -> list:
    if not value:
        return []
    parts = []
    for chunk in str(value).replace("\n", ",").split(","):
        item = chunk.strip()
        if item:
            parts.append(item)
    return parts


async def _render_datasource_config(ctx: dict, config: dict, defaults: dict):
    """渲染数据源配置"""
    all_types = [
        {"label": "⏱️ 定时器", "value": "timer"},
        {"label": "📡 命名流", "value": "stream"},
        {"label": "🌐 HTTP服务", "value": "http"},
        {"label": "📨 Kafka", "value": "kafka"},
        {"label": "🗄️ Redis", "value": "redis"},
        {"label": "🔌 TCP端口", "value": "tcp"},
        {"label": "📄 文件", "value": "file"},
        {"label": "📂 目录", "value": "directory"},
        {"label": "⚙️ 自定义代码", "value": "custom"},
        {"label": "📼 数据回放", "value": "replay"},
    ]
    
    enabled_types = config.get("enabled_types", defaults.get("enabled_types", ["timer", "custom", "replay"]))
    enabled_timer_modes = config.get(
        "enabled_timer_execution_modes",
        defaults.get("enabled_timer_execution_modes", ["timer", "scheduler", "event_trigger"]),
    )
    
    form = await ctx["input_group"]("数据源配置", [
        ctx["input"]("默认间隔(秒)", name="default_interval", type="number",
                    value=config.get("default_interval", defaults.get("default_interval", 5))),
        ctx["input"]("最大重试次数", name="max_retries", type="number",
                    value=config.get("max_retries", defaults.get("max_retries", 3))),
        ctx["input"]("重试延迟(秒)", name="retry_delay", type="number",
                    value=config.get("retry_delay", defaults.get("retry_delay", 1.0))),
        ctx["input"]("超时时间(秒)", name="timeout", type="number",
                    value=config.get("timeout", defaults.get("timeout", 30))),
        ctx["checkbox"]("启用的数据源类型", name="enabled_types", options=all_types, 
                       value=enabled_types, help_text="勾选的类型将在创建/编辑数据源时显示"),
        ctx["checkbox"](
            "定时器可用调度方式",
            name="enabled_timer_execution_modes",
            options=[
                {"label": "Timer（固定间隔执行）", "value": "timer"},
                {"label": "Scheduler（计划调度执行）", "value": "scheduler"},
                {"label": "EventTrigger（事件触发执行）", "value": "event_trigger"},
            ],
            value=enabled_timer_modes,
            help_text="勾选后会在“定时器”数据源的创建/编辑流程中显示",
        ),
        ctx["actions"]("操作", [
            {"label": "保存", "value": "save", "color": "primary"},
            {"label": "恢复默认", "value": "reset", "color": "warning"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])
    
    if form and form.get("action") == "save":
        set_category_config("datasource", {
            "default_interval": int(form.get("default_interval", 5)),
            "max_retries": int(form.get("max_retries", 3)),
            "retry_delay": float(form.get("retry_delay", 1.0)),
            "timeout": int(form.get("timeout", 30)),
            "enabled_types": form.get("enabled_types", ["timer", "custom", "replay"]),
            "enabled_timer_execution_modes": form.get(
                "enabled_timer_execution_modes", ["timer", "scheduler", "event_trigger"]
            ),
        })
        ctx["toast"]("数据源配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "reset":
        reset_to_default("datasource")
        ctx["toast"]("已恢复默认配置", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _render_performance_config(ctx: dict, config: dict, defaults: dict):
    """渲染性能监控配置"""
    # 获取配置值
    strategy_enabled = config.get("strategy_monitoring_enabled", True)
    task_enabled = config.get("task_monitoring_enabled", True)
    datasource_enabled = config.get("datasource_monitoring_enabled", True)
    storage_enabled = config.get("storage_monitoring_enabled", False)
    lock_enabled = config.get("lock_monitoring_enabled", False)
    web_enabled = config.get("web_request_monitoring_enabled", True)
    lock_threshold = config.get("lock_monitoring_threshold_ms", 100)
    
    # 显示说明和表单
    ctx["put_html"](f"""
    <div style="background:#f8f9fa;padding:12px;border-radius:8px;margin-bottom:16px;">
        <div style="font-weight:600;margin-bottom:8px;">💡 性能监控配置</div>
        <div style="font-size:13px;color:#666;">
            开启/关闭各类性能监控<br>
            • 阈值：只有超过此值的操作才会被记录
        </div>
    </div>
    <form id="perf_config_form">
        <div style="margin-bottom:12px;">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                <input type="checkbox" name="strategy_monitoring" {"checked" if strategy_enabled else ""}>
                📊 策略监控
            </label>
        </div>
        <div style="margin-bottom:12px;">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                <input type="checkbox" name="task_monitoring" {"checked" if task_enabled else ""}>
                ⏰ 任务监控
            </label>
        </div>
        <div style="margin-bottom:12px;">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                <input type="checkbox" name="datasource_monitoring" {"checked" if datasource_enabled else ""}>
                📡 数据源监控
            </label>
        </div>
        <div style="margin-bottom:12px;">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                <input type="checkbox" name="storage_monitoring" {"checked" if storage_enabled else ""}>
                💾 存储监控
            </label>
        </div>
        <div style="margin-bottom:12px;">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                <input type="checkbox" name="lock_monitoring" {"checked" if lock_enabled else ""}>
                🔒 锁监控
            </label>
        </div>
        <div style="margin-bottom:12px;">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                <input type="checkbox" name="web_monitoring" {"checked" if web_enabled else ""}>
                🌐 Web请求监控
            </label>
        </div>
        <div style="margin-bottom:16px;">
            <label style="display:block;margin-bottom:4px;">锁监控阈值 (ms)</label>
            <input type="number" name="lock_threshold" value="{lock_threshold}" style="width:200px;padding:6px;border:1px solid #ddd;border-radius:4px;">
        </div>
        <div style="display:flex;gap:8px;">
            <button type="button" onclick="savePerformanceConfig()" style="padding:8px 16px;background:#0d6efd;color:white;border:none;border-radius:4px;cursor:pointer;">💾 保存配置</button>
            <button type="button" onclick="PyWebIO.closePopup()" style="padding:8px 16px;background:#6c757d;color:white;border:none;border-radius:4px;cursor:pointer;">取消</button>
        </div>
    </form>
    <script>
    function savePerformanceConfig() {{
        var form = document.getElementById('perf_config_form');
        var formData = new FormData(form);
        var data = {{
            strategy_monitoring: formData.has('strategy_monitoring'),
            task_monitoring: formData.has('task_monitoring'),
            datasource_monitoring: formData.has('datasource_monitoring'),
            storage_monitoring: formData.has('storage_monitoring'),
            lock_monitoring: formData.has('lock_monitoring'),
            web_monitoring: formData.has('web_monitoring'),
            lock_threshold: parseInt(formData.get('lock_threshold') || 100)
        }};
        PyWebIO.call_pyfunc(save_performance_config, [data]);
    }}
    </script>
    """)


async def _render_performance_config(ctx: dict, config: dict, defaults: dict):
    pass  # 已废弃，使用 JavaScript 方式


async def save_performance_config(data: dict):
    """通过 JavaScript 调用保存性能监控配置"""
    from . import set_config
    
    strategy_monitoring = data.get("strategy_monitoring", True)
    task_monitoring = data.get("task_monitoring", True)
    datasource_monitoring = data.get("datasource_monitoring", True)
    storage_monitoring = data.get("storage_monitoring", False)
    lock_monitoring = data.get("lock_monitoring", False)
    web_monitoring = data.get("web_monitoring", True)
    lock_threshold = data.get("lock_threshold", 100)
    
    # 保存配置
    set_config("performance", "strategy_monitoring_enabled", strategy_monitoring)
    set_config("performance", "task_monitoring_enabled", task_monitoring)
    set_config("performance", "datasource_monitoring_enabled", datasource_monitoring)
    set_config("performance", "storage_monitoring_enabled", storage_monitoring)
    set_config("performance", "lock_monitoring_enabled", lock_monitoring)
    set_config("performance", "web_request_monitoring_enabled", web_monitoring)
    set_config("performance", "lock_monitoring_threshold_ms", lock_threshold)
    
    # 更新 LockMonitor 状态
    try:
        from ..performance.lock_monitor import LockMonitor
        if lock_monitoring:
            LockMonitor.set_threshold(lock_threshold)
            LockMonitor.enable()
        else:
            LockMonitor.disable()
    except Exception as e:
        print(f"[Performance Config] 更新LockMonitor失败: {e}")
    
    from pywebio import toast
    toast("性能监控配置已保存", color="success")
    
    from pywebio import close_popup
    close_popup()


async def _save_performance_config(ctx: dict, config: dict, defaults: dict):
    pass  # 已废弃


async def _render_strategy_config(ctx: dict, config: dict, defaults: dict):
    """渲染策略配置"""
    form = await ctx["input_group"]("策略配置", [
        ctx["input"]("单条策略历史保留条数", name="single_history_count", type="number",
                    value=config.get("single_history_count", defaults.get("single_history_count", 30)),
                    help_text="每个策略保留的执行结果数量，默认30"),
        ctx["input"]("总历史数据保留条数", name="total_history_count", type="number",
                    value=config.get("total_history_count", defaults.get("total_history_count", 500)),
                    help_text="所有策略的总历史数据保留条数，默认500"),
        ctx["input"]("默认窗口大小", name="default_window_size", type="number",
                    value=config.get("default_window_size", defaults.get("default_window_size", 5))),
        ctx["input"]("默认窗口间隔", name="default_window_interval",
                    value=config.get("default_window_interval", defaults.get("default_window_interval", "10s")),
                    placeholder="如 5s / 1min / 1h"),
        ctx["actions"]("操作", [
            {"label": "保存", "value": "save", "color": "primary"},
            {"label": "恢复默认", "value": "reset", "color": "warning"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])
    
    if form and form.get("action") == "save":
        single_count = int(form.get("single_history_count", 30))
        total_count = int(form.get("total_history_count", 500))
        
        if single_count < 1 or single_count > 1000:
            ctx["toast"]("单条历史保留条数应在 1-1000 之间", color="error")
            return
        if total_count < 1 or total_count > 10000:
            ctx["toast"]("总历史保留条数应在 1-10000 之间", color="error")
            return
        
        set_category_config("strategy", {
            "single_history_count": single_count,
            "total_history_count": total_count,
            "default_window_size": int(form.get("default_window_size", 5)),
            "default_window_interval": form.get("default_window_interval", "10s"),
        })
        ctx["toast"]("策略配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "reset":
        reset_to_default("strategy")
        ctx["toast"]("已恢复默认配置", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _render_task_config(ctx: dict, config: dict, defaults: dict):
    """渲染任务配置"""
    form = await ctx["input_group"]("任务配置", [
        ctx["input"]("默认间隔(秒)", name="default_interval", type="number",
                    value=config.get("default_interval", defaults.get("default_interval", 60))),
        ctx["input"]("最大并发数", name="max_concurrent", type="number",
                    value=config.get("max_concurrent", defaults.get("max_concurrent", 10))),
        ctx["input"]("重试次数", name="retry_count", type="number",
                    value=config.get("retry_count", defaults.get("retry_count", 3))),
        ctx["input"]("重试延迟(秒)", name="retry_delay", type="number",
                    value=config.get("retry_delay", defaults.get("retry_delay", 5))),
        ctx["actions"]("操作", [
            {"label": "保存", "value": "save", "color": "primary"},
            {"label": "恢复默认", "value": "reset", "color": "warning"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])
    
    if form and form.get("action") == "save":
        set_category_config("task", {
            "default_interval": int(form.get("default_interval", 60)),
            "max_concurrent": int(form.get("max_concurrent", 10)),
            "retry_count": int(form.get("retry_count", 3)),
            "retry_delay": int(form.get("retry_delay", 5)),
        })
        ctx["toast"]("任务配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "reset":
        reset_to_default("task")
        ctx["toast"]("已恢复默认配置", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _render_dictionary_config(ctx: dict, config: dict, defaults: dict):
    """渲染字典配置"""
    form = await ctx["input_group"]("字典配置", [
        ctx["input"]("默认间隔(秒)", name="default_interval", type="number",
                    value=config.get("default_interval", defaults.get("default_interval", 300))),
        ctx["input"]("默认每日时间", name="default_daily_time",
                    value=config.get("default_daily_time", defaults.get("default_daily_time", "03:00")),
                    placeholder="HH:MM"),
        ctx["input"]("最大缓存大小", name="max_cache_size", type="number",
                    value=config.get("max_cache_size", defaults.get("max_cache_size", 10000))),
        ctx["actions"]("操作", [
            {"label": "保存", "value": "save", "color": "primary"},
            {"label": "恢复默认", "value": "reset", "color": "warning"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])
    
    if form and form.get("action") == "save":
        set_category_config("dictionary", {
            "default_interval": int(form.get("default_interval", 300)),
            "default_daily_time": form.get("default_daily_time", "03:00"),
            "max_cache_size": int(form.get("max_cache_size", 10000)),
        })
        ctx["toast"]("字典配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "reset":
        reset_to_default("dictionary")
        ctx["toast"]("已恢复默认配置", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _render_memory_config(ctx: dict, config: dict, defaults: dict):
    """渲染记忆配置"""
    form = await ctx["input_group"]("记忆配置", [
        ctx["checkbox"]("自动加载", name="auto_load_on_start", options=[
            {"label": "启动时自动加载记忆状态", "value": "auto_load_on_start", "selected": config.get("auto_load_on_start", defaults.get("auto_load_on_start", True))}
        ]),
        ctx["checkbox"]("自动保存", name="auto_save_enabled", options=[
            {"label": "启用记忆自动保存", "value": "auto_save_enabled", "selected": config.get("auto_save_enabled", defaults.get("auto_save_enabled", True))}
        ]),
        ctx["input"]("自动保存间隔(秒)", name="auto_save_interval", type="number",
                    value=config.get("auto_save_interval", defaults.get("auto_save_interval", 300))),
        ctx["actions"]("操作", [
            {"label": "保存", "value": "save", "color": "primary"},
            {"label": "恢复默认", "value": "reset", "color": "warning"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])

    if form and form.get("action") == "save":
        set_category_config("memory", {
            "auto_load_on_start": "auto_load_on_start" in form.get("auto_load_on_start", []),
            "auto_save_enabled": "auto_save_enabled" in form.get("auto_save_enabled", []),
            "auto_save_interval": int(form.get("auto_save_interval", 300)),
        })
        ctx["toast"]("记忆配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "reset":
        reset_to_default("memory")
        ctx["toast"]("已恢复默认配置", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _render_radar_config(ctx: dict, config: dict, defaults: dict):
    """渲染雷达配置"""
    form = await ctx["input_group"]("雷达配置", [
        ctx["input"]("事件保留天数", name="event_retention_days", type="number",
                    value=config.get("event_retention_days", defaults.get("event_retention_days", 7))),
        ctx["input"]("清理间隔(秒)", name="cleanup_interval_seconds", type="number",
                    value=config.get("cleanup_interval_seconds", defaults.get("cleanup_interval_seconds", 600))),
        ctx["actions"]("操作", [
            {"label": "保存", "value": "save", "color": "primary"},
            {"label": "恢复默认", "value": "reset", "color": "warning"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])

    if form and form.get("action") == "save":
        set_category_config("radar", {
            "event_retention_days": float(form.get("event_retention_days", 7)),
            "cleanup_interval_seconds": int(form.get("cleanup_interval_seconds", 600)),
        })
        ctx["toast"]("雷达配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "reset":
        reset_to_default("radar")
        ctx["toast"]("已恢复默认配置", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _render_llm_config(ctx: dict, config: dict, defaults: dict):
    """渲染 LLM 调节配置"""
    actions_options = [
        {"label": "update_params", "value": "update_params"},
        {"label": "update_strategy", "value": "update_strategy"},
        {"label": "reset", "value": "reset"},
        {"label": "start", "value": "start"},
        {"label": "stop", "value": "stop"},
        {"label": "restart", "value": "restart"},
    ]
    current_actions = config.get("allowed_actions", defaults.get("allowed_actions", []))

    form = await ctx["input_group"]("LLM 调节配置", [
        ctx["checkbox"]("自动调节", name="auto_adjust_enabled", options=[
            {"label": "启用 LLM 自动调节任务", "value": "auto_adjust_enabled", "selected": config.get("auto_adjust_enabled", defaults.get("auto_adjust_enabled", True))}
        ]),
        ctx["input"]("最小调节间隔(秒)", name="min_interval_seconds", type="number",
                    value=config.get("min_interval_seconds", defaults.get("min_interval_seconds", 300))),
        ctx["input"]("自动调节间隔(秒)", name="auto_adjust_interval_seconds", type="number",
                    value=config.get("auto_adjust_interval_seconds", defaults.get("auto_adjust_interval_seconds", 900))),
        ctx["input"]("调节窗口(秒)", name="auto_adjust_window_seconds", type="number",
                    value=config.get("auto_adjust_window_seconds", defaults.get("auto_adjust_window_seconds", 600))),
        ctx["input"]("最小雷达事件数", name="auto_adjust_min_events", type="number",
                    value=config.get("auto_adjust_min_events", defaults.get("auto_adjust_min_events", 3))),
        ctx["checkbox"]("Dry Run", name="auto_adjust_dry_run", options=[
            {"label": "只模拟不落地", "value": "auto_adjust_dry_run", "selected": config.get("auto_adjust_dry_run", defaults.get("auto_adjust_dry_run", False))}
        ]),
        ctx["checkbox"]("允许动作", name="allowed_actions", options=actions_options, value=current_actions),
        ctx["input"]("单次最大动作数", name="max_actions_per_run", type="number",
                    value=config.get("max_actions_per_run", defaults.get("max_actions_per_run", 5))),
        ctx["input"]("最小样本数(调节阈值)", name="min_results_count_for_adjust", type="number",
                    value=config.get("min_results_count_for_adjust", defaults.get("min_results_count_for_adjust", 20))),
        ctx["input"]("高成功率保护阈值(0-1)", name="max_success_rate_to_adjust", type="number",
                    value=config.get("max_success_rate_to_adjust", defaults.get("max_success_rate_to_adjust", 1.0))),
        ctx["textarea"]("策略白名单(逗号/换行分隔)", name="strategy_allowlist",
                        value="\n".join(config.get("strategy_allowlist", defaults.get("strategy_allowlist", [])))),
        ctx["textarea"]("策略黑名单(逗号/换行分隔)", name="strategy_denylist",
                        value="\n".join(config.get("strategy_denylist", defaults.get("strategy_denylist", [])))),
        ctx["textarea"]("允许参数键(可选)", name="allowed_param_keys",
                        value="\n".join(config.get("allowed_param_keys", defaults.get("allowed_param_keys", [])))),
        ctx["textarea"]("禁止参数键(可选)", name="blocked_param_keys",
                        value="\n".join(config.get("blocked_param_keys", defaults.get("blocked_param_keys", [])))),
        ctx["actions"]("操作", [
            {"label": "保存", "value": "save", "color": "primary"},
            {"label": "恢复默认", "value": "reset", "color": "warning"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])

    if form and form.get("action") == "save":
        set_category_config("llm", {
            "min_interval_seconds": int(form.get("min_interval_seconds", 300)),
            "auto_adjust_enabled": "auto_adjust_enabled" in form.get("auto_adjust_enabled", []),
            "auto_adjust_interval_seconds": int(form.get("auto_adjust_interval_seconds", 900)),
            "auto_adjust_window_seconds": int(form.get("auto_adjust_window_seconds", 600)),
            "auto_adjust_min_events": int(form.get("auto_adjust_min_events", 3)),
            "auto_adjust_dry_run": "auto_adjust_dry_run" in form.get("auto_adjust_dry_run", []),
            "allowed_actions": form.get("allowed_actions", []),
            "max_actions_per_run": int(form.get("max_actions_per_run", 5)),
            "strategy_allowlist": _split_list(form.get("strategy_allowlist", "")),
            "strategy_denylist": _split_list(form.get("strategy_denylist", "")),
            "min_results_count_for_adjust": int(form.get("min_results_count_for_adjust", 20)),
            "max_success_rate_to_adjust": float(form.get("max_success_rate_to_adjust", 1.0)),
            "allowed_param_keys": _split_list(form.get("allowed_param_keys", "")),
            "blocked_param_keys": _split_list(form.get("blocked_param_keys", "")),
        })
        ctx["toast"]("LLM 调节配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "reset":
        reset_to_default("llm")
        ctx["toast"]("已恢复默认配置", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _render_auth_config(ctx: dict, config: dict, defaults: dict):
    """渲染认证配置"""
    import secrets
    
    ctx["put_markdown"]("### 🔐 认证配置")
    ctx["put_markdown"]("管理管理员登录凭证和认证密钥。")
    
    form = await ctx["input_group"]("认证配置", [
        ctx["input"]("管理员用户名", name="username", 
                    value=config.get("username", defaults.get("username", "")),
                    placeholder="请输入管理员用户名"),
        ctx["input"]("新密码", name="password", type=ctx["PASSWORD"], 
                    value="", placeholder="输入新密码（留空则不修改）"),
        ctx["input"]("确认新密码", name="password_confirm", type=ctx["PASSWORD"], 
                    value="", placeholder="再次输入新密码"),
        ctx["checkbox"]("开发模式", name="dev_mode", options=[
            {"label": "启用开发模式（免认证）", "value": "dev_mode", "selected": config.get("dev_mode", defaults.get("dev_mode", False))}
        ], help_text="启用后跳过认证，仅用于开发环境"),
        ctx["actions"]("操作", [
            {"label": "保存", "value": "save", "color": "primary"},
            {"label": "重新生成密钥", "value": "regen_secret", "color": "warning"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])
    
    if form and form.get("action") == "save":
        username = form.get("username", "").strip()
        if not username:
            ctx["toast"]("用户名不能为空", color="error")
            return
        
        password = form.get("password", "")
        password_confirm = form.get("password_confirm", "")
        
        if password:
            if len(password) < 6:
                ctx["toast"]("密码至少6位", color="error")
                return
            if password != password_confirm:
                ctx["toast"]("两次密码不一致", color="error")
                return
            set_config("auth", "password", password)
        
        set_config("auth", "username", username)
        
        # 保存开发模式设置
        dev_mode = "dev_mode" in form.get("dev_mode", [])
        set_config("auth", "dev_mode", dev_mode)
        
        ctx["toast"]("认证配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "regen_secret":
        confirm = await ctx["popup"]("确认重新生成认证密钥？", [
            ctx["put_text"]("重新生成后，所有已登录用户需要重新登录。"),
            ctx["put_buttons"]([
                {"label": "确认生成", "value": "confirm", "color": "warning"},
                {"label": "取消", "value": "cancel", "color": "default"},
            ], onclick=lambda v: v),
        ])
        
        if confirm == "confirm":
            new_secret = secrets.token_hex(32)
            set_config("auth", "secret", new_secret)
            ctx["toast"]("认证密钥已重新生成", color="success")
            ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()
