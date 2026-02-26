.. image:: https://raw.githubusercontent.com/sostc/deva/master/deva.jpeg
   :target: https://github.com/sostc/deva
   :align: center
   :alt: Deva Logo

======

Deva - 异步流式处理框架
========================

.. image:: https://img.shields.io/pypi/v/deva.svg
   :target: https://pypi.org/project/deva/
   :alt: PyPI Version

.. image:: https://img.shields.io/pypi/pyversions/deva.svg
   :target: https://pypi.org/project/deva/
   :alt: Python Versions

.. contents:: 目录
   :backlinks: top
   :depth: 2

简介
----

``deva`` 是一个基于 Python 的异步流式处理框架，让编写实时数据流处理管道、事件驱动程序和异步函数变得简单易用。

核心理念：

- **流式处理**：用 ``Stream`` 表达数据流动，通过管道操作符组合处理逻辑
- **事件驱动**：基于消息总线和路由机制实现松耦合组件通信
- **定时调度**：内置定时器和调度器，轻松实现周期性任务和计划任务
- **持久化**：集成 SQLite 存储，支持事件回放和状态持久化
- **可视化**：一键生成 Web 监控页面，实时观察数据流状态

典型应用场景：

- 实时日志监控与告警
- 流式 ETL 和数据清洗
- 定时任务和数据采集
- 量化交易策略执行
- 事件驱动的微服务


快速开始
--------

安装后，5 分钟快速体验 Deva 的核心功能。

1. 安装 Deva
~~~~~~~~~~~~

.. code-block:: bash

   pip install deva

2. 第一个流处理程序
~~~~~~~~~~~~~~~~~~~

创建 ``hello.py``：

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

运行：

.. code-block:: bash

   python hello.py

输出：

.. code-block:: text

   [2026-02-26 10:00:00] INFO: log: 4
   [2026-02-26 10:00:00] INFO: log: 6
   [2026-02-26 10:00:00] INFO: log: 8


3. 定时任务示例
~~~~~~~~~~~~~~~

.. code-block:: python

   from deva import timer, log, Deva
   import time

   # 每隔 1 秒获取当前时间并输出日志
   timer(interval=1, func=lambda: time.strftime('%H:%M:%S'), start=True) >> log

   Deva.run()


4. Web 可视化
~~~~~~~~~~~~~~

.. code-block:: python

   from deva import timer, Deva

   # 创建实时数据流
   s = timer(interval=1, func=lambda: {'time': __import__('time').time()}, start=True)

   # 一键生成 Web 页面
   s.webview('/realtime')

   Deva.run()

访问 ``http://127.0.0.1:9999/realtime`` 查看实时数据。


核心特性
--------

流式处理算子
~~~~~~~~~~~~

- **转换**：``map()``, ``starmap()``, ``flatten()``
- **过滤**：``filter()``, ``unique()``, ``distinct()``
- **窗口**：``sliding_window()``, ``timed_window()``, ``partition()``
- **聚合**：``reduce()``, ``accumulate()``, ``collect()``
- **合流**：``zip()``, ``zip_latest()``, ``combine_latest()``, ``union()``
- **缓冲**：``buffer()``, ``rate_limit()``, ``delay()``

事件驱动
~~~~~~~~

- **消息总线**：全局 ``bus`` 对象，支持跨进程通信
- **路由机制**：``@bus.route()`` 装饰器实现事件分发
- **主题订阅**：``Topic`` 类支持发布订阅模式
- **条件触发**：``when()`` 函数实现条件驱动

定时与调度
~~~~~~~~~~

- **定时器**：``timer()`` 支持固定间隔和周期函数
- **调度器**：``scheduler()`` 支持 CRON 表达式和复杂计划
- **事件监听**：进程启动/退出事件处理

持久化存储
~~~~~~~~~~

- **DBStream**：流式 SQLite 存储
- **事件回放**：支持时间范围回放和历史重放
- **命名空间**：``NB()`` 全局单例工厂

