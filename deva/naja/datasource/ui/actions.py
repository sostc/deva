"""数据源操作：启停、删除、导出、分类批量操作"""

import time

from pywebio.session import run_async


def _handle_ds_action(action: str, mgr, ctx: dict):
    """处理数据源操作按钮（详情/编辑/启停/删除）"""
    parts = action.split("_")
    action_type = parts[0]
    entry_id = "_".join(parts[1:])

    if action_type == "detail":
        from .detail import _show_ds_detail
        run_async(_show_ds_detail(ctx, mgr, entry_id))
        return
    elif action_type == "edit":
        from .dialogs import _edit_ds_dialog
        run_async(_edit_ds_dialog(ctx, mgr, entry_id))
        return
    elif action_type == "toggle":
        entry = mgr.get(entry_id)
        if entry and entry.is_running:
            mgr.stop(entry_id)
            ctx["toast"]("已停止", color="warning")
        else:
            result = mgr.start(entry_id)
            if result.get("success"):
                ctx["toast"]("已启动", color="success")
            else:
                ctx["toast"](f"启动失败: {result.get('error')}", color="error")
    elif action_type == "delete":
        mgr.delete(entry_id)
        ctx["toast"]("已删除", color="error")

    from .table import _render_ds_content
    _render_ds_content(ctx)


def _create_ds_dialog(mgr, ctx: dict):
    """创建数据源对话框（入口）"""
    from .dialogs import _create_ds_dialog_async
    run_async(_create_ds_dialog_async(mgr, ctx))


def _start_all_ds(mgr, ctx: dict):
    result = mgr.start_all()
    ctx["toast"](f"启动完成: 成功{result['success']}, 失败{result['failed']}, 跳过{result['skipped']}", color="info")
    from .table import _render_ds_content
    _render_ds_content(ctx)


def _stop_all_ds(mgr, ctx: dict):
    result = mgr.stop_all()
    ctx["toast"](f"停止完成: 成功{result['success']}, 失败{result['failed']}, 跳过{result['skipped']}", color="info")
    from .table import _render_ds_content
    _render_ds_content(ctx)


def _export_all_ds_to_file(mgr, ctx: dict):
    """导出所有数据源到文件配置"""
    from deva.naja.config.file_config import get_file_config_manager

    file_mgr = get_file_config_manager('datasource')
    count = 0

    for entry in mgr.list_all():
        if not entry or not entry.name:
            continue

        try:
            from deva.naja.config.file_config import ConfigFileItem, DatasourceConfigMetadata

            meta = entry._metadata
            config_meta = DatasourceConfigMetadata(
                id=entry.id,
                name=entry.name,
                description=meta.description or '',
                tags=meta.tags or [],
                category=getattr(meta, 'category', ''),
                created_at=getattr(meta, 'created_at', 0),
                updated_at=time.time(),
                enabled=getattr(meta, 'enabled', True),
                source='file',
                source_type=getattr(meta, 'source_type', 'timer'),
                interval_seconds=getattr(meta, 'interval', 5.0),
                enabled_types=getattr(meta, 'enabled_types', []),
            )

            parameters = {
                'interval_seconds': getattr(meta, 'interval', 5.0),
                'timeout': getattr(meta, 'timeout', 30),
            }

            config = {
                'source_type': getattr(meta, 'source_type', 'timer'),
                'config': getattr(meta, 'config', {}),
            }

            item = ConfigFileItem(
                name=entry.name,
                config_type='datasource',
                metadata=config_meta,
                parameters=parameters,
                config=config,
                func_code=entry._func_code or '',
            )

            if file_mgr.save(item):
                count += 1
        except Exception as e:
            print(f"Export datasource failed: {entry.name}, error: {e}")

    ctx["toast"](f"已导出 {count} 个数据源到文件", color="success")


def _handle_category_action(action: str, mgr, ctx: dict):
    """处理分类批量操作"""
    if action.startswith("start_cat_"):
        category = action.replace("start_cat_", "")
        _start_category_ds(mgr, ctx, category)
    elif action.startswith("stop_cat_"):
        category = action.replace("stop_cat_", "")
        _stop_category_ds(mgr, ctx, category)


def _start_category_ds(mgr, ctx: dict, category: str):
    """按分类启动数据源"""
    from .table import _categorize_datasource, _render_ds_content

    entries = mgr.list_all()
    target_entries = [e for e in entries if _categorize_datasource(e) == category]

    success = 0
    failed = 0
    for entry in target_entries:
        if not entry.is_running:
            result = mgr.start(entry.id)
            if result.get("success"):
                success += 1
            else:
                failed += 1

    ctx["toast"](f"{category}: 启动完成，成功{success}个，失败{failed}个", color="info")
    _render_ds_content(ctx)


def _stop_category_ds(mgr, ctx: dict, category: str):
    """按分类停止数据源"""
    from .table import _categorize_datasource, _render_ds_content

    entries = mgr.list_all()
    target_entries = [e for e in entries if _categorize_datasource(e) == category]

    success = 0
    for entry in target_entries:
        if entry.is_running:
            mgr.stop(entry.id)
            success += 1

    ctx["toast"](f"{category}: 已停止{success}个数据源", color="info")
    _render_ds_content(ctx)
