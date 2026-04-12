"""页面路由函数"""

from __future__ import annotations

from typing import Any

from pywebio.output import put_html, put_markdown, put_text, set_scope
from pywebio.session import set_env, run_js
from tornado.web import RequestHandler

from deva import NB
from deva.naja.register import SR
from .theme import get_request_theme, set_request_theme
from .ui_base import _ctx


async def render_main(ctx: dict):
    """渲染主页"""
    await ctx["init_naja_ui"]("管理平台")
    from deva.naja.home.ui import render_home
    await render_home(ctx)


async def main():
    """主页"""
    return await render_main(_ctx())


async def dsadmin():
    """数据源管理"""
    from deva.naja.datasource.ui import render_datasource_admin
    ctx = _ctx()
    await ctx["init_naja_ui"]("数据源管理")
    return await render_datasource_admin(ctx)


async def signaladmin():
    """信号流 - 策略结果可视化"""
    from deva.naja.signal.ui import render_signal_page
    ctx = _ctx()
    await ctx["init_naja_ui"]("信号流")
    await render_signal_page(ctx)


async def taskadmin():
    """任务管理"""
    from deva.naja.tasks.ui import render_task_admin
    ctx = _ctx()
    await ctx["init_naja_ui"]("任务管理")
    return await render_task_admin(ctx)


async def strategyadmin():
    """策略管理"""
    from deva.naja.strategy.ui import render_strategy_admin
    ctx = _ctx()
    await ctx["init_naja_ui"]("策略管理")
    return await render_strategy_admin(ctx)


async def radaradmin():
    """雷达感知层"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass
    from deva.naja.radar.ui import RadarUI
    ctx = _ctx()
    await ctx["init_naja_ui"]("雷达")
    ui = RadarUI()
    ui.render()


async def insightadmin():
    """洞察中心已整合到认知页面"""
    ctx = _ctx()
    await ctx["init_naja_ui"]("认知")
    from deva.naja.cognition.ui import CognitionUI
    ui = CognitionUI()
    ui.render()


async def cognition_page():
    """认知中枢页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass
    from deva.naja.cognition.ui import CognitionUI
    ui = CognitionUI()
    ui.render()


def memory_page():
    """兼容旧入口：重定向到认知页面"""
    from deva.naja.cognition.ui import CognitionUI
    ui = CognitionUI()
    ui.render()


async def llmadmin():
    """LLM 调节"""
    from deva.naja.llm_controller.ui import render_llm_admin
    ctx = _ctx()
    await ctx["init_naja_ui"]("LLM 调节")
    return await render_llm_admin(ctx)


async def banditadmin():
    """Bandit 自适应交易"""
    from deva.naja.bandit.ui import render_bandit_admin
    ctx = _ctx()
    await ctx["init_naja_ui"]("Bandit 自适应交易")
    await render_bandit_admin(ctx)


async def bandit_attribution():
    """Bandit 盈亏归因分析"""
    from deva.naja.bandit.attribution_ui import render_attribution_page
    ctx = _ctx()
    await ctx["init_naja_ui"]("盈亏归因分析")
    await render_attribution_page(ctx)


async def market():
    """市场热点监测"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass

    ctx = _ctx()
    await ctx["init_naja_ui"]("市场热点监测 [已刷新]")

    from pywebio.session import eval_js
    url_params = None
    try:
        url_params = await eval_js("new URLSearchParams(window.location.search).get('ui')")
    except:
        pass

    if url_params == 'v2':
        toast("V2 UI 已合并到主版本", color="info")

    from deva.naja.market_hotspot.ui import render_market_hotspot_admin
    await render_market_hotspot_admin(ctx)


async def awakening_page():
    """觉醒系统页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass

    ctx = _ctx()
    await ctx["init_naja_ui"]("觉醒系统")

    from deva.naja.attention.ui.dashboard import render_attention_monitor_page
    render_attention_monitor_page(ctx)


async def dictadmin():
    """字典管理"""
    from deva.naja.dictionary.ui import render_dictionary_admin
    ctx = _ctx()
    await ctx["init_naja_ui"]("字典管理")
    return await render_dictionary_admin(ctx)


async def tableadmin():
    """数据表管理"""
    from deva.naja.tables.ui import render_tables_page
    ctx = _ctx()
    ctx["NB"] = NB
    ctx["pd"] = __import__("pandas")
    await ctx["init_naja_ui"]("数据表管理")
    set_scope("tables_content")
    render_tables_page(ctx)


async def runtimestateadmin():
    """运行时状态管理"""
    from deva.naja.runtime_state.ui import render_runtime_state_page
    ctx = _ctx()
    await ctx["init_naja_ui"]("运行时状态管理")
    set_scope("runtime_state_content")
    render_runtime_state_page(ctx)


