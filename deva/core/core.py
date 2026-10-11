"""deva 流式核心 —— 兼容聚合层。

实现已按职责拆到同目录下的子模块，本文件只做再导出，
保证 `from deva.core.core import Stream` 这类既有写法不变：

    stream.py           Stream 基类与流基础设施
    operators.py        Sink / sink / to_textfile / map / starmap / filter / run_future
    http_stream.py      httpx / crawler
    loop.py             sync / Deva
    logging_adapter.py  日志 record 归一化与默认 handler

新代码请直接从子模块导入，不要再往这里加东西。
"""

from __future__ import absolute_import, division, print_function

from .stream import (
    Stream,
    identity,
    OrderedSet,
    OrderedWeakrefSet,
)
from .operators import (
    Sink,
    sink,
    to_textfile,
    map,
    starmap,
    filter,
    run_future,
    no_default,
)
from .http_stream import httpx, crawler
from .loop import sync, Deva, thread_state
from .logging_adapter import (
    LEVEL_ORDER,
    should_emit_level,
    normalize_record,
    format_line,
    DevaFormatter,
    setup_deva_logging,
)

__all__ = [
    'Stream',
    'identity',
    'no_default',
    'OrderedSet',
    'OrderedWeakrefSet',
    'Sink',
    'sink',
    'to_textfile',
    'map',
    'starmap',
    'filter',
    'run_future',
    'httpx',
    'crawler',
    'sync',
    'Deva',
    'thread_state',
    'LEVEL_ORDER',
    'should_emit_level',
    'normalize_record',
    'format_line',
    'DevaFormatter',
    'setup_deva_logging',
]

