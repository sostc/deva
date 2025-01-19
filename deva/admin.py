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
import traceback
from urllib.parse import urljoin
from deva import (
    NW, NB, log, ls, Stream, first, sample, Deva, print, timer,NS,concat, Dtalk
)
from deva.browser import browser,tab,tabs
from deva.page import page #这里为了给流注入 webview 方法和sse 方法
from pywebio.output import (
    put_text, put_markdown, set_scope, put_table,use_scope, clear, toast, put_button, put_collapse, put_datatable,
    put_buttons, put_row, put_html, put_link, popup,close_popup
)

from tornado.web import create_signed_value, decode_signed_value
from typing import Callable, Union
from pywebio.platform.tornado import webio_handler
from pywebio_battery import put_logbox, logbox_append, set_localstorage, get_localstorage
from pywebio.pin import pin, put_input
from pywebio.session import set_env, run_async, run_js, run_asyncio_coroutine, get_session_implement

from pywebio.input import input, input_group, PASSWORD, textarea, actions, TEXT
import pandas as pd
import json
import time

from openai import AsyncOpenAI
from tornado.web import create_signed_value, decode_signed_value
from typing import Callable, Union
from pywebio.platform.tornado import webio_handler
from pywebio_battery import put_logbox, logbox_append, set_localstorage, get_localstorage
from pywebio.pin import pin, put_input
from pywebio.session import set_env, run_async, run_js, run_asyncio_coroutine, get_session_implement
from pywebio.input import input, input_group, PASSWORD, textarea, actions, TEXT
import pandas as pd


from deva.gpt import async_gpt,sync_gpt


@timer(5,start=False)
def logtimer():
    """打印当前时间到 log 里"""
    return time.time()

logtimer.start()
logtimer>>log

browser.log>>log


async def get_gpt_response(prompt, session=None, scope=None, model_type='deepseek',flush_interval=3):
    """获取GPT的流式响应并返回完整结果
    
    Args:
        prompt: 用户输入的提示词
        session: 当前会话对象
        scope: 输出作用域
        flush_interval: 刷新显示的间隔时间（秒），默认为3秒
        
    Returns:
        str: 完整的GPT响应内容
    """
    api_key = NB(model_type)['api_key']
    base_url = NB(model_type)['base_url']
    model = NB(model_type)['model']
    gpt_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    start_time = time.time()
    
    if session:
        def logfunc(output_text):
            put_out(msg=output_text, type='markdown', scope=scope, session=session)
    else:
        def logfunc(output_text):
            output_text>>log
    # 初始化消息列表
    messages = [{"role": "user", "content": prompt}]
    
    try:
        # 创建GPT流式响应
        response = await gpt_client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=8192
        )
    except Exception as e:
        (f"请求失败: {traceback.format_exc()}")>>log
        toast("请求失败~")
        return ""

    # 初始化文本缓冲区
    buffer = ""
    accumulated_text = ""
    
    async def process_chunk(chunk, buffer, accumulated_text, start_time):
        """处理单个响应块
        
        参数:
            chunk: 响应块
            buffer: 当前缓冲区
            accumulated_text: 累计文本
            start_time: 开始时间
            
        返回:
            tuple: (更新后的buffer, 更新后的accumulated_text, 更新后的start_time)
        """
        if chunk.choices[0].delta.content:
            # 如果内容以"检索"开头，跳过该行
            if chunk.choices[0].delta.content.startswith("检索"):
                return buffer, accumulated_text, start_time
                
            buffer += chunk.choices[0].delta.content
            
            # 判断是否到达段落结尾（以句号、问号、感叹号+换行符为标志）
            paragraph_end_markers = ('.', '?', '!', '。', '？', '！')
            is_paragraph_end = (
                len(buffer) >= 2 and 
                buffer[-2] in paragraph_end_markers and 
                buffer[-1] == '\n'
            )
            
            # 当遇到段落结尾或超过刷新间隔时，显示缓冲内容
            if (is_paragraph_end or time.time()-start_time >= flush_interval) and buffer.strip():
                # 确保输出完整段落
                if is_paragraph_end:
                    # 找到最后一个段落结束符的位置
                    last_paragraph_end = max(
                        (buffer.rfind(marker) for marker in paragraph_end_markers),
                        default=-1
                    )
                    if last_paragraph_end != -1:
                        # 输出完整段落
                        output_text = buffer[:last_paragraph_end+1]
                        # 剩余内容保留在buffer中
                        buffer = buffer[last_paragraph_end+1:]
                    else:
                        # 如果没有找到段落结束符，输出整个buffer
                        output_text = buffer
                        buffer = ""
                else:
                    # 如果超时但未到段落结尾，找到最后一个完整句子
                    last_sentence_end = max(
                        (buffer.rfind(marker) for marker in paragraph_end_markers),
                        default=-1
                    )
                    if last_sentence_end != -1:
                        output_text = buffer[:last_sentence_end+1]
                        buffer = buffer[last_sentence_end+1:]
                    else:
                        output_text = buffer
                        buffer = ""
                
                # 输出内容并更新时间
                if output_text.strip():
                    accumulated_text += output_text
                    logfunc(output_text)
                    start_time = time.time()
                
        # 处理最后一个未显示的块
        if buffer and not chunk.choices[0].delta.content:
            accumulated_text += buffer
            logfunc(buffer)
            start_time = time.time()
            buffer = ""
            
        return buffer, accumulated_text, start_time
    async for chunk in response:
        buffer, accumulated_text, start_time = await process_chunk(
            chunk, buffer, accumulated_text, start_time
        )
    
    # 返回完整的累计文本
    return accumulated_text


# tab('http://secsay.com')

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
                input("用户名", name='username'),
                input("密码", type=PASSWORD, name='password'),
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
                         "sanitize": True,
                         'scope': scope,
                         },
                'task_id': '_start_main_task-Qoqo1zPS7O'
                }
        print(data)
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

def show_timer_detail(t):
    """显示定时任务详情"""
    clear('timer_content')
    with use_scope('timer_content'):
        # 创建表格数据
        table_data = [
            ['属性', '值'],
            ['函数名', t.func.__name__],
            ['功能描述', t.func.__doc__.strip() if t.func.__doc__ else '无描述'],  # 新增功能描述
            ['执行间隔', f'{t.interval}秒'],
            ['执行状态', '运行中' if t.started else '已停止'],
            ['生命周期', f'{t.ttl}秒'],
            ['下游消费者', ', '.join(map(str, t.downstreams)) or '无']
        ]
        
        # 显示标题和表格
        put_markdown(f"### {t.func.__name__} 任务详情")
        put_table(table_data)

