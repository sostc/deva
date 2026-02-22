"""Stock admin page with runtime switches."""

from __future__ import annotations


async def render_stock_admin_page(ctx):
    await ctx["init_admin_ui"]("Deva股票监控")

    def refresh_status():
        cfg = ctx["get_stock_config"]()
        meta = ctx["get_stock_basic_meta"]()
        fetch_mode = "强制抓取(忽略交易日判断)" if cfg["force_fetch"] else "仅交易日抓取"
        bus_mode = "开启" if cfg["sync_bus"] else "关闭"
        updated_at = meta.get("updated_at", 0)
        updated_at_text = "-"
        if updated_at:
            import datetime
            updated_at_text = datetime.datetime.fromtimestamp(float(updated_at)).strftime("%Y-%m-%d %H:%M:%S")
        with ctx["use_scope"]("stock_status", clear=True):
            ctx["put_table"]([
                ["配置项", "当前状态"],
                ["行情抓取模式", fetch_mode],
                ["行情同步到Bus", bus_mode],
                ["blockname数据来源", str(meta.get("source", "unknown"))],
                ["blockname记录数", str(meta.get("rows", 0))],
                ["blockname最近更新时间", updated_at_text],
            ])

    def set_force_fetch(flag):
        ctx["set_stock_config"](force_fetch=flag)
        ctx["toast"]("已更新行情抓取模式", color="success")
        refresh_status()

    def set_sync_bus(flag):
        ctx["set_stock_config"](sync_bus=flag)
        ctx["toast"]("已更新Bus同步开关", color="success")
        refresh_status()

    def refresh_blockname():
        async def _do_refresh():
            await ctx["refresh_stock_basic_df_async"](force=True)
            ctx["toast"]("已触发板块数据更新", color="success")
            refresh_status()

        ctx["run_async"](_do_refresh())

    ctx["put_markdown"]("### 股票监控开关")
    ctx["put_row"]([
        ctx["put_button"]("开启强制抓取", onclick=lambda: set_force_fetch(True)).style("margin-right: 10px"),
        ctx["put_button"]("关闭强制抓取(按交易日)", onclick=lambda: set_force_fetch(False)),
    ]).style("display: flex; justify-content: flex-start; align-items: center")

    ctx["put_row"]([
        ctx["put_button"]("开启Bus同步", onclick=lambda: set_sync_bus(True)).style("margin-right: 10px"),
        ctx["put_button"]("关闭Bus同步", onclick=lambda: set_sync_bus(False), color="warning"),
    ]).style("display: flex; justify-content: flex-start; align-items: center")

    ctx["set_scope"]("stock_status")
    refresh_status()

    ctx["put_row"]([
        ctx["put_button"]("立即更新板块数据", onclick=refresh_blockname),
    ]).style("display: flex; justify-content: flex-start; align-items: center")

    ctx["put_markdown"]("### 股票监控流")
    stream_names = ["实时新闻", "涨跌停", "领涨领跌板块", "1分钟板块异动", "30秒板块异动"]
    for name in stream_names:
        stream = ctx["NS"](name)
        ctx["put_markdown"](f"#### {name}")
        ctx["put_html"](f'<iframe src="/{hash(stream)}" style="width:100%;height:260px;border:1px solid #ddd;border-radius:6px;"></iframe>')


# Compatibility alias
render_stock_admin = render_stock_admin_page
