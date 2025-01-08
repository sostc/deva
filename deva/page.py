from collections import defaultdict
"""
页面视图模块
~~~~~~~~~

本模块提供了Web页面视图相关的功能,包括:

- 页面路由和渲染
- 数据流的Web可视化
- WebSocket实时更新
- 页面服务器管理

主要组件:
- page: 全局Page实例,用于注册路由
- PageServer: Web服务器类,用于启动和管理服务
- render_template: 模板渲染函数

使用示例::

    from deva.page import page,PageServer,render_template 
    from deva import *

    # 创建数据流
    s = from_textfile('/var/log/systemf.log')
    s1 = s.sliding_window(5).map(concat('<br>'),name='system.log')
    s.start()

    def sample_df_html(n=5):
        return NB('sample')['df'].sample(n).to_html()

    # 创建定时更新的数据流
    s2 = timer(func=sample_df_html,start=True,name='每秒更新',interval=1)
    s3 = timer(func=sample_df_html,start=True,name='每三秒更新',interval=3)

    # 注册路由
    @page.route('/')
    def get():
        streams = [s1,s2,s3]
        return render_template('./templates/streams.html', streams=streams)

    # 启动服务器
    ps = PageServer()
    ps.start()

注:调试接口参考自 https://gist.github.com/rduplain/4983839
"""

import tornado.ioloop
import tornado.web
import tornado.wsgi
import contextlib
from functools import partial
from werkzeug.routing import Map, Rule
import re
import os
import inspect
from werkzeug.local import LocalStack, LocalProxy
import logging
from collections import OrderedDict
from pymaybe import maybe
# from .web.sockjs.tornado import SockJSRouter, SockJSConnection
from sockjs.tornado import SockJSRouter, SockJSConnection

import json
from tornado import gen
from .core import Deva, Stream
from .bus import log, bus
from .pipe import ls
import datetime
from .namespace import NW


try:
    from tornado.wsgi import WSGIAdapter
except Exception:
    with_wsgi_adapter = False
else:
    with_wsgi_adapter = True

logger = logging.getLogger(__name__)
try:
    logger.addHandler(logging.NullHandler())
except Exception:
    # python 2.6
    pass


_rule_re = re.compile(
    r"""
    (?P<static>[^<]*)                           # static rule data
    <
    (?:
        (?P<converter>[a-zA-Z_][a-zA-Z0-9_]*)   # converter name
        (?:\((?P<args>.*?)\))?                  # converter arguments
        \:                                      # variable delimiter
    )?
    (?P<variable>[a-zA-Z_][a-zA-Z0-9_]*)        # variable name
    >
    """,
    re.VERBOSE,
)


def _lookup_handler_object(name):
    top = _handler_ctx_stack.top
    if top is None:
        raise RuntimeError('working outside of request context')
    return top


_handler_ctx_stack = LocalStack()

"""
proxy to the current request handler object.
"""
handler = LocalProxy(partial(_lookup_handler_object, 'handler'))


@contextlib.contextmanager
def ctx_man(ctx):
    _handler_ctx_stack.push(ctx)
    yield
    _handler_ctx_stack.pop()


def get_current_traceback():
    "Get the current traceback in debug mode, using werkzeug debug tools."
    # Lazy import statement, as debugger is only used in development.
    from werkzeug.debug.tbtools import get_current_traceback
    # Experiment with skip argument, to skip stack frames in traceback.
    traceback = get_current_traceback(skip=2, show_hidden_frames=False,
                                      ignore_system_exceptions=True)
    return traceback


class DebuggableHandler(tornado.web.RequestHandler):

    def write_error(self, status_code, **kwargs):
        self.finish(self.get_debugger_html(status_code, **kwargs))

    def get_debugger_html(self, status_code, **kwargs):
        assert isinstance(self.application, DebugApplication)
        traceback = self.application.get_current_traceback()
        keywords = self.application.get_traceback_renderer_keywords()
        html = traceback.render_full(**keywords).encode('utf-8', 'replace')
        return html.replace(b'WSGI', b'tornado')


