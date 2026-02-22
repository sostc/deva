"""Monitor-style HTTP routes implemented under admin architecture."""

from __future__ import annotations

import json

from tornado.escape import url_escape, xhtml_escape
from tornado.web import RequestHandler


class MonitorHomeHandler(RequestHandler):
    def initialize(self, *, ctx):
        self.ctx = ctx

    def get(self):
        streams = [s for s in self.ctx["Stream"].instances() if getattr(s, "name", None)]
        tables = list(self.ctx["NB"]("default").tables)

        stream_items = []
        for stream in streams:
            sid = str(hash(stream))
            name = xhtml_escape(stream.name)
            stream_items.append(f'<li><a href="/stream/{sid}">{name}</a></li>')

        table_items = []
        for tablename in tables:
            esc = xhtml_escape(str(tablename))
            link = url_escape(str(tablename), plus=False)
            table_items.append(f'<li><a href="/table/{link}">{esc}</a></li>')

        html = (
            "<title>Deva Admin Monitor</title>"
            "<h3>streams</h3>"
            f"<ul>{''.join(stream_items) or '<li>暂无流</li>'}</ul>"
            "<h3>tables</h3>"
            f"<ul>{''.join(table_items) or '<li>暂无表</li>'}</ul>"
            "<h3>执行代码</h3>"
            "<form method='post' action='/monitor/exec'>"
            "<input type='text' name='command' placeholder='例如: 1+1 或 a=1' style='width:360px'>"
            "<button type='submit'>执行</button>"
            "</form>"
            "<h3>links</h3>"
            "<ul>"
            '<li><a href="/allstreams">allstreams</a></li>'
            '<li><a href="/alltables">alltables</a></li>'
            '<li><a href="/">admin首页</a></li>'
            "</ul>"
        )
        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.finish(html)


class MonitorAllStreamsHandler(RequestHandler):
    def initialize(self, *, ctx):
        self.ctx = ctx

    def get(self):
        items = []
        for stream in self.ctx["Stream"].instances():
            text = xhtml_escape(str(stream))
            sid = str(hash(stream))
            items.append(f'<li><a href="/stream/{sid}">{text}</a></li>')
        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.finish("".join(items))


class MonitorAllTablesHandler(RequestHandler):
    def initialize(self, *, ctx):
        self.ctx = ctx

    def get(self):
        items = []
        for tablename in self.ctx["NB"]("default").tables:
            esc_name = xhtml_escape(str(tablename))
            link_name = url_escape(str(tablename), plus=False)
            items.append(f'<li><a class="Stream" href="/table/{link_name}">{esc_name}</a></li>')
        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.finish("".join(items))


class MonitorTableKeysHandler(RequestHandler):
    def initialize(self, *, ctx):
        self.ctx = ctx

    def get(self, tablename):
        try:
            table = self.ctx["NB"](tablename)
        except Exception:
            self.set_status(404)
            return self.finish(f"table not found: {xhtml_escape(tablename)}")
        keys = self.ctx["sample"](20) << table.keys()
        items = []
        for key in keys:
            key_text = str(key)
            esc = xhtml_escape(key_text)
            link = url_escape(key_text, plus=False)
            tlink = url_escape(tablename, plus=False)
            items.append(f'<li><a class="Stream" href="/table/{tlink}/{link}">{esc}</a></li>')
        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.finish("".join(items))


class MonitorTableValueHandler(RequestHandler):
    def initialize(self, *, ctx):
        self.ctx = ctx

    def get(self, tablename, key):
        import pandas as pd

        try:
            data = self.ctx["NB"](tablename).get(key)
        except Exception:
            self.set_status(404)
            return self.finish(f"table not found: {xhtml_escape(tablename)}")
        if isinstance(data, list):
            rows = data[:250]
            return self.finish(json.dumps(pd.DataFrame(rows).to_dict(orient="records"), ensure_ascii=False))
        if isinstance(data, dict):
            return self.finish(json.dumps(data, ensure_ascii=False))
        if isinstance(data, pd.DataFrame):
            self.set_header("Content-Type", "text/html; charset=utf-8")
            return self.finish(data.head(250).to_html())
        return self.finish(json.dumps({key: str(data)}, ensure_ascii=False))


class MonitorStreamHandler(RequestHandler):
    def initialize(self, *, ctx):
        self.ctx = ctx

    def get(self, name_or_id):
        stream = None
        for s in self.ctx["Stream"].instances():
            if getattr(s, "name", None) == name_or_id or str(hash(s)) == name_or_id:
                stream = s
                break

        if stream is None:
            self.set_status(404)
            return self.finish(f"stream not found: {xhtml_escape(name_or_id)}")

        self.redirect(f"/{hash(stream)}")


class MonitorExecHandler(RequestHandler):
    def initialize(self, *, ctx):
        self.ctx = ctx

    def post(self):
        command = (self.get_body_argument("command", "") or "").strip()
        if not command:
            return self.finish("empty command")
        command >> self.ctx["log"]
        try:
            if "=" in command:
                var_name, expr = command.replace(" ", "").split("=", 1)
                self.ctx["global_ns"][var_name] = eval(expr, self.ctx["global_ns"])
                return self.finish(f"exec:{command}\n")
            answer = eval(command, self.ctx["global_ns"])
            return self.finish(f"{command}\n{answer}\n")
        except Exception as e:
            return self.finish(str(e))


def monitor_route_handlers(ctx):
    """Build monitor-compatible handlers for admin tornado app."""
    route_ctx = {
        "NB": ctx["NB"],
        "Stream": ctx["Stream"],
        "sample": ctx["sample"],
        "log": ctx["log"],
        "global_ns": ctx,
    }
    return [
        (r"/monitor", MonitorHomeHandler, {"ctx": route_ctx}),
        (r"/monitor/exec", MonitorExecHandler, {"ctx": route_ctx}),
        (r"/allstreams", MonitorAllStreamsHandler, {"ctx": route_ctx}),
        (r"/alltables", MonitorAllTablesHandler, {"ctx": route_ctx}),
        (r"/table/([^/]+)", MonitorTableKeysHandler, {"ctx": route_ctx}),
        (r"/table/([^/]+)/([^/]+)", MonitorTableValueHandler, {"ctx": route_ctx}),
        (r"/stream/([^/]+)", MonitorStreamHandler, {"ctx": route_ctx}),
    ]
