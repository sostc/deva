#!/usr/bin/env python
# coding: utf-8
"""
Deva AI 工作室

整合 AI 代码生成和创建功能，提供统一的 AI 辅助开发体验。

功能层次：
1. 快速生成 - 简单代码片段，无需配置
2. 标准创建 - 带配置的完整创建流程
3. 高级定制 - 自定义代码和参数
"""

from __future__ import annotations

import time
from typing import Dict, Any, List, Optional


# ============================================================================
# AI 工作室主界面
# ============================================================================

async def show_ai_studio(ctx):
    """显示 AI 工作室主界面 - 简化版"""
    put_markdown = ctx['put_markdown']
    put_button = ctx['put_button']
    put_row = ctx['put_row']
    run_async = ctx['run_async']

    put_markdown("## 🤖 AI 工作室")
    put_markdown("一站式 AI 辅助开发平台，从代码生成到部署")

    # 模型设置区域（放在最显眼的位置）
    with ctx['use_scope']('ai_model_settings'):
        await show_model_settings(ctx)

    put_markdown("---")

    # 快速操作区
    put_markdown("### ⚡ 快速操作")
    put_row([
        put_button('💬 对话生成代码', onclick=lambda: run_async(show_quick_chat_gen(ctx)), color='primary'),
        put_button('📝 代码片段生成', onclick=lambda: run_async(show_quick_code_gen(ctx)), color='info'),
        put_button('🔧 模板创建', onclick=lambda: run_async(show_template_creator(ctx)), color='success'),
    ])

    put_markdown("---")

    # 直接显示创建中心内容
    run_async(show_creation_center(ctx))


async def show_model_settings(ctx):
    """显示模型设置 - 仅显示已配置的模型列表"""
    put_markdown = ctx['put_markdown']
    put_button = ctx['put_button']
    put_row = ctx['put_row']
    put_table = ctx['put_table']
    run_async = ctx['run_async']
    toast = ctx['toast']
    use_scope = ctx['use_scope']
    clear = ctx['clear']

    # 从配置数据库读取所有已配置的大模型
    available_models = get_available_models_from_config()
    
    if not available_models:
        return  # 没有配置的模型则不显示
    
    # 获取当前默认模型
    current_model = ctx.get('ai_default_model', '')
    if not current_model and available_models:
        current_model = available_models[0][0]
    
    # 模型描述
    model_descriptions = {
        'deepseek': '🚀 DeepSeek - 代码生成能力强',
        'kimi': '💬 Kimi - 中文理解优秀',
        'qwen': '⚖️ 通义千问 - 综合能力均衡',
        'baichuan': '⚡ 百川 - 快速响应',
        'glm': '🧠 智谱 GLM - 长文本处理',
        'minimax': '🎯 MiniMax - 多场景适用',
    }
    
    # 显示所有已配置模型列表
    put_markdown(f"**📊 已配置 {len(available_models)} 个大模型：**")
    
    model_table = [['模型', '状态', '快捷操作']]
    for model_id, config in available_models:
        is_default = '✅ 默认' if model_id == current_model else '⭕'
        model_table.append([
            model_descriptions.get(model_id, model_id),
            is_default,
            put_button('设为默认', 
                      onclick=lambda mid=model_id: run_async(switch_and_save_model(ctx, mid)),
                      color='text')
        ])
    
    put_table(model_table)
    
    # 显示当前状态
    current_desc = model_descriptions.get(current_model, current_model)
    put_markdown(f"> 📌 当前代码生成默认模型：**{current_model}** {current_desc}")


async def switch_and_save_model(ctx, model_id: str):
    """切换并保存模型"""
    toast = ctx['toast']
    clear = ctx['clear']
    use_scope = ctx['use_scope']
    
    ctx['ai_default_model'] = model_id
    
    try:
        from deva.config import config
        config.set('ai.default_model', model_id)
        toast(f'✅ 已切换到 {model_id}', color='success')
    except Exception as e:
        toast(f'保存失败：{e}', color='error')
    
    # 刷新设置区域
    clear('ai_model_settings')
    with use_scope('ai_model_settings'):
        await show_model_settings(ctx)


