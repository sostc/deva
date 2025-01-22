
# coding: utf-8

# 1. monitor监控全局streams和tables，并可执行代码。属于内部需求
# 2. webview可能给外部用户使用，考虑安全性，不能执行代码，不能和monitor混在一起，属于外部需求。
# 3. monitor需要手工开启，安全上可以考虑身份验证（所有页面都需要验证），端口隔离（限制内网访问）

# In[1]:


import tornado
import json
import os
from pymaybe import maybe
# from .web.sockjs.tornado import SockJSRouter, SockJSConnection
from sockjs.tornado import SockJSRouter, SockJSConnection

from tornado import gen
from deva.core import Stream
from deva.namespace import NB, NS
from deva.bus import log
from deva.pipe import ls, pmap, concat, head, sample
from deva.page import Page,render_template
import datetime
"""
Deva监控模块

主要功能:
- 监控全局streams和tables
- 提供代码执行功能
- 提供Web界面查看监控数据

主要组件:
- monitor_page: 监控页面实例,用于注册路由
- MonitorConnection: WebSocket连接类,用于实时数据推送
- ChatConnection: WebSocket连接类,用于代码执行

使用示例::

    from deva.monitor import monitor_page
    from deva.page import PageServer
    
    # 启动监控服务器
    ps = PageServer()
    ps.add_routes(monitor_page.get_routes())
    ps.start()

注意:
- 监控功能仅供内部使用,需要手动开启
- 建议通过身份验证和端口隔离等方式保证安全性
- 不建议与面向外部用户的webview混用
"""


monitor_page = Page()


@monitor_page.route('/')
def index():
    # 取出所有有缓冲设置且有名称的流实例,类似NS('当下行情数据抽样',cache_max_len=1)
    #     streams = namespace.values()>>ls
    streams = [stream for stream in Stream.instances() if stream.name]
    tables = NB('default').tables | ls
    return render_template('./templates/monitor.html', streams=streams,
                tablenames=tables, sock_url='/')


@monitor_page.route("/allstreams")
def allstreams():
    """获取所有数据流实例并生成HTML列表

    将所有Stream实例转换为HTML链接列表,每个链接指向对应流的详情页。
    链接文本为Stream的字符串表示,链接地址使用Stream的hash值作为标识。

    Returns:
        str: 包含所有数据流链接的HTML列表
    """
    s_list = [s for s in Stream.instances()]

    def _f(s):
        text = str(s).replace('<', '[').replace('>', ']')
        sid = hash(s)
        return f'<li><a href="stream/{sid}">{text}</a></li>'

    result = s_list >> pmap(_f) >> concat('')
    return result

@monitor_page.route('/alltables')
def get_tables():
    """获取所有数据表并生成HTML列表
    
    将数据库中的所有表名转换为HTML链接列表,每个链接指向对应表的详情页。
    链接文本为表名,链接地址使用表名作为标识。
    
    Returns:
        str: 包含所有数据表链接的HTML列表
    """
    data = NB('default').tables >> pmap(lambda x: f'<li><a class="Stream" href="table/{x}">{x}</a></li>') >> concat('')
    return data


@monitor_page.route('/table/<tablename>')
def get_table_keys(tablename):
    """获取指定数据表的键列表并生成HTML链接
    
    从指定的数据表中随机采样20个键,并将其转换为HTML链接列表。
    每个链接指向该键对应的数据详情页。
    
    Args:
        tablename (str): 数据表名称
        
    Returns:
        None: 直接写入HTML响应
        
    示例:
        /table/mytable 将返回mytable表中20个随机键的链接列表
    """
    keys = sample(20) << NB(tablename).keys()
    data = keys >> pmap(lambda x: f'<li><a class="Stream" href="{tablename}/{x}">{x}</a></li>') >> concat('')
    return data

