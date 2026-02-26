#!/usr/bin/env python
"""
Deva 管理面板 - 基于 PyWebIO 和 Tornado 的 Web 应用程序

核心功能：
- 实时数据流监控：访问日志、实时新闻、涨跌停数据、板块异动等
- 定时任务管理：查看和管理所有定时任务的执行状态
- 数据表展示：支持分页和实时更新的表格数据展示
- 日志系统：实时日志监控和手动日志写入
- 用户认证：基于用户名和密码的登录系统
- 数据库管理：支持 SQLite 数据库的 CRUD 操作和状态监控
- 流式处理：实时监控和操作 Deva 数据流
- 对象检查：支持 Python 对象的详细属性检查

主要模块：
- 数据流模块：实时监控多个数据流，包括访问日志、新闻、板块数据等
- 定时任务模块：展示所有定时任务的执行间隔、状态和生命周期
- 数据表模块：支持分页、过滤和实时更新的表格展示
- 日志模块：提供日志查看器和手动日志写入功能
- 用户认证模块：基于 PyWebIO 的 basic_auth 实现
- 数据库管理模块：提供 SQLite 数据库的 CRUD 操作和状态监控
- 流式处理模块：支持 Deva 数据流的实时监控和操作
- 对象检查模块：支持 Python 对象的详细属性检查

技术栈：
- 前端：PyWebIO
- 后端：Tornado
- 数据流：Deva 流处理框架
- 数据库：SQLite
- 缓存：基于 ExpiringDict 的缓存系统
- 异步处理：Tornado 异步框架
- 持久化存储：基于 DBStream 的时序数据存储

核心特性：
- 实时性：支持毫秒级数据更新和监控
- 可扩展性：模块化设计，易于功能扩展
- 安全性：完善的用户认证机制
- 易用性：简洁的 API 和直观的 Web 界面
- 高性能：基于异步 IO 的高效处理能力
- 持久化：支持数据自动持久化和历史数据回放

典型应用场景：
- 实时监控系统：设备指标、日志异常等实时监控
- 数据分析系统：流式 ETL、特征提取、模型预测
- 数据采集系统：智能爬虫、IoT 数据处理
- 任务调度系统：定时任务管理和监控
"""


# coding: utf-8

# In[2]:
import asyncio
import os
import traceback
import json
import time
import requests
from urllib.parse import urljoin
from typing import Callable, Union
import re
import inspect
import pkgutil
try:
    from .admin_ui import runtime as admin_runtime
    from .admin_ui import auth_routes as admin_auth
    from .admin_ui import auth_routes as admin_route_helpers
    from .admin_ui import document as admin_document
    from .admin_ui import tasks as admin_tasks
    from .admin_ui import tables as admin_tables
    from .admin_ui import main_ui as admin_main_ui
    from .admin_ui import llm_service as admin_llm_response_service
    from .admin_ui import contexts as admin_contexts
    from .admin_ui import monitor_routes as admin_monitor_routes
    from .admin_ui import monitor_ui as admin_monitor_ui
    from .admin_ui.strategy import panel as admin_strategy_panel
    from .admin_ui.strategy import runtime as admin_strategy_runtime
    from .admin_ui import follow_ui as admin_follow_ui
    from .admin_ui import browser_ui as admin_browser_ui
    from .llm.worker_runtime import run_ai_in_worker
    from .admin_ui import ai_center as admin_ai_center
except ImportError:
    # Allow running as a script: python deva/admin.py
    from deva.admin_ui import runtime as admin_runtime
    from deva.admin_ui import auth_routes as admin_auth
    from deva.admin_ui import auth_routes as admin_route_helpers
    from deva.admin_ui import document as admin_document
    from deva.admin_ui import tasks as admin_tasks
    from deva.admin_ui import tables as admin_tables
    from deva.admin_ui import main_ui as admin_main_ui
    from deva.admin_ui import llm_service as admin_llm_response_service
    from deva.admin_ui import contexts as admin_contexts
    from deva.admin_ui import monitor_routes as admin_monitor_routes
    from deva.admin_ui import monitor_ui as admin_monitor_ui
    from deva.admin_ui.strategy import panel as admin_strategy_panel
    from deva.admin_ui.strategy import runtime as admin_strategy_runtime
    from deva.admin_ui import follow_ui as admin_follow_ui
    from deva.admin_ui import browser_ui as admin_browser_ui
    from deva.llm.worker_runtime import run_ai_in_worker

