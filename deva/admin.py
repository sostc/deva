#!/usr/bin/env python
"""
Deva 管理面板 - 基于 PyWebIO 和 Tornado 的 Web 应用程序

核心功能：
- 实时数据流监控：访问日志、实时新闻、涨跌停数据、板块异动等
- 定时任务管理：查看和管理所有定时任务的执行状态
- 数据表展示：支持分页和实时更新的表格数据展示
- 日志系统：实时日志监控和手动日志写入
- 用户认证：基于用户名和密码的登录系统

主要模块：
- 数据流模块：实时监控多个数据流，包括访问日志、新闻、板块数据等
- 定时任务模块：展示所有定时任务的执行间隔、状态和生命周期
- 数据表模块：支持分页、过滤和实时更新的表格展示
- 日志模块：提供日志查看器和手动日志写入功能
- 用户认证模块：基于 PyWebIO 的 basic_auth 实现

技术栈：
- 前端：PyWebIO
- 后端：Tornado
- 数据流：Deva 流处理框架
- 缓存：基于 ExpiringDict 的缓存系统
"""


# coding: utf-8

# In[2]:
import os
from deva import (
    NW, NB, log, ls, Stream, extract, first, tail, head,
    sample, last, http, Deva, stdout, print, passed, P,
    timer,NS,concat
)
from deva.page import webview
from pywebio.output import (
    put_error, put_text, put_markdown, set_scope, put_table,put_success,
    put_info, use_scope, clear, toast, put_button, put_collapse, put_datatable,
    put_buttons, put_row, put_html, put_link, put_code, popup,style
)
import datetime
from tornado.web import create_signed_value, decode_signed_value
from typing import Callable, Union
from deva import (
    NW, NB, log, ls, Stream, extract, first, tail, head,
    sample, last, http, Deva, stdout, print, passed, P
)
from pywebio.platform.tornado import webio_handler
from pywebio_battery import put_logbox, logbox_append, set_localstorage, get_localstorage
from pywebio.pin import pin_wait_change, pin, put_input
from pywebio.session import set_env, run_async, run_js, run_asyncio_coroutine, get_session_implement

from pywebio.input import input, input_group, PASSWORD, textarea, actions, TEXT
from pywebio.output import (
    put_error, put_text, put_markdown, set_scope, put_table,
    put_info, use_scope, clear, toast, put_button, put_collapse, put_datatable,
    put_buttons, put_row, put_html, put_link, put_code, popup
)
import pandas as pd
import asyncio
from functools import partial
import openai
# In[3]:
import json
import time


from openai import AsyncOpenAI
import datetime
from tornado.web import create_signed_value, decode_signed_value
from typing import Callable, Union
from pywebio.platform.tornado import webio_handler
from pywebio_battery import put_logbox, logbox_append, set_localstorage, get_localstorage
from pywebio.pin import pin_wait_change, pin, put_input
from pywebio.session import set_env, run_async, run_js, run_asyncio_coroutine, get_session_implement
from pywebio.input import input, input_group, PASSWORD, textarea, actions, TEXT
import pandas as pd
import asyncio
from functools import partial
import openai

@timer(1,start=True)
def logtimer():
    """每秒打印一下时间到 log 里"""
    return time.time()

logtimer>>log


def cut_foot():
    run_js('document.getElementsByClassName("footer")[0].style.display="none"')
    put_link('浙ICP备2021016438号',
             'https://beian.miit.gov.cn/').style("position: fixed;bottom: 10px;right: 10px")
    # put_button('说明', onclick=about).style("position: fixed;bottom: 10px;right: 10px")


class ExceedMaxTokenError(Exception):
    pass


class OmittedContentError(Exception):
    pass



