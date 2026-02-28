"""Connections, server and routing (merged from connections.py, server.py, routing.py)."""

import inspect
import os
import re
import time
import threading
from collections import OrderedDict, defaultdict
import datetime
import json
import asyncio

import tornado.web
from tornado.ioloop import IOLoop
from tornado.iostream import StreamClosedError
from tornado.websocket import WebSocketClosedError
from pymaybe import maybe
from sockjs.tornado import SockJSRouter, SockJSConnection
from tornado import gen

from deva.core.bus import log
from deva.core import Stream

from .rendering import DebuggableHandler, TemplateProxy, render_template


def _is_ws_close_race(context):
    exc = context.get("exception")
    if not isinstance(exc, (WebSocketClosedError, StreamClosedError)):
        return False
    fut = context.get("future")
    if fut is None:
        return False
    coro = getattr(fut, "get_coro", lambda: None)()
    qualname = getattr(coro, "__qualname__", "")
    return "write_message" in qualname


def _install_asyncio_ws_close_filter():
    io_loop = IOLoop.current(instance=False)
    async_loop = getattr(io_loop, "asyncio_loop", None)
    if async_loop is None:
        try:
            async_loop = asyncio.get_running_loop()
        except RuntimeError:
            return
    if getattr(async_loop, "_deva_ws_close_filter_installed", False):
        return

    previous = async_loop.get_exception_handler()

    def _handler(loop, context):
        if _is_ws_close_race(context):
            return
        if previous is not None:
            previous(loop, context)
        else:
            loop.default_exception_handler(context)

    async_loop.set_exception_handler(_handler)
    async_loop._deva_ws_close_filter_installed = True


# ---- StreamsConnection (from connections.py) ----
class StreamsConnection(SockJSConnection):
    # 连接管理相关配置
    MAX_CONNECTIONS_PER_IP = 10  # 每个IP最大连接数
    CONNECTION_TIMEOUT = 30  # 连接超时时间(秒)
    
    # 全局连接计数器，用于限制并发连接数
    _active_connections = 0
    _connections_per_ip = defaultdict(int)
    _connection_lock = threading.RLock()
    
    def __init__(self, *args, **kwargs):
        self._out_stream = Stream()
        self._closed = False
        self.link1 = self._out_stream.sink(self._safe_send)
        self._in_stream = Stream()
        self.link2 = self._in_stream.sink(self.process_msg)
        self.connections = set()
        self.connection = None
        self.out_stream = None
        self.connection_time = time.time()
        self.stream_cache = {}
        self.cache_timestamp = 0
        self.cache_interval = 5  # 缓存有效期(秒)
        super(StreamsConnection, self).__init__(*args, **kwargs)

    def _safe_send(self, payload):
        if self._closed:
            return
        try:
            # 确保在正确的事件循环中执行发送操作
            from deva.core.utils.ioloop import get_io_loop
            loop = get_io_loop(asynchronous=False)
            if loop is not None:
                loop.add_callback(lambda p=payload: self.send(p))
            else:
                self.send(payload)
        except (WebSocketClosedError, StreamClosedError):
            self._closed = True

    def on_open(self, request):
        # 检查连接限制
        self.request = request
        self.request.ip = maybe(self.request.headers)["x-forward-for"].or_else(self.request.ip)
        
        with self._connection_lock:
            # 检查每个IP的连接数限制
            if self._connections_per_ip.get(self.request.ip, 0) >= self.MAX_CONNECTIONS_PER_IP:
                f"reject:{self.request.ip}:{datetime.datetime.now()}:connection_limit_exceeded" >> log
                self.close()
                return
            
            # 增加连接计数
            self._connections_per_ip[self.request.ip] += 1
            self._active_connections += 1
        
        self._closed = False
        self.out_stream = Stream()
        self.connection = self.out_stream >> self._out_stream
        json.dumps({"id": "default", "html": "welcome"}) >> self.out_stream
        f"open:{self.request.ip}:{datetime.datetime.now()}:{self._active_connections}" >> log

    @gen.coroutine
    def on_message(self, msg):
        json.loads(msg) >> self._in_stream

    def get_streams(self):
        """获取所有流实例，使用缓存减少开销"""
        current_time = time.time()
        if current_time - self.cache_timestamp < self.cache_interval and self.stream_cache:
            return self.stream_cache
        
        # 重新获取并缓存
        self.stream_cache = {str(hash(stream)): stream for stream in Stream.instances()}
        self.cache_timestamp = current_time
        return self.stream_cache
    
    def process_msg(self, msg):
        # Backward-compatible payload handling:
        # - new pages send {"stream_ids": ["..."]}
        # - legacy page sends {"stream_id": "..."}
        stream_ids = msg.get("stream_ids", [])
        if not stream_ids and "stream_id" in msg:
            stream_ids = [str(msg.get("stream_id"))]
        "view:%s:%s:%s" % (stream_ids, self.request.ip, datetime.datetime.now()) >> log
        
        # 使用缓存的流实例，避免每次都遍历所有流
        streams = self.get_streams()
        self.out_streams = [streams[sid] for sid in stream_ids if sid in streams]

        def _(sid):
            return lambda x: json.dumps({"id": sid, "html": x, "stream_id": sid, "data": x})

        for connection in self.connections:
            connection.destroy()
        self.connections = set()
        for s in self.out_streams:
            sid = str(hash(s))
            f = _(sid)
            self.connections.add(s.map(repr).map(f) >> self._out_stream)
            html = maybe(s).recent(1)[0].or_else("流内暂无数据")
            json.dumps({"id": sid, "html": html, "stream_id": sid, "data": html}) >> self._out_stream

    def on_close(self):
        self._closed = True
        request = getattr(self, "request", None)
        ip = getattr(request, "ip", "unknown")
        
        # 减少连接计数
        with self._connection_lock:
            if ip != "unknown" and ip in self._connections_per_ip:
                self._connections_per_ip[ip] = max(0, self._connections_per_ip[ip] - 1)
                if self._connections_per_ip[ip] == 0:
                    del self._connections_per_ip[ip]
            self._active_connections = max(0, self._active_connections - 1)
        
        f"close:{ip}:{datetime.datetime.now()}:{self._active_connections}" >> log
        for connection in self.connections:
            connection.destroy()
        self.connections = set()
        if self.connection is not None:
            self.connection.destroy()
        self.link1.destroy()
        self.link2.destroy()
        if self.out_stream is not None:
            self.out_stream.destroy()


