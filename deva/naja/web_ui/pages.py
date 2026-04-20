"""页面路由函数"""

from __future__ import annotations

from typing import Any

from pywebio.output import put_html, put_markdown, put_text, set_scope
from pywebio.session import set_env, run_js
from tornado.web import RequestHandler

from deva import NB
from deva.naja.register import SR
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
    ctx = _ctx()
    await ctx["init_naja_ui"]("认知")
    from deva.naja.cognition.ui import CognitionUI
    ui = CognitionUI()
    ui.render()


async def memory_page():
    """兼容旧入口：重定向到认知页面"""
    ctx = _ctx()
    await ctx["init_naja_ui"]("认知")
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
    """运行时状态管理（已停用）"""
    from pywebio.output import put_markdown
    ctx = _ctx()
    await ctx["init_naja_ui"]("运行时状态管理")
    put_markdown("""
    ## 运行时状态管理

    此功能已暂停服务。
    """)


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
    """系统页面 - 重定向到健康监控仪表盘"""
    from deva.naja.infra.observability.health_ui import health_dashboard_page
    await health_dashboard_page()


async def _render_system_page(ctx: dict):
    """渲染系统页面（从 system/ui.py 内联）"""
    from datetime import datetime as _dt

    from ..strategy.result_store import get_result_store
    from ..market_hotspot.integration import get_market_hotspot_integration
    from ..infra.lifecycle.bootstrap import get_last_boot_report

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
            from ..infra.log.log_stream import log_strategy
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

    from ..infra.observability.performance_ui import render_performance_page
    await render_performance_page(ctx)

    from ..infra.observability.loop_audit_ui import render_loop_audit_page
    await render_loop_audit_page(ctx)


def _get_log_stream_page():
    from .log_stream import log_stream_page
    return log_stream_page


def _get_loop_audit_page():
    from ..infra.observability.loop_audit_ui import render_loop_audit_page
    return render_loop_audit_page


async def narrative_page():
    """叙事追踪概览页面"""
    ctx = _ctx()
    await ctx["init_naja_ui"]("叙事追踪")
    from deva.naja.cognition.narrative import render_narrative_page
    await render_narrative_page(ctx)


async def narrative_lifecycle_page():
    """叙事生命周期详细页面"""
    ctx = _ctx()
    await ctx["init_naja_ui"]("叙事生命周期")
    from deva.naja.cognition.narrative import render_narrative_lifecycle_page
    await render_narrative_lifecycle_page(ctx)


async def merrill_clock_page():
    """美林时钟经济周期页面"""
    from deva.naja.cognition.merrill_clock.ui.web_ui import render_merrill_clock_page
    ctx = _ctx()
    await ctx["init_naja_ui"]("美林时钟")
    await render_merrill_clock_page(ctx)


async def learningadmin():
    """学习层管理页面"""
    ctx = _ctx()
    await ctx["init_naja_ui"]("学习层")

    from deva.naja.knowledge.web_ui import render_learning_page
    html = render_learning_page(ctx)
    from pywebio.output import put_html
    put_html(html)


async def learning_list_page():
    """知识列表页面"""
    ctx = _ctx()
    await ctx["init_naja_ui"]("知识列表")

    from deva.naja.knowledge import render_knowledge_list_page
    html = render_knowledge_list_page(ctx)
    from pywebio.output import put_html
    put_html(html)


async def learning_history_page():
    """状态转换历史页面"""
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
    ctx = _ctx()
    await ctx["init_naja_ui"]("供应链知识图谱")

    from deva.naja.attention.ui.supply_chain import render_supply_chain_knowledge_graph_page
    render_supply_chain_knowledge_graph_page()


