"""File Configuration UI - 文件配置管理界面

提供文件配置的管理界面，包括任务、策略、数据源、字典等配置文件的管理。
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

from pywebio.output import put_html, put_buttons, put_table, put_markdown, toast
from pywebio.input import input_group, input, select, actions
from pywebio.session import run_async

from .file_config import (
    BASE_CONFIG_DIR,
    get_config_dir,
    get_config_path,
    load_raw_config,
    save_raw_config,
    delete_raw_config,
    ensure_config_dirs,
)


CONFIG_TYPE_NAMES = {
    "task": "任务",
    "strategy": "策略",
    "datasource": "数据源",
    "dictionary": "字典",
}

CONFIG_TYPE_DIRS = {
    "task": "tasks",
    "strategy": "strategies",
    "datasource": "datasources",
    "dictionary": "dictionaries",
}


def _list_files(config_type: str) -> list:
    """列出指定类型的配置文件"""
    config_dir = get_config_dir(CONFIG_TYPE_DIRS.get(config_type, config_type))
    files = []
    if config_dir.exists():
        for f in config_dir.glob("*.yaml"):
            if not f.name.startswith("_"):
                files.append(f.name.replace(".yaml", ""))
        for f in config_dir.glob("*.json"):
            if not f.name.startswith("_"):
                files.append(f.name.replace(".json", ""))
    return sorted(files)


async def render_config_list(ctx: dict, config_type: str = "task"):
    """渲染配置文件列表

    Args:
        ctx: pywebio 上下文
        config_type: 配置类型 (task/strategy/datasource/dictionary)
    """
    ctx["set_scope"]("file_config_list")

    await _render_config_type_selector(ctx, config_type)
    await _render_config_file_list(ctx, config_type)


async def _render_config_type_selector(ctx: dict, current_type: str):
    """渲染配置类型选择器"""
    types = [
        ("task", "📋 任务"),
        ("strategy", "📊 策略"),
        ("datasource", "📡 数据源"),
        ("dictionary", "📖 字典"),
    ]

    buttons = []
    for type_id, label in types:
        color = "primary" if type_id == current_type else "secondary"
        buttons.append({"label": label, "value": type_id, "color": color})

    ctx["put_buttons"](buttons, onclick=lambda v: run_async(_on_type_selected(ctx, v)), scope="file_config_list")


async def _on_type_selected(ctx: dict, config_type: str):
    """当选择配置类型时"""
    ctx["clear"]("file_config_list")
    await render_config_list(ctx, config_type)


async def _render_config_file_list(ctx: dict, config_type: str):
    """渲染配置文件列表"""
    type_name = CONFIG_TYPE_NAMES.get(config_type, config_type)
    files = _list_files(config_type)

    ctx["put_html"](f'<div style="margin:12px 0;font-size:16px;font-weight:600;">{type_name}配置列表</div>', scope="file_config_list")

    if files:
        ctx["put_html"](f'<div style="color:#666;margin-bottom:12px;">共 {len(files)} 个配置文件</div>', scope="file_config_list")

        for fname in files:
            await _render_config_item(ctx, fname, config_type)
    else:
        ctx["put_html"](f'<div style="color:#999;padding:20px;text-align:center;">暂无{type_name}配置</div>', scope="file_config_list")

    ctx["put_html"]('<div style="margin-top:16px;">', scope="file_config_list")
    ctx["put_buttons"]([
        {"label": "➕ 创建新配置", "value": "create", "color": "success"},
    ], onclick=lambda v: run_async(_on_create_config(ctx, config_type)), scope="file_config_list")
    ctx["put_html"]('</div>', scope="file_config_list")


async def _render_config_item(ctx: dict, name: str, config_type: str):
    """渲染单个配置项"""
    type_name = CONFIG_TYPE_NAMES.get(config_type, config_type)

    ctx["put_html"](f"""
    <div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin-bottom:8px;background:#f9fafb;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
                <div style="font-weight:600;color:#374151;">{name}</div>
                <div style="font-size:12px;color:#6b7280;margin-top:2px;">{type_name}</div>
            </div>
            <div style="display:flex;gap:8px;">
                <button onclick="PyWebIO.call_api('view_file_config', {{'name':'{name}','type':'{config_type}'}})" style="padding:4px 12px;background:#3b82f6;color:white;border:none;border-radius:4px;cursor:pointer;">查看</button>
                <button onclick="PyWebIO.call_api('edit_file_config', {{'name':'{name}','type':'{config_type}'}})" style="padding:4px 12px;background:#f59e0b;color:white;border:none;border-radius:4px;cursor:pointer;">编辑</button>
                <button onclick="PyWebIO.call_api('delete_file_config', {{'name':'{name}','type':'{config_type}'}})" style="padding:4px 12px;background:#ef4444;color:white;border:none;border-radius:4px;cursor:pointer;">删除</button>
            </div>
        </div>
    </div>
    """, scope="file_config_list")

    ctx[f"view_file_config"] = lambda name=name, type=config_type: _on_view_config(ctx, name, type)
    ctx[f"edit_file_config"] = lambda name=name, type=config_type: _on_edit_config(ctx, name, type)
    ctx[f"delete_file_config"] = lambda name=name, type=config_type: _on_delete_config(ctx, name, type)


async def _on_view_config(ctx: dict, name: str, config_type: str):
    """查看配置"""
    data = load_raw_config(name, CONFIG_TYPE_DIRS.get(config_type, config_type))
    type_name = CONFIG_TYPE_NAMES.get(config_type, config_type)

    if data:
        import yaml
        content = yaml.dump(data, allow_unicode=True, default_flow_style=False)
        with ctx["popup"](f"📄 {name} 配置内容", size="large", closable=True):
            ctx["put_html"](f'<pre style="background:#f5f5f5;padding:16px;border-radius:8px;overflow:auto;max-height:400px;font-size:13px;"><code>{content}</code></pre>')
    else:
        ctx["toast"](f"加载配置失败", color="error")


async def _on_edit_config(ctx: dict, name: str, config_type: str):
    """编辑配置"""
    type_name = CONFIG_TYPE_NAMES.get(config_type, config_type)
    data = load_raw_config(name, CONFIG_TYPE_DIRS.get(config_type, config_type))

    if not data:
        ctx["toast"](f"加载配置失败", color="error")
        return

    import yaml
    content = yaml.dump(data, allow_unicode=True, default_flow_style=False)

    form = await ctx["input_group"](f"编辑 {type_name} 配置", [
        ctx["textarea"]("配置内容 (YAML)", name="content", value=content,
                       code={'theme': 'monokai'}, rows=20),
        ctx["actions"]("操作", [
            {"label": "💾 保存", "value": "save", "color": "primary"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])

    if form and form.get("action") == "save":
        try:
            new_data = yaml.safe_load(form.get("content", ""))
            if new_data is None:
                new_data = {}
            success = save_raw_config(name, CONFIG_TYPE_DIRS.get(config_type, config_type), new_data)
            if success:
                ctx["toast"]("配置已保存", color="success")
                ctx["close_popup"]()
            else:
                ctx["toast"]("保存失败", color="error")
        except Exception as e:
            ctx["toast"](f"YAML 解析错误: {str(e)}", color="error")
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _on_delete_config(ctx: dict, name: str, config_type: str):
    """删除配置"""
    type_name = CONFIG_TYPE_NAMES.get(config_type, config_type)

    form = await ctx["input_group"]("确认删除", [
        ctx["put_html"](f"<div style='padding:10px;background:#fef2f2;border-radius:8px;color:#b91c1c;'>"
                       f"⚠️ 确定要删除配置 <strong>{name}</strong> 吗？此操作不可恢复。</div>"),
        ctx["actions"]("操作", [
            {"label": "🗑️ 确认删除", "value": "delete", "color": "danger"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])

    if form and form.get("action") == "delete":
        success = delete_raw_config(name, CONFIG_TYPE_DIRS.get(config_type, config_type))
        if success:
            ctx["toast"]("配置已删除", color="success")
            ctx["close_popup"]()
            ctx["clear"]("file_config_list")
            await render_config_list(ctx, config_type)
        else:
            ctx["toast"]("删除失败", color="error")
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


async def _on_create_config(ctx: dict, config_type: str):
    """创建新配置"""
    type_name = CONFIG_TYPE_NAMES.get(config_type, config_type)

    form = await ctx["input_group"]("创建新配置", [
        ctx["input"]("配置名称", name="name", placeholder="输入配置名称"),
        ctx["textarea"]("配置内容 (YAML)", name="content", value="# 配置内容\n",
                       code={'theme': 'monokai'}, rows=20),
        ctx["actions"]("操作", [
            {"label": "💾 创建", "value": "create", "color": "primary"},
            {"label": "取消", "value": "cancel", "color": "default"},
        ], name="action"),
    ])

    if form and form.get("action") == "create":
        name = form.get("name", "").strip()
        if not name:
            ctx["toast"]("名称不能为空", color="error")
            return

        try:
            data = yaml.safe_load(form.get("content", "")) or {}
            success = save_raw_config(name, CONFIG_TYPE_DIRS.get(config_type, config_type), data)
            if success:
                ctx["toast"]("配置已创建", color="success")
                ctx["close_popup"]()
                ctx["clear"]("file_config_list")
                await render_config_list(ctx, config_type)
            else:
                ctx["toast"]("创建失败", color="error")
        except Exception as e:
            ctx["toast"](f"YAML 解析错误: {str(e)}", color="error")
    elif form and form.get("action") == "cancel":
        ctx["close_popup"]()


__all__ = ['render_config_list']
