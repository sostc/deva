"""策略管理UI面板(Strategy Admin Panel)

提供策略的可视化管理界面，包括：
- 策略管理（创建、编辑、启动/停止、删除）
- 历史记录管理（配置保留条数、查看历史结果）
- 执行监控（状态、统计、错误处理）
- 系统配置（全局历史记录限制设置）

================================================================================
系统架构
================================================================================

【架构流程图】
┌─────────────────────────────────────────────────────────────────────────────┐
│                               用户界面                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────┐  ┌─────────────────────────┐                │
│  │   策略管理界面          │  │   配置管理界面          │                │
│  ├─────────────────────────┤  ├─────────────────────────┤                │
│  │ - 创建/编辑策略         │  │ - 全局历史记录限制      │                │
│  │ - 启动/停止策略         │  │ - 其他系统配置         │                │
│  │ - 查看历史记录          │  └─────────────────────────┘                │
│  └─────────────────────────┘                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                            策略管理器                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ - 策略生命周期管理                                                          │
│ - 历史记录管理                                                              │
│ - 执行状态监控                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                            策略执行单元                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ - 数据处理逻辑                                                              │
│ - 历史记录保存                                                              │
│ - 自动清理过期记录                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                            结果存储                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ - 内存缓存（最近记录）                                                      │
│ - 持久化存储（SQLite）                                                     │
│ - 历史记录清理                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

================================================================================
UI 组件结构
================================================================================

【页面布局】
┌─────────────────────────────────────────────────────────────────────────────┐
│  导航栏                                                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  统计概览卡片                                                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│  │ 总策略数  │ │ 运行中   │ │ 暂停中   │ │ 错误数   │                        │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  策略列表表格                                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 名称 │ 状态 │ 绑定数据源 │ 策略简介 │ 最近数据 │ 操作 │                  │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │ ...  │ ...  │ ...         │ ...      │ ...      │ 启动/停止/编辑/删除 │  │
│  └──────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│  使用说明与文档                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 系统架构 │ 核心功能 │ 使用流程 │ 最佳实践 │                            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘

================================================================================
历史记录管理流程
================================================================================

【历史记录管理】
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. 创建/编辑策略                                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  - 设置历史记录保留条数（默认30条）                                           │
│  - 系统自动检查是否超过全局限制（默认300条）                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  2. 策略执行                                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  - 执行处理逻辑                                                              │
│  - 保存执行结果                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  3. 历史记录管理                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  - 检查是否超过保留限制                                                      │
│  - 自动清理最旧的记录                                                        │
│  - 更新内存缓存和持久化存储                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  4. 查看历史记录                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  - 在策略详情页面查看                                                      │
│  - 支持按条件筛选                                                          │
│  - 可导出为JSON/CSV格式                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from deva import NS, NB

from .strategy_unit import StrategyUnit, StrategyStatus
from .strategy_manager import get_manager

from .fault_tolerance import (
    get_error_collector,
    get_metrics_collector,
)
from ..datasource.datasource import get_ds_manager
from ..ai.ai_strategy_generator import (
    generate_strategy_code,
    validate_strategy_code,
    test_strategy_code,
    analyze_data_schema,
    build_datasource_context,
    build_schema_from_metadata,
)
from .strategy_logic_db import (
    get_logic_db,
    get_instance_db,
)
from .result_store import get_result_store
import pandas as pd

# 导入策略详情和编辑模块
from .strategy_detail import _show_strategy_detail, _show_code_version_detail, _show_result_detail
from .strategy_edit import _edit_strategy_dialog, _save_strategy, _bind_datasource_and_start, _create_strategy_dialog, _create_ai_strategy_dialog


STATUS_COLORS = {
    StrategyStatus.STOPPED: "#6c757d",
    StrategyStatus.RUNNING: "#28a745",
}

STATUS_LABELS = {
    StrategyStatus.STOPPED: "已停止",
    StrategyStatus.RUNNING: "运行中",
}


def render_strategy_admin_panel(ctx):
    """渲染策略管理面板"""
    ctx["put_markdown"]("### 📊 策略管理面板")
    
    _render_stats_overview(ctx)
    
    ctx["put_markdown"]("### 📋 策略列表")
    _render_strategy_table(ctx)
    
    ctx["put_markdown"]("### 📡 策略输出监控")
    _render_result_monitor(ctx)
    

    
    ctx["put_markdown"]("### 🚨 错误监控")
    _render_error_panel(ctx)
    
    ctx["put_markdown"]("### 📈 监控指标")
    _render_metrics_panel(ctx)


def _render_stats_overview(ctx):
    manager = get_manager()
    stats = manager.get_stats()
    
    error_stats = get_error_collector().get_stats()
    
    cards_html = f"""
    <div style="display:flex;gap:16px;margin-bottom:20px;">
        <div style="flex:1;background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">总策略数</div>
            <div style="font-size:24px;font-weight:bold;color:#333;">{stats['total_units']}</div>
        </div>
        <div style="flex:1;background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">运行中</div>
            <div style="font-size:24px;font-weight:bold;color:#28a745;">{stats['running_count']}</div>
        </div>
        <div style="flex:1;background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">已暂停</div>
            <div style="font-size:24px;font-weight:bold;color:#ffc107;">{stats['paused_count']}</div>
        </div>
        <div style="flex:1;background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">错误数</div>
            <div style="font-size:24px;font-weight:bold;color:#dc3545;">{error_stats['unresolved']}</div>
        </div>
    </div>
    """
    ctx["put_html"](cards_html)


def _render_strategy_table(ctx):
    manager = get_manager()
    units = manager.list_all()
    
    if not units:
        ctx["put_text"]('暂无策略，请创建新策略')
        ctx["put_button"]('创建策略', onclick=lambda: ctx["run_async"](_create_strategy_dialog(ctx)))
        return
    
    table_data = [["名称", "状态", "绑定数据源", "策略简介", "最近数据", "操作"]]
    
    for unit_data in units:
        # 安全获取状态
        state_data = unit_data.get("state", {})
        status = state_data.get("status", "stopped")
        
        # 处理状态值，确保与StrategyStatus兼容
        try:
            status_enum = StrategyStatus(status)
        except ValueError:
            # 对于未知状态，默认为stopped
            status_enum = StrategyStatus.STOPPED
        
        status_color = STATUS_COLORS.get(status_enum, "#666")
        status_label = STATUS_LABELS.get(status_enum, "未知")
        
        metadata = unit_data.get("metadata", {})
        bound_ds_name = metadata.get("bound_datasource_name", "")
        summary = metadata.get("summary", "")
        
        bound_datasource = bound_ds_name if bound_ds_name else "-"
        
        # 策略简介显示 - 优先使用summary，其次使用description
        summary_text = summary or metadata.get("description", "")
        summary_preview = summary_text[:100] + ("..." if len(summary_text) > 100 else "") if summary_text else "-"
        
        # 最近数据显示
        processed_count = state_data.get("processed_count", 0)
        last_process_ts = state_data.get("last_process_ts", 0)
        
        recent_data = "-"
        if last_process_ts > 0:
            from datetime import datetime
            try:
                last_process_time = datetime.fromtimestamp(last_process_ts).strftime("%Y-%m-%d %H:%M:%S")
                recent_data = f"执行 {processed_count} 次<br>最后执行: {last_process_time}"
            except Exception:
                # 时间戳异常时只显示计数
                recent_data = f"执行 {processed_count} 次"
        else:
            recent_data = f"执行 {processed_count} 次"
        
        unit_id = metadata.get("id", "")
        
        status_html = f'<span style="background:{status_color};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">{status_label}</span>'
        
        if status_enum == StrategyStatus.RUNNING:
            toggle_label = "停止"
        else:
            toggle_label = "启动"
        
        actions = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{unit_id}"},
            {"label": "编辑", "value": f"edit_{unit_id}"},
            {"label": toggle_label, "value": f"toggle_{unit_id}"},
            {"label": "删除", "value": f"delete_{unit_id}"},
        ], onclick=lambda v, uid=unit_id: _handle_strategy_action(ctx, v, uid))
        
        table_data.append([
            metadata.get("name", "-"),
            ctx["put_html"](status_html),
            bound_datasource[:20] + "..." if len(bound_datasource) > 20 else bound_datasource,
            ctx["put_html"](f'<span style="font-size:12px;">{summary_preview}</span>'),
            ctx["put_html"](f'<span style="font-size:12px;">{recent_data}</span>'),
            actions,
        ])
    
    ctx["put_table"](table_data)
    
    ctx["put_row"]([
        ctx["put_button"]("创建策略", onclick=lambda: ctx["run_async"](_create_strategy_dialog(ctx))).style("margin-right: 10px"),
        ctx["put_button"]("全部启动", onclick=lambda: _start_all_strategies(ctx)),
        ctx["put_button"]("全部停止", onclick=lambda: _stop_all_strategies(ctx)).style("margin-left: 10px"),
    ]).style("margin-top: 10px")


def _render_result_monitor(ctx):
    manager = get_manager()
    units = manager.list_all()
    
    if not units:
        ctx["put_text"]("暂无策略执行结果")
        return
    
    store = get_result_store()
    result_stats = store.get_stats()
    
    cards_html = f"""
    <div style="display:flex;gap:16px;margin-bottom:20px;">
        <div style="flex:1;background:#fff;padding:12px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">总执行次数</div>
            <div style="font-size:20px;font-weight:bold;color:#333;">{result_stats.get('total_results', 0)}</div>
        </div>
        <div style="flex:1;background:#fff;padding:12px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">成功次数</div>
            <div style="font-size:20px;font-weight:bold;color:#28a745;">{result_stats.get('total_success', 0)}</div>
        </div>
        <div style="flex:1;background:#fff;padding:12px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">失败次数</div>
            <div style="font-size:20px;font-weight:bold;color:#dc3545;">{result_stats.get('total_failed', 0)}</div>
        </div>
        <div style="flex:1;background:#fff;padding:12px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">平均耗时</div>
            <div style="font-size:20px;font-weight:bold;color:#17a2b8;">{result_stats.get('avg_process_time_ms', 0):.2f}ms</div>
        </div>
        <div style="flex:1;background:#fff;padding:12px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">成功率</div>
            <div style="font-size:20px;font-weight:bold;color:{'#28a745' if result_stats.get('success_rate', 0) > 0.9 else '#ffc107'};">{result_stats.get('success_rate', 0)*100:.1f}%</div>
        </div>
    </div>
    """
    ctx["put_html"](cards_html)
    
    unit_options = [
        {"label": u.get("metadata", {}).get("name", u.get("metadata", {}).get("id", "unknown")), 
         "value": u.get("metadata", {}).get("id", "")}
        for u in units
    ]
    
    ctx["put_row"]([
        ctx["put_button"]("查看执行历史", onclick=lambda: ctx["run_async"](_show_result_history_dialog(ctx)), color="primary").style("margin-right: 10px"),
        ctx["put_button"]("导出结果(JSON)", onclick=lambda: _export_results(ctx, "json"), color="info").style("margin-right: 10px"),
        ctx["put_button"]("导出结果(CSV)", onclick=lambda: _export_results(ctx, "csv"), color="info").style("margin-right: 10px"),
        ctx["put_button"]("清空缓存", onclick=lambda: _clear_result_cache(ctx), color="warning"),
    ]).style("margin-top: 10px")
    
    ctx["put_markdown"]("#### 最近执行结果")
    ctx["set_scope"]("recent_results_table")
    _refresh_recent_results(ctx)


def _refresh_recent_results(ctx, limit: int = 10):
    manager = get_manager()
    store = get_result_store()
    
    all_results = []
    for unit_data in manager.list_all():
        unit_id = unit_data.get("metadata", {}).get("id", "")
        results = store.get_recent(unit_id, limit=5)
        all_results.extend(results)
    
    all_results.sort(key=lambda x: x.ts, reverse=True)
    all_results = all_results[:limit]
    
    if not all_results:
        with ctx["use_scope"]("recent_results_table", clear=True):
            ctx["put_text"]("暂无执行结果")
        return
    
    table_data = [["时间", "策略名称", "状态", "耗时", "输出预览", "操作"]]
    
    for r in all_results:
        status_html = '<span style="color:#28a745;">✅ 成功</span>' if r.success else '<span style="color:#dc3545;">❌ 失败</span>'
        output_preview = r.output_preview[:80] + "..." if len(r.output_preview) > 80 else r.output_preview
        if not r.success and r.error:
            output_preview = f"错误: {r.error[:60]}..."
        
        actions = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{r.id}"},
        ], onclick=lambda v, rid=r.id: _show_result_detail(ctx, rid))
        
        table_data.append([
            r.ts_readable if hasattr(r, 'ts_readable') else datetime.fromtimestamp(r.ts).strftime("%H:%M:%S"),
            r.strategy_name[:15],
            ctx["put_html"](status_html),
            f"{r.process_time_ms:.1f}ms",
            output_preview,
            actions,
        ])
    
    with ctx["use_scope"]("recent_results_table", clear=True):
        ctx["put_table"](table_data)





def _export_results(ctx, format: str):
    manager = get_manager()
    export_data = manager.export_results(format=format, limit=1000)
    
    filename = f"strategy_results.{format}"
    
    # 创建弹窗显示下载链接
    with ctx["popup"]("导出结果", size="small", closable=True):
        ctx["put_markdown"]("### 📥 导出完成")
        ctx["put_text"]("文件已准备就绪，请点击下方链接下载")
        ctx["put_text"]("")  # 空行用于间距
        
        from pywebio.output import put_file
        put_file(filename, export_data.encode('utf-8'))
        
        ctx["put_row"]([
            ctx["put_button"]("关闭", onclick=lambda: ctx["close_popup"](), color="primary"),
        ]).style("margin-top: 20px")
    
    ctx["toast"](f"已导出 {filename}", color="success")


def _clear_result_cache(ctx):
    store = get_result_store()
    store.clear_cache()
    ctx["toast"]("已清空结果缓存", color="success")
    ctx["run_js"]("location.reload()")


async def _show_result_history_dialog(ctx):
    manager = get_manager()
    units = manager.list_all()
    
    unit_options = [
        {"label": "全部策略", "value": ""},
    ] + [
        {"label": u.get("metadata", {}).get("name", "unknown"), 
         "value": u.get("metadata", {}).get("id", "")}
        for u in units
    ]
    
    # 创建弹窗
    with ctx["popup"]("📜 执行历史", size="large", closable=True):
        # 显示查询表单
        form = await ctx["input_group"]("查询条件", [
            ctx["select"]("策略", name="unit_id", options=unit_options, value=""),
            ctx["input"]("时间范围(分钟)", name="minutes", type=ctx["NUMBER"], value=60, placeholder="查询最近N分钟"),
            ctx["checkbox"]('仅成功', name="success_only", options=[{"label": "仅显示成功", "value": "success_only", "selected": False}]),
            ctx["input"]("限制条数", name="limit", type=ctx["NUMBER"], value=100),
            ctx["actions"]("操作", [
                {"label": "查询", "value": "query"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not form or form.get("action") == "cancel":
            return
        
        # 计算时间范围
        import time as time_module
        start_ts = time_module.time() - form["minutes"] * 60
        
        # 查询结果
        results = manager.query_results(
            unit_id=form["unit_id"] or None,
            start_ts=start_ts,
            success_only="success_only" in form.get("success_only", []),
            limit=form["limit"],
        )
        
        # 关闭当前弹窗并打开新的结果弹窗
        ctx["close_popup"]()
        
        # 创建结果显示弹窗
        with ctx["popup"]("📜 执行历史查询结果", size="large", closable=True):
            # 显示结果标题
            ctx["put_markdown"](f"### 📜 执行历史查询结果")
            ctx["put_markdown"](f"**查询条件:** 时间范围: {form['minutes']}分钟, 限制条数: {form['limit']}")
            ctx["put_markdown"](f"**查询结果:** 共找到 {len(results)} 条记录")
            
            if not results:
                ctx["put_html"]("<div style='padding:20px;background:#f8d7da;border-radius:4px;color:#721c24;'>未找到符合条件的记录</div>")
                ctx["put_button"]("关闭", onclick=lambda: ctx["close_popup"]())
                return
            
            # 显示结果表格
            table_data = [["时间", "策略", "状态", "耗时", "预览"]]
            for r in results:
                status = "✅" if r.get("success") else "❌"
                preview = r.get("output_preview", "")[:50] or r.get("error", "")[:50]
                table_data.append([
                    r.get("ts_readable", "")[:16],
                    r.get("strategy_name", "")[:15],
                    status,
                    f"{r.get('process_time_ms', 0):.1f}ms",
                    preview[:50] + "...",
                ])
            
            ctx["put_table"](table_data)
            
            # 添加关闭按钮
            ctx["put_row"]([
                ctx["put_button"]("关闭", onclick=lambda: ctx["close_popup"](), color="primary"),
            ]).style("margin-top: 20px")





def _handle_strategy_action(ctx, action_value: str, unit_id: str):
    parts = action_value.split("_", 1)
    action = parts[0]
    
    manager = get_manager()
    
    if action == "detail":
        _show_strategy_detail(ctx, unit_id)
        return
    elif action == "edit":
        ctx["run_async"](_edit_strategy_dialog(ctx, unit_id))
        return
    elif action == "toggle":
        unit = manager.get_unit(unit_id)
        if unit:
            if unit.status == StrategyStatus.RUNNING:
                result = manager.stop(unit_id)
                ctx["toast"](f"已停止: {result.get('status', '')}", color="success")
            else:
                if not unit.metadata.bound_datasource_id:
                    ctx["run_async"](_bind_datasource_and_start(ctx, unit_id))
                else:
                    result = manager.start(unit_id)
                    ctx["toast"](f"已启动: {result.get('status', '')}", color="success")
    elif action == "delete":
        manager.delete(unit_id)
        ctx["toast"]("策略已删除", color="success")
    
    ctx["run_js"]("location.reload()")























def _start_all_strategies(ctx):
    manager = get_manager()
    result = manager.start_all()
    ctx["toast"](f"启动完成: 成功{result['success']}, 失败{result['failed']}, 跳过{result['skipped']}", color="info")
    ctx["run_js"]("location.reload()")


def _stop_all_strategies(ctx):
    manager = get_manager()
    result = manager.stop_all()
    ctx["toast"](f"停止完成: 成功{result['success']}, 失败{result['failed']}, 跳过{result['skipped']}", color="info")
    ctx["run_js"]("location.reload()")


def _render_lab_section(ctx):
    ctx["put_html"]("""
    <details>
        <summary style="cursor:pointer;padding:8px;background:#e8f5e9;border-radius:4px;">
            🧪 点击展开策略实验室
        </summary>
        <div style="padding:16px;background:#fafafa;border-radius:4px;margin-top:8px;">
            <p>策略实验室支持：</p>
            <ul>
                <li>数据回放：从存储中提取历史数据</li>
                <li>影子测试：创建隔离沙盒运行新逻辑</li>
                <li>可视化比对：并排对比新旧输出</li>
                <li>合规性检查：验证 Schema 兼容性</li>
            </ul>
        </div>
    </details>
    """)
    

def _render_error_panel(ctx):
    error_collector = get_error_collector()
    errors = error_collector.get_errors(limit=10, unresolved_only=True)
    
    if not errors:
        ctx["put_html"]('<div style="padding:16px;background:#d4edda;border-radius:4px;color:#155724;">✅ 暂无未解决的错误</div>')
        return
    
    error_table = [["时间", "策略", "错误类型", "消息", "操作"]]
    
    for e in errors:
        actions = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{e['id']}"},
            {"label": "已解决", "value": f"resolve_{e['id']}"},
        ], onclick=lambda v, eid=e["id"]: _handle_error_action(ctx, v, eid))
        
        error_table.append([
            e.get("ts_readable", "")[:16],
            e.get("strategy_name", "-")[:15],
            e.get("error_type", "-")[:15],
            e.get("error_message", "-")[:30],
            actions,
        ])
    
    ctx["put_table"](error_table)
    
    stats = error_collector.get_stats()
    ctx["put_html"](f"""
    <div style="margin-top:10px;padding:12px;background:#f8d7da;border-radius:4px;">
        <strong>错误统计:</strong> 总计 {stats['total_errors']} 条，未解决 {stats['unresolved']} 条
    </div>
    """)


def _handle_error_action(ctx, action_value: str, error_id: str):
    parts = action_value.split("_", 1)
    action = parts[0]
    
    error_collector = get_error_collector()
    
    if action == "detail":
        errors = error_collector.get_errors(limit=100)
        for e in errors:
            if e["id"] == error_id:
                ctx["popup"](f"错误详情: {e.get('error_type', '')}", [
                    ctx["put_markdown"](f"**策略**: {e.get('strategy_name', '')}"),
                    ctx["put_markdown"](f"**时间**: {e.get('ts_readable', '')}"),
                    ctx["put_markdown"](f"**消息**: {e.get('error_message', '')}"),
                    ctx["put_markdown"]("**数据预览**"),
                    ctx["put_code"](e.get('data_preview', ''), language="text"),
                    ctx["put_markdown"]("**堆栈跟踪**"),
                    ctx["put_code"](e.get('traceback', ''), language="python"),
                ], size="large")
                break
    elif action == "resolve":
        if error_collector.resolve_error(error_id):
            ctx["toast"]("已标记为已解决", color="success")
            ctx["run_js"]("location.reload()")


def _render_metrics_panel(ctx):
    metrics_collector = get_metrics_collector()
    summary = metrics_collector.get_summary()
    
    ctx["put_html"](f"""
    <div style="display:flex;gap:16px;margin-bottom:20px;">
        <div style="flex:1;background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">总处理数</div>
            <div style="font-size:20px;font-weight:bold;color:#333;">{summary['total_processed']}</div>
        </div>
        <div style="flex:1;background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">平均耗时</div>
            <div style="font-size:20px;font-weight:bold;color:#333;">{summary['avg_time_ms']:.2f}ms</div>
        </div>
        <div style="flex:1;background:#fff;padding:16px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size:12px;color:#666;">错误率</div>
            <div style="font-size:20px;font-weight:bold;color:{'#dc3545' if summary['error_rate'] > 0.01 else '#28a745'};">{summary['error_rate']*100:.2f}%</div>
        </div>
    </div>
    """)
    



async def render_strategy_admin(ctx):
    """策略管理页面入口"""
    await ctx["init_admin_ui"]("Deva策略管理")
    
    manager = get_manager()
    manager.load_from_db()
    
    from .fault_tolerance import initialize_fault_tolerance
    initialize_fault_tolerance()
    
    render_strategy_admin_panel(ctx)
    
    ctx["put_markdown"]("### 📚 使用说明")
    ctx["put_collapse"]("点击查看文档", [
        ctx["put_markdown"]("""