async def refresh_model_status(ctx):
    """刷新模型状态"""
    toast = ctx['toast']
    clear = ctx['clear']
    use_scope = ctx['use_scope']
    
    current_model = ctx.get('ai_default_model', 'deepseek')
    toast(f'正在刷新 {current_model} 状态...', color='info')
    
    clear('ai_model_settings')
    with use_scope('ai_model_settings'):
        await show_model_settings(ctx)


def get_available_models_from_config() -> list:
    """从配置数据库读取所有已配置的大模型"""
    available = []
    seen_keys = set()
    
    try:
        # 方式 1: 从 deva.config 读取（配置模块使用的方式）
        from deva.config import config
        
        # 获取所有 LLM 配置
        model_types = ['deepseek', 'kimi', 'qwen', 'baichuan', 'glm', 'minimax', 'sambanova']
        
        for model_type in model_types:
            model_config = config.get_llm_config(model_type)
            if model_config and model_config.get('api_key'):
                available.append((model_type, model_config))
                seen_keys.add(model_type)
    except Exception as e:
        print(f"从 config 读取失败：{e}")
    
    try:
        # 方式 2: 从 NB('llm_config') 读取（兼容旧配置）
        from deva import NB
        llm_nb = NB('llm_config')
        
        for key, cfg in llm_nb.items():
            if isinstance(cfg, dict) and cfg.get('api_key'):
                # 避免重复
                if key not in seen_keys:
                    available.append((key, cfg))
    except Exception as e:
        print(f"从 NB 读取失败：{e}")
    
    return available


def get_model_status_info(ctx, model_type: str) -> dict:
    """获取模型配置状态"""
    try:
        # 从 config 读取（主要方式）
        from deva.config import config
        model_config = config.get_llm_config(model_type)
        
        if model_config and model_config.get('api_key'):
            return {'ready': True, 'model_type': model_type, 'configured': True}
            
        return {'ready': False, 'model_type': model_type, 'configured': False}
    except Exception as e:
        print(f"获取模型状态失败：{e}")
        return {'ready': False, 'model_type': model_type, 'configured': False}


# ============================================================================
# 快速生成（轻量级）
# ============================================================================