# ---------------------------------------------------------------------------
# 以下是原 core.py 自带的使用说明，保留在此便于检索
# ---------------------------------------------------------------------------
_USAGE = """
deva 是一个基于 Python 的异步流式处理框架。它提供了以下主要功能:

1. 流式处理
- 支持数据流的创建、转换和组合
- 提供丰富的流操作符(map, filter, reduce等)
- 支持异步流处理

2. HTTP 客户端
- 基于 requests-html 的异步 HTTP 客户端
- 支持网页抓取和解析
- 支持 JavaScript 渲染

3. 事件处理
- 基于 tornado 的事件循环
- 支持异步事件处理
- 提供定时器和调度功能

4. 管道操作
- 链式调用风格的数据处理
- 支持自定义管道操作符
- 方便的数据转换和过滤

5. 路由函数
- 支持根据特定条件路由函数
- 可以使用 lambda 表达式或者自定义函数
- 可以根据函数的返回值或者参数进行路由

6. 异常捕获
- catch 方法用于捕获函数执行结果到流内
- 支持异步和同步函数的捕获
- 可以在函数执行前和执行后执行任务

7. 异常捕获（catch_except）
- catch_except 方法用于捕获函数执行异常到流内
- 支持异步和同步函数的异常捕获
- 可以在函数执行前和执行后执行任务

主要用途:
- 网络爬虫和数据采集
- 实时数据处理
- 异步任务调度
- ETL 数据处理
- 事件驱动应用

使用示例:

1. 流式处理
from deva import Stream
# 创建数据流并进行转换
source = Stream()
result = (source.map(lambda x: x * 2)
                .filter(lambda x: x > 0)
                .rate_limit(0.5))  # 限流
                
# 输入数据
for i in range(5):
    source.emit(i)

2. 网页抓取
from deva import http
# 异步抓取网页
urls = ['http://example1.com', 'http://example2.com']
(Stream()
 .emit(urls)
 .rate_limit(0.5)  # 限制请求速率
 .map(http.get)  # 异步HTTP请求
 .map(lambda r: r.html.find('h1', first=True))  # 解析HTML
 .sink(print))  # 打印结果

3. 定时任务
from deva import Stream, timer
# 每30秒执行一次任务
(timer(30)
 .rate_limit(30)  # 限制执行频率
 .map(lambda _: http.get('http://api.example.com/data'))  # 定时获取数据
 .map(lambda r: r.json())
 .sink(print))  # 处理结果

4. 管道处理
from deva.core.pipe import pmap, pfilter, sum as pipe_sum
# 使用管道操作符处理数据（helper 需直接导入；P 只能作装饰器，
# 不支持 P.map / P.filter 这类属性访问）
data = [{'name': 'foo', 'value': 1}, 
        {'name': 'bar', 'value': 2}]
(data >> pmap(lambda x: x['value'])  # 提取value字段
      >> pfilter(lambda x: x > 1)    # 过滤
      >> pipe_sum)                   # 求和

5. 存储和回放
from deva import Stream, store
# 将数据流存储到Redis
source = Stream()
store = store('redis://localhost:6379')
(source.map(lambda x: {'time': time.time(), 'value': x})
       .sink(store.save))  # 保存到Redis

# 从Redis回放数据
(store.load()  # 加载历史数据
      .rate_limit(0.1)  # 控制回放速度
      .sink(print))  # 打印结果

6. HTTP请求处理
from deva import http
# 异步并发请求
h = http(workers=10)  # 10个并发worker
urls = ['http://api1.com', 'http://api2.com']
(urls >> h.map(lambda r: r.json())  # 解析JSON响应
         >> print)

# 渲染JavaScript
h = http(render=True)  # 启用JS渲染
'http://spa.com' >> h.map(lambda r: r.html.search('data-value="{}"')[0]) >> print

7. 命名空间(namespace)
from deva import NB
# 创建命名空间
# 创建一个新的流对象
stream = Stream()

# 使用装饰器订阅主题
@stream.sub('topic1')  # 订阅topic1
def handler1(msg):
    print(f'收到消息: {msg}')

@stream.sub('topic2')  # 订阅topic2 
def handler2(msg):
    print(f'收到消息: {msg}')

# 发布消息
stream.pub('topic1', '你好')  # 输出: 收到消息: 你好
stream.pub('topic2', '世界')  # 输出: 收到消息: 世界

# 远程过程调用(RPC)
@nb.rpc('add')  # 注册RPC方法
def add(a, b):
    return a + b
    
# 调用RPC方法
result = nb.call('add', 1, 2)  # 返回3

# 共享状态
nb.set('counter', 0)  # 设置共享变量
nb.get('counter')  # 获取共享变量
nb.incr('counter')  # 原子递增

# 分布式锁
with nb.lock('resource'):  # 获取分布式锁
    # 临界区代码
    pass

# 任务队列
@nb.task('process_data')  # 注册任务处理器
def process_data(data):
    print(f'处理数据: {data}')
    
nb.send_task('process_data', '待处理数据')  # 发送任务

# 事件总线
@nb.on('user.created')  # 监听事件
def on_user_created(user):
    print(f'新用户创建: {user}')
    
nb.emit('user.created', {'id': 1, 'name': 'test'})  # 触发事件

8. 路由函数
from deva import Stream
# 创建数据流
source = Stream()

# 定义路由函数
@source.route(lambda x: x % 2 == 0)  # 跱要求是偶数的函数
def even_handler(x):
    print(f'偶数: {x}')

@source.route(lambda x: x % 2 != 0)  # 要求是奇数的函数
def odd_handler(x):
    print(f'奇数: {x}')

# 发送数据
for i in range(5):
    source.emit(i)

# 输出结果
# 偶数: 0
# 奇数: 1
# 偶数: 2
# 奇数: 3
# 偶数: 4

9. 异常捕获
from deva import Stream
# 创建数据流
source = Stream()

# 定义一个可能抛出异常的函数
def divide(x, y):
    if y == 0:
        raise ZeroDivisionError
    return x / y

# 使用catch方法捕获异常
@source.catch(divide)
def handle_division(x, y):
    print(f'结果: {x / y}')

# 发送数据
source.emit((10, 2))  # 正常情况
source.emit((10, 0))  # 异常情况

# 输出结果
# 结果: 5.0
# 异常: division by zero

10. 缓存和回放
from deva import Stream
# 创建数据流
source = Stream()

# 缓存数据
source.cache = {'key': 'value'}

# 回放缓存的数据
source.recent()  # 获取最近的数据

11. 过滤器
from deva import Stream
# 创建数据流
source = Stream()

# 定义过滤器
@source.filter(lambda x: x > 0)  # 过滤出正数
def positive_filter(x):
    print(f'正数: {x}')

# 发送数据
for i in range(-5, 6):
    source.emit(i)

# 输出结果
# 正数: 1
# 正数: 2
# 正数: 3
# 正数: 4
# 正数: 5

12. 映射
from deva import Stream
# 创建数据流
source = Stream()

# 定义映射
@source.map(lambda x: x * 2)  # 将数据乘以2
def double_map(x):
    print(f'乘以2后的结果: {x}')

# 发送数据
for i in range(5):
    source.emit(i)

# 输出结果
# 乘以2后的结果: 0
# 乘以2后的结果: 2
# 乘以2后的结果: 4
# 乘以2后的结果: 6
# 乘以2后的结果: 8

13. reduce
from deva import Stream
# 创建数据流
source = Stream()

# 定义减少操作
@source.reduce(lambda x, y: x + y)  # 累加数据
def sum_reduce(x):
    print(f'累加结果: {x}')

# 发送数据
for i in range(5):
    source.emit(i)

# 输出结果
# 累加结果: 10

14. 异常捕获（catch_except）
from deva import Stream
# 创建数据流
source = Stream()


# 使用装饰器捕获异常
@source.catch_except
def divide(x, y):
    if y == 0:
        raise ZeroDivisionError
    return x / y

# 发送数据
divide(10,0)执行时，异常会被发送到 source 中



# 使用^运算符捕获异常
divide = lambda x, y: x / y if y != 0 else raise ZeroDivisionError
(10,0) | divide^source


更多信息请访问: https://github.com/sostc/deva
"""
