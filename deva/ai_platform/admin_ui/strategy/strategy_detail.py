"""策略详情模块

提供策略详情查看和相关功能。
"""

from __future__ import annotations
from .strategy_edit import _edit_strategy_dialog

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from deva import NS

from .strategy_unit import StrategyUnit, StrategyStatus
from .strategy_manager import get_manager
from .fault_tolerance import get_error_collector, get_metrics_collector
from .strategy_logic_db import get_logic_db, get_instance_db
from .result_store import get_result_store


STATUS_LABELS = {
    StrategyStatus.STOPPED: "已停止",
    StrategyStatus.RUNNING: "运行中",
}


def _show_strategy_detail(ctx, unit_id: str):
    manager = get_manager()
    unit = manager.get_unit(unit_id)

    if not unit:
        ctx["toast"]("策略不存在", color="error")
        return

    logic_db = get_logic_db()
    instance_db = get_instance_db()

    strategy_type = getattr(unit, 'STRATEGY_TYPE', 'custom')
    logic_meta = logic_db.get_logic_by_type(strategy_type) if strategy_type != 'custom' else None
    instance_state = instance_db.get_instance_state(unit_id)

    with ctx["popup"](f"策略详情: {unit.name}", size="large", closable=True):
        ctx["put_markdown"](f"### 📋 基本信息")

        info_table = [
            ["ID", unit.id],
            ["名称", unit.name],
            ["描述", unit.metadata.description or "-"],
            ["标签", ", ".join(unit.metadata.tags) or "-"],
            ["状态", STATUS_LABELS.get(unit.status, unit.status.value)],
            ["策略类型", strategy_type or "自定义"],
            ["绑定数据源", unit.metadata.bound_datasource_name or "-"],
            ["创建时间", datetime.fromtimestamp(
                unit.metadata.created_at).strftime("%Y-%m-%d %H:%M:%S")],
            ["更新时间", datetime.fromtimestamp(
                unit.metadata.updated_at).strftime("%Y-%m-%d %H:%M:%S")],
            ["代码版本", str(unit._code_version)],
        ]
        ctx["put_table"](info_table)

        ctx["put_row"]([
            ctx["put_button"]("编辑策略", onclick=lambda: ctx["run_async"](
                _edit_strategy_dialog(ctx, unit_id)), color="primary"),
        ]).style("margin-top: 10px")

        if hasattr(unit, 'params') and unit.params:
            ctx["put_markdown"]("### ⚙️ 策略参数")
            params_table = [["参数名", "值"]]
            for key, value in unit.params.items():
                params_table.append([key, str(value)])
            ctx["put_table"](params_table)

        ctx["put_markdown"]("### 📊 执行状态")
        state_table = [
            ["处理计数", str(unit.state.processed_count)],
            ["错误计数", str(unit.state.error_count)],
            ["最近错误", unit.state.last_error or "-"],
            ["最后处理时间", datetime.fromtimestamp(unit.state.last_process_ts).strftime(
                "%Y-%m-%d %H:%M:%S") if unit.state.last_process_ts > 0 else "-"],
        ]
        ctx["put_table"](state_table)

        ctx["put_markdown"]("### 📥 最近输入数据")
        try:
            recent_inputs = unit.get_recent_input_data(limit=3)
            if recent_inputs:
                for i, input_item in enumerate(recent_inputs, 1):
                    timestamp = input_item.get("timestamp", "-")
                    data_type = input_item.get("data_type", "-")
                    data_size = input_item.get("data_size", 0)
                    preview = input_item.get("preview", str(input_item.get("data", ""))[:100])

                    ctx["put_html"](f"<div style='padding:8px;margin:4px 0;background:#f8f9fa;border-radius:4px;'>")
                    ctx["put_html"](f"<strong>输入 {i}:</strong> {timestamp}<br>")
                    ctx["put_html"](f"类型: {data_type}, 大小: {data_size}<br>")
                    ctx["put_html"](f"预览: <code>{preview}</code>")
                    ctx["put_html"]("</div>")
            else:
                ctx["put_text"]("暂无输入数据")
        except Exception as e:
            ctx["put_text"](f"获取输入数据失败: {str(e)}")

        ctx["put_markdown"]("### 📤 最近输出结果")

        try:
            output_stream = None

            if hasattr(unit, '_output_stream') and unit._output_stream:
                output_stream = unit._output_stream

            if not output_stream:
                # 已移除血缘关系管理功能，不再获取下游输出流
                pass

            if output_stream:
                recent_data = output_stream.recent(5)
                if recent_data:
                    ctx["put_markdown"]("#### 输出流数据 (最近5条)")
                    for i, data in enumerate(recent_data):
                        data_preview = str(data)[:200]
                        ctx["put_html"](f"<div style='padding:8px;margin:4px 0;background:#f8f9fa;border-radius:4px;font-family:monospace;'>[{i+1}] {data_preview}</div>")
                else:
                    ctx["put_text"]("暂无输出数据")
            else:
                ctx["put_text"]("暂无输出流")
        except Exception as e:
            ctx["put_text"](f"获取输出流失败: {str(e)}")

        ctx["put_markdown"]("#### 历史执行结果")
        recent_results = unit.get_recent_results(limit=10)
        if recent_results:
            result_table = [["时间", "状态", "耗时", "输出预览", "操作"]]
            for r in recent_results:
                status_html = '<span style="color:#28a745;">✅</span>' if r.get(
                    "success") else '<span style="color:#dc3545;">❌</span>'
                output_preview = r.get("output_preview", "")[:50]
                if not r.get("success") and r.get("error"):
                    output_preview = f"错误: {r.get('error', '')[:40]}"

                actions = ctx["put_buttons"]([
                    {"label": "详情", "value": f"detail_{r.get('id', '')}"},
                ], onclick=lambda v, rid=r.get("id", ""): _show_result_detail(ctx, rid))

                result_table.append([
                    r.get("ts_readable", "")[:16],
                    ctx["put_html"](status_html),
                    f"{r.get('process_time_ms', 0):.1f}ms",
                    output_preview[:50] + "..." if len(output_preview) > 50 else output_preview,
                    actions,
                ])
            ctx["put_table"](result_table)

            result_stats = get_result_store().get_stats(unit_id)
            ctx["put_html"](f"""
            <div style="margin-top:10px;padding:10px;background:#f5f5f5;border-radius:4px;">
                <strong>执行统计:</strong> 
                总计 {result_stats.get('results_count', 0)} 次 | 
                成功率 {result_stats.get('success_rate', 0)*100:.1f}% | 
                平均耗时 {result_stats.get('avg_process_time_ms', 0):.2f}ms
            </div>
            """)

            trend_data = get_result_store().get_trend_data(unit_id, interval_minutes=5, limit=20)
            if trend_data.get("timestamps"):
                ctx["put_markdown"]("#### 执行趋势")
                timestamps = trend_data["timestamps"][::-1]
                success_counts = trend_data["success_counts"][::-1]
                failed_counts = trend_data["failed_counts"][::-1]
                process_counts = trend_data["process_counts"][::-1]

                max_count = max(process_counts) if process_counts else 1
                chart_html = '<div style="display:flex;gap:2px;align-items:flex-end;height:60px;margin-top:10px;">'
                for i, ts in enumerate(timestamps):
                    total = process_counts[i] if i < len(process_counts) else 0
                    success = success_counts[i] if i < len(success_counts) else 0
                    failed = failed_counts[i] if i < len(failed_counts) else 0

                    total_height = int((total / max_count) * 50) if max_count > 0 else 0
                    success_height = int((success / max_count) * 50) if max_count > 0 else 0
                    failed_height = int((failed / max_count) * 50) if max_count > 0 else 0

                    chart_html += f'''
                    <div style="display:flex;flex-direction:column;align-items:center;width:30px;">
                        <div style="display:flex;flex-direction:column-reverse;height:50px;width:20px;background:#f0f0f0;border-radius:2px;">
                            <div style="height:{success_height}px;background:#28a745;border-radius:2px;"></div>
                            <div style="height:{failed_height}px;background:#dc3545;border-radius:2px;"></div>
                        </div>
                        <div style="font-size:8px;color:#666;margin-top:2px;">{ts}</div>
                    </div>
                    '''
                chart_html += '</div>'
                chart_html += '<div style="margin-top:5px;font-size:11px;color:#666;"><span style="color:#28a745;">■</span> 成功 <span style="color:#dc3545;">■</span> 失败</div>'
                ctx["put_html"](chart_html)
        else:
            ctx["put_text"]("暂无执行结果")

        if instance_state:
            ctx["put_markdown"]("### 💾 持久化状态")
            persist_table = [
                ["持久化状态", instance_state.state],
                ["持久化处理计数", str(instance_state.processed_count)],
                ["持久化错误计数", str(instance_state.error_count)],
                ["持久化更新时间", datetime.fromtimestamp(
                    instance_state.updated_at).strftime("%Y-%m-%d %H:%M:%S")],
            ]
            ctx["put_table"](persist_table)

        if logic_meta:
            ctx["put_markdown"]("### 📚 策略逻辑信息")
            logic_table = [
                ["逻辑ID", logic_meta.id],
                ["逻辑名称", logic_meta.name],
                ["策略类型", logic_meta.strategy_type],
                ["版本", str(logic_meta.version)],
                ["描述", logic_meta.description or "-"],
                ["标签", ", ".join(logic_meta.tags) or "-"],
            ]
            ctx["put_table"](logic_table)

            if logic_meta.params_schema:
                ctx["put_markdown"]("#### 参数模式定义")
                schema_table = [["参数名", "类型", "默认值", "描述"]]
                for param_name, param_def in logic_meta.params_schema.items():
                    schema_table.append([
                        param_name,
                        param_def.get("type", "-"),
                        str(param_def.get("default", "-")),
                        param_def.get("description", "-"),
                    ])
                ctx["put_table"](schema_table)

            ctx["put_markdown"]("#### 策略逻辑代码")
            ctx["put_collapse"]("点击展开/收起代码", [
                ctx["put_code"](logic_meta.code, language="python")
            ])

        if unit._ai_documentation:
            ctx["put_markdown"]("### 🤖 AI 说明文档")
            ctx["put_markdown"](unit._ai_documentation)

        strategy_code = unit.metadata.strategy_func_code or unit._processor_code
        if strategy_code:
            ctx["put_markdown"]("### 🔧 策略执行代码")
            ctx["put_collapse"]("点击展开/收起代码", [
                ctx["put_code"](strategy_code, language="python")
            ])

        code_versions = unit.get_code_versions(5)
        if code_versions:
            ctx["put_markdown"]("### 📜 代码版本历史")
            version_table = [["版本", "更新时间", "操作"]]
            for idx, ver in enumerate(code_versions):
                ts = ver.get("timestamp", 0)
                ts_readable = datetime.fromtimestamp(ts).strftime(
                    "%m-%d %H:%M:%S") if ts > 0 else "-"
                version_table.append([
                    f"v{idx + 1}",
                    ts_readable,
                    ctx["put_buttons"]([
                        {"label": "查看", "value": f"view_{idx}"},
                    ], onclick=lambda v, vid=idx: _show_code_version_detail(ctx, unit, vid))
                ])
            ctx["put_table"](version_table)

        ctx["put_markdown"]("### 📤 导出策略配置")
        export_json = json.dumps(unit.to_dict(), ensure_ascii=False, indent=2)
        ctx["put_collapse"]("点击展开/收起配置", [
            ctx["put_code"](export_json, language="json")
        ])