import pandas as pd
from openai import AsyncOpenAI
from tornado.web import create_signed_value, decode_signed_value

from deva import (
    NW, NB, log, ls, Stream, first, sample, Deva, print, timer, NS, concat, Dtalk
)
from deva.store import DBStream
from deva.browser import browser, tab, tabs
from deva.bus import (
    warn,
    get_bus_runtime_status,
    get_bus_clients,
    get_bus_recent_messages,
    send_bus_message,
)
from deva.page import page  # 这里为了给流注入 webview 方法和sse 方法
from deva.llm import async_gpt, sync_gpt

from pywebio.output import (
    put_text, put_markdown, set_scope, put_table, use_scope, clear, toast, 
    put_button, put_collapse, put_datatable, put_buttons, put_row, put_html, 
    put_link, popup, close_popup, put_tabs, put_code
)
from pywebio.platform.tornado import webio_handler
from pywebio_battery import put_logbox, logbox_append, set_localstorage, get_localstorage
from pywebio.pin import pin, put_file_upload, put_input
from pywebio.session import set_env, run_async, run_js, run_asyncio_coroutine, get_session_implement
from pywebio.input import input, input_group, PASSWORD, textarea, actions, TEXT, file_upload, NUMBER, radio, select, checkbox


@timer(5,start=False)
def logtimer():
    """打印当前时间到 log 里"""
    return time.time()

_admin_runtime_initialized = False
_DOCUMENT_CACHE = {'ts': 0.0, 'data': None}
_DOCUMENT_CACHE_TTL = 60
DOCUMENT_MODULE_WHITELIST = admin_document.DOCUMENT_MODULE_WHITELIST


def setup_admin_runtime(enable_webviews=True, enable_timer=True, enable_scheduler=True, enable_strategy=True):
    """初始化 admin 运行时资源（幂等）。"""
    state = {
        'initialized': _admin_runtime_initialized,
        'logtimer': logtimer,
        'log': log,
        'browser': browser,
        'concat': concat,
        'NS': NS,
        'scheduler': scheduler,
        'enable_strategy': enable_strategy,
    }
    admin_runtime.setup_admin_runtime(
        state,
        enable_webviews=enable_webviews,
        enable_timer=enable_timer,
        enable_scheduler=enable_scheduler
    )
    globals()['_admin_runtime_initialized'] = state['initialized']


def _get_admin_streams():
    return admin_runtime.build_admin_streams(NS)


def _document_module_allowed(module_name):
    return admin_document.document_module_allowed(module_name)


def _extract_doc_examples(doc):
    return admin_document.extract_doc_examples(doc)


def _mask_attr_value(attr_name, value, limit=100):
    return admin_document.mask_attr_value(attr_name, value, limit=limit)


def _callable_smoke_eligibility(obj):
    return admin_document.callable_smoke_eligibility(obj)


async def _run_object_smoke_test(module_name, obj_name, obj, examples):
    return await admin_document.run_object_smoke_test(
        module_name,
        obj_name,
        obj,
        examples,
        toast=toast,
        popup=popup,
        put_markdown=put_markdown,
        put_table=put_table,
    )


def _scan_document_modules(use_cache=True):
    if not use_cache:
        _DOCUMENT_CACHE['ts'] = 0.0
        _DOCUMENT_CACHE['data'] = None
    return admin_document.scan_document_modules(
        cache=_DOCUMENT_CACHE,
        cache_ttl=_DOCUMENT_CACHE_TTL,
        warn=warn
    )


async def get_gpt_response(prompt, session=None, scope=None, model_type='kimi',flush_interval=3):
    return await admin_llm_response_service.get_gpt_response(
        {
            'NB': NB,
            'warn': warn,
            'log': log,
            'requests': requests,
            'AsyncOpenAI': AsyncOpenAI,
            'put_out': put_out,
            'toast': toast,
            'traceback': traceback,
            'run_ai_in_worker': run_ai_in_worker,
        },
        prompt,
        session=session,
        scope=scope,
        model_type=model_type,
        flush_interval=flush_interval,
    )


