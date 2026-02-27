"""策略编辑模块

提供策略编辑和创建相关功能。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from deva import NS

from .strategy_unit import StrategyUnit, StrategyStatus
from .strategy_manager import get_manager
from .fault_tolerance import get_error_collector, get_metrics_collector
from ..datasource.datasource import get_ds_manager
from ..ai.ai_strategy_generator import (
    generate_strategy_code,
    validate_strategy_code,
    test_strategy_code,
    analyze_data_schema,
    build_datasource_context,
    build_schema_from_metadata,
)


DEFAULT_STRATEGY_FUNC_CODE = '''# 策略执行函数
# 必须定义 process(data) 函数，处理输入数据并返回结果

def process(data):
    """
    策略执行主体函数
    
    参数:
        data: 输入数据 (通常为 pandas.DataFrame)
    
    返回:
        处理后的数据
    """
    import pandas as pd
    import numpy as np
    from typing import Dict, Any
    
    # 示例：直接返回原始数据
    # 你可以在这里添加自定义处理逻辑
    
    # 示例：筛选涨幅大于5%的股票
    # if isinstance(data, pd.DataFrame) and 'p_change' in data.columns:
    #     return data[data['p_change'] > 5]
    
    return data
'''


async def _edit_strategy_dialog(ctx, unit_id: str):
    """编辑策略的弹窗，合并了配置和代码编辑功能"""
    manager = get_manager()
    unit = manager.get_unit(unit_id)
    
    if not unit:
        ctx["toast"]("策略不存在", color="error")
        return
    
    ds_mgr = get_ds_manager()
    sources = ds_mgr.list_source_objects()
    
    current_code = unit.metadata.strategy_func_code or unit._processor_code or DEFAULT_STRATEGY_FUNC_CODE
    
    # 构建数据源选项
    source_options = []
    for s in sources:
        if isinstance(s, dict):
            source_name = s.get('name', '')
            source_id = s.get('id', '')
            source_status = s.get('state', {}).get('status', 'stopped')
        else:
            source_name = getattr(s, 'name', '')
            source_id = getattr(s, 'id', '')
            source_status = getattr(s, 'status', 'stopped')
            if hasattr(source_status, 'value'):
                source_status = source_status.value
        
        status_label = "运行中" if source_status == "running" else "已停止"
        
        source_options.append({
            "label": f"{source_name} [{status_label}]",
            "value": source_id,
            "selected": source_id == unit.metadata.bound_datasource_id
        })
    
    if not any(s.get('selected') for s in source_options):
        source_options = [{"label": "无", "value": ""}] + source_options
    
    with ctx["popup"](f"编辑策略: {unit.name}", size="large", closable=True):
        ctx["put_markdown"]("### 策略配置")
        ctx["put_html"]("<p style='color:#666;font-size:12px;'>可以修改策略的基本信息、代码和绑定的数据源</p>")
        
        # 获取系统配置的最大历史记录条数
        from deva.config import get_config
        max_system_history = get_config("strategy", "max_history_count", 300)
        
        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("策略名称", name="name", required=True, value=unit.name),
            ctx["textarea"]("策略简介", name="summary", value=unit.metadata.summary or unit.metadata.description or "", rows=3),
            ctx["input"]("标签", name="tags", value=", ".join(unit.metadata.tags or [])),
            ctx["select"]("绑定数据源", name="datasource_id", options=source_options, value=unit.metadata.bound_datasource_id or ""),
            ctx["input"]("上游数据源", name="upstream", value=""),
            ctx["input"]("下游输出", name="downstream", value=""),
            ctx["input"]("历史记录保留条数", name="max_history_count", type="number", min=0, max=max_system_history, value=getattr(unit.metadata, "max_history_count", 30), placeholder="默认30，不超过系统限制"),
            ctx["textarea"]("执行代码", name="code", value=current_code, rows=15, code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "测试代码", "value": "test"},
                {"label": "AI生成", "value": "ai_generate"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not form or form.get("action") == "cancel":
            ctx["close_popup"]()
            return
        
        if form.get("action") == "test":
            ctx["put_markdown"]("### 测试代码")
            
            code = form.get("code", "")
            source = ds_mgr.get_source(form.get("datasource_id"))
            if source:
                recent_data = source.get_recent_data(1)
                if recent_data:
                    test_result = test_strategy_code(code, recent_data[0])
                    if test_result["success"]:
                        ctx["put_html"](f"<div style='color:#155724;background:#d4edda;padding:8px;border-radius:4px;margin-bottom:10px;'>✅ 测试通过，执行时间: {test_result['execution_time_ms']:.2f}ms</div>")
                        
                        output = test_result.get("output")
                        if output is not None:
                            ctx["put_markdown"]("**测试输出预览:**")
                            if isinstance(output, pd.DataFrame):
                                ctx["put_html"](output.head(5).to_html(classes='df-table', index=False))
                            else:
                                ctx["put_text"](str(output)[:500])
                    else:
                        ctx["put_html"](f"<div style='color:#721c24;background:#f8d7da;padding:8px;border-radius:4px;margin-bottom:10px;'>❌ 测试失败: {test_result.get('error', '未知错误')}</div>")
                else:
                    ctx["put_html"](f"<div style='color:#856404;background:#fff3cd;padding:8px;border-radius:4px;margin-bottom:10px;'>⚠️ 数据源暂无数据，无法测试</div>")
            else:
                ctx["put_html"](f"<div style='color:#856404;background:#fff3cd;padding:8px;border-radius:4px;margin-bottom:10px;'>⚠️ 请先选择数据源或确保数据源有数据</div>")
            
            ctx["put_row"]([
                ctx["put_button"]("保存", onclick=lambda: ctx["run_async"](_save_strategy(ctx, unit, form, code)), color="primary"),
            ])
            return
        
        if form.get("action") == "ai_generate":
            if not source_options or len(source_options) <= 1:
                ctx["toast"]("请先创建数据源，AI需要基于数据源结构生成代码", color="warning")
                return
            
            ai_form = await ctx["input_group"]("AI生成代码", [
                ctx["select"]("选择数据源", name="datasource_id", options=source_options[1:], required=True),  # 排除"无"选项
                ctx["textarea"]("需求描述", name="requirement", required=True, placeholder="描述你的策略需求，例如：筛选涨幅超过5%的股票", rows=4),
                ctx["actions"]("操作", [
                    {"label": "生成代码", "value": "generate"},
                    {"label": "取消", "value": "cancel"},
                ], name="action"),
            ])
            
            if not ai_form or ai_form.get("action") == "cancel":
                return
            
            source = ds_mgr.get_source(ai_form["datasource_id"])
            if not source:
                ctx["toast"]("数据源不存在", color="error")
                return
            
            datasource_context = build_datasource_context(source)
            
            recent_data = source.get_recent_data(1)
            sample_data = None
            if recent_data:
                sample_data = recent_data[0]
                data_schema = analyze_data_schema(sample_data)
                ctx["put_markdown"]("**数据结构分析（来自实际数据）:**")
            else:
                data_schema = build_schema_from_metadata(source)
                ctx["put_markdown"]("**数据结构分析（来自元数据推断）:**")
                ctx["put_html"]("<div style='color:#856404;background:#fff3cd;padding:8px;border-radius:4px;margin-bottom:10px;'>⚠️ 数据源暂无实际数据，AI将根据数据获取代码推断数据结构</div>")
            
            ctx["put_code"](json.dumps(data_schema, ensure_ascii=False, indent=2), language="json")
            
            ctx["put_markdown"]("**AI生成代码中...**")
            
            try:
                code = await generate_strategy_code(
                    ctx,
                    data_schema=data_schema,
                    user_requirement=ai_form["requirement"],
                    strategy_name=form.get("name", ""),
                    datasource_context=datasource_context,
                )
            except Exception as e:
                ctx["toast"](f"AI生成失败: {e}", color="error")
                return
            
            ctx["put_markdown"]("**生成的代码:**")
            ctx["put_code"](code, language="python")
            
            validation = validate_strategy_code(code)
            if validation["valid"]:
                ctx["put_html"]("<div style='color:#155724;background:#d4edda;padding:8px;border-radius:4px;'>✅ 代码验证通过</div>")
            else:
                ctx["put_html"](f"<div style='color:#721c24;background:#f8d7da;padding:8px;border-radius:4px;'>❌ 验证失败: {'; '.join(validation['errors'])}</div>")
                return
            
            if sample_data is not None:
                test_result = test_strategy_code(code, sample_data)
                if test_result["success"]:
                    ctx["put_html"](f"<div style='color:#155724;background:#d4edda;padding:8px;border-radius:4px;'>✅ 测试通过，执行时间: {test_result['execution_time_ms']:.2f}ms</div>")
                else:
                    ctx["put_html"](f"<div style='color:#856404;background:#fff3cd;padding:8px;border-radius:4px;'>⚠️ 测试警告: {test_result['error']}</div>")
            else:
                ctx["put_html"]("<div style='color:#856404;background:#fff3cd;padding:8px;border-radius:4px;'>⚠️ 无实际数据，跳过测试</div>")
            
            confirm = await ctx["input_group"]("确认", [
                ctx["actions"]("是否使用此代码?", [
                    {"label": "使用此代码", "value": "use"},
                    {"label": "重新生成", "value": "regenerate"},
                    {"label": "取消", "value": "cancel"},
                ], name="action"),
            ])
            
            if not confirm or confirm.get("action") == "cancel":
                return
            
            if confirm.get("action") == "regenerate":
                ctx["close_popup"]()
                await _edit_strategy_dialog(ctx, unit_id)
                return
            
            form["code"] = code
        
        await _save_strategy(ctx, unit, form, form.get("code"))


async def _save_strategy(ctx, unit, form, code):
    """保存策略"""
    # 保存代码
    if code:
        code = code.rstrip()
        lines = code.split('\n')
        
        if len(lines) > 1:
            non_empty_lines = [line for line in lines if line.strip()]
            if non_empty_lines:
                min_indent = min(len(line) - len(line.lstrip()) for line in non_empty_lines)
                
                if min_indent > 0:
                    fixed_lines = []
                    for line in lines:
                        if line.strip():
                            fixed_lines.append(line[min_indent:])
                        else:
                            fixed_lines.append(line)
                    code = '\n'.join(fixed_lines)
    
    update_result = unit.update_strategy_func_code(code)
    
    if not update_result.get("success"):
        ctx["toast"](f"代码保存失败: {update_result.get('error', '')}", color="error")
        return
    
    # 保存基本信息
    name = form.get("name", unit.name)
    summary = form.get("summary", "")
    tags = [t.strip() for t in form.get("tags", "").split(",") if t.strip()]
    max_history_count = form.get("max_history_count", 0)
    
    unit.metadata.name = name
    unit.metadata.description = summary
    unit.metadata.summary = summary
    unit.metadata.tags = tags
    unit.metadata.strategy_func_code = code or ""
    unit.metadata.max_history_count = max_history_count
    unit.save()
    
    # 绑定数据源
    datasource_id = form.get("datasource_id", "")
    if datasource_id:
        ds_mgr = get_ds_manager()
        source = ds_mgr.get_source(datasource_id)
        if source:
            unit.bind_datasource(datasource_id, source.name)
            
            source_stream = source.get_stream()
            if source_stream and code:
                try:
                    from deva import NS
                    
                    local_ns = {"__builtins__": __builtins__}
                    exec(code, local_ns, local_ns)
                    process_func = local_ns.get("process")
                    
                    if process_func:
                        output_stream_name = f"strategy_output_{unit.id}"
                        output_stream = NS(
                            output_stream_name,
                            cache_max_len=3,
                            cache_max_age_seconds=3600,
                            description=f"策略 {unit.name} 的输出流"
                        )
                        
                        source_stream.map(lambda data: unit.process(data)) >> output_stream
                        
                        unit.set_input_stream(source_stream)
                        unit.set_output_stream(output_stream)
                        
                        unit.save()
                except Exception as e:
                    ctx["toast"](f"绑定数据源时出错: {str(e)}", color="warning")
    
    ctx["toast"]("策略保存成功", color="success")
    ctx["close_popup"]()
    ctx["run_js"]("location.reload()")


async def _bind_datasource_and_start(ctx, unit_id: str):
    """绑定数据源并启动策略"""
    manager = get_manager()
    unit = manager.get_unit(unit_id)
    
    if not unit:
        ctx["toast"]("策略不存在", color="error")
        return
    
    ds_mgr = get_ds_manager()
    sources = ds_mgr.list_source_objects()
    
    if not sources:
        ctx["toast"]("没有可用的数据源，请先创建数据源", color="warning")
        return
    
    source_options = []
    for s in sources:
        source_name = getattr(s, 'name', '')
        source_id = getattr(s, 'id', '')
        source_status = getattr(s, 'status', 'stopped')
        if hasattr(source_status, 'value'):
            source_status = source_status.value
        status_label = "运行中" if source_status == "running" else "已停止"
        source_options.append({
            "label": f"{source_name} [{status_label}]",
            "value": source_id,
        })
    
    with ctx["popup"]("绑定数据源并启动", size="small", closable=True):
        ctx["put_markdown"]("**选择数据源**")
        
        form = await ctx["input_group"]("绑定数据源", [
            ctx["select"]("绑定数据源", name="datasource_id", options=source_options),
            ctx["actions"]("操作", [
                {"label": "绑定并启动", "value": "bind_start"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not form or form.get("action") == "cancel":
            ctx["close_popup"]()
            return
        
        datasource_id = form.get("datasource_id", "")
        if not datasource_id:
            ctx["toast"]("请选择数据源", color="warning")
            return
        
        ds_mgr = get_ds_manager()
        source = ds_mgr.get_source(datasource_id)
        
        if not source:
            ctx["toast"]("数据源不存在", color="error")
            return
        
        unit = manager.get_unit(unit_id)
        if not unit:
            ctx["toast"]("策略不存在", color="error")
            return
        
        code = unit.metadata.strategy_func_code or unit._processor_code
        if not code:
            ctx["toast"]("策略没有代码，请先编辑策略代码", color="warning")
            return
        
        unit.bind_datasource(datasource_id, source.name)
        
        source_stream = source.get_stream()
        if source_stream and code:
            try:
                from deva import NS
                
                local_ns = {"__builtins__": __builtins__}
                exec(code, local_ns, local_ns)
                process_func = local_ns.get("process")
                
                if process_func:
                    output_stream_name = f"strategy_output_{unit.id}"
                    output_stream = NS(
                        output_stream_name,
                        cache_max_len=3,
                        cache_max_age_seconds=3600,
                        description=f"策略 {unit.name} 的输出流"
                    )
                    
                    source_stream.map(lambda data: unit.process(data)) >> output_stream
                    
                    unit.set_input_stream(source_stream)
                    unit.set_output_stream(output_stream)
                    
                    unit.save()
            except Exception as e:
                ctx["toast"](f"绑定数据源时出错: {str(e)}", color="warning")
        
        result = manager.start(unit_id)
        if result.get("success"):
            ctx["toast"](f"已绑定数据源并启动: {source.name}", color="success")
        else:
            ctx["toast"](f"启动失败: {result.get('error', '')}", color="error")
        
        ctx["close_popup"]()


async def _create_strategy_dialog(ctx):
    ds_mgr = get_ds_manager()
    sources = ds_mgr.list_source_objects()
    
    source_options = []
    for s in sources:
        if isinstance(s, dict):
            source_name = s.get('name', '')
            source_id = s.get('id', '')
        else:
            source_name = getattr(s, 'name', '')
            source_id = getattr(s, 'id', '')
        source_options.append({"label": source_name, "value": source_id})
    
    source_options = source_options if source_options else []
    
    with ctx["popup"]("创建新策略", size="large", closable=True):
        ctx["put_markdown"]("### 策略配置")
        ctx["put_html"]("<p style='color:#666;font-size:12px;'>可以直接输入代码，也可以点击「AI生成」按钮，由AI根据需求描述自动生成代码</p>")
        
        # 获取系统配置的最大历史记录条数
        from deva.config import get_config
        max_system_history = get_config("strategy", "max_history_count", 300)
        
        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("策略名称", name="name", required=True, placeholder="输入策略名称"),
            ctx["textarea"]("策略简介", name="summary", placeholder="策略简介（将显示在列表页）", rows=3),
            ctx["input"]("标签", name="tags", placeholder="多个标签用逗号分隔"),
            ctx["input"]("历史记录保留条数", name="max_history_count", type="number", min=0, max=max_system_history, value=30, placeholder="默认30，不超过系统限制"),
            ctx["textarea"]("处理器代码", name="code", placeholder="def process(data): ...", rows=8),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "AI生成", "value": "ai_generate"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not form or form.get("action") == "cancel":
            ctx["close_popup"]()
            return
        
        if form.get("action") == "ai_generate":
            if not source_options:
                ctx["toast"]("请先创建数据源，AI需要基于数据源结构生成代码", color="warning")
                return
            
            ai_form = await ctx["input_group"]("AI生成代码", [
                ctx["select"]("选择数据源", name="datasource_id", options=source_options, required=True),
                ctx["textarea"]("需求描述", name="requirement", required=True, placeholder="描述你的策略需求，例如：筛选涨幅超过5%的股票", rows=4),
                ctx["actions"]("操作", [
                    {"label": "生成代码", "value": "generate"},
                    {"label": "取消", "value": "cancel"},
                ], name="action"),
            ])
            
            if not ai_form or ai_form.get("action") == "cancel":
                return
            
            source = ds_mgr.get_source(ai_form["datasource_id"])
            if not source:
                ctx["toast"]("数据源不存在", color="error")
                return
            
            datasource_context = build_datasource_context(source)
            
            recent_data = source.get_recent_data(1)
            sample_data = None
            if recent_data:
                sample_data = recent_data[0]
                data_schema = analyze_data_schema(sample_data)
                ctx["put_markdown"]("**数据结构分析（来自实际数据）:**")
            else:
                data_schema = build_schema_from_metadata(source)
                ctx["put_markdown"]("**数据结构分析（来自元数据推断）:**")
                ctx["put_html"]("<div style='color:#856404;background:#fff3cd;padding:8px;border-radius:4px;margin-bottom:10px;'>⚠️ 数据源暂无实际数据，AI将根据数据获取代码推断数据结构</div>")
            
            ctx["put_code"](json.dumps(data_schema, ensure_ascii=False, indent=2), language="json")
            
            ctx["put_markdown"]("**AI生成代码中...**")
            
            try:
                code = await generate_strategy_code(
                    ctx,
                    data_schema=data_schema,
                    user_requirement=ai_form["requirement"],
                    strategy_name=form.get("name", ""),
                    datasource_context=datasource_context,
                )
            except Exception as e:
                ctx["toast"](f"AI生成失败: {e}", color="error")
                return
            
            ctx["put_markdown"]("**生成的代码:**")
            ctx["put_code"](code, language="python")
            
            validation = validate_strategy_code(code)
            if validation["valid"]:
                ctx["put_html"]("<div style='color:#155724;background:#d4edda;padding:8px;border-radius:4px;'>✅ 代码验证通过</div>")
            else:
                ctx["put_html"](f"<div style='color:#721c24;background:#f8d7da;padding:8px;border-radius:4px;'>❌ 验证失败: {'; '.join(validation['errors'])}</div>")
                return
            
            if sample_data is not None:
                test_result = test_strategy_code(code, sample_data)
                if test_result["success"]:
                    ctx["put_html"](f"<div style='color:#155724;background:#d4edda;padding:8px;border-radius:4px;'>✅ 测试通过，执行时间: {test_result['execution_time_ms']:.2f}ms</div>")
                else:
                    ctx["put_html"](f"<div style='color:#856404;background:#fff3cd;padding:8px;border-radius:4px;'>⚠️ 测试警告: {test_result['error']}</div>")
            else:
                ctx["put_html"]("<div style='color:#856404;background:#fff3cd;padding:8px;border-radius:4px;'>⚠️ 无实际数据，跳过测试</div>")
            
            confirm = await ctx["input_group"]("确认", [
                ctx["actions"]("是否使用此代码?", [
                    {"label": "使用此代码", "value": "use"},
                    {"label": "重新生成", "value": "regenerate"},
                    {"label": "取消", "value": "cancel"},
                ], name="action"),
            ])
            
            if not confirm or confirm.get("action") == "cancel":
                return
            
            if confirm.get("action") == "regenerate":
                ctx["close_popup"]()
                await _create_strategy_dialog(ctx)
                return
            
            form["code"] = code
        
        manager = get_manager()
        summary = form.get("summary", "")
        result = manager.create_strategy(
            name=form["name"],
            description=summary,
            summary=summary,
            tags=[t.strip() for t in form.get("tags", "").split(",") if t.strip()],
            processor_code=form.get("code") or None,
            max_history_count=form.get("max_history_count", 0),
        )
        
        if result.get("success"):
            ctx["toast"](f"策略创建成功: {result['unit_id']}", color="success")
            ctx["run_js"]("location.reload()")
        else:
            ctx["toast"](f"创建失败: {result.get('error', '')}", color="error")


async def _create_ai_strategy_dialog(ctx):
    ds_mgr = get_ds_manager()
    sources = ds_mgr.list_source_objects()
    
    if not sources:
        ctx["toast"]("请先创建数据源", color="warning")
        return
    
    source_options = [
        {"label": f"{s.name} ({s.status.value})", "value": s.id}
        for s in sources
    ]
    
    with ctx["popup"]("🤖 AI生成策略代码", size="large", closable=True):
        ctx["put_markdown"]("### 步骤1: 选择数据源并描述需求")
        
        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("策略名称", name="name", required=True, placeholder="输入策略名称"),
            ctx["select"]("选择数据源", name="datasource_id", options=source_options, required=True),
            ctx["textarea"]("需求描述", name="requirement", required=True, placeholder="描述你的策略需求，例如：筛选涨幅超过5%的股票，按板块分组统计", rows=4),
            ctx["actions"]("操作", [
                {"label": "生成代码", "value": "generate"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not form or form.get("action") == "cancel":
            return
        
        source = ds_mgr.get_source(form["datasource_id"])
        if not source:
            ctx["toast"]("数据源不存在", color="error")
            return
        
        ctx["put_markdown"]("### 步骤2: 分析数据源结构")
        
        recent_data = source.get_recent_data(1)
        if not recent_data:
            ctx["toast"]("数据源暂无数据，请先启动数据源", color="warning")
            return
        
        sample_data = recent_data[0]
        data_schema = analyze_data_schema(sample_data)
        
        ctx["put_markdown"]("**数据结构分析:**")
        ctx["put_code"](json.dumps(data_schema, ensure_ascii=False, indent=2), language="json")
        
        ctx["put_markdown"]("### 步骤3: AI生成代码中...")
        
        try:
            code = await generate_strategy_code(
                ctx,
                data_schema=data_schema,
                user_requirement=form["requirement"],
                strategy_name=form["name"],
            )
        except Exception as e:
            ctx["toast"](f"AI生成失败: {e}", color="error")
            return
        
        ctx["put_markdown"]("### 步骤4: 审核生成的代码")
        ctx["put_code"](code, language="python")
        
        validation = validate_strategy_code(code)
        if not validation["valid"]:
            ctx["toast"](f"代码验证失败: {validation['errors']}", color="error")
            return
        
        if validation["warnings"]:
            ctx["put_html"](f"<div style='color:#856404;background:#fff3cd;padding:8px;border-radius:4px;'>警告: {'; '.join(validation['warnings'])}</div>")
        
        ctx["put_markdown"]("### 步骤5: 测试代码")
        
        test_result = test_strategy_code(code, sample_data)
        if test_result["success"]:
            ctx["put_html"](f"<div style='color:#155724;background:#d4edda;padding:8px;border-radius:4px;'>✅ 测试通过，执行时间: {test_result['execution_time_ms']:.2f}ms</div>")
            
            output = test_result["output"]
            if output is not None:
                ctx["put_markdown"]("**测试输出预览:**")
                if isinstance(output, pd.DataFrame):
                    ctx["put_html"](output.head(5).to_html(classes='df-table', index=False))
                elif isinstance(output, str) and len(output) > 50:
                    ctx["put_html"](output[:500])
                else:
                    ctx["put_text"](str(output))
        else:
            ctx["put_html"](f"<div style='color:#721c24;background:#f8d7da;padding:8px;border-radius:4px;'>❌ 测试失败: {test_result['error']}</div>")
        
        ctx["put_markdown"]("### 步骤6: 确认保存")
        
        confirm = await ctx["input_group"]("确认", [
            ctx["actions"]("是否保存此策略?", [
                {"label": "保存策略", "value": "save"},
                {"label": "重新生成", "value": "regenerate"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not confirm or confirm.get("action") == "cancel":
            return
        
        if confirm.get("action") == "regenerate":
            ctx["close_popup"]()
            await _create_ai_strategy_dialog(ctx)
            return
        
        manager = get_manager()
        
        result = manager.create_strategy(
            name=form["name"],
            processor_code=code,
            description=form.get("summary", form["requirement"]),
            summary=form.get("summary", form["requirement"]),
            auto_start=False,
        )
        
        if result.get("success"):
            unit = manager.get_unit(result["unit_id"])
            if unit:
                ds_mgr.link_strategy(source.id, unit.id)
                unit.save()
            
            ctx["toast"](f"策略创建成功: {result['unit_id']}", color="success")
            ctx["run_js"]("location.reload()")
        else:
            ctx["toast"](f"创建失败: {result.get('error', '')}", color="error")


# 避免循环导入
import pandas as pd
