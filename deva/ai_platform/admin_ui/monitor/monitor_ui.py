"""Monitor UI implemented with pywebio."""

from __future__ import annotations

import json
import re

import pandas as pd


def _match_stream(ctx, name_or_id):
    for stream in ctx["Stream"].instances():
        if getattr(stream, "name", None) == name_or_id or str(hash(stream)) == str(name_or_id):
            return stream
    return None


def _get_valid_scope_name(prefix, name):
    valid_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    return f"{prefix}_{valid_name}"


async def render_monitor_home(ctx):
    await ctx["init_admin_ui"]("Deva监控")
    ctx["put_markdown"]("### 监控总览")
    
    streams = list(ctx["Stream"].instances())
    
    stream_table = [["流名称", "流信息", "操作"]]
    for stream in streams:
        sid = str(hash(stream))
        name = getattr(stream, "name", "") or sid
        text = str(stream)
        actions = ctx["put_buttons"](
            [{"label": "查看", "value": sid}],
            onclick=lambda sid=sid: ctx["run_async"](view_stream(ctx, sid))
        )
        stream_table.append([name, text[:80] + "..." if len(text) > 80 else text, actions])
    
    if len(stream_table) == 1:
        stream_table.append(["暂无流", "-", "-"])
    
    ctx["put_table"](stream_table)
    
    ctx["put_markdown"]("### 执行代码")
    ctx["put_input"]("exec_command", type="text", value="", placeholder="例如: 1+1 或 a=1")
    ctx["put_button"]("执行", onclick=lambda: ctx["run_async"](exec_command(ctx)))
    ctx["set_scope"]("exec_result")


async def exec_command(ctx):
    command = await ctx["pin"].exec_command
    if not command or not command.strip():
        ctx["toast"]("请输入命令", color="warning")
        return
    
    command >> ctx["log"]
    
    with ctx["use_scope"]("exec_result", clear=True):
        try:
            if "=" in command:
                var_name, expr = command.replace(" ", "").split("=", 1)
                ctx["global_ns"][var_name] = eval(expr, ctx["global_ns"])
                ctx["put_markdown"](f"**执行结果:**\n```\nexec: {command}\n```")
            else:
                answer = eval(command, ctx["global_ns"])
                ctx["put_markdown"](f"**执行结果:**\n```\n{command}\n{answer}\n```")
        except Exception as e:
            ctx["put_markdown"](f"**错误:**\n```\n{e}\n```")


async def render_all_streams(ctx):
    await ctx["init_admin_ui"]("所有流")
    ctx["put_markdown"]("### 所有数据流")
    
    streams = list(ctx["Stream"].instances())
    
    stream_table = [["流信息", "操作"]]
    for stream in streams:
        sid = str(hash(stream))
        text = str(stream)
        actions = ctx["put_buttons"](
            [{"label": "查看", "value": sid}],
            onclick=lambda sid=sid: ctx["run_async"](view_stream(ctx, sid))
        )
        stream_table.append([text[:100] + "..." if len(text) > 100 else text, actions])
    
    if len(stream_table) == 1:
        stream_table.append(["暂无流", "-"])
    
    ctx["put_table"](stream_table)


async def render_all_tables(ctx):
    await ctx["init_admin_ui"]("所有表")
    ctx["put_markdown"]("### 所有数据表")
    
    tables = list(ctx["NB"]("default").tables)
    
    table_table = [["表名称", "操作"]]
    for tablename in tables:
        actions = ctx["put_buttons"](
            [{"label": "查看键", "value": tablename}],
            onclick=lambda name=tablename: ctx["run_async"](view_table_keys(ctx, name))
        )
        table_table.append([str(tablename), actions])
    
    if len(table_table) == 1:
        table_table.append(["暂无表", "-"])
    
    ctx["put_table"](table_table)


async def view_table_keys(ctx, tablename):
    try:
        table = ctx["NB"](tablename)
    except Exception:
        ctx["toast"](f"表不存在: {tablename}", color="error")
        return
    
    scope_name = _get_valid_scope_name("table_keys", tablename)
    
    with ctx["use_scope"](scope_name, clear=True):
        ctx["put_markdown"](f"### 表: {tablename}")
        
        keys = ctx["sample"](20) << table.keys()
        
        key_table = [["键", "操作"]]
        for key in keys:
            key_text = str(key)
            actions = ctx["put_buttons"](
                [{"label": "查看值", "value": key_text}],
                onclick=lambda k=key_text, t=tablename: ctx["run_async"](view_table_value(ctx, t, k))
            )
            key_table.append([key_text[:50] + "..." if len(key_text) > 50 else key_text, actions])
        
        if len(key_table) == 1:
            key_table.append(["无键", "-"])
        
        ctx["put_table"](key_table)
        ctx["put_button"]("关闭", onclick=lambda: ctx["clear"](scope_name))


async def view_table_value(ctx, tablename, key):
    try:
        data = ctx["NB"](tablename).get(key)
    except Exception:
        ctx["toast"](f"获取数据失败: {tablename}/{key}", color="error")
        return
    
    scope_name = _get_valid_scope_name("table_value", f"{tablename}_{key}")
    
    with ctx["use_scope"](scope_name, clear=True):
        ctx["put_markdown"](f"### {tablename} / {key}")
        
        if isinstance(data, list):
            rows = data[:250]
            try:
                df = pd.DataFrame(rows)
                ctx["put_html"](df.to_html())
            except Exception:
                ctx["put_code"](json.dumps(rows, ensure_ascii=False, indent=2)[:5000], "json")
        elif isinstance(data, dict):
            ctx["put_code"](json.dumps(data, ensure_ascii=False, indent=2)[:5000], "json")
        elif isinstance(data, pd.DataFrame):
            ctx["put_html"](data.head(250).to_html())
        else:
            ctx["put_code"](json.dumps({key: str(data)}, ensure_ascii=False, indent=2), "json")
        
        ctx["put_button"]("关闭", onclick=lambda: ctx["clear"](scope_name))


async def view_stream(ctx, stream_id):
    stream = _match_stream(ctx, stream_id)
    if stream is None:
        ctx["toast"](f"流不存在: {stream_id}", color="error")
        return
    
    stream_name = getattr(stream, "name", "") or stream_id
    
    with ctx["popup"](f"流: {stream_name}", size="large"):
        ctx["put_html"](
            f'<iframe src="/{stream_id}" style="width:100%;height:70vh;border:1px solid #e5e7eb;border-radius:12px;background:#fff;"></iframe>'
        )