async def show_quick_chat_gen(ctx):
    """通过对话快速生成代码"""
    put_markdown = ctx['put_markdown']
    input_comp = ctx['input']
    put_button = ctx['put_button']
    put_textarea = ctx['textarea']
    put_row = ctx['put_row']
    pin = ctx['pin']
    use_scope = ctx['use_scope']
    clear = ctx['clear']
    run_async = ctx['run_async']
    toast = ctx['toast']
    log = ctx.get('log')

    with ctx['popup']('对话生成代码', size='large', closable=True):
        put_markdown("### 💬 对话生成代码")
        put_markdown("**描述你的需求，AI 会生成对应代码：**")
        
        # 第一步：输入需求
        with use_scope('chat_input_scope'):
            result = await ctx['input_group']('需求', [
                input_comp('代码需求', name='requirement', type='text',
                          placeholder='例如：写一个函数计算列表平均值', required=True),
                ctx['actions']('操作', [
                    {'label': '🤖 生成', 'value': 'generate'},
                ], name='action')
            ])

        if result.get('action') == 'generate':
            requirement = result['requirement']
            model_type = ctx.get('ai_default_model', 'deepseek')
            
            # 打印日志
            if log:
                (f"[AI 代码生成] 开始生成代码，模型：{model_type}, 需求：{requirement[:50]}...") >> log
            
            # 显示生成中
            clear('chat_input_scope')
            with use_scope('chat_input_scope'):
                put_markdown(f"*🤖 正在使用 {model_type} 生成代码...*")
            
            try:
                from deva.admin_ui.llm_service import get_gpt_response

                # 打印日志
                if log:
                    (f"[AI 代码生成] 正在调用 AI 服务...") >> log

                # 构建完整的上下文
                from openai import AsyncOpenAI
                import requests
                
                # 获取 log 和 warn 对象，并创建支持 >> 操作的包装器
                log_func = ctx.get('log')
                warn_func = ctx.get('warn', lambda x: print(f"[WARN] {x}"))
                
                # 创建支持 >> 操作的包装器（模拟 Deva Stream 行为）
                class LogWrapper:
                    def __init__(self, func):
                        self.func = func if func else (lambda x: print(f"[LOG] {x}"))
                    def __rshift__(self, other):
                        # 支持 stream >> func 模式
                        self.func(other)
                        return other
                    def __rrshift__(self, other):
                        # 支持 str >> LogWrapper 模式
                        self.func(other)
                        return other
                    def __call__(self, msg):
                        # 支持 func(msg) 直接调用
                        self.func(msg)
                        return msg
                
                llm_ctx = {
                    'NB': ctx.get('NB'),
                    'warn': LogWrapper(warn_func),
                    'log': LogWrapper(log_func),
                    'requests': requests,
                    'AsyncOpenAI': AsyncOpenAI,
                    'put_out': ctx.get('put_out'),
                    'toast': ctx.get('toast', lambda x, color='info': print(f"[TOAST] {x}")),
                    'run_ai_in_worker': ctx.get('run_ai_in_worker'),
                    'traceback': __import__('traceback'),
                }

                prompt = f"请生成以下需求的 Python 代码，只返回代码，不要解释：{requirement}"
                code = await get_gpt_response(llm_ctx, prompt, model_type=model_type)

                # 打印日志
                if log:
                    code_lines = len(code.split('\n'))
                    code_chars = len(code)
                    (f"[AI 代码生成] 代码生成成功，{code_lines} 行，{code_chars} 字符") >> log

                # 显示生成的代码和编辑窗口
                clear('chat_input_scope')
                with use_scope('chat_input_scope'):
                    put_markdown("### 📝 生成的代码")
                    put_markdown("**💡 提示：** 代码已生成，您可以在下方文本框中直接编辑修改")
                    
                    # 使用 textarea 提供可编辑的代码窗口
                    await put_textarea(
                        'generated_code',
                        value=code,
                        code={'mode': 'python', 'theme': 'darcula'},
                        rows=20,
                        placeholder='在此编辑代码...'
                    )
                    
                    put_markdown(f"> 🤖 使用模型：{model_type}")
                    
                    put_markdown("**📋 操作：**")
                    put_row([
                        put_button('📋 复制代码',
                                  onclick=lambda: run_async(copy_code_from_pin(ctx, 'generated_code')),
                                  color='primary'),
                        put_button('💾 保存到文件',
                                  onclick=lambda: run_async(save_code_to_file(ctx, 'generated_code')),
                                  color='success'),
                        put_button('🔄 重新生成',
                                  onclick=lambda: run_async(show_quick_chat_gen(ctx)),
                                  color='warning'),
                    ])
                
                toast('代码生成成功', color='success')
            except Exception as e:
                # 打印错误日志
                if log:
                    import traceback
                    (f"[AI 代码生成] 生成失败：{e}") >> log
                    traceback.format_exc() >> log
                
                clear('chat_input_scope')
                with use_scope('chat_input_scope'):
                    put_markdown(f"❌ 生成失败：{e}")
                toast(f'生成失败：{e}', color='error')


