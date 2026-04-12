"""数据源详情弹窗"""

from deva.naja.infra.ui.ui_style import (
    render_detail_section, render_status_badge, format_timestamp,
)
from .constants import _fmt_ts_short
from .table import _timer_trigger_text


async def _show_ds_detail(ctx: dict, mgr, entry_id: str):
    """显示数据源详情"""
    entry = mgr.get(entry_id)
    if not entry:
        ctx["toast"]("数据源不存在", color="error")
        return

    with ctx["popup"](f"数据源详情: {entry.name}", size="large", closable=True):
        ctx["put_html"](render_detail_section("📊 基本信息"))

        source_type = getattr(entry._metadata, "source_type", "custom")
        type_labels = {
            "timer": "定时器",
            "stream": "命名流",
            "http": "HTTP服务",
            "kafka": "Kafka",
            "redis": "Redis",
            "tcp": "TCP端口",
            "file": "文件",
            "custom": "自定义",
            "replay": "数据回放",
        }
        type_label = type_labels.get(source_type, source_type)

        ctx["put_table"]([
            ["ID", entry.id],
            ["名称", entry.name],
            ["类型", type_label],
            ["描述", getattr(entry._metadata, "description", "") or "-"],
            ["状态", "运行中" if entry.is_running else "已停止"],
            ["触发配置", _timer_trigger_text(entry) if source_type == "timer" else f"{getattr(entry._metadata, 'interval', 5):.1f} 秒"],
            ["创建时间", format_timestamp(entry._metadata.created_at)],
            ["更新时间", format_timestamp(entry._metadata.updated_at)],
        ], header=["字段", "值"])

        func_code_file = getattr(entry._metadata, "func_code_file", "") or ""
        if not func_code_file:
            try:
                from deva.naja.config.file_config import get_file_config_manager
                file_mgr = get_file_config_manager("datasource")
                item = file_mgr.get(entry.name)
                if item:
                    func_code_file = item.func_code_file or ""
            except Exception:
                pass

        if func_code_file:
            ctx["put_html"](render_detail_section("📁 代码文件"))
            ctx["put_text"](func_code_file)

        ctx["put_html"](render_detail_section("📈 运行统计"))

        ctx["put_table"]([
            ["发射次数", entry._state.total_emitted],
            ["错误次数", entry._state.error_count],
            ["最后错误", entry._state.last_error or "-"],
            ["错误时间", format_timestamp(entry._state.last_error_ts)],
            ["最后活动", format_timestamp(entry._state.last_data_ts)],
            ["启动时间", format_timestamp(entry._state.start_time)],
        ], header=["字段", "值"])

        ctx["put_html"](render_detail_section("📦 最新数据"))

        latest_data = entry.get_latest_data()
        if latest_data is not None:
            try:
                import pandas as pd
                import json
                if isinstance(latest_data, pd.DataFrame):
                    ctx["put_html"](latest_data.head(10).to_html(index=False))
                elif isinstance(latest_data, (dict, list)):
                    ctx["put_code"](json.dumps(latest_data, ensure_ascii=False,
                                               default=str, indent=2), language="json")
                else:
                    ctx["put_text"](str(latest_data)[:2000])
            except Exception:
                ctx["put_text"](str(latest_data)[:2000])
        else:
            ctx["put_text"]("暂无数据")

        ctx["put_html"](render_detail_section("💻 执行代码"))

        if entry.func_code:
            ctx["put_code"](entry.func_code, language="python")
        else:
            ctx["put_text"]("暂无代码")

        dependent_strategies = _get_dependent_strategies(entry_id)
        ctx["put_html"](render_detail_section("🔗 依赖策略"))

        if dependent_strategies:
            strategy_table = []
            for s in dependent_strategies:
                status_html = render_status_badge(s.get("is_running"))
                ht = s.get("handler_type", "unknown")
                ht_icon = "📡" if ht == "radar" else "🧠" if ht == "memory" else "🎰" if ht == "bandit" else "🤖" if ht == "llm" else "📋"
                strategy_table.append([f"{ht_icon} {s.get('name', '-')}", status_html, ht])
            ctx["put_table"](strategy_table, header=["策略名称", "状态", "消费类型"])
        else:
            ctx["put_text"]("暂无依赖策略")


def _get_dependent_strategies(ds_id: str) -> list:
    """获取依赖该数据源的策略列表"""
    try:
        from deva.naja.strategy import get_strategy_manager
        mgr = get_strategy_manager()
        strategies = []
        for s in mgr.list_all():
            bound_ds = getattr(s._metadata, "bound_datasource_id", "")
            if bound_ds == ds_id:
                ht = getattr(s._metadata, "handler_type", "unknown") or "unknown"
                strategies.append({
                    "id": s.id,
                    "name": s.name,
                    "is_running": s.is_running,
                    "handler_type": ht,
                })
        return strategies
    except Exception:
        return []
