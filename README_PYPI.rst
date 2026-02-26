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

.. image:: https://img.shields.io/pypi/l/deva.svg
   :target: https://github.com/sostc/deva/blob/master/LICENSE
   :alt: License

|

``deva`` 是一个基于 Python 的异步流式处理框架，让编写实时数据流处理管道、事件驱动程序和异步函数变得简单易用。

🚀 核心理念
-----------

- **流式处理**：用 ``Stream`` 表达数据流动，通过管道操作符组合处理逻辑
- **事件驱动**：基于消息总线和路由机制实现松耦合组件通信
- **定时调度**：内置定时器和调度器，轻松实现周期性任务和计划任务
- **持久化**：集成 SQLite 存储，支持事件回放和状态持久化
- **可视化**：一键生成 Web 监控页面，实时观察数据流状态

📦 典型应用场景
---------------

- 实时日志监控与告警
- 流式 ETL 和数据清洗
- 定时任务和数据采集
- 量化交易策略执行
- 事件驱动的微服务
- AI 工作流编排

⚡ 快速开始
-----------

1. 安装
~~~~~~~

.. code-block:: bash

   pip install deva

2. 第一个流处理程序
~~~~~~~~~~~~~~~~~~~

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

运行结果：

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
~~~~~~~~~~~~~

.. code-block:: python

   from deva import timer, Deva

   # 创建实时数据流
   s = timer(interval=1, func=lambda: {'time': __import__('time').time()}, start=True)

   # 一键生成 Web 页面
   s.webview('/realtime')

   Deva.run()

访问 ``http://127.0.0.1:9999/realtime`` 查看实时数据。

📚 主要功能模块
---------------

核心模块
~~~~~~~~

- **Stream** - 流式处理核心，支持 map/filter/reduce/concat 等操作符
- **Bus** - 消息总线，支持发布/订阅模式
- **Timer/Scheduler** - 定时器和调度器
- **Namespace (NB)** - 命名空间数据存储
- **DBStream** - 持久化流，支持事件回放

Admin UI
~~~~~~~~

- **策略管理** - 可视化创建和管理交易策略
- **数据源管理** - 配置和监控数据源
- **任务管理** - 任务调度和执行监控
- **AI Studio** - AI 代码生成和智能对话
- **文档中心** - 完整的在线文档

🔧 安装选项
-----------

基础安装
~~~~~~~~

.. code-block:: bash

   pip install deva

开发环境
~~~~~~~~

.. code-block:: bash

   pip install deva[dev]

📖 文档资源
-----------

- **GitHub**: https://github.com/sostc/deva
- **PyPI**: https://pypi.org/project/deva/
- **完整文档**: https://github.com/sostc/deva/tree/master/docs

文档目录：

- 快速开始指南
- 安装指南
- 使用手册
- 最佳实践
- 故障排查
- API 参考

🤝 社区与支持
-------------

源代码仓库
~~~~~~~~~~

- GitHub: https://github.com/sostc/deva

问题反馈
~~~~~~~~

- Issue Tracker: https://github.com/sostc/deva/issues

📄 许可证
---------

Copyright © 2018-2026 spark

本项目采用 MIT 许可证。详见 `LICENSE <https://github.com/sostc/deva/blob/master/LICENSE>`_ 文件。