async def create_new_table():
        """创建新表的函数"""
        # 弹出输入框获取表名和描述
        table_info = await input_group('新建表', [
            input('表名', name='table_name', required=True),
            textarea('表描述', name='table_desc')
        ])
        
        # 获取默认数据库实例
        db = NB('default')
        
        # 检查表是否已存在
        if table_info['table_name'] in db.tables:
            toast('表已存在', color='error')
            return
            
        try:
            # 创建新表
            NB(table_info['table_name'])
            NB('default')[table_info['table_name']]=table_info['table_desc']
            toast('表创建成功')
            # 刷新表格列表
            refresh_table_display()
            table_click(table_info['table_name'])
            
        except Exception as e:
            toast(f'创建表失败: {str(e)}', color='error')

# 删除表的回调函数
async def delete_table(tablename):
    # 获取用户输入的确认信息
    confirm = await pin['delete_confirm']
    if confirm == '确认':#tablename:
        # 删除表描述
        try:
            del NB('default')[tablename]
        except:
            pass
        # 删除表数据
        NB(tablename).db.drop()
        # 显示成功提示
        toast(f'表 {tablename} 已删除', color='success')
        # 刷新表格列表
        refresh_table_display()
        table_click('default')
        # 关闭弹窗
        close_popup()
    else:
        toast('输入正确的表的名称才可以删除哦', color='warning')

# 定义刷新数据表显示的函数
def refresh_table_display():
    """刷新数据表显示区域"""
    clear('table_display')  # 清空原有内容
    with use_scope('table_display'):  # 使用指定scope
        put_markdown('### 数据表')
        put_buttons(NB('default').tables | ls, onclick=table_click)
        put_button('+新建表', onclick=lambda: run_async(create_new_table()))

async def show_browser_status():
    """显示浏览器状态"""
    
    # 如果没有打开的标签页
    if not tabs:
        with use_scope('browser_status'):
            clear('browser_status')
            put_text("当前没有打开的浏览器标签页")
        return None
    
    # 创建表格显示标签页信息
    browser.table_data = [['序号', 'URL', '标题','操作']]
    
    # 遍历所有标签页
    # 复制 tabs 集合
    tabs_copy = list(tabs) # 或者使用 set(tabs) 如果 tabs 是集合
    for i, tab in enumerate(tabs_copy):
        # 获取标签页状态
        article = await tab.article
        page = await tab.page
        if page:
            if article:
                title = article.title
                summary = article.summary
            else:
                title = page.html.search('<title>{}</title>')|first
                summary = '无法获取摘要'
            # 添加操作按钮
            actions = put_buttons([
                {'label': '查看', 'value': 'view'},
                {'label': '关闭', 'value': 'close'}
            ], onclick=lambda v, t=tab: view_tab(t) if v == 'view' else close_tab(t))
            
            # 添加行数据，为标题添加悬停显示摘要的功能
            browser.table_data.append([
                i+1,
                truncate(tab.url),
                put_html(f'<span title="{summary}" style="cursor:pointer;text-decoration:underline dotted">{truncate(title)}</span>'),
                # summary,
                actions
            ])
    
    # 在browser scope中显示表格
    with use_scope('browser_status',clear=True):
        put_table(browser.table_data)
    return browser.table_data

def view_tab(tab):
    """查看指定标签页"""
    async def get_content():
        article = await tab.article
        if article.text:  # 如果文章内容不为空
            popup(f"{article.title}", [
                put_markdown('>'+tab.url),
                put_markdown(article.text)  # 展示文章内容
            ], size='large')
        else:  # 如果文章内容为空
            popup(f"iframe查看标签页 - {tab.url}", [
                put_html(f'<iframe src="{tab.url}" style="width:100%;height:80vh;border:none;"></iframe>')
            ], size='large')
    
    run_async(get_content())
def close_tab(tab):
    """关闭指定标签页"""
    tab.close()
    toast(f"已关闭标签页: {tab.url}")
    # 刷新显示
    run_async(show_browser_status())
    
async def open_new_tab():
    """手动打开新标签页"""
    from pywebio.input import actions
    url = await input_group('请输入要打开的URL', [
        input('URL', name='url', type=TEXT),
        actions('操作', [
            {'label': '确定', 'value': 'confirm'},
            {'label': '取消', 'value': 'cancel'}
        ], name='action')
    ])
    print(url)
    if url['action'] == 'cancel':
        return
    url = url['url']
    if url:
        # 使用正则表达式验证URL格式
        import re
        url_pattern = re.compile(r'^https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)$')
        if url_pattern.match(url):
            
            toast(f"浏览器在后台打开新标签页 ing: {url}")
            tab(url)
            # 刷新显示
            run_async(show_browser_status())
        else:
            toast(f"无效的URL格式: {url}", color='error')

    


