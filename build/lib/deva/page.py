from collections import defaultdict
"""
    webview
    ~~~~~~~~~

    example::

        from deva.page import page,PageServer,render_template
        from deva import *

        s = from_textfile('/var/log/systemf.log')
        s1 =s.sliding_window(5).map(concat('<br>'),name='system.log')
        s.start()

        def sample_df_html(n=5):
            return NB('sample')['df'].sample(n).to_html()

        s2 = timer(func=sample_df_html,start=True,name='每秒更新',interval=1)
        s3 = timer(func=sample_df_html,start=True,name='每三秒更新',interval=3)

        @page.route('/')
        def get():
            streams = [s1,s2,s3]
            return render_template('./templates/streams.html', streams=streams)


        ps = PageServer()
        ps.start()

    debug interface stolen from: https://gist.github.com/rduplain/4983839
"""

import tornado.ioloop
import tornado.web
import tornado.wsgi
import contextlib
from functools import partial
from werkzeug.routing import Map, Rule, _rule_re
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
from .core import Stream
from .bus import log
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

    """

    Example usage::

        from deva.page import Page

        page = Page(debug=True)

        @app.route("/hello")
        def foo():
            return "hello"

    :param debug: enables werkzeug debugger
    :param template_path: we normally look for template in ./templates folder of your app.py
                          you can explicitly set for some other template path
    """

    def __init__(self, debug=False, template_path=None, template_engine='tornado'):
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
        """
        returns our compiled routes and classes as a list to be used in tornado
        """
        self.registery = OrderedDict()
        for rule in self.methods:
            self.route_(**rule)
        return [(k, v) for k, v in self.registery.items()]

    def is_werkzeug_route(self, route):
        """
        does it look like a werkzeug route or direct reg exp. of
        tornado.
        """
        return _rule_re.match(route)

    def route(self, rule, methods=None, werkzeug_route=None, tornado_route=None, handler_bases=None, nowrap=None):
        """
        our super handy dandy routing function, usually you create an application,
        and decorate your functions so they become RequestHandlers::

                    app = App()

                    @app.route("/hello")
                    def hello():
                        return "foo"

        :param rule: this can be either a werkzeug route or a reg.expression as in tornado.
                     we try to understand the type of it automatically - wheter werkzeug or reg.exp. -
                     this by checking with a regexp. If it is a werkzeug route, we simply get the compiled
                     reg. exp from werkzeug and pass it to tornado handlers.

        :param methods: methods can be a combination of ['GET', 'POST', 'HEAD', 'PUT'...]
                        any http verb that tornado accepts. Behind the scenes we create a class
                        and attach these methods.

                        for example something like::

                            class HelloHandler(tornado.web.RequestHandler):
                                def get(self):


        :param werkzeug_route: we explicitly tell that this is a werkzeug route, in case auto detection fails.
        :param tornado_route: we explicitly tell that this is a tornado reg. exp. route
        :param handler_bases: for debug we create DebuggableHandler, and for normal operations we create
                                tornado.web.RequestHandler but in case you want to use your own classes for request
                                handling, you can pass it with handler_bases parameter. So behind the scenes this::

                                    @route("/foo", handler_bases=(MyHandler,))
                                    def foo():
                                        pass

                                becomes this::

                                    class HelloHandler(MyHandler):
                                        def get(self):
                                            ...

                                if you set a base class for your FooHandler, in debug mode we'll add DebuggableHandler in between
                                handler.__class__.__mro__
                                (<class 'tornado_smack.app.FooHandler'>, <class 'tornado_smack.app.DebuggableHandler'>, <class '__main__.MyBaseHandler'>, <class 'tornado.web.RequestHandler'>, <type 'object'>)


        :param nowrap: if you add use self - or handler - as your first parameter::

                            @route('/foo')
                            def foo(self):
                                self.write("hello")

                        if becomes something like this::

                            class HelloHandler(tornado.web.RequestHandler):
                                def get(self):
                                    self.write("hello")

                        if you omit self as your first parameter::

                            @route('/foo')
                            def foo():
                                return "hello"

                        we implicitly wrap foo so it becomes something like this::

                            class HelloHandler(tornado.web.RequestHandler):
                                def get(self, *args, **kwargs):
                                    def wrapper(*args, **kwargs):
                                        return foo(*args, **kwargs)
                                    wrapper(*args, **kwargs)

                        in case you want to use some other name for your first parameter,
                        or for some other reason you can explicitly say don't wrap.

                        in case you are using tornado.coroutine or some other tornado decorator,
                        we don't wrap your function - because simply it won't work. so this::

                            @route('/foo')
                            @coroutine
                            def foo():
                                ...

                        will give you an error.

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
        if not methods:
            methods = ['GET']

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
            inspected = inspect.getargspec(fn)

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
                    # with StackContext(functools.partial(ctx_man, self)) as cm:
                    w = fn  # wrap(fn)
                    result = w(*args, **kwargs)

                    if isinstance(result, TemplateProxy):
                        if self._template_engine == 'tornado':
                            self.render(*result.args, **result.kwargs)
                        else:
                            template = self._template_env.get_template(
                                result.args[0])
                            self.finish(template.render(
                                handler=self, **result.kwargs))
                    else:
                        self.finish(result)

                    # import gc
                    # # gc.collect()
                    # print "is gc enabled", gc.isenabled()
                    # print "-----------------"
                    # for obj in gc.get_objects():
                    #     if isinstance(obj, DebuggableHandler):
                    #         print ">>>", type(obj), "<<<"
                    #
                    # print "-----------------"

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
        self.routes_list = routes_list

    def run(self, port=9999, host="127.0.0.1", **settings):
        self.debug = settings.get('debug', False)
        template_path = settings.get('template_path')
        if not template_path:
            settings['template_path'] = self.template_path
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

    def __init__(self, *args, **kwargs):
        self._out_stream = Stream()
        self.link1 = self._out_stream.sink(self.send)
        self._in_stream = Stream()
        self.link2 = self._in_stream.sink(self.process_msg)
        super(StreamsConnection, self).__init__(*args, **kwargs)

    def on_open(self, request):
        self.out_stream = Stream()  # name='default')
        self.connection = self.out_stream >> self._out_stream
        json.dumps({'id': 'default', 'html': 'welcome'}) >> self.out_stream
        self.request = request
        self.request.ip = maybe(self.request.headers)[
            'x-forward-for'].or_else(self.request.ip)

        f'open:{self.request.ip}:{datetime.datetime.now()}' >> log

    @gen.coroutine
    def on_message(self, msg):
        json.loads(msg) >> self._in_stream

    def process_msg(self, msg):
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
    page = page

    def __init__(self, name='default', host='127.0.0.1', port=9999, start=False):
        self.name = name
        self.page = page
        self.port = port
        self.host = host
        self.streams = defaultdict(list)
        self.page.get_routes() >> ls >> log
        self.StreamRouter = SockJSRouter(StreamsConnection, r'')
        self.application = tornado.web.Application(
            self.page.get_routes() +
            self.StreamRouter.urls
        )
        if start:
            self.start()

    def add_page(self, page):
        self.application.add_handlers('.*$', page.get_routes())

    def start(self,):
        self.server = self.application.listen(self.port)
        os.system(f'open http://{self.host}:{self.port}/')

    def close(self):
        self.server.close()


def webview(s, url='/', server=None):
    if not url.startswith('/'):
        url = '/'+url
    if not server:
        server = NW('stream_webview')
    server.streams[url].append(s)

    page.route(url)(lambda: render_template(
        './templates/streams.html', streams=server.streams[url]))
    server.add_page(page)
    print('start webview:', 'http://'+server.host+':'+str(server.port)+url)
    print('with these streams:', server.streams[url])


Stream.webview = webview