class DebugApplication(tornado.web.Application):
    "Tornado Application supporting werkzeug interactive debugger."

    def get_current_traceback(self):
        "Get the current Python traceback, keeping stack frames in debug app."
        traceback = get_current_traceback()
        for frame in traceback.frames:
            self.debug_app.frames[frame.id] = frame
        self.debug_app.tracebacks[traceback.id] = traceback
        return traceback

    def get_traceback_renderer_keywords(self):
        "Keep consistent debug app configuration."
        # DebuggedApplication generates a secret for use in interactions.
        # Otherwise, an attacker could inject code into our application.
        # Debugger gives an empty response when secret is not provided.
        return dict(evalex=self.debug_app.evalex, secret=self.debug_app.secret)

    if not with_wsgi_adapter:
        # these are needed for tornado < 4
        def __init__(self, *args, **kwargs):
            from werkzeug.debug import DebuggedApplication
            self.debug_app = DebuggedApplication(app=self, evalex=True)
            self.debug_container = tornado.wsgi.WSGIContainer(self.debug_app)
            super(DebugApplication, self).__init__(*args, **kwargs)

        def __call__(self, request):
            if '__debugger__' in request.uri:
                # Do not call get_current_traceback here, as this is a follow-up
                # request from the debugger. DebugHandler loads the traceback.
                return self.debug_container(request)
            return super(DebugApplication, self).__call__(request)

        @classmethod
        def debug_wsgi_app(cls, environ, start_response):
            "Fallback WSGI application, wrapped by werkzeug's debug middleware."
            status = '500 Internal Server Error'
            response_headers = [('Content-type', 'text/plain')]
            start_response(status, response_headers)
            return ['Failed to load debugger.\n']


class TemplateProxy(object):
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


def render_template(*args, **kwargs):
    return TemplateProxy(*args, **kwargs)