def init_floating_menu_manager():
    """初始化浮动菜单管理器"""
    js_code = """
    const FloatingMenuManager = {
        init() {
            this.restoreMenus();
        },

        createMenu(content, title, menuId = null) {
            const menuCount = document.querySelectorAll('.summary-floating-menu').length;
            
            // 限制最大菜单数量
            if (menuCount >= 10) {
                this.removeOldestMenu();
            }

            const menuData = {
                content,
                title: title || '摘要',
                timestamp: Date.now()
            };

            if (!menuId) {
                menuId = `summary_menu_${Date.now()}`;
                localStorage.setItem(menuId, JSON.stringify(menuData));
            }

            const menu = this._createMenuElement(menuData, menuCount);
            menu.dataset.menuId = menuId;
            document.body.appendChild(menu);
            
            return menuId;
        },

        _createMenuElement(menuData, menuCount) {
            const { content, title } = menuData;
            const baseRight = 20;
            const menuSpacing = 60;
            const menuRight = baseRight + (menuCount * menuSpacing);

            const menu = document.createElement('div');
            menu.className = 'summary-floating-menu';
            Object.assign(menu.style, {
                position: 'fixed',
                bottom: '20px',
                right: `${menuRight}px`,
                zIndex: String(1000 + menuCount),
                backgroundColor: '#fff',
                borderRadius: '5px',
                boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
                padding: '10px',
                cursor: 'pointer',
                width: '50px',
                height: '50px',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                transition: 'all 0.3s ease'
            });

            // 添加图标
            const icon = document.createElement('div');
            icon.innerText = '📄';
            icon.style.fontSize = '24px';
            menu.appendChild(icon);

            // 添加工具提示
            const tooltip = this._createTooltip(title);
            menu.appendChild(tooltip);

            // 添加删除按钮
            const deleteBtn = this._createDeleteButton();
            menu.appendChild(deleteBtn);

            // 绑定事件
            this._bindMenuEvents(menu, tooltip, deleteBtn, content, title);

            return menu;
        },

        _createTooltip(title) {
            const tooltip = document.createElement('div');
            tooltip.innerText = title;
            Object.assign(tooltip.style, {
                position: 'absolute',
                bottom: '60px',
                left: '50%',
                transform: 'translateX(-50%)',
                backgroundColor: '#333',
                color: '#fff',
                padding: '5px 10px',
                borderRadius: '4px',
                fontSize: '12px',
                whiteSpace: 'nowrap',
                opacity: '0',
                transition: 'opacity 0.2s ease',
                pointerEvents: 'none'
            });
            return tooltip;
        },

        _createDeleteButton() {
            const btn = document.createElement('div');
            btn.innerText = '×';
            Object.assign(btn.style, {
                position: 'absolute',
                top: '-5px',
                right: '-5px',
                width: '20px',
                height: '20px',
                backgroundColor: '#ff4444',
                color: '#fff',
                borderRadius: '50%',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                cursor: 'pointer',
                opacity: '0',
                transition: 'opacity 0.2s ease'
            });
            return btn;
        },

        _bindMenuEvents(menu, tooltip, deleteBtn, content, title) {
            menu.onmouseenter = () => {
                menu.style.transform = 'scale(1.1)';
                menu.style.boxShadow = '0 4px 15px rgba(0,0,0,0.2)';
                tooltip.style.opacity = '1';
                deleteBtn.style.opacity = '1';
            };

            menu.onmouseleave = () => {
                menu.style.transform = 'scale(1)';
                menu.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
                tooltip.style.opacity = '0';
                deleteBtn.style.opacity = '0';
            };

            menu.onclick = () => this.showPopup(content, title);

            deleteBtn.onclick = (e) => {
                e.stopPropagation();
                this.removeMenu(menu.dataset.menuId);
            };
        },

        removeMenu(menuId) {
            const menu = document.querySelector(`[data-menu-id="${menuId}"]`);
            if (menu) {
                menu.remove();
                console.log(menuId);
                localStorage.removeItem(menuId);
                this.adjustMenuPositions();
            }
        },

        removeOldestMenu() {
            const menus = Array.from(document.querySelectorAll('.summary-floating-menu'));
            if (menus.length > 0) {
                const oldestMenu = menus.reduce((oldest, current) => {
                    const oldestTime = JSON.parse(localStorage.getItem(oldest.dataset.menuId))?.timestamp || 0;
                    const currentTime = JSON.parse(localStorage.getItem(current.dataset.menuId))?.timestamp || 0;
                    return oldestTime < currentTime ? oldest : current;
                });
                this.removeMenu(oldestMenu.dataset.menuId);
            }
        },

        adjustMenuPositions() {
            const menus = document.querySelectorAll('.summary-floating-menu');
            menus.forEach((menu, index) => {
                const right = 20 + (index * 60);
                menu.style.right = `${right}px`;
            });
        },

        restoreMenus() {
            Object.keys(localStorage).forEach(key => {
                if (key.startsWith('summary_menu_')) {
                    const data = JSON.parse(localStorage.getItem(key));
                    if (data) {
                        this.createMenu(data.content, data.title, key);
                    }
                }
            });
        },

        showPopup(content, title) {
            const popup = document.createElement('div');
            popup.className = 'summary-popup';
            Object.assign(popup.style, {
                position: 'fixed',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                backgroundColor: '#fff',
                padding: '20px',
                borderRadius: '8px',
                boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
                maxWidth: '80%',
                maxHeight: '80vh',
                overflow: 'auto',
                zIndex: '2000'
            });

            const titleEl = document.createElement('h3');
            titleEl.innerText = title;
            titleEl.style.marginBottom = '10px';

            const contentEl = document.createElement('div');
            contentEl.innerHTML = content.replace(/\\n/g, '<br>');

            const closeBtn = document.createElement('button');
            closeBtn.innerText = '关闭';
            closeBtn.style.marginTop = '15px';
            closeBtn.onclick = () => popup.remove();

            popup.appendChild(titleEl);
            popup.appendChild(contentEl);
            popup.appendChild(closeBtn);
            document.body.appendChild(popup);
        }
    };

    // 初始化
    if (!window.FloatingMenuManager) {
        window.FloatingMenuManager = FloatingMenuManager;
        FloatingMenuManager.init();
    }
    """
    run_js(js_code)



# 在应用启动时调用


async def dynamic_popup(title, async_content_func):
    """创建动态弹出窗口"""
    with popup("Dynamic Popup", closable=True):
        scope = 'Dynamic_summary'
        session = get_session_implement().get_current_session()
        with use_scope(scope, clear=True):
            try:                    
                summary = await run_asyncio_coroutine(async_content_func(session=session,scope=scope))
            except Exception as e:
                e>>log
                summary = ''
                toast(f"生成摘要失败: {str(e)}", color='error')

        with use_scope(scope, clear=True):
            put_out(summary,type='markdown',scope=scope,session=session)
            summary>>log
            put_button('发送到钉钉', onclick=lambda: ('@md@焦点分析|'+summary>>Dtalk()) and toast('已发送到钉钉'))
            # 添加关闭popup时的回调
            run_js(f"""
                // 保存摘要内容到变量
                const summaryScope = document.getElementById('pywebio-scope-{scope}');
                const summaryContent = summaryScope.innerHTML;  // 使用innerHTML保留markdown格式
                // 使用第一行内容作为标题
                const firstLine = summaryScope.querySelector('h1, h2, h3, h4, h5, h6, p')?.innerText || '';
                const summaryTitle = firstLine.substring(0, 20) + (firstLine.length > 20 ? '...' : '');
                if (!window.FloatingMenuManager) {{
                    {init_floating_menu_manager()}
                }}
                FloatingMenuManager.createMenu(summaryContent, summaryTitle);
            """)
            

    

async def summarize_tabs():
    """汇总所有标签页内容并生成摘要"""
    # 获取所有标签页
    all_tabs = list(tabs)
    # 收集所有标签页的article.text内容
    contents = []
    for tab in list(all_tabs):
        try:
            article = await tab.article
            if hasattr(article, 'text') :
                contents.append(article.text)
        except Exception as e:
            print(f"获取标签页 {tab.url} 内容时出错: {e}")
    
    if not contents:
        toast("没有可总结的内容", color='error')
        return
        
    # 将所有内容合并
    combined_content = "\n\n".join(contents)
    # 如果内容过长，截取前10000个字符
    if len(combined_content) > 20000:
        combined_content = combined_content[:20000]
        toast("内容过长，已截取前10000字符进行总结", color='warning')
    
    # 显示加载提示
    toast("正在生成摘要，请稍候...")
    async def async_content_func(session,scope):
        result= await get_gpt_response(prompt=f"请分析随后给的多篇新闻内容，要求返回的内容每一行都是一个一句话新闻，开头用一个和内容对应的图标，然后是一个不大于十个字的高度浓缩概括词，概括词用加粗字体，最后后面是新闻的一句话摘要，用破折号区隔开。每行一个新闻，不要有标题等其他任何介绍性内容，只需要返回6 条新闻即可。\n{combined_content}",
                         session=session,
                         scope=scope
                         )
        return result
            
    run_async(dynamic_popup(title='总结摘要',async_content_func=async_content_func))

