快速开始
========

.. contents:: 目录
   :depth: 3
   :local:

5 分钟快速上手 Deva
------------------

本指南将带你快速体验 Deva 的核心功能，从零开始创建第一个流处理程序。

步骤 1：安装 Deva
~~~~~~~~~~~~~~~~

.. code-block:: bash

   pip install deva

验证安装：

.. code-block:: python

   import deva
   print(f"Deva 版本：{deva.__version__}")


步骤 2：创建第一个流
~~~~~~~~~~~~~~~~~~

创建 ``hello_stream.py`` 文件：

.. code-block:: python

   from deva import Stream, log, Deva

   # 创建数据流
   source = Stream(name="numbers")

   # 添加处理逻辑：乘 2 -> 过滤大于 3 的数 -> 输出日志
   source.map(lambda x: x * 2).filter(lambda x: x > 3) >> log

   # 启动流处理
   source.start()

   # 注入数据
   for i in range(5):
       source.emit(i)

   # 运行事件循环
   Deva.run()

运行程序：

.. code-block:: bash

   python hello_stream.py

输出结果：

.. code-block:: text

   [2026-02-26 10:00:00] INFO: log: 4
   [2026-02-26 10:00:00] INFO: log: 6
   [2026-02-26 10:00:00] INFO: log: 8


步骤 3：添加定时器
~~~~~~~~~~~~~~~~

创建 ``timer_example.py`` 文件：

.. code-block:: python

   from deva import timer, log, Deva
   import time

   # 每隔 1 秒获取当前时间并输出日志
   timer(interval=1, func=lambda: time.strftime('%H:%M:%S'), start=True) >> log

   Deva.run()

运行程序，你会看到每秒输出一次当前时间。


步骤 4：Web 可视化
~~~~~~~~~~~~~~~~

创建 ``webview_example.py`` 文件：

.. code-block:: python

   from deva import timer, Deva
   import time

   # 创建实时数据流
   s = timer(
       interval=1,
       func=lambda: {
           'time': time.strftime('%H:%M:%S'),
           'timestamp': time.time()
       },
       start=True,
       name='实时时间'
   )

   # 一键生成 Web 页面
   s.webview('/realtime')

   print("访问 http://127.0.0.1:9999/realtime 查看实时数据")

   Deva.run()

运行程序，然后访问 ``http://127.0.0.1:9999/realtime`` 查看实时数据流。


核心概念速览
------------

Stream（流）
~~~~~~~~~~~

Stream 是 Deva 的核心概念，代表数据的流动管道。

.. code-block:: python

   from deva import Stream

   # 创建流
   s = Stream(name="my_stream")

   # 注入数据
   s.emit("hello")

   # 添加处理逻辑
   s.map(str.upper) >> log


算子（Operators）
~~~~~~~~~~~~~~~~

算子用于对流中的数据进行处理：

- **map**: 转换每个元素
- **filter**: 过滤元素
- **sliding_window**: 滑动窗口
- **buffer**: 缓冲收集

.. code-block:: python

   from deva import Stream, log

   s = Stream()

   # 链式调用算子
   s.map(lambda x: x * 2).filter(lambda x: x > 10) >> log

   s.emit(3)  # 输出：6
   s.emit(6)  # 输出：12


消息总线（Bus）
~~~~~~~~~~~~~

Bus 用于跨组件或跨进程通信：

.. code-block:: python

   from deva import bus, log

   # 发送消息
   "hello" >> bus

   # 接收并处理消息
   bus.map(str.upper) >> log


定时器（Timer）
~~~~~~~~~~~~

Timer 用于周期性执行任务：

.. code-block:: python

   from deva import timer, log

   # 每秒执行一次
   timer(interval=1, func=lambda: "tick", start=True) >> log


数据持久化（DBStream）
~~~~~~~~~~~~~~~~~~~~

DBStream 提供流式数据存储：

.. code-block:: python

   from deva import NB

   # 创建命名存储
   db = NB('events', key_mode='time')

   # 写入数据
   db.append({'event': 'click', 'user': 'alice'})

   # 回放历史数据
   for event in db.replay():
       print(event)


下一步
------

完成快速开始后，你可以：

1. 阅读 :doc:`manual_cn` 深入了解各模块功能
2. 查看 :doc:`examples` 学习完整示例
3. 参考 :doc:`api` 了解详细 API 文档
4. 访问 `GitHub Examples <https://github.com/sostc/deva/tree/master/deva/examples>`_ 运行示例代码

常见问题
--------

Q: 脚本不退出怎么办？
~~~~~~~~~~~~~~~~~~~

A: Deva.run() 会启动事件循环，脚本会持续运行。需要按 Ctrl+C 停止。

Q: 如何在 Jupyter 中使用？
~~~~~~~~~~~~~~~~~~~~~~~~

A: 在 Jupyter 中不需要调用 Deva.run()，直接运行流代码即可。

Q: 如何实现跨进程通信？
~~~~~~~~~~~~~~~~~~~~

A: 使用 bus 并配置 Redis 后端：

.. code-block:: bash

   export DEVA_BUS_MODE=redis
   export DEVA_REDIS_URL=redis://localhost:6379


相关文档
--------

- :doc:`installation` - 详细安装指南
- :doc:`manual_cn` - 完整使用手册
- :doc:`usage` - 使用指南
- :doc:`examples` - 示例集合
