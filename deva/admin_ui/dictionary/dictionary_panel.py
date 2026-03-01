"""Data Dictionary admin panel."""

from __future__ import annotations

import json
from datetime import datetime

from .dictionary_service import get_dictionary_manager


DEFAULT_STOCK_BLOCK_CODE = '''def fetch_data():
    """更新股票基础信息（含板块字段）"""
    import pandas as pd
    from deva import NB
    from deva.admin_ui.strategy.data import build_market_universe_dataframe

    df = build_market_universe_dataframe()
    df = df[["code", "name", "industry", "blockname"]].copy()
    df["code"] = df["code"].astype(str)

    # 可选：同步给策略既有依赖表
    NB("naja")["basic_df"] = df
    return df
'''


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "-"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def _schedule_label(entry) -> str:
    if entry.schedule_type == "daily":
        return f"每日 {entry.daily_time}"
    return f"每 {entry.interval_seconds} 秒"


async def render_dictionary_admin(ctx):
    await ctx["init_admin_ui"]("Deva数据字典")

    mgr = get_dictionary_manager()
    if not mgr.list_entries():
        mgr.load_from_db()

    ctx["put_markdown"]("### 📚 数据字典")
    ctx["put_html"]("<p style='color:#666'>管理用于策略补齐的基础数据条目，支持代码更新与定时刷新。</p>")

    _render_stats(ctx, mgr)
    _render_toolbar(ctx)
    _render_table(ctx, mgr)


def _render_stats(ctx, mgr):
    s = mgr.get_stats()
    html = f"""
    <div style='display:flex;gap:12px;margin:12px 0 18px 0;'>
      <div style='flex:1;background:#fff;padding:14px;border-radius:8px;border:1px solid #eee;'>
        <div style='font-size:12px;color:#666;'>字典条目</div><div style='font-size:24px;font-weight:700;'>{s['total']}</div>
      </div>
      <div style='flex:1;background:#fff;padding:14px;border-radius:8px;border:1px solid #eee;'>
        <div style='font-size:12px;color:#666;'>运行中</div><div style='font-size:24px;font-weight:700;color:#0a7f3f;'>{s['running']}</div>
      </div>
      <div style='flex:1;background:#fff;padding:14px;border-radius:8px;border:1px solid #eee;'>
        <div style='font-size:12px;color:#666;'>健康</div><div style='font-size:24px;font-weight:700;color:#1b6fd1;'>{s['healthy']}</div>
      </div>
      <div style='flex:1;background:#fff;padding:14px;border-radius:8px;border:1px solid #eee;'>
        <div style='font-size:12px;color:#666;'>异常</div><div style='font-size:24px;font-weight:700;color:#d33f2f;'>{s['error']}</div>
      </div>
    </div>
    """
    ctx["put_html"](html)


def _render_toolbar(ctx):
    ctx["put_row"]([
        ctx["put_button"]("新建字典条目", onclick=lambda: ctx["run_async"](_upsert_dialog(ctx, None)), color="primary"),
        ctx["put_button"]("刷新列表", onclick=lambda: ctx["run_js"]("location.reload()")),
    ]).style("margin-bottom: 10px")


def _render_table(ctx, mgr):
    entries = mgr.list_entries()
    if not entries:
        ctx["put_html"]("<div style='padding:16px;border:1px dashed #ccc;border-radius:8px;color:#666;'>暂无数据字典条目</div>")
        return

    rows = [["名称", "类型", "状态", "大小", "最后更新时间", "更新频率", "操作"]]
    for e in entries:
        status = "运行中" if e.enabled else "已停止"
        status_color = "#0a7f3f" if e.enabled else "#666"
        if e.last_status == "running":
            status = "执行中"
            status_color = "#1b6fd1"
        if e.last_status == "error":
            status = "异常"
            status_color = "#d33f2f"

        actions = ctx["put_buttons"](
            [
                {"label": "详情", "value": f"detail_{e.id}"},
                {"label": "编辑", "value": f"edit_{e.id}"},
                {"label": "执行", "value": f"run_{e.id}"},
                {"label": "清空数据", "value": f"clear_{e.id}"},
                {"label": "停止" if e.enabled else "启动", "value": f"toggle_{e.id}"},
                {"label": "删除", "value": f"delete_{e.id}"},
            ],
            onclick=lambda v, eid=e.id: _handle_action(ctx, v, eid),
        )
        rows.append([
            e.name,
            e.dict_type,
            ctx["put_html"](f"<span style='color:{status_color};font-weight:600'>{status}</span>"),
            _fmt_size(e.data_size_bytes),
            _fmt_ts(e.last_update_ts),
            _schedule_label(e),
            actions,
        ])

    ctx["put_table"](rows)


