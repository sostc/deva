"""策略管理 UI"""

import json
from datetime import datetime

from pywebio.output import put_text, put_markdown, put_table, put_buttons, put_html, toast, popup, close_popup, put_code, put_collapse, put_row, use_scope, set_scope, clear
from pywebio.input import input_group, input, textarea, select, actions
from pywebio.session import run_async


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


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _render_status_badge(is_running: bool) -> str:
    if is_running:
        return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#e8f5e9;color:#2e7d32;">● 运行中</span>'
    return '<span style="display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;background:#f5f5f5;color:#757575;">○ 已停止</span>'


def _render_detail_section(title: str) -> str:
    return f"""
    <div style="margin:20px 0 12px 0;padding-bottom:8px;border-bottom:2px solid #e0e0e0;">
        <span style="font-size:15px;font-weight:600;color:#333;">{title}</span>
    </div>
    """


async def render_strategy_admin(ctx: dict):
    """渲染策略管理面板"""
    await ctx["init_naja_ui"]("策略管理")
    
    set_scope("strategy_content")
    _render_strategy_content(ctx)


def _render_strategy_content(ctx: dict):
    """渲染策略管理内容（支持局部刷新）"""
    from . import get_strategy_manager
    from .result_store import get_result_store
    mgr = get_strategy_manager()
    store = get_result_store()
    
    entries = mgr.list_all()
    stats = mgr.get_stats()
    result_stats = store.get_stats()
    
    running_count = sum(1 for e in entries if e.is_running)
    error_count = sum(1 for e in entries if e._state.error_count > 0)
    
    with use_scope("strategy_content", clear=True):
        ctx["put_html"](_render_strategy_stats_html(stats, running_count, error_count))
        
        if entries:
            table_data = _build_table_data(ctx, entries, mgr)
            ctx["put_table"](table_data, header=["名称", "状态", "绑定数据源", "策略简介", "最近数据", "操作"])
            
            ctx["put_html"]('<div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">')
            ctx["put_buttons"]([{"label": "➕ 创建策略", "value": "create"}], onclick=lambda v, m=mgr, c=ctx: _create_strategy_dialog(m, c))
            ctx["put_buttons"]([{"label": "▶️ 全部启动", "value": "start_all"}], onclick=lambda v, m=mgr, c=ctx: _start_all_strategies(c, m))
            ctx["put_buttons"]([{"label": "⏹️ 全部停止", "value": "stop_all"}], onclick=lambda v, m=mgr, c=ctx: _stop_all_strategies(c, m))
            ctx["put_html"]('</div>')
        else:
            ctx["put_html"]('<div style="padding:40px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无策略，点击下方按钮创建</div>')
            ctx["put_buttons"]([{"label": "➕ 创建策略", "value": "create"}], 
                               onclick=lambda v, m=mgr, c=ctx: _create_strategy_dialog(m, c))
        
        ctx["put_html"]("<hr style='margin:24px 0;border:none;border-top:1px solid #e0e0e0;'>")
        
        ctx["put_html"](_render_result_stats_html(result_stats))
        
        ctx["put_html"]('<div style="margin:16px 0 12px 0;font-size:15px;font-weight:600;color:#333;">最近执行结果</div>')
        _render_recent_results(ctx, entries, store)


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
    table_data = []
    for e in entries:
        status_html = _render_status_badge(e.is_running)
        
        bound_ds_id = getattr(e._metadata, "bound_datasource_id", "")
        bound_ds_name = bound_ds_id
        if bound_ds_id:
            from ..datasource import get_datasource_manager
            ds_mgr = get_datasource_manager()
            ds = ds_mgr.get(bound_ds_id)
            if ds:
                bound_ds_name = ds.name
                bound_ds = ctx["put_buttons"]([
                    {"label": bound_ds_name[:20], "value": bound_ds_id}
                ], onclick=lambda v, c=ctx: _show_ds_detail_from_strategy(c, v), small=True)
            else:
                bound_ds = bound_ds_id[:12]
        else:
            bound_ds = "-"
        
        description = getattr(e._metadata, "description", "") or ""
        summary_preview = description[:80] + "..." if len(description) > 80 else description if description else "-"
        
        processed_count = e._state.processed_count
        last_process_ts = e._state.last_process_ts
        
        if last_process_ts > 0:
            try:
                last_process_time = datetime.fromtimestamp(last_process_ts).strftime("%m-%d %H:%M:%S")
                recent_data = f"执行 {processed_count} 次<br>最后: {last_process_time}"
            except Exception:
                recent_data = f"执行 {processed_count} 次"
        else:
            recent_data = f"执行 {processed_count} 次"
        
        toggle_label = "停止" if e.is_running else "启动"
        
        actions = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{e.id}"},
            {"label": "编辑", "value": f"edit_{e.id}"},
            {"label": toggle_label, "value": f"toggle_{e.id}"},
            {"label": "删除", "value": f"delete_{e.id}"},
        ], onclick=lambda v, m=mgr, c=ctx: _handle_strategy_action(v, m, c))
        
        table_data.append([
            ctx["put_html"](f"<strong>{e.name}</strong>"),
            ctx["put_html"](status_html),
            bound_ds,
            ctx["put_html"](f'<span style="font-size:12px;color:#666;">{summary_preview}</span>'),
            ctx["put_html"](f'<span style="font-size:12px;color:#666;">{recent_data}</span>'),
            actions,
        ])
    
    return table_data