async def async_json_gpt( prompts):
    """
    异步查询大模型
    
    参数:
        prompts: 提示词列表或字符串
        
    返回:
        大模型返回的结果
    """
    from openai import AsyncOpenAI
    config = NB('deepseek')
    api_key = config['api_key']
    base_url = config['base_url']
    model = config['model']  # 从配置中获取模型名称
    
    # 初始化同步和异步客户端
    async_client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    if isinstance(prompts, str):
        prompts = [prompts]
        
    messages = [{"role": "user", "content": prompt} for prompt in prompts]
    completion = await async_client.chat.completions.create(
        model=model,
        messages=messages,
        stream=False,
        max_tokens=8000,
        response_format={
                'type': 'json_object'
            }
    )
    
    return completion.choices[0].message.content

async def extract_important_links(page):
    # 获取页面所有链接的标题和绝对路径
    all_links = []
    for link in page.html.find('a'):
        href = link.attrs.get('href', '')
        if href:
            # 拼接绝对路径
            full_url = urljoin(page.url, href)
            title = link.text.strip()
            if title:  # 只保留有标题的链接
                all_links.append({
                    'title': title,
                    'url': full_url
                })
    
    # 将获取到的所有链接信息传递给GPT进行分析
    prompt = f"""
    作为一个新闻分析师，请从下面数据是一个网页里面的连接数据，分析一下哪些连接是经常更新发布的链接，从链接位置和特征，分析找出最新的10个链接, 再按照链接的标题内容判断这 10 个链接嘴重要的 3 个链接，最后返回这 3 个链接\n{all_links}
    最终返回的json,这是您需要的 JSON 数据：
    {{
      "news_links": [
        {{
          "title": "......",
          "url": "http://....."
        }},
        {{
          "title": "......",
          "url": "http://....."
        }},
        {{
          "title": "......",
          "url": "http://....."
        }}
      ]
    }}
    严格遵守 JSON 格式，不返回额外解释或多余文本。
    """
    response = await async_json_gpt(prompt)

    return json.loads(response)
        
def truncate(text, max_length=20):
    """截断内容超过指定长度的文本"""
    return text if len(text) <= max_length else text[:max_length] + "..."
def set_table_style():
        """设置表格样式，包括固定布局、宽度限制和自动换行"""
        put_html("""
            <style>
                table {
                    table-layout: fixed; /* 固定布局 */
                    width: 100%; /* 表格宽度 */
                }
                td, th {
                    max-width: 250px; /* 限制单元格宽度 */
                    word-wrap: break-word; /* 自动换行 */
                    white-space: normal; /* 启用文本换行 */
                }
            </style>
            """)

async def process_tabs(session):
    urls = [t.url for t in tabs]
    for t in list(tabs):
        page = await t.page
        j = await extract_important_links(page)
        links = j['news_links']
        links >>log
        
        for i in links:
            t = tab(i['url'])
            p = await t.page
            if p:
                session.run_async( show_browser_status())
                (p.url, p.article.summary) >> log

def extended_reading():
    process_tabs(get_session_implement().get_current_session())|print
    
    
async def close_all_tabs():
    """关闭所有浏览器标签页"""
    # 检查是否有打开的标签页
    if not tabs:
        toast('当前没有打开的标签页', color='info')
        return
    
    # 弹出确认对话框
    confirm = await actions('确认关闭所有标签页吗？', [
        {'label': '确认', 'value': 'confirm'},
        {'label': '取消', 'value': 'cancel'}
    ])
    
    if confirm == 'confirm':
        # 复制tabs集合以避免迭代时修改
        tabs_copy = list(tabs)
        for tab in tabs_copy:
            tab.close()  # 关闭每个标签页
        toast('所有标签页已关闭', color='success')
        # 刷新浏览器状态显示
        await show_browser_status()



def create_sidebar():
    """创建可伸缩的右边栏"""
    set_scope('sidebar')  # 创建边栏作用域
    run_js('''
        // 创建边栏容器
        const sidebar = document.createElement('div');
        sidebar.id = 'custom-sidebar';
        sidebar.style.position = 'fixed';
        sidebar.style.right = '0';
        sidebar.style.top = '0';
        sidebar.style.width = '300px';
        sidebar.style.height = '100vh';
        sidebar.style.backgroundColor = '#f5f5f5';
        sidebar.style.boxShadow = '-2px 0 5px rgba(0,0,0,0.1)';
        sidebar.style.transition = 'transform 0.3s ease';
        sidebar.style.zIndex = '1000';
        
        // 创建切换按钮
        const toggleBtn = document.createElement('div');
        toggleBtn.style.position = 'absolute';
        toggleBtn.style.left = '-40px';
        toggleBtn.style.top = '20px';
        toggleBtn.style.width = '40px';
        toggleBtn.style.height = '40px';
        toggleBtn.style.backgroundColor = '#fff';
        toggleBtn.style.borderRadius = '5px 0 0 5px';
        toggleBtn.style.boxShadow = '-2px 0 5px rgba(0,0,0,0.1)';
        toggleBtn.style.cursor = 'pointer';
        toggleBtn.style.display = 'flex';
        toggleBtn.style.alignItems = 'center';
        toggleBtn.style.justifyContent = 'center';
        
        // 从localStorage获取边栏状态
        let isOpen = localStorage.getItem('sidebarState') !== 'closed';
        
        // 初始化边栏状态
        sidebar.style.transform = isOpen ? 'translateX(0)' : 'translateX(100%)';
        toggleBtn.innerHTML = isOpen ? '×' : '☰';
        
        // 添加点击事件
        toggleBtn.onclick = function() {
            isOpen = !isOpen;
            sidebar.style.transform = isOpen ? 'translateX(0)' : 'translateX(100%)';
            toggleBtn.innerHTML = isOpen ? '×' : '☰';
            // 保存状态到localStorage
            localStorage.setItem('sidebarState', isOpen ? 'open' : 'closed');
            
            // 调整主页面内容位置
            const mainContent = document.querySelector('.container-fluid');
            if (mainContent) {
                mainContent.style.marginRight = isOpen ? '300px' : '0';
                mainContent.style.transition = 'margin-right 0.3s ease';
            }
        };
        
        // 初始化主页面内容位置
        const mainContent = document.querySelector('.container-fluid');
        if (mainContent) {
            mainContent.style.marginRight = isOpen ? '300px' : '0';
        }
        
        // 将元素添加到页面
        sidebar.appendChild(toggleBtn);
        document.body.appendChild(sidebar);
        
        // 将WebIO内容放入边栏
        const sidebarScope = document.getElementById('pywebio-scope-sidebar');
        sidebar.appendChild(sidebarScope);
    ''')
    # 在右边栏添加默认iframe
    with use_scope('sidebar'):
        put_html(f'<iframe src="{hash(NS('访问日志'))}" style="width:100%;height:120vh;border:none;"></iframe>')

async def init_admin_ui(title):
        """初始化管理界面UI
        
        参数:
            title (str): 页面标题
        """
        
        admin_info = NB('admin')
        if not admin_info.get('username'):
            admin_info = await input_group('创建管理员账户', [
                input("用户名", name='username'),
                input("密码", type=PASSWORD, name='password'),
            ])
            NB('admin').update(admin_info)
            
        user_name = await basic_auth(lambda username, password: username == admin_info['username'] and password == admin_info['password'],
                                 secret="random_value001")
        
        create_sidebar()
        set_env(title=title)
        cut_foot()
        create_nav_menu()
        put_text(f"Hello, {user_name}. 欢迎光临，恭喜发财")


