"""事件循环工具：sync（跨线程执行协程）与 Deva（循环启停）。

从 core.py 拆出（P2 #11）。
"""
from __future__ import absolute_import, division, print_function
import os

import logging
import six
import sys
import threading

try:
    from tornado import gen
except ImportError:
    gen = None
from tornado.ioloop import IOLoop
try:
    from tornado.ioloop import PollIOLoop
except ImportError:
    PollIOLoop = None  # dropped in tornado 6.0

from datetime import timedelta
from deva.utils.ioloop import get_io_loop
from threading import get_ident as get_thread_identity

__all__ = ['sync', 'Deva', 'thread_state']

logger = logging.getLogger(__name__)

# 每线程标记：当前是否在 sync() 拉起的协程上下文里
thread_state = threading.local()


def sync(loop, func, *args, **kwargs):
    """在单独线程中运行的事件循环中执行协程函数

    参数:
        loop: 事件循环对象,如果为None则使用get_io_loop()获取
        func: 要执行的协程函数
        *args: 传递给func的位置参数
        **kwargs: 传递给func的关键字参数,其中callback_timeout用于设置超时时间

    返回:
        协程函数的执行结果

    异常:
        RuntimeError: 如果事件循环已关闭,或在运行loop的线程中调用
        TimeoutError: 如果执行超时

    示例:
        # 基本用法
        async def async_task():
            await asyncio.sleep(1)
            return "done"

        result = sync(None, async_task)  # 在默认事件循环中执行
        print(result)  # 输出: done

        # 带超时设置
        try:
            result = sync(None, async_task, callback_timeout=0.5)
        except gen.TimeoutError:
            print("任务超时")

        # 在事件循环线程中调用会抛出异常
        loop = get_io_loop()
        try:
            loop.add_callback(lambda: sync(loop, async_task))
        except RuntimeError as e:
            print(e)  # 输出: sync() called from thread of running loop
    """
    # 检查事件循环是否已关闭
    loop = loop or get_io_loop()
    if PollIOLoop\
        and ((isinstance(loop, PollIOLoop)
              and getattr(loop, '_closing', False))
             or (hasattr(loop, 'asyncio_loop')
                 and loop.asyncio_loop._closed)):
        raise RuntimeError("IOLoop is closed")

    # 获取超时设置
    timeout = kwargs.pop('callback_timeout', None)

    # 用于同步的事件对象
    e = threading.Event()
    main_tid = get_thread_identity()
    result = [None]
    error = [False]

    @gen.coroutine
    def f():
        try:
            # 检查是否在事件循环线程中调用
            if main_tid == get_thread_identity():
                raise RuntimeError("sync() called from thread of running loop")
            yield gen.moment
            thread_state.asynchronous = True
            future = func(*args, **kwargs)
            # 添加超时控制
            if timeout is not None:
                future = gen.with_timeout(timedelta(seconds=timeout), future)
            result[0] = yield future
        except Exception:
            error[0] = sys.exc_info()
        finally:
            thread_state.asynchronous = False
            e.set()

    # 将协程添加到事件循环
    loop.add_callback(f)

    # 等待执行完成或超时
    if timeout is not None:
        if not e.wait(timeout):
            raise gen.TimeoutError("timed out after %s s." % (timeout,))
    else:
        while not e.is_set():
            e.wait(10)

    # 处理执行结果
    if error[0]:
        six.reraise(*error[0])
    else:
        return result[0]

class Deva:
    """Deva 事件循环管理类

    提供统一的事件循环启动和管理接口，支持优雅退出和异常处理。

    使用方法
    --------
    1. 在程序入口处调用 Deva.run() 启动事件循环
    2. 使用 Ctrl+C 可以优雅地停止事件循环
    3. 所有异步任务将在事件循环中执行

    示例
    --------
    >>> from deva import Deva
    >>> Deva.run()  # 启动事件循环
    >>> # 在此处添加你的异步任务
    >>> # 按 Ctrl+C 停止事件循环
    """

    @classmethod
    def run(cls):
        """启动 Tornado IOLoop 事件循环（阻塞）。

        事件循环的启动权在调用方（如 run_web_application），本方法
        只负责 start + 优雅退出，不猜测 loop 运行状态。
        """
        logger.info("Starting Deva event loop...")
        try:
            IOLoop.current().start()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
        finally:
            logger.info("Deva event loop stopped")


logger.info(f"当前进程ID: {os.getpid()}")