@monitor_page.route('/table/<tablename>/<key>')
def get_table_values(tablename, key):
    """获取指定数据表中指定键的值
    
    从指定的数据表中获取指定键对应的数据,并根据数据类型进行不同的处理:
    - 列表类型: 转换为DataFrame并取前250行,以JSON格式返回
    - 字典类型: 直接转换为JSON格式返回
    - DataFrame类型: 取前250行并转换为HTML表格返回
    - 其他类型: 转换为字符串并以JSON格式返回
    
    Args:
        tablename (str): 数据表名称
        key: 要查询的键值
        
    Returns:
        str: 处理后的数据,可能是JSON字符串或HTML表格
    """
    import pandas as pd
    data = NB(tablename).get(key)
    if isinstance(data, list):
        data = data >> head(250) >> ls
        return json.dumps(pd.DataFrame(data)
                          .to_dict(orient='records'), ensure_ascii=False)
    elif isinstance(data, dict):
        return json.dumps(data, ensure_ascii=False)
    elif isinstance(data, pd.DataFrame):
        # return json.dumps(data.head(250)
        #                   .to_dict(orient='records'), ensure_ascii=False)
        return data.head(250).to_html()
    else:
        return json.dumps({key: str(data)}, ensure_ascii=False)

@monitor_page.route('/stream/<name_or_id>')
def get_stream( name_or_id):
    """获取指定数据流并渲染详情页面
    
    根据名称或ID查找数据流实例,并渲染对应的详情页面。
    优先按名称匹配,若未找到则按hash值匹配。
    
    Args:
        name_or_id (str): 数据流名称或hash值
        
    Returns:
        None: 直接渲染stream.html模板
        
    示例:
        /stream/mystream 将渲染mystream数据流的详情页
        /stream/123456 将渲染hash值为123456的数据流详情页
    """
    try:
        stream = [stream for stream in Stream.instances(
        ) if stream.name == name_or_id][0]
    except:
        stream = [stream for stream in Stream.instances() if str(
            hash(stream)) == name_or_id][0]
    stream_id = hash(stream)
    return render_template('./templates/stream.html', stream_id=stream_id, sock_url='../')


class StreamConnection(SockJSConnection):
    """WebSocket连接处理类,用于处理数据流的实时推送

    主要功能:
    - 建立WebSocket连接并处理数据流订阅
    - 接收客户端消息并处理数据流切换
    - 将数据流实时推送给客户端
    - 处理连接关闭和资源清理

    继承自SockJSConnection,实现了WebSocket连接的基本功能。
    使用Stream类实现数据流的订阅和推送。

    属性:
        _out_stream (Stream): 输出数据流,用于向客户端推送数据
        _in_stream (Stream): 输入数据流,用于处理客户端消息
        out_stream (Stream): 当前订阅的数据流
        connection: 数据流连接对象
        request: WebSocket请求对象
    """

    def __init__(self, *args, **kwargs):
        self._out_stream = Stream()
        self.link1 = self._out_stream.sink(self.send)
        self._in_stream = Stream()
        self.link2 = self._in_stream.sink(self.process_msg)
        super(StreamConnection, self).__init__(*args, **kwargs)

    def on_open(self, request):
        """处理WebSocket连接打开事件
        
        主要功能:
        - 创建输出数据流
        - 建立数据流连接
        - 发送欢迎消息
        - 记录客户端IP和连接时间
        
        Args:
            request: WebSocket请求对象,包含客户端信息
            
        注意:
            - 使用maybe处理headers中的x-forward-for获取真实IP
            - 通过log记录连接信息
        """
        self.out_stream = Stream()
        self.connection = self.out_stream >> self._out_stream
        json.dumps({'data': 'welcome'}) >> self.out_stream
        self.request = request
        self.request.ip = maybe(self.request.headers)[
            'x-forward-for'].or_else(self.request.ip)

        f'open:{self.request.ip}:{datetime.datetime.now()}' >> log

    @gen.coroutine
    def on_message(self, msg):
        json.loads(msg) >> self._in_stream

    def process_msg(self, msg):
        """处理客户端发送的消息
        
        主要功能:
        - 接收客户端发送的stream_id
        - 记录查看日志
        - 切换数据流订阅
        - 将数据流内容推送给客户端
        
        参数:
            msg (dict): 客户端发送的消息,包含stream_id
            
        注意:
            - 异步操作(如gen.sleep)才能实现真正的异步请求
            - IO操作适合异步,CPU计算不适合异步
            - 一个用户的超时不会影响其他用户
        """
        import pandas as pd
        stream_id = msg['stream_id']
        'view:%s:%s:%s' % (stream_id, self.request.ip,
                           datetime.datetime.now()) >> log
        # gen.sleep(10)##只有这里的操作都类似gensleep一样是异步操作时,
        # 整个请求才能异步,某个用户超时才不会影响别的用户,否则一个用户影响其他用户
        # io的东西走异步,其余的函数如果是cpu计算,不要走异步
        if stream_id != hash(self.out_stream):
            self.connection.destroy()
            self.out_stream = [stream for stream in Stream.instances() if str(
                hash(stream)) == stream_id][0]
            self.connection = self.out_stream.map(lambda x: json.dumps(
                {'stream_id': stream_id, 'data': x.to_html() if isinstance(x, pd.DataFrame) else x})) >> self._out_stream
            data = maybe(self.out_stream).recent(1)[
                0].or_else('暂无数据')
            json.dumps({'stream_id': stream_id, 'data': data}) >> self._out_stream
    def on_close(self):
        f'close:{self.request.ip}:{datetime.datetime.now()}' >> log
        # for connection in self.connections:
        #     connection.destroy()

        # self.connections = set()
        self.connection.destroy()
        self.link1.destroy()
        self.link2.destroy()
        self.out_stream.destroy()

