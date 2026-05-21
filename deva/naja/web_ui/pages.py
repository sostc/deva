"""页面路由函数"""

from __future__ import annotations

from typing import Any

from pywebio.output import put_html, put_markdown, put_text, set_scope
from pywebio.session import set_env, run_js
from tornado.web import RequestHandler

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
    """信号流 - 策略结果可视化（包含双总线事件）"""
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
        {"name": "市场热点", "path": "/api/market/hotspot", "method": "GET", "description": "市场热点数据"},
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
        {"name": "系统状态", "path": "/api/system/runtime", "method": "GET", "description": "系统状态数据"},
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


async def investment_sandbox_page():
    """AI编程全生态与硬件重构投资沙盘"""
    html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI编程全生态与硬件重构投资沙盘</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .chart-container { 
            position: relative; 
            width: 100%; 
            max-width: 800px; 
            margin-left: auto; 
            margin-right: auto; 
            height: 35vh; 
            max-height: 350px; 
            min-height: 250px;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #FAF9F5; 
            color: #1E293B;
        }
        .active-tab {
            background-color: #0F766E;
            color: white;
            box-shadow: 0 4px 6px -1px rgba(15, 118, 110, 0.2);
        }
    </style>
</head>
<body class="antialiased">
    <nav class="sticky top-0 bg-white/95 backdrop-blur shadow-sm z-50 border-b border-stone-200">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between h-16 items-center">
                <div class="flex items-center space-x-2">
                    <span class="text-2xl">⚡</span>
                    <span class="font-bold text-lg sm:text-xl text-teal-850 tracking-tight">AI编程时代：全栈算力与商业变现投资图谱</span>
                </div>
                <div class="hidden md:flex space-x-6 text-sm font-medium text-slate-600">
                    <a href="#article-body" class="hover:text-teal-700 transition-colors">深度研报</a>
                    <a href="#sandbox" class="hover:text-teal-700 transition-colors">执行环沙盒</a>
                    <a href="#portfolio" class="hover:text-teal-700 transition-colors">选股决策矩阵</a>
                </div>
            </div>
        </div>
    </nav>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-16">
        <header class="text-center space-y-4 max-w-4xl mx-auto">
            <span class="px-3 py-1 bg-teal-100 text-teal-800 text-xs font-bold rounded-full border border-teal-200 uppercase tracking-widest">Master Strategy Report</span>
            <h1 class="text-3xl sm:text-4xl md:text-5xl font-black text-slate-900 leading-tight">
                AI编程引爆的<span class="text-teal-700">“全链条算力”</span>与<span class="text-amber-600">“Office化变现”</span>深度投资指南
            </h1>
            <p class="text-base sm:text-lg text-slate-600 leading-relaxed">
                本报告完美融合：大模型双头垄断、B2B企业级付费逻辑、以及“生成 ➡️ 编译 ➡️ 24小时沙箱运行”闭环对 <strong>CPU、DRAM内存、云端/端侧消费电子</strong> 的深度重构。
            </p>
        </header>

        <section id="article-body" class="bg-white rounded-3xl p-6 sm:p-10 border border-stone-200 shadow-sm space-y-10">
            <div class="border-b border-stone-100 pb-6 text-center max-w-3xl mx-auto">
                <h2 class="text-2xl sm:text-3xl font-bold text-slate-900">核心研报：穿透“大模型与编程Agent”迷雾</h2>
                <p class="text-sm text-slate-500 mt-2">点击各章节探索硬件压榨与商业付费的底层产业变化</p>
            </div>

            <div class="bg-stone-50 border-l-4 border-teal-600 p-6 rounded-r-xl">
                <p class="text-slate-700 text-sm sm:text-base italic leading-relaxed">
                    “AI编程助手（如Devin、Claude-3.7）和AI Agent的爆火，其投资核心决不能只停留在‘大模型’或‘英伟达GPU训练’上。因为代码不仅要‘写出来（GPU推理）’，更要在安全沙箱里‘编译运行、24小时不间断测试（CPU+DRAM消耗）’。同时，B2B企业买单的Office订阅制逻辑，正成为商业闭环的最强引擎。”
                </p>
            </div>

            <div class="space-y-6">
                <div class="border border-stone-200 rounded-2xl p-6 hover:shadow-md transition-shadow">
                    <div class="flex justify-between items-center cursor-pointer" onclick="toggleChapter('chap1')">
                        <h3 class="text-lg sm:text-xl font-bold text-slate-800 flex items-center">
                            <span class="text-teal-700 mr-3">📌 第一章</span>
                            商业化变现终局：为什么是“企业统一采购（Office化）”？
                        </h3>
                        <span class="text-stone-400 font-bold" id="chap1-arrow">▼</span>
                    </div>
                    <div class="mt-4 text-sm sm:text-base text-slate-600 space-y-4 hidden" id="chap1-content">
                        <p>
                            个人开发者每个月掏20美元可能需要反复权衡。但对于企业级雇主而言，程序员是极度昂贵的生产力要素。任何能够将研发效率提升15%-25%的AI Agent套件，其带来的ROI（投资回报率）都是巨大的。
                        </p>
                        <p class="font-semibold text-slate-800">
                            付费形态演变：
                        </p>
                        <ul class="list-disc pl-5 space-y-2 text-sm">
                            <li><strong>Office化B2B大包套餐：</strong> 就像企业为所有员工采购 Microsoft 365 办公套件一样，未来企业会直接为研发部门、乃至全员采购AI编程/办公套件（以人头费或Token总包计费）。</li>
                            <li><strong>企业级预算重构：</strong> 企业原本拨给外包公司、初级初创开发工具的预算，将大规模向AI Agent软件订阅倾斜。</li>
                        </ul>
                    </div>
                </div>

                <div class="border border-stone-200 rounded-2xl p-6 hover:shadow-md transition-shadow">
                    <div class="flex justify-between items-center cursor-pointer" onclick="toggleChapter('chap2')">
                        <h3 class="text-lg sm:text-xl font-bold text-slate-800 flex items-center">
                            <span class="text-teal-700 mr-3">📌 第二章</span>
                            大模型竞争哑铃格局：双头垄断与长尾并存
                        </h3>
                        <span class="text-stone-400 font-bold" id="chap2-arrow">▼</span>
                    </div>
                    <div class="mt-4 text-sm sm:text-base text-slate-600 space-y-4 hidden" id="chap2-content">
                        <p>
                            AI编程是一场对复杂逻辑有着近乎偏执要求的战役。这导致大模型层面未来将呈现典型的“哑铃型”市场格局：
                        </p>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                            <div class="bg-teal-50/50 p-4 rounded-xl border border-teal-100">
                                <h4 class="font-bold text-teal-900 text-sm mb-1">重负载核心：Anthropic &amp; OpenAI 双头垄断</h4>
                                <p class="text-xs text-slate-600">系统架构设计、长上下文漏洞调试、大型重构需要极强泛化能力。Anthropic (Claude 家族) 与 OpenAI (Codex 家族) 将吃掉70%的高价Token市场。</p>
                            </div>
                            <div class="bg-amber-50/50 p-4 rounded-xl border border-amber-100">
                                <h4 class="font-bold text-amber-900 text-sm mb-1">轻负载边缘：开源小模型（Llama, DeepSeek等）</h4>
                                <p class="text-xs text-slate-600">单行补全、前端基础编写。这些任务由于高频、高实时性要求，将直接跑在端侧（AI PC）或企业低功耗私有云上。</p>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="border border-stone-200 rounded-2xl p-6 hover:shadow-md transition-shadow">
                    <div class="flex justify-between items-center cursor-pointer" onclick="toggleChapter('chap3')">
                        <h3 class="text-lg sm:text-xl font-bold text-slate-800 flex items-center">
                            <span class="text-teal-700 mr-3">📌 第三章</span>
                            “生成-执行-反馈”闭环：隐秘压榨的硬件暗线
                        </h3>
                        <span class="text-stone-400 font-bold" id="chap3-arrow">▼</span>
                    </div>
                    <div class="mt-4 text-sm sm:text-base text-slate-600 space-y-4 hidden" id="chap3-content">
                        <p>
                            代码生成的动作转瞬即逝，但代码的运行是一直持续的。AI Agent要完成一个真实任务，其底层运作链路如下：
                        </p>
                        <p class="font-semibold text-slate-800">
                            “硬件压榨”三部曲：
                        </p>
                        <ul class="list-decimal pl-5 space-y-3 text-sm">
                            <li><strong class="text-slate-800">CPU 算力黑洞：</strong> 编译代码、安装依赖库、跑静态测试集（Linting）、运行单元测试，这些动作全部由<strong>CPU（而非GPU）</strong>执行。</li>
                            <li><strong class="text-slate-800">DRAM（内存）狂潮：</strong> 为防止AI生成危险或越权代码，每个Agent的运行都必须在一个个独立的虚拟化<strong>“安全沙箱”</strong>里。多开沙箱将直接吞噬系统内存，将云端服务器和本地 <strong>AI PC 内存门槛直接推向 32GB/64GB/128GB</strong>。</li>
                            <li><strong class="text-slate-850">消费电子与服务器双向拉动：</strong> 远端高密度 CPU/内存服务器集群（如24小时在线的Agent后台）需求飙升；同时本地开发终端也需要高算力CPU与超大内存，极大地拉动了办公消费电子（AI PC、工作站）的硬升级。</li>
                        </ul>
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 pt-6">
                <div class="bg-stone-50 p-6 rounded-2xl border border-stone-200">
                    <h4 class="font-bold text-center text-slate-800 mb-4 text-sm sm:text-base">AI 编程硬件市场新增预算结构占比预测</h4>
                    <div class="chart-container">
                        <canvas id="budgetChart"></canvas>
                    </div>
                    <script>
                        (function() {
                            var budgetCanvas = document.getElementById('budgetChart');
                            if (budgetCanvas && typeof Chart !== 'undefined') {
                                new Chart(budgetCanvas.getContext('2d'), {
                                    type: 'bar',
                                    data: {
                                        labels: ['GPU (模型推理与生成)', 'CPU (测试编译与容器部署)', 'DRAM 内存 (安全沙箱多开)', '端侧办公电脑 (AI PC 硬件替换)'],
                                        datasets: [{
                                            label: '新增算力预算份额分布预测 (%)',
                                            data: [45, 25, 20, 10],
                                            backgroundColor: [
                                                '#0F766E',
                                                '#D97706',
                                                '#14B8A6',
                                                '#6B7280'
                                            ],
                                            borderWidth: 0
                                        }]
                                    },
                                    options: {
                                        responsive: true,
                                        maintainAspectRatio: false,
                                        scales: {
                                            y: {
                                                beginAtZero: true,
                                                ticks: { callback: function(value) { return value + '%'; } }
                                            }
                                        }
                                    }
                                });
                            }
                        })();
                    </script>
                </div>
                <div class="bg-stone-50 p-6 rounded-2xl border border-stone-200">
                    <h4 class="font-bold text-center text-slate-800 mb-4 text-sm sm:text-base">云端大模型 Token 销售市场份额猜想</h4>
                    <div class="chart-container">
                        <canvas id="shareChart"></canvas>
                    </div>
                    <script>
                        (function() {
                            var shareCanvas = document.getElementById('shareChart');
                            if (shareCanvas && typeof Chart !== 'undefined') {
                                new Chart(shareCanvas.getContext('2d'), {
                                    type: 'pie',
                                    data: {
                                        labels: ['Anthropic (Claude 3.7+)', 'OpenAI (GPT-5/Codex)', '开源端侧小模型 (Llama/DeepSeek)', '其他垂直模型'],
                                        datasets: [{
                                            data: [35, 35, 20, 10],
                                            backgroundColor: ['#0F766E', '#14B8A6', '#D97706', '#94A3B8'],
                                            borderWidth: 1
                                        }]
                                    },
                                    options: {
                                        responsive: true,
                                        maintainAspectRatio: false,
                                        plugins: {
                                            legend: { position: 'bottom' }
                                        }
                                    }
                                });
                            }
                        })();
                    </script>
                </div>
            </div>
        </section>

        <section id="sandbox" class="bg-white rounded-3xl p-6 sm:p-10 border border-stone-200 shadow-sm space-y-8">
            <div class="border-b border-stone-100 pb-4">
                <h2 class="text-2xl font-bold text-slate-900">🔬 交互演示：代码运行沙盒的硬件资源压榨</h2>
                <p class="text-sm text-slate-500 mt-1">
                    AI编程不仅仅是在键盘上敲代码。观察下方AI Agent在后台调试时的四步物理闭环，点击不同节点查看云端/本地端硬件承受的负荷变动：
                </p>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-12 gap-8">
                <div class="lg:col-span-5 space-y-3" id="sandbox-selectors">
                    <div onclick="selectSandboxStep(1)" id="step-btn-1" class="p-4 border-2 border-stone-200 rounded-xl cursor-pointer transition-all step-active hover:border-teal-600">
                        <span class="block font-bold text-teal-850 text-sm">Step 1: GPU 推理（代码生成）</span>
                        <span class="block text-xs text-slate-500 mt-1">调用千亿模型生成长上下文，消耗Token。</span>
                    </div>
                    <div onclick="selectSandboxStep(2)" id="step-btn-2" class="p-4 border-2 border-stone-200 rounded-xl cursor-pointer transition-all hover:border-teal-600">
                        <span class="block font-bold text-teal-850 text-sm">Step 2: 容器/安全沙箱部署</span>
                        <span class="block text-xs text-slate-500 mt-1">创建高度隔离的安全执行环境，防止恶意或错误代码外泄。</span>
                    </div>
                    <div onclick="selectSandboxStep(3)" id="step-btn-3" class="p-4 border-2 border-stone-200 rounded-xl cursor-pointer transition-all hover:border-teal-600">
                        <span class="block font-bold text-teal-850 text-sm">Step 3: CPU编译与运行测试</span>
                        <span class="block text-xs text-slate-500 mt-1">高频运行单元测试与依赖安装，瞬间压榨系统内存。</span>
                    </div>
                    <div onclick="selectSandboxStep(4)" id="step-btn-4" class="p-4 border-2 border-stone-200 rounded-xl cursor-pointer transition-all hover:border-teal-600">
                        <span class="block font-bold text-teal-850 text-sm">Step 4: 日志报错捕获反馈</span>
                        <span class="block text-xs text-slate-500 mt-1">报错堆栈收集，反馈给模型开启下一轮优化调试。</span>
                    </div>
                </div>

                <div class="lg:col-span-7 bg-stone-50 rounded-2xl p-6 border border-stone-200 flex flex-col justify-between">
                    <div class="space-y-6">
                        <h4 class="font-bold text-lg text-slate-900 border-b border-stone-200 pb-2">
                            🔍 物理负荷监测：<span id="sb-title" class="text-teal-750">Step 1: GPU 推理（代码生成）</span>
                        </h4>
                        
                        <div class="grid grid-cols-2 gap-4">
                            <div class="bg-white p-4 rounded-xl border border-stone-200">
                                <span class="text-xs text-slate-400 block font-semibold">云端/数据中心硬件负荷</span>
                                <p class="text-base sm:text-lg font-bold text-slate-800 mt-1" id="sb-dc">GPU H100 / Blackwell 负载达 95%</p>
                            </div>
                            <div class="bg-white p-4 rounded-xl border border-stone-200">
                                <span class="text-xs text-slate-400 block font-semibold">个人AI PC/消费电子负荷</span>
                                <p class="text-base sm:text-lg font-bold text-slate-800 mt-1" id="sb-pc">NPU/本地大显存芯片高负荷</p>
                            </div>
                        </div>

                        <div class="space-y-2">
                            <span class="text-xs font-bold text-teal-700 uppercase">底层硬件压榨逻辑说明</span>
                            <p class="text-sm text-slate-600 leading-relaxed" id="sb-desc">
                                此阶段的瓶颈纯粹在于大模型的吐出速率。由于编程需要处理长篇项目架构（100k+ Tokens），因此极大放大了对高频、大容量 HBM3E 内存及超大规模高性能推理服务器集群的需求。
                            </p>
                        </div>
                    </div>
                    <span class="text-xs text-slate-400 block border-t border-stone-200 pt-3 mt-4">
                        💡 逻辑推演：代码生成的动作极快，但执行调试可能维持24小时，这表明对 CPU 和 DRAM 内存的常态负载远高于 GPU。
                    </span>
                </div>
            </div>
        </section>

        <section id="portfolio" class="bg-white rounded-3xl p-6 sm:p-10 border border-stone-200 shadow-sm space-y-8">
            <div class="border-b border-stone-100 pb-4">
                <h2 class="text-2xl font-bold text-slate-900">📊 核心选股矩阵：稳定确定性 vs 高赔率弹性</h2>
                <p class="text-sm text-slate-500 mt-1">
                    通过投资风险偏好与物理产业链角色，筛选符合您交易风格的美股和A股标的：
                </p>
            </div>

            <div class="flex flex-col md:flex-row gap-4 justify-between items-start md:items-center">
                <div class="flex flex-wrap gap-2">
                    <button onclick="filterStocks('all')" id="btn-all" class="px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg active-tab transition-all">
                        🌍 全部标的
                    </button>
                    <button onclick="filterStocks('certainty')" id="btn-certainty" class="px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg bg-stone-100 text-slate-700 hover:bg-stone-200 transition-all">
                        🛡️ 确定性收益 (高概率/白马)
                    </button>
                    <button onclick="filterStocks('elasticity')" id="btn-elasticity" class="px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg bg-stone-100 text-slate-700 hover:bg-stone-200 transition-all">
                        🚀 高弹性爆点 (高赔率/高波动)
                    </button>
                </div>
                <select id="market-select" onchange="applyMarketFilter()" class="border border-stone-300 rounded-lg p-2 text-xs sm:text-sm bg-white font-semibold text-slate-700">
                    <option value="all">所有市场 (美股+A股)</option>
                    <option value="us">仅看美股</option>
                    <option value="ashare">仅看A股</option>
                </select>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" id="portfolio-grid">
            </div>
            <script>
                (function() {
                    var grid = document.getElementById('portfolio-grid');
                    if (grid && typeof renderStockGrid !== 'undefined') {
                        renderStockGrid();
                    }
                })();
            </script>
        </section>
    </main>

    <footer class="bg-slate-900 text-stone-300 py-12 mt-20">
        <div class="max-w-7xl mx-auto px-4 text-center space-y-4">
            <p class="text-sm text-stone-400">AI编程全生态与算力硬件投资研报 1.0 版 · 深度策略专供</p>
            <p class="text-xs text-stone-500">
                本研报所提供之所有行业分析、逻辑推演以及具体标的推荐仅供学术与行业研究交流。投资者在根据此框架进行实盘操作前，请务必结合自身的风险承受能力及深入的财务审计进行决策。
            </p>
        </div>
    </footer>

    <script>
        function toggleChapter(id) {
            const content = document.getElementById(id + '-content');
            const arrow = document.getElementById(id + '-arrow');
            if (content.classList.contains('hidden')) {
                content.classList.remove('hidden');
                arrow.innerText = '▲';
            } else {
                content.classList.add('hidden');
                arrow.innerText = '▼';
            }
        }

        toggleChapter('chap1');
        toggleChapter('chap3');

        const sandboxData = {
            1: {
                title: "Step 1: GPU 推理（代码生成）",
                dc: "GPU H100 / Blackwell 负载达 95%",
                pc: "端侧 NPU/本地显卡阶段性极高并发",
                desc: "AI编程Agent发出长Prompt，由高单价的大型云端集群进行解答。此阶段高度利好大模型提供商（OpenAI/Anthropic）和独家算力基建运营商，直接推动高并发ASIC和高带宽HBM内存的需求放量。"
            },
            2: {
                title: "Step 2: 容器与安全虚拟化部署",
                dc: "数据中心多核 CPU 占有率提升 40%",
                pc: "AI PC 内存占用瞬间激增 8-16 GB",
                desc: "为了防止代码注入和系统级恶意代码逃逸，每个Agent必须运行在一个独立的安全沙箱（Docker容器/虚拟机）中。这需要云端高密度服务器CPU快速部署，在端侧则要求普通开发PC拥有巨大的系统内存容量以满足多开虚拟机沙箱。"
            },
            3: {
                title: "Step 3: CPU 编译、环境配置与测试运行",
                dc: "云端服务器 CPU 线程100%跑满",
                pc: "本地 CPU 满载 / 风扇狂飙",
                desc: "编译代码、加载底层依赖包、运行成百上千个单元自动化测试程序。大模型GPU在此阶段完全处于空闲状态，所有的压力全部倒灌回<strong>多核心 CPU 以及高速 DRAM 内存系统</strong>。云端常驻运行极度压榨云主机的持续资源，本地运行直接激发 AI PC 换代。"
            },
            4: {
                title: "Step 4: 编译错误捕获与闭环反馈",
                dc: "高速 800G 光模块 / 交换机满载网络连接",
                pc: "本地 Wi-Fi 7 网络高频率收发",
                desc: "测试报错日志被实时收集，整理成堆栈信息后，瞬间回传给大模型。因为大语言模型需要再次读取这万级Token的报错进行重构生成，这就极大地考验数据中心内部网络架构（光模块/核心交换）以及终端的高频收发时延。"
            }
        };

        function selectSandboxStep(stepNum) {
            const btns = document.querySelectorAll('#sandbox-selectors > div');
            btns.forEach(btn => btn.classList.remove('step-active', 'border-teal-600'));
            document.getElementById('step-btn-' + stepNum).classList.add('step-active', 'border-teal-600');

            const data = sandboxData[stepNum];
            document.getElementById('sb-title').innerText = data.title;
            document.getElementById('sb-dc').innerText = data.dc;
            document.getElementById('sb-pc').innerText = data.pc;
            document.getElementById('sb-desc').innerHTML = data.desc;
        }

        const stockData = [
            {
                name: "微软 (Microsoft)",
                ticker: "MSFT.US",
                type: "certainty",
                market: "us",
                tags: ["B2B 订阅王者", "Office大礼包"],
                desc: "【高确定性收益】垄断OpenAI商业化出口。AI编程Agent是高价值高壁垒工具，企业买单确定性极高。微软凭借庞大的企业销售渠道，拥有全行业最宽广的收费桥头堡。"
            },
            {
                name: "亚马逊 (AWS)",
                ticker: "AMZN.US",
                type: "certainty",
                market: "us",
                tags: ["Claude 唯一指定云", "自研推理芯"],
                desc: "【高确定性收益】作为Anthropic（Claude）的核心战投者，AWS云不仅出售高单价Claude Token，更是企业云端大规模编译沙箱后台的绝对算力垄断者。"
            },
            {
                name: "英伟达 (NVIDIA)",
                ticker: "NVDA.US",
                type: "certainty",
                market: "us",
                tags: ["推理加速至尊", "Blackwell生态"],
                desc: "【高确定性收益】推理时代的大底座。由于AI编程长文本处理和持续生成特性，虽然CPU跑编译，但高阶推理和实时长上下文计算依然严重依赖英伟达Blackwell生态。"
            },
            {
                name: "美光科技 (Micron)",
                ticker: "MU.US",
                type: "certainty",
                market: "us",
                tags: ["DRAM 内存大繁荣", "AI PC 换代"],
                desc: "【高确定性收益】由于代码Agent需要不间断沙箱多开运行，物理内存（DRAM）需求正急剧膨胀。从云端到本地办公设备，大内存成为必然趋势，美光弹性极大。"
            },
            {
                name: "博通 (Broadcom)",
                ticker: "AVGO.US",
                type: "certainty",
                market: "us",
                tags: ["大厂自研芯片IP", "高速网络互联"],
                desc: "【高确定性收益】为降低高频高负荷推理的Token单单价，互联网巨头纷纷自研ASIC推理卡。博通作为全球最顶尖的ASIC协同设计霸主，直接锁定云巨头算力底座。"
            },
            {
                name: "海光信息",
                ticker: "688041.SH",
                type: "certainty",
                market: "ashare",
                tags: ["国产 CPU 白马", "高兼容x86生态"],
                desc: "【高确定性收益】国内大模型私有云部署与编译测试不可绕开的算力主梁。其深算系列高度兼容x86和CUDA，在信创和国企研发闭环中拥有绝对壁垒。"
            },
            {
                name: "超威半导体 (AMD)",
                ticker: "AMD.US",
                type: "elasticity",
                market: "us",
                tags: ["EPYC 高核 CPU", "MI300X 替代者"],
                desc: "【高弹性/高赔率】极度受益于“编译执行闭环”。其高线程、高核心数的云端 EPYC 处理器在容器部署和编译测试中弹性极大，同时MI300X大显存优势在推理端具备极强爆发力。"
            },
            {
                name: "寒武纪",
                ticker: "688256.SH",
                type: "elasticity",
                market: "ashare",
                tags: ["国产推理弹性王", "思元芯片"],
                desc: "【高弹性/高赔率】如果国内AI Agent及国产AI编程套件实现爆发，寒武纪将成为国产生态链条中最具弹性的推理加速卡黑马，股价高赔率属性极强。"
            },
            {
                name: "金山办公 (WPS)",
                ticker: "688111.SH",
                type: "certainty",
                market: "ashare",
                tags: ["办公/集成开发套件", "订阅变现先锋"],
                desc: "【高确定性收益】A股最纯粹的企业SaaS买单典范。WPS AI在协作文档与高频商业场景中的变现逻辑已闭环，是国内最先尝到AI订阅大包套餐甜头的企业。"
            },
            {
                name: "红帽/IBM (IBM)",
                ticker: "IBM.US",
                type: "elasticity",
                market: "us",
                tags: ["OpenShift 容器隔离", "沙箱安全"],
                desc: "【高弹性/高赔率】当数以亿计的代码Agent全天候自动在后台编译运行时，虚拟机越权与隔离防护对红帽（OpenShift）和安全软件提出了前所未有的暴增诉求。"
            }
        ];

        let currentTypeFilter = 'all';

        function renderStockGrid() {
            const grid = document.getElementById('portfolio-grid');
            grid.innerHTML = '';
            const marketSel = document.getElementById('market-select').value;

            const filtered = stockData.filter(item => {
                const matchesType = currentTypeFilter === 'all' || item.type === currentTypeFilter;
                const matchesMarket = marketSel === 'all' || item.market === marketSel;
                return matchesType && matchesMarket;
            });

            filtered.forEach(stock => {
                const typeStyle = stock.type === 'certainty' 
                    ? 'bg-teal-50 text-teal-800 border-teal-200' 
                    : 'bg-amber-50 text-amber-800 border-amber-250';
                const typeLabel = stock.type === 'certainty' ? '🛡️ 确定性稳健收益' : '🚀 高弹性高赔率';

                const card = document.createElement('div');
                card.className = "bg-white border border-stone-200 rounded-2xl p-5 hover:shadow-lg transition-all flex flex-col justify-between h-full space-y-4";
                card.innerHTML = `
                    <div class="space-y-3">
                        <div class="flex justify-between items-start">
                            <div>
                                <h4 class="font-extrabold text-slate-900 text-lg">${stock.name}</h4>
                                <span class="text-xs font-mono font-bold text-teal-700 tracking-wider bg-stone-100 px-2 py-0.5 rounded">${stock.ticker}</span>
                            </div>
                            <span class="text-xs font-bold px-2 py-1 border rounded-lg ${typeStyle}">
                                ${typeLabel}
                            </span>
                        </div>
                        <div class="flex flex-wrap gap-1.5">
                            ${stock.tags.map(t => `<span class="px-2 py-0.5 bg-stone-100 text-stone-600 text-xs rounded border border-stone-200">${t}</span>`).join('')}
                        </div>
                        <p class="text-xs sm:text-sm text-slate-600 leading-relaxed pt-2">
                            ${stock.desc}
                        </p>
                    </div>
                `;
                grid.appendChild(card);
            });
        }

        function filterStocks(type) {
            currentTypeFilter = type;
            const btns = document.querySelectorAll('#screener-buttons, .flex > button');
            btns.forEach(btn => {
                if (btn.id === 'btn-' + type) {
                    btn.classList.add('active-tab');
                    btn.classList.remove('bg-stone-100', 'text-slate-700');
                } else if (btn.id && btn.id.startsWith('btn-')) {
                    btn.classList.remove('active-tab');
                    btn.classList.add('bg-stone-100', 'text-slate-700');
                }
            });
            renderStockGrid();
        }

        function applyMarketFilter() {
            renderStockGrid();
        }
    </script>