## 系统架构

### 架构流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                               用户界面                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────┐  ┌─────────────────────────┐                │
│  │   策略管理界面          │  │   配置管理界面          │                │
│  ├─────────────────────────┤  ├─────────────────────────┤                │
│  │ - 创建/编辑策略         │  │ - 全局历史记录限制      │                │
│  │ - 启动/停止策略         │  │ - 其他系统配置         │                │
│  │ - 查看历史记录          │  └─────────────────────────┘                │
│  └─────────────────────────┘                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                            策略管理器                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ - 策略生命周期管理                                                          │
│ - 历史记录管理                                                              │
│ - 执行状态监控                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                            策略执行单元                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ - 数据处理逻辑                                                              │
│ - 历史记录保存                                                              │
│ - 自动清理过期记录                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                            结果存储                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ - 内存缓存（最近记录）                                                      │
│ - 持久化存储（SQLite）                                                     │
│ - 历史记录清理                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 策略执行单元

策略执行单元是一个独立的逻辑资产，封装了：

- **元数据**：名称、ID、备注、标签、历史记录保留设置
- **执行体**：Python处理函数，负责数据转换和处理
- **状态管理**：运行、停止状态管理和执行统计
- **数据处理**：输入数据流处理和输出结果生成
- **历史记录**：可配置的执行结果持久化存储

