"""Naja 配置管理 UI

提供集中的配置管理界面，包括：
- 系统配置（认证、数据源、策略、任务、字典等）
- 文件配置管理（任务/策略/数据源/字典）
"""

import secrets
from typing import Dict, Any

from pywebio.output import put_text, put_markdown, put_table, put_buttons, put_html, toast, popup
from pywebio.input import input_group, input, select, NUMBER, PASSWORD, textarea, checkbox, actions
from pywebio.session import run_async

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
    get_noise_filter_config,
    get_block_noise_config,
    get_memory_config,
    get_llm_config,
    get_radar_config,
    ensure_auth_secret,
    reset_to_default,
    DEFAULT_CONFIG,
)


def render_config_page(ctx: dict):
    """渲染配置管理页面（集中式配置管理 + 文件配置管理）"""
    ctx["set_scope"]("config_content")
    apply_strategy_like_styles(ctx, scope="config_content")

    ctx["put_html"](
        '<div style="margin:0 0 14px 0;">'
        '<div style="font-size:24px;font-weight:700;color:#2c3e50;">⚙️ Naja 配置管理</div>'
        '<div style="font-size:13px;color:#6c757d;margin-top:6px;">管理数据源、策略、任务、字典等模块的配置参数</div>'
        '</div>',
        scope="config_content"
    )

    ctx["put_html"]('<div style="margin:16px 0;">', scope="config_content")
    ctx["put_buttons"]([
        {"label": "🔐 认证配置", "value": "auth", "color": "warning"},
        {"label": "📡 数据源配置", "value": "datasource", "color": "info"},
        {"label": "📈 策略配置", "value": "strategy", "color": "primary"},
        {"label": "⏰ 任务配置", "value": "task", "color": "success"},
        {"label": "📚 字典配置", "value": "dictionary", "color": "default"},
        {"label": "🧠 记忆配置", "value": "memory", "color": "primary"},
        {"label": "🧭 雷达配置", "value": "radar", "color": "info"},
        {"label": "🤖 LLM 调节", "value": "llm", "color": "warning"},
        {"label": "📱 钉钉通知", "value": "dtalk", "color": "success"},
        {"label": "⚡ 性能监控", "value": "performance", "color": "danger"},
        {"label": "🔇 个股噪音", "value": "noise_filter", "color": "secondary"},
        {"label": "🏢 题材噪音", "value": "block_noise", "color": "secondary"},
        {"label": "📁 文件配置", "value": "file_config", "color": "info"},
    ], onclick=lambda v: run_async(_show_config_dialog(ctx, v)), group=True, scope="config_content")
    ctx["put_html"]('</div>', scope="config_content")

    _render_config_summary(ctx)


def _render_config_summary(ctx: dict):
    """渲染配置摘要"""
    ctx["set_scope"]("config_summary")
    ctx["put_html"]('<div style="margin:8px 0 10px 0;font-size:18px;font-weight:600;color:#333;">📊 当前配置摘要</div>', scope="config_summary")

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
        f"默认间隔: {dict_config.get('default_interval', 300)}s",
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
    config_data.append([
        "⚡ 性能监控",
        f"锁监控: {'启用' if lock_enabled else '禁用'}\nWeb请求: {'启用' if web_enabled else '禁用'}",
        f"阈值: {perf_config.get('lock_monitoring_threshold_ms', 100)}ms"
    ])

    memory_config = get_memory_config()
    config_data.append([
        "🧠 记忆",
        f"自动保存: {'启用' if memory_config.get('auto_save_enabled', True) else '禁用'}",
        f"保存间隔: {memory_config.get('auto_save_interval', 300)}s"
    ])

    radar_config = get_radar_config()
    config_data.append([
        "🧭 雷达",
        f"事件保留: {radar_config.get('event_retention_days', 7)} 天",
        f"清理间隔: {radar_config.get('cleanup_interval_seconds', 600)}s"
    ])

    llm_config = get_llm_config()
    config_data.append([
        "🤖 LLM 调节",
        f"自动调节：{'启用' if llm_config.get('auto_adjust_enabled', True) else '禁用'}",
        f"调节间隔：{llm_config.get('auto_adjust_interval_seconds', 900)}s"
    ])

    # 钉钉通知配置
    dtalk_webhook = get_config("dtalk.webhook", "")
    config_data.append([
        "📱 钉钉通知",
        f"状态：{'✓ 已配置' if dtalk_webhook else '✗ 未配置'}",
        f"Webhook: {dtalk_webhook[:30] + '...' if dtalk_webhook else '无'}"
    ])

    nf_config = get_noise_filter_config()
    config_data.append([
        "🔇 个股噪音",
        f"状态: {'启用' if nf_config.get('enabled', True) else '禁用'}\n最小金额: {nf_config.get('min_amount', 1000000):,.0f}",
        f"B股过滤: {'启用' if nf_config.get('filter_b_shares', True) else '禁用'}"
    ])

    block_nf_config = get_block_noise_config()
    config_data.append([
        "🏢 题材噪音",
        f"状态: {'启用' if block_nf_config.get('enabled', True) else '禁用'}",
        f"噪音模式: {len(block_nf_config.get('blacklist_patterns', []))} 个"
    ])

    ctx["put_html"](render_stats_cards([
        {"label": "配置模块", "value": 11, "gradient": "linear-gradient(135deg,#667eea,#764ba2)", "shadow": "rgba(102,126,234,0.3)"},
        {"label": "启用开发模式", "value": 1 if auth_config.get('dev_mode', False) else 0, "gradient": "linear-gradient(135deg,#f0ad4e,#ec971f)", "shadow": "rgba(240,173,78,0.3)"},
        {"label": "默认策略窗口", "value": strategy_config.get('default_window_size', 5), "gradient": "linear-gradient(135deg,#11998e,#38ef7d)", "shadow": "rgba(17,153,142,0.3)"},
    ]), scope="config_summary")

    ctx["put_table"](config_data, scope="config_summary")