async def api_explorer():
    """API浏览器页面"""
    ctx = _ctx()
    await ctx["init_naja_ui"]("API浏览器")
    
    api_endpoints = [
        # 核心API
        {"name": "健康检查", "path": "/api/health", "method": "GET", "description": "系统健康状态"},
        {"name": "市场热点", "path": "/api/hotspot", "method": "GET", "description": "市场热点数据"},
        {"name": "知识操作", "path": "/api/knowledge/action", "method": "POST", "description": "知识操作接口"},
        
        # 认知相关API
        {"name": "认知记忆", "path": "/api/cognition/memory", "method": "GET", "description": "认知记忆数据"},
        {"name": "认知主题", "path": "/api/cognition/topics", "method": "GET", "description": "认知主题数据"},
        {"name": "认知注意力", "path": "/api/cognition/attention", "method": "GET", "description": "认知注意力数据"},
        {"name": "认知思考", "path": "/api/cognition/thought", "method": "GET", "description": "认知思考数据"},
        
        # 市场相关API
        {"name": "市场状态", "path": "/api/market/state", "method": "GET", "description": "市场状态数据"},
        {"name": "热点详情", "path": "/api/market/hotspot/details", "method": "GET", "description": "热点详情数据"},
        {"name": "市场热点API", "path": "/api/market/hotspot", "method": "GET", "description": "市场热点API数据"},
        
        # 系统相关API
        {"name": "系统状态", "path": "/api/system/status", "method": "GET", "description": "系统状态数据"},
        {"name": "系统模块", "path": "/api/system/modules", "method": "GET", "description": "系统模块数据"},
        
        # 雷达相关API
        {"name": "雷达事件", "path": "/api/radar/events", "method": "GET", "description": "雷达事件数据"},
        
        # Bandit相关API
        {"name": "Bandit统计", "path": "/api/bandit/stats", "method": "GET", "description": "Bandit统计数据"},
        
        # 知识相关API
        {"name": "知识列表", "path": "/api/knowledge/list", "method": "GET", "description": "知识列表数据"},
        {"name": "知识统计", "path": "/api/knowledge/stats", "method": "GET", "description": "知识统计数据"},
        {"name": "知识详情", "path": "/api/knowledge/detail", "method": "GET", "description": "知识详情数据"},
        {"name": "知识交易", "path": "/api/knowledge/trading", "method": "GET", "description": "知识交易数据"},
        
        # 数据源和策略API
        {"name": "数据源列表", "path": "/api/datasource/list", "method": "GET", "description": "数据源列表数据"},
        {"name": "策略列表", "path": "/api/strategy/list", "method": "GET", "description": "策略列表数据"},
        
        # Alaya状态API
        {"name": "Alaya状态", "path": "/api/alaya/status", "method": "GET", "description": "Alaya状态数据"},
        
        # 注意力相关API
        {"name": "Manas状态", "path": "/api/attention/manas/state", "method": "GET", "description": "Manas状态数据"},
        {"name": "和谐度", "path": "/api/attention/harmony", "method": "GET", "description": "和谐度数据"},
        {"name": "决策", "path": "/api/attention/decision", "method": "GET", "description": "决策数据"},
        {"name": "信念", "path": "/api/attention/conviction", "method": "GET", "description": "信念数据"},
        {"name": "信念时机", "path": "/api/attention/conviction/timing", "method": "GET", "description": "信念时机数据"},
        {"name": "信念添加", "path": "/api/attention/conviction/should-add", "method": "GET", "description": "信念添加数据"},
        {"name": "组合摘要", "path": "/api/attention/portfolio/summary", "method": "GET", "description": "组合摘要数据"},
        {"name": "持仓指标", "path": "/api/attention/position/metrics", "method": "GET", "description": "持仓指标数据"},
        {"name": "追踪热点", "path": "/api/attention/tracking/hotspot", "method": "GET", "description": "追踪热点数据"},
        {"name": "追踪统计", "path": "/api/attention/tracking/stats", "method": "GET", "description": "追踪统计数据"},
        {"name": "盲点", "path": "/api/attention/blind-spots", "method": "GET", "description": "盲点数据"},
        {"name": "融合", "path": "/api/attention/fusion", "method": "GET", "description": "融合数据"},
        {"name": "焦点", "path": "/api/attention/focus", "method": "GET", "description": "焦点数据"},
        {"name": "叙事板块矩阵", "path": "/api/attention/narrative-block-matrix", "method": "GET", "description": "叙事板块矩阵数据"},
        {"name": "注意力报告", "path": "/api/attention/report", "method": "GET", "description": "注意力报告数据"},
        {"name": "实验室状态", "path": "/api/attention/lab/status", "method": "GET", "description": "实验室状态数据"},
        {"name": "流动性", "path": "/api/attention/liquidity", "method": "GET", "description": "流动性数据"},
        {"name": "策略顶级符号", "path": "/api/attention/strategy/top-symbols", "method": "GET", "description": "策略顶级符号数据"},
        {"name": "策略顶级板块", "path": "/api/attention/strategy/top-blocks", "method": "GET", "description": "策略顶级板块数据"},
        {"name": "注意力上下文", "path": "/api/attention/context", "method": "GET", "description": "注意力上下文数据"},
    ]
    
    html = """
    <div style="padding: 20px; max-width: 1200px; margin: 0 auto;">
        <h1 style="color: #e2e8f0; margin-bottom: 20px;">API浏览器</h1>
        <p style="color: #94a3b8; margin-bottom: 30px;">点击下方API端点进行测试，查看响应结果</p>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 15px;">
    """
    
    for i, endpoint in enumerate(api_endpoints):
        endpoint_id = f"endpoint-{i}"
        html += f"""
            <div style="background: #1e293b; border-radius: 8px; padding: 15px; border: 1px solid #334155; transition: all 0.3s ease;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <h3 style="color: #f8fafc; margin: 0; font-size: 16px;">{endpoint['name']}</h3>
                    <span style="background: #3b82f6; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px;">{endpoint['method']}</span>
                </div>
                <div style="color: #94a3b8; font-size: 14px; margin-bottom: 10px; word-break: break-all;">{endpoint['path']}</div>
                <div style="color: #cbd5e1; font-size: 12px; margin-bottom: 15px; line-height: 1.4;">{endpoint['description']}</div>
                <button onclick="testApi('{endpoint_id}', '{endpoint['path']}', '{endpoint['method']}')" 
                        style="background: #3b82f6; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; transition: background 0.2s ease;">
                    测试
                </button>
                <div id="{endpoint_id}-response" style="margin-top: 15px; padding: 15px; background: #111111; border-radius: 6px; border: 1px solid #444444; display: none;">
                    <pre id="{endpoint_id}-content" style="background: #111111; color: #00ff88; margin: 0; padding: 0; overflow-x: auto; max-height: 400px; white-space: pre-wrap; font-size: 16px; line-height: 1.6; font-family: 'Courier New', monospace;"></pre>
                </div>
            </div>
        """
    
    html += """
        </div>
    </div>
    
    <script>
        function testApi(endpointId, path, method) {
            const responseDiv = document.getElementById(endpointId + '-response');
            const contentDiv = document.getElementById(endpointId + '-content');
            
            responseDiv.style.display = 'block';
            contentDiv.textContent = '测试中...';
            
            fetch(path, {
                method: method
            })
            .then(response => response.json())
            .then(data => {
                contentDiv.textContent = JSON.stringify(data, null, 2);
            })
            .catch(error => {
                contentDiv.textContent = '错误: ' + error.message;
            });
        }
    </script>
    """
    
    put_html(html)


