import asyncio
from tornado.web import RequestHandler, Application
from tornado.ioloop import IOLoop
import time
from deva import NW,Deva,Stream,timer,log
from deva.page import page

# 全局 Web 应用实例
web_app = NW(name='stream_webview').application

def sse_handler(path):
    """装饰器：为对象添加 SSE 能力并自动挂载到 Web 服务器"""
    def decorator(func):
        # 动态创建 SSEHandler 类
        class SSEHandler(RequestHandler):
            async def get(self):
                # 设置响应头
                self.set_header('Content-Type', 'text/event-stream')
                self.set_header('Cache-Control', 'no-cache')
                self.set_header('Connection', 'keep-alive')

                # 调用对象的 SSE 方法
                while True:
                    data = func()
                    if data:
                        self.write(f"data: {data}\n\n")
                        self.flush()
                    else:
                        time.sleep(0.1)  # 避免 CPU 占用过高

        # 将 SSEHandler 挂载到 Web 服务器
        web_app.add_handlers(r".*", [(path, SSEHandler)])

        # 返回原始类
        return func
    return decorator

# 使用装饰器
@sse_handler("/sse/stream1")  # 指定路由路径
def handle_sse():
    """SSE 数据处理方法"""
    time.sleep(1)  # 模拟数据生成延迟
    return f"Data from stream1 at {time.time()}"


@timer(1,start=True)
def foo():
    time.time() >> log

# def sse_view(self, url,server=None):
#     """为log流提供SSE服务
    
#     当有新的连接时，将log流sink到SSE服务的self.write方法
#     当连接断开时，销毁sink释放内存
    
#     Args:
#         url (str): SSE服务的URL路径
#     """
#     from tornado.web import RequestHandler
#     from tornado.escape import json_encode
    
#     class SSEHandler(RequestHandler):
#         stream = self
        
            
#         async def get(self):
#             self.set_header('Content-Type', 'text/event-stream')
#             self.set_header('Cache-Control', 'no-cache')
#             self.set_header('Connection', 'keep-alive')
            
#             # 创建sink
#             def write_to_sse(data):
#                 self.write(f"data: {json_encode(data)}\n\n")
#                 self.flush()
                
#             sink = SSEHandler.stream.sink(write_to_sse)
            
#             # 保持连接
#             while not self.request.connection.stream.closed():
#                 await asyncio.sleep(1)
                
#             # 连接断开时销毁sink
#             sink.destroy()
            
#     # 注册路由
#     server = server or NW('stream_webview')
#     server.application.add_handlers('.*$', [(r'/', SSEHandler)])
#     return self

# # 将方法添加到log流
# Stream.sse = sse_view



from deva.page import page


# 启动 Web 服务器
if __name__ == '__main__':
    log.sse('/')
    Deva.run()