from deva import *
"""
Deva 爬虫框架使用指南
========================

本指南介绍如何使用 Deva 流式处理框架构建高效异步爬虫。

一、核心组件
----------
1. HTTP 请求流 (http)
   - 自动处理异步请求
   - 支持请求速率控制
   - 内置响应解析功能

2. 流处理管道
   - 链式数据处理流程
   - 支持 map/filter/rate_limit 等操作
   - 自动错误处理与重试

3. 结果处理
   - 支持多种输出方式：日志、警告、数据库等
   - 实时数据流监控

二、基础用法
----------
```python
# 创建基础爬虫流
basic_crawler = http().map(lambda r: (
    r.url, 
    r.html.search('<title>{}</title>')[0]  # 使用HTML解析模板
)) >> log  # 结果输出到日志

# 注入初始URL
'http://example.com' >> basic_crawler
```

三、高阶功能
----------
1. 并发控制
```python
advanced_crawler = (
    Stream()
    .rate_limit(1)  # 每秒1个请求
    .http(workers=20)  # 20个并发worker
    .map(parse_function)  # 自定义解析函数
    .filter(validation_function)  # 数据过滤
    >> warn  # 异常结果输出到警告
)
```

2. 链式处理
```python
(url_stream 
 | http_filter()  # 自定义过滤逻辑
 | rate_limiter() 
 | html_parser()
 >> [log, database_sink]  # 多路输出
)
```

四、配置选项
---------
1. HTTP 客户端配置
```python
h = http(
    headers={'User-Agent': 'DevaBot/1.0'},
    timeout=30,
    retries=3
)
```

2. 性能调优参数
```python
s = Stream()
s.http(
    workers=100,        # 并发worker数
    queue_size=500,     # 请求队列容量
    retry_delay=5       # 重试间隔(秒)
)
```

五、最佳实践
---------
1. 页面解析建议
```python
def parse_response(r):
    return {
        'url': r.url,
        'title': r.html.find('h1', first=True).text,
        'content': r.html.search('Main Content:{}<!-- end -->')[0]
    }
```

2. 异常处理
```python
crawler_stream = (
    http()
    .map(safe_parse)  # 包装解析函数
    .catch(HTTPError)  # 捕获特定异常
    .throttle(0.5)     # 错误后限速
)
```

六、运行与监控
---------
```python
# 启动事件循环（必须）
Deva.run()

# 运行时监控
@log.timer(10)
def monitor():
    return f"当前队列: {crawler.queue_size} 个请求"
```

注意事项
-------
1. 遵守 robots.txt 规则
2. 合理设置请求间隔（建议 ≥1 秒）
3. 使用 try/except 处理解析异常
4. 分布式场景使用 Deva 的集群模式
5. 及时释放响应对象内存
"""

h = crawler()
h.map(lambda r: (r.url, r.html.search('<title>{}</title>')[0])) >> log
'http://secsay.com' >> h


s = Stream()
s.rate_limit(1).http(workers=20).map(lambda r: (
    r.url, r.html.search('<title>{}</title>')[0])) >> warn
'http://secsay.com' >> s


"""
Deva Stream 爬虫设计指南

一、设计思路
1. 流式处理：将爬虫任务抽象为数据流，每个URL作为一个数据项在流中传递
2. 模块化：将不同功能拆分为独立函数，通过流操作符组合
3. 自动扩展：通过链接发现机制自动扩展爬取范围
4. 异步处理：利用Deva的异步特性提高爬取效率

二、编程范式
1. 声明式编程：通过流操作符声明数据处理流程
2. 函数式编程：使用纯函数处理数据，避免副作用
3. 响应式编程：数据流自动触发后续处理

三、核心组件
1. 数据源：Stream()创建源流，emit()注入初始URL
2. 数据处理链：
   - unique()：URL去重
   - rate_limit()：限速控制
   - map()：数据转换
   - filter()：数据过滤
   - flatten()：数据展平
3. 数据输出：sink()用于结果输出或反馈

四、典型流程
1. URL收集 -> 2. 请求发送 -> 3. 响应处理 -> 4. 数据提取 -> 5. 链接发现 -> 6. 结果输出

五、示例代码
"""

from requests_html import HTMLSession

# 初始化HTML会话
session = HTMLSession()

# 定义数据处理函数
def get_response(url):
    """发送HTTP请求"""
    return session.get(url)

def get_result(response):
    """提取页面信息"""
    return response.html.search('<title>{}</title>'), response.url

def get_links(response):
    """提取页面链接"""
    return response.html.absolute_links

def is_special_response(response):
    """过滤条件判断"""
    return 'gndy' in response.url

# 构建爬虫流
source = Stream()  # 创建源流
pages = source.unique()  # URL去重
response = pages.rate_limit(1).map(get_response)  # 限速请求
special_response = response.filter(is_special_response)  # 条件过滤
result = special_response.map(get_result)  # 提取结果
links = response.map(get_links).flatten()  # 发现新链接
links.sink(source.emit)  # 反馈新链接

# 输出结果
result.sink(print)

# 启动爬虫
source.emit('http://www.dytt8.net')
Deva.run()
"""
Stream 流式编程指南

一、概述
Stream 是一种基于数据流的编程范式，通过将数据处理过程分解为多个可组合的操作步骤，实现复杂任务的简洁表达。它特别适合处理异步、多流程的任务，如网络爬虫、数据处理管道等。

二、核心概念
1. 数据流 (Stream)：数据流动的管道，可以承载任意类型的数据
2. 操作符 (Operator)：对流数据进行处理的函数，如 map、filter 等
3. 源 (Source)：数据流的起点，通常通过 emit() 方法注入数据
4. 汇 (Sink)：数据流的终点，用于输出或存储结果

三、基本操作
1. 创建流：source = Stream()
2. 数据转换：stream.map(func)  # 对每个元素应用 func
3. 数据过滤：stream.filter(func)  # 保留 func 返回 True 的元素  
4. 数据展平：stream.flatten()  # 将嵌套结构展平
5. 数据去重：stream.unique()  # 去除重复元素
6. 限速控制：stream.rate_limit(n)  # 限制每秒处理 n 个元素
7. 数据输出：stream.sink(func)  # 将数据传递给 func 处理

四、编程模式
1. 声明式编程：通过链式调用描述数据处理流程
2. 函数式编程：使用纯函数进行数据处理
3. 响应式编程：数据流动自动触发后续处理

五、爬虫示例解析
1. 创建源流：source = Stream()
2. URL 去重：pages = source.unique()
3. 限速请求：response = pages.rate_limit(1).map(get_response)
4. 条件过滤：special_response = response.filter(is_special_response)
5. 提取结果：result = special_response.map(get_result)
6. 发现链接：links = response.map(get_links).flatten()
7. 反馈链接：links.sink(source.emit)
8. 输出结果：result.sink(print)

六、优势
1. 代码简洁：通过链式调用表达复杂逻辑
2. 易于扩展：通过添加操作符即可增加新功能
3. 异步友好：天然支持异步数据处理
4. 模块化：每个操作符独立且可复用

七、最佳实践
1. 保持操作符的纯函数特性
2. 合理使用限速控制避免资源耗尽
3. 使用 unique() 避免重复处理
4. 通过 sink() 实现数据持久化
5. 使用 flatten() 处理嵌套数据结构

八、应用场景
1. 网络爬虫
2. 数据处理管道
3. 实时数据流处理
4. 事件驱动编程
5. 异步任务编排
"""