def _render_recent_results(ctx, entries, store, limit: int = 10):
    """渲染最近执行结果表格"""
    all_results = []
    for e in entries:
        results = store.get_recent(e.id, limit=5)
        all_results.extend(results)
    
    all_results.sort(key=lambda x: x.ts, reverse=True)
    all_results = all_results[:limit]
    
    if not all_results:
        ctx["put_html"]('<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无执行结果</div>')
        return
    
    table_data = [["时间", "策略名称", "状态", "耗时", "输出预览", "操作"]]
    
    for r in all_results:
        status_html = '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;background:#e8f5e9;color:#2e7d32;">✅ 成功</span>' if r.success else '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;background:#ffebee;color:#c62828;">❌ 失败</span>'
        output_preview = r.output_preview[:60] + "..." if len(r.output_preview) > 60 else r.output_preview
        if not r.success and r.error:
            output_preview = f"错误: {r.error[:50]}..."
        
        actions = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{r.id}"},
        ], onclick=lambda v, rid=r.id: _show_result_detail_by_id(ctx, rid))
        
        table_data.append([
            r.ts_readable[:16] if hasattr(r, 'ts_readable') else datetime.fromtimestamp(r.ts).strftime("%m-%d %H:%M:%S"),
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


def _show_result_detail_by_id(ctx, result_id: str):
    """根据结果ID显示结果详情"""
    from .result_store import get_result_store
    store = get_result_store()
    result = store.get_by_id(result_id)
    
    if not result:
        ctx["toast"]("结果不存在", color="error")
        return
    
    with ctx["popup"](f"执行结果详情", size="large", closable=True):
        ctx["put_html"](_render_detail_section("基本信息"))
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
        
        ctx["put_html"](_render_detail_section("输入数据预览"))
        ctx["put_code"](result.input_preview, language="text")
        
        if result.success and result.output_full is not None:
            ctx["put_html"](_render_detail_section("输出结果"))
            output_data = result.output_full
            if isinstance(output_data, dict):
                if "html" in output_data:
                    ctx["put_html"](output_data["html"])
                else:
                    ctx["put_code"](json.dumps(output_data, ensure_ascii=False, indent=2), language="json")
            elif isinstance(output_data, str):
                if output_data.startswith("<"):
                    ctx["put_html"](output_data)
                else:
                    ctx["put_code"](output_data[:2000], language="text")
            elif isinstance(output_data, list):
                ctx["put_code"](json.dumps(output_data[:20], ensure_ascii=False, indent=2), language="json")
            else:
                ctx["put_code"](str(output_data)[:2000], language="text")


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
    elif action_type == "delete":
        mgr.delete(entry_id)
        ctx["toast"]("已删除", color="error")
    
    _render_strategy_content(ctx)


async def _show_strategy_detail(ctx: dict, mgr, entry_id: str):
    """显示策略详情"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("策略不存在", color="error")
        return
    
    with ctx["popup"](f"策略详情: {entry.name}", size="large", closable=True):
        ctx["put_html"](_render_detail_section("📊 基本信息"))
        
        ctx["put_table"]([
            ["ID", entry.id],
            ["名称", entry.name],
            ["描述", getattr(entry._metadata, "description", "") or "-"],
            ["状态", "运行中" if entry.is_running else "已停止"],
            ["计算模式", getattr(entry._metadata, "compute_mode", "record")],
            ["窗口大小", getattr(entry._metadata, "window_size", 5)],
            ["绑定数据源", getattr(entry._metadata, "bound_datasource_id", "") or "-"],
            ["历史保留", getattr(entry._metadata, "max_history_count", 100)],
            ["创建时间", _fmt_ts(entry._metadata.created_at)],
            ["更新时间", _fmt_ts(entry._metadata.updated_at)],
        ], header=["字段", "值"])
        
        dict_ids = getattr(entry._metadata, "dictionary_profile_ids", [])
        if dict_ids:
            ctx["put_html"]("<p><strong>数据字典:</strong> " + ", ".join(dict_ids) + "</p>")
        
        ctx["put_html"](_render_detail_section("📈 执行统计"))
        
        ctx["put_table"]([
            ["处理次数", entry._state.processed_count],
            ["输出次数", entry._state.output_count],
            ["错误次数", entry._state.error_count],
            ["最后错误", entry._state.last_error or "-"],
            ["最后处理", _fmt_ts(entry._state.last_process_ts)],
        ], header=["字段", "值"])
        
        ctx["put_html"](_render_detail_section("📜 历史执行结果"))
        
        try:
            recent_results = entry.get_recent_results(limit=10)
            if recent_results:
                result_table = [["时间", "状态", "耗时", "输出预览", "操作"]]
                for r in recent_results:
                    status_html = '<span style="color:#28a745;">✅</span>' if r.get("success") else '<span style="color:#dc3545;">❌</span>'
                    output_preview = r.get("output_preview", "")[:50]
                    if not r.get("success") and r.get("error"):
                        output_preview = f"错误: {r.get('error', '')[:40]}"
                    
                    actions = ctx["put_buttons"]([
                        {"label": "详情", "value": f"result_{r.get('id', '')}"},
                    ], onclick=lambda v, rid=r.get("id", ""), e=entry: _show_result_detail(ctx, e, rid))
                    
                    result_table.append([
                        r.get("ts_readable", "")[:16],
                        ctx["put_html"](status_html),
                        f"{r.get('process_time_ms', 0):.1f}ms",
                        output_preview[:50] + "..." if len(output_preview) > 50 else output_preview,
                        actions,
                    ])
                ctx["put_table"](result_table)
                
                result_stats = entry.get_result_stats()
                ctx["put_html"](f"""
                <div style="margin-top:10px;padding:10px;background:#f5f5f5;border-radius:4px;">
                    <strong>执行统计:</strong> 
                    总计 {result_stats.get('results_count', 0)} 次 | 
                    成功率 {result_stats.get('success_rate', 0)*100:.1f}% | 
                    平均耗时 {result_stats.get('avg_process_time_ms', 0):.2f}ms
                </div>
                """)
                
                trend_data = entry.get_result_trend(interval_minutes=5, limit=20)
                if trend_data.get("timestamps"):
                    ctx["put_html"]("<p style='margin-top:15px;'><strong>执行趋势:</strong></p>")
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
                ctx["put_html"]('<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无执行结果</div>')
        except Exception as e:
            ctx["put_text"](f"获取历史结果失败: {str(e)}")
        
        ctx["put_html"](_render_detail_section("💻 处理代码"))
        
        if entry.func_code:
            ctx["put_code"](entry.func_code, language="python")
        else:
            ctx["put_text"]("暂无代码")
        
        export_json = json.dumps(entry.to_dict(), ensure_ascii=False, indent=2)
        ctx["put_html"](_render_detail_section("📤 导出策略配置"))
        ctx["put_collapse"]("点击展开/收起配置", [
            ctx["put_code"](export_json, language="json")
        ])


def _show_result_detail(ctx: dict, entry, result_id: str):
    """显示执行结果详情"""
    from .result_store import get_result_store
    store = get_result_store()
    result = store.get_by_id(result_id)
    
    if not result:
        ctx["toast"]("结果不存在", color="error")
        return
    
    with ctx["popup"](f"执行结果详情", size="large", closable=True):
        ctx["put_html"](_render_detail_section("基本信息"))
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
        
        ctx["put_html"](_render_detail_section("输入数据预览"))
        ctx["put_code"](result.input_preview, language="text")
        
        if result.success and result.output_full is not None:
            ctx["put_html"](_render_detail_section("输出结果"))
            output_data = result.output_full
            if isinstance(output_data, dict):
                if "html" in output_data:
                    ctx["put_html"](output_data["html"])
                else:
                    ctx["put_code"](json.dumps(output_data, ensure_ascii=False, indent=2), language="json")
            elif isinstance(output_data, str):
                if output_data.startswith("<"):
                    ctx["put_html"](output_data)
                else:
                    ctx["put_code"](output_data[:2000], language="text")
            elif isinstance(output_data, list):
                ctx["put_code"](json.dumps(output_data[:20], ensure_ascii=False, indent=2), language="json")
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
    
    source_options = [{"label": "无", "value": ""}]
    for ds in ds_mgr.list_all():
        source_options.append({"label": ds.name, "value": ds.id})
    
    dict_options = []
    for d in dict_mgr.list_all():
        dict_options.append({"label": d.name, "value": d.id})
    
    with ctx["popup"](f"编辑策略: {entry.name}", size="large", closable=True):
        compute_mode = getattr(entry._metadata, "compute_mode", "record")
        window_type = getattr(entry._metadata, "window_type", "sliding")
        window_return_partial = getattr(entry._metadata, "window_return_partial", False)
        bound_datasource_id = getattr(entry._metadata, "bound_datasource_id", "")
        dictionary_profile_ids = getattr(entry._metadata, "dictionary_profile_ids", [])
        
        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("名称", name="name", required=True, value=entry.name),
            ctx["textarea"]("描述", name="description", rows=2, 
                          value=getattr(entry._metadata, "description", "") or ""),
            ctx["select"]("绑定数据源", name="datasource_id", options=source_options, 
                        value=bound_datasource_id),
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
            form_window_return_partial = str(form.get("window_return_partial", "false")).lower() in ("true", "1", "yes")
            
            result = entry.update_config(
                name=form["name"].strip(),
                description=form.get("description", "").strip(),
                bound_datasource_id=form.get("datasource_id", ""),
                dictionary_profile_ids=form.get("dictionary_profile_ids", []),
                compute_mode=form.get("compute_mode"),
                window_type=form.get("window_type"),
                window_size=int(form.get("window_size", 5)),
                window_interval=form.get("window_interval", "10s"),
                window_return_partial=form_window_return_partial,
                max_history_count=int(form.get("max_history_count", 100)),
                func_code=form.get("code"),
            )
            
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
    
    source_options = [{"label": "无", "value": ""}]
    for ds in ds_mgr.list_all():
        source_options.append({"label": ds.name, "value": ds.id})
    
    dict_options = []
    for d in dict_mgr.list_all():
        dict_options.append({"label": d.name, "value": d.id})
    
    with ctx["popup"]("创建策略", size="large", closable=True):
        ctx["put_markdown"]("### 创建策略")
        ctx["put_html"]("<p style='color:#666;font-size:13px;'>处理数据流中的数据</p>")
        
        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("名称", name="name", required=True, placeholder="输入策略名称"),
            ctx["textarea"]("描述", name="description", rows=2, placeholder="策略描述（可选）"),
            ctx["select"]("绑定数据源", name="datasource_id", options=source_options, value=""),
            ctx["select"]("字典配置", name="dictionary_profile_ids", options=dict_options, multiple=True, value=[]),
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
            ctx["textarea"]("代码", name="code", 
                          value=DEFAULT_STRATEGY_CODE, 
                          rows=14, 
                          code={"mode": "python", "theme": "darcula"}),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if form and form.get("action") == "create":
            window_return_partial = str(form.get("window_return_partial", "false")).lower() in ("true", "1", "yes")
            
            result = mgr.create(
                name=form["name"].strip(),
                func_code=form.get("code", ""),
                description=form.get("description", "").strip(),
                bound_datasource_id=form.get("datasource_id", ""),
                dictionary_profile_ids=form.get("dictionary_profile_ids", []),
                compute_mode=form.get("compute_mode", "record"),
                window_type=form.get("window_type", "sliding"),
                window_size=int(form.get("window_size", 5)),
                window_interval=form.get("window_interval", "10s"),
                window_return_partial=window_return_partial,
                max_history_count=int(form.get("max_history_count", 100)),
            )
            
            if result.get("success"):
                ctx["toast"]("创建成功", color="success")
                ctx["close_popup"]()
                _render_strategy_content(ctx)
            else:
                ctx["toast"](f"创建失败: {result.get('error')}", color="error")