## 核心功能

### 1. 策略生命周期管理

- **创建策略**：手动编写或通过AI生成策略代码，设置基本信息和历史记录保留条数
- **编辑策略**：修改策略代码、配置和历史记录保留设置
- **启动/停止**：控制策略的运行状态
- **删除策略**：移除不需要的策略及其相关数据

### 2. 历史记录管理

- **保留设置**：创建或编辑策略时可设置历史记录保留条数（默认30条）
- **系统限制**：单个策略的保留条数不能超过系统配置的最大值（默认300条）
- **自动清理**：当历史记录超过设置的限制时，系统会自动清理最旧的记录
- **查看历史**：在策略详情页面可查看历史执行结果，支持按条件筛选

### 3. 执行与监控

- **数据处理**：策略接收数据源输入，执行处理逻辑，输出结果到下游
- **执行统计**：实时记录执行次数、成功率、处理时间等指标
- **错误处理**：捕获和记录执行过程中的错误
- **状态监控**：实时显示策略运行状态和健康状况

### 4. 系统配置

- **全局设置**：在Admin配置页面的"策略配置"标签页中设置全局最大历史记录条数限制
- **范围限制**：全局历史记录限制范围为1-1000条
- **配置生效**：修改配置后立即生效，新创建的策略会使用新的限制