def _show_code_version_detail(ctx, unit, version_idx):
    """显示代码版本详情"""
    code_versions = unit.get_code_versions(10)

    if version_idx >= len(code_versions):
        ctx["toast"]("版本不存在", color="error")
        return

    version = code_versions[version_idx]
    code = version.get("new_code", "")
    ts = version.get("timestamp", 0)
    ts_readable = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts > 0 else "-"

    with ctx["popup"](f"代码版本 v{version_idx + 1}", size="large", closable=True):
        ctx["put_markdown"]("### 版本信息")
        info = [
            ["版本", f"v{version_idx + 1}"],
            ["更新时间", ts_readable],
            ["策略名称", version.get("name", "-")],
        ]
        ctx["put_table"](info)

        ctx["put_markdown"]("### 代码内容")
        ctx["put_code"](code, language="python")


def _show_result_detail(ctx, result_id: str):
    store = get_result_store()
    result = store.get_by_id(result_id)

    if not result:
        ctx["toast"]("结果不存在", color="error")
        return

    with ctx["popup"](f"执行结果详情: {result.strategy_name}", size="large", closable=True):
        ctx["put_markdown"]("### 基本信息")
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

        ctx["put_markdown"]("### 输入数据预览")
        ctx["put_code"](result.input_preview, language="text")

        if result.success and result.output_full is not None:
            ctx["put_markdown"]("### 输出结果")
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


# 避免循环导入
