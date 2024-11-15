# Deva Core 模块

## 模块概述
这是 Deva 框架的核心模块,提供了基于 Python 的异步流式处理框架。主要功能包括流式数据处理、HTTP 客户端、事件处理等。

## 主要功能

### 1. 流式处理 (Stream)
- 支持数据流的创建、转换和组合
- 提供丰富的流操作符(map, filter, reduce等)
- 支持异步流处理
- 内置缓存机制
- 支持流的可视化

### 2. HTTP 客户端
- 异步 HTTP 请求
- 支持 JavaScript 渲染
- 并发请求控制
- 错误处理机制

### 3. 事件处理
- 基于 Tornado 的事件循环
- 支持异步/同步操作
- 提供事件路由机制

## 核心类

### Stream
流处理的基础类,提供数据流的核心功能。

主要方法:
- `emit(x)`: 发送数据到流中
- `map(func)`: 转换流中的数据
- `filter(predicate)`: 过滤流数据
- `sink(func)`: 消费流数据
- `catch(func)`: 捕获函数执行结果
- `route(occasion)`: 路由分发

### Sink
数据流的终端处理类。

主要方法:
- `to_textfile()`: 写入文本文件
- `to_list()`: 转换为列表

### HTTP
HTTP 请求处理类。

主要方法:
- `get()`: 发送 GET 请求
- `request()`: 发送通用请求
- `get_web_article()`: 提取网页文章

## 使用示例

### 1. 基础流操作

```python
from deva import Stream

# 创建基础流
source = Stream()

# 添加处理和输出
source.map(lambda x: x * 2)\
      .filter(lambda x: x > 5)\
      .sink(print)

# 发送数据
for i in range(5):
    source.emit(i)  # 将输出: 6, 8
```

## 2. 流的缓存操作

```python
# 创建带缓存的流
cached_stream = Stream(cache_max_len=100, cache_max_age_seconds=300)

# 发送数据
for i in range(10):
    cached_stream.emit(i)

# 获取最近的值
recent_values = cached_stream.recent(n=5)  # 获取最近5个值
recent_time = cached_stream.recent(seconds=60)  # 获取最近60秒的值
```

## 3. HTTP 请求处理

```python
from deva import Stream, http

# 创建 HTTP 流
h = http(workers=10)  # 10个并发worker

# 处理网页内容
h.map(lambda r: r.html.search('<title>{}</title>')[0])\
 .sink(print)

# 发送请求
'https://example.com' >> h

# 使用请求参数字典
{
    'url': 'https://api.example.com/data',
    'headers': {'Authorization': 'Bearer token'},
    'params': {'key': 'value'}
} >> h
```

## 4. 异常处理

```python
from deva import Stream

# 创建错误日志流
error_log = Stream()
error_log.sink(lambda e: print(f"Error: {e}"))

# 主处理流
main = Stream()

@main.catch
def process_data(x):
    if x == 0:
        raise ValueError("Zero is not allowed")
    return 100 / x

@error_log.catch_except
def risky_function(x):
    return x / 0  # 这会触发异常并被捕获到error_log流
```

## 5. 路由功能

```python
from deva import Stream

# 创建路由流
router = Stream()

# 根据类型路由
@router.route(lambda x: isinstance(x, str))
def handle_strings(x):
    print(f"处理字符串: {x}")

@router.route(lambda x: isinstance(x, int))
def handle_numbers(x):
    print(f"处理数字: {x * 2}")

# 发送不同类型的数据
router.emit("hello")  # 输出: 处理字符串: hello
router.emit(42)      # 输出: 处理数字: 84
```

## 6. 异步操作

```python
from deva import Stream, sync
from tornado import gen

# 创建异步流
async_stream = Stream()

@async_stream.catch
async def async_process(x):
    await gen.sleep(1)  # 异步等待
    return x * 2

# 启动事件循环
from deva import Deva
Deva.run()  # 在主线程中运行事件循环
```

## 7. 管道操作符

```python
from deva import Stream
from deva.pipe import P, print

# 使用管道操作符
data = [1, 2, 3, 4, 5]
result = data >> P.map(lambda x: x * 2)\
                 >> P.filter(lambda x: x > 5)\
                 >> print

# 使用流式API
stream = Stream()
stream >> P.map(str)\
       >> P.concat(',')\
       >> print
```

## 其他说明
####  `sink` 和 `map` 的主要区别：

1. **基本概念**
```python
# map: 转换数据并继续传递
source.map(lambda x: x * 2)  # 数据流继续

# sink: 消费数据的终点
source.sink(print)  # 数据流结束
```

2. **具体区别**

| 特性 | map | sink |
|------|-----|------|
| 返回值 | 返回新的流 | 返回None |
| 数据流向 | 继续向下传递 | 终止于此 |
| 主要用途 | 数据转换 | 数据消费 |
| 链式调用 | 可以继续链接 | 不能继续链接 |

3. **使用示例**
```python
from deva import Stream

source = Stream()

# map 示例：数据转换后继续流动
source.map(lambda x: x * 2)    # 乘以2
      .map(lambda x: str(x))   # 转为字符串
      .sink(print)             # 最后打印

# sink 示例：数据的最终处理
L = []
source.sink(L.append)  # 收集到列表
source.sink(print)     # 打印输出

# 发送数据
source.emit(1)  # 会触发所有 sink
```

4. **常见用法**
```python
# map 常用于:
source.map(int)              # 类型转换
source.map(lambda x: x + 1)  # 数据处理
source.map(json.loads)       # 格式转换

# sink 常用于:
source.sink(print)           # 打印输出
source.sink(file.write)      # 写入文件
source.sink(list.append)     # 收集数据
source.sink(db.save)         # 保存数据库
```

5. **关键点总结**
- `map` 是中间操作，用于转换数据
- `sink` 是终端操作，用于消费数据
- 一个流可以有多个 `sink`，但每个 `map` 只能有一个输出
- `map` 支持链式操作，`sink` 是终点
- `sink` 通常用于产生副作用（打印、保存等）