# tab('http://secsay.com')

def cut_foot():
    return admin_main_ui.cut_foot(_main_ui_ctx())


ExceedMaxTokenError = admin_route_helpers.ExceedMaxTokenError
OmittedContentError = admin_route_helpers.OmittedContentError



async def basic_auth(verify_func: Callable[[str, str], bool], secret: Union[str, bytes],
                     expire_days=7, token_name='pywebio_auth_token') -> str:
    """基于用户名和密码的持久化认证。"""
    return await admin_auth.basic_auth(
        verify_func=verify_func,
        secret=secret,
        expire_days=expire_days,
        token_name=token_name,
        decode_signed_value=decode_signed_value,
        create_signed_value=create_signed_value,
        get_localstorage=get_localstorage,
        set_localstorage=set_localstorage,
        input_group=input_group,
        input=input,
        PASSWORD=PASSWORD,
        toast=toast,
        log=log,
    )


async def write_to_log():
    return await admin_main_ui.write_to_log(_main_ui_ctx())


def put_out(msg, type='text',scope='',session=''):
        return admin_main_ui.put_out(_main_ui_ctx(), msg, type=type, scope=scope, session=session)

def scope_clear(scope,session):
        return admin_route_helpers.scope_clear(scope, session)


def show_timer_detail(t):
    return admin_main_ui.show_timer_detail(_main_ui_ctx(), t)

async def create_new_table():
    return await admin_tables.create_new_table_ui(_tables_ctx())

# 删除表的回调函数
async def delete_table(tablename):
    return await admin_tables.delete_table_ui(_tables_ctx(), tablename)

# 定义刷新数据表显示的函数
def refresh_table_display():
    return admin_tables.refresh_table_display_ui(_tables_ctx())

async def show_browser_status():
    return await admin_main_ui.show_browser_status(_main_ui_ctx())

def view_tab(tab):
    return admin_main_ui.view_tab(_main_ui_ctx(), tab)

def close_tab(tab):
    return admin_main_ui.close_tab(_main_ui_ctx(), tab)
    
async def open_new_tab():
    return await admin_main_ui.open_new_tab(_main_ui_ctx())

    


def init_floating_menu_manager():
    return admin_main_ui.init_floating_menu_manager(_main_ui_ctx())



# 在应用启动时调用


async def dynamic_popup(title, async_content_func):
    return await admin_main_ui.dynamic_popup(_main_ui_ctx(), title, async_content_func)
            

    

async def summarize_tabs():
    return await admin_main_ui.summarize_tabs(_main_ui_ctx())

async def async_json_gpt( prompts):
    return await admin_main_ui.async_json_gpt(_main_ui_ctx(), prompts)

async def extract_important_links(page):
    return await admin_main_ui.extract_important_links(_main_ui_ctx(), page)
        
def truncate(text, max_length=20):
    return admin_main_ui.truncate(text, max_length)

def set_table_style():
    return admin_main_ui.set_table_style(_main_ui_ctx())

def apply_global_styles():
    return admin_main_ui.apply_global_styles(_main_ui_ctx())

async def process_tabs(session):
    return await admin_main_ui.process_tabs(_main_ui_ctx(), session)

def extended_reading():
    return admin_main_ui.extended_reading(_main_ui_ctx())
    
    
async def close_all_tabs():
    return await admin_main_ui.close_all_tabs(_main_ui_ctx())



def create_sidebar():
    return admin_main_ui.create_sidebar(_main_ui_ctx())

async def init_admin_ui(title):
        return await admin_main_ui.init_admin_ui(_main_ui_ctx(), title)


from apscheduler.schedulers.tornado import TornadoScheduler
from pywebio import start_server
from pywebio.input import input, select, TEXT, textarea
from pywebio.output import put_text, put_table, put_button, toast, put_row, put_code
from pywebio.session import run_js
from datetime import datetime

# 初始化调度器
scheduler = TornadoScheduler()

# 存储任务信息
tasks = {}


async def watch_topic(topic):
    return await admin_tasks.watch_topic(_tasks_ctx(), topic)


async def create_task():
    return await admin_tasks.create_task(_tasks_ctx())