</body>
</html>
    """
    from pywebio.output import put_html
    put_html(html_content)


def alab_investment_sandbox_page():
    """Astera Labs (ALAB) 专题分析：AI Agent 时代的连接芯片霸主"""
    html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Astera Labs (ALAB) 专题分析：AI Agent 时代的连接芯片霸主</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .chart-container { 
            position: relative; 
            width: 100%; 
            max-width: 800px; 
            margin-left: auto; 
            margin-right: auto; 
            height: 35vh; 
            max-height: 350px; 
            min-height: 250px;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #FAF9F6; 
            color: #0F172A;
        }
        .active-btn {
            background-color: #0D9488;
            color: white;
            border-color: #0D9488;
        }
    </style>
</head>
<body class="antialiased">

    <nav class="sticky top-0 bg-white/95 backdrop-blur shadow-sm z-50 border-b border-stone-200">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between h-16 items-center">
                <div class="flex items-center space-x-2">
                    <span class="text-2xl">⚡</span>
                    <span class="font-bold text-lg text-teal-850">Astera Labs (ALAB) 投资决策沙盘</span>
                </div>
                <div class="hidden md:flex space-x-6 text-sm font-medium text-slate-600">
                    <a href="#bottleneck" class="hover:text-teal-600 transition-colors">协同瓶颈</a>
                    <a href="#simulator" class="hover:text-teal-600 transition-colors">连接模拟器</a>
                    <a href="#products" class="hover:text-teal-600 transition-colors">核心产品线</a>
                    <a href="#investment" class="hover:text-teal-600 transition-colors">投资评级</a>
                </div>
            </div>
        </div>
    </nav>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-16">

        <!-- Intro -->
        <header class="text-center space-y-4 max-w-4xl mx-auto">
            <span class="px-3 py-1 bg-teal-50 text-teal-700 text-xs font-semibold rounded-full border border-teal-200 uppercase tracking-widest">ALAB Special Report</span>
            <h1 class="text-3xl sm:text-4xl md:text-5xl font-black text-slate-950 leading-tight">
                解密 Astera Labs：打通 <span class="text-teal-600">GPU 与 CPU</span> 高频协同的“高速路网”
            </h1>
            <p class="text-base sm:text-lg text-slate-600 leading-relaxed">
                你的直觉完全正确！在 AI Agent 持续“生成-执行-反馈”的闭环中，数据不能拥堵在总线上。Astera Labs (ALAB) 凭借其在 <strong>PCIe 5.0/6.0 Retimer</strong> 和 <strong>CXL 内存扩展</strong> 芯片的绝对垄断，成为了算力重构中最高确定性的“修路人”。
            </p>
        </header>

        <!-- Bottleneck Section -->
        <section id="bottleneck" class="bg-white rounded-3xl p-6 sm:p-10 border border-stone-200 shadow-sm space-y-8">
            <div class="border-b border-stone-100 pb-4">
                <h2 class="text-2xl font-bold text-slate-900">1. 为什么 GPU 和 CPU 协同需要 PCIe / CXL 连接？</h2>
                <p class="text-sm text-slate-500 mt-1">剖析 AI Agent 运行时的隐性物理瓶颈：数据高速公路的“修路逻辑”</p>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div class="p-6 bg-stone-50 rounded-2xl border border-stone-100 space-y-2">
                    <span class="text-2xl">🚗</span>
                    <h3 class="font-bold text-slate-800">总线拥堵：Gen 5/6 物理限制</h3>
                    <p class="text-sm text-slate-600">当 GPU 将生成的代码传给 CPU 编译时，数据通过 PCIe 通道传输。由于物理信号在高频下衰减极快，传输距离只要超过几厘米，信号就会失真失锁。这就需要 <strong>Retimer（重定时器）芯片</strong> 来放大和修复信号。</p>
                </div>
                <div class="p-6 bg-stone-50 rounded-2xl border border-stone-100 space-y-2">
                    <span class="text-2xl">🧠</span>
                    <h3 class="font-bold text-slate-800">CXL 内存池化：消灭“内存墙”</h3>
                    <p class="text-sm text-slate-600">CPU 在沙箱里编译运行需要极高内存，而 GPU 需要 HBM。CXL 技术允许 CPU 直接借用和共享 GPU 端的内存空间。ALAB 的 CXL 控制器芯片是实现这种“零延迟内存共享”的关键桥梁。</p>
                </div>
                <div class="p-6 bg-stone-50 rounded-2xl border border-stone-100 space-y-2">
                    <span class="text-2xl">💎</span>
                    <h3 class="font-bold text-slate-800">单机芯用量暴增</h3>
                    <p class="text-sm text-slate-600">在英伟达 Blackwell 架构或下一代超大型推理机柜中，由于芯片密度极高、走线极长，每台服务器需要的 PCIe Retimer 芯片数量相比上一代 Hopper 呈现翻倍增长，物理单价也在大幅提升。</p>
                </div>
            </div>
        </section>

        <!-- Connectivity Simulator Section (Interactive Sandbox) -->
        <section id="simulator" class="bg-white rounded-3xl p-6 sm:p-10 border border-stone-200 shadow-sm space-y-8">
            <div class="border-b border-stone-100 pb-4">
                <h2 class="text-2xl font-bold text-slate-900">💻 交互模拟：GPU-CPU 传输延迟与信号质量对比</h2>
                <p class="text-sm text-slate-500 mt-1">切换下方硬件通道配置，直观查看在 AI Agent 频繁的“代码生成 ➡️ 编译执行”中，有无 ALAB 重定时芯片对系统效率的决定性影响：</p>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-12 gap-8">
                <!-- Control Panel (Left) -->
                <div class="lg:col-span-4 flex flex-col justify-between space-y-4">
                    <div class="space-y-3">
                        <label class="block text-xs font-bold text-slate-500 uppercase">选择总线连接方案</label>
                        <button onclick="toggleRoute(false)" id="btn-no-retimer" class="w-full text-left p-4 border-2 border-stone-200 rounded-xl active-btn font-semibold text-sm transition-all">
                            ❌ 无 Retimer 芯片（传统长铜线走线）
                        </button>
                        <button onclick="toggleRoute(true)" id="btn-with-retimer" class="w-full text-left p-4 border-2 border-stone-200 rounded-xl font-semibold text-sm transition-all">
                            ✅ 搭载 ALAB Aries PCIe 5.0/6.0 Retimer
                        </button>
                    </div>

                    <div class="bg-stone-50 p-4 rounded-xl border border-stone-200 space-y-3">
                        <div class="flex justify-between text-xs">
                            <span class="text-slate-500 font-semibold">物理信号完整性:</span>
                            <span id="stat-signal" class="font-bold text-rose-600">极差 (容易丢包报错)</span>
                        </div>
                        <div class="flex justify-between text-xs">
                            <span class="text-slate-500 font-semibold">GPU-CPU 协同延迟:</span>
                            <span id="stat-latency" class="font-bold text-rose-600">180 ns (存在二次握手重发)</span>
                        </div>
                        <div class="flex justify-between text-xs">
                            <span class="text-slate-500 font-semibold">Agent 编译执行效率:</span>
                            <span id="stat-efficiency" class="font-bold text-rose-600">折损 35%</span>
                        </div>
                    </div>
                </div>

                <!-- Visualization Panel (Right) -->
                <div class="lg:col-span-8 bg-slate-950 text-white rounded-2xl p-6 flex flex-col justify-between relative min-h-[300px]">
                    <span class="absolute top-3 right-3 text-[10px] font-mono text-teal-400 uppercase tracking-widest font-bold">硬件拓扑实效演示</span>
                    
                    <div class="space-y-8 w-full mt-4">
                        <!-- Simulated Block Diagram (Pure HTML/CSS) -->
                        <div class="flex items-center justify-between px-4">
                            <!-- GPU -->
                            <div class="bg-teal-900 border border-teal-500 px-4 py-3 rounded-xl text-center shadow-md w-24">
                                <span class="block text-xs text-teal-300 font-bold">GPU</span>
                                <span class="block text-[10px] text-teal-100">代码生成</span>
                            </div>

                            <!-- Interconnect line with dynamic status -->
                            <div class="flex-grow mx-4 relative h-2 bg-slate-800 rounded">
                                <div id="flow-line" class="absolute top-0 left-0 h-full bg-rose-500 w-1/3 transition-all duration-700"></div>
                                <div id="chip-node" class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-slate-700 border border-slate-600 w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-bold transition-all">
                                    ❌
                                </div>
                            </div>

                            <!-- CPU -->
                            <div class="bg-slate-800 border border-slate-600 px-4 py-3 rounded-xl text-center shadow-md w-24">
                                <span class="block text-xs text-stone-300 font-bold">CPU</span>
                                <span class="block text-[10px] text-stone-400">沙箱编译</span>
                            </div>
                        </div>

                        <!-- Explanatory description -->
                        <div class="bg-slate-900 p-4 rounded-xl border border-slate-800">
                            <h4 id="desc-title" class="text-sm font-bold text-rose-400 mb-1">物理红线：高频走线带来的高延迟与信号反射</h4>
                            <p id="desc-text" class="text-xs text-slate-400 leading-relaxed">
                                当不使用 Retimer 芯片时，PCIe 5.0/6.0 的高频信号在长PCB走线中迅速耗散，产生巨大的电磁反射和通道串扰。CPU在编译运行代码时需要频繁向GPU申请重发数据包，延迟急剧上升，严重拖累 Agent 运行效率。
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Products Section -->
        <section id="products" class="bg-white rounded-3xl p-6 sm:p-10 border border-stone-200 shadow-sm space-y-8">
            <div class="border-b border-stone-100 pb-4">
                <h2 class="text-2xl font-bold text-slate-900">2. Astera Labs 的“连接芯片三驾马车”</h2>
                <p class="text-sm text-slate-500 mt-1">透视 ALAB 在 AI 服务器中无可替代的芯片级产品矩阵：</p>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div class="border border-stone-200 rounded-2xl p-6 space-y-4 hover:shadow-md transition-all">
                    <div class="flex items-center space-x-2">
                        <span class="px-2 py-1 bg-teal-50 text-teal-700 text-xs font-bold rounded">Aries 系列</span>
                        <h3 class="font-bold text-slate-800 text-base">PCIe Retimer 芯片</h3>
                    </div>
                    <p class="text-xs sm:text-sm text-slate-600 leading-relaxed">
                        **ALAB 的超级印钞机**。在英伟达、超威（AMD）、谷歌等大厂的加速卡机架上，Aries 是出货量最大、市占率极高的 PCIe 5.0/6.0 信号重定时器，牢牢卡位最核心的信号中继节点。
                    </p>
                </div>
                
                <div class="border border-stone-200 rounded-2xl p-6 space-y-4 hover:shadow-md transition-all">
                    <div class="flex items-center space-x-2">
                        <span class="px-2 py-1 bg-amber-50 text-amber-700 text-xs font-bold rounded">Leo 系列</span>
                        <h3 class="font-bold text-slate-800 text-base">CXL 内存扩展控制器</h3>
                    </div>
                    <p class="text-xs sm:text-sm text-slate-600 leading-relaxed">
                        **打通 CPU-GPU 共享物理内存的钥匙**。Leo 芯片能让 CPU 顺畅读写 GPU 显存，反之亦然，大幅拓宽系统级 DRAM 瓶颈，是未来万亿参数闭环推理必不可少的算力总线硬件。
                    </p>
                </div>

                <div class="border border-stone-200 rounded-2xl p-6 space-y-4 hover:shadow-md transition-all">
                    <div class="flex items-center space-x-2">
                        <span class="px-2 py-1 bg-sky-50 text-sky-700 text-xs font-bold rounded">Taurus 系列</span>
                        <h3 class="font-bold text-slate-800 text-base">有源电缆 (AEC) 芯片</h3>
                    </div>
                    <p class="text-xs sm:text-sm text-slate-600 leading-relaxed">
                        **机柜之间的高速网络连接**。在超大规模 AI 机群部署中，传统的无源铜线拉不远，光模块成本太贵，Taurus 有源电缆控制芯片完美解决了数据中心内部的高速传输成本。
                    </p>
                </div>
            </div>
        </section>

        <!-- Investment Value Ratings Section -->
        <section id="investment" class="bg-white rounded-3xl p-6 sm:p-10 border border-stone-200 shadow-sm space-y-8">
            <div class="border-b border-stone-100 pb-4">
                <h2 class="text-2xl font-bold text-slate-900">3. 投资价值判定：胜率（确定性） vs 赔率（高弹性）</h2>
                <p class="text-sm text-slate-500 mt-1">基于我们前期的“选股矩阵框架”，对 Astera Labs 进行深度的多维度定量和定性评级：</p>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <!-- Bull/Bear Case -->
                <div class="space-y-4">
                    <h3 class="font-bold text-slate-800 text-base border-l-4 border-teal-600 pl-3">核心多空博弈观点</h3>
                    <div class="space-y-3 text-xs sm:text-sm text-slate-600">
                        <div class="bg-teal-50/50 p-4 rounded-xl border border-teal-100">
                            <strong class="text-teal-900 block mb-1">👍 胜率（确定性白马）逻辑：</strong>
                            由于 AI 硬件设计的物理铁律，信号衰减不可逆。不管未来是 Anthropic 赢还是 OpenAI 赢，只要加速卡部署数量提升，对高速 PCIe Retimer 的刚需就呈几何级倍增。ALAB 拥有极高的毛利率（超过70%），且深度绑定英伟达 Blackwell 供应链。
                        </div>
                        <div class="bg-amber-50/50 p-4 rounded-xl border border-amber-100">
                            <strong class="text-amber-900 block mb-1">⚠️ 赔率与估值波动风险：</strong>
                            因为市场对 ALAB 预期极高，其估值溢价（市盈率/市销率）相较于普通芯片股处于绝对高位。一旦英伟达 Blackwell 出货节奏出现细微波动，或者出现澜起科技等国产芯片、以及德州仪器（TI）等巨头的剧烈竞争，股价波动弹性极大。
                        </div>
                    </div>
                </div>

                <!-- ALAB Chart Valuation -->
                <div class="bg-stone-50 p-6 rounded-2xl border border-stone-200 flex flex-col justify-between">
                    <div>
                        <h4 class="font-bold text-slate-800 text-sm sm:text-base text-center mb-4">ALAB 的三大业绩爆发催化剂</h4>
                        <div class="chart-container">
                            <canvas id="alabChart"></canvas>
                        </div>
                    </div>
                    <p class="text-xs text-stone-500 text-center mt-3">
                        * 数据表明：伴随英伟达 Blackwell 架构放量，PCIe Gen6 Retimer（Aries）已成为拉动 ALAB 下一轮营收翻倍的最核心引擎。
                    </p>
                </div>
            </div>

            <!-- Conclusion Matrix Card -->
            <div class="bg-slate-900 text-white rounded-2xl p-6 sm:p-10 space-y-4">
                <h3 class="font-bold text-lg sm:text-xl text-teal-400">📊 终局投资判定：将 ALAB 加入你的战略配置池</h3>
                <p class="text-sm text-slate-300 leading-relaxed">
                    在我们的AI编程选股图谱中，我们将 <strong>Astera Labs (ALAB)</strong> 定位为：<strong>【高确定性（高胜率）底层硬基建，兼具 Blackwell 高弹性释放】</strong> 标的。
                </p>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2 text-xs">
                    <div class="border-l-2 border-teal-500 pl-4 space-y-1">
                        <span class="font-bold text-teal-300">入选理由：</span>
                        <p class="text-slate-400">它是完美解决 GPU 与 CPU 进行 24 小时沙盒编译时，所产生的 PCIe 通信拥堵的唯一高门槛芯片大厂。毛利极高、成长天花板极高。</p>
                    </div>
                    <div class="border-l-2 border-amber-500 pl-4 space-y-1">
                        <span class="font-bold text-amber-300">建仓策略：</span>
                        <p class="text-slate-400">鉴于其高成长带来的高估值，不建议单次全仓追高。推荐采取“逢 Blackwell 供应链利空回调分批买入”的建仓策略，作为长期享受 AI 推理及物理连接瓶颈爆发红利的核心筹码。</p>
                    </div>
                </div>
            </div>
        </section>

    </main>

    <footer class="bg-slate-900 text-stone-400 py-12 border-t border-slate-800 text-center text-xs space-y-2">
        <p>Astera Labs (ALAB) 专题投资研究沙盘 1.0 版</p>
        <p class="text-stone-500">免责声明：本报告由AI自动计算物理模型与逻辑链生成，标的仅供逻辑和学术讨论。证券交易存在高风险，请谨慎决策。</p>
    </footer>

    <script>
        // Interactive Toggle logic
        function toggleRoute(hasRetimer) {
            const btnNo = document.getElementById('btn-no-retimer');
            const btnWith = document.getElementById('btn-with-retimer');
            const flowLine = document.getElementById('flow-line');
            const chipNode = document.getElementById('chip-node');
            
            const statSignal = document.getElementById('stat-signal');
            const statLatency = document.getElementById('stat-latency');
            const statEfficiency = document.getElementById('stat-efficiency');
            
            const descTitle = document.getElementById('desc-title');
            const descText = document.getElementById('desc-text');

            if (hasRetimer) {
                btnNo.classList.remove('active-btn');
                btnWith.classList.add('active-btn');
                
                // Flow line active animation
                flowLine.style.width = '100%';
                flowLine.className = "absolute top-0 left-0 h-full bg-teal-500 transition-all duration-700";
                chipNode.innerText = "⚡";
                chipNode.className = "absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-teal-600 border border-teal-400 w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-bold transition-all animate-pulse";
                
                // Stats
                statSignal.innerText = "极佳 (误码率降至 1e-12 级别)";
                statSignal.className = "font-bold text-teal-600";
                statLatency.innerText = "80 ns (无重发抖动)";
                statLatency.className = "font-bold text-teal-600";
                statEfficiency.innerText = "完全释放 100%";
                statEfficiency.className = "font-bold text-teal-600";
                
                // Desc
                descTitle.innerText = "物理奇迹：通过 Aries Retimer 芯片重构清洁信号";
                descTitle.className = "text-sm font-bold text-teal-400 mb-1";
                descText.innerText = "搭载 ALAB 的 Aries 芯片后，处于总线中点处的高频衰减信号被成功解码并重新定时发射，误码率趋近于零。GPU可以无缝、最高速地向CPU沙箱投递待测试代码，将 AI Agent 闭环逻辑编译时间缩短 35% 以上。";

            } else {
                btnWith.classList.remove('active-btn');
                btnNo.classList.add('active-btn');
                
                // Flow line bad state
                flowLine.style.width = '35%';
                flowLine.className = "absolute top-0 left-0 h-full bg-rose-500 transition-all duration-700";
                chipNode.innerText = "❌";
                chipNode.className = "absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-slate-700 border border-slate-600 w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-bold transition-all";
                
                // Stats
                statSignal.innerText = "极差 (容易丢包报错)";
                statSignal.className = "font-bold text-rose-600";
                statLatency.innerText = "180 ns (存在二次握手重发)";
                statLatency.className = "font-bold text-rose-600";
                statEfficiency.innerText = "折损 35%";
                statEfficiency.className = "font-bold text-rose-600";
                
                // Desc
                descTitle.innerText = "物理红线：高频走线带来的高延迟与信号反射";
                descTitle.className = "text-sm font-bold text-rose-400 mb-1";
                descText.innerText = "当不使用 Retimer 芯片时，PCIe 5.0/6.0 的高频信号在长PCB走线中迅速耗散，产生巨大的电磁反射和通道串扰。CPU在编译运行代码时需要频繁向GPU申请重发数据包，延迟急剧上升，严重拖累 Agent 运行效率。";
            }
        }

        // Initialize alab chart
        document.addEventListener('DOMContentLoaded', function() {
            const alabCtx = document.getElementById('alabChart');
            if (alabCtx && alabCtx.getContext) {
                const ctx = alabCtx.getContext('2d');
                new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: ['PCIe 5.0 渗透放量', 'Blackwell 芯片高密度组网', 'CXL (Leo) 内存扩展破局'],
                        datasets: [{
                            label: '营收拉动增长权重指数 (%)',
                            data: [50, 35, 15],
                            backgroundColor: ['#0D9488', '#14B8A6', '#D97706'],
                            borderWidth: 0
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                max: 60,
                                ticks: { callback: value => value + '%' }
                            }
                        }
                    }
                });
            }
        });
    </script>
</body>
</html>
    """
    from pywebio.output import put_html
    put_html(html_content)

