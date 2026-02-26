#!/usr/bin/env python
# coding: utf-8
"""
AI 代码创建组件

提供 AI 辅助创建 Deva 数据源、策略、任务等功能，支持一键保存和部署。
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, Any, List, Optional


# ============================================================================
# AI 代码创建器主界面
# ============================================================================

async def show_ai_code_creator(ctx):
    """显示 AI 代码创建器主界面"""
    put_markdown = ctx['put_markdown']
    put_button = ctx['put_button']
    put_row = ctx['put_row']
    put_collapse = ctx['put_collapse']
    run_async = ctx['run_async']

    put_markdown("### 🤖 AI 代码创建器")
    put_markdown("使用 AI 辅助创建 Deva 数据源、策略、任务，支持一键保存和部署")

    # 快速创建选项
    put_markdown("**快速创建：**")
    put_row([
        put_button('📈 创建数据源', onclick=lambda: run_async(show_datasource_creator(ctx)), color='success'),
        put_button('📊 创建策略', onclick=lambda: run_async(show_strategy_creator(ctx)), color='primary'),
        put_button('⚙️ 创建任务', onclick=lambda: run_async(show_task_creator(ctx)), color='warning'),
        put_button('🔧 自定义代码', onclick=lambda: run_async(show_custom_code_creator(ctx)), color='info'),
    ])

    put_markdown("---")

    # 显示最近创建的项目
    with ctx['use_scope']('recent_creations'):
        show_recent_creations(ctx)


def show_recent_creations(ctx):
    """显示最近创建的项目"""
    put_markdown = ctx['put_markdown']
    put_table = ctx['put_table']

    put_markdown("#### 📋 最近创建")

    # 从上下文获取最近创建记录
    creations = ctx.get('recent_creations', [])
    if not creations:
        put_markdown("*暂无创建记录*")
        return

    table_data = [['类型', '名称', '创建时间', '状态', '操作']]
    for item in creations[-5:]:
        status_color = '✅' if item.get('status') == 'success' else '❌'
        table_data.append([
            item.get('type', 'unknown'),
            item.get('name', 'unnamed'),
            time.strftime('%m-%d %H:%M', time.localtime(item.get('created_at', 0))),
            status_color,
            '已保存' if item.get('saved') else '未保存'
        ])

    put_table(table_data)


# ============================================================================
# 数据源创建器
# ============================================================================

async def show_datasource_creator(ctx):
    """显示数据源创建器"""
    put_markdown = ctx['put_markdown']
    put_button = ctx['put_button']
    put_row = ctx['put_row']
    run_async = ctx['run_async']

    with ctx['popup']('创建数据源', size='large', closable=True):
        put_markdown("### 📈 AI 辅助创建数据源")

        put_markdown("""
        **数据源类型：**
        - **定时器数据源**: 定时获取数据（如每秒获取股票价格）
        - **HTTP 数据源**: 从 HTTP 接口获取数据
        - **文件数据源**: 从文件读取数据
        - **Kafka 数据源**: 从 Kafka 消费数据
        - **自定义数据源**: 自定义逻辑获取数据
        """)

        put_row([
            put_button('⏱️ 定时器数据源', onclick=lambda: run_async(create_timer_datasource(ctx)), color='primary'),
            put_button('🌐 HTTP 数据源', onclick=lambda: run_async(create_http_datasource(ctx)), color='primary'),
            put_button('📁 文件数据源', onclick=lambda: run_async(create_file_datasource(ctx)), color='primary'),
            put_button('🔧 自定义数据源', onclick=lambda: run_async(create_custom_datasource(ctx)), color='info'),
        ])


async def create_timer_datasource(ctx):
    """创建定时器数据源"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    input_comp = ctx['input']

    with ctx['popup']('创建定时器数据源', size='large', closable=True):
        put_markdown("### ⏱️ 定时器数据源")

        put_markdown("""
        **示例需求：**
        - "每 5 秒获取一次 AAPL 股票价格"
        - "每分钟获取一次比特币价格"
        - "每小时记录一次系统 CPU 使用率"
        """)

        config = await ctx['input_group']('配置', [
            textarea('数据源描述', name='description', required=True,
                    placeholder='描述数据源功能，如：每 5 秒获取一次 AAPL 股票价格', rows=4),
            input_comp('数据源名称', name='name', type='text',
                      placeholder='例如：AAPL 股价数据源', required=True),
            input_comp('更新间隔 (秒)', name='interval', type='number',
                      value='5.0', required=True),
            ctx['actions']('操作', [
                {'label': '🤖 AI 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])

        if config['action'] == 'generate':
            await generate_datasource_code(ctx, config, 'timer')


async def create_http_datasource(ctx):
    """创建 HTTP 数据源"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    input_comp = ctx['input']

    with ctx['popup']('创建 HTTP 数据源', size='large', closable=True):
        put_markdown("### 🌐 HTTP 数据源")

        put_markdown("""
        **示例需求：**
        - "从 CoinGecko API 获取加密货币价格"
        - "从天气 API 获取北京天气数据"
        """)

        config = await ctx['input_group']('配置', [
            textarea('数据源描述', name='description', required=True,
                    placeholder='描述数据源功能，如：从 CoinGecko API 获取比特币价格', rows=4),
            input_comp('数据源名称', name='name', type='text',
                      placeholder='例如：加密货币数据源', required=True),
            input_comp('API URL', name='api_url', type='text',
                      placeholder='https://api.coingecko.com/api/v3/...', required=False),
            ctx['actions']('操作', [
                {'label': '🤖 AI 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])

        if config['action'] == 'generate':
            await generate_datasource_code(ctx, config, 'http')


async def create_file_datasource(ctx):
    """创建文件数据源"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    input_comp = ctx['input']

    with ctx['popup']('创建文件数据源', size='large', closable=True):
        put_markdown("### 📁 文件数据源")

        put_markdown("""
        **示例需求：**
        - "读取 CSV 文件，解析为字典"
        - "从 JSON 文件加载配置数据"
        """)

        config = await ctx['input_group']('配置', [
            textarea('数据源描述', name='description', required=True,
                    placeholder='描述数据源功能，如：读取 CSV 文件并解析', rows=4),
            input_comp('数据源名称', name='name', type='text',
                      placeholder='例如：CSV 数据源', required=True),
            input_comp('文件路径', name='file_path', type='text',
                      placeholder='/path/to/file.csv', required=False),
            ctx['actions']('操作', [
                {'label': '🤖 AI 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])

        if config['action'] == 'generate':
            await generate_datasource_code(ctx, config, 'file')


async def create_custom_datasource(ctx):
    """创建自定义数据源"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    input_comp = ctx['input']

    with ctx['popup']('创建自定义数据源', size='large', closable=True):
        put_markdown("### 🔧 自定义数据源")

        put_markdown("**描述你的数据源需求，AI 会生成完整代码：**")

        config = await ctx['input_group']('配置', [
            textarea('数据源描述', name='description', required=True,
                    placeholder='详细描述数据源功能...', rows=6),
            input_comp('数据源名称', name='name', type='text',
                      placeholder='例如：自定义数据源', required=True),
            ctx['actions']('操作', [
                {'label': '🤖 AI 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])

        if config['action'] == 'generate':
            await generate_datasource_code(ctx, config, 'custom')


async def generate_datasource_code(ctx, config: dict, source_type: str):
    """生成数据源代码"""
    toast = ctx['toast']
    put_markdown = ctx['put_markdown']
    put_code = ctx['put_code']
    put_button = ctx['put_button']

    toast('正在生成数据源代码...', color='info')

    try:
        from deva.admin_ui.llm_service import get_gpt_response

        # 构建提示词
        prompt = f"""
        创建一个 Deva DataSource 数据源代码，要求：
        - 名称：{config.get('name', 'MyDataSource')}
        - 类型：{source_type}
        - 功能：{config.get('description', '获取数据')}
        """

        if source_type == 'timer':
            prompt += f"""
        - 更新间隔：{config.get('interval', '5.0')}秒
        - 使用定时器等间隔获取数据
        """
        elif source_type == 'http':
            prompt += f"""
        - API URL: {config.get('api_url', '')}
        - 使用 httpx 库发送 HTTP 请求
        - 解析 JSON 响应
        """
        elif source_type == 'file':
            prompt += f"""
        - 文件路径：{config.get('file_path', '')}
        - 读取文件并解析数据
        """

        prompt += """
        代码要求：
        1. 使用 DataSource 类
        2. 实现 fetch_data 方法
        3. 添加详细注释
        4. 包含错误处理
        5. 只返回 Python 代码，不要其他说明
        """

        code = await get_gpt_response(ctx, prompt, model_type='deepseek')

        # 显示生成的代码和操作按钮
        with ctx['popup']('生成的数据源代码', size='large', closable=True):
            put_markdown(f"### 📈 数据源代码 - {config.get('name', 'DataSource')}")
            put_code(code)

            put_markdown("**操作：**")
            put_button('📋 复制代码',
                      onclick=lambda: ctx['run_js'](f"navigator.clipboard.writeText(`{code}`)"),
                      color='primary')
            put_button('💾 保存并创建',
                      onclick=lambda: run_async(save_datasource(ctx, config, code)),
                      color='success')

        toast('数据源代码生成成功', color='success')

    except Exception as e:
        toast(f'生成失败：{e}', color='error')


async def save_datasource(ctx, config: dict, code: str):
    """保存数据源到数据库"""
    toast = ctx['toast']
    put_markdown = ctx['put_markdown']
    close_popup = ctx.get('close_popup')

    try:
        from deva.admin_ui.strategy.datasource import DataSource, DataSourceType, get_ds_manager

        # 映射类型 - 从 config 中获取 source_type
        source_type_str = config.get('source_type', 'custom')
        type_map = {
            'timer': DataSourceType.TIMER,
            'http': DataSourceType.HTTP,
            'file': DataSourceType.FILE,
            'custom': DataSourceType.CUSTOM,
        }

        # 获取间隔
        interval = 5.0
        try:
            interval = float(config.get('interval', 5.0))
        except (ValueError, TypeError):
            pass

        # 创建数据源
        ds_mgr = get_ds_manager()
        result = ds_mgr.create_source(
            name=config.get('name', 'DataSource'),
            source_type=type_map.get(source_type_str, DataSourceType.CUSTOM),
            description=config.get('description', ''),
            data_func_code=code,
            interval=interval,
            auto_start=False,
        )

        if result.get('success'):
            # 添加到最近创建
            await add_to_recent_creations(ctx, {
                'type': '数据源',
                'name': config.get('name'),
                'status': 'success',
                'saved': True,
                'created_at': time.time(),
            })

            toast(f"数据源 '{config.get('name')}' 创建成功！", color='success')

            # 关闭弹窗
            if close_popup:
                close_popup()

            # 显示成功信息
            with ctx['popup']('创建成功', closable=True):
                put_markdown(f"### ✅ 数据源创建成功")
                put_markdown(f"**名称：** {config.get('name')}")
                put_markdown(f"**ID：** {result.get('source_id')}")
                put_markdown("**下一步：**")
                put_markdown("1. 前往「数据源管理」页面查看")
                put_markdown("2. 点击「启动」按钮开始运行")
                put_markdown("3. 在策略中订阅此数据源")
        else:
            toast(f"保存失败：{result.get('error')}", color='error')

    except Exception as e:
        toast(f'保存失败：{e}', color='error')


# ============================================================================
# 策略创建器
# ============================================================================

async def show_strategy_creator(ctx):
    """显示策略创建器"""
    put_markdown = ctx['put_markdown']
    put_button = ctx['put_button']
    put_row = ctx['put_row']
    run_async = ctx['run_async']

    with ctx['popup']('创建策略', size='large', closable=True):
        put_markdown("### 📊 AI 辅助创建量化策略")

        put_markdown("""
        **策略类型：**
        - **均线策略**: 双均线、多均线等
        - **指标策略**: MACD、RSI、KDJ 等技术指标
        - **动量策略**: 趋势跟踪、均值回归
        - **自定义策略**: 自定义交易逻辑
        """)

        put_row([
            put_button('📈 均线策略', onclick=lambda: run_async(create_ma_strategy(ctx)), color='primary'),
            put_button('📊 指标策略', onclick=lambda: run_async(create_indicator_strategy(ctx)), color='primary'),
            put_button('🔧 自定义策略', onclick=lambda: run_async(create_custom_strategy(ctx)), color='info'),
        ])


async def create_ma_strategy(ctx):
    """创建均线策略"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    input_comp = ctx['input']

    with ctx['popup']('创建均线策略', size='large', closable=True):
        put_markdown("### 📈 均线策略")

        put_markdown("""
        **经典均线策略：**
        - 双均线：5 日/20 日金叉买入，死叉卖出
        - 多均线：5/10/20/60 日均线多头排列买入
        """)

        config = await ctx['input_group']('配置', [
            textarea('策略描述', name='description', required=True,
                    placeholder='描述策略逻辑，如：双均线策略，5 日线上穿 20 日线买入，下穿卖出', rows=4),
            input_comp('策略名称', name='name', type='text',
                      placeholder='例如：双均线策略', required=True),
            input_comp('短期均线周期', name='short_period', type='number',
                      value='5', required=True),
            input_comp('长期均线周期', name='long_period', type='number',
                      value='20', required=True),
            ctx['actions']('操作', [
                {'label': '🤖 AI 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])

        if config['action'] == 'generate':
            await generate_strategy_code(ctx, config, 'ma')


async def create_indicator_strategy(ctx):
    """创建指标策略"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    input_comp = ctx['input']

    with ctx['popup']('创建指标策略', size='large', closable=True):
        put_markdown("### 📊 技术指标策略")

        config = await ctx['input_group']('配置', [
            textarea('策略描述', name='description', required=True,
                    placeholder='描述策略逻辑，如：MACD 金叉买入，死叉卖出', rows=4),
            input_comp('策略名称', name='name', type='text',
                      placeholder='例如：MACD 策略', required=True),
            input_comp('技术指标', name='indicator', type='text',
                      placeholder='例如：MACD, RSI, KDJ', required=True),
            ctx['actions']('操作', [
                {'label': '🤖 AI 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])

        if config['action'] == 'generate':
            await generate_strategy_code(ctx, config, 'indicator')


async def create_custom_strategy(ctx):
    """创建自定义策略"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    input_comp = ctx['input']

    with ctx['popup']('创建自定义策略', size='large', closable=True):
        put_markdown("### 🔧 自定义策略")

        put_markdown("**描述你的策略逻辑，AI 会生成完整代码：**")

        config = await ctx['input_group']('配置', [
            textarea('策略描述', name='description', required=True,
                    placeholder='详细描述策略逻辑...', rows=6),
            input_comp('策略名称', name='name', type='text',
                      placeholder='例如：自定义策略', required=True),
            ctx['actions']('操作', [
                {'label': '🤖 AI 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])

        if config['action'] == 'generate':
            await generate_strategy_code(ctx, config, 'custom')


async def generate_strategy_code(ctx, config: dict, strategy_type: str):
    """生成策略代码"""
    toast = ctx['toast']
    put_markdown = ctx['put_markdown']
    put_code = ctx['put_code']
    put_button = ctx['put_button']

    toast('正在生成策略代码...', color='info')

    try:
        from deva.admin_ui.llm_service import get_gpt_response

        prompt = f"""
        创建一个 Deva StrategyUnit 量化策略代码，要求：
        - 名称：{config.get('name', 'MyStrategy')}
        - 类型：{strategy_type}
        - 策略逻辑：{config.get('description', '交易策略')}
        """

        if strategy_type == 'ma':
            prompt += f"""
        - 短期均线：{config.get('short_period', '5')}周期
        - 长期均线：{config.get('long_period', '20')}周期
        - 金叉买入，死叉卖出
        """
        elif strategy_type == 'indicator':
            prompt += f"""
        - 技术指标：{config.get('indicator', 'MACD')}
        - 根据指标信号交易
        """

        prompt += """
        代码要求：
        1. 使用 StrategyUnit 类
        2. 实现 process 方法处理数据
        3. 实现 generate_signals 方法生成交易信号
        4. 添加详细注释
        5. 包含错误处理
        6. 只返回 Python 代码，不要其他说明
        """

        code = await get_gpt_response(ctx, prompt, model_type='deepseek')

        # 显示代码
        with ctx['popup']('生成的策略代码', size='large', closable=True):
            put_markdown(f"### 📊 策略代码 - {config.get('name', 'Strategy')}")
            put_code(code)

            put_markdown("**操作：**")
            put_button('📋 复制代码',
                      onclick=lambda: ctx['run_js'](f"navigator.clipboard.writeText(`{code}`)"),
                      color='primary')
            put_button('💾 保存并创建',
                      onclick=lambda: run_async(save_strategy(ctx, config, code)),
                      color='success')

        toast('策略代码生成成功', color='success')

    except Exception as e:
        toast(f'生成失败：{e}', color='error')


async def save_strategy(ctx, config: dict, code: str):
    """保存策略到数据库"""
    toast = ctx['toast']
    close_popup = ctx.get('close_popup')

    try:
        # 这里调用策略管理器的创建方法
        # 由于策略创建较复杂，暂时只保存代码
        await add_to_recent_creations(ctx, {
            'type': '策略',
            'name': config.get('name'),
            'status': 'success',
            'saved': False,
            'created_at': time.time(),
            'code': code,
        })

        toast(f"策略 '{config.get('name')}' 代码已生成，请手动保存", color='success')

        # 关闭弹窗
        if close_popup:
            close_popup()

        with ctx['popup']('创建成功', closable=True):
            put_markdown(f"### ✅ 策略代码生成成功")
            put_markdown(f"**名称：** {config.get('name')}")
            put_markdown("**下一步：**")
            put_markdown("1. 复制代码")
            put_markdown("2. 前往「策略管理」页面")
            put_markdown("3. 创建新策略并粘贴代码")
            put_markdown("4. 配置数据源和参数")

    except Exception as e:
        toast(f'保存失败：{e}', color='error')


# ============================================================================
# 任务创建器
# ============================================================================

async def show_task_creator(ctx):
    """显示任务创建器"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    input_comp = ctx['input']

    with ctx['popup']('创建任务', size='large', closable=True):
        put_markdown("### ⚙️ AI 辅助创建定时任务")

        put_markdown("""
        **示例任务：**
        - 每天凌晨 2 点备份数据库
        - 每小时检查系统状态
        - 每分钟记录一次指标
        """)

        config = await ctx['input_group']('配置', [
            textarea('任务描述', name='description', required=True,
                    placeholder='描述任务功能，如：每天凌晨 2 点备份数据库', rows=4),
            input_comp('任务名称', name='name', type='text',
                      placeholder='例如：数据库备份', required=True),
            input_comp('执行时间', name='schedule', type='text',
                      placeholder='例如：每天 02:00 或 3600(秒)', required=True),
            ctx['actions']('操作', [
                {'label': '🤖 AI 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])

        if config['action'] == 'generate':
            await generate_task_code(ctx, config)


async def generate_task_code(ctx, config: dict):
    """生成任务代码"""
    toast = ctx['toast']
    put_markdown = ctx['put_markdown']
    put_code = ctx['put_code']
    put_button = ctx['put_button']

    toast('正在生成任务代码...', color='info')

    try:
        from deva.admin_ui.llm_service import get_gpt_response

        prompt = f"""
        创建一个 Deva 定时任务代码，要求：
        - 任务名称：{config.get('name', 'MyTask')}
        - 执行时间：{config.get('schedule', '每天 00:00')}
        - 任务功能：{config.get('description', '执行任务')}

        代码要求：
        1. 使用异步函数
        2. 添加详细注释
        3. 包含错误处理
        4. 只返回 Python 代码，不要其他说明
        """

        code = await get_gpt_response(ctx, prompt, model_type='deepseek')

        # 显示代码
        with ctx['popup']('生成的任务代码', size='large', closable=True):
            put_markdown(f"### ⚙️ 任务代码 - {config.get('name', 'Task')}")
            put_code(code)

            put_markdown("**操作：**")
            put_button('📋 复制代码',
                      onclick=lambda: ctx['run_js'](f"navigator.clipboard.writeText(`{code}`)"),
                      color='primary')
            put_button('💾 保存并创建',
                      onclick=lambda: run_async(save_task(ctx, config, code)),
                      color='success')

        toast('任务代码生成成功', color='success')

    except Exception as e:
        toast(f'生成失败：{e}', color='error')


async def save_task(ctx, config: dict, code: str):
    """保存任务到数据库"""
    toast = ctx['toast']
    close_popup = ctx.get('close_popup')

    try:
        await add_to_recent_creations(ctx, {
            'type': '任务',
            'name': config.get('name'),
            'status': 'success',
            'saved': False,
            'created_at': time.time(),
            'code': code,
        })

        toast(f"任务 '{config.get('name')}' 代码已生成", color='success')

        # 关闭弹窗
        if close_popup:
            close_popup()

    except Exception as e:
        toast(f'保存失败：{e}', color='error')


# ============================================================================
# 自定义代码创建器
# ============================================================================

async def show_custom_code_creator(ctx):
    """显示自定义代码创建器"""
    put_markdown = ctx['put_markdown']
    textarea = ctx['textarea']
    radio = ctx['radio']

    with ctx['popup']('自定义代码创建', size='large', closable=True):
        put_markdown("### 🔧 自定义代码创建")

        put_markdown("**选择代码类型：**")
        code_type = await radio('代码类型', options=[
            ('python', 'Python 通用代码'),
            ('deva_stream', 'Deva 流处理'),
            ('deva_pipe', 'Deva 管道'),
            ('other', '其他'),
        ], name='code_type', required=True)

        put_markdown("**描述你的需求：**")
        config = await ctx['input_group']('需求', [
            textarea('需求描述', name='description', required=True,
                    placeholder='详细描述你需要的代码功能...', rows=6),
            ctx['actions']('操作', [
                {'label': '🤖 AI 生成代码', 'value': 'generate'},
                {'label': '❌ 取消', 'value': 'cancel'}
            ], name='action')
        ])

        if config['action'] == 'generate':
            await generate_custom_code(ctx, config, code_type)


async def generate_custom_code(ctx, config: dict, code_type: str):
    """生成自定义代码"""
    toast = ctx['toast']
    put_markdown = ctx['put_markdown']
    put_code = ctx['put_code']
    put_button = ctx['put_button']

    toast('正在生成代码...', color='info')

    try:
        from deva.admin_ui.llm_service import get_gpt_response

        type_prompts = {
            'python': 'Python 通用代码',
            'deva_stream': 'Deva 流处理代码，使用 Stream 类',
            'deva_pipe': 'Deva 管道代码，使用 Pipe 类',
            'other': 'Python 代码',
        }

        prompt = f"""
        生成{type_prompts.get(code_type, 'Python')}代码，要求：
        - 功能：{config.get('description', '实现功能')}

        代码要求：
        1. 添加详细注释
        2. 包含错误处理
        3. 只返回 Python 代码，不要其他说明
        """

        code = await get_gpt_response(ctx, prompt, model_type='deepseek')

        # 显示代码
        with ctx['popup']('生成的代码', size='large', closable=True):
            put_markdown("### 🔧 生成的代码")
            put_code(code)

            put_markdown("**操作：**")
            put_button('📋 复制代码',
                      onclick=lambda: ctx['run_js'](f"navigator.clipboard.writeText(`{code}`)"),
                      color='primary')

        toast('代码生成成功', color='success')

    except Exception as e:
        toast(f'生成失败：{e}', color='error')


# ============================================================================
# 工具函数
# ============================================================================

async def add_to_recent_creations(ctx, item: dict):
    """添加到最近创建列表"""
    if 'recent_creations' not in ctx:
        ctx['recent_creations'] = []

    ctx['recent_creations'].append(item)

    # 限制最多保存 20 条
    if len(ctx['recent_creations']) > 20:
        ctx['recent_creations'] = ctx['recent_creations'][-20:]

    # 刷新显示
    try:
        ctx['clear']('recent_creations')
        with ctx['use_scope']('recent_creations'):
            show_recent_creations(ctx)
    except Exception:
        # 忽略刷新错误
        pass


# ============================================================================
# 导出接口
# ============================================================================

__all__ = [
    'show_ai_code_creator',
    'show_datasource_creator',
    'show_strategy_creator',
    'show_task_creator',
    'show_custom_code_creator',
]