def manage_tasks():
    return admin_tasks.manage_tasks(_tasks_ctx())


def stop_task(name):
    return admin_tasks.stop_task(_tasks_ctx(), name)

def start_task(name):
    return admin_tasks.start_task(_tasks_ctx(), name)

def delete_task(name):
    return admin_tasks.delete_task(_tasks_ctx(), name)
        
def recover_task(name):
    return admin_tasks.recover_task(_tasks_ctx(), name)

def remove_task_forever(name):
    return admin_tasks.remove_task_forever(_tasks_ctx(), name)


def _tasks_ctx():
    return admin_contexts.tasks_ctx(globals())
    
async def taskadmin():
    await init_admin_ui('Deva任务管理')
    
    put_button("创建定时任务", onclick=create_task)
    manage_tasks()  # 直接展示任务列表
    set_scope('task_log')
  

async def dbadmin():
    """数据库管理入口函数"""
    await init_admin_ui('Deva数据库管理')
    refresh_table_display()

async def busadmin():
    return await admin_main_ui.render_bus_admin(_main_ui_ctx())

async def streamadmin():
    await init_admin_ui("Deva命名流管理")
    put_markdown('### 命名流列表')
    named_streams = [s for s in Stream.instances() if getattr(s, "name", None) and not isinstance(s, DBStream)]
    if not named_streams:
        put_text("暂无命名流")
        return
    
    def get_stream_sort_key(stream):
        has_description = 1 if getattr(stream, 'description', None) else 0
        last_update = getattr(stream, 'last_update_time', None) or 0
        return (has_description, last_update)
    
    def format_last_update(stream):
        last_update = getattr(stream, 'last_update_time', None)
        if not last_update:
            return "从未更新"
        
        import time
        from datetime import datetime
        time_diff = time.time() - last_update
        
        if time_diff < 60:
            return f"{int(time_diff)}秒前"
        elif time_diff < 3600:
            return f"{int(time_diff / 60)}分钟前"
        elif time_diff < 86400:
            return f"{int(time_diff / 3600)}小时前"
        else:
            dt = datetime.fromtimestamp(last_update)
            return dt.strftime("%m-%d %H:%M")
    
    def get_data_count(stream):
        if not stream.is_cache:
            return "未启用"
        try:
            return str(len(stream.cache))
        except Exception:
            return "0"
    
    named_streams.sort(key=get_stream_sort_key, reverse=True)
    
    table_data = [["流名称", "描述", "数据量", "最后更新", "操作"]]
    
    for s in named_streams:
        description = getattr(s, 'description', None) or '暂无描述'
        if len(description) > 50:
            description = description[:50] + "..."
        
        data_count = get_data_count(s)
        last_update = format_last_update(s)
        
        stream_name = s.name
        action_buttons = put_buttons(
            [{"label": "", "value": stream_name}],
            onclick=lambda name: stream_click(name)
        )
        
        table_data.append([
            f"**{stream_name}**",
            description,
            data_count,
            last_update,
            action_buttons
        ])
    
    put_table(table_data)
    
    put_markdown("---")
    put_markdown("💡 **提示**: 列表优先显示有描述的流，并按最新更新时间排序")


async def strategyadmin():
    from .admin_ui.strategy.strategy_panel import render_strategy_admin
    return await render_strategy_admin(_strategy_ctx())


async def datasourceadmin():
    from .admin_ui.strategy.datasource_panel import render_datasource_admin
    return await render_datasource_admin(_datasource_ctx())

async def followadmin():
    from .admin_ui.follow_ui import render_follow_ui
    return await render_follow_ui(_follow_ui_ctx())

async def browseradmin():
    from .admin_ui.browser_ui import render_browser_ui
    return await render_browser_ui(_browser_ui_ctx())

async def configadmin():
    from .admin_ui.config_ui import render_config_admin
    return await render_config_admin(_config_ui_ctx())

async def inspect_object(obj):
    return admin_document.inspect_object_ui(_document_ui_ctx(), obj)
async def document():
    await init_admin_ui("Deva管理面板")
    return admin_document.render_document_ui(_document_ui_ctx())


def _document_ui_ctx():
    return admin_contexts.document_ui_ctx(globals())