async def souladmin():
    """灵魂管理"""
    from deva.naja.home.soul_admin import render_soul_admin
    ctx = _ctx()
    await ctx["init_naja_ui"]("灵魂管理")
    render_soul_admin()


async def configadmin():
    """配置管理"""
    from deva.naja.config.ui import render_config_page
    ctx = _ctx()
    await ctx["init_naja_ui"]("配置管理")
    render_config_page(ctx)


async def tuningadmin():
    """全局调优监控"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass

    ctx = _ctx()
    await ctx["init_naja_ui"]("全局调优监控")

    ctx["put_html"]('<div style="margin: 20px; color: #64748b;">加载中...</div>')

    try:
        from deva.naja.attention.ui.auto_tuning_monitor import (
            render_tuning_monitor_panel,
            render_frequency_monitor_panel,
            render_datasource_tuning_panel,
        )
        panel1 = render_tuning_monitor_panel()
        panel2 = render_frequency_monitor_panel()
        panel3 = render_datasource_tuning_panel()
        ctx["put_html"](panel1)
        ctx["put_html"](panel2)
        ctx["put_html"](panel3)
    except Exception as e:
        ctx["put_html"](f'<div style="color: #f87171; padding: 20px;">渲染失败: {str(e)}</div>')


async def system_page():
    """系统页面（原 system/ui.py 已内联）"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass
    ctx = _ctx()
    await _render_system_page(ctx)


async def _render_system_page(ctx: dict):
    """渲染系统页面（从 system/ui.py 内联）"""
    from datetime import datetime as _dt

    from ..strategy.result_store import get_result_store
    from ..market_hotspot.integration import get_market_hotspot_integration
    from ..bootstrap import get_last_boot_report

    def _format_ts(ts: float) -> str:
        if not ts:
            return "未写入"
        return _dt.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

    def _status_color(level: str) -> str:
        if level == "critical":
            return "#dc2626"
        if level == "warning":
            return "#f59e0b"
        return "#16a34a"

    def _status_label(level: str) -> str:
        if level == "critical":
            return "严重"
        if level == "warning":
            return "告警"
        return "正常"

    def _get_write_level(seconds_since_write) -> str:
        if seconds_since_write is None:
            return "warning"
        if seconds_since_write > 900:
            return "critical"
        if seconds_since_write > 300:
            return "warning"
        return "ok"

    await ctx["init_naja_ui"]("系统")

    result_store = get_result_store()
    health = result_store.get_health_summary()

    last_write_time = health.get("last_write_time", 0) or 0
    seconds_since_write = health.get("seconds_since_write")
    write_level = _get_write_level(seconds_since_write)
    write_color = _status_color(write_level)

    attention_report = {"status": "not_initialized"}
    try:
        attention_report = get_market_hotspot_integration().get_hotspot_report()
    except Exception:
        pass

    alert = result_store.should_alert_no_writes(stale_seconds=300, cooldown_seconds=300)
    if alert.get("should_alert"):
        gap = alert.get("seconds_since_write")
        msg = f"ResultStore 超过 {int(gap)} 秒未写入，雷达/记忆可能无沉淀"
        try:
            ctx["toast"](msg, color="warn", duration=6)
        except Exception:
            pass
        try:
            from ..log_stream import log_strategy
            log_strategy("WARN", "system", "System", msg)
        except Exception:
            pass

    boot_report = get_last_boot_report()

    status_badge = f"<span style='padding:2px 8px;border-radius:10px;background:{write_color};color:#fff;font-size:12px;'>{_status_label(write_level)}</span>"
    seconds_text = f"{seconds_since_write:.0f}s" if seconds_since_write is not None else "未写入"

    ctx["put_html"](
    """<div style="margin: 10px 0 16px 0; padding: 14px; border-radius: 12px; background: #0f172a; color: #e2e8f0;">
        <div style="display: flex; align-items: center; gap: 10px;">
            <div style="width: 10px; height: 10px; border-radius: 50%; background: """ + write_color + """;"></div>
            <div style="font-size: 15px; font-weight: 600;">系统健康摘要</div>
        </div>
        <div style="margin-top: 10px; font-size: 12px; color: #94a3b8;">
            阈值说明：绿色 ≤ 300s，橙色 300-900s，红色 > 900s
        </div>
    </div>""")

    ctx["put_html"](
    """<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-bottom:14px;">
        <div style="padding:12px;border-radius:10px;background:#111827;">
            <div style="font-size:12px;color:#94a3b8;">结果存储</div>
            <div style="margin-top:6px;font-size:14px;">状态: """ + status_badge + """</div>
            <div style="margin-top:6px;font-size:12px;color:#9ca3af;">最近写入: """ + _format_ts(last_write_time) + """</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">间隔: """ + seconds_text + """</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">队列: """ + str(health.get("write_queue_size", 0)) + """ | 失败: """ + str(health.get("failed_writes", 0)) + """</div>
        </div>
        <div style="padding:12px;border-radius:10px;background:#111827;">
            <div style="font-size:12px;color:#94a3b8;">注意力系统</div>
            <div style="margin-top:6px;font-size:14px;">状态: """ + str(attention_report.get("status", "unknown")) + """</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">快照: """ + str(attention_report.get("processed_snapshots", 0)) + """</div>
            <div style="margin-top:4px;font-size:12px;color:#9ca3af;">全局注意力: """ + f"{attention_report.get('global_attention', 0):.3f}" + """</div>
        </div>
    </div>""")

    ctx["put_html"](
    """<div style="margin-top: 10px; font-size: 12px; color: #94a3b8;">
        说明：结果存储长期无写入，通常意味着策略未运行或数据源无数据输入。
    </div>""")

    if boot_report:
        ctx["put_markdown"]("### 系统启动报告")
        summary_rows = [
            ["启动成功", "是" if boot_report.get("success") else "否"],
            ["阶段", boot_report.get("stage", "unknown")],
            ["耗时(ms)", f"{boot_report.get('duration_ms', 0):.1f}"],
            ["消息", boot_report.get("message", "")],
        ]
        ctx["put_table"](summary_rows)

        details = boot_report.get("details") or {}
        if details:
            ctx["put_markdown"]("#### 详细信息")
            ctx["put_code"](str(details))

    from ..performance.ui import render_performance_page
    await render_performance_page(ctx)

    from .loop_audit_ui import render_loop_audit_page
    await render_loop_audit_page(ctx)