from apscheduler.schedulers.tornado import TornadoScheduler
from pywebio import start_server
from pywebio.input import input, select, TEXT, textarea
from pywebio.output import put_text, put_table, put_button, toast, put_row, put_code
from pywebio.session import run_js
from datetime import datetime

# 初始化调度器
scheduler = TornadoScheduler()
scheduler.start()

# 存储任务信息
tasks = {}

async def async_code_gpt( prompts):
    """
    异步查询大模型
    
    参数:
        prompts: 提示词列表或字符串
        
    返回:
        大模型返回的结果
    """
    from openai import AsyncOpenAI
    config = NB('deepseek')
    api_key = config['api_key']
    base_url = config['base_url']
    model = config['model']  # 从配置中获取模型名称
    
    # 初始化同步和异步客户端
    async_client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    if isinstance(prompts, str):
        prompts = [prompts]
        
    messages = [{"role": "user", "content": prompt} for prompt in prompts]
    completion = await async_client.chat.completions.create(
        model=model,
        messages=messages,
        stream=False,
        max_tokens=8000,
        
    )
    
    return completion.choices[0].message.content

async def watch_topic(topic):
    """分析主题并显示结果"""
    
    # 自定义提示词
    full_prompt = f' 获取{ topic},要求返回的内容每一行都是一个一句话，开头用一个和内容对应的图标，然后是一个不大于十个字的高度浓缩概括词，概括词用加粗字体，再后面是一句话摘要，用破折号区隔开。每行一个内容，不要有标题等其他任何介绍性内容，只需要返回6 条新闻即可。'
    
    result = await get_gpt_response(
            prompt=full_prompt,
            model_type='kimi',
        )
    return result

async def create_task():
    """创建定时任务"""
    task_info = await input_group("创建定时任务", [
        input("任务名称", name="name", type=TEXT),
        textarea("任务描述", name="description", placeholder="请输入任务描述"),
        select("任务类型", name="type", options=[
            ("间隔任务（每隔X秒执行）", "interval"),
            ("定时任务（每天固定时间执行）", "cron")
        ]),
        input("间隔时间（秒）或执行时间（HH:MM）", name="time", type=TEXT)
    ])

    name = task_info["name"]
    description = task_info["description"]
    task_type = task_info["type"]
    time_value = task_info["time"]

    if name in tasks:
        toast("任务名称已存在，请使用其他名称！", color="error")
        return

    task_info >>log
    # 生成任务代码
    samplecode = """我有下面这些功能可以调用，使用例子如下,请选择使用里面的功能来合理完成需求：
    from deva import write_to_file,httpx,Dtalk
    from deva.admin import watch_topic
    打印日志：'sometext' >> log
    写入文件： 'some text' >>write_to_file('filename')
    抓取网页： response = await httpx(url)
    查找网页标签：response.html.search('<title>{}</title>')
    发送到钉钉：'@md@焦点分析|'+'some text'>>Dtalk()
    关注总结查看话题： content = await watch_topic('话题')
    """
    # 调用GPT生成Python代码
    prompt = f"仅限于以下的功能和使用方法：{samplecode}，根据以下描述: {description}，生成一个Python异步函数,只生成函数主体就可以，不需要执行代码，所有 import 都放在函数内部"
    result = sync_gpt(prompts=prompt)
    def get_python_code_from_deepseek(content):
        # 假设返回的内容中 Python 代码被标记为 ```python ... ```
        import re
        python_code = re.findall(r'```python(.*?)```', content, re.DOTALL)
        if python_code:
            return python_code[0].strip()
        return None
    job_code = get_python_code_from_deepseek(result)

    job_code>>log
    import ast



# 使用 AST 解析代码
    tree = ast.parse(job_code)

# 获取所有函数定义的名称
    namespace = {}
    exec(job_code,globals(), namespace)  # 动态执行生成的代码
    function_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)]
    job_name = function_names[0]
    
    job = namespace[job_name]

    if task_type == "interval":
        try:
            interval = int(time_value)
            # j = timer(interval=interval,start=True)(job)
            # print(j)
            scheduler.add_job(job, "interval", seconds=interval, id=name)
        except ValueError:
            toast("间隔时间必须为整数！", color="error")
            return
    elif task_type == "cron":
        try:
            hour, minute = map(int, time_value.split(":"))
            scheduler.add_job(job, "cron", hour=hour, minute=minute, id=name)
        except ValueError:
            toast("时间格式应为 HH:MM！", color="error")
            return

    tasks[name] = {
        "type": task_type,
        "time": time_value,
        "status": "运行中",
        "description": description,
        "job_code": job_code
    }
    toast(f"任务 '{name}' 创建成功！", color="success")
    # run_js("location.reload()")  # 刷新页面,刷新后 session 会失效

def manage_tasks():
    """管理定时任务"""
    if not tasks:
        put_text("当前没有定时任务。")
        return

    table_data = []
    for name, info in tasks.items():
        row = [
            name,
            info["description"],
            info["type"],
            info["time"],
            info["status"],
            put_row([
                put_button("停止", onclick=lambda n=name: stop_task(n), color="danger" if info["status"] == "运行中" else "secondary", disabled=info["status"] != "运行中"),
                put_button("启动", onclick=lambda n=name: start_task(n), color="success" if info["status"] == "已停止" else "secondary", disabled=info["status"] != "已停止"),
                put_button("删除", onclick=lambda n=name: delete_task(n), color="warning")
            ])
        ]
        table_data.append(row)

    put_table(
        table_data,
        header=["任务名称", "任务描述", "任务类型", "时间/间隔", "状态", "操作"]
    )
    

def stop_task(name):
    """停止任务"""
    if name in tasks:
        scheduler.pause_job(name)
        tasks[name]["status"] = "已停止"
        toast(f"任务 '{name}' 已停止！", color="success")
        run_js("location.reload()")  # 刷新页面

def start_task(name):
    """启动任务"""
    if name in tasks:
        scheduler.resume_job(name)
        tasks[name]["status"] = "运行中"
        toast(f"任务 '{name}' 已启动！", color="success")
        run_js("location.reload()")  # 刷新页面

def delete_task(name):
    """删除任务"""
    if name in tasks:
        scheduler.remove_job(name)
        del tasks[name]
        toast(f"任务 '{name}' 已删除！", color="success")
        run_js("location.reload()")  # 刷新页面

async def taskadmin():
    await init_admin_ui('Deva任务管理')
    
    
    put_button("创建定时任务", onclick=create_task)
    manage_tasks()  # 直接展示任务列表
    set_scope('task_log')
    
  
  

async def dbadmin():
    """数据库管理入口函数"""
    await init_admin_ui('Deva数据库管理')
    refresh_table_display()

