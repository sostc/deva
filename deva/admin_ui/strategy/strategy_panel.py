"""策略管理UI面板(Strategy Admin Panel)

提供策略的可视化管理界面，包括：
- 策略拓扑图
- 资产概览
- AI逻辑说明书
- 操作控制台

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
│  │ 名称 │ 状态 │ 上游 │ 下游 │ 处理数 │ 错误数 │ 操作 │                  │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │ ...  │ ...  │ ... │ ... │ ...   │ ...   │ 暂停/恢复/删除 │            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│  策略实验室                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 代码编辑器 │ 测试数据选择 │ 结果对比 │                                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│  错误监控面板                                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 最新错误列表 │ 错误趋势图 │ 一键反馈AI │                              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from deva import NS, NB

from .strategy_unit import StrategyUnit, StrategyStatus
from .strategy_manager import get_manager
from .replay_lab import get_lab
from .fault_tolerance import (
    get_error_collector,
    get_metrics_collector,
)
from .stock_strategies import (
    list_available_strategies,
    initialize_default_stock_strategies,
)
from .datasource import get_ds_manager
from .ai_strategy_generator import (
    generate_strategy_code,
    generate_strategy_documentation,
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


STATUS_COLORS = {
    StrategyStatus.DRAFT: "#6c757d",
    StrategyStatus.RUNNING: "#28a745",
    StrategyStatus.PAUSED: "#ffc107",
    StrategyStatus.ARCHIVED: "#dc3545",
}

STATUS_LABELS = {
    StrategyStatus.DRAFT: "草稿",
    StrategyStatus.RUNNING: "运行中",
    StrategyStatus.PAUSED: "已暂停",
    StrategyStatus.ARCHIVED: "已归档",
}


def render_strategy_admin_panel(ctx):
    """渲染策略管理面板"""
    ctx["put_markdown"]("### 📊 策略管理面板")
    
    _render_stats_overview(ctx)
    
    ctx["put_markdown"]("### 📋 策略列表")
    _render_strategy_table(ctx)
    
    ctx["put_markdown"]("### 📈 股票策略")
    _render_stock_strategy_section(ctx)
    
    ctx["put_markdown"]("### 📡 策略输出监控")
    _render_result_monitor(ctx)
    
    ctx["put_markdown"]("### 🧪 策略实验室")
    _render_lab_section(ctx)
    
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
        ctx["put_text"]("暂无策略，请创建新策略")
        ctx["put_button"]("创建策略", onclick=lambda: ctx["run_async"](_create_strategy_dialog(ctx)))
        return
    
    table_data = [["名称", "状态", "上游", "下游", "处理数", "错误数", "操作"]]
    
    for unit_data in units:
        status = unit_data.get("state", {}).get("status", "draft")
        status_color = STATUS_COLORS.get(StrategyStatus(status), "#666")
        status_label = STATUS_LABELS.get(StrategyStatus(status), status)
        
        upstream = ", ".join([u.get("name", "") or "" for u in unit_data.get("lineage", {}).get("upstream", [])]) or "-"
        downstream = ", ".join([d.get("name", "") or "" for d in unit_data.get("lineage", {}).get("downstream", [])]) or "-"
        
        processed = unit_data.get("state", {}).get("processed_count", 0)
        errors = unit_data.get("state", {}).get("error_count", 0)
        
        unit_id = unit_data.get("metadata", {}).get("id", "")
        
        status_html = f'<span style="background:{status_color};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">{status_label}</span>'
        
        if status == "running":
            toggle_label = "暂停"
        elif status == "draft":
            toggle_label = "启动"
        else:
            toggle_label = "恢复"
        
        actions = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{unit_id}"},
            {"label": toggle_label, "value": f"toggle_{unit_id}"},
            {"label": "删除", "value": f"delete_{unit_id}"},
        ], onclick=lambda v, uid=unit_id: _handle_strategy_action(ctx, v, uid))
        
        table_data.append([
            unit_data.get("metadata", {}).get("name", "-"),
            ctx["put_html"](status_html),
            upstream[:30] + "..." if len(upstream) > 30 else upstream,
            downstream[:30] + "..." if len(downstream) > 30 else downstream,
            str(processed),
            str(errors),
            actions,
        ])
    
    ctx["put_table"](table_data)
    
    ctx["put_row"]([
        ctx["put_button"]("创建策略", onclick=lambda: ctx["run_async"](_create_strategy_dialog(ctx))).style("margin-right: 10px"),
        ctx["put_button"]("全部启动", onclick=lambda: _start_all_strategies(ctx)),
        ctx["put_button"]("全部暂停", onclick=lambda: _pause_all_strategies(ctx)).style("margin-left: 10px"),
    ]).style("margin-top: 10px")


def _render_stock_strategy_section(ctx):
    available_strategies = list_available_strategies()
    
    ctx["put_html"]("""
    <div style="background:#e3f2fd;padding:12px;border-radius:8px;margin-bottom:16px;">
        <p style="margin:0;color:#1565c0;"><b>股票策略类型</b></p>
        <ul style="margin:8px 0 0 0;padding-left:20px;color:#1976d2;">
            <li><b>block_change</b>: 板块异动分析 - 计算板块在时间窗口内的涨跌幅变化</li>
            <li><b>block_ranking</b>: 领涨领跌板块 - 计算当日各板块的涨跌幅排名</li>
            <li><b>limit_up_down</b>: 涨跌停统计 - 统计涨停和跌停的股票数量及分布</li>
            <li><b>custom_filter</b>: 自定义筛选 - 根据自定义条件筛选股票</li>
        </ul>
    </div>
    """)
    
    table_data = [["策略名称", "类型", "描述", "操作"]]
    
    for config in available_strategies:
        actions = ctx["put_buttons"]([
            {"label": "创建", "value": f"create_{config['type']}_{config['name']}"},
        ], onclick=lambda v, cfg=config: _handle_stock_strategy_action(ctx, v, cfg))
        
        table_data.append([
            config["name"],
            config["type"],
            config.get("description", "-"),
            actions,
        ])
    
    ctx["put_table"](table_data)
    
    ctx["put_row"]([
        ctx["put_button"]("🤖 AI生成策略", onclick=lambda: ctx["run_async"](_create_ai_strategy_dialog(ctx)), color="success").style("margin-right: 10px"),
        ctx["put_button"]("初始化默认股票策略", onclick=lambda: _init_default_stock_strategies(ctx), color="primary").style("margin-right: 10px"),
        ctx["put_button"]("创建自定义股票策略", onclick=lambda: ctx["run_async"](_create_custom_stock_strategy_dialog(ctx))),
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


def _export_results(ctx, format: str):
    manager = get_manager()
    export_data = manager.export_results(format=format, limit=1000)
    
    filename = f"strategy_results.{format}"
    ctx["put_file"](filename, export_data.encode('utf-8'))
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
    
    with ctx["popup"]("📜 执行历史", size="large", closable=True):
        form = await ctx["input_group"]("查询条件", [
            ctx["select"]("策略", name="unit_id", options=unit_options, value=""),
            ctx["input"]("时间范围(分钟)", name="minutes", type=ctx["NUMBER"], value=60, placeholder="查询最近N分钟"),
            ctx["checkbox"]("仅成功", name="success_only", options=[{"label": "仅显示成功", "value": True}]),
            ctx["input"]("限制条数", name="limit", type=ctx["NUMBER"], value=100),
            ctx["actions"]("操作", [
                {"label": "查询", "value": "query"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not form or form.get("action") == "cancel":
            return
        
        import time as time_module
        start_ts = time_module.time() - form["minutes"] * 60
        
        results = manager.query_results(
            unit_id=form["unit_id"] or None,
            start_ts=start_ts,
            success_only=form.get("success_only", False),
            limit=form["limit"],
        )
        
        ctx["put_markdown"](f"### 查询结果 ({len(results)} 条)")
        
        if not results:
            ctx["put_text"]("未找到符合条件的记录")
            return
        
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


def _handle_stock_strategy_action(ctx, action_value: str, config: dict):
    from .stock_strategies import create_stock_strategy
    
    parts = action_value.split("_", 1)
    action = parts[0]
    
    if action == "create":
        strategy = create_stock_strategy(
            strategy_type=config["type"],
            name=config["name"],
        )
        
        if strategy:
            ds_mgr = get_ds_manager()
            quant_source = ds_mgr.get_source_by_name("quant_source")
            
            if quant_source:
                manager = get_manager()
                manager.register(strategy)
                ds_mgr.link_strategy(quant_source.id, strategy.id)
                
                stream = quant_source.get_stream()
                if stream:
                    strategy.set_input_stream(stream.filter(lambda x: x is not None))
                
                strategy.save()
                ctx["toast"](f"策略创建成功并已关联 quant_source: {strategy.name}", color="success")
            else:
                ctx["toast"](f"策略创建成功，但未找到 quant_source 数据源: {strategy.name}", color="warning")
        else:
            ctx["toast"](f"创建失败: 未知策略类型", color="error")
        
        ctx["run_js"]("location.reload()")


def _init_default_stock_strategies(ctx):
    ds_mgr = get_ds_manager()
    quant_source = ds_mgr.get_source_by_name("quant_source")
    
    if not quant_source:
        ctx["toast"]("未找到 quant_source 数据源，请先创建数据源", color="warning")
        return
    
    results = initialize_default_stock_strategies(
        auto_start=False,
        register_to_manager=True,
        datasource_name="quant_source"
    )
    success_count = len(results)
    ctx["toast"](f"初始化完成: 成功 {success_count} 个策略，已关联 quant_source", color="success")
    ctx["run_js"]("location.reload()")


async def _create_custom_stock_strategy_dialog(ctx):
    from .stock_strategies import create_stock_strategy
    
    ds_mgr = get_ds_manager()
    sources = ds_mgr.list_sources()
    
    source_options = [
        {"label": f"{s['name']} ({s['status']})", "value": s['id']}
        for s in sources
    ]
    
    quant_source = ds_mgr.get_source_by_name("quant_source")
    default_source_id = quant_source.id if quant_source else (source_options[0]["value"] if source_options else None)
    
    strategy_types = [
        {"label": "板块异动分析", "value": "block_change"},
        {"label": "领涨领跌板块", "value": "block_ranking"},
        {"label": "涨跌停统计", "value": "limit_up_down"},
        {"label": "自定义筛选", "value": "custom_filter"},
    ]
    
    with ctx["popup"]("创建自定义股票策略", size="large", closable=True):
        form = await ctx["input_group"]("策略配置", [
            ctx["select"]("策略类型", name="strategy_type", options=strategy_types, required=True),
            ctx["input"]("策略名称", name="name", required=True, placeholder="输入策略名称"),
            ctx["select"]("上游数据源", name="datasource_id", options=source_options, value=default_source_id, required=True),
            ctx["input"]("下游输出流名称", name="downstream", placeholder="输出流名称（可选）"),
            ctx["textarea"]("参数配置(JSON)", name="params_json", placeholder='{"window_size": 6, "top_n": 5}', rows=3),
            ctx["actions"]("操作", [
                {"label": "创建", "value": "create"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not form or form.get("action") == "cancel":
            return
        
        params = {}
        if form.get("params_json"):
            try:
                params = json.loads(form["params_json"])
            except json.JSONDecodeError:
                ctx["toast"]("参数JSON格式错误", color="error")
                return
        
        if form.get("downstream"):
            params["output_stream_name"] = form["downstream"]
        
        result = create_stock_strategy(
            strategy_type=form["strategy_type"],
            name=form["name"],
            **params
        )
        
        if result:
            source = ds_mgr.get_source(form["datasource_id"])
            if source:
                manager = get_manager()
                manager.register(result)
                ds_mgr.link_strategy(source.id, result.id)
                
                stream = source.get_stream()
                if stream:
                    result.set_input_stream(stream.filter(lambda x: x is not None))
                
                result.save()
                ctx["toast"](f"策略创建成功并已关联数据源 {source.name}: {result.name}", color="success")
            else:
                ctx["toast"](f"策略创建成功: {result.name}", color="success")
            ctx["run_js"]("location.reload()")
        else:
            ctx["toast"](f"创建失败: 未知策略类型", color="error")


async def _create_ai_strategy_dialog(ctx):
    ds_mgr = get_ds_manager()
    sources = ds_mgr.list_sources()
    
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
            ctx["input"]("下游输出流名称", name="downstream", placeholder="输出流名称（可选）"),
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
            description=form["requirement"],
            upstream_source=source.name,
            downstream_sink=form.get("downstream"),
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


def _handle_strategy_action(ctx, action_value: str, unit_id: str):
    parts = action_value.split("_", 1)
    action = parts[0]
    
    manager = get_manager()
    
    if action == "detail":
        ctx["run_async"](_show_strategy_detail(ctx, unit_id))
        return
    elif action == "toggle":
        unit = manager.get_unit(unit_id)
        if unit:
            if unit.status == StrategyStatus.RUNNING:
                result = manager.pause(unit_id)
                ctx["toast"](f"已暂停: {result.get('status', '')}", color="success")
            elif unit.status == StrategyStatus.DRAFT:
                result = manager.start(unit_id)
                ctx["toast"](f"已启动: {result.get('status', '')}", color="success")
            else:
                result = manager.resume(unit_id)
                ctx["toast"](f"已恢复: {result.get('status', '')}", color="success")
    elif action == "delete":
        result = manager.analyze_deletion_impact(unit_id)
        if result.get("success"):
            impact = result.get("impact", {})
            warnings = impact.get("warnings", [])
            if warnings:
                ctx["toast"](f"警告: {'; '.join(warnings)}", color="warning")
            else:
                manager.delete(unit_id)
                ctx["toast"]("策略已删除", color="success")
    
    ctx["run_js"]("location.reload()")


async def _show_strategy_detail(ctx, unit_id: str):
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
            ["创建时间", datetime.fromtimestamp(unit.metadata.created_at).strftime("%Y-%m-%d %H:%M:%S")],
            ["更新时间", datetime.fromtimestamp(unit.metadata.updated_at).strftime("%Y-%m-%d %H:%M:%S")],
            ["代码版本", str(unit._code_version)],
        ]
        ctx["put_table"](info_table)
        
        ctx["put_row"]([
            ctx["put_button"]("编辑策略", onclick=lambda: ctx["run_async"](_edit_strategy_dialog(ctx, unit_id)), color="primary"),
        ]).style("margin-top: 10px")
        
        if hasattr(unit, 'params') and unit.params:
            ctx["put_markdown"]("### ⚙️ 策略参数")
            params_table = [["参数名", "值"]]
            for key, value in unit.params.items():
                params_table.append([key, str(value)])
            ctx["put_table"](params_table)
        
        ctx["put_markdown"]("### 🔗 血缘关系")
        lineage_table = [["类型", "名称", "说明"]]
        
        for upstream in unit.lineage.upstream:
            lineage_table.append(["上游", upstream.name, upstream.description or "-"])
        for downstream in unit.lineage.downstream:
            exclusive = " (独占)" if downstream.exclusive else ""
            lineage_table.append(["下游", downstream.name + exclusive, downstream.description or "-"])
        
        if len(lineage_table) > 1:
            ctx["put_table"](lineage_table)
        else:
            ctx["put_text"]("暂无血缘关系")
        
        ctx["put_markdown"]("### 📊 执行状态")
        state_table = [
            ["处理计数", str(unit.state.processed_count)],
            ["错误计数", str(unit.state.error_count)],
            ["最近错误", unit.state.last_error or "-"],
            ["最后处理时间", datetime.fromtimestamp(unit.state.last_process_ts).strftime("%Y-%m-%d %H:%M:%S") if unit.state.last_process_ts > 0 else "-"],
        ]
        ctx["put_table"](state_table)
        
        ctx["put_markdown"]("### 📤 最近输出结果")
        recent_results = unit.get_recent_results(limit=10)
        if recent_results:
            result_table = [["时间", "状态", "耗时", "输出预览", "操作"]]
            for r in recent_results:
                status_html = '<span style="color:#28a745;">✅</span>' if r.get("success") else '<span style="color:#dc3545;">❌</span>'
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
                ["持久化更新时间", datetime.fromtimestamp(instance_state.updated_at).strftime("%Y-%m-%d %H:%M:%S")],
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
            ctx["put_html"]("<details open><summary style='cursor:pointer;font-weight:bold;'>点击展开/收起代码</summary>")
            ctx["put_code"](logic_meta.code, language="python")
            ctx["put_html"]("</details>")
        
        if unit._ai_documentation:
            ctx["put_markdown"]("### 🤖 AI 说明文档")
            ctx["put_markdown"](unit._ai_documentation)
        
        if unit._processor_code:
            ctx["put_markdown"]("### 🔧 实例处理器代码")
            ctx["put_html"]("<details open><summary style='cursor:pointer;font-weight:bold;'>点击展开/收起代码</summary>")
            ctx["put_code"](unit._processor_code, language="python")
            ctx["put_html"]("</details>")
        
        ctx["put_markdown"]("### 📤 导出策略配置")
        export_json = json.dumps(unit.to_dict(), ensure_ascii=False, indent=2)
        ctx["put_code"](export_json, language="json")


async def _edit_strategy_dialog(ctx, unit_id: str):
    manager = get_manager()
    unit = manager.get_unit(unit_id)
    
    if not unit:
        ctx["toast"]("策略不存在", color="error")
        return
    
    ds_mgr = get_ds_manager()
    sources = ds_mgr.list_sources()
    source_options = [
        {"label": f"{s['name']}", "value": s['id']}
        for s in sources
    ] if sources else []
    
    with ctx["popup"](f"编辑策略: {unit.name}", size="large", closable=True):
        ctx["put_markdown"]("### 编辑策略配置")
        ctx["put_html"]("<p style='color:#666;font-size:12px;'>可以直接修改代码，也可以点击「AI生成」按钮，由AI根据需求描述自动生成代码</p>")
        
        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("策略名称", name="name", required=True, value=unit.name),
            ctx["textarea"]("描述", name="description", value=unit.metadata.description or "", rows=2),
            ctx["input"]("标签", name="tags", value=", ".join(unit.metadata.tags or [])),
            ctx["input"]("上游数据源", name="upstream", value=unit.lineage.upstream[0].name if unit.lineage.upstream else ""),
            ctx["input"]("下游输出", name="downstream", value=unit.lineage.downstream[0].name if unit.lineage.downstream else ""),
            ctx["textarea"]("处理器代码", name="code", value=unit._processor_code or "", rows=10),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
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
                await _edit_strategy_dialog(ctx, unit_id)
                return
            
            form["code"] = code
        
        result = manager.hot_update(
            unit_id=unit_id,
            code=form.get("code"),
            validate=True,
        )
        
        if result.get("success"):
            unit.metadata.description = form.get("description", "")
            unit.metadata.tags = [t.strip() for t in form.get("tags", "").split(",") if t.strip()]
            unit.save()
            
            ctx["toast"](f"策略更新成功，版本: {result['code_version']}", color="success")
            ctx["close_popup"]()
            ctx["run_js"]("location.reload()")
        else:
            ctx["toast"](f"更新失败: {result.get('error', '')}", color="error")


async def _create_strategy_dialog(ctx):
    ds_mgr = get_ds_manager()
    sources = ds_mgr.list_sources()
    source_options = [
        {"label": f"{s.name}", "value": s.id}
        for s in sources
    ] if sources else []
    
    with ctx["popup"]("创建新策略", size="large", closable=True):
        ctx["put_markdown"]("### 策略配置")
        ctx["put_html"]("<p style='color:#666;font-size:12px;'>可以直接输入代码，也可以点击「AI生成」按钮，由AI根据需求描述自动生成代码</p>")
        
        form = await ctx["input_group"]("策略配置", [
            ctx["input"]("策略名称", name="name", required=True, placeholder="输入策略名称"),
            ctx["textarea"]("描述", name="description", placeholder="策略描述（可选）", rows=2),
            ctx["input"]("标签", name="tags", placeholder="多个标签用逗号分隔"),
            ctx["input"]("上游数据源", name="upstream", placeholder="数据源名称（可选）"),
            ctx["input"]("下游输出", name="downstream", placeholder="输出目标名称（可选）"),
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
        result = manager.create_strategy(
            name=form["name"],
            description=form.get("description", ""),
            tags=[t.strip() for t in form.get("tags", "").split(",") if t.strip()],
            processor_code=form.get("code") or None,
            upstream_source=form.get("upstream") or None,
            downstream_sink=form.get("downstream") or None,
        )
        
        if result.get("success"):
            ctx["toast"](f"策略创建成功: {result['unit_id']}", color="success")
            ctx["run_js"]("location.reload()")
        else:
            ctx["toast"](f"创建失败: {result.get('error', '')}", color="error")


def _start_all_strategies(ctx):
    manager = get_manager()
    result = manager.start_all()
    ctx["toast"](f"启动完成: 成功{result['success']}, 失败{result['failed']}, 跳过{result['skipped']}", color="info")
    ctx["run_js"]("location.reload()")


def _pause_all_strategies(ctx):
    manager = get_manager()
    result = manager.pause_all()
    ctx["toast"](f"暂停完成: 成功{result['success']}, 失败{result['failed']}, 跳过{result['skipped']}", color="info")
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
    
    ctx["put_button"]("打开策略实验室", onclick=lambda: ctx["run_async"](_open_lab_dialog(ctx)))


async def _open_lab_dialog(ctx):
    manager = get_manager()
    units = manager.list_all()
    
    with ctx["popup"]("🧪 策略实验室", size="large", closable=True):
        ctx["put_markdown"]("### 选择策略进行测试")
        
        unit_options = [
            {"label": u.get("metadata", {}).get("name", u.get("metadata", {}).get("id", "unknown")), 
             "value": u.get("metadata", {}).get("id", "")}
            for u in units
        ]
        
        if not unit_options:
            ctx["put_text"]("暂无可测试的策略")
            return
        
        form = await ctx["input_group"]("实验室配置", [
            ctx["select"]("选择策略", name="unit_id", options=unit_options),
            ctx["input"]("测试数据条数", name="limit", type=ctx["NUMBER"], value=10),
            ctx["textarea"]("新策略代码", name="new_code", placeholder="def process(data): ...", rows=8),
            ctx["actions"]("操作", [
                {"label": "开始测试", "value": "test"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])
        
        if not form or form.get("action") == "cancel":
            return
        
        unit = manager.get_unit(form["unit_id"])
        if not unit or not unit._processor_func:
            ctx["toast"]("策略不存在或无处理器", color="error")
            return
        
        lab = get_lab()
        
        test_data = []
        if unit._input_stream and unit._input_stream.is_cache:
            test_data = list(unit._input_stream.recent(form["limit"]))
        
        if not test_data:
            ctx["toast"]("无可用测试数据", color="warning")
            return
        
        ctx["put_markdown"]("### 测试进行中...")
        ctx["set_scope"]("lab_results")
        
        report = lab.test_strategy(
            strategy_name=unit.name,
            original_processor=unit._processor_func,
            new_code=form["new_code"],
            test_data=test_data,
        )
        
        with ctx["use_scope"]("lab_results", clear=True):
            ctx["put_markdown"](report.summary)
            
            ctx["put_markdown"]("### 测试结果详情")
            result_table = [["状态", "输入预览", "新输出预览", "差异说明"]]
            
            for r in report.results[:10]:
                result_table.append([
                    r.status,
                    r._preview(r.input_data, 50),
                    r._preview(r.new_output, 50),
                    r.diff_note[:50] if r.diff_note else "-",
                ])
            
            ctx["put_table"](result_table)
            
            ctx["put_row"]([
                ctx["put_button"]("采纳新策略", onclick=lambda: _adopt_new_logic(ctx, unit.id, form["new_code"]), color="success").style("margin-right: 10px"),
                ctx["put_button"]("放弃更新", onclick=lambda: ctx["close_popup"](), color="danger"),
            ]).style("margin-top: 10px")


def _adopt_new_logic(ctx, unit_id: str, new_code: str):
    manager = get_manager()
    result = manager.hot_update(unit_id, code=new_code, validate=True)
    
    if result.get("success"):
        ctx["toast"](f"策略已更新，版本: {result['code_version']}", color="success")
    else:
        ctx["toast"](f"更新失败: {result.get('error', '')}", color="error")


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
    
    manager = get_manager()
    topology = manager.get_topology()
    
    if topology["nodes"]:
        ctx["put_markdown"]("### 拓扑概览")
        
        node_count = len(topology["nodes"])
        edge_count = len(topology["edges"])
        
        ctx["put_html"](f"""
        <div style="padding:12px;background:#f5f5f5;border-radius:4px;">
            <p>节点数: {node_count} | 连接数: {edge_count}</p>
            <p style="font-size:12px;color:#666;">
                数据源(蓝色) → 策略(绿色) → 下游(橙色)
            </p>
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
#### 策略执行单元

策略执行单元是一个独立的逻辑资产，封装了：
- **元数据**：名称、ID、备注、属性、上下游血缘
- **执行体**：AI生成的Python函数，负责数据转换
- **数据模版**：输入与输出的数据结构定义
- **状态机**：管理生命周期（运行、暂停、归档）

#### 生命周期管理

- **创建策略**：基于数据源和AI生成的代码初始化流
- **策略暂停**：停止处理输入，下游流变为"空数据流"
- **热更新**：动态替换处理器函数，无需重启
- **策略删除**：检查下游影响，提示级联处理

#### 策略实验室

- **数据回放**：从存储中提取历史数据
- **影子测试**：创建隔离沙盒运行新逻辑
- **可视化比对**：并排对比新旧输出
- **合规性检查**：验证Schema兼容性
        """),
    ], open=False)