class Page(object):
    """页面类,用于处理HTTP请求和路由

    主要功能:
    - 注册路由和处理函数
    - 支持werkzeug和tornado两种路由语法
    - 支持tornado和jinja2两种模板引擎
    - 支持调试模式

    示例用法::

        from deva.page import Page

        page = Page(debug=True)

        @app.route("/hello")
        def foo():
            return "hello"

    参数:
        debug (bool): 是否启用werkzeug调试器
        template_path (str): 模板文件路径,默认为app.py所在目录下的templates目录
        template_engine (str): 使用的模板引擎,可选'tornado'或'jinja2'
    """

    def __init__(self, debug=False, template_path=None, template_engine='tornado'):
        """初始化Page实例

        Args:
            debug (bool): 是否启用调试模式
            template_path (str): 模板路径,默认为None
            template_engine (str): 模板引擎,可选'tornado'或'jinja2'
        """
        assert template_engine in ('tornado', 'jinja2')
        self.registery = OrderedDict()
        self.url_map = Map()
        self.mapper = self.url_map.bind("", "/")
        self.debug = True
        self.methods = []
        self.routes_list = []

        if not template_path:
            frames = inspect.getouterframes(inspect.currentframe())
            frame, filename, line_number, function_name, lines, index = frames[0]
            for frame in frames:
                if filename != frame[1]:
                    filename = frame[1]
                    break
            self.template_path = os.path.realpath(
                os.path.join(os.path.dirname(filename), 'templates'))
        else:
            self.template_path = template_path

        self.template_engine = template_engine

        if template_engine == 'jinja2':
            from jinja2 import Environment, FileSystemLoader
            self.template_env = Environment(
                loader=FileSystemLoader(self.template_path))

    def get_routes(self):
        """获取编译后的路由和处理类列表

        Returns:
            list: 跚由和处理类的元组列表
        """
        self.registery = OrderedDict()
        for rule in self.methods:
            self.route_(**rule)
        return [(k, v) for k, v in self.registery.items()]

    def is_werkzeug_route(self, route):
        """判断是否为werkzeug路由语法

        Args:
            route (str): 跷路由字符串

        Returns:
            bool: 是否为werkzeug路由
        """
        return _rule_re.match(route)

    def __call__(self, *args: tornado.ioloop.Any, **kwds: tornado.ioloop.Any) -> tornado.ioloop.Any:
        self.route(*args, **kwds)

    def route(self, rule, methods=None, werkzeug_route=None,
              tornado_route=None, handler_bases=None, fn=None, nowrap=None):
        """路由装饰器,用于注册处理函数

        Args:
            rule (str): 跷路由规则,支持werkzeug和tornado语法
            methods (list): HTTP方法列表,如['GET','POST']
            werkzeug_route (bool): 是否强制使用werkzeug路由
            tornado_route (bool): 是否强制使用tornado路由
            handler_bases (tuple): 处理器基类元组
            fn (callable): 处理函数
            nowrap (bool): 是否不包装处理函数

        Returns:
            function: 装饰器函数
        """
        def inner(fn):
            self.add_route(rule=rule,
                           methods=methods,
                           werkzeug_route=werkzeug_route,
                           tornado_route=tornado_route,
                           handler_bases=handler_bases,
                           fn=fn,
                           nowrap=nowrap)
            return fn
        return inner

    def add_route(self, rule, fn=None, methods=None,
                  werkzeug_route=None, tornado_route=None,
                  handler_bases=None, nowrap=None):
        """添加路由规则

        Args:
            rule (str): 跷路由规则
            fn (callable): 处理函数
            methods (list): HTTP方法列表
            werkzeug_route (bool): 是否使用werkzeug路由
            tornado_route (bool): 是否使用tornado路由
            handler_bases (tuple): 处理器基类
            nowrap (bool): 是否不包装处理函数
        """
        assert callable(fn)
        self.methods.append(dict(
            rule=rule,
            methods=methods,
            werkzeug_route=werkzeug_route,
            tornado_route=tornado_route,
            handler_bases=handler_bases,
            fn=fn,
            nowrap=nowrap
        ))

    def route_(self, rule, methods=None, werkzeug_route=None,
               tornado_route=None, handler_bases=None, fn=None, nowrap=None):
        """实际的路由注册逻辑

        Args:
            rule (str): 跷路由规则
            methods (list): HTTP方法列表
            werkzeug_route (bool): 是否使用werkzeug路由
            tornado_route (bool): 是否使用tornado路由
            handler_bases (tuple): 处理器基类
            fn (callable): 处理函数
            nowrap (bool): 是否不包装处理函数
        """
        methods = methods or ['GET']

        clsname = '%sHandler' % fn.__name__.capitalize()
        # TODO: things get complicated if you use your own base class and debug=True
        if not handler_bases:
            if self.debug:
                bases = (DebuggableHandler,)
            else:
                bases = (tornado.web.RequestHandler,)
        else:
            bases = (DebuggableHandler,) + handler_bases
        m = {}
        for method in methods:
            inspected = inspect.getfullargspec(fn)

            can_be_wrapped = True
            if nowrap == None:
                # are we using a tornado.coroutine or something similar,
                # we dont wrap
                if 'tornado' in inspect.getsourcefile(fn):
                    can_be_wrapped = False
                else:
                    can_be_wrapped = nowrap != True
            else:
                can_be_wrapped = nowrap

            self_in_args = inspected.args and inspected.args[0] in [
                'self', 'handler']

            if not self_in_args and can_be_wrapped == True:
                def wrapper(self, *args, **kwargs):
                    result = fn(*args, **kwargs)  # 调用原始处理函数

                    # 检查返回值是否为Stream类型
                    if isinstance(result, Stream):
                        # 渲染streams.html模板，并传递streams参数
                        # self.finish(result.name)
                        result = render_template('./templates/streams.html', streams=[result])

                    # 处理其他返回值
                    if isinstance(result, TemplateProxy):
                        if self._template_engine == 'tornado':
                            self.render(*result.args, **result.kwargs)
                        else:
                            template = self._template_env.get_template(result.args[0])
                            self.finish(template.render(handler=self, **result.kwargs))
                    else:
                        self.finish(result)

                m[method.lower()] = wrapper
            else:
                m[method.lower()] = fn

        klass = type(clsname, bases, m)
        klass._template_engine = self.template_engine
        if self.template_engine != 'tornado':
            klass._template_env = self.template_env

        use_werkzeug_route = None

        if tornado_route:
            use_werkzeug_route = False

        if werkzeug_route:
            use_werkzeug_route = True

        if use_werkzeug_route == None:
            use_werkzeug_route = self.is_werkzeug_route(rule)

        if use_werkzeug_route:
            r = Rule(rule, methods=methods)
            self.url_map.add(r)
            r.compile()
            pattern = r._regex.pattern.replace('^\\|', "")
            self.registery[pattern] = klass
        else:
            self.registery[rule] = klass

    def add_routes(self, routes_list):
        """添加路由列表

        Args:
            routes_list (list): 跷路由规则列表
        """
        self.routes_list = routes_list

    def run(self, port=9999, host="127.0.0.1", **settings):
        """启动HTTP服务器

        Args:
            port (int): 监听端口,默认9999
            host (str): 监听地址,默认127.0.0.1
            **settings: 其他设置参数

        Returns:
            Application: tornado应用实例
        """
        self.debug = settings.get('debug', False)
        settings['template_path'] = settings.get('template_path') or self.template_path
        if self.debug:
            if with_wsgi_adapter:
                import tornado.httpserver
                from werkzeug.debug import DebuggedApplication
                application = DebugApplication(
                    self.get_routes() + self.routes_list, **settings)
                wsgi_application = tornado.wsgi.WSGIAdapter(application)

                debug_app = DebuggedApplication(app=wsgi_application, evalex=True)
                application.debug_app = debug_app
                debug_container = tornado.wsgi.WSGIContainer(debug_app)

                http_server = tornado.httpserver.HTTPServer(debug_container)
                http_server.listen(port)
                # tornado.ioloop.IOLoop.instance().start()
            else:
                import tornado.ioloop
                application = DebugApplication(
                    self.get_routes() + self.routes_list, **settings)
                application.listen(port, host)
                # tornado.ioloop.IOLoop.instance().start()
        else:
            import tornado.web
            application = tornado.web.Application(
                self.get_routes() + self.routes_list, **settings)
            logger.info("starting server on port: %s", port)
            application.listen(port, host)
            os.system(f'open http://{host}:{port}')

        return application
        # tornado.ioloop.IOLoop.instance().start()