async def generate_code_simple(ctx, requirement: str):
    """简单代码生成 - 带可编辑窗口"""
    toast = ctx['toast']
    put_markdown = ctx['put_markdown']
    put_code = ctx['put_code']
    put_button = ctx['put_button']
    put_textarea = ctx['textarea']
    pin = ctx['pin']
    use_scope = ctx['use_scope']
    clear = ctx['clear']
    run_async = ctx['run_async']

    # 获取默认模型
    model_type = ctx.get('ai_default_model', 'deepseek')

    toast(f'正在使用 {model_type} 生成代码...', color='info')

    try:
        from deva.admin_ui.llm_service import get_gpt_response

        prompt = f"请生成以下需求的 Python 代码，只返回代码，不要解释：{requirement}"
        code = await get_gpt_response(ctx, prompt, model_type=model_type)

        # 显示生成的代码和编辑窗口
        with ctx['popup']('生成的代码', size='large', closable=True):
            put_markdown("### 📝 生成的代码")
            put_markdown("**💡 提示：** 代码已生成，您可以在下方文本框中直接编辑修改")
            
            # 使用 textarea 提供可编辑的代码窗口
            with use_scope('code_editor_scope'):
                await put_textarea(
                    'generated_code',
                    value=code,
                    code={'mode': 'python', 'theme': 'darcula'},
                    rows=20,
                    placeholder='在此编辑代码...'
                )
            
            put_markdown(f"> 🤖 使用模型：{model_type}")
            
            put_markdown("**📋 操作：**")
            put_button('📋 复制代码',
                      onclick=lambda: run_async(copy_code_from_pin(ctx, 'generated_code')),
                      color='primary')
            put_button('💾 保存到文件',
                      onclick=lambda: run_async(save_code_to_file(ctx, 'generated_code')),
                      color='success')
            put_button('🔄 重新生成',
                      onclick=lambda: run_async(regenerate_code(ctx, requirement)),
                      color='warning')

        toast('代码生成成功', color='success')
    except Exception as e:
        toast(f'生成失败：{e}', color='error')


async def copy_code_from_pin(ctx, pin_name: str):
    """从 pin 组件复制代码"""
    code = await ctx['pin'][pin_name]
    await ctx['run_js'](f"navigator.clipboard.writeText(`{code}`)")
    ctx['toast']('代码已复制到剪贴板', color='success')


async def save_code_to_file(ctx, pin_name: str):
    """保存代码到文件"""
    code = await ctx['pin'][pin_name]
    
    # 获取文件名
    filename = await ctx['input']('文件名', type='text', value='generated_code.py')
    
    if filename:
        try:
            from deva import write_to_file
            code >> write_to_file(filename)
            ctx['toast'](f'代码已保存到 {filename}', color='success')
        except Exception as e:
            ctx['toast'](f'保存失败：{e}', color='error')


async def regenerate_code(ctx, requirement: str):
    """重新生成代码"""
    ctx['clear']('code_editor_scope')
    await generate_code_simple(ctx, requirement)


async def show_quick_code_gen(ctx):
    """快速代码片段生成"""
    put_markdown = ctx['put_markdown']
    put_button = ctx['put_button']
    put_row = ctx['put_row']
    run_async = ctx['run_async']

    with ctx['popup']('代码片段生成', size='large', closable=True):
        put_markdown("### 📝 代码片段生成")
        put_markdown("**选择代码类型：**")

        put_row([
            put_button('🐍 Python 函数', onclick=lambda: run_async(show_quick_python_gen(ctx)), color='info'),
            put_button('📊 Deva 组件', onclick=lambda: run_async(show_quick_deva_gen(ctx)), color='info'),
        ])