class Monitor(object):
    """监控器类,用于启动和管理监控服务器
    
    主要功能:
    - 启动HTTP服务器
    - 注册WebSocket路由
    - 管理页面路由
    
    属性:
        page (Page): 全局页面实例
        port (int): 监听端口
        host (str): 监听地址
        ChatRouter (SockJSRouter): 聊天WebSocket路由
        StreamRouter (SockJSRouter): 数据流WebSocket路由
        application (Application): Tornado应用实例
        server (HTTPServer): HTTP服务器实例
    """
    page = monitor_page

    def __init__(self, host='127.0.0.1', port=9998):
        """初始化监控器实例
        
        Args:
            host (str): 监听地址,默认127.0.0.1
            port (int): 监听端口,默认9998
        """
        self.page = Monitor.page
        self.port = port 
        self.host = host

        self.StreamRouter = SockJSRouter(StreamConnection, r'')
        self.application = tornado.web.Application(
            self.page.get_routes() +
            self.StreamRouter.urls 
        )

    def add_page(self, page):
        """添加页面路由
        
        Args:
            page (Page): 页面实例
        """
        self.application.add_handlers('.*$', page.get_routes())

    def start(self,):
        """启动监控服务器并打开浏览器"""
        self.server = self.application.listen(self.port)
        os.system(f'open http://{self.host}:{self.port}/')

    def close(self):
        """关闭监控服务器"""
        self.server.close()


def exec_command(command):
    """执行命令并返回结果
    
    主要功能:
    - 记录命令到日志
    - 执行赋值语句或普通表达式
    - 返回执行结果或错误信息
    
    参数:
        command (str): 要执行的命令字符串
        
    返回:
        str: 执行结果或错误信息
        
    示例:
        >>> exec_command("a=1")  
        'exec:a=1\n'
        >>> exec_command("1+1")
        '1+1\n2\n'
    """
    command>>log
    try:
        if '=' in command:  # 执行赋值语句
            v, ex = command.replace(' ', '').split('=')
            globals()[v] = eval(ex)
            return f'exec:{command}\n'
        else:  # 执行普通表达式
            anwser = eval(command)
            return f'{command}\n{anwser}\n'
    except Exception as e:
        return str(e)


if __name__ == '__main__':
    # monitor = Monitor(port=9998)
    # monitor.start()
    from deva.when import timer
    @timer(1)
    def foo():
        'hello'>>log
    from deva.core import Deva
    from deva.namespace import NW
    NW('stream_webview').add_page(monitor_page)
    Deva.run()
# In[7]:


# In[12]:


# server.stop()
