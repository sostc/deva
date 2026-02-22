import inspect
import os
import re
from collections import OrderedDict

import tornado.web
from werkzeug.routing import Map, Rule

from deva.core import Stream

from .debug import DebuggableHandler
from .rendering import TemplateProxy, render_template


_rule_re = re.compile(
    r"""
    (?P<static>[^<]*)
    <
    (?:
        (?P<converter>[a-zA-Z_][a-zA-Z0-9_]*)
        (?:\((?P<args>.*?)\))?
        \:
    )?
    (?P<variable>[a-zA-Z_][a-zA-Z0-9_]*)
    >
    """,
    re.VERBOSE,
)


class Page(object):
    def __init__(self, debug=False, template_path=None, template_engine="tornado"):
        assert template_engine in ("tornado", "jinja2")
        self.registery = OrderedDict()
        self.url_map = Map()
        self.mapper = self.url_map.bind("", "/")
        self.debug = True
        self.methods = []
        self.routes_list = []

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

    def is_werkzeug_route(self, route):
        return _rule_re.match(route)

    def __call__(self, *args, **kwargs):
        self.route(*args, **kwargs)

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
        for method in methods:
            inspected = inspect.getfullargspec(fn)
            self_in_args = inspected.args and inspected.args[0] in ["self", "handler"]
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

        use_werkzeug = kwargs.get("werkzeug_route", self.is_werkzeug_route(rule))
        if use_werkzeug:
            r = Rule(rule, methods=methods)
            self.url_map.add(r)
            r.compile()
            pattern = r._regex.pattern.replace("^\\|", "")
            self.registery[pattern] = klass
        else:
            self.registery[rule] = klass

    def add_routes(self, routes_list):
        self.routes_list = routes_list