可视化与监控
~~~~~~~~~~~~

- **WebView**：一键生成流数据监控页面
- **管理面板**：内置 Admin UI 管理界面
- **日志系统**：统一的结构化日志输出


安装指南
--------

基础安装
~~~~~~~~

.. code-block:: bash

   pip install deva

或使用 pip3：

.. code-block:: bash

   pip3 install deva

可选依赖
~~~~~~~~

启用 Redis 消息总线（跨进程通信）：

.. code-block:: bash

   pip install deva[redis]

启用全文检索：

.. code-block:: bash

   pip install deva[search]

启用 LLM 集成：

.. code-block:: bash

   pip install deva[llm]

开发环境安装
~~~~~~~~~~~~

.. code-block:: bash

   git clone https://github.com/sostc/deva.git
   cd deva
   pip install -e ".[dev]"

验证安装
~~~~~~~~

.. code-block:: python

   import deva
   print(deva.__version__)


使用示例
--------

实时日志监控
~~~~~~~~~~~~

监控日志文件并告警错误：

.. code-block:: python

   from deva import from_textfile, log, warn, Deva

   # 监控日志文件
   s = from_textfile('/var/log/app.log', start=True)

   # 过滤错误日志并告警
   s.filter(lambda line: 'ERROR' in line) >> warn

   # 所有日志输出
   s >> log

   Deva.run()

数据采集与存储
~~~~~~~~~~~~~~~

.. code-block:: python

   from deva import timer, NB, log, Deva

   # 定时获取数据
   s = timer(interval=5, func=lambda: {'price': 100.5}, start=True)

   # 存储到命名空间
   db = NB('prices', key_mode='time')
   s >> db

   # 同时输出日志
   s >> log

   Deva.run()

跨进程通信
~~~~~~~~~~

生产者：

.. code-block:: python

   from deva import bus, timer, Deva

   # 每秒发送数据到 bus
   timer(interval=1, func=lambda: {'event': 'tick'}) >> bus

   Deva.run()

消费者：

.. code-block:: python

   from deva import bus, log, Deva

   # 从 bus 接收并处理数据
   bus.filter(lambda x: isinstance(x, dict)).map(lambda x: x['event']) >> log

   Deva.run()

Web 可视化面板
~~~~~~~~~~~~~~

.. code-block:: python

   from deva import timer, Stream, Deva

   # 创建多个数据流
   s1 = timer(interval=1, func=lambda: '流 1 数据', start=True, name='流 1')
   s2 = timer(interval=2, func=lambda: '流 2 数据', start=True, name='流 2')

   # 生成 Web 页面
   s1.webview('/stream1')
   s2.webview('/stream2')

   # 启动服务
   Deva.run()


文档导航
--------

================== ==================
文档类型           链接
================== ==================
快速开始           `source/quickstart.rst`_
使用手册           `source/manual_cn.rst`_
安装指南           `source/installation.rst`_
示例集合           `deva/examples/README.md`_
API 参考           `source/api.rst`_
================== ==================

完整文档目录详见项目仓库：https://github.com/sostc/deva/tree/master/docs


社区与支持
----------

源代码仓库
~~~~~~~~~~

- GitHub: https://github.com/sostc/deva

问题反馈
~~~~~~~~

- Issue Tracker: https://github.com/sostc/deva/issues

许可证
------

Copyright © 2018-2026 spark

本项目采用 MIT 许可证。详见 `LICENSE`_ 文件。

.. _LICENSE: https://github.com/sostc/deva/blob/master/LICENSE
.. _source/quickstart.rst: source/quickstart.rst
.. _source/manual_cn.rst: source/manual_cn.rst
.. _source/installation.rst: source/installation.rst
.. _source/usage.rst: source/usage.rst
.. _source/api.rst: source/api.rst
.. _deva/examples/README.md: deva/examples/README.md