def _handle_action(ctx, action_value: str, entry_id: str):
    action = action_value.split("_", 1)[0]
    mgr = get_dictionary_manager()
    entry = mgr.get_entry(entry_id)
    if not entry:
        ctx["toast"]("条目不存在", color="error")
        return

    if action == "detail":
        ctx["run_async"](_detail_dialog(ctx, entry_id))
        return
    if action == "edit":
        ctx["run_async"](_upsert_dialog(ctx, entry_id))
        return
    if action == "run":
        ret = mgr.run_once_async(entry_id)
        if ret.get("success"):
            ctx["toast"]("已提交异步执行任务", color="success")
        else:
            ctx["toast"](f"执行失败: {ret.get('error', '')}", color="error")
        ctx["run_js"]("location.reload()")
        return
    if action == "clear":
        ret = mgr.clear_payload(entry_id)
        if ret.get("success"):
            ctx["toast"](f"已清空数据（删除 {ret.get('removed', 0)} 条）", color="warning")
        else:
            ctx["toast"](f"清空失败: {ret.get('error', '')}", color="error")
        ctx["run_js"]("location.reload()")
        return
    if action == "toggle":
        if entry.enabled:
            mgr.stop(entry_id)
            ctx["toast"]("已停止", color="warning")
        else:
            mgr.start(entry_id)
            ctx["toast"]("已启动", color="success")
        ctx["run_js"]("location.reload()")
        return
    if action == "delete":
        mgr.delete(entry_id)
        ctx["toast"]("已删除", color="warning")
        ctx["run_js"]("location.reload()")


async def _detail_dialog(ctx, entry_id: str):
    mgr = get_dictionary_manager()
    entry = mgr.get_entry(entry_id)
    if not entry:
        ctx["toast"]("条目不存在", color="error")
        return

    payload = mgr.get_latest_payload(entry)

    with ctx["popup"](f"数据字典详情: {entry.name}", size="large", closable=True):
        info = [
            ["字段", "值"],
            ["名称", entry.name],
            ["类型", entry.dict_type],
            ["描述", entry.description or "-"],
            ["状态", entry.last_status],
            ["更新频率", _schedule_label(entry)],
            ["最后更新时间", _fmt_ts(entry.last_update_ts)],
            ["数据大小", _fmt_size(entry.data_size_bytes)],
            ["运行次数", str(entry.run_count)],
            ["最后错误", entry.last_error or "-"],
        ]
        ctx["put_table"](info)

        ctx["put_markdown"]("#### 最新数据样例")
        if payload is None:
            ctx["put_text"]("暂无数据")
        else:
            try:
                import pandas as pd
                if isinstance(payload, pd.DataFrame):
                    ctx["put_html"](payload.head(20).to_html(index=False))
                else:
                    ctx["put_code"](json.dumps(payload, ensure_ascii=False, default=str, indent=2), language="json")
            except Exception:
                ctx["put_text"](str(payload)[:2000])

        ctx["put_markdown"]("#### 更新代码")
        ctx["put_code"](entry.code or "", language="python")


async def _upsert_dialog(ctx, entry_id: str | None):
    mgr = get_dictionary_manager()
    entry = mgr.get_entry(entry_id) if entry_id else None

    with ctx["popup"]("编辑数据字典条目" if entry else "新建数据字典条目", size="large", closable=True):
        form = await ctx["input_group"]("字典条目", [
            ctx["input"]("名称", name="name", required=True, value=entry.name if entry else "stock_basic_with_block"),
            ctx["select"]("字典类型", name="dict_type", options=[
                {"label": "股票基础信息(含板块)", "value": "stock_basic_block"},
                {"label": "行业映射", "value": "industry_mapping"},
                {"label": "自定义", "value": "custom"},
            ], value=entry.dict_type if entry else "stock_basic_block"),
            ctx["input"]("描述", name="description", value=entry.description if entry else "用于策略补齐 blockname / industry 的股票基础维表"),
            ctx["select"]("更新模式", name="schedule_type", options=[
                {"label": "按间隔(秒)", "value": "interval"},
                {"label": "按每日时间", "value": "daily"},
            ], value=entry.schedule_type if entry else "interval"),
            ctx["input"]("间隔秒数", name="interval_seconds", type="number", min=5, value=entry.interval_seconds if entry else 300),
            ctx["input"]("每日执行时间", name="daily_time", value=entry.daily_time if entry else "03:00", placeholder="HH:MM"),
            ctx["input"]("保留版本数", name="retention", type="number", min=1, value=entry.retention if entry else 1),
            ctx["select"]("保存后状态", name="enabled", options=[
                {"label": "启用", "value": "true"},
                {"label": "停用", "value": "false"},
            ], value="true" if (entry.enabled if entry else True) else "false"),
            ctx["textarea"]("更新代码", name="code", rows=16, code={"mode": "python", "theme": "darcula"}, value=entry.code if entry else DEFAULT_STOCK_BLOCK_CODE),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])

        if not form or form.get("action") != "save":
            return

        try:
            mgr.upsert(
                entry_id=entry_id,
                name=form.get("name", "").strip(),
                dict_type=form.get("dict_type", "custom"),
                description=form.get("description", "").strip(),
                schedule_type=form.get("schedule_type", "interval"),
                interval_seconds=int(form.get("interval_seconds", 300) or 300),
                daily_time=(form.get("daily_time", "03:00") or "03:00").strip(),
                enabled=str(form.get("enabled", "true")).lower() == "true",
                code=form.get("code", ""),
                retention=int(form.get("retention", 1) or 1),
            )
            ctx["toast"]("保存成功", color="success")
            ctx["close_popup"]()
            ctx["run_js"]("location.reload()")
        except Exception as e:
            ctx["toast"](f"保存失败: {e}", color="error")