async def show_quick_python_gen(ctx):
    """快速 Python 函数生成"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']

    with ctx['popup']('生成 Python 函数', size='large', closable=True):
        put_markdown("### 🐍 Python 函数生成")
        put_markdown("**示例：**")
        put_markdown("- 计算列表平均值")
        put_markdown("- 实现单例模式")
        put_markdown("- 装饰器计算执行时间")

        result = await ctx['input_group']('需求', [
            textarea('函数描述', name='description', required=True,
                    placeholder='描述函数功能...', rows=4),
            ctx['actions']('操作', [
                {'label': '🤖 生成', 'value': 'generate'},
            ], name='action')
        ])

        if result.get('action') == 'generate':
            await generate_code_simple(ctx, f"Python 函数：{result['description']}")


async def show_quick_deva_gen(ctx):
    """快速 Deva 组件生成"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']

    with ctx['popup']('生成 Deva 组件', size='large', closable=True):
        put_markdown("### 📊 Deva 组件生成")
        put_markdown("**示例：**")
        put_markdown("- 简单的数据过滤 Pipe")
        put_markdown("- 数据转换 Lambda")
        put_markdown("- Stream 处理函数")

        result = await ctx['input_group']('需求', [
            textarea('组件描述', name='description', required=True,
                    placeholder='描述组件功能...', rows=4),
            ctx['actions']('操作', [
                {'label': '🤖 生成', 'value': 'generate'},
            ], name='action')
        ])

        if result.get('action') == 'generate':
            await generate_code_simple(ctx, f"Deva 组件：{result['description']}")


# ============================================================================
# 创建中心（完整流程）
# ============================================================================

async def show_creation_center(ctx):
    """显示创建中心"""
    put_markdown = ctx['put_markdown']
    put_button = ctx['put_button']
    put_row = ctx['put_row']
    run_async = ctx['run_async']

    put_markdown("### 📦 创建中心")
    put_markdown("创建完整的数据源、策略、任务等 Deva 组件")

    put_markdown("**选择创建类型：**")
    put_row([
        put_button('📈 创建数据源', onclick=lambda: run_async(show_datasource_creator(ctx)), color='success'),
        put_button('📊 创建策略', onclick=lambda: run_async(show_strategy_creator(ctx)), color='primary'),
        put_button('⚙️ 创建任务', onclick=lambda: run_async(show_task_creator(ctx)), color='warning'),
        put_button('🔧 自定义组件', onclick=lambda: run_async(show_custom_component_creator(ctx)), color='info'),
    ])

    put_markdown("---")
    put_markdown("#### 💡 创建流程说明")
    put_markdown("""
    1. **选择类型** - 选择要创建的组件类型
    2. **配置参数** - 填写名称、描述、参数等
    3. **AI 生成代码** - AI 根据配置生成完整代码
    4. **预览调整** - 查看生成的代码，可选择调整
    5. **保存部署** - 保存到数据库并部署使用
    """)


