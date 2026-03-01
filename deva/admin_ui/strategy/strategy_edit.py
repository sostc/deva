"""策略编辑模块

提供策略编辑和创建相关功能。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from .strategy_unit import StrategyUnit, StrategyStatus
from .strategy_manager import get_manager
from .fault_tolerance import get_error_collector, get_metrics_collector
from ..datasource.datasource import get_ds_manager
from ..dictionary import get_dictionary_manager_v2
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
    dict_mgr = get_dictionary_manager_v2()
    dict_entries = dict_mgr.list_all()
    dict_options = [{"label": e.name, "value": e.id} for e in dict_entries]
    
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
        
      
        
        # 添加JavaScript来监听数据源选择变化
        ctx["put_html"]("""
        <script>
        (function() {
            const datasourceSelect = document.querySelector('select[name="datasource_id"]');
            const infoDiv = document.getElementById('datasource_instance_info');
            const copyDiv = document.getElementById('datasource_sample_copy');
            
            if (datasourceSelect) {
                datasourceSelect.addEventListener('change', async function() {
                    const datasourceId = this.value;
                    if (!datasourceId) {
                        infoDiv.innerHTML = '请选择一个数据源以查看数据实例信息';
                        copyDiv.innerHTML = '';
                        return;
                    }
                    
                    infoDiv.innerHTML = '<span style="color:#6c757d;">加载中...</span>';
                    copyDiv.innerHTML = '';
                    
                    try {
                        // 发送请求获取数据源信息
                        const response = await fetch(`/api/datasource/info/${datasourceId}`);
                        if (response.ok) {
                            const data = await response.json();
                            if (data.success) {
                                const instance = data.data_type_instance;
                                if (instance) {
                                    let infoHtml = `
                                        <div style="margin-bottom:8px;">
                                            <strong>数据类型:</strong> ${instance.data_type}<br>
                                            <strong>类型模块:</strong> ${instance.type_module}<br>
                                            <strong>更新时间:</strong> ${new Date(instance.timestamp * 1000).toLocaleString()}
                                        </div>
                                        <div style="margin-top:10px;">
                                            <strong>数据样例:</strong>
                                            <pre style="background:#e9ecef;padding:8px;border-radius:4px;font-size:12px;max-height:200px;overflow:auto;">${JSON.stringify(instance.data_sample, null, 2)}</pre>
                                        </div>
                                    `;
                                    infoDiv.innerHTML = infoHtml;
                                    
                                    // 添加复制按钮
                                    copyDiv.innerHTML = `
                                        <button onclick="copyToClipboard('${encodeURIComponent(JSON.stringify(instance.data_sample))}')" 
                                            style="padding:4px 8px;background:#007bff;color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;">
                                            复制数据样例
                                        </button>
                                        <button onclick="copyToClipboard('${encodeURIComponent(JSON.stringify(instance, null, 2))}')" 
                                            style="padding:4px 8px;background:#28a745;color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px;margin-left:8px;">
                                            复制完整实例
                                        </button>
                                    `;
                                } else {
                                    infoDiv.innerHTML = '<span style="color:#6c757d;">该数据源暂无数据实例信息</span>';
                                }
                            } else {
                                infoDiv.innerHTML = '<span style="color:#dc3545;">获取数据源信息失败: ' + (data.error || '未知错误') + '</span>';
                            }
                        } else {
                            infoDiv.innerHTML = '<span style="color:#dc3545;">请求失败，请稍后重试</span>';
                        }
                    } catch (error) {
                        infoDiv.innerHTML = '<span style="color:#dc3545;">加载失败: ' + error.message + '</span>';
                    }
                });
                
                // 初始触发一次
                if (datasourceSelect.value) {
                    datasourceSelect.dispatchEvent(new Event('change'));
                }
            }
        })();
        
        function copyToClipboard(text) {
            navigator.clipboard.writeText(decodeURIComponent(text))
                .then(() => {
                    alert('已复制到剪贴板');
                })
                .catch(err => {
                    console.error('复制失败:', err);
                    alert('复制失败，请手动复制');
                });
        }
        </script>
        """)
        
        # 获取系统配置的最大历史记录条数
        from deva.config import get_config
        config = get_config()
        max_system_history = config.get("strategy.max_history_count", 300)
        
        # 添加JavaScript来处理查看数据源样例的功能
        ctx["put_html"]('''
        <script>
        function showDatasourceSample() {
            const datasourceSelect = document.querySelector('select[name="datasource_id"]');
            const datasourceId = datasourceSelect ? datasourceSelect.value : '';
            
            // 清理并验证数据源ID
            const cleanDatasourceId = datasourceId.replace(/"/g, '').trim();
            
            if (!cleanDatasourceId) {
                alert('请先选择一个数据源');
                return;
            }
            
            // 创建浮窗
            const popup = document.createElement('div');
            popup.style.cssText = `
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: 80%;
                max-width: 800px;
                height: 60%;
                max-height: 600px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.2);
                z-index: 10000;
                padding: 20px;
                overflow: auto;
            `;
            
            // 创建标题
            const title = document.createElement('h3');
            title.textContent = '数据源数据样例';
            title.style.marginTop = '0';
            popup.appendChild(title);
            
            // 创建内容区域
            const content = document.createElement('div');
            content.innerHTML = '<p style="color:#6c757d;">加载中...</p>';
            popup.appendChild(content);
            
            // 创建关闭按钮
            const closeBtn = document.createElement('button');
            closeBtn.textContent = '关闭';
            closeBtn.style.cssText = `
                position: absolute;
                top: 10px;
                right: 10px;
                padding: 5px 10px;
                background: #6c757d;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
            `;
            closeBtn.onclick = function() {
                document.body.removeChild(popup);
                document.body.removeChild(overlay);
            };
            popup.appendChild(closeBtn);
            
            // 创建遮罩层
            const overlay = document.createElement('div');
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.5);
                z-index: 9999;
            `;
            overlay.onclick = function() {
                document.body.removeChild(popup);
                document.body.removeChild(overlay);
            };
            
            document.body.appendChild(overlay);
            document.body.appendChild(popup);
            
            // 加载数据源信息
            fetch(`/api/datasource/info/${cleanDatasourceId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const instance = data.data_type_instance;
                        if (instance) {
                            let infoHtml = `
                                <div style="margin-bottom:15px;">
                                    <strong>数据类型:</strong> ${instance.data_type}<br>
                                    <strong>类型模块:</strong> ${instance.type_module}<br>
                                    <strong>更新时间:</strong> ${new Date(instance.timestamp * 1000).toLocaleString()}
                                </div>
                                <div style="margin-top:15px;">
                                    <strong>数据样例:</strong>
                                    <pre style="background:#e9ecef;padding:12px;border-radius:4px;font-size:13px;max-height:300px;overflow:auto;">${JSON.stringify(instance.data_sample, null, 2)}</pre>
                                </div>
                                <div style="margin-top:15px;">
                                    <button onclick="copyToClipboard('${encodeURIComponent(JSON.stringify(instance.data_sample))}')" 
                                        style="padding:6px 12px;background:#007bff;color:white;border:none;border-radius:4px;cursor:pointer;font-size:13px;margin-right:10px;">
                                        复制数据样例
                                    </button>
                                    <button onclick="copyToClipboard('${encodeURIComponent(JSON.stringify(instance, null, 2))}')" 
                                        style="padding:6px 12px;background:#28a745;color:white;border:none;border-radius:4px;cursor:pointer;font-size:13px;">
                                        复制完整实例
                                    </button>
                                </div>
                            `;
                            content.innerHTML = infoHtml;
                        } else {
                            content.innerHTML = '<p style="color:#6c757d;">该数据源暂无数据实例信息</p>';
                        }
                    } else {
                        content.innerHTML = `<p style="color:#dc3545;">获取数据源信息失败: ${data.error || '未知错误'}</p>`;
                    }
                })
                .catch(error => {
                    content.innerHTML = `<p style="color:#dc3545;">加载失败: ${error.message}</p>`;
                });
        }
        
        function copyToClipboard(text) {
            navigator.clipboard.writeText(decodeURIComponent(text))
                .then(() => {
                    alert('已复制到剪贴板');
                })
                .catch(err => {
                    console.error('复制失败:', err);
                    alert('复制失败，请手动复制');
                });
        }
        </script>
        ''')
        
        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("策略名称", name="name", required=True, value=unit.name),
            ctx["textarea"]("策略简介", name="summary", value=unit.metadata.summary or unit.metadata.description or "", rows=3),
            ctx["input"]("标签", name="tags", value=", ".join(unit.metadata.tags or [])),
            ctx["select"]("绑定数据源", name="datasource_id", options=source_options, value=unit.metadata.bound_datasource_id or ""),
            ctx["checkbox"](
                "自动补齐数据字典 Profiles",
                name="dictionary_profile_ids",
                options=dict_options,
                value=getattr(unit.metadata, "dictionary_profile_ids", []),
            ),
            ctx["select"](
                "计算模式",
                name="compute_mode",
                options=[
                    {"label": "逐条处理 (record)", "value": "record"},
                    {"label": "窗口处理 (window)", "value": "window"},
                ],
                value=getattr(unit.metadata, "compute_mode", "record"),
            ),
            ctx["select"](
                "窗口类型",
                name="window_type",
                options=[
                    {"label": "滑动窗口 (sliding)", "value": "sliding"},
                    {"label": "定时窗口 (timed)", "value": "timed"},
                ],
                value=getattr(unit.metadata, "window_type", "sliding"),
            ),
            ctx["input"]("滑动窗口大小", name="window_size", type="number", min=1, value=getattr(unit.metadata, "window_size", 5)),
            ctx["input"]("定时窗口间隔", name="window_interval", value=getattr(unit.metadata, "window_interval", "10s"), placeholder="如 5s / 1min"),
            ctx["select"](
                "窗口未满是否输出",
                name="window_return_partial",
                options=[
                    {"label": "否 (False)", "value": "false"},
                    {"label": "是 (True)", "value": "true"},
                ],
                value="true" if getattr(unit.metadata, "window_return_partial", False) else "false",
            ),
            ctx["input"]("历史记录保留条数", name="max_history_count", type="number", min=0, max=max_system_history, value=getattr(unit.metadata, "max_history_count", 30), placeholder="默认30，不超过系统限制"),
            ctx["textarea"]("执行代码", name="code", value=current_code, rows=15, code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "测试代码", "value": "test"},
                {"label": "AI生成", "value": "ai_generate"},
                {"label": "查看数据源样例", "value": "view_sample"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not form or form.get("action") == "cancel":
            ctx["close_popup"]()
            return
        
        if form.get("action") == "view_sample":
            # 执行查看数据源样例的JavaScript函数
            ctx["run_js"]("showDatasourceSample()")
            # 重新显示表单，保持当前状态
            await _edit_strategy_dialog(ctx, unit_id)
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
    compute_mode = form.get("compute_mode", getattr(unit.metadata, "compute_mode", "record")) or "record"
    window_type = form.get("window_type", getattr(unit.metadata, "window_type", "sliding")) or "sliding"
    window_interval = (form.get("window_interval", getattr(unit.metadata, "window_interval", "10s")) or "10s").strip()
    try:
        window_size = int(form.get("window_size", getattr(unit.metadata, "window_size", 5)) or 5)
    except (TypeError, ValueError):
        window_size = 5
    if window_size < 1:
        window_size = 1
    window_return_partial = str(form.get("window_return_partial", "false")).lower() in ("1", "true", "yes", "on")
    dictionary_profile_ids = form.get("dictionary_profile_ids", []) or []
    
    unit.metadata.name = name
    unit.metadata.description = summary
    unit.metadata.summary = summary
    unit.metadata.tags = tags
    unit.metadata.strategy_func_code = code or ""
    unit.metadata.max_history_count = max_history_count
    unit.metadata.compute_mode = compute_mode
    unit.metadata.window_type = window_type
    unit.metadata.window_size = window_size
    unit.metadata.window_interval = window_interval
    unit.metadata.window_return_partial = window_return_partial
    unit.metadata.dictionary_profile_ids = dictionary_profile_ids
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
                    unit.build_runtime_pipeline(source_stream)
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
                unit.build_runtime_pipeline(source_stream)
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
    dict_mgr = get_dictionary_manager_v2()
    dict_entries = dict_mgr.list_all()
    dict_options = [{"label": e.name, "value": e.id} for e in dict_entries]
    
    # 构建数据源选项，显示运行状态并优先排序运行中的数据源
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
            "is_running": source_status == "running"
        })
    
    # 优先排序运行中的数据源
    source_options.sort(key=lambda x: (not x.get('is_running', False), x['label']))
    
    # 移除排序键，只保留必要的字段
    source_options = [{"label": opt["label"], "value": opt["value"]} for opt in source_options]
    
    # 添加"无"选项
    source_options = [{"label": "无", "value": ""}] + source_options
    
    with ctx["popup"]("创建新策略", size="large", closable=True):
        ctx["put_markdown"]("### 策略配置")
        ctx["put_html"]("<p style='color:#666;font-size:12px;'>可以直接输入代码，也可以点击「AI生成」按钮，由AI根据需求描述自动生成代码</p>")
        
        # 获取系统配置的最大历史记录条数
        from deva.config import get_config
        config = get_config()
        max_system_history = config.get("strategy.max_history_count", 300)
        
        # 空行，保持布局美观
        ctx["put_html"]("<br>");
        
        # 添加JavaScript来处理查看数据源样例的功能
        ctx["put_html"]("""
        <script>
        function showDatasourceSample() {
            const datasourceSelect = document.querySelector('select[name="datasource_id"]');
            const datasourceId = datasourceSelect ? datasourceSelect.value : '';
            
            // 清理并验证数据源ID
            const cleanDatasourceId = datasourceId.replace(/"/g, '').trim();
            
            if (!cleanDatasourceId) {
                alert('请先选择一个数据源');
                return;
            }
            
            // 创建浮窗
            const popup = document.createElement('div');
            popup.style.cssText = `
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: 80%;
                max-width: 800px;
                height: 60%;
                max-height: 600px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.2);
                z-index: 10000;
                padding: 20px;
                overflow: auto;
            `;
            
            // 创建标题
            const title = document.createElement('h3');
            title.textContent = '数据源数据样例';
            title.style.marginTop = '0';
            popup.appendChild(title);
            
            // 创建内容区域
            const content = document.createElement('div');
            content.innerHTML = '<p style="color:#6c757d;">加载中...</p>';
            popup.appendChild(content);
            
            // 创建关闭按钮
            const closeBtn = document.createElement('button');
            closeBtn.textContent = '关闭';
            closeBtn.style.cssText = `
                position: absolute;
                top: 10px;
                right: 10px;
                padding: 5px 10px;
                background: #6c757d;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
            `;
            closeBtn.onclick = function() {
                document.body.removeChild(popup);
                document.body.removeChild(overlay);
            };
            popup.appendChild(closeBtn);
            
            // 创建遮罩层
            const overlay = document.createElement('div');
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.5);
                z-index: 9999;
            `;
            overlay.onclick = function() {
                document.body.removeChild(popup);
                document.body.removeChild(overlay);
            };
            
            document.body.appendChild(overlay);
            document.body.appendChild(popup);
            
            // 加载数据源信息
            fetch(`/api/datasource/info/${cleanDatasourceId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const instance = data.data_type_instance;
                        if (instance) {
                            let infoHtml = `
                                <div style="margin-bottom:15px;">
                                    <strong>数据类型:</strong> ${instance.data_type}<br>
                                    <strong>类型模块:</strong> ${instance.type_module}<br>
                                    <strong>更新时间:</strong> ${new Date(instance.timestamp * 1000).toLocaleString()}
                                </div>
                                <div style="margin-top:15px;">
                                    <strong>数据样例:</strong>
                                    <pre style="background:#e9ecef;padding:12px;border-radius:4px;font-size:13px;max-height:300px;overflow:auto;">${JSON.stringify(instance.data_sample, null, 2)}</pre>
                                </div>
                                <div style="margin-top:15px;">
                                    <button onclick="copyToClipboard('${encodeURIComponent(JSON.stringify(instance.data_sample))}')" 
                                        style="padding:6px 12px;background:#007bff;color:white;border:none;border-radius:4px;cursor:pointer;font-size:13px;margin-right:10px;">
                                        复制数据样例
                                    </button>
                                    <button onclick="copyToClipboard('${encodeURIComponent(JSON.stringify(instance, null, 2))}')" 
                                        style="padding:6px 12px;background:#28a745;color:white;border:none;border-radius:4px;cursor:pointer;font-size:13px;">
                                        复制完整实例
                                    </button>
                                </div>
                            `;
                            content.innerHTML = infoHtml;
                        } else {
                            content.innerHTML = '<p style="color:#6c757d;">该数据源暂无数据实例信息</p>';
                        }
                    } else {
                        content.innerHTML = `<p style="color:#dc3545;">获取数据源信息失败: ${data.error || '未知错误'}</p>`;
                    }
                })
                .catch(error => {
                    content.innerHTML = `<p style="color:#dc3545;">加载失败: ${error.message}</p>`;
                });
        }
        
        function copyToClipboard(text) {
            navigator.clipboard.writeText(decodeURIComponent(text))
                .then(() => {
                    alert('已复制到剪贴板');
                })
                .catch(err => {
                    console.error('复制失败:', err);
                    alert('复制失败，请手动复制');
                });
        }
        </script>
        """)
        
        # 显示表单
        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("策略名称", name="name", required=True, placeholder="输入策略名称"),
            ctx["textarea"]("策略简介", name="summary", placeholder="策略简介（将显示在列表页）", rows=3),
            ctx["input"]("标签", name="tags", placeholder="多个标签用逗号分隔"),
            ctx["select"]("绑定数据源", name="datasource_id", options=source_options, value=""),
            ctx["checkbox"]("自动补齐数据字典 Profiles", name="dictionary_profile_ids", options=dict_options, value=[]),
            ctx["select"](
                "计算模式",
                name="compute_mode",
                options=[
                    {"label": "逐条处理 (record)", "value": "record"},
                    {"label": "窗口处理 (window)", "value": "window"},
                ],
                value="record",
            ),
            ctx["select"](
                "窗口类型",
                name="window_type",
                options=[
                    {"label": "滑动窗口 (sliding)", "value": "sliding"},
                    {"label": "定时窗口 (timed)", "value": "timed"},
                ],
                value="sliding",
            ),
            ctx["input"]("滑动窗口大小", name="window_size", type="number", min=1, value=5),
            ctx["input"]("定时窗口间隔", name="window_interval", value="10s", placeholder="如 5s / 1min"),
            ctx["select"](
                "窗口未满是否输出",
                name="window_return_partial",
                options=[
                    {"label": "否 (False)", "value": "false"},
                    {"label": "是 (True)", "value": "true"},
                ],
                value="false",
            ),
            ctx["input"]("历史记录保留条数", name="max_history_count", type="number", min=0, max=max_system_history, value=30, placeholder="默认30，不超过系统限制"),
            ctx["textarea"]("处理器代码", name="code", placeholder="def process(data): ...", rows=8),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "AI生成", "value": "ai_generate"},
                {"label": "查看数据源样例", "value": "view_sample"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not form or form.get("action") == "cancel":
            ctx["close_popup"]()
            return
        
        if form.get("action") == "view_sample":
            # 执行查看数据源样例的JavaScript函数
            ctx["run_js"]("showDatasourceSample()")
            # 重新显示表单，保持当前状态
            await _create_strategy_dialog(ctx)
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
        compute_mode = form.get("compute_mode", "record") or "record"
        window_type = form.get("window_type", "sliding") or "sliding"
        window_interval = (form.get("window_interval", "10s") or "10s").strip()
        try:
            window_size = int(form.get("window_size", 5) or 5)
        except (TypeError, ValueError):
            window_size = 5
        if window_size < 1:
            window_size = 1
        window_return_partial = str(form.get("window_return_partial", "false")).lower() in ("1", "true", "yes", "on")
        dictionary_profile_ids = form.get("dictionary_profile_ids", []) or []

        result = manager.create_strategy(
            name=form["name"],
            description=summary,
            summary=summary,
            tags=[t.strip() for t in form.get("tags", "").split(",") if t.strip()],
            processor_code=form.get("code") or None,
            max_history_count=form.get("max_history_count", 0),
            compute_mode=compute_mode,
            window_type=window_type,
            window_size=window_size,
            window_interval=window_interval,
            window_return_partial=window_return_partial,
            dictionary_profile_ids=dictionary_profile_ids,
        )
        
        if result.get("success"):
            unit_id = result["unit_id"]
            unit = manager.get_unit(unit_id)
            
            # 绑定数据源
            datasource_id = form.get("datasource_id", "")
            if datasource_id:
                source = ds_mgr.get_source(datasource_id)
                if source:
                    unit.bind_datasource(datasource_id, source.name)
                    unit.save()
            
            ctx["toast"](f"策略创建成功: {unit_id}", color="success")
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