## 历史记录管理流程

### 历史记录管理流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. 创建/编辑策略                                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  - 设置历史记录保留条数（默认30条）                                           │
│  - 系统自动检查是否超过全局限制（默认300条）                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  2. 策略执行                                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  - 执行处理逻辑                                                              │
│  - 保存执行结果                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  3. 历史记录管理                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  - 检查是否超过保留限制                                                      │
│  - 自动清理最旧的记录                                                        │
│  - 更新内存缓存和持久化存储                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  4. 查看历史记录                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  - 在策略详情页面查看                                                      │
│  - 支持按条件筛选                                                          │
│  - 可导出为JSON/CSV格式                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 使用流程

1. **创建策略**：点击"创建策略"按钮，填写策略名称、简介，编写或生成策略代码，设置历史记录保留条数
2. **绑定数据源**：选择并绑定数据源，建立数据输入通道
3. **启动策略**：点击"启动"按钮，开始处理数据
4. **监控运行**：在策略列表页面查看执行状态和统计信息
5. **查看历史**：在策略详情页面查看历史执行结果
6. **调整配置**：根据需要编辑策略，调整历史记录保留设置

## 最佳实践

- **合理设置历史记录**：根据策略执行频率和数据量，设置合适的历史记录保留条数
- **定期清理**：对于执行频率高的策略，建议设置较小的保留条数
- **监控性能**：关注策略执行时间和成功率，及时优化代码
- **错误处理**：在策略代码中添加适当的错误处理，提高稳定性
        """),
    ], open=False)
