#!/usr/bin/env python
"""
这是一个基于 PyWebIO 和 Tornado 的 Web 应用程序，集成了多个功能模块，包括用户认证、GPT 问答、新闻提取、动态数据刷新等。

主要功能：
1. 用户认证：使用用户名和密码进行持久化认证。
2. GPT 问答：通过 GPT 模型生成回答。
3. 新闻提取：从指定 URL 提取新闻内容并生成摘要。
4. 动态数据刷新：定时刷新页面内容。
5. 汉字笔画数计算：输入汉字并计算其笔画数。
6. 日志记录：手动或自动写入日志。
7. 数据表展示：展示数据库中的表格数据。

主要模块：
- `basic_auth`: 用户认证函数。
- `word_strokes_count`: 汉字笔画数计算函数。
- `write_to_log`: 写入日志函数。
- `acreate_completion`: 异步生成 GPT 回答函数。
- `ask_gpt`: 处理 GPT 问答请求函数。
- `news_extract`: 新闻提取函数。
- `my_timer`: 定时器函数。
- `add_note`: 添加评论函数。
- `main`: 主函数，初始化并运行各个功能模块。
- `convert_timestamp_columns_to_string`: 将 DataFrame 中的时间戳列转换为字符串。
- `table_click`: 处理表格点击事件函数。

异常类：
- `ExceedMaxTokenError`: 超过最大令牌数异常。
- `OmittedContentError`: 内容省略异常。

使用方法：
1. 运行脚本后，打开浏览器访问相应 URL。
2. 进行用户登录。
3. 使用页面提供的各项功能，如 GPT 问答、新闻提取、日志记录等。
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
    put_buttons, put_row, put_html, put_link, put_code, popup
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

@timer(1)
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

    # run_async(print_library())

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

       
def convert_timestamp_columns_to_string(dataframe):
    # 处理时间后才可以转换成json
    for column in dataframe.columns:
        if pd.api.types.is_datetime64_any_dtype(dataframe[column]):
            dataframe[column] = dataframe[column].dt.strftime('%Y-%m-%d %H:%M:%S')

    dataframe = dataframe.fillna('')  # 去空值
    return dataframe

def paginate_dataframe(scope,df, page_size):
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
    clear('table_content')
    put_markdown("> You click `%s` table,show sample 10 records:" % tablename)

    items = NB(tablename).items() >> sample(10)

    df_items = [i for i in items if isinstance(i[1], pd.DataFrame)]
    str_items = [i for i in items if isinstance(i[1], str)]
    other_items = [i for i in items if not isinstance(i[1], pd.DataFrame) and not isinstance(i[1], str)]
    if str_items:
        put_table(str_items)
    if other_items:
        for k, v in other_items:
            with put_collapse(k, open=True):
                if isinstance(v, dict) or hasattr(v, '__dict__'):
                    def format_value(value, level=0):
                        if isinstance(value, dict):
                            return [[str(k), format_value(v, level + 1)] for k, v in value.items()]
                        elif hasattr(value, '__dict__'):
                            attrs = {k: v for k, v in value.__dict__.items() if not k.startswith('_')}
                            return [[str(k), format_value(v, level + 1)] for k, v in attrs.items()]
                        else:
                            return str(value)
                    formatted_items = format_value(v)
                    put_table(formatted_items)
                else:
                    put_text(str(v))
    if df_items:
        with put_collapse('DataFrames', open=True):
            for k, v in df_items:
                v = convert_timestamp_columns_to_string(v)
                with put_collapse(f'{k}', open=True):
                    # if len(v.index) < 20:
                    #     put_datatable(v.to_dict(orient='records'), height='auto')
                    # else:
                    #     put_datatable(v.head(20).to_dict(orient='records'))
                    paginate_dataframe(scope=k,df=v,page_size=10)

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

