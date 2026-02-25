#!/usr/bin/env python
# coding: utf-8
"""
Deva AI 功能中心

提供统一的 AI 功能体验界面，包括：
- AI 代码生成（策略、数据源、任务）
- AI 智能对话
- AI 模型配置
- AI 功能演示
"""

import json
import time
from pathlib import Path

from pywebio import start_server
from pywebio.output import *
from pywebio.input import *
from pywebio.pin import *
from pywebio.session import info as session_info
from pywebio.exceptions import SessionClosedException


# ============================================================================
# AI 模型配置管理
# ============================================================================

def show_llm_config_panel(ctx):
    """显示 LLM 配置面板"""
    put_markdown("### 🤖 AI 模型配置")
    
    NB = ctx['NB']
    toast = ctx['toast']
    put_button = ctx['put_button']
    run_async = ctx['run_async']
    
    # 获取当前配置
    llm_config = NB('llm_config', key_mode='explicit')
    
    # 显示当前配置状态
    put_markdown("**当前配置：**")
    
    config_table = [['模型', '状态', '操作']]
    
    models = ['kimi', 'deepseek', 'qwen', 'gpt']
    for model in models:
        config = llm_config.get(model, {})
        status = '✅ 已配置' if config.get('api_key') else '❌ 未配置'
        config_table.append([
            model.upper(),
            status,
            put_button('配置', onclick=lambda m=model: run_async(show_model_config_dialog(ctx, m)), link_style=True)
        ])
    
    put_table(config_table)
    
    # 快捷操作
    put_markdown("**快捷操作：**")
    put_row([
        put_button('📝 配置 Kimi', onclick=lambda: run_async(show_model_config_dialog(ctx, 'kimi')), color='primary'),
        put_button('📝 配置 DeepSeek', onclick=lambda: run_async(show_model_config_dialog(ctx, 'deepseek')), color='primary'),
        put_button('📝 配置 Qwen', onclick=lambda: run_async(show_model_config_dialog(ctx, 'qwen')), color='primary'),
        put_button('📝 配置 GPT', onclick=lambda: run_async(show_model_config_dialog(ctx, 'gpt')), color='primary'),
    ])
    
    # 测试连接
    put_markdown("**测试连接：**")
    put_row([
        put_button('🧪 测试 Kimi', onclick=lambda: run_async(test_llm_connection(ctx, 'kimi')), color='success'),
        put_button('🧪 测试 DeepSeek', onclick=lambda: run_async(test_llm_connection(ctx, 'deepseek')), color='success'),
    ])


