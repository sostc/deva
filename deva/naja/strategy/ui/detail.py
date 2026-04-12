"""策略详情与结果详情展示"""

import json
from datetime import datetime

from pywebio.output import use_scope
from pywebio.session import run_async

from deva.naja.register import SR
from deva.naja.infra.ui.ui_style import render_detail_section, format_timestamp
from .diagrams import _render_strategy_diagram_section


def _render_recent_results(ctx, entries, store, limit: int = 10):
    """渲染最近执行结果表格"""
    all_results = []
    for e in entries:
        results = store.get_recent(e.id, limit=5)
        all_results.extend(results)

    all_results.sort(key=lambda x: x.ts, reverse=True)
    all_results = all_results[:limit]

    if not all_results:
        ctx["put_html"](
            '<div style="padding:20px;text-align:center;color:#999;background:#f9f9f9;border-radius:8px;">暂无执行结果</div>')
        return

    table_data = [["时间", "策略名称", "状态", "耗时", "输出预览", "操作"]]

    for r in all_results:
        status_html = '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;background:#e8f5e9;color:#2e7d32;">✅ 成功</span>' if r.success else '<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;background:#ffebee;color:#c62828;">❌ 失败</span>'
        output_preview = r.output_preview[:60] + \
            "..." if len(r.output_preview) > 60 else r.output_preview
        if not r.success and r.error:
            output_preview = f"错误: {r.error[:50]}..."

        actions = ctx["put_buttons"]([
            {"label": "详情", "value": f"detail_{r.id}", "color": "info"},
        ], onclick=lambda v, rid=r.id: _show_result_detail_by_id(ctx, rid), small=True)

        table_data.append([
            r.ts_readable[:16] if hasattr(r, 'ts_readable') else datetime.fromtimestamp(
                r.ts).strftime("%m-%d %H:%M:%S"),
            r.strategy_name[:15],
            ctx["put_html"](status_html),
            f"{r.process_time_ms:.1f}ms",
            output_preview,
            actions,
        ])

    ctx["put_table"](table_data)


def _show_ds_detail_from_strategy(ctx, ds_id: str):
    """从策略页面显示数据源详情"""
    from deva.naja.datasource import get_datasource_manager
    from deva.naja.datasource.ui import _show_ds_detail
    mgr = get_datasource_manager()
    run_async(_show_ds_detail(ctx, mgr, ds_id))


def _show_result_detail_by_id(ctx, result_id: str):
    """根据结果ID显示结果详情"""
    from ..result_store import get_result_store
    store = get_result_store()
    result = store.get_by_id(result_id)

    if not result:
        ctx["toast"]("结果不存在", color="error")
        return

    with ctx["popup"](f"执行结果详情", size="large", closable=True):
        ctx["put_html"](render_detail_section("基本信息"))
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

        ctx["put_html"](render_detail_section("输入数据预览"))
        ctx["put_code"](result.input_preview, language="text")

        if result.success and result.output_full is not None:
            ctx["put_html"](render_detail_section("输出结果"))
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

        # 删除按钮
        ctx["put_html"]("<div style='margin-top:20px;'>")
        ctx["put_buttons"]([
            {"label": "🗑️ 删除此结果", "value": result_id, "color": "danger"},
        ], onclick=lambda v, c=ctx, s=store: _delete_result(c, s, v))
        ctx["put_html"]("</div>")


def _delete_result(ctx, store, result_id: str):
    """删除执行结果"""
    from pywebio.output import clear
    
    try:
        store.delete(result_id)
        ctx["toast"]("删除成功", color="success")
        ctx["close_popup"]()
    except Exception as e:
        ctx["toast"](f"删除失败: {e}", color="error")


def _handle_result_action(ctx, entry, result_id: str, action: str):
    """处理结果操作（详情/删除）"""
    if action.startswith("result_"):
        _show_result_detail(ctx, entry, result_id)
    elif action.startswith("delete_"):
        _delete_result_with_confirm(ctx, entry, result_id)


def _delete_result_with_confirm(ctx, entry, result_id: str):
    """删除执行结果（带确认）"""
    from ..result_store import get_result_store
    from . import get_strategy_manager
    from pywebio.output import clear, use_scope
    
    store = get_result_store()
    
    try:
        store.delete(result_id)
        ctx["toast"]("删除成功", color="success")
        ctx["close_popup"]()
        
        # 刷新信号流
        mgr = get_strategy_manager()
        entries = list(mgr.list_all())
        with use_scope("signal_stream", clear=True):
            _render_signal_stream_content(ctx, entries, store)
    except Exception as e:
        ctx["toast"](f"删除失败: {e}", color="error")