class StreamsConnection(SockJSConnection):
    """WebSocket连接处理类

    处理WebSocket连接的建立、消息收发和关闭
    """

    def __init__(self, *args, **kwargs):
        """初始化连接

        创建输入输出流并建立连接
        """
        self._out_stream = Stream()
        self.link1 = self._out_stream.sink(self.send)
        self._in_stream = Stream()
        self.link2 = self._in_stream.sink(self.process_msg)
        super(StreamsConnection, self).__init__(*args, **kwargs)

    def on_open(self, request):
        """处理连接打开

        Args:
            request: HTTP请求对象
        """
        self.out_stream = Stream()  # name='default')
        self.connection = self.out_stream >> self._out_stream
        json.dumps({'id': 'default', 'html': 'welcome'}) >> self.out_stream
        self.request = request
        self.request.ip = maybe(self.request.headers)[
            'x-forward-for'].or_else(self.request.ip)

        f'open:{self.request.ip}:{datetime.datetime.now()}' >> log

    @gen.coroutine
    def on_message(self, msg):
        """处理收到的消息

        Args:
            msg (str): 收到的消息
        """
        json.loads(msg) >> self._in_stream

    def process_msg(self, msg):
        """处理消息

        Args:
            msg (dict): 消息内容
        """
        stream_ids = msg['stream_ids']

        'view:%s:%s:%s' % (stream_ids, self.request.ip,
                           datetime.datetime.now()) >> log
        # gen.sleep(10)##只有这里的操作都类似gensleep一样是异步操作时,
        # 整个请求才能异步,某个用户超时才不会影响别的用户,否则一个用户影响其他用户
        # io的东西走异步,其余的函数如果是cpu计算,不要走异步

        self.out_streams = [stream for stream in Stream.instances() if
                            str(hash(stream)) in stream_ids]

        def _(sid):
            return lambda x: json.dumps({'id': sid, 'html': x})

        self.connections = set()
        for s in self.out_streams:
            sid = str(hash(s))
            f = _(sid)
            self.connections.add(s.map(repr).map(f) >> self._out_stream)

            html = maybe(s).recent(1)[0].or_else('流内暂无数据')
            # html = '等待数据加载。。。。'
            json.dumps({'id': sid, 'html': html}) >> self._out_stream

    def on_close(self):
        """处理连接关闭"""
        f'close:{self.request.ip}:{datetime.datetime.now()}' >> log
        for connection in self.connections:
            connection.destroy()

        self.connections = set()
        self.connection.destroy()
        self.link1.destroy()
        self.link2.destroy()
        self.out_stream.destroy()