async def show_model_config_dialog(ctx, model_type):
    """显示模型配置对话框"""
    put_markdown = ctx['put_markdown']
    input = ctx['input']
    NB = ctx['NB']
    toast = ctx['toast']
    
    llm_config = NB('llm_config', key_mode='explicit')
    current_config = llm_config.get(model_type, {})
    
    with ctx['popup'](f'配置 {model_type.upper()} 模型', closable=True):
        put_markdown(f"### {model_type.upper()} 模型配置")
        
        # 配置表单
        config_data = await ctx['input_group']('模型配置', [
            ctx['input']('API Key', name='api_key', type='password', 
                        value=current_config.get('api_key', ''), 
                        required=True, placeholder='请输入 API Key'),
            ctx['input']('Base URL', name='base_url', type='text',
                        value=current_config.get('base_url', ''),
                        placeholder='https://api.moonshot.cn/v1'),
            ctx['input']('模型名称', name='model', type='text',
                        value=current_config.get('model', 'moonshot-v1-8k'),
                        placeholder='moonshot-v1-8k'),
            ctx['actions']('操作', [
                {'label': '💾 保存', 'value': 'save'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])
        
        if config_data['action'] == 'save':
            # 保存配置
            llm_config.upsert(model_type, {
                'api_key': config_data['api_key'],
                'base_url': config_data['base_url'],
                'model': config_data['model']
            })
            toast(f'{model_type.upper()} 配置已保存', color='success')


async def test_llm_connection(ctx, model_type):
    """测试 LLM 连接"""
    toast = ctx['toast']
    NB = ctx['NB']
    log = ctx['log']
    
    toast(f'正在测试 {model_type.upper()} 连接...', color='info')
    
    llm_config = NB('llm_config', key_mode='explicit')
    config = llm_config.get(model_type, {})
    
    if not config.get('api_key'):
        toast(f'{model_type.upper()} 未配置', color='warning')
        return
    
    try:
        # 简单测试
        import requests
        url = config.get('base_url', '').rstrip('/') + '/chat/completions'
        headers = {
            'Authorization': f"Bearer {config.get('api_key')}",
            'Content-Type': 'application/json'
        }
        payload = {
            'model': config.get('model'),
            'messages': [{'role': 'user', 'content': 'Hello'}],
            'max_tokens': 10
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            toast(f'{model_type.upper()} 连接成功！', color='success')
            (f"✅ {model_type.upper()} 连接测试通过") >> log
        else:
            toast(f'{model_type.upper()} 连接失败：{response.status_code}', color='error')
            (f"❌ {model_type.upper()} 连接失败：{response.status_code}") >> log
            
    except Exception as e:
        toast(f'{model_type.upper()} 连接异常：{e}', color='error')
        (f"❌ {model_type.upper()} 连接异常：{e}") >> log


# ============================================================================
# AI 代码生成
# ============================================================================

async def show_ai_code_generator(ctx):
    """显示 AI 代码生成器"""
    put_markdown = ctx['put_markdown']
    put_button = ctx['put_button']
    run_async = ctx['run_async']
    
    put_markdown("### 💻 AI 代码生成")
    put_markdown("选择要生成的代码类型：")
    
    # 代码生成选项
    code_types = [
        {'label': '📊 量化策略', 'value': 'strategy', 'desc': '生成交易策略代码'},
        {'label': '📈 数据源', 'value': 'datasource', 'desc': '生成数据采集代码'},
        {'label': '⚙️ 任务', 'value': 'task', 'desc': '生成定时任务代码'},
    ]
    
    # 显示选项卡片
    for code_type in code_types:
        with ctx['use_scope'](f"ai_code_{code_type['value']}"):
            put_markdown(f"**{code_type['label']}** - {code_type['desc']}")
    
    put_row([
        put_button('📊 生成量化策略', onclick=lambda: run_async(show_strategy_code_gen(ctx)), color='primary'),
        put_button('📈 生成数据源', onclick=lambda: run_async(show_datasource_code_gen(ctx)), color='primary'),
        put_button('⚙️ 生成任务', onclick=lambda: run_async(show_task_code_gen(ctx)), color='primary'),
    ])


async def show_strategy_code_gen(ctx):
    """显示策略代码生成界面"""
    put_markdown = ctx['put_markdown']
    input = ctx['input']
    textarea = ctx['textarea']
    NB = ctx['NB']
    
    with ctx['popup']('AI 生成量化策略', closable=True):
        put_markdown("### 📊 AI 生成量化策略")
        
        # 需求输入
        requirement = await ctx['input_group']('策略需求', [
            ctx['input']('策略名称', name='name', type='text', required=True, 
                        placeholder='例如：双均线策略'),
            textarea('策略描述', name='description', required=True,
                    placeholder='详细描述策略逻辑，例如：当 5 日均线上穿 20 日均线时买入，下穿时卖出'),
            ctx['input']('输入数据', name='input_data', type='text',
                        value='股票 K 线数据', placeholder='策略需要的输入数据'),
            ctx['input']('输出格式', name='output_format', type='text',
                        value='交易信号（buy/sell/hold）', placeholder='策略的输出格式'),
            ctx['actions']('操作', [
                {'label': '🤖 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])
        
        if requirement['action'] == 'generate':
            # 调用 AI 生成代码
            await generate_strategy_code(ctx, requirement)


async def generate_strategy_code(ctx, requirement):
    """生成策略代码"""
    put_markdown = ctx['put_markdown']
    NB = ctx['NB']
    toast = ctx['toast']
    
    toast('正在生成策略代码...', color='info')
    
    # 构建提示词
    prompt = f"""
请生成一个 Deva 量化策略代码。

策略信息：
- 名称：{requirement['name']}
- 描述：{requirement['description']}
- 输入数据：{requirement['input_data']}
- 输出格式：{requirement['output_format']}

要求：
1. 使用 Deva 框架的 StrategyUnit 类
2. 实现 process 方法处理数据
3. 返回交易信号（buy/sell/hold）
4. 添加适当的错误处理
5. 代码要有清晰的注释

请只返回 Python 代码，不要其他说明。
"""
    
    # 调用 AI
    try:
        from .llm_service import get_gpt_response
        code = await get_gpt_response(prompt)
        
        # 显示生成的代码
        with ctx['popup']('生成的策略代码', closable=True):
            put_markdown("### 📊 生成的策略代码")
            put_code(code)
            
            # 操作按钮
            put_row([
                ctx['put_button']('✅ 使用此代码', onclick=lambda: save_strategy_code(ctx, requirement['name'], code), color='success'),
                ctx['put_button']('📋 复制代码', onclick=lambda: ctx['run_js'](f"navigator.clipboard.writeText(`{code}`)"), color='primary'),
                ctx['put_button']('🔄 重新生成', onclick=lambda: ctx['run_async'](show_strategy_code_gen(ctx)), color='warning'),
            ])
            
    except Exception as e:
        toast(f'生成失败：{e}', color='error')


def save_strategy_code(ctx, name, code):
    """保存策略代码"""
    toast = ctx['toast']
    log = ctx['log']
    
    # 保存到策略管理器
    try:
        from .strategy.strategy_manager import get_strategy_manager
        mgr = get_strategy_manager()
        mgr.add_strategy(name=name, code=code)
        toast(f'策略 "{name}" 已保存', color='success')
        (f"✅ 策略已保存：{name}") >> log
    except Exception as e:
        toast(f'保存失败：{e}', color='error')
        (f"❌ 策略保存失败：{name}, 错误：{e}") >> log


async def show_datasource_code_gen(ctx):
    """显示数据源代码生成界面"""
    put_markdown = ctx['put_markdown']
    input = ctx['input']
    textarea = ctx['textarea']
    
    with ctx['popup']('AI 生成数据源', closable=True):
        put_markdown("### 📈 AI 生成数据源")
        
        # 需求输入
        requirement = await ctx['input_group']('数据源需求', [
            ctx['input']('数据源名称', name='name', type='text', required=True,
                        placeholder='例如：股票实时数据'),
            textarea('数据源描述', name='description', required=True,
                    placeholder='详细描述数据源，例如：从 Yahoo Finance 获取股票实时行情数据'),
            ctx['input']('数据类型', name='data_type', type='text',
                        value='dict', placeholder='返回的数据类型'),
            ctx['input']('更新频率', name='interval', type='text',
                        value='5', placeholder='数据更新间隔（秒）'),
            ctx['actions']('操作', [
                {'label': '🤖 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])
        
        if requirement['action'] == 'generate':
            await generate_datasource_code(ctx, requirement)


async def generate_datasource_code(ctx, requirement):
    """生成数据源代码"""
    toast = ctx['toast']
    
    toast('正在生成数据源代码...', color='info')
    
    prompt = f"""
请生成一个 Deva 数据源代码。

数据源信息：
- 名称：{requirement['name']}
- 描述：{requirement['description']}
- 数据类型：{requirement['data_type']}
- 更新频率：{requirement['interval']}秒

要求：
1. 使用 Deva 框架的 DataSource 类
2. 实现 fetch_data 方法获取数据
3. 添加适当的错误处理
4. 代码要有清晰的注释

请只返回 Python 代码，不要其他说明。
"""
    
    try:
        from .llm_service import get_gpt_response
        code = await get_gpt_response(prompt)
        
        with ctx['popup']('生成的数据源代码', closable=True):
            put_markdown("### 📈 生成的数据源代码")
            put_code(code)
            
            put_row([
                ctx['put_button']('✅ 使用此代码', onclick=lambda: save_datasource_code(ctx, requirement['name'], code), color='success'),
                ctx['put_button']('📋 复制代码', onclick=lambda: ctx['run_js'](f"navigator.clipboard.writeText(`{code}`)"), color='primary'),
            ])
            
    except Exception as e:
        toast(f'生成失败：{e}', color='error')


def save_datasource_code(ctx, name, code):
    """保存数据源代码"""
    toast = ctx['toast']
    log = ctx['log']
    
    try:
        from .strategy.datasource_manager import get_datasource_manager
        mgr = get_datasource_manager()
        mgr.add_datasource(name=name, code=code)
        toast(f'数据源 "{name}" 已保存', color='success')
        (f"✅ 数据源已保存：{name}") >> log
    except Exception as e:
        toast(f'保存失败：{e}', color='error')
        (f"❌ 数据源保存失败：{name}, 错误：{e}") >> log


async def show_task_code_gen(ctx):
    """显示任务代码生成界面"""
    put_markdown = ctx['put_markdown']
    input = ctx['input']
    textarea = ctx['textarea']
    
    with ctx['popup']('AI 生成任务', closable=True):
        put_markdown("### ⚙️ AI 生成任务")
        
        requirement = await ctx['input_group']('任务需求', [
            ctx['input']('任务名称', name='name', type='text', required=True,
                        placeholder='例如：每日数据备份'),
            textarea('任务描述', name='description', required=True,
                    placeholder='详细描述任务功能'),
            ctx['input']('执行时间', name='schedule', type='text',
                        value='每天 00:00', placeholder='任务执行时间'),
            ctx['actions']('操作', [
                {'label': '🤖 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])
        
        if requirement['action'] == 'generate':
            await generate_task_code(ctx, requirement)


async def generate_task_code(ctx, requirement):
    """生成任务代码"""
    toast = ctx['toast']
    
    toast('正在生成任务代码...', color='info')
    
    prompt = f"""
请生成一个 Deva 任务代码。

任务信息：
- 名称：{requirement['name']}
- 描述：{requirement['description']}
- 执行时间：{requirement['schedule']}

要求：
1. 使用 Deva 框架的 TaskUnit 类
2. 实现 execute 方法执行任务
3. 添加适当的错误处理
4. 代码要有清晰的注释

请只返回 Python 代码，不要其他说明。
"""
    
    try:
        from .llm_service import get_gpt_response
        code = await get_gpt_response(prompt)
        
        with ctx['popup']('生成的任务代码', closable=True):
            put_markdown("### ⚙️ 生成的任务代码")
            put_code(code)
            
            put_row([
                ctx['put_button']('✅ 使用此代码', onclick=lambda: save_task_code(ctx, requirement['name'], code), color='success'),
                ctx['put_button']('📋 复制代码', onclick=lambda: ctx['run_js'](f"navigator.clipboard.writeText(`{code}`)"), color='primary'),
            ])
            
    except Exception as e:
        toast(f'生成失败：{e}', color='error')


def save_task_code(ctx, name, code):
    """保存任务代码"""
    toast = ctx['toast']
    log = ctx['log']
    
    try:
        from .strategy.task_manager import get_task_manager
        mgr = get_task_manager()
        mgr.add_task(name=name, code=code)
        toast(f'任务 "{name}" 已保存', color='success')
        (f"✅ 任务已保存：{name}") >> log
    except Exception as e:
        toast(f'保存失败：{e}', color='error')
        (f"❌ 任务保存失败：{name}, 错误：{e}") >> log


# ============================================================================
# AI 智能对话
# ============================================================================

async def show_ai_chat(ctx):
    """显示 AI 智能对话界面"""
    put_markdown = ctx['put_markdown']
    input = ctx['input']
    run_async = ctx['run_async']
    
    put_markdown("### 🤖 AI 智能对话")
    
    # 初始化对话历史
    if 'chat_history' not in ctx:
        ctx['chat_history'] = []
    
    # 显示对话历史
    with ctx['use_scope']('chat_history'):
        for msg in ctx['chat_history'][-10:]:  # 只显示最近 10 条
            if msg['role'] == 'user':
                put_markdown(f"**👤 你：** {msg['content']}")
            else:
                put_markdown(f"**🤖 AI：** {msg['content']}")
    
    # 输入框
    user_input = await ctx['input_group']('输入消息', [
        ctx['input']('消息内容', name='message', type='text', 
                    placeholder='输入你想问的问题...', required=True),
        ctx['actions']('发送', [
            {'label': '📤 发送', 'value': 'send'},
        ], name='action')
    ])
    
    if user_input['action'] == 'send' and user_input['message']:
        await process_chat_message(ctx, user_input['message'])


async def process_chat_message(ctx, message):
    """处理对话消息"""
    put_markdown = ctx['put_markdown']
    NB = ctx['NB']
    
    # 添加用户消息到历史
    ctx['chat_history'].append({'role': 'user', 'content': message})
    
    # 清空输入历史
    ctx['clear']('chat_history')
    
    # 显示思考中
    with ctx['use_scope']('thinking'):
        put_markdown("*🤖 AI 正在思考...*")
    
    # 调用 AI
    try:
        from .llm_service import get_gpt_response
        
        # 构建对话历史
        messages = []
        for msg in ctx['chat_history'][-5:]:  # 使用最近 5 条历史
            messages.append({
                'role': msg['role'],
                'content': msg['content']
            })
        
        # 获取 AI 响应
        response = await get_gpt_response(messages=messages)
        
        # 添加 AI 响应到历史
        ctx['chat_history'].append({'role': 'assistant', 'content': response})
        
        # 更新显示
        ctx['clear']('thinking')
        ctx['clear']('chat_history')
        
        with ctx['use_scope']('chat_history'):
            for msg in ctx['chat_history'][-10:]:
                if msg['role'] == 'user':
                    put_markdown(f"**👤 你：** {msg['content']}")
                else:
                    put_markdown(f"**🤖 AI：** {msg['content']}")
        
        # 重新显示输入框
        await show_ai_chat(ctx)
        
    except Exception as e:
        ctx['clear']('thinking')
        put_markdown(f"❌ 错误：{e}")


# ============================================================================
# AI 功能演示
# ============================================================================

async def show_ai_demos(ctx):
    """显示 AI 功能演示"""
    put_markdown = ctx['put_markdown']
    put_button = ctx['put_button']
    run_async = ctx['run_async']
    
    put_markdown("### 🎯 AI 功能演示")
    put_markdown("体验 Deva 的 AI 功能：")
    
    # 演示选项
    demos = [
        {'label': '📝 文章摘要', 'value': 'summary', 'desc': '自动生成文章摘要'},
        {'label': '🔗 链接提取', 'value': 'links', 'desc': '智能提取重要链接'},
        {'label': '📊 数据分析', 'value': 'analysis', 'desc': 'AI 分析数据趋势'},
        {'label': '🌐 新闻翻译', 'value': 'translate', 'desc': '自动翻译外文新闻'},
    ]
    
    for demo in demos:
        with ctx['use_scope'](f"ai_demo_{demo['value']}"):
            put_markdown(f"**{demo['label']}** - {demo['desc']}")
    
    put_row([
        put_button('📝 文章摘要', onclick=lambda: run_async(demo_article_summary(ctx)), color='info'),
        put_button('🔗 链接提取', onclick=lambda: run_async(demo_link_extraction(ctx)), color='info'),
        put_button('📊 数据分析', onclick=lambda: run_async(demo_data_analysis(ctx)), color='info'),
        put_button('🌐 新闻翻译', onclick=lambda: run_async(demo_translation(ctx)), color='info'),
    ])


async def demo_article_summary(ctx):
    """演示文章摘要"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    
    with ctx['popup']('文章摘要', closable=True):
        put_markdown("### 📝 文章摘要生成")
        
        article = await ctx['input_group']('输入文章', [
            textarea('文章内容', name='content', required=True,
                    placeholder='粘贴文章内容...', rows=10),
            ctx['actions']('操作', [
                {'label': '🤖 生成摘要', 'value': 'generate'},
            ], name='action')
        ])
        
        if article['action'] == 'generate':
            toast = ctx['toast']
            toast('正在生成摘要...', color='info')
            
            try:
                from .llm_service import get_gpt_response
                prompt = f"请用一句话总结以下文章：\n\n{article['content']}"
                summary = await get_gpt_response(prompt)
                
                put_markdown("### 摘要")
                put_markdown(f"> {summary}")
                
            except Exception as e:
                toast(f'生成失败：{e}', color='error')


async def demo_link_extraction(ctx):
    """演示链接提取"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    
    with ctx['popup']('链接提取', closable=True):
        put_markdown("### 🔗 智能链接提取")
        
        html = await ctx['input_group']('输入 HTML', [
            textarea('HTML 内容', name='html', required=True,
                    placeholder='粘贴 HTML 代码...', rows=10),
            ctx['actions']('操作', [
                {'label': '🤖 提取链接', 'value': 'extract'},
            ], name='action')
        ])
        
        if html['action'] == 'extract':
            toast = ctx['toast']
            toast('正在提取链接...', color='info')
            
            try:
                from .llm_service import get_gpt_response
                prompt = f"从以下 HTML 中提取最重要的 3 个链接，返回 JSON 格式：\n\n{html['html']}"
                result = await get_gpt_response(prompt)
                
                put_markdown("### 提取的链接")
                put_code(result)
                
            except Exception as e:
                toast(f'提取失败：{e}', color='error')


async def demo_data_analysis(ctx):
    """演示数据分析"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    
    with ctx['popup']('数据分析', closable=True):
        put_markdown("### 📊 AI 数据分析")
        
        data = await ctx['input_group']('输入数据', [
            textarea('数据', name='data', required=True,
                    placeholder='粘贴数据（CSV、JSON 等）...', rows=10),
            ctx['actions']('操作', [
                {'label': '🤖 分析数据', 'value': 'analyze'},
            ], name='action')
        ])
        
        if data['action'] == 'analyze':
            toast = ctx['toast']
            toast('正在分析数据...', color='info')
            
            try:
                from .llm_service import get_gpt_response
                prompt = f"分析以下数据，找出关键趋势和洞察：\n\n{data['data']}"
                analysis = await get_gpt_response(prompt)
                
                put_markdown("### 分析结果")
                put_markdown(analysis)
                
            except Exception as e:
                toast(f'分析失败：{e}', color='error')


async def demo_translation(ctx):
    """演示翻译"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    
    with ctx['popup']('翻译', closable=True):
        put_markdown("### 🌐 AI 翻译")
        
        text_data = await ctx['input_group']('输入文本', [
            textarea('原文', name='text', required=True,
                    placeholder='粘贴要翻译的文本...', rows=10),
            ctx['input']('目标语言', name='target', type='text',
                        value='中文', placeholder='例如：中文、英文'),
            ctx['actions']('操作', [
                {'label': '🤖 翻译', 'value': 'translate'},
            ], name='action')
        ])
        
        if text_data['action'] == 'translate':
            toast = ctx['toast']
            toast('正在翻译...', color='info')
            
            try:
                from .llm_service import get_gpt_response
                prompt = f"将以下文本翻译成{text_data['target']}：\n\n{text_data['text']}"
                translation = await get_gpt_response(prompt)
                
                put_markdown("### 翻译结果")
                put_markdown(translation)
                
            except Exception as e:
                toast(f'翻译失败：{e}', color='error')


# ============================================================================
# AI Tab 主界面
# ============================================================================

def render_ai_tab_ui(ctx):
    """渲染 AI Tab 主界面"""
    put_markdown = ctx['put_markdown']
    put_tabs = ctx['put_tabs']
    run_async = ctx['run_async']
    
    put_markdown("## 🤖 AI 功能中心")
    put_markdown("体验 Deva 的强大 AI 功能")
    
    # 构建 Tabs
    tabs = [
        {
            'title': '🤖 模型配置',
            'content': show_llm_config_panel(ctx)
        },
        {
            'title': '💻 代码生成',
            'content': run_async(show_ai_code_generator(ctx))
        },
        {
            'title': '💬 智能对话',
            'content': run_async(show_ai_chat(ctx))
        },
        {
            'title': '🎯 功能演示',
            'content': run_async(show_ai_demos(ctx))
        }
    ]
    
    put_tabs(tabs)


if __name__ == '__main__':
    # 测试运行
    from pywebio import start_server
    from pywebio.output import *
    
    def test_ai_tab():
        render_ai_tab_ui({
            'put_markdown': put_markdown,
            'put_tabs': put_tabs,
            'run_async': lambda f: f(),
            'input': input,
            'textarea': textarea,
            'input_group': input_group,
            'popup': popup,
            'toast': toast,
            'put_button': put_button,
            'put_table': put_table,
            'put_row': put_row,
            'put_code': put_code,
            'clear': clear,
            'use_scope': use_scope,
            'run_js': run_js,
            'NB': None,
            'log': None,
        })
    
    start_server(test_ai_tab, port=8080, debug=True)
