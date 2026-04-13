# Deva Core 核心引擎文档

## 概述

Deva Core 是一个基于 Python 的异步流式处理框架，提供完整的数据流处理、事件驱动、HTTP 客户端等核心功能。它是整个 Deva 生态系统的基础，为上层应用提供强大的数据处理能力。

## 核心特性

- **流式处理**：支持数据流的创建、转换和组合，提供丰富的流操作符
- **异步支持**：完整的异步事件循环，基于 Tornado 实现
- **HTTP 客户端**：基于 requests-html 的异步 HTTP 客户端，支持 JavaScript 渲染
- **消息总线**：事件驱动的消息总线，支持 RPC 和共享状态管理
- **管道操作**：链式调用风格的数据处理
- **调度器**：强大的定时任务调度功能

## 模块结构

```
deva/core/
├── core.py          # 核心流处理系统
├── bus.py           # 消息总线
├── pipe.py          # 管道操作
├── sources.py       # 数据源
├── store.py         # 存储系统
├── when.py          # 调度器
├── namespace.py     # 命名空间
├── compute/         # 计算模块
│   ├── graph.py     # 计算图
│   └── ops.py       # 计算操作
└── utils/           # 工具函数
    ├── ioloop.py    # 事件循环
    ├── simhash.py   # 相似哈希
    ├── sqlitedict.py # SQLite 字典
    ├── time.py      # 时间工具
    └── whooshalchemy.py # 全文搜索
```

## 核心模块详解

### 1. Stream 流处理系统

**位置**：[deva/core/core.py](file:///workspace/deva/core/core.py#L391)

Stream 类是整个框架的核心，提供无限数据序列的处理能力。

#### 主要特性

- 流之间可以相互订阅、传递和转换数据
- 支持同步和异步操作
- 提供丰富的操作符：map、filter、reduce、sink 等
- 支持缓存和最近数据回放
- 支持路由函数、异常捕获
- 支持发布/订阅模式

#### 核心方法

| 方法 | 说明 |
|------|------|
| `emit(x)` | 将数据推入流 |
| `map(func)` | 对流中的每个元素应用函数 |
| `filter(predicate)` | 只允许满足谓词的元素通过 |
| `sink(func)` | 对流中的每个元素应用函数（终点） |
| `route(occasion)` | 路由函数，根据条件分发数据 |
| `catch(func)` | 捕获函数执行结果到流内 |
| `catch_except(func)` | 捕获函数执行异常到流内 |
| `recent(n, seconds)` | 获取最近的缓存数据 |
| `pub(topic, message)` | 发布消息到特定主题 |
| `sub(topic)` | 装饰器，订阅特定主题 |

#### 使用示例

```python
from deva import Stream

source = Stream()

result = (source.map(lambda x: x * 2)
                .filter(lambda x: x > 0)
                .rate_limit(0.5))

result.sink(print)

for i in range(5):
    source.emit(i)
```

### 2. Bus 消息总线

**位置**：[deva/core/bus.py](file:///workspace/deva/core/bus.py)

提供事件驱动的消息总线功能，支持：
- 事件发布和订阅
- 远程过程调用 (RPC)
- 共享状态管理
- 分布式锁
- 任务队列

### 3. Pipe 管道操作

**位置**：[deva/core/pipe.py](file:///workspace/deva/core/pipe.py)

提供链式调用风格的数据处理，使用 `>>` 操作符组合操作。

#### 使用示例

```python
from deva import P

data = [{'name': 'foo', 'value': 1},
        {'name': 'bar', 'value': 2}]

(data >> P.map(lambda x: x['value'])
      >> P.filter(lambda x: x > 1)
      >> P.reduce(lambda x,y: x + y)
      >> print)
```

### 4. HTTP 客户端

**位置**：[deva/core/core.py#L1561](file:///workspace/deva/core/core.py#L1561)

基于 requests-html 的异步 HTTP 客户端，支持：
- 异步并发请求
- JavaScript 渲染
- 网页抓取和解析

**核心函数**：`httpx(req, render=False, timeout=30, workers=10, **kwargs)`

### 5. When 调度器

**位置**：[deva/core/when.py](file:///workspace/deva/core/when.py)

提供强大的定时任务调度功能，支持：
- 定时任务
- 间隔任务
- Cron 表达式
- 工作队列

### 6. Store 存储系统

**位置**：[deva/core/store.py](file:///workspace/deva/core/store.py)

提供数据持久化功能，支持多种后端存储。

## 依赖关系

### 核心依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| tornado | >=6.0 | 异步 Web 框架和事件循环 |
| pandas | >=1.0 | 数据分析和处理 |
| dill | >=0.3 | 对象序列化 |
| toolz | >=0.10 | 函数式编程工具 |
| requests | >=2.28 | HTTP 请求 |
| requests-html | >=0.10 | HTML 解析和 JavaScript 渲染 |
| aiohttp | >=3.8 | 异步 HTTP |

## 快速开始

### 安装

```bash
pip install -r requirements.txt
```

### 基本使用

```python
from deva import Stream, http

source = Stream()

(source.map(http.get)
       .map(lambda r: r.html.find('h1', first=True))
       .sink(print))

source.emit('https://example.com')
```

## 示例代码

更多示例请参考 [deva/examples/](file:///workspace/deva/examples/) 目录。

## 相关文档

- [CODE_WIKI.md](file:///workspace/CODE_WIKI.md) - 项目总览文档
- [NAJA_OVERVIEW.md](file:///workspace/docs/NAJA_OVERVIEW.md) - Naja 平台文档

---

**文档版本**：1.0
**最后更新**：2026-04-13