async def streamadmin():
    await init_admin_ui("Deva实时流管理")
    put_markdown('### 数据流')
    put_buttons([s.name for s in streams],onclick=stream_click)
    

async def main():
    # await my_timer()
    # 这个将会把会话协程卡在这里不动，采用 run_async则不会堵塞
    # 添加可伸缩边栏
    
    
    await init_admin_ui("Deva管理面板")
    
    
    init_floating_menu_manager()
    
    set_table_style()  # 调用函数应用样式
    
    
    # 获取所有主题数据
    topics = NB('topics').items()
    peoples = NB('people').items()
    
    # 创建人物表格
    put_markdown('### 焦点分析')
    people_table = [['人物', '描述', '操作']]
    for key, value in peoples:
        # 添加操作按钮
        actions = put_button('news', onclick=lambda k=key, v=value: run_async(analyze_person(k, v)))
        
        # 添加行数据
        people_table.append([truncate(key), truncate(value, 50), actions])
    
    
    
    async def analyze_person(key, value):
        """分析人物并显示结果"""
        # 自定义提示词
        person = key
        action = '并将他的观点总结成几行经典的名言名句'
        full_prompt = f'获取关于{person}的最新6条新闻，要求返回的内容每一行都是一个一句话新闻，开头用一个和内容对应的图标，然后是一个不大于十个字的高度浓缩概括词，概括词用加粗字体，最后后面是新闻的一句话摘要，用破折号区隔开。每行一个新闻，不要有标题等其他任何介绍性内容，每行结尾也不要有类似[^2^]这样的引用标识，只需要返回6 条新闻即可。在新闻的最后面，总附加要求如下：{action}'
        
        # 定义异步内容函数
        async def async_content_func(session, scope):
            result = await get_gpt_response(
                prompt=full_prompt,
                session=session,
                scope=scope,
                model_type='kimi',
            )
            return result
            
        # 在动态弹窗中显示分析结果
        run_async(dynamic_popup(
            title=f'人物分析: {key}',
            async_content_func=async_content_func
        ))
        
    # 创建表格显示主题
    topic_table = [['主题', '附加要求', '操作']]
    # 用于存储每个主题的附加要求输入框
    action_inputs = {}
    
    for key, value in topics:
        # 创建可编辑的输入框
        action_input = put_input(name=f'action_{hash(key)}', value=value, placeholder='请输入附加要求')
        action_inputs[key] = action_input
        
        # 添加操作按钮，传入输入框的值
        actions = put_button('分析', onclick=lambda k=key: run_async(analyze_topic(k, action_inputs[k])))
        
        # 添加行数据
        topic_table.append([truncate(key), action_input, actions])
    
    put_row([
        put_table(topic_table).style('width: 48%; margin-right: 2%'),
        put_table(people_table).style('width: 48%; margin-left: 2%')
    ]).style('display: flex; justify-content: space-between')
    
    async def analyze_topic(key, action_input):
        """分析主题并显示结果"""
        # 获取当前输入框的值
        action = await pin[f'action_{hash(key)}']
        
        # 自定义提示词
        topic = key
        full_prompt = f' 获取{ topic}{action},要求返回的内容每一行都是一个一句话，开头用一个和内容对应的图标，然后是一个不大于十个字的高度浓缩概括词，概括词用加粗字体，再后面是一句话摘要，用破折号区隔开。每行一个内容，不要有标题等其他任何介绍性内容，只需要返回6 条新闻即可。'
        
        # 定义异步内容函数
        async def async_content_func(session, scope):
            result = await get_gpt_response(
                prompt=full_prompt,
                session=session,
                scope=scope,
                model_type='kimi',
            )
            return result
            
        # 在动态弹窗中显示分析结果
        run_async(dynamic_popup(
            title=f'主题分析: {key}',
            async_content_func=async_content_func
        ))
    
    put_markdown('### 浏览器')
    
    with put_collapse('书签', open=False):
        # 显示书签数据
        
        # 获取书签数据
        bookmarks = NB('bookmarks').items()
        
        # 创建表格显示书签
        bookmark_table = [['键', '值', '操作']]
        for key, value in bookmarks:
            # 添加操作按钮
            actions = put_buttons([
                {'label': '打开', 'value': 'open'},
                {'label': '删除', 'value': 'delete'}
            ], onclick=lambda v, k=key, val=value: (tab(val), toast(f"正在打开书签: {k}"), run_async(show_browser_status())) if v == 'open' else delete_bookmark(k))
            
            # 添加行数据
            bookmark_table.append([truncate(key), truncate(value,50), actions])
        
        put_table(bookmark_table)
        
        # 一键打开所有书签按钮
        def open_all_bookmarks():
            """打开所有书签"""
            for (key, value) in NB('bookmarks').items():
                tab(value)
            toast('正在后台打开所有书签...')
            run_async(show_browser_status())
        
        put_row([
            put_button('一键打开所有书签', onclick=open_all_bookmarks).style('margin-right: 10px'),
            put_button('新建书签', onclick=lambda:edit_data_popup(NB('bookmarks').items()|ls,'bookmarks'))
        ]).style('display: flex; justify-content: flex-start; align-items: center')
        # 删除书签函数
        def delete_bookmark(key):
            """删除指定书签"""
            NB('bookmarks').delete(key)
            toast(f'已删除书签: {key}')
            # 刷新页面
            run_js('window.location.reload()')
    
    
    
    # 显示浏览器状态
    set_scope('browser_status')
    # 添加打开新标签页的按钮
    put_row([
        put_button('+ 标签页', onclick=open_new_tab).style('margin-right: 10px'),
        put_button('拓展阅读', onclick=lambda: (extended_reading(),run_async(show_browser_status()))).style('margin-right: 10px'),
        put_button('总结', onclick=summarize_tabs).style('margin-right: 10px'),
        put_button('关闭所有', onclick=lambda: run_async(close_all_tabs()),color='danger'),
    ]).style('display: flex; justify-content: flex-start; align-items: center')
    
    
    run_async(show_browser_status())
    
    
    
    # 将书签管理放入可折叠区域
    

    
    
    put_markdown('### 定时任务')
    # 先获取所有timer实例
    timers = [s for s in Stream.instances() if isinstance(s, timer)]
    
    # 一次性创建所有按钮
    put_buttons(
        buttons=[s.func.__name__ for s in timers],
        # 定义独立的点击处理函数
        # 使用独立函数处理点击事件
        onclick=[lambda s=s: show_timer_detail(t) for t in timers]
    )
    set_scope('timer_content')
    # put_text(Stream.instances()|ls)
    
    log.sse('/logsse')
    # 创建SSE消息显示区域
    with put_collapse('log', open=True):
        put_logbox("log", height=100)

    run_js('''
        // 确保DOM元素存在
        function ensureElementReady(selector, callback) {
            const checkExist = setInterval(function() {
                const element = document.querySelector(selector);
                if (element) {
                    clearInterval(checkExist);
                    callback(element);
                }
            }, 100);
        }

        // 检查是否已经存在SSE连接
        if (window.sseConnection) {
            window.sseConnection.close();
        }
        
        // 创建新的SSE连接
        window.sseConnection = new EventSource('/logsse');
        
        // 确保消息容器存在后再添加事件监听器
        ensureElementReady('#webio-logbox-log', function(messageList) {
            // 监听消息事件
            window.sseConnection.onopen = function() {
                console.log('SSE连接已打开，等待消息...');
            };
            window.sseConnection.onmessage = function(event) {
                try {
                    // 解析接收到的数据
                    const data = JSON.parse(event.data);
                    const message = data.message || data;
                    
                    // 直接追加纯文本到logbox
                    const logbox = document.querySelector("#webio-logbox-log");
                    if (logbox) {
                        const logEntry = `${new Date().toLocaleTimeString()} - ${message}\\n`;
                        logbox.textContent += logEntry;
                        logbox.scrollTop = logbox.scrollHeight;
                    } else {
                        console.warn('未找到logbox元素');
                    }
                    
                    // 自动滚动到底部
                    messageList.scrollTop = messageList.scrollHeight;
                    
                    
                } catch (error) {
                    console.error('处理SSE消息时出错:', error);
                }
            };
        });

        // 处理连接错误
        window.sseConnection.onerror = function(error) {
            console.error('SSE连接出错:', error);
            if (window.sseConnection) {
                window.sseConnection.close();
            }
            setTimeout(() => {
                try {
                    window.sseConnection = new EventSource('/logsse');
                    console.log('SSE连接已重新建立');
                } catch (e) {
                    console.error('重新连接SSE失败:', e);
                }
            }, 5000);
        };

        // 添加调试信息
        console.log('SSE脚本已加载');
        console.log('当前页面URL:', window.location.href);
        console.log('SSE连接URL:', '/logsse');
    ''')
    
     
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