def _get_log_stream_page():
    from .log_stream import log_stream_page
    return log_stream_page


def _get_loop_audit_page():
    from .loop_audit_ui import render_loop_audit_page
    return render_loop_audit_page


async def narrative_page():
    """叙事追踪概览页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass
    ctx = _ctx()
    await ctx["init_naja_ui"]("叙事追踪")
    from deva.naja.cognition.narrative import render_narrative_page
    await render_narrative_page(ctx)


async def narrative_lifecycle_page():
    """叙事生命周期详细页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass
    ctx = _ctx()
    await ctx["init_naja_ui"]("叙事生命周期")
    from deva.naja.cognition.narrative import render_narrative_lifecycle_page
    await render_narrative_lifecycle_page(ctx)


async def merrill_clock_page():
    """美林时钟经济周期页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass
    from deva.naja.cognition.merrill_clock.ui.web_ui import render_merrill_clock_page
    ctx = {"put_html": put_html, "put_markdown": put_markdown}
    await render_merrill_clock_page(ctx)


async def learningadmin():
    """学习层管理页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass

    ctx = _ctx()
    await ctx["init_naja_ui"]("学习层")

    from deva.naja.knowledge.web_ui import render_learning_page
    html = render_learning_page(ctx)
    from pywebio.output import put_html
    put_html(html)


async def learning_list_page():
    """知识列表页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass

    ctx = _ctx()
    await ctx["init_naja_ui"]("知识列表")

    from deva.naja.knowledge import render_knowledge_list_page
    html = render_knowledge_list_page(ctx)
    from pywebio.output import put_html
    put_html(html)


async def learning_history_page():
    """状态转换历史页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass

    ctx = _ctx()
    await ctx["init_naja_ui"]("状态转换历史")

    from deva.naja.knowledge.web_ui import render_knowledge_history_page
    html = render_knowledge_history_page(ctx)
    from pywebio.output import put_html
    put_html(html)


class KnowledgeActionHandler(RequestHandler):
    """知识操作 API 处理器"""

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")

    def options(self):
        self.write({})

    async def post(self):
        """处理知识操作"""
        import json
        try:
            data = json.loads(self.request.body.decode('utf-8'))
            action = data.get('action', '')
            entry_id = data.get('entry_id', '')
            note = data.get('note', '')

            from deva.naja.knowledge import get_learning_ui
            learning_ui = get_learning_ui()
            result = learning_ui.handle_action(action, entry_id, note)

            self.write(json.dumps(result))
        except Exception as e:
            self.write(json.dumps({"success": False, "message": str(e)}))


async def learning_detail_page():
    """知识详情页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass

    entry_id = None
    try:
        entry_id = await eval_js("new URLSearchParams(window.location.search).get('entry_id')")
    except:
        pass

    ctx = _ctx()
    await ctx["init_naja_ui"]("知识详情")

    from deva.naja.knowledge.web_ui import render_knowledge_detail_page
    html = render_knowledge_detail_page(ctx, entry_id)
    from pywebio.output import put_html
    put_html(html)


async def supplychain_page():
    """供应链知识图谱页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass

    ctx = _ctx()
    await ctx["init_naja_ui"]("供应链知识图谱")

    from deva.naja.attention.ui.supply_chain import render_supply_chain_knowledge_graph_page
    render_supply_chain_knowledge_graph_page()

