"""事件循环工具模块

提供统一的 IOLoop 获取和管理接口。
"""
import threading
from tornado.ioloop import IOLoop

# 全局变量，存储在守护线程中运行的 IOLoop 实例
_io_loops = []


def get_io_loop(asynchronous=None):
    """获取IOLoop实例

    这个函数用于获取IOLoop对象，理解它的关键在于区分同步和异步模式：
    
    1. 同步模式（asynchronous=False/None）：
    - 在后台启动一个守护线程
    - 在该线程中创建并运行一个新的IOLoop
    - 适合在普通Python函数中使用
    
    2. 异步模式（asynchronous=True）：
    - 直接返回当前线程的IOLoop
    - 适合在async/await异步函数中使用
    
    简单来说，同步模式会创建新线程来处理事件循环，而异步模式则使用当前线程的事件循环。

    参数:
        asynchronous (bool, optional): 
            - True: 返回当前线程的IOLoop
            - False/None: 返回在守护线程中运行的IOLoop

    返回:
        IOLoop: tornado的IOLoop实例

    示例:
        # 获取当前线程的IOLoop
        loop = get_io_loop(asynchronous=True)

        # 获取守护线程中的IOLoop
        loop = get_io_loop(asynchronous=False)
    """
    if asynchronous:
        return IOLoop.current()

    if not _io_loops:
        loop = IOLoop()
        thread = threading.Thread(target=loop.start)
        thread.daemon = True  # 设置为守护线程，主线程退出时自动退出
        thread.start()
        _io_loops.append(loop)

    return _io_loops[-1]  # 返回最近创建的IOLoop