async def basic_auth(verify_func: Callable[[str, str], bool], secret: Union[str, bytes],
                     expire_days=7, token_name='pywebio_auth_token') -> str:
    """基于用户名和密码的持久化认证。

    你需要提供一个基于用户名和密码验证当前用户的函数。`basic_auth()`函数会将认证状态
    保存在用户的浏览器中，这样已认证的用户就不需要重复登录。

    参数:
        verify_func (callable): 用户认证函数。该函数接收两个参数:用户名和密码。
            如果认证成功返回True，否则返回False。
        secret (str): 用于签名的HMAC密钥。应该是一个较长的随机字符串。
        expire_days (int): 认证状态的有效天数。超过这个时间后,已认证用户需要重新登录。
        token_name (str): 用于在用户浏览器中存储认证状态的token名称。
    
    返回:
        str: 当前认证用户的用户名

    示例:
        user_name = basic_auth(lambda username, password: username == 'admin' and password == '123',
                               secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__")
        put_text("你好, %s. 你可以刷新页面看看会发生什么" % user_name)

    版本: 0.4新增
    """
    # 从用户浏览器获取token
    token = await get_localstorage(token_name)
    
    # 尝试从token中解密用户名
    username = decode_signed_value(secret, token_name, token, max_age_days=expire_days)
    if username:
        username = username.decode('utf8')
        
    # 如果没有token或token验证失败
    if not token or not username:
        while True:
            # 显示登录表单
            user = await input_group('登录', [
                input("用户名", name='username', value='admin'),
                input("密码", type=PASSWORD, name='password', value='123'),
            ])
            username = user['username']
            # 验证用户名和密码
            ok = verify_func(username, user['password'])
            ok >> log
            if ok:
                # 将用户名加密为token
                signed = create_signed_value(secret, token_name, username).decode("utf-8")
                # 将token保存到用户浏览器
                set_localstorage(token_name, signed)
                break
            else:
                # 显示错误提示
                toast('用户名或密码错误', color='error')

    return username


async def write_to_log():
    l = await pin.write_to_log
    logbox_append("log", l+'\n')
    l >> log




def put_out(msg, type='text',scope='',session=''):
        """
        将消息输出到指定的作用域中。

        参数:
            msg (str): 要输出的消息。
            type (str, optional): 消息类型。默认为 'text'。
        """
        scope = '#pywebio-scope-'+scope
        if not session:
            session = get_session_implement().get_current_session()
        data = {'command': 'output',
                'spec': {'type': type,
                         'content': msg,
                         'inline': True,
                         'position': -1,#-1 添加到后面
                         'scope': scope,
                         },
                'task_id': '_start_main_task-Qoqo1zPS7O'
                }
        
        return session.send_task_command(data)

def scope_clear(scope,session):
        """
        清除指定作用域中的所有输出。
        """
        scope = '#pywebio-scope-'+scope
        data = {'command': 'output_ctl',
                'spec': {'clear': scope},
                'task_id': 'callback_coro-eEh6wdXSnH'
                }
        return session.send_task_command(data)




log.start_cache(200, cache_max_age_seconds=60 * 60 * 24 * 30)
log.map(lambda x: log.recent(10) >> concat('<br>'))\
    >> NS('访问日志', cache_max_len=1, cache_max_age_seconds=60 * 60 * 24 * 30)

os.getpid() >> log

streams = [NS('访问日志'), NS('实时新闻'), NS(
    '涨跌停'), NS('领涨领跌板块'), NS('1分钟板块异动'), NS('30秒板块异动')]
for s in streams:
    s.webview(f'/{hash(s)}')


async def main():
    # await my_timer()
    # 这个将会把会话协程卡在这里不动，采用 run_async则不会堵塞

    set_env(title="Deva管理面板")
    cut_foot()
    run_js(
        'WebIO._state.CurrentSession.on_session_close(()=>{setTimeout(()=>location.reload(), 4000})')

    # 创建更美观的顶部导航菜单栏
    put_row([
        set_scope('nav_buttons'),  # 为导航按钮创建独立作用域
        set_scope('nav_style')     # 为样式创建独立作用域
    ])

  
    

    # 登录部分要直接用 await来堵塞，登录成功才可以进入后续流程
    user_name = await basic_auth(lambda username, password: username == 'admin' and password == '123',
                                 secret="random_value001")

    put_text(f"Hello, {user_name}. 欢迎光临，恭喜发财")

    put_markdown('### 数据流')
    put_buttons([s.name for s in streams],onclick=stream_click)
    
    put_markdown('### 定时任务')
    for s in Stream.instances():
        if isinstance(s,timer):
            put_markdown(f'#### 函数名：{s.func.__name__}')
            put_text(f'执行间隔：{s.interval}秒,执行状态：{s.started}')
            put_markdown(f'生命周期：{s.ttl}秒,下游消费者：{list(s.downstreams)}')
    
    put_text(Stream.instances()|ls)
    
    put_markdown('### 数据表')
    put_buttons(NB('default').tables | ls, onclick=table_click)
    set_scope('table_content')

    with put_collapse('log', open=True):
        put_logbox("log", height=100)
     
    with put_collapse('其他控件', open=True):
        put_input('write_to_log', type='text', value='', placeholder='手动写入日志')
        put_button('>', onclick=write_to_log)
       


