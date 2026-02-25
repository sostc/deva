API 参考
========

.. contents:: 目录
   :depth: 2
   :local:

概述
----

本文档提供 Deva 所有公共 API 的详细参考说明。

核心模块
--------

Stream - 流处理核心
~~~~~~~~~~~~~~~~~~~

.. automodule:: deva.stream
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

Compute - 计算算子
~~~~~~~~~~~~~~~~~~

.. automodule:: deva.compute
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

Sources - 数据源
~~~~~~~~~~~~~~~~

.. automodule:: deva.sources
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

事件与调度
----------

Timer - 定时器
~~~~~~~~~~~~~~

.. automodule:: deva.timer
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

Scheduler - 调度器
~~~~~~~~~~~~~~~~~~

.. automodule:: deva.scheduler
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

Bus - 消息总线
~~~~~~~~~~~~~~

.. automodule:: deva.bus
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

Topic - 主题
~~~~~~~~~~~~

.. automodule:: deva.topic
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

存储与持久化
------------

DBStream - 数据库流
~~~~~~~~~~~~~~~~~~~

.. automodule:: deva.dbstream
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

Namespace - 命名空间
~~~~~~~~~~~~~~~~~~~~

.. automodule:: deva.namespace
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

Store - 存储
~~~~~~~~~~~~

.. automodule:: deva.store
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

可视化与管理
------------

Page - 页面服务
~~~~~~~~~~~~~~~

.. automodule:: deva.page
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

Admin - 管理面板
~~~~~~~~~~~~~~~~

.. automodule:: deva.admin
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

扩展功能
--------

HTTP - HTTP 客户端
~~~~~~~~~~~~~~~~~~

.. automodule:: deva.http
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

Search - 全文检索
~~~~~~~~~~~~~~~~~

.. automodule:: deva.search
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

Endpoints - 输出端
~~~~~~~~~~~~~~~~~~

.. automodule:: deva.endpoints
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

LLM - 大语言模型
~~~~~~~~~~~~~~~~

.. automodule:: deva.llm
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

工具函数
--------

日志函数
~~~~~~~~

.. code-block:: python

   from deva import log, warn, debug

   "消息" >> log
   {"level": "warning", "msg": "警告"} >> warn

快捷工厂
~~~~~~~~

.. code-block:: python

   from deva import NS, NT, NB, NW

   s = NS("stream_name")  # 命名 Stream
   t = NT("topic_name")   # 命名 Topic
   db = NB("table_name")  # 命名 DBStream
   page = NW("page_name") # 命名 PageServer

事件处理
~~~~~~~~

.. code-block:: python

   from deva import when

   when('open', source=bus).then(lambda: print("开盘"))

Deva 类
~~~~~~~

.. automodule:: deva.core
   :members: Deva
   :undoc-members:
   :show-inheritance:
   :member-order: bysource


索引
----

* :ref:`genindex`
* :ref:`modindex`