# ============================================================================
# AI 功能中心
# ============================================================================

async def aicenter():
    """AI 功能中心"""
    await init_admin_ui("Deva AI 功能中心")
    from .admin_ui.ai_center import render_ai_tab_ui
    return await render_ai_tab_ui(_aicenter_ctx())


def _aicenter_ctx():
    """AI 中心上下文"""
    return admin_contexts.main_ui_ctx(globals(), admin_tables)
def show_dtalk_archive():
    return admin_main_ui.show_dtalk_archive(_main_ui_ctx())

def view_dtalk_message(timestamp, message):
    return admin_main_ui.view_dtalk_message(_main_ui_ctx(), timestamp, message)

def delete_dtalk_message(timestamp):
    return admin_main_ui.delete_dtalk_message(_main_ui_ctx(), timestamp)

def clear_all_dtalk_messages():
    return admin_main_ui.clear_all_dtalk_messages(_main_ui_ctx())

async def main():
    return await admin_main_ui.render_main(_main_ui_ctx())


def _main_ui_ctx():
    return admin_contexts.main_ui_ctx(globals(), admin_tables)


def _tables_ctx():
    return admin_contexts.tables_ctx(globals(), admin_tables)


def _stream_ctx():
    return {
        'Stream': Stream,
        'toast': toast,
        'popup': popup,
        'put_markdown': put_markdown,
        'put_html': put_html,
        'put_table': put_table,
        'put_text': put_text,
        'put_buttons': put_buttons,
    }


def _strategy_ctx():
    return admin_contexts.strategy_ctx(globals())


def _datasource_ctx():
    return admin_contexts.datasource_ctx(globals())


def _follow_ui_ctx():
    return admin_contexts.follow_ui_ctx(globals(), admin_tables)

# 添加render_llm_config_guide到全局命名空间
def render_llm_config_guide(ctx, model_types=("kimi", "deepseek")):
    return admin_main_ui.render_llm_config_guide(ctx, model_types)

def _browser_ui_ctx():
    return admin_contexts.browser_ui_ctx(globals(), admin_tables)

def _config_ui_ctx():
    return admin_contexts.config_ui_ctx(globals())

def _monitor_ui_ctx():
    return admin_contexts.monitor_ui_ctx(globals())


async def monitor():
    return await admin_monitor_ui.render_monitor_home(_monitor_ui_ctx())


async def allstreams():
    return await admin_monitor_ui.render_all_streams(_monitor_ui_ctx())


async def alltables():
    return await admin_monitor_ui.render_all_tables(_monitor_ui_ctx())


def get_strategy_config():
    return admin_strategy_runtime.get_strategy_config()


def set_strategy_config(force_fetch=None, sync_bus=None):
    return admin_strategy_runtime.set_strategy_config(force_fetch=force_fetch, sync_bus=sync_bus)


def get_strategy_basic_meta():
    return admin_strategy_runtime.get_strategy_basic_meta()


def refresh_strategy_basic_df(force=True):
    return admin_strategy_runtime.refresh_strategy_basic_df(force=force)


async def refresh_strategy_basic_df_async(force=True):
    return await admin_strategy_runtime.refresh_strategy_basic_df_async(force=force)


def get_replay_config():
    return admin_strategy_runtime.get_replay_config()


def set_replay_config(mode=None, replay_date=None, replay_interval=None):
    return admin_strategy_runtime.set_replay_config(mode=mode, replay_date=replay_date, replay_interval=replay_interval)


def get_history_metadata():
    return admin_strategy_runtime.get_history_metadata()


def save_current_quant_to_history():
    return admin_strategy_runtime.save_current_quant_to_history()


def get_auto_save_config():
    return admin_strategy_runtime.get_auto_save_config()


def set_auto_save(enabled):
    return admin_strategy_runtime.set_auto_save(enabled)


def get_tick_metadata():
    return admin_strategy_runtime.get_tick_metadata()


def get_tick_stream():
    return admin_strategy_runtime.get_tick_stream()


def get_tick_keys_in_range(start, end=None):
    return admin_strategy_runtime.get_tick_keys_in_range(start, end)


def load_tick_by_key(key):
    return admin_strategy_runtime.load_tick_by_key(key)


