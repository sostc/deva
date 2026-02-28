import asyncio

from deva.core.bus import log, warn
from deva.core import Stream
from deva.core.namespace import NW

from .rendering import render_template


def webview(s, page, url="/", server=None):
    url = url if url.startswith("/") else "/" + url
    server = server or NW("stream_webview")
    server.streams[url].append(s)
    sockjs_prefix = getattr(server, 'sockjs_prefix', '')
    page.route(url)(lambda: render_template("./templates/streams.html", streams=server.streams[url], sockjs_prefix=sockjs_prefix))
    server.add_page(page)
    {
        "level": "INFO",
        "source": "deva.page",
        "message": "start webview",
        "url": "http://" + server.host + ":" + str(server.port) + url,
    } >> log
    return server


def sse_view(stream, url, server=None):
    from tornado.escape import json_encode
    from tornado.web import RequestHandler

    class SSEHandler(RequestHandler):
        stream = None

        async def get(self):
            self.set_header("Content-Type", "text/event-stream")
            self.set_header("Cache-Control", "no-cache")
            self.set_header("Connection", "keep-alive")

            def write_to_sse(data):
                try:
                    # 确保在正确的事件循环中执行操作
                    from deva.core.utils.ioloop import get_io_loop
                    loop = get_io_loop(asynchronous=False)
                    
                    def do_write(data):
                        try:
                            # Handle pandas DataFrame objects by converting them to a serializable format
                            import pandas as pd
                            if isinstance(data, pd.DataFrame):
                                # Convert DataFrame to JSON-serializable format
                                data = {
                                    'type': 'dataframe',
                                    'data': data.to_dict('records'),
                                    'columns': list(data.columns),
                                    'shape': data.shape
                                }
                            elif isinstance(data, pd.Series):
                                # Convert Series to JSON-serializable format
                                data = {
                                    'type': 'series',
                                    'data': data.to_dict(),
                                    'name': data.name
                                }
                            
                            self.write(f"data: {json_encode(data)}\n\n")
                            self.flush()
                        except Exception as e:
                            {
                                "level": "WARNING",
                                "source": "deva.page",
                                "message": "sse write failed",
                                "error": str(e),
                            } >> warn
                    
                    if loop is not None:
                        loop.add_callback(do_write, data)
                    else:
                        do_write(data)
                except Exception as e:
                    {
                        "level": "WARNING",
                        "source": "deva.page",
                        "message": "sse write failed",
                        "error": str(e),
                    } >> warn

            sink = SSEHandler.stream.sink(write_to_sse)
            while not self.request.connection.stream.closed():
                await asyncio.sleep(1)
            sink.destroy()

    url = url if url.startswith("/") else "/" + url
    server = server or NW("stream_webview")
    SSEHandler.stream = stream
    server.application.add_handlers(".*$", [(url, SSEHandler)])
    return stream


def attach_stream_methods(page):
    def _webview(s, url="/", server=None):
        return webview(s, page=page, url=url, server=server)

    def _sse_view(s, url, server=None):
        return sse_view(s, url=url, server=server)

    Stream.webview = _webview
    Stream.sse = _sse_view
