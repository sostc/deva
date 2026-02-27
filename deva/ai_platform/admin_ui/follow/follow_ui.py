"""Follow UI module for managing topics and people."""

from __future__ import annotations

# 从main_ui导入render_llm_config_guide函数
from ..main_ui import render_llm_config_guide


async def render_follow_ui(ctx):
    await ctx["init_admin_ui"]("Deva 关注管理")
    ctx["init_floating_menu_manager"](ctx)
    ctx["set_table_style"]()
    ctx["apply_global_styles"]()
    render_llm_config_guide(ctx)  # 重新启用函数调用

    topics = ctx["NB"]("topics").items()
    peoples = ctx["NB"]("people").items()
    
    ctx["put_html"]('<div class="card"><div class="card-title">🎯 焦点分析</div>')
    
    people_table = [["人物", "描述", "操作"]]

    async def analyze_person(key, value):
        person = key
        action = "并将他的观点总结成几行经典的名言名句"
        full_prompt = f"获取关于{person}的最新6条新闻，要求返回的内容每一行都是一个一句话新闻，开头用一个和内容对应的图标，然后是一个不大于十个字的高度浓缩概括词，概括词用加粗字体，最后后面是新闻的一句话摘要，用破折号区隔开。每行一个新闻，不要有标题等其他任何介绍性内容，每行结尾也不要有类似[^2^]这样的引用标识，只需要返回6 条新闻即可。在新闻的最后面，总附加要求如下：{action}"
        async def async_content_func(session, scope):
            return await ctx["get_gpt_response"](prompt=full_prompt, session=session, scope=scope, model_type="kimi")
        ctx["run_async"](ctx["dynamic_popup"](title=f"人物分析: {key}", async_content_func=async_content_func))

    for key, value in peoples:
        actions = ctx["put_button"]("🔍 分析", onclick=lambda k=key, v=value: ctx["run_async"](analyze_person(k, v)))
        people_table.append([ctx["truncate"](key), ctx["truncate"](value, 50), actions])

    topic_table = [["主题", "附加要求", "操作"]]
    action_inputs = {}

    async def analyze_topic(key, action_input):
        action = await ctx["pin"][ctx["stable_widget_id"](key, prefix="action")]
        topic = key
        full_prompt = f" 获取{topic}{action},要求返回的内容每一行都是一个一句话，开头用一个和内容对应的图标，然后是一个不大于十个字的高度浓缩概括词，概括词用加粗字体，再后面是一句话摘要，用破折号区隔开。每行一个内容，不要有标题等其他任何介绍性内容，只需要返回6 条新闻即可。"
        async def async_content_func(session, scope):
            return await ctx["get_gpt_response"](prompt=full_prompt, session=session, scope=scope, model_type="kimi")
        ctx["run_async"](ctx["dynamic_popup"](title=f"主题分析: {key}", async_content_func=async_content_func))

    for key, value in topics:
        action_input_name = ctx["stable_widget_id"](key, prefix="action")
        action_input = ctx["put_input"](name=action_input_name, value=value, placeholder="请输入附加要求")
        action_inputs[key] = action_input
        actions = ctx["put_button"]("📊 分析", onclick=lambda k=key: ctx["run_async"](analyze_topic(k, action_inputs[k])))
        topic_table.append([ctx["truncate"](key), action_input, actions])

    ctx["put_html"]('<div class="section-grid">')
    ctx["put_html"]('<div style="background:#fff;border-radius:12px;padding:16px;border:1px solid #e2e8f0;">')
    ctx["put_html"]('<h4 style="margin:0 0 12px 0;color:#1e293b;font-size:15px;">📝 主题列表</h4>')
    ctx["put_table"](topic_table)
    ctx["put_html"]('</div>')
    
    ctx["put_html"]('<div style="background:#fff;border-radius:12px;padding:16px;border:1px solid #e2e8f0;">')
    ctx["put_html"]('<h4 style="margin:0 0 12px 0;color:#1e293b;font-size:15px;">👥 人物列表</h4>')
    ctx["put_table"](people_table)
    ctx["put_html"]('</div>')
    ctx["put_html"]('</div>')
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
