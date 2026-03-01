"""Data Dictionary V2 admin panel.

基于 RecoverableUnit 基类重构的数据字典管理界面。
"""

from __future__ import annotations

import json
from datetime import datetime

from .dictionary_v2 import (
    get_dictionary_manager,
    DictionaryEntry,
    DictionaryManager,
    DICT_ENTRY_TABLE,
    DICT_PAYLOAD_TABLE,
)


DEFAULT_FETCH_CODE = '''def fetch_data():
    """获取股票基础信息示例"""
    import pandas as pd
    import time
    
    data = {
        "timestamp": time.time(),
        "stocks": [
            {"code": "000001", "name": "平安银行", "industry": "银行"},
            {"code": "000002", "name": "万科A", "industry": "房地产"},
        ]
    }
    return data
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


def _schedule_label(entry: DictionaryEntry) -> str:
    if entry._metadata.schedule_type == "daily":
        return f"每日 {entry._metadata.daily_time}"
    return f"每 {entry._metadata.interval_seconds} 秒"


async def render_dictionary_v2_admin(ctx):
    await ctx["init_admin_ui"]("Deva数据字典 V2")

    mgr = get_dictionary_manager()
    if not mgr.list_all():
        mgr.load_from_db()

    ctx["put_markdown"]("### 📚 数据字典 V2")
    ctx["put_html"]("<p style='color:#666'>基于 RecoverableUnit 的数据字典管理，支持自动恢复。</p>")

    _render_stats(ctx, mgr)
    _render_toolbar(ctx, mgr)
    _render_table(ctx, mgr)


def _render_stats(ctx, mgr: DictionaryManager):
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
        <div style='font-size:12px;color:#666;'>成功</div><div style='font-size:24px;font-weight:700;color:#1b6fd1;'>{s['success']}</div>
      </div>
      <div style='flex:1;background:#fff;padding:14px;border-radius:8px;border:1px solid #eee;'>
        <div style='font-size:12px;color:#666;'>异常</div><div style='font-size:24px;font-weight:700;color:#d33f2f;'>{s['error']}</div>
      </div>
    </div>
    """
    ctx["put_html"](html)


def _render_toolbar(ctx, mgr: DictionaryManager):
    ctx["put_row"]([
        ctx["put_button"]("新建字典条目", onclick=lambda: ctx["run_async"](_create_dialog(ctx, mgr)), color="primary"),
        ctx["put_button"]("刷新列表", onclick=lambda: ctx["run_js"]("location.reload()")),
        ctx["put_button"]("恢复运行状态", onclick=lambda: _restore_states(ctx, mgr)),
    ]).style("margin-bottom: 10px")


def _restore_states(ctx, mgr: DictionaryManager):
    result = mgr.restore_running_states()
    ctx["toast"](f"恢复完成: 成功={result['restored_count']}, 失败={result['failed_count']}", color="info")
    ctx["run_js"]("location.reload()")


def _render_table(ctx, mgr: DictionaryManager):
    entries = mgr.list_all()
    if not entries:
        ctx["put_html"]("<div style='padding:16px;border:1px dashed #ccc;border-radius:8px;color:#666;'>暂无数据字典条目</div>")
        return

    rows = [["名称", "类型", "状态", "大小", "最后更新", "更新频率", "操作"]]
    for entry in entries:
        status = "运行中" if entry.is_running else "已停止"
        status_color = "#0a7f3f" if entry.is_running else "#666"
        
        if entry._state.last_status == "running":
            status = "执行中"
            status_color = "#1b6fd1"
        elif entry._state.last_status == "error":
            status = "异常"
            status_color = "#d33f2f"
        elif entry._state.last_status == "success":
            status = "正常" if not entry.is_running else "运行中"

        actions = ctx["put_buttons"](
            [
                {"label": "详情", "value": f"detail_{entry.id}"},
                {"label": "编辑", "value": f"edit_{entry.id}"},
                {"label": "执行", "value": f"run_{entry.id}"},
                {"label": "清空", "value": f"clear_{entry.id}"},
                {"label": "停止" if entry.is_running else "启动", "value": f"toggle_{entry.id}"},
                {"label": "删除", "value": f"delete_{entry.id}"},
            ],
            onclick=lambda v, eid=entry.id: _handle_action(ctx, mgr, v, eid),
        )
        rows.append([
            entry.name,
            entry._metadata.dict_type,
            ctx["put_html"](f"<span style='color:{status_color};font-weight:600'>{status}</span>"),
            _fmt_size(entry._state.data_size_bytes),
            _fmt_ts(entry._state.last_update_ts),
            _schedule_label(entry),
            actions,
        ])

    ctx["put_table"](rows)


def _handle_action(ctx, mgr: DictionaryManager, action_value: str, entry_id: str):
    action = action_value.split("_", 1)[0]
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("条目不存在", color="error")
        return

    if action == "detail":
        ctx["run_async"](_detail_dialog(ctx, entry))
        return
    if action == "edit":
        ctx["run_async"](_edit_dialog(ctx, mgr, entry))
        return
    if action == "run":
        result = entry.run_once()
        if result.get("success"):
            ctx["toast"]("执行成功", color="success")
        else:
            ctx["toast"](f"执行失败: {result.get('error', '')}", color="error")
        ctx["run_js"]("location.reload()")
        return
    if action == "clear":
        result = entry.clear_payload()
        if result.get("success"):
            ctx["toast"]("数据已清空", color="warning")
        else:
            ctx["toast"](f"清空失败: {result.get('error', '')}", color="error")
        ctx["run_js"]("location.reload()")
        return
    if action == "toggle":
        if entry.is_running:
            entry.stop()
            ctx["toast"]("已停止", color="warning")
        else:
            result = entry.start()
            if result.get("success"):
                ctx["toast"]("已启动", color="success")
            else:
                ctx["toast"](f"启动失败: {result.get('error', '')}", color="error")
        ctx["run_js"]("location.reload()")
        return
    if action == "delete":
        mgr.delete(entry_id)
        ctx["toast"]("已删除", color="warning")
        ctx["run_js"]("location.reload()")


async def _detail_dialog(ctx, entry: DictionaryEntry):
    with ctx["popup"](f"数据字典详情: {entry.name}", size="large", closable=True):
        info = [
            ["字段", "值"],
            ["ID", entry.id],
            ["名称", entry.name],
            ["类型", entry._metadata.dict_type],
            ["描述", entry._metadata.description or "-"],
            ["状态", entry._state.last_status],
            ["运行状态", "运行中" if entry.is_running else "已停止"],
            ["更新频率", _schedule_label(entry)],
            ["最后更新", _fmt_ts(entry._state.last_update_ts)],
            ["数据大小", _fmt_size(entry._state.data_size_bytes)],
            ["运行次数", str(entry._state.run_count)],
            ["错误次数", str(entry._state.error_count)],
            ["最后错误", entry._state.last_error or "-"],
            ["编译状态", "已编译" if entry.compiled_func else "未编译"],
        ]
        ctx["put_table"](info)

        ctx["put_markdown"]("#### 最新数据")
        payload = entry.get_payload()
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
        ctx["put_code"](entry.func_code or "", language="python")


async def _create_dialog(ctx, mgr: DictionaryManager):
    with ctx["popup"]("新建数据字典条目", size="large", closable=True):
        form = await ctx["input_group"]("字典条目", [
            ctx["input"]("名称", name="name", required=True, placeholder="输入字典名称"),
            ctx["select"]("字典类型", name="dict_type", options=[
                {"label": "股票基础信息", "value": "stock_basic"},
                {"label": "行业映射", "value": "industry_mapping"},
                {"label": "自定义", "value": "custom"},
            ], value="custom"),
            ctx["input"]("描述", name="description", placeholder="输入描述"),
            ctx["select"]("更新模式", name="schedule_type", options=[
                {"label": "按间隔(秒)", "value": "interval"},
                {"label": "按每日时间", "value": "daily"},
            ], value="interval"),
            ctx["input"]("间隔秒数", name="interval_seconds", type="number", min=5, value=300),
            ctx["input"]("每日执行时间", name="daily_time", value="03:00", placeholder="HH:MM"),
            ctx["select"]("保存后状态", name="enabled", options=[
                {"label": "启用", "value": "true"},
                {"label": "停用", "value": "false"},
            ], value="false"),
            ctx["textarea"]("更新代码", name="code", rows=16, code={"mode": "python", "theme": "darcula"}, value=DEFAULT_FETCH_CODE),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])

        if not form or form.get("action") != "save":
            return

        try:
            result = mgr.create(
                name=form.get("name", "").strip(),
                func_code=form.get("code", ""),
                description=form.get("description", "").strip(),
                dict_type=form.get("dict_type", "custom"),
                schedule_type=form.get("schedule_type", "interval"),
                interval_seconds=int(form.get("interval_seconds", 300) or 300),
                daily_time=(form.get("daily_time", "03:00") or "03:00").strip(),
                enabled=str(form.get("enabled", "false")).lower() == "true",
            )
            
            if result.get("success"):
                ctx["toast"]("创建成功", color="success")
                ctx["close_popup"]()
                ctx["run_js"]("location.reload()")
            else:
                ctx["toast"](f"创建失败: {result.get('error', '')}", color="error")
        except Exception as e:
            ctx["toast"](f"创建失败: {e}", color="error")


async def _edit_dialog(ctx, mgr: DictionaryManager, entry: DictionaryEntry):
    with ctx["popup"](f"编辑数据字典: {entry.name}", size="large", closable=True):
        form = await ctx["input_group"]("字典条目", [
            ctx["input"]("名称", name="name", required=True, value=entry.name),
            ctx["select"]("字典类型", name="dict_type", options=[
                {"label": "股票基础信息", "value": "stock_basic"},
                {"label": "行业映射", "value": "industry_mapping"},
                {"label": "自定义", "value": "custom"},
            ], value=entry._metadata.dict_type),
            ctx["input"]("描述", name="description", value=entry._metadata.description),
            ctx["select"]("更新模式", name="schedule_type", options=[
                {"label": "按间隔(秒)", "value": "interval"},
                {"label": "按每日时间", "value": "daily"},
            ], value=entry._metadata.schedule_type),
            ctx["input"]("间隔秒数", name="interval_seconds", type="number", min=5, value=entry._metadata.interval_seconds),
            ctx["input"]("每日执行时间", name="daily_time", value=entry._metadata.daily_time, placeholder="HH:MM"),
            ctx["select"]("状态", name="enabled", options=[
                {"label": "启用", "value": "true"},
                {"label": "停用", "value": "false"},
            ], value="true" if entry.is_running else "false"),
            ctx["textarea"]("更新代码", name="code", rows=16, code={"mode": "python", "theme": "darcula"}, value=entry.func_code),
            ctx["actions"]("操作", [
                {"label": "保存", "value": "save"},
                {"label": "取消", "value": "cancel"},
            ], name="action"),
        ])

        if not form or form.get("action") != "save":
            return

        try:
            result = entry.update_config(
                name=form.get("name", "").strip(),
                description=form.get("description", "").strip(),
                dict_type=form.get("dict_type"),
                schedule_type=form.get("schedule_type"),
                interval_seconds=int(form.get("interval_seconds", 300) or 300),
                daily_time=(form.get("daily_time", "03:00") or "03:00").strip(),
                func_code=form.get("code"),
                enabled=str(form.get("enabled", "false")).lower() == "true",
            )
            
            if result.get("success"):
                ctx["toast"]("保存成功", color="success")
                ctx["close_popup"]()
                ctx["run_js"]("location.reload()")
            else:
                ctx["toast"](f"保存失败: {result.get('error', '')}", color="error")
        except Exception as e:
            ctx["toast"](f"保存失败: {e}", color="error")
