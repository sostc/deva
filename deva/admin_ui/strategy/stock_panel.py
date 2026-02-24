"""Stock admin page with runtime switches and data management."""

from __future__ import annotations

FLOW_CHART_HTML = """
<pre style="font-size: 11px; line-height: 1.4; background: #f8f9fa; padding: 12px; border-radius: 6px; overflow-x: auto;">
<b>【数据流】</b>
gen_quant() / 历史数据 → DataSourceManager → quant stream
                                            ↓
                    ┌───────────┬───────────┬───────────┐
                    ↓           ↓           ↓           ↓
                Bus同步    板块异动计算   领涨领跌     涨跌停
                    ↓           ↓           ↓           ↓
                NS("bus")  NS("板块异动") NS("领涨领跌") NS("涨跌停")

<b>【回放流程】</b>
开启自动保存 → 行情自动存入DBStream → 点击Tick回放 → 数据推送到stream → 下游自动计算

<b>【数据处理】</b>
_prepare_df: 选择列 → 添加元数据 → 展开板块(军工|安防 → 两行)
_calc_block_ranking: 排序 → 每板块取前N只 → 计算平均涨幅 → TOP10
</pre>
"""


async def render_stock_admin_page(ctx):
    await ctx["init_admin_ui"]("Deva股票管理")

    def refresh_all_status():
        cfg = ctx["get_strategy_config"]()
        meta = ctx["get_strategy_basic_meta"]()
        replay_cfg = ctx["get_replay_config"]()
        auto_save_cfg = ctx["get_auto_save_config"]()
        tick_meta = ctx["get_tick_metadata"]()
        history_meta = ctx["get_history_metadata"]()
        
        updated_at = meta.get("updated_at", 0)
        updated_at_text = "-"
        if updated_at:
            import datetime
            updated_at_text = datetime.datetime.fromtimestamp(float(updated_at)).strftime("%Y-%m-%d %H:%M:%S")
        
        is_replaying = ctx["is_replay_running"]()
        auto_save_status = "✅ 已开启" if auto_save_cfg.get("enabled") else "❌ 已关闭"
        force_fetch_status = "✅ 强制抓取" if cfg["force_fetch"] else "❌ 仅交易日"
        bus_status = "✅ 已开启" if cfg["sync_bus"] else "❌ 已关闭"
        replay_status = f"🔄 正在回放 {replay_cfg.get('replay_date', '')}" if is_replaying else "⏹️ 空闲"
        
        with ctx["use_scope"]("status_table", clear=True):
            ctx["put_table"]([
                ["功能", "状态", "操作"],
                ["行情抓取", force_fetch_status, ctx["put_buttons"](["切换"], onclick=lambda _: toggle_force_fetch())],
                ["Bus同步", bus_status, ctx["put_buttons"](["切换"], onclick=lambda _: toggle_sync_bus())],
                ["自动保存", auto_save_status, ctx["put_buttons"](["切换"], onclick=lambda _: toggle_auto_save())],
                ["回放状态", replay_status, ctx["put_buttons"](["停止"], onclick=lambda _: stop_replay()) if is_replaying else "-"],
                ["历史快照数", str(tick_meta.get("total_ticks", 0)), "-"],
                ["板块数据更新", updated_at_text, ctx["put_buttons"](["更新"], onclick=lambda _: refresh_blockname())],
            ])

    def toggle_force_fetch():
        cfg = ctx["get_strategy_config"]()
        ctx["set_strategy_config"](force_fetch=not cfg["force_fetch"])
        ctx["toast"]("已切换行情抓取模式", color="success")
        refresh_all_status()

    def toggle_sync_bus():
        cfg = ctx["get_strategy_config"]()
        ctx["set_strategy_config"](sync_bus=not cfg["sync_bus"])
        ctx["toast"]("已切换Bus同步", color="success")
        refresh_all_status()

    def toggle_auto_save():
        cfg = ctx["get_auto_save_config"]()
        ctx["set_auto_save"](not cfg.get("enabled", False))
        ctx["toast"]("已切换自动保存", color="success")
        refresh_all_status()

    def refresh_blockname():
        async def _do_refresh():
            await ctx["refresh_strategy_basic_df_async"](force=True)
            ctx["toast"]("板块数据已更新", color="success")
            refresh_all_status()
        ctx["run_async"](_do_refresh())

    def stop_replay():
        result = ctx["stop_history_replay"]()
        if result.get("success"):
            ctx["toast"]("已停止回放", color="success")
        else:
            ctx["toast"](f"停止失败: {result.get('error')}", color="error")
        refresh_all_status()

    def select_replay_date(date_str):
        ctx["set_replay_config"](replay_date=date_str)
        ctx["toast"](f"已选择: {date_str}", color="info")
        refresh_all_status()

    def start_replay():
        replay_cfg = ctx["get_replay_config"]()
        date_str = replay_cfg.get("replay_date")
        if not date_str:
            ctx["toast"]("请先选择日期", color="warning")
            return
        result = ctx["start_history_replay"](date_str=date_str, interval=3.0, use_ticks=False)
        if result.get("success"):
            ctx["toast"](f"开始回放: {date_str}", color="success")
        else:
            ctx["toast"](f"启动失败: {result.get('error')}", color="error")
        refresh_all_status()

    def start_tick_replay():
        result = ctx["start_history_replay"](interval=3.0, use_ticks=True)
        if result.get("success"):
            ctx["toast"]("开始Tick回放", color="success")
        else:
            ctx["toast"](f"启动失败: {result.get('error')}", color="error")
        refresh_all_status()

    def save_snapshot():
        result = ctx["save_current_quant_to_history"]()
        if result.get("success"):
            ctx["toast"](f"已保存: {result.get('date')} ({result.get('rows')}行)", color="success")
        else:
            ctx["toast"](f"保存失败: {result.get('error')}", color="error")
        refresh_all_status()

    ctx["put_collapse"]("📊 数据流程图", [ctx["put_html"](FLOW_CHART_HTML)], open=False)
    
    ctx["put_markdown"]("### 状态控制")
    ctx["set_scope"]("status_table")
    refresh_all_status()

    ctx["put_markdown"]("### 历史数据回放")
    history_meta = ctx["get_history_metadata"]()
    available_dates = history_meta.get("dates", [])
    if available_dates:
        ctx["put_text"]("选择日期:")
        date_buttons = [(d, d) for d in available_dates[:10]]
        ctx["put_buttons"](date_buttons, onclick=select_replay_date)
        if len(available_dates) > 10:
            ctx["put_text"](f"... 共{len(available_dates)}天")
    
    ctx["put_row"]([
        ctx["put_button"]("回放选中日期", onclick=start_replay, color="success").style("margin-right: 10px"),
        ctx["put_button"]("Tick回放", onclick=start_tick_replay, color="info").style("margin-right: 10px"),
        ctx["put_button"]("保存当前快照", onclick=save_snapshot),
    ]).style("display: flex; justify-content: flex-start; align-items: center")

    ctx["put_markdown"]("### 监控流")
    stream_names = ["涨跌停", "领涨领跌板块", "1分钟板块异动", "30秒板块异动"]
    for name in stream_names:
        stream = ctx["NS"](name)
        ctx["put_html"](f'<details><summary>{name}</summary><iframe src="/{hash(stream)}" style="width:100%;height:240px;border:none;"></iframe></details>')


render_stock_admin = render_stock_admin_page
