"""Monitor-style HTTP routes implemented under admin architecture."""

from __future__ import annotations

import os

from tornado.escape import xhtml_escape
from tornado.template import Loader
from tornado.web import RequestHandler

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "page_ui", "templates")
_STREAMS_TEMPLATE = Loader(_TEMPLATE_DIR).load("streams.html")
_PRIMARY_TABS = [
    ("/dbadmin", "数据库"),
    ("/busadmin", "Bus"),
    ("/streamadmin", "命名流"),
    ("/strategyadmin", "策略"),
    ("/monitor", "监控"),
    ("/taskadmin", "任务"),
    ("/document", "文档"),
]


def _match_stream(ctx, name_or_id):
    for stream in ctx["Stream"].instances():
        if getattr(stream, "name", None) == name_or_id or str(hash(stream)) == str(name_or_id):
            return stream
    return None


def _render_stream_page(handler, stream):
    handler.set_header("Content-Type", "text/html; charset=utf-8")
    handler.finish(_STREAMS_TEMPLATE.generate(streams=[stream], sockjs_prefix=""))


def _render_page_shell(handler, title, body_html, primary_active="/monitor", subnav_html=""):
    tabs = []
    for path, label in _PRIMARY_TABS:
        cls = "tab active" if path == primary_active else "tab"
        tabs.append(f'<a class="{cls}" href="{path}">{label}</a>')
    html = (
        "<!doctype html>"
        "<html><head><meta charset='utf-8'>"
        f"<title>{xhtml_escape(title)}</title>"
        "<style>"
        "body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f7fb;color:#1f2937;}"
        ".top{position:sticky;top:0;z-index:20;background:#ffffff;border-bottom:1px solid #e5e7eb;padding:0 20px;}"
        ".tabs{display:flex;gap:8px;flex-wrap:wrap;padding:10px 0;}"
        ".tab{display:inline-block;padding:8px 12px;border-radius:8px;text-decoration:none;color:#334155;background:#eef2f7;}"
        ".tab.active{background:#111827;color:#fff;}"
        ".subnav{padding:0 0 10px 0;display:flex;gap:8px;flex-wrap:wrap;}"
        ".subnav a{display:inline-block;padding:6px 10px;border-radius:8px;background:#eef2f7;color:#334155;text-decoration:none;}"
        ".wrap{padding:20px;}"
        ".card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px;}"
        "ul{margin:8px 0 0 0;padding-left:18px;}"
        "a{color:#0f4aa1;text-decoration:none;}a:hover{text-decoration:underline;}"
        ".inline{display:flex;gap:8px;align-items:center;flex-wrap:wrap;}"
        ".code-input{min-width:320px;max-width:720px;width:100%;padding:8px;border-radius:8px;border:1px solid #cbd5e1;}"
        ".btn{padding:8px 12px;border:0;border-radius:8px;background:#111827;color:#fff;cursor:pointer;}"
        ".section{margin-top:16px;}"
        ".stream-frame{width:100%;height:calc(100vh - 170px);border:1px solid #e5e7eb;border-radius:12px;background:#fff;}"
        "</style></head><body>"
        "<div class='top'>"
        f"<div class='tabs'>{''.join(tabs)}</div>"
        f"<div class='subnav'>{subnav_html}</div>"
        "</div>"
        f"<div class='wrap'>{body_html}</div>"
        "</body></html>"
    )
    handler.set_header("Content-Type", "text/html; charset=utf-8")
    handler.finish(html)


class MonitorHomeHandler(RequestHandler):
    def initialize(self, *, ctx):
        self.ctx = ctx

    def get(self):
        streams = [s for s in self.ctx["Stream"].instances() if getattr(s, "name", None)]

        stream_items = []
        for stream in streams:
            sid = str(hash(stream))
            name = xhtml_escape(stream.name)
            stream_items.append(f'<li><a href="/{sid}">{name}</a></li>')

        body_html = (
            "<div class='card'>"
            "<h3>streams</h3>"
            f"<ul>{''.join(stream_items) or '<li>暂无流</li>'}</ul>"
            "</div>"
            "<div class='card section'>"
            "<h3>执行代码</h3>"
            "<form method='post' action='/monitor/exec'>"
            "<div class='inline'>"
            "<input class='code-input' type='text' name='command' placeholder='例如: 1+1 或 a=1'>"
            "<button class='btn' type='submit'>执行</button>"
            "</div>"
            "</form>"
            "</div>"
        )
        subnav_html = (
            '<a href="/monitor">总览</a>'
            '<a href="/allstreams">allstreams</a>'
        )
        _render_page_shell(self, "Deva Admin Monitor", body_html, primary_active="/monitor", subnav_html=subnav_html)


class MonitorAllStreamsHandler(RequestHandler):
    def initialize(self, *, ctx):
        self.ctx = ctx

    def get(self):
        items = []
        for stream in self.ctx["Stream"].instances():
            text = xhtml_escape(str(stream))
            sid = str(hash(stream))
            items.append(f'<li><a href="/{sid}">{text}</a></li>')
        body_html = "<div class='card'><h3>allstreams</h3><ul>%s</ul></div>" % (
            "".join(items) or "<li>暂无流</li>"
        )
        subnav_html = (
            '<a href="/monitor">总览</a>'
            '<a href="/allstreams">allstreams</a>'
        )
        _render_page_shell(self, "All Streams", body_html, primary_active="/monitor", subnav_html=subnav_html)


class MonitorLegacyStreamIdHandler(RequestHandler):
    def initialize(self, *, ctx):
        self.ctx = ctx

    def get(self, stream_id):
        stream = _match_stream(self.ctx, stream_id)
        if stream is None:
            self.set_status(404)
            return self.finish(f"stream not found: {xhtml_escape(stream_id)}")
        _render_stream_page(self, stream)


class MonitorExecHandler(RequestHandler):
    def initialize(self, *, ctx):
        self.ctx = ctx

    def post(self):
        command = (self.get_body_argument("command", "") or "").strip()
        if not command:
            return _render_page_shell(
                self,
                "Monitor Exec",
                "<div class='card'>empty command</div>",
                primary_active="/monitor",
                subnav_html='<a href="/monitor">总览</a>',
            )
        command >> self.ctx["log"]
        try:
            if "=" in command:
                var_name, expr = command.replace(" ", "").split("=", 1)
                self.ctx["global_ns"][var_name] = eval(expr, self.ctx["global_ns"])
                payload = xhtml_escape(f"exec: {command}")
                return _render_page_shell(
                    self,
                    "Monitor Exec",
                    f"<div class='card'><pre>{payload}</pre></div>",
                    primary_active="/monitor",
                    subnav_html='<a href="/monitor">总览</a>',
                )
            answer = eval(command, self.ctx["global_ns"])
            payload = xhtml_escape(f"{command}\n{answer}")
            return _render_page_shell(
                self,
                "Monitor Exec",
                f"<div class='card'><pre>{payload}</pre></div>",
                primary_active="/monitor",
                subnav_html='<a href="/monitor">总览</a>',
            )
        except Exception as e:
            payload = xhtml_escape(str(e))
            return _render_page_shell(
                self,
                "Monitor Exec Error",
                f"<div class='card'><pre>{payload}</pre></div>",
                primary_active="/monitor",
                subnav_html='<a href="/monitor">总览</a>',
            )


def monitor_route_handlers(ctx):
    """Build monitor-compatible handlers for admin tornado app."""
    route_ctx = {
        "Stream": ctx["Stream"],
        "log": ctx["log"],
        "global_ns": ctx,
    }
    return [
        (r"/monitor", MonitorHomeHandler, {"ctx": route_ctx}),
        (r"/monitor/exec", MonitorExecHandler, {"ctx": route_ctx}),
        (r"/allstreams", MonitorAllStreamsHandler, {"ctx": route_ctx}),
        (r"/(-?\d+)", MonitorLegacyStreamIdHandler, {"ctx": route_ctx}),
    ]