async def _show_config_dialog(ctx: dict, category: str):
    """显示配置对话框"""
    if category == "file_config":
        from .ui_file import render_config_list
        with ctx["popup"]("📁 文件配置管理", size="large", closable=True):
            await render_config_list(ctx, "task")
        return

    defaults = DEFAULT_CONFIG.get(category, {})

    category_names = {
        "auth": "认证",
        "datasource": "数据源",
        "strategy": "策略",
        "task": "任务",
        "dictionary": "字典",
        "memory": "记忆",
        "radar": "雷达",
        "llm": "LLM 调节",
        "dtalk": "钉钉通知",
        "performance": "性能监控",
        "noise_filter": "个股噪音",
        "block_noise": "题材噪音",
    }

    config_getters = {
        "auth": get_auth_config,
        "datasource": get_datasource_config,
        "strategy": get_strategy_config,
        "task": get_task_config,
        "dictionary": get_dictionary_config,
        "memory": get_memory_config,
        "radar": lambda: vars(get_radar_config()).get('_config', {}) if hasattr(get_radar_config(), '_config') else {},
        "llm": get_llm_config,
        "performance": lambda: get_config("performance") or {},
        "noise_filter": get_noise_filter_config,
        "block_noise": get_block_noise_config,
    }

    config = config_getters.get(category, lambda: {})()

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
        elif category == "dtalk":
            await _render_dtalk_config(ctx, config, defaults)
        elif category == "noise_filter":
            await _render_noise_filter_config(ctx, config, defaults)
        elif category == "block_noise":
            await _render_block_noise_config(ctx, config, defaults)


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
    form = await ctx["input_group"]("数据源配置", [
        ctx["input"]("默认间隔(秒)", name="default_interval", type="number",
                    value=config.get("default_interval", defaults.get("default_interval", 5))),
        ctx["input"]("最大重试次数", name="max_retries", type="number",
                    value=config.get("max_retries", defaults.get("max_retries", 3))),
        ctx["input"]("重试延迟(秒)", name="retry_delay", type="number",
                    value=config.get("retry_delay", defaults.get("retry_delay", 1.0))),
        ctx["input"]("超时时间(秒)", name="timeout", type="number",
                    value=config.get("timeout", defaults.get("timeout", 30))),
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
        })
        ctx["toast"]("数据源配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "reset":
        reset_to_default("datasource")
        ctx["toast"]("已恢复默认配置", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _render_noise_filter_config(ctx: dict, config: dict, defaults: dict):
    """渲染噪音过滤配置"""
    form = await ctx["input_group"]("噪音过滤配置", [
        ctx["select"]("启用噪音过滤", name="enabled",
                     options=[{"label": "是", "value": "1"}, {"label": "否", "value": "0"}],
                     value="1" if config.get("enabled", defaults.get("enabled", True)) else "0"),
        ctx["input"]("最小成交金额(元)", name="min_amount", type="number",
                    value=config.get("min_amount", defaults.get("min_amount", 1000000))),
        ctx["input"]("最小成交量(股)", name="min_volume", type="number",
                    value=config.get("min_volume", defaults.get("min_volume", 100000))),
        ctx["input"]("最小价格(元)", name="min_price", type="number",
                    value=config.get("min_price", defaults.get("min_price", 1.0))),
        ctx["input"]("最大价格(元)", name="max_price", type="number",
                    value=config.get("max_price", defaults.get("max_price", 1000.0))),
        ctx["select"]("过滤B股", name="filter_b_shares",
                     options=[{"label": "是", "value": "1"}, {"label": "否", "value": "0"}],
                     value="1" if config.get("filter_b_shares", defaults.get("filter_b_shares", True)) else "0"),
        ctx["select"]("过滤ST股", name="filter_st",
                     options=[{"label": "是", "value": "1"}, {"label": "否", "value": "0"}],
                     value="1" if config.get("filter_st", defaults.get("filter_st", False)) else "0"),
        ctx["textarea"]("黑名单(逗号/换行分隔)", name="blacklist",
                        value="\n".join(config.get("blacklist", defaults.get("blacklist", []))),
                        help_text="强制过滤的股票代码列表"),
        ctx["textarea"]("白名单(逗号/换行分隔)", name="whitelist",
                        value="\n".join(config.get("whitelist", defaults.get("whitelist", []))),
                        help_text="保护不被过滤的股票代码列表"),
        ctx["actions"]("操作", [
            {"label": "保存", "value": "save", "color": "primary"},
            {"label": "恢复默认", "value": "reset", "color": "warning"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])

    if form and form.get("action") == "save":
        set_category_config("noise_filter", {
            "enabled": form.get("enabled") == "1",
            "min_amount": float(form.get("min_amount", 1000000)),
            "min_volume": float(form.get("min_volume", 100000)),
            "min_price": float(form.get("min_price", 1.0)),
            "max_price": float(form.get("max_price", 1000.0)),
            "filter_b_shares": form.get("filter_b_shares") == "1",
            "filter_st": form.get("filter_st") == "1",
            "blacklist": _split_list(form.get("blacklist", "")),
            "whitelist": _split_list(form.get("whitelist", "")),
        })
        ctx["toast"]("噪音过滤配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "reset":
        reset_to_default("noise_filter")
        ctx["toast"]("已恢复默认配置", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _render_block_noise_config(ctx: dict, config: dict, defaults: dict):
    """渲染题材噪音配置"""
    patterns_text = "\n".join(config.get("blacklist_patterns", defaults.get("blacklist_patterns", [])))

    form = await ctx["input_group"]("题材噪音配置", [
        ctx["select"]("启用题材噪音过滤", name="enabled",
                     options=[{"label": "是", "value": "1"}, {"label": "否", "value": "0"}],
                     value="1" if config.get("enabled", defaults.get("enabled", True)) else "0"),
        ctx["select"]("启用自动黑名单", name="auto_blacklist_enabled",
                     options=[{"label": "是", "value": "1"}, {"label": "否", "value": "0"}],
                     value="1" if config.get("auto_blacklist_enabled", defaults.get("auto_blacklist_enabled", True)) else "0"),
        ctx["input"]("最低热点阈值", name="min_attention_threshold", type="number",
                    value=config.get("min_attention_threshold", defaults.get("min_attention_threshold", 0.01)),
                    help_text="低于此热点阈值的题材将被过滤"),
        ctx["textarea"]("噪音模式(每行一个)", name="blacklist_patterns",
                       value=patterns_text,
                       help_text="题材名称中包含这些关键词的将被过滤"),
        ctx["actions"]("操作", [
            {"label": "保存", "value": "save", "color": "primary"},
            {"label": "恢复默认", "value": "reset", "color": "warning"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])

    if form and form.get("action") == "save":
        set_category_config("block_noise", {
            "enabled": form.get("enabled") == "1",
            "auto_blacklist_enabled": form.get("auto_blacklist_enabled") == "1",
            "min_attention_threshold": float(form.get("min_attention_threshold", 0.01)),
            "blacklist_patterns": _split_list(form.get("blacklist_patterns", "")),
        })
        ctx["toast"]("题材噪音配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "reset":
        reset_to_default("block_noise")
        ctx["toast"]("已恢复默认配置", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _render_performance_config(ctx: dict, config: dict, defaults: dict):
    """渲染性能监控配置"""
    ctx["put_markdown"]("### 性能监控配置")
    ctx["put_markdown"]("开启/关闭各类性能监控功能")

    lock_enabled = config.get("lock_monitoring_enabled", False)
    web_enabled = config.get("web_request_monitoring_enabled", True)
    lock_threshold = config.get("lock_monitoring_threshold_ms", 100)

    form = await ctx["input_group"]("性能监控配置", [
        ctx["select"]("锁监控", name="lock_monitoring_enabled",
                     options=[{"label": "启用", "value": "1"}, {"label": "禁用", "value": "0"}],
                     value="1" if lock_enabled else "0"),
        ctx["select"]("Web请求监控", name="web_request_monitoring_enabled",
                     options=[{"label": "启用", "value": "1"}, {"label": "禁用", "value": "0"}],
                     value="1" if web_enabled else "0"),
        ctx["input"]("锁监控阈值(ms)", name="lock_monitoring_threshold_ms", type="number",
                    value=lock_threshold),
        ctx["actions"]("操作", [
            {"label": "保存", "value": "save", "color": "primary"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])

    if form and form.get("action") == "save":
        set_config("performance", {
            "lock_monitoring_enabled": form.get("lock_monitoring_enabled") == "1",
            "web_request_monitoring_enabled": form.get("web_request_monitoring_enabled") == "1",
            "lock_monitoring_threshold_ms": int(form.get("lock_monitoring_threshold_ms", 100)),
        })
        ctx["toast"]("性能监控配置已保存", color="success")
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
        ctx["select"]("自动加载", name="auto_load_on_start",
                     options=[{"label": "是", "value": "1"}, {"label": "否", "value": "0"}],
                     value="1" if config.get("auto_load_on_start", defaults.get("auto_load_on_start", True)) else "0"),
        ctx["select"]("自动保存", name="auto_save_enabled",
                     options=[{"label": "是", "value": "1"}, {"label": "否", "value": "0"}],
                     value="1" if config.get("auto_save_enabled", defaults.get("auto_save_enabled", True)) else "0"),
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
            "auto_load_on_start": form.get("auto_load_on_start") == "1",
            "auto_save_enabled": form.get("auto_save_enabled") == "1",
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
        radar = get_radar_config()
        radar.update({
            "event_retention_days": float(form.get("event_retention_days", 7)),
            "cleanup_interval_seconds": int(form.get("cleanup_interval_seconds", 600)),
        })
        ctx["toast"]("雷达配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "reset":
        radar = get_radar_config()
        radar.update({"event_retention_days": 7, "cleanup_interval_seconds": 600})
        ctx["toast"]("已恢复默认配置", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _render_llm_config(ctx: dict, config: dict, defaults: dict):
    """渲染 LLM 调节配置"""
    form = await ctx["input_group"]("LLM 调节配置", [
        ctx["select"]("自动调节", name="auto_adjust_enabled",
                     options=[{"label": "是", "value": "1"}, {"label": "否", "value": "0"}],
                     value="1" if config.get("auto_adjust_enabled", defaults.get("auto_adjust_enabled", True)) else "0"),
        ctx["input"]("最小调节间隔 (秒)", name="min_interval_seconds", type="number",
                    value=config.get("min_interval_seconds", defaults.get("min_interval_seconds", 300))),
        ctx["input"]("自动调节间隔 (秒)", name="auto_adjust_interval_seconds", type="number",
                    value=config.get("auto_adjust_interval_seconds", defaults.get("auto_adjust_interval_seconds", 900))),
        ctx["input"]("最小雷达事件数", name="auto_adjust_min_events", type="number",
                    value=config.get("auto_adjust_min_events", defaults.get("auto_adjust_min_events", 3))),
        ctx["actions"]("操作", [
            {"label": "保存", "value": "save", "color": "primary"},
            {"label": "恢复默认", "value": "reset", "color": "warning"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])

    if form and form.get("action") == "save":
        set_category_config("llm", {
            "auto_adjust_enabled": form.get("auto_adjust_enabled") == "1",
            "min_interval_seconds": int(form.get("min_interval_seconds", 300)),
            "auto_adjust_interval_seconds": int(form.get("auto_adjust_interval_seconds", 900)),
            "auto_adjust_min_events": int(form.get("auto_adjust_min_events", 3)),
        })
        ctx["toast"]("LLM 调节配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "reset":
        reset_to_default("llm")
        ctx["toast"]("已恢复默认配置", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _render_dtalk_config(ctx: dict, config: dict, defaults: dict):
    """渲染钉钉通知配置"""
    from pywebio.input import input
    
    ctx["put_markdown"]("### 📱 钉钉通知配置")
    ctx["put_markdown"]("配置流动性预测系统的钉钉机器人通知。")
    ctx["put_markdown"]("> **获取钉钉机器人 Webhook**: 在钉钉群中添加自定义机器人，复制 Webhook 地址")
    
    dtalk_webhook = config.get("dtalk.webhook", "")
    dtalk_secret = config.get("dtalk.secret", "")
    
    form = await ctx["input_group"]("钉钉通知配置", [
        ctx["input"]("钉钉机器人 Webhook", name="webhook", type="text",
                    value=dtalk_webhook,
                    placeholder="https://oapi.dingtalk.com/robot/send?access_token=xxx"),
        ctx["input"]("签名密钥 (Secret)", name="secret", type=ctx["PASSWORD"],
                    value="",  # 不显示已保存的密钥，避免泄露
                    placeholder="SEC 开头的安全设置密钥（可选但推荐）"),
        ctx["actions"]("操作", [
            {"label": "保存配置", "value": "save", "color": "primary"},
            {"label": "测试发送", "value": "test", "color": "success"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])
    
    if form and form.get("action") == "save":
        webhook = form.get("webhook", "").strip()
        secret = form.get("secret", "").strip()
        
        if not webhook:
            ctx["toast"]("Webhook 地址不能为空", color="error")
            return
        
        # 保存配置
        set_config("dtalk.webhook", webhook)
        if secret:  # 只有填写了新密钥才更新
            set_config("dtalk.secret", secret)
        
        ctx["toast"]("钉钉通知配置已保存", color="success")
        ctx["close_popup"]()
        
    elif form and form.get("action") == "test":
        webhook = form.get("webhook", "").strip()
        
        if not webhook:
            ctx["toast"]("Webhook 地址不能为空", color="error")
            return
        
        # 临时保存配置用于测试
        set_config("dtalk.webhook", webhook)
        if form.get("secret", "").strip():
            set_config("dtalk.secret", form.get("secret", "").strip())
        
        # 发送测试消息
        try:
            from deva.endpoints import Dtalk
            
            test_message = "@md@Naja 流动性预测系统测试|✅ 钉钉通知配置成功！\n\n系统已正确配置，可以正常发送通知。"
            test_message >> Dtalk()
            
            ctx["toast"]("测试消息发送成功！", color="success")
        except Exception as e:
            ctx["toast"](f"发送失败：{str(e)}", color="error")
            
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _render_auth_config(ctx: dict, config: dict, defaults: dict):
    """渲染认证配置"""
    ctx["put_markdown"]("### 🔐 认证配置")
    ctx["put_markdown"]("管理管理员登录凭证。")

    form = await ctx["input_group"]("认证配置", [
        ctx["input"]("管理员用户名", name="username",
                    value=config.get("username", defaults.get("username", "")),
                    placeholder="请输入管理员用户名"),
        ctx["input"]("新密码", name="password", type=PASSWORD,
                    value="", placeholder="输入新密码（留空则不修改）"),
        ctx["input"]("确认新密码", name="password_confirm", type=PASSWORD,
                    value="", placeholder="再次输入新密码"),
        ctx["select"]("开发模式", name="dev_mode",
                     options=[{"label": "是", "value": "1"}, {"label": "否", "value": "0"}],
                     value="1" if config.get("dev_mode", defaults.get("dev_mode", False)) else "0",
                     help_text="启用后跳过认证，仅用于开发环境"),
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
            from . import set_auth_config
            set_auth_config(username=username, password=password, dev_mode=form.get("dev_mode") == "1")
        else:
            from . import set_auth_config
            set_auth_config(username=username, dev_mode=form.get("dev_mode") == "1")

        ctx["toast"]("认证配置已保存", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "regen_secret":
        new_secret = secrets.token_hex(32)
        set_config("auth_secret", new_secret)
        ctx["toast"]("认证密钥已重新生成", color="success")
        ctx["close_popup"]()
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


__all__ = [
    'render_config_page',
]