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
    from .admin_ui.stock import panel as admin_stock_panel
    from .admin_ui.stock import runtime as admin_stock_runtime
    from .llm.worker_runtime import run_ai_in_worker
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
    from deva.admin_ui.stock import panel as admin_stock_panel
    from deva.admin_ui.stock import runtime as admin_stock_runtime
    from deva.llm.worker_runtime import run_ai_in_worker

import pandas as pd
from openai import AsyncOpenAI
from tornado.web import create_signed_value, decode_signed_value

from deva import (
    NW, NB, log, ls, Stream, first, sample, Deva, print, timer, NS, concat, Dtalk
)
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
    put_link, popup, close_popup, put_tabs
)
from pywebio.platform.tornado import webio_handler
from pywebio_battery import put_logbox, logbox_append, set_localstorage, get_localstorage
from pywebio.pin import pin, put_file_upload, put_input
from pywebio.session import set_env, run_async, run_js, run_asyncio_coroutine, get_session_implement
from pywebio.input import input, input_group, PASSWORD, textarea, actions, TEXT, file_upload


@timer(5,start=False)
def logtimer():
    """打印当前时间到 log 里"""
    return time.time()

_admin_runtime_initialized = False
_DOCUMENT_CACHE = {'ts': 0.0, 'data': None}
_DOCUMENT_CACHE_TTL = 60
DOCUMENT_MODULE_WHITELIST = admin_document.DOCUMENT_MODULE_WHITELIST


def setup_admin_runtime(enable_webviews=True, enable_timer=True, enable_scheduler=True, enable_stock=True):
    """初始化 admin 运行时资源（幂等）。"""
    state = {
        'initialized': _admin_runtime_initialized,
        'logtimer': logtimer,
        'log': log,
        'browser': browser,
        'concat': concat,
        'NS': NS,
        'scheduler': scheduler,
        'enable_stock': enable_stock,
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
    await init_admin_ui("Deva实时流管理")
    put_markdown('### 数据流')
    put_buttons([s.name for s in _get_admin_streams()], onclick=stream_click)


async def stockadmin():
    return await admin_stock_panel.render_stock_admin(_stock_ctx())
    
async def inspect_object(obj):
    return admin_document.inspect_object_ui(_document_ui_ctx(), obj)
async def document():
    await init_admin_ui("Deva管理面板")
    return admin_document.render_document_ui(_document_ui_ctx())


def _document_ui_ctx():
    return admin_contexts.document_ui_ctx(globals())
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
    }


def _stock_ctx():
    return admin_contexts.stock_ctx(globals())


def get_stock_config():
    return admin_stock_runtime.get_stock_config()


def set_stock_config(force_fetch=None, sync_bus=None):
    return admin_stock_runtime.set_stock_config(force_fetch=force_fetch, sync_bus=sync_bus)


def get_stock_basic_meta():
    return admin_stock_runtime.get_stock_basic_meta()


def refresh_stock_basic_df(force=True):
    return admin_stock_runtime.refresh_stock_basic_df(force=force)


async def refresh_stock_basic_df_async(force=True):
    return await admin_stock_runtime.refresh_stock_basic_df_async(force=force)


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
    admin_tasks.restore_tasks_from_db(_tasks_ctx())

    # 创建一个名为'stream_webview'的Web服务器实例，监听所有网络接口(0.0.0.0)
    # 然后为该服务器添加路由处理器，将'/admin'路径映射到dbadmin处理函数
    # 使用PyWebIO的webio_handler进行封装，并指定CDN地址
    cdn='https://fastly.jsdelivr.net/gh/wang0618/PyWebIO-assets@v1.8.3/'
    handlers = [
        (r'/dbadmin', webio_handler(dbadmin, cdn=cdn)),
        (r'/busadmin', webio_handler(busadmin, cdn=cdn)),
        (r'/streamadmin', webio_handler(streamadmin, cdn=cdn)),
        (r'/stockadmin', webio_handler(stockadmin, cdn=cdn)),
        (r'/', webio_handler(main, cdn=cdn)),
        (r'/taskadmin', webio_handler(taskadmin, cdn=cdn)),
        (r'/document', webio_handler(document, cdn=cdn)),
        *admin_monitor_routes.monitor_route_handlers(globals()),
    ]
    NW('stream_webview',host='0.0.0.0').application.add_handlers('.*$', handlers)
 

    Deva.run()
