使用指南
========

.. contents:: 目录
   :depth: 3
   :local:

概述
----

本指南详细介绍 Deva 的核心功能和使用方法，涵盖流处理、事件驱动、定时调度、持久化存储等主要模块。

流处理基础
----------

创建 Stream
~~~~~~~~~~~

.. code-block:: python

   from deva import Stream

   # 创建命名流
   s = Stream(name="my_stream")

   # 创建匿名流
   s = Stream()

数据注入
~~~~~~~~

.. code-block:: python

   # 注入单个数据
   s.emit("hello")

   # 注入字典
   s.emit({"key": "value"})

处理算子
~~~~~~~~

.. code-block:: python

   from deva import Stream, log

   s = Stream()

   # map: 转换
   s.map(lambda x: x * 2) >> log

   # filter: 过滤
   s.filter(lambda x: x > 0) >> log

   # 链式调用
   s.map(lambda x: x * 2).filter(lambda x: x > 10) >> log

启动流
~~~~~~

.. code-block:: python

   # 启动流处理
   s.start()

   # 停止流处理
   s.stop()


事件驱动
--------

消息总线
~~~~~~~~

使用全局 bus：

.. code-block:: python

   from deva import bus, log

   # 发送消息
   "hello" >> bus

   # 接收并处理
   bus.map(str.upper) >> log

路由机制
~~~~~~~~

使用装饰器定义路由：

.. code-block:: python

   from deva import bus, log

   @bus.route(lambda x: x == 'open')
   def on_open(x):
       '市场开盘' >> log

   @bus.route(lambda x: x == 'close')
   def on_close(x):
       '市场收盘' >> log

主题订阅
~~~~~~~~

使用 Topic 类：

.. code-block:: python

   from deva.topic import Topic

   # 创建主题
   orders = Topic("orders")

   # 发布消息
   orders.publish({"symbol": "AAPL", "action": "buy"})

   # 订阅消息
   for msg in orders.subscribe():
       print(msg)


定时与调度
----------

定时器
~~~~~~

基本用法：

.. code-block:: python

   from deva import timer, log

   # 每秒执行一次
   timer(interval=1, func=lambda: "tick", start=True) >> log

自定义间隔：

.. code-block:: python

   # 每 5 秒执行一次
   timer(interval=5, func=lambda: {"time": __import__('time').time()}, start=True) >> log

调度器
~~~~~~

基本用法：

.. code-block:: python

   from deva import Stream

   sch = Stream.scheduler()

   # 添加定时任务
   sch.add_job(func=lambda: "heartbeat", seconds=10)

   # 添加 CRON 任务
   sch.add_job(func=lambda: "daily_report", hour=9, minute=0)

   # 启动调度器
   sch.start()

任务类型：

.. code-block:: python

   # 间隔执行
   sch.add_job(func=func1, seconds=30)

   # 每天执行
   sch.add_job(func=func2, days=1, hour=9, minute=0)

   # 每周执行
   sch.add_job(func=func3, weeks=1, day_of_week='mon')


持久化存储
----------

DBStream 基本用法
~~~~~~~~~~~~~~~

.. code-block:: python

   from deva import DBStream

   # 创建 DBStream
   db = DBStream('events.db', 'events')

   # 写入数据
   db['key1'] = 'value1'

   # 读取数据
   value = db['key1']

命名空间
~~~~~~~~

使用 NB 工厂函数：

.. code-block:: python

   from deva import NB

   # 创建命名存储
   events = NB('events', key_mode='time')

   # 追加事件
   events.append({'event': 'click', 'user': 'alice'})

   # 回放历史
   for event in events.replay():
       print(event)

键模式
~~~~~~

显式键模式（默认）：

.. code-block:: python

   config = NB('config')  # key_mode='explicit'
   config.upsert('risk.max_position', 0.2)

时间键模式：

.. code-block:: python

   events = NB('events', key_mode='time')
   events.append({'event': 'trade', 'price': 100.5})


Web 可视化
----------

WebView 基本用法
~~~~~~~~~~~~~~

.. code-block:: python

   from deva import timer, Stream

   # 创建数据流
   s = timer(interval=1, func=lambda: {"time": __import__('time').time()}, start=True)

   # 生成 Web 页面
   s.webview('/realtime')

   # 启动服务
   from deva import Deva
   Deva.run()

访问 ``http://127.0.0.1:9999/realtime`` 查看实时数据。

多流展示
~~~~~~~~

.. code-block:: python

   from deva import timer

   s1 = timer(interval=1, func=lambda: '流 1', start=True, name='流 1')
   s2 = timer(interval=2, func=lambda: '流 2', start=True, name='流 2')

   s1.webview('/stream1')
   s2.webview('/stream2')


日志系统
--------

日志级别
~~~~~~~~

.. code-block:: python

   from deva import log, warn, debug

   "信息" >> log
   "警告" >> warn
   "调试" >> debug

结构化日志
~~~~~~~~~~

.. code-block:: python

   {
       "level": "info",
       "source": "my_module",
       "message": "处理完成",
       "data": {"count": 100}
   } >> log

日志配置
~~~~~~~~

通过环境变量配置：

.. code-block:: bash

   export DEVA_LOG_LEVEL=INFO
   export DEVA_LOG_FORWARD_TO_LOGGING=1


最佳实践
--------

1. 流命名

为重要的流指定名称，便于调试和监控：

.. code-block:: python

   s = Stream(name="order_stream")

2. 错误处理

使用 catch 处理异常：

.. code-block:: python

   s.map(process).catch(lambda e: log_error(e)) >> log

3. 资源清理

使用上下文管理器：

.. code-block:: python

   with Stream() as s:
       s >> log

4. 性能优化

使用 rate_limit 控制流速：

.. code-block:: python

   s.rate_limit(100) >> process  # 每秒最多 100 条


下一步
------

- :doc:`examples` - 查看完整示例
- :doc:`api` - API 详细参考
- :doc:`best_practices` - 最佳实践指南
