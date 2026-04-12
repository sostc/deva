"""页面路由函数"""

from __future__ import annotations

from typing import Any

from pywebio.output import put_html, put_markdown, put_text
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
    ui = CognitionUI()
    ui.render()


def memory_page():
    """兼容旧入口：重定向到认知页面"""
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
    """系统页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
    except:
        pass
    from deva.naja.system.ui import render_system_page
    ctx = _ctx()
    await render_system_page(ctx)


def _get_log_stream_page():
    from .log_stream import log_stream_page
    return log_stream_page


def _get_loop_audit_page():
    from deva.naja.loop_audit.ui import render_loop_audit_page
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


async def learning_detail_page(entry_id: str = None):
    """知识详情页面"""
    from pywebio.session import eval_js
    try:
        theme = await eval_js("document.cookie.includes('naja-theme=') ? document.cookie.split('naja-theme=')[1].split(';')[0] : null")
        if theme:
            set_request_theme(theme)
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

