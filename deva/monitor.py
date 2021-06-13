
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
from .core import Stream
from .namespace import NB, NS
from .bus import log
from .pipe import ls, pmap, concat, head, sample
from .page import Page
import datetime


monitor_page = Page()


@monitor_page.route('/')
@gen.coroutine
def get(self, *args, **kwargs):
    # 取出所有有缓冲设置且有名称的流实例,类似NS('当下行情数据抽样',cache_max_len=1)
    #     streams = namespace.values()>>ls
    streams = [stream for stream in Stream.instances() if stream.name]
    tables = NB('default').tables | ls
    self.render('./templates/monitor.html', streams=streams,
                tablenames=tables, sock_url='/')


@monitor_page.route("/allstreams")
@gen.coroutine
def allstreams(self):
    s_list = [s for s in Stream.instances()]

    def _f(s):
        text = str(s).replace('<', '[').replace('>', ']')
        sid = hash(s)
        return f'<li><a href="stream/{sid}">{text}</a></li>'

    result = s_list >> pmap(_f) >> concat('')
    self.write(result)


@monitor_page.route('/alltables')
@gen.coroutine
def get_tables(self,):
    data = NB('default').tables >> pmap(lambda x: f'<li><a class="Stream" href="table/{x}">{x}</a></li>') >> concat('')
    self.write(data)


@monitor_page.route('/table/<tablename>')
@gen.coroutine
def get_table_keys(self, tablename):
    keys = sample(20) << NB(tablename).keys()
    data = keys >> pmap(lambda x: f'<li><a class="Stream" href="{tablename}/{x}">{x}</a></li>') >> concat('')
    self.write(data)


@monitor_page.route('/table/<tablename>/<key>')
def get_table_values(tablename, key):
    import pandas as pd
    data = NB(tablename).get(key)
    if isinstance(data, list):
        data = data >> head(250) >> ls
        return json.dumps(pd.DataFrame(data)
                          .to_dict(orient='records'), ensure_ascii=False)
    elif isinstance(data, dict):
        return json.dumps(data, ensure_ascii=False)
    elif isinstance(data, pd.DataFrame):
        return json.dumps(data.head(250)
                          .to_dict(orient='records'), ensure_ascii=False)
    else:
        return json.dumps({key: data}, ensure_ascii=False)


@monitor_page.route('/stream/<name_or_id>')
def get_stream(self, name_or_id):
    try:
        stream = [stream for stream in Stream.instances(
        ) if stream.name == name_or_id][0]
    except:
        stream = [stream for stream in Stream.instances() if str(
            hash(stream)) == name_or_id][0]
    stream_id = hash(stream)
    self.render('./templates/stream.html', stream_id=stream_id, sock_url='../')


class StreamConnection(SockJSConnection):

    def __init__(self, *args, **kwargs):
        self._out_stream = Stream()
        self.link1 = self._out_stream.sink(self.send)
        self._in_stream = Stream()
        self.link2 = self._in_stream.sink(self.process_msg)
        super(StreamConnection, self).__init__(*args, **kwargs)

    def on_open(self, request):
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


# In[4]:

# 代码执行
NS('执行代码').start_cache(200)
chatroom = Stream()
chatroom.start_cache(200, cache_max_age_seconds=60 * 60 * 24 * 30)


def exec_command(command):
    try:
        if '=' in command:  # 执行赋值语句
            v, ex = command.replace(' ', '').split('=')
            globals()[v] = eval(ex)
            return f'exec:{command}'
        else:  # 执行普通表达式
            anwser = eval(command)
            return f'eval:{command}</br>anwser:{anwser}'
    except Exception as e:
        return e


exec_room = chatroom.map(exec_command)
exec_room.start_cache(200)
exec_room.map(lambda x: exec_room.recent(5) | concat('</br>')) >> NS('执行代码')


class ChatConnection(StreamConnection):
    def on_open(self, request):
        self.out_stream = NS('执行代码')
        self.out_stream.sink(self.send)
        maybe(NS('执行代码')).recent(1)[0].or_else('暂无数据') >> self.out_stream

        self.request = request
        self.request.ip = maybe(self.request.headers)[
            'x-forward-for'].or_else(self.request.ip)

    def on_message(self, msg):
        msg >> chatroom
        f'{msg}:{self.request.ip}:{datetime.datetime.now()}' >> log


class Monitor(object):
    page = monitor_page

    def __init__(self, host='127.0.0.1', port=9998):
        self.page = Monitor.page
        self.port = port
        self.host = host

        self.ChatRouter = SockJSRouter(ChatConnection, r'/chatroom')
        self.StreamRouter = SockJSRouter(StreamConnection, r'')
        self.application = tornado.web.Application(
            self.page.get_routes() +
            self.StreamRouter.urls +
            self.ChatRouter.urls
        )

    def add_page(self, page):
        self.application.add_handlers('.*$', page.get_routes())

    def start(self,):
        self.server = self.application.listen(self.port)
        os.system(f'open http://{self.host}:{self.port}/')

    def close(self):
        self.server.close()


if __name__ == '__main__':
    monitor = Monitor(port=9998)
    monitor.start()
# In[7]:


# In[12]:


# server.stop()