async def _show_strategy_detail(ctx: dict, mgr, entry_id: str):
    """显示策略详情"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("策略不存在", color="error")
        return

    # 获取多数据源绑定列表
    bound_datasource_ids = getattr(entry._metadata, "bound_datasource_ids", [])
    if not bound_datasource_ids:
        # 兼容旧版本单数据源
        bound_ds_id = getattr(entry._metadata, "bound_datasource_id", "")
        if bound_ds_id:
            bound_datasource_ids = [bound_ds_id]

    # 构建数据源名称列表
    if bound_datasource_ids:
        from deva.naja.datasource import get_datasource_manager
        ds_mgr = get_datasource_manager()
        ds_names = []
        for ds_id in bound_datasource_ids:
            ds = ds_mgr.get(ds_id)
            if ds:
                ds_names.append(f"{ds.name} ({ds_id[:8]}...)")
            else:
                ds_names.append(ds_id[:12])
        bound_ds_display = "\n".join([f"• {name}" for name in ds_names]) if ds_names else "-"
    else:
        bound_ds_display = "-"

    with ctx["popup"](f"策略详情: {entry.name}", size="large", closable=True):
        # 计算 state_persist 状态
        state_persist = False
        try:
            cfg = getattr(entry._metadata, "strategy_config", {}) or {}
            state_persist = bool(cfg.get("state_persist", False))
        except Exception:
            state_persist = False
        
        strategy_type = getattr(entry._metadata, "strategy_type", "legacy") or "legacy"
        is_running = entry.is_running
        
        type_colors = {
            "legacy": {"bg": "#f1f5f9", "color": "#64748b"},
            "declarative": {"bg": "#e0f2fe", "color": "#0284c7"},
            "river": {"bg": "#dcfce7", "color": "#16a34a"},
            "plugin": {"bg": "#ede9fe", "color": "#7c3aed"},
            "attention": {"bg": "#fef3c7", "color": "#f59e0b"},
        }
        type_style = type_colors.get(strategy_type, type_colors["legacy"])
        
        # 紧凑顶部栏
        ctx["put_html"](f"""
        <div style="margin-bottom:12px;padding:10px 14px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
            <div style="display:flex;align-items:center;gap:10px;">
                <span style="font-size:16px;font-weight:600;color:#1e293b;">{entry.name}</span>
                <span style="background:{type_style['bg']};color:{type_style['color']};padding:2px 6px;border-radius:4px;font-size:11px;font-weight:500;">{strategy_type.upper()}</span>
                <span style="font-size:11px;color:#64748b;">{getattr(entry._metadata, "compute_mode", "record")}</span>
            </div>
            <div style="display:flex;align-items:center;gap:10px;">
                <span style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;background:{"#dcfce7" if is_running else "#f3f4f6"};color:{"#22c55e" if is_running else "#9ca3af"};border-radius:12px;font-size:11px;font-weight:500;">
                    {"●" if is_running else "○"} {"运行中" if is_running else "已停止"}
                </span>
                <span style="font-size:11px;color:#64748b;">{entry._state.processed_count}次</span>
            </div>
        </div>
        """)
        
        # 紧凑二列布局：基本信息 + 执行统计
        ctx["put_html"]('<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">')

        # 策略元数据概览
        category = getattr(entry._metadata, "category", "-") or "-"
        handler_type = getattr(entry._metadata, "handler_type", "-") or "-"
        window_type = getattr(entry._metadata, "window_type", "-") or "-"
        window_interval = getattr(entry._metadata, "window_interval", "-") or "-"
        version = getattr(entry._metadata, "version", 1)
        tags = getattr(entry._metadata, "tags", []) or []

        # 标签显示
        tags_html = ""
        if tags:
            for tag in tags[:5]:
                tags_html += f'<span style="display:inline-block;padding:1px 6px;background:#f1f5f9;color:#64748b;border-radius:4px;font-size:10px;margin-right:4px;">{tag}</span>'

        handler_icons = {
            "radar": "📡",
            "memory": "🧠",
            "bandit": "🎰",
            "llm": "🤖",
            "attention": "👁️",
        }
        handler_icon = handler_icons.get(handler_type, "📋")
        handler_html = f"{handler_icon} {handler_type}"

        # 左侧：关键信息
        ctx["put_html"](f"""
        <div style="background:#fff;padding:12px;border-radius:8px;border:1px solid #e5e7eb;font-size:11px;">
            <div style="font-weight:600;color:#1e293b;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #e5e7eb;">📋 基本信息</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
                <div><span style="color:#64748b;">类别:</span> <span style="color:#1e293b;">{category}</span></div>
                <div><span style="color:#64748b;">Handler:</span> <span style="color:#1e293b;">{handler_html}</span></div>
                <div><span style="color:#64748b;">窗口:</span> <span style="color:#1e293b;">{getattr(entry._metadata, "window_size", 5)} ({window_type})</span></div>
                <div><span style="color:#64748b;">间隔:</span> <span style="color:#1e293b;">{window_interval}</span></div>
                <div><span style="color:#64748b;">持久化:</span> <span style="color:{"#22c55e" if state_persist else "#9ca3af"};">{"开" if state_persist else "关"}</span></div>
                <div><span style="color:#64748b;">版本:</span> <span style="color:#1e293b;">v{version}</span></div>
            </div>
            {f'<div style="margin-top:8px;padding-top:6px;border-top:1px solid #e5e7eb;"><span style="color:#64748b;">标签:</span> {tags_html}</div>' if tags_html else ''}
        </div>
        """)

        func_code_file = _get_strategy_func_code_file(entry)
        if func_code_file:
            ctx["put_html"](f'''
            <div style="background:#fff;padding:12px;border-radius:8px;border:1px solid #e5e7eb;font-size:11px;margin-bottom:12px;">
                <div style="font-weight:600;color:#1e293b;margin-bottom:6px;">📁 代码文件</div>
                <div style="color:#1e293b;word-break:break-all;">{func_code_file}</div>
            </div>
            ''')

        handler_labels = {
            "radar": "📡 Radar雷达 → 信号检测异常检测",
            "memory": "🧠 Memory记忆 → 主题聚类语义分析",
            "bandit": "🎰 Bandit交易 → 交易信号仓位管理",
            "llm": "🤖 LLM调节 → 参数优化策略调优",
            "attention": "👁️ Attention注意 → 注意力评分",
        }
        handler_desc = handler_labels.get(handler_type, "")
        if handler_desc:
            ctx["put_html"](f'''
            <div style="background:#fff;padding:12px;border-radius:8px;border:1px solid #e5e7eb;font-size:11px;margin-bottom:12px;">
                <div style="font-weight:600;color:#1e293b;margin-bottom:6px;">📤 输出目标 (消费)</div>
                <div style="color:#1e293b;">{handler_desc}</div>
            </div>
            ''')

        # 错误信息 + 最新正确信息并排显示
        try:
            recent_results = entry.get_recent_results(limit=2)
            has_error = entry._state.error_count > 0 and entry._state.last_error
            has_success = any(r.get("success") for r in recent_results if r.get("success"))
            
            if has_error or has_success:
                ctx["put_html"]('<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;">')
                
                # 错误信息 - 红色背景
                if has_error and entry._state.last_error:
                    ctx["put_html"](f'''
                    <div style="padding:8px;background:#fef2f2;border-radius:6px;border:1px solid #fecaca;">
                        <div style="font-size:10px;font-weight:600;color:#dc2626;margin-bottom:4px;">❌ 最新错误</div>
                        <div style="font-size:10px;color:#991b1b;">{entry._state.last_error or ""}</div>
                        <div style="font-size:9px;color:#f87171;margin-top:4px;">{format_timestamp(entry._state.last_error_ts) if entry._state.last_error_ts > 0 else ""}</div>
                    </div>
                    ''')
                
                # 最新正确信息 - 绿色背景
                success_result = next((r for r in recent_results if r.get("success")), None)
                if success_result:
                    ctx["put_html"](f'''
                    <div style="padding:8px;background:#f0fdf4;border-radius:6px;border:1px solid #bbf7d0;">
                        <div style="font-size:10px;font-weight:600;color:#16a34a;margin-bottom:4px;">✅ 最新成功</div>
                        <div style="font-size:10px;color:#166534;">{(success_result.get("output_preview") or "-")[:60]}</div>
                        <div style="font-size:9px;color:#4ade80;margin-top:4px;">{success_result.get("ts_readable", "")[:19] if success_result.get("ts_readable") else ""}</div>
                    </div>
                    ''')
                
                ctx["put_html"]('</div>')
        except Exception:
            pass
        
        # 执行统计
        ctx["put_html"](f"""
        <div style="background:#fff;padding:12px;border-radius:8px;border:1px solid #e5e7eb;font-size:11px;">
            <div style="font-weight:600;color:#1e293b;margin-bottom:6px;">📊 执行统计</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
                <div><span style="color:#64748b;">输出:</span> <span style="color:#1e293b;">{entry._state.output_count}</span></div>
                <div><span style="color:#64748b;">错误:</span> <span style="color:{"#ef4444" if entry._state.error_count > 0 else "#1e293b"};">{entry._state.error_count}</span></div>
                <div><span style="color:#64748b;">历史:</span> <span style="color:#1e293b;">{getattr(entry._metadata, "max_history_count", 100)}</span></div>
                <div><span style="color:#64748b;">最后:</span> <span style="color:#1e293b;">{format_timestamp(entry._state.last_process_ts) if entry._state.last_process_ts > 0 else "-"}</span></div>
            </div>
        </div>
        """)

        # 右侧：数据源
        ctx["put_html"](f"""
        <div style="background:#fff;padding:12px;border-radius:8px;border:1px solid #e5e7eb;font-size:11px;">
            <div style="font-weight:600;color:#1e293b;margin-bottom:6px;">🔗 数据源</div>
            <div style="color:#64748b;line-height:1.6;">{bound_ds_display.replace(chr(10), '<br>').replace('• ', '• ') if bound_ds_display != '-' else '<span style="color:#9ca3af;">未绑定</span>'}</div>
        </div>
        """)
        ctx["put_html"]('</div>')
        
        dict_ids = getattr(entry._metadata, "dictionary_profile_ids", [])
        if dict_ids:
            ctx["put_html"](f'<div style="margin-bottom:12px;font-size:11px;"><span style="color:#64748b;">📖 字典:</span> <span style="color:#1e293b;">{", ".join(dict_ids)}</span></div>')

        # 注意力策略特有信息
        if strategy_type == "attention":
            attention_scope = getattr(entry, 'scope', getattr(entry._metadata, 'scope', '-'))
            try:
                attn_stats = entry.get_attention_stats() if hasattr(entry, 'get_attention_stats') else {}
            except Exception:
                attn_stats = {}
            exec_count = attn_stats.get('execution_count', 0)
            skip_count = attn_stats.get('skip_count', 0)
            signal_count = attn_stats.get('signal_count', 0)
            scope = attn_stats.get('scope', attention_scope)

            priority = "-"
            try:
                from deva.naja.market_hotspot.strategies import get_strategy_manager as get_attn_mgr
                attn_mgr = get_attn_mgr()
                config = attn_mgr.configs.get(entry.id)
                if config:
                    priority = config.priority
            except Exception:
                pass

            ctx["put_html"](f"""
            <div style="margin-bottom:12px;padding:12px;background:linear-gradient(135deg, #fef3c7, #fde68a);border-radius:8px;border:1px solid #f59e0b;">
                <div style="font-weight:600;color:#92400e;margin-bottom:8px;">👁️ 注意力策略信息</div>
                <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:11px;">
                    <div style="background:#fff;border-radius:4px;padding:6px 8px;">
                        <div style="color:#64748b;">Scope</div>
                        <div style="color:#1e293b;font-weight:600;">{scope}</div>
                    </div>
                    <div style="background:#fff;border-radius:4px;padding:6px 8px;">
                        <div style="color:#64748b;">执行次数</div>
                        <div style="color:#1e293b;font-weight:600;">{exec_count}</div>
                    </div>
                    <div style="background:#fff;border-radius:4px;padding:6px 8px;">
                        <div style="color:#64748b;">跳过次数</div>
                        <div style="color:#1e293b;font-weight:600;">{skip_count}</div>
                    </div>
                    <div style="background:#fff;border-radius:4px;padding:6px 8px;">
                        <div style="color:#64748b;">信号数量</div>
                        <div style="color:#1e293b;font-weight:600;">{signal_count}</div>
                    </div>
                    <div style="background:#fff;border-radius:4px;padding:6px 8px;">
                        <div style="color:#64748b;">优先级</div>
                        <div style="color:#1e293b;font-weight:600;">{priority}</div>
                    </div>
                    <div style="background:#fff;border-radius:4px;padding:6px 8px;">
                        <div style="color:#64748b;">活跃状态</div>
                        <div style="color:{'#22c55e' if attn_stats.get('is_active') else '#9ca3af'};font-weight:600;">{'● 运行中' if attn_stats.get('is_active') else '○ 已停止'}</div>
                    </div>
                </div>
            </div>
            """)

        # AI调节历史 - 提前到更前面
        try:
            llm_rows = _get_llm_adjustments(entry, limit=5)
            if llm_rows:
                ctx["put_html"]('<div style="margin-top:12px;">')
                ctx["put_collapse"](f"🤖 AI调节 ({len(llm_rows)}条)", [
                    ctx["put_table"](llm_rows, header=["时间", "摘要", "动作"])
                ])
                ctx["put_html"]('</div>')
        except Exception:
            pass

        # 策略详解 - 直接调用（内部已处理空数据情况）
        _render_strategy_diagram_section(ctx, entry)

        # 代码区块 - 折叠显示
        strategy_config = getattr(entry._metadata, "strategy_config", {}) or {}
        display_code = entry.func_code
        if not display_code and strategy_type in ("declarative", "river", "plugin"):
            logic_config = strategy_config.get("logic", {})
            display_code = logic_config.get("code", "")
        
        code_char_count = len(display_code) if display_code else 0
        ctx["put_collapse"](f"💻 代码 {f'({strategy_type.upper()})' if strategy_type != 'legacy' else ''} [{code_char_count}字符]", [
            ctx["put_code"](display_code[:2000], language="python") if display_code else ctx["put_html"]('<div style="color:#9ca3af;font-size:11px;">暂无代码</div>')
        ])

        # 配置折叠
        config = getattr(entry._metadata, "strategy_config", {}) or {}
        params = getattr(entry._metadata, "strategy_params", {}) or {}
        if params:
            config = dict(config)
            config["params"] = {**(config.get("params", {}) or {}), **params}
        
        if config:
            ctx["put_collapse"](f"🧩 配置 ({len(json.dumps(config))//512 + 1}KB)", [
                ctx["put_code"](json.dumps(config, ensure_ascii=False, indent=2), language="json")
            ])

        # 执行结果 - 紧凑
        try:
            recent_results = entry.get_recent_results(limit=5)
            if recent_results:
                ctx["put_html"]('<div style="margin-top:12px;">')
                ctx["put_html"]('<div style="font-size:12px;font-weight:600;color:#1e293b;margin-bottom:8px;">📜 最近结果</div>')
                result_table = [["时间", "状态", "耗时", "预览"]]
                for r in recent_results:
                    status = "✅" if r.get("success") else "❌"
                    preview = (r.get("output_preview", "") or r.get("error", ""))[:30]
                    result_table.append([
                        r.get("ts_readable", "")[:12] if r.get("ts_readable") else "-",
                        status,
                        f"{r.get('process_time_ms', 0):.0f}ms",
                        preview + "..." if len(preview) >= 30 else preview
                    ])
                ctx["put_table"](result_table)
                ctx["put_html"]('</div>')
        except Exception:
            pass

        # 操作按钮
        ctx["put_html"]("<div style='margin-top:16px;text-align:center;'>")
        ctx["put_buttons"]([
            {"label": "🗑️ 删除", "value": f"delete_{entry.id}", "color": "danger"},
        ], onclick=lambda v, m=mgr, c=ctx: _handle_strategy_action(v, m, c))
        ctx["put_html"]("</div>")



def _show_result_detail(ctx: dict, entry, result_id: str):
    """显示执行结果详情"""
    from ..result_store import get_result_store
    store = get_result_store()
    result = store.get_by_id(result_id)

    if not result:
        ctx["toast"]("结果不存在", color="error")
        return

    with ctx["popup"](f"执行结果详情", size="large", closable=True):
        ctx["put_html"](render_detail_section("基本信息"))
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

        ctx["put_html"](render_detail_section("输入数据预览"))
        ctx["put_code"](result.input_preview, language="text")

        if result.success and result.output_full is not None:
            ctx["put_html"](render_detail_section("输出结果"))
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


def _get_llm_adjustments(entry, limit: int = 10):
    """获取与该策略相关的 LLM 调节历史"""
    try:
        from deva import NB
        db = NB("naja_llm_decisions")
        items = []
        for _, value in list(db.items()):
            if not isinstance(value, dict):
                continue
            actions = value.get("actions", []) or []
            matched_actions = []
            for action in actions:
                if not isinstance(action, dict):
                    continue
                target = str(action.get("strategy", "") or "")
                if target == entry.id or target == entry.name:
                    matched_actions.append(action)
            if matched_actions:
                items.append((value, matched_actions))

        items.sort(key=lambda x: float(x[0].get("timestamp", 0) or 0), reverse=True)
        rows = []
        for value, acts in items[:limit]:
            ts = format_timestamp(float(value.get("timestamp", 0) or 0))
            summary = value.get("summary", "") or "-"
            reason = value.get("reason", "") or "-"
            act_texts = []
            for a in acts:
                act_texts.append(f"{a.get('action', '')}({a.get('strategy', '')})")
            rows.append([ts, summary, "; ".join(act_texts), reason])
        return rows
    except Exception:
        return []