def paginate_dataframe(scope,df, page_size):
    # 处理时间列并填充空值，处理时间后才可以转换成json
    for column in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[column]):
            df[column] = df[column].dt.strftime('%Y-%m-%d %H:%M:%S')
    df = df.fillna('')

    # 计算总页数
    total_pages = (len(df) - 1) // page_size + 1
    
    # 定义一个内部函数来显示当前页的数据
    def show_page(page, filtered_df=None):
        # 如果没有过滤，则使用原始 DataFrame
        if filtered_df is None:
            filtered_df = df
        
        # 获取当前页的数据
        start = (page - 1) * page_size
        end = start + page_size
        page_data = filtered_df.iloc[start:end]
        
        # 使用 use_scope 清除原先的表格内容并展示新数据
        with use_scope('table_scope'+scope, clear=True):
            if len(page_data) == 0:
                put_text('没有找到匹配的结果')
            else:
                put_datatable(page_data.to_dict(orient='records'),height='auto')
        
        # 使用 use_scope 清除原先的按钮内容并重新显示按钮
        with use_scope('buttons_scope'+scope, clear=True):
            # 显示当前页码
            put_text(f'第 {page} 页 / 共 {len(filtered_df) // page_size + 1} 页')
            
            # 根据当前页码显示翻页按钮
            buttons = []
            if page > 1:
                buttons.append({'label': '上一页', 'value': 'prev'})
            if page < len(filtered_df) // page_size + 1:
                buttons.append({'label': '下一页', 'value': 'next'})
            
            put_buttons(buttons, 
                        onclick=lambda v: show_page(page - 1 if v == 'prev' else page + 1, filtered_df)
                       )
    
    # 搜索功能
    async def search():
        keyword = await pin['search_input'+scope]
        if keyword:
            filtered_df = df[df.apply(lambda row: row.astype(str).str.contains(keyword, case=False).any(), axis=1)]
            show_page(1, filtered_df)
        else:
            show_page(1)
    
    # 初始展示第一页
    show_page(1)
    
    # 添加搜索按钮
    put_row([
        put_input('search_input'+scope, placeholder='搜索...'),
        put_button('搜索', onclick=search)
    ])

@use_scope('table_content')
def table_click(tablename):
    """处理表格点击事件，展示表格内容
    
    参数:
        tablename (str): 表格名称
    """
    clear('table_content')
    put_markdown(f"> 您点击了 `{tablename}` 表格，展示前10条记录：")

    # 获取表格数据并采样10条
    items = NB(tablename).items() >> sample(10)
    
    # 按数据类型分类
    data_items = {
        'dataframes': [(k, v) for k, v in items if isinstance(v, pd.DataFrame)],
        'strings': [(k, v) for k, v in items if isinstance(v, str)],
        'others': [(k, v) for k, v in items if not isinstance(v, (pd.DataFrame, str))]
    }

    # 显示字符串类型数据
    if data_items['strings']:
        with put_collapse('strings', open=True):
            put_table(data_items['strings'])

    # 显示其他类型数据
    if data_items['others']:
        with put_collapse('其他对象', open=True):
            for key, value in data_items['others']:
                with put_collapse(key, open=True):
                    if isinstance(value, (dict, object)):
                        def format_value(val, level=0):
                            """递归格式化字典或对象的值"""
                            if isinstance(val, dict):
                                return [[str(k), format_value(v, level + 1)] for k, v in val.items()]
                            elif hasattr(val, '__dict__'):
                                attrs = {k: v for k, v in val.__dict__.items() 
                                    if not k.startswith('_')}
                                return [[str(k), format_value(v, level + 1)] 
                                    for k, v in attrs.items()]
                            return str(val)
                        
                        formatted_data = format_value(value)
                        put_table(formatted_data)
                    else:
                        put_text(str(value))

    # 显示DataFrame类型数据
    if data_items['dataframes']:
        with put_collapse('dataframe', open=True):
            for df_name, df in data_items['dataframes']:
                with put_collapse(df_name, open=True):
                    paginate_dataframe(scope=df_name, df=df, page_size=10)
                    
def stream_click(streamname):
    put_markdown("> You click `%s` stream,show records:" % streamname)
    
    s = [s for s in Stream.instances() if s.name==streamname][0]
    popup('Stream Viewer', [
        put_html(f'<iframe src="{hash(s)}" style="width:100%;height:80vh;border:none;"></iframe>')
    ], size='large')




# In[5]:
if __name__ == '__main__':
    NW('stream_webview').application.add_handlers(
        '.*$', [(r'/', webio_handler(main, cdn='https://fastly.jsdelivr.net/gh/wang0618/PyWebIO-assets@v1.8.2/'))])
    log.webview('/log')

    Deva.run()


# In[ ]:

