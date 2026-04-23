"""
实时推送模块 - 提供便捷的 PyWebIO 实时推送功能

基于 PyWebIO 的 WebSocket 协议实现，支持：
1. 向指定 scope 实时推送内容（HTML/Markdown/Text/Table）
2. 后台定时推送
3. 流式数据推送

使用示例 1: 基本推送
====================

    from deva.naja.infra.ui.realtime_pusher import RealtimePusher

    async def render_market_page(ctx):
        pusher = RealtimePusher(ctx, scope="market_data")

        with ctx["use_scope"]("market_data"):
            ctx["put_html"]("<div>Loading...</div>")

        pusher.clear()
        pusher.push_html("<h3>Market Hotspot</h3>")
        pusher.push_markdown("**A股** Hot blocks: Tech, Finance")
        pusher.push_table([["Block", "Change"], ["Tech", "+2.5%"], ["Finance", "+1.2%"]])

使用示例 2: 后台定时推送
=======================

    from deva.naja.infra.ui.realtime_pusher import RealtimePusher

    async def render_market_page(ctx):
        pusher = RealtimePusher(ctx, scope="market_data")

        with ctx["use_scope"]("market_data"):
            ctx["put_html"]("<div>Monitoring...</div>")

        def fetch_market_data():
            integration = get_market_hotspot_integration()
            report = integration.get_hotspot_report()
            return "**Global Hotspot**: " + str(report.get('global_hotspot', 0))

        pusher.start_auto_push(fetch_market_data, interval=10.0, content_type="markdown")

使用示例 3: 流式推送（适用于 LLM 响应）
=======================================

    from deva.naja.infra.ui.realtime_pusher import StreamingPusher

    async def render_llm_page(ctx):
        pusher = StreamingPusher(ctx, scope="llm_response", flush_interval=2.0)

        with ctx["use_scope"]("llm_response"):
            ctx["put_html"]("<div>Waiting...</div>")

        async def stream_llm_response():
            response = await get_gpt_response_stream(prompt)
            async for chunk in response:
                pusher.update(chunk)
            pusher.flush()

        await stream_llm_response()
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass


@dataclass
class PushItem:
    """推送项"""
    content: str
    content_type: str
    position: int = -1


class RealtimePusher:
    """
    PyWebIO 实时推送器

    封装 PyWebIO 的 session.send_task_command 接口，提供更便捷的实时推送功能。
    """

    def __init__(self, ctx: dict, scope: str = "realtime_content", task_id: str = None):
        """
        初始化实时推送器

        Args:
            ctx: PyWebIO 上下文（包含 session, put_html 等）
            scope: 目标 scope 名称
            task_id: 任务 ID（通常不需要手动指定）
        """
        self.ctx = ctx
        self.scope = scope
        self.task_id = task_id or "realtime_pusher"

        self._session = None
        self._auto_push_task: Optional[asyncio.Task] = None
        self._running = False

    def _get_session(self):
        """获取当前 session"""
        if self._session is None:
            get_session_impl = self.ctx.get("get_session_implement")
            if get_session_impl:
                self._session = get_session_impl().get_current_session()
            else:
                raise RuntimeError("ctx 中缺少 get_session_implement 方法")
        return self._session

    def _build_output_spec(self, content: Any, content_type: str, position: int = -1) -> Dict:
        """构建 PyWebIO 输出规范"""
        spec = {
            "type": content_type,
            "content": content,
            "inline": True,
            "position": position,
            "sanitize": True,
            "scope": "#pywebio-scope-" + self.scope,
        }
        return spec

    def _send_command(self, command: str, spec: Dict):
        """发送命令到前端"""
        session = self._get_session()
        data = {
            "command": command,
            "spec": spec,
            "task_id": self.task_id,
        }
        return session.send_task_command(data)

    def push(self, content: Any, content_type: str = "text", position: int = -1):
        """
        推送内容到前端

        Args:
            content: 内容（字符串或列表）
            content_type: 类型 (html, markdown, text, table)
            position: 插入位置，-1 表示末尾
        """
        spec = self._build_output_spec(content, content_type, position)
        self._send_command("output", spec)

    def push_html(self, html: str, position: int = -1):
        """推送 HTML 内容"""
        self.push(html, "html", position)

    def push_markdown(self, md: str, position: int = -1):
        """推送 Markdown 内容"""
        self.push(md, "markdown", position)

    def push_text(self, text: str, position: int = -1):
        """推送纯文本内容"""
        self.push(text, "text", position)

    def push_table(self, data: List[List], position: int = -1):
        """推送表格内容"""
        self.push(data, "table", position)

    def clear(self):
        """清空 scope 内容"""
        spec = {"clear": "#pywebio-scope-" + self.scope}
        self._send_command("output_ctl", spec)

    def remove(self):
        """移除 scope"""
        spec = {"remove": "#pywebio-scope-" + self.scope}
        self._send_command("output_ctl", spec)

    async def push_async(self, content: Any, content_type: str = "text", position: int = -1):
        """异步推送内容（用于 async 函数中）"""
        spec = self._build_output_spec(content, content_type, position)
        self._send_command("output", spec)

    async def push_html_async(self, html: str, position: int = -1):
        """异步推送 HTML 内容"""
        await self.push_async(html, "html", position)

    async def push_markdown_async(self, md: str, position: int = -1):
        """异步推送 Markdown 内容"""
        await self.push_async(md, "markdown", position)

    async def clear_async(self):
        """异步清空 scope 内容"""
        spec = {"clear": "#pywebio-scope-" + self.scope}
        self._send_command("output_ctl", spec)

    def render_scope(self):
        """在上下文中渲染 scope（创建空的 scope 区域）"""
        use_scope = self.ctx.get("use_scope")
        if use_scope:
            use_scope(self.scope)
        return self.scope

    def start_auto_push(self, fetch_func: Callable[[], Any],
                       interval: float = 10.0,
                       content_type: str = "html",
                       on_error: Callable[[Exception], None] = None):
        """
        启动后台定时推送

        Args:
            fetch_func: 获取数据的函数，返回要推送的内容
            interval: 推送间隔（秒）
            content_type: 推送内容的类型
            on_error: 错误回调函数
        """
        if self._auto_push_task is not None and not self._auto_push_task.done():
            self.stop_auto_push()

        self._running = True

        async def _auto_push_loop():
            while self._running:
                try:
                    content = fetch_func()
                    if content:
                        self.push(content, content_type)
                except Exception as e:
                    if on_error:
                        on_error(e)
                    else:
                        import traceback
                        traceback.print_exc()
                await asyncio.sleep(interval)

        loop = asyncio.get_event_loop()
        self._auto_push_task = loop.create_task(_auto_push_loop())

    def stop_auto_push(self):
        """停止后台定时推送"""
        self._running = False
        if self._auto_push_task is not None:
            self._auto_push_task.cancel()
            self._auto_push_task = None

    async def start_auto_push_async(self, fetch_func: Callable[[], Any],
                                   interval: float = 10.0,
                                   content_type: str = "html",
                                   on_error: Callable[[Exception], None] = None):
        """
        异步启动后台定时推送（用于 async 函数中）

        Args:
            fetch_func: 异步获取数据的函数
            interval: 推送间隔（秒）
            content_type: 推送内容的类型
            on_error: 错误回调函数
        """
        if self._auto_push_task is not None and not self._auto_push_task.done():
            self.stop_auto_push()

        self._running = True

        async def _auto_push_loop():
            while self._running:
                try:
                    content = await fetch_func()
                    if content:
                        await self.push_async(content, content_type)
                except Exception as e:
                    if on_error:
                        on_error(e)
                    else:
                        import traceback
                        traceback.print_exc()
                await asyncio.sleep(interval)

        self._auto_push_task = asyncio.create_task(_auto_push_loop())

    def is_auto_push_running(self) -> bool:
        """检查后台推送是否正在运行"""
        return self._auto_push_task is not None and not self._auto_push_task.done()


class StreamingPusher(RealtimePusher):
    """
    流式数据推送器

    适用于 LLM 流式响应等场景，支持：
    1. 增量更新（不是追加，而是覆盖或局部更新）
    2. 流式缓冲区（积累到一定量才推送）
    3. 智能刷新（段落结束或超时才推送）
    """

    def __init__(self, ctx: dict, scope: str = "streaming_content",
                 flush_interval: float = 3.0,
                 paragraph_markers: str = None):
        """
        初始化流式推送器

        Args:
            ctx: PyWebIO 上下文
            scope: 目标 scope
            flush_interval: 强制刷新间隔（秒）
            paragraph_markers: 段落结束标记字符
        """
        super().__init__(ctx, scope)
        self.flush_interval = flush_interval
        self.paragraph_markers = paragraph_markers or ".。?？!！"
        self._buffer = ""
        self._last_flush_ts = time.time()
        self._accumulated_text = ""

    def update(self, chunk: str):
        """
        更新流式内容（追加到缓冲区，满足条件时推送）

        Args:
            chunk: 新收到的文本块
        """
        self._buffer += chunk
        self._accumulated_text += chunk

        should_flush = False
        if len(self._buffer) >= 2 and self._buffer[-2] in self.paragraph_markers and self._buffer[-1] == "\n":
            should_flush = True

        if not should_flush and (time.time() - self._last_flush_ts >= self.flush_interval):
            should_flush = True

        if should_flush and self._buffer.strip():
            self.push(self._buffer, "markdown")
            self._buffer = ""
            self._last_flush_ts = time.time()

    def flush(self):
        """强制刷新缓冲区"""
        if self._buffer.strip():
            self.push(self._buffer, "markdown")
            self._buffer = ""
            self._last_flush_ts = time.time()

    def get_accumulated_text(self) -> str:
        """获取累积的全部文本"""
        return self._accumulated_text

    def reset(self):
        """重置缓冲区和累积文本"""
        self._buffer = ""
        self._accumulated_text = ""
        self._last_flush_ts = time.time()


def create_pusher(ctx: dict, scope: str = "realtime_content") -> RealtimePusher:
    """
    便捷函数：创建实时推送器

    Args:
        ctx: PyWebIO 上下文
        scope: scope 名称

    Returns:
        RealtimePusher 实例
    """
    return RealtimePusher(ctx, scope)


def create_streaming_pusher(ctx: dict, scope: str = "streaming_content",
                          flush_interval: float = 3.0) -> StreamingPusher:
    """
    便捷函数：创建流式推送器

    Args:
        ctx: PyWebIO 上下文
        scope: scope 名称
        flush_interval: 刷新间隔

    Returns:
        StreamingPusher 实例
    """
    return StreamingPusher(ctx, scope, flush_interval)


__all__ = [
    "RealtimePusher",
    "StreamingPusher",
    "create_pusher",
    "create_streaming_pusher",
]
