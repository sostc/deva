#!/usr/bin/env python
# coding: utf-8
"""
Deva AI 功能中心

整合 Deva 代码库中所有 LLM 和 AI 相关功能，提供可视化 UI 体验界面。

功能模块：
1. AI 智能对话 - 与 AI 进行多轮对话
2. AI 代码生成 - 生成 Python/Deva 代码
3. AI 文本处理 - 摘要、翻译、润色等
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

from .ai_studio import (
    show_ai_studio,
)


# ============================================================================
# AI 智能对话
# ============================================================================

async def show_ai_chat(ctx):
    """显示 AI 智能对话界面"""
    put_markdown = ctx['put_markdown']
    put_text = ctx['put_text']
    input = ctx['input']
    run_async = ctx['run_async']
    
    put_markdown("### 💬 AI 智能对话")
    put_markdown("与 AI 进行多轮对话，解答问题、提供建议")
    
    # 初始化对话历史
    if 'chat_history' not in ctx:
        ctx['chat_history'] = []
    
    # 显示对话历史
    with ctx['use_scope']('chat_history_display'):
        if not ctx['chat_history']:
            put_text("💡 输入问题开始对话...")
        else:
            for msg in ctx['chat_history'][-10:]:  # 只显示最近 10 条
                if msg['role'] == 'user':
                    put_markdown(f"**👤 你：** {msg['content']}")
                else:
                    put_markdown(f"**🤖 AI：** {msg['content']}")
    
    # 输入框
    put_markdown("---")
    user_input = await ctx['input_group']('输入消息', [
        input('消息内容', name='message', type='text', 
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
    toast = ctx['toast']
    
    # 添加用户消息到历史
    ctx['chat_history'].append({'role': 'user', 'content': message})
    
    # 清空并重新显示
    ctx['clear']('chat_history_display')
    
    # 显示思考中
    with ctx['use_scope']('thinking'):
        put_markdown("*🤖 AI 正在思考...*")
    
    try:
        # 构建对话历史
        from deva.admin_ui.llm_service import get_gpt_response
        
        messages = []
        for msg in ctx['chat_history'][-5:]:  # 使用最近 5 条历史
            messages.append({
                'role': msg['role'],
                'content': msg['content']
            })
        
        # 获取 AI 响应
        prompt = message
        response = await get_gpt_response(ctx, prompt, model_type='deepseek')
        
        # 添加 AI 响应到历史
        ctx['chat_history'].append({'role': 'assistant', 'content': response})
        
        # 更新显示
        ctx['clear']('thinking')
        ctx['clear']('chat_history_display')
        
        with ctx['use_scope']('chat_history_display'):
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
        toast(f'对话失败：{e}', color='error')


# ============================================================================
# AI 代码生成
# ============================================================================

async def show_ai_code_generator(ctx):
    """显示 AI 代码生成器"""
    put_markdown = ctx['put_markdown']
    put_button = ctx['put_button']
    put_row = ctx['put_row']
    run_async = ctx['run_async']
    
    put_markdown("### 💻 AI 代码生成")
    put_markdown("使用 AI 生成 Python 代码、Deva 代码等")
    
    # 代码生成选项
    put_markdown("**选择代码类型：**")
    
    put_row([
        put_button('📝 生成 Python 代码', onclick=lambda: run_async(show_python_code_gen(ctx)), color='primary'),
        put_button('📊 生成 Deva 策略', onclick=lambda: run_async(show_deva_strategy_gen(ctx)), color='primary'),
        put_button('📈 生成 Deva 数据源', onclick=lambda: run_async(show_deva_datasource_gen(ctx)), color='primary'),
        put_button('⚙️ 生成 Deva 任务', onclick=lambda: run_async(show_deva_task_gen(ctx)), color='primary'),
    ])


async def show_python_code_gen(ctx):
    """显示 Python 代码生成界面"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    
    with ctx['popup']('生成 Python 代码', size='large', closable=True):
        put_markdown("### 📝 生成 Python 代码")
        
        put_markdown("""
        **输入你的需求，AI 会生成对应的 Python 代码：**
        
        示例：
        - "写一个函数，计算列表中所有数字的平均值"
        - "写一个类，实现单例模式"
        - "写一个装饰器，用于计算函数执行时间"
        """)
        
        requirement = await ctx['input_group']('代码需求', [
            textarea('需求描述', name='description', required=True,
                    placeholder='详细描述你想要的代码功能...', rows=5),
            ctx['actions']('操作', [
                {'label': '🤖 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])
        
        if requirement['action'] == 'generate':
            await generate_code(ctx, requirement['description'], 'python')


async def show_deva_strategy_gen(ctx):
    """显示 Deva 策略代码生成"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    
    with ctx['popup']('生成 Deva 策略', size='large', closable=True):
        put_markdown("### 📊 生成 Deva 量化策略")
        
        put_markdown("""
        **输入策略逻辑，AI 会生成 Deva 策略代码：**
        
        示例：
        - "双均线策略：当 5 日均线上穿 20 日均线时买入，下穿时卖出"
        - "MACD 策略：当 MACD 金叉时买入，死叉时卖出"
        """)
        
        requirement = await ctx['input_group']('策略需求', [
            textarea('策略描述', name='description', required=True,
                    placeholder='详细描述策略逻辑...', rows=5),
            ctx['input']('策略名称', name='name', type='text', 
                        placeholder='例如：双均线策略', required=True),
            ctx['actions']('操作', [
                {'label': '🤖 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])
        
        if requirement['action'] == 'generate':
            prompt = f"生成一个 Deva 量化策略代码，策略名称：{requirement['name']}，策略逻辑：{requirement['description']}。要求使用 StrategyUnit 类，实现 process 方法。"
            await generate_code(ctx, prompt, 'deva_strategy')


async def show_deva_datasource_gen(ctx):
    """显示 Deva 数据源代码生成"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    
    with ctx['popup']('生成 Deva 数据源', size='large', closable=True):
        put_markdown("### 📈 生成 Deva 数据源")
        
        put_markdown("""
        **输入数据源需求，AI 会生成 Deva 数据源代码：**
        
        示例：
        - "从 Yahoo Finance 获取股票实时数据，每 5 秒更新一次"
        - "读取本地 CSV 文件，解析为字典格式"
        """)
        
        requirement = await ctx['input_group']('数据源需求', [
            textarea('数据源描述', name='description', required=True,
                    placeholder='详细描述数据源功能...', rows=5),
            ctx['input']('数据源名称', name='name', type='text', 
                        placeholder='例如：股票数据源', required=True),
            ctx['actions']('操作', [
                {'label': '🤖 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])
        
        if requirement['action'] == 'generate':
            prompt = f"生成一个 Deva 数据源代码，数据源名称：{requirement['name']}，功能描述：{requirement['description']}。要求使用 DataSource 类，实现 fetch_data 方法。"
            await generate_code(ctx, prompt, 'deva_datasource')


async def show_deva_task_gen(ctx):
    """显示 Deva 任务代码生成"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    
    with ctx['popup']('生成 Deva 任务', size='large', closable=True):
        put_markdown("### ⚙️ 生成 Deva 任务")
        
        put_markdown("""
        **输入任务需求，AI 会生成 Deva 任务代码：**
        
        示例：
        - "每天凌晨 2 点备份数据库"
        - "每小时检查一次系统状态，异常时发送告警"
        """)
        
        requirement = await ctx['input_group']('任务需求', [
            textarea('任务描述', name='description', required=True,
                    placeholder='详细描述任务功能...', rows=5),
            ctx['input']('任务名称', name='name', type='text', 
                        placeholder='例如：数据库备份', required=True),
            ctx['input']('执行时间', name='schedule', type='text', 
                        placeholder='例如：每天 02:00', required=True),
            ctx['actions']('操作', [
                {'label': '🤖 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])
        
        if requirement['action'] == 'generate':
            prompt = f"生成一个 Deva 任务代码，任务名称：{requirement['name']}，功能描述：{requirement['description']}，执行时间：{requirement['schedule']}。要求使用 TaskUnit 类，实现 execute 方法。"
            await generate_code(ctx, prompt, 'deva_task')


async def generate_code(ctx, prompt: str, code_type: str):
    """生成代码"""
    put_markdown = ctx['put_markdown']
    put_code = ctx['put_code']
    put_button = ctx['put_button']
    toast = ctx['toast']
    
    toast('正在生成代码...', color='info')
    
    try:
        from deva.admin_ui.llm_service import get_gpt_response
        
        # 构建提示词
        system_prompt = "你是一个专业的 Python 开发者，请生成高质量、可运行的代码。只返回代码，不要其他说明。"
        full_prompt = f"{system_prompt}\n\n{prompt}"
        
        # 调用 AI
        code = await get_gpt_response(ctx, full_prompt, model_type='deepseek')
        
        # 显示生成的代码
        with ctx['popup']('生成的代码', size='large', closable=True):
            put_markdown(f"### {'代码类型'.join({'python': 'Python', 'deva_strategy': 'Deva 策略', 'deva_datasource': 'Deva 数据源', 'deva_task': 'Deva 任务'})}")
            put_code(code)
            
            put_markdown("**操作：**")
            put_button('📋 复制代码', onclick=lambda: ctx['run_js'](f"navigator.clipboard.writeText(`{code}`)"), color='primary')
            
        toast('代码生成成功', color='success')
        
    except Exception as e:
        toast(f'生成失败：{e}', color='error')


# ============================================================================
# AI 文本处理
# ============================================================================

async def show_ai_text_processor(ctx):
    """显示 AI 文本处理器"""
    put_markdown = ctx['put_markdown']
    put_button = ctx['put_button']
    put_row = ctx['put_row']
    run_async = ctx['run_async']
    
    put_markdown("### 📝 AI 文本处理")
    put_markdown("使用 AI 进行文本摘要、翻译、润色等处理")
    
    put_row([
        put_button('📄 文章摘要', onclick=lambda: run_async(show_text_summary(ctx)), color='info'),
        put_button('🌐 翻译', onclick=lambda: run_async(show_translation(ctx)), color='info'),
        put_button('✏️ 润色', onclick=lambda: run_async(show_text_polish(ctx)), color='info'),
        put_button('📊 分析', onclick=lambda: run_async(show_text_analysis(ctx)), color='info'),
    ])


async def show_text_summary(ctx):
    """显示文本摘要功能"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    
    with ctx['popup']('文章摘要', size='large', closable=True):
        put_markdown("### 📄 文章摘要生成")
        
        put_markdown("**粘贴文章内容，AI 会自动生成摘要：**")
        
        article = await ctx['input_group']('文章内容', [
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
                from deva.admin_ui.llm_service import get_gpt_response
                prompt = f"请用一句话总结以下文章：\n\n{article['content']}"
                summary = await get_gpt_response(ctx, prompt)
                
                put_markdown("### 摘要")
                put_markdown(f"> {summary}")
                
            except Exception as e:
                toast(f'生成失败：{e}', color='error')


async def show_translation(ctx):
    """显示翻译功能"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    
    with ctx['popup']('翻译', size='large', closable=True):
        put_markdown("### 🌐 AI 翻译")
        
        text_data = await ctx['input_group']('翻译', [
            textarea('原文', name='text', required=True,
                    placeholder='粘贴要翻译的文本...', rows=5),
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
                from deva.admin_ui.llm_service import get_gpt_response
                prompt = f"将以下文本翻译成{text_data['target']}：\n\n{text_data['text']}"
                translation = await get_gpt_response(ctx, prompt)
                
                put_markdown("### 翻译结果")
                put_markdown(translation)
                
            except Exception as e:
                toast(f'翻译失败：{e}', color='error')


async def show_text_polish(ctx):
    """显示文本润色功能"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    
    with ctx['popup']('文本润色', size='large', closable=True):
        put_markdown("### ✏️ 文本润色")
        
        put_markdown("**粘贴要润色的文本，AI 会优化表达：**")
        
        text_data = await ctx['input_group']('文本润色', [
            textarea('原文', name='text', required=True,
                    placeholder='粘贴要润色的文本...', rows=5),
            ctx['actions']('操作', [
                {'label': '🤖 润色', 'value': 'polish'},
            ], name='action')
        ])
        
        if text_data['action'] == 'polish':
            toast = ctx['toast']
            toast('正在润色...', color='info')
            
            try:
                from deva.admin_ui.llm_service import get_gpt_response
                prompt = f"请润色以下文本，使其更流畅、专业：\n\n{text_data['text']}"
                polished = await get_gpt_response(ctx, prompt)
                
                put_markdown("### 润色结果")
                put_markdown(polished)
                
            except Exception as e:
                toast(f'润色失败：{e}', color='error')


async def show_text_analysis(ctx):
    """显示文本分析功能"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    
    with ctx['popup']('文本分析', size='large', closable=True):
        put_markdown("### 📊 文本分析")
        
        put_markdown("**粘贴文本，AI 会分析情感、主题等：**")
        
        text_data = await ctx['input_group']('文本分析', [
            textarea('文本', name='text', required=True,
                    placeholder='粘贴要分析的文本...', rows=5),
            ctx['actions']('操作', [
                {'label': '🤖 分析', 'value': 'analyze'},
            ], name='action')
        ])
        
        if text_data['action'] == 'analyze':
            toast = ctx['toast']
            toast('正在分析...', color='info')
            
            try:
                from deva.admin_ui.llm_service import get_gpt_response
                prompt = f"请分析以下文本，包括情感倾向、主题、关键词等：\n\n{text_data['text']}"
                analysis = await get_gpt_response(ctx, prompt)
                
                put_markdown("### 分析结果")
                put_markdown(analysis)
                
            except Exception as e:
                toast(f'分析失败：{e}', color='error')


# ============================================================================
# AI Tab 主界面
# ============================================================================

async def render_ai_tab_ui(ctx):
    """渲染 AI Tab 主界面 - 使用 AI Studio"""
    return await show_ai_studio(ctx)

if __name__ == '__main__':
    from pywebio import start_server
    from pywebio.output import *
    from pywebio.input import *
    from pywebio.session import *
    
    def test_ai_tab():
        put_markdown("### 🤖 Deva AI 功能中心")
        put_markdown("体验 Deva 的强大 AI 功能，包括智能对话、代码生成、文本处理等")
        put_markdown("---")
        put_markdown("💡 功能开发中，敬请期待...")
    
    start_server(test_ai_tab, port=8080, debug=True)