async def show_custom_component_creator(ctx):
    """自定义组件创建器"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    radio = ctx['radio']

    with ctx['popup']('创建自定义组件', size='large', closable=True):
        put_markdown("### 🔧 自定义组件创建")

        put_markdown("**选择组件类型：**")
        component_type = await radio('组件类型', options=[
            ('stream', 'Stream 流'),
            ('pipe', 'Pipe 管道'),
            ('processor', 'Processor 处理器'),
            ('other', '其他'),
        ], name='component_type', required=True)

        put_markdown("**描述组件功能：**")
        config = await ctx['input_group']('配置', [
            textarea('组件描述', name='description', required=True,
                    placeholder='详细描述组件功能...', rows=6),
            ctx['input']('组件名称', name='name', type='text',
                        placeholder='例如：数据过滤器', required=True),
            ctx['actions']('操作', [
                {'label': '🤖 AI 生成', 'value': 'generate'},
            ], name='action')
        ])

        if config.get('action') == 'generate':
            await generate_component_code(ctx, config, component_type)


async def generate_component_code(ctx, config: dict, component_type: str):
    """生成组件代码"""
    toast = ctx['toast']
    put_markdown = ctx['put_markdown']
    put_code = ctx['put_code']
    put_button = ctx['put_button']

    toast('正在生成组件代码...', color='info')

    try:
        from deva.admin_ui.llm_service import get_gpt_response

        type_map = {
            'stream': 'Deva Stream 流处理组件',
            'pipe': 'Deva Pipe 数据管道组件',
            'processor': 'Deva Processor 数据处理组件',
            'other': 'Deva 组件',
        }

        prompt = f"""
        创建一个{type_map.get(component_type, 'Deva')}代码，要求：
        - 名称：{config.get('name', 'MyComponent')}
        - 功能：{config.get('description', '处理数据')}

        代码要求：
        1. 使用 Deva 框架规范
        2. 添加详细注释
        3. 包含错误处理
        4. 只返回 Python 代码
        """

        code = await get_gpt_response(ctx, prompt, model_type='deepseek')

        with ctx['popup']('生成的组件代码', size='large', closable=True):
            put_markdown(f"### 🔧 组件代码 - {config.get('name', 'Component')}")
            put_code(code)
            put_button('📋 复制代码',
                      onclick=lambda: ctx['run_js'](f"navigator.clipboard.writeText(`{code}`)"),
                      color='primary')

        toast('组件代码生成成功', color='success')
    except Exception as e:
        toast(f'生成失败：{e}', color='error')


# ============================================================================
# 生成中心（代码片段）
# ============================================================================

async def show_generation_center(ctx):
    """显示生成中心"""
    put_markdown = ctx['put_markdown']
    put_button = ctx['put_button']
    put_row = ctx['put_row']
    run_async = ctx['run_async']

    put_markdown("### ✨ 生成中心")
    put_markdown("快速生成代码片段，无需复杂配置")

    put_markdown("**选择生成类型：**")
    put_row([
        put_button('🐍 Python 代码', onclick=lambda: run_async(show_python_code_gen(ctx)), color='info'),
        put_button('📊 Deva 策略', onclick=lambda: run_async(show_deva_strategy_gen(ctx)), color='primary'),
        put_button('📈 Deva 数据源', onclick=lambda: run_async(show_deva_datasource_gen(ctx)), color='success'),
        put_button('⚙️ Deva 任务', onclick=lambda: run_async(show_deva_task_gen(ctx)), color='warning'),
    ])


# 从原有代码生成器导入
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


async def generate_code(ctx, prompt: str, code_type: str):
    """生成代码 - 带可编辑窗口和日志"""
    toast = ctx['toast']
    put_markdown = ctx['put_markdown']
    put_textarea = ctx['textarea']
    put_button = ctx['put_button']
    pin = ctx['pin']
    use_scope = ctx['use_scope']
    clear = ctx['clear']
    run_async = ctx['run_async']
    log = ctx.get('log')

    # 获取默认模型
    model_type = ctx.get('ai_default_model', 'deepseek')

    # 打印日志
    if log:
        (f"[AI 代码生成] 开始生成代码，模型：{model_type}, 类型：{code_type}") >> log

    toast(f'正在使用 {model_type} 生成代码...', color='info')

    try:
        from deva.admin_ui.llm_service import get_gpt_response

        # 打印日志
        if log:
            (f"[AI 代码生成] 正在调用 AI 服务...") >> log

        # 构建完整的上下文
        from openai import AsyncOpenAI
        import requests
        
        # 获取 log 和 warn 对象，并创建支持 >> 操作的包装器
        log_func = ctx.get('log')
        warn_func = ctx.get('warn', lambda x: print(f"[WARN] {x}"))
        
        # 创建支持 >> 操作的包装器（模拟 Deva Stream 行为）
        class LogWrapper:
            def __init__(self, func):
                self.func = func if func else (lambda x: print(f"[LOG] {x}"))
            def __rshift__(self, other):
                # 支持 stream >> func 模式
                self.func(other)
                return other
            def __rrshift__(self, other):
                # 支持 str >> LogWrapper 模式
                self.func(other)
                return other
            def __call__(self, msg):
                # 支持 func(msg) 直接调用
                self.func(msg)
                return msg
        
        llm_ctx = {
            'NB': ctx.get('NB'),
            'warn': LogWrapper(warn_func),
            'log': LogWrapper(log_func),
            'requests': requests,
            'AsyncOpenAI': AsyncOpenAI,
            'put_out': ctx.get('put_out'),
            'toast': ctx.get('toast', lambda x, color='info': print(f"[TOAST] {x}")),
            'run_ai_in_worker': ctx.get('run_ai_in_worker'),
            'traceback': __import__('traceback'),
        }

        system_prompt = "你是一个专业的 Python 开发者，请生成高质量、可运行的代码。只返回代码，不要其他说明。"
        full_prompt = f"{system_prompt}\n\n{prompt}"

        code = await get_gpt_response(llm_ctx, full_prompt, model_type=model_type)

        # 打印日志
        if log:
            code_lines = len(code.split('\n'))
            code_chars = len(code)
            (f"[AI 代码生成] 代码生成成功，{code_lines} 行，{code_chars} 字符") >> log

        # 显示生成的代码和编辑窗口
        with ctx['popup']('生成的代码', size='large', closable=True):
            put_markdown("### 📝 生成的代码")
            put_markdown("**💡 提示：** 代码已生成，您可以在下方文本框中直接编辑修改")
            
            # 使用 textarea 提供可编辑的代码窗口
            with use_scope('code_editor_scope'):
                await put_textarea(
                    'generated_code',
                    value=code,
                    code={'mode': 'python', 'theme': 'darcula'},
                    rows=20,
                    placeholder='在此编辑代码...'
                )
            
            put_markdown(f"> 🤖 使用模型：{model_type}")
            
            put_markdown("**📋 操作：**")
            put_button('📋 复制代码',
                      onclick=lambda: run_async(copy_code_from_pin(ctx, 'generated_code')),
                      color='primary')
            put_button('💾 保存到文件',
                      onclick=lambda: run_async(save_code_to_file(ctx, 'generated_code')),
                      color='success')
            put_button('🔄 重新生成',
                      onclick=lambda: run_async(regenerate_code(ctx, full_prompt)),
                      color='warning')

        toast('代码生成成功', color='success')
    except Exception as e:
        # 打印错误日志
        if log:
            import traceback
            (f"[AI 代码生成] 生成失败：{e}") >> log
            traceback.format_exc() >> log
        
        toast(f'生成失败：{e}', color='error')


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
            prompt = f"生成一个 Deva 任务代码，任务名称：{requirement['name']}，功能描述：{requirement['description']}，执行时间：{requirement['schedule']}。要求使用异步函数实现。"
            await generate_code(ctx, prompt, 'deva_task')


# ============================================================================
# 创建历史
# ============================================================================

async def show_creation_history(ctx):
    """显示创建历史"""
    put_markdown = ctx['put_markdown']
    put_table = ctx['put_table']

    put_markdown("### 📋 创建历史")
    put_markdown("查看最近创建的项目")

    creations = ctx.get('recent_creations', [])
    if not creations:
        put_markdown("*暂无创建记录*")
        return

    # 倒序显示，最新的在前
    creations = list(reversed(creations[-20:]))

    table_data = [['类型', '名称', '创建时间', '状态', '保存']]
    for item in creations:
        status_icon = '✅' if item.get('status') == 'success' else '❌'
        saved_icon = '💾' if item.get('saved') else '📋'
        time_str = time.strftime('%m-%d %H:%M', time.localtime(item.get('created_at', 0)))
        
        table_data.append([
            item.get('type', 'unknown'),
            item.get('name', 'unnamed'),
            time_str,
            status_icon,
            saved_icon
        ])

    put_table(table_data)


# ============================================================================
# 从 ai_code_creator 导入创建器
# ============================================================================

# 导入完整的创建器功能
from .ai_code_creator import (
    show_datasource_creator,
    show_strategy_creator,
    show_task_creator,
    add_to_recent_creations,
)


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    'show_ai_studio',
    'show_quick_chat_gen',
    'show_quick_code_gen',
    'show_creation_center',
    'show_generation_center',
    'show_creation_history',
]