# ---- PageServer (from server.py) ----
class PageServer(object):
    def __init__(self, name="default", host="127.0.0.1", port=9999, start=False, sockjs_prefix="/sockjs", **kwargs):
        self.name = name
        self.port = port
        self.host = host
        self.streams = defaultdict(list)
        self.sockjs_prefix = sockjs_prefix.rstrip('/') if sockjs_prefix else ""
        self.StreamRouter = SockJSRouter(StreamsConnection, self.sockjs_prefix)
        self.application = tornado.web.Application(self.StreamRouter.urls, **kwargs)
        _install_asyncio_ws_close_filter()
        if start:
            self.start()

    def add_page(self, page):
        self.application.add_handlers(".*$", page.get_routes())

    def start(self):
        self.server = self.application.listen(self.port)
        os.system(f"open http://{self.host}:{self.port}/")

    def stop(self):
        self.server.stop()


# ---- Page routing (from routing.py) ----
_route_param_re = re.compile(
    r"<(?:(?P<converter>[a-zA-Z_][a-zA-Z0-9_]*)\:)?(?P<variable>[a-zA-Z_][a-zA-Z0-9_]*)>"
)


def _converter_regex(converter):
    converter = (converter or "string").lower()
    if converter == "int":
        return r"\d+"
    if converter == "float":
        return r"\d+(?:\.\d+)?"
    if converter == "path":
        return r".+"
    return r"[^/]+"


def _compile_rule(rule):
    if "<" not in rule:
        return rule

    parts = []
    last = 0
    for match in _route_param_re.finditer(rule):
        parts.append(re.escape(rule[last:match.start()]))
        name = match.group("variable")
        pattern = _converter_regex(match.group("converter"))
        parts.append(f"(?P<{name}>{pattern})")
        last = match.end()
    parts.append(re.escape(rule[last:]))
    return "^" + "".join(parts) + "$"


class Page(object):
    def __init__(self, debug=False, template_path=None, template_engine="tornado"):
        assert template_engine in ("tornado", "jinja2")
        self.registery = OrderedDict()
        self.debug = bool(debug)
        self.methods = []

        if not template_path:
            frame = inspect.currentframe()
            while frame and frame.f_code.co_filename == __file__:
                frame = frame.f_back
            filename = frame.f_code.co_filename if frame else __file__
            self.template_path = os.path.join(os.path.dirname(filename), "templates")
        else:
            self.template_path = template_path

        self.template_engine = template_engine
        if template_engine == "jinja2":
            from jinja2 import Environment, FileSystemLoader
            self.template_env = Environment(loader=FileSystemLoader(self.template_path))

    def get_routes(self):
        self.registery = OrderedDict()
        for rule in self.methods:
            self.route_(**rule)
        return list(self.registery.items())

    def __call__(self, *args, **kwargs):
        return self.route(*args, **kwargs)

    def route(self, rule, methods=None, **kwargs):
        def decorator(fn):
            self.add_route(rule=rule, methods=methods, fn=fn, **kwargs)
            return fn
        return decorator

    def add_route(self, rule, fn, methods=None, **kwargs):
        assert callable(fn)
        self.methods.append(dict(rule=rule, methods=methods, fn=fn, **kwargs))

    def _create_handler_class(self, fn, methods, bases):
        clsname = f"{fn.__name__.capitalize()}Handler"
        m = {}
        inspected = inspect.getfullargspec(fn)
        self_in_args = inspected.args and inspected.args[0] in ["self", "handler"]
        for method in methods:
            if not self_in_args:
                def wrapper(self, *args, **kwargs):
                    result = fn(*args, **kwargs)
                    if isinstance(result, Stream):
                        result = render_template("./templates/streams.html", streams=[result])
                    if isinstance(result, TemplateProxy):
                        if self._template_engine == "tornado":
                            self.render(*result.args, **result.kwargs)
                        else:
                            template = self._template_env.get_template(result.args[0])
                            self.finish(template.render(handler=self, **result.kwargs))
                    else:
                        self.finish(result)
                m[method.lower()] = wrapper
            else:
                m[method.lower()] = fn
        return type(clsname, bases, m)

    def route_(self, rule, methods=None, fn=None, **kwargs):
        methods = methods or ["GET"]
        bases = (DebuggableHandler,) if self.debug else (tornado.web.RequestHandler,)
        klass = self._create_handler_class(fn, methods, bases)
        klass._template_engine = self.template_engine
        if self.template_engine != "tornado":
            klass._template_env = self.template_env

        use_dynamic = kwargs.get("werkzeug_route", "<" in rule and ">" in rule)
        pattern = _compile_rule(rule) if use_dynamic else rule
        self.registery[pattern] = klass

    def add_routes(self, routes_list):
        for route in routes_list:
            self.add_route(**route)
