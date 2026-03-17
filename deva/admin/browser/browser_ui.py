"""Browser UI module for managing browser tabs and bookmarks."""

from __future__ import annotations

import re


async def render_browser_ui(ctx):
    await ctx["init_admin_ui"]("Deva 浏览器管理")
    ctx["init_floating_menu_manager"](ctx)
    ctx["set_table_style"]()
    ctx["apply_global_styles"]()

    ctx["put_html"]('<div class="card"><div class="card-title">🌐 浏览器</div>')
    with ctx["put_collapse"]("📚 书签管理", open=False):
        bookmarks = ctx["NB"]("bookmarks").items()
        bookmark_table = [["键", "值", "操作"]]
        for key, value in bookmarks:
            actions = ctx["put_buttons"](
                [{"label": "🔗 打开", "value": "open"}, {"label": "🗑 删除", "value": "delete"}],
                onclick=lambda v, k=key, val=value: (ctx["tab"](val), ctx["toast"](f"正在打开书签: {k}"), ctx["run_async"](ctx["show_browser_status"]())) if v == "open" else delete_bookmark(k),
            )
            bookmark_table.append([ctx["truncate"](key), ctx["truncate"](value, 50), actions])
        ctx["put_table"](bookmark_table)

        def open_all_bookmarks():
            for _, value in ctx["NB"]("bookmarks").items():
                ctx["tab"](value)
            ctx["toast"]("正在后台打开所有书签...")
            ctx["run_async"](ctx["show_browser_status"]())

        def delete_bookmark(key):
            ctx["NB"]("bookmarks").delete(key)
            ctx["toast"](f"已删除书签: {key}")
            ctx["run_js"]("window.location.reload()")

        ctx["put_html"]('<div class="btn-group">')
        ctx["put_button"]("📖 一键打开所有书签", onclick=open_all_bookmarks)
        ctx["put_button"]("➕ 新建书签", onclick=lambda: ctx["edit_data_popup"](ctx["NB"]("bookmarks").items() | ctx["ls"], "bookmarks"))
        ctx["put_html"]('</div>')

    ctx["set_scope"]("browser_status")
    ctx["put_html"]('<div class="btn-group">')
    ctx["put_button"]("➕ 新建标签页", onclick=ctx["open_new_tab"])
    ctx["put_button"]("📖 拓展阅读", onclick=lambda: (ctx["extended_reading"](), ctx["run_async"](ctx["show_browser_status"]())))
    ctx["put_button"]("📝 总结", onclick=ctx["summarize_tabs"])
    ctx["put_button"]("🗑 关闭所有", onclick=lambda: ctx["run_async"](ctx["close_all_tabs"]()), color="danger")
    ctx["put_html"]('</div>')
    ctx["run_async"](ctx["show_browser_status"]())
    ctx["put_html"]('</div>')

    ctx["put_html"]('<div class="card"><div class="card-title">📋 系统日志</div>')
    ctx["log"].sse("/logsse")
    with ctx["put_collapse"]("实时日志", open=True):
        ctx["put_logbox"]("log", height=150)
    ctx["run_js"](ctx["sse_js"])

    with ctx["put_collapse"]("🔧 调试工具", open=False):
        ctx["put_html"]('<div style="display:flex;gap:10px;align-items:center;">')
        ctx["put_input"]("write_to_log", type="text", value="", placeholder="手动写入日志内容...")
        ctx["put_button"]("📤 发送", onclick=ctx["write_to_log"])
        ctx["put_html"]('</div>')
    ctx["put_html"]('</div>')