def display_table_basic_info(db, tablename):
    """显示表基本信息
    
    参数:
        db: 数据库对象
        tablename (str): 表名称
    """
    # 获取数据库中的所有数据类型
    data_types = {}
    for key, value in db.items():
        data_type = type(value).__name__
        data_types[data_type] = data_types.get(data_type, 0) + 1
    
    # 将数据类型统计转换为表格行
    type_rows = [[dtype, count] for dtype, count in data_types.items()]
    
    # 显示基本信息标题
    put_markdown(f"> 您点击了 `{tablename}` 表格，表基本信息：")
    
    # 显示基本信息表格
    put_row([
        put_table([
            ['属性', '值'],
            ['记录数', len(db)],
            ['最大容量', db.maxsize or '无限制'], 
            ['存储路径', db.db.filename],
            ['表描述', NB('default').get(db.name) or '无描述']
        ]),
        
        # 显示数据类型统计表格
        put_table([
            ['数据类型', '数量'],
            *type_rows  # 展开所有数据类型统计行
        ])
    ])
    
@use_scope('table_content')
def table_click(tablename):
    """处理表格点击事件，展示表格内容
    
    参数:
        tablename (str): 表格名称
    """
    db = NB(tablename)
    clear('table_content')
    put_markdown(f"#### 表：{tablename} ")
                
    
    
    # 调用显示表基本信息函数
    display_table_basic_info(db, tablename)

    async def save_table_desc():
        # 获取输入的表描述
        new_desc = await pin['table_desc']
        # 更新数据库中的表描述
        NB('default').update((db.name, new_desc))
        # 关闭弹窗
        close_popup()
        # 刷新表格显示
        table_click(db.name)
    
    put_row([
        put_button('修改表描述', onclick=lambda: 
                   popup('修改表描述', [
                        put_input('table_desc', value=NB('default').get(db.name) or '', placeholder='请输入表描述'),
                        put_buttons(['保存', '取消'], onclick=[
                            lambda: run_async(save_table_desc()),
                            close_popup
                        ])
                   ])),
        put_button('删除表', onclick=lambda: 
                   popup('删除表', [
                        put_markdown('### ⚠️警告：此操作不可逆！'),
                        put_markdown(f'请输入"确认"以删除表**{tablename}**'),
                        put_input('delete_confirm', placeholder='请输入"确认"确认不误删'),
                        put_buttons(['删除', '取消'], onclick=[
                            lambda: run_async(delete_table(tablename)),
                            close_popup
                        ])
                   ]), color='danger')
    ]).style('display: flex; justify-content: flex-start; align-items: center')
    
    put_markdown(f"####  数据表内容")
    put_markdown(f"> 仅仅随机展示 10 条信息：")
    # 获取表格数据并采样10条
    items = NB(tablename).items() >> sample(10)
    
    # 按数据类型分类
    categorized_data = {
        'dataframes': [(k, v) for k, v in items if isinstance(v, pd.DataFrame)],
        'strings': [(k, v) for k, v in items if isinstance(v, (str,int,float)) and not str(k).replace('.', '').isdigit()],
        'timeseries': [(k, v) for k, v in items if isinstance(k, (float, int)) or str(k).replace('.', '').isdigit()],
        'others': [(k, v) for k, v in items if not isinstance(v, (pd.DataFrame, str)) and not isinstance(v, (float, int,str))and not (isinstance(k, (float, int)) and str(k).replace('.', '').isdigit()) ]
    }
    
    put_button('新增数据', onclick=lambda: edit_data_popup(categorized_data['strings'],tablename=tablename))

    
    
    # 显示字符串类型数据
    if categorized_data['strings']:
        with put_collapse('strings', open=True):
            # 创建带表头的只读表格
            read_only_table = [['键', '值']]  # 表头
            # 添加数据行
            for key, value in categorized_data['strings']:
                read_only_table.append([key, value])
            # 显示表格
            put_table(read_only_table)
                        # 定义编辑数据的弹出窗口函数
            
            put_button('编辑数据', onclick=lambda: edit_data_popup(categorized_data['strings'],tablename=tablename))
            
    # 显示其他类型数据
    if categorized_data['others']:
        with put_collapse('其他对象', open=True):
            for key, value in categorized_data['others']:
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
                        print(formatted_data)
                        if formatted_data:
                            put_table(formatted_data)
                        else:
                            put_text(str(value))
                    else:
                        put_text(str(value))

    # 显示DataFrame类型数据
    if categorized_data['dataframes']:
        with put_collapse('dataframe', open=True):
            for df_name, df in categorized_data['dataframes']:
                with put_collapse(df_name, open=True):
                    paginate_dataframe(scope=df_name, df=df, page_size=10)

    # 显示时间序列数据
    if categorized_data['timeseries']:
        with put_collapse('时间序列数据', open=True):
            put_button('编辑数据', onclick=lambda: edit_data_popup(categorized_data['timeseries'],tablename=tablename))
            # 创建表头
            table_data = [['时间戳', '可读时间', '值']]
            
            # 遍历所有时间序列数据
            for key, value in categorized_data['timeseries']:
                # 将时间戳转换为可读时间格式
                from datetime import datetime
                readable_time = datetime.fromtimestamp(float(key)).strftime('%Y-%m-%d %H:%M:%S')
                
                # 添加行数据
                table_data.append([key, readable_time, value])
            
            # 统一显示所有时间序列数据
            put_table(table_data)

