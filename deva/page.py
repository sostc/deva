"""页面视图模块外观层。实现位于 deva.page_ui，此模块保持历史 API 兼容。"""

from .page_ui import (
    DebugApplication,
    DebuggableHandler,
    Page,
    PageServer,
    StreamsConnection,
    TemplateProxy,
    render_template,
    ctx_man,
    get_current_traceback,
    handler,
)
from .page_ui import stream_views as _stream_views


page = Page()
_stream_views.attach_stream_methods(page)


def webview(s, url='/', server=None):
    return _stream_views.webview(s, page=page, url=url, server=server)


def sse_view(s, url, server=None):
    return _stream_views.sse_view(s, url=url, server=server)


__all__ = [
    'DebugApplication',
    'DebuggableHandler',
    'StreamsConnection',
    'TemplateProxy',
    'handler',
    'ctx_man',
    'get_current_traceback',
    'PageServer',
    'Page',
    'render_template',
    'webview',
    'sse_view',
    'page',
]
