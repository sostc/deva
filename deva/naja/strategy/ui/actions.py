"""策略工具栏操作与批量操作"""

import json
import time as time_module

from pywebio.session import run_async

from deva.naja.register import SR


def _get_render_strategy_content():
    """延迟导入避免循环引用"""
    from . import _render_strategy_content
    return _render_strategy_content


def _export_all_strategies_to_file(mgr, ctx: dict):
    """导出所有策略到文件配置"""
    from deva.naja.config.file_config import get_file_config_manager

    file_mgr = get_file_config_manager('strategy')
    count = 0

    for entry in mgr.list_all():
        if not entry or not entry.name:
            continue

        try:
            from deva.naja.config.file_config import ConfigFileItem, StrategyConfigMetadata

            meta = entry._metadata
            config_meta = StrategyConfigMetadata(
                id=entry.id,
                name=entry.name,
                description=meta.description or '',
                tags=meta.tags or [],
                category=meta.category or '默认',
                created_at=getattr(meta, 'created_at', 0),
                updated_at=time_module.time(),
                enabled=getattr(meta, 'enabled', True),
                source='file',
                bound_datasource_id=getattr(meta, 'bound_datasource_id', ''),
                bound_datasource_ids=getattr(meta, 'bound_datasource_ids', []),
                compute_mode=getattr(meta, 'compute_mode', 'record'),
                window_size=getattr(meta, 'window_size', 5),
                window_type=getattr(meta, 'window_type', 'sliding'),
                window_interval=getattr(meta, 'window_interval', '10s'),
                window_return_partial=getattr(meta, 'window_return_partial', False),
                dictionary_profile_ids=getattr(meta, 'dictionary_profile_ids', []),
                max_history_count=getattr(meta, 'max_history_count', 100),
                strategy_type=getattr(meta, 'strategy_type', 'legacy'),
                handler_type=getattr(meta, 'handler_type', 'unknown'),
            )

            parameters = {
                'window_size': getattr(meta, 'window_size', 5),
                'max_history_count': getattr(meta, 'max_history_count', 100),
                'enabled': getattr(meta, 'enabled', True),
            }

            config = {
                'compute_mode': getattr(meta, 'compute_mode', 'record'),
                'window_type': getattr(meta, 'window_type', 'sliding'),
                'strategy_type': getattr(meta, 'strategy_type', 'legacy'),
                'handler_type': getattr(meta, 'handler_type', 'unknown'),
            }

            item = ConfigFileItem(
                name=entry.name,
                config_type='strategy',
                metadata=config_meta,
                parameters=parameters,
                config=config,
                func_code=entry._func_code or '',
            )

            if file_mgr.save(item):
                count += 1
        except Exception as e:
            print(f"Export strategy failed: {entry.name}, error: {e}")

    ctx["toast"](f"已导出 {count} 个策略到文件", color="success")


def _start_all_strategies(ctx, mgr):
    """启动所有策略"""
    count = 0
    for e in mgr.list_all():
        if not e.is_running:
            mgr.start(e.id)
            count += 1
    ctx["toast"](f"已启动 {count} 个策略", color="success")
    _get_render_strategy_content()(ctx)


def _stop_all_strategies(ctx, mgr):
    """停止所有策略"""
    count = 0
    for e in mgr.list_all():
        if e.is_running:
            mgr.stop(e.id)
            count += 1
    ctx["toast"](f"已停止 {count} 个策略", color="warning")
    _get_render_strategy_content()(ctx)


def _reload_all_strategies(ctx, mgr):
    """热重载所有策略"""
    try:
        result = mgr.reload_all()
        reloaded = result.get("reloaded", 0)
        failed = result.get("failed", 0)

        if failed > 0:
            ctx["toast"](f"重载完成: {reloaded} 成功, {failed} 失败", color="warning")
        else:
            ctx["toast"](f"已重载 {reloaded} 个策略", color="success")
    except Exception as e:
        ctx["toast"](f"重载过程中出现错误: {str(e)}", color="error")
    finally:
        # 无论重载是否成功，都刷新策略列表页
        _get_render_strategy_content()(ctx)


def _refresh_results(ctx, mgr):
    """刷新执行结果"""
    _get_render_strategy_content()(ctx)
    ctx["toast"]("结果已刷新", color="success")


def _handle_toolbar_action(action: str, mgr, ctx: dict):
    """处理工具栏按钮操作"""
    from .dialogs import (
        _create_strategy_dialog, _show_history_dialog,
        _open_experiment_dialog, _close_experiment_mode,
    )

    if action == "create":
        _create_strategy_dialog(mgr, ctx)
    elif action == "start_all":
        _start_all_strategies(ctx, mgr)
    elif action == "stop_all":
        _stop_all_strategies(ctx, mgr)
    elif action == "reload_all":
        _reload_all_strategies(ctx, mgr)
    elif action == "refresh_results":
        _refresh_results(ctx, mgr)
    elif action == "show_history":
        run_async(_show_history_dialog(ctx, mgr))
    elif action == "open_experiment":
        run_async(_open_experiment_dialog(ctx, mgr))
    elif action == "close_experiment":
        _close_experiment_mode(ctx, mgr)



def _handle_strategy_action(action: str, mgr, ctx: dict):
    """处理策略操作"""
    from .detail import _show_strategy_detail
    from .dialogs import _edit_strategy_dialog
    from .board import _show_strategy_board

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
    elif action_type == "board":
        run_async(_show_strategy_board(ctx, mgr, entry_id))
        return
    elif action_type == "delete":
        mgr.delete(entry_id)
        ctx["toast"]("已删除", color="error")
        ctx["close_popup"]()

    _get_render_strategy_content()(ctx)



