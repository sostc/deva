import contextlib
from functools import partial

import tornado.web
import tornado.wsgi
from werkzeug.local import LocalProxy, LocalStack


try:
    from tornado.wsgi import WSGIAdapter
except Exception:
    with_wsgi_adapter = False
else:
    with_wsgi_adapter = True


def _lookup_handler_object(name):
    top = _handler_ctx_stack.top
    if top is None:
        raise RuntimeError("working outside of request context")
    return top


_handler_ctx_stack = LocalStack()

handler = LocalProxy(partial(_lookup_handler_object, "handler"))


@contextlib.contextmanager
def ctx_man(ctx):
    _handler_ctx_stack.push(ctx)
    yield
    _handler_ctx_stack.pop()


def get_current_traceback():
    from werkzeug.debug.tbtools import get_current_traceback as _get_current_traceback

    return _get_current_traceback(
        skip=2,
        show_hidden_frames=False,
        ignore_system_exceptions=True,
    )


class DebuggableHandler(tornado.web.RequestHandler):
    def write_error(self, status_code, **kwargs):
        self.finish(self.get_debugger_html(status_code, **kwargs))

    def get_debugger_html(self, status_code, **kwargs):
        assert isinstance(self.application, DebugApplication)
        traceback = self.application.get_current_traceback()
        keywords = self.application.get_traceback_renderer_keywords()
        html = traceback.render_full(**keywords).encode("utf-8", "replace")
        return html.replace(b"WSGI", b"tornado")


class DebugApplication(tornado.web.Application):
    def get_current_traceback(self):
        traceback = get_current_traceback()
        for frame in traceback.frames:
            self.debug_app.frames[frame.id] = frame
        self.debug_app.tracebacks[traceback.id] = traceback
        return traceback

    def get_traceback_renderer_keywords(self):
        return dict(evalex=self.debug_app.evalex, secret=self.debug_app.secret)

    if not with_wsgi_adapter:
        def __init__(self, *args, **kwargs):
            from werkzeug.debug import DebuggedApplication

            self.debug_app = DebuggedApplication(app=self, evalex=True)
            self.debug_container = tornado.wsgi.WSGIContainer(self.debug_app)
            super(DebugApplication, self).__init__(*args, **kwargs)

        def __call__(self, request):
            if "__debugger__" in request.uri:
                return self.debug_container(request)
            return super(DebugApplication, self).__call__(request)

        @classmethod
        def debug_wsgi_app(cls, environ, start_response):
            status = "500 Internal Server Error"
            response_headers = [("Content-type", "text/plain")]
            start_response(status, response_headers)
            return ["Failed to load debugger.\n"]