async def health_page():
    """系统健康监控仪表盘"""
    from deva.naja.infra.observability.health_ui import health_dashboard_page
    await health_dashboard_page()


async def devtools_page():
    """开发者工具页面"""
    from deva.naja.web_ui.ui_base import _ctx
    ctx = _ctx()
    await ctx["init_naja_ui"]("开发者工具")
    
    dev_tools = {
        "数据管理": [
            {"name": "🗃️ 数据源", "path": "/dsadmin", "desc": "数据源管理"},
            {"name": "📖 字典", "path": "/dictadmin", "desc": "字典管理"},
            {"name": "🗄️ 数据表", "path": "/tableadmin", "desc": "数据表管理"},
        ],
        "策略与交易": [
            {"name": "⏱️ 任务", "path": "/taskadmin", "desc": "任务管理"},
            {"name": "🎯 策略", "path": "/strategyadmin", "desc": "策略管理"},
            {"name": "🤖 LLM", "path": "/llmadmin", "desc": "LLM 调节"},
            {"name": "🎰 Bandit", "path": "/banditadmin", "desc": "Bandit 自适应交易"},
        ],
        "系统监控": [
            {"name": "🩺 健康", "path": "/health", "desc": "系统健康监控"},
            {"name": "🎛️ 调优监控", "path": "/tuningadmin", "desc": "全局调优监控"},
        ],
        "开发调试": [
            {"name": "💾 持久化", "path": "/runtime_state", "desc": "运行时状态"},
            {"name": "🌐 API浏览器", "path": "/api_explorer", "desc": "API 端点测试"},
            {"name": "🔧 配置", "path": "/configadmin", "desc": "配置管理"},
            {"name": "🧿 灵魂", "path": "/souladmin", "desc": "灵魂管理"},
        ],
    }
    
    html = """
    <div style="padding: 24px; max-width: 1200px; margin: 0 auto;">
        <h1 style="color: #e2e8f0; margin-bottom: 8px; font-size: 28px;">🛠️ 开发者工具</h1>
        <p style="color: #94a3b8; margin-bottom: 32px; font-size: 15px;">系统开发、调试、管理工具集合</p>
    """
    
    for category, tools in dev_tools.items():
        html += f"""
        <div style="margin-bottom: 32px;">
            <h2 style="color: #e2e8f0; font-size: 18px; font-weight: 600; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid #334155;">{category}</h2>
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px;">
        """
        
        for tool in tools:
            html += f"""
                <a href="{tool['path']}" class="tool-card" style="display: block; background: #1e293b; border-radius: 10px; padding: 16px; border: 1px solid #334155; text-decoration: none; transition: all 0.2s ease;">
                    <div style="font-size: 16px; color: #e2e8f0; font-weight: 600; margin-bottom: 4px;">{tool['name']}</div>
                    <div style="font-size: 12px; color: #94a3b8;">{tool['desc']}</div>
                </a>
            """
        
        html += """
            </div>
        </div>
        """
    
    html += """
    </div>
    
    <style>
        .tool-card:hover {
            border-color: #60a5fa !important;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(96, 165, 250, 0.15);
            background: #233044;
        }
    </style>
    """
    
    from pywebio.output import put_html
    put_html(html)