page = Page()


class PageServer(object):
    """页面服务器类,用于启动和管理Web服务器

    主要功能:
    - 启动Tornado Web服务器
    - 管理页面路由
    - 处理WebSocket连接
    - 管理数据流

    参数:
        name (str): 服务器名称,默认为'default'
        host (str): 监听的主机地址,默认为'127.0.0.1'
        port (int): 监听的端口号,默认为9999
        start (bool): 是否立即启动服务器,默认为False
        **kwargs: 传递给tornado.web.Application的额外参数
    """
    page = page

    def __init__(self, name='default', host='127.0.0.1', port=9999, start=False, **kwargs):
        self.name = name
        self.page = page
        self.port = port
        self.host = host
        self.streams = defaultdict(list)
        self.page.get_routes() >> ls >> log
        self.StreamRouter = SockJSRouter(StreamsConnection, r'')
        self.application = tornado.web.Application(
            self.page.get_routes() +
            self.StreamRouter.urls,
            **kwargs
        )
        if start:
            self.start()

    def add_page(self, page):
        """添加新的页面路由

        Args:
            page: Page实例,包含要添加的路由
        """
        self.application.add_handlers('.*$', page.get_routes())

    def start(self,):
        """启动Web服务器并在浏览器中打开"""
        self.server = self.application.listen(self.port)
        os.system(f'open http://{self.host}:{self.port}/')

    def stop(self):
        """停止Web服务器"""
        self.server.stop()


def webview(s, url='/', server=None):
    """为数据流创建Web视图

    为数据流创建一个Web页面视图,可以在浏览器中实时查看数据流的内容。
    支持多个数据流在同一个页面展示,也可以为不同数据流创建不同的URL路径。

    Args:
        s: 要展示的数据流对象,可以是任意Stream实例
        url (str): 视图的URL路径,默认为'/',如果不以'/'开头会自动添加
        server: PageServer实例,如果为None则创建新的服务器实例

    Returns:
        PageServer: 返回服务器实例对象

    Example::

        # 创建一个简单的数据流
        s = timer(interval=1, func=lambda: datetime.now())

        # 在默认路径'/'展示
        s.webview()

        # 指定URL路径
        s.webview('/timer')

        # 多个数据流展示在同一页面
        s1 = from_list([1,2,3])
        s2 = from_list(['a','b','c']) 
        server = s1.webview('/data')
        s2.webview('/data', server=server)

        # 不同数据流使用不同URL
        s1.webview('/numbers')
        s2.webview('/letters')
    """
    url = url if url.startswith('/') else '/'+url
    server = server or NW('stream_webview')
    server.streams[url].append(s)

    page.route(url)(lambda: render_template(
        './templates/streams.html', streams=server.streams[url]))
    server.add_page(page)
    print('start webview:', 'http://'+server.host+':'+str(server.port)+url)
    print('with these streams:', server.streams[url])
    return server


Stream.webview = webview

if __name__ == '__main__':

    @page.route('/')
    def index():
        return log
        # return 'hello'

    @page.route('/s')
    def my_log():
        return 'hello world'

    ps = PageServer()
    ps.start()
    Deva.run()