def replay_ticks(start, end=None, interval=None):
    return admin_strategy_runtime.replay_ticks(start, end, interval)


def is_replay_running():
    return admin_strategy_runtime.is_replay_running()


def start_history_replay(date_str=None, interval=5.0, use_ticks=False, start_time=None, end_time=None):
    return admin_strategy_runtime.start_history_replay(
        date_str=date_str, interval=interval, use_ticks=use_ticks,
        start_time=start_time, end_time=end_time
    )


def stop_history_replay():
    return admin_strategy_runtime.stop_history_replay()


def paginate_dataframe(scope,df, page_size):
    return admin_tables.paginate_dataframe(_tables_ctx(), scope, df, page_size)



def display_table_basic_info(db, tablename):
    return admin_tables.display_table_basic_info(_tables_ctx(), db, tablename)
    
@use_scope('table_content')
def table_click(tablename):
    return admin_tables.table_click(_tables_ctx(), tablename)

# 保存修改的回调函数
async def save_string(key,data,tablename):
    return await admin_tables.save_string(_tables_ctx(), key, data, tablename)
# 删除DataFrame的回调函数
async def delete_dataframe(df_name, tablename):
    return await admin_tables.delete_dataframe(_tables_ctx(), df_name, tablename)

# 删除键值对的回调函数
async def delete_string(key,data,tablename):
    return await admin_tables.delete_string(_tables_ctx(), key, data, tablename)

# 新增键值对的回调函数
async def add_string(data,tablename):
    return await admin_tables.add_string(_tables_ctx(), data, tablename)

def edit_data_popup(data,tablename):
    return admin_tables.edit_data_popup(_tables_ctx(), data, tablename)

def stream_click(streamname):
    return admin_route_helpers.stream_click(_stream_ctx(), streamname)


def create_nav_menu():
    return admin_main_ui.create_nav_menu(_main_ui_ctx())


if __name__ == '__main__':
    from deva.page import page
    setup_admin_runtime(enable_webviews=True, enable_timer=True, enable_scheduler=True)
    admin_tasks.restore_tasks_from_db(_tasks_ctx())  # 系统启动时从数据库恢复任务
    # 系统启动时恢复数据源的运行状态
    from .admin_ui.strategy.datasource import get_ds_manager
    ds_mgr = get_ds_manager()
    # 先从数据库加载数据源配置，再恢复运行状态
    ds_mgr.load_from_db()
    ds_mgr.restore_running_states()

    # 创建一个名为'stream_webview'的Web服务器实例，监听所有网络接口(0.0.0.0)
    # 然后为该服务器添加路由处理器，将'/admin'路径映射到dbadmin处理函数
    # 使用PyWebIO的webio_handler进行封装，并指定CDN地址
    cdn='https://fastly.jsdelivr.net/gh/wang0618/PyWebIO-assets@v1.8.3/'
    handlers = [
        (r'/dbadmin', webio_handler(dbadmin, cdn=cdn)),
        (r'/busadmin', webio_handler(busadmin, cdn=cdn)),
        (r'/streamadmin', webio_handler(streamadmin, cdn=cdn)),
        (r'/strategyadmin', webio_handler(strategyadmin, cdn=cdn)),
        (r'/datasourceadmin', webio_handler(datasourceadmin, cdn=cdn)),
        (r'/followadmin', webio_handler(followadmin, cdn=cdn)),
        (r'/browseradmin', webio_handler(browseradmin, cdn=cdn)),
        (r'/configadmin', webio_handler(configadmin, cdn=cdn)),
        (r'/', webio_handler(main, cdn=cdn)),
        (r'/taskadmin', webio_handler(taskadmin, cdn=cdn)),
        (r'/document', webio_handler(document, cdn=cdn)),
        (r'/aicenter', webio_handler(aicenter, cdn=cdn)),
        (r'/monitor', webio_handler(monitor, cdn=cdn)),
        (r'/allstreams', webio_handler(allstreams, cdn=cdn)),
        (r'/alltables', webio_handler(alltables, cdn=cdn)),
        *admin_monitor_routes.monitor_route_handlers(globals()),
    ]
    NW('stream_webview',host='0.0.0.0').application.add_handlers('.*$', handlers)
 

    Deva.run()
