"""Naja 配置管理 UI"""

from pywebio.output import put_text, put_markdown, put_table, put_buttons, put_html, toast, popup, close_popup, put_row
from pywebio.input import input_group, input, select, NUMBER, PASSWORD
from pywebio.session import run_async
from pywebio import pin

from . import (
    get_config,
    set_config,
    set_category_config,
    get_datasource_config,
    get_strategy_config,
    get_task_config,
    get_dictionary_config,
    get_auth_config,
    ensure_auth_secret,
    reset_to_default,
    DEFAULT_CONFIG,
)


def render_config_page(ctx: dict):
    """渲染配置管理页面"""
    ctx["put_markdown"]("## ⚙️ Naja 配置管理")
    ctx["put_markdown"]("管理数据源、策略、任务、字典四个模块的配置参数。配置存储在 `NB('naja_config')` 命名空间中。")
    
    ctx["put_html"]('<div style="margin:16px 0;">')
    ctx["put_buttons"]([
        {"label": "🔐 认证配置", "value": "auth"},
        {"label": "📡 数据源配置", "value": "datasource"},
        {"label": "📈 策略配置", "value": "strategy"},
        {"label": "⏰ 任务配置", "value": "task"},
        {"label": "📚 字典配置", "value": "dictionary"},
    ], onclick=lambda v: run_async(_show_config_dialog(ctx, v)), group=True)
    ctx["put_html"]('</div>')
    
    _render_config_summary(ctx)


def _render_config_summary(ctx: dict):
    """渲染配置摘要"""
    ctx["put_markdown"]("### 当前配置摘要")
    
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
        ctx["actions"]("操作", [
            {"label": "保存", "value": "save"},
            {"label": "恢复默认", "value": "reset"},
            {"label": "取消", "value": "cancel"},
        ], name="action"),
    ])
    
    if form and form.get("action") == "save":
        set_category_config("datasource", {
            "default_interval": int(form.get("default_interval", 5)),
            "max_retries": int(form.get("max_retries", 3)),
            "retry_delay": float(form.get("retry_delay", 1.0)),
            "timeout": int(form.get("timeout", 30)),
            "enabled_types": form.get("enabled_types", ["timer", "custom", "replay"]),
        })
        ctx["toast"]("数据源配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "reset":
        reset_to_default("datasource")
        ctx["toast"]("已恢复默认配置", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


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
            {"label": "保存", "value": "save"},
            {"label": "恢复默认", "value": "reset"},
            {"label": "取消", "value": "cancel"},
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
            {"label": "保存", "value": "save"},
            {"label": "恢复默认", "value": "reset"},
            {"label": "取消", "value": "cancel"},
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
            {"label": "保存", "value": "save"},
            {"label": "恢复默认", "value": "reset"},
            {"label": "取消", "value": "cancel"},
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
            {"label": "保存", "value": "save"},
            {"label": "重新生成密钥", "value": "regen_secret"},
            {"label": "取消", "value": "cancel"},
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
                {"label": "确认生成", "value": "confirm"},
                {"label": "取消", "value": "cancel"},
            ], onclick=lambda v: v),
        ])
        
        if confirm == "confirm":
            new_secret = secrets.token_hex(32)
            set_config("auth", "secret", new_secret)
            ctx["toast"]("认证密钥已重新生成", color="success")
            ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()