# 保存修改的回调函数
async def save_string(key,data,tablename):
    new_value = await pin[f'value_{hash(key)}']  # 使用hash值作为输入框ID，避免中文key的问题
    # 更新数据库
    NB(tablename).update((key, new_value))
    # 更新data列表中的值
    for i, (k, v) in enumerate(data):
        if k == key:
            data[i] = (key, new_value)
            break
    # 刷新显示
    table_click(tablename)
# 关闭当前popup
    close_popup()
        # 重新打开编辑popup以刷新内容
    edit_data_popup(data,tablename=tablename)
# 删除键值对的回调函数
async def delete_string(key,data,tablename):
    # 删除数据
    del NB(tablename)[key]
    # 刷新显示
    # 从data中删除对应的键值对
    data[:] = [item for item in data if item[0] != key]
    table_click(tablename)
    # 关闭当前popup
    close_popup()
        # 重新打开编辑popup以刷新内容
    edit_data_popup(data,tablename=tablename)

# 新增键值对的回调函数
async def add_string(data,tablename):
    new_key = await pin['new_key']
    new_value = await pin['new_value']
    if new_key and new_value:
        # print(data)
        # 更新数据库
        data.append((new_key, new_value))
        NB(tablename).update((new_key, new_value))
        # 清除新增表单
        clear('add_form')
        # 刷新显示
        table_click(tablename)
        # 关闭当前popup
        close_popup()
        # 重新打开编辑popup以刷新内容
        edit_data_popup(data,tablename=tablename)
    else:
        toast("键名和值不能为空", color='error')

def edit_data_popup(data,tablename):
    return popup('编辑数据', [
        # put_button('新增键值对', onclick=show_add_form),
        put_row([
            put_input('new_key', placeholder='新键名'),
            put_input('new_value', placeholder='新值'),
            put_button('新增', onclick=lambda:add_string(data,tablename)),
            # put_button('取消', onclick=lambda: clear('add_form'))
        ]),
        # 创建带表头的可编辑表格
        put_table([
            ['键', '值', '操作'],  # 表头
            *[
                [
                    put_text(key),
                    put_input(f'value_{hash(key)}', value=value),
                    put_buttons([
                        {'label': '保存', 'value': 'save'},
                        {'label': '删除', 'value': 'delete'}
                    ], onclick=lambda v, k=key: save_string(k,data,tablename) if v == 'save' else delete_string(k,data,tablename=tablename))
                ] for key, value in data
            ]
        ]),
        # 如果所有key都不是float类型，才显示新增按钮
    ], size='large')

def stream_click(streamname):
    put_markdown("> You click `%s` stream,show records:" % streamname)
    
    s = [s for s in Stream.instances() if s.name==streamname][0]
    popup('Stream Viewer', [
        put_html(f'<iframe src="{hash(s)}" style="width:100%;height:80vh;border:none;"></iframe>')
    ], size='large')


def create_nav_menu():
    """创建Bootstrap1风格的导航菜单"""
    run_js('''
        // 创建导航栏容器
        const nav = document.createElement('div');
        nav.className = 'navbar';
        nav.style.position = 'fixed';
        nav.style.top = '0';
        nav.style.width = '100%';
        nav.style.zIndex = '1000';
        nav.style.backgroundColor = '#f5f5f5';
        nav.style.borderBottom = '1px solid #ddd';
        nav.style.padding = '10px 20px';

        // 创建品牌logo
        const brand = document.createElement('div');
        brand.className = 'brand';
        const brandLink = document.createElement('a');
        brandLink.href = '#';
        // 判断是否为移动设备
        if (!/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)) {
            brandLink.innerText = document.title;  // 仅在非移动设备显示标题
        }
        brandLink.style.fontSize = '20px';
        brandLink.style.fontWeight = 'bold';
        brandLink.style.color = '#333';
        brandLink.style.textDecoration = 'none';
        brand.appendChild(brandLink);

        // 创建菜单容器
        const menu = document.createElement('div');
        menu.className = 'nav';
        menu.style.display = 'flex';
        menu.style.marginLeft = '20px';

        // 获取当前页面路径
        const currentPath = window.location.pathname;

        // 创建菜单项
        const menuItems = [
            {name: '首页', path: '/', action: () => location.reload()},
            {name: '数据库', path: '/dbadmin', action: () => window.location.href = '/dbadmin'},
            {name: '实时流', path: '/streamadmin', action: () => window.location.href = '/streamadmin'},
            {name: '任务', path: '/taskadmin', action: () => window.location.href = '/taskadmin'},
            {name: '关于', path: '#', action: () => alert('Deva管理面板 v1.0')}
        ];

        menuItems.forEach(item => {
            const link = document.createElement('a');
            link.href = item.path;
            link.innerText = item.name;
            link.style.padding = '5px 15px';
            link.style.color = '#333';
            link.style.textDecoration = 'none';
            link.style.marginRight = '10px';
            link.style.borderRadius = '3px';
            
            // 高亮当前页面
            if (currentPath === item.path) {
                link.style.backgroundColor = '#ddd';
            }

            // 添加hover效果
            link.onmouseover = () => {
                link.style.backgroundColor = '#eee';
            };
            link.onmouseout = () => {
                link.style.backgroundColor = currentPath === item.path ? '#ddd' : 'transparent';
            };

            link.onclick = item.action;
            menu.appendChild(link);
        });

        // 将元素添加到页面
        nav.appendChild(brand);
        nav.appendChild(menu);
        document.body.insertBefore(nav, document.body.firstChild);

        // 调整页面内容位置
        document.body.style.paddingTop = '50px';
    ''')


if __name__ == '__main__':
    from deva.page import page
    

    # 创建一个名为'stream_webview'的Web服务器实例，监听所有网络接口(0.0.0.0)
    # 然后为该服务器添加路由处理器，将'/admin'路径映射到dbadmin处理函数
    # 使用PyWebIO的webio_handler进行封装，并指定CDN地址
    handlers = [
        (r'/dbadmin', webio_handler(dbadmin, cdn='https://fastly.jsdelivr.net/gh/wang0618/PyWebIO-assets@v1.8.3/')),
        (r'/streamadmin', webio_handler(streamadmin, cdn='https://fastly.jsdelivr.net/gh/wang0618/PyWebIO-assets@v1.8.3/')),
        (r'/', webio_handler(main, cdn='https://fastly.jsdelivr.net/gh/wang0618/PyWebIO-assets@v1.8.3/')),
        (r'/taskadmin', webio_handler(taskadmin, cdn='https://fastly.jsdelivr.net/gh/wang0618/PyWebIO-assets@v1.8.3/'))
    ]
    NW('stream_webview',host='0.0.0.0').application.add_handlers('.*$', handlers)
 

    Deva.run()

