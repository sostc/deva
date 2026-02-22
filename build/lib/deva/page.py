"""页面视图模块外观层。

实现已拆分到 `deva.page_parts.*`，此模块保持历史 API 兼容。
"""

from deva.core import Deva, Stream
from deva.bus import log
from deva.namespace import NB
from deva.pipe import ls

from .page_parts import (
    DebugApplication,
    DebuggableHandler,
    Page,
    PageServer,
    StreamsConnection,
    TemplateProxy,
    render_template,
)
from .page_parts.debug import ctx_man, get_current_traceback, handler
from .page_parts import stream_views as _stream_views


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


if __name__ == '__main__':
    @page.route('/')
    def get():
        streams = [stream for stream in Stream.instances() if stream.name]
        tables = NB('default').tables | ls
        return render_template('./templates/monitor.html', streams=streams, tablenames=tables)

    @page.route('/s')
    def my_log():
        return log

    log.webview('/log')
    Deva.run